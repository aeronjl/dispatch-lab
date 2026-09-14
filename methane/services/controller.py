"""Run-level service scheduling over observed work, charging and process MPC.

This is a bounded, receding-horizon decomposition. The existing executive still
creates compatible requests from observations and enforces physical execution.
The controller never receives injected causes, private outcomes or future truth.
"""

import copy
from dataclasses import asdict, dataclass
from math import isfinite
from time import perf_counter

from methane.cancellation import checkpoint
from methane.services import charge_control
from methane.services.contracts import available_boundary
from methane.services.core import ASSETS
from methane.services.coupling import decision_key, identity
from methane.services.pricing import recorded_inputs

VERSION = "coordinated-services/1"
VISIT_VERSION = "coordinated-services/2"
VERIFICATION_VERSION = "coordinated-services/3"
OPTIONAL = {"cleaning", "portable-cleaning", "routine-service"}
RETRYABLE = {"module-replacement", "flow-calibration", "hardware-replacement"}


@dataclass(frozen=True)
class ServicePolicy:
    version: str = VERSION
    maximum_wait_hours: int = 24
    retry_after_hours: int = 2
    maximum_repair_attempts: int = 2
    charging_wait_hours: int = 6
    robot_reserve_fraction: float = 0.25
    maximum_candidates: int = 8
    comparison_seconds: float = 2

    def __post_init__(self):
        if self.version not in (VERSION, VISIT_VERSION, VERIFICATION_VERSION):
            raise ValueError("Unknown coordinated service policy")
        for key, upper in (
            ("maximum_wait_hours", 168),
            ("retry_after_hours", 168),
            ("maximum_repair_attempts", 8),
            ("charging_wait_hours", 168),
            ("maximum_candidates", 32),
        ):
            value = getattr(self, key)
            if type(value) is not int or not 1 <= value <= upper:
                raise ValueError(f"{key} must be a whole number from 1 to {upper}")
        for key in ("robot_reserve_fraction", "comparison_seconds"):
            value = getattr(self, key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{key} must be finite")
        if not 0 <= self.robot_reserve_fraction <= 1 or not 0.05 <= self.comparison_seconds <= 60:
            raise ValueError("Robot reserve must be 0–1; comparison budget must be .05–60 seconds")


class ServiceController:
    def __init__(self, policy, *, investigation=None):
        self.policy = policy
        self.obligations = {}
        self.energy_targets = {}
        self.target_history = []
        self.last_status = None
        self.verifier = None
        self.verification = None
        self.investigator = None
        self.inactive_investigation_requests = set()
        if investigation is not None:
            from methane.services.investigator import Investigator

            if policy.version != VERIFICATION_VERSION:
                raise ValueError("Investigation requires measured post-service follow-up")
            self.investigator = Investigator(investigation, policy)

    def _visit_windows(self, rt, orders, now, n):
        """Bounded contiguous groups in priority order, never future work.

        Keep at most eight currently compatible crew requests. This is a
        reproducible proposal family, not a route optimizer. Every omitted
        request and rejected group remains visible in the decision record.
        """
        pool, rejected, omitted = [], [], []
        for order in orders:
            checkpoint()
            try:
                plan = rt._build(order)
            except (ValueError, KeyError):
                continue  # Individual prescreen retains the prerequisite error.
            if plan.asset.asset_id != ASSETS["crew"]:
                continue
            if len(pool) == 8:
                omitted.append("visit-pool:" + order["id"])
            else:
                pool.append(order["id"])
        windows = []
        for size in range(2, min(rt.options.visit_max_jobs, len(pool)) + 1):
            for index in range(len(pool) - size + 1):
                keys = tuple(pool[index : index + size])
                possible, reasons = [], set()
                for offset in range(n):
                    checkpoint()
                    try:
                        plan, assessment = rt.propose_visit(keys, starting_at=now + offset)
                        if not assessment["feasible"]:
                            reasons.update(assessment["reasons"])
                        elif plan.ending_at > now + n:
                            reasons.add(
                                "Shared work including return exceeds the comparison horizon"
                            )
                        else:
                            possible.append((now + offset, plan.ending_at))
                    except (ValueError, KeyError) as exc:
                        reasons.add(str(exc))
                rejected.extend(dict(order_ids=list(keys), reason=r) for r in sorted(reasons))
                if possible:
                    indices = sorted({0, len(possible) // 2, len(possible) - 1})
                    windows.append((keys, [possible[i] for i in indices]))
        return windows, rejected, omitted

    def _work(self, rt):
        now = rt.executive.at_hour
        public = rt.public()["orders"]
        for order in public:
            if self.investigator and order.get("investigation_id"):
                continue  # Its episode, rather than a single mission, owns recovery.
            if order["kind"] in OPTIONAL:
                continue
            root = order.get("obligation_origin", order["id"])
            if root not in self.obligations:
                self.obligations[root] = dict(
                    id=root,
                    kind=order["kind"],
                    created_hour=order["created_hour"],
                    due_hour=order["created_hour"] + self.policy.maximum_wait_hours,
                    attempts=[],
                    status="pending",
                    deadline_missed_at=None,
                )
            task = self.obligations[root]
            if order["id"] not in task["attempts"]:
                task["attempts"].append(order["id"])
            if order["id"] != task["attempts"][-1]:
                continue
            task["status"] = order["status"]
            task["current_order_id"] = order["id"]
            task["latest_reason"] = order.get("blocked")
            if order["status"] in ("verified", "completed"):
                task["satisfied_at"] = (
                    order.get("verified_at_hour") or order.get("completed_hour") or now
                )
                continue
            if now >= task["due_hour"] and task["deadline_missed_at"] is None:
                task["deadline_missed_at"] = now
                rt.messages.append(
                    dict(
                        hour=now,
                        component="services",
                        label=f"Service deadline missed: {root}; obligation remains open",
                    )
                )
            if task.get("escalated_at") is not None:
                task["status"] = "escalation-required"
                continue
            if (
                self.verification is not None
                and order["kind"] == "module-replacement"
                and order["status"] == "awaiting verification"
            ):
                evidence = next(
                    (a for a in self.verification["attempts"] if a["order_id"] == order["id"]),
                    None,
                )
                task["verification"] = copy.deepcopy(evidence)
                if evidence and evidence["status"] == "follow-up supported":
                    if len(task["attempts"]) >= self.policy.maximum_repair_attempts:
                        task.update(
                            status="escalation-required",
                            escalated_at=now,
                            latest_reason="Repeated post-service tests still fall short and the repair attempt budget is exhausted; recovery remains unverified",
                        )
                    elif now >= evidence["supported_at"] + self.policy.retry_after_hours:
                        new = rt.followup_unverified(order["id"], self.verification)
                        task["attempts"].append(new["id"])
                        task.update(current_order_id=new["id"], status="queued")
                continue
            if order["status"] != "failed" or order["kind"] not in RETRYABLE:
                continue
            if len(task["attempts"]) >= self.policy.maximum_repair_attempts:
                task["status"] = "escalation-required"
                if self.policy.version == VERIFICATION_VERSION:
                    task["escalated_at"] = now
                task["latest_reason"] = (
                    "Configured repair attempt budget exhausted; no automatic resolution claimed"
                )
                continue
            mission = rt.executive.missions[order["id"]]
            failed_at = available_boundary(
                mission.interrupted_at if mission.interrupted_at is not None else now
            )
            if now >= failed_at + self.policy.retry_after_hours:
                new = rt.retry_failed(
                    order["id"],
                    "Observed interrupted repair remains required; retry under its original obligation deadline",
                )
                task["attempts"].append(new["id"])
                task.update(current_order_id=new["id"], status="queued")

    def _targets(self, rt, n):
        now = rt.executive.at_hour
        required = {}
        for name in ("cleaner", "rover"):
            if ASSETS[name] in rt.registry.assets:
                required[name] = self.policy.robot_reserve_fraction * getattr(
                    rt.config, name + "_battery_kwh"
                )
        # A failed resource assessment may still expose an exact registered
        # mission's energy need. No future delivery or successful repair enters it.
        for order in rt.orders:
            if order["status"] != "queued":
                continue
            try:
                _, assessment = rt.propose(order["id"])
            except (ValueError, KeyError):
                continue
            for quantity in assessment["requested_stocks"]:
                name = quantity["resource"].removeprefix("energy:")
                if name in required:
                    required[name] = max(required[name], quantity["amount"])
        targets = []
        for name, need in required.items():
            energy = rt.ledger.stock["energy:" + name]
            existing = self.energy_targets.get(name)
            if existing and energy >= existing["energy_kwh"] - 1e-7:
                self.target_history.append(
                    {**existing, "satisfied_at": now, "late": now > existing["due_hour"]}
                )
                del self.energy_targets[name]
                existing = None
            if energy < need - 1e-7 and existing is None:
                existing = dict(
                    robot=name,
                    energy_kwh=need,
                    created_hour=now,
                    due_hour=available_boundary(now) + self.policy.charging_wait_hours,
                    reason="Observed registered work energy or declared operating reserve",
                )
                self.energy_targets[name] = existing
            elif existing and need > existing["energy_kwh"]:
                existing["energy_kwh"] = (
                    need  # New work may tighten amount, never postpone deadline.
                )
            if existing and existing["due_hour"] <= now + n:
                targets.append(
                    charge_control.Target(
                        name, existing["energy_kwh"], existing["due_hour"], existing["reason"]
                    )
                )
            else:
                targets.append(
                    charge_control.Target(
                        name,
                        0,
                        int(now + n),
                        "Inventory tracked; no energy target due inside this horizon",
                    )
                )
        return targets

    def _candidates(self, rt, forecast):
        now, n = rt.executive.at_hour, len(forecast["pv_kw"])
        queued = {
            o["id"]
            for o in rt.orders
            if o["status"] == "queued" and o["id"] not in self.inactive_investigation_requests
        }
        due = {
            t["current_order_id"]: t["due_hour"]
            for t in self.obligations.values()
            if t["current_order_id"] in queued and t["due_hour"] <= now + n
        }
        orders = sorted(
            (o for o in rt.orders if o["id"] in queued),
            key=lambda o: (
                o["id"] not in due,
                due.get(o["id"], float("inf")),
                o["created_hour"],
                o["id"],
            ),
        )
        candidates = [dict(id="retain", selections=())]
        rejected = []
        windows = []
        for order in orders:
            checkpoint()
            possible = []
            for offset in range(n):
                try:
                    plan, assessment = rt.propose(order["id"], starting_at=now + offset)
                    if not assessment["feasible"]:
                        reason = "; ".join(assessment["reasons"])
                    elif plan.ending_at > now + n:
                        reason = "New work including return exceeds the comparison horizon"
                    else:
                        possible.append((now + offset, plan.ending_at))
                        continue
                except (ValueError, KeyError) as exc:
                    reason = str(exc)
                # Record each reason once per order; the actual evaluated
                # candidates retain full interval/quantity constraints.
                item = dict(order_id=order["id"], reason=reason)
                if item not in rejected:
                    rejected.append(item)
            if possible:
                # Bounded early/middle/late proposals, explicitly not exhaustive.
                indices = sorted({0, len(possible) // 2, len(possible) - 1})
                windows.append((order, [possible[i] for i in indices]))
        visit_windows, group_omissions = [], []
        if self.policy.version in (VISIT_VERSION, VERIFICATION_VERSION):
            visit_windows, visit_rejected, group_omissions = self._visit_windows(rt, orders, now, n)
            rejected.extend(visit_rejected)
        # Round-robin gives each feasible request an earliest candidate before
        # later starts consume the finite solver budget.
        for round_index in range(3):
            # Interleave single and shared alternatives so neither consumes
            # the whole finite comparison budget before the other is offered.
            for index in range(max(len(windows), len(visit_windows))):
                if index < len(windows):
                    order, possible = windows[index]
                    if round_index < len(possible):
                        start, end = possible[round_index]
                        candidates.append(
                            dict(
                                id=f"{order['id']}@{start:g}",
                                selections=((order["id"], start),),
                                completion_at=end,
                            )
                        )
                if index < len(visit_windows):
                    keys, possible = visit_windows[index]
                    if round_index < len(possible):
                        start, end = possible[round_index]
                        candidates.append(
                            dict(
                                id=f"visit:{'+'.join(keys)}@{start:g}",
                                selections=(),
                                visit_groups=((keys, start),),
                                completion_at=end,
                            )
                        )
        limit = self.policy.maximum_candidates
        omitted = [*group_omissions, *[c["id"] for c in candidates[limit:]]]
        return candidates[:limit], due, rejected, omitted

    def decide(
        self,
        rt,
        plant,
        state,
        forecast,
        capacity_kw,
        costs,
        prices,
        *,
        prefix=(),
        objective="methane",
        seconds=0.5,
        components=None,
        reference_forecast=None,
        terminal_battery_value=0,
        sensors=None,
        observed_interval=None,
        diagnosis=None,
        recovery_request=None,
        recovery_scheduler=None,
    ):
        checkpoint()
        rt._require_prepared()
        if recovery_scheduler is not None and (
            recovery_request is not None or diagnosis is None or sensors is None
        ):
            raise ValueError(
                "A joint recovery executive needs current diagnosis/sensors and owns its single request"
            )
        if (
            self.policy.version in (VISIT_VERSION, VERIFICATION_VERSION)
            and not rt.options.visit_bundling_enabled
        ):
            raise ValueError("Joint-visit service planning requires enabled visit bundling")
        if self.policy.version == VERIFICATION_VERSION:
            from methane.services.verification import Followup, assess

            if sensors is None or not sensors.enabled:
                raise ValueError("Post-service follow-up requires enabled observed load tests")
            if self.verifier is None:
                self.verifier = Followup(
                    sensors.confirmation_hours,
                    self.policy.maximum_wait_hours,
                    include_resets=self.investigator is not None,
                )
            evidence = (
                assess(plant, sensors, observed_interval, components=components)
                if observed_interval is not None
                else None
            )
            self.verification = self.verifier.advance(
                int(rt.executive.at_hour), rt.public()["orders"], evidence
            )
        elif observed_interval is not None:
            raise ValueError("Post-service test evidence requires the version-3 service policy")
        cost_inputs = recorded_inputs(prefix)
        prefix = cost_inputs["rows"]
        investigation = None
        if self.investigator:
            if diagnosis is None:
                raise ValueError("Investigation requires current diagnostic observations")
            investigation = self.investigator.step(
                rt,
                diagnosis,
                plant,
                state,
                forecast,
                capacity_kw,
                costs,
                prices,
                verification=self.verification,
                sensors=sensors,
                prefix=prefix,
                objective=objective,
                components=components,
                reference_forecast=reference_forecast,
                test_hours=sensors.confirmation_hours,
                **(
                    dict(
                        test_target_kw=min(
                            plant.electrolyser_kw,
                            max(
                                plant.min_kw,
                                capacity_kw + plant.electrolyser_kw * sensors.probe_fraction,
                            ),
                        )
                    )
                    if self.investigator.policy.version
                    in ("observed-service-investigation/2", "observed-service-investigation/3")
                    else {}
                ),
            )
            self.inactive_investigation_requests = {
                key
                for episode in investigation["episodes"]
                if episode["status"] in ("observer confirmed", "escalation required")
                for key in episode["requests"]
            }
        if recovery_scheduler is not None:
            from methane.services.continuation import Continuation

            nominated = investigation.get("test_obligation") if investigation else None
            recovery_request = recovery_scheduler.begin(
                plant,
                sensors,
                diagnosis,
                hour=int(rt.executive.at_hour),
                orders=rt.public()["orders"],
                continuation=Continuation.from_dict(nominated) if nominated else None,
                **(
                    dict(
                        state=state,
                        forecast=forecast,
                        costs=costs,
                        seconds=seconds,
                        components=components,
                    )
                    if recovery_scheduler.policy.version
                    in ("scheduled-load-tests/4", "scheduled-load-tests/5")
                    else {}
                ),
                **(
                    dict(evidence=self.verification["previous_test"] if self.verification else None)
                    if recovery_scheduler.policy.version
                    in (
                        "scheduled-load-tests/3",
                        "scheduled-load-tests/4",
                        "scheduled-load-tests/5",
                    )
                    else {}
                ),
            )
        self._work(rt)
        if recovery_scheduler is not None and recovery_scheduler.pending.get(
            "verification_loop", {}
        ).get("escalation_required"):
            for task in self.obligations.values():
                if task["status"] == "awaiting verification":
                    task.update(
                        status="escalation-required",
                        escalated_at=rt.executive.at_hour,
                        latest_reason="The recorded verification window expired without observed recovery; no repair success is inferred",
                    )
        targets = self._targets(rt, len(forecast["pv_kw"]))
        candidates, due, rejected, omitted = self._candidates(rt, forecast)
        required = investigation["required_current_request"] if investigation else None
        if required:
            # The branch comparison assumes its first request starts now.
            # A delayed/bundled first request is a different prediction.
            candidates = [
                c
                for c in candidates
                if c["selections"] == ((required, rt.executive.at_hour),)
                and not c.get("visit_groups")
            ]
            if not candidates:
                candidates = [
                    dict(
                        id=f"{required}@{rt.executive.at_hour:g}",
                        selections=((required, rt.executive.at_hour),),
                        completion_at=float("inf"),
                    )
                ]
        key = decision_key(rt)
        context = dict(
            policy=asdict(self.policy),
            decision_key=key,
            plant=asdict(plant),
            state=asdict(state),
            forecast=forecast,
            capacity_kw=capacity_kw,
            costs=asdict(costs),
            prices=prices,
            objective=objective,
            targets=[asdict(t) for t in targets],
            obligations=copy.deepcopy(list(self.obligations.values())),
            reference_forecast=reference_forecast,
            terminal_battery_value=terminal_battery_value,
            service_cost_prefix={key: value for key, value in cost_inputs.items() if key != "rows"},
            **(
                dict(recovery_request=recovery_request.to_dict())
                if recovery_request is not None
                else {}
            ),
        )
        results = []
        best = None
        started = perf_counter()
        for candidate in candidates:
            checkpoint()
            remaining = self.policy.comparison_seconds - (perf_counter() - started)
            if remaining <= 0:
                results.append(
                    dict(
                        candidate_id=candidate["id"],
                        status="not-evaluated",
                        reason="Total comparison budget exhausted",
                    )
                )
                continue
            evaluated = charge_control.evaluate(
                rt,
                plant,
                state,
                forecast,
                capacity_kw,
                costs,
                targets,
                service_prices=prices,
                recorded_prefix=prefix,
                objective=objective,
                seconds=min(seconds, remaining),
                components=components,
                terminal_battery_value=terminal_battery_value,
                selections=candidate["selections"],
                joint_work=True,
                reference_forecast=reference_forecast,
                recovery_request=recovery_request,
                **(
                    {"visit_groups": candidate["visit_groups"]}
                    if candidate.get("visit_groups")
                    else {}
                ),
            )
            chosen_orders = {key for key, _ in candidate["selections"]}
            chosen_orders.update(
                key for keys, _ in candidate.get("visit_groups", ()) for key in keys
            )
            met = {
                key
                for key in chosen_orders
                if key in due and candidate.get("completion_at", float("inf")) <= due[key]
            }
            # Once a deadline is missed, useful late work still has priority.
            progressing = chosen_orders & due.keys()
            rank = (
                len(set(due) - progressing),
                sum(due[k] for k in progressing),
                len(set(due) - met),
                evaluated.get("score", float("inf")),
                candidate["id"],
            )
            row = dict(
                candidate_id=candidate["id"],
                status=evaluated["state"],
                evaluation=evaluated,
                unmet_deadlines=sorted(set(due) - met),
                progressing_obligations=sorted(progressing),
            )
            results.append(row)
            if evaluated["state"] == "feasible" and (best is None or rank < best[0]):
                best = (rank, row)
        checkpoint()
        if decision_key(rt) != key:
            raise ValueError("Service selection belongs to a stale decision")
        decision = dict(
            implementation_id=self.policy.version,
            input_id=identity(context),
            inputs=context,
            candidates=results,
            prescreen_rejections=rejected,
            omitted_candidates=omitted,
            obligations=copy.deepcopy(list(self.obligations.values())),
            energy_targets=copy.deepcopy(self.energy_targets),
            fulfilled_energy_targets=copy.deepcopy(self.target_history),
            seconds=perf_counter() - started,
            scope="Bounded early/middle/late single-request scheduling with joint current charging and process MPC. Due essential work has explicit priority over optional profit; missed deadlines remain unmet. Conditional cleaning continuation, no inferred repair success or value of unknown findings. Current registered recipes/resources are rechecked. New visits are separate; local baseline retains its bundling rule. Multi-job contingent remedies, failure scenarios and fleet optimization remain outside this policy version.",
        )
        if self.policy.version in (VISIT_VERSION, VERIFICATION_VERSION):
            decision["scope"] = (
                "Bounded early/middle/late scheduling with joint charging and process MPC. "
                "Single requests and contiguous shared crew groups use the first eight compatible "
                "queued crew requests in priority order, up to the configured visit size. Other "
                "groups, permutations and future jobs are not searched. Due essential work has "
                "explicit priority; completion deadlines include the whole shared return. "
                "Shared journeys and callouts retain separate work effects, stock and verification. "
                "Continuation is conditional: an interruption may prevent later visit jobs. "
                "No inferred repair success, value of unknown findings, risk optimization or "
                "global fleet optimality. Current recipes/resources are rechecked at acceptance."
            )
        if self.verification is not None:
            decision["verification"] = copy.deepcopy(self.verification)
            decision["scope"] += (
                " Completed unverified module substitutions may receive a separate compatible "
                "follow-up after repeated same-load shortfalls within the declared evidence window. "
                "Actual observations, resource feasibility, retry delay and original attempt/deadline "
                "limits apply. Inconclusive tests do not justify a repeat. The physical cause and "
                "future recovery remain unknown. Inspection-contingent action selection is separate."
            )
        if investigation is not None:
            decision["investigation"] = investigation
            decision["scope"] += (
                " The opt-in investigation port selects present requests from explicit finding branches. Its episode deadline and unverified health remain separate from completed individual work. Actual process dispatch is solved again against accepted work; conditional test schedules are predictions, not accepted future commitments."
            )
        selected_recovery = None
        if best and (not due or best[1]["progressing_obligations"]):
            selected = best[1]
            ev = selected["evaluation"]
            power = charge_control.accept(rt, ev)
            decision.update(
                status="selected-with-unmet-obligations"
                if selected["unmet_deadlines"]
                else "selected",
                selected_candidate_id=selected["candidate_id"],
                unmet_deadlines=selected["unmet_deadlines"],
                fallback_used=False,
            )
            selected_forecast, planned = ev["forecast"], ev["process_plan"]
            selected_recovery = ev.get("recovery_planning")
        else:
            # Preserve accepted obligations and make current feasible essential
            # progress. Optional work never bundles a repair into its interruption.
            ready = []
            for order in sorted(
                rt.orders,
                key=lambda o: (
                    o["id"] != required if required else False,
                    o["kind"] in OPTIONAL,
                    o["created_hour"],
                    o["id"],
                ),
            ):
                if order["status"] != "queued" or order["kind"] in OPTIONAL:
                    continue
                if order["id"] in self.inactive_investigation_requests:
                    continue
                try:
                    _, assessment = rt.propose(order["id"])
                    if assessment["feasible"]:
                        ready.append((order["id"], rt.executive.at_hour))
                        break
                except (ValueError, KeyError):
                    pass
            power = rt.dispatch_selected(
                ready, charge=True, projection_hours=len(forecast["pv_kw"])
            )
            selected_forecast = copy.deepcopy(forecast)
            demand = rt.planned_demands(len(forecast["pv_kw"]))
            selected_forecast.update(
                service_kw=[r["bus_kwh"] for r in demand["rows"]],
                electrolyser_isolated=rt.isolation_horizon(len(forecast["pv_kw"])),
            )
            planned = None
            decision.update(
                status="fallback",
                selected_candidate_id=None,
                unmet_deadlines=sorted(due),
                fallback_used=True,
                fallback_reason="No validated combined incumbent; current feasible essential recipe plus local charging; process planner must solve against actual commitments",
            )
        decision["applied_service_kw"] = power
        if self.investigator is not None and investigation.get("test_obligation") is not None:
            decision["investigation"] = self.investigator.record_acceptance(selected_recovery)
        if recovery_request is not None:
            decision["scope"] += (
                " The version-2 recovery request constrains the same candidate solve, including dock power and original test/charge deadlines. A missing incumbent triggers an explicit unresolved test and feasible essential-work fallback."
            )
        rt.interval["decision"]["service_control"] = copy.deepcopy(decision)
        status = (decision["status"], tuple(decision["unmet_deadlines"]))
        if status != self.last_status and (
            decision["fallback_used"] or decision["unmet_deadlines"]
        ):
            rt.messages.append(
                dict(
                    hour=rt.executive.at_hour,
                    component="services",
                    label="Service planning: " + decision["status"],
                )
            )
        self.last_status = status
        return dict(
            forecast=selected_forecast,
            plan=planned,
            decision=decision,
            service_kw=power,
            **(dict(recovery_planning=selected_recovery) if recovery_request is not None else {}),
        )
