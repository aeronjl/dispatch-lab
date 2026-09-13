"""Finite outcome-tree MPC with explicit information and shared decisions.

Branches contain declared predictions and observation histories, never simulator
fault state. Equality constraints prevent independent branch solves from using
an observation before its declared arrival. This is a bounded scenario model,
not a claim that its probabilities or recovery forecasts are calibrated.
"""

import json
from dataclasses import dataclass
from math import isfinite

import numpy as np

from methane.audit import PhysicalAuditError
from methane.cancellation import checkpoint
from methane.dispatch import (
    ACTION_KEYS,
    Model,
    capacity_horizon,
    predicted,
    prepare_model,
    trajectory,
)
from methane.services.contracts import identifier
from methane.timebase import utc

VERSION = "service-outcome-tree-mpc/2"
CONDITIONAL_BOUNDS_VERSION = "service-outcome-tree-mpc/3"
CHARGING_VERSION = "service-outcome-tree-mpc/4"


@dataclass(frozen=True)
class Branch:
    branch_id: str
    probability: float
    forecast_json: str
    information: tuple[str, ...]
    source: str
    service_cost_eur: float = 0
    delivery_capacity_kw: tuple[float, ...] | None = None
    hypothesis_forecast_json: str | None = None

    @classmethod
    def create(
        cls,
        branch_id,
        probability,
        forecast,
        information,
        *,
        source,
        service_cost_eur=0,
        delivery_capacity_kw=None,
        hypothesis_forecast=None,
    ):
        return cls(
            branch_id,
            probability,
            json.dumps(forecast, sort_keys=True, separators=(",", ":"), allow_nan=False),
            tuple(information),
            source,
            service_cost_eur,
            tuple(delivery_capacity_kw) if delivery_capacity_kw is not None else None,
            json.dumps(hypothesis_forecast, sort_keys=True, allow_nan=False)
            if hypothesis_forecast is not None
            else None,
        )

    def __post_init__(self):
        identifier(self.branch_id, "outcome branch")
        identifier(self.source, "outcome assumption source")
        for value in (self.probability, self.service_cost_eur):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError("Scenario probabilities and service costs must be finite")
        if not 0 < self.probability <= 1 or self.service_cost_eur < 0:
            raise ValueError("Branches need positive probability and nonnegative service cost")
        for name in self.information:
            identifier(name, "observation history")
        if type(self.information) is not tuple:
            raise ValueError("Observation histories must be immutable")
        json.loads(self.forecast_json)
        if self.hypothesis_forecast_json is not None:
            nominal, hypothesis = (
                json.loads(self.forecast_json),
                json.loads(self.hypothesis_forecast_json),
            )
            n = len(nominal.get("pv_kw", []))
            if any(hypothesis.get(k) != nominal.get(k) for k in ("times", "source")):
                raise ValueError(
                    "Forecast hypotheses must retain the original issue and time window"
                )
            for key in ("pv_kw", "ambient_c", "deliveries_kg", "service_kw"):
                values = hypothesis.get(key, nominal.get(key, [0] * n))
                original = nominal.get(key, [0] * n)
                if len(values) != n or any(
                    type(v) not in (int, float) or not isfinite(v) or (key != "ambient_c" and v < 0)
                    for v in values
                ):
                    raise ValueError("Forecast hypotheses require finite hourly physical inputs")
                if not values or values[0] != original[0]:
                    raise ValueError(
                        "A latent forecast cannot change current observed inputs or reserved service power"
                    )
            if len(hypothesis.get("electrolyser_isolated", [False] * n)) != n or any(
                type(v) is not bool for v in hypothesis.get("electrolyser_isolated", [False] * n)
            ):
                raise ValueError("Hypothetical isolation requires Boolean hourly inputs")
            if (
                hypothesis.get("electrolyser_isolated", [False] * n)[0]
                != nominal.get("electrolyser_isolated", [False] * n)[0]
            ):
                raise ValueError("Current isolation must be common to every hypothesis")
        if self.delivery_capacity_kw is not None:
            if type(self.delivery_capacity_kw) is not tuple or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v < 0
                for v in self.delivery_capacity_kw
            ):
                raise ValueError(
                    "Hypothetical delivered capacity must be an immutable nonnegative profile"
                )

    @property
    def forecast(self):
        return json.loads(self.forecast_json)


