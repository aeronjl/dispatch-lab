"""Shared sparse MILP constraints for forecasts and feasible physical execution."""

import os
import time
import warnings
from dataclasses import asdict

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from methane.audit import PhysicalAuditError, physical, require
from methane.battery import BatteryState
from methane.cancellation import checkpoint
from methane.components import assemble
from methane.costing import decision_cost, marginal
from methane.electrolyser import State as ElyState
from methane.physics import (
    ACTION_KEYS,
    H2_PER_CH4,
    REACTION_KWH_PER_KG,
    temperature_after,
    thermal_coefficients,
    transition,
)
from methane.reactor import ReactorState, operating_transition
from methane.storage import State as GasState

VARIABLES = (
    *ACTION_KEYS,
    "battery_kwh",
    "h2_kg",
    "co2_kg",
    "temperature_c",
    "electrolyser_on",
    "electrolyser_start",
    "reactor_on",
    "reactor_start",
    "direction",
    "heat_direction",
    "accepted",
    "rejected",
    "tank_full",
    "hydrogen_produced_kg",
    "hydrogen_consumed_kg",
    "co2_consumed_kg",
    "electrolyser_bus_kw",
    "reactor_bus_kw",
)
BINARY = (
    "electrolyser_on",
    "electrolyser_start",
    "reactor_on",
    "reactor_start",
    "direction",
    "heat_direction",
    "tank_full",
)

UNITS = {
    k: "boolean"
    if k in BINARY
    else "kWh"
    if k == "battery_kwh"
    else "°C"
    if k == "temperature_c"
    else "kg"
    if k.endswith("_kg") or k in ("accepted", "rejected")
    else "kW"
    for k in VARIABLES
}


class Model:
    def __init__(self, n):
        self.n = n
        self.ids = {k: np.arange(i * n, (i + 1) * n) for i, k in enumerate(VARIABLES)}
        self.lower = np.zeros(n * len(VARIABLES))
        self.upper = np.full_like(self.lower, np.inf)
        self.integer = np.zeros_like(self.lower)
        self.rows, self.cols, self.values, self.lo, self.hi = [], [], [], [], []
        self.bus_rows = []
        self.objective = np.zeros_like(self.lower)
        self._component_bounds = set()
        for k in BINARY:
            self.upper[self.ids[k]] = self.integer[self.ids[k]] = 1

    def add(self, terms, lo=-np.inf, hi=np.inf):
        row = len(self.lo)
        for key, t, value in terms:
            self.rows.append(row)
            self.cols.append(self.ids[key][t])
            self.values.append(value)
        self.lo.append(lo)
        self.hi.append(hi)

    def add_component(self, block, bindings):
        if set(bindings) != {k for k, *_ in block.bounds}:
            raise ValueError("Every component port must be bound exactly once")
        for port in block.ports:
            if UNITS[bindings[port.name]] != port.unit:
                raise ValueError(
                    f"Port unit mismatch: {port.name} ({port.unit}) -> {bindings[port.name]}"
                )
        for name, lower, upper, integer in block.bounds:
            key = bindings[name]
            ids = self.ids[key]
            if key in self._component_bounds:
                self.lower[ids] = np.maximum(self.lower[ids], lower)
                self.upper[ids] = np.minimum(self.upper[ids], upper)
            else:
                self.lower[ids], self.upper[ids] = lower, upper
                self._component_bounds.add(key)
            self.integer[ids] = np.maximum(self.integer[ids], int(integer))
        for row in block.rows:
            self.add([(bindings[k], t, v) for k, t, v in row.terms], row.lower, row.upper)

    def solve(self, seconds):
        checkpoint()
        matrix = coo_matrix(
            (self.values, (self.rows, self.cols)), shape=(len(self.lo), len(self.lower))
        ).tocsc()
        begin = time.perf_counter()
        try:
            options = {"time_limit": seconds, "mip_rel_gap": 0.001}
            if os.environ.get("DISPATCH_BATCH_WORKER") == "1":
                options["threads"] = 1
            with warnings.catch_warnings():
                warnings.filterwarnings(
                    "ignore",
                    message="Unrecognized options detected.*threads.*",
                    category=RuntimeWarning,
                )
                r = milp(
                    self.objective,
                    integrality=self.integer,
                    bounds=Bounds(self.lower, self.upper),
                    constraints=LinearConstraint(matrix, self.lo, self.hi),
                    options=options,
                )
        except (RuntimeError, ValueError) as exc:
            return None, {
                "status": "solver-error",
                "termination": "solver-error",
                "seconds": time.perf_counter() - begin,
                "gap": None,
                "message": str(exc),
                "valid_incumbent": False,
                "fallback_used": False,
            }
        elapsed = time.perf_counter() - begin
        x = r.x
        valid = x is not None and np.all(np.isfinite(x))
        if valid:
            ax = matrix @ x
            valid = (
                np.all(x >= self.lower - 1e-5)
                and np.all(x <= self.upper + 1e-5)
                and np.all(ax >= np.array(self.lo) - 1e-5)
                and np.all(ax <= np.array(self.hi) + 1e-5)
                and np.all(np.abs(x[self.integer == 1] - np.round(x[self.integer == 1])) < 1e-5)
            )
        status = {
            0: "solved",
            1: "time-limited",
            2: "infeasible",
            3: "unbounded",
            4: "solver-error",
        }.get(r.status, "solver-error")
        termination = "optimal-within-tolerance" if status == "solved" else status
        if x is not None and not valid:
            status = "invalid-incumbent"
        return (x if valid and r.status in (0, 1) else None), {
            "status": status,
            "termination": termination,
            "native_status_code": int(r.status),
            "objective_value": float(r.fun)
            if getattr(r, "fun", None) is not None and np.isfinite(r.fun)
            else None,
            "objective_bound": float(r.mip_dual_bound)
            if getattr(r, "mip_dual_bound", None) is not None and np.isfinite(r.mip_dual_bound)
            else None,
            "fallback_used": False,
            "seconds": elapsed,
            "gap": float(r.mip_gap)
            if getattr(r, "mip_gap", None) is not None and np.isfinite(r.mip_gap)
            else None,
            "message": r.message,
            "valid_incumbent": bool(valid),
        }


