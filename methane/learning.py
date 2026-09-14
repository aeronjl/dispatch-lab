"""Small, reproducible teaching adapters. No source-run mutation or network access."""

import copy
import json
import math
from dataclasses import asdict
from datetime import timedelta
from functools import lru_cache

from methane.audit import PhysicalAuditError, check
from methane.battery import IMPLEMENTATIONS, Battery, BatteryInput, BatteryParameters, BatteryState
from methane.config import Costs, Plant, Sensors, WeatherConfig
from methane.costing import allocation
from methane.electrolyser import Electrolyser
from methane.electrolyser import Inputs as ElyInput
from methane.electrolyser import Parameters as ElyParameters
from methane.electrolyser import State as ElyState
from methane.forecast import ForecastRequest, SavedForecastProvider
from methane.model_topics import TOPICS
from methane.physics import ACTION_KEYS, State, transition
from methane.reactor import REACTION_KWH_PER_KG, Reactor, ReactorState, ThermalInput, coefficients
from methane.reactor import Parameters as ThermalParameters
from methane.sensing import Diagnosis, observe, update
from methane.solar_model import default_design, interval
from methane.storage import Inputs as GasInput
from methane.storage import Parameters as GasParameters
from methane.storage import State as GasState
from methane.storage import Storage
from methane.timebase import stamp, utc


def defaults(topic):
    return {c["key"]: c["default"] for p in TOPICS[topic]["passages"] for c in p["controls"]}


def validate(topic, values):
    controls = {c["key"]: c for p in TOPICS[topic]["passages"] for c in p["controls"]}
    if set(values) - controls.keys():
        raise ValueError("Unknown learning input")
    result = defaults(topic)
    result.update(values)
    for key, value in result.items():
        c = controls[key]
        if c["options"] is not None:
            if value not in c["options"]:
                raise ValueError("Unsupported " + c["label"])
        elif (
            isinstance(value, bool)
            or not isinstance(value, (float, int))
            or not math.isfinite(value)
            or not c["lower"] <= value <= c["upper"]
        ):
            raise ValueError(f"{c['label']} must be {c['lower']}–{c['upper']} {c['unit']}")
        elif c["step"] == 1 and value != int(value):
            raise ValueError(c["label"] + " must be a whole number")
    return result


def metric(label, value, unit=""):
    return dict(label=label, value=value, unit=unit)


def series(label, points, unit=""):
    return dict(label=label, points=list(points), unit=unit)


def result(metrics, sequences=(), steps=(), checks=(), **extra):
    return dict(
        metrics=metrics, series=list(sequences), steps=list(steps), checks=list(checks), **extra
    )


def _thermal_action(p, temperature, ambient, methane, heater_limit=60):
    a, b = coefficients(p.thermal_capacity_kwh_per_k, p.heat_loss_kw_per_k)
    net = (300 - a * temperature - (1 - a) * ambient) / b
    heat = min(heater_limit, max(0, net - methane * REACTION_KWH_PER_KG))
    cooling = min(p.cooling_max_kw, max(0, methane * REACTION_KWH_PER_KG - net))
    return heat, cooling


@lru_cache(maxsize=2)
def teaching_trace(producing=True):
    p = Plant()
    state = State(400, 20, 500, 300)
    rows = []
    for hour in range(6):
        methane = 10 if producing else 0
        heat, cooling = _thermal_action(p, state.temperature_c, 20, methane)
        action = dict.fromkeys(ACTION_KEYS, 0.0)
        action.update(electrolyser_kw=275, methane_kg=methane, heater_kw=heat, cooling_kw=cooling)
        state, row = transition(p, state, action, 1000, 20, 0)
        row["time"] = stamp(utc("2026-04-10T00:00:00Z") + timedelta(hours=hour))
        rows.append(row)
    return rows