def _validate(plant, branches, capacity):
    if (
        isinstance(capacity, bool)
        or not isinstance(capacity, (int, float))
        or not isfinite(capacity)
        or not 0 <= capacity <= plant.electrolyser_kw
    ):
        raise ValueError("Current capacity must be a finite in-range observation estimate")
    if not branches or len(branches) > 32 or len({b.branch_id for b in branches}) != len(branches):
        raise ValueError("Supply 1–32 distinct outcome branches")
    if abs(sum(b.probability for b in branches) - 1) > 1e-9:
        raise ValueError("Declared outcome probabilities must sum to one")
    forecasts = [b.forecast for b in branches]
    n = len(forecasts[0].get("pv_kw", ()))
    if not 1 <= n <= 168 or any(len(b.information) != n for b in branches):
        raise ValueError("Each branch needs the same 1–168 hour information horizon")
    if len({b.information[0] for b in branches}) != 1:
        raise ValueError("The current action cannot observe a future branch")
    if any(b.delivery_capacity_kw is not None for b in branches):
        if any(
            b.delivery_capacity_kw is None
            or len(b.delivery_capacity_kw) != n
            or any(v > plant.electrolyser_kw for v in b.delivery_capacity_kw)
            for b in branches
        ):
            raise ValueError(
                "Every delivered-capacity branch needs one in-range hypothesis per interval"
            )
    profiles = []
    for forecast in forecasts:
        for key in ("pv_kw", "ambient_c", "deliveries_kg"):
            values = forecast.get(key, ())
            if len(values) != n or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
                for v in values
            ):
                raise ValueError("Every branch needs matching finite forecast intervals")
            if key != "ambient_c" and min(values) < 0:
                raise ValueError("Forecast power and material supply cannot be negative")
        for key in ("service_kw",):
            values = forecast.get(key, [0] * n)
            if len(values) != n or any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v < 0
                for v in values
            ):
                raise ValueError("Service forecasts need one nonnegative load per interval")
        isolated = forecast.get("electrolyser_isolated", [False] * n)
        if len(isolated) != n or any(type(v) is not bool for v in isolated):
            raise ValueError("Isolation forecasts need a Boolean per interval")
        times, source = forecast.get("times", ()), forecast.get("source", {})
        if (
            len(times) != n
            or not source.get("id")
            or not source.get("available_at")
            or not source.get("initialized_at")
        ):
            raise ValueError("Outcome forecasts need their original source and publication timing")
        if utc(source["initialized_at"]) > utc(source["available_at"]) or utc(
            source["available_at"]
        ) > utc(times[0]):
            raise ValueError("An outcome branch cannot use an unpublished forecast")
        if times != forecasts[0].get("times"):
            raise ValueError("Outcome branches must share the same time window")
        from datetime import timedelta

        if (
            utc(times[0]).minute
            or utc(times[0]).second
            or utc(times[0]).microsecond
            or any(utc(t) != utc(times[0]) + timedelta(hours=i) for i, t in enumerate(times))
        ):
            raise ValueError("Outcome forecasts must use consecutive UTC hourly boundaries")
        caps = capacity_horizon(plant, forecast, capacity)
        if abs(caps[0] - capacity) > 1e-9:
            raise ValueError("Branches must retain the current observed capacity estimate")
        profiles.append(caps)
    for i, a in enumerate(branches):
        for j, b in enumerate(branches[:i]):
            separated = False
            for t, (ha, hb) in enumerate(zip(a.information, b.information, strict=True)):
                if ha != hb:
                    separated = True
                    continue
                if separated:
                    raise ValueError("Different observation histories cannot silently merge")
                # These are estimates/currently available quantities, not latent truth.
                # An updated capacity estimate needs its declared observation branch.
                for key, default in (
                    ("pv_kw", 0),
                    ("ambient_c", 20),
                    ("deliveries_kg", 0),
                    ("service_kw", 0),
                    ("electrolyser_isolated", False),
                ):
                    if (
                        forecasts[i].get(key, [default] * n)[t]
                        != forecasts[j].get(key, [default] * n)[t]
                    ):
                        raise ValueError("Shared information cannot contain different known inputs")
                if profiles[i][t] != profiles[j][t]:
                    raise ValueError("Capacity belief cannot change before the observation branch")
    return forecasts, n


