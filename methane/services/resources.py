"""Atomic stock and time-window capacity reservations for service missions.

Stocks are quantities (kWh, kg, kits); capacities are simultaneous rates/slots
(kW, people, chargers). A reservation never consumes stock. Consumption and
replenishment have separate recorded events and can be independently reconciled.
"""

import copy
from dataclasses import asdict, dataclass, replace

from methane.services.contracts import Quantity, identifier, nonnegative

EPS = 1e-10


@dataclass(frozen=True)
class Resource:
    resource_id: str
    unit: str
    kind: str
    capacity: float
    initial: float = 0

    def __post_init__(self):
        identifier(self.resource_id, "resource")
        identifier(self.unit, "resource unit")
        if self.kind not in ("stock", "capacity"):
            raise ValueError("Resource must be stock or simultaneous capacity")
        nonnegative(self.capacity, "resource capacity")
        nonnegative(self.initial, "initial inventory")
        if self.initial > self.capacity or (self.kind == "capacity" and self.initial):
            raise ValueError("Invalid resource initial inventory")


@dataclass(frozen=True)
class Booking:
    resource: str
    start: float
    end: float
    amount: float
    unit: str
    mission_id: str = ""

    def __post_init__(self):
        for key in ("start", "end", "amount"):
            nonnegative(getattr(self, key), key)
        if self.end <= self.start:
            raise ValueError("Reservation must have positive duration")


class ResourceConflict(ValueError):
    def __init__(self, reasons):
        self.reasons = tuple(reasons)
        super().__init__("; ".join(self.reasons))


