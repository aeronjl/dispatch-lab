"""Observed handoff from a conditional remedy prediction to operating tests.

Consensus is taken across every remaining latent branch. A private restoration
outcome is never selected to obtain a convenient test schedule.
"""

import json
from dataclasses import asdict, dataclass
from math import isfinite

from methane.services.contracts import available_boundary, identifier
from methane.services.coupling import identity

VERSION = "observed-investigation-continuation/1"


@dataclass(frozen=True)
class Continuation:
    episode_id: str
    work_order_id: str
    action: str
    created_hour: int
    due_hour: int
    test_hours: int
    test_target_kw: float
    predicted_test_start: int | None
    selection_id: str
    finding: str
    branch_ids: tuple[str, ...]
    evidence_json: str
    origin: str = "conditional-branch-consensus"
    version: str = VERSION

    def __post_init__(self):
        for v in (self.episode_id, self.work_order_id, self.selection_id):
            identifier(v, "investigation continuation")
        if self.version != VERSION or self.action not in ("reset", "module-replacement"):
            raise ValueError("Only a registered intervention can nominate its operating test")
        if (
            any(type(v) is not int for v in (self.created_hour, self.due_hour, self.test_hours))
            or self.created_hour < 0
            or self.due_hour <= self.created_hour
            or not 1 <= self.test_hours <= 8
        ):
            raise ValueError("Continuation needs an original finite deadline and test duration")
        if self.predicted_test_start is not None and (
            type(self.predicted_test_start) is not int or self.predicted_test_start < 0
        ):
            raise ValueError("Predicted test boundary must remain an original absolute hour")
        if (
            isinstance(self.test_target_kw, bool)
            or not isinstance(self.test_target_kw, (int, float))
            or not isfinite(self.test_target_kw)
            or self.test_target_kw <= 0
        ):
            raise ValueError("Continuation requires a finite positive requested test load")
        if type(self.branch_ids) is not tuple or any(
            not isinstance(v, str) for v in self.branch_ids
        ):
            raise ValueError("Original branch identities must be immutable")
        if self.origin not in ("conditional-branch-consensus", "observed-follow-up"):
            raise ValueError("Unknown operating-test justification")
        if self.origin == "conditional-branch-consensus" and not self.branch_ids:
            raise ValueError("A conditional handoff needs its original possible branches")
        json.loads(self.evidence_json)

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, value):
        return cls(**{**value, "branch_ids": tuple(value["branch_ids"])})

    @property
    def continuation_id(self):
        return identity(self.to_dict())


