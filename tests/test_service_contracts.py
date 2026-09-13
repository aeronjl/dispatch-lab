"""Independent checks of service scheduling, time, resource and information contracts."""

import copy
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

from methane.services.access import Access, Edge
from methane.services.adapters import claims, fixed, mobile, schedule
from methane.services.contracts import (
    Asset,
    Capability,
    Context,
    Interface,
    Quantity,
    Reading,
    Requirement,
    WorkOrder,
    available_boundary,
)
from methane.services.executive import Executive, Receipt
from methane.services.resources import Booking, Ledger, Resource, ResourceConflict


def reading(channel, value, at=0, unit="boolean", available_at=None, quality="usable"):
    return Reading(
        channel,
        value,
        unit,
        at,
        at if available_at is None else available_at,
        "test-meter/1",
        quality,
    )


def context(at=0, route=True):
    return Context(at, (reading("route-open", route, at),))


def fixture():
    route = Requirement("route-open", "equals", True, "boolean", 2)
    graph = Access(
        (
            Edge("out", "dock", "ely", 0.5, ("wheeled",), (route,), "corridor"),
            Edge("back", "ely", "dock", 0.5, ("wheeled",), (route,), "corridor"),
        )
    )
    cap = Capability(
        "contact-inspection",
        "read-contact",
        "observe",
        "contact-reader/1",
        0.25,
        0.25,
        work_kw=0.4,
        consumables=(Quantity("references", 1, "kit"),),
        acceptance=(Requirement("trip-contact", "available", True, "boolean", 2),),
    )
    port = Interface(
        "ely-contact",
        "ELY-01",
        "ely",
        ("read-contact",),
        ("contact-reader",),
        exclusive_resources=("work-area",),
    )
    rover = Asset(
        "ROVER",
        "ground-inspector",
        "test-rover/1",
        "dock",
        "wheeled",
        (cap.capability_id,),
        ("contact-reader",),
        "rover-energy",
        0.2,
        0.6,
    )
    sensor = Asset(
        "FIXED",
        "fixed-sensor",
        "test-fixed/1",
        "ely",
        "fixed",
        (cap.capability_id,),
        ("contact-reader",),
    )
    stocks = (
        Resource("rover-energy", "kWh", "stock", 2, 2),
        Resource("references", "kit", "stock", 4, 4),
        *(
            Resource(key, "slot", "capacity", 1)
            for key in ("asset:ROVER", "asset:FIXED", "corridor", "work-area")
        ),
        Resource("plant:service-power", "kW", "capacity", 1),
    )
    return graph, cap, port, rover, sensor, stocks


class ContactPort:
    def __init__(self, latched=True):
        self.latched, self.calls = latched, []

    def perform(self, plan, completed_at):
        self.calls.append((plan.order.order_id, completed_at))
        return Receipt(
            "Contact inspection completed",
            (
                reading(
                    "trip-contact",
                    self.latched,
                    completed_at,
                    available_at=available_boundary(completed_at),
                ),
            ),
            ({"hidden_damage": 0.5},),
        )


def plan_for(asset="rover", start=0, order_id="WORK"):
    graph, cap, port, rover, sensor, stocks = fixture()
    order = WorkOrder(order_id, cap.action, port.interface_id, 0, "Investigate reported anomaly")
    builder = mobile if asset == "rover" else fixed
    plan = builder(
        order,
        rover if asset == "rover" else sensor,
        port,
        cap,
        context(),
        starting_at=start,
        access=graph,
    )
    return plan, stocks


def test_fixed_and_mobile_adapters_fulfil_same_request_with_distinct_resource_use():
    plans = [plan_for(asset)[0] for asset in ("fixed", "rover")]
    assert plans[0].order == plans[1].order
    assert [s.phase for s in plans[0].stages] == ["perform", "verify"]
    assert [s.phase for s in plans[1].stages] == ["travel", "perform", "verify", "return"]
    for plan, expected_battery, expected_bus in zip(plans, (0, 0.8), (0.2, 0), strict=True):
        executor = Executive(Ledger(fixture()[-1]), ContactPort())
        executor.submit(plan)
        executor.advance(2, context())
        executor.reconcile_verification(context(2))
        row = executor.public()["orders"][0]
        assert row["status"] == "completed" and row["verified_at"] == 2
        assert row["battery_kwh"] == pytest.approx(expected_battery)
        assert row["bus_kwh"] == pytest.approx(expected_bus)
        assert executor.ledger.stock["references"] == 3
        assert all(r["passed"] for r in executor.ledger.reconcile())


