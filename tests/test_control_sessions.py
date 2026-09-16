"""Actual paused simulator, capability boundaries and exactly-once dispatch."""

import copy
import json
import time
from dataclasses import replace

import pytest
from fastapi import HTTPException
from test_control_view import load_result

from methane import control_sessions as sessions
from methane.config import Config
from methane.control_port import observation, preview
from methane.model_service import register
from methane.simulation import run


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPATCH_CONTROL_DIR", str(tmp_path))
    yield
    sessions.cleanup()


def call(context, operation, agent=False, **kwargs):
    return (sessions.agent if agent else sessions.handle)(
        sessions.Request(**context, operation=operation, **kwargs)
    )


def create(hours=2):
    source = load_result()
    answer = call(
        dict(token=register(source), run_id=source["run_id"], controller="Greedy"),
        "create",
        hours=hours,
    )
    return source, dict(session_id=answer["session_id"], credential=answer["owner_key"])


def await_state(context, status="waiting", revision=0):
    end = time.monotonic() + 25
    while time.monotonic() < end:
        answer = call(context, "observe")
        s = answer["state"]
        assert s["status"] not in ("failed", "interrupted"), s
        if s["status"] == status and s["revision"] == revision:
            return answer
        time.sleep(0.05)
    pytest.fail(str(answer))


def test_real_session_reference_manual_archive_and_immutable_source():
    source, owner = create()
    before = copy.deepcopy(source)
    first = await_state(owner)
    assert first["observation"]["hour"] == 0
    proposal = call(owner, "preview", revision=0)
    assert call(owner, "observe")["state"]["revision"] == 0
    args = dict(
        revision=0,
        proposal_id=proposal["proposal_id"],
        request_id="first",
        reason="Use the reference plan",
    )
    accepted = call(owner, "advance", **args)
    assert call(owner, "advance", **args) == accepted
    second = await_state(owner, revision=1)
    assert len(second["receipts"]) == 1
    actions = {k: 0.0 for k in proposal["preview"]["requested"]}
    manual = call(owner, "preview", revision=1, actions=actions)
    assert manual["preview"]["mode"] == "manual"
    call(
        owner,
        "advance",
        revision=1,
        proposal_id=manual["proposal_id"],
        request_id="second",
        reason="Hold process loads for this interval",
    )
    final = await_state(owner, "complete", 2)
    assert all(r["audits_passed"] for r in final["receipts"])
    recording = sessions.recording(
        **dict(identifier=owner["session_id"], owner_key=owner["credential"])
    )
    assert (
        recording["records"]["Greedy"][1]["decision"]["external_control"]["reason"]
        == "Hold process loads for this interval"
    )
    assert recording["provenance"]["external_control"]["origin"] == source["run_id"]
    assert source == before


def test_agent_permissions_revoke_pause_stale_and_information_boundary():
    source, owner = create()
    await_state(owner)
    grant = call(owner, "grant", permission="observe")
    agent = dict(session_id=owner["session_id"], credential=grant["agent_token"])
    data = call(agent, "observe", agent=True)
    text = json.dumps(data)
    for private in (
        "retrospective_truth",
        "owner_hash",
        "agent_hash",
        "faults",
        "uncertainty_world",
        "observations_after",
        "recording.json",
    ):
        assert f'"{private}"' not in text
    with pytest.raises(HTTPException):
        call(agent, "preview", agent=True, revision=0)
    grant = call(owner, "grant", permission="advance")
    with pytest.raises(HTTPException):
        call(agent, "observe", agent=True)
    agent["credential"] = grant["agent_token"]
    proposal = call(agent, "preview", agent=True, revision=0)
    call(owner, "pause")
    with pytest.raises(HTTPException):
        call(
            agent,
            "advance",
            agent=True,
            revision=0,
            proposal_id=proposal["proposal_id"],
            request_id="a",
            reason="test",
        )
    call(owner, "resume")
    with pytest.raises(HTTPException):
        call(
            agent,
            "advance",
            agent=True,
            revision=0,
            proposal_id=proposal["proposal_id"],
            request_id="a",
            reason="test",
        )
    fresh = call(agent, "preview", agent=True, revision=0)
    call(
        agent,
        "advance",
        agent=True,
        revision=0,
        proposal_id=fresh["proposal_id"],
        request_id="b",
        reason="Agent follows bounded policy",
    )
    updated = await_state(owner, revision=1)
    assert updated["receipts"][0]["actor"] == "agent"
    call(owner, "revoke")
    with pytest.raises(HTTPException):
        call(agent, "observe", agent=True)
    call(owner, "stop")


