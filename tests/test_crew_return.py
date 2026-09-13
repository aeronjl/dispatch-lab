"""Independent return timing, original work, finite labour and causal receipts."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.faults import FaultState
from methane.reference import audit
from methane.service_economics import ACTIVITY_VERSION, illustrative, reprice_run
from methane.services.configuration import ServiceSystem
from methane.services.controller import ServiceController
from methane.services.core import ASSETS
from methane.services.crew_return import remaining_route
from methane.services.portable_demo import execute, fixture
from tests.test_service_controller import runtime


def crew():
    c, _, d = runtime()
    from methane.services.plant import PlantServices

    c = replace(c, service_system=replace(c.service_system, crew_return_enabled=True))
    rt = PlantServices(c.field_operations, c.service_system, 7, 450)
    rt.prepare(0, d, 1000)
    fault = FaultState(c.plant, c.scenario, c.faults)
    return c, rt, d, fault


def stop_after_departure():
    c, rt, d, f = crew()
    key = rt.orders[0]["id"]
    rt.dispatch_selected(((key, 0),), charge=False)
    first = rt.end(0, f, d)
    rt.executive.interrupt(key, "Observed work cancellation after arrival")
    return c, rt, d, f, key, first


def test_return_does_not_complete_abandoned_work_or_create_a_new_visit():
    c, rt, d, f, key, first = stop_after_departure()
    controller = ServiceController(c.service_policy)
    rows = [first]
    for h in range(1, 4):
        rt.prepare(h, d, 1000)
        controller._work(rt)
        rt.dispatch_local()
        rows.append(rt.end(h, f, d))
    effects = [e for r in rows for e in r["support_effects"] if e["kind"] == "crew-return"]
    expected = Decimal(1) + Decimal(".25") + Decimal(1) + Decimal(".25")
    assert effects[0]["completed_at"] == float(expected) == 2.5
    assert effects[0]["effective_at"] == 3
    assert sum(r["human_visits"] for r in rows[:3]) == 1
    assert rows[3]["human_visits"] == 1  # The later repair retry is a new visit.
    assert rows[1]["state"]["support"]["returned"] == {}
    original = next(q for q in rows[2]["state"]["orders"] if q["id"] == key)
    assert original["status"] == "failed" and original["retrieved_at"] == 3
    assert not any(
        e["kind"] in ("module-replacement", "restock") for r in rows for e in r["support_effects"]
    )
    assert controller.obligations[key]["due_hour"] == 6
    # Once returned, a distinct retry can really depart; its old deadline remains.
    assert len(controller.obligations[key]["attempts"]) == 2


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"crew_hours_per_period": 1}, "crew-hours"),
        ({"crew_shift_duration_hours": 2}, "fit a declared shift"),
    ],
)
def test_return_cannot_invent_available_labour(changes, reason):
    _, rt, d, f, key, _ = stop_after_departure()
    rt.options = replace(rt.options, **changes)
    rt.support.o = rt.options
    if "crew_hours_per_period" in changes:
        # Spend the remaining allowance through the real resource ledger.
        from methane.services.contracts import Quantity

        amount = rt.ledger.stock["crew-hours"]
        rt.ledger.reserve("used-labour", (Quantity("crew-hours", amount, "h"),), (), 1)
        rt.ledger.consume("used-labour", Quantity("crew-hours", amount, "h"), 1, "perform")
        rt.ledger.release("used-labour", 1)
    rt.begin(1, d, 1000)
    row = rt.end(1, f, d)
    q = next(q for q in row["state"]["orders"] if q["kind"] == "crew-return")
    assert q["status"] == "queued" and reason in q["blocked"]
    assert not rt._available(ASSETS["crew"])
    assert key not in rt.support.returned


def test_remaining_route_cuts_only_the_untravelled_fraction_without_work():
    _, rt, d, f = crew()
    key = rt.orders[0]["id"]
    rt.dispatch_selected(((key, 0),), charge=False)
    rt._effects._faults = f
    rt._effects.hour = 0
    rt.executive.advance(0.4, rt.context(0, d))
    rt.executive.interrupt(key, "Observed stop en route")
    route, operands = remaining_route(rt, rt.executive.missions[key])
    assert [s.duration_hours for s in route] == pytest.approx([0.6, 1])
    assert all(s.phase == "return" and not s.effect and not s.consumables for s in route)
    assert operands[0]["interruption_at"] == 0.4
    assert route[0].from_point == "recovery/" + key and route[-1].to_point == "site-gate"


def test_second_interruption_keeps_both_original_location_obligations():
    _, rt, d, f, key, _ = stop_after_departure()
    rt.begin(1, d, 1000)
    rt.end(1, f, d)
    returning = next(q for q in rt.orders if q["kind"] == "crew-return")
    rt.executive.interrupt(returning["id"], "Route became unavailable during return")
    rt.begin(2, d, 1000)
    row = rt.end(2, f, d)
    newer = next(q for q in rt.orders if q["kind"] == "crew-return" and q["id"] != returning["id"])
    assert newer["return_origins"] == [key, returning["id"]]
    assert newer["return_route"][0]["duration_hours"] == pytest.approx(0.25)
    assert rt.support.returned[key]["effective_at"] == 3
    assert rt.support.returned[returning["id"]]["effective_at"] == 3
    assert row["human_visits"] == 0


@pytest.mark.parametrize("at,remaining", [(1, 1), (2.25, 0)])
def test_interrupted_packing_or_arrival_can_retry_from_its_actual_position(at, remaining):
    _, rt, d, f, key, _ = stop_after_departure()
    rt.begin(1, d, 1000)
    returning = next(q for q in rt.orders if q["kind"] == "crew-return")
    rt._effects._faults = f
    rt._effects.hour = 1
    if at > 1:
        rt.executive.advance(2, rt.context(1, d))
        rt.executive.advance(at, rt.context(2, d))
    rt.executive.interrupt(returning["id"], "Observed interruption outside travel")
    assert rt.executive.missions[returning["id"]].status == "blocked"
    from methane.services.crew_return import build, policy

    policy(rt, at)
    newer = rt.orders[-1]
    assert newer["origin_order"] == returning["id"] and newer["return_origins"] == [
        key,
        returning["id"],
    ]
    rt._context = rt.context(at, d)
    plan, _ = build(rt, newer)
    assert sum(s.duration_hours for s in plan.stages if s.phase == "return") == remaining
    assert plan.stages[0].from_point == ("electrolyser" if at == 1 else "site-gate")
    assert key not in rt.support.returned


@pytest.fixture(scope="module")
def portable_return():
    c = fixture(crew_return_enabled=True, work_failure_fraction=0.3)
    c = replace(
        c,
        field_operations=replace(c.field_operations, mission_failure_probability=1),
        service_economics=illustrative(c.costs, version=ACTIVITY_VERSION),
    )
    return execute(c)


def test_complete_portable_trace_reconciles_return_and_costs(portable_return):
    report = audit(portable_return)
    assert report["passed"], [q for q in report["checks"] if not q["passed"]][:10]
    services = [r["field_operations"] for r in portable_return["records"]["Greedy"]]
    returns = [e for r in services for e in r["support_effects"] if e["kind"] == "crew-return"]
    assert returns and all(e["robot"] == "portable" for e in returns)
    for r in services:
        plans = {p["order"]["order_id"]: p for p in r["new_missions"]}
        assert all(
            not s["bus_kw"]
            for p in plans.values()
            if p["order"]["action"] == "crew-return"
            for s in p["stages"]
        )
    fixed = reprice_run(portable_return, portable_return["config"]["service_economics"])
    assert all(v["services"]["status"] == "complete" for v in fixed["controllers"].values())


@pytest.mark.parametrize("field", ["duration", "arrival", "origins"])
def test_independent_reference_rejects_forged_return(portable_return, field):
    damaged = copy.deepcopy(portable_return)
    rows = [r["field_operations"] for r in damaged["records"]["Greedy"]]
    if field == "duration":
        q = next(q for r in rows for q in r["state"]["orders"] if q["kind"] == "crew-return")
        q["return_route_operands"][0]["remaining_hours"] += 1
    elif field == "arrival":
        effect = next(e for r in rows for e in r["support_effects"] if e["kind"] == "crew-return")
        effect["effective_at"] -= 1
    else:
        q = next(q for r in rows for q in r["state"]["orders"] if q["kind"] == "crew-return")
        q["return_origins"] = []
    assert not audit(damaged)["passed"]


def test_configuration_is_opt_in_and_strict():
    assert not ServiceSystem().crew_return_enabled
    with pytest.raises(ValueError, match="finite support"):
        ServiceSystem(crew_return_enabled=True)
    with pytest.raises(ValueError, match="positive"):
        ServiceSystem(crew_return_pack_hours=0)
    with pytest.raises(ValueError, match="boolean"):
        ServiceSystem(crew_return_enabled=1)


def test_return_from_interrupted_shared_visit_preserves_all_jobs_and_cargo():
    from methane.services.visits_demo import execute as visit_execute
    from methane.services.visits_demo import fixture as visit_fixture

    c = visit_fixture("interrupted-portable")
    result = visit_execute(
        replace(c, service_system=replace(c.service_system, crew_return_enabled=True))
    )
    checked = audit(result)
    assert checked["passed"], [q for q in checked["checks"] if not q["passed"]][:6]
    rows = [r["field_operations"] for r in result["records"]["Greedy"]]
    first = next(e for r in rows for e in r["support_effects"] if e["kind"] == "crew-return")
    at = first["effective_at"] - 1
    original = next(
        v for v in rows[at]["state"]["executive"]["visits"] if first["origin_order"] in v["members"]
    )
    assert original["status"] == "interrupted" and original["returned_at"] is None
    assert original["unfinished"]  # A later return does not rewrite original visit success.
    plan = next(
        p for r in rows for p in r["new_missions"] if p["order"]["order_id"] == first["order_id"]
    )
    assert {q["resource"] for q in plan["asset"]["support_resources"]} == {
        "asset:" + ASSETS["crew"]
    }
    assert first["completed_at"] == 6.75


def test_return_policy_only_reads_observed_work_not_future_faults():
    from methane.services.crew_return import policy

    _, rt, d, _, _, _ = stop_after_departure()
    before = copy.deepcopy(rt)
    before._effects._faults = object()  # No truth API is callable through this port.
    policy(rt, 1)
    policy(before, 1)
    assert rt.orders == before.orders
    for candidate in (rt, before):
        candidate._context = candidate.context(1, d)
        plan = candidate.support.build(candidate.orders[-1], decorate=False)
        assert plan.order.action == "crew-return"
