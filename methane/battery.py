"""Pure battery contracts and replaceable kernels; no plant, solver, UI or I/O imports.

Power ports are measured on the DC bus. Execution never repairs an infeasible
action. Planning exports linear rows in local port names, leaving composition
and optimisation to the plant. Both kernels implement the same physical model.
"""

from dataclasses import asdict, dataclass
from math import isfinite, sqrt
from typing import Protocol

from methane.audit import check, require
from methane.contracts import BATTERY, ComponentResult
from methane.ports import LinearRow, PlanningBlock, Port


@dataclass(frozen=True)
class BatteryParameters:
    capacity_kwh: float = 800
    c_rate: float = 0.5
    roundtrip_efficiency: float = 0.9

    def __post_init__(self):
        for name, value in zip(
            ("battery_kwh", "battery_c_rate", "roundtrip_efficiency"),
            (self.capacity_kwh, self.c_rate, self.roundtrip_efficiency),
            strict=True,
        ):
            next(p for p in BATTERY.parameters if p.key == name).validate(value)

    @property
    def eta(self):
        return sqrt(self.roundtrip_efficiency)

    @property
    def power_kw(self):
        return self.capacity_kwh * self.c_rate


@dataclass(frozen=True)
class BatteryState:
    energy_kwh: float


@dataclass(frozen=True)
class BatteryInput:
    charge_kw: float = 0
    discharge_kw: float = 0
    duration_hours: float = 1


class BatteryKernel(Protocol):
    implementation_id: str
    description: str

    def execute(
        self, p: BatteryParameters, state: BatteryState, inputs: BatteryInput
    ) -> ComponentResult: ...

    def planning(
        self, p: BatteryParameters, state: BatteryState, durations: tuple[float, ...]
    ) -> PlanningBlock: ...


def _block(p, state, durations, energy_coefficient, charge_coefficient, discharge_coefficient):
    rows = []
    for t, duration in enumerate(durations):
        terms = [
            ("energy", t, energy_coefficient),
            ("charge", t, charge_coefficient * duration),
            ("discharge", t, discharge_coefficient * duration),
        ]
        if t:
            terms.append(("energy", t - 1, -energy_coefficient))
        rhs = state.energy_kwh * energy_coefficient if t == 0 else 0
        rows.extend(
            (
                LinearRow("energy_balance", tuple(terms), rhs, rhs),
                LinearRow(
                    "charge_direction",
                    (("charge", t, 1), ("charging", t, -p.power_kw)),
                    -float("inf"),
                    0,
                ),
                LinearRow(
                    "discharge_direction",
                    (("discharge", t, 1), ("charging", t, p.power_kw)),
                    -float("inf"),
                    p.power_kw,
                ),
            )
        )
    return PlanningBlock(
        (
            ("energy", 0, p.capacity_kwh, False),
            ("charge", 0, p.power_kw, False),
            ("discharge", 0, p.power_kw, False),
            ("charging", 0, 1, True),
        ),
        tuple(rows),
        (
            Port("energy", "kWh", "Ending stored energy"),
            Port("charge", "kW", "Mean bus charge"),
            Port("discharge", "kW", "Mean bus discharge"),
            Port("charging", "boolean", "Charge direction"),
        ),
    )


@dataclass(frozen=True)
class AffineBattery:
    implementation_id: str = "affine/1"
    description: str = "Direct constant-efficiency state equation; unscaled energy-balance rows"

    def execute(self, p, state, inputs):
        c, d, dt = inputs.charge_kw, inputs.discharge_kw, inputs.duration_hours
        end = state.energy_kwh + p.eta * c * dt - d * dt / p.eta
        charge_loss = (1 - p.eta) * c * dt
        discharge_loss = (1 / p.eta - 1) * d * dt
        return _result(end, charge_loss, discharge_loss)

    def planning(self, p, state, durations):
        return _block(p, state, durations, 1, -p.eta, 1 / p.eta)


@dataclass(frozen=True)
class LossLedgerBattery:
    implementation_id: str = "loss-ledger/1"
    description: str = "Bus/cell energy ledger; energy-balance rows scaled by one-way efficiency"

    def execute(self, p, state, inputs):
        incoming = inputs.charge_kw * inputs.duration_hours
        outgoing = inputs.discharge_kw * inputs.duration_hours
        retained = incoming * sqrt(p.roundtrip_efficiency)
        withdrawn = outgoing / sqrt(p.roundtrip_efficiency)
        charge_loss, discharge_loss = incoming - retained, withdrawn - outgoing
        end = state.energy_kwh + (incoming - outgoing) - (charge_loss + discharge_loss)
        return _result(end, charge_loss, discharge_loss)

    def planning(self, p, state, durations):
        return _block(p, state, durations, p.eta, -p.eta * p.eta, 1)


