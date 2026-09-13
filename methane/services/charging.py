"""Joint plant dispatch and dock charging from recorded service commitments.

Charging is a requested hourly bus load. Credits arrive at the interval end
only in this conditional prediction; execution posts actual dock receipts.
There is no hidden hardware-fault state or automatic future repair here.
"""

import copy
from dataclasses import asdict, dataclass
from math import isfinite

import numpy as np

from methane.audit import PhysicalAuditError
from methane.components import assemble
from methane.dispatch import ACTION_KEYS, predicted, prepare_model, trajectory
from methane.services.contracts import identifier, nonnegative
from methane.services.scenario_planning import Branch, _validate

VERSION = "service-charge-process-mpc/1"


@dataclass(frozen=True)
class Battery:
    name: str
    initial_kwh: float
    capacity_kwh: float
    efficiency: float
    available: tuple[bool, ...]
    use_kwh: tuple[float, ...]
    reserve_kwh: tuple[float, ...]
    target_kwh: float
    required_at_offset: int

    def __post_init__(self):
        identifier(self.name, "service battery")
        for key in ("initial_kwh", "capacity_kwh", "efficiency", "target_kwh"):
            nonnegative(getattr(self, key), key)
        if self.initial_kwh > self.capacity_kwh or self.target_kwh > self.capacity_kwh:
            raise ValueError("Service energy and targets must fit their battery")
        if not 0 < self.efficiency <= 1:
            raise ValueError("Charging efficiency must be greater than zero and at most one")
        n = len(self.available)
        if not 1 <= n <= 168 or any(type(v) is not bool for v in self.available):
            raise ValueError("Charging availability needs 1–168 Boolean hourly entries")
        for profile in (self.available, self.use_kwh, self.reserve_kwh):
            if type(profile) is not tuple or len(profile) != n:
                raise ValueError(
                    "Service battery profiles must be immutable and have equal lengths"
                )
        for value in (*self.use_kwh, *self.reserve_kwh):
            nonnegative(value, "service energy obligation")
        if type(self.required_at_offset) is not int or not 1 <= self.required_at_offset <= n:
            raise ValueError("A charging target needs a decision boundary within the horizon")


def _variables(model, key, upper, integer=0):
    n, start = model.n, len(model.lower)
    model.ids[key] = np.arange(start, start + n)
    model.lower = np.append(model.lower, np.zeros(n))
    model.upper = np.append(model.upper, np.broadcast_to(upper, n))
    model.integer = np.append(model.integer, np.full(n, integer))
    model.objective = np.append(model.objective, np.zeros(n))


def _cost(model, on_keys, costs, scale):
    """Choose the exact precomputed usage/parts cost for the active dock hours."""
    # This small one-hot set preserves nonlinear allowance pooling without
    # replacing it by a rate which could charge consumed parts a second time.
    start = len(model.lower)
    ids = np.arange(start, start + model.n + 1)
    model.lower = np.append(model.lower, np.zeros(len(ids)))
    model.upper = np.append(model.upper, np.ones(len(ids)))
    model.integer = np.append(model.integer, np.ones(len(ids)))
    model.objective = np.append(model.objective, np.array(costs) * scale)
    row = len(model.lo)
    model.rows.extend([row] * len(ids))
    model.cols.extend(ids)
    model.values.extend([1] * len(ids))
    model.lo.append(1)
    model.hi.append(1)
    model.add([(key, t, 1) for key in on_keys for t in range(model.n)], 0, 0)
    row = len(model.lo) - 1
    model.rows.extend([row] * len(ids))
    model.cols.extend(ids)
    model.values.extend(-np.arange(len(ids)))


@dataclass(frozen=True)
class Inputs:
    """Frozen charging obligations shared by deterministic and scenario planners."""

    batteries: tuple[Battery, ...]
    dock_available_kw: tuple[float, ...]
    incremental_cost_by_active_hours: tuple[float, ...]

    def __post_init__(self):
        if any(
            type(v) is not tuple
            for v in (self.batteries, self.dock_available_kw, self.incremental_cost_by_active_hours)
        ) or any(not isinstance(b, Battery) for b in self.batteries):
            raise ValueError("Charging inputs require immutable battery, dock and cost profiles")
        self.validate(len(self.dock_available_kw))

    def validate(self, n):
        batteries, dock, charges = (
            self.batteries,
            self.dock_available_kw,
            self.incremental_cost_by_active_hours,
        )
        if not 1 <= len(batteries) <= 8 or len({b.name for b in batteries}) != len(batteries):
            raise ValueError("Supply 1–8 distinct service batteries")
        if any(len(b.available) != n for b in batteries) or len(dock) != n:
            raise ValueError("Dock and robot profiles must match the original forecast")
        for value in (*dock, *charges):
            nonnegative(value, "charging limit or cost")
        if (
            len(charges) != n + 1
            or charges[0] != 0
            or any(a > b for a, b in zip(charges, charges[1:], strict=False))
        ):
            raise ValueError(
                "Charge costs need a nondecreasing zero-based table through the horizon"
            )

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        return cls(
            tuple(
                Battery(
                    **{**b, **{k: tuple(b[k]) for k in ("available", "use_kwh", "reserve_kwh")}}
                )
                for b in value["batteries"]
            ),
            tuple(value["dock_available_kw"]),
            tuple(value["incremental_cost_by_active_hours"]),
        )


