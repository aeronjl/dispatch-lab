"""Executable reference-device models; no import into the plant's dispatch kernels."""

from functools import lru_cache
from typing import Literal

import numpy as np
from pydantic import Field
from scipy.optimize import least_squares

from methane.siting.contracts import Record


class PEMRequest(Record):
    profile: Literal["csu-pem"] = "csu-pem"
    power: Literal["system_power", "stack_power"] = "system_power"
    channel: Literal["hydrogen_flow", "hydrogen_flow_cs"] = "hydrogen_flow"
    model: Literal["affine", "constant-specific"] = "affine"
    query_kw: float = Field(default=45, gt=0, le=100)
    flow_offset_bound: float = Field(default=0, ge=0, le=0.1)


class ReactorRequest(Record):
    profile: Literal["kit-slurry"] = "kit-slurry"
    query_minutes: float = Field(default=20, ge=0, le=40)
    digitization_bound_k: float = Field(default=1, ge=0, le=3)


def request(data):
    if data.get("profile") == "csu-pem":
        return PEMRequest(**data)
    if data.get("profile") == "kit-slurry":
        return ReactorRequest(**data)
    raise ValueError("Choose a supported reference-device adapter")


def linear_fit(x, y, model):
    if model == "constant-specific":
        return np.array([x @ y / (x @ x), 0.0])
    a = np.column_stack((x, np.ones(len(x))))
    if np.linalg.matrix_rank(a) != 2:
        raise ValueError("Power variation is insufficient to identify an affine relationship")
    return np.linalg.lstsq(a, y, rcond=None)[0]


def summary(observed, predicted):
    residual = np.asarray(predicted) - np.asarray(observed)
    return dict(
        n=len(residual), bias=float(np.mean(residual)), rmse=float(np.sqrt(np.mean(residual**2)))
    )


def pem(profile, inputs):
    rows = profile["data"]["rows"]
    train = [r for r in rows if r["split"] == "development"]
    test = [r for r in rows if r["split"] == "evaluation"]
    x = np.array([r[inputs.power] for r in train])
    y = np.array([r[inputs.channel] for r in train])
    # Declare the observed reference envelope, separately from the fitting range.
    low, high = min(r[inputs.power] for r in rows), max(r[inputs.power] for r in rows)
    if not low <= inputs.query_kw <= high:
        raise ValueError(
            f"Query outside the observed {inputs.power} envelope: {low:.3f}–{high:.3f} kW; no extrapolation"
        )
    coefficients = linear_fit(x, y, inputs.model)
    slope, intercept = map(float, coefficients)
    comparisons = []
    for model in ("affine", "constant-specific"):
        p = linear_fit(x, y, model)
        comparisons.append(
            dict(
                model=model,
                coefficients=p.tolist(),
                **summary(
                    [r[inputs.channel] for r in test],
                    [float(p[0] * r[inputs.power] + p[1]) for r in test],
                ),
            )
        )
    fitted = [
        dict(
            **r,
            x=r[inputs.power],
            observed=r[inputs.channel],
            predicted=float(slope * r[inputs.power] + intercept),
            residual=float(slope * r[inputs.power] + intercept - r[inputs.channel]),
        )
        for r in rows
    ]
    # Keep paired coefficients; marginal slope/intercept extremes are not mixed.
    variants = [
        dict(
            reason="omit development plateau",
            omitted_segment=train[i]["segment"],
            coefficients=linear_fit(np.delete(x, i), np.delete(y, i), inputs.model).tolist(),
        )
        for i in range(len(train))
    ]
    offsets = [
        dict(offset_kgph=offset, coefficients=linear_fit(x, y + offset, inputs.model).tolist())
        for offset in (-inputs.flow_offset_bound, inputs.flow_offset_bound)
    ]
    query_sensitivity = [
        v["coefficients"][0] * inputs.query_kw + v["coefficients"][1] for v in variants
    ]
    query_offsets = [v["coefficients"][0] * inputs.query_kw + v["coefficients"][1] for v in offsets]
    curve = []
    for v in np.linspace(low, high, 81):
        sensitivity = [p["coefficients"][0] * v + p["coefficients"][1] for p in variants]
        meter = [p["coefficients"][0] * v + p["coefficients"][1] for p in offsets]
        curve.append(
            dict(
                x=float(v),
                predicted=float(slope * v + intercept),
                low=float(min(sensitivity)),
                high=float(max(sensitivity)),
                measurement_low=float(min(meter)),
                measurement_high=float(max(meter)),
            )
        )
    return dict(
        model_identity="csu-pem-" + inputs.model + "/1",
        unit="kg/h",
        x_label=inputs.power + " · kW",
        parameters=dict(slope_kg_per_kwh=slope, intercept_kgph=intercept),
        equation="hydrogen channel (kg/h) = slope (kg/kWh) × selected power (kW) + intercept (kg/h)",
        domain=dict(observed=[low, high], fitted=[float(min(x)), float(max(x))]),
        query=dict(
            x=inputs.query_kw,
            predicted=slope * inputs.query_kw + intercept,
            parameter_low=min(query_sensitivity),
            parameter_high=max(query_sensitivity),
            measurement_low=min(query_offsets),
            measurement_high=max(query_offsets),
        ),
        rows=fitted,
        curve=curve,
        comparisons=comparisons,
        statistics={
            split: summary(
                [r["observed"] for r in fitted if r["split"] == split],
                [r["predicted"] for r in fitted if r["split"] == split],
            )
            for split in ("development", "evaluation")
        },
        sensitivity=dict(
            parameter_vectors=variants,
            measurement_scenarios=offsets,
            scope="Band: leave-one-development-plateau-out parameter sensitivity. Separate coherent flow-offset scenarios use the supplied bound; zero means not assessed. Neither is a confidence or prediction interval. Correlated coefficients stay paired.",
        ),
        claims=[
            dict(
                claim="Evaluation samples excluded from fitting",
                outcome="passed",
                method="Frozen per-plateau first/second halves; eight paired plateaus",
            ),
            dict(
                claim="Independent equipment validation",
                outcome="unsupported",
                method="Same device and day; adjacent halves are correlated and data has previously been inspected",
            ),
            dict(
                claim="Startup and AEM transfer",
                outcome="unsupported",
                method="No identified model or transfer map",
            ),
        ],
    )


