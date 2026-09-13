"""Shared visits conserve travel/labour without merging effects or evidence."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.reference import audit
from methane.services.access import Access, Edge
from methane.services.adapters import mobile
from methane.services.contracts import (
    Asset,
    Capability,
    Context,
    Interface,
    Quantity,
    Reading,
    Requirement,
    WorkOrder,
)
from methane.services.executive import Executive, Receipt
from methane.services.resources import Ledger, Resource, ResourceConflict
from methane.services.visits import VisitPlan, compose
from methane.services.visits_demo import CASES, execute, fixture


class Effects:
    def __init__(self, failed_first=False):
        self.work = []
        self.failed_first = failed_first

    def perform(self, plan, at):
        self.work.append((plan.order.order_id, at))
        value = not (self.failed_first and plan.order.order_id == "one")
        return Receipt(
            "Test measurement",
            (
                Reading(
                    plan.order.order_id + "-ready",
                    value,
                    "boolean",
                    at,
                    int(at + 0.999999),
                    "independent-test-port",
                ),
            ),
        )


def example(kits=2, failed_first=False):
    actor = Asset("crew", "crew", "test-crew/1", "gate", "crew", ("one", "two"), autonomy="human")
    edges = [
        Edge("out-a", "gate", "a", 1, ("crew",)),
        Edge("a-home", "a", "gate", 1, ("crew",)),
        Edge("out-b", "gate", "b", 1, ("crew",)),
        Edge("b-home", "b", "gate", 1, ("crew",)),
        Edge("a-b", "a", "b", 0.25, ("crew",)),
    ]
    access = Access(edges)
    ledger = Ledger(
        [
            Resource("asset:crew", "slot", "capacity", 1),
            Resource("kits", "kit", "stock", kits, kits),
            Resource("crew-hours", "h", "stock", 8, 8),
        ]
    )
    plans = []
    for name, point in (("one", "a"), ("two", "b")):
        cap = Capability(
            name,
            name,
            "repair",
            "test-" + name,
            1,
            0.25,
            consumables=(Quantity("kits", 1, "kit"),),
            acceptance=(Requirement(name + "-ready", "equals", True, "boolean", 4),),
        )
        order = WorkOrder(name, name, point, 0, "Different repair question")
        plans.append(
            mobile(
                order,
                actor,
                Interface(point, point, point, (name,)),
                cap,
                Context(0, ()),
                access=access,
            )
        )
    visit = compose(plans, access, "asset:crew", "visit", "Share travel only")
    visit = replace(
        visit,
        members=tuple(
            replace(
                p,
                stages=tuple(
                    replace(s, hourly_consumables=(Quantity("crew-hours", 1, "h"),))
                    for s in p.stages
                ),
            )
            for p in visit.members
        ),
    )
    port = Effects(failed_first)
    return visit, Executive(ledger, port), port, plans


def advance(executive, hour):
    while executive.at_hour < hour:
        at = executive.at_hour
        executive.advance(min(hour, at + 1), Context(at, ()))
    executive.reconcile_verification(Context(hour, ()))


def test_shared_visit_reconciles_two_jobs_and_one_return_against_decimal_arithmetic():
    visit, ex, port, separate = example()
    expected = Decimal(1) + 2 * (Decimal(1) + Decimal(".25")) + Decimal(".25") + Decimal(1)
    assert visit.ending_at == float(expected) == 4.75
    assert sum(p.ending_at for p in separate) == 6.5
    ex.submit_visit(visit)
    advance(ex, 5)
    assert port.work == [("one", 2.0), ("two", 3.5)]
    assert ex.public()["visits"][0]["returned_at"] == 4.75
    assert ex.public()["visits"][0]["status"] == "completed"
    assert ex.ledger.stock["crew-hours"] == 8 - float(expected)
    assert ex.ledger.stock["kits"] == 0
    assert all(r["passed"] for r in ex.ledger.reconcile())


def test_failed_later_reservation_leaves_no_partial_visit_or_consumption():
    visit, ex, _, _ = example(kits=1)
    before = copy.deepcopy(ex.ledger.__dict__)
    with pytest.raises(ResourceConflict, match="kits"):
        ex.submit_visit(visit)
    assert ex.ledger.__dict__ == before and ex.missions == {} and ex.visits == {}


def test_interrupted_crew_stops_unstarted_jobs_and_retains_spent_material():
    visit, ex, port, _ = example()
    ex.submit_visit(visit)
    advance(ex, 1.5)
    ex.interrupt("one", "Vehicle access interrupted")
    advance(ex, 7)
    assert port.work == [] and ex.ledger.stock["kits"] == 1
    assert ex.missions["one"].status == "stranded" and ex.missions["two"].status == "blocked"
    report = ex.public()["visits"][0]
    assert report["returned_at"] is None and report["unfinished"] == ["one", "two"]
    assert report["status"] == "interrupted"
    assert not ex.ledger.holds and all(r["passed"] for r in ex.ledger.reconcile())


def test_shared_return_does_not_merge_or_certify_job_acceptance():
    visit, ex, port, _ = example(failed_first=True)
    ex.submit_visit(visit)
    advance(ex, 5)
    assert len(port.work) == 2 and ex.missions["one"].status == "awaiting verification"
    assert ex.missions["two"].status == "completed"
    assert ex.public()["visits"][0]["status"] == "returned; acceptance pending"


@pytest.mark.parametrize("at,current", [(1.5, "one"), (2.25, "two")])
def test_upcoming_job_failure_stops_the_shared_crew_at_its_current_location(at, current):
    visit, ex, port, _ = example()
    ex.submit_visit(visit)
    advance(ex, at)
    ex.interrupt("two", "Upcoming work lost its required supply")
    assert ex.missions[current].status == "stranded"
    advance(ex, 7)
    assert ex.public()["visits"][0]["returned_at"] is None
    assert ex.ledger.stock["crew-hours"] == 8 - at
    assert not any(key == "two" for key, _ in port.work)
    assert not ex.ledger.holds


def test_visit_rejects_teleportation_changed_crew_and_return_deadline():
    visit, _, _, _ = example()
    first, second = visit.members
    with pytest.raises(ValueError, match="teleport"):
        replace(
            visit,
            members=(
                first,
                replace(
                    second,
                    stages=(replace(second.stages[0], from_point="elsewhere"), *second.stages[1:]),
                ),
            ),
        )
    with pytest.raises(ValueError, match="same declared crew"):
        replace(visit, crew_resource="asset:another-crew")
    with pytest.raises(ValueError, match="Shared return"):
        replace(visit, members=(replace(first, order=replace(first.order, deadline=3)), second))
    with pytest.raises(ValueError, match="two distinct"):
        VisitPlan("single", "asset:crew", (first,), "No second job")


@pytest.fixture(scope="module")
def cases():
    return {name: execute(fixture(name)) for name in CASES}


def records(result):
    return [r["field_operations"] for r in result["records"]["Greedy"]]


@pytest.mark.parametrize("case", CASES)
def test_coupled_visit_examples_reconcile_with_the_independent_reference(cases, case):
    result = cases[case]
    assert result["status"] == "complete", result["failures"]
    report = audit(result)
    assert report["passed"], [r for r in report["checks"] if not r["passed"]][:6]


def test_supplies_share_a_real_journey_and_keep_individual_delivery_receipts(cases):
    joint, separate = (records(cases[n]) for n in ("supplies", "separate-supplies"))
    assert sum(r["human_visits"] for r in joint) == 1
    assert sum(r["human_visits"] for r in separate) == 3
    assert sum(r["crew_committed_hours"] for r in joint) == 3.5
    assert sum(r["crew_committed_hours"] for r in separate) == 7.5
    effects = [e for r in joint for e in r["support_effects"]]
    assert [e["completed_at"] for e in effects] == [3.5, 4, 4.5]
    assert [e["effective_at"] for e in effects] == [4, 4, 5]
    assert len({e["order_id"] for e in effects}) == 3
    assert joint[-1]["state"]["executive"]["visits"][0]["returned_at"] == 5.5


def test_short_shift_splits_the_visit_and_empty_pipeline_never_credits_future_stock(cases):
    short = records(cases["short-shift"])
    assert sum(r["human_visits"] for r in short) == 2
    first = next(v for r in short for v in r.get("new_visits", []))
    assert len(first["members"]) == 2
    empty = records(cases["empty-pipeline"])
    assert not any(r["human_visits"] or r.get("new_visits") for r in empty)
    assert empty[-1]["state"]["service_kits"] == 0
    assert all(
        q["status"] == "queued" and "upstream:" in q["blocked"]
        for q in empty[-1]["state"]["orders"]
    )


def test_unobserved_repair_outcome_cannot_change_the_original_combined_visit(cases):
    successful, failed = (
        records(cases[n]) for n in ("interventions", "unsuccessful-interventions")
    )
    plans = [
        next(v for r in rows for v in r.get("new_visits", [])) for rows in (successful, failed)
    ]
    assert plans[0] == plans[1]
    assert [p["order"]["action"] for p in plans[0]["members"]] == ["restock", "module-replacement"]
    # Calibration only becomes observable later; it cannot be added retrospectively.
    assert not any(q["kind"] == "flow-calibration" for q in successful[8]["decision"]["orders"])
    report = failed[-1]["state"]["executive"]["visits"][0]
    assert report["returned_at"] == 13 and report["status"] == "returned; acceptance pending"
    work = failed[-1]["state"]["orders"]
    assert next(q for q in work if q["kind"] == "restock")["status"] == "completed"
    assert (
        next(q for q in work if q["kind"] == "module-replacement")["status"]
        == "awaiting verification"
    )


def test_interrupted_portable_job_keeps_water_and_work_but_blocks_its_later_delivery(cases):
    rows = records(cases["interrupted-portable"])
    assert sum(r["human_visits"] for r in rows) == 1
    expected = Decimal(1) + Decimal(".5") + Decimal(5000) / 3 / 1000 / 2
    assert sum(r["crew_committed_hours"] for r in rows) == pytest.approx(float(expected))
    assert sum(r["water_used_l"] for r in rows) == pytest.approx(
        float(Decimal(10) + Decimal(5000) / 3 / 2 * Decimal(".5"))
    )
    assert not any(r["support_effects"] for r in rows)
    report = rows[-1]["state"]["executive"]["visits"][0]
    assert report["status"] == "interrupted" and report["returned_at"] is None
    assert len(report["unfinished"]) == 2
    assert rows[-1]["state"]["service_kits"] == 0


@pytest.mark.parametrize(
    "change", ["return", "callout", "envelope", "missing-job", "start", "lost-backlog"]
)
def test_independent_visit_audit_rejects_forged_itineraries_and_aggregates(cases, change):
    result = copy.deepcopy(
        cases["supplies" if change != "lost-backlog" else "interrupted-portable"]
    )
    rows = records(result)
    if change == "return":
        rows[-1]["state"]["executive"]["visits"][0]["returned_at"] -= 1
    elif change == "callout":
        rows[2]["human_visits"] += 1
    elif change == "envelope":
        reserve = next(
            e
            for r in rows
            for e in r["resource_events"]
            if e["kind"] == "reserve" and e["mission_id"].startswith("VISIT-")
        )
        reserve["capacity"][0]["end"] -= 1
    elif change == "missing-job":
        rows[-1]["state"]["executive"]["visits"][0]["planned_jobs"].pop()
    elif change == "start":
        visit = next(v for r in rows for v in r.get("new_visits", []))
        visit["members"][1]["starting_at"] -= 0.25
    else:
        rows[-1]["state"]["executive"]["visits"][0]["unfinished"] = []
    assert not audit(result)["passed"]
