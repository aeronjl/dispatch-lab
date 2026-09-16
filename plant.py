"""Inspectable, hourly DC-bus model. All parameters are illustrative assumptions."""

from dataclasses import dataclass
from math import isfinite, sqrt


@dataclass(frozen=True)
class Plant:
    solar_kw: float = 1000
    battery_kwh: float = 800
    battery_c_rate: float = 0.5
    electrolyser_kw: float = 450
    min_load_fraction: float = 0.3
    start_energy_kwh: float = 40
    specific_energy_kwh_per_kg: float = 55
    roundtrip_efficiency: float = 0.9
    initial_soc: float = 0.0
    dt_hours: float = 1.0

    def __post_init__(self):
        for key in Plant.__dataclass_fields__:
            value = getattr(self, key)
            if not isfinite(value):
                raise ValueError("Plant parameters must be finite.")
        if min(self.solar_kw, self.battery_kwh, self.start_energy_kwh) < 0:
            raise ValueError("Capacities and start energy must be nonnegative.")
        if min(self.electrolyser_kw, self.battery_c_rate, self.dt_hours) <= 0:
            raise ValueError("Electrolyser size, C-rate and timestep must be positive.")
        if self.specific_energy_kwh_per_kg <= 0:
            raise ValueError("Specific energy must be positive.")
        if not 0 < self.roundtrip_efficiency <= 1:
            raise ValueError("Round-trip efficiency must be in (0, 1].")
        if not 0 < self.min_load_fraction <= 1 or not 0 <= self.initial_soc <= 1:
            raise ValueError("Minimum load must be in (0, 1]; initial SOC must be in [0, 1].")

    @property
    def eta(self):
        return sqrt(self.roundtrip_efficiency)

    @property
    def battery_kw(self):
        return self.battery_kwh * self.battery_c_rate

    @property
    def min_kw(self):
        return self.electrolyser_kw * self.min_load_fraction


@dataclass(frozen=True)
class State:
    energy_kwh: float
    on: bool = False


def feasible_production(plant: Plant, state: State, pv_kw: float, capacity_kw: float):
    """Maximum productive load feasible now, including the energy needed to start."""
    discharge = min(plant.battery_kw, state.energy_kwh * plant.eta / plant.dt_hours)
    startup_kw = 0 if state.on else plant.start_energy_kwh / plant.dt_hours
    maximum = min(capacity_kw, max(0, pv_kw + discharge - startup_kw))
    return 0.0 if maximum < plant.min_kw - 1e-7 else maximum


def step(plant: Plant, state: State, request_kw: float, pv_kw: float, capacity_kw: float):
    """Apply a production request; actual conditions enforce all physical limits.

    Start energy is a lumped electrical overhead within the hour, with no warm-up
    delay. Productive power excludes this overhead. Storage always absorbs unused
    PV if it has room. No grid, power export, idle load, thermal or gas dynamics.
    """
    if not all(isfinite(x) for x in (request_kw, pv_kw, capacity_kw, state.energy_kwh)):
        raise ValueError("Inputs must be finite.")
    if pv_kw < 0 or not 0 <= capacity_kw <= plant.electrolyser_kw + 1e-7:
        raise ValueError("Invalid available power or electrolyser capacity.")
    if not -1e-7 <= state.energy_kwh <= plant.battery_kwh + 1e-7:
        raise ValueError("Stored energy is out of bounds.")
    limit = feasible_production(plant, state, pv_kw, capacity_kw)
    productive_kw = max(0.0, min(request_kw, limit))
    if productive_kw < plant.min_kw - 1e-7 or productive_kw < 1e-7:
        productive_kw = 0.0
    on = productive_kw > 0
    started = on and not state.on
    start_kwh = plant.start_energy_kwh if started else 0.0
    demand_kw = productive_kw + start_kwh / plant.dt_hours
    discharge_kw = max(0.0, demand_kw - pv_kw)
    charge_kw = min(
        max(0.0, pv_kw - demand_kw),
        plant.battery_kw,
        max(0.0, plant.battery_kwh - state.energy_kwh) / (plant.eta * plant.dt_hours),
    )
    energy_change = (charge_kw * plant.eta - discharge_kw / plant.eta) * plant.dt_hours
    next_energy = min(plant.battery_kwh, max(0.0, state.energy_kwh + energy_change))
    curtailed_kw = max(0.0, pv_kw + discharge_kw - demand_kw - charge_kw)
    loss_kwh = ((1 - plant.eta) * charge_kw + (1 / plant.eta - 1) * discharge_kw) * plant.dt_hours
    productive_kwh = productive_kw * plant.dt_hours
    residual = pv_kw * plant.dt_hours - (
        productive_kwh
        + start_kwh
        + curtailed_kw * plant.dt_hours
        + loss_kwh
        + next_energy
        - state.energy_kwh
    )
    measurements = {
        "pv_kw": pv_kw,
        "capacity_kw": capacity_kw,
        "requested_kw": request_kw,
        "productive_kw": productive_kw,
        "electrical_demand_kw": demand_kw,
        "charge_kw": charge_kw,
        "discharge_kw": discharge_kw,
        "battery_kwh": next_energy,
        "curtailed_kw": curtailed_kw,
        "h2_kg": productive_kwh / plant.specific_energy_kwh_per_kg,
        "started": int(started),
        "on": int(on),
        "startup_kwh": start_kwh,
        "battery_loss_kwh": loss_kwh,
        "balance_residual_kwh": residual,
    }
    return State(next_energy, on), measurements