def _battery(v):
    p = BatteryParameters(roundtrip_efficiency=v["efficiency"])
    b = Battery(p, IMPLEMENTATIONS[v["implementation"]])
    step = b.step(BatteryState(v["energy"]), BatteryInput(v["charge"], v["discharge"]))
    other = Battery(
        p, IMPLEMENTATIONS["loss-ledger/1" if v["implementation"] == "affine/1" else "affine/1"]
    ).step(BatteryState(v["energy"]), BatteryInput(v["charge"], v["discharge"]))
    flows = dict(step.flows)
    # Independent closed-form expected energy for a complete 100 kWh cycle.
    first = b.step(BatteryState(0), BatteryInput(charge_kw=100))
    last = b.step(first.state, BatteryInput(discharge_kw=100 * v["efficiency"]))
    checks = [
        *step.audits,
        check("round_trip_empty", "battery", last.state.energy_kwh, "kWh"),
        check(
            "equivalent_implementation",
            "battery",
            step.state.energy_kwh - other.state.energy_kwh,
            "kWh",
        ),
    ]
    return result(
        [
            metric("Ending energy", step.state.energy_kwh, "kWh"),
            metric("SOC", 100 * step.state.energy_kwh / 800, "%"),
            metric("Charge loss", flows["charge_loss_kwh"], "kWh"),
            metric("Discharge loss", flows["discharge_loss_kwh"], "kWh"),
            metric("Round-trip bus return", 100 * v["efficiency"], "kWh"),
        ],
        [series("Stored energy", [v["energy"], step.state.energy_kwh], "kWh")],
        checks=checks,
        terms={"E_start": v["energy"], "η": p.eta, "Δt": 1},
        implementation=b.identity(),
        independent_expected={"100 kWh cycle return": 100 * v["efficiency"]},
    )


def _solar(v):
    p, w = Plant(), WeatherConfig()
    design = default_design(p, w)
    for s in design["sections"]:
        s.update(tilt=v["tilt"], azimuth=v["azimuth"], shade=v["shade"], soiling=v["soiling"])
    design.update(noct_c=v["noct"], converter_kw=v["converter"])
    from methane.pv import dc_power

    readings = []
    for hour in range(6, 19):
        light = max(0, 850 * math.sin((hour - 6) / 12 * math.pi))
        sample = {
            "irradiance_wm2": light,
            "ambient_c": v["ambient"],
            "pv_kw": dc_power(light, v["ambient"], p, w),
        }
        readings.append(interval(design, sample, f"2026-04-10T{hour:02}:00:00Z", p, w))
    noon = readings[6]
    return result(
        [
            metric("Noon DC output", noon["output_kw"], "kW"),
            metric("Converter clipping", noon["clipped_kw"], "kW"),
            metric("Conversion loss", noon["conversion_loss_kw"], "kW"),
        ],
        [
            series("DC output", [r["output_kw"] for r in readings], "kW"),
            series("Clipped", [r["clipped_kw"] for r in readings], "kW"),
        ],
        steps=readings,
        design=design,
        terms={"NOCT": v["noct"]},
        checks=[
            check(
                "converter_balance",
                "solar",
                noon["output_kw"]
                + noon["clipped_kw"]
                - (noon["available_kw"] + noon["scenario_adjustment_kw"]) * design["efficiency"],
                "kW",
            )
        ],
    )


def _electrolyser(v):
    e = Electrolyser(ElyParameters(specific_energy_kwh_per_kg=v["sec"]))
    state = ElyState(v["initial_on"] == "yes")
    steps = []
    checks = []
    for i in range(6):
        r = e.step(state, ElyInput(v["load"] if i < v["run_hours"] else 0, 450))
        state = r.state
        steps.append({"interval": i, **dict(r.flows), "on": state.on})
        checks.extend(r.audits)
    return result(
        [
            metric("Hydrogen", sum(x["hydrogen_kg"] for x in steps), "kg"),
            metric("Water consumed", sum(x["water_kg"] for x in steps), "kg"),
            metric("Startup electricity", sum(x["startup_kwh"] for x in steps), "kWh"),
        ],
        [
            series("Productive electricity", [x["productive_kwh"] for x in steps], "kWh"),
            series("Startup electricity", [x["startup_kwh"] for x in steps], "kWh"),
        ],
        steps,
        checks,
    )


