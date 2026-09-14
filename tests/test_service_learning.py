import copy

import pytest

from methane.learning import evaluate

TOPICS = [
    "cleaning",
    "inspection",
    "recovery",
    "charging",
    "logistics",
    "service_costs",
    "service_uncertainty",
]


@pytest.mark.parametrize("topic", TOPICS)
def test_existing_service_learning_executes(topic):
    r = evaluate(topic)
    assert r["status"] == "complete", r.get("error")
    assert r["metrics"] and r["steps"] and r["series"]
    assert all(c["passed"] for c in r["checks"])
    assert r["execution_identity"] and r["fixture_id"]


def values(r):
    return {m["label"]: m["value"] for m in r["metrics"]}


def test_cleaning_preserves_untreated_area_and_damage():
    dry = evaluate("cleaning", {"coverage": 0.5, "efficacy": 1})
    assert dry["patches"][0]["removable"] == 0
    assert dry["patches"][1]["removable"] == 0.12
    assert all(p["damaged"] == 0.03 for p in dry["patches"])
    wet = evaluate("cleaning", {"coverage": 0.5, "efficacy": 1, "method": "wet"})
    assert values(wet)["Transmission after"] > values(dry)["Transmission after"]
    zero = values(evaluate("cleaning", {"coverage": 0}))
    assert zero["Transmission before"] == zero["Transmission after"]


def test_inspection_availability_drift_and_dropout():
    early = evaluate("inspection", {"clock": 0, "delay": 2})
    assert early["observation"]["quality"] == "not yet available"
    assert early["raw_measurement"] is None
    assert early["series"][0]["points"] == [None, None, None]
    assert evaluate("inspection", {"offset": 5})["observation"]["quality"] == "uncertain"
    assert evaluate("inspection", {"dropout": "yes"})["observation"]["quality"] == "unavailable"
    assert evaluate("inspection", {"delay": 2, "clock": 2})["observation"]["quality"] == "usable"


def test_logistics_atomic_overlap_and_rejected_delivery():
    x = evaluate("logistics", {"duration": 4})
    assert values(x)["Tasks supplied"] == 1
    assert "capacity exceeded" in x["steps"][1]["outcome"]
    y = evaluate("logistics", {"stock": 5, "delivery": 7, "arrival": 0})
    assert values(y)["Rejected delivery"] == 7
    assert all(c["passed"] for c in y["checks"])


def test_service_prices_preserve_quantities_and_do_not_double_wear():
    a = evaluate("service_costs")
    b = evaluate("service_costs", {"crew_price": 100, "purchase": "yes"})
    assert a["physical_trace_id"] == b["physical_trace_id"]
    assert values(b)["Decision cost"] - values(a)["Decision cost"] == pytest.approx(60)
    assert values(b)["Expenditure"] > values(a)["Expenditure"]
    assert (
        values(evaluate("service_costs", {"wear": 50}))["Decision cost"]
        == values(a)["Decision cost"]
    )
    source = copy.deepcopy(a)
    b["allocation"]["quantities"]["rover_hours"] = -1
    assert evaluate("service_costs") == source


def test_future_jobs_cannot_change_earlier_inference_and_support_remains_explicit():
    a = evaluate("service_uncertainty", {"jobs": 3, "clock": 1})
    b = evaluate("service_uncertainty", {"jobs": 6, "clock": 1})
    assert a["posterior"] == b["posterior"]
    assert (
        values(evaluate("service_uncertainty", {"duration": 2.5}))["Model applicability"]
        == "outside model support"
    )


def test_charging_cannot_invent_sunlight_or_start_inventory():
    r = evaluate("charging", {"power": 0})
    assert values(r)["Plan status"] == "unresolved"
    assert not r["solver"]["valid_incumbent"]
    r = evaluate("charging", {"efficiency": 0.5, "use": 6})
    assert values(r)["Plan status"] == "unresolved"


def test_service_parameters_are_bound_to_relevant_reviewed_groups():
    from methane.documentation import catalogue

    pages = catalogue()["topics"]
    for key in TOPICS:
        assert pages[key]["configuration_reference"]
        assert pages[key]["assumption_review"]["groups"]
        assert all(
            g["review_status"] == "reviewed"
            for g in pages[key]["assumption_review"]["groups"].values()
        )