def promote(episode, order, *, finding, evidence, test_hours, test_target_kw, followup=False):
    """Bind actual work to a finding-level consensus or observed follow-up.

    Caller supplies current eligible evidence and an actually queued request.
    This creates no mission, future observation, repair effect or stock credit.
    """
    now = evidence.get("at_hour")
    if type(now) is not int or now < 0 or not 0 <= order["created_hour"] <= now:
        raise ValueError("Continuation requires an actual request at the current evidence boundary")
    previous = evidence.get("preceding_order") or {}
    observed = evidence.get("finding") or {}
    channels = observed.get("channels", ())
    if any(
        not 0
        <= channel.get("measured_at", float("inf"))
        <= channel.get("available_at", float("inf"))
        <= now
        for channel in channels
        if channel.get("quality") != "missing"
    ):
        raise ValueError("A finding cannot use unavailable or future observations")
    if finding in ("closed", "open") and (
        observed.get("quality") != "usable"
        or observed.get("value") is not (finding == "closed")
        or not channels
    ):
        raise ValueError("The nominated finding must match actual eligible contact evidence")
    if finding == "interrupted" and previous.get("status") != "failed":
        raise ValueError("An interrupted finding needs an observed failed inspection")
    if followup:
        post = evidence.get("post_service") or {}
        tests = post.get("qualifying", ())
        supported = (
            post.get("order_id") == previous.get("id")
            and post.get("status") == "follow-up supported"
            and 0 <= post.get("supported_at", float("inf")) <= now
            and len(tests) >= test_hours
            and len({t.get("evidence_id") for t in tests}) == len(tests)
            and all(
                t.get("outcome") == "tracking shortfall"
                and t.get("evidence_id")
                and 0 <= t.get("hour", float("inf")) < t.get("available_at", float("inf")) <= now
                for t in tests
            )
        )
        if (
            previous.get("id") != order.get("followup_of")
            or previous.get("investigation_id") != episode["id"]
            or previous.get("kind") not in ("reset", "module-replacement")
            or not 0 <= previous.get("created_hour", float("inf")) <= now
            or not (previous.get("status") == "failed" or supported)
        ):
            raise ValueError("Follow-up requires observed interruption or eligible repeated tests")
    selection = episode.get("selection") or {}
    if order.get("investigation_id") != episode["id"] or order["kind"] not in (
        "reset",
        "module-replacement",
    ):
        raise ValueError("Operating test must follow this investigation's actual work order")
    cases = []
    if not followup:
        strategy = episode["selected_strategy"]
        arm = selection["comparison"]["strategies"][strategy]
        cases = [
            c for c in arm.get("cases", ()) if c["finding"] == finding and c["probability"] > 0
        ]
        signatures = {
            (
                c["requested_remedy"],
                c["test_start_hour"],
                c["test_end_hour"] - c["test_start_hour"],
                c["test_target_kw"],
            )
            for c in cases
        }
        if len(signatures) != 1:
            raise ValueError(
                "No unanimous original remedy/test continuation for this observed finding"
            )
        action, start, duration, target = next(iter(signatures))
        if action != order["kind"] or duration != test_hours:
            raise ValueError(
                "Actual remedy or test duration differs from the conditional prediction"
            )
    else:
        # A post-intervention static prior is deliberately not reconstructed.
        start, duration, target = None, test_hours, test_target_kw
    return Continuation(
        episode["id"],
        order["id"],
        order["kind"],
        now,
        episode["due_hour"],
        duration,
        target,
        start,
        selection.get("selection_id") or identity(evidence),
        finding,
        tuple(c["branch_id"] for c in cases),
        json.dumps(evidence, sort_keys=True, allow_nan=False),
        origin="observed-follow-up" if followup else "conditional-branch-consensus",
    )


def completion(runtime, continuation, commitments, visits=()):
    """Earliest test boundary from accepted/proposed work or eligible receipts."""
    now = runtime.executive.at_hour
    public = runtime.public()
    order = next((o for o in public["orders"] if o["id"] == continuation.work_order_id), None)
    if (
        order is None
        or order["kind"] != continuation.action
        or order.get("investigation_id") != continuation.episode_id
    ):
        raise ValueError("The original investigation's actual intervention is missing")
    if order["status"] == "failed":
        raise ValueError("Interrupted intervention cannot authorise its planned post-return test")
    plans = [c.plan for c in commitments if c.plan.order.order_id == continuation.work_order_id]
    if plans:
        boundary = max(available_boundary(p.ending_at) for p in plans)
        basis = "Conditional continuation of accepted or proposed work and its return"
    else:
        receipt = order.get("reported")
        if (
            not receipt
            or receipt.get("available_at", float("inf")) > now
            or receipt.get("completed_at", float("inf")) > now
        ):
            raise ValueError(
                "Required intervention is neither in this candidate nor observably complete"
            )
        boundary = available_boundary(receipt["completed_at"])
        basis = (
            "Eligible actual procedure-completion receipt; operating recovery remains unverified"
        )
    for visit in (*runtime.executive.visits.values(), *visits):
        if continuation.work_order_id not in {p.order.order_id for p in visit.members}:
            continue
        if any(
            c.plan.order.order_id in {p.order.order_id for p in visit.members} for c in commitments
        ):
            boundary = max(boundary, available_boundary(visit.ending_at))
            basis = "Conditional whole shared-visit return, including later jobs"
        else:
            record = next(
                (
                    v
                    for v in public.get("executive", {}).get("visits", ())
                    if v["visit_id"] == visit.visit_id
                ),
                None,
            )
            if record is None or record.get("returned_at") is None or record["returned_at"] > now:
                raise ValueError("The shared crew journey has not observably returned")
            boundary = max(boundary, available_boundary(record["returned_at"]))
    return dict(
        boundary=boundary,
        basis=basis,
        work_order_id=continuation.work_order_id,
        continuation_id=continuation.continuation_id,
    )