def _storage(topic, v):
    gas = Storage(
        GasParameters(60 if topic == "hydrogen" else 1000, topic),
        v.get("implementation", "balance/1"),
    )
    state = GasState(v["inventory"])
    steps = []
    checks = []
    for i in range(1 if topic == "hydrogen" else 6):
        inflow = v["inflow"] if topic == "hydrogen" else (v["delivery"] if i == v["arrival"] else 0)
        r = gas.step(state, GasInput(inflow, v["outflow"]))
        state = r.state
        steps.append({"interval": i, "inventory_kg": state.inventory_kg, **dict(r.flows)})
        checks.extend(r.audits)
    return result(
        [
            metric("Ending inventory", state.inventory_kg, "kg"),
            metric("Rejected delivery", sum(s["rejected_kg"] for s in steps), "kg"),
            metric(
                "Feedstock-only methane ceiling",
                v["outflow"] / (0.5 if topic == "hydrogen" else 2.75),
                "kg/interval",
            ),
        ],
        [series("Inventory", [v["inventory"]] + [s["inventory_kg"] for s in steps], "kg")],
        steps,
        checks,
    )


def _reactor(v):
    if 0 < v["methane"] < 3:
        raise ValueError("Methane request must be zero or at least 3 kg/h")
    p = ThermalParameters(heat_loss_kw_per_k=v["loss"])
    reactor = Reactor(p)
    state = ReactorState(v["ambient"])
    steps = []
    checks = []
    for hour in range(12):
        demand = v["methane"] if hour < v["cutoff"] else 0
        requested = demand if 250 <= state.temperature_c <= 400 else 0
        methane = requested
        heat, cool = _thermal_action(p, state.temperature_c, v["ambient"], methane, v["heater"])
        a, b = coefficients(p.thermal_capacity_kwh_per_k, p.heat_loss_kw_per_k)
        end = (
            a * state.temperature_c
            + (1 - a) * v["ambient"]
            + b * (heat + REACTION_KWH_PER_KG * methane - cool)
        )
        if methane and not 250 <= end <= 400:
            methane = 0
            heat, cool = _thermal_action(p, state.temperature_c, v["ambient"], 0, v["heater"])
        r = reactor.execute(
            state,
            ThermalInput(state.temperature_c, v["ambient"], heat, methane, cool),
            requested_running=requested >= 3,
        )
        state = r.state
        checks.extend(r.audits)
        steps.append(
            {
                "interval": hour,
                "temperature_c": state.temperature_c,
                "production_demand_kg": demand,
                "requested_methane_kg": requested,
                "methane_kg": methane,
                "heater_kw": heat,
                "cooling_kw": cool,
                "commitment_hours": state.commitment_hours,
                **dict(r.flows),
                **dict(r.diagnostics),
                "h2_consumed_kg": 0.5 * methane,
                "co2_consumed_kg": 2.75 * methane,
                "water_produced_kg": 2.25 * methane,
            }
        )
    return result(
        [
            metric("Ending temperature", state.temperature_c, "°C"),
            metric("Methane", sum(s["methane_kg"] for s in steps), "kg"),
            metric("Reaction heat", sum(s["reaction_heat_kwh"] for s in steps), "kWh"),
        ],
        [
            series("Temperature", [s["temperature_c"] for s in steps], "°C"),
            series("Methane", [s["methane_kg"] for s in steps], "kg"),
        ],
        steps,
        checks,
        terms={"C": 0.3, "UA": v["loss"]},
    )


