"""Observation-driven scheduling of consecutive electrolyser load tests.

This controller never receives a FaultState, injected schedule or successful
repair effect. Both delivery profiles are declared hypotheses. Only the existing
observer can confirm a capacity increase after actual execution.
"""

import copy
from dataclasses import asdict, dataclass
from math import isfinite
from time import perf_counter

from methane.cancellation import checkpoint
from methane.services.scenario_planning import Branch, solve

JOINT_VERSION = "scheduled-load-tests/2"
LOOP_VERSION = "scheduled-load-tests/3"
WEATHER_VERSION = "scheduled-load-tests/4"
LOOP_VERSIONS = (LOOP_VERSION, WEATHER_VERSION)
JOINT_VERSIONS = (JOINT_VERSION, *LOOP_VERSIONS)


@dataclass(frozen=True)
class RecoveryPolicy:
    version: str = "scheduled-load-tests/1"
    maximum_wait_hours: int = 12
    retry_after_hours: int = 24
    battery_reserve_fraction: float = 0.1
    tracking_success_probability: float = 0.5
    risk_weight: float = 0.5

    def __post_init__(self):
        if self.version not in ("scheduled-load-tests/1", *JOINT_VERSIONS):
            raise ValueError("Unknown recovery planning policy")
        for name in ("maximum_wait_hours", "retry_after_hours"):
            v = getattr(self, name)
            if type(v) is not int or not 1 <= v <= 168:
                raise ValueError("Recovery waiting and retry periods must be 1–168 hours")
        for name in ("battery_reserve_fraction", "tracking_success_probability", "risk_weight"):
            v = getattr(self, name)
            if (
                isinstance(v, bool)
                or not isinstance(v, (int, float))
                or not isfinite(v)
                or not 0 <= v <= 1
            ):
                raise ValueError("Recovery fractions must be finite values between zero and one")
        if not 0 < self.tracking_success_probability < 1:
            raise ValueError("Both successful tracking and unchanged capacity must remain possible")


def outcomes(rows, truth, nameplate_kw):
    """Retrospective report derivation, never an input to the recovery scheduler."""
    derated = False
    restored = None
    for item in truth:
        if item["capacity_kw"] < nameplate_kw * 0.999:
            derated = True
        elif derated:
            restored = item["hour"]
            break
    seen_estimated_derating = False
    confirmed = None
    for row in rows:
        cap = row["diagnosis_after"]["capacity_kw"]
        if cap < nameplate_kw * 0.999:
            seen_estimated_derating = True
        elif seen_estimated_derating and restored is not None and row["hour"] >= restored:
            confirmed = row["hour"] + 1
            break
    scheduling = [
        row["decision"]["recovery_planning"]
        for row in rows
        if "recovery_planning" in row["decision"]
    ]
    result = dict(
        capacity_restored_hour=restored,
        capacity_confirmed_hour=confirmed,
        recovery_confirmation_delay_hours=confirmed - restored if confirmed is not None else None,
        recovery_probe_hours=sum(bool(row["decision"]["probe"]) for row in rows),
        recovery_deadline_misses=sum(r["status"] == "deadline-missed" for r in scheduling)
        if scheduling
        else None,
        recovery_candidate_solves=sum(len(r.get("candidate_windows", ())) for r in scheduling)
        if scheduling
        else None,
    )
    loops = [r for r in scheduling if r.get("version") in LOOP_VERSIONS]
    if loops:
        # Count receipt-defined windows once, using the latest recorded outcome.
        # Escalation can precede a completed mission, so intervals are separate.
        episodes = {
            tuple(e["receipt_ids"]): e for r in loops for e in r["verification_loop"]["episodes"]
        }
        result.update(
            recovery_episode_report_version="post-mission-outcomes/1",
            recovery_deadline_misses=None,
            recovery_verification_windows=len(episodes),
            recovery_verification_deadline_misses=sum(
                e.get("outcome") == "verification deadline missed" for e in episodes.values()
            ),
            recovery_observer_confirmed_windows=sum(
                e.get("outcome") == "observer confirmed" for e in episodes.values()
            ),
            recovery_escalation_hours=sum(r["status"] == "escalation-required" for r in loops),
        )
    return result


