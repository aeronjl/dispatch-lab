"""Bounded residual diagnosis. This module never receives a fault schedule."""

import hashlib
from dataclasses import asdict, dataclass

import numpy as np


@dataclass
class Diagnosis:
    capacity_kw: float
    status: str = "insufficient evidence"
    flow_isolated: bool = False
    tracking_count: int = 0
    flow_count: int = 0
    recovery_count: int = 0
    flow_recovery_count: int = 0
    active_incident: bool = False
    incidents: int = 0
    informative: bool = False
    tracking_residual: float = 0
    flow_residual: float = 0
    uncertainty: str = "Awaiting informative operation"


def observe(p, sensors, before, row, seed, hour, flow_bias=0, rng_policy="legacy/1"):
    """Independent channels. Same seeded noise draws for every strategy.

    Buffer metrology noise is expressed in interval-throughput units, not tank
    nameplate, to keep a low-flow residual observable; this is an explicit idealisation.
    Electrolysis electric power excludes separately metered start energy.
    Battery, CO2 and temperature are ideal state sensors in this bounded study.
    """
    if rng_policy == "legacy/1":
        z = np.random.default_rng(np.random.SeedSequence([seed, hour, 2107])).normal(size=3)
    elif rng_policy == "named-channels/1":
        z = [
            np.random.default_rng(
                np.random.SeedSequence(
                    [seed, hour, int.from_bytes(hashlib.sha256(name.encode()).digest()[:4], "big")]
                )
            ).normal()
            for name in ("electrical-power", "hydrogen-flow", "hydrogen-inventory")
        ]
    else:
        raise ValueError("Unknown random-stream policy.")
    flow = row["h2_produced_kg"]
    power = max(0, row["applied"]["electrolyser_kw"] * (1 + sensors.noise_fraction * z[0]))
    flow_meter = max(0, flow * (1 + flow_bias) * (1 + sensors.noise_fraction * z[1]))
    tank = row["state"]["h2_kg"] + flow * sensors.noise_fraction * z[2]
    # Mass balance uses successive readings, never the hidden true initial inventory.
    return {
        "power_kw": power,
        "hydrogen_flow_kg": flow_meter,
        "h2_inventory_kg": float(np.clip(tank, 0, p.h2_capacity_kg)),
        "h2_outflow_kg": row["h2_consumed_kg"],
        "battery_kwh": row["state"]["battery_kwh"],
        "co2_kg": row["state"]["co2_kg"],
        "temperature_c": row["state"]["temperature_c"],
        "electrolyser_on": row["state"]["electrolyser_on"],
        "reactor_on": row["state"]["reactor_on"],
        "commitment_hours": row["state"]["commitment_hours"],
    }