class Ledger:
    def __init__(self, resources):
        specs = tuple(resources)
        self.specs = {r.resource_id: r for r in specs}
        if len(self.specs) != len(specs):
            raise ValueError("Duplicate resource identifier")
        self.stock = {r.resource_id: r.initial for r in specs if r.kind == "stock"}
        self.holds, self.bookings, self.events = {}, [], []
        self.seen_missions = set()

    def _spec(self, resource, unit, kind):
        spec = self.specs.get(resource)
        if spec is None or spec.kind != kind or spec.unit != unit:
            raise ResourceConflict([f"{resource}: expected declared {kind} resource in {unit}"])
        return spec

    def available(self, resource):
        if resource not in self.stock:
            raise ResourceConflict([f"{resource}: not a stock resource"])
        return self.stock[resource] - sum(h.get(resource, 0) for h in self.holds.values())

    def check(self, mission_id, quantities, bookings):
        reasons, claims = [], {}
        if mission_id in self.seen_missions:
            reasons.append(f"{mission_id}: mission identifier already used")
        for q in quantities:
            try:
                self._spec(q.resource, q.unit, "stock")
            except ResourceConflict as exc:
                reasons.extend(exc.reasons)
                continue
            claims[q.resource] = claims.get(q.resource, 0) + q.amount
        for key, amount in claims.items():
            if amount > self.available(key) + EPS:
                reasons.append(f"{key}: {amount:g} required, {self.available(key):g} unreserved")
        proposed = {}
        for b in bookings:
            try:
                self._spec(b.resource, b.unit, "capacity")
            except ResourceConflict as exc:
                reasons.extend(exc.reasons)
                continue
            proposed.setdefault(b.resource, []).append(b)
        for key, added in proposed.items():
            periods = added + [b for b in self.bookings if b.resource == key]
            # Half-open windows: work ending at 1h does not conflict with work starting at 1h.
            points = sorted({t for b in periods for t in (b.start, b.end)})
            for t in points[:-1]:
                demand = sum(b.amount for b in periods if b.start <= t < b.end)
                if demand > self.specs[key].capacity + EPS:
                    reasons.append(f"{key}: capacity exceeded at {t:g}h ({demand:g})")
                    break
        return tuple(reasons)

    def reserve(self, mission_id, quantities, bookings, at_hour):
        identifier(mission_id, "mission")
        nonnegative(at_hour, "reservation time")
        quantities, bookings = tuple(quantities), tuple(bookings)
        if any(b.start < at_hour for b in bookings):
            raise ResourceConflict(["Cannot reserve a past capacity window"])
        reasons = self.check(mission_id, quantities, bookings)
        if reasons:
            raise ResourceConflict(reasons)
        held = {}
        for q in quantities:
            held[q.resource] = held.get(q.resource, 0) + q.amount
        self.holds[mission_id] = held
        self.seen_missions.add(mission_id)
        self.bookings.extend(replace(b, mission_id=mission_id) for b in bookings)
        self.events.append(
            {
                "kind": "reserve",
                "at_hour": at_hour,
                "mission_id": mission_id,
                "stocks": [asdict(q) for q in quantities],
                "capacity": [asdict(b) for b in bookings],
            }
        )

    def consume(self, mission_id, quantity, at_hour, phase):
        q = quantity
        self._spec(q.resource, q.unit, "stock")
        nonnegative(at_hour, "consumption time")
        held = self.holds.get(mission_id, {})
        if q.amount > held.get(q.resource, 0) + EPS:
            raise ResourceConflict([f"{q.resource}: consumption exceeds mission reservation"])
        if q.amount > self.stock[q.resource] + EPS:
            raise ResourceConflict([f"{q.resource}: consumption exceeds physical inventory"])
        self.stock[q.resource] -= q.amount
        held[q.resource] = held.get(q.resource, 0) - q.amount
        self.events.append(
            dict(kind="consume", at_hour=at_hour, mission_id=mission_id, phase=phase, **asdict(q))
        )

    def reserve_batch(self, entries, at_hour, *, dry_run=False):
        """Publish all linked reservations together, or leave the ledger untouched."""
        # reserve() only appends bookings/events and adds new hold dictionaries;
        # it does not mutate existing stock or held quantities. Copy the changing
        # containers, not the potentially long history of immutable past events.
        trial = copy.copy(self)
        trial.holds, trial.bookings = dict(self.holds), list(self.bookings)
        trial.seen_missions, trial.events = set(self.seen_missions), []
        for key, quantities, bookings in entries:
            trial.reserve(key, quantities, bookings, at_hour)
        if not dry_run:
            self.holds, self.bookings = trial.holds, trial.bookings
            self.events.extend(trial.events)
            self.seen_missions = trial.seen_missions

    def replenish(self, quantity, at_hour, source_id):
        q = quantity
        spec = self._spec(q.resource, q.unit, "stock")
        nonnegative(at_hour, "delivery time")
        identifier(source_id, "replenishment source")
        accepted = min(q.amount, max(0, spec.capacity - self.stock[q.resource]))
        self.stock[q.resource] += accepted
        self.events.append(
            dict(
                kind="replenish",
                at_hour=at_hour,
                source_id=source_id,
                resource=q.resource,
                unit=q.unit,
                offered=q.amount,
                accepted=accepted,
                rejected=q.amount - accepted,
            )
        )
        return Quantity(q.resource, accepted, q.unit)

    def release(self, mission_id, at_hour):
        nonnegative(at_hour, "release time")
        if mission_id not in self.holds:
            raise ResourceConflict([f"{mission_id}: no active reservation"])
        unused = self.holds.pop(mission_id)
        retained = []
        for b in self.bookings:
            if b.mission_id != mission_id or b.end <= at_hour:
                retained.append(b)
            elif b.start < at_hour:
                retained.append(replace(b, end=at_hour))
        self.bookings = retained
        self.events.append(
            dict(kind="release", at_hour=at_hour, mission_id=mission_id, unused_stocks=unused)
        )

    def reconcile(self):
        rows = []
        for key, value in self.stock.items():
            consumed = sum(
                e["amount"] for e in self.events if e["kind"] == "consume" and e["resource"] == key
            )
            received = sum(
                e["accepted"]
                for e in self.events
                if e["kind"] == "replenish" and e["resource"] == key
            )
            residual = value - self.specs[key].initial - received + consumed
            rows.append(
                dict(
                    resource=key,
                    unit=self.specs[key].unit,
                    initial=self.specs[key].initial,
                    received=received,
                    consumed=consumed,
                    ending=value,
                    reserved=value - self.available(key),
                    residual=residual,
                    passed=abs(residual) < 1e-8 and self.available(key) >= -EPS,
                )
            )
        return rows