def capacity_horizon(p, forecast, capacity):
    """A declared planning estimate per hour, separate from simulator fault truth."""
    values = forecast.get("electrolyser_capacity_kw", [capacity] * len(forecast["pv_kw"]))
    if (
        len(values) == 0
        or len(values) != len(forecast["pv_kw"])
        or any(
            isinstance(v, bool)
            or not isinstance(v, (float, int))
            or not np.isfinite(v)
            or not 0 <= v <= p.electrolyser_kw
            for v in values
        )
    ):
        raise ValueError("Electrolyser capacity needs one finite in-range estimate per hour")
    return values


def build(p, state, forecast, capacity, enforce_commitment=True, *, battery=None, components=None):
    """Compose component ports; only shared DC-bus allocation belongs here."""
    n = len(forecast["pv_kw"])
    capacities = capacity_horizon(p, forecast, capacity)
    m = Model(n)
    components = components or assemble(p, battery_override=battery)
    durations = (p.dt_hours,) * n
    m.add_component(
        components.battery.planning(BatteryState(state.battery_kwh), durations),
        {
            "energy": "battery_kwh",
            "charge": "charge_kw",
            "discharge": "discharge_kw",
            "charging": "direction",
        },
    )
    m.add_component(
        components.electrolyser.planning(
            ElyState(state.electrolyser_on), max(capacities), durations
        ),
        {
            "power": "electrolyser_kw",
            "on": "electrolyser_on",
            "start": "electrolyser_start",
            "hydrogen": "hydrogen_produced_kg",
            "electricity": "electrolyser_bus_kw",
        },
    )
    m.add_component(
        components.hydrogen.planning(GasState(state.h2_kg), n),
        {"inventory": "h2_kg", "inflow": "hydrogen_produced_kg", "outflow": "hydrogen_consumed_kg"},
    )
    m.add_component(
        components.co2.planning(GasState(state.co2_kg), n, forecast["deliveries_kg"]),
        {
            "inventory": "co2_kg",
            "outflow": "co2_consumed_kg",
            "accepted": "accepted",
            "rejected": "rejected",
            "full": "tank_full",
        },
    )
    m.add_component(
        components.reactor.planning(
            ReactorState(state.temperature_c, state.reactor_on, state.commitment_hours),
            forecast["ambient_c"],
            durations,
            enforce_commitment,
        ),
        {
            "temperature": "temperature_c",
            "heater": "heater_kw",
            "cooling": "cooling_kw",
            "methane": "methane_kg",
            "on": "reactor_on",
            "start": "reactor_start",
            "heating": "heat_direction",
            "electricity": "reactor_bus_kw",
            "hydrogen": "hydrogen_consumed_kg",
            "co2": "co2_consumed_kg",
        },
    )
    for t, pv in enumerate(forecast["pv_kw"]):
        m.upper[m.ids["electrolyser_kw"][t]] = capacities[t]
        if forecast.get("electrolyser_isolated", [False] * n)[t]:
            m.upper[m.ids["electrolyser_kw"][t]] = 0
        m.bus_rows.append(len(m.lo))
        m.add(
            [
                ("electrolyser_bus_kw", t, 1),
                ("reactor_bus_kw", t, 1),
                ("charge_kw", t, 1),
                ("discharge_kw", t, -1),
            ],
            hi=pv - forecast.get("service_kw", [0] * n)[t],
        )
    return m


