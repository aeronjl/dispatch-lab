"""Paired service/production branches share information, not hidden success."""

import copy
from dataclasses import replace

import pytest
from test_service_procedures import inspection
from test_visit_planning import forecast

from methane.physics import State
from methane.sensing import Diagnosis
from methane.services.investigation_belief import illustrative
from methane.services.investigation_planning import compare
from methane.services.plant import PlantServices


def fixture(*, repair_probability=0.6, crew_lead=0, mission_failure=0):
    c, _, _, _, _ = inspection()
    c = replace(
        c,
        field_operations=replace(
            c.field_operations,
            repair_success_probability=repair_probability,
            mission_failure_probability=mission_failure,
        ),
        service_system=replace(
            c.service_system,
            crew_response_lead_hours=crew_lead,
            crew_travel_hours=0.25,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
        ),
    )
    rt = PlantServices(c.field_operations, c.service_system, 7, 450)
    rt.prepare(
        0,
        Diagnosis(225, active_incident=True, incidents=1, informative=True, tracking_residual=0.5),
        750,
    )
    return c, rt


def evaluate(c, rt, *, kind="inspection", hours=12):
    key = next(q["id"] for q in rt.orders if q["kind"] == kind)
    return compare(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(hours),
        225,
        c.costs,
        illustrative(),
        key,
        c.service_economics,
        seconds=2,
    )


def test_inspection_changes_remedy_only_after_arrival_without_observing_repair_success():
    c, rt = fixture()
    before = copy.deepcopy((rt.public(), rt.orders, rt.ledger.events))
    r = evaluate(c, rt)
    assert r["status"] == "complete", r
    assert (rt.public(), rt.orders, rt.ledger.events) == before
    direct = r["strategies"]["direct-intervention"]
    inspected = r["strategies"]["inspect-first"]
    assert {x["requested_remedy"] for x in direct["cases"]} == {"module-replacement"}
    assert {x["requested_remedy"] for x in inspected["cases"]} == {"module-replacement", "reset"}
    for strategy in (direct, inspected):
        assert sum(x["probability"] for x in strategy["cases"]) == pytest.approx(1)
        outcomes = strategy["process"]["branches"]
        for out in outcomes:
            assert out["requested_actions"][0] == pytest.approx(outcomes[0]["requested_actions"][0])
            case = next(c for c in strategy["cases"] if c["branch_id"] == out["branch_id"])
            for hour in range(case["test_start_hour"], case["test_end_hour"]):
                assert out["requested_actions"][hour]["electrolyser_kw"] == pytest.approx(450)
                assert out["actions"][hour]["electrolyser_kw"] == pytest.approx(
                    450 if case["restoration_hypothesis"] else 225
                )
            for other in outcomes:
                if other["information"] == out["information"]:
                    for a, b in zip(
                        out["requested_actions"], other["requested_actions"], strict=True
                    ):
                        assert a == pytest.approx(b)
            assert "Unverified" in case["ending_diagnostic_state"]
            assert out["forecast"]["electrolyser_capacity_kw"] == [225] * 12
    shared = [
        x for x in inspected["cases"] if x["mechanism_hypothesis"] == "damage-and-stuck-contact"
    ]
    assert all(x["requested_remedy"] == "reset" and not x["restoration_hypothesis"] for x in shared)
    assert sum(x["probability"] for x in shared) == pytest.approx(0.2)
    assert sum(
        x["probability"] for x in inspected["cases"] if x["finding"] == "closed"
    ) == pytest.approx(0.7)


def test_every_possible_finding_needs_a_feasible_continuation_without_renormalizing():
    c, rt = fixture(crew_lead=20)
    r = evaluate(c, rt)
    assert r["status"] == "incomplete"
    inspected = r["strategies"]["inspect-first"]
    assert inspected["status"] == "incomplete" and "process" not in inspected
    assert any(
        e["finding"] == "open" and e["probability"] == pytest.approx(0.3)
        for e in inspected["conditions"]
    )
    assert sum(x["probability"] for x in inspected["cases"]) == pytest.approx(0.7)


def test_private_physical_state_is_not_an_input_and_mobile_interruption_retains_recovery_work():
    c, rt = fixture()

    class NoTruth:
        def __getattr__(self, key):
            raise AssertionError("Private fault truth accessed: " + key)

    rt._effects._faults = NoTruth()
    assert evaluate(c, rt)["status"] == "complete"
    c, rt = fixture(mission_failure=0.2)
    r = evaluate(c, rt, kind="inspection-confirm")
    assert r["status"] == "complete", r
    assert r["strategies"]["direct-intervention"]["status"] == "feasible"
    inspected = r["strategies"]["inspect-first"]
    interrupted = [x for x in inspected["cases"] if x["finding"] == "interrupted"]
    assert sum(x["probability"] for x in interrupted) == pytest.approx(0.2)
    assert sum(x["probability"] for x in inspected["cases"]) == pytest.approx(1)
    assert all(x["requested_remedy"] == "module-replacement" for x in interrupted)
    for case in interrupted:
        assert case["outstanding_recovery"][0]["status"] == "stranded"
        assert not case["outstanding_recovery"][0]["observation_produced"]
        assert not case["outstanding_recovery"][0]["return_completed"]
        projection = inspected["projections"][case["projection_id"]]
        stopped = projection["predicted_interruptions"][0]
        assert not any(s["phase"] == "return" for s in stopped["demand_plan"]["stages"])
