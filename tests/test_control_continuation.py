"""P1 acceptance: frozen projects, private checkpoints, crash recovery and replay."""

import copy
import json
import signal
import time
from dataclasses import replace

import pytest
from fastapi import HTTPException
from test_control_sessions import await_state, call, create
from test_siting_production import fixture

from methane import control_sessions as sessions
from methane import control_sources
from methane.control_replay import replay
from methane.control_storage import committed
from methane.provenance import verify
from methane.siting import production, projects
from methane.siting.store import Store


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPATCH_CONTROL_DIR", str(tmp_path / "sessions"))
    store = Store(tmp_path / "sites")
    monkeypatch.setattr(control_sources, "Store", lambda: store)
    yield store
    sessions.cleanup()


def step(owner, hour, actions=None):
    await_state(owner, revision=hour)
    preview = call(owner, "preview", revision=hour, **({"actions": actions} if actions else {}))
    call(
        owner,
        "advance",
        revision=hour,
        proposal_id=preview["proposal_id"],
        request_id=f"request-{hour}-{preview['proposal_id']}",
        reason="P1 bounded acceptance",
    )
    return preview


def wait_exit(owner):
    worker = sessions._workers[owner["session_id"]]
    worker.wait(timeout=20)


def archive(owner):
    return sessions.recording(owner["session_id"], owner["credential"])


def test_restart_registry_loss_kill_uncommitted_action_and_continue():
    _, owner = create(hours=2)
    step(owner, 0)
    await_state(owner, revision=1)
    root = sessions.folder(owner["session_id"])
    worker = sessions._workers.pop(owner["session_id"])
    try:
        # A fresh app has no Popen object, but the inherited lease still owns the session.
        assert call(owner, "observe")["state"]["status"] == "waiting"
        with pytest.raises(HTTPException, match="still active"):
            call(owner, "recover")
    finally:
        sessions._workers[owner["session_id"]] = worker
    grant = call(owner, "grant", permission="advance")
    agent = {**owner, "credential": grant["agent_token"]}
    proposal = call(owner, "preview", revision=1)
    # Kill after API acceptance, before the worker can execute/commit it.
    worker.send_signal(signal.SIGSTOP)
    call(
        owner,
        "advance",
        revision=1,
        proposal_id=proposal["proposal_id"],
        request_id="lost",
        reason="Interrupted request",
    )
    worker.kill()
    worker.wait(timeout=10)
    saved = committed(root)
    assert saved["next_hour"] == 1 and len(saved["receipts"]) == 1
    call(owner, "recover")
    await_state(owner, revision=1)
    assert len(list(root.glob("uncommitted-1-*.json"))) == 1
    with pytest.raises(HTTPException):
        call(agent, "observe", agent=True)
    with pytest.raises(HTTPException, match="stale"):
        call(
            owner,
            "advance",
            revision=1,
            proposal_id=proposal["proposal_id"],
            request_id="lost",
            reason="Retry",
        )
    step(owner, 1)
    await_state(owner, "complete", 2)
    wait_exit(owner)
    first = archive(owner)
    call(owner, "extend", hours=1)
    step(owner, 2)
    final = await_state(owner, "complete", 3)
    assert [r["hour"] for r in final["receipts"]] == [0, 1, 2]
    result = archive(owner)
    verify(result)
    assert result["records"]["Greedy"][:2] == first["records"]["Greedy"]
    assert result["control_reproduction"]["ending_checkpoint"]["next_hour"] == 3
    assert result["continuous_period"]["start_hour"] == 0
    numerical, report = replay(result)
    assert report["status"] == "complete" and report["independent_reference_passed"]
    assert report["differences"] == []
    assert numerical["run_id"] != result["run_id"]
    assert all(not r["changed_fields"] for r in report["information"])


