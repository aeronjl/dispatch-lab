"""Versioned uncertainty-aware service policy assumptions and observation beliefs.

Public assumptions and eligible observations are the only inputs to Beliefs.
Simulator schedules are handled by a separate support observation port.
"""

import copy
import math

from methane.adaptation import Observer as PerformanceObserver
from methane.provenance import digest
from methane.services.uncertain_timing import GROUPS

VERSION = "uncertainty-aware-services/1"
DEFAULT = dict(
    version=VERSION,
    mode="risk-aware",
    duration_bounds={key: [0.5, 2.0] for key in GROUPS},
    duration_prior_strength=2.0,
    reliability_prior_strength=2.0,
    weather_factors=[0.65, 1.0, 1.2],
    weather_weights=[0.2, 0.6, 0.2],
    risk_weight=0.5,
    terminal_minimum={},
    solar_relative_error=0.05,
    surface_absolute_error=0.005,
    evidence_max_age_hours=24,
    source="Illustrative bounded clocks, observation error budgets and finite weather regimes; no site calibration",
)
SCOPE = (
    "Finite assumed uncertainty model. Task clocks are private within public reservation "
    "bounds. Completed work is distinct from verified recovery. Duration beliefs include "
    "unfinished jobs; probability estimates are conditional on the declared model and "
    "selected service activity, not calibrated field reliability. Ambiguous observations "
    "and out-of-support evidence remain explicit."
)


def validate(value):
    from methane.duration_population import AUTONOMY_VERSION
    from methane.duration_population import validate as validate_population

    extended = isinstance(value, dict) and value.get("version") == AUTONOMY_VERSION
    if not isinstance(value, dict) or set(value) != set(DEFAULT) | (
        {"duration_model"} if extended else set()
    ):
        raise ValueError("Autonomy requires every versioned assumption explicitly")
    if value["version"] not in (VERSION, AUTONOMY_VERSION) or value["mode"] not in (
        "fixed",
        "adaptive",
        "risk-aware",
    ):
        raise ValueError("Unsupported autonomous service mode")
    bounds = value["duration_bounds"]
    if not isinstance(bounds, dict) or set(bounds) != set(GROUPS):
        raise ValueError("Declare duration bounds for all service clock groups")
    for b in bounds.values():
        if (
            not isinstance(b, list)
            or len(b) != 2
            or any(type(x) not in (int, float) or not math.isfinite(x) for x in b)
            or not 0 < b[0] <= 1 <= b[1] <= 8
        ):
            raise ValueError("Duration supports must be finite, positive and include nominal time")
    for key in ("duration_prior_strength", "reliability_prior_strength", "evidence_max_age_hours"):
        x = value[key]
        if type(x) not in (int, float) or not math.isfinite(x) or x <= 0:
            raise ValueError("Evidence strengths and age must be positive and finite")
    for key in ("risk_weight", "solar_relative_error", "surface_absolute_error"):
        x = value[key]
        if type(x) not in (int, float) or not math.isfinite(x) or not 0 <= x <= 1:
            raise ValueError("Risk and observation budgets must lie between zero and one")
    f, w = value["weather_factors"], value["weather_weights"]
    if not isinstance(f, list) or not isinstance(w, list) or not 1 <= len(f) == len(w) <= 5:
        raise ValueError("Declare one to five matched weather regimes and weights")
    if (
        any(type(x) not in (int, float) or not math.isfinite(x) or x <= 0 for x in (*f, *w))
        or abs(sum(w) - 1) > 1e-9
    ):
        raise ValueError("Weather factors and probability weights must be positive and sum to one")
    if len(set(f)) != len(f):
        raise ValueError("Weather regimes must be distinct")
    terminal = value["terminal_minimum"]
    if (
        not isinstance(terminal, dict)
        or set(terminal) - {"battery_kwh", "h2_kg", "co2_kg", "temperature_c"}
        or any(
            type(x) not in (int, float) or not math.isfinite(x) or x < 0 for x in terminal.values()
        )
    ):
        raise ValueError("Terminal minima require named nonnegative physical states")
    if not isinstance(value["source"], str) or not value["source"].strip():
        raise ValueError("Record the evidence or assumption behind autonomous service uncertainty")
    if extended:
        validate_population(value["duration_model"], bounds)
    digest(value)
    return copy.deepcopy(value)


def validate_world(world):
    options = validate(world["autonomy"])
    c = world["config"]
    if not c["field_operations"]["enabled"] or c["service_system"] is None:
        raise ValueError("Uncertainty-aware services require enabled fractional service contracts")
    for key in GROUPS:
        x = c["service_system"].get(key + "_time_factor", 1)
        low, high = options["duration_bounds"][key]
        if not low <= x <= high:
            raise ValueError("Actual duration exceeds declared support: " + key)
        if (
            "duration_model" in options
            and x not in options["duration_model"]["groups"][key]["persistent_factors"]
        ):
            raise ValueError(
                "Actual persistent equipment factor is outside its declared grid: " + key
            )
    validate_support_events(world.get("support_events", []))