def restrictions(m, alternative):
    key = {
        "battery": "discharge_kw",
        "electrolyser": "electrolyser_kw",
        "reactor": "reactor_start",
    }.get(alternative)
    if key:
        m.upper[m.ids[key][0]] = 0


def trajectory(p, state, actions, forecast, *, battery=None, components=None, capacity=None):
    rows = []
    capacities = capacity_horizon(p, forecast, p.electrolyser_kw if capacity is None else capacity)
    for t, action in enumerate(actions):
        state, row = transition(
            p,
            state,
            action,
            forecast["pv_kw"][t],
            forecast["ambient_c"][t],
            forecast["deliveries_kg"][t],
            battery=battery,
            components=components,
            capacity=capacities[t],
            service_kw=forecast.get("service_kw", [0] * len(forecast["pv_kw"]))[t],
        )
        audits = row.pop("audits", [])
        row["audit_summary"] = {"passed": sum(a["passed"] for a in audits), "total": len(audits)}
        rows.append(row)
    return rows


def prepare_model(
    p,
    state,
    forecast,
    capacity,
    costs,
    objective="methane",
    seconds=0.5,
    alternative=None,
    request=None,
    minimum_ely=0,
    dependable_capacity=None,
    battery=None,
    components=None,
    terminal_battery_value=0.0,
):
    execution = request is not None
    m = build(
        p,
        state,
        forecast,
        capacity,
        enforce_commitment=not execution,
        battery=battery,
        components=components,
    )
    restrictions(m, alternative)
    if minimum_ely:
        m.lower[m.ids["electrolyser_kw"][0]] = minimum_ely
    if dependable_capacity is not None:
        m.upper[m.ids["methane_kg"][0]] = min(
            p.methane_max_kgph,
            max(0, (state.h2_kg + dependable_capacity / p.specific_energy_kwh_per_kg) / H2_PER_CH4),
        )
    if execution:
        for k in ACTION_KEYS:
            m.upper[m.ids[k][0]] = min(m.upper[m.ids[k][0]], max(0, request[k]))
        # Preserve requested downstream production first, then electrolysis and heat.
        weights = {
            "methane_kg": -10000,
            "electrolyser_kw": -10,
            "heater_kw": -1,
            "cooling_kw": -1,
            "charge_kw": -0.01,
            "discharge_kw": 0.001,
        }
        for k, v in weights.items():
            m.objective[m.ids[k]] = v
    else:
        rates = marginal(p, costs)
        scale = 1 if objective == "economics" else 0.001
        for k, v in rates.items():
            m.objective[m.ids[k]] += scale * v
        m.objective[m.ids["methane_kg"]] -= (
            costs.methane_eur_per_kg if objective == "economics" else 1
        )
        for k in ("electrolyser_start", "reactor_start"):
            m.objective[m.ids[k]] += 1e-4
        for k in ("heater_kw", "cooling_kw", "charge_kw", "discharge_kw"):
            m.objective[m.ids[k]] += 1e-7
        if terminal_battery_value:
            from methane.policy import Policy

            Policy(objective=objective, terminal_battery_value_kg_per_kwh=terminal_battery_value)
            m.objective[m.ids["battery_kwh"][-1]] -= terminal_battery_value
    return m


def solve(
    p,
    state,
    forecast,
    capacity,
    costs,
    objective="methane",
    seconds=0.5,
    alternative=None,
    request=None,
    minimum_ely=0,
    dependable_capacity=None,
    battery=None,
    components=None,
    terminal_battery_value=0.0,
):
    m = prepare_model(
        p,
        state,
        forecast,
        capacity,
        costs,
        objective,
        seconds,
        alternative,
        request,
        minimum_ely,
        dependable_capacity,
        battery,
        components,
        terminal_battery_value,
    )
    x, info = m.solve(seconds)
    if x is None:
        return None, info
    actions = [{k: float(max(0, x[m.ids[k][t]])) for k in ACTION_KEYS} for t in range(m.n)]
    try:
        trajectory(
            p, state, actions, forecast, battery=battery, components=components, capacity=capacity
        )
    except PhysicalAuditError as exc:
        return None, {
            **info,
            "status": "invalid-trajectory",
            "valid_incumbent": False,
            "message": "Incumbent failed physical replay: " + str(exc),
            "audits": exc.audits,
            "rejected_candidate": exc.context,
        }
    return actions, info