def test_project_inputs_utilities_and_saved_checkpoint(isolated):
    store = isolated
    design, env = fixture(store, hours=16)
    value = store.get("design", design)
    value["utilities"] = dict(water_lph=0, co2_deliveries=[dict(hour=13, kg=7)])
    design = store.put("design", value)
    study = production.create(
        store,
        name="Water-restricted site",
        cases=[dict(design_id=design, environment_id=env)],
        partition_hours=12,
    )
    production.execute(store, study["id"])
    original = production.inspect(store, study["id"])
    origin = dict(study_id=study["id"], case_id="case-001", start_hour=12, controller="Greedy")
    answer = call(origin, "create", hours=2)
    owner = dict(session_id=answer["session_id"], credential=answer["owner_key"])
    observed = await_state(owner, revision=12)["observation"]
    assert observed["forecast"]["site_supply"]["water_lph"] == 0
    assert observed["forecast"]["electrolyser_supply_limit_kw"][0] == 0
    assert observed["forecast"]["deliveries_kg"][:2] == [0, 7]
    actions = {k: 0.0 for k in observed["reference_plan"]["actions"][0]}
    actions["electrolyser_kw"] = 100.0
    p = step(owner, 12, actions)
    assert p["preview"]["plan"]["trajectory"][0]["applied"]["electrolyser_kw"] == 0
    step(owner, 13)
    await_state(owner, "complete", 14)
    result = archive(owner)
    assert result["records"]["Greedy"][0]["site_utilities"]["water_available_l"] == 0
    assert result["records"]["Greedy"][0]["applied"]["electrolyser_kw"] == 0
    assert result["records"]["Greedy"][1]["co2_delivered_kg"] == 7
    assert original == production.inspect(store, study["id"])
    _, report = replay(result)
    assert report["differences"] == [] and report["independent_reference_passed"]
    with pytest.raises(HTTPException, match="saved committed checkpoint"):
        call({**origin, "start_hour": 11}, "create", hours=1)
    text = json.dumps(call(owner, "observe"))
    for hidden in ('"checkpoint"', '"graph"', '"physical_faults"', '"control_reproduction"'):
        assert hidden not in text


def test_direct_project_retains_site_utilities(isolated):
    from methane.config import Config
    from methane.siting.catalogue import bootstrap
    from methane.siting.contracts import DeploymentDesign
    from methane.siting.geometry import centre

    site = bootstrap(isolated)[0]
    latitude, longitude = centre(site["geometry"])
    c = Config()
    c = replace(
        c,
        weather=replace(
            c.weather, latitude=latitude, longitude=longitude, timezone=site["timezone"]
        ),
    )
    design = isolated.put(
        "design",
        DeploymentDesign(
            name="Project utility check",
            site_revision=site["id"],
            config=c.to_dict(),
            utilities=dict(water_lph=0),
        ),
    )
    p = projects.create(isolated, site["id"], design_id=design)["project"]
    sources = call({}, "sources")
    assert sources["projects"][0]["id"] == p["id"]
    created = call(dict(project_id=p["id"], synthetic=True, controller="Greedy"), "create", hours=1)
    owner = dict(session_id=created["session_id"], credential=created["owner_key"])
    assert await_state(owner)["observation"]["forecast"]["site_supply"]["water_lph"] == 0
    step(owner, 0)
    await_state(owner, "complete", 1)
    assert archive(owner)["provenance"]["external_control"]["origin"]["project_revision"] == p["id"]


def test_recovery_rejects_tampered_inputs_and_changed_implementation():
    _, owner = create(hours=1)
    await_state(owner)
    call(owner, "stop")
    wait_exit(owner)
    root = sessions.folder(owner["session_id"])
    inputs = sessions.read(root / "input.json")
    changed = copy.deepcopy(inputs)
    changed["config"]["plant"]["solar_kw"] += 1
    sessions.write(root / "input.json", changed)
    with pytest.raises(HTTPException, match="inputs changed"):
        call(owner, "recover")
    sessions.write(root / "input.json", inputs)
    meta = sessions.read(root / "meta.json")
    meta["source_content_hash"] = "old-implementation"
    sessions.write(root / "meta.json", meta)
    with pytest.raises(HTTPException, match="implementation differs"):
        call(owner, "recover")


def test_replay_worker_new_edition_and_original_archive_immutable():
    _, owner = create(hours=1)
    step(owner, 0)
    await_state(owner, "complete", 1)
    wait_exit(owner)
    before = copy.deepcopy(archive(owner))
    started = call(owner, "replay")
    end = time.monotonic() + 25
    while time.monotonic() < end:
        result = call(owner, "observe")["replay"]
        if result["status"] != "running":
            break
        time.sleep(0.05)
    assert result["status"] == "complete", result
    assert result["differences"] == []
    assert archive(owner) == before
    edition = sessions.recording(owner["session_id"], owner["credential"], started["id"])
    assert edition["recorded_action_comparison"]["recorded_run_id"] == before["run_id"]
    assert verify(edition)
    assert result["source_matches"]


