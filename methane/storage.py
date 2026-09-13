"""Gas inventories: concurrent hydrogen flow or CO2 deliveries at interval start."""

from dataclasses import asdict, dataclass
from math import isfinite

from methane.audit import check, require
from methane.contracts import HYDROGEN, ComponentResult
from methane.ports import LinearRow, PlanningBlock, Port, equality

IMPLEMENTATIONS = ("balance/1", "ledger/1")


@dataclass(frozen=True)
class Parameters:
    capacity_kg: float
    kind: str = "hydrogen"

    def __post_init__(self):
        HYDROGEN.parameters[0].validate(self.capacity_kg)
        if (
            not isfinite(self.capacity_kg)
            or self.capacity_kg <= 0
            or self.kind not in ("hydrogen", "co2")
        ):
            raise ValueError("Invalid gas storage parameters")


@dataclass(frozen=True)
class State:
    inventory_kg: float


@dataclass(frozen=True)
class Inputs:
    incoming_kg: float
    outgoing_kg: float


@dataclass(frozen=True)
class Storage:
    parameters: Parameters
    implementation_id: str = "balance/1"

    def __post_init__(self):
        if self.implementation_id not in IMPLEMENTATIONS:
            raise ValueError("Unknown storage implementation")

    def identity(self):
        return dict(
            model_id="dispatch-lab/" + self.parameters.kind + "-buffer",
            model_version="1",
            implementation_id=self.implementation_id,
        )

    def step(self, state: State, inputs: Inputs):
        p = self.parameters
        if not all(
            isfinite(v) for v in (state.inventory_kg, inputs.incoming_kg, inputs.outgoing_kg)
        ):
            raise ValueError("Finite storage values required")
        accepted = (
            min(inputs.incoming_kg, max(0, p.capacity_kg - state.inventory_kg))
            if p.kind == "co2"
            else inputs.incoming_kg
        )
        rejected = inputs.incoming_kg - accepted
        if self.implementation_id == "balance/1":
            end = state.inventory_kg + accepted - inputs.outgoing_kg
        else:
            end = state.inventory_kg + (inputs.incoming_kg - inputs.outgoing_kg) - rejected
        audits = [
            check(
                "storage_initial_bounds",
                p.kind,
                max(-state.inventory_kg, state.inventory_kg - p.capacity_kg, 0),
                "kg",
                p.capacity_kg,
            ),
            check(
                "storage_ending_bounds",
                p.kind,
                max(-end, end - p.capacity_kg, 0),
                "kg",
                p.capacity_kg,
            ),
            check("storage_inflow", p.kind, min(0, inputs.incoming_kg), "kg"),
            check("storage_outflow", p.kind, min(0, inputs.outgoing_kg), "kg"),
            check(
                "storage_mass_balance",
                p.kind,
                end - state.inventory_kg - inputs.incoming_kg + inputs.outgoing_kg + rejected,
                "kg",
                p.capacity_kg,
            ),
        ]
        require(audits, {"before": asdict(state), "inputs": asdict(inputs)})
        return ComponentResult(
            State(end),
            (
                ("accepted_kg", accepted),
                ("rejected_kg", rejected),
                ("outgoing_kg", inputs.outgoing_kg),
            ),
            tuple(self.identity().items()),
            tuple(audits),
        )

    def planning(self, state: State, intervals, deliveries=None):
        p = self.parameters
        if (
            intervals < 1
            or int(intervals) != intervals
            or not isfinite(state.inventory_kg)
            or not -1e-5 <= state.inventory_kg <= p.capacity_kg + 1e-5
        ):
            raise ValueError("Invalid storage planning state")
        if p.kind == "co2" and (deliveries is None or len(deliveries) != intervals):
            raise ValueError("CO2 delivery sequence required")
        rows = []
        factor = 1 if self.implementation_id == "balance/1" else 1 / p.capacity_kg
        for t in range(intervals):
            accepted = "accepted" if p.kind == "co2" else "inflow"
            terms = [("inventory", t, factor), (accepted, t, -factor), ("outflow", t, factor)]
            if t:
                terms.append(("inventory", t - 1, -factor))
            rows.append(
                equality("inventory_balance", terms, state.inventory_kg * factor if t == 0 else 0)
            )
            if p.kind == "co2":
                arrival = deliveries[t]
                if not isfinite(arrival) or arrival < 0:
                    raise ValueError("Nonnegative finite deliveries required")
                rows.append(
                    equality(
                        "delivery_accounting", [("accepted", t, 1), ("rejected", t, 1)], arrival
                    )
                )
                terms = [("accepted", t, 1)] + ([("inventory", t - 1, 1)] if t else [])
                initial = state.inventory_kg if not t else 0
                rows.extend(
                    (
                        LinearRow(
                            "start_capacity", tuple(terms), -float("inf"), p.capacity_kg - initial
                        ),
                        LinearRow(
                            "full_before_rejection",
                            tuple([*terms, ("full", t, -p.capacity_kg)]),
                            -initial,
                            float("inf"),
                        ),
                        LinearRow(
                            "rejection_only_when_full",
                            (("rejected", t, 1), ("full", t, -arrival)),
                            -float("inf"),
                            0,
                        ),
                    )
                )
        bounds = [("inventory", 0, p.capacity_kg, False), ("outflow", 0, float("inf"), False)]
        bounds += (
            [
                ("accepted", 0, float("inf"), False),
                ("rejected", 0, float("inf"), False),
                ("full", 0, 1, True),
            ]
            if p.kind == "co2"
            else [("inflow", 0, float("inf"), False)]
        )
        ports = tuple(
            Port(name, "boolean" if name == "full" else "kg", name + " / " + p.kind)
            for name, *_ in bounds
        )
        return PlanningBlock(tuple(bounds), tuple(rows), ports)


def from_plant(p, kind, implementation="balance/1"):
    return Storage(
        Parameters(p.h2_capacity_kg if kind == "hydrogen" else p.co2_capacity_kg, kind),
        implementation,
    )


@dataclass(frozen=True)
class DeliverySchedule:
    amount_kg: float
    every_hours: int
    delay_hours: int = 0

    def __post_init__(self):
        if (
            not isfinite(self.amount_kg)
            or self.amount_kg < 0
            or self.every_hours < 1
            or self.delay_hours < 0
            or any(int(v) != v for v in (self.every_hours, self.delay_hours))
        ):
            raise ValueError("Delivery schedule uses nonnegative mass and whole hourly timing")

    def intervals(self, start, count):
        if min(start, count) < 0 or any(int(v) != v for v in (start, count)):
            raise ValueError("Delivery interval indices must be nonnegative integers")
        return [
            self.amount_kg
            if h - self.delay_hours > 0 and (h - self.delay_hours) % self.every_hours == 0
            else 0.0
            for h in range(start, start + count)
        ]
