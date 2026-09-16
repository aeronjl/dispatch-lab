"""Conditional uncertainty through observed procedures and subsequent measurements.

This filter has no fault-state or repair-outcome port. Procedure completion is
an observation of attempted work. Its declared success probability propagates
the belief; it never certifies restoration or upgrades a capacity estimate.
"""

import copy
import math
from dataclasses import asdict, dataclass, replace

from scipy.special import log_ndtr, logsumexp

from methane.services.contracts import Context, available_boundary, identifier, nonnegative
from methane.services.coupling import identity
from methane.services.investigation_belief import MECHANISMS, likelihood, observations
from methane.services.verification import validate

VERSION = "observed-recovery-belief/1"


@dataclass(frozen=True)
class Procedure:
    order_id: str
    action: str
    completed_at: float

    def __post_init__(self):
        identifier(self.order_id, "observed procedure")
        if self.action not in ("reset", "module-replacement"):
            raise ValueError("Recovery belief needs a compatible module procedure")
        nonnegative(self.completed_at, "observed work completion")

    @property
    def available_at(self):
        return available_boundary(self.completed_at)


def log_power_likelihood(measured, mean, noise, tolerance=1e-5):
    """Likelihood of the existing nonnegative multiplicative Gaussian power sensor.

    At zero the sensor has an atom, not a probability density. Positive values
    use densities in 1/kW. With zero noise every supported mean is a point mass.
    No probability floor or invented measurement variance is introduced.
    """
    for name, value in (
        ("power observation", measured),
        ("predicted power", mean),
        ("noise", noise),
    ):
        nonnegative(value, name)
    if mean == 0 or noise == 0:
        return 0.0 if abs(measured - mean) <= tolerance else -math.inf
    if measured == 0:
        return float(log_ndtr(-1 / noise))
    sigma = mean * noise
    return -0.5 * ((measured - mean) / sigma) ** 2 - math.log(sigma * math.sqrt(2 * math.pi))


def contact_likelihood(hypothesis, restored, reader, options, points):
    # A successful module procedure does not repair a separate stuck contact or
    # either reader. An operational, non-stuck contact has the same open signal
    # as the original equipment-damage hypothesis.
    h = (
        replace(hypothesis, mechanism="equipment-damage")
        if restored and hypothesis.mechanism != "damage-and-stuck-contact"
        else hypothesis
    )
    return likelihood(h, reader, options, points)