def test_port_rejects_hidden_or_invalid_inputs_and_preserves_causality():
    source = load_result()
    c = Config.from_dict(source["config"])
    row = source["records"]["Greedy"][12]
    public = observation(row["decision"], c.plant, c.costs, c.models, row["time"])
    row["state"]["battery_kwh"] = 99999
    source["retrospective_truth"] = []
    source["weather"]["truth"] = {}
    assert observation(row["decision"], c.plant, c.costs, c.models, row["time"]) == public
    actions = {k: 0.0 for k in preview(public)["requested"]}
    for change in (
        {"charge_kw": 1.0, "discharge_kw": 1.0},
        {"heater_kw": 999.0},
        {"charge_kw": float("nan")},
        {"true_capacity": 50.0},
    ):
        with pytest.raises(ValueError):
            preview(public, actions | change)
    public["recovery_protected"] = True
    with pytest.raises(ValueError, match="recovery"):
        preview(public, actions)
    assert preview(public)["mode"] == "reference"


def test_reference_port_preserves_execution_and_independent_balances():
    from methane.reference import audit

    class Reference:
        def start(self, *args):
            pass

        def decide(self, public):
            p = preview(public)
            return {**p, "trace": dict(actor="test", reason="Reference policy passthrough")}

        def completed(self, *args):
            pass

    config = Config()
    config = replace(
        config, scenario=replace(config.scenario, hours=14, horizon_hours=6, solver_seconds=0.05)
    )
    normal = run(config, strategies=["Greedy"])
    controlled = run(config, weather=normal["weather"], strategies=["Greedy"], control=Reference())
    assert normal["status"] == controlled["status"] == "complete"
    for a, b in zip(normal["records"]["Greedy"], controlled["records"]["Greedy"], strict=True):
        assert a["applied"] == pytest.approx(b["applied"], abs=1e-6)
        assert a["state"] == pytest.approx(b["state"], abs=1e-6)
    assert audit(controlled)["passed"]
    assert any(r["applied"]["electrolyser_kw"] > 0 for r in controlled["records"]["Greedy"])


def test_valid_request_without_power_is_visibly_projected_not_silently_relabelled():
    source = load_result()
    c = Config.from_dict(source["config"])
    row = source["records"]["Greedy"][0]
    public = observation(row["decision"], c.plant, c.costs, c.models, row["time"])
    public["forecast"]["pv_kw"][0] = 0
    public["estimate"]["battery_kwh"] = 0
    before = copy.deepcopy(public)
    actions = {k: 0.0 for k in preview(public)["requested"]}
    actions["electrolyser_kw"] = 300.0
    actions["heater_kw"] = 60.0
    result = preview(public, actions)
    trajectory = result["plan"]["trajectory"][0]
    assert result["requested"] == actions
    assert trajectory["applied"]["electrolyser_kw"] == 0
    assert trajectory["applied"]["heater_kw"] == 0
    assert all(a["passed"] for a in trajectory["audits"])
    assert public == before


def test_stop_expiry_and_unavailable_context_are_explicit():
    _, owner = create()
    await_state(owner)
    grant = call(owner, "grant", permission="advance")
    agent = dict(session_id=owner["session_id"], credential=grant["agent_token"])
    root = sessions.folder(owner["session_id"])
    meta = sessions.read(root / "meta.json")
    meta["expires_at"] = time.time() - 1
    sessions.write(root / "meta.json", meta)
    with pytest.raises(HTTPException, match="expired"):
        call(agent, "observe", agent=True)
    call(owner, "stop")
    final = await_state(owner, "cancelled", 0)
    assert final["receipts"] == []
    source = load_result()
    source["continuous_period"] = dict(start_hour=24)
    with pytest.raises(HTTPException, match="continued initial state"):
        call(dict(token=register(source), run_id=source["run_id"], controller="Greedy"), "create")


def test_external_recording_is_not_silently_recomputed_as_reference(tmp_path):
    from recompute import recompute

    source = load_result()
    source.setdefault("provenance", {})["external_control"] = dict(contract="dispatch-control/1")
    with pytest.raises(ValueError, match="External-control recording"):
        recompute(source, tmp_path / "rerun.json")
    assert not (tmp_path / "rerun.json").exists()