def test_agent_cannot_select_sources_recover_extend_or_replay():
    _, owner = create(hours=1)
    await_state(owner)
    grant = call(owner, "grant", permission="advance")
    agent = dict(session_id=owner["session_id"], credential=grant["agent_token"])
    for operation in ("sources", "recover", "extend", "replay", "cancel_replay", "create"):
        with pytest.raises(HTTPException) as error:
            call(agent, operation, agent=True)
        assert error.value.status_code == 403


def test_service_runtime_and_economic_prefix_survive_control_recovery(monkeypatch):
    from methane.config import Config, Scenario
    from methane.model_service import register
    from methane.service_economics import illustrative
    from methane.services.configuration import ServiceSystem
    from methane.simulation import run
    from methane.siting.checkpoint import unpack

    monkeypatch.setenv("DISPATCH_BATCH_WORKER", "1")
    c = Config(scenario=Scenario(hours=4, horizon_hours=6, solver_seconds=0.1))
    c = replace(
        c,
        field_operations=replace(c.field_operations, enabled=True),
        service_system=ServiceSystem(support_model="logistics/1"),
        service_economics=illustrative(c.costs),
    )
    source = run(c, strategies=["Greedy"])
    answer = call(
        dict(token=register(source), run_id=source["run_id"], controller="Greedy"),
        "create",
        hours=3,
    )
    owner = dict(session_id=answer["session_id"], credential=answer["owner_key"])
    step(owner, 0)
    await_state(owner, revision=1)
    root = sessions.folder(owner["session_id"])
    saved = committed(root)
    assert unpack(saved["checkpoint"]["graph"])["services"] is not None
    call(owner, "stop")
    wait_exit(owner)
    call(owner, "recover")
    step(owner, 1)
    step(owner, 2)
    await_state(owner, "complete", 3)
    r = archive(owner)
    numerical, report = replay(r)
    assert report["differences"] == []
    assert json.loads(
        json.dumps([row["field_operations"] for row in r["records"]["Greedy"]])
    ) == json.loads(json.dumps([row["field_operations"] for row in numerical["records"]["Greedy"]]))
    assert r["metrics"]["Greedy"]["total_eur"] == pytest.approx(
        numerical["metrics"]["Greedy"]["total_eur"]
    )
    assert (
        len(unpack(r["control_reproduction"]["ending_checkpoint"]["graph"])["service_cost_rows"])
        == 3
    )
    assert report["independent_reference_passed"], report["independent_reference_failures"]


def test_control_period_independent_check_detects_corruption():
    from methane.reference import audit

    _, owner = create(hours=1)
    step(owner, 0)
    await_state(owner, "complete", 1)
    result = archive(owner)
    assert audit(result)["passed"]
    changed = copy.deepcopy(result)
    changed["records"]["Greedy"][0]["state"]["battery_kwh"] += 1
    assert not audit(changed)["passed"]


def test_offline_bundle_retains_checkpoint_and_recompute_route(tmp_path):
    import subprocess
    import sys

    from methane.bundle import make, unpack
    from methane.bundle_runtime import check
    from recompute import recompute

    _, owner = create(hours=1)
    step(owner, 0)
    await_state(owner, "complete", 1)
    result = archive(owner)
    path = make(result, tmp_path / "portable.zip")
    restored = tmp_path / "restored"
    unpack(path, restored)
    receipt = check(restored)
    assert receipt["reference_passed"] and receipt["integrity_passed"], receipt
    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(restored / "check_bundle.py"), str(restored)],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stdout + completed.stderr
    report = recompute(result, tmp_path / "comparison.json")
    assert report["independent_reference_passed"] and report["differences"] == []
    assert archive(owner) == result


def test_cancelled_replay_is_explicit_and_does_not_advance_session():
    _, owner = create(hours=1)
    step(owner, 0)
    await_state(owner, "complete", 1)
    wait_exit(owner)
    original = archive(owner)
    call(owner, "replay")
    call(owner, "cancel_replay")
    end = time.monotonic() + 25
    while time.monotonic() < end:
        value = call(owner, "observe")
        if value["replay"]["status"] != "running":
            break
        time.sleep(0.05)
    assert value["replay"]["status"] == "cancelled"
    assert value["replay"]["replayed_intervals"] == 0
    assert archive(owner) == original