def update(
    p,
    sensors,
    diagnosis,
    prior_observation,
    observation,
    requested_power,
    probe=False,
    *,
    strict_probe=False,
    consecutive_probe_power=None,
):
    d = Diagnosis(**asdict(diagnosis))
    if strict_probe and (
        not probe
        or consecutive_probe_power is None
        or abs(consecutive_probe_power - requested_power) > 1e-5
    ):
        d.recovery_count = 0
    incident, event = False, None
    if not sensors.enabled:
        d.status, d.uncertainty = "diagnosis disabled", "Nameplate assumption; diagnosis ablation"
        return d, incident, event
    d.informative = requested_power >= p.min_kw - 1e-5
    if not d.informative:
        d.tracking_count = d.flow_count = d.recovery_count = d.flow_recovery_count = 0
        d.status = (
            "flow channel isolated"
            if d.flow_isolated
            else "derated; insufficient excitation"
            if d.capacity_kw < p.electrolyser_kw * 0.95
            else "insufficient evidence"
        )
        d.uncertainty = "No informative electrical request; health cannot be established"
        return d, incident, event
    threshold = max(sensors.discrepancy_fraction, 3 * sensors.noise_fraction)
    power = observation["power_kw"]
    expected_flow = power / p.specific_energy_kwh_per_kg
    balance_flow = (
        observation["h2_inventory_kg"]
        - prior_observation["h2_inventory_kg"]
        + observation["h2_outflow_kg"]
    )
    d.tracking_residual = (requested_power - power) / max(requested_power, 1)
    d.flow_residual = (observation["hydrogen_flow_kg"] - balance_flow) / max(
        abs(balance_flow), p.min_kw / p.specific_energy_kwh_per_kg
    )
    # Flow channel is suspect only when the independent balance agrees with electricity.
    balance_limit = threshold * max(expected_flow, p.min_kw / p.specific_energy_kwh_per_kg)
    track_limit, flow_limit = threshold, threshold
    if observation.get("measurement_uncertainty"):
        from methane.uncertainty import residual_budgets

        budgets = residual_budgets(prior_observation, observation, p.specific_energy_kwh_per_kg)

        def combined(sd, scale):
            # Retain the legacy relative-noise proxy, combine independent added
            # error in quadrature, then apply the non-statistical discrepancy floor.
            return max(
                sensors.discrepancy_fraction,
                3 * (sensors.noise_fraction**2 + (sd / scale) ** 2) ** 0.5,
            )

        track_limit = combined(budgets["tracking_kw"], max(requested_power, 1))
        flow_limit = combined(
            budgets["flow_kg"], max(abs(balance_flow), p.min_kw / p.specific_energy_kwh_per_kg)
        )
        scale = max(expected_flow, p.min_kw / p.specific_energy_kwh_per_kg)
        balance_limit = combined(budgets["balance_kg"], scale) * scale
    balance_agrees = abs(balance_flow - expected_flow) <= balance_limit
    track_bad, flow_bad = d.tracking_residual > track_limit, abs(d.flow_residual) > flow_limit
    if strict_probe and (track_bad or not balance_agrees):
        d.recovery_count = 0
    d.tracking_count = d.tracking_count + 1 if track_bad else 0
    d.flow_count = d.flow_count + 1 if flow_bad and balance_agrees else 0
    if not balance_agrees:
        d.status, d.uncertainty = (
            "ambiguous",
            "Electrical and inventory channels disagree; prior capacity estimate retained"
            if sensors.ambiguity_policy == "retain-capacity/1"
            else "Electrical and inventory channels disagree; conservative capacity retained",
        )
        # A separately versioned ablation: disagreement alone need not establish
        # a new capacity ceiling. Keep every other residual/probe rule unchanged.
        if sensors.ambiguity_policy == "reduce-capacity/1":
            d.capacity_kw = min(d.capacity_kw, max(0, power * (1 - threshold)))
    elif d.tracking_count >= sensors.confirmation_hours:
        newly_derated = d.capacity_kw >= p.electrolyser_kw * 0.95
        d.capacity_kw = min(d.capacity_kw, max(0, power * (1 - sensors.noise_fraction)))
        d.status, d.uncertainty = (
            "capacity loss",
            "Observed tracking shortfall; future recovery time unknown",
        )
        if newly_derated or not d.active_incident:
            event = "Capacity loss confirmed"
    elif d.flow_count >= sensors.confirmation_hours and (not strict_probe or not d.flow_isolated):
        if strict_probe:
            d.recovery_count = 0
        if not d.flow_isolated:
            event = "Hydrogen-flow sensor isolated"
        d.flow_isolated = True
        d.status, d.uncertainty = (
            "flow channel isolated",
            "Using independent inventory mass balance",
        )
    elif not track_bad and balance_agrees:
        d.uncertainty = "Tracking supported only at the tested load"
        d.status = (
            "flow channel isolated"
            if d.flow_isolated
            else "derated"
            if d.capacity_kw < p.electrolyser_kw * 0.95
            else "tracking consistent"
        )
        if probe:
            d.recovery_count += 1
            if d.recovery_count >= sensors.confirmation_hours:
                d.capacity_kw = min(p.electrolyser_kw, max(d.capacity_kw, requested_power))
                d.recovery_count = 0
                event = "Capacity probe confirmed"
                if d.capacity_kw >= p.electrolyser_kw * 0.999:
                    d.status, event = "tracking consistent", "Capacity recovered"
        if d.flow_isolated and not flow_bad:
            d.flow_recovery_count += 1
            if d.flow_recovery_count >= sensors.confirmation_hours:
                d.flow_isolated = False
                d.flow_recovery_count = 0
                event = "Hydrogen-flow sensor recovered"
    else:
        d.status, d.uncertainty = (
            "suspected anomaly",
            "Waiting for consecutive informative intervals",
        )
        d.recovery_count = 0
    if (
        event in ("Capacity loss confirmed", "Hydrogen-flow sensor isolated")
        and not d.active_incident
    ):
        d.active_incident = True
        d.incidents += 1
        incident = True
    if (
        not d.flow_isolated
        and d.capacity_kw >= p.electrolyser_kw * 0.999
        and not track_bad
        and not flow_bad
    ):
        d.active_incident = False
    return d, incident, event