def step_temperature(t, parameters):
    base, increment, tau = parameters
    return base + increment * -np.expm1(-np.maximum(np.asarray(t) - 5, 0) / tau)


def step_fit(t, y):
    fit = least_squares(
        lambda p: step_temperature(t, p) - y,
        [320, 14, 8],
        bounds=([315, 5, 0.1], [325, 25, 50]),
        ftol=1e-10,
        xtol=1e-10,
        gtol=1e-10,
    )
    if not fit.success or not np.isfinite(fit.x).all():
        raise ValueError("Reference response fit did not converge")
    return fit.x


@lru_cache(maxsize=32)
def step_ensemble(points, bound):
    t, y = np.array(points).T
    p = step_fit(t, y)
    # Deliberate digitization stress, not an inferred experimental error distribution.
    rng = np.random.default_rng(20260917)
    variants = (
        [step_fit(t, y + rng.uniform(-bound, bound, len(y))).tolist() for _ in range(64)]
        if bound
        else [p.tolist()]
    )
    return p.tolist(), variants


def reactor(profile, inputs):
    rows = profile["data"]["rows"]
    points = tuple((r["time_minutes"], r["temperature_c"]) for r in rows)
    p, variants = step_ensemble(points, inputs.digitization_bound_k)
    t, y = np.array(points).T
    prediction = step_temperature(t, p)
    fitted = [
        dict(
            **r,
            x=float(t[i]),
            observed=float(y[i]),
            predicted=float(prediction[i]),
            residual=float(prediction[i] - y[i]),
        )
        for i, r in enumerate(rows)
    ]
    curve = []
    for v in np.linspace(0, 40, 81):
        sensitivity = [float(step_temperature(v, other)) for other in variants]
        curve.append(
            dict(
                x=float(v),
                predicted=float(step_temperature(v, p)),
                low=min(sensitivity),
                high=max(sensitivity),
            )
        )
    return dict(
        model_identity="kit-slurry-first-order/1",
        unit="°C",
        x_label="Time from figure origin · min",
        parameters=dict(baseline_c=p[0], increment_k=p[1], tau_minutes=p[2], step_minutes=5),
        equation="T(t) = baseline + increment × (1 − exp(−max(t − 5, 0) / tau)); time in minutes",
        domain=dict(observed=[float(min(t)), float(max(t))], illustrated=[0, 40]),
        query=dict(
            x=inputs.query_minutes, predicted=float(step_temperature(inputs.query_minutes, p))
        ),
        rows=fitted,
        curve=curve,
        comparisons=[],
        statistics=dict(descriptive=summary(y, prediction)),
        sensitivity=dict(
            seed=20260917,
            replicates=len(variants),
            parameter_vectors=variants,
            scope="Band: min/max of 64 seeded fits with independent uniform vertical digitization perturbations within the chosen bound (one fit at zero). This stress assumption is not sensor noise, a probability interval or transfer uncertainty.",
        ),
        claims=[
            dict(
                claim="Descriptive first-order response",
                outcome="reported",
                method="All twelve manually digitized points fitted; 30 s ramp approximated by an ideal step",
            ),
            dict(
                claim="Held-out validation",
                outcome="missing",
                method="No independent thermal trace available in this adapter",
            ),
            dict(
                claim="Independent thermal capacity and ambient heat loss",
                outcome="unsupported",
                method="Controlled-coolant response identifies neither C nor ambient UA separately",
            ),
        ],
    )