def _weather(v):
    from zoneinfo import ZoneInfo

    data = {}
    start = utc("2026-10-25T00:00:00Z")
    for i in range(36):
        data[stamp(start + timedelta(hours=i))] = {"pv_kw": i * 10, "ambient_c": 15}
    if v["missing"] == "yes":
        data.pop(stamp(start + timedelta(hours=v["hour"] + 1)))
    vintages = [
        dict(
            id=f"teaching-issue-{h}",
            source="Synthetic saved-issue teaching fixture",
            initialized_at=stamp(start + timedelta(hours=h)),
            available_at=stamp(start + timedelta(hours=h + v["lag"])),
            data={
                time: {**point, "pv_kw": point["pv_kw"] + (60 if h == 0 else 20)}
                for time, point in data.items()
            },
        )
        for h in (0, 6)
    ]
    provider = SavedForecastProvider.from_weather({"mode": "historical", "vintages": vintages})
    decision = start + timedelta(hours=v["hour"])
    forecast = provider.horizon(ForecastRequest(stamp(decision), 6, 100, 15, 1000))
    return result(
        [
            metric("Eligible issues", sum(utc(x["available_at"]) <= decision for x in vintages)),
            metric("Decision UTC", stamp(decision)),
            metric("Local London", decision.astimezone(ZoneInfo("Europe/London")).isoformat()),
        ],
        [
            series("Selected forecast", forecast["pv_kw"], "kW"),
            series(
                "Synthetic historical reference", [(v["hour"] + i) * 10 for i in range(6)], "kW"
            ),
        ],
        steps=vintages,
        forecast=forecast,
        source="Synthetic fixture; not ERA5 measurements",
        reference_semantics="An illustrative historical reference, withheld from forecast selection. It demonstrates the role of reanalysis; these numbers are not ERA5 data or site measurements.",
        interval_semantics="A sample labelled 12:00 as a preceding-hour mean describes [11:00, 12:00) UTC.",
        dst_example=[
            (start + timedelta(hours=h)).astimezone(ZoneInfo("Europe/London")).isoformat()
            for h in (0, 1, 2)
        ],
    )


def _diagnosis(v):
    p = Plant()
    sensors = Sensors(
        noise_fraction=v["noise"],
        discrepancy_fraction=v["threshold"],
        ambiguity_policy=v["ambiguity_policy"],
    )
    d = Diagnosis(450)
    prior = {"h2_inventory_kg": 20}
    inventory = 20
    steps = []
    for hour in range(24):
        probing = d.capacity_kw < 449
        request = min(450, d.capacity_kw + 45) if probing else 275
        if v["fault"] == "low activity":
            request = 0
        capacity = 160 if v["fault"] == "capacity" and 3 <= hour < 8 else 450
        delivered = min(request, capacity)
        flow = delivered / 55
        before = {"h2_inventory_kg": inventory}
        outflow = flow
        inventory = 20
        row = {
            "h2_produced_kg": flow,
            "h2_consumed_kg": outflow,
            "applied": {"electrolyser_kw": delivered},
            "state": {
                "h2_kg": inventory,
                "battery_kwh": 400,
                "co2_kg": 500,
                "temperature_c": 300,
                "electrolyser_on": delivered > 0,
                "reactor_on": True,
                "commitment_hours": 0,
            },
        }
        measured = observe(
            p,
            sensors,
            before,
            row,
            7,
            hour,
            flow_bias=0.5 if v["fault"] == "flow" and 3 <= hour < 8 else 0,
            rng_policy="named-channels/1",
        )
        if v["fault"] == "ambiguous" and 3 <= hour < 8:
            measured["h2_inventory_kg"] += 8 if hour % 2 else -8
        d, incident, event = update(p, sensors, d, prior, measured, request, probe=probing)
        steps.append(
            {
                "interval": hour,
                "requested_kw": request,
                "observed": measured,
                "diagnosis": asdict(d),
                "incident": incident,
                "event": event,
                "probe": probing,
                "retrospective_truth": {"capacity_kw": capacity, "flow_kg": flow},
            }
        )
        prior = measured
    return result(
        [
            metric("Final estimate", d.capacity_kw, "kW"),
            metric("Confirmed incidents", d.incidents),
            metric("Final diagnosis", d.status),
        ],
        [
            series("Capacity estimate", [s["diagnosis"]["capacity_kw"] for s in steps], "kW"),
            series("Measured power", [s["observed"]["power_kw"] for s in steps], "kW"),
        ],
        steps,
    )