def _result(end, charge_loss, discharge_loss):
    return ComponentResult(
        BatteryState(end),
        (
            ("charge_loss_kwh", charge_loss),
            ("discharge_loss_kwh", discharge_loss),
            ("loss_kwh", charge_loss + discharge_loss),
        ),
    )


IMPLEMENTATIONS = {k.implementation_id: k for k in (AffineBattery(), LossLedgerBattery())}


@dataclass(frozen=True)
class Battery:
    parameters: BatteryParameters
    kernel: BatteryKernel = AffineBattery()

    def identity(self):
        return {
            "model_id": BATTERY.model_id,
            "model_version": BATTERY.version,
            "implementation_id": self.kernel.implementation_id,
        }

    def _validate(self, state, inputs):
        values = {**asdict(state), **asdict(inputs)}
        invalid = [
            check("finite_battery_" + k, "battery", float("nan"), "input")
            for k, v in values.items()
            if not isfinite(v)
        ]
        require(invalid, values)
        if inputs.duration_hours <= 0:
            raise ValueError("Battery duration must be positive.")

    def step(self, state: BatteryState, inputs: BatteryInput):
        self._validate(state, inputs)
        p = self.parameters
        result = self.kernel.execute(p, state, inputs)
        flows = dict(result.flows)
        audits = []
        for key, value, maximum, unit in (
            ("battery_initial_bounds", state.energy_kwh, p.capacity_kwh, "kWh"),
            ("battery_bounds", result.state.energy_kwh, p.capacity_kwh, "kWh"),
            ("battery_charge_bounds", inputs.charge_kw, p.power_kw, "kW"),
            ("battery_discharge_bounds", inputs.discharge_kw, p.power_kw, "kW"),
        ):
            audits.append(check(key, "battery", max(-value, value - maximum, 0), unit, maximum))
        audits.extend(
            (
                check(
                    "battery_exclusive",
                    "battery",
                    min(inputs.charge_kw, inputs.discharge_kw),
                    "kW",
                    p.power_kw,
                ),
                check(
                    "battery_energy_balance",
                    "battery",
                    result.state.energy_kwh
                    - state.energy_kwh
                    - (inputs.charge_kw - inputs.discharge_kw) * inputs.duration_hours
                    + flows["loss_kwh"],
                    "kWh",
                    p.capacity_kwh,
                ),
                check("battery_loss_nonnegative", "battery", min(0, flows["loss_kwh"]), "kWh"),
            )
        )
        require(
            audits, {"before": asdict(state), "inputs": asdict(inputs), "result": asdict(result)}
        )
        return ComponentResult(
            result.state, result.flows, tuple(self.identity().items()), tuple(audits)
        )

    def planning(self, state: BatteryState, durations: tuple[float, ...]):
        if not durations:
            raise ValueError("Battery planning requires at least one interval.")
        for duration in durations:
            self._validate(state, BatteryInput(duration_hours=duration))
        require(
            [
                check(
                    "battery_initial_bounds",
                    "battery",
                    max(-state.energy_kwh, state.energy_kwh - self.parameters.capacity_kwh, 0),
                    "kWh",
                    self.parameters.capacity_kwh,
                )
            ],
            asdict(state),
        )
        return self.kernel.planning(self.parameters, state, durations)

    def record(self, state, inputs, result):
        return {
            "schema_version": "dispatch-lab/battery-record/1",
            **self.identity(),
            "parameters": asdict(self.parameters),
            "before": asdict(state),
            "inputs": asdict(inputs),
            "after": asdict(result.state),
            "flows": dict(result.flows),
            "audits": list(result.audits),
        }


def from_plant(plant, implementation="affine/1"):
    """Boundary adapter; numeric kernels depend only on BatteryParameters."""
    if implementation not in IMPLEMENTATIONS:
        raise ValueError(f"Unknown battery implementation: {implementation}")
    return Battery(
        BatteryParameters(plant.battery_kwh, plant.battery_c_rate, plant.roundtrip_efficiency),
        IMPLEMENTATIONS[implementation],
    )
