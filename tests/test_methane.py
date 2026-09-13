"""Physical, informational and accounting boundaries of the methane extension."""

import copy
import json
import threading
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import numpy as np
import pytest

from methane.config import Config, Costs, Plant, Scenario, Sensors, WeatherConfig
from methane.costing import allocation, reprice
from methane.dispatch import build, execute, plan
from methane.evidence import batch, cases, load, save
from methane.physics import (
    ACTION_KEYS,
    REACTION_KWH_PER_KG,
    State,
    temperature_after,
    transition,
)
from methane.sensing import Diagnosis, update
from methane.simulation import run, what_if
from methane.weather import (
    IncompleteWeather,
    choose_vintage,
    dc_power,
    fetch,
    forecast_at,
    local_stamp,
    normalize,
    prepare,
    stamp,
)


def forecast(pv, ambient=20, delivery=None):
    return {
        "pv_kw": pv,
        "ambient_c": [ambient] * len(pv),
        "deliveries_kg": delivery or [0] * len(pv),
    }


def action(**values):
    return {k: values.get(k, 0.0) for k in ACTION_KEYS}


def test_analytic_warmup_cooling_and_reaction():
    p = Plant()
    assert temperature_after(p, 20, 20, 60) == pytest.approx(195.5537462265)
    assert temperature_after(p, 195.5537462265, 20, 60) == pytest.approx(330.0153353675)
    assert temperature_after(p, 300, 20) < 300
    assert temperature_after(p, 300, 20, methane=10) > temperature_after(p, 300, 20)
    assert REACTION_KWH_PER_KG == pytest.approx(2.8645833333)
    no_loss = replace(p, heat_loss_kw_per_k=0)
    assert temperature_after(no_loss, 20, 20, 60) == pytest.approx(220)


def test_stoichiometry_and_recorded_delivery_rejection():
    p = Plant()
    s = State(800, 50, 999, 300)
    n, row = transition(p, s, action(methane_kg=10), 12, 20, 300)
    assert row["co2_delivered_kg"] == 1
    assert row["co2_rejected_kg"] == 299
    assert n.h2_kg == 45
    assert n.co2_kg == 972.5
    assert row["water_produced_kg"] == 22.5
    assert row["reaction_mass_residual_kg"] == 0
    assert row["electrical_residual_kwh"] == 0


@pytest.mark.parametrize(
    "state", [State(0, 0, 0, 20), State(800, 60, 1000, 400), State(0, 0, 0, 250, False, True, 3)]
)
def test_execution_clips_requests_preserving_limits(state):
    p = Plant()
    requested = action(
        electrolyser_kw=450,
        methane_kg=10,
        charge_kw=400,
        discharge_kw=400,
        heater_kw=60,
        cooling_kw=40,
    )
    n, row = execute(p, state, requested, 20, 15, 300, 80, Costs())
    assert 0 <= n.battery_kwh <= 800
    assert row["applied"]["electrolyser_kw"] == 0
    assert row["curtailed_kwh"] >= -1e-7
    assert row["requested"] == requested
    assert not (row["applied"]["charge_kw"] > 1e-5 and row["applied"]["discharge_kw"] > 1e-5)
    if state.commitment_hours:
        assert row["forced_trip"]
        assert n.commitment_hours == 0


def test_cold_reactor_cannot_produce_even_with_feedstock():
    p = Plant()
    n, row = execute(
        p, State(800, 50, 500, 20), action(methane_kg=10, heater_kw=60), 100, 20, 0, 450, Costs()
    )
    assert row["applied"]["methane_kg"] == 0
    assert n.temperature_c == pytest.approx(195.5537462265)


def test_minimum_run_carried_and_no_heat_cool_arbitrage():
    p = Plant()
    state = State(800, 50, 500, 300)
    d = plan(p, state, forecast([100] * 6), 450, Costs())
    assert d["actions"]
    rows = d["trajectory"]
    assert rows[0]["reactor_start"]
    assert rows[0]["state"]["commitment_hours"] == 3
    assert all(r["state"]["reactor_on"] for r in rows[:4])
    assert all(
        not (r["applied"]["heater_kw"] > 1e-5 and r["applied"]["cooling_kw"] > 1e-5) for r in rows
    )


