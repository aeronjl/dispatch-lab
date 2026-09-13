"""Pure reactor thermal and discrete transitions; dispatch remains plant-wide."""

from dataclasses import asdict, dataclass, fields
from math import exp, expm1, isfinite

from methane.audit import check, require
from methane.contracts import REACTOR, ComponentResult
from methane.ports import LinearRow, PlanningBlock, Port, equality, on_start_rows

REACTION_KWH_PER_KG = 165000 / 16 / 3600


@dataclass(frozen=True)
class ThermalInput:
    temperature_c: float
    ambient_c: float
    heater_kw: float = 0
    methane_kg: float = 0
    cooling_kw: float = 0
    duration_hours: float = 1


@dataclass(frozen=True)
class ReactorState:
    temperature_c: float
    running: bool = False
    commitment_hours: int = 0


def coefficients(capacity, loss, duration=1):
    if (
        not all(isfinite(v) for v in (capacity, loss, duration))
        or capacity <= 0
        or loss < 0
        or duration <= 0
    ):
        raise ValueError("Thermal capacity/duration must be positive and heat loss nonnegative.")
    if loss == 0:
        return 1.0, duration / capacity
    x = loss * duration / capacity
    return exp(-x), -expm1(-x) / loss


def step(p, inputs: ThermalInput):
    if not all(isfinite(v) for v in vars(inputs).values()):
        raise ValueError("Thermal inputs must be finite.")
    if min(inputs.heater_kw, inputs.methane_kg, inputs.cooling_kw) < 0:
        raise ValueError("Heating, cooling and interval methane must be nonnegative.")
    duration = inputs.duration_hours
    a, b = coefficients(p.thermal_capacity_kwh_per_k, p.heat_loss_kw_per_k, duration)
    reaction = inputs.methane_kg * REACTION_KWH_PER_KG
    net = inputs.heater_kw + reaction / duration - inputs.cooling_kw
    end = a * inputs.temperature_c + (1 - a) * inputs.ambient_c + b * net
    # Analytic integral of UA(T(t)−Tamb); independently accounted, not a residual.
    x = p.heat_loss_kw_per_k * duration / p.thermal_capacity_kwh_per_k
    remainder = x / 2 - x * x / 6 + x**3 / 24 if x < 1e-4 else 1 - (-expm1(-x)) / x
    loss = (
        p.thermal_capacity_kwh_per_k * (inputs.temperature_c - inputs.ambient_c) * (-expm1(-x))
        + net * duration * remainder
    )
    return ComponentResult(
        ReactorState(end),
        (("reaction_heat_kwh", reaction), ("heat_loss_kwh", loss)),
        (("model", REACTOR.model_id), ("duration_hours", duration)),
    )


def operating_transition(
    was_running, commitment, running, requested_running, heating, hot, minimum_run
):
    """Classify an applied, physically checked action. `hot` means above ambient +1 K."""
    if minimum_run < 1 or int(minimum_run) != minimum_run or not 0 <= commitment < minimum_run:
        raise ValueError("Invalid reactor commitment.")
    start = running and not was_running
    remaining = max(0, (minimum_run if start else commitment) - 1) if running else 0
    trip = not running and (commitment > 0 or requested_running)
    mode = (
        "forced-trip"
        if trip
        else "running"
        if running
        else "warming"
        if heating
        else "cooling"
        if hot
        else "off"
    )
    return mode, remaining, bool(start), bool(trip)


