"""Finite persistent equipment effects with independent bounded job variation.

Only observed clocks enter inference. A shared job multiplier correlates its
phases in one clock group; a new accepted job receives a fresh draw. The finite
persistent grid and uniform job noise are explicit assumptions, not field fits.
"""

import copy
import math

from methane.provenance import digest
from methane.services.uncertain_timing import GROUPS

VERSION = "equipment-job-duration/1"
AUTONOMY_VERSION = "uncertainty-aware-services/2"


def default_model():
    return dict(
        version=VERSION,
        groups={
            k: dict(
                persistent_factors=[0.75, 1.0, 1.25, 1.5],
                prior_weights=[0.25] * 4,
                job_multiplier_bounds=[0.8, 1.2],
            )
            for k in GROUPS
        },
        source="Illustrative finite equipment factors and uniform independent job variation; not field calibrated",
    )


def validate(model, bounds):
    if (
        not isinstance(model, dict)
        or set(model) != {"version", "groups", "source"}
        or model["version"] != VERSION
        or set(model["groups"]) != set(GROUPS)
        or not isinstance(model["source"], str)
        or not model["source"].strip()
    ):
        raise ValueError("Declare a versioned equipment/job duration model and source")
    for key, item in model["groups"].items():
        if set(item) != {"persistent_factors", "prior_weights", "job_multiplier_bounds"}:
            raise ValueError("Declare persistent support, prior and job variation separately")
        p, w, b = (
            item[k] for k in ("persistent_factors", "prior_weights", "job_multiplier_bounds")
        )
        if (
            not all(isinstance(x, list) for x in (p, w, b))
            or not 1 <= len(p) == len(w) <= 16
            or len(b) != 2
            or any(
                type(x) not in (float, int) or not math.isfinite(x) or x <= 0 for x in (*p, *w, *b)
            )
            or sorted(set(p)) != p
            or abs(sum(w) - 1) > 1e-9
            or not b[0] <= 1 <= b[1]
            or p[0] * b[0] < bounds[key][0] - 1e-9
            or p[-1] * b[1] > bounds[key][1] + 1e-9
        ):
            raise ValueError("Equipment × job support must fit the declared reservation bounds")
    return copy.deepcopy(model)


def jobs(rows):
    """One likelihood per accepted job/group, even for repeated phase packets."""
    result = {}
    for r in {r["id"]: r for r in rows}.values():
        if r["nominal_hours"] <= 0 or r["elapsed_hours"] < 0:
            raise ValueError("Observed service clocks require positive nominal duration")
        v = r["elapsed_hours"] / r["nominal_hours"]
        j = result.setdefault(r["order_id"], dict(exact=None, lower=0, ids=[], inconsistent=False))
        j["ids"].append(r["id"])
        if r["censored"]:
            j["lower"] = max(j["lower"], v)
        elif j["exact"] is not None and abs(j["exact"] - v) > 1e-7:
            j["inconsistent"] = True
        else:
            j["exact"] = v
    for j in result.values():
        if j["exact"] is not None and j["exact"] < j["lower"] - 1e-7:
            j["inconsistent"] = True
    return result


def likelihood(job, a, b):
    if job["inconsistent"]:
        return 0.0
    if job["exact"] is not None:
        return (1 / (b - a) if b > a else 1.0) if a - 1e-7 <= job["exact"] <= b + 1e-7 else 0.0
    return max(0, b - max(a, job["lower"])) / (b - a) if b > a else float(b > job["lower"])


def estimate(item, rows, bounds, hour, max_age, *, conditionals=True):
    p, prior = item["persistent_factors"], item["prior_weights"]
    a, b = item["job_multiplier_bounds"]
    bins = [[x * a, x * b] for x in p]
    logs = [math.log(x) for x in prior]
    grouped, unsupported = jobs(rows), []
    for order, job in sorted(grouped.items()):
        values = [likelihood(job, x, y) for x, y in bins]
        if not any(values):
            unsupported.append(order)
            continue
        logs = [
            v + math.log(lik) if lik else -math.inf for v, lik in zip(logs, values, strict=True)
        ]
    z = max(logs)
    incompatible = z == -math.inf
    if incompatible:
        unsupported.extend(grouped)
    weights = prior if incompatible else [math.exp(x - z) for x in logs]
    total = sum(weights)
    weights = [x / total for x in weights]
    last = max((r["available_at"] for r in rows), default=None)
    result = dict(
        version=VERSION,
        bounds=list(bounds),
        bins=bins,
        weights=weights,
        persistent_factors=list(p),
        prior_weights=list(prior),
        posterior_weights=weights,
        job_multiplier_bounds=[a, b],
        mean_factor=sum(x * w * (a + b) / 2 for x, w in zip(p, weights, strict=True)),
        independent_jobs=len(grouped),
        completed_phases=sum(not r["censored"] for r in rows),
        censored_phases=sum(r["censored"] for r in rows),
        unsupported=sorted(set(unsupported)),
        last_evidence_hour=last,
        status="outside model support"
        if unsupported
        else "stale"
        if last is not None and hour - last > max_age
        else "observed"
        if rows
        else "insufficient evidence",
        interpretation="Exact finite-grid posterior under uniform job noise. Future-job prediction marginalises fresh job variation; it is not a confidence interval for a fixed duration. One persistent effect per equipment/clock group, held constant within a run. Incompatible evidence retains the declared prior and blocks model-based predictions.",
    )
    if conditionals:
        result["job_conditionals"] = {}
        for order, job in grouped.items():
            if job["exact"] is not None:
                value = dict(bins=[[job["exact"], job["exact"]]], weights=[1.0])
            else:
                value = estimate(
                    item,
                    [r for r in rows if r["order_id"] != order],
                    bounds,
                    hour,
                    max_age,
                    conditionals=False,
                )
                value["minimum_elapsed_factor"] = job["lower"]
            result["job_conditionals"][order] = value
    return result


def record(options, observations, hour):
    model = options["duration_model"]
    base, equipment = {}, {}
    for key in GROUPS:
        base[key] = estimate(
            model["groups"][key],
            [],
            options["duration_bounds"][key],
            hour,
            options["evidence_max_age_hours"],
        )
    for asset in sorted({r["asset_id"] for r in observations if r["group"] is not None}):
        equipment[asset] = {}
        for key in GROUPS:
            rows = [r for r in observations if r["asset_id"] == asset and r["group"] == key]
            equipment[asset][key] = estimate(
                model["groups"][key],
                rows,
                options["duration_bounds"][key],
                hour,
                options["evidence_max_age_hours"],
            )
    return dict(durations=base, equipment_durations=equipment, duration_model_id=digest(model))


def for_plan(belief, plan, key):
    if belief["options"]["mode"] == "fixed":
        return belief["durations"][key]
    value = (
        belief.get("equipment_durations", {})
        .get(plan.asset.asset_id, {})
        .get(key, belief["durations"][key])
    )
    if value.get("unsupported"):
        raise ValueError("Equipment duration evidence lies outside the declared model support")
    return value.get("job_conditionals", {}).get(plan.order.order_id, value)