def test_small_analytic_case_planning_preserves_heat_and_feed():
    # Initial buffer supports exactly four hours at 3 kg/h. Battery has 4 kWh.
    # Methane auxiliary demand is 1 kW, zero variable demand. Greedy spends its
    # battery on electrolysis in hour zero; planning reserves it for four outputs.
    p = Plant(
        solar_kw=0,
        battery_kwh=4,
        battery_c_rate=1,
        electrolyser_kw=3,
        min_load_fraction=1,
        start_energy_kwh=0,
        initial_soc=1,
        specific_energy_kwh_per_kg=55,
        initial_h2_kg=6,
        methane_max_kgph=3,
        methane_min_kgph=3,
        auxiliary_kw=1,
        methane_electric_kwh_per_kg=0,
        heat_loss_kw_per_k=0,
        heater_max_kw=0,
        roundtrip_efficiency=1,
        minimum_run_hours=4,
    )
    state = State(4, 6, 500, 250)
    f = forecast([0] * 4)
    optimal = plan(p, state, f, 3, Costs())
    local = plan(p, state, f, 3, Costs(), "greedy")
    assert optimal["predicted"]["methane_kg"] == pytest.approx(12)
    assert local["predicted"]["methane_kg"] < 12
    assert optimal["actions"][0]["electrolyser_kw"] == pytest.approx(0)


def test_invalid_incumbent_is_rejected(monkeypatch):
    import methane.dispatch as dispatch

    class Bad:
        x = np.array([np.nan])
        status = 1
        message = "bad incumbent"

    monkeypatch.setattr(dispatch, "milp", lambda *a, **kw: Bad())
    m = build(Plant(), State.initial(Plant()), forecast([0]), 450)
    x, info = m.solve(0.1)
    assert x is None and not info["valid_incumbent"]


def test_infeasible_whatif_is_not_presented_as_success():
    p = Plant()
    state = State(100, 5, 50, 300, False, True, 3)
    d = plan(p, state, forecast([0] * 6), 450, Costs(), alternative="battery", allow_fallback=False)
    assert d["predicted"] is None
    assert not d["solver"]["valid_incumbent"]


def observation(power=300, flow=None, inventory=20, outflow=0):
    return {
        "power_kw": power,
        "hydrogen_flow_kg": power / 55 if flow is None else flow,
        "h2_inventory_kg": inventory,
        "h2_outflow_kg": outflow,
    }


@pytest.mark.parametrize("kind", ["capacity", "flow"])
def test_diagnosis_two_informative_intervals_and_one_budget(kind):
    p, sensors, d = Plant(), Sensors(noise_fraction=0), Diagnosis(450)
    previous = observation(inventory=0)
    incidents = 0
    for i in range(5):
        power = 225 if kind == "capacity" else 450
        flow = power / 55 * (1.4 if kind == "flow" else 1)
        obs = observation(power, flow, previous["h2_inventory_kg"] + power / 55)
        d, incident, _ = update(p, sensors, d, previous, obs, 450)
        incidents += incident
        previous = obs
        if i == 0:
            assert incidents == 0
    assert incidents == 1
    if kind == "capacity":
        assert d.capacity_kw == 225 and not d.flow_isolated
    else:
        assert d.flow_isolated and d.capacity_kw == 450


def test_diagnosis_low_excitation_ambiguity_and_recovery():
    p, s = Plant(), Sensors(noise_fraction=0)
    d, _, _ = update(p, s, Diagnosis(450), observation(), observation(), 0)
    assert d.status == "insufficient evidence"
    d, _, _ = update(p, s, d, observation(inventory=0), observation(300, inventory=0), 450)
    assert d.status == "ambiguous"
    d = Diagnosis(405, active_incident=True)
    prior = observation(inventory=0)
    for i in range(2):
        obs = observation(450, inventory=(i + 1) * 450 / 55)
        d, _, event = update(p, s, d, prior, obs, 450, probe=True)
        prior = obs
    assert d.capacity_kw == 450 and event == "Capacity recovered"
    assert not d.active_incident


def test_weather_preceding_hour_and_initial_null():
    saved = {
        "raw": {
            "hourly_units": {"temperature_2m": "°C", "global_tilted_irradiance": "W/m²"},
            "hourly": {
                "time": ["2026-01-01T00:00", "2026-01-01T01:00", "2026-01-01T02:00"],
                "temperature_2m": [10, 20, 30],
                "relative_humidity_2m": [60, 70, 80],
                "global_tilted_irradiance": [None, 100, 200],
            },
        }
    }
    p, w = Plant(), WeatherConfig()
    result = normalize(saved, p, w)
    assert result["2026-01-01T00:00:00+00:00"]["pv_kw"] == dc_power(100, 10, p, w)
    assert len(result) == 2
    saved["raw"]["hourly"]["time"][1] = "2026-01-01T04:00"
    assert normalize(saved, p, w) == {}