@dataclass(frozen=True)
class Parameters:
    thermal_capacity_kwh_per_k: float = 0.3
    heat_loss_kw_per_k: float = 0.08
    temperature_min_c: float = 250
    temperature_max_c: float = 400
    heater_max_kw: float = 60
    cooling_max_kw: float = 40
    minimum_run_hours: int = 4
    methane_min_kgph: float = 3
    methane_max_kgph: float = 10
    auxiliary_kw: float = 2
    methane_electric_kwh_per_kg: float = 1
    cooling_electric_fraction: float = 0.1

    def __post_init__(self):
        for parameter in REACTOR.parameters:
            parameter.validate(getattr(self, parameter.key))
        if (
            not all(isfinite(v) for v in asdict(self).values())
            or not self.temperature_min_c < self.temperature_max_c
            or not 0 < self.methane_min_kgph <= self.methane_max_kgph
            or min(
                self.auxiliary_kw, self.methane_electric_kwh_per_kg, self.cooling_electric_fraction
            )
            < 0
        ):
            raise ValueError("Invalid reactor parameters")
        if int(self.minimum_run_hours) != self.minimum_run_hours:
            raise ValueError("Minimum run must be whole hours")


@dataclass(frozen=True)
class Reactor:
    parameters: Parameters
    implementation_id: str = "analytic/1"

    def __post_init__(self):
        if self.implementation_id != "analytic/1":
            raise ValueError("Unknown reactor implementation")

    def identity(self):
        return dict(
            model_id=REACTOR.model_id,
            model_version=REACTOR.version,
            implementation_id=self.implementation_id,
        )

    def execute(self, state: ReactorState, inputs: ThermalInput, requested_running=False):
        p = self.parameters
        if inputs.duration_hours != 1:
            raise ValueError(
                "Discrete reactor operation is hourly; thermal helper supports arbitrary duration"
            )
        if inputs.temperature_c != state.temperature_c:
            raise ValueError("Thermal input must match the supplied reactor state")
        thermal = step(p, inputs)
        active = inputs.methane_kg > 1e-5
        mode, remaining, start, trip = operating_transition(
            state.running,
            state.commitment_hours,
            active,
            requested_running,
            inputs.heater_kw > 1e-4,
            thermal.state.temperature_c > inputs.ambient_c + 1,
            p.minimum_run_hours,
        )
        audits = []
        for name, value, maximum in (
            ("heater", inputs.heater_kw, p.heater_max_kw),
            ("cooling", inputs.cooling_kw, p.cooling_max_kw),
            ("methane", inputs.methane_kg, p.methane_max_kgph),
        ):
            audits.append(
                check(
                    "reactor_" + name,
                    "reactor",
                    max(0, -value, value - maximum),
                    "kg" if name == "methane" else "kW",
                    maximum,
                )
            )
        audits.append(
            check(
                "reactor_exclusive_heat",
                "reactor",
                min(inputs.heater_kw, inputs.cooling_kw),
                "kW",
                p.heater_max_kw,
            )
        )
        if active:
            audits.append(
                check(
                    "reactor_minimum_output",
                    "reactor",
                    max(0, p.methane_min_kgph - inputs.methane_kg),
                    "kg",
                )
            )
            for label, temp in (
                ("begin", state.temperature_c),
                ("end", thermal.state.temperature_c),
            ):
                audits.append(
                    check(
                        "production_temperature_" + label,
                        "reactor",
                        max(p.temperature_min_c - temp, temp - p.temperature_max_c, 0),
                        "°C",
                        p.temperature_max_c,
                    )
                )
        require(audits, {"before": asdict(state), "inputs": asdict(inputs)})
        flows = {
            **dict(thermal.flows),
            "hydrogen_kg": inputs.methane_kg * 0.5,
            "co2_kg": inputs.methane_kg * 2.75,
            "water_kg": inputs.methane_kg * 2.25,
            "electricity_kw": inputs.heater_kw
            + inputs.cooling_kw * p.cooling_electric_fraction
            + active * p.auxiliary_kw
            + inputs.methane_kg * p.methane_electric_kwh_per_kg,
            "start": float(start),
            "forced_trip": float(trip),
        }
        return ComponentResult(
            ReactorState(thermal.state.temperature_c, active, remaining),
            tuple(flows.items()),
            tuple({**self.identity(), "mode": mode}.items()),
            tuple(audits),
        )

    def planning(self, state: ReactorState, ambient, durations, enforce_commitment=True):
        p = self.parameters
        if (
            not ambient
            or len(ambient) != len(durations)
            or any(d != 1 for d in durations)
            or not all(isfinite(v) for v in (*ambient, state.temperature_c))
        ):
            raise ValueError("Reactor scheduling requires finite hourly ambient intervals")
        a, b = coefficients(p.thermal_capacity_kwh_per_k, p.heat_loss_kw_per_k)
        big = p.temperature_max_c + 100
        rows = []
        for t, amb in enumerate(ambient):
            terms = [
                ("temperature", t, 1),
                ("heater", t, -b),
                ("methane", t, -b * REACTION_KWH_PER_KG),
                ("cooling", t, b),
            ]
            rhs = (1 - a) * amb
            if t:
                terms.append(("temperature", t - 1, -a))
            else:
                rhs += a * state.temperature_c
            rows.append(equality("thermal_balance", terms, rhs))
            rows.extend(
                on_start_rows(
                    "methane",
                    "on",
                    "start",
                    t,
                    p.methane_min_kgph,
                    p.methane_max_kgph,
                    state.running,
                )
            )
            rows.append(
                LinearRow(
                    "hot_at_end",
                    (("temperature", t, 1), ("on", t, -big)),
                    p.temperature_min_c - big,
                    float("inf"),
                )
            )
            if t:
                rows.append(
                    LinearRow(
                        "hot_at_start",
                        (("temperature", t - 1, 1), ("on", t, -big)),
                        p.temperature_min_c - big,
                        float("inf"),
                    )
                )
            elif (
                not p.temperature_min_c - 1e-6 <= state.temperature_c <= p.temperature_max_c + 1e-6
            ):
                rows.append(equality("cold_cannot_run", [("on", t, 1)]))
            if enforce_commitment:
                if t < state.commitment_hours:
                    rows.append(equality("committed", [("on", t, 1)], 1))
                for j in range(t, min(len(ambient), t + p.minimum_run_hours)):
                    rows.append(
                        LinearRow("minimum_run", (("on", j, 1), ("start", t, -1)), 0, float("inf"))
                    )
            rows.extend(
                (
                    LinearRow(
                        "heat_direction",
                        (("heater", t, 1), ("heating", t, -p.heater_max_kw)),
                        -float("inf"),
                        0,
                    ),
                    LinearRow(
                        "cool_direction",
                        (("cooling", t, 1), ("heating", t, p.cooling_max_kw)),
                        -float("inf"),
                        p.cooling_max_kw,
                    ),
                    equality(
                        "electrical_demand",
                        [
                            ("electricity", t, 1),
                            ("heater", t, -1),
                            ("cooling", t, -p.cooling_electric_fraction),
                            ("on", t, -p.auxiliary_kw),
                            ("methane", t, -p.methane_electric_kwh_per_kg),
                        ],
                    ),
                    equality("hydrogen_use", [("hydrogen", t, 1), ("methane", t, -0.5)]),
                    equality("co2_use", [("co2", t, 1), ("methane", t, -2.75)]),
                )
            )
        bounds = (
            ("temperature", -80, p.temperature_max_c, False),
            ("heater", 0, p.heater_max_kw, False),
            ("cooling", 0, p.cooling_max_kw, False),
            ("methane", 0, p.methane_max_kgph, False),
            ("on", 0, 1, True),
            ("start", 0, 1, True),
            ("heating", 0, 1, True),
            ("hydrogen", 0, float("inf"), False),
            ("co2", 0, float("inf"), False),
            ("electricity", 0, float("inf"), False),
        )
        units = {
            "temperature": "°C",
            "heater": "kW",
            "cooling": "kW",
            "methane": "kg",
            "on": "boolean",
            "start": "boolean",
            "heating": "boolean",
            "hydrogen": "kg",
            "co2": "kg",
            "electricity": "kW",
        }
        return PlanningBlock(
            bounds, tuple(rows), tuple(Port(k, units[k], k + " / reactor") for k, *_ in bounds)
        )


def from_plant(p, implementation="analytic/1"):
    return Reactor(
        Parameters(**{f.name: getattr(p, f.name) for f in fields(Parameters)}), implementation
    )
