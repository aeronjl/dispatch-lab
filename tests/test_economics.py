"""Accounting boundaries, unit conversions, causal comparisons and export integrity."""

import copy
import csv
import io
import json
import zipfile
from dataclasses import asdict, replace

import pytest

from economics import Costs, battery_study, capital, evaluate, sensitivities
from experiment import Scenario, run_experiment
from plant import Plant


@pytest.fixture(scope="module")
def physical():
    return run_experiment(Plant(), Scenario())


def free_costs(**overrides):
    values = asdict(Costs())
    for key in values:
        if "eur" in key or key == "installation_fraction":
            values[key] = 0
    values.update(overrides)
    return Costs(**values)


def test_purchase_bill_is_counted_once_with_stack_inside_system_price():
    cap = capital(Plant(), Costs())
    # 500k solar + 144k cells + 32k electronics + 315k electrolyser,
    # plus 25% installation on that hardware + 50k site.
    assert cap["upfront_eur"] == pytest.approx(1_288_750)
    assert cap["assets"]["Electrolyser stack"] == pytest.approx(126_000)
    assert cap["calendar_plus_standing_eur_per_year"] == pytest.approx(83_937.5)


def test_water_litres_to_cubic_metres_and_per_kg_consumables(physical):
    costs = free_costs(water_litres_per_kg=20, water_eur_per_m3=5, consumables_eur_per_kg=0.2)
    result = evaluate(physical, costs)
    for row in result["controllers"].values():
        # 20 L/kg × €5/m³ / 1000 + €0.20/kg = €0.30/kg.
        assert row["allocated_cost_eur"] == pytest.approx(row["hydrogen_kg"] * 0.3)
        assert row["period_eur_per_kg"] == pytest.approx(0.3)


def test_annual_cost_is_prorated_to_recorded_hours_without_projecting_hydrogen(physical):
    result = evaluate(physical, free_costs(fixed_opex_eur_per_year=8760))
    assert result["hours"] == 72
    for row in result["controllers"].values():
        assert row["cash_opex_budget_eur"] == pytest.approx(72)
        assert (
            row["hydrogen_kg"]
            == physical["metrics"][
                "Greedy" if row is result["controllers"]["Greedy"] else "Forecast MPC"
            ]["hydrogen_kg"]
        )


def test_replaceable_capital_uses_calendar_or_usage_never_both(physical):
    # With effectively unlimited cycle life, only the calendar allocation is charged.
    costs = free_costs(battery_eur_per_kwh=100, battery_calendar_years=10, battery_cycles=1e12)
    low = evaluate(physical, costs)["controllers"]["Greedy"]
    assert low["allocated_cost_eur"] == pytest.approx(80_000 / 10 * 72 / 8760)
    # With 100-cycle assumed life, discharge-related capital use dominates.
    high = evaluate(physical, replace(costs, battery_cycles=100))["controllers"]["Greedy"]
    discharged_internal_kwh = (
        sum(r["discharge_kw"] for r in physical["records"]["Greedy"]) / Plant().eta
    )
    assert high["allocated_cost_eur"] == pytest.approx(discharged_internal_kwh * 100 / 100)
    assert high["allocated_cost_eur"] < sum(
        high["allowances"][k] for k in ("battery_calendar_eur", "battery_usage_eur")
    )


def test_extra_start_wear_changes_cost_but_not_the_physical_trace(physical):
    original = copy.deepcopy(physical)
    base = evaluate(physical, Costs())
    stressed = evaluate(physical, replace(Costs(), start_equivalent_hours=10))
    for name in base["controllers"]:
        expected = physical["metrics"][name]["starts"] * 10 * 126_000 / 60_000
        assert stressed["controllers"][name]["allocated_cost_eur"] - base["controllers"][name][
            "allocated_cost_eur"
        ] == pytest.approx(expected)
    assert physical == original