def test_vintage_availability_boundary_and_dst():
    now = datetime(2026, 7, 10, 6, tzinfo=UTC)
    old = {
        "initialized_at": stamp(now - timedelta(hours=12)),
        "available_at": stamp(now - timedelta(hours=6)),
    }
    new = {"initialized_at": stamp(now - timedelta(hours=6)), "available_at": stamp(now)}
    assert choose_vintage([new, old], now - timedelta(seconds=1)) == old
    assert choose_vintage([new, old], now) == new
    assert local_stamp("2026-10-25T00:00:00+00:00", "Europe/London").endswith("+01:00")
    assert local_stamp("2026-10-25T01:00:00+00:00", "Europe/London").endswith("+00:00")


def test_offline_cache_and_missing_result(tmp_path, monkeypatch):
    import methane.weather as weather

    with pytest.raises(IncompleteWeather, match="offline"):
        fetch("https://example.invalid", {}, offline=True, cache=tmp_path)
    monkeypatch.setattr(
        weather, "fetch", lambda *a, **kw: (_ for _ in ()).throw(IncompleteWeather("missing"))
    )
    with pytest.raises(IncompleteWeather):
        prepare(Config(weather=WeatherConfig(mode="historical")))


def test_forecast_does_not_consult_future_reference():
    c = Config(scenario=Scenario(hours=12, horizon_hours=6))
    weather = prepare(c)
    baseline = forecast_at(weather, c, 0)
    for t in list(weather["truth"])[1:]:
        weather["truth"][t]["pv_kw"] = 1e8
        weather["truth"][t]["ambient_c"] = 999
    assert forecast_at(weather, c, 0) == baseline


@pytest.fixture(scope="module")
def paired():
    return run(
        Config(scenario=Scenario(hours=18, horizon_hours=6), sensors=Sensors(noise_fraction=0))
    )


def test_physical_balances_all_strategies(paired):
    for metrics in paired["metrics"].values():
        assert metrics["max_balance_error"] < 1e-6
        assert metrics["false_alarms"] == 0
        assert metrics["methane_kg"] >= 0


def test_whatif_immutable_frozen_same_information(paired):
    before = json.dumps(paired, sort_keys=True)
    answer = what_if(paired, "MPC · methane", 10, "battery")
    assert answer["cost_version"] == paired["decision_cost_version"]
    assert (
        answer["forecast_source"]
        == paired["records"]["MPC · methane"][10]["decision"]["forecast"]["source"]
    )
    assert "PREDICTION" in answer["label"]
    assert json.dumps(paired, sort_keys=True) == before
    poisoned = copy.deepcopy(paired)
    poisoned["retrospective_truth"] = [{"capacity_kw": 0}] * 18
    poisoned["weather"]["truth"] = {}
    alternate = what_if(poisoned, "MPC · methane", 10, "battery")
    assert alternate["alternative_plan"]["predicted"]["methane_kg"] == pytest.approx(
        answer["alternative_plan"]["predicted"]["methane_kg"]
    )


def test_allocation_max_once_zero_output_and_reprice(paired):
    p, c = Plant(), Costs()
    assert allocation(p, c, [])["eur_per_kg_ch4"] is None
    report = reprice(paired)
    before = json.dumps(paired, sort_keys=True)
    for frames in report["controllers"].values():
        assert frames[-1]["total_eur"] == pytest.approx(sum(frames[-1]["components"].values()))
        for calendar, usage, charged in frames[-1]["allowances"].values():
            assert charged == max(calendar, usage)
        assert frames[0]["total_eur"] == 0
    reprice(paired, replace(c, methane_eur_per_kg=10, battery_eur_per_kwh=999))
    assert json.dumps(paired, sort_keys=True) == before


def test_future_fault_does_not_change_earlier_decisions():
    config = Config(scenario=Scenario(hours=8, horizon_hours=6), sensors=Sensors(noise_fraction=0))
    first = run(config, strategies=["MPC · methane"])
    altered = run(
        replace(config, scenario=replace(config.scenario, fault_start_hour=7, capacity_fraction=0)),
        strategies=["MPC · methane"],
    )
    for a, b in zip(
        first["records"]["MPC · methane"][:7], altered["records"]["MPC · methane"][:7], strict=True
    ):
        assert a["requested"] == pytest.approx(b["requested"])
        assert a["decision"]["diagnosis"] == b["decision"]["diagnosis"]


