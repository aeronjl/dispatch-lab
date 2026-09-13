"""Whole candidate selection, fixed decision information and explicit obligations."""

import copy
from dataclasses import replace

import pytest

from methane.cancellation import CancelledOperation, predicate
from methane.config import Costs, Plant
from methane.field_operations import FieldOperations
from methane.physics import State
from methane.sensing import Diagnosis
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.configuration import ServiceSystem
from methane.services.plant import PlantServices
from methane.services.scenario_planning import Branch
from methane.services.supervisor import Candidate, choose, commit, schedules


def fixture():
    p = replace(Plant(), battery_kwh=0, heater_max_kw=0, initial_h2_kg=0)
    runtime = PlantServices(
        FieldOperations(
            enabled=True,
            cleaner_enabled=False,
            human_fallback=False,
            dock_available=False,
            reset_enabled=False,
            inspection_hours=2,
            mission_failure_probability=0,
        ),
        ServiceSystem(
            support_model="logistics/1",
            inspector="fixed",
            contact_error_probability=0,
            contact_unreadable_probability=0,
            outcome_randomness="target-action-request/1",
        ),
        7,
        450,
    )
    d = Diagnosis(
        225,
        active_incident=True,
        incidents=1,
        informative=True,
        status="capacity loss",
        tracking_residual=0.5,
    )
    runtime.prepare(0, d, 1)
    forecast = dict(
        decision_hour=0,
        pv_kw=[1] * 5,
        ambient_c=[20] * 5,
        deliveries_kg=[0] * 5,
        times=[f"2026-01-01T0{i}:00:00Z" for i in range(5)],
        source=dict(
            id="service-window/1",
            initialized_at="2026-01-01T00:00:00Z",
            available_at="2026-01-01T00:00:00Z",
        ),
    )
    dark = copy.deepcopy(forecast)
    dark["pv_kw"][1] = 0.1
    branches = tuple(
        Branch.create(
            name, 0.5, f, ("same", *([name] * 4)), source="assumption:two-weather-outcomes/1"
        )
        for name, f in (("normal", forecast), ("cloud", dark))
    )
    prices = illustrative(Costs(), version=ACTIVITY_VERSION)
    prices["assets"]["fixed_reader"]["wear_eur_per_hour"] = 8
    key = runtime.orders[0]["id"]
    inputs = dict(
        runtime=runtime,
        plant=p,
        state=State.initial(p),
        forecast=forecast,
        capacity_kw=225,
        costs=Costs(),
        branches=branches,
        service_prices=prices,
        seconds_per_candidate=2,
        wall_seconds=30,
    )
    return inputs, key


def test_required_procedure_chooses_feasible_weather_window_without_accepting_candidates():
    args, key = fixture()
    runtime = args["runtime"]
    before = copy.deepcopy(
        (
            runtime.public(),
            vars(runtime.ledger),
            runtime.interval,
            vars(runtime._effects.random_events),
        )
    )
    progress = []
    candidates = schedules([key], [0, 1, 2, 3])
    result = choose(**args, candidates=candidates, required_by={key: 5}, progress=progress.append)
    assert result["status"] == "selected"
    winner = next(
        r for r in result["candidates"] if r["candidate_id"] == result["selected_candidate_id"]
    )
    assert winner["evaluation"]["selections"] == [dict(order_id=key, starting_at=2)]
    assert winner["evaluation"]["service_pricing"]["incremental_decision_eur"] == 18
    assert len(progress) == 5
    assert all(r["status"] == "infeasible" for r in result["candidates"] if r is not winner)
    assert (
        runtime.public(),
        vars(runtime.ledger),
        runtime.interval,
        vars(runtime._effects.random_events),
    ) == before
    assert commit(runtime, result) == 0
    assert list(runtime.executive.missions) == [key]
    assert runtime.executive.missions[key].plan.starting_at == 2
    assert runtime.interval["decision"]["service_supervisor"] == result


