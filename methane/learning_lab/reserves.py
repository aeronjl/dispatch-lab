"""Mode-dependent, saturating inventory needs; no terminal sale credit."""

import math

import numpy as np

DEFAULTS = dict(
    version="homeostatic-reserves/1",
    battery_fraction=0.2,
    hydrogen_fraction=0.2,
    co2_fraction=0.1,
    thermal_fraction=0.2,
    shortage_weight=0.5,
    service_hours=2,
)


def validate(value):
    if set(value) != set(DEFAULTS) or value["version"] != DEFAULTS["version"]:
        raise ValueError("Unknown reserve contract")
    for key in set(DEFAULTS) - {"version"}:
        number = value[key]
        upper = 24 if key == "service_hours" else 10 if key == "shortage_weight" else 1
        if (
            type(number) not in (int, float)
            or not math.isfinite(number)
            or not 0 <= number <= upper
        ):
            raise ValueError(f"Invalid reserve assumption: {key}")
    return value


def targets(p, state, forecast, value):
    validate(value)
    service = sum(forecast.get("service_kw", [])[: int(value["service_hours"])])
    hot = state.reactor_on or state.commitment_hours > 0
    scale = 1.0 if hot else 0.5
    ambient = forecast["ambient_c"][0]
    return {
        "battery_kwh": (
            min(p.battery_kwh, p.battery_kwh * value["battery_fraction"] + service),
            max(1.0, p.battery_kwh),
        ),
        "h2_kg": (p.h2_capacity_kg * value["hydrogen_fraction"] * scale, p.h2_capacity_kg),
        "co2_kg": (p.co2_capacity_kg * value["co2_fraction"] * scale, p.co2_capacity_kg),
        "temperature_c": (
            ambient
            + max(0.0, p.temperature_min_c - ambient) * (1.0 if hot else value["thermal_fraction"]),
            max(1.0, p.temperature_min_c - ambient),
        ),
    }


def add_objective(m, p, state, forecast):
    value = forecast.get("reserve_policy")
    if value is None:
        return
    # Each deficit is a nonnegative continuous slack. It changes the objective
    # only, so scarce power never makes a preference a physical obligation.
    for key, (target, normaliser) in targets(p, state, forecast, value).items():
        name = "reserve_deficit_" + key
        start = len(m.lower)
        m.ids[name] = np.arange(start, start + m.n)
        m.lower = np.append(m.lower, np.zeros(m.n))
        m.upper = np.append(m.upper, np.full(m.n, np.inf))
        m.integer = np.append(m.integer, np.zeros(m.n))
        m.objective = np.append(
            m.objective, np.full(m.n, value["shortage_weight"] / normaliser / m.n)
        )
        for t in range(m.n):
            m.add([(key, t, 1), (name, t, 1)], lo=target)


def account(p, state, forecast, trajectory):
    value = forecast.get("reserve_policy")
    if value is None:
        return None
    needs = targets(p, state, forecast, value)
    rows = [
        {key: max(0, target - row["state"][key]) for key, (target, _) in needs.items()}
        for row in trajectory
    ]
    penalty = (
        sum(sum(row[k] / needs[k][1] for k in row) for row in rows)
        * value["shortage_weight"]
        / max(1, len(rows))
    )
    return dict(
        targets={k: v[0] for k, v in needs.items()},
        deficits=rows,
        preference_penalty=penalty,
        units="Objective units: kg methane equivalent for methane MPC; EUR for economics MPC",
        interpretation="Saturating shortfall penalty, not expenditure or inventory sale value. Reserves compete with production and variable costs; no reward above target. Reference/stock/job needs remain explicit service obligations.",
    )