def compare(
    plant,
    state,
    diagnosis,
    forecast,
    costs,
    policy,
    *,
    hour,
    target_kw,
    required_hours,
    due_hour,
    objective,
    seconds,
    components=None,
    alternative=None,
    terminal_battery_value=0,
    charging_inputs=None,
    accepted_start=None,
    total_seconds=None,
    not_before_hour=None,
):
    """Earliest feasible consecutive test window under declared delivery hypotheses.

    The complete scenario horizon shares requested actions. There is no unearned
    information gain or capacity upgrade after the planned procedure. Real future
    decisions will observe and replan. Tests may use the plant battery, subject to
    power/energy constraints and an explicit ending reserve.
    """
    n = len(forecast["pv_kw"])
    base = diagnosis.capacity_kw
    if accepted_start is not None and (type(accepted_start) is not int or accepted_start < hour):
        raise ValueError("An accepted test must name this or a future decision interval")
    if not_before_hour is not None and (type(not_before_hour) is not int or not_before_hour < 0):
        raise ValueError("Service completion must identify an absolute hourly boundary")
    if total_seconds is not None and (
        isinstance(total_seconds, bool)
        or not isinstance(total_seconds, (int, float))
        or not isfinite(total_seconds)
        or total_seconds <= 0
    ):
        raise ValueError("Recovery comparison budget must be positive and finite")
    result = dict(
        version=policy.version,
        status="unresolved",
        candidate_windows=[],
        selected_start=None,
        probe_now=False,
        plan=None,
        inputs=dict(
            hour=hour,
            target_kw=target_kw,
            required_hours=required_hours,
            due_hour=due_hour,
            objective=objective,
            seconds=seconds,
            policy=asdict(policy),
            terminal_battery_value=terminal_battery_value,
            **(
                dict(
                    charging_inputs=charging_inputs.to_dict(),
                    fixed_service_kw=list(forecast.get("service_kw", [0] * n)),
                )
                if charging_inputs is not None
                else {}
            ),
            **(dict(accepted_start=accepted_start) if accepted_start is not None else {}),
            **(dict(not_before_hour=not_before_hour) if not_before_hour is not None else {}),
        ),
        scope="Earliest validated window for consecutive requested load tests. Successful tracking and unchanged delivery are explicit assumptions. Requested actions are shared throughout this horizon; only actual observations can update diagnosis. Fixed service work is held to its recorded schedule. No hidden fault identity, success draw or recovery time is consulted.",
    )
    if type(required_hours) is not int or required_hours < 1:
        raise ValueError(
            "A recovery test requires a positive whole number of informative intervals"
        )
    if not base < target_kw <= plant.electrolyser_kw or target_kw < plant.min_kw:
        raise ValueError("A recovery test must exceed the current estimate within operating bounds")
    last = min(n - required_hours, due_hour - hour - required_hours)
    first = max(0, (not_before_hour or hour) - hour)
    offsets = range(first, max(0, last + 1)) if accepted_start is None else [accepted_start - hour]
    started = perf_counter()
    for offset in offsets:
        if offset > last or offset < first:
            break
        checkpoint()
        remaining = seconds if total_seconds is None else total_seconds - (perf_counter() - started)
        if remaining <= 0:
            result["candidate_windows"].append(
                dict(
                    start_hour=hour + offset,
                    status="not-evaluated",
                    reason="Total recovery comparison budget exhausted",
                )
            )
            break
        minimum = [0] * n
        maximum = [base if base >= plant.min_kw else 0] * n
        success = [base] * n
        for t in range(offset, offset + required_hours):
            minimum[t] = maximum[t] = success[t] = target_kw
        source = "assumption:recovery-tracking-hypotheses/1"
        # Even beyond the test, no future observation is silently granted. These
        # forecasts preserve the original issue while varying possible delivery.
        branches = (
            Branch.create(
                "tracks-request",
                policy.tracking_success_probability,
                forecast,
                ("same-unobserved-history",) * n,
                source=source,
                delivery_capacity_kw=success,
            ),
            Branch.create(
                "unchanged-delivery",
                1 - policy.tracking_success_probability,
                forecast,
                ("same-unobserved-history",) * n,
                source=source,
                delivery_capacity_kw=[base] * n,
            ),
        )
        outcome = solve(
            plant,
            state,
            branches,
            base,
            costs,
            objective="methane" if objective == "greedy" else objective,
            risk_weight=policy.risk_weight,
            seconds=min(seconds, remaining),
            components=components,
            requested_minimum=minimum,
            requested_maximum=maximum,
            alternative=alternative,
            terminal_minimum={"battery_kwh": plant.battery_kwh * policy.battery_reserve_fraction},
            terminal_battery_value=terminal_battery_value,
            charging_inputs=charging_inputs,
        )
        result["candidate_windows"].append(
            dict(
                start_hour=hour + offset,
                end_hour=hour + offset + required_hours,
                status=outcome["status"],
                solver=outcome["solver"],
            )
        )
        if outcome["status"] != "feasible":
            continue
        nominal = outcome["branches"][0]
        plan = dict(
            actions=nominal["requested_actions"],
            trajectory=nominal["trajectory"],
            predicted=nominal["predicted"],
            solver=outcome["solver"],
            forecast=nominal["forecast"],
            **(nominal["charging_plan"] if charging_inputs is not None else {}),
            prediction_basis="Conditional tracking branch; uncertain delivered-power branches are retained in recovery_outcomes",
            recovery_outcomes=outcome,
        )
        result.update(
            status="scheduled", selected_start=hour + offset, probe_now=offset == 0, plan=plan
        )
        break
    if not result["candidate_windows"]:
        result["status"] = "no-window-before-deadline"
    return result