class RecoveryBelief:
    """Replay admitted observations in physical order, preserving arrival times.

    Delayed packets can condition an earlier latent state and propagate through
    known procedures. Previously emitted results remain immutable. Admission
    uses the actual decision's age limit; re-reading a packet cannot inflate
    evidence or make an expired packet fresh.
    """

    def __init__(
        self, assumptions, plant, sensors, options, impaired_capacity_kw, success_probability
    ):
        nonnegative(impaired_capacity_kw, "declared impaired capacity")
        nonnegative(success_probability, "declared procedure success probability")
        if impaired_capacity_kw >= plant.electrolyser_kw or success_probability > 1:
            raise ValueError("Declare a capacity shortfall and a probability in [0, 1]")
        if plant.dt_hours != 1 or not sensors.enabled:
            raise ValueError("Recovery belief needs enabled hourly process observations")
        self.assumptions, self.plant, self.sensors, self.options = (
            assumptions,
            plant,
            sensors,
            options,
        )
        self.capacity, self.success = impaired_capacity_kw, success_probability
        self.events, self.packet_identities = {}, {}
        self.last_hour = -1
        self._contact = {
            (h.hypothesis_id, restored, reader): contact_likelihood(
                h, restored, reader, options, assumptions.quadrature_points
            )
            for h in assumptions.hypotheses
            for restored in (False, True)
            for reader in ("fixed", "mobile")
        }

    def advance(self, context, procedures=(), test=None):
        previous = self.last_hour, dict(self.events), dict(self.packet_identities)
        try:
            return self._advance(context, procedures, test)
        except Exception:
            self.last_hour, self.events, self.packet_identities = previous
            raise

    def _advance(self, context, procedures, test):
        now = context.at_hour
        if now != int(now) or now < self.last_hour or now < self.assumptions.epoch_start_hour:
            raise ValueError("Belief decisions must advance through hourly boundaries")
        self.last_hour = now
        epoch = self.assumptions.epoch_start_hour
        for procedure in procedures:
            if not isinstance(procedure, Procedure):
                raise ValueError("Supply observed procedure descriptors, never outcome receipts")
            if procedure.available_at > now:
                raise ValueError("A future procedure is not an observation")
            if procedure.completed_at < epoch:
                continue
            event = dict(
                kind="procedure",
                at=procedure.completed_at,
                available_at=procedure.available_at,
                procedure=asdict(procedure),
            )
            self._keep("procedure:" + procedure.order_id, event)
        # The static reader helper is reused without its epoch-ending cutoff:
        # the explicitly supplied procedures now model those state transitions.
        raw = Context(
            now, tuple(r for r in context.readings if r.channel != "contact-evidence-cutoff")
        )
        packets = observations(raw, self.options, since_hour=epoch)
        for packet in packets:
            if set(packet["operands_v"]) != {"signal", "zero", "span"}:
                continue
            key = identity({k: packet[k] for k in ("source_id", "measured_at", "reader")})
            prior = self.packet_identities.get(key)
            if prior is not None and prior != packet["observation_id"]:
                raise ValueError("An original complete reader packet was changed")
            self.packet_identities[key] = packet["observation_id"]
            if packet["applicable"]:
                self._keep(
                    "contact:" + key,
                    dict(
                        kind="contact",
                        at=packet["measured_at"],
                        available_at=packet["available_at"],
                        packet={
                            k: v for k, v in packet.items() if k not in ("applicable", "reason")
                        },
                    ),
                )
        if test is not None:
            validate(test)
            p = test["inputs"]["packet"]
            if p["available_at"] > now:
                raise ValueError("A future operating test is not evidence")
            if test["inputs"]["plant"] != self.plant.to_dict() or test["inputs"][
                "sensors"
            ] != asdict(self.sensors):
                raise ValueError("Operating evidence uses different plant or sensor assumptions")
            if p["hour"] >= epoch:
                self._keep(
                    "power:" + str(p["hour"]),
                    dict(
                        kind="power",
                        at=p["hour"],
                        available_at=p["available_at"],
                        evidence=copy.deepcopy(test),
                    ),
                )
        cutoff = context.latest("contact-evidence-cutoff")
        if cutoff and cutoff.quality == "usable":
            nonnegative(cutoff.value, "observed procedure cutoff")
            if cutoff.unit != "h" or cutoff.value > now:
                raise ValueError("Procedure cutoff needs an already observed hour")
        missing = bool(
            cutoff
            and cutoff.quality == "usable"
            and cutoff.value >= epoch
            and not any(
                e["kind"] == "procedure" and e["at"] == cutoff.value for e in self.events.values()
            )
        )
        return self._calculate(now, packets, missing)

    def _keep(self, key, event):
        if key in self.events and self.events[key] != event:
            raise ValueError("Conflicting copies of an observed belief event")
        self.events[key] = copy.deepcopy(event)

    def _calculate(self, now, packets, missing):
        hypotheses = self.assumptions.hypotheses
        weights = {
            (h.hypothesis_id, restored): math.log(h.probability)
            if not restored and h.probability
            else -math.inf
            for h in hypotheses
            for restored in (False, True)
        }
        events = sorted(
            self.events.items(),
            key=lambda x: (
                x[1]["at"],
                {"procedure": 0, "power": 1, "contact": 2}[x[1]["kind"]],
                x[0],
            ),
        )
        history, conflict = [], None
        for key, event in events:
            before = self._rows(weights)
            if event["kind"] == "procedure":
                action = event["procedure"]["action"]
                for h in hypotheses:
                    compatible = MECHANISMS[h.mechanism][
                        "reset_restores" if action == "reset" else "replacement_restores"
                    ]
                    chance = self.success if compatible else 0
                    previous = weights[h.hypothesis_id, False]
                    moved = previous + math.log(chance) if chance else -math.inf
                    weights[h.hypothesis_id, False] = (
                        previous + math.log1p(-chance) if chance < 1 else -math.inf
                    )
                    weights[h.hypothesis_id, True] = float(
                        logsumexp([weights[h.hypothesis_id, True], moved])
                    )
                history.append(
                    dict(
                        event_id=key,
                        event=event,
                        used=True,
                        before=before,
                        after=self._rows(weights),
                        reason="Observed attempted procedure; declared transition probability, not observed repair success",
                    )
                )
                continue
            likelihoods = {}
            if event["kind"] == "contact":
                if any(
                    e["kind"] == "procedure" and e["at"] == event["at"]
                    for e in self.events.values()
                ):
                    history.append(
                        dict(
                            event_id=key,
                            event=event,
                            used=False,
                            reason="Contact and procedure share a timestamp; their physical ordering is unspecified",
                        )
                    )
                    continue
                packet = event["packet"]
                for h in hypotheses:
                    for restored in (False, True):
                        p = self._contact[h.hypothesis_id, restored, packet["reader"]][
                            packet["finding"]
                        ]
                        likelihoods[h.hypothesis_id, restored] = math.log(p) if p else -math.inf
            else:
                evidence = event["evidence"]
                if evidence["resource_check"]["status"] != "feasible at recorded estimate":
                    history.append(
                        dict(
                            event_id=key,
                            event=event,
                            used=False,
                            reason="No resource-feasible informative operating test; no health information added",
                        )
                    )
                    continue
                requested = evidence["operands"]["requested_kw"]
                measured = evidence["operands"]["measured_kw"]
                if measured < 0:
                    conflict = "Negative power is outside the declared observation model"
                for h in hypotheses:
                    for restored in (False, True):
                        mean = min(
                            requested, self.plant.electrolyser_kw if restored else self.capacity
                        )
                        if mean < self.plant.min_kw - 1e-5:
                            mean = 0
                        likelihoods[h.hypothesis_id, restored] = (
                            log_power_likelihood(measured, mean, self.sensors.noise_fraction)
                            if measured >= 0
                            else -math.inf
                        )
            terms = {k: v + likelihoods[k] for k, v in weights.items()}
            peak = max(terms.values())
            if peak == -math.inf:
                conflict = (
                    conflict or "Observation outside the declared hypothesis/measurement support"
                )
                history.append(dict(event_id=key, event=event, used=False, reason=conflict))
                break
            total = sum(math.exp(v - peak) for v in terms.values())
            normalizer = peak + math.log(total)
            weights = {k: v - normalizer for k, v in terms.items()}
            history.append(
                dict(
                    event_id=key,
                    event=event,
                    used=True,
                    before=before,
                    after=self._rows(weights),
                    log_predictive_likelihood=peak + math.log(total),
                    likelihood_measure="probability for contact/zero-power atoms; density in 1/kW for positive noisy power",
                    log_likelihoods=[
                        dict(
                            hypothesis=k[0],
                            restored=k[1],
                            value=v if math.isfinite(v) else None,
                            zero_likelihood=not math.isfinite(v),
                        )
                        for k, v in likelihoods.items()
                    ],
                )
            )
        supported = not missing and conflict is None
        result = dict(
            implementation_id=VERSION,
            at_hour=now,
            inputs=dict(
                assumptions=asdict(self.assumptions),
                plant=self.plant.to_dict(),
                sensors=asdict(self.sensors),
                reader_options=asdict(self.options),
                impaired_capacity_kw=self.capacity,
                success_probability=self.success,
            ),
            observations=packets,
            history=history,
            status="unmodelled intervention"
            if missing
            else "unsupported observation"
            if conflict
            else "conditioned"
            if history
            else "prior only",
            reason="An observed intervention lacks its original procedure descriptor"
            if missing
            else conflict,
            posterior=self._rows(weights) if supported else None,
            restoration_probability=math.exp(
                float(logsumexp([v for (_, restored), v in weights.items() if restored]))
            )
            if supported
            else None,
            scope="Conditional on the declared incident hypotheses, point impaired-capacity estimate, static reader faults, independent power sensor and procedure reliability. Independent inventory balance and full recovery confirmation remain separate observer checks. No fault cause, physical success draw or future information enters; no capacity upgrade is authorised. No additional failures or degradation within this incident epoch are assumed.",
        )
        result["belief_id"] = identity(result)
        return copy.deepcopy(result)

    @staticmethod
    def _rows(weights):
        return [
            dict(
                hypothesis=h,
                restored=r,
                probability=math.exp(p),
                log_probability=p if math.isfinite(p) else None,
                impossible=not math.isfinite(p),
            )
            for (h, r), p in weights.items()
        ]