def test_independent_decimal_energy_and_split_interval_invariance():
    plan, stocks = plan_for()
    trace = []
    for times in ((2,), (0.1, 0.5, 0.7, 0.75, 1, 1.25, 2)):
        executor = Executive(Ledger(stocks), ContactPort())
        executor.submit(plan)
        for t in times:
            executor.advance(t, context(executor.at_hour))
        expected_use = Decimal("0.6") * Decimal("1") + Decimal("0.4") * Decimal("0.5")
        assert executor.ledger.stock["rover-energy"] == pytest.approx(
            float(Decimal("2") - expected_use)
        )
        trace.append(executor.public()["orders"][0])
    assert trace[0]["battery_kwh"] == pytest.approx(trace[1]["battery_kwh"])
    assert trace[0]["completed_at"] == trace[1]["completed_at"] == 1.5


def test_observation_arrival_and_retrospective_truth_are_separate():
    plan, stocks = plan_for()
    executor = Executive(Ledger(stocks), ContactPort())
    executor.submit(plan)
    executor.advance(0.75, context())
    assert executor.retrospective()[0]["effects"] == ({"hidden_damage": 0.5},)
    assert executor.public()["observations"] == []
    assert executor.public()["orders"][0]["reports"] == []
    assert "hidden_damage" not in json.dumps(executor.public())
    executor.advance(1, context(0.75))
    assert executor.public()["observations"][0]["value"] is True
    assert executor.public()["orders"][0]["status"] == "active"
    with pytest.raises(ValueError, match="future"):
        executor.observations(2)


def test_failed_repair_requires_fresh_independent_acceptance_not_a_completion_flag():
    plan, stocks = plan_for("fixed")
    threshold = Requirement("tracking", "at_least", 0.9, "fraction", 3)
    plan = replace(
        plan, capability=replace(plan.capability, effect_kind="repair", acceptance=(threshold,))
    )
    executor = Executive(Ledger(stocks), ContactPort())
    executor.submit(plan)
    executor.advance(1, context())
    for sample in (
        reading("tracking", 1.0, 0, "fraction"),
        reading("tracking", 0.5, 1, "fraction"),
    ):
        executor.reconcile_verification(Context(1, (sample,)))
        assert executor.public()["orders"][0]["status"] == "awaiting verification"
    executor.reconcile_verification(Context(1, (reading("tracking", 1.0, 1, "fraction"),)))
    assert executor.public()["orders"][0]["verified_at"] == 1


def test_unknown_stale_ambiguous_and_wrong_unit_prerequisites_are_not_healthy():
    rule = Requirement("route-open", "equals", True, "boolean", 1)
    for c in (
        Context(0, ()),
        Context(2, (reading("route-open", True),)),
        Context(0, (reading("route-open", True, quality="uncertain"),)),
        Context(0, (reading("route-open", 1, unit="count"),)),
    ):
        assert rule.failure(c)
    assert rule.failure(context()) is None
    with pytest.raises(ValueError, match="unavailable"):
        Context(0, (reading("future", True, 0, available_at=1),))
    with pytest.raises(ValueError, match="unavailable"):
        WorkOrder("bad", "read", "port", 0, "reason", (reading("future", True, 1),))


def test_blocked_route_wrong_mobility_tools_and_fixed_location_reject_dispatch():
    graph, cap, port, rover, sensor, _ = fixture()
    order = WorkOrder("work", cap.action, port.interface_id, 0, "reason")
    with pytest.raises(ValueError, match="eligible"):
        mobile(order, rover, port, cap, context(route=False), access=graph)
    with pytest.raises(ValueError, match="eligible"):
        mobile(order, replace(rover, mobility="aerial"), port, cap, context(), access=graph)
    with pytest.raises(ResourceConflict, match="tools"):
        fixed(order, replace(sensor, tools=()), port, cap, context())
    with pytest.raises(ResourceConflict, match="installed"):
        fixed(order, replace(sensor, home="elsewhere"), port, cap, context())


