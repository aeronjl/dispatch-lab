"""A bounded, explicit belief over contact and module hypotheses.

The inputs are priors, eligible observations and a declared reader model. There
is no fault schedule or simulator port. A posterior is conditional on these
hypotheses and likelihoods, not a calibrated diagnosis of a physical plant.
"""

import itertools
from dataclasses import asdict, dataclass
from math import isfinite, sqrt

from methane.services.contracts import identifier, nonnegative
from methane.services.coupling import identity
from methane.services.inspection import VERSION as READER_VERSION
from methane.services.inspection import classify

VERSION = "contact-investigation-belief/1"
FINDINGS = ("closed", "open", "unusable")
MECHANISMS = {
    "resettable-trip": dict(signal_v=24, reset_restores=True, replacement_restores=True),
    "equipment-damage": dict(signal_v=0, reset_restores=False, replacement_restores=True),
    "damage-and-stuck-contact": dict(signal_v=24, reset_restores=False, replacement_restores=True),
}


@dataclass(frozen=True)
class Hypothesis:
    hypothesis_id: str
    mechanism: str
    probability: float
    fixed_offset_v: float = 0
    mobile_offset_v: float = 0
    fixed_dropout: bool = False
    mobile_dropout: bool = False

    def __post_init__(self):
        identifier(self.hypothesis_id, "hypothesis")
        if self.mechanism not in MECHANISMS:
            raise ValueError("Unknown bounded module/contact mechanism")
        for name in ("probability", "fixed_offset_v", "mobile_offset_v"):
            value = getattr(self, name)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError("Hypothesis weights and offsets must be finite")
        if not 0 <= self.probability <= 1:
            raise ValueError("Hypothesis probability must be between zero and one")
        if type(self.fixed_dropout) is not bool or type(self.mobile_dropout) is not bool:
            raise ValueError("Reader dropout hypotheses must be Boolean")


@dataclass(frozen=True)
class Assumptions:
    hypotheses: tuple[Hypothesis, ...]
    source: str
    quadrature_points: int = 3
    epoch_start_hour: float = 0

    def __post_init__(self):
        identifier(self.source, "declared belief source")
        nonnegative(self.epoch_start_hour, "declared prior epoch")
        if type(self.hypotheses) is not tuple or not 1 <= len(self.hypotheses) <= 16:
            raise ValueError("Supply one to sixteen immutable hypotheses")
        if len({h.hypothesis_id for h in self.hypotheses}) != len(self.hypotheses):
            raise ValueError("Hypothesis identities must be unique")
        if abs(sum(h.probability for h in self.hypotheses) - 1) > 1e-10:
            raise ValueError("Prior probabilities must sum to one")
        if type(self.quadrature_points) is not int or not 1 <= self.quadrature_points <= 9:
            raise ValueError("Reader quadrature requires one to nine points per noise channel")

    @property
    def assumption_id(self):
        return identity(asdict(self))


def illustrative():
    return Assumptions(
        (
            Hypothesis("latch", "resettable-trip", 0.5),
            Hypothesis("damage", "equipment-damage", 0.3),
            Hypothesis("shared-contact", "damage-and-stuck-contact", 0.2),
        ),
        "assumption:illustrative-contact-investigation/1",
    )


def category(value, quality):
    return (
        "closed"
        if quality == "usable" and value is True
        else "open"
        if quality == "usable" and value is False
        else "unusable"
    )


