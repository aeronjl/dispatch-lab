import copy
from dataclasses import replace

import pytest

from methane.config import Costs, Plant
from methane.physics import State
from methane.services.charge_control import Target, evaluate
from methane.services.pricing import recorded_inputs
from methane.services.snapshot import RecordedServices


@pytest.fixture(scope="module")
def saved_return():
    from test_service_charging import service_prices
    from test_service_support import execute, fixture

    c = fixture(crew_response_lead_hours=0, crew_shift_duration_hours=24, crew_hours_per_period=24)
    c = replace(c, service_economics=service_prices())
    r = execute(c)
    for row in r["records"]["Greedy"]:
        f = row["field_operations"]
        retrievals = [p for p in f["new_missions"] if p["order"]["action"] == "retrieve"]
        if retrievals:
            return r, row, retrievals[0]
    pytest.fail("Fixture must expose an actual stranded mission and nominated retrieval")


def compare(saved, *, selected=True, due_offset=6):
    r, row, retrieval = saved
    snap = row["field_operations"]["planning_snapshot"]
    rt = RecordedServices(snap, r["service_planning_catalogues"][snap["catalogue_id"]])
    inputs = row["decision"]["service_planning_inputs"]
    name = "cleaner"
    # Choose a target above the observed remaining charge. This is a planning
    # alternative, not a mutation of the source run or its resource ledger.
    target = min(rt.config.cleaner_battery_kwh, rt.ledger.stock["energy:cleaner"] + 0.5)
    result = evaluate(
        rt,
        Plant(**r["config"]["plant"]),
        State(**inputs["estimate"]),
        inputs["forecast"],
        inputs["capacity_kw"],
        Costs(**r["config"]["costs"]),
        [Target(name, target, row["hour"] + due_offset, "post-retrieval reserve")],
        service_prices=r["config"]["service_economics"],
        recorded_prefix=recorded_inputs(r["records"]["Greedy"][: row["hour"]])["rows"],
        selections=[(retrieval["order"]["order_id"], retrieval["starting_at"])] if selected else (),
        reference_forecast=inputs.get("reference_forecast"),
        joint_work=True,
        uncertain=False,
        seconds=2,
    )
    return result


def test_validated_retrieval_allows_later_charge_but_never_immediate_credit(saved_return):
    source = copy.deepcopy(saved_return)
    out = compare(saved_return)
    assert out["state"] == "feasible", out
    returned = out["conditional_returns"][0]
    assert returned["status"] == "conditional"
    assert returned["available_at"] > saved_return[1]["hour"]
    assert out["current_requests"] == []
    charges = out["charging"]["plan"]["charging"]
    assert any(c["requested_kw"] > 0 for c in charges)
    assert all(
        c["requested_kw"] == 0 or saved_return[1]["hour"] + c["offset"] >= returned["available_at"]
        for c in charges
    )
    assert saved_return == source
    from methane.retrieval_reference import audit_candidate

    snapshot = saved_return[1]["field_operations"]["planning_snapshot"]
    assert all(c["passed"] for c in audit_candidate(out, snapshot))
    out["conditional_returns"][0]["available_at"] -= 1
    assert not all(c["passed"] for c in audit_candidate(out, snapshot))


def test_omitted_retrieval_and_premature_target_remain_infeasible(saved_return):
    omitted = compare(saved_return, selected=False)
    assert omitted["state"] != "feasible"
    assert omitted["conditional_returns"][0]["available_at"] is None
    early = compare(saved_return, due_offset=1)
    assert early["state"] != "feasible"