@pytest.mark.parametrize("at,expected_energy,expected_kits", [(0.25, 1.85, 4), (0.6, 1.66, 3)])
def test_interruption_keeps_consumed_energy_and_kits_and_does_not_teleport_home(
    at, expected_energy, expected_kits
):
    plan, stocks = plan_for()
    effect = ContactPort()
    executor = Executive(Ledger(stocks), effect)
    executor.submit(plan)
    executor.advance(at, context())
    executor.interrupt("WORK", "Remote support unavailable; retrieval required")
    assert executor.ledger.stock["rover-energy"] == pytest.approx(expected_energy)
    assert executor.ledger.stock["references"] == expected_kits
    position = executor.public()["orders"][0]
    assert position["status"] == "stranded"
    executor.advance(3, context(at))
    assert executor.public()["orders"][0]["progress"] == position["progress"]
    assert executor.public()["orders"][0]["from_point"] == position["from_point"]
    assert not effect.calls
    assert all(r["reserved"] == pytest.approx(0) for r in executor.ledger.reconcile())


def test_return_route_blocked_after_work_strands_asset_and_retains_observation():
    plan, stocks = plan_for()
    executor = Executive(Ledger(stocks), ContactPort())
    executor.submit(plan)
    executor.advance(1, context())
    executor.advance(2, context(1, route=False))
    assert executor.public()["orders"][0]["status"] == "stranded"
    assert executor.public()["orders"][0]["from_point"] == "ely"
    assert executor.observations()[0].value is True


def test_reservations_include_return_margin_and_combined_material_claims():
    plan, stocks = plan_for()
    quantities, bookings = claims(plan)
    assert next(q.amount for q in quantities if q.resource == "rover-energy") == pytest.approx(1)
    ledger = Ledger(
        replace(r, initial=0.99) if r.resource_id == "rover-energy" else r for r in stocks
    )
    before = copy.deepcopy(vars(ledger))
    with pytest.raises(ResourceConflict, match="rover-energy"):
        ledger.reserve("WORK", quantities, bookings, 0)
    assert vars(ledger) == before
    with pytest.raises(ResourceConflict, match="references"):
        ledger.reserve(
            "WORK", (Quantity("references", 3, "kit"), Quantity("references", 2, "kit")), (), 0
        )
    assert vars(ledger) == before


def test_capacity_is_aggregate_half_open_and_released_only_from_interruption_time():
    ledger = Ledger((Resource("dock", "slot", "capacity", 2),))
    ledger.reserve("a", (), (Booking("dock", 0, 2, 1, "slot"),), 0)
    ledger.reserve("b", (), (Booking("dock", 1, 2, 1, "slot"),), 0)
    with pytest.raises(ResourceConflict, match="capacity exceeded"):
        ledger.reserve("c", (), (Booking("dock", 1.5, 3, 1, "slot"),), 0)
    ledger.release("b", 1.5)
    ledger.reserve("c", (), (Booking("dock", 1.5, 3, 1, "slot"),), 1.5)
    assert next(b.end for b in ledger.bookings if b.mission_id == "b") == 1.5
    ledger.reserve("d", (), (Booking("dock", 2, 3, 1, "slot"),), 1.5)


def test_replenishment_rejects_excess_and_never_creates_unrecorded_inventory():
    ledger = Ledger((Resource("water", "kg", "stock", 10, 8),))
    assert ledger.replenish(Quantity("water", 5, "kg"), 1, "delivery").amount == 2
    assert ledger.events[-1]["rejected"] == 3
    assert ledger.reconcile()[0]["residual"] == 0
    with pytest.raises(ResourceConflict, match="expected"):
        ledger.replenish(Quantity("water", 5, "litre"), 1, "delivery")


def test_declared_decimal_hours_reach_boundary_without_optimistic_early_rounding():
    plan, _ = plan_for("fixed")
    stages = (
        replace(plan.stages[0], phase="prepare", duration_hours=0.1, effect=False),
        replace(plan.stages[0], duration_hours=0.2),
        replace(plan.stages[1], duration_hours=0.7),
    )
    assert schedule(replace(plan, stages=stages))[-1][1] == 1
    assert available_boundary(1) == 1
    assert available_boundary(1.00000000001) == 2
    assert replace(plan, stages=stages).ending_at == 1
    with pytest.raises(ValueError, match="deadline"):
        replace(plan, order=replace(plan.order, deadline=0.4))


def test_planning_and_early_public_state_do_not_depend_on_hidden_outcomes():
    plan, stocks = plan_for()
    original = plan.to_dict()
    states = []
    for hidden in (True, False):
        executor = Executive(Ledger(stocks), ContactPort(hidden))
        executor.submit(plan)
        executor.advance(0.75, context())
        states.append(executor.public())
    assert states[0] == states[1]
    assert plan.to_dict() == original


