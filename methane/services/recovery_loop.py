"""Bounded repair-to-verification episodes using public mission and load evidence.

The original diagnosis/service deadlines are not rewritten. A completed mission
opens a distinct test window; a receipt never establishes repaired capacity.
"""

import copy

from methane.recovery import LOOP_VERSION
from methane.services.contracts import available_boundary
from methane.services.joint_recovery import Scheduler as JointScheduler
from methane.services.verification import validate as validate_evidence


class Scheduler(JointScheduler):
    def __init__(self, policy):
        if policy.version != LOOP_VERSION:
            raise ValueError("The bounded verification loop requires recovery policy version 3")
        super().__init__(policy)
        self.episodes = []
        self.completed_receipts = set()
        self.shortfalls = []
        self.escalated = False
        self.last_hour = -1
        self.original_deadline = None

    def begin(
        self, plant, sensors, diagnosis, *, hour, orders=(), continuation=None, evidence=None
    ):
        if hour <= self.last_hour or self.pending is not None:
            raise ValueError("Recovery observations require one advancing decision at a time")
        if evidence is not None:
            validate_evidence(evidence)
            packet = evidence["inputs"]["packet"]
            if packet["available_at"] > hour or packet["hour"] != hour - 1:
                raise ValueError("Recovery must use the immediately preceding eligible load test")
        else:
            packet = None
        completed = []
        pending_work = []
        for order in orders:
            if order.get("kind") not in ("reset", "module-replacement"):
                continue
            report = order.get("reported")
            end = order.get("completed_hour")
            if (
                end is not None
                and available_boundary(end) <= hour
                and report
                and report.get("available_at", float("inf")) <= hour
            ):
                completed.append(order)
            elif order.get("status") in ("queued", "active", "scheduled"):
                pending_work.append(order["id"])
        new = [o for o in completed if o["id"] not in self.completed_receipts]
        active = sensors.enabled and diagnosis.capacity_kw < plant.electrolyser_kw * 0.999
        if active and self.original_deadline is None:
            self.original_deadline = hour + self.policy.maximum_wait_hours
        if new:
            if self.episodes:
                self.episodes[-1].setdefault("closed_at", hour)
                self.episodes[-1].setdefault(
                    "outcome", "superseded by a separate completed mission"
                )
            boundary = max(
                max(available_boundary(o["completed_hour"]), o["reported"]["available_at"])
                for o in new
            )
            self.due_hour = boundary + self.policy.maximum_wait_hours
            self.episodes.append(
                dict(
                    receipt_ids=sorted(o["id"] for o in new),
                    opened_at=hour,
                    available_boundary=boundary,
                    due_hour=self.due_hour,
                    original_diagnosis_deadline=self.original_deadline,
                    original_deadline_missed=hour >= self.original_deadline if active else False,
                )
            )
            self.completed_receipts.update(o["id"] for o in new)
            self.shortfalls = []
            self.escalated = False
            self.accepted = None
            self.previous_probe = False
            self.next_eligible_hour = hour
        elif self.previous_probe and packet is not None and packet["probe"]:
            if evidence["outcome"] == "tracking shortfall":
                load = packet["request"]["electrolyser_kw"]
                self.shortfalls = [
                    x
                    for x in self.shortfalls
                    if abs(x["requested_kw"] - load) <= 1e-5
                    and hour - x["available_at"] <= self.policy.maximum_wait_hours
                ]
                self.shortfalls.append(
                    dict(evidence_id=evidence["evidence_id"], available_at=hour, requested_kw=load)
                )
            else:
                self.shortfalls = []
            if diagnosis.recovery_count == 0:
                # Inconclusive/failed intervals do not impose the old 24 h pause.
                # They consume the existing finite window; only real tracking
                # retains a consecutive confirmation prefix.
                self.previous_probe = False
                self.accepted = None
                self.next_eligible_hour = hour
        elif self.previous_probe and packet is None:
            self.previous_probe = False
            self.accepted = None
            self.shortfalls = []
        self.last_hour = hour
        request = super().begin(
            plant, sensors, diagnosis, hour=hour, orders=completed, continuation=continuation
        )
        status = self.pending["status"]
        if not active:
            self.escalated = False
            self.shortfalls = []
            if self.episodes:
                self.episodes[-1].setdefault("closed_at", hour)
                self.episodes[-1].setdefault(
                    "outcome", "observer confirmed" if sensors.enabled else "sensing disabled"
                )
        elif self.escalated or status == "deadline-missed":
            self.escalated = True
            status = "escalation-required"
            if self.episodes:
                self.episodes[-1].setdefault("closed_at", hour)
                self.episodes[-1].setdefault("outcome", "verification deadline missed")
        elif pending_work:
            status = "awaiting-procedure"
        elif len(self.shortfalls) >= sensors.confirmation_hours:
            status = "awaiting-remedy"
        if status in ("escalation-required", "awaiting-procedure", "awaiting-remedy"):
            self.request = request = None
            self.accepted = None
            self.previous_probe = False
        self.pending.update(
            version=LOOP_VERSION,
            status=status,
            verification_loop=dict(
                version="post-mission-verification-episodes/1",
                original_diagnosis_deadline=self.original_deadline,
                episodes=copy.deepcopy(self.episodes),
                shortfall_tests=copy.deepcopy(self.shortfalls),
                pending_work=sorted(pending_work),
                escalation_required=self.escalated,
                reason={
                    "escalation-required": "No observed recovery within the bounded window; obligation remains unresolved",
                    "awaiting-procedure": "Complete the accepted/queued remedy before allocating verification power",
                    "awaiting-remedy": "Repeated observed shortfalls support the existing bounded follow-up rule; additional probes wait for a separate remedy",
                }.get(
                    status,
                    "Jointly reserve test power and charging within the recorded verification window",
                ),
            ),
        )
        if not active:
            # A later independent diagnosis starts its own original deadline.
            # Completed episodes retain the immutable deadline recorded above.
            self.original_deadline = None
        return request