def _commands(model, plant, caps, lower, upper):
    """Requested command and predicted delivered power are distinct ports.

    q = min(command, declared capacity), with zero delivery below stable load.
    This is a scenario hypothesis, not a copy of execution truth. The production
    model still checks the full bus/material/thermal trajectory for delivered q.
    """
    n, start = model.n, len(model.lower)
    for i, name in enumerate(("requested_electrolyser_kw", "requested_ely_on", "capacity_limited")):
        model.ids[name] = np.arange(start + i * n, start + (i + 1) * n)
    model.lower = np.concatenate((model.lower, np.zeros(3 * n)))
    model.upper = np.concatenate((model.upper, np.full(n, plant.electrolyser_kw), np.ones(2 * n)))
    model.integer = np.concatenate((model.integer, np.zeros(n), np.ones(2 * n)))
    model.objective = np.concatenate((model.objective, np.full(n, 1e-9), np.zeros(2 * n)))
    m = plant.electrolyser_kw
    for t, cap in enumerate(caps):
        cap = cap if cap >= plant.min_kw else 0
        model.lower[model.ids["requested_electrolyser_kw"][t]] = lower[t]
        model.upper[model.ids["requested_electrolyser_kw"][t]] = upper[t]
        model.add([("requested_electrolyser_kw", t, 1), ("requested_ely_on", t, -m)], hi=0)
        model.add(
            [("requested_electrolyser_kw", t, 1), ("requested_ely_on", t, -plant.min_kw)], lo=0
        )
        model.add([("electrolyser_kw", t, 1), ("requested_electrolyser_kw", t, -1)], hi=0)
        model.add([("electrolyser_kw", t, 1)], hi=cap)
        model.add(
            [
                ("electrolyser_kw", t, 1),
                ("requested_electrolyser_kw", t, -1),
                ("capacity_limited", t, m),
            ],
            lo=0,
        )
        model.add([("electrolyser_kw", t, 1), ("capacity_limited", t, -m)], lo=cap - m)


