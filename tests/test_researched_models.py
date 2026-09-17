"""Source reproduction, independent energy ledgers, and bounded model-transfer checks."""

from copy import deepcopy
from dataclasses import replace
from math import exp

import numpy as np
import pytest

from methane.audit import PhysicalAuditError, physical
from methane.config import Config, Costs, Plant, Scenario
from methane.dispatch import build, execute, plan
from methane.engineering import audit_archive
from methane.integration import Integration, forecast, settings
from methane.physics import ACTION_KEYS, State, transition
from methane.reference import interval as reference_interval
from methane.researched_models import (
    AC_FRACTIONS,
    HHV_KWH_PER_KG,
    Research,
    converter_input,
    converter_points,
    cooling_limit,
    enthalpy,
    heat_fraction,
    preview,
    reactor_coefficients,
)
from methane.simulation import run


def plant(**research):
    return Plant(start_energy_kwh=0, min_load_fraction=0.01, integration={"research": research})


def action(**values):
    return {**dict.fromkeys(ACTION_KEYS, 0.0), **values}


@pytest.mark.parametrize("eta", [0.92, 0.96, 0.99])
def test_published_converter_equation_at_knots_and_interpolation_bound(eta):
    capacity = 600
    s = Integration(ac_efficiency=eta, research=Research())
    points = converter_points(capacity, eta, 1)
    for fraction, (ac, dc) in zip(AC_FRACTIONS, points, strict=True):
        z = dc / (capacity / eta)
        source_eta = eta / 0.9637 * (-0.0162 * z - 0.0059 / z + 0.9858)
        assert source_eta * dc == pytest.approx(ac, abs=1e-9)
        assert ac == fraction * capacity
    errors = []
    for ac in np.linspace(12, 600, 201):
        dc = converter_input(s, ac)
        z = dc / (capacity / eta)
        delivered = capacity * (-0.0162 * z * z + 0.9858 * z - 0.0059) / 0.9637
        errors.append(abs(delivered - ac) / capacity)
    assert max(errors) < 0.0003  # approximation vs published curve, not device accuracy
    assert converter_input(s, 0) == 0
    for ac in [1, 601, -1, float("nan")]:
        with pytest.raises(ValueError):
            converter_input(s, ac)


def test_converter_segment_is_exact_in_feasibility_not_an_objective_penalty():
    p = plant(converter_loss_scale=1.5)
    f = forecast(p, dict(pv_kw=[700], ambient_c=[20], deliveries_kg=[0]), 0)
    m = build(p, State.initial(p), f, p.electrolyser_kw)
    # Fix 35 kW AC between knots (30,60); an adversarial objective must not
    # select a nonadjacent segment or exaggerate the required DC power.
    m.add([("heater_kw", 0, 1)], lo=35, hi=35)
    for k in ["electrolyser_kw", "methane_kg", "charge_kw", "discharge_kw", "cooling_kw"]:
        m.upper[m.ids[k]] = 0
    m.objective[m.ids["interface_dc_kw"]] = -1
    x, info = m.solve(1)
    assert x is not None, info
    assert x[m.ids["interface_dc_kw"][0]] == pytest.approx(converter_input(settings(p), 35))
    active = sum(x[m.ids[f"converter_segment_{j}"][0]] for j in range(7))
    assert active == pytest.approx(1)


def test_reference_heat_and_cold_feed_are_separate_from_coolant_dynamics():
    p = plant()
    s = settings(p)
    assert HHV_KWH_PER_KG == pytest.approx(39.38588716700508)
    assert heat_fraction(p, s) * 55 + HHV_KWH_PER_KG == pytest.approx(55)
    assert cooling_limit(s, 20) == 160
    assert cooling_limit(s, 40) == 32
    assert cooling_limit(s, 45) == 0
    assert cooling_limit(s, 60) == 0
    gross, feed = reactor_coefficients(300, 0)
    # Earlier NIST reference computation used 16.0425 g/mol; preserve rounded
    # plant chemistry and explicitly account for the changed denominator.
    assert gross == pytest.approx(3.08098180946257 * 16.0425 / 16)
    assert feed == pytest.approx(0.7573798904027373 * 16.0425 / 16)
    recovered_gross, remaining_feed = reactor_coefficients(300, 1)
    assert recovered_gross == gross
    assert remaining_feed == pytest.approx(feed - 0.5348701105648862)
    assert remaining_feed > 0
    # Perfect sensible recuperation can at most restore reference-state reaction
    # heat; it cannot invent heat by fully preheating the higher-duty feed stream.
    assert recovered_gross - remaining_feed == pytest.approx(165.0035 / 57.6)
    from methane.reference import research_heat

    for tc in (250, 300, 400):
        for effectiveness in (0, 0.5, 1):
            r = Research(reactor_reference_c=tc, feed_recovery_fraction=effectiveness)
            values = reactor_coefficients(tc, effectiveness)
            independent = research_heat(r.model_dump())
            assert values == pytest.approx(tuple(float(x) for x in independent))
            assert values[0] - values[1] <= 165.0035 / 57.6 + 1e-10
    with pytest.raises(ValueError):
        enthalpy("water", 298.15)