def validate_support_events(events):
    if not isinstance(events, list) or len(events) > 100:
        raise ValueError("Supply a bounded list of explicit support availability events")
    for e in events:
        if not isinstance(e, dict) or set(e) != {"channel", "start", "end", "available", "source"}:
            raise ValueError("Support events need channel, interval, availability and evidence")
        if (
            e["channel"]
            not in (
                "crew-available",
                "communications",
                "route-open",
                "dock-available",
                "calibration-reference",
            )
            or type(e["available"]) is not bool
        ):
            raise ValueError("Unsupported support observation")
        if (
            any(type(e[k]) is not int for k in ("start", "end"))
            or not 0 <= e["start"] < e["end"]
            or not e["source"]
        ):
            raise ValueError("Support event boundaries must be increasing hourly integers")
    for i, a in enumerate(events):
        if any(
            a["channel"] == b["channel"] and a["start"] < b["end"] and a["end"] > b["start"]
            for b in events[:i]
        ):
            raise ValueError("Overlapping support events cannot disagree about the same channel")


class SupportObservations:
    """Private timetable → present status packets. No schedule accessor."""

    def __init__(self, events):
        validate_support_events(events)
        self.__events = copy.deepcopy(events)

    def at(self, hour, readings):
        from dataclasses import replace

        values = []
        for r in readings:
            active = next(
                (
                    e
                    for e in self.__events
                    if e["channel"] == r.channel and e["start"] <= hour < e["end"]
                ),
                None,
            )
            # Unavailability can remove support; an event cannot create a crew
            # outside its ordinary shift, an absent dock or unavailable equipment.
            values.append(
                replace(
                    r,
                    value=bool(r.value and active["available"]),
                    source_id="current-support-status/1",
                )
                if active
                else r
            )
        return values


