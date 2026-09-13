"""Observation-contingent requests over the registered service executive.

Inspection predictions do not execute. Only a selected present request is
commissioned; its actual returned observations determine the later remedy.
"""

import copy
from dataclasses import asdict, dataclass, field, replace
from math import isfinite

from methane.services.coupling import identity
from methane.services.investigation_belief import Assumptions, Hypothesis, illustrative, update
from methane.services.investigation_planning import compare
from methane.services.snapshot import RecordedServices, capture

VERSION = "observed-service-investigation/1"
CONTINUATION_VERSION = "observed-service-investigation/2"
BELIEF_VERSION = "observed-service-investigation/3"


@dataclass(frozen=True)
class InvestigationPolicy:
    version: str = VERSION
    mode: str = "planned"
    reader: str = "fixed"
    assumptions: Assumptions = field(default_factory=illustrative)
    comparison_seconds: float = 1
    risk_weight: float = 0.2
    minimum_restoration_probability: float = 0.3
    observation_wait_hours: int = 12
    followup_impairment_probability: float | None = None

    def __post_init__(self):
        if self.version not in (VERSION, CONTINUATION_VERSION, BELIEF_VERSION) or self.mode not in (
            "planned",
            "inspect-first",
            "direct-intervention",
        ):
            raise ValueError("Unknown investigation policy or comparison arm")
        if self.reader not in ("fixed", "mobile"):
            raise ValueError("Choose a declared fixed or mobile investigation reader")
        if not isinstance(self.assumptions, Assumptions):
            value = copy.deepcopy(self.assumptions)
            value["hypotheses"] = tuple(Hypothesis(**h) for h in value["hypotheses"])
            object.__setattr__(self, "assumptions", Assumptions(**value))
        for key in ("comparison_seconds", "risk_weight", "minimum_restoration_probability"):
            value = getattr(self, key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{key} must be finite")
        if (
            not 0.05 <= self.comparison_seconds <= 60
            or not 0 <= self.risk_weight <= 1
            or not 0 <= self.minimum_restoration_probability <= 1
        ):
            raise ValueError("Invalid investigation comparison budget or probability")
        if (
            type(self.observation_wait_hours) is not int
            or not 1 <= self.observation_wait_hours <= 168
        ):
            raise ValueError("Observation wait must be one to 168 hours")
        threshold = self.followup_impairment_probability
        if self.version == BELIEF_VERSION:
            if threshold is None:
                threshold = 0.5
                object.__setattr__(self, "followup_impairment_probability", threshold)
            if (
                isinstance(threshold, bool)
                or not isinstance(threshold, (int, float))
                or not isfinite(threshold)
                or not 0 <= threshold <= 1
            ):
                raise ValueError("Follow-up impairment probability must be in [0, 1]")
        elif threshold is not None:
            raise ValueError(
                "An impairment-probability gate requires recovery belief follow-through"
            )


def proposal(rt, kind, incident, *, reader=None):
    """A private planning request; no ledger reservation or live backlog entry."""
    return dict(
        id="proposal-investigation",
        kind=kind,
        incident=incident,
        created_hour=rt.executive.at_hour,
        reason="Compare a current investigation request",
        sequence=1 + sum(q["kind"] == kind for q in rt.orders),
        section=None,
        status="queued",
        phase="queued",
        evidence=[asdict(r) for r in rt._context.readings],
        **(dict(reader=reader) if reader else {}),
    )


def preview(rt, request):
    packet = capture(rt)
    recorded = RecordedServices(packet["snapshot"], packet["catalogue"])
    recorded.orders.append(copy.deepcopy(request))
    try:
        recipe = dict(plan=rt._build(request).to_dict(), unavailable=None)
    except (KeyError, ValueError) as exc:
        recipe = dict(plan=None, unavailable=str(exc))
    recorded.recipes[request["id"]] = recipe
    return recorded, dict(**packet, proposed_request=copy.deepcopy(request), proposed_recipe=recipe)


class Investigator:
    def __init__(self, policy, service_policy):
        self.policy, self.limits = policy, service_policy
        self.episodes = {}
        self.current = None
        self.beliefs = {}

    def record_acceptance(self, evaluated):
        """Record the selected, rechecked operating window; no result is inferred."""
        nominated = self.current.get("test_obligation") if self.current else None
        if nominated is None:
            return self.current
        episode = next(e for e in self.episodes.values() if e["id"] == nominated["episode_id"])
        if evaluated is not None and evaluated.get("status") == "scheduled":
            original = evaluated["request"].get("continuation")
            if original != nominated:
                raise ValueError(
                    "Accepted operating window belongs to another investigation follow-up"
                )
            episode["continuation_status"] = "test window accepted"
            episode["accepted_test"] = dict(
                start_hour=evaluated["selected_start"],
                end_hour=evaluated["selected_start"] + evaluated["inputs"]["required_hours"],
                target_kw=evaluated["inputs"]["target_kw"],
                not_before_hour=evaluated["inputs"].get("not_before_hour"),
                due_hour=evaluated["inputs"]["due_hour"],
                request_id=evaluated["request_id"],
            )
        else:
            episode["continuation_status"] = "no joint continuation selected"
            episode.pop("accepted_test", None)
        self.current["episodes"] = copy.deepcopy(list(self.episodes.values()))
        self.current.pop("record_id", None)
        self.current["record_id"] = identity(self.current)
        return copy.deepcopy(self.current)

    def _queue(self, rt, episode, kind, reason, *, reader=None, previous=None):
        links = dict(investigation_id=episode["id"])
        if reader:
            links["reader"] = reader
        if previous:
            links["followup_of"] = previous["id"]
        request = rt._queue(kind, rt.executive.at_hour, episode["incident"], reason, **links)
        if request is None:
            old = next(
                q
                for q in reversed(rt.orders)
                if q["kind"] == kind and q.get("investigation_id") == episode["id"]
            )
            request = rt._repeat_order(old, reason, **{**links, "followup_of": old["id"]})
        episode["requests"].append(request["id"])
        episode["status"] = "work requested"
        if self.policy.version == BELIEF_VERSION:
            episode.pop("reason", None)
        return request["id"]

    def _select(self, rt, episode, plant, state, forecast, capacity, costs, prices, **kwargs):
        kind = "inspection-confirm" if self.policy.reader == "mobile" else "inspection"
        request = proposal(rt, kind, episode["incident"], reader=self.policy.reader)
        recorded, packet = preview(rt, request)
        assumptions = replace(self.policy.assumptions, epoch_start_hour=episode["created_hour"])
        try:
            comparison = compare(
                recorded,
                plant,
                state,
                forecast,
                capacity,
                costs,
                assumptions,
                request["id"],
                prices,
                seconds=self.policy.comparison_seconds,
                risk_weight=self.policy.risk_weight,
                **kwargs,
            )
        except ValueError as exc:
            comparison = dict(status="incomplete", reason=str(exc), strategies={})
        candidates = []
        for name, arm in comparison["strategies"].items():
            mass = sum(
                c["probability"] for c in arm.get("cases", ()) if c["restoration_hypothesis"]
            )
            score = arm.get("process", {}).get("solver", {}).get("objective_value")
            qualifies = (
                arm["status"] == "feasible"
                and score is not None
                and mass + 1e-10 >= self.policy.minimum_restoration_probability
            )
            candidates.append(
                dict(
                    strategy=name,
                    status=arm["status"],
                    score=score,
                    restoration_probability=mass,
                    eligible=qualifies,
                )
            )
        choices = [
            c
            for c in candidates
            if c["eligible"]
            and (self.policy.mode == "planned" or c["strategy"] == self.policy.mode)
        ]
        choice = min(choices, key=lambda c: (c["score"], c["strategy"]), default=None)
        record = dict(
            inputs=packet,
            comparison=comparison,
            candidates=candidates,
            selected=choice,
            restoration_requirement=self.policy.minimum_restoration_probability,
        )
        record["selection_id"] = identity(record)
        episode["selection"] = record
        if choice is None:
            episode.update(
                status="selection unresolved",
                reason="No evaluated arm has a validated incumbent and the declared restoration probability; no unpriced or unsupported remedy is substituted",
            )
            return None
        episode["selected_strategy"] = choice["strategy"]
        return self._queue(
            rt,
            episode,
            kind if choice["strategy"] == "inspect-first" else "module-replacement",
            "Selected from the original-information investigation comparison",
            reader=self.policy.reader if choice["strategy"] == "inspect-first" else None,
        )

    def step(
        self,
        rt,
        diagnosis,
        plant,
        state,
        forecast,
        capacity,
        costs,
        prices,
        *,
        verification=None,
        sensors=None,
        **kwargs,
    ):
        rt._require_prepared()
        if (
            rt.options.inspection_model != "referenced-contact/1"
            or rt._capacity_request_policy != "investigation"
        ):
            raise ValueError(
                "Investigation requires delegated capacity requests and referenced contact sensing"
            )
        now = int(rt.executive.at_hour)
        continuing = self.policy.version in (CONTINUATION_VERSION, BELIEF_VERSION)
        if continuing and "test_target_kw" not in kwargs:
            raise ValueError("Observed continuation requires the current bounded test target")
        unresolved = next(
            (
                e
                for e in reversed(tuple(self.episodes.values()))
                if e["status"] != "observer confirmed"
            ),
            None,
        )
        if (
            diagnosis.active_incident
            and capacity < 0.95 * plant.electrolyser_kw
            and diagnosis.incidents not in self.episodes
            and unresolved is None
        ):
            self.episodes[diagnosis.incidents] = dict(
                id=f"INV-{diagnosis.incidents}",
                incident=diagnosis.incidents,
                created_hour=now,
                due_hour=now + self.limits.maximum_wait_hours,
                status="selection pending",
                requests=[],
                deadline_missed_at=None,
                prior_epoch=now,
                prior_scope="Declared prior for a new observed incident, not learned incidence. It is never silently renewed after an intervention.",
            )
        episode = unresolved or self.episodes.get(diagnosis.incidents)
        force = None
        if episode:
            if self.policy.version == BELIEF_VERSION:
                from methane.services.recovery_belief import RecoveryBelief

                if sensors is None or not sensors.enabled:
                    raise ValueError("Recovery belief requires the current sensor model")
                if episode["id"] not in self.beliefs:
                    self.beliefs[episode["id"]] = RecoveryBelief(
                        replace(self.policy.assumptions, epoch_start_hour=episode["created_hour"]),
                        plant,
                        sensors,
                        rt.options,
                        capacity,
                        rt.config.repair_success_probability,
                    )
                episode["recovery_belief"] = self.beliefs[episode["id"]].advance(
                    rt._context,
                    rt.observed_module_procedures(),
                    (verification or {}).get("previous_test"),
                )
            orders = [
                q for q in rt.public()["orders"] if q.get("investigation_id") == episode["id"]
            ]
            restored = rt._context.latest("capacity-restored")
            if (
                restored
                and restored.quality == "usable"
                and restored.value is True
                and restored.measured_at >= episode["created_hour"]
            ):
                episode.update(status="observer confirmed")
                if self.policy.version == BELIEF_VERSION:
                    episode.pop("reason", None)
                episode.setdefault("confirmed_at", now)
            if now >= episode["due_hour"] and episode["status"] != "observer confirmed":
                episode.setdefault("escalated_at", now)
                episode.update(
                    status="escalation required",
                    reason="Original investigation deadline reached; impairment and outstanding work remain unresolved",
                )
                if episode["deadline_missed_at"] is None:
                    episode["deadline_missed_at"] = now
            if episode["status"] not in ("observer confirmed", "escalation required"):
                if not orders:
                    force = self._select(
                        rt, episode, plant, state, forecast, capacity, costs, prices, **kwargs
                    )
                else:
                    last = orders[-1]
                    if last["status"] == "queued":
                        force = last["id"]
                    elif last["kind"] in ("inspection", "inspection-confirm"):
                        assumptions = replace(
                            self.policy.assumptions, epoch_start_hour=episode["prior_epoch"]
                        )
                        belief = update(assumptions, rt._context, rt.options)
                        episode["belief"] = belief
                        observation = rt.inspection_evidence()
                        episode["finding"] = observation
                        if last["status"] == "failed":
                            force = self._queue(
                                rt,
                                episode,
                                "module-replacement",
                                "Observed inspection interruption; no contact finding inferred",
                                previous=last,
                            )
                        elif observation["quality"] == "usable" and belief["posterior"] is not None:
                            remedy = (
                                "reset" if observation["value"] is True else "module-replacement"
                            )
                            force = self._queue(
                                rt,
                                episode,
                                remedy,
                                "Compatible remedy selected from the actual eligible contact finding",
                                previous=last,
                            )
                        elif (
                            now >= last["created_hour"] + self.policy.observation_wait_hours
                            or belief["posterior"] is None
                        ):
                            episode.update(
                                status="escalation required",
                                escalated_at=now,
                                reason="Current findings are missing, ambiguous or outside the declared hypothesis support; no hidden cause inferred",
                            )
                        else:
                            episode["status"] = "awaiting eligible finding"
                    else:
                        episode["status"] = "awaiting operating verification"
                        episode["belief_after_intervention"] = (
                            "Declared procedure transitions and eligible measurements update the conditional belief; only the operating observer can confirm recovery"
                            if self.policy.version == BELIEF_VERSION
                            else "Original static prior is no longer applicable; continuation uses actual tests, not a silently reset posterior"
                        )
                        attempts = [
                            q for q in orders if q["kind"] in ("reset", "module-replacement")
                        ]
                        evidence = next(
                            (
                                a
                                for a in (verification or {}).get("attempts", ())
                                if a["order_id"] == last["id"]
                            ),
                            None,
                        )
                        episode["post_service_evidence"] = copy.deepcopy(evidence)
                        supported = (
                            evidence
                            and evidence["status"] == "follow-up supported"
                            and now >= evidence["supported_at"] + self.limits.retry_after_hours
                        )
                        if supported and self.policy.version == BELIEF_VERSION:
                            belief = episode["recovery_belief"]
                            probability = belief["restoration_probability"]
                            impairment = None if probability is None else 1 - probability
                            episode["followup_belief_gate"] = dict(
                                at_hour=now,
                                after_order_id=last["id"],
                                belief_id=belief["belief_id"],
                                impairment_probability=impairment,
                                threshold=self.policy.followup_impairment_probability,
                                eligible=impairment is not None
                                and impairment >= self.policy.followup_impairment_probability,
                                scope="Additional qualified work also requires the existing repeated resource-feasible shortfalls; this belief gate cannot verify recovery or override physical limits.",
                            )
                            supported = episode["followup_belief_gate"]["eligible"]
                            if impairment is None:
                                episode.update(
                                    status="escalation required",
                                    escalated_at=now,
                                    reason="Operating evidence is outside the declared recovery belief; no unsupported repair probability is substituted",
                                )
                            elif not supported:
                                episode["reason"] = (
                                    "Observed shortfalls require investigation, but the declared belief does not support another repair at its probability threshold; operating verification and the original deadline remain"
                                )
                        if last["status"] == "failed" or supported:
                            if len(attempts) >= self.limits.maximum_repair_attempts:
                                episode.update(
                                    status="escalation required",
                                    escalated_at=now,
                                    reason="Bounded intervention attempts exhausted; recovery is unverified",
                                )
                            elif last["status"] == "failed":
                                new = (
                                    rt.retry_failed(
                                        last["id"],
                                        "Observed interruption of qualified service; bounded retry under the original investigation deadline",
                                    )
                                    if last["kind"] == "module-replacement"
                                    else None
                                )
                                force = (
                                    new["id"]
                                    if new
                                    else self._queue(
                                        rt,
                                        episode,
                                        "module-replacement",
                                        "Interrupted reset; qualified intervention remains required",
                                        previous=last,
                                    )
                                )
                                if new:
                                    episode["requests"].append(new["id"])
                            else:
                                force = self._queue(
                                    rt,
                                    episode,
                                    "module-replacement",
                                    "Repeated resource-feasible post-service tests still fall short; qualified follow-up is permitted, not a proven diagnosis",
                                    previous=last,
                                )
        obligation = None
        if (
            continuing
            and episode
            and episode["status"] not in ("observer confirmed", "escalation required")
        ):
            from methane.services.continuation import promote

            actual_orders = [
                q for q in rt.public()["orders"] if q.get("investigation_id") == episode["id"]
            ]
            latest = actual_orders[-1] if actual_orders else None
            if (
                latest
                and latest["kind"] in ("reset", "module-replacement")
                and latest["status"] != "failed"
            ):
                existing = episode.get("test_obligation")
                if existing is None or existing["work_order_id"] != latest["id"]:
                    earlier = actual_orders[:-1]
                    followup = any(q["kind"] in ("reset", "module-replacement") for q in earlier)
                    observation = episode.get("finding") or {}
                    finding = (
                        "observed-follow-up"
                        if followup
                        else "not-inspected"
                        if episode["selected_strategy"] == "direct-intervention"
                        else "interrupted"
                        if earlier and earlier[-1]["status"] == "failed"
                        else "closed"
                        if observation.get("quality") == "usable"
                        and observation.get("value") is True
                        else "open"
                        if observation.get("quality") == "usable"
                        and observation.get("value") is False
                        else "unusable"
                    )
                    try:
                        promoted = promote(
                            episode,
                            latest,
                            finding=finding,
                            evidence=dict(
                                at_hour=now,
                                diagnosis=asdict(diagnosis),
                                finding=observation,
                                post_service=episode.get("post_service_evidence"),
                                preceding_order=earlier[-1] if earlier else None,
                            ),
                            test_hours=kwargs["test_hours"],
                            test_target_kw=kwargs["test_target_kw"],
                            followup=followup,
                        )
                        episode["test_obligation"] = promoted.to_dict()
                        episode["continuation_status"] = "awaiting joint acceptance"
                        episode.pop("continuation_error", None)
                    except ValueError as exc:
                        episode["continuation_status"] = "unresolved"
                        episode["continuation_error"] = str(exc)
                        episode.pop("test_obligation", None)
                obligation = episode.get("test_obligation")
        self.current = dict(
            implementation_id=self.policy.version,
            at_hour=now,
            policy=asdict(self.policy),
            episodes=copy.deepcopy(list(self.episodes.values())),
            required_current_request=force,
            **(dict(test_obligation=copy.deepcopy(obligation)) if continuing else {}),
            scope="Bounded observation-contingent service choice. Hypothetical branches never execute. Current work is rechecked jointly with dock and process demand. The conditional comparison is a decomposition prediction, not the executed process trajectory or guaranteed recovery. "
            + (
                "The recovery belief propagates declared intervention probabilities and actual measurements; only the independent operating observer confirms recovery."
                if self.policy.version == BELIEF_VERSION
                else "Static belief becomes inapplicable after intervention; only actual tracking can justify continuation and confirmation."
            ),
        )
        self.current["record_id"] = identity(self.current)
        return self.current