def greedy_action(
    p,
    state,
    pv,
    ambient,
    delivery,
    capacity,
    alternative=None,
    minimum_ely=0,
    dependable_capacity=None,
    battery=None,
    components=None,
    service_kw=0,
    electrolyser_isolated=False,
):
    """Local priority: maintain/produce methane, warm to Tmin+5, make H2, store surplus.

    It consults only this interval. Physical limits override a minimum-run promise.
    """
    forecast = {
        "pv_kw": [pv],
        "ambient_c": [ambient],
        "deliveries_kg": [delivery],
        "service_kw": [service_kw],
        "electrolyser_isolated": [electrolyser_isolated],
    }
    m = build(
        p,
        state,
        forecast,
        capacity,
        enforce_commitment=False,
        battery=battery,
        components=components,
    )
    restrictions(m, alternative)
    if minimum_ely:
        m.lower[m.ids["electrolyser_kw"][0]] = minimum_ely
    if dependable_capacity is not None:
        m.upper[m.ids["methane_kg"][0]] = min(
            p.methane_max_kgph,
            max(0, (state.h2_kg + dependable_capacity / p.specific_energy_kwh_per_kg) / H2_PER_CH4),
        )
    target = min(p.temperature_max_c, p.temperature_min_c + 5)
    passive = temperature_after(p, state.temperature_c, ambient)
    _, b = thermal_coefficients(p)
    m.upper[m.ids["heater_kw"]] = min(p.heater_max_kw, max(0, (target - passive) / b))
    heat_need = max(0, (target - passive) / b)
    big_heat = p.heater_max_kw + p.methane_max_kgph * REACTION_KWH_PER_KG
    m.add(
        [
            ("heater_kw", 0, 1),
            ("methane_kg", 0, REACTION_KWH_PER_KG),
            ("heat_direction", 0, big_heat),
        ],
        hi=heat_need + big_heat,
    )
    for k, v in {
        "methane_kg": -10000,
        "heater_kw": -2,
        "electrolyser_kw": -1,
        "charge_kw": -0.01,
        "discharge_kw": 0.001,
        "cooling_kw": 0.001,
    }.items():
        m.objective[m.ids[k]] = v
    x, info = m.solve(0.5)
    if x is None:
        return {k: 0.0 for k in ACTION_KEYS}, {**info, "status": "safe-off"}
    action = {k: float(max(0, x[m.ids[k][0]])) for k in ACTION_KEYS}
    try:
        transition(
            p,
            state,
            action,
            pv,
            ambient,
            delivery,
            battery=battery,
            components=components,
            capacity=capacity,
            service_kw=service_kw,
        )
    except PhysicalAuditError as exc:
        return {k: 0.0 for k in ACTION_KEYS}, {
            **info,
            "status": "safe-off",
            "message": str(exc),
            "audits": exc.audits,
            "rejected_candidate": exc.context,
        }
    return action, {**info, "status": "local-rule"}


def rollout_greedy(
    p,
    state,
    forecast,
    capacity,
    costs,
    alternative=None,
    minimum_ely=0,
    dependable_capacity=None,
    battery=None,
    components=None,
):
    actions, rows, failures = [], [], []
    capacities = capacity_horizon(p, forecast, capacity)
    for t, pv in enumerate(forecast["pv_kw"]):
        action, info = greedy_action(
            p,
            state,
            pv,
            forecast["ambient_c"][t],
            forecast["deliveries_kg"][t],
            capacities[t],
            alternative if t == 0 else None,
            minimum_ely if t == 0 else 0,
            dependable_capacity if t == 0 else None,
            battery=battery,
            components=components,
            electrolyser_isolated=forecast.get(
                "electrolyser_isolated", [False] * len(forecast["pv_kw"])
            )[t],
            service_kw=forecast.get("service_kw", [0] * len(forecast["pv_kw"]))[t],
        )
        if info["status"] == "safe-off":
            failures.append({"offset": t, **info})
        state, row = transition(
            p,
            state,
            action,
            pv,
            forecast["ambient_c"][t],
            forecast["deliveries_kg"][t],
            battery=battery,
            components=components,
            capacity=capacities[t],
            service_kw=forecast.get("service_kw", [0] * len(forecast["pv_kw"]))[t],
        )
        actions.append(action)
        audits = row.pop("audits", [])
        row["audit_summary"] = {"passed": sum(a["passed"] for a in audits), "total": len(audits)}
        rows.append(row)
    return {
        "actions": actions,
        "trajectory": rows,
        "solver": {
            "status": "fallback" if failures else "local-rule",
            "fallback_used": bool(failures),
            "seconds": 0,
            "gap": None,
            "failures": failures,
        },
        "predicted": predicted(p, costs, rows),
    }