class Beliefs:
    def __init__(self, options, completion_prior=0.5):
        self.options = validate(options)
        if not 0 <= completion_prior <= 1:
            raise ValueError("Completion prior must lie between zero and one")
        self.completion_prior = completion_prior
        self.durations, self.outcomes = {}, {}
        self.hour = -1

    def update(self, hour, durations, orders):
        if hour <= self.hour:
            raise ValueError("Belief updates require an advancing observation clock")
        self.hour = hour
        for row in durations:
            if (
                row["available_at"] > hour
                or row["started_at"] > hour
                or row["completed_at"] is not None
                and row["completed_at"] > hour
            ):
                raise ValueError("A duration belief cannot use future completion information")
            self.durations[row["id"]] = copy.deepcopy(
                row
            )  # Replace the same censored observation, never recount it.
        for order in orders:
            key = order["id"]
            if order["status"] in (
                "failed",
                "stranded",
                "interrupted",
                "completed",
                "verified",
                "awaiting verification",
            ):
                self.outcomes[key] = dict(
                    action=order["kind"],
                    returned=order["status"] not in ("failed", "stranded", "interrupted"),
                    verified=order["status"] == "verified",
                    pending_verification=order["status"] == "awaiting verification",
                    available_at=hour,
                )
            # Awaiting verification is unresolved, never an automatic failed repair.
        record = self.record()
        return record

    def record(self):
        duration = {}
        for key in () if "duration_model" in self.options else GROUPS:
            lo, hi = self.options["duration_bounds"][key]
            bins = (
                [(lo + (hi - lo) * i / 8, lo + (hi - lo) * (i + 1) / 8) for i in range(8)]
                if hi > lo
                else [(lo, hi)]
            )
            prior = [self.options["duration_prior_strength"] / len(bins)] * len(bins)
            observed, censored, unsupported, last = 0, 0, [], None
            # Each job phase contributes once. A running phase has survival
            # evidence, not a completed-duration pseudo-observation.
            for row in self.durations.values():
                if row["group"] != key:
                    continue
                last = max(
                    last or 0,
                    row["completed_at"]
                    if row["completed_at"] is not None
                    else row["started_at"] + row["elapsed_hours"],
                )
                ratio = row["elapsed_hours"] / row["nominal_hours"]
                if ratio > hi + 1e-8 or not row["censored"] and ratio < lo - 1e-8:
                    unsupported.append(row["id"])
                    continue
                if row["censored"]:
                    censored += 1
                else:
                    observed += 1
                    j = next(
                        (i for i, (a, b) in enumerate(bins) if a - 1e-8 <= ratio <= b + 1e-8), None
                    )
                    if j is not None:
                        prior[j] += 1
            # Fit one likelihood per job/group, including right-censored work.
            # A round trip's correlated phase clocks do not create extra trials.
            jobs = {}
            for row in self.durations.values():
                if row["group"] != key or row["id"] in unsupported:
                    continue
                ratio = row["elapsed_hours"] / row["nominal_hours"]
                entry = jobs.setdefault(row["order_id"], dict(exact=None, lower=0))
                if not row["censored"]:
                    entry["exact"] = ratio
                else:
                    entry["lower"] = max(entry["lower"], ratio)
            likelihoods = []
            for entry in jobs.values():
                if entry["exact"] is not None:
                    ratio = entry["exact"]
                    j = next(
                        (i for i, (a, b) in enumerate(bins) if a - 1e-8 <= ratio <= b + 1e-8), None
                    )
                    likelihoods.append([float(i == j) for i in range(len(bins))])
                else:
                    likelihoods.append(
                        [
                            max(0, b - max(a, entry["lower"])) / (b - a)
                            if b > a
                            else float(b > entry["lower"])
                            for a, b in bins
                        ]
                    )
            weights = [1 / len(bins)] * len(bins)
            converged = False
            for _iteration in range(100):
                counts = [self.options["duration_prior_strength"] / len(bins)] * len(bins)
                for likelihood in likelihoods:
                    denominator = sum(w * lik for w, lik in zip(weights, likelihood, strict=True))
                    if denominator:
                        counts = [
                            v + w * lik / denominator
                            for v, w, lik in zip(counts, weights, likelihood, strict=True)
                        ]
                total = sum(counts)
                new = [v / total for v in counts]
                converged = max(abs(a - b) for a, b in zip(weights, new, strict=True)) < 1e-9
                weights = new
                if converged:
                    break
            active = [
                r
                for r in self.durations.values()
                if r["group"] == key and r["censored"] and not r["interrupted"]
            ]
            conditional = []
            for row in active:
                elapsed = row["elapsed_hours"] / row["nominal_hours"]
                survival = [
                    w * (max(0, b - max(a, elapsed)) / (b - a) if b > a else float(b > elapsed))
                    for w, (a, b) in zip(weights, bins, strict=True)
                ]
                z = sum(survival)
                conditional.append(
                    dict(
                        id=row["id"],
                        elapsed_factor=elapsed,
                        survival_mass=z,
                        conditional_weights=[x / z for x in survival] if z else None,
                        status="unfinished" if z else "outside duration support",
                    )
                )
            duration[key] = dict(
                independent_jobs=len(jobs),
                fit_iterations=_iteration + 1,
                fit_converged=converged,
                bounds=[lo, hi],
                bins=bins,
                weights=weights,
                mean_factor=sum(w * (a + b) / 2 for w, (a, b) in zip(weights, bins, strict=True)),
                completed_phases=observed,
                censored_phases=censored,
                active=conditional,
                unsupported=unsupported,
                last_evidence_hour=last,
                status="outside model support"
                if unsupported
                else "stale"
                if last is not None and self.hour - last > self.options["evidence_max_age_hours"]
                else "observed"
                if observed
                else "insufficient evidence",
                interpretation="Assumed piecewise-uniform duration population; regularized likelihood fit includes completed and right-censored jobs. Correlated phases from one job are grouped. Active jobs condition their remaining duration. Weights are approximate model fits, not an exact posterior or calibrated confidence limits.",
            )
        reliability = {}
        for action in sorted({r["action"] for r in self.outcomes.values()}):
            rows = [r for r in self.outcomes.values() if r["action"] == action]
            strength = self.options["reliability_prior_strength"]
            success, failure = (
                sum(r["returned"] for r in rows),
                sum(not r["returned"] for r in rows),
            )
            a, b = (
                strength * self.completion_prior + success,
                strength * (1 - self.completion_prior) + failure,
            )
            reliability[action] = dict(
                prior_mean=self.completion_prior,
                returned=success,
                interrupted=failure,
                alpha=a,
                beta=b,
                mean_completion_probability=a / (a + b),
                variance=a * b / ((a + b) ** 2 * (a + b + 1)),
                verified_recoveries=sum(r["verified"] for r in rows),
                pending_verifications=sum(r["pending_verification"] for r in rows),
                interpretation="Beta-binomial work-completion model conditional on attempted action. Completion probability is not repair success; unverified recovery remains unresolved.",
            )
        record = dict(
            version=self.options["version"],
            hour=self.hour,
            options=copy.deepcopy(self.options),
            durations=duration,
            reliability=reliability,
            evidence_ids=sorted(self.durations),
            scope=SCOPE,
        )
        if "duration_model" in self.options:
            from methane.duration_population import record as population_record

            record.update(population_record(self.options, list(self.durations.values()), self.hour))
        return record