def solve(
    plant,
    state,
    branches,
    capacity,
    costs,
    *,
    objective="methane",
    risk_weight=0,
    terminal_minimum=None,
    seconds=0.5,
    components=None,
    requested_minimum=None,
    requested_maximum=None,
    alternative=None,
    terminal_battery_value=0,
    branch_requested_bounds=None,
    charging_inputs=None,
):
    """Minimise expected/worst-case process objective with shared action histories.

    risk_weight=0 is expectation, 1 is worst branch, intermediate values mix
    those two explicit criteria. Service cost is a branch constant; fixed plant
    ownership is absent. Terminal minima are physical constraints in every branch.
    """
    checkpoint()
    branches = tuple(branches)
    forecasts, n = _validate(plant, branches, capacity)
    if charging_inputs is not None:
        from methane.services.charging import Inputs, attach, extract

        if not isinstance(charging_inputs, Inputs):
            raise ValueError("Scenario charging requires frozen, validated obligations")
        charging_inputs.validate(n)
    commands = branches[0].delivery_capacity_kw is not None
    if (requested_minimum is not None or requested_maximum is not None) and not commands:
        raise ValueError("Requested-power bounds require delivered-capacity hypotheses")
    lower, upper = (
        list(requested_minimum or [0] * n),
        list(requested_maximum or [plant.electrolyser_kw] * n),
    )
    for profile in (lower, upper):
        if len(profile) != n or any(
            isinstance(v, bool)
            or not isinstance(v, (int, float))
            or not isfinite(v)
            or not 0 <= v <= plant.electrolyser_kw
            for v in profile
        ):
            raise ValueError("Requested-power bounds need one finite in-range value per interval")
    if any(a > b for a, b in zip(lower, upper, strict=True)):
        raise ValueError("Requested-power lower bound exceeds upper bound")
    bounds = {}
    if branch_requested_bounds is not None:
        if not commands or set(branch_requested_bounds) != {b.branch_id for b in branches}:
            raise ValueError("Conditional requested bounds require every delivered-capacity branch")
        for branch in branches:
            value = branch_requested_bounds[branch.branch_id]
            if set(value) != {"minimum", "maximum"}:
                raise ValueError("Conditional bounds require minimum and maximum profiles")
            if any(
                len(profile) != n
                or any(
                    isinstance(v, bool)
                    or not isinstance(v, (int, float))
                    or not isfinite(v)
                    or not 0 <= v <= plant.electrolyser_kw
                    for v in profile
                )
                for profile in value.values()
            ):
                raise ValueError(
                    "Conditional requested bounds need finite in-range hourly profiles"
                )
            lo = [max(a, b) for a, b in zip(lower, value["minimum"], strict=True)]
            hi = [min(a, b) for a, b in zip(upper, value["maximum"], strict=True)]
            if any(a > b for a, b in zip(lo, hi, strict=True)):
                raise ValueError("Conditional bounds cannot relax or contradict shared commitments")
            bounds[branch.branch_id] = dict(minimum=lo, maximum=hi)
        for i, branch in enumerate(branches):
            for other in branches[:i]:
                for t, history in enumerate(branch.information):
                    if history == other.information[t] and any(
                        bounds[branch.branch_id][key][t] != bounds[other.branch_id][key][t]
                        for key in ("minimum", "maximum")
                    ):
                        raise ValueError(
                            "Requested commitments cannot change before their observation"
                        )
    if objective not in ("methane", "economics"):
        raise ValueError("Outcome-tree MPC supports methane or economics")
    if (
        isinstance(risk_weight, bool)
        or not isinstance(risk_weight, (int, float))
        or not isfinite(risk_weight)
        or not 0 <= risk_weight <= 1
    ):
        raise ValueError("Risk weight must be between zero and one")
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not isfinite(seconds)
        or seconds <= 0
    ):
        raise ValueError("Solver time must be positive and finite")
    terminal = dict(terminal_minimum or {})
    if set(terminal) - {"battery_kwh", "h2_kg", "co2_kg", "temperature_c"} or any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) or v < 0
        for v in terminal.values()
    ):
        raise ValueError(
            "Terminal minima must name finite nonnegative plant inventories or temperature"
        )
    models = []
    charging_ports = []
    execution_forecasts = []
    for branch, forecast in zip(branches, forecasts, strict=True):
        hypothesized = (
            json.loads(branch.hypothesis_forecast_json)
            if branch.hypothesis_forecast_json
            else forecast
        )
        physical = {
            **hypothesized,
            **({"electrolyser_capacity_kw": list(branch.delivery_capacity_kw)} if commands else {}),
        }
        model = prepare_model(
            plant,
            state,
            physical,
            capacity,
            costs,
            objective,
            components=components,
            alternative=alternative if alternative != "electrolyser" or not commands else None,
            terminal_battery_value=terminal_battery_value,
        )
        if commands:
            limits = bounds.get(branch.branch_id, dict(minimum=lower, maximum=upper))
            _commands(
                model, plant, branch.delivery_capacity_kw, limits["minimum"], limits["maximum"]
            )
            if alternative == "electrolyser":
                model.upper[model.ids["requested_electrolyser_kw"][0]] = 0
            for t, isolated in enumerate(forecast.get("electrolyser_isolated", [False] * n)):
                if isolated:
                    model.upper[model.ids["requested_electrolyser_kw"][t]] = 0
        for key, value in terminal.items():
            model.add([(key, n - 1, 1)], lo=value)
        if charging_inputs is not None:
            charging_ports.append(attach(model, hypothesized, charging_inputs, objective))
        models.append(model)
        execution_forecasts.append(physical)
    merged = Model(n * len(models))
    merged.ids = {}
    offsets = np.cumsum([0] + [len(m.lower) for m in models[:-1]]).tolist()
    total = sum(len(m.lower) for m in models)
    constant, worst = total, total + 1
    merged.lower = np.concatenate([*[m.lower for m in models], [1], [-np.inf]])
    merged.upper = np.concatenate([*[m.upper for m in models], [1], [np.inf]])
    merged.integer = np.concatenate([*[m.integer for m in models], [0], [0]])
    scale = 1 if objective == "economics" else 0.001
    merged.objective = np.concatenate(
        [
            *[
                (1 - risk_weight) * b.probability * m.objective
                for b, m in zip(branches, models, strict=True)
            ],
            [(1 - risk_weight) * sum(b.probability * b.service_cost_eur * scale for b in branches)],
            [risk_weight],
        ]
    )
    merged.rows, merged.cols, merged.values, merged.lo, merged.hi = [], [], [], [], []
    for offset, model in zip(offsets, models, strict=True):
        row_offset = len(merged.lo)
        merged.rows.extend(row_offset + r for r in model.rows)
        merged.cols.extend(offset + c for c in model.cols)
        merged.values.extend(model.values)
        merged.lo.extend(model.lo)
        merged.hi.extend(model.hi)

    def row(terms, lower, upper):
        number = len(merged.lo)
        for column, value in terms:
            merged.rows.append(number)
            merged.cols.append(column)
            merged.values.append(value)
        merged.lo.append(lower)
        merged.hi.append(upper)

    equalities = 0
    for t in range(n):
        seen = {}
        for i, b in enumerate(branches):
            h = b.information[t]
            if h in seen:
                j = seen[h]
                shared_keys = list(ACTION_KEYS)
                if charging_inputs is not None:
                    shared_keys.extend(
                        k for power, _, on in charging_ports[i][0] for k in (power, on)
                    )
                for key in shared_keys:
                    key = (
                        "requested_electrolyser_kw"
                        if commands and key == "electrolyser_kw"
                        else key
                    )
                    row(
                        [
                            (offsets[i] + int(models[i].ids[key][t]), 1),
                            (offsets[j] + int(models[j].ids[key][t]), -1),
                        ],
                        0,
                        0,
                    )
                    equalities += 1
            else:
                seen[h] = i
    for offset, model, b in zip(offsets, models, branches, strict=True):
        row(
            [(offset + i, float(c)) for i, c in enumerate(model.objective) if c]
            + [(constant, b.service_cost_eur * scale), (worst, -1)],
            -np.inf,
            0,
        )
    x, info = merged.solve(seconds)
    result = dict(
        implementation_id=CHARGING_VERSION
        if charging_inputs is not None
        else CONDITIONAL_BOUNDS_VERSION
        if bounds
        else VERSION,
        status="unresolved",
        objective=objective,
        risk_weight=risk_weight,
        terminal_minimum=terminal,
        solver=info,
        shared_action_equalities=equalities,
        command_model="capacity-limited-request/1" if commands else None,
        requested_minimum=lower if commands else None,
        requested_maximum=upper if commands else None,
        **(dict(branch_requested_bounds=bounds) if bounds else {}),
        **(dict(charging_inputs=charging_inputs.to_dict()) if charging_inputs is not None else {}),
        terminal_battery_value_kg_per_kwh=terminal_battery_value,
        current_action=None,
        branches=[],
        hypothesis_inputs=any(b.hypothesis_forecast_json is not None for b in branches),
        expected=None,
        scope="Finite declared outcome histories. Decisions are shared until an observation distinguishes branches. Probabilities and capacity recoveries are assumptions; no simulator truth is queried. A missing incumbent is unresolved, and decomposition is not a global service-routing optimum.",
    )
    if x is None:
        return result
    outcomes = []
    try:
        for index, (offset, model, b, f, physical) in enumerate(
            zip(offsets, models, branches, forecasts, execution_forecasts, strict=True)
        ):
            known_forecast = f
            if b.hypothesis_forecast_json:
                f = json.loads(b.hypothesis_forecast_json)
            fleet_plan = None
            if charging_inputs is not None:
                fleet_plan = extract(
                    model,
                    x[offset : offset + len(model.lower)],
                    charging_inputs,
                    *charging_ports[index],
                )
                loads = [
                    f.get("service_kw", [0] * n)[t]
                    + sum(r["requested_kw"] for r in fleet_plan["charging"] if r["offset"] == t)
                    for t in range(n)
                ]
                physical = {**physical, "service_kw": loads}
                f = {**f, "service_kw": loads}
            actions = [
                {key: float(max(0, x[offset + model.ids[key][t]])) for key in ACTION_KEYS}
                for t in range(n)
            ]
            rows = trajectory(
                plant, state, actions, physical, components=components, capacity=capacity
            )
            requests = (
                [
                    dict(
                        a,
                        electrolyser_kw=float(
                            max(0, x[offset + model.ids["requested_electrolyser_kw"][t]])
                        ),
                    )
                    for t, a in enumerate(actions)
                ]
                if commands
                else actions
            )
            values = predicted(plant, costs, rows)
            outcomes.append(
                dict(
                    branch_id=b.branch_id,
                    probability=b.probability,
                    source=b.source,
                    information=list(b.information),
                    forecast=f,
                    **(
                        dict(original_information_forecast=known_forecast)
                        if b.hypothesis_forecast_json
                        else {}
                    ),
                    actions=actions,
                    requested_actions=requests,
                    delivery_capacity_kw=list(b.delivery_capacity_kw) if commands else None,
                    trajectory=rows,
                    predicted=values,
                    service_decision_eur=b.service_cost_eur,
                    **(dict(charging_plan=fleet_plan) if fleet_plan is not None else {}),
                    assumed_contribution_eur=values["assumed_contribution_eur"]
                    - b.service_cost_eur
                    - (
                        fleet_plan["incremental_service_decision_eur"]
                        if fleet_plan is not None
                        else 0
                    ),
                )
            )
    except (PhysicalAuditError, ValueError) as exc:
        result["solver"] = {
            **info,
            "status": "invalid-trajectory",
            "valid_incumbent": False,
            "audits": getattr(exc, "audits", []),
            "message": str(exc),
        }
        return result
    result.update(
        status="feasible",
        current_action=outcomes[0]["requested_actions"][0],
        branches=outcomes,
        expected=dict(
            methane_kg=sum(o["probability"] * o["predicted"]["methane_kg"] for o in outcomes),
            assumed_contribution_eur=sum(
                o["probability"] * o["assumed_contribution_eur"] for o in outcomes
            ),
        ),
        worst=dict(
            methane_kg=min(o["predicted"]["methane_kg"] for o in outcomes),
            assumed_contribution_eur=min(o["assumed_contribution_eur"] for o in outcomes),
        ),
    )
    return result
