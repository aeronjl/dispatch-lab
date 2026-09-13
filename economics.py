"""Explanatory cost allocation over completed physical runs; no dispatch changes.

All defaults are illustrative EUR assumptions, not market quotes. Replaceable
capital is allocated ONCE using max(calendar use, estimated usage). This is an
explicit accounting proxy, not a physical degradation or lifetime cash-flow model.
"""

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from math import isfinite

from experiment import Scenario, run_experiment
from plant import Plant

HOURS_PER_YEAR = 8760
MODEL_VERSION = "0.1.0"
CATEGORIES = (
    "Solar ownership",
    "Battery capital use",
    "Electrolyser capital use",
    "Installation & site ownership",
    "Standing operation",
    "Water & consumables",
    "Fault budget",
)


@dataclass(frozen=True)
class Costs:
    solar_eur_per_kw: float = 500
    solar_years: float = 25
    battery_eur_per_kwh: float = 180
    battery_power_eur_per_kw: float = 80
    battery_calendar_years: float = 15
    battery_cycles: float = 4000
    electrolyser_eur_per_kw: float = 700
    stack_share: float = 0.4
    stack_calendar_years: float = 15
    stack_operating_hours: float = 60000
    start_equivalent_hours: float = 0
    other_equipment_years: float = 20
    installation_fraction: float = 0.25
    site_setup_eur: float = 50000
    fixed_opex_eur_per_year: float = 20000
    water_litres_per_kg: float = 12
    water_eur_per_m3: float = 3
    consumables_eur_per_kg: float = 0.05
    repair_eur_per_incident: float = 500
    visit_eur_per_incident: float = 300

    def __post_init__(self):
        if not all(isfinite(x) and x >= 0 for x in vars(self).values()):
            raise ValueError("Cost assumptions must be finite and nonnegative.")
        for name in (
            "solar_years",
            "battery_calendar_years",
            "battery_cycles",
            "stack_calendar_years",
            "stack_operating_hours",
            "other_equipment_years",
        ):
            if getattr(self, name) <= 0:
                raise ValueError("Assumed equipment lives must be positive.")
        if self.stack_share > 1:
            raise ValueError("Stack share must be a fraction from 0 to 1.")


