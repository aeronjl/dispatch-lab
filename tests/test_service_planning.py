"""Independent interval arithmetic and read-only service decision boundaries."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from methane.config import Costs, Plant, Scenario
from methane.faults import FaultPolicy, FaultState
from methane.field_operations import FieldOperations
from methane.physics import State
from methane.sensing import Diagnosis
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.adapters import fixed
from methane.services.configuration import ServiceSystem
from methane.services.contracts import (
    Asset,
    Capability,
    Context,
    Interface,
    Quantity,
    Reading,
    Requirement,
    Stage,
    WorkOrder,
)
from methane.services.coupling import accept, evaluate
from methane.services.executive import Executive, Receipt
from methane.services.planning import Commitment, assess_candidate, horizon
from methane.services.plant import PlantServices
from methane.services.resources import Ledger, Resource
from methane.services.scenario_planning import Branch


def example(key="A", start=0):
    asset = Asset(key, "station", "test-station/1", "port", "fixed", ("work",), ())
    cap = Capability("work", "test", "observe", "test-method/1", 0.25, 0, work_kw=4)
    port = Interface("port", "ELY-01", "port", ("test",), ())
    plan = fixed(
        WorkOrder(key, "test", "port", 0, "Test measurement"),
        asset,
        port,
        cap,
        Context(0, ()),
        starting_at=start,
    )
    return replace(
        plan,
        stages=(
            Stage(
                "perform",
                0.25,
                "port",
                "port",
                bus_kw=4,
                consumables=(Quantity("references", 1, "kit"),),
                hourly_consumables=(Quantity("water", 2, "L"),),
                reservations=(Quantity("isolation", 1, "slot"),),
                effect=True,
            ),
        ),
    )


def ledger():
    return Ledger(
        (
            Resource("references", "kit", "stock", 4, 4),
            Resource("water", "L", "stock", 10, 10),
            Resource("plant:service-power", "kW", "capacity", 8),
            Resource("isolation", "slot", "capacity", 1),
            *(Resource("asset:" + k, "slot", "capacity", 1) for k in ("A", "B")),
        )
    )


def test_fractional_power_peak_is_not_hourly_energy_and_boundary_is_half_open():
    first, second = example(start=0.75), example("B", start=1)
    data = horizon(
        (Commitment(first), Commitment(second)),
        0,
        2,
        standby_kw=0.1,
        isolation_resource="isolation",
    )
    assert [r["bus_kwh"] for r in data["rows"]] == [1.1, 1.1]
    assert [r["bus_peak_kw"] for r in data["rows"]] == [4.1, 4.1]
    assert [r["electrolyser_isolated"] for r in data["rows"]] == [True, True]
    assert [r["order_ids"] for r in data["rows"]] == [["A"], ["B"]]
    assert data["terminal_obligations"] == []
    simultaneous = horizon((Commitment(first), Commitment(example("B", start=0.875))), 0, 2)
    assert [r["bus_peak_kw"] for r in simultaneous["rows"]] == [8, 4]
    assert [r["bus_kwh"] for r in simultaneous["rows"]] == [1.5, 0.5]


def test_terminal_work_excludes_waiting_and_keeps_return_margin_unspent():
    p = example(start=3)
    p = replace(
        p,
        asset=replace(p.asset, battery_resource="robot", return_reserve_kwh=0.4),
        stages=(
            replace(p.stages[0], bus_kw=0, battery_kw=2),
            Stage("return", 0.5, "port", "dock", battery_kw=1),
        ),
    )
    data = horizon((Commitment(p),), 0, 1)
    terminal = data["terminal_obligations"][0]
    assert terminal["remaining_work_hours"] == 0.75
    assert terminal["waiting_hours"] == 2
    assert terminal["time_until_completion_hours"] == 2.75
    assert terminal["return_hours"] == 0.5
    assert terminal["battery_use_after_horizon_kwh"] == 1
    assert terminal["held_return_margin_kwh"] == 0.4
    assert data["rows"][0]["robot_use_kwh"] == {}


def test_observed_cursor_does_not_consume_entry_material_twice():
    p = replace(example(), stages=(replace(example().stages[0], duration_hours=2),))
    start = horizon((Commitment(p),), 0, 1)["rows"][0]
    rest = horizon((Commitment(p, entered=True),), 1, 1)["rows"][0]
    assert start["stock_use"] == [
        dict(resource="references", unit="kit", amount=1),
        dict(resource="water", unit="L", amount=2),
    ]
    assert rest["stock_use"] == [dict(resource="water", unit="L", amount=2)]
    assert all(e["basis"] == "rate" for e in rest["stock_events"])
    assert start["bus_kwh"] == rest["bus_kwh"] == 4


def test_remaining_projection_reconciles_with_executive_and_independent_decimal():
    class NoTruth:
        def perform(self, plan, completed_at):
            return Receipt("Attempt completed")

    p = replace(example(start=0.75), stages=(replace(example().stages[0], duration_hours=1.5),))
    runtime = Executive(ledger(), NoTruth())
    runtime.submit(p)
    initial = horizon((Commitment(p),), 0, 3)
    runtime.advance(1, Context(0, ()))
    m = runtime.missions["A"]
    remaining = horizon((Commitment(m.plan, m.stage_index, m.entered),), 1, 2)
    assert sum(r["bus_kwh"] for r in initial["rows"]) == float(Decimal("1.5") * Decimal(4))
    assert sum(r["bus_kwh"] for r in remaining["rows"]) == float(Decimal("1.25") * Decimal(4))
    runtime.advance(3, Context(1, ()))
    assert m.bus_kwh == sum(r["bus_kwh"] for r in initial["rows"])
    assert runtime.ledger.stock["references"] == 3
    assert runtime.ledger.stock["water"] == 7
    assert all(r["passed"] for r in runtime.ledger.reconcile())


@pytest.mark.parametrize(
    "change,origin", [(dict(stage_index=1), 0), (dict(entered=True), 0), ({}, 2), ({}, 1)]
)
def test_invalid_or_unobserved_execution_cursor_is_rejected(change, origin):
    p = example(start=0.5)
    with pytest.raises(ValueError):
        horizon((Commitment(p, **change),), origin, 1)


def test_future_context_duplicates_and_invalid_horizons_are_rejected():
    p = example()
    with pytest.raises(ValueError, match="once"):
        horizon((Commitment(p), Commitment(p)), 0, 1)
    p = replace(p, context=Context(1, ()), starting_at=1)
    with pytest.raises(ValueError, match="future"):
        horizon((Commitment(p),), 0, 1)
    for hours in (0, True, 0.5, 8761):
        with pytest.raises(ValueError):
            horizon((), 0, hours)


def test_candidate_assessment_is_read_only_and_keeps_resource_and_eligibility_reasons():
    p, resources = example(), ledger()
    before = copy.deepcopy(vars(resources))
    for _ in range(3):
        assert assess_candidate(p, resources, 0)["feasible"]
    assert vars(resources) == before
    need = Requirement("route", "equals", True, "boolean", 1)
    p = replace(
        p,
        stages=(replace(p.stages[0], requirements=(need,)),),
        context=Context(0, (Reading("route", False, "boolean", 0, 0, "declared/1"),)),
    )
    resources.stock["references"] = 0
    assessment = assess_candidate(p, resources, 0)
    assert not assessment["feasible"]
    assert any("route" in r for r in assessment["reasons"])
    assert any("references" in r for r in assessment["reasons"])
    assert not resources.seen_missions and not resources.events


def plant_runtime(*, support_model="none", **overrides):
    config = replace(
        FieldOperations(
            enabled=True,
            cleaner_enabled=False,
            human_fallback=False,
            dock_available=False,
            reset_enabled=False,
            mission_failure_probability=0,
        ),
        **overrides,
    )
    options = ServiceSystem(
        support_model=support_model,
        inspector="fixed",
        contact_error_probability=0,
        contact_unreadable_probability=0,
        outcome_randomness="target-action-request/1",
    )
    return PlantServices(config, options, 7, 450)


def diagnosis():
    return Diagnosis(
        225,
        active_incident=True,
        incidents=1,
        informative=True,
        status="capacity loss",
        tracking_residual=0.5,
    )


def faults():
    return FaultState(
        Plant(),
        Scenario(fault_start_hour=0, capacity_fraction=0.5),
        FaultPolicy(capacity_cause="equipment-damage"),
    )


def test_proposals_do_not_accept_work_reserve_or_sample_and_delay_is_executed():
    rt, d, f = plant_runtime(), diagnosis(), faults()
    rt.prepare(0, d, 650)
    key = rt.orders[0]["id"]
    before = copy.deepcopy(
        (rt.public(), vars(rt.ledger), vars(rt._effects.random_events), rt.interval)
    )
    for _ in range(3):
        p, a = rt.propose(key, starting_at=1)
        assert p.starting_at == 1 and a["feasible"]
        projection = rt.planned_demands(3, candidates=(p,))
        assert [r["bus_kwh"] for r in projection["rows"]] == [0, 0.2, 0.05]
    assert (rt.public(), vars(rt.ledger), vars(rt._effects.random_events), rt.interval) == before
    assert rt.dispatch_selected(((key, 1),), charge=False, projection_hours=3) == 0
    assert rt.interval["decision"]["committed_demands"] == projection
    row = rt.end(0, f, d)
    assert row["applied_service_kwh"] == 0 and not row["state"]["executive"]["observations"]
    rt.begin(1, d, 650)
    row = rt.end(1, f, d)
    assert row["applied_service_kwh"] == pytest.approx(0.2)
    rt.begin(2, d, 650)
    row = rt.end(2, f, d)
    assert row["applied_service_kwh"] == pytest.approx(0.05)
    assert row["state"]["executive"]["observations"][0]["available_at"] == 2
    assert f.truth(3)["capacity_kw"] == 225


def test_selected_plan_is_rebuilt_and_rechecks_current_power_and_stock():
    rt = plant_runtime()
    rt.prepare(0, diagnosis(), 0.1)
    key = rt.orders[0]["id"]
    _, assessment = rt.propose(key)
    assert not assessment["feasible"] and "solar" in str(assessment["reasons"])
    assert rt.dispatch_selected(((key, 0),), charge=False) == 0
    assert rt.interval["selection"]["results"][0]["accepted"] is False
    assert not rt.executive.missions and not rt.ledger.seen_missions
    assert rt._effects.random_events.count == 0


def test_preparation_and_decision_must_finish_before_execution_or_a_new_decision():
    rt, f, d = plant_runtime(), faults(), diagnosis()
    with pytest.raises(ValueError, match="prepared"):
        rt.propose("missing")
    rt.prepare(0, d, 650)
    with pytest.raises(ValueError, match="open service"):
        rt.prepare(0, d, 650)
    with pytest.raises(ValueError, match="exactly once"):
        rt.execute_interval(0, f)
    rt.dispatch_selected((), charge=False)
    rt.end(0, f, d)
    with pytest.raises(ValueError, match="accepted interval"):
        rt.end(0, f, d)
    with pytest.raises(ValueError, match="current service"):
        rt.planned_demands(2)
    rt.prepare(1, d, 650)
    assert not rt.executive.missions


def test_repeated_projection_of_accepted_mission_uses_current_cursor():
    rt, f, d = plant_runtime(inspection_hours=2), faults(), diagnosis()
    rt.begin(0, d, 650)
    first = rt.planned_demands(3)
    assert first["rows"][0]["bus_kwh"] == 0.2
    rt.end(0, f, d)
    rt.prepare(1, d, 650)
    rest = rt.planned_demands(2)
    assert [r["bus_kwh"] for r in rest["rows"]] == [0.2, 0.05]
    assert all(r["stock_use"] == [] for r in rest["rows"])
    rt.dispatch_local()
    rt.end(1, f, d)


def forecast(pv):
    return dict(
        pv_kw=pv,
        ambient_c=[20] * len(pv),
        deliveries_kg=[0] * len(pv),
        decision_hour=0,
        times=[
            (datetime(2026, 1, 1, tzinfo=UTC) + timedelta(hours=i)).isoformat()
            for i in range(len(pv))
        ],
        source=dict(
            id="saved-teaching-issue/1",
            initialized_at="2026-01-01T00:00:00+00:00",
            available_at="2026-01-01T00:00:00+00:00",
        ),
    )


def test_joint_evaluation_rejects_forecast_power_loss_and_can_accept_a_later_window():
    rt, d, p = plant_runtime(inspection_hours=2), diagnosis(), Plant()
    rt.prepare(0, d, 1)
    key = rt.orders[0]["id"]
    weather = forecast([1, 0.1, 1, 1, 1])
    state = State.initial(p)
    before = copy.deepcopy(
        (rt.public(), rt.interval, vars(rt.ledger), vars(rt._effects.random_events), weather)
    )
    early = evaluate(rt, p, state, weather, 225, Costs(), ((key, 0),), objective="greedy")
    assert early["state"] == "infeasible" and early["process_plan"] is None
    assert early["constraints"] == [
        dict(
            condition="active service solar power",
            offset=1,
            required_kw=0.2,
            available_kw=0.1,
            order_ids=[key],
            reason="Declared tool/charger peak exceeds forecast solar supply",
        )
    ]
    later = evaluate(rt, p, state, weather, 225, Costs(), ((key, 2),), objective="greedy")
    assert later["state"] == "feasible"
    assert later["forecast"]["service_kw"] == [0, 0, 0.2, 0.2, 0.05]
    assert (
        rt.public(),
        rt.interval,
        vars(rt.ledger),
        vars(rt._effects.random_events),
        weather,
    ) == before
    assert early["input_key"] == later["input_key"]
    assert accept(rt, later) == 0
    f = faults()
    rt.end(0, f, d)
    applied = []
    for hour in range(1, 5):
        rt.prepare(hour, d, weather["pv_kw"][hour])
        rt.dispatch_selected((), charge=False)
        row = rt.end(hour, f, d)
        applied.append(row["applied_service_kwh"])
        assert all(a["passed"] for a in row["audits"])
    assert applied == pytest.approx([0, 0.2, 0.2, 0.05])
    assert rt.executive.missions[key].completed_at == 4.25
    assert not any(e["kind"] == "interrupted" for e in rt.executive.missions[key].events)


def test_comparison_cannot_evade_work_or_return_by_moving_it_past_the_window():
    rt, p = plant_runtime(), Plant()
    rt.prepare(0, diagnosis(), 1)
    key = rt.orders[0]["id"]
    result = evaluate(rt, p, State.initial(p), forecast([1] * 3), 225, Costs(), ((key, 2),))
    assert result["state"] == "infeasible"
    assert result["constraints"][0]["condition"] == "new work completion"
    conditional = evaluate(
        rt,
        p,
        State.initial(p),
        forecast([1] * 3),
        225,
        Costs(),
        ((key, 2),),
        complete_new_work=False,
        objective="greedy",
    )
    assert conditional["state"] == "feasible"
    assert conditional["projection"]["terminal_obligations"][0]["remaining_work_hours"] == 0.25
    assert conditional["assumptions"]["complete_new_work_within_horizon"] is False


def test_forecast_current_power_must_match_the_service_decision():
    rt, p = plant_runtime(), Plant()
    rt.prepare(0, diagnosis(), 1)
    with pytest.raises(ValueError, match="current power"):
        evaluate(rt, p, State.initial(p), forecast([2, 2]), 225, Costs())


def test_no_incumbent_is_unresolved_and_never_a_feasible_zero_action_plan(monkeypatch):
    rt, p = plant_runtime(), Plant()
    rt.prepare(0, diagnosis(), 1)

    def no_incumbent(*args, **kwargs):
        assert kwargs["allow_fallback"] is False
        return dict(
            actions=[],
            trajectory=[],
            predicted=None,
            solver=dict(status="time-limited", valid_incumbent=False),
        )

    monkeypatch.setattr("methane.services.coupling.process_plan", no_incumbent)
    result = evaluate(rt, p, State.initial(p), forecast([1, 1]), 225, Costs())
    assert result["state"] == "unresolved"
    assert result["constraints"][0]["solver"]["status"] == "time-limited"
    with pytest.raises(ValueError, match="feasible"):
        accept(rt, result)
    assert not rt.ledger.seen_missions


def test_late_candidate_cannot_be_accepted_after_current_resources_change():
    rt, p = plant_runtime(), Plant()
    rt.prepare(0, diagnosis(), 1)
    result = evaluate(rt, p, State.initial(p), forecast([1, 1]), 225, Costs(), objective="greedy")
    assert result["state"] == "feasible"
    rt.ledger.stock["stock:calibration"] = 0
    with pytest.raises(ValueError, match="stale"):
        accept(rt, result)


def test_joint_capacity_check_catches_individually_feasible_competing_work():
    rt, p = plant_runtime(), Plant()
    rt.prepare(0, diagnosis(), 1)
    first = rt.orders[0]["id"]
    other = copy.deepcopy(rt.orders[0])
    other["id"] = "ANOTHER-REQUEST"
    rt.orders.append(other)
    for key in (first, other["id"]):
        assert rt.propose(key)[1]["feasible"]
    result = evaluate(
        rt, p, State.initial(p), forecast([1, 1]), 225, Costs(), ((first, 0), (other["id"], 0))
    )
    assert (
        result["state"] == "infeasible"
        and result["constraints"][0]["condition"] == "joint resources"
    )
    assert "capacity" in result["constraints"][0]["reason"]
    assert not rt.executive.missions and not rt.ledger.holds


@pytest.mark.parametrize(
    "problem", ["unpublished", "different-decision", "missing-hour", "missing-origin"]
)
def test_future_or_unidentified_forecast_cannot_enter_a_service_comparison(problem):
    rt, p = plant_runtime(), Plant()
    rt.prepare(0, diagnosis(), 1)
    weather = forecast([1, 1])
    if problem == "unpublished":
        weather["source"]["available_at"] = "2026-01-01T01:00:00+00:00"
    elif problem == "different-decision":
        weather["decision_hour"] = 1
    elif problem == "missing-hour":
        weather["times"][1] = "2026-01-01T02:00:00+00:00"
    else:
        del weather["source"]["available_at"]
    with pytest.raises(ValueError, match="Forecast"):
        evaluate(rt, p, State.initial(p), weather, 225, Costs())
    assert not rt.executive.missions and not rt.ledger.holds


def test_costed_outcome_comparison_and_acceptance_use_one_current_service_decision():
    rt, p = plant_runtime(inspection_hours=2, support_model="logistics/1"), Plant()
    rt.prepare(0, diagnosis(), 1)
    key = rt.orders[0]["id"]
    nominal = forecast([1] * 5)
    dark = copy.deepcopy(nominal)
    dark["pv_kw"][1] = 0.1
    branches = (
        Branch.create(
            "nominal",
            0.5,
            nominal,
            ("same", "nominal", "nominal", "nominal", "nominal"),
            source="assumption:weather-error/1",
        ),
        Branch.create(
            "cloud",
            0.5,
            dark,
            ("same", "cloud", "cloud", "cloud", "cloud"),
            source="assumption:weather-error/1",
        ),
    )
    prices = illustrative(Costs(), version=ACTIVITY_VERSION)
    prices["assets"]["fixed_reader"]["wear_eur_per_hour"] = 8
    early = evaluate(
        rt,
        p,
        State.initial(p),
        nominal,
        225,
        Costs(),
        ((key, 0),),
        service_prices=prices,
        outcome_branches=branches,
        seconds=2,
    )
    assert early["state"] == "infeasible"
    assert early["constraints"][0]["condition"] == "outcome service solar power"
    later = evaluate(
        rt,
        p,
        State.initial(p),
        nominal,
        225,
        Costs(),
        ((key, 2),),
        service_prices=prices,
        outcome_branches=branches,
        risk_weight=0.3,
        seconds=2,
    )
    assert later["state"] == "feasible", later
    assert later["service_pricing"]["incremental_decision_eur"] == 18
    assert (
        later["outcome_plan"]["branches"][0]["actions"][0]
        == later["outcome_plan"]["branches"][1]["actions"][0]
    )
    assert all(b["service_decision_eur"] == 18 for b in later["outcome_plan"]["branches"])
    assert not rt.executive.missions
    assert accept(rt, later) == 0
    assert rt.interval["decision"]["coupled_evaluation"]["outcome_plan"]["risk_weight"] == 0.3


def test_priced_candidate_requires_the_same_execution_ledger_as_its_cost_report():
    rt, p = plant_runtime(), Plant()
    rt.prepare(0, diagnosis(), 1)
    with pytest.raises(ValueError, match="finite-logistics"):
        evaluate(
            rt,
            p,
            State.initial(p),
            forecast([1] * 5),
            225,
            Costs(),
            service_prices=illustrative(Costs(), version=ACTIVITY_VERSION),
        )
    assert not rt.executive.missions