def predicted(p, costs, rows):
    return {
        "methane_kg": sum(r["applied"]["methane_kg"] for r in rows),
        "reactor_starts": sum(r["reactor_start"] for r in rows),
        "ending": rows[-1]["state"] if rows else None,
        "temperature_c": [r["state"]["temperature_c"] for r in rows],
        **decision_cost(p, costs, rows),
    }


def plan(
    p,
    state,
    forecast,
    capacity,
    costs,
    objective="methane",
    seconds=0.5,
    alternative=None,
    allow_fallback=True,
    minimum_ely=0,
    dependable_capacity=None,
    battery=None,
    components=None,
    terminal_battery_value=0.0,
):
    if objective == "greedy":
        result = rollout_greedy(
            p,
            state,
            forecast,
            capacity,
            costs,
            alternative,
            minimum_ely,
            dependable_capacity,
            battery=battery,
            components=components,
        )
        if not allow_fallback and result["solver"]["failures"]:
            return {"actions": [], "trajectory": [], "predicted": None, "solver": result["solver"]}
        return result
    actions, info = solve(
        p,
        state,
        forecast,
        capacity,
        costs,
        objective,
        seconds,
        alternative,
        minimum_ely=minimum_ely,
        dependable_capacity=dependable_capacity,
        battery=battery,
        components=components,
        terminal_battery_value=terminal_battery_value,
    )
    if actions is None:
        if not allow_fallback:
            return {"actions": [], "trajectory": [], "solver": info, "predicted": None}
        fallback = rollout_greedy(
            p, state, forecast, capacity, costs, alternative, battery=battery, components=components
        )
        fallback["solver"] = {
            **info,
            "status": "fallback",
            "fallback_used": True,
            "reason": info["status"],
        }
        return fallback
    rows = trajectory(
        p, state, actions, forecast, battery=battery, components=components, capacity=capacity
    )
    return {
        "actions": actions,
        "trajectory": rows,
        "solver": info,
        "predicted": predicted(p, costs, rows),
    }


def execute(
    p,
    state,
    requested,
    pv,
    ambient,
    delivery,
    capacity,
    costs,
    *,
    battery=None,
    components=None,
    service_kw=0,
):
    forecast = {
        "pv_kw": [pv],
        "ambient_c": [ambient],
        "deliveries_kg": [delivery],
        "service_kw": [service_kw],
    }
    actions, info = solve(
        p,
        state,
        forecast,
        capacity,
        costs,
        request=requested,
        seconds=0.5,
        battery=battery,
        components=components,
    )
    if not actions:
        info = {
            **info,
            "fallback_used": True,
            "fallback_action": "safe-off",
            "reason": info["status"],
        }
    applied = actions[0] if actions else {k: 0.0 for k in ACTION_KEYS}
    next_state, row = transition(
        p,
        state,
        applied,
        pv,
        ambient,
        delivery,
        battery=battery,
        components=components,
        capacity=capacity,
        requested=requested,
        service_kw=service_kw,
    )
    trip = (
        state.commitment_hours > 0 or requested["methane_kg"] >= p.methane_min_kgph
    ) and not next_state.reactor_on
    row.update(
        requested=requested,
        forced_trip=bool(trip),
        execution_solver=info,
        unmet_action={k: max(0, requested[k] - applied[k]) for k in ACTION_KEYS},
    )
    mode, commitment, _, trip = operating_transition(
        state.reactor_on,
        state.commitment_hours,
        next_state.reactor_on,
        requested["methane_kg"] >= p.methane_min_kgph,
        applied["heater_kw"] > 1e-4,
        next_state.temperature_c > ambient + 1,
        p.minimum_run_hours,
    )
    row["mode"], row["forced_trip"] = mode, trip
    row["audits"] = physical(p, state, row, capacity=capacity)
    require(row["audits"], {"before": asdict(state), "row": row})
    return next_state, row