def test_no_duplicate_execution_on_same_boundary_or_backward_time():
    plan, stocks = plan_for("fixed")
    effect = ContactPort()
    executor = Executive(Ledger(stocks), effect)
    executor.submit(plan)
    executor.advance(1, context())
    executor.advance(1, context(1))
    assert len(effect.calls) == 1
    assert executor.ledger.stock["references"] == 3
    with pytest.raises(ValueError, match="monotonic"):
        executor.advance(0.5, context(1))


def test_invalid_effect_receipt_cannot_be_retried_as_if_work_had_not_happened():
    class InvalidPort:
        calls = 0

        def perform(self, plan, completed_at):
            self.calls += 1
            # A result from .25h cannot reach the hourly decision before 1h.
            return Receipt("invalid early data", (reading("bad", True, completed_at),))

    plan, stocks = plan_for("fixed")
    port = InvalidPort()
    executor = Executive(Ledger(stocks), port)
    executor.submit(plan)
    with pytest.raises(ValueError, match="prematurely"):
        executor.advance(1, context())
    assert executor.public()["orders"][0]["status"] == "invalid"
    assert executor.ledger.stock["references"] == 3
    executor.advance(1, context(executor.at_hour))
    assert port.calls == 1
    assert executor.public()["observations"] == []


@pytest.mark.parametrize("event", [0, -1, float("nan")])
def test_invalid_physical_event_hook_releases_reservations_and_cannot_repeat(event):
    class InvalidEvent(ContactPort):
        def next_event(self, plan, at_hour):
            return event

    plan, stocks = plan_for()
    executor = Executive(Ledger(stocks), InvalidEvent())
    executor.submit(plan)
    with pytest.raises(ValueError):
        executor.advance(1, context())
    assert executor.public()["orders"][0]["status"] == "invalid"
    assert executor.ledger.stock["references"] == 4
    assert all(r["reserved"] == 0 for r in executor.ledger.reconcile())
    executor.advance(1, context())
    assert not executor.retrospective()


def test_invalid_partial_observation_preserves_consumption_but_releases_unused_holds():
    class InvalidProgress(ContactPort):
        def progress(self, plan, stage, start, stop):
            return Receipt("premature observation", (reading("bad", True, stop),))

    plan, stocks = plan_for("fixed")
    executor = Executive(Ledger(stocks), InvalidProgress())
    executor.submit(plan)
    with pytest.raises(ValueError, match="prematurely"):
        executor.advance(0.1, context())
    assert executor.ledger.stock["references"] == 3
    assert executor.public()["orders"][0]["bus_kwh"] == pytest.approx(0.04)
    assert all(r["reserved"] == 0 for r in executor.ledger.reconcile())
    assert not executor.observations()


def test_registry_rejects_undeclared_resources_and_exports_source_bound_metadata():
    from methane.services.example import reference_system, run_example
    from methane.services.registry import Registry

    system = reference_system()
    with pytest.raises(ValueError, match="requires"):
        Registry(
            system.assets.values(),
            system.interfaces.values(),
            system.capabilities.values(),
            (),
            system.access,
        )
    first, second = run_example(), run_example()
    assert first == second
    assert first["definitions"]["source"]["executive.py"] == first["source"]["executive.py"]
    assert first["cases"][0]["applied"]["orders"][0]["bus_kwh"] == pytest.approx(0.2)
    assert first["cases"][1]["applied"]["orders"][0]["battery_kwh"] == pytest.approx(0.8)


@settings(max_examples=40, deadline=None)
@given(st.lists(st.tuples(st.integers(0, 7), st.integers(1, 4), st.integers(1, 3)), max_size=15))
def test_capacity_admission_matches_independent_discrete_occupancy(requests):
    ledger = Ledger((Resource("crew", "person", "capacity", 3),))
    occupied = [0] * 12
    for i, (start, duration, people) in enumerate(requests):
        expected = all(occupied[t] + people <= 3 for t in range(start, start + duration))
        booking = Booking("crew", start, start + duration, people, "person")
        before = copy.deepcopy(vars(ledger))
        if expected:
            ledger.reserve(str(i), (), (booking,), 0)
            for t in range(start, start + duration):
                occupied[t] += people
        else:
            with pytest.raises(ResourceConflict):
                ledger.reserve(str(i), (), (booking,), 0)
            assert vars(ledger) == before
