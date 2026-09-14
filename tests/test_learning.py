"""Independent expectations and immutable, version-aware documentation consumers."""

import copy
import json
import math

import pytest

from methane.documentation import bindings, catalogue, check_freshness, read, recorded
from methane.learning import defaults, evaluate, teaching_trace
from methane.model_topics import TOPICS


@pytest.mark.parametrize("topic", TOPICS)
def test_each_essay_has_executable_default_and_bound_controls(topic):
    page = catalogue()["topics"][topic]
    answer = evaluate(topic)
    assert answer["status"] == "complete", answer
    assert answer["inputs"] == defaults(topic)
    assert page["passages"] and page["assumptions"] and page["evidence"]
    assert all(a["passed"] for a in answer["checks"])
    assert answer["metrics"] and answer["series"]
    assert answer["execution_identity"] == bindings()[topic]


def test_battery_independent_balance_swap_and_round_trip():
    expected = 200 + math.sqrt(0.81) * 100
    for impl in ("affine/1", "loss-ledger/1"):
        r = evaluate("battery", {"efficiency": 0.81, "implementation": impl})
        assert r["metrics"][0]["value"] == pytest.approx(expected)
        assert r["metrics"][2]["value"] == pytest.approx(10)
        assert r["independent_expected"]["100 kWh cycle return"] == 81
    assert (
        evaluate("battery", {"energy": 0, "charge": 0, "discharge": 100})["status"] == "infeasible"
    )
    assert evaluate("battery", {"energy": 800})["status"] == "infeasible"
    assert evaluate("battery", {"discharge": 100})["status"] == "infeasible"


def test_recorded_decision_estimate_is_preserved_without_using_later_state():
    from methane.config import Config, Scenario
    from methane.simulation import run

    source = run(Config(scenario=Scenario(hours=2)), strategies=("Greedy",))
    row = source["records"]["Greedy"][0]
    estimate = copy.deepcopy(row["decision"]["estimate"])
    row["state"]["battery_kwh"] = 123456
    for topic in ("battery", "controllers", "recovery"):
        value = recorded(source, topic, "Greedy", 0)
        assert value["estimated_before"] == estimate
        if topic == "controllers":
            assert value["calculation"]["estimated_state"] == estimate
        value["estimated_before"]["battery_kwh"] = -1
        assert row["decision"]["estimate"] == estimate


def test_independent_gas_and_electrolysis_examples():
    x = evaluate("hydrogen", {"inventory": 10, "inflow": 8, "outflow": 5})
    assert x["metrics"][0]["value"] == 13
    assert evaluate("hydrogen", {"inventory": 60})["status"] == "infeasible"
    x = evaluate("co2", {"inventory": 950, "delivery": 300, "arrival": 0, "outflow": 20})
    assert x["steps"][0]["accepted_kg"] == 50
    assert x["steps"][0]["rejected_kg"] == 250
    assert x["metrics"][0]["value"] == 880
    assert evaluate("co2", {"inventory": 0})["status"] == "infeasible"
    x = evaluate("electrolyser")
    assert x["metrics"][0]["value"] == 15
    assert x["metrics"][1]["value"] == 135
    assert x["metrics"][2]["value"] == 40
    assert evaluate("electrolyser", {"load": 100})["status"] == "infeasible"


def test_independent_thermal_first_interval_and_chemistry():
    x = evaluate("reactor")
    first = x["steps"][0]
    assert first["mode"] == "warming"
    assert first["requested_methane_kg"] == 0
    assert first["production_demand_kg"] == 10
    expected = 20 + 60 / 0.08 * (1 - math.exp(-0.08 / 0.3))
    assert first["temperature_c"] == pytest.approx(expected)
    for s in x["steps"]:
        assert s["co2_consumed_kg"] + s["h2_consumed_kg"] == pytest.approx(
            s["methane_kg"] + s["water_produced_kg"]
        )
        assert s["reaction_heat_kwh"] == pytest.approx(s["methane_kg"] * 165000 / 16 / 3600)
        if s["methane_kg"]:
            assert 250 <= s["temperature_c"] <= 400
    cut = evaluate("reactor", {"cutoff": 4})
    assert any(s["forced_trip"] for s in cut["steps"])
    assert evaluate("reactor", {"methane": 1})["status"] == "incomplete"


def test_forecast_availability_missing_and_dst():
    before = evaluate("weather", {"hour": 11})
    after = evaluate("weather", {"hour": 12})
    assert before["forecast"]["source"]["id"] == "teaching-issue-0"
    assert after["forecast"]["source"]["id"] == "teaching-issue-6"
    assert before["series"][1]["label"] == "Synthetic historical reference"
    assert before["series"][0]["points"] != before["series"][1]["points"]
    assert evaluate("weather", {"missing": "yes"})["status"] == "incomplete"
    assert "+01:00" in before["dst_example"][0]
    assert "+00:00" in before["dst_example"][1]
    assert evaluate("weather", {"hour": 6, "lag": 12})["status"] == "incomplete"


