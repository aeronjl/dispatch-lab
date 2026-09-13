"""Planned shared work: independent itinerary, costs, and actual execution."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from methane.config import Config, Costs, Scenario
from methane.faults import FaultState
from methane.field_operations import FieldOperations
from methane.physics import State
from methane.sensing import Diagnosis
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services import charge_control, coupling
from methane.services.configuration import ServiceSystem
from methane.services.plant import PlantServices


def fixture(**changes):
    c = Config(
        scenario=Scenario(hours=12, horizon_hours=6, solver_seconds=2),
        field_operations=FieldOperations(
            enabled=True,
            initial_soiling_fraction=0,
            soiling_per_day=0,
            mission_failure_probability=0,
        ),
        service_system=ServiceSystem(
            inspector="mobile",
            support_model="logistics/1",
            visit_bundling_enabled=True,
            maintenance_enabled=True,
            maintenance_target="resident",
            maintenance_first_due_hour=0,
            maintenance_interval_hours=24,
            maintenance_work_hours=0.5,
            maintenance_kits=8,
            crew_response_lead_hours=0,
            crew_travel_hours=0.25,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
            replenishment_enabled=False,
            outcome_randomness="target-action-request/1",
        ),
        service_economics=illustrative(Costs(), version=ACTIVITY_VERSION),
    )
    c = replace(c, service_system=replace(c.service_system, **changes))
    rt = PlantServices(c.field_operations, c.service_system, 7, c.plant.electrolyser_kw)
    rt.prepare(0, Diagnosis(450), 750)
    orders = [q["id"] for q in rt.orders if q["kind"] == "routine-service"]
    assert len(orders) == 4
    return c, rt, tuple(orders)


def forecast(n=6):
    start = datetime(2026, 4, 10, tzinfo=UTC)
    return dict(
        decision_hour=0,
        times=[(start + timedelta(hours=h)).isoformat() for h in range(n)],
        source=dict(
            id="shared-visit-example",
            initialized_at=start.isoformat(),
            available_at=start.isoformat(),
        ),
        pv_kw=[750] * n,
        ambient_c=[20] * n,
        deliveries_kg=[0] * n,
    )


def evaluate(c, rt, *, singles=(), groups=(), hours=6, project_only=True):
    return coupling.evaluate(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(hours),
        450,
        c.costs,
        singles,
        visit_groups=groups,
        service_prices=c.service_economics,
        project_only=project_only,
        seconds=2,
    )


def test_future_visit_shifts_time_without_using_future_observations_or_mutating_runtime():
    c, rt, keys = fixture()
    before = copy.deepcopy((rt.public(), rt.interval, rt.orders, rt.ledger.events))
    visit, assessment = rt.propose_visit(keys[:2], starting_at=2)
    assert assessment["feasible"]
    # Two .5-hour jobs at the dock share .25-hour outward/return journeys.
    assert visit.starting_at == 2
    assert visit.ending_at == float(
        Decimal(2) + Decimal(".25") + 2 * Decimal(".5") + Decimal(".25")
    )
    assert all(p.context.at_hour == 0 for p in visit.members)
    assert [p.order.order_id for p in visit.members] == list(keys[:2])
    assert (
        sum(q["amount"] for q in assessment["requested_stocks"] if q["resource"] == "crew-hours")
        == 1.5
    )
    assert (rt.public(), rt.interval, rt.orders, rt.ledger.events) == before
    # Proposals do not consume the matched stochastic event stream.
    assert rt._effects.random_events.count == 0


def test_shared_projection_cost_matches_independent_trip_and_labour_calculation():
    c, rt, keys = fixture()
    # Compare conditional quantities; two independent departures cannot be
    # accepted at one decision before the first return has been observed.
    from methane.services.planning import Commitment
    from methane.services.pricing import price

    separate_quote = price(
        (),
        [
            Commitment(rt.propose(key, starting_at=start)[0])
            for key, start in ((keys[0], 1), (keys[1], 2))
        ],
        c.service_economics,
        at_hour=0,
        hours=6,
        installed=[k for k, present in rt.interval["assets"].items() if present],
    )
    separate = {"service_pricing": separate_quote}
    combined = evaluate(c, rt, groups=((keys[:2], 1),))
    assert combined["state"] == "projected" and separate_quote["status"] == "complete"
    a, b = (
        x["service_pricing"]["with_additions"]["predicted_quantities"] for x in (separate, combined)
    )
    assert (a["human_visits"], b["human_visits"]) == (2, 1)
    assert (a["crew-hours"], b["crew-hours"]) == (2, 1.5)
    expected_saving = Decimal(300) + Decimal(".5") * Decimal(80) + Decimal(".5") * Decimal(20)
    assert separate["service_pricing"]["incremental_decision_eur"] - combined["service_pricing"][
        "incremental_decision_eur"
    ] == float(expected_saving)
    assert len(rt.executive.missions) == 0


def test_accepted_future_visit_reconciles_with_projection_and_keeps_per_job_effects():
    c, rt, keys = fixture()
    predicted = evaluate(c, rt, groups=((keys[:2], 1),), project_only=False)
    # Use the public acceptance interface, which rebuilds and rechecks recipes.
    assert predicted["state"] == "feasible"
    coupling.accept(rt, predicted)
    assert len(rt.executive.visits) == 1
    assert len(rt.executive.missions) == 2
    assert rt._effects.random_events.count == 0
    assert all(rt._effects.random_events.identity(key) for key in keys[:2])
    faults, diagnosis, rows = FaultState(c.plant, c.scenario, c.faults), Diagnosis(450), []
    for hour in range(4):
        if hour:
            rt.prepare(hour, diagnosis, 750)
            rt.dispatch_selected((), charge=False)
        rt.execute_interval(hour, faults)
        rows.append(rt.end(hour, faults, diagnosis))
    assert sum(r["human_visits"] for r in rows) == 1
    assert sum(r["crew_committed_hours"] for r in rows) == 1.5
    assert rows[0]["human_visits"] == 0
    effects = [e for r in rows for e in r["support_effects"] if e["kind"] == "routine-service"]
    assert len(effects) == 2 and len({e["order_id"] for e in effects}) == 2
    assert rt.ledger.stock["stock:maintenance"] == 6
    assert all(r["passed"] for r in rt.ledger.reconcile())
    from methane.reference import service_accounts
    from methane.service_economics import report

    recorded = [dict(field_operations=r) for r in rows]
    actual = report(recorded, c.service_economics)
    independent = service_accounts(c.service_economics, recorded)
    expected = (
        Decimal(300) + Decimal("1.5") * Decimal(80) + Decimal(".5") * Decimal(20) + 2 * Decimal(50)
    )
    assert (
        actual["views"]["decision"]["total_eur"]
        == predicted["service_pricing"]["incremental_decision_eur"]
        == float(expected)
    )
    assert independent["decision"] == expected


def test_visit_and_standalone_job_cannot_claim_the_same_crew_or_order():
    c, rt, keys = fixture()
    blocked = evaluate(c, rt, singles=((keys[2], 1),), groups=((keys[:2], 1),))
    assert blocked["state"] == "infeasible"
    assert any(
        q["condition"] in ("joint resources", "crew return dependency")
        for q in blocked["constraints"]
    )
    with pytest.raises(ValueError, match="only once"):
        rt.dispatch_selected(((keys[0], 0),), visit_groups=((keys[:2], 1),))
    assert not rt.executive.missions and not rt.executive.visits


def test_two_visits_require_observed_return_without_promising_replenishment():
    c, rt, keys = fixture(maintenance_kits=3)
    blocked = evaluate(c, rt, groups=((keys[:2], 0), (keys[2:], 3)))
    assert blocked["state"] == "infeasible"
    assert any(
        q["condition"] in ("joint resources", "crew return dependency")
        for q in blocked["constraints"]
    )
    assert rt.ledger.stock["stock:maintenance"] == 3
    assert not rt.executive.missions


@pytest.mark.parametrize("change", ["stock", "lead", "shift", "disabled", "future-horizon"])
def test_missing_prerequisites_remain_explicit_without_partially_accepting_a_visit(change):
    options = {
        "stock": dict(maintenance_kits=1),
        "lead": dict(crew_response_lead_hours=3),
        "shift": dict(crew_shift_duration_hours=1),
        "disabled": dict(visit_bundling_enabled=False),
    }
    c, rt, keys = fixture(**options.get(change, {}))
    result = evaluate(c, rt, groups=((keys[:2], 5 if change == "future-horizon" else 0),))
    assert result["state"] == "infeasible" and result["constraints"]
    assert not rt.executive.missions


def test_visit_acceptance_rejects_a_stale_decision_and_actual_stock_shortage():
    c, rt, keys = fixture()
    result = evaluate(c, rt, groups=((keys[:2], 1),), project_only=False)
    assert result["state"] == "feasible"
    changed = copy.deepcopy(result)
    changed["decision_key"] = "wrong"
    with pytest.raises(ValueError, match="stale"):
        coupling.accept(rt, changed)
    rt.ledger.stock["stock:maintenance"] = 1
    rt.dispatch_selected((), charge=False, visit_groups=((keys[:2], 1),))
    assert not rt.executive.missions
    assert not rt.interval["selection"]["visit_groups"][0]["accepted"]
    assert rt._effects.random_events.count == 0


def test_joint_charging_interface_uses_the_shared_visit_in_its_cost_and_acceptance():
    c, rt, keys = fixture()
    planned = charge_control.evaluate(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(),
        450,
        c.costs,
        [],
        service_prices=c.service_economics,
        joint_work=True,
        visit_groups=((keys[:2], 1),),
        seconds=2,
    )
    assert planned["state"] == "feasible", planned["constraints"]
    assert planned["mission_pricing"]["with_additions"]["predicted_quantities"]["human_visits"] == 1
    charge_control.accept(rt, planned)
    assert len(rt.executive.visits) == 1


def repair_fixture():
    from methane.services.controller import VISIT_VERSION, ServicePolicy

    c, _, _ = fixture()
    c = replace(
        c,
        field_operations=replace(
            c.field_operations,
            cleaner_enabled=False,
            rover_enabled=False,
            reset_enabled=False,
            repair_success_probability=1,
        ),
        service_system=replace(c.service_system, inspector="none", maintenance_enabled=False),
        service_policy=ServicePolicy(
            version=VISIT_VERSION,
            maximum_wait_hours=6,
            maximum_candidates=8,
            comparison_seconds=30,
        ),
    )
    rt = PlantServices(c.field_operations, c.service_system, 7, 450)
    diagnosis = Diagnosis(
        225,
        active_incident=True,
        incidents=1,
        status="capacity loss",
        informative=True,
        flow_isolated=True,
        tracking_residual=0.5,
    )
    rt.prepare(0, diagnosis, 750)
    assert {o["kind"] for o in rt.orders} == {"flow-calibration", "module-replacement"}
    return c, rt, diagnosis


def test_joint_policy_prescreens_shared_and_single_work_without_drawing_outcomes():
    from methane.services.controller import VERSION, ServiceController

    c, rt, _ = repair_fixture()
    controller = ServiceController(c.service_policy)
    controller._work(rt)
    before = copy.deepcopy((rt.public(), rt.orders))
    candidates, due, rejected, omitted = controller._candidates(rt, forecast())
    grouped = [q for q in candidates if q.get("visit_groups")]
    assert grouped and len(due) == 2
    assert any(q["selections"] for q in candidates)
    assert (rt.public(), rt.orders) == before
    assert not rt._effects.random_events.retrospective()
    assert all(rt._effects.random_events.identity(o["id"]) is None for o in rt.orders)
    original = ServiceController(replace(c.service_policy, version=VERSION))
    original._work(rt)
    assert not any(q.get("visit_groups") for q in original._candidates(rt, forecast())[0])
    tiny = ServiceController(replace(c.service_policy, maximum_candidates=2))
    tiny._work(rt)
    offered, _, _, omitted = tiny._candidates(rt, forecast())
    assert len(offered) == 2 and any(q.startswith("visit:") for q in omitted)


def test_joint_policy_chooses_due_pair_and_execution_keeps_unverified_work_separate():
    from dataclasses import asdict

    from methane.reference import SupportReference
    from methane.services.controller import ServiceController

    c, rt, d = repair_fixture()
    result = ServiceController(c.service_policy).decide(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(),
        225,
        c.costs,
        c.service_economics,
        seconds=2,
    )
    decision = result["decision"]
    assert decision["selected_candidate_id"].startswith("visit:")
    assert not decision["fallback_used"] and not decision["unmet_deadlines"]
    assert len(rt.executive.visits) == 1
    chosen = next(
        q for q in decision["candidates"] if q["candidate_id"] == decision["selected_candidate_id"]
    )
    assert len(chosen["progressing_obligations"]) == 2
    quote = chosen["evaluation"]["mission_pricing"]
    assert quote["with_additions"]["predicted_quantities"]["human_visits"] == 1
    # Both hypotheses are observed; the candidate receives no fault truth or
    # assumption of restored capacity. Execution here intentionally has no fault.
    faults = FaultState(c.plant, c.scenario, c.faults)
    rows, checks = [], []
    reference = None
    for hour in range(6):
        if hour:
            rt.prepare(hour, d, 750)
            rt.dispatch_selected((), charge=False)
        rt.execute_interval(hour, faults)
        row = rt.end(hour, faults, d)
        rows.append(row)
        if reference is None:
            reference = SupportReference(
                asdict(c.service_system), [k for k, present in row["assets"].items() if present]
            )
        reference.interval(row, hour, checks, "shared-example")
    assert all(q["passed"] for q in checks), [q for q in checks if not q["passed"]][:5]
    assert sum(r["human_visits"] for r in rows) == 1
    assert (
        sum(r["crew_committed_hours"] for r in rows)
        == quote["with_additions"]["predicted_quantities"]["crew-hours"]
    )
    assert all(q["status"] == "awaiting verification" for q in rt.public()["orders"])


def test_future_visit_selection_is_checked_independently_and_cannot_be_rewritten():
    from dataclasses import asdict

    from methane.reference import SupportReference

    c, rt, keys = fixture()
    rt.dispatch_selected((), charge=False, visit_groups=((keys[:2], 1),))
    row = rt.end(0, FaultState(c.plant, c.scenario, c.faults), Diagnosis(450))

    def failures(record):
        checks = []
        SupportReference(
            asdict(c.service_system), [k for k, present in record["assets"].items() if present]
        ).interval(record, 0, checks, "fixture")
        return {q["check"] for q in checks if not q["passed"]}

    assert not failures(row)
    for field in ("starting_at", "returning_at"):
        changed = copy.deepcopy(row)
        changed["selection"]["visit_groups"][0][field] += 1
        assert failures(changed)
    changed = copy.deepcopy(row)
    changed.pop("selection")
    assert "support.future_visit_authorized" in failures(changed)


def test_joint_policy_rejects_missing_support_at_configuration_and_direct_entry():
    from methane.services.controller import ServiceController

    c, rt, _ = repair_fixture()
    with pytest.raises(ValueError, match="visit bundling"):
        replace(c, service_system=replace(c.service_system, visit_bundling_enabled=False))
    rt.options = replace(rt.options, visit_bundling_enabled=False)
    with pytest.raises(ValueError, match="visit bundling"):
        ServiceController(c.service_policy).decide(
            rt,
            c.plant,
            State.initial(c.plant),
            forecast(),
            225,
            c.costs,
            c.service_economics,
        )
    assert not rt.executive.missions


def test_interrupted_shared_procedure_preserves_spent_stock_and_stops_later_work():
    c, rt, d = repair_fixture()
    keys = tuple(o["id"] for o in rt.orders)
    rt.dispatch_selected((), charge=False, visit_groups=((keys, 0),))
    faults = FaultState(c.plant, c.scenario, c.faults)
    rt.end(0, faults, d)
    # The first calibration is still underway. Its issued kit cannot be
    # refunded, and interrupting it must prevent the later replacement.
    rt.executive.interrupt(keys[0], "Observed access interruption after departure")
    missions = rt.executive.missions
    assert missions[keys[0]].status == "stranded"
    assert missions[keys[1]].work_completed_at is None
    assert rt.ledger.stock["stock:calibration"] == c.service_system.calibration_kits - 1
    assert rt.ledger.stock["stock:module"] == c.field_operations.service_kits
    rt.prepare(1, d, 750)
    rt.dispatch_selected((), charge=False)
    row = rt.end(1, faults, d)
    visit = row["state"]["executive"]["visits"][0]
    assert visit["status"] == "interrupted" and visit["returned_at"] is None
    assert len(visit["unfinished"]) == 2
    assert not rt._effects.random_events.retrospective()  # No successful job outcome happened.


def test_proposals_are_identical_when_private_outcome_draws_change():
    c, left, d = repair_fixture()
    right = PlantServices(c.field_operations, c.service_system, 99, 450)
    right.prepare(0, d, 750)
    keys = tuple(o["id"] for o in left.orders)
    a, b = (rt.propose_visit(keys, starting_at=1) for rt in (left, right))
    assert a == b
    assert all(rt._effects.random_events.count == 0 for rt in (left, right))


def test_shared_charging_accepts_one_shot_recipe_iterables():
    c, rt, keys = fixture()
    planned = charge_control.evaluate(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(),
        450,
        c.costs,
        [],
        service_prices=c.service_economics,
        joint_work=True,
        visit_groups=iter(((keys[:2], 1),)),
        seconds=2,
    )
    assert planned["state"] == "feasible", planned["constraints"]
    assert planned["mission_pricing"]["with_additions"]["predicted_quantities"]["human_visits"] == 1
    charge_control.accept(rt, planned)
    assert len(rt.executive.visits) == 1


def test_separate_future_departures_are_not_reported_as_executable_before_return():
    c, rt, keys = fixture()
    result = evaluate(c, rt, singles=((keys[0], 1), (keys[1], 2)))
    assert result["state"] == "infeasible"
    assert any(q["condition"] == "crew return dependency" for q in result["constraints"])
    with pytest.raises(ValueError, match="feasible"):
        coupling.accept(rt, result)
    assert not rt.executive.missions