class ReferenceMonitors:
    """Bounded reference-channel error, with a persistent offset and reading noise.

    Uniform errors are illustrative measurement assumptions. The current plant
    bus meter and commissioned section geometry retain their existing boundary.
    """

    def __init__(self, options, seed):
        self.options, self.seed = options, seed

    def error(self, channel, hour, bound):
        from methane.uncertainty import rng

        bias = rng(self.seed, VERSION, channel, "offset").uniform(-bound / 2, bound / 2)
        noise = rng(self.seed, VERSION, channel, hour, "reading").uniform(-bound / 2, bound / 2)
        return bias + noise

    def reference_power(self, hour, nominal_kw):
        bound = self.options["solar_relative_error"]
        measured = nominal_kw * (1 + self.error("conversion-reference", hour, bound))
        return dict(
            value_kw=measured,
            relative_error_bound=bound,
            available_at=hour,
            basis="Nominal conversion from imperfect current-weather reference; bounded persistent offset plus reading noise. Current plant-bus power remains separately observed.",
        )

    def surface(self, hour, snapshot):
        result, observations = copy.deepcopy(snapshot), []
        bound = self.options["surface_absolute_error"]
        for section, patches in result.items():
            error = self.error("surface:" + section, hour, bound)
            for p in patches:
                raw = p["removable"] + error
                lo, hi = max(0, raw - bound), min(0.3, raw + bound)
                if lo > hi:
                    raise ValueError("Surface measurement is inconsistent with physical bounds")
                p["removable"] = (lo + hi) / 2
                observations.append(
                    dict(
                        section=section,
                        start_m2=p["start_m2"],
                        end_m2=p["end_m2"],
                        raw=raw,
                        feasible_interval=[lo, hi],
                        estimate=p["removable"],
                        available_at=hour,
                    )
                )
        return result, dict(
            version="bounded-reference-monitors/1",
            hour=hour,
            absolute_error_bound=bound,
            readings=observations,
            scope="Known patch geometry and fixed adhered/damage assumptions; removable-loss channel has shared section offset and noise. Feasible intervals intersect the measurement error budget with physical bounds; they are not confidence intervals.",
        )


class BoundedPerformanceObserver(PerformanceObserver):
    def __init__(self, options, field, autonomy, seed):
        super().__init__(options, field)
        self.autonomy = validate(autonomy)
        self.monitors = ReferenceMonitors(autonomy, seed)
        self.ratio_intervals = []

    def solar_observation(self, hour, expected_kw, measured_kw):
        packet = self.monitors.reference_power(hour, expected_kw)
        out = super().solar_observation(hour, packet["value_kw"], measured_kw)
        self.solar_record["reference_measurement"] = packet
        if out["ratio"] is not None:
            error = self.autonomy["solar_relative_error"]
            interval = [out["ratio"] * (1 - error), out["ratio"] * (1 + error)]
            self.ratio_intervals.append((hour, interval))
            recent = [
                v
                for h, v in self.ratio_intervals
                if hour - h <= self.autonomy["evidence_max_age_hours"]
            ]
            lo, hi = max(v[0] for v in recent), min(v[1] for v in recent)
            self.solar_record["feasible_multiplier_interval"] = [lo, hi] if lo <= hi else None
            self.solar_record["model_evidence"] = (
                "conversion change and reference-channel bias remain ambiguous"
                if lo <= hi
                else "no constant multiplier explains recent reference-error intervals"
            )
        return copy.deepcopy(self.solar_record)

    def service_observation(self, hour, packet):
        operands = copy.deepcopy(packet)
        bounds = operands.pop("measurement_bounds", None)
        super().service_observation(hour, operands)
        interval = None
        if bounds and bounds["exposure"][0] > 1e-8:
            lo = max(0, bounds["removed"][0] / bounds["exposure"][1])
            hi = min(1, bounds["removed"][1] / bounds["exposure"][0])
            if lo <= hi:
                interval = [lo, hi]
        self.service_record.update(
            measurement_bounds=bounds,
            feasible_removal_interval=interval,
            uncertainty_status="bounded but cause ambiguous"
            if interval
            else "insufficient excitation or model discrepancy",
            interpretation="Inverse removal interval from correlated surface-error budgets and reported coverage. It is not a confidence interval or an identified mechanical fault.",
        )
        return copy.deepcopy(self.service_record)

    def record(self):
        value = super().record()
        value["scope"] = (
            SCOPE
            + " Solar conversion-reference and removable-surface measurements use explicit bounded errors. Their interval estimates are not calibrated confidence limits or a unique fault diagnosis."
        )
        value["reference_monitor_version"] = "bounded-reference-monitors/1"
        return value