def _bus(v):
    from methane.dispatch import execute

    p = Plant()
    state = State(v["reserve"], 20, 500, 300)
    steps = []
    for hour in range(6):
        a = dict.fromkeys(ACTION_KEYS, 0.0)
        heat, cool = _thermal_action(p, state.temperature_c, 20, 10)
        a.update(
            electrolyser_kw=v["load"],
            methane_kg=10,
            heater_kw=heat,
            cooling_kw=cool,
            discharge_kw=400,
        )
        state, row = execute(p, state, a, v["pv"] if hour < 3 else 0, 20, 0, 450, Costs())
        steps.append(row)
    return result(
        [
            metric("Ending battery", state.battery_kwh, "kWh"),
            metric("Methane", sum(x["applied"]["methane_kg"] for x in steps), "kg"),
            metric("Unused solar", sum(x["curtailed_kwh"] for x in steps), "kWh"),
        ],
        [
            series("Battery energy", [s["state"]["battery_kwh"] for s in steps], "kWh"),
            series("Applied electrolysis", [s["applied"]["electrolyser_kw"] for s in steps], "kW"),
        ],
        steps,
        [a for s in steps for a in s["audits"]],
    )


def _controllers(v):
    from methane.cancellation import checkpoint
    from methane.dispatch import plan

    p = Plant()
    state = State(300, 20, 500, 300)
    n = int(v["horizon"])
    forecast = {
        "pv_kw": [
            max(0, 700 * math.sin((i + 6) % 24 / 24 * 2 * math.pi)) * (1 + v["bias"])
            for i in range(n)
        ],
        "ambient_c": [20] * n,
        "deliveries_kg": [0] * n,
    }
    from methane.simulation import evidence

    forecast["source"] = {
        "id": "teaching-controller-forecast/1",
        "source": "Frozen synthetic forecast fixture",
    }
    forecast["current_forecast_error_kw"] = 0
    plans = {}
    for objective in ("greedy", "methane", "economics"):
        checkpoint()
        plans[objective] = plan(p, state, forecast, 450, Costs(), objective=objective, seconds=0.5)
        if plans[objective]["actions"]:
            plans[objective]["evidence"] = evidence(
                p, state, forecast, plans[objective], Diagnosis(450), objective
            )
    return result(
        [
            metric(
                label + " predicted methane",
                x["predicted"]["methane_kg"] if x.get("predicted") else None,
                "kg",
            )
            for label, x in plans.items()
        ],
        [
            series(label, [r["state"]["temperature_c"] for r in x["trajectory"]], "°C")
            for label, x in plans.items()
        ],
        plans=plans,
        starting_state=asdict(state),
        forecast=forecast,
        costs=asdict(Costs()),
        checks=[a for x in plans.values() for r in x["trajectory"] for a in r.get("audits", [])],
    )


def _economics(v):
    p = Plant()
    rows = teaching_trace(v["output"] == "producing")
    costs = Costs(
        methane_eur_per_kg=v["price"],
        co2_eur_per_kg=v["co2_price"],
        methane_assets_years=v["life"],
        reactor_operating_hours=v["reactor_life"],
    )
    allocation_result = allocation(p, costs, rows, with_lineage=True)
    return result(
        [
            metric("Allocated cost", allocation_result["total_eur"], "€"),
            metric("Decision cost", allocation_result["variable_and_wear_eur"], "€"),
            metric("Assumed contribution", allocation_result["assumed_contribution_eur"], "€"),
            metric("Cost per kg", allocation_result["eur_per_kg_ch4"], "€/kg"),
        ],
        [
            series(
                "Allocated cost",
                [allocation(p, costs, rows[:i])["total_eur"] for i in range(1, 7)],
                "€",
            )
        ],
        steps=rows,
        allocation=allocation_result,
        physical_trace_sha256=_digest(rows),
    )


