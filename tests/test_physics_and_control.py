"""Physical limits, an analytic scheduling example, and causal experiment checks."""

from dataclasses import replace
from types import SimpleNamespace

import numpy as np
import pytest

import controllers
from controllers import greedy, plan
from experiment import Scenario, Weather, forecast_at, make_weather, run_experiment
from plant import Plant, State, step


def test_solar_charge_discharge_accounts_for_roundtrip_losses():
    plant = Plant(
        battery_kwh=100,
        battery_c_rate=2,
        roundtrip_efficiency=0.81,
        electrolyser_kw=100,
        min_load_fraction=0.1,
        start_energy_kwh=0,
    )
    state, charge = step(plant, State(0), 0, 100, 100)
    assert state.energy_kwh == pytest.approx(90)
    state, discharge = step(plant, state, 100, 0, 100)
    assert discharge["productive_kw"] == pytest.approx(81)
    assert state.energy_kwh == pytest.approx(0)
    assert charge["battery_loss_kwh"] + discharge["battery_loss_kwh"] == pytest.approx(19)


def test_startup_energy_and_minimum_load_are_enforced():
    plant = Plant(battery_kwh=0, electrolyser_kw=100, min_load_fraction=0.5, start_energy_kwh=20)
    state, row = step(plant, State(0), 100, 69, 100)
    assert not state.on
    assert row["h2_kg"] == 0
    state, row = step(plant, state, 100, 70, 100)
    assert state.on
    assert row["startup_kwh"] == 20
    assert row["productive_kw"] == pytest.approx(50)
    _, row = step(plant, state, 100, 70, 100)
    assert row["startup_kwh"] == 0
    assert row["productive_kw"] == pytest.approx(70)


def test_exact_energy_limit_for_a_small_planning_problem():
    # There are 220 kWh total (150 stored + 70 solar). One 40 kWh start leaves
    # exactly 180 productive kWh possible. MPC must spread production across the
    # two dark hours to avoid stopping. A greedy discharge cannot meet the bound.
    plant = Plant(
        battery_kwh=200,
        battery_c_rate=1,
        electrolyser_kw=100,
        min_load_fraction=0.5,
        start_energy_kwh=40,
        roundtrip_efficiency=1,
    )
    pv = np.array([0.0, 0.0, 70.0])
    output = {}
    for name in ("greedy", "mpc"):
        state = State(150)
        productive = 0
        for t in range(3):
            decision = (
                greedy(plant, state, pv[t], 100)
                if name == "greedy"
                else plan(plant, state, pv[t:], 100)
            )
            state, row = step(plant, state, decision.productive_kw, pv[t], 100)
            productive += row["productive_kw"]
        output[name] = productive
    assert output["mpc"] == pytest.approx(180)
    assert output["greedy"] == pytest.approx(100)


@pytest.mark.parametrize(
    "battery,initial,fault,seed",
    [
        (0, 0, 1, 7),
        (800, 0, 0.3, 7),
        (2000, 0.5, 0, 19),
        (100, 1, 1, 2),
    ],
)
def test_paired_runs_obey_limits_and_conserve_energy(battery, initial, fault, seed):
    plant = Plant(battery_kwh=battery, initial_soc=initial)
    result = run_experiment(plant, Scenario(days=2, seed=seed, fault_capacity_fraction=fault))
    assert result["metrics"]["Greedy"]["pv_kwh"] == result["metrics"]["Forecast MPC"]["pv_kwh"]
    for name, rows in result["records"].items():
        for row in rows:
            assert 0 <= row["battery_kwh"] <= battery + 1e-6
            assert row["productive_kw"] <= row["capacity_kw"] + 1e-6
            assert row["productive_kw"] == 0 or row["productive_kw"] >= plant.min_kw - 1e-6
            assert min(row["charge_kw"], row["discharge_kw"]) == 0
            assert row["charge_kw"] <= plant.battery_kw + 1e-6
            assert row["discharge_kw"] <= plant.battery_kw + 1e-6
            assert abs(row["balance_residual_kwh"]) < 1e-6
            if 34 <= row["hour"] < 42 and fault == 0:
                assert row["productive_kw"] == 0
        m = result["metrics"][name]
        destinations = sum(
            m[key]
            for key in (
                "productive_kwh",
                "startup_kwh",
                "curtailed_kwh",
                "battery_loss_kwh",
                "battery_change_kwh",
            )
        )
        assert m["pv_kwh"] == pytest.approx(destinations, abs=1e-6)
        assert m["fallbacks"] == 0


def test_no_energy_means_no_hydrogen_for_either_controller():
    result = run_experiment(Plant(solar_kw=0, battery_kwh=0), Scenario(days=2))
    for metrics in result["metrics"].values():
        assert metrics["hydrogen_kg"] == 0
        assert metrics["starts"] == 0


def test_forecast_never_reads_future_realised_weather():
    scenario = Scenario(days=2)
    weather = make_weather(Plant(), scenario)
    before = forecast_at(weather, scenario, 12)
    changed_future = weather.actual_kw.copy()
    changed_future[13:] = 999999  # poison all future realised measurements
    after = forecast_at(
        Weather(weather.clear_kw, weather.expected_cloud, changed_future), scenario, 12
    )
    np.testing.assert_array_equal(before, after)
    assert before[0] == weather.actual_kw[12]


def test_seed_and_forecast_bias_do_not_change_realised_weather():
    plant, scenario = Plant(), Scenario(days=2)
    first = make_weather(plant, scenario)
    repeat = make_weather(plant, scenario)
    biased = make_weather(plant, replace(scenario, forecast_bias=0.5))
    np.testing.assert_array_equal(first.actual_kw, repeat.actual_kw)
    np.testing.assert_array_equal(first.actual_kw, biased.actual_kw)
    assert not np.array_equal(
        forecast_at(first, scenario, 6), forecast_at(first, replace(scenario, forecast_bias=0.5), 6)
    )


def test_future_fault_schedule_does_not_change_pre_fault_actions():
    plant = Plant()
    healthy = run_experiment(plant, Scenario(days=2))
    fault = run_experiment(plant, Scenario(days=2, fault_capacity_fraction=0))
    for name in healthy["records"]:
        a = [r["productive_kw"] for r in healthy["records"][name][:34]]
        b = [r["productive_kw"] for r in fault["records"][name][:34]]
        np.testing.assert_allclose(a, b, atol=1e-6)


def test_missing_solver_solution_falls_back_to_a_feasible_rule(monkeypatch):
    monkeypatch.setattr(controllers, "milp", lambda *a, **kw: SimpleNamespace(x=None, status=1))
    plant, state = Plant(), State(100)
    decision = plan(plant, state, np.array([200.0, 300.0]), 450)
    assert decision.status == "fallback"
    assert decision.productive_kw == greedy(plant, state, 200, 450).productive_kw


def test_reject_invalid_physical_parameters():
    with pytest.raises(ValueError):
        Plant(roundtrip_efficiency=1.1)
    with pytest.raises(ValueError):
        Plant(battery_kwh=-1)
    with pytest.raises(ValueError):
        Plant(solar_kw=float("nan"))
