"""Small inspectable models. Episode holdouts select no simulator truth features.

These models predict subsequent measured channels or observed completed clocks;
they cannot establish fault cause, true condition or remaining useful life.
"""

import json
import math
import time
from collections import defaultdict

import numpy as np

from methane.learning_lab.datasets import PORT, validate_splits

VERSION = "bounded-estimator/1"
TASKS = {
    "pv": ("Next observed PV", "kW"),
    "solar_condition": ("Next solar condition reading", "fraction loss"),
    "electrolyser_condition": ("Next electrolyser condition reading", "fraction loss"),
    "soiling": ("Next removable-surface reading", "fraction loss"),
    "duration": ("Completed phase duration / nominal", "ratio"),
}
FEATURES = ["previous_reading", "activity_kw", "ambient_c", "age_hours"]


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def reading(p, task):
    if task == "pv":
        values = p["forecast"].get("pv_kw", [])
        return (values[0] if values else None), p["hour"]
    if task == "soiling":
        return p.get("soiling", {}).get("soiling_estimate"), p["hour"]
    if task.endswith("_condition"):
        m = p.get("condition", {}).get(task.removesuffix("_condition"), {})
        return m.get("value"), m.get("measured_at")
    return None, None


def features(p, task):
    value, measured = reading(p, task)
    ambient = p["forecast"].get("ambient_c", [None])[0]
    activity = p["observations"].get("power_kw")
    if not all(finite(x) for x in (value, measured, ambient, activity)):
        return None
    return [value, activity, ambient, p["hour"] - measured]


def examples(samples, task):
    if task not in TASKS:
        raise ValueError("Unknown estimator task; no unsupported RUL target is offered")
    grouped = defaultdict(list)
    for s in samples:
        grouped[s["episode"]].append(s)
    rows, exclusions = [], []
    for episode, seq in grouped.items():
        seq.sort(key=lambda s: s["packet"]["hour"])
        if task == "duration":
            clocks = {}
            for s in seq:
                for clock in s["packet"].get("duration_observations", []):
                    clocks[clock["id"]] = (clock, s)
            for clock, s in clocks.values():
                if clock["censored"] or clock["nominal_hours"] <= 0:
                    exclusions.append(
                        dict(
                            episode=episode,
                            id=clock["id"],
                            reason="Right-censored work; not a completed-duration label",
                            lower_hours=clock["elapsed_hours"],
                        )
                    )
                    continue
                # Only nominal duration is known at start. Never use elapsed or
                # eventual completion as a predictor of that same duration.
                rows.append(
                    dict(
                        episode=episode,
                        split=s["split"],
                        id=s["id"] + "/" + clock["id"],
                        x=[1.0, 0.0, 20.0, 0.0],
                        baseline=1.0,
                        y=clock["elapsed_hours"] / clock["nominal_hours"],
                        hour=clock["started_at"],
                        available_at=clock["available_at"],
                        group=clock["group"],
                    )
                )
            continue
        for a, b in zip(seq, seq[1:], strict=False):
            p, next_p = a["packet"], b["packet"]
            x = features(p, task)
            y, measured = reading(next_p, task)
            prior_measured = reading(p, task)[1]
            reason = None
            if x is None or not finite(y):
                reason = "Required observed channel is missing"
            elif measured == prior_measured:
                reason = "No new independent reading; repeated stale meter value"
            elif next_p["hour"] != p["hour"] + 1:
                reason = "Missing adjacent observation boundary"
            elif (
                task == "pv"
                and max(
                    x[0],
                    p["forecast"].get("pv_kw", [0, 0])[1:2][0]
                    if len(p["forecast"].get("pv_kw", [])) > 1
                    else 0,
                )
                < 10
            ):
                reason = "Insufficient solar excitation (<10 kW); no gain identification"
            if reason:
                exclusions.append(dict(episode=episode, id=a["id"], reason=reason))
                continue
            forecast = p["forecast"].get("pv_kw", [])
            baseline = forecast[1] if task == "pv" and len(forecast) > 1 else x[0]
            rows.append(
                dict(
                    episode=episode,
                    split=a["split"],
                    id=a["id"],
                    x=x,
                    y=y,
                    baseline=baseline,
                    hour=p["hour"],
                    available_at=next_p["hour"],
                )
            )
    return rows, exclusions


