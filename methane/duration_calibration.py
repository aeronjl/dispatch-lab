"""Auditable finite-model selection with a predeclared observation-time holdout.

Inputs are measured phase clocks with known nominal recipes. This interface does
not infer unseen faults, equipment truth, or service opportunity denominators.
"""

import argparse
import copy
import json
import math
from pathlib import Path

from methane.duration_population import estimate, jobs, likelihood, validate
from methane.provenance import digest
from methane.services.uncertain_timing import GROUPS

VERSION = "service-duration-calibration/1"


def dataset(value):
    if set(value) != {"version", "source", "observations"} or value["version"] != VERSION:
        raise ValueError("Supply a versioned clock-observation dataset")
    source = value["source"]
    if (
        set(source) != {"id", "kind", "reference"}
        or source["kind"] not in ("field-observation", "simulated-observation")
        or not all(source.values())
    ):
        raise ValueError("Identify field or simulated observations and their original source")
    for row in value["observations"]:
        if row.get("group") not in GROUPS:
            raise ValueError("Unknown observed clock group")
        for key in ("asset_id", "order_id", "id", "group"):
            if not isinstance(row.get(key), str) or not row[key]:
                raise ValueError(
                    "Observation requires equipment, job, phase and clock-group identities"
                )
        for key in ("available_at", "started_at", "elapsed_hours", "nominal_hours"):
            if (
                type(row.get(key)) not in (float, int)
                or not math.isfinite(row[key])
                or row[key] < 0
            ):
                raise ValueError("Observation clock operands must be finite and nonnegative")
        if (
            row["nominal_hours"] <= 0
            or row["available_at"] < row["started_at"] + row["elapsed_hours"] - 1e-7
        ):
            raise ValueError("Phase duration cannot extend beyond its observation boundary")
        if type(row.get("censored")) is not bool or row["censored"] != (
            row.get("completed_at") is None
        ):
            raise ValueError("Distinguish completed and right-censored phase clocks")
        if (
            not row["censored"]
            and abs(row["completed_at"] - row["started_at"] - row["elapsed_hours"]) > 1e-7
        ):
            raise ValueError("Completed phase clock does not reconcile")
    digest(value)
    return copy.deepcopy(value)


def grouped(rows):
    result = {}
    for row in rows:
        result.setdefault((row["asset_id"], row["group"]), []).append(row)
    return result


def score(model, train, test, bounds, hour):
    """Conditional predictive density/survival on held-out *jobs*, not phases."""
    training = grouped(train)
    total, count, unsupported, outcomes = 0.0, 0, [], []
    for (asset, group), rows in grouped(test).items():
        item = model["groups"][group]
        posterior = estimate(item, training.get((asset, group), []), bounds[group], hour, 1e12)
        for order, job in jobs(rows).items():
            probability = sum(
                w * likelihood(job, a, b)
                for w, (a, b) in zip(posterior["weights"], posterior["bins"], strict=True)
            )
            if posterior["unsupported"] or probability <= 0:
                unsupported.append(order)
            else:
                total -= math.log(probability)
            count += 1
            from methane.services.uncertain_planning import quantile

            lo, hi = quantile(posterior, 0.05), quantile(posterior, 0.95)
            outcomes.append(
                dict(
                    asset=asset,
                    group=group,
                    order_id=order,
                    factor=job["exact"],
                    censored_after_factor=job["lower"],
                    predictive_interval_90=[lo, hi],
                    covered=None if job["exact"] is None else lo <= job["exact"] <= hi,
                    density_or_survival=probability,
                )
            )
    return dict(
        negative_log_score=None if unsupported else total,
        jobs=count,
        unsupported=sorted(set(unsupported)),
        outcomes=outcomes,
    )


def fit(value, candidates, cutoff, bounds):
    value = dataset(value)
    if not math.isfinite(cutoff) or cutoff < 0 or not candidates:
        raise ValueError("Predeclare a nonnegative time boundary and candidate models")
    observations = value["observations"]
    before = [r for r in observations if r["available_at"] <= cutoff]
    used_jobs = {r["order_id"] for r in before}
    after = [
        r
        for r in observations
        if r["available_at"] > cutoff
        and r["started_at"] >= cutoff
        and r["order_id"] not in used_jobs
    ]
    if not before or not after:
        raise ValueError(
            "Calibration requires training observations and separate future held-out jobs"
        )
    models = [validate(c, bounds) for c in candidates]
    # Marginal evidence per equipment/group integrates the common persistent
    # factor once. Multiplying marginal per-job densities would erase correlation.
    scores = []
    for model in models:
        loss, unsupported = 0.0, []
        for (asset, group), rows in grouped(before).items():
            item = model["groups"][group]
            logs = []
            for persistent, prior in zip(
                item["persistent_factors"], item["prior_weights"], strict=True
            ):
                a, b = [persistent * x for x in item["job_multiplier_bounds"]]
                values = [likelihood(j, a, b) for j in jobs(rows).values()]
                logs.append(
                    math.log(prior) + sum(math.log(x) for x in values) if all(values) else -math.inf
                )
            largest = max(logs)
            if largest == -math.inf:
                unsupported.append([asset, group])
            else:
                loss -= largest + math.log(sum(math.exp(v - largest) for v in logs))
        scores.append(
            dict(
                model_id=digest(model),
                training_negative_log_evidence=None if unsupported else loss,
                unsupported=unsupported,
            )
        )
    valid = [i for i, s in enumerate(scores) if s["training_negative_log_evidence"] is not None]
    chosen = (
        min(
            valid,
            key=lambda i: (scores[i]["training_negative_log_evidence"], scores[i]["model_id"]),
        )
        if valid
        else None
    )
    result = dict(
        version=VERSION,
        dataset_id=digest(value),
        source=value["source"],
        cutoff=cutoff,
        training_ids=sorted({r["id"] for r in before}),
        heldout_ids=sorted({r["id"] for r in after}),
        candidates=models,
        training_scores=scores,
        selected_model=models[chosen] if chosen is not None else None,
        status="fitted" if chosen is not None else "incomplete: all candidate models contradicted",
        scope="Finite candidate selection under declared uniform job noise and persistent support. Held-out jobs do not select the model. Density scores are not event probabilities. Censored jobs use survival likelihoods. Simulator clocks verify the workflow; they do not establish field calibration or identifiability.",
    )
    if chosen is not None:
        result["heldout"] = score(models[chosen], before, after, bounds, cutoff)
        groups = grouped(before)
        result["identification_gaps"] = [
            list(k) for k, rows in groups.items() if len(jobs(rows)) < 3
        ]
        if result["heldout"]["unsupported"]:
            result["status"] = "held-out model inadequacy"
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "protocol", type=Path, help="JSON containing dataset, candidates, cutoff and bounds"
    )
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    p = json.loads(args.protocol.read_text())
    result = fit(p["dataset"], p["candidates"], p["cutoff"], p["bounds"])
    # An existing calibration edition is never silently replaced.
    with args.output.open("x") as stream:
        json.dump(result, stream, indent=2, allow_nan=False)


if __name__ == "__main__":
    main()
