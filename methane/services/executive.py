"""Fractional-hour task executive; scheduling and hidden physical outcomes are separate.

The executive does not choose work or a repair hypothesis. A decision supplies a
MissionPlan. The effect port alone can own simulator truth. Its physical receipts
are retrospective; only explicitly declared observations cross to a controller.
"""

import copy
import json
from dataclasses import asdict, dataclass, field
from typing import Protocol

from methane.services.adapters import claims, eligibility, schedule
from methane.services.contracts import Context, MissionPlan, Quantity, Reading, available_boundary
from methane.services.resources import ResourceConflict


@dataclass(frozen=True)
class Receipt:
    report: str
    observations: tuple[Reading, ...] = ()
    physical_effects: tuple[dict, ...] = ()
    interrupted: bool = False

    def __post_init__(self):
        json.dumps(self.physical_effects, allow_nan=False)


class EffectPort(Protocol):
    def perform(self, plan: MissionPlan, completed_at: float) -> Receipt: ...


@dataclass
class Mission:
    plan: MissionPlan
    stage_index: int = 0
    entered: bool = False
    status: str = "scheduled"
    work_completed_at: float | None = None
    completed_at: float | None = None
    verified_at: float | None = None
    interrupted_at: float | None = None
    reason: str | None = None
    bus_kwh: float = 0
    battery_kwh: float = 0
    events: list[dict] = field(default_factory=list)