def _experiments(v):
    from pathlib import Path

    comparison = {}
    for name in ("produce", "retain"):
        rows = teaching_trace(name == "produce")[: int(v["window"])]
        comparison[name] = {
            "methane_kg": sum(r["applied"]["methane_kg"] for r in rows),
            "ending": rows[-1]["state"],
            "cost": allocation(Plant(), Costs(), rows),
        }
    selected = comparison[v["schedule"]]
    path = Path(__file__).resolve().parent.parent / "docs/learning-recomputation.json"
    return result(
        [
            metric("Methane", selected["methane_kg"], "kg"),
            metric("Ending hydrogen", selected["ending"]["h2_kg"], "kg"),
            metric("Ending CO₂", selected["ending"]["co2_kg"], "kg"),
            metric("Ending battery", selected["ending"]["battery_kwh"], "kWh"),
        ],
        [
            series(
                name,
                [
                    sum(r["applied"]["methane_kg"] for r in teaching_trace(name == "produce")[:i])
                    for i in range(1, int(v["window"]) + 1)
                ],
                "kg",
            )
            for name in comparison
        ],
        comparison=comparison,
        saved_recomputation=json.loads(path.read_text())
        if path.exists()
        else {"status": "unavailable"},
    )


def _siting(v):
    from methane.siting.cashflow import calculate
    from methane.weather import dc_power

    capacity = max(0, 10000 * (1 - v["excluded"]) - v["footprint"]) * 0.04
    p = Plant(solar_kw=capacity)
    powers = [
        dc_power(
            v["irradiance"] * max(0, math.sin(math.pi * (h - 6) / 12)),
            v["ambient"],
            p,
            WeatherConfig(),
        )
        if 6 <= h <= 18
        else 0
        for h in range(24)
    ]
    years = [
        dict(
            receipts_eur=30000 * v["acceptance"] * v["price"],
            cost_eur=20000,
            accepted_kg=30000 * v["acceptance"],
        )
        for _ in range(10)
    ]
    cash = calculate(500000, years, v["discount"])
    independent = -500000 + sum(
        (30000 * v["acceptance"] * v["price"] - 20000) / (1 + v["discount"]) ** i
        for i in range(1, 11)
    )
    return result(
        [
            metric("Coarse PV capacity", capacity, "kW"),
            metric("Resource DC energy", sum(powers), "kWh"),
            metric("Project NPV", cash["npv_eur"], "EUR"),
            metric("Accepted methane", 30000 * v["acceptance"], "kg/year"),
        ],
        [
            series("Hourly DC resource", powers, "kW"),
            series(
                "Cumulative discounted cash",
                [r["discounted_cumulative_eur"] for r in cash["ledger"]],
                "EUR",
            ),
        ],
        cash["ledger"],
        [dict(id="cash-independent", passed=abs(independent - cash["npv_eur"]) < 1e-6)],
        geometry=dict(
            parcel_m2=10000, excluded_m2=10000 * v["excluded"], footprint_m2=v["footprint"]
        ),
        cashflow=cash,
    )


def _digest(value):
    import hashlib

    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


@lru_cache(maxsize=128)
def _evaluate(topic, encoded):
    v = json.loads(encoded)
    from methane.service_learning import ADAPTERS

    if topic in ADAPTERS:
        return ADAPTERS[topic](v)
    if topic in ("hydrogen", "co2"):
        return _storage(topic, v)
    return globals()["_" + topic](v)


