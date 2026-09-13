"""Hourly ideal chemistry and analytic lumped reactor heat balance.

Rounded molecular weights (kg/kmol): H2=2, CO2=44, CH4=16, H2O=18.
CO2 + 4 H2 -> CH4 + 2 H2O. Reaction heat: 165 MJ/kmol CH4.
No pressure dynamics, gas quality, venting or water recycling are modelled.
"""

from dataclasses import asdict, dataclass
from math import isfinite

from methane.audit import check, physical, require
from methane.battery import BatteryInput, BatteryState
from methane.components import assemble, record
from methane.config import Plant
from methane.electrolyser import Inputs as ElyInputs
from methane.electrolyser import State as ElyState
from methane.reactor import REACTION_KWH_PER_KG, ReactorState, ThermalInput, coefficients, step
from methane.storage import Inputs as GasInputs
from methane.storage import State as GasState

H2_PER_CH4 = 0.5
CO2_PER_CH4 = 2.75
WATER_PER_CH4 = 2.25
ACTION_KEYS = (
    "electrolyser_kw",
    "charge_kw",
    "discharge_kw",
    "heater_kw",
    "cooling_kw",
    "methane_kg",
)


@dataclass(frozen=True)
class State:
    battery_kwh: float
    h2_kg: float
    co2_kg: float
    temperature_c: float
    electrolyser_on: bool = False
    reactor_on: bool = False
    commitment_hours: int = 0

    @classmethod
    def initial(cls, p: Plant, ambient=20):
        return cls(p.battery_kwh * p.initial_soc, p.initial_h2_kg, p.initial_co2_kg, ambient)


def thermal_coefficients(p):
    return coefficients(p.thermal_capacity_kwh_per_k, p.heat_loss_kw_per_k)


def temperature_after(p, temperature, ambient, heater=0, methane=0, cooling=0):
    return step(p, ThermalInput(temperature, ambient, heater, methane, cooling)).state.temperature_c


def transition(
    p,
    state,
    action,
    pv,
    ambient,
    delivery,
    *,
    battery=None,
    components=None,
    capacity=None,
    requested=None,
    service_kw=0,
):
    """Account for an already feasible action; no hidden corrective dispatch."""
    inputs = {
        **asdict(state),
        **action,
        "pv_kw": pv,
        "ambient_c": ambient,
        "delivery_kg": delivery,
        "service_kw": service_kw,
    }
    invalid = [
        check("finite_input_" + key, "site", float("nan"), "input")
        for key, value in inputs.items()
        if not isfinite(value)
    ]
    require(
        invalid,
        {
            "state": asdict(state),
            "action": action,
            "pv": pv,
            "ambient": ambient,
            "delivery": delivery,
        },
    )
    ely, charge, discharge, heater, cooling, methane = [float(action[k]) for k in ACTION_KEYS]
    components = components or assemble(p, battery_override=battery)
    battery = components.battery
    battery_before = BatteryState(state.battery_kwh)
    battery_inputs = BatteryInput(charge, discharge, p.dt_hours)
    battery_result = battery.step(battery_before, battery_inputs)
    battery_energy = battery_result.state.energy_kwh
    ely_before = ElyState(state.electrolyser_on)
    ely_inputs = ElyInputs(ely, p.electrolyser_kw if capacity is None else capacity, p.dt_hours)
    ely_result = components.electrolyser.step(ely_before, ely_inputs)
    reactor_before = ReactorState(state.temperature_c, state.reactor_on, state.commitment_hours)
    reactor_inputs = ThermalInput(state.temperature_c, ambient, heater, methane, cooling)
    reactor_result = components.reactor.execute(
        reactor_before, reactor_inputs, (requested or action)["methane_kg"] >= p.methane_min_kgph
    )
    eflows, rflows = dict(ely_result.flows), dict(reactor_result.flows)
    h2_inputs = GasInputs(eflows["hydrogen_kg"], rflows["hydrogen_kg"])
    co2_inputs = GasInputs(delivery, rflows["co2_kg"])
    h2_before, co2_before = GasState(state.h2_kg), GasState(state.co2_kg)
    h2_result = components.hydrogen.step(h2_before, h2_inputs)
    co2_result = components.co2.step(co2_before, co2_inputs)
    accepted = dict(co2_result.flows)["accepted_kg"]
    h2_made, h2_used, co2_used = eflows["hydrogen_kg"], rflows["hydrogen_kg"], rflows["co2_kg"]
    startup = eflows["startup_kwh"]
    on, running = ely_result.state.on, reactor_result.state.running
    ely_start, reactor_start = eflows["start"], rflows["start"]
    temperature = reactor_result.state.temperature_c
    process_demand = eflows["electricity_kw"] + rflows["electricity_kw"]
    demand = process_demand + service_kw
    curtailed = pv + discharge - charge - demand
    commitment = reactor_result.state.commitment_hours
    next_state = State(
        battery_energy,
        h2_result.state.inventory_kg,
        co2_result.state.inventory_kg,
        temperature,
        on,
        running,
        commitment,
    )
    battery_loss = dict(battery_result.flows)["loss_kwh"]
    heat_loss = rflows["heat_loss_kwh"]
    row = {
        "applied": {k: float(action[k]) for k in ACTION_KEYS},
        "state": asdict(next_state),
        "pv_kw": pv,
        "ambient_c": ambient,
        "demand_kw": demand,
        "process_demand_kw": process_demand,
        "service_kw": service_kw,
        "curtailed_kwh": curtailed,
        "h2_produced_kg": h2_made,
        "h2_consumed_kg": h2_used,
        "co2_consumed_kg": co2_used,
        "co2_delivered_kg": accepted,
        "co2_rejected_kg": dict(co2_result.flows)["rejected_kg"],
        "water_produced_kg": rflows["water_kg"],
        "electrolysis_stoichiometric_water_kg": eflows["water_kg"],
        "electrolyser_start": int(ely_start),
        "reactor_start": int(reactor_start),
        "startup_kwh": startup,
        "battery_loss_kwh": battery_loss,
        "battery_record": battery.record(battery_before, battery_inputs, battery_result),
        "component_records": {
            "electrolyser": record(components.electrolyser, ely_before, ely_inputs, ely_result),
            "hydrogen": record(components.hydrogen, h2_before, h2_inputs, h2_result),
            "co2": record(components.co2, co2_before, co2_inputs, co2_result),
            "reactor": record(components.reactor, reactor_before, reactor_inputs, reactor_result),
        },
        "reaction_heat_kwh": methane * REACTION_KWH_PER_KG,
        "heat_loss_kwh": heat_loss,
        "thermal_residual_kwh": p.thermal_capacity_kwh_per_k * (temperature - state.temperature_c)
        - (heater + methane * REACTION_KWH_PER_KG - cooling - heat_loss),
        "electrical_residual_kwh": pv
        - demand
        - curtailed
        - battery_loss
        - (battery_energy - state.battery_kwh),
        "h2_residual_kg": next_state.h2_kg - state.h2_kg - h2_made + h2_used,
        "co2_residual_kg": next_state.co2_kg - state.co2_kg - accepted + co2_used,
        "reaction_mass_residual_kg": h2_used + co2_used - methane - methane * WATER_PER_CH4,
    }
    row["audits"] = physical(p, state, row)
    require(row["audits"], {"before": asdict(state), "row": row})
    return next_state, row
