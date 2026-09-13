"""Independent dock balances, shared capacity and delayed plant trade-offs."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from methane.config import Costs, Plant
from methane.dispatch import Model
from methane.physics import State
from methane.services.charging import Battery, solve


def forecast(pv):
    origin = datetime(2026, 1, 1, tzinfo=UTC)
    return dict(
        pv_kw=list(pv),
        ambient_c=[20] * len(pv),
        deliveries_kg=[0] * len(pv),
        times=[(origin + timedelta(hours=t)).isoformat() for t in range(len(pv))],
        source=dict(
            id="charge-teaching/1",
            initialized_at=origin.isoformat(),
            available_at=origin.isoformat(),
        ),
    )


def robot(n=2, **changes):
    return replace(Battery("rover", 0, 10, 0.8, (True,) * n, (0,) * n, (0,) * n, 8, n), **changes)


def fixture():
    return replace(
        Plant(),
        battery_kwh=0,
        initial_h2_kg=0,
        heater_max_kw=0,
        cooling_max_kw=0,
        minimum_run_hours=1,
    )


def calculate(batteries, pv, **kwargs):
    p = kwargs.pop("plant", fixture())
    state = kwargs.pop("state", State.initial(p))
    return solve(
        p,
        state,
        forecast(pv),
        0,
        Costs(),
        batteries,
        kwargs.pop("dock", [10] * len(pv)),
        kwargs.pop("prices", [0] * (len(pv) + 1)),
        seconds=2,
        **kwargs,
    )


def test_known_departure_after_dark_requires_charging_beforehand_and_reconciles_losses():
    b = robot(
        3,
        available=(True, False, False),
        use_kwh=(0, 0, 6),
        reserve_kwh=(0, 0, 2),
        target_kwh=8,
        required_at_offset=2,
    )
    result = calculate([b], [10, 0, 0])
    assert result["status"] == "feasible", result["solver"]
    rows = result["plan"]["charging"]
    assert [r["requested_kw"] for r in rows] == pytest.approx([10, 0, 0])
    assert [r["after_kwh"] for r in rows] == pytest.approx([8, 8, 2])
    # Independent decimal accounting: 10 from bus = 6 travel + 2 reserve + 2 loss.
    energy = Decimal(10)
    loss = energy * (1 - Decimal("0.8"))
    assert sum(r["charging_loss_kwh"] for r in rows) == pytest.approx(float(loss), abs=1e-9)
    assert rows[-1]["after_kwh"] == pytest.approx(float(energy - loss - Decimal(6)), abs=1e-9)
    assert result["plan"]["forecast"]["service_kw"] == pytest.approx([10, 0, 0])


def test_end_of_interval_charge_cannot_fund_same_interval_departure():
    b = robot(1, use_kwh=(1,), target_kwh=0)
    result = calculate([b], [10])
    assert result["status"] == "unresolved"
    assert result["plan"] is None and not result["solver"]["valid_incumbent"]


def test_shared_dock_needs_two_intervals_for_two_connected_robots():
    a, b = robot(), robot(name="cleaner")
    result = calculate([a, b], [10, 10])
    assert result["status"] == "feasible", result["solver"]
    rows = result["plan"]["charging"]
    for t in (0, 1):
        assert sum(r["requested_kw"] > 1e-6 for r in rows if r["offset"] == t) == 1
        assert sum(r["requested_kw"] for r in rows if r["offset"] == t) == pytest.approx(10)
    assert result["plan"]["active_dock_hours"] == 2
    blocked = calculate(
        [replace(a, required_at_offset=1), replace(b, required_at_offset=1)],
        [20, 20],
        dock=[20, 20],
    )
    # A stronger shared charger still cannot serve two robots in the same slot.
    assert blocked["status"] == "unresolved"


def test_storage_headroom_and_economic_pool_favour_one_active_interval():
    result = calculate(
        [robot(initial_kwh=7, target_kwh=8)], [10, 10], prices=[0, 3, 12], objective="economics"
    )
    assert result["status"] == "feasible"
    rows = result["plan"]["charging"]
    assert sum(r["requested_kw"] for r in rows) == pytest.approx(1.25)
    assert result["plan"]["active_dock_hours"] == 1
    assert result["plan"]["incremental_service_decision_eur"] == 3
    full = calculate([robot(initial_kwh=10, target_kwh=10)], [10, 10], prices=[0, 3, 12])
    assert full["status"] == "feasible"
    assert sum(r["requested_kw"] for r in full["plan"]["charging"]) == pytest.approx(0)
    assert full["plan"]["incremental_service_decision_eur"] == 0


@pytest.mark.parametrize("change,dock", [({"available": (False, True)}, [10, 10]), ({}, [0, 10])])
def test_unavailable_robot_or_dock_misses_fixed_deadline(change, dock):
    b = robot(required_at_offset=1, **change)
    assert calculate([b], [10, 10], dock=dock)["status"] == "unresolved"


def test_active_dock_cannot_spend_plant_battery_during_darkness():
    p = replace(fixture(), battery_kwh=100, initial_soc=1)
    result = calculate([robot()], [0, 0], plant=p)
    assert result["status"] == "unresolved"


def test_postponing_charge_preserves_short_lived_methane_opportunity():
    p = replace(fixture(), initial_h2_kg=5)
    state = State.initial(p, 300)
    # 12 kWh now can make 10 kg CH4 while the reactor is hot. With no heater
    # it cools below its production band next hour. Charging takes 10 kWh.
    later = calculate([robot()], [12, 12], plant=p, state=state)
    now = calculate([robot(required_at_offset=1)], [12, 12], plant=p, state=state)
    assert later["status"] == now["status"] == "feasible"
    assert later["plan"]["predicted"]["methane_kg"] == pytest.approx(10)
    assert now["plan"]["predicted"]["methane_kg"] == pytest.approx(0)
    assert later["plan"]["charging"][0]["requested_kw"] == pytest.approx(0)
    assert later["plan"]["charging"][1]["requested_kw"] == pytest.approx(10)


def test_fixed_demands_do_not_get_spent_twice_and_inputs_are_immutable():
    p, data, b = fixture(), forecast([10, 10]), robot()
    data["service_kw"] = [4, 4]
    before = copy.deepcopy(data)
    result = solve(p, State.initial(p), data, 0, Costs(), [b], [10, 10], [0, 0, 0], seconds=2)
    assert result["status"] == "feasible"
    assert max(r["requested_kw"] for r in result["plan"]["charging"]) <= 6 + 1e-6
    assert sum(result["plan"]["forecast"]["service_kw"]) == pytest.approx(18)
    assert data == before


def test_alternative_preserves_its_inputs_and_changes_only_the_declared_action_limit():
    p = replace(
        fixture(),
        initial_h2_kg=5,
        battery_kwh=12,
        initial_soc=1,
        battery_c_rate=1,
        roundtrip_efficiency=1,
    )
    state, battery = State.initial(p, 300), robot(1)
    normal = calculate([battery], [10], plant=p, state=state)
    alternative = calculate([battery], [10], plant=p, state=state, alternative="battery")
    assert normal["status"] == alternative["status"] == "feasible"
    assert normal["plan"]["predicted"]["methane_kg"] == pytest.approx(10)
    assert alternative["plan"]["predicted"]["methane_kg"] == pytest.approx(0)
    assert alternative["inputs"]["alternative"] == "battery"
    before, after = copy.deepcopy(normal["inputs"]), copy.deepcopy(alternative["inputs"])
    before.pop("alternative")
    after.pop("alternative")
    assert before == after
    assert before["component_implementations"]
    with pytest.raises(ValueError, match="Unknown"):
        calculate([battery], [10], alternative="unsupported")


def test_no_valid_solver_incumbent_is_not_reported_as_a_plan(monkeypatch):
    monkeypatch.setattr(
        Model, "solve", lambda *_: (None, dict(valid_incumbent=False, status="time-limit"))
    )
    result = calculate([robot()], [10, 10])
    assert result["status"] == "unresolved" and result["plan"] is None
    assert result["solver"]["status"] == "time-limit"


@pytest.mark.parametrize(
    "change",
    [
        dict(initial_kwh=11),
        dict(efficiency=0),
        dict(use_kwh=(-1, 0)),
        dict(available=[True, True]),
        dict(required_at_offset=0),
        dict(required_at_offset=True),
        dict(target_kwh=float("nan")),
    ],
)
def test_invalid_battery_inputs_are_not_silently_adjusted(change):
    with pytest.raises(ValueError):
        robot(**change)


@pytest.mark.parametrize("prices", [[0, 1], [1, 2, 3], [0, 2, 1], [0, None, 1]])
def test_incomplete_or_nonmonotone_prices_cannot_enter_optimizer(prices):
    with pytest.raises((ValueError, TypeError)):
        calculate([robot()], [10, 10], prices=prices)


def runtime(*, dock_available=True, **options):
    from methane.field_operations import FieldOperations
    from methane.sensing import Diagnosis
    from methane.services.configuration import ServiceSystem
    from methane.services.plant import PlantServices

    cfg = FieldOperations(
        enabled=True,
        cleaner_enabled=False,
        rover_enabled=True,
        human_fallback=False,
        reset_enabled=False,
        dock_available=dock_available,
        dock_kw=10,
        rover_battery_kwh=10,
        charging_efficiency=0.8,
        mission_failure_probability=0,
    )
    rt = PlantServices(cfg, ServiceSystem(support_model="logistics/1", **options), 7, 450)
    # This teaching fixture starts with an empty docked rover. Change the declared
    # initial resource, not the current balance without a matching ledger basis.
    rt.ledger.__init__(
        [
            replace(r, initial=0) if r.resource_id == "energy:rover" else r
            for r in rt.ledger.specs.values()
        ]
    )
    return rt, Diagnosis(450)


def service_prices():
    from methane.service_economics import ACTIVITY_VERSION, illustrative

    a = illustrative(Costs(), version=ACTIVITY_VERSION)
    for asset in a["assets"].values():
        for key in asset:
            if key not in ("provision", "life_years"):
                asset[key] = 0
    for key in a["rates"]:
        a["rates"][key] = 0
    a["assets"]["dock"]["wear_eur_per_hour"] = 3
    return a


def control(rt, *, pv=(10, 0), target_hour=2, prices=None, prefix=()):
    from methane.services.charge_control import Target, evaluate

    p, data = fixture(), forecast(pv)
    hour = rt.executive.at_hour
    data["decision_hour"] = hour
    data["times"] = [
        (datetime.fromisoformat(t) + timedelta(hours=hour)).isoformat() for t in data["times"]
    ]
    return evaluate(
        rt,
        p,
        State.initial(p),
        data,
        0,
        Costs(),
        [Target("rover", 8, target_hour, "Energy for the declared next inspection")],
        service_prices=prices or service_prices(),
        recorded_prefix=prefix,
        seconds=2,
    )


def test_charge_proposal_is_read_only_and_actual_receipt_reconciles_with_plan_and_prices():
    from methane.config import Scenario
    from methane.faults import FaultPolicy, FaultState
    from methane.service_economics import report
    from methane.services.charge_control import accept

    rt, diagnosis = runtime()
    rt.prepare(0, diagnosis, 10)
    before = copy.deepcopy((rt.public(), rt.ledger.events, rt.interval))
    result = control(rt)
    assert result["state"] == "feasible", result["constraints"]
    assert result["demand"]["process_plan"] is None  # No redundant optimizer call.
    assert (rt.public(), rt.ledger.events, rt.interval) == before
    assert result["current_requests"] == [dict(robot="rover", power_kw=pytest.approx(10))]
    assert accept(rt, result) == pytest.approx(10)
    assert rt.energy["rover"] == 0  # Booking a charge is not an energy credit.
    faults = FaultState(Plant(), Scenario(), FaultPolicy())
    row = rt.end(0, faults, diagnosis)
    assert row["energy_after_kwh"]["rover"] == pytest.approx(8)
    assert row["charge_input_kwh"] == pytest.approx(10)
    assert row["charging_loss_kwh"] == pytest.approx(2)
    assert all(r["passed"] for r in rt.ledger.reconcile())
    assert row["selection"]["charging"][0]["accepted"]
    actual = report([dict(field_operations=row)], service_prices())
    assert actual["quantities"]["dock_hours"] == 1
    assert actual["views"]["decision"]["total_eur"] == 3
    assert result["charging"]["plan"]["incremental_service_decision_eur"] == 3


def test_stale_charge_plan_is_rejected_without_acceptance():
    from methane.services.charge_control import accept
    from methane.services.contracts import Quantity

    rt, diagnosis = runtime()
    rt.prepare(0, diagnosis, 10)
    result = control(rt)
    rt.ledger.replenish(Quantity("energy:rover", 1, "kWh"), 0, "Observed changed stock")
    with pytest.raises(ValueError, match="stale"):
        accept(rt, result)
    assert not rt.executive.missions


def test_ineligible_current_charge_is_explicit_and_does_not_silently_shrink():
    rt, diagnosis = runtime()
    rt.prepare(0, diagnosis, 6)
    before = copy.deepcopy(rt.ledger.events)
    with pytest.raises(ValueError, match="exceeds current limit"):
        rt.propose_charge("rover", 10)
    rt.dispatch_selected((), charge=False, charge_requests=[("rover", 10)])
    selected = rt.interval["selection"]["charging"][0]
    assert selected["requested_kw"] == 10 and not selected["accepted"]
    assert rt.ledger.events == before
    assert rt.interval["new_missions"] == []


def test_no_charger_means_an_unmet_target_not_free_inventory():
    rt, diagnosis = runtime(dock_available=False)
    rt.prepare(0, diagnosis, 10)
    result = control(rt)
    assert result["state"] == "unresolved" and not result["current_requests"]
    assert rt.energy["rover"] == 0
    assert not rt.executive.missions


@pytest.mark.parametrize("recovery", [False, True])
def test_unobserved_charger_fault_changes_receipt_not_the_earlier_charge_decision(recovery):
    from methane.config import Scenario
    from methane.faults import FaultPolicy, FaultState
    from methane.services.charge_control import accept

    cases = []
    for cause in ("none", "charger-power-loss"):
        rt, diagnosis = runtime(equipment_recovery_enabled=recovery)
        rt.prepare(0, diagnosis, 10)
        result = control(rt)
        assert result["state"] == "feasible"
        accept(rt, result)
        fault = FaultState(
            Plant(), Scenario(), FaultPolicy(dock_service_fault=cause, service_fault_start_hour=0)
        )
        row = rt.end(0, fault, diagnosis)
        cases.append((result, row))
        if cause != "none":
            assert row["requested_service_kwh"] == pytest.approx(10)
            assert row["unapplied_service_kwh"] == pytest.approx(10)
            assert row["charge_input_kwh"] == row["energy_after_kwh"]["rover"] == 0
            assert any(e["kind"] == "interrupted" for e in row["mission_events"])
            rt.prepare(1, diagnosis, 10)
            next_plan = control(rt, prefix=[dict(field_operations=row)])
            assert next_plan["state"] == "unresolved"
            assert not next_plan["current_requests"]
    assert cases[0][0]["current_requests"] == cases[1][0]["current_requests"]
    assert cases[0][0]["charging"]["inputs"] == cases[1][0]["charging"]["inputs"]
    assert cases[0][1]["energy_after_kwh"]["rover"] == pytest.approx(8)


def test_future_reserved_slot_is_not_available_for_planned_charging():
    from methane.services.core import ASSETS
    from methane.services.resources import Booking

    rt, diagnosis = runtime()
    rt.prepare(0, diagnosis, 10)
    rt.ledger.reserve(
        "existing-reservation", (), [Booking("asset:" + ASSETS["dock"], 1, 2, 1, "slot")], 0
    )
    result = control(rt, pv=(10, 10))
    assert result["state"] == "feasible"
    assert result["charging"]["inputs"]["dock_available_kw"] == [10, 0]
    assert result["current_requests"][0]["power_kw"] == pytest.approx(10)


def test_can_charge_before_a_committed_departure_without_borrowing_its_return_reserve():
    from methane.services.charge_control import accept

    rt, diagnosis = runtime()
    rt.ledger.__init__(
        [
            replace(r, initial=4) if r.resource_id == "energy:rover" else r
            for r in rt.ledger.specs.values()
        ]
    )
    diagnosis = replace(
        diagnosis,
        capacity_kw=225,
        active_incident=True,
        incidents=1,
        informative=True,
        status="capacity loss",
        tracking_residual=0.5,
    )
    rt.prepare(0, diagnosis, 10)
    order = rt.orders[0]
    mission, assessment = rt.propose(order["id"], starting_at=1)
    assert assessment["feasible"]
    rt.executive.submit(mission)
    rt._accepted(order, mission, 0)
    result = control(rt, pv=(10, 0, 0, 0), target_hour=1)
    assert result["state"] == "feasible", result["constraints"]
    assert result["current_requests"][0]["power_kw"] == pytest.approx(5)
    inputs = result["charging"]["inputs"]["batteries"][0]
    assert inputs["available"] == (True, False, False, False)
    assert sum(inputs["use_kwh"]) == pytest.approx(0.45)
    assert inputs["reserve_kwh"] == (0.2,) * 4
    assert result["charging"]["plan"]["charging"][-1]["after_kwh"] == pytest.approx(7.55)
    assert accept(rt, result) == pytest.approx(5)
    assert rt.interval["selection"]["charging"][0]["accepted"]
    assert rt.energy["rover"] == 4


def test_exploration_cannot_read_fault_draws_or_accept_an_unavailable_forecast(monkeypatch):
    from methane.services.charge_control import Target, evaluate

    rt, diagnosis = runtime()
    rt.prepare(0, diagnosis, 10)
    monkeypatch.setattr(
        rt._effects, "draw", lambda *_: pytest.fail("Planning requested hidden outcome")
    )
    assert control(rt)["state"] == "feasible"
    data, p = forecast([10, 0]), fixture()
    data["decision_hour"] = 0
    data["source"]["available_at"] = "2026-01-01T01:00:00Z"
    with pytest.raises(ValueError, match="not available"):
        evaluate(
            rt,
            p,
            State.initial(p),
            data,
            0,
            Costs(),
            [Target("rover", 8, 2, "Future mission")],
            service_prices=service_prices(),
        )


def test_deadline_does_not_roll_forward_and_missing_prices_remain_unknown():
    rt, diagnosis = runtime()
    rt.prepare(0, diagnosis, 10)
    with pytest.raises(ValueError, match="beyond the selected horizon"):
        control(rt, target_hour=3)
    prices = service_prices()
    prices["assets"]["dock"]["wear_eur_per_hour"] = None
    result = control(rt, prices=prices)
    assert result["state"] == "unresolved"
    assert result["pricing"]["status"] == "incomplete-prices"
    assert result["charging"] is None


def test_dock_usage_table_reuses_existing_replaceable_parts_allowance():
    from methane.services.pricing import dock_cost_table

    prices = service_prices()
    prices["assets"]["dock"]["wear_eur_per_hour"] = 600
    prefix = [
        dict(
            field_operations=dict(
                hour=0,
                assets=dict(dock=True),
                crew_committed_hours=0,
                mission_events=[],
                resource_events=[
                    dict(
                        kind="consume",
                        resource="stock:hardware:dock",
                        amount=1,
                        unit="module",
                        phase="perform",
                    )
                ],
                state=dict(executive=dict(resources=[])),
            )
        )
    ]
    table = dock_cost_table((), prices, at_hour=1, hours=3, installed=["dock"], prefix=prefix)
    # A €1,000 part is already in the dock's allowance. More activity only costs
    # the excess: max(1000, 600*n) - 1000, not a second parts plus wear charge.
    assert table["incremental_decision_eur"] == [0, 0, 200, 800]
    assert table["status"] == "complete"
    prices["assets"]["dock"].update(capital_eur=1000000, replaceable_capital_eur=10000)
    assert dock_cost_table((), prices, at_hour=1, hours=3, installed=["dock"], prefix=prefix)[
        "incremental_decision_eur"
    ] == [0, 0, 200, 800]


def test_new_mission_and_charge_share_slots_and_reconcile_actual_combined_cost():
    from methane.config import Scenario
    from methane.faults import FaultPolicy, FaultState
    from methane.service_economics import report
    from methane.services.charge_control import Target, accept, evaluate

    rt, diagnosis = runtime()
    rt.ledger.__init__(
        [
            replace(r, initial=4) if r.resource_id == "energy:rover" else r
            for r in rt.ledger.specs.values()
        ]
    )
    diagnosis = replace(
        diagnosis,
        capacity_kw=225,
        active_incident=True,
        incidents=1,
        informative=True,
        status="capacity loss",
        tracking_residual=0.5,
    )
    rt.prepare(0, diagnosis, 10)
    order = rt.orders[0]
    prices = service_prices()
    prices["assets"]["rover"]["wear_eur_per_hour"] = 8
    data, p = forecast([10] * 6), fixture()
    data["decision_hour"] = 0
    before = copy.deepcopy((rt.public(), rt.ledger.events))
    result = evaluate(
        rt,
        p,
        State.initial(p),
        data,
        225,
        Costs(),
        [Target("rover", 8, 1, "Declared reserve before inspection")],
        selections=[(order["id"], 1)],
        joint_work=True,
        service_prices=prices,
        seconds=2,
    )
    assert result["state"] == "feasible", result["constraints"]
    assert (rt.public(), rt.ledger.events) == before
    assert result["mission_decision_eur"] > 0
    inputs = result["charging"]["inputs"]["batteries"][0]
    assert inputs["available"][:4] == (True, False, False, False)
    assert result["current_requests"] == [dict(robot="rover", power_kw=pytest.approx(5))]
    accept(rt, result)
    assert all(x["accepted"] for x in rt.interval["selection"]["results"])
    assert all(x["accepted"] for x in rt.interval["selection"]["charging"])
    fault = FaultState(p, Scenario(), FaultPolicy())
    rows = [dict(field_operations=rt.end(0, fault, diagnosis))]
    for hour in range(1, 6):
        rt.prepare(hour, diagnosis, 10)
        rt.dispatch_selected((), charge=False)
        rows.append(dict(field_operations=rt.end(hour, fault, diagnosis)))
    actual = report(rows, prices)
    expected = (
        result["mission_decision_eur"]
        + result["charging"]["plan"]["incremental_service_decision_eur"]
    )
    assert actual["views"]["decision"]["total_eur"] == pytest.approx(expected)
    assert rt.energy["rover"] == pytest.approx(
        result["charging"]["plan"]["charging"][-1]["after_kwh"]
    )
    assert all(x["passed"] for x in rt.ledger.reconcile())


def test_joint_work_retains_impossible_and_overdue_targets_explicitly():
    from methane.services.charge_control import Target, evaluate

    rt, diagnosis = runtime(dock_available=False)
    rt.prepare(0, diagnosis, 10)
    p, data = fixture(), forecast([10, 10])
    data["decision_hour"] = 0
    result = evaluate(
        rt,
        p,
        State.initial(p),
        data,
        0,
        Costs(),
        [Target("rover", 11, 1, "Too much energy for installed hardware")],
        service_prices=service_prices(),
        joint_work=True,
    )
    assert result["state"] == "infeasible"
    assert result["targets"][0]["energy_kwh"] == 11
    assert "capacity" in result["constraints"][0]["condition"]
    assert rt.energy["rover"] == 0 and not rt.executive.missions
