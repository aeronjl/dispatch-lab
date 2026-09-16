"""An investigation preserves evidence without granting notes or future data authority."""

import copy
import json

import pytest
from fastapi import HTTPException
from test_control_view import load_result

from methane import control_view as control
from methane import investigations as inv
from methane.model_service import register
from methane.siting.store import Store


@pytest.fixture
def result():
    return load_result()


def draft(**changes):
    return inv.Draft(
        title="A difficult afternoon",
        start=10,
        end=16,
        focus_hour=12,
        component="battery",
        pins=[12],
        **changes,
    )


def test_period_totals_are_execution_not_sensor_or_forecast_values(result):
    before = copy.deepcopy(result)
    value = inv.overview(result, "MPC · methane")
    window = inv.period(value["points"], 10, 16)
    rows = result["records"]["MPC · methane"][10:16]
    assert window["totals"]["methane_kg"] == pytest.approx(
        sum(r["applied"]["methane_kg"] for r in rows)
    )
    assert window["totals"]["shortfall_kg"] == pytest.approx(
        sum(max(0, r["requested"]["methane_kg"] - r["applied"]["methane_kg"]) for r in rows)
    )
    assert value["points"][12]["bindings"] == rows[2]["decision"]["evidence"]["bindings"]
    assert result == before
    result["records"]["MPC · methane"][10]["applied"].pop("methane_kg")
    assert (
        inv.period(inv.overview(result, "MPC · methane")["points"], 10, 16)["totals"]["methane_kg"]
        is None
    )
    for bounds in ((12, 12), (16, 10), (-1, 10), (0, 10000)):
        with pytest.raises(ValueError):
            inv.period(value["points"], *bounds)


def test_saved_editions_bind_notes_pins_and_predictions_and_leave_source_unchanged(
    result, tmp_path
):
    store, before = Store(tmp_path), copy.deepcopy(result)
    packet = control.prepare(result, "MPC · methane", 12)
    packet["seconds"] = 0.1
    outcome = control.compare(packet)
    key = inv.save_comparison(result, "MPC · methane", 12, packet, outcome, store)
    saved = inv.save(result, "MPC · methane", draft(comparisons=[key]), store)
    edited = inv.save(
        result,
        "MPC · methane",
        draft(parent=saved["id"], finding="A hypothesis, not a causal proof.", comparisons=[key]),
        store,
    )
    assert edited["id"] != saved["id"]
    assert store.get("investigation", saved["id"])["draft"]["finding"] == ""
    assert saved["evidence"][0]["estimate"] == packet["state"]
    assert saved["comparisons"][0]["inputs"] == packet
    assert saved["comparisons"][0]["output"] == outcome
    assert saved["source"]["original_integrity"] == result.get("integrity_sha256")
    assert result == before
    # A portable JSON contains the complete saved evidence without needing a job or network.
    assert json.loads(json.dumps(saved))["comparisons"][0]["output"] == outcome
    with pytest.raises(ValueError, match="another"):
        inv.save(result, "Greedy", draft(comparisons=[key]), store)
    different = copy.deepcopy(result)
    different["integrity_sha256"] = "changed-edition"
    with pytest.raises(ValueError, match="another"):
        inv.save(different, "MPC · methane", draft(comparisons=[key]), store)
    bad = draft(comparisons=[key]).model_copy(update={"start": 13, "focus_hour": 13, "pins": []})
    with pytest.raises(ValueError, match="outside"):
        inv.save(result, "MPC · methane", bad, store)


def test_transport_does_not_accept_browser_calculations_and_export_escapes_notes(
    result, tmp_path, monkeypatch
):
    monkeypatch.setattr(inv, "Store", lambda: Store(tmp_path))
    c = dict(
        token=register(result),
        run_id=result["run_id"],
        controller="MPC · methane",
        key="generation-7",
    )
    request = inv.Request(**c, operation="save", draft=draft(finding='<script>alert("x")</script>'))
    response = inv.handle(request)
    assert response["key"] == c["key"]
    assert "<script>alert" not in response["html"] and "&lt;script&gt;" in response["html"]
    assert "http" not in response["html"].split("<style>")[1].split("</style>")[0]
    assert (
        inv.handle(inv.Request(**c, operation="overview"))["saved"][0]["id"]
        == response["record"]["id"]
    )
    reopened = inv.handle(inv.Request(**c, operation="load", id=response["record"]["id"]))
    assert reopened["record"] == response["record"]
    with pytest.raises(ValueError):
        inv.Request(**c, operation="save", draft=draft(), predictions={"methane": 999})
    with pytest.raises(HTTPException) as exc:
        inv.handle(inv.Request(**{**c, "token": "wrong"}, operation="overview"))
    assert exc.value.status_code == 410
    with pytest.raises(HTTPException):
        inv.handle(inv.Request(**c, operation="load", id="../escape"))


@pytest.mark.parametrize("alternative", ["battery", "electrolyser", "reactor", "co2"])
def test_real_alternatives_reconcile_and_only_restrict_declared_information(result, alternative):
    packet = control.prepare_alternative(result, "MPC · methane", 12, alternative)
    packet["seconds"] = 0.1
    before = copy.deepcopy(packet)
    output = control.compare_alternative(packet)
    assert len(output["predictions"]) == 2
    assert packet == before
    for p in output["predictions"].values():
        assert p["information_id"] == packet["information_id"]
        if p["predicted"] is not None:
            assert p["predicted"]["methane_kg"] == pytest.approx(
                sum(v["action"]["methane_kg"] for v in p["points"])
            )
            assert p["predicted"]["ending"] == p["points"][-1]["state"]
        assert not p["solver"].get("fallback_used")
    revised = list(output["predictions"].values())[1]
    if revised["predicted"] is not None:
        if alternative == "battery":
            assert revised["points"][0]["action"]["discharge_kw"] == pytest.approx(0)
        if alternative == "electrolyser":
            assert revised["points"][0]["action"]["electrolyser_kw"] == pytest.approx(0)
        if alternative == "co2":
            assert sum(p["deliveries_kg"] for p in revised["points"]) < sum(
                packet["forecast"]["deliveries_kg"]
            )


def test_alternative_packet_remains_causal_and_incomplete_results_are_honest(result, monkeypatch):
    packet = control.prepare_alternative(result, "MPC · methane", 12, "battery")
    result["weather"]["truth"] = {"pv_kw": [999999]}
    result["records"]["MPC · methane"][12]["observations_after"] = {"power_kw": 999999}
    result["records"]["MPC · methane"][13:] = []
    assert packet == control.prepare_alternative(result, "MPC · methane", 12, "battery")
    monkeypatch.setattr(
        control,
        "plan",
        lambda *a, **k: dict(
            predicted=None, solver=dict(status="time-limited", fallback_used=False), trajectory=[]
        ),
    )
    output = control.compare_alternative(packet)
    assert output["status"] == "incomplete"
    assert all(p["predicted"] is None for p in output["predictions"].values())


def test_missing_original_identity_is_not_invented(result):
    result.pop("integrity_sha256", None)
    result.pop("provenance", None)
    source = inv.identity(result)
    assert source["original_integrity"] is None and source["original_source"] is None
    assert source["recording_fingerprint"]  # Local binding, not reconstructed provenance.