def test_optional_inspection_is_not_given_an_invented_information_benefit():
    args, key = fixture()
    result = choose(**args, candidates=schedules([key], [2]), objective="economics")
    winner = next(
        r for r in result["candidates"] if r["candidate_id"] == result["selected_candidate_id"]
    )
    assert winner["evaluation"]["selections"] == []
    assert winner["evaluation"]["service_pricing"]["incremental_decision_eur"] == 0
    # Both alternatives produce zero methane in this low-power fixture. The
    # procedure costs EUR 18; no possible finding is assigned fabricated value.
    other = next(r for r in result["candidates"] if r is not winner)
    assert other["score"] - winner["score"] == pytest.approx(18)


def test_deadline_and_service_reserve_failures_are_explicit_and_do_not_commit():
    args, key = fixture()
    cases = [dict(required_by={key: 4}), dict(service_reserves={"stock:module": 100})]
    for options in cases:
        result = choose(**args, candidates=[Candidate("late", ((key, 2),))], **options)
        assert result["status"] == "no-feasible-candidate"
        assert result["current_action"] is None
        assert result["candidates"][0]["constraints"]
        with pytest.raises(ValueError, match="selected"):
            commit(args["runtime"], result)
    assert not args["runtime"].executive.missions


def test_time_limited_missing_incumbent_does_not_become_a_zero_cost_choice(monkeypatch):
    args, key = fixture()
    monkeypatch.setattr(
        "methane.services.scenario_planning.Model.solve",
        lambda self, seconds: (None, dict(status="time-limited", valid_incumbent=False)),
    )
    result = choose(**args, candidates=[Candidate("later", ((key, 2),))])
    assert result["status"] == "unresolved" and result["selected_candidate_id"] is None
    assert result["candidates"][0]["score"] is None


def test_total_budget_retains_unattempted_candidates_and_never_claims_full_search(monkeypatch):
    args, key = fixture()
    ticks = iter((0, 2, 3))
    monkeypatch.setattr("methane.services.supervisor.perf_counter", lambda: next(ticks))
    args["wall_seconds"] = 1
    result = choose(**args, candidates=schedules([key], [2]))
    assert result["status"] == "unresolved" and result["budget_exhausted"]
    assert len(result["candidates"]) == 2
    assert all(r["status"] == "not-evaluated" for r in result["candidates"])


def test_cancellation_between_candidates_leaves_live_work_unaccepted():
    args, key = fixture()
    cancelled = False

    def progress(_):
        nonlocal cancelled
        cancelled = True

    token = predicate.set(lambda: cancelled)
    try:
        with pytest.raises(CancelledOperation):
            choose(**args, candidates=schedules([key], [2]), progress=progress)
    finally:
        predicate.reset(token)
    assert not args["runtime"].executive.missions
    assert not args["runtime"].ledger.holds


def test_changed_current_information_cannot_receive_a_late_selection():
    args, key = fixture()
    result = choose(**args, candidates=[Candidate("later", ((key, 2),))])
    args["runtime"].ledger.stock["stock:module"] = 0
    with pytest.raises(ValueError, match="stale"):
        commit(args["runtime"], result)
    assert not args["runtime"].executive.missions


def test_enumeration_is_complete_and_refuses_unlabelled_truncation():
    result = schedules(["A", "B"], [0, 1], required=["A"])
    assert len(result) == 6
    assert {tuple(c.selections) for c in result} == {
        (("A", a),) + (() if b is None else (("B", b),)) for a in (0, 1) for b in (None, 0, 1)
    }
    with pytest.raises(ValueError, match="search contains"):
        schedules(["A", "B", "C"], range(10))
    with pytest.raises(ValueError, match="work set"):
        schedules(["A"], [0], required=["B"])
    assert schedules([], [0]) == (Candidate("schedule-000", ()),)


@pytest.mark.parametrize(
    "option",
    [
        dict(service_reserves={"invented-kit": 0}),
        dict(required_by={"not-queued": 2}),
        dict(seconds_per_candidate="fast"),
        dict(wall_seconds=False),
    ],
)
def test_missing_resources_orders_and_invalid_limits_reject_before_mutation(option):
    args, key = fixture()
    args.update(option)
    with pytest.raises(ValueError):
        choose(**args, candidates=[Candidate("later", ((key, 2),))])
    assert not args["runtime"].executive.missions
