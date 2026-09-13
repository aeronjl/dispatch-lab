"""Illustrative section-level PV model and immutable saved-weather design previews.

The archived source contains tilted irradiance, not independent DNI/DHI. Changed
orientations therefore use an explicitly assumed isotropic sky with 30% diffuse
horizontal irradiance, normalized to the archived reference plane. This is a
sensitivity model, not a calibrated site/shading or electrical string model.
"""

import copy
import json

from methane.pv import dc_power
from methane.solar_model import (
    MODEL as MODEL,
)
from methane.solar_model import (
    NOTE,
    _validated_interval,
    default_design,
    interval,
    validate,
)
from methane.solar_model import (
    SolarInput as SolarInput,
)
from methane.solar_model import (
    component_step as component_step,
)


def source_weather(result):
    return result["weather"].get("solar_reference_weather", result["weather"])


def source_config(result):
    from methane.config import Config

    return Config.from_dict(result["weather"].get("solar_reference_config", result["config"]))


def design_for(result):
    c = source_config(result)
    return result["config"].get("solar") or default_design(c.plant, c.weather)


def preview(result, design=None):
    design = validate(design or design_for(result))
    source, c = source_weather(result), source_config(result)
    encoded_design = json.dumps(design, sort_keys=True)
    frames = [
        _validated_interval(encoded_design, source["truth"][t], t, c.plant, c.weather)
        for t in result["weather"]["times"]
    ]
    return {
        "run_id": result["run_id"],
        "design": design,
        "frames": frames,
        "note": NOTE,
        "energy_kwh": sum(f["output_kw"] for f in frames),
        "recorded_energy_kwh": sum(
            result["weather"]["truth"][t]["pv_kw"] for t in result["weather"]["times"]
        ),
    }


def _with_radiation(sample, p, w):
    if "irradiance_wm2" in sample:
        return sample
    # Old synthetic forecast templates stored only power. Invert the monotone
    # part of their documented conversion, explicitly recording this fallback.
    if sample["pv_kw"] >= p.solar_kw - 1e-7 and p.solar_kw > 0:
        raise ValueError("Archived forecast clips at nameplate; irradiance cannot be recovered.")
    lo, hi = 0.0, 1000.0
    for _ in range(45):
        mid = (lo + hi) / 2
        if dc_power(mid, sample["ambient_c"], p, w) < sample["pv_kw"]:
            lo = mid
        else:
            hi = mid
    if abs(dc_power(hi, sample["ambient_c"], p, w) - sample["pv_kw"]) > 1e-5:
        raise ValueError("Archived forecast lacks recoverable irradiance; start a new experiment.")
    return {**sample, "irradiance_wm2": hi, "radiation_basis": "inverted legacy PV conversion"}


def transform_weather(weather, config, design):
    """Transform truth and each original forecast independently, preserving availability."""
    base = weather.get("solar_reference_weather", weather)
    from methane.config import Config

    reference = Config.from_dict(weather.get("solar_reference_config", config.to_dict()))
    out = copy.deepcopy(base)
    for mapping in [
        out["truth"],
        out.get("template", {}),
        *[v["data"] for v in out.get("vintages", [])],
    ]:
        for time, sample in mapping.items():
            source = _with_radiation(sample, reference.plant, reference.weather)
            detail = interval(design, source, time, reference.plant, reference.weather)
            sample.update(pv_kw=detail["output_kw"], solar_detail=detail)
    out["solar_design"] = copy.deepcopy(design)
    out["solar_reference_weather"] = copy.deepcopy(base)
    out["solar_reference_config"] = reference.to_dict()
    out["solar_model_note"] = NOTE
    return out


def execution_record(weather, config, t):
    """Record the actual source conversion separately from hypothetical section previews."""
    from dataclasses import asdict

    from methane.pv import Parameters

    time = weather["times"][t]
    actual = weather["truth"][time]
    reference = weather.get("solar_reference_weather", weather)["truth"][time]
    source = source_config({"weather": weather, "config": config.to_dict()})
    p, w = source.plant, source.weather
    parameters = asdict(
        Parameters(p.solar_kw, w.loss_fraction, w.noct_c, w.temperature_coefficient)
    )
    detail = actual.get("solar_detail")
    if detail:
        parameters.update(
            design_json=json.dumps(weather["solar_design"], sort_keys=True),
            latitude=w.latitude,
            longitude=w.longitude,
            tilt=w.tilt,
            azimuth=w.azimuth,
        )
    ideal = dc_power(reference["irradiance_wm2"], reference["ambient_c"], p, w)
    return dict(
        schema_version="dispatch-lab/component-record/1",
        model_id="dispatch-lab/solar-sections" if detail else "dispatch-lab/reference-pv",
        model_version="2" if detail else "1",
        implementation_id="sections/2" if detail else "noct-linear/1",
        parameters=parameters,
        before={},
        inputs={
            "time": time,
            "irradiance_wm2": reference["irradiance_wm2"],
            "ambient_c": reference["ambient_c"],
            "scenario_pv_kw": reference["pv_kw"],
        },
        after={},
        flows={
            "output_kw": actual["pv_kw"],
            "reference_power_kw": ideal,
            "source_scenario_adjustment_kw": reference["pv_kw"] - ideal,
        },
        diagnostics={
            "detail": detail,
            "weather_time": time,
            "reference": weather["reference"],
            "snapshot_ids": [s["id"] for s in weather.get("snapshots", [])],
        },
        audits=detail.get("audits", []) if detail else [],
    )
