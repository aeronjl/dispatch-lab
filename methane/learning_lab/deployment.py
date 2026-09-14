"""Data-only planning aids: no executable plugins, plant truth or actuation API."""

import copy
import math
import time

from methane.learning_lab.datasets import PORT
from methane.learning_lab.estimators import VERSION as MODEL_VERSION
from methane.learning_lab.estimators import features, predict
from methane.siting.store import digest, encode

VERSION = "bounded-policy-deployment/1"


def validate(value):
    if value.get("version") != VERSION or value.get("port") != PORT:
        raise ValueError("Unsupported deployment interface")
    if len(encode(value)) > 100000:
        raise ValueError("Deployment exceeds 100 KB data-only artifact budget")
    if value.get("mode") not in ("shadow", "forecast-aid", "homeostatic"):
        raise ValueError("Unknown deployment mode")
    if value.get("fallback") != "original-policy":
        raise ValueError("Deployment fallback must preserve the original policy")
    budget = value.get("budget_ms")
    if type(budget) not in (int, float) or not math.isfinite(budget) or not 0 < budget <= 100:
        raise ValueError("Inference budget must be greater than 0 and at most 100 ms")
    model = value.get("model")
    if model:
        if digest(model) != value.get("model_id") or model.get("version") != MODEL_VERSION:
            raise ValueError("Frozen model identity mismatch")
        if value["mode"] == "forecast-aid" and model["task"] != "pv":
            raise ValueError("Only an observed-PV model can modify forecast PV")
        for key, length in (("weights", 5), ("mean", 4), ("scale", 4)):
            if len(model[key]) != length or not all(
                type(x) in (int, float) and math.isfinite(x) for x in model[key]
            ):
                raise ValueError("Invalid bounded model operands")
        if any(x <= 0 for x in model["scale"]):
            raise ValueError("Preprocessing scale must be positive")
    elif value["mode"] != "homeostatic":
        raise ValueError("Shadow or forecast aid needs a registered model")
    from methane.learning_lab.reserves import validate as validate_reserves

    validate_reserves(value["reserves"])
    return copy.deepcopy(value)


def register(store, *, name, model_id=None, mode="shadow", budget_ms=20, reserves=None):
    from methane.learning_lab.reserves import DEFAULTS

    model = store.get("model", model_id) if model_id else None
    if not name.strip():
        raise ValueError("Name the experimental policy")
    value = validate(
        dict(
            version=VERSION,
            port=PORT,
            name=name,
            model_id=model_id,
            model=model,
            mode=mode,
            budget_ms=budget_ms,
            fallback="original-policy",
            reserves=reserves or DEFAULTS,
            scope="Simulator planning aid. Hard limits and service capabilities remain in existing execution kernels. Shadow predictions do not alter actions. Only the first future PV prediction changes in forecast-aid mode; current measured PV is immutable.",
        )
    )
    return dict(id=store.put("deployment", value), **value)


def apply(value, packet, forecast):
    """Bounded O(4) inference; return trace even when model applicability fails."""
    started = time.perf_counter()
    original = copy.deepcopy(forecast)
    trace = dict(
        deployment_id=digest(value),
        name=value.get("name"),
        input_id=digest(packet),
        port=PORT,
        status="fallback",
        proposed=None,
        applied=None,
        missing=packet.get("missing", []),
        fallback="original-policy",
    )
    try:
        validate(value)
        trace["mode"] = value["mode"]
        candidate = copy.deepcopy(original)
        if value.get("model"):
            model = value["model"]
            x = features(packet, model["task"])
            if x is None:
                raise ValueError("Required observed channel is unavailable")
            prediction = predict(model, x)
            trace.update(
                model_id=value["model_id"],
                features=x,
                proposed=prediction,
                error_band=model["error_band"],
                units=model["units"],
            )
            if model["error_band"] is None:
                raise ValueError("Validation error band unavailable")
            if value["mode"] == "forecast-aid":
                if len(candidate["pv_kw"]) < 2:
                    raise ValueError("No future interval in the original forecast")
                if prediction > packet["plant"]["solar_kw"]:
                    raise ValueError("Prediction exceeds declared solar capacity")
                candidate["pv_kw"][1] = prediction
                trace["applied"] = dict(
                    interval=1, original_kw=original["pv_kw"][1], predicted_kw=prediction
                )
        if value["mode"] == "homeostatic":
            candidate["reserve_policy"] = copy.deepcopy(value["reserves"])
            trace["applied"] = dict(
                reserves=value["reserves"],
                support=packet.get("support"),
                boundary="Process reserves are soft targets. Service energy follows recorded demands; robot reserves remain in the explicit service policy. Spare/reference availability and unfinished work are reported, not invented as process dispatch decisions.",
            )
        elapsed = (time.perf_counter() - started) * 1000
        if elapsed > value["budget_ms"]:
            raise TimeoutError("Inference exceeded registered budget")
        trace.update(
            status="shadow" if value["mode"] == "shadow" else "applied", elapsed_ms=elapsed
        )
        return candidate, trace
    except (ValueError, KeyError, TypeError, IndexError, OverflowError, TimeoutError) as exc:
        trace.update(
            reason=str(exc), elapsed_ms=(time.perf_counter() - started) * 1000, applied=None
        )
        return original, trace
