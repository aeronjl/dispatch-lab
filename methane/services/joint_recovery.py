"""Accepted load-test windows coordinated with work, charging and plant dispatch.

Only public procedure receipts and the process observer enter this executive.
Plans predict two delivery hypotheses; neither is a diagnosis or repair receipt.
"""

import copy
from dataclasses import asdict, dataclass

from methane.recovery import JOINT_VERSION, RecoveryPolicy, compare
from methane.sensing import Diagnosis
from methane.services.continuation import Continuation
from methane.services.coupling import identity


@dataclass(frozen=True)
class Request:
    hour: int
    capacity_kw: float
    target_kw: float
    required_hours: int
    due_hour: int
    policy: RecoveryPolicy
    accepted_start: int | None = None
    continuation: Continuation | None = None

    def __post_init__(self):
        if self.policy.version != JOINT_VERSION:
            raise ValueError("Joint recovery requests require the version-2 policy")
        if (
            any(type(v) is not int for v in (self.hour, self.required_hours, self.due_hour))
            or self.hour < 0
            or self.required_hours < 1
            or self.due_hour <= self.hour
        ):
            raise ValueError(
                "Recovery requests need current, duration and absolute deadline boundaries"
            )
        from methane.services.contracts import nonnegative

        nonnegative(self.capacity_kw, "observed capacity")
        nonnegative(self.target_kw, "requested recovery test load")
        if self.target_kw <= self.capacity_kw:
            raise ValueError("Recovery tests must exceed the current capacity estimate")
        if self.accepted_start is not None and (
            type(self.accepted_start) is not int or self.accepted_start < self.hour
        ):
            raise ValueError("An accepted test window cannot start in the past")
        if self.continuation is not None and (
            not isinstance(self.continuation, Continuation)
            or self.continuation.created_hour > self.hour
            or self.due_hour > self.continuation.due_hour
        ):
            raise ValueError(
                "Recovery request must preserve its observed continuation and original deadline"
            )

    def to_dict(self):
        value = asdict(self)
        if self.continuation is None:
            value.pop("continuation")
        return value

    @classmethod
    def from_dict(cls, value):
        return cls(
            **{
                **value,
                "policy": RecoveryPolicy(**value["policy"]),
                **(
                    dict(continuation=Continuation.from_dict(value["continuation"]))
                    if value.get("continuation")
                    else {}
                ),
            }
        )

    @property
    def request_id(self):
        return identity(self.to_dict())


def evaluate(
    request,
    plant,
    state,
    forecast,
    costs,
    *,
    objective,
    seconds,
    components=None,
    alternative=None,
    terminal_battery_value=0,
    charging_inputs=None,
    completion_boundary=None,
):
    """Pure candidate evaluation; acceptance is a separate, keyed operation."""
    if request.continuation is not None and completion_boundary is None:
        raise ValueError(
            "A nominated operating test must retain its actual work completion prerequisite"
        )
    result = compare(
        plant,
        state,
        Diagnosis(request.capacity_kw),
        forecast,
        costs,
        request.policy,
        hour=request.hour,
        target_kw=request.target_kw,
        required_hours=request.required_hours,
        due_hour=request.due_hour,
        objective=objective,
        seconds=seconds,
        components=components,
        alternative=alternative,
        terminal_battery_value=terminal_battery_value,
        charging_inputs=charging_inputs,
        accepted_start=request.accepted_start,
        total_seconds=seconds,
        not_before_hour=completion_boundary,
    )
    result.update(request_id=request.request_id, request=request.to_dict())
    return result


