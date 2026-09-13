"""Outcome-tree checks against bounded independent resource calculations."""

import copy
from dataclasses import replace

import pytest

from methane.config import Costs, Plant
from methane.dispatch import plan
from methane.physics import State
from methane.services.scenario_planning import Branch, solve


def forecast(pv, service=(0, 12), capacities=None):
    result = dict(
        pv_kw=list(pv),
        ambient_c=[20, 20],
        deliveries_kg=[0, 0],
        service_kw=list(service),
        times=["2026-01-01T00:00:00Z", "2026-01-01T01:00:00Z"],
        source=dict(
            id="teaching-vintage/1",
            initialized_at="2026-01-01T00:00:00Z",
            available_at="2026-01-01T00:00:00Z",
        ),
    )
    if capacities is not None:
        result["electrolyser_capacity_kw"] = capacities
    return result


def fixture():
    plant = replace(
        Plant(),
        battery_kwh=12,
        battery_c_rate=1,
        initial_soc=1,
        roundtrip_efficiency=1,
        initial_h2_kg=5,
        heater_max_kw=0,
        cooling_max_kw=0,
        minimum_run_hours=1,
    )
    state = State.initial(plant, 300)
    branches = (
        Branch.create(
            "sun",
            0.5,
            forecast([0, 12]),
            ("same", "sun-observed"),
            source="assumption:two-weather-cases/1",
        ),
        Branch.create(
            "dark",
            0.5,
            forecast([0, 0]),
            ("same", "dark-observed"),
            source="assumption:two-weather-cases/1",
        ),
    )
    return plant, state, branches


def test_shared_actions_prevent_clairvoyant_spending_before_a_weather_observation():
    p, state, branches = fixture()
    result = solve(p, state, branches, 0, Costs(), seconds=2)
    assert result["status"] == "feasible", result["solver"]
    assert result["shared_action_equalities"] == 6
    assert result["current_action"]["discharge_kw"] == pytest.approx(0, abs=1e-7)
    assert result["expected"]["methane_kg"] == pytest.approx(0, abs=1e-7)
    assert result["branches"][0]["actions"][0] == result["branches"][1]["actions"][0]
    # In the dark branch all 12 kWh must survive for the essential next-hour bus load.
    # With no heater the idle reactor cools below 250 C, removing the later methane option.
    # An oracle that knows the sunny branch can spend those 12 kWh on 10 kg methane now.
    oracle = [
        plan(p, state, b.forecast, 0, Costs(), seconds=2, allow_fallback=False) for b in branches
    ]
    assert oracle[0]["predicted"]["methane_kg"] == pytest.approx(10)
    assert oracle[1]["predicted"]["methane_kg"] == pytest.approx(0)
    assert sum(0.5 * r["predicted"]["methane_kg"] for r in oracle) == pytest.approx(5)


def test_terminal_reserve_is_a_hard_constraint_in_every_branch():
    p, state, branches = fixture()
    result = solve(p, state, branches, 0, Costs(), terminal_minimum=dict(battery_kwh=1), seconds=2)
    assert result["status"] == "unresolved" and result["current_action"] is None
    assert not result["solver"]["valid_incumbent"]


def test_fixed_service_costs_enter_the_objective_once_without_changing_actions():
    p, state, branches = fixture()
    a = solve(p, state, branches, 0, Costs(), risk_weight=0.5, seconds=2)
    b = solve(
        p,
        state,
        tuple(replace(x, service_cost_eur=50) for x in branches),
        0,
        Costs(),
        risk_weight=0.5,
        seconds=2,
    )
    assert a["status"] == b["status"] == "feasible"
    assert b["solver"]["objective_value"] - a["solver"]["objective_value"] == pytest.approx(0.05)
    assert b["expected"]["assumed_contribution_eur"] - a["expected"][
        "assumed_contribution_eur"
    ] == pytest.approx(-50)
    assert b["current_action"] == a["current_action"]


def test_capacity_changes_need_an_explicit_later_observation_and_remain_predictions():
    p = replace(Plant(), battery_kwh=0, heater_max_kw=0, initial_h2_kg=0)
    state = State.initial(p)
    data = forecast([0, 450], (0, 0), [0, 450])
    branches = [
        Branch.create(
            "recovered", 0.5, data, ("same", "passed-test"), source="assumption:post-service-test/1"
        ),
        Branch.create(
            "unchanged",
            0.5,
            forecast([0, 450], (0, 0), [0, 0]),
            ("same", "failed-test"),
            source="assumption:post-service-test/1",
        ),
    ]
    original = copy.deepcopy(data)
    data["pv_kw"][1] = 0
    result = solve(p, state, branches, 0, Costs(), seconds=2)
    assert result["status"] == "feasible"
    assert branches[0].forecast == original
    assert result["branches"][1]["actions"][1]["electrolyser_kw"] == 0
    invalid = [replace(x, information=("same", "still-unknown")) for x in branches]
    with pytest.raises(ValueError, match="before the observation"):
        solve(p, state, invalid, 0, Costs())


@pytest.mark.parametrize(
    "problem",
    ["probability", "current-label", "merge", "unpublished", "different-current-capacity"],
)
def test_invalid_information_structures_and_unavailable_data_are_rejected(problem):
    p, state, branches = fixture()
    branches = list(branches)
    if problem == "probability":
        branches[0] = replace(branches[0], probability=0.2)
    elif problem == "current-label":
        branches[0] = replace(branches[0], information=("already-know-sun", "sun-observed"))
    elif problem == "merge":
        # Three-interval histories distinguish at hour one, then incorrectly merge.
        for i, b in enumerate(branches):
            f = b.forecast
            for key in ("pv_kw", "ambient_c", "deliveries_kg", "service_kw"):
                f[key].append(f[key][-1])
            f["times"].append("2026-01-01T02:00:00Z")
            branches[i] = Branch.create(
                b.branch_id, b.probability, f, (*b.information, "merged"), source=b.source
            )
    else:
        f = branches[0].forecast
        if problem == "unpublished":
            f["source"]["available_at"] = "2026-01-01T01:00:00Z"
        else:
            f["electrolyser_capacity_kw"] = [450, 450]
        branches[0] = Branch.create(
            "sun", 0.5, f, branches[0].information, source=branches[0].source
        )
    with pytest.raises(ValueError):
        solve(p, state, branches, 0, Costs())


def test_solver_time_limit_without_an_incumbent_remains_unresolved(monkeypatch):
    p, state, branches = fixture()
    monkeypatch.setattr(
        "methane.services.scenario_planning.Model.solve",
        lambda self, seconds: (None, dict(status="time-limited", valid_incumbent=False)),
    )
    result = solve(p, state, branches, 0, Costs())
    assert result["status"] == "unresolved" and result["current_action"] is None
    assert result["branches"] == [] and result["solver"]["status"] == "time-limited"


@pytest.mark.parametrize(
    "options", [dict(risk_weight="high"), dict(seconds=None), dict(capacity=float("nan"))]
)
def test_invalid_scalar_inputs_are_rejected_even_with_explicit_capacity_profiles(options):
    p, state, branches = fixture()
    args = dict(capacity=0, costs=Costs())
    args.update(options)
    with pytest.raises(ValueError):
        solve(p, state, branches, **args)