def attach(model, forecast, inputs, objective):
    """Attach the same bus, beginning-inventory, dock and cost constraints."""
    inputs.validate(model.n)
    n = model.n
    batteries, dock, charges = (
        inputs.batteries,
        inputs.dock_available_kw,
        inputs.incremental_cost_by_active_hours,
    )
    fixed = forecast.get("service_kw", [0] * n)
    limits = [
        min(d, max(0, pv - service))
        for d, pv, service in zip(dock, forecast["pv_kw"], fixed, strict=True)
    ]
    keys = []
    for index, battery in enumerate(batteries):
        power, energy, on = [f"dock_{index}_{term}" for term in ("kw", "kwh", "on")]
        keys.append((power, energy, on))
        _variables(
            model,
            power,
            [v if free else 0 for v, free in zip(limits, battery.available, strict=True)],
        )
        _variables(model, energy, battery.capacity_kwh)
        _variables(model, on, [int(v) for v in battery.available], 1)
        model.lower[model.ids[energy][battery.required_at_offset - 1]] = battery.target_kwh
        for t in range(n):
            model.add([(power, t, 1), (on, t, -limits[t])], hi=0)
            terms = [(energy, t, 1), (power, t, -battery.efficiency)]
            rhs = -battery.use_kwh[t]
            if t:
                terms.append((energy, t - 1, -1))
                model.add([(energy, t - 1, 1)], lo=battery.use_kwh[t] + battery.reserve_kwh[t])
            else:
                rhs += battery.initial_kwh
                # A charge delivered at the end cannot fund this interval's departure.
                model.add([], lo=battery.use_kwh[t] + battery.reserve_kwh[t] - battery.initial_kwh)
            model.add(terms, rhs, rhs)
            model.rows.append(model.bus_rows[t])
            model.cols.append(model.ids[power][t])
            model.values.append(1)
        model.objective[model.ids[power]] += 1e-5
        model.objective[model.ids[on]] += 1e-5
    for t in range(n):
        model.add([(on, t, 1) for _, _, on in keys], hi=1)
    _cost(model, [on for _, _, on in keys], charges, 1 if objective == "economics" else 0.001)
    return keys, limits


def extract(model, x, inputs, keys, limits):
    """Independently reconcile the proposed fleet trajectory before acceptance."""
    n, batteries, charges = model.n, inputs.batteries, inputs.incremental_cost_by_active_hours
    fleet, adjustments = [], []
    for battery, (power, _, on) in zip(batteries, keys, strict=True):
        value = battery.initial_kwh
        for t in range(n):
            grant = float(max(0, x[model.ids[power][t]]))
            if x[model.ids[on][t]] <= 0.5 and 0 < grant <= 1e-5:
                adjustments.append(
                    dict(
                        robot=battery.name,
                        offset=t,
                        solver_kw=grant,
                        applied_plan_kw=0,
                        reason="Numerical residue in an off slot",
                    )
                )
                grant = 0.0
            after = value - battery.use_kwh[t] + grant * battery.efficiency
            good = (
                value >= battery.use_kwh[t] + battery.reserve_kwh[t] - 1e-5
                and -1e-5 <= after <= battery.capacity_kwh + 1e-5
                and (t + 1 != battery.required_at_offset or after >= battery.target_kwh - 1e-5)
                and grant <= (limits[t] if battery.available[t] else 0) + 1e-5
                and (not grant or x[model.ids[on][t]] > 0.5)
            )
            fleet.append(
                dict(
                    robot=battery.name,
                    offset=t,
                    before_kwh=value,
                    requested_kw=grant,
                    use_kwh=battery.use_kwh[t],
                    charging_loss_kwh=grant * (1 - battery.efficiency),
                    after_kwh=after,
                    passed=bool(good),
                )
            )
            value = after
    shared = all(
        sum(r["requested_kw"] for r in fleet if r["offset"] == t) <= limits[t] + 1e-5
        and sum(x[model.ids[on][t]] > 0.5 for _, _, on in keys) <= 1
        for t in range(n)
    )
    if not shared or not all(r["passed"] for r in fleet):
        raise ValueError("invalid-robot-energy")
    # A degenerate incumbent may reserve a zero-power slot. Releasing that slot
    # cannot increase a nondecreasing cost table. Keep both counts so its solver
    # objective is not misrepresented as the price of the replayed trajectory.
    active = sum(any(r["requested_kw"] > 0 for r in fleet if r["offset"] == t) for t in range(n))
    reserved = sum(bool(x[model.ids[on][t]] > 0.5) for _, _, on in keys for t in range(n))
    if active > reserved:
        raise ValueError("invalid-dock-occupancy")
    return dict(
        charging=fleet,
        numerical_adjustments=adjustments,
        active_dock_hours=active,
        solver_reserved_dock_hours=reserved,
        released_zero_power_hours=reserved - active,
        solver_service_cost_eur=charges[reserved],
        incremental_service_decision_eur=charges[active],
    )


