"""Controllers see measured capacity and a forecast, never the future realised weather."""

import time
from dataclasses import dataclass

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import lil_matrix

from plant import Plant, State, feasible_production


@dataclass(frozen=True)
class Decision:
    productive_kw: float
    status: str
    seconds: float = 0
    gap: float = 0


def greedy(plant: Plant, state: State, measured_pv_kw: float, measured_capacity_kw: float):
    """Use PV first, then battery, to produce as much as is feasible in this hour."""
    return Decision(feasible_production(plant, state, measured_pv_kw, measured_capacity_kw), "rule")


def plan(plant: Plant, state: State, forecast_kw: np.ndarray, measured_capacity_kw: float):
    """Receding-horizon MILP; only the first production decision is executed.

    Maximise forecast productive energy, with a tiny battery-throughput tie-break.
    Hourly variables: productive power, charge, discharge, energy after step,
    on/off, start, charge/discharge direction. Binary direction prohibits
    simultaneous charging and discharging. Future capacity persists from the
    current measurement; the controller has no access to the fault schedule.

    Terminal stored energy has zero value. This simple boundary assumption is
    exposed in the UI; final inventory is reported for both controllers.
    """
    started = time.perf_counter()
    n = len(forecast_kw)
    if n == 0 or not np.all(np.isfinite(forecast_kw)) or np.any(forecast_kw < 0):
        raise ValueError("The forecast must contain finite nonnegative power values.")
    p, charge, discharge, energy, on, start, direction = [
        np.arange(i * n, (i + 1) * n) for i in range(7)
    ]
    objective = np.zeros(7 * n)
    objective[p] = -plant.dt_hours
    objective[charge] = objective[discharge] = 1e-5 * plant.dt_hours
    upper = np.full(7 * n, np.inf)
    upper[p] = measured_capacity_kw
    upper[charge] = upper[discharge] = plant.battery_kw
    upper[energy] = plant.battery_kwh
    upper[on] = upper[start] = upper[direction] = 1
    if measured_capacity_kw < plant.min_kw - 1e-7 or measured_capacity_kw == 0:
        upper[on] = 0
    integer = np.zeros(7 * n)
    integer[on] = integer[start] = integer[direction] = 1
    # Nine constraints per interval: bus, storage, load bounds, exact start,
    # and mutually exclusive battery directions.
    matrix = lil_matrix((9 * n, 7 * n))
    lower = np.full(9 * n, -np.inf)
    bound = np.full(9 * n, np.inf)
    dt = plant.dt_hours
    for t in range(n):
        r = 9 * t
        matrix[r, [p[t], charge[t], discharge[t], start[t]]] = [
            1,
            1,
            -1,
            plant.start_energy_kwh / dt,
        ]
        bound[r] = forecast_kw[t]  # unused solar may be curtailed
        matrix[r + 1, [energy[t], charge[t], discharge[t]]] = [1, -plant.eta * dt, dt / plant.eta]
        if t:
            matrix[r + 1, energy[t - 1]] = -1
        lower[r + 1] = bound[r + 1] = state.energy_kwh if t == 0 else 0
        matrix[r + 2, [p[t], on[t]]] = [1, -measured_capacity_kw]
        bound[r + 2] = 0
        matrix[r + 3, [p[t], on[t]]] = [-1, plant.min_kw]
        bound[r + 3] = 0
        matrix[r + 4, [on[t], start[t]]] = [1, -1]
        if t:
            matrix[r + 4, on[t - 1]] = -1
        bound[r + 4] = int(state.on) if t == 0 else 0
        matrix[r + 5, [start[t], on[t]]] = [1, -1]
        bound[r + 5] = 0
        matrix[r + 6, start[t]] = 1
        if t:
            matrix[r + 6, on[t - 1]] = 1
        bound[r + 6] = 1 - int(state.on) if t == 0 else 1
        matrix[r + 7, [charge[t], direction[t]]] = [1, -plant.battery_kw]
        bound[r + 7] = 0
        matrix[r + 8, [discharge[t], direction[t]]] = [1, plant.battery_kw]
        bound[r + 8] = plant.battery_kw
    matrix = matrix.tocsc()
    result = milp(
        objective,
        integrality=integer,
        bounds=Bounds(np.zeros(7 * n), upper),
        constraints=LinearConstraint(matrix, lower, bound),
        options={"time_limit": 0.5, "mip_rel_gap": 0.001},
    )
    elapsed = time.perf_counter() - started
    # A time-limited incumbent is usable only if it is actually feasible.
    x = result.x
    valid = x is not None and np.all(np.isfinite(x))
    if valid:
        ax = matrix @ x
        valid = (
            np.all(x >= -1e-5)
            and np.all(x <= upper + 1e-5)
            and np.all(ax >= lower - 1e-5)
            and np.all(ax <= bound + 1e-5)
            and np.all(np.abs(x[integer == 1] - np.round(x[integer == 1])) < 1e-5)
        )
    if valid and result.status in (0, 1):
        return Decision(
            float(max(0, x[p[0]])),
            "solved" if result.status == 0 else "time-limited",
            elapsed,
            float(result.mip_gap or 0),
        )
    fallback = greedy(plant, state, float(forecast_kw[0]), measured_capacity_kw)
    return Decision(fallback.productive_kw, "fallback", elapsed)
