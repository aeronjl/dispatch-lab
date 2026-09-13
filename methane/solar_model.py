"""Pure section-level solar model. No network, archive, controller or UI dependencies."""

import json
import math
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache

from methane.audit import check, require
from methane.contracts import SOLAR, ComponentResult
from methane.pv import dc_power
from methane.timebase import utc

MODEL = "dispatch-lab/solar-sections/2"


NOTE = (
    "Illustrative sections, not individual panel measurements. Orientation uses an assumed "
    "30% diffuse sky normalized to the saved reference plane; no measured DNI/DHI. "
    "Uniform section shading and soiling; simple temperature model; independent MPPT channels. "
    "Panel tiles are schematic. Clipping and plant curtailment are separate."
)


def default_design(p, w):
    return {
        "version": MODEL,
        "sections": [
            {
                "capacity_kw": p.solar_kw / 3,
                "tilt": w.tilt,
                "azimuth": w.azimuth,
                "shade": 0,
                "soiling": 0,
                "online": True,
            }
            for _ in range(3)
        ],
        "converter_kw": p.solar_kw,
        "efficiency": 1.0,
        "noct_c": w.noct_c,
    }


def validate(design):
    if not isinstance(design, dict) or design.get("version") not in (
        MODEL,
        "dispatch-lab/solar-sections/1",
    ):
        raise ValueError("Unknown solar design version.")
    sections = design.get("sections")
    if not isinstance(sections, list) or len(sections) != 3:
        raise ValueError("The solar workspace requires three array sections.")
    result = {"version": MODEL, "sections": []}

    def number(obj, key, lower, upper):
        return next(x for x in SOLAR.parameters if x.key == key).validate(obj.get(key))

    for section in sections:
        if not isinstance(section, dict) or not isinstance(section.get("online"), bool):
            raise ValueError("Every section requires an online state.")
        item = {
            key: number(section, key, lo, hi)
            for key, lo, hi in (
                ("capacity_kw", 0, 10000),
                ("tilt", 0, 90),
                ("azimuth", -180, 180),
                ("shade", 0, 1),
                ("soiling", 0, 1),
            )
        }
        result["sections"].append({**item, "online": section["online"]})
    result.update(
        converter_kw=number(design, "converter_kw", 0, 30000),
        efficiency=number(design, "efficiency", 0.5, 1),
        noct_c=number(design, "noct_c", 20, 80),
    )
    return result


def sun_position(time, latitude, longitude):
    """Approximate solar geometry at the interval midpoint, in UTC.

    Declination/hour-angle approximation is sufficient for the labelled
    orientation sensitivity; no claim of precise shading geometry is made.
    """
    d = utc(time) + timedelta(minutes=30)
    day = d.timetuple().tm_yday
    b = math.radians(360 * (day - 81) / 364)
    equation = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    hour = d.hour + d.minute / 60 + longitude / 15 + equation / 60
    angle = math.radians(15 * (hour - 12))
    dec = math.radians(23.45 * math.sin(math.radians(360 * (284 + day) / 365)))
    lat = math.radians(latitude)
    up = math.sin(lat) * math.sin(dec) + math.cos(lat) * math.cos(dec) * math.cos(angle)
    east = -math.cos(dec) * math.sin(angle)
    south = math.sin(lat) * math.cos(dec) * math.cos(angle) - math.cos(lat) * math.sin(dec)
    return east, south, up


def plane_factor(vector, tilt, azimuth):
    # Open-Meteo convention: 0 south, -90 east, +90 west.
    east, south, up = vector
    tilt, azimuth = math.radians(tilt), math.radians(azimuth)
    incidence = max(
        0,
        -east * math.sin(tilt) * math.sin(azimuth)
        + south * math.sin(tilt) * math.cos(azimuth)
        + up * math.cos(tilt),
    )
    # Stable near sunrise: use a minimum sun elevation for the beam conversion.
    return 0.7 * incidence / max(0.1, up) + 0.3 * (1 + math.cos(tilt)) / 2


def _interval(design, sample, time, p, w):
    vector = sun_position(time, w.latitude, w.longitude)
    baseline_plane = max(0.05, plane_factor(vector, w.tilt, w.azimuth))
    radiation = max(0, sample["irradiance_wm2"])
    ambient = sample["ambient_c"]
    sections = []
    for index, section in enumerate(design["sections"]):
        orientation = plane_factor(vector, section["tilt"], section["azimuth"]) / baseline_plane
        # Retain saved diffuse/radiation at very low sun, including synthetic
        # fixtures whose day length is deliberately independent of latitude.
        if vector[2] <= 0:
            orientation = (1 + math.cos(math.radians(section["tilt"]))) / (
                1 + math.cos(math.radians(w.tilt))
            )
        item = json.loads(
            _section(
                json.dumps(section, sort_keys=True),
                radiation * orientation,
                ambient,
                w,
                design["noct_c"],
            )
        )
        item["id"] = f"PV-{index + 1:02d}"
        sections.append(item)
    available = sum(x["available_kw"] for x in sections)
    # Saved current-forecast scenarios sometimes stress generation rather than
    # irradiance. Preserve that exogenous stress in both baseline and draft.
    reference_power = dc_power(radiation, ambient, p, w)
    stress = sample["pv_kw"] / reference_power if reference_power > 1e-8 else 1
    stressed = available * stress
    converted = stressed * design["efficiency"]
    output = min(design["converter_kw"], converted)
    return {
        "sections": sections,
        "available_kw": available,
        "conversion_loss_kw": stressed - converted,
        "clipped_kw": max(0, converted - design["converter_kw"]),
        "scenario_adjustment_kw": stressed - available,
        "output_kw": output,
        "reference_irradiance_wm2": radiation,
        "ambient_c": ambient,
        "sun_elevation_deg": math.degrees(math.asin(max(-1, min(1, vector[2])))),
    }