def physical_id(result):
    """Stable identity includes realised actions but excludes solver timing noise."""
    payload = {
        "plant": result["plant"],
        "scenario": result["scenario"],
        "model_version": result["model_version"],
        "traces": {
            name: [[r["productive_kw"], r["battery_kwh"], r["started"]] for r in rows]
            for name, rows in result["records"].items()
        },
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()[:12]


def capital(plant: Plant, costs: Costs):
    solar = plant.solar_kw * costs.solar_eur_per_kw
    battery_cells = plant.battery_kwh * costs.battery_eur_per_kwh
    battery_power = plant.battery_kw * costs.battery_power_eur_per_kw
    electrolyser = plant.electrolyser_kw * costs.electrolyser_eur_per_kw
    hardware = solar + battery_cells + battery_power + electrolyser
    stack = electrolyser * costs.stack_share
    installation = hardware * costs.installation_fraction
    assets = {
        "Solar": solar,
        "Battery cells": battery_cells,
        "Battery power electronics": battery_power,
        "Electrolyser stack": stack,
        "Electrolyser other equipment": electrolyser - stack,
        "Installation": installation,
        "Site setup": costs.site_setup_eur,
    }
    calendar = (
        solar / costs.solar_years
        + battery_cells / costs.battery_calendar_years
        + stack / costs.stack_calendar_years
        + (battery_power + electrolyser - stack + installation + costs.site_setup_eur)
        / costs.other_equipment_years
    )
    return {
        "assets": assets,
        "upfront_eur": sum(assets.values()),
        "calendar_capital_eur_per_year": calendar,
        "calendar_plus_standing_eur_per_year": calendar + costs.fixed_opex_eur_per_year,
    }


def evaluate(result, costs: Costs):
    """Allocate costs to the recorded period, without annualising its hydrogen yield."""
    plant = Plant(**result["plant"])
    cap = capital(plant, costs)
    assets = cap["assets"]
    dt = plant.dt_hours
    hours = len(result["records"]["Greedy"]) * dt
    year_fraction = hours / HOURS_PER_YEAR
    s = result["scenario"]
    incidents = int(
        s["fault_capacity_fraction"] < 1
        and s["fault_duration_hours"] > 0
        and 0 <= s["fault_start_hour"] < hours
    )
    outputs = {}
    for name, rows in result["records"].items():
        physical = result["metrics"][name]
        discharge = sum(r["discharge_kw"] for r in rows) * dt
        on_hours = sum(r["on"] for r in rows) * dt
        equivalent_cycles = discharge / (plant.battery_kwh * plant.eta) if plant.battery_kwh else 0
        battery_calendar = assets["Battery cells"] / costs.battery_calendar_years * year_fraction
        battery_usage = assets["Battery cells"] * equivalent_cycles / costs.battery_cycles
        stack_calendar = assets["Electrolyser stack"] / costs.stack_calendar_years * year_fraction
        effective_hours = on_hours + physical["starts"] * costs.start_equivalent_hours
        stack_usage = assets["Electrolyser stack"] * effective_hours / costs.stack_operating_hours
        # Do not add a second replacement/depreciation allowance for the same capital.
        battery_allowance = max(battery_calendar, battery_usage)
        stack_allowance = max(stack_calendar, stack_usage)
        productive_kg = physical["hydrogen_kg"]
        water_m3 = productive_kg * costs.water_litres_per_kg / 1000
        buckets = dict(
            zip(
                CATEGORIES,
                (
                    assets["Solar"] / costs.solar_years * year_fraction,
                    battery_allowance
                    + assets["Battery power electronics"]
                    / costs.other_equipment_years
                    * year_fraction,
                    stack_allowance
                    + assets["Electrolyser other equipment"]
                    / costs.other_equipment_years
                    * year_fraction,
                    (assets["Installation"] + assets["Site setup"])
                    / costs.other_equipment_years
                    * year_fraction,
                    costs.fixed_opex_eur_per_year * year_fraction,
                    water_m3 * costs.water_eur_per_m3
                    + productive_kg * costs.consumables_eur_per_kg,
                    incidents * (costs.repair_eur_per_incident + costs.visit_eur_per_incident),
                ),
                strict=True,
            )
        )
        total = sum(buckets.values())
        outputs[name] = {
            "buckets_eur": buckets,
            "allocated_cost_eur": total,
            "cash_opex_budget_eur": sum(buckets[k] for k in CATEGORIES[4:]),
            "capital_allowance_eur": sum(buckets[k] for k in CATEGORIES[:4]),
            "period_eur_per_kg": total / productive_kg if productive_kg > 1e-9 else None,
            "hydrogen_kg": productive_kg,
            "initial_battery_kwh": physical["initial_battery_kwh"],
            "final_battery_kwh": physical["final_battery_kwh"],
            "curtailed_kwh": physical["curtailed_kwh"],
            "startup_kwh": physical["startup_kwh"],
            "starts": physical["starts"],
            "water_m3": water_m3,
            "battery_equivalent_cycles": equivalent_cycles,
            "electrolyser_on_hours": on_hours,
            "allowances": {
                "battery_calendar_eur": battery_calendar,
                "battery_usage_eur": battery_usage,
                "battery_charged_eur": battery_allowance,
                "stack_calendar_eur": stack_calendar,
                "stack_usage_eur": stack_usage,
                "stack_charged_eur": stack_allowance,
            },
        }
    return {
        "economics_version": MODEL_VERSION,
        "physical_run_id": physical_id(result),
        "currency": "EUR",
        "basis": "illustrative undiscounted period cost allocation",
        "hours": hours,
        "incidents": incidents,
        "cost_assumptions": asdict(costs),
        "capital": cap,
        "controllers": outputs,
    }


def cost_timeline(result, costs: Costs):
    """Cost states at hourly boundaries, using exactly the completed-run accounting.

    A prefix includes only completed intervals. In particular, the incident budget
    first appears after the interval in which a fault begins, never in advance.
    """
    plant = Plant(**result["plant"])
    frames = {name: [] for name in result["records"]}
    records = {name: [] for name in frames}
    metrics = {
        name: {
            "hydrogen_kg": 0,
            "starts": 0,
            "initial_battery_kwh": plant.battery_kwh * plant.initial_soc,
            "final_battery_kwh": plant.battery_kwh * plant.initial_soc,
            "curtailed_kwh": 0,
            "startup_kwh": 0,
        }
        for name in frames
    }
    losses = dict.fromkeys(frames, 0)
    for hour in range(len(result["records"]["Greedy"]) + 1):
        if hour:
            for name in frames:
                row = result["records"][name][hour - 1]
                records[name].append(row)
                m = metrics[name]
                m["hydrogen_kg"] += row["h2_kg"]
                m["starts"] += row["started"]
                m["final_battery_kwh"] = row["battery_kwh"]
                m["curtailed_kwh"] += row["curtailed_kw"] * plant.dt_hours
                m["startup_kwh"] += row["startup_kwh"]
                losses[name] += row["battery_loss_kwh"]
        prefix = evaluate({**result, "records": records, "metrics": metrics}, costs)
        for name, values in prefix["controllers"].items():
            frames[name].append({**values, "battery_loss_kwh": losses[name]})
    return {
        "physical_run_id": physical_id(result),
        "capital": prefix["capital"],
        "cost_assumptions": asdict(costs),
        "controllers": frames,
    }


def sensitivities(result, costs: Costs):
    """Explicit stress scenarios, not confidence intervals or market forecasts."""
    fields = [
        ("solar_eur_per_kw", "Solar purchase cost"),
        ("battery_eur_per_kwh", "Battery cell purchase cost"),
        ("electrolyser_eur_per_kw", "Electrolyser purchase cost"),
        ("fixed_opex_eur_per_year", "Standing operating costs"),
        ("installation_fraction", "Installation allowance"),
        ("battery_cycles", "Battery cycle life"),
        ("stack_operating_hours", "Stack operating life"),
        ("start_equivalent_hours", "Extra wear per start"),
    ]
    base = evaluate(result, costs)["controllers"]["Forecast MPC"]["period_eur_per_kg"]
    if base is None:
        return []
    comparisons = []
    for field, label in fields:
        value = getattr(costs, field)
        lo, hi = (
            (0, max(10, 2 * value))
            if field == "start_equivalent_hours"
            else (0.5 * value, 1.5 * value)
        )
        low = evaluate(result, replace(costs, **{field: lo}))["controllers"]["Forecast MPC"]
        high = evaluate(result, replace(costs, **{field: hi}))["controllers"]["Forecast MPC"]
        outcomes = [low["period_eur_per_kg"], high["period_eur_per_kg"]]
        comparisons.append(
            {
                "parameter": field,
                "label": label,
                "low_input": lo,
                "high_input": hi,
                "low_input_eur_per_kg": outcomes[0],
                "high_input_eur_per_kg": outcomes[1],
                "min_delta": min(*outcomes, base) - base,
                "max_delta": max(*outcomes, base) - base,
                "span": max(outcomes) - min(outcomes),
            }
        )
    return sorted(comparisons, key=lambda item: item["span"], reverse=True)


def battery_study(source, costs: Costs, progress=None):
    """Change only storage size, beginning every candidate with an EMPTY battery.

    Runs share weather, forecasts, fault schedules and all other equipment. No
    annual production extrapolation or optimal annual-size claim is made.
    Full traces are retained so the comparison can be checked and reproduced.
    """
    base_plant = replace(Plant(**source["plant"]), initial_soc=0)
    scenario = Scenario(**source["scenario"])
    scale = max(400, base_plant.battery_kwh)
    sizes = sorted({0.0, scale * 0.25, scale * 0.5, scale, min(8000, scale * 2)})
    candidates = []
    for i, size in enumerate(sizes):
        plant = replace(base_plant, battery_kwh=size)

        def report(fraction, desc="", index=i, capacity=size):
            if progress:
                progress((index + fraction) / len(sizes), desc=f"{capacity:g} kWh battery · {desc}")

        physical = run_experiment(plant, scenario, progress=report)
        costed = evaluate(physical, costs)
        candidates.append({"battery_kwh": size, "physical": physical, "economics": costed})
    no_battery = candidates[0]["economics"]
    rows = []
    for candidate in candidates:
        costed = candidate["economics"]
        for name, value in costed["controllers"].items():
            base = no_battery["controllers"][name]
            delta_kg = value["hydrogen_kg"] - base["hydrogen_kg"]
            delta_cost = value["allocated_cost_eur"] - base["allocated_cost_eur"]
            rows.append(
                {
                    "battery_kwh": candidate["battery_kwh"],
                    "controller": name,
                    "upfront_eur": costed["capital"]["upfront_eur"],
                    "annual_calendar_and_standing_eur": costed["capital"][
                        "calendar_plus_standing_eur_per_year"
                    ],
                    "period_allocated_eur": value["allocated_cost_eur"],
                    "hydrogen_kg": value["hydrogen_kg"],
                    "period_eur_per_kg": value["period_eur_per_kg"],
                    "extra_kg_vs_no_battery": delta_kg,
                    "extra_cost_vs_no_battery_eur": delta_cost,
                    "eur_per_extra_kg": delta_cost / delta_kg if delta_kg > 1e-6 else None,
                    "final_battery_kwh": value["final_battery_kwh"],
                    "curtailed_kwh": value["curtailed_kwh"],
                    "fallbacks": candidate["physical"]["metrics"][name]["fallbacks"],
                    "limited_solves": candidate["physical"]["metrics"][name]["limited_solves"],
                }
            )
    return {
        "source_run_id": physical_id(source),
        "cost_assumptions": asdict(costs),
        "initial_battery_kwh_all_candidates": 0,
        "candidates": candidates,
        "rows": rows,
    }