@pytest.mark.parametrize(
    "start,duration,fraction,expected",
    [
        (34, 8, 0.3, 800),
        (34, 24, 0.3, 800),
        (72, 8, 0.3, 0),
        (34, 0, 0.3, 0),
        (34, 8, 1, 0),
        (0, 8, 0, 800),
    ],
)
def test_incident_budget_is_one_event_not_a_per_hour_charge(
    physical, start, duration, fraction, expected
):
    scenario = copy.deepcopy(physical)
    scenario["scenario"].update(
        fault_start_hour=start, fault_duration_hours=duration, fault_capacity_fraction=fraction
    )
    result = evaluate(scenario, free_costs(repair_eur_per_incident=500, visit_eur_per_incident=300))
    for row in result["controllers"].values():
        assert row["allocated_cost_eur"] == expected


def test_zero_production_has_no_defined_cost_per_kg():
    physical = run_experiment(Plant(solar_kw=0, battery_kwh=0), Scenario(days=2))
    result = evaluate(physical, Costs())
    for row in result["controllers"].values():
        assert row["period_eur_per_kg"] is None
        assert row["allocated_cost_eur"] > 0
        assert row["buckets_eur"]["Battery capital use"] == 0
    assert sensitivities(physical, Costs()) == []
    json.dumps(result, allow_nan=False)


def test_cost_totals_reconcile_and_energy_losses_are_not_extra_invoices(physical):
    result = evaluate(physical, Costs())
    for row in result["controllers"].values():
        assert row["allocated_cost_eur"] == pytest.approx(sum(row["buckets_eur"].values()))
        assert row["allocated_cost_eur"] == pytest.approx(
            row["cash_opex_budget_eur"] + row["capital_allowance_eur"]
        )
        assert not any(
            "electricity" in key.lower() or "curtail" in key.lower() for key in row["buckets_eur"]
        )


def test_sensitivity_ranges_are_labelled_and_no_schedule_changes(physical):
    before = copy.deepcopy(physical)
    items = sensitivities(physical, Costs())
    solar = next(i for i in items if i["parameter"] == "solar_eur_per_kw")
    assert (solar["low_input"], solar["high_input"]) == (250, 750)
    assert solar["low_input_eur_per_kg"] < solar["high_input_eur_per_kg"]
    starts = next(i for i in items if i["parameter"] == "start_equivalent_hours")
    assert (starts["low_input"], starts["high_input"]) == (0, 10)
    assert physical == before


def test_battery_study_holds_weather_fixed_and_starts_all_candidates_empty(physical):
    source = copy.deepcopy(physical)
    source["plant"]["initial_soc"] = 0.8
    study = battery_study(source, Costs())
    assert len(study["candidates"]) == 5
    expected_pv = [r["pv_kw"] for r in physical["records"]["Greedy"]]
    for candidate in study["candidates"]:
        p = candidate["physical"]
        assert p["plant"]["initial_soc"] == 0
        assert [r["pv_kw"] for r in p["records"]["Greedy"]] == expected_pv
        for m in p["metrics"].values():
            assert m["initial_battery_kwh"] == 0
    for row in study["rows"]:
        if row["battery_kwh"] == 0:
            assert row["extra_kg_vs_no_battery"] == 0
            assert row["eur_per_extra_kg"] is None
    json.dumps(study, allow_nan=False)


def test_export_contains_actual_assumptions_and_costs(physical, tmp_path, monkeypatch):
    import economics_ui

    monkeypatch.setattr(economics_ui, "ROOT", tmp_path)
    costs = Costs(solar_eur_per_kw=321)
    result = evaluate(physical, costs)
    path = economics_ui.archive(physical, result, sensitivities(physical, costs))
    with zipfile.ZipFile(path) as z:
        archived = json.loads(z.read("economics.json"))
        assert archived["cost_assumptions"]["solar_eur_per_kw"] == 321
        assert json.loads(z.read("physical-run.json")) == physical
        rows = list(csv.DictReader(io.StringIO(z.read("period-costs.csv").decode())))
        assert sum(float(r["forecast_mpc_eur"]) for r in rows) == pytest.approx(
            result["controllers"]["Forecast MPC"]["allocated_cost_eur"]
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"battery_cycles": 0},
        {"solar_eur_per_kw": -1},
        {"stack_share": 1.1},
        {"solar_years": float("nan")},
    ],
)
def test_invalid_cost_assumptions_are_rejected(kwargs):
    with pytest.raises(ValueError):
        Costs(**kwargs)