def likelihood(hypothesis, reader, options, points=3):
    """Midpoint quadrature of the execution reader's independent bounded noise.

    Signal/zero/span are passed through the actual reference and band classifier.
    This finite approximation is recorded explicitly, not claimed to be an
    analytic probability or a fitted sensor-error model. Static offset/dropout
    are latent hypotheses; time-varying drift needs a new hypothesis epoch.
    """
    if reader not in ("fixed", "mobile") or options.inspection_model != READER_VERSION:
        raise ValueError("Investigation needs a registered referenced fixed or mobile reader")
    if type(points) is not int or not 1 <= points <= 9:
        raise ValueError("Reader quadrature requires one to nine points per noise channel")
    if getattr(hypothesis, reader + "_dropout"):
        return dict(closed=0.0, open=0.0, unusable=1.0)
    width = sqrt(3) * options.inspection_noise_v
    values = [width * (2 * (i + 0.5) / points - 1) for i in range(points)] if width else [0]
    offset = getattr(hypothesis, reader + "_offset_v")
    counts = dict.fromkeys(FINDINGS, 0)
    for a, b, c in itertools.product(values, repeat=3):
        r = classify(
            MECHANISMS[hypothesis.mechanism]["signal_v"] + offset + a,
            offset + b,
            24 + offset + c,
            options,
        )
        counts[category(r["value"], r["quality"])] += 1
    return {k: n / len(values) ** 3 for k, n in counts.items()}


def _epoch(context, since_hour):
    nonnegative(since_hour, "belief epoch start")
    if since_hour > context.at_hour:
        raise ValueError("A belief epoch cannot start after the current observation boundary")
    cutoff = context.latest("contact-evidence-cutoff")
    if cutoff and cutoff.quality == "usable":
        nonnegative(cutoff.value, "recorded inspection cutoff")
        if cutoff.unit != "h" or cutoff.value > context.at_hour:
            raise ValueError("An inspection cutoff must identify an observed hour")
        since_hour = max(since_hour, cutoff.value)
    return since_hour


def observations(context, options, *, since_hour=0):
    """Extract only eligible referenced packets; incomplete/stale packets stay gaps.

    A cutoff from a recorded intervention ends the previous static-condition
    epoch. Re-reading a packet never changes its original age or duplicates it.
    """
    since_hour = _epoch(context, since_hour)
    packets = {}
    for r in context.readings:
        if not r.channel.startswith("contact-") or not r.source_id.startswith(READER_VERSION + "/"):
            continue
        channel, _, reader = r.channel.partition(":")
        if reader not in ("fixed", "mobile") or channel not in (
            "contact-signal",
            "contact-zero",
            "contact-span",
        ):
            continue
        if r.unit != "V":
            raise ValueError("Referenced reader operands must be recorded in volts")
        if r.source_id.split("/")[-2] != reader:
            raise ValueError("Reader channel and recorded source disagree")
        key = (r.source_id, r.measured_at, r.available_at, reader)
        group = packets.setdefault(key, {})
        if channel in group and group[channel] != r:
            raise ValueError("Conflicting copies of an original reader operand")
        group[channel] = r
    result = []
    for (source, measured, available, reader), packet in sorted(
        packets.items(), key=lambda item: (item[0][2], item[0][0])
    ):
        operands = {k.removeprefix("contact-"): r.value for k, r in packet.items()}
        complete = set(operands) == {"signal", "zero", "span"}
        raw = classify(operands.get("signal"), operands.get("zero"), operands.get("span"), options)
        applicable = (
            complete
            and measured > since_hour
            and context.at_hour - measured <= options.contact_max_age_hours
            and all(
                r.quality == "usable" or (r.quality == "unavailable" and r.value is None)
                for r in packet.values()
            )
        )
        reason = (
            "Current complete packet"
            if applicable
            else "Packet incomplete/unavailable, predates this epoch, or exceeds the evidence age limit"
        )
        value = dict(
            reader=reader,
            source_id=source,
            measured_at=measured,
            available_at=available,
            operands_v=operands,
            finding=category(raw["value"], raw["quality"]),
            interpretation=raw,
            applicable=applicable,
            reason=reason,
        )
        value["observation_id"] = identity(
            {k: v for k, v in value.items() if k not in ("applicable", "reason")}
        )
        result.append(value)
    return result


