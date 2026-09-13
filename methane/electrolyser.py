"""Productive electrical conversion and startup accounting, without plant allocation."""

from dataclasses import asdict, dataclass
from math import isfinite

from methane.audit import check, require
from methane.contracts import ELECTROLYSER, ComponentResult
from methane.ports import PlanningBlock, Port, equality, on_start_rows

IMPLEMENTATIONS = ("specific-energy/1", "yield-ledger/1")
MODEL_ID = "dispatch-lab/electrolyser"
PORTS = (
    Port("power", "kW", "Productive DC demand"),
    Port("electricity", "kW", "Productive plus start demand"),
    Port("hydrogen", "kg", "Hydrogen produced in interval"),
    Port("on", "boolean", "Operating"),
    Port("start", "boolean", "Off to on transition"),
)


@dataclass(frozen=True)
class Parameters:
    capacity_kw: float = 450
    minimum_fraction: float = 0.3
    specific_energy_kwh_per_kg: float = 55
    start_energy_kwh: float = 40

    def __post_init__(self):
        for parameter in ELECTROLYSER.parameters:
            parameter.validate(getattr(self, parameter.key))
        if (
            not all(isfinite(v) for v in asdict(self).values())
            or self.capacity_kw <= 0
            or not 0 < self.minimum_fraction <= 1
            or self.specific_energy_kwh_per_kg <= 0
            or self.start_energy_kwh < 0
        ):
            raise ValueError("Invalid electrolyser parameters")


@dataclass(frozen=True)
class State:
    on: bool = False


@dataclass(frozen=True)
class Inputs:
    productive_kw: float
    available_kw: float
    duration_hours: float = 1


@dataclass(frozen=True)
class Electrolyser:
    parameters: Parameters
    implementation_id: str = "specific-energy/1"

    def __post_init__(self):
        if self.implementation_id not in IMPLEMENTATIONS:
            raise ValueError("Unknown electrolyser implementation")

    def identity(self):
        return dict(model_id=MODEL_ID, model_version="1", implementation_id=self.implementation_id)

    def step(self, state: State, inputs: Inputs):
        p = self.parameters
        if (
            not all(isfinite(v) for v in asdict(inputs).values())
            or inputs.duration_hours <= 0
            or inputs.available_kw < 0
        ):
            raise ValueError("Finite electrolyser inputs and positive duration required")
        on = inputs.productive_kw > 1e-5
        start = on and not state.on
        minimum = p.capacity_kw * p.minimum_fraction if on else 0
        audits = [
            check(
                "electrolyser_power",
                "electrolyser",
                max(
                    0,
                    -inputs.productive_kw,
                    minimum - inputs.productive_kw,
                    inputs.productive_kw - min(inputs.available_kw, p.capacity_kw),
                ),
                "kW",
                p.capacity_kw,
            )
        ]
        require(audits, asdict(inputs))
        energy = inputs.productive_kw * inputs.duration_hours
        hydrogen = (
            energy / p.specific_energy_kwh_per_kg
            if self.implementation_id == "specific-energy/1"
            else energy * (1 / p.specific_energy_kwh_per_kg)
        )
        startup = float(start) * p.start_energy_kwh
        flows = dict(
            productive_kwh=energy,
            startup_kwh=startup,
            hydrogen_kg=hydrogen,
            water_kg=hydrogen * 9,
            electricity_kw=(energy + startup) / inputs.duration_hours,
            start=float(start),
        )
        return ComponentResult(
            State(on), tuple(flows.items()), tuple(self.identity().items()), tuple(audits)
        )

    def planning(self, state: State, available_kw, durations):
        p = self.parameters
        if not durations or not isfinite(available_kw) or not 0 <= available_kw <= p.capacity_kw:
            raise ValueError("Invalid electrolyser planning availability")
        rows = []
        for t, dt in enumerate(durations):
            if not isfinite(dt) or dt <= 0:
                raise ValueError("Positive finite duration required")
            rows.extend(
                on_start_rows(
                    "power",
                    "on",
                    "start",
                    t,
                    p.capacity_kw * p.minimum_fraction,
                    available_kw,
                    state.on,
                )
            )
            if self.implementation_id == "specific-energy/1":
                rows.append(
                    equality(
                        "hydrogen_conversion",
                        [("hydrogen", t, 1), ("power", t, -dt / p.specific_energy_kwh_per_kg)],
                    )
                )
            else:
                rows.append(
                    equality(
                        "hydrogen_conversion",
                        [("hydrogen", t, p.specific_energy_kwh_per_kg), ("power", t, -dt)],
                    )
                )
            rows.append(
                equality(
                    "electrical_demand",
                    [
                        ("electricity", t, 1),
                        ("power", t, -1),
                        ("start", t, -p.start_energy_kwh / dt),
                    ],
                )
            )
        return PlanningBlock(
            (
                ("power", 0, available_kw, False),
                ("hydrogen", 0, float("inf"), False),
                ("electricity", 0, float("inf"), False),
                ("on", 0, 1, True),
                ("start", 0, 1, True),
            ),
            tuple(rows),
            PORTS,
        )


def from_plant(p, implementation="specific-energy/1"):
    return Electrolyser(
        Parameters(
            p.electrolyser_kw, p.min_load_fraction, p.specific_energy_kwh_per_kg, p.start_energy_kwh
        ),
        implementation,
    )