def predict(model, x):
    if model.get("version") != VERSION or model.get("port") != PORT:
        raise ValueError("Model interface is incompatible")
    if len(x) != len(FEATURES) or not all(finite(v) for v in x):
        raise ValueError("Missing or invalid features")
    if any(v < lo - 1e-8 or v > hi + 1e-8 for v, (lo, hi) in zip(x, model["domain"], strict=True)):
        raise ValueError("Features outside the registered training domain")
    z = [
        1.0,
        *[
            (v - mean) / scale
            for v, mean, scale in zip(x, model["mean"], model["scale"], strict=True)
        ],
    ]
    result = sum(a * b for a, b in zip(z, model["weights"], strict=True))
    if not finite(result) or result < 0:
        raise ValueError("Prediction is negative or non-finite")
    return result


def metrics(rows):
    valid = [r for r in rows if r["prediction"] is not None]
    errors = [abs(r["prediction"] - r["observed"]) for r in valid]
    return dict(
        count=len(rows),
        predictions=len(valid),
        unavailable=len(rows) - len(valid),
        mae=sum(errors) / len(errors) if errors else None,
        coverage=sum(r["lower"] <= r["observed"] <= r["upper"] for r in valid) / len(valid)
        if valid
        else None,
        mean_width=sum(r["upper"] - r["lower"] for r in valid) / len(valid) if valid else None,
    )