def solve(
    plant,
    state,
    forecast,
    capacity_kw,
    costs,
    batteries,
    dock_available_kw,
    incremental_cost_by_active_hours,
    *,
    objective="methane",
    seconds=0.5,
    components=None,
    alternative=None,
    terminal_battery_value=0,
):
    """Optimise plant actions and one connected robot's charging each hour.

    The supplied dock profile already excludes occupied/failed hardware and
    fixed-service peaks. It is additionally bounded by forecast solar power:
    an active dock is not silently allowed to use the plant battery. Accepted
    robot consumption requires beginning-of-interval inventory, while charging
    is credited at the end. A fixed target deadline must not roll forward each
    time the caller replans.
    """
    branch = Branch.create(
        "forecast",
        1,
        forecast,
        ("saved-forecast",) * len(forecast["pv_kw"]),
        source="assumption:conditional-charge-continuation/1",
    )
    _validate(plant, [branch], capacity_kw)
    n = len(forecast["pv_kw"])
    batteries, dock, charges = (
        tuple(batteries),
        tuple(dock_available_kw),
        tuple(incremental_cost_by_active_hours),
    )
    inputs = Inputs(batteries, dock, charges)
    inputs.validate(n)
    if objective not in ("methane", "economics"):
        raise ValueError("Joint charging requires an explicit methane or economics objective")
    if alternative not in (None, "battery", "electrolyser", "reactor"):
        raise ValueError("Unknown current-interval charging comparison alternative")
    components = components or assemble(plant)
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not isfinite(seconds)
        or seconds <= 0
    ):
        raise ValueError("The charging solver limit must be positive and finite")
    model = prepare_model(
        plant,
        state,
        forecast,
        capacity_kw,
        costs,
        objective,
        seconds,
        alternative=alternative,
        components=components,
        terminal_battery_value=terminal_battery_value,
    )
    keys, limits = attach(model, forecast, inputs, objective)
    x, info = model.solve(seconds)
    result = dict(
        implementation_id=VERSION,
        status="unresolved",
        solver=info,
        plan=None,
        inputs=dict(
            plant=asdict(plant),
            state=asdict(state),
            capacity_estimate_kw=capacity_kw,
            process_costs=asdict(costs),
            component_implementations=components.identities(),
            alternative=alternative,
            batteries=[asdict(b) for b in batteries],
            dock_available_kw=list(dock),
            incremental_cost_by_active_hours=list(charges),
            forecast=copy.deepcopy(forecast),
            objective=objective,
            terminal_battery_value=terminal_battery_value,
            charge_numerical_tie_break=1e-5,
        ),
        scope="Conditional saved-forecast charging and plant dispatch. Beginning inventory funds robot use; charge arrives at interval end. One robot occupies the dock each hour. Fixed deadlines and usage/parts cost table are explicit inputs. Actual hardware, weather and receipts must still be rechecked; no repair or future observation is inferred.",
    )
    if x is None:
        return result
    actions = [{key: float(max(0, x[model.ids[key][t]])) for key in ACTION_KEYS} for t in range(n)]
    try:
        fleet_plan = extract(model, x, inputs, keys, limits)
    except ValueError as exc:
        result["solver"] = {**info, "status": str(exc), "valid_incumbent": False}
        return result
    fleet = fleet_plan["charging"]
    coupled = copy.deepcopy(forecast)
    fixed = forecast.get("service_kw", [0] * n)
    coupled["service_kw"] = [
        fixed[t] + sum(r["requested_kw"] for r in fleet if r["offset"] == t) for t in range(n)
    ]
    try:
        rows = trajectory(
            plant, state, actions, coupled, components=components, capacity=capacity_kw
        )
    except PhysicalAuditError as exc:
        result["solver"] = {
            **info,
            "status": "invalid-trajectory",
            "valid_incumbent": False,
            "message": str(exc),
        }
        return result
    active = fleet_plan["active_dock_hours"]
    process_prediction = predicted(plant, costs, rows)
    result.update(
        status="feasible",
        plan=dict(
            actions=actions,
            trajectory=rows,
            predicted=process_prediction,
            comparison_economics=dict(
                process_decision_eur=process_prediction["variable_and_wear_eur"],
                additional_dock_decision_eur=charges[active],
                assumed_contribution_after_additional_dock_eur=(
                    process_prediction["assumed_contribution_eur"] - charges[active]
                ),
                scope="Process prediction less incremental dock cost. Unchanged committed service costs and sunk prefix costs are excluded from this comparison; this is not an allocated whole-run cost report.",
            ),
            solver=info,
            forecast=coupled,
            **fleet_plan,
        ),
    )
    return result