def test_diagnosis_cases_and_future_isolation():
    normal = evaluate("diagnosis", {"fault": "normal"})
    capacity = evaluate("diagnosis", {"fault": "capacity"})
    flow = evaluate("diagnosis", {"fault": "flow"})
    low = evaluate("diagnosis", {"fault": "low activity"})
    assert normal["metrics"][1]["value"] == 0
    assert capacity["metrics"][1]["value"] == 1
    assert flow["metrics"][1]["value"] == 1
    assert any(s["diagnosis"]["flow_isolated"] for s in flow["steps"])
    assert all(s["diagnosis"]["status"] == "insufficient evidence" for s in low["steps"])
    assert normal["steps"][:3] == capacity["steps"][:3] == flow["steps"][:3]
    assert any(
        s["diagnosis"]["status"] == "ambiguous"
        for s in evaluate("diagnosis", {"fault": "ambiguous"})["steps"]
    )
    assert any(s["probe"] for s in capacity["steps"])


def test_repricing_keeps_trace_and_no_double_allowances():
    original = copy.deepcopy(teaching_trace())
    a = evaluate("economics")
    b = evaluate("economics", {"price": 3, "co2_price": 0.3, "life": 10})
    assert a["physical_trace_sha256"] == b["physical_trace_sha256"]
    usage = evaluate("economics", {"reactor_life": 10000})
    assert usage["physical_trace_sha256"] == a["physical_trace_sha256"]
    assert usage["allocation"]["variable_and_wear_eur"] > a["allocation"]["variable_and_wear_eur"]
    assert teaching_trace() == original
    for r in (a, b):
        cost = r["allocation"]
        assert sum(cost["components"].values()) == pytest.approx(cost["total_eur"])
        assert all(pair[2] == max(pair[:2]) for pair in cost["allowances"].values())
    assert evaluate("economics", {"output": "zero output"})["allocation"]["eur_per_kg_ch4"] is None
    a["steps"][0]["state"]["h2_kg"] = -100
    assert evaluate("economics")["steps"][0]["state"]["h2_kg"] >= 0


def test_comparison_boundaries_and_solver_scope():
    a = evaluate("experiments", {"window": 1})
    b = evaluate("experiments", {"window": 6})
    assert a["comparison"]["produce"]["methane_kg"] < b["comparison"]["produce"]["methane_kg"]
    assert (
        b["comparison"]["retain"]["ending"]["h2_kg"] > b["comparison"]["produce"]["ending"]["h2_kg"]
    )
    x = evaluate("controllers", {"horizon": 6})
    assert set(x["plans"]) == {"greedy", "methane", "economics"}
    assert all("status" in p["solver"] for p in x["plans"].values())
    assert all(len(p["trajectory"]) == 6 for p in x["plans"].values())


def test_review_freshness_and_missing_identity(monkeypatch):
    assert check_freshness()
    import methane.documentation as documentation

    altered = copy.deepcopy(TOPICS)
    altered["battery"]["purpose"] = "Changed explanation without review"
    monkeypatch.setattr(documentation, "TOPICS", altered)
    assert (
        bindings()["battery"]["narrative"]
        != catalogue()["topics"]["battery"]["bindings"]["narrative"]
    )
    with pytest.raises(ValueError, match="review"):
        check_freshness()


def test_run_lineage_preserves_archive_and_marks_missing_snapshot():
    from dataclasses import replace

    from methane.config import Config
    from methane.provenance import seal
    from methane.simulation import run

    c = Config()
    source = run(replace(c, scenario=replace(c.scenario, hours=4)), strategies=("Greedy",))
    assert set(source["documentation"]["topics"]) == set(TOPICS)
    assert set(source["learning_examples"]) == set(TOPICS)
    original = read(source, "battery", "This run", "Greedy", 0)
    assert original["status"] == "available"
    source = copy.deepcopy(source)
    del source["documentation"]
    source = seal(source)
    prior = json.dumps(source, sort_keys=True)
    answer = read(source, "battery", "This run", "Greedy", 0)
    assert answer["status"] == "unavailable"
    assert answer["recorded"]["calculation"]["status"] == "recorded"
    assert json.dumps(source, sort_keys=True) == prior
    for topic in TOPICS:
        assert recorded(source, topic, "Greedy", 0)["controller"] == "Greedy"


def test_documentation_bundle_is_readable_and_keeps_original_versions(tmp_path):
    from dataclasses import replace

    from methane.bundle import make, unpack
    from methane.bundle_runtime import check
    from methane.config import Config
    from methane.simulation import run

    c = Config()
    source = run(replace(c, scenario=replace(c.scenario, hours=2)), strategies=("Greedy",))
    bundle = make(source, tmp_path / "run.zip")
    unpack(bundle, tmp_path / "restored")
    report = (tmp_path / "restored/model-report.html").read_text()
    assert "Keeping energy for later" in report
    assert "saved learning output" in report
    assert "Recorded calculations" in report
    assert source["run_id"] in report
    assert '<script src="http' not in report
    assert check(tmp_path / "restored")["status"] == "passed"


def test_learning_service_cancellation_before_worker_start_and_context_access():
    from fastapi import HTTPException

    from methane.model_service import Request, example, job, register

    token = register({"run_id": "teaching-test"})
    base = dict(token=token, run_id="teaching-test", key="cancel-race", topic="controllers")
    assert job(Request(**base, operation="cancel"))["status"] == "cancelled"
    assert job(Request(**base, operation="start"))["status"] == "cancelled"
    with pytest.raises(HTTPException):
        example(Request(**{**base, "token": "wrong", "topic": "battery"}))
    response = example(Request(**{**base, "topic": "battery"}))
    assert response["status"] == "complete"
    assert response["key"] == "cancel-race"