@dataclass(frozen=True)
class ArrayCapacity:
    solar_kw: float


@dataclass(frozen=True)
class SolarContext:
    latitude: float
    longitude: float
    tilt: float
    azimuth: float
    noct_c: float
    temperature_coefficient: float
    loss_fraction: float


@dataclass(frozen=True)
class SolarInput:
    design_json: str
    sample_json: str
    time: str
    plant: ArrayCapacity
    weather: SolarContext


@lru_cache(maxsize=4096)
def _cached_interval(inputs):
    sample = json.loads(inputs.sample_json)
    if (
        not all(
            math.isfinite(sample.get(k, float("nan")))
            for k in ("pv_kw", "irradiance_wm2", "ambient_c")
        )
        or min(sample["pv_kw"], sample["irradiance_wm2"]) < 0
    ):
        raise ValueError("Solar inputs require finite ambient and nonnegative power/irradiance")
    context = vars(inputs.weather)
    if (
        not all(math.isfinite(v) for v in context.values())
        or not -90 <= inputs.weather.latitude <= 90
        or not -180 <= inputs.weather.longitude <= 180
    ):
        raise ValueError("Invalid solar geometry or conversion context")
    row = _interval(
        validate(json.loads(inputs.design_json)),
        sample,
        inputs.time,
        inputs.plant,
        inputs.weather,
    )
    audits = [
        check(
            "solar_dc_balance",
            "solar",
            row["available_kw"]
            + row["scenario_adjustment_kw"]
            - row["conversion_loss_kw"]
            - row["clipped_kw"]
            - row["output_kw"],
            "kW",
            abs(row["available_kw"]),
        )
    ]
    for i, section in enumerate(row["sections"]):
        loss = sum(
            section[k]
            for k in (
                "shade_loss_kw",
                "soiling_loss_kw",
                "temperature_loss_kw",
                "electrical_loss_kw",
                "offline_loss_kw",
            )
        )
        audits.append(
            check(
                f"section_{i}_balance",
                "solar",
                section["gross_kw"] - loss - section["available_kw"],
                "kW",
                section["gross_kw"],
            )
        )
    row["audits"] = audits
    require(audits, {"inputs": inputs.sample_json, "row": row})
    return (
        json.dumps(row, allow_nan=False),
        row["output_kw"],
        tuple(json.dumps(a, sort_keys=True) for a in audits),
    )


def component_step(inputs: SolarInput):
    # Cached value is immutable JSON; callers always receive independent results.
    encoded, output_kw, audits = _cached_interval(inputs)
    return ComponentResult(
        None,
        (("output_kw", output_kw),),
        (("detail_json", encoded),),
        audits,
    )


def interval(design, sample, time, p, w):
    return _validated_interval(json.dumps(validate(design), sort_keys=True), sample, time, p, w)


def _validated_interval(encoded_design, sample, time, p, w):
    inputs = SolarInput(
        encoded_design,
        json.dumps(sample, sort_keys=True),
        time,
        ArrayCapacity(p.solar_kw),
        SolarContext(**{k: getattr(w, k) for k in SolarContext.__dataclass_fields__}),
    )
    return json.loads(dict(component_step(inputs).diagnostics)["detail_json"])


@lru_cache(maxsize=16384)
def _section(section_json, poa, ambient, w, noct_c):
    section = json.loads(section_json)
    gross = section["capacity_kw"] * poa / 1000
    shaded = gross * (1 - section["shade"])
    clean = shaded * (1 - section["soiling"])
    effective = poa * (1 - section["shade"]) * (1 - section["soiling"])
    temperature = ambient + (noct_c - 20) * effective / 800
    thermal = clean * max(0, 1 + w.temperature_coefficient * (temperature - 25))
    wired = thermal * (1 - w.loss_fraction)
    available = wired if section["online"] else 0
    return json.dumps(
        {
            "id": "section",
            "irradiance_wm2": poa,
            "temperature_c": temperature,
            "gross_kw": gross,
            "shade_loss_kw": gross - shaded,
            "soiling_loss_kw": shaded - clean,
            "temperature_loss_kw": clean - thermal,
            "electrical_loss_kw": thermal - wired,
            "offline_loss_kw": wired - available,
            "available_kw": available,
        },
        allow_nan=False,
    )