class RecoveryScheduler:
    """Episode timing from past observations and eligible public procedure receipts."""

    def __init__(self, policy):
        self.policy = policy
        self.due_hour = None
        self.next_eligible_hour = 0
        self.last_capacity = None
        self.previous_probe = False
        self.seen_receipts = set()

    def decide(
        self,
        plant,
        sensors,
        state,
        diagnosis,
        forecast,
        costs,
        *,
        hour,
        objective,
        seconds,
        components=None,
        service_decision=None,
        terminal_battery_value=0,
    ):
        policy = self.policy
        receipts = []
        for order in (service_decision or {}).get("orders", []):
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
        if not sensors.enabled or diagnosis.capacity_kw >= plant.electrolyser_kw * 0.999:
            self.due_hour = None
            self.previous_probe = False
            self.last_capacity = diagnosis.capacity_kw
            return dict(
                version=policy.version,
                status="inactive",
                probe_now=False,
                plan=None,
                receipts=receipts,
            )
        failed = (
            self.previous_probe
            and diagnosis.recovery_count == 0
            and self.last_capacity is not None
            and diagnosis.capacity_kw <= self.last_capacity + 1e-8
        )
        if failed:
            self.next_eligible_hour = hour + policy.retry_after_hours
            self.due_hour = None
        increased = (
            self.last_capacity is not None and diagnosis.capacity_kw > self.last_capacity + 1e-8
        )
        if receipts or increased:
            self.next_eligible_hour = hour
            self.due_hour = None
        was_probe = self.previous_probe
        self.last_capacity = diagnosis.capacity_kw
        self.previous_probe = False
        if hour < self.next_eligible_hour:
            return dict(
                version=policy.version,
                status="waiting-for-retry",
                next_eligible_hour=self.next_eligible_hour,
                probe_now=False,
                plan=None,
                receipts=receipts,
                reason="Previous actual test did not confirm tracking; no physical recovery is assumed",
            )
        if self.due_hour is None:
            self.due_hour = hour + policy.maximum_wait_hours
        if hour >= self.due_hour:
            self.next_eligible_hour = hour + policy.retry_after_hours
            deadline = self.due_hour
            self.due_hour = None
            return dict(
                version=policy.version,
                status="deadline-missed",
                due_hour=deadline,
                next_eligible_hour=self.next_eligible_hour,
                probe_now=False,
                plan=None,
                receipts=receipts,
            )
        target = min(
            plant.electrolyser_kw,
            max(
                plant.min_kw, diagnosis.capacity_kw + plant.electrolyser_kw * sensors.probe_fraction
            ),
        )
        remaining = max(
            1, sensors.confirmation_hours - (diagnosis.recovery_count if was_probe else 0)
        )
        result = compare(
            plant,
            state,
            diagnosis,
            forecast,
            costs,
            policy,
            hour=hour,
            target_kw=target,
            required_hours=remaining,
            due_hour=self.due_hour,
            objective=objective,
            seconds=seconds,
            components=components,
            terminal_battery_value=terminal_battery_value,
        )
        result["receipts"] = receipts
        result["previous_test_inconclusive_or_failed"] = failed
        result["subplanner_objective"] = "methane" if objective == "greedy" else objective
        self.previous_probe = result["probe_now"]
        return result