class Executive:
    def __init__(self, ledger, effect_port):
        self.ledger, self._effect_port = ledger, effect_port
        self.at_hour = 0.0
        self.missions = {}
        self.visits, self.member_visits = {}, {}
        self._observations, self._reports, self._physical = [], [], []

    def submit(self, plan):
        if plan.adapter_id.startswith("conditional-"):
            raise ValueError(
                "Conditional recipes are predictions; rebuild from current observations before dispatch"
            )
        key = plan.order.order_id
        if key in self.missions:
            raise ResourceConflict([f"{key}: work order already dispatched"])
        if plan.context.at_hour != self.at_hour or plan.starting_at < self.at_hour:
            raise ValueError("Dispatch context must match the executive's present time")
        reasons = eligibility(plan.order, plan.asset, plan.interface, plan.capability, plan.context)
        if reasons:
            raise ResourceConflict(reasons)
        quantities, bookings = claims(plan)
        self.ledger.reserve(key, quantities, bookings, self.at_hour)
        self.missions[key] = Mission(plan)
        return key

    def observations(self, at_hour=None):
        at = self.at_hour if at_hour is None else at_hour
        if at > self.at_hour:
            raise ValueError("Cannot request future execution observations")
        return tuple(r for r in self._observations if r.available_at <= at)

    def check_visit(self, visit):
        from methane.services.visits import reservations

        if visit.visit_id in self.visits:
            raise ResourceConflict(["Visit identifier already dispatched"])
        for plan in visit.members:
            if plan.adapter_id.startswith("conditional-"):
                raise ValueError("A visit cannot execute a conditional recipe")
            if plan.order.order_id in self.missions:
                raise ResourceConflict(["Visit job already dispatched"])
            if plan.context.at_hour != self.at_hour or plan.starting_at < self.at_hour:
                raise ValueError("Visit requires the present decision context")
            reasons = eligibility(
                plan.order, plan.asset, plan.interface, plan.capability, plan.context
            )
            if reasons:
                raise ResourceConflict(reasons)
        self.ledger.reserve_batch(reservations(visit), self.at_hour, dry_run=True)

    def submit_visit(self, visit):
        from methane.services.visits import reservations

        self.check_visit(visit)
        self.ledger.reserve_batch(reservations(visit), self.at_hour)
        self.visits[visit.visit_id] = visit
        for plan in visit.members:
            key = plan.order.order_id
            self.missions[key] = Mission(plan)
            self.member_visits[key] = visit.visit_id
        return visit.visit_id

    def _stop_visit(self, mission_id, reason):
        visit = self.visits.get(self.member_visits.get(mission_id))
        if visit is None:
            return
        members = [self.missions[p.order.order_id] for p in visit.members]
        away = any(
            e["kind"] == "interval" and e["phase"] == "travel" and e["end"] > e["start"]
            for member in members
            for e in member.events
        )
        # An upcoming job can lose a prerequisite while the crew is still doing
        # its predecessor. Stop the physical crew where it is, not at the future
        # job's service point; cancel the other unstarted members.
        current = max(
            (m for m in members if m.completed_at is None and m.plan.starting_at <= self.at_hour),
            key=lambda m: m.plan.starting_at,
            default=None,
        )
        for plan in visit.members:
            key = plan.order.order_id
            member = self.missions[key]
            if member.completed_at is None and (
                key == mission_id or member.status in ("scheduled", "active")
            ):
                if member.status != "invalid":
                    member.status = "stranded" if away and member is current else "blocked"
                member.interrupted_at = self.at_hour
                if key != mission_id:
                    member.reason = "Shared visit interrupted: " + reason
                    member.events.append(
                        dict(kind="interrupted", at_hour=self.at_hour, reason=member.reason)
                    )
                    self.ledger.release(key, self.at_hour)
        if visit.visit_id in self.ledger.holds:
            self.ledger.release(visit.visit_id, self.at_hour)

    @property
    def receipt_count(self):
        return len(self._physical)

    def retrospective(self, start=0):
        return copy.deepcopy(self._physical[start:])

    def _context(self, context, at_hour):
        return Context(
            at_hour,
            (*context.readings, *(r for r in self._observations if r.available_at <= at_hour)),
        )

    def reconcile_verification(self, context):
        if context.at_hour != self.at_hour:
            raise ValueError("Verification context must be current")
        current = self._context(context, self.at_hour)
        for mission in self.missions.values():
            if mission.status != "awaiting verification":
                continue
            if available_boundary(mission.completed_at) > current.at_hour:
                continue
            tests = mission.plan.capability.acceptance
            failures = [r.failure(current) for r in tests]
            fresh = all(
                current.latest(r.channel) is not None
                and current.latest(r.channel).measured_at
                >= (
                    mission.work_completed_at
                    if mission.plan.capability.effect_kind in ("repair", "calibrate")
                    else next(start for start, _, stage in schedule(mission.plan) if stage.effect)
                )
                for r in tests
            )
            if not any(failures) and fresh:
                mission.status = "completed"
                mission.verified_at = current.at_hour if tests else None
                mission.events.append(
                    dict(
                        kind="accepted" if tests else "completed",
                        at_hour=current.at_hour,
                        evidence=[asdict(current.latest(r.channel)) for r in tests],
                    )
                )

    def interrupt(self, mission_id, reason):
        """Stop at the current physical time. Retrieval is a subsequent explicit task."""
        mission = self.missions[mission_id]
        if mission.status not in ("scheduled", "active"):
            raise ValueError("Only outstanding execution may be interrupted")
        mobile = mission.plan.asset.mobility != "fixed"
        phase = schedule(mission.plan)[mission.stage_index][2].phase
        travelled = any(e["kind"] == "stage_end" and e["phase"] == "travel" for e in mission.events)
        travelling = phase in ("travel", "return") and mission.status == "active"
        mission.status = "stranded" if mobile and (travelled or travelling) else "blocked"
        mission.interrupted_at, mission.reason = self.at_hour, reason
        mission.events.append(dict(kind="interrupted", at_hour=self.at_hour, reason=reason))
        self.ledger.release(mission_id, self.at_hour)
        self._stop_visit(mission_id, reason)

    def _enter(self, mission, stage, context):
        requirements = (
            *mission.plan.capability.requirements,
            *stage.requirements,
            *(
                mission.plan.interface.requirements
                if stage.phase not in ("travel", "return")
                else ()
            ),
        )
        failures = [r.failure(context) for r in requirements]
        if any(failures):
            self.interrupt(mission.plan.order.order_id, "; ".join(r for r in failures if r))
            return False
        if hasattr(self._effect_port, "before_stage"):
            try:
                receipt = self._effect_port.before_stage(mission.plan, stage, self.at_hour)
                if receipt is not None:
                    self._record_receipt(mission, receipt)
                    if receipt.interrupted:
                        return False
            except Exception as exc:
                self._invalidate(mission, exc)
                raise
        if not mission.entered:
            for quantity in stage.consumables:
                self.ledger.consume(
                    mission.plan.order.order_id, quantity, self.at_hour, stage.phase
                )
            mission.entered = True
            mission.events.append(dict(kind="stage_start", at_hour=self.at_hour, phase=stage.phase))
        mission.status = "active"
        return True

    def _invalidate(self, mission, exc):
        key = mission.plan.order.order_id
        mission.status, mission.reason = "invalid", str(exc)
        mission.interrupted_at = self.at_hour
        mission.events.append(dict(kind="invalid", at_hour=self.at_hour, reason=str(exc)))
        if key in self.ledger.holds:
            self.ledger.release(key, self.at_hour)
        self._stop_visit(key, str(exc))

    def _record_receipt(self, mission, receipt, kind="completion"):
        for reading in receipt.observations:
            if reading.measured_at > self.at_hour or reading.available_at < available_boundary(
                self.at_hour
            ):
                raise ValueError(
                    "Effect port returned a future or prematurely available observation"
                )
        key = mission.plan.order.order_id
        self._observations.extend(receipt.observations)
        self._reports.append(
            dict(
                order_id=key,
                report=receipt.report,
                completed_at=self.at_hour,
                available_at=available_boundary(self.at_hour),
            )
        )
        self._physical.append(
            dict(
                order_id=key,
                completed_at=self.at_hour,
                effective_at=available_boundary(self.at_hour),
                capability=mission.plan.capability.implementation_id,
                effects=copy.deepcopy(receipt.physical_effects),
            )
        )
        if kind == "progress":
            mission.events.append(
                dict(
                    kind="progress",
                    at_hour=self.at_hour,
                    available_at=available_boundary(self.at_hour),
                )
            )
        if receipt.interrupted:
            self.interrupt(key, receipt.report)

    def _finish_stage(self, mission, stage):
        key = mission.plan.order.order_id
        mission.events.append(dict(kind="stage_end", at_hour=self.at_hour, phase=stage.phase))
        if stage.effect:
            try:
                receipt = self._effect_port.perform(mission.plan, self.at_hour)
                self._record_receipt(mission, receipt)
            except Exception as exc:
                self._invalidate(mission, exc)
                raise
            mission.work_completed_at = self.at_hour
            if receipt.interrupted:
                return
        mission.stage_index += 1
        mission.entered = False
        if mission.stage_index == len(mission.plan.stages):
            mission.completed_at = self.at_hour
            mission.status = "awaiting verification"
            self.ledger.release(key, self.at_hour)
            visit = self.visits.get(self.member_visits.get(key))
            if visit is not None and all(
                self.missions[p.order.order_id].completed_at is not None for p in visit.members
            ):
                self.ledger.release(visit.visit_id, self.at_hour)

    def advance(self, until, context):
        """Integrate each stage's rates exactly over [present, until).

        Context is available at the start, not sampled from the end of this
        integration. Call again at a new environmental observation/event boundary
        to make a changed condition affect execution from that point onward.
        """
        if until < self.at_hour or context.at_hour != self.at_hour:
            raise ValueError("Execution time is monotonic and requires present observations")
        from methane.services.contracts import nonnegative

        nonnegative(until, "advance target")
        self.reconcile_verification(context)
        while self.at_hour < until:
            edges = [until]
            for mission in self.missions.values():
                if mission.status not in ("scheduled", "active"):
                    continue
                edges.extend(
                    t
                    for start, end, _ in schedule(mission.plan)[mission.stage_index :]
                    for t in (start, end)
                    if t > self.at_hour
                )
                if hasattr(self._effect_port, "next_event"):
                    try:
                        event = self._effect_port.next_event(mission.plan, self.at_hour)
                        if event is not None:
                            nonnegative(event, "execution event")
                            if event <= self.at_hour:
                                raise ValueError("An execution event must advance time")
                            edges.append(event)
                    except Exception as exc:
                        self._invalidate(mission, exc)
                        raise
            stop = min(edges)
            running = []
            progressing = []
            current = self._context(context, self.at_hour)
            for key in sorted(self.missions):
                mission = self.missions[key]
                if mission.status not in ("scheduled", "active"):
                    continue
                start, end, stage = schedule(mission.plan)[mission.stage_index]
                if start > self.at_hour or not self._enter(mission, stage, current):
                    continue
                duration = stop - self.at_hour
                for rate in stage.hourly_consumables:
                    self.ledger.consume(
                        key,
                        Quantity(rate.resource, rate.amount * duration, rate.unit),
                        stop,
                        stage.phase,
                    )
                energy = stage.battery_kw * duration
                if energy:
                    self.ledger.consume(
                        key,
                        Quantity(mission.plan.asset.battery_resource, energy, "kWh"),
                        stop,
                        stage.phase,
                    )
                    mission.battery_kwh += energy
                mission.bus_kwh += stage.bus_kw * duration
                mission.events.append(
                    dict(
                        kind="interval",
                        start=self.at_hour,
                        end=stop,
                        phase=stage.phase,
                        battery_kwh=energy,
                        bus_kwh=stage.bus_kw * duration,
                    )
                )
                if end == stop:
                    running.append((mission, stage))
                progressing.append((mission, stage, self.at_hour))
            self.at_hour = stop
            if hasattr(self._effect_port, "progress"):
                for mission, stage, started in progressing:
                    try:
                        receipt = self._effect_port.progress(mission.plan, stage, started, stop)
                        if receipt is not None:
                            self._record_receipt(mission, receipt, "progress")
                    except Exception as exc:
                        self._invalidate(mission, exc)
                        raise
            for mission, stage in running:
                if mission.status in ("scheduled", "active"):
                    self._finish_stage(mission, stage)
        return self.public()

    def public(self):
        """Execution telemetry and eligible reports; never physical receipt contents."""
        orders = []
        for key, mission in self.missions.items():
            slots = schedule(mission.plan)
            index = min(mission.stage_index, len(slots) - 1)
            start, end, stage = slots[index]
            at = mission.interrupted_at if mission.interrupted_at is not None else self.at_hour
            progress = min(1, max(0, (at - start) / (end - start)))
            orders.append(
                dict(
                    order_id=key,
                    asset_id=mission.plan.asset.asset_id,
                    action=mission.plan.order.action,
                    target=mission.plan.interface.target_asset_id,
                    status=mission.status,
                    phase=stage.phase,
                    from_point=stage.from_point,
                    to_point=stage.to_point,
                    progress=progress,
                    started_at=mission.plan.starting_at,
                    completed_at=mission.completed_at,
                    verified_at=mission.verified_at,
                    reason=mission.reason,
                    bus_kwh=mission.bus_kwh,
                    battery_kwh=mission.battery_kwh,
                    reports=[
                        copy.deepcopy(r)
                        for r in self._reports
                        if r["order_id"] == key and r["available_at"] <= self.at_hour
                    ],
                )
            )
        result = dict(
            version="service-executive/1",
            at_hour=self.at_hour,
            orders=orders,
            observations=[asdict(r) for r in self.observations()],
            resources=self.ledger.reconcile(),
        )
        if self.visits:
            result["visits"] = [self.visit_public(v) for v in self.visits.values()]
        return result

    def visit_public(self, visit):
        members = [self.missions[p.order.order_id] for p in visit.members]
        interrupted = next(
            (m for m in members if m.status in ("blocked", "stranded", "invalid")), None
        )
        returned = all(m.completed_at is not None for m in members)
        return dict(
            visit_id=visit.visit_id,
            implementation_id=visit.implementation_id,
            crew_resource=visit.crew_resource,
            reason=visit.reason,
            starting_at=visit.starting_at,
            planned_return_at=visit.ending_at,
            returned_at=members[-1].completed_at if returned else None,
            status="interrupted"
            if interrupted
            else "completed"
            if all(m.status == "completed" for m in members)
            else "returned; acceptance pending"
            if returned
            else "underway"
            if self.at_hour > visit.starting_at
            else "scheduled",
            members=[p.order.order_id for p in visit.members],
            planned_jobs=[
                dict(
                    order_id=p.order.order_id,
                    action=p.order.action,
                    target=p.interface.target_asset_id,
                    starting_at=p.starting_at,
                    ending_at=p.ending_at,
                )
                for p in visit.members
            ],
            planned_crew_hours=visit.ending_at - visit.starting_at,
            active_member=next(
                (m.plan.order.order_id for m in members if m.status == "active"), None
            ),
            interruption=interrupted.reason if interrupted else None,
            unfinished=[m.plan.order.order_id for m in members if m.completed_at is None],
        )