def evaluate(topic, inputs=None):
    from methane.documentation import bindings

    if topic not in TOPICS:
        raise ValueError("Unknown model topic")
    v = validate(topic, inputs or {})
    identity = {
        "schema_version": "dispatch-lab/learning-result/1",
        "topic": topic,
        "fixture_id": TOPICS[topic]["fixture_id"],
        "inputs": v,
        "seed": 7,
        "context": "Learning example",
        "input_digest": _digest(v),
        "execution_identity": bindings()[topic],
    }
    try:
        payload = copy.deepcopy(_evaluate(topic, json.dumps(v, sort_keys=True)))
        payload["summary"] = learning_summary(topic, v, payload)
        return {**identity, "status": "complete", **payload}
    except (ValueError, KeyError) as exc:
        return {
            **identity,
            "status": "infeasible" if isinstance(exc, PhysicalAuditError) else "incomplete",
            "error": str(exc),
            "checks": getattr(exc, "audits", []),
        }


def learning_summary(topic, inputs, payload):
    if topic in (
        "cleaning",
        "inspection",
        "logistics",
        "service_costs",
        "service_uncertainty",
        "charging",
        "recovery",
    ):
        return payload["scope"]
    m = {x["label"]: x["value"] for x in payload["metrics"]}
    if topic == "siting":
        return f"The declared area screen supports {m['Coarse PV capacity']:.1f} kW. The fixed teaching production yields an assumed NPV of €{m['Project NPV']:.0f}; this is independent of resource power and is not an operating simulation."
    if topic == "battery":
        return f"This interval ends with {m['Ending energy']:.2f} kWh stored. Charging loses {m['Charge loss']:.2f} kWh and discharging loses {m['Discharge loss']:.2f} kWh. A complete 100 kWh cycle returns {m['Round-trip bus return']:.1f} kWh at this efficiency."
    if topic == "solar":
        return f"At noon, {m['Noon DC output']:.1f} kW reaches the bus and {m['Converter clipping']:.1f} kW is clipped at the converter. Plant curtailment is outside this isolated calculation."
    if topic == "electrolyser":
        return f"The sequence produces {m['Hydrogen']:.2f} kg hydrogen, consumes {m['Water consumed']:.2f} kg water and uses {m['Startup electricity']:.1f} kWh for starting, in addition to productive electricity."
    if topic in ("hydrogen", "co2"):
        return f"The sequence ends with {m['Ending inventory']:.2f} kg stored and {m['Rejected delivery']:.2f} kg explicitly rejected. The withdrawal can support at most {m['Feedstock-only methane ceiling']:.2f} kg methane per interval before other constraints."
    if topic == "reactor":
        return f"The sequence produces {m['Methane']:.2f} kg methane and ends at {m['Ending temperature']:.1f} °C. Its reaction releases {m['Reaction heat']:.2f} kWh of heat. Use the interval control to inspect starts and commitments."
    if topic == "weather":
        return f"At this decision boundary, {m['Eligible issues']} saved issue(s) are available. The selected issue is {payload['forecast']['source']['id']}. These are teaching fixtures, not measured weather."
    if topic == "diagnosis":
        return f"The sequence confirms {m['Confirmed incidents']} incident(s). Its final capacity estimate is {m['Final estimate']:.1f} kW and the diagnostic state is {m['Final diagnosis']}. Step through the evidence before interpreting that final state."
    if topic == "economics":
        return f"The same physical trace is allocated €{m['Allocated cost']:.2f}. Action-sensitive inputs and wear account for €{m['Decision cost']:.2f}; the assumed operating contribution is €{m['Assumed contribution']:.2f}."
    if topic == "experiments":
        return f"At this reporting boundary the selected schedule has produced {m['Methane']:.1f} kg methane and retains {m['Ending hydrogen']:.1f} kg hydrogen, {m['Ending CO₂']:.1f} kg CO₂ and {m['Ending battery']:.1f} kWh battery energy."
    if topic == "bus":
        return f"After solar disappears, the sequence ends with {m['Ending battery']:.1f} kWh battery energy. It has produced {m['Methane']:.1f} kg methane. Requested and applied actions show which loads could be supplied."
    return "These are predictions from identical starting information. Inspect ending inventories, operating limits and each solver outcome alongside the methane totals."
