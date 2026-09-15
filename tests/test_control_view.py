"""Original-information forks and honest, aligned recorded visualisations."""

import copy
import gzip
import json
from pathlib import Path

import pytest

from methane import control_view as control


def load_result():
    with gzip.open(Path(__file__).parent / "fixtures/browser-demo-v2.json.gz", "rt") as stream:
        return json.load(stream)


@pytest.fixture
def result():
    return load_result()


def test_previous_plan_aligns_absolute_intervals_and_never_fabricates_missing_points(result):
    before = copy.deepcopy(result)
    view = control.describe(result, "MPC · methane", 12)
    assert view["previous"][0]["hour"] == 12
    assert view["previous"][0]["time"] == view["points"][0]["time"]
    assert view["previous"][-1] is None  # Previous forecast ends one interval earlier.
    assert view["estimate"] == result["records"]["MPC · methane"][12]["decision"]["estimate"]
    assert "state" not in view and "retrospective_truth" not in view
    assert result == before
    result["records"]["MPC · methane"][11]["decision"]["forecast"]["times"][1] = "wrong vintage"
    assert control.describe(result, "MPC · methane", 12)["previous"][0] is None
    del result["records"]["MPC · methane"][12]["decision"]["plan"]["trajectory"]
    assert control.describe(result, "MPC · methane", 12)["points"][0]["state"] == {}
    assert all(p is None for p in control.describe(result, "Greedy", 0)["previous"])


def test_future_and_execution_truth_cannot_change_comparison_packet(result):
    original = control.prepare(result, "MPC · methane", 12)
    row = result["records"]["MPC · methane"][12]
    row["state"]["battery_kwh"] = 0
    row["applied"]["electrolyser_kw"] = 0
    row["observations_after"]["temperature_c"] = -123
    result["records"]["MPC · methane"][13:] = []
    result["weather"]["truth"] = {"pv_kw": [999999]}
    result["retrospective_truth"] = {"fault": "changed"}
    assert control.prepare(result, "MPC · methane", 12) == original
    assert "records" not in original and "observations_after" not in original


def test_policies_share_inputs_original_costs_service_and_probe_contract(result, monkeypatch):
    d = result["records"]["MPC · methane"][12]["decision"]
    d["probe"] = True
    d["probe_policy_revision"] = 2
    d["capacity_used_kw"] = 300
    d["diagnosis"]["capacity_kw"] = 225
    d["forecast"]["service_kw"] = [12] * 24
    d["forecast"]["electrolyser_isolated"] = [False] * 24
    packet = control.prepare(result, "MPC · methane", 12)
    original = copy.deepcopy(packet)
    calls = []

    def fake(p, state, forecast, capacity, costs, objective, seconds, **kwargs):
        calls.append((state, copy.deepcopy(forecast), capacity, costs, kwargs))
        forecast["pv_kw"][0] = -999  # Even a misbehaving adapter cannot affect the next policy.
        return dict(predicted=None, solver={"status": "time-limited"}, trajectory=[])

    monkeypatch.setattr(control, "plan", fake)
    output = control.compare(packet)
    assert output["status"] == "incomplete"
    assert len(calls) == 3
    assert calls[0] == calls[1] == calls[2]
    assert calls[0][4]["allow_fallback"] is False
    assert calls[0][4]["minimum_ely"] == 300
    assert calls[0][4]["dependable_capacity"] == 225
    assert calls[0][1]["service_kw"] == [12] * 24
    assert calls[0][3].co2_eur_per_kg == result["config"]["costs"]["co2_eur_per_kg"]
    assert packet == original
    assert {p["information_id"] for p in output["predictions"].values()} == {
        packet["information_id"]
    }


def test_conditional_recovery_is_not_silently_replaced_by_a_plain_dispatcher(result):
    d = result["records"]["MPC · methane"][12]["decision"]
    d["recovery_planning"] = {"status": "scheduled"}
    with pytest.raises(ValueError, match="conditional"):
        control.prepare(result, "MPC · methane", 12)
    view = control.describe(result, "MPC · methane", 12)
    assert view["points"] and not view["comparison"]["available"]


def test_real_predictions_reconcile_and_preserve_completed_run(result):
    packet = control.prepare(result, "MPC · methane", 12)
    packet["seconds"] = 0.1
    original = copy.deepcopy(result)
    output = control.compare(packet)
    assert output["status"] == "complete"
    for value in output["predictions"].values():
        assert value["predicted"]["methane_kg"] == pytest.approx(
            sum(p["action"]["methane_kg"] for p in value["points"])
        )
        assert value["predicted"]["ending"] == value["points"][-1]["state"]
        assert all(
            p["action"]["charge_kw"] * p["action"]["discharge_kw"] < 1e-4 for p in value["points"]
        )
        assert value["solver"]["status"]
    assert result == original