def test_archive_version_and_matrix(paired, tmp_path):
    path = save(paired, tmp_path)
    restored = load(path)
    assert restored["run_id"] == paired["run_id"]
    assert len(list(cases(suite="synthetic"))) == 18
    assert len(list(cases(suite="historical"))) == 9
    assert all(not c.sensors.enabled for _, c in cases(suite="ablation"))
    assert len(list(cases(suite="thermal"))) == 6


def test_cancelled_batch_keeps_unfinished_cases(tmp_path, monkeypatch):
    import methane.evidence as evidence

    monkeypatch.setattr(evidence, "RUNS", tmp_path)
    token = threading.Event()
    token.set()
    result = list(batch(suite="synthetic", cancel=token))[-1]
    assert len(result) == 18
    assert all(r["status"] == "cancelled" for r in result)


def test_economic_policy_responds_to_value_not_fixed_site_cost():
    p = Plant()
    state = State(800, 30, 500, 300)
    weather = forecast([100] * 6)
    low = plan(p, state, weather, 450, Costs(methane_eur_per_kg=0), "economics")
    high_costs = Costs(methane_eur_per_kg=10)
    high = plan(p, state, weather, 450, high_costs, "economics")
    fixed = plan(
        p, state, weather, 450, replace(high_costs, fixed_opex_eur_per_year=1e12), "economics"
    )
    assert low["predicted"]["methane_kg"] == pytest.approx(0)
    assert high["predicted"]["methane_kg"] > 0
    assert fixed["predicted"]["methane_kg"] == pytest.approx(high["predicted"]["methane_kg"])


def test_full_physical_replay_rejects_inconsistent_incumbent(monkeypatch):
    import methane.dispatch as dispatch
    from methane.audit import PhysicalAuditError, check

    def reject(*args, **kwargs):
        raise PhysicalAuditError([check("thermal_inconsistency", "reactor", 1, "kWh")], {})

    monkeypatch.setattr(dispatch, "trajectory", reject)
    result = plan(
        Plant(), State.initial(Plant()), forecast([0] * 6), 450, Costs(), allow_fallback=False
    )
    assert result["predicted"] is None
    assert result["solver"]["status"] == "invalid-trajectory"
    assert "thermal_inconsistency" in result["solver"]["message"]


def test_disabled_diagnosis_and_flow_recovery():
    p = Plant()
    previous = observation(inventory=0)
    d, incident, _ = update(
        p,
        Sensors(enabled=False),
        Diagnosis(450),
        previous,
        observation(225, inventory=225 / 55),
        450,
    )
    assert d.capacity_kw == 450 and not incident and d.status == "diagnosis disabled"
    d = Diagnosis(450, flow_isolated=True, active_incident=True)
    for i in range(2):
        obs = observation(450, inventory=(i + 1) * 450 / 55)
        d, incident, event = update(p, Sensors(noise_fraction=0), d, previous, obs, 450)
        previous = obs
    assert not d.flow_isolated and not d.active_incident
    assert event == "Hydrogen-flow sensor recovered"


def test_greedy_probe_remains_local_and_does_not_spend_unconfirmed_hydrogen():
    p = Plant()
    state = State(800, 0, 500, 300)
    d = plan(
        p,
        state,
        forecast([500] * 6),
        200,
        Costs(),
        "greedy",
        minimum_ely=200,
        dependable_capacity=135,
        allow_fallback=False,
    )
    assert d["actions"]
    first = d["actions"][0]
    assert first["electrolyser_kw"] == pytest.approx(200)
    assert first["methane_kg"] <= 135 / 55 / 0.5 + 1e-6
    _, actual = execute(p, state, first, 500, 20, 0, 135, Costs())
    assert not actual["forced_trip"]
    assert actual["applied"]["methane_kg"] == pytest.approx(first["methane_kg"])


def test_playback_time_is_completed_interval_boundary(paired):
    from methane.ui import playback_value

    view = playback_value(paired)
    frames = view["frames"]["Greedy"]
    assert frames[0]["local_time"] == "2026-07-10T01:00:00+01:00"
    assert frames[1]["local_time"] == "2026-07-10T02:00:00+01:00"