def test_thermal_and_electrical_execution_match_independent_decimal_ledger():
    p = replace(plant(), heat_loss_kw_per_k=0.04, initial_h2_kg=10)
    before = replace(State.initial(p), temperature_c=300, reactor_on=True)
    a = action(electrolyser_kw=165, methane_kg=5, heater_kw=10)
    after, row = transition(p, before, a, 700, 20, 0)
    expected = reference_interval(p.to_dict(), vars(before), a, 700, 20, 0)
    assert vars(after) == pytest.approx(expected["state"])
    for k in [
        "reaction_heat_kwh",
        "feed_heating_kwh",
        "heat_loss_kwh",
        "demand_kw",
        "curtailed_kwh",
    ]:
        assert row[k] == pytest.approx(expected[k])
    q = row["reaction_heat_kwh"] - row["feed_heating_kwh"] + 10
    equilibrium = 20 + q / 0.04
    assert after.temperature_c == pytest.approx(
        equilibrium + (300 - equilibrium) * exp(-0.04 / 0.3)
    )
    assert row["thermal_residual_kwh"] == pytest.approx(0, abs=1e-10)
    assert row["component_records"]["reactor"]["implementation_id"] == "analytic-nist-cold-feed/1"
    corrupted = deepcopy(row)
    corrupted["integration"]["cooling_heat_kw"] += 5
    assert not all(a["passed"] for a in physical(p, before, corrupted))
    corrupted = deepcopy(row)
    corrupted["integration"]["converter_points_kw"][0][1] += 1
    assert not all(a["passed"] for a in physical(p, before, corrupted))


@pytest.mark.parametrize("objective", ["greedy", "methane", "economics"])
def test_planners_reconcile_and_weather_error_changes_applied_cooling_capacity(objective):
    p = plant()
    state = State.initial(p)
    f = forecast(p, dict(pv_kw=[700] * 6, ambient_c=[20] * 6, deliveries_kg=[0] * 6), 0)
    r = plan(p, state, f, p.electrolyser_kw, Costs(), objective, seconds=1)
    assert r["trajectory"]
    for a, row in zip(r["actions"], r["trajectory"], strict=True):
        expected = reference_interval(p.to_dict(), vars(state), a, 700, 20, 0)
        assert row["demand_kw"] == pytest.approx(expected["demand_kw"])
        assert row["state"] == pytest.approx(expected["state"])
        state = State(**row["state"])
    request = action(electrolyser_kw=400, heater_kw=30)
    _, cool = execute(p, State.initial(p), request, 700, 20, 0, p.electrolyser_kw, Costs())
    _, hot = execute(p, State.initial(p), request, 700, 44, 0, p.electrolyser_kw, Costs())
    assert cool["applied"]["electrolyser_kw"] > 300
    assert hot["applied"]["electrolyser_kw"] < 30
    assert hot["requested"] == request
    assert hot["integration"]["effective_cooler_capacity_kw"] == pytest.approx(6.4)
    assert all(a["passed"] for a in hot["audits"])
    with pytest.raises(PhysicalAuditError):
        transition(p, State.initial(p), request, 700, 44, 0)


def test_preview_is_pure_and_legacy_shape_is_unchanged():
    p = plant()
    saved = deepcopy(p.to_dict())
    v = preview(p)
    assert p.to_dict() == saved
    assert v["context"].startswith("Learning preview")
    assert v["conversion"][0]["loss_kw"] > 0
    assert "research" not in Plant(integration={}).to_dict()["integration"]
    assert "integration" not in Plant().to_dict()
    assert Integration(research=None).to_dict() == Integration().to_dict()
    r = run(Config(plant=p, scenario=Scenario(hours=6, horizon_hours=6)), strategies=("Greedy",))
    assert r["status"] == "complete", r.get("errors")
    assert audit_archive(r)["passed"]
    assert r["config"]["plant"]["integration"]["research"]["version"] == "researched-interfaces/1"
    from methane.reference import audit

    assert audit(r)["passed"]


@pytest.mark.parametrize(
    "changes",
    [
        {"specific_energy_kwh_per_kg": 30},
        {"temperature_max_c": 800},
        {"integration": {"research": {"reactor_reference_c": 200}}},
        {"integration": {"research": {"converter_loss_scale": -1}}},
        {"integration": {"research": {}, "ac_efficiency": 1}},
    ],
)
def test_out_of_domain_models_rejected_without_clipping(changes):
    with pytest.raises(ValueError):
        replace(plant(), **changes)


def test_research_parameters_are_disclosed_uncertainty_choices():
    from methane.uncertainty import catalogue, validate_world

    c = Config(plant=plant()).to_dict()
    view = catalogue(c)
    assert not view["unregistered"]
    entries = [r for r in view["parameters"] if r["path"].startswith("plant.integration.research.")]
    assert len(entries) == len(Research.model_fields)
    assert all(r["active"] for r in entries)
    changed = deepcopy(c)
    changed["plant"]["integration"]["research"]["cooler_ua_kw_per_k"] = 3.2
    with pytest.raises(ValueError, match="[Hh]idden"):
        validate_world(dict(config=changed, controller_config=c, draws=[]))


def test_explanation_uses_forecast_cooling_envelope_not_rated_capacity():
    from methane.sensing import Diagnosis
    from methane.simulation import evidence

    p = plant()
    state = State.initial(p)
    f = forecast(p, dict(pv_kw=[700], ambient_c=[40], deliveries_kg=[0]), 0)
    planned = plan(p, state, f, p.electrolyser_kw, Costs(), "greedy")
    row = planned["trajectory"][0]
    assert row["integration"]["cooling_heat_kw"] == pytest.approx(32)
    assert row["integration"]["parameters"]["cooler_capacity_kw"] == 160
    f.update(source="synthetic test", current_forecast_error_kw=0)
    explanation = evidence(p, state, f, planned, Diagnosis(p.electrolyser_kw), "greedy")
    assert "External cooler reaches its thermal limit" in explanation["bindings"]["electrolyser"]
