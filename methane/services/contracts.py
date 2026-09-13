"""Serializable service contracts, with explicit units and no simulator-truth input.

Descriptors are immutable. Planning consumes Context (available observations),
while execution produces time-stamped receipts through a separate effect port.
Quantities use declared units; no implicit conversion occurs at resource ports.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal
from math import ceil, isfinite

from methane.services import CONTRACT_VERSION


def nonnegative(value, name):
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    if not isfinite(value) or value < 0:
        raise ValueError(f"{name} must be finite and nonnegative")


def identifier(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must be a nonempty identifier")


def available_boundary(completed_at):
    """First hourly decision boundary at/after completion, without early rounding."""
    nonnegative(completed_at, "completion time")
    return ceil(completed_at)


@dataclass(frozen=True)
class Quantity:
    resource: str
    amount: float
    unit: str

    def __post_init__(self):
        identifier(self.resource, "resource")
        identifier(self.unit, "unit")
        nonnegative(self.amount, self.resource)


@dataclass(frozen=True)
class Source:
    claim_id: str
    basis: str
    reference: str
    scope: str

    def __post_init__(self):
        identifier(self.claim_id, "claim")
        if self.basis not in ("assumption", "manufacturer", "experiment", "derived"):
            raise ValueError("Unknown evidence basis")
        identifier(self.reference, "source reference")
        identifier(self.scope, "source scope")


@dataclass(frozen=True)
class Reading:
    """An available sensor/report value; precision and error model belong to its source."""

    channel: str
    value: bool | float | str | None
    unit: str
    measured_at: float
    available_at: float
    source_id: str
    quality: str = "usable"

    def __post_init__(self):
        identifier(self.channel, "channel")
        identifier(self.source_id, "source")
        identifier(self.unit, "unit")
        nonnegative(self.measured_at, "measurement time")
        nonnegative(self.available_at, "availability time")
        if self.available_at < self.measured_at:
            raise ValueError("A reading cannot precede its measurement")
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("Nonfinite reading; use unavailable with a reason")
        if self.quality not in ("usable", "uncertain", "unavailable", "stale"):
            raise ValueError("Unknown reading quality")


@dataclass(frozen=True)
class Context:
    at_hour: float
    readings: tuple[Reading, ...]

    def __post_init__(self):
        nonnegative(self.at_hour, "decision time")
        if any(r.available_at > self.at_hour for r in self.readings):
            raise ValueError("Context contains a reading unavailable at this decision")

    def latest(self, channel):
        eligible = [r for r in self.readings if r.channel == channel]
        return max(eligible, key=lambda r: (r.measured_at, r.available_at), default=None)


@dataclass(frozen=True)
class Requirement:
    channel: str
    comparison: str
    value: bool | float | str
    unit: str
    max_age_hours: float

    def __post_init__(self):
        identifier(self.channel, "required channel")
        if self.comparison not in ("equals", "at_least", "at_most", "available"):
            raise ValueError("Unknown requirement comparison")
        nonnegative(self.max_age_hours, "reading maximum age")
        if isinstance(self.value, float) and not isfinite(self.value):
            raise ValueError("Requirement value must be finite")

    def failure(self, context):
        reading = context.latest(self.channel)
        if reading is None:
            return f"{self.channel}: no available observation"
        if reading.quality != "usable" or reading.value is None:
            return f"{self.channel}: {reading.quality} observation"
        if context.at_hour - reading.measured_at > self.max_age_hours:
            return f"{self.channel}: observation too old"
        if reading.unit != self.unit:
            return f"{self.channel}: unit mismatch ({reading.unit}, expected {self.unit})"
        if self.comparison == "available":
            passed = True
        elif self.comparison == "equals":
            same_kind = type(reading.value) is type(self.value) or all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in (reading.value, self.value)
            )
            passed = same_kind and reading.value == self.value
        else:
            numeric = all(
                isinstance(v, (int, float)) and not isinstance(v, bool)
                for v in (reading.value, self.value)
            )
            passed = numeric and (
                reading.value >= self.value
                if self.comparison == "at_least"
                else reading.value <= self.value
            )
        return None if passed else f"{self.channel}: requires {self.comparison} {self.value}"


@dataclass(frozen=True)
class Asset:
    asset_id: str
    archetype: str
    implementation_id: str
    home: str
    mobility: str
    capabilities: tuple[str, ...]
    tools: tuple[str, ...] = ()
    battery_resource: str | None = None
    return_reserve_kwh: float = 0
    travel_kw: float = 0
    autonomy: str = "autonomous"
    support_resources: tuple[Quantity, ...] = ()
    sources: tuple[Source, ...] = ()

    def __post_init__(self):
        for key in ("asset_id", "archetype", "implementation_id", "home"):
            identifier(getattr(self, key), key)
        if self.mobility not in ("fixed", "wheeled", "tracked", "legged", "aerial", "crew"):
            raise ValueError("Unknown asset mobility")
        if self.autonomy not in ("autonomous", "remote-operated", "human", "hypothetical"):
            raise ValueError("Unknown autonomy mode")
        nonnegative(self.return_reserve_kwh, "return energy reserve")
        nonnegative(self.travel_kw, "travel power")
        if self.battery_resource is None and (self.return_reserve_kwh or self.travel_kw):
            raise ValueError("Mobile electrical consumption requires a declared battery")
        if len(set(self.capabilities)) != len(self.capabilities):
            raise ValueError("Duplicate capability")


@dataclass(frozen=True)
class Interface:
    interface_id: str
    target_asset_id: str
    point: str
    actions: tuple[str, ...]
    required_tools: tuple[str, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    exclusive_resources: tuple[str, ...] = ()
    implementation_id: str = "declared-service-interface/1"

    def __post_init__(self):
        for key in ("interface_id", "target_asset_id", "point", "implementation_id"):
            identifier(getattr(self, key), key)
        if not self.actions:
            raise ValueError("A service interface must declare its compatible actions")


@dataclass(frozen=True)
class Capability:
    capability_id: str
    action: str
    effect_kind: str
    implementation_id: str
    work_hours: float
    verify_hours: float
    work_kw: float = 0
    prepare_hours: float = 0
    consumables: tuple[Quantity, ...] = ()
    requirements: tuple[Requirement, ...] = ()
    shared_resources: tuple[Quantity, ...] = ()
    sources: tuple[Source, ...] = ()
    acceptance: tuple[Requirement, ...] = ()
    hourly_consumables: tuple[Quantity, ...] = ()

    def __post_init__(self):
        for key in ("capability_id", "action", "implementation_id"):
            identifier(getattr(self, key), key)
        if self.effect_kind not in ("observe", "clean", "repair", "calibrate", "supply", "deploy"):
            raise ValueError("Unknown physical/observational effect kind")
        for key in ("work_hours", "verify_hours", "work_kw", "prepare_hours"):
            nonnegative(getattr(self, key), key)
        if self.work_hours <= 0:
            raise ValueError("Physical work must have positive duration")
        if self.effect_kind in ("repair", "calibrate") and not self.acceptance:
            raise ValueError("Restoration requires a declared post-work acceptance test")


@dataclass(frozen=True)
class WorkOrder:
    """Deadline is latest physical mission completion, including return if required."""

    order_id: str
    action: str
    interface_id: str
    requested_at: float
    reason: str
    evidence: tuple[Reading, ...] = ()
    priority: int = 0
    deadline: float | None = None

    def __post_init__(self):
        for key in ("order_id", "action", "interface_id", "reason"):
            identifier(getattr(self, key), key)
        nonnegative(self.requested_at, "work request time")
        if isinstance(self.priority, bool) or not isinstance(self.priority, int):
            raise ValueError("Work priority must be an integer")
        if any(r.available_at > self.requested_at for r in self.evidence):
            raise ValueError("Work order cites evidence unavailable when requested")
        if self.deadline is not None:
            nonnegative(self.deadline, "deadline")
            if self.deadline < self.requested_at:
                raise ValueError("Work deadline precedes request")


@dataclass(frozen=True)
class Stage:
    phase: str
    duration_hours: float
    from_point: str
    to_point: str
    battery_kw: float = 0
    bus_kw: float = 0
    consumables: tuple[Quantity, ...] = ()
    reservations: tuple[Quantity, ...] = ()
    effect: bool = False
    requirements: tuple[Requirement, ...] = ()
    hourly_consumables: tuple[Quantity, ...] = ()

    def __post_init__(self):
        if self.phase not in ("prepare", "travel", "perform", "verify", "return"):
            raise ValueError("Unknown mission phase")
        for key in ("duration_hours", "battery_kw", "bus_kw"):
            nonnegative(getattr(self, key), key)
        if self.duration_hours <= 0:
            raise ValueError("A mission stage must have positive duration")
        if self.effect and self.phase != "perform":
            raise ValueError("Only work stages may apply a capability effect")


@dataclass(frozen=True)
class MissionPlan:
    order: WorkOrder
    asset: Asset
    interface: Interface
    capability: Capability
    starting_at: float
    stages: tuple[Stage, ...]
    context: Context
    adapter_id: str
    schema_version: str = CONTRACT_VERSION
    timing: dict | None = None

    def __post_init__(self):
        nonnegative(self.starting_at, "mission start")
        if self.starting_at < max(self.context.at_hour, self.order.requested_at):
            raise ValueError("Mission starts before its decision or request")
        if not self.stages or sum(s.effect for s in self.stages) != 1:
            raise ValueError("Mission must contain one declared work effect")
        if not self.asset.battery_resource and any(s.battery_kw for s in self.stages):
            raise ValueError("Battery load requires an asset battery resource")
        if self.schema_version != CONTRACT_VERSION:
            raise ValueError("Unsupported service contract version")
        if self.timing is not None:
            from methane.services.uncertain_timing import validate_contract

            validate_contract(self)
        if self.order.deadline is not None and self.ending_at > self.order.deadline:
            raise ValueError("Mission including return exceeds the work deadline")

    @property
    def ending_at(self):
        return float(
            Decimal(str(self.starting_at))
            + sum(Decimal(str(s.duration_hours)) for s in self.stages)
        )

    def to_dict(self):
        value = asdict(self)
        if self.timing is None:
            value.pop("timing")
        return value