def update(assumptions, context, options):
    """Recompute this epoch from its prior, avoiding repeated-use evidence inflation."""
    since_hour = _epoch(context, assumptions.epoch_start_hour)
    renewal = since_hour != assumptions.epoch_start_hour
    rows = observations(context, options, since_hour=since_hour)
    weights = {h.hypothesis_id: h.probability for h in assumptions.hypotheses}
    evidence, conflict = [], False
    for row in rows:
        if renewal or not row["applicable"]:
            continue
        values = {
            h.hypothesis_id: likelihood(h, row["reader"], options, assumptions.quadrature_points)[
                row["finding"]
            ]
            for h in assumptions.hypotheses
        }
        probability = sum(weights[k] * values[k] for k in weights)
        if probability <= 0:
            conflict = True
            evidence.append(
                dict(
                    observation_id=row["observation_id"],
                    predictive_probability=0,
                    used=False,
                    reason="Observed finding is outside the supported belief; no arbitrary probability floor or healthy reset",
                )
            )
            break
        weights = {k: weights[k] * values[k] / probability for k in weights}
        evidence.append(
            dict(
                observation_id=row["observation_id"],
                predictive_probability=probability,
                likelihoods=values,
                used=True,
            )
        )
    result = dict(
        implementation_id=VERSION,
        assumption_id=assumptions.assumption_id,
        assumptions=asdict(assumptions),
        at_hour=context.at_hour,
        since_hour=since_hour,
        reader_model=asdict(options),
        observations=rows,
        evidence=evidence,
        status="prior requires renewal"
        if renewal
        else "unsupported observation"
        if conflict
        else "conditioned"
        if evidence
        else "prior only",
        posterior=weights if not conflict and not renewal else None,
        reason="An observed intervention ended this prior's static-condition epoch. Declare a new prior for the current epoch or use a separately validated transition model; the original prior is not silently reset."
        if renewal
        else None,
        scope="Hypotheses conditional on a diagnosed module-capacity shortfall, not a calibrated posterior. Common-contact error is explicit. This model neither upgrades capacity nor verifies a repair. Finite noise quadrature and static reader-condition hypotheses are assumptions; an unsupported finding requires escalation or a revised declared model.",
    )
    result["belief_id"] = identity(result)
    return result


def findings(belief, reader, options, *, measured_at):
    """Future observation branches, distinct from observations actually received."""
    from methane.services.contracts import available_boundary

    if belief.get("implementation_id") != VERSION or identity(
        {k: v for k, v in belief.items() if k != "belief_id"}
    ) != belief.get("belief_id"):
        raise ValueError("Original belief identity mismatch")
    if reader not in ("fixed", "mobile") or options.inspection_model != READER_VERSION:
        raise ValueError("Future findings need a referenced fixed or mobile reader")

    nonnegative(measured_at, "predicted inspection completion")
    if measured_at < belief["at_hour"]:
        raise ValueError("A new inspection cannot complete in the past")
    if belief["posterior"] is None:
        raise ValueError("Unsupported current evidence cannot support an inspection-value estimate")
    hypotheses = tuple(Hypothesis(**h) for h in belief["assumptions"]["hypotheses"])
    points = belief["assumptions"]["quadrature_points"]
    available = available_boundary(measured_at + options.inspection_delay_hours)
    stale = available - measured_at > options.contact_max_age_hours
    branches = []
    for finding in FINDINGS:
        joint = {
            h.hypothesis_id: belief["posterior"][h.hypothesis_id]
            * (
                float(finding == "unusable")
                if stale
                else likelihood(h, reader, options, points)[finding]
            )
            for h in hypotheses
        }
        p = sum(joint.values())
        if p <= 0:
            continue
        branches.append(
            dict(
                finding=finding,
                probability=p,
                posterior={k: v / p for k, v in joint.items()},
                joint=joint,
                reader=reader,
                measured_at=measured_at,
                available_at=available,
                context="prediction",
                stale_on_arrival=stale,
                permitted_contact_reset=finding == "closed" and not stale,
                scope="A possible finding can permit a compatible reset; it does not establish restoration. Process tracking remains required.",
            )
        )
    return dict(
        implementation_id=VERSION,
        belief_id=belief["belief_id"],
        branches=branches,
        context="prediction",
        reader_model=asdict(options),
        quadrature_points=points,
    )