def fit(
    store,
    dataset_id,
    *,
    task="pv",
    ridge=1.0,
    seed=7,
    name="Observation estimator",
    progress=None,
    cancelled=None,
):
    started = time.monotonic()
    if not finite(ridge) or not 0.000001 <= ridge <= 10000 or type(seed) is not int:
        raise ValueError("Declare a positive ridge penalty (1e-6–10000) and integer seed")
    data = store.get("dataset", dataset_id)
    validate_splits(data["episodes"], data["holdout_axes"])
    samples = json.loads(store.read_raw(data["observations_sha256"]))
    if len(samples) > 100000:
        raise ValueError("Training budget is 100,000 observations; use a declared smaller dataset")
    rows, excluded = examples(samples, task)
    by_split = {k: [r for r in rows if r["split"] == k] for k in ("train", "validation", "test")}
    protocol = dict(
        version="estimator-protocol/1",
        dataset_id=dataset_id,
        task=task,
        ridge=ridge,
        seed=seed,
        features=FEATURES,
        transform="Training-mean centring and population standard deviation; constant channels use scale 1",
        label="Subsequent observed channel or completed clock; no private truth labels",
        interval="90th percentile absolute validation error; empirical error band, no coverage guarantee",
        selection="Penalty declared before fitting; validation calibrates error bands; test is evaluation only",
    )
    result = dict(
        version="estimator-evaluation/1",
        name=name,
        protocol=protocol,
        exclusions=excluded,
        rows_per_split={k: len(v) for k, v in by_split.items()},
        status="incomplete",
        source=None,
        scope="Synthetic observed-channel prediction; not physical identification, remaining useful life or field calibration. Duration fits completed phases only; censored jobs remain explicit and require the existing survival-likelihood model for unbiased duration inference.",
    )
    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE

    result["source"] = LOADED_SOURCE["content_hash"]
    if any(len(v) < 2 for v in by_split.values()):
        result["reason"] = (
            "Each split needs at least two informative examples; unavailable channels are not synthesised"
        )
        return dict(id=store.put("evaluation", result), **result)
    if cancelled and cancelled():
        raise InterruptedError("Training cancelled")
    if progress:
        progress("Fitting four-feature ridge model on training episodes")
    train = by_split["train"]
    x = np.asarray([r["x"] for r in train])
    y = np.asarray([r["y"] for r in train])
    mean, scale = x.mean(axis=0), x.std(axis=0)
    scale[scale < 1e-12] = 1
    z = np.column_stack((np.ones(len(x)), (x - mean) / scale))
    penalty = np.diag([0.0, *([ridge] * len(FEATURES))])
    weights = np.linalg.solve(z.T @ z + penalty, z.T @ y)
    # Applicability is observed training support. Never widen it with held-out data.
    model = dict(
        version=VERSION,
        port=PORT,
        name=name,
        task=task,
        protocol=protocol,
        dataset_id=dataset_id,
        source=LOADED_SOURCE["content_hash"],
        source_capsule_sha256=LOADED_CAPSULE["sha256"],
        mean=mean.tolist(),
        scale=scale.tolist(),
        weights=weights.tolist(),
        domain=[[float(min(v)), float(max(v))] for v in x.T],
        applicability={
            k: sorted({e[k] for e in data["episodes"] if e["split"] == "train"})
            for k in ("design", "equipment")
        },
        units=TASKS[task][1],
        training_examples=len(train),
    )
    bands, outcomes = {}, {}
    for strategy in ("fixed", "adaptive", "ridge"):
        errors = []
        outcomes[strategy] = []
        for split in ("validation", "test"):
            adaptive = {}
            pending = defaultdict(list)
            for row in sorted(by_split[split], key=lambda r: (r["episode"], r["hour"])):
                if cancelled and cancelled():
                    raise InterruptedError("Training cancelled before publication")
                episode = row["episode"]
                adjustment = adaptive.get(episode, 0.0)
                ready = [r for r in pending[episode] if r["available_at"] <= row["hour"]]
                pending[episode] = [r for r in pending[episode] if r["available_at"] > row["hour"]]
                for past in ready:
                    adjustment += 0.2 * (past["y"] - past["baseline"] - adjustment)
                adaptive[episode] = adjustment
                status = "predicted"
                try:
                    prediction = (
                        predict(model, row["x"])
                        if strategy == "ridge"
                        else max(
                            0.0, row["baseline"] + (adjustment if strategy == "adaptive" else 0.0)
                        )
                    )
                except ValueError as exc:
                    prediction, status = None, str(exc)
                # Completed service clocks can arrive much later than the next
                # job starts. Queue the outcome until its recorded availability.
                pending[episode].append(row)
                if split == "validation":
                    if prediction is not None:
                        errors.append(abs(prediction - row["y"]))
                    continue
                band = float(np.quantile(errors, 0.9)) if errors else None
                outcomes[strategy].append(
                    dict(
                        id=row["id"],
                        episode=episode,
                        observed=row["y"],
                        prediction=prediction,
                        status=status,
                        lower=max(0.0, prediction - band)
                        if prediction is not None and band is not None
                        else None,
                        upper=prediction + band
                        if prediction is not None and band is not None
                        else None,
                    )
                )
            if split == "validation":
                bands[strategy] = float(np.quantile(errors, 0.9)) if errors else None
        if bands[strategy] is None:
            for r in outcomes[strategy]:
                r.update(
                    prediction=None,
                    status="No applicable validation examples; uncertainty unavailable",
                )
    model["error_band"] = bands["ridge"]
    model["limitations"] = result["scope"]
    model["capsule_raw_sha256"] = store.raw(json.dumps(LOADED_CAPSULE, sort_keys=True).encode())
    model_id = store.put("model", model)
    result.update(
        status="complete",
        model_id=model_id,
        model=model,
        comparisons={k: metrics(v) for k, v in outcomes.items()},
        outcomes=outcomes,
        error_bands=bands,
        wall_seconds=time.monotonic() - started,
        data_bytes=len(store.read_raw(data["observations_sha256"])),
        detection_delay="Not identifiable from next-reading prediction; diagnostic incident metrics remain in operating studies",
        decision_consequences="Run a matched deployed-policy study; prediction error alone is not production value",
    )
    return dict(id=store.put("evaluation", result), **result)