class Scheduler:
    """Preserve accepted windows and the original episode deadline on replanning."""

    def __init__(self, policy):
        if policy.version != JOINT_VERSION:
            raise ValueError("Joint scheduler requires the version-2 recovery policy")
        self.policy = policy
        self.due_hour = None
        self.next_eligible_hour = 0
        self.last_capacity = None
        self.previous_probe = False
        self.accepted = None
        self.seen_receipts = set()
        self.pending = None
        self.request = None
        self.continuation_id = None

    def begin(self, plant, sensors, diagnosis, *, hour, orders=(), continuation=None):
        if self.pending is not None:
            raise ValueError("The previous recovery decision must finish before the next begins")
        if continuation is not None and (
            not isinstance(continuation, Continuation)
            or continuation.created_hour > hour
            or continuation.test_hours != sensors.confirmation_hours
        ):
            raise ValueError(
                "Operating continuation must use current observed work and the configured test duration"
            )
        receipts = []
        for order in orders:
            report = order.get("reported")
            if (
                order.get("kind") in ("reset", "module-replacement")
                and report
                and report.get("available_at", float("inf")) <= hour
            ):
                key = (order["id"], report.get("completed_at"))
                if key not in self.seen_receipts:
                    self.seen_receipts.add(key)
                    receipts.append(dict(order_id=key[0], report=copy.deepcopy(report)))
        previous = copy.deepcopy(self.accepted)
        changes = []
        next_continuation = continuation.continuation_id if continuation else None
        changed_continuation = next_continuation != self.continuation_id
        self.continuation_id = next_continuation
        status = "ready"
        active = sensors.enabled and diagnosis.capacity_kw < plant.electrolyser_kw * 0.999
        failed = (
            self.previous_probe
            and diagnosis.recovery_count == 0
            and self.last_capacity is not None
            and diagnosis.capacity_kw <= self.last_capacity + 1e-8
        )
        increased = (
            self.last_capacity is not None and diagnosis.capacity_kw > self.last_capacity + 1e-8
        )
        if not active:
            status = "inactive"
            self.due_hour, self.accepted = None, None
            self.next_eligible_hour = 0
            if previous:
                changes.append(
                    "Observer confirms capacity or sensing is disabled; the test commitment is released"
                )
        else:
            if self.due_hour is None and hour >= self.next_eligible_hour:
                self.due_hour = hour + self.policy.maximum_wait_hours
            if failed:
                self.next_eligible_hour = hour + self.policy.retry_after_hours
                self.accepted = None
                changes.append(
                    "Actual tracking did not confirm the previous test; the window is interrupted and retry delay applies"
                )
            if receipts or increased:
                self.next_eligible_hour = hour
                self.accepted = None
                changes.append(
                    "Eligible procedure receipt or observer capacity change requires a new test window; the original deadline is retained"
                )
            if changed_continuation:
                self.accepted = None
                self.previous_probe = False
                self.next_eligible_hour = hour
                changes.append(
                    "Actual investigation follow-up changed; the previous test window is released before jointly scheduling its work and test"
                    if continuation
                    else "Investigation no longer nominates this test; the previous work-bound window is released"
                )
                if self.due_hour is None:
                    self.due_hour = hour + self.policy.maximum_wait_hours
            if continuation is not None and self.due_hour is not None:
                self.due_hour = min(self.due_hour, continuation.due_hour)
            if self.due_hour is not None and hour >= self.due_hour:
                status = "deadline-missed"
                self.accepted = None
                # A subsequent episode starts only after this explicit missed deadline.
                self.next_eligible_hour = hour + self.policy.retry_after_hours
            elif self.due_hour is None or hour < self.next_eligible_hour:
                status = "waiting-for-retry"
            if self.accepted and self.accepted["start_hour"] < hour:
                if self.previous_probe and diagnosis.recovery_count > 0:
                    # An informative consecutive prefix is consumed, not postponed.
                    pass
                else:
                    self.accepted = None
                    changes.append(
                        "Consecutive test evidence was interrupted; the old window is released without moving the deadline"
                    )
        self.pending = dict(
            version=JOINT_VERSION,
            status=status,
            receipts=receipts,
            probe_now=False,
            plan=None,
            due_hour=self.due_hour,
            next_eligible_hour=self.next_eligible_hour,
            previous_commitment=previous,
            commitment_changes=changes,
            previous_test_inconclusive_or_failed=failed,
            scope="Accepted test windows constrain work and charging until completion or an explicitly recorded interruption. Both delivery hypotheses share commands. Procedure completion never establishes recovered capacity; only actual observer evidence can do that.",
        )
        self.request = None
        if status == "ready":
            remaining = max(
                1,
                sensors.confirmation_hours
                - (diagnosis.recovery_count if self.previous_probe else 0),
            )
            self.request = Request(
                hour,
                diagnosis.capacity_kw,
                min(
                    plant.electrolyser_kw,
                    max(
                        plant.min_kw,
                        diagnosis.capacity_kw + plant.electrolyser_kw * sensors.probe_fraction,
                    ),
                ),
                remaining,
                self.due_hour,
                self.policy,
                max(hour, self.accepted["start_hour"]) if self.accepted else None,
                continuation,
            )
        self.previous_probe = False
        self.last_capacity = diagnosis.capacity_kw
        return self.request

    def finish(self, evaluated=None):
        if self.pending is None:
            raise ValueError("No recovery decision is pending")
        if evaluated is not None and (
            self.request is None or evaluated.get("request_id") != self.request.request_id
        ):
            raise ValueError("Recovery result belongs to a different request")
        result = copy.deepcopy(self.pending)
        if self.request is not None:
            result.update(
                evaluated
                or dict(
                    status="unresolved",
                    reason="No validated combined service, charge and test plan was selected",
                )
            )
            result["request"] = self.request.to_dict()
            result["request_id"] = self.request.request_id
            if result.get("status") == "scheduled" and result.get("plan"):
                self.accepted = dict(
                    start_hour=result["selected_start"],
                    end_hour=result["selected_start"] + self.request.required_hours,
                    target_kw=self.request.target_kw,
                    due_hour=self.request.due_hour,
                    accepted_at=self.accepted["accepted_at"]
                    if self.accepted
                    else self.request.hour,
                    **(
                        dict(
                            continuation_id=self.request.continuation.continuation_id,
                            work_order_id=self.request.continuation.work_order_id,
                            predicted_test_start=self.request.continuation.predicted_test_start,
                            origin=self.request.continuation.origin,
                        )
                        if self.request.continuation
                        else {}
                    ),
                )
                if (
                    self.request.continuation
                    and self.request.continuation.predicted_test_start != result["selected_start"]
                ):
                    result["commitment_changes"].append(
                        "The accepted test differs from the original conditional prediction after rechecking actual finding time, work completion and current resources; the original episode deadline remains unchanged"
                    )
                self.previous_probe = result["probe_now"]
            elif self.accepted:
                result["commitment_changes"].append(
                    "No validated continuation under current forecasts and accepted work; test commitment released, original deadline retained"
                )
                self.accepted = None
        if result["status"] == "deadline-missed":
            self.due_hour = None
        result["commitment"] = copy.deepcopy(self.accepted)
        self.pending, self.request = None, None
        return result
