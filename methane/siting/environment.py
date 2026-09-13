"""Frozen chronological environments with explicit, causal forecast information."""

import csv
import io
import json
import math
from datetime import UTC, datetime, timedelta

from methane.cancellation import CancelledOperation
from methane.config import Config
from methane.pv import dc_power
from methane.siting.sources import MissingData, fetch
from methane.siting.store import digest, encode
from methane.timebase import stamp, utc
from methane.weather import FIELDS, normalize

VERSION = "site-environment/1"
ARCHIVE = "https://archive-api.open-meteo.com/v1/archive"
RUNS = "https://single-runs-api.open-meteo.com/v1/forecast"
CONVENTION = "Radiation at t+1 is preceding-hour mean for [t,t+1); temperature/humidity at t; UTC one-hour intervals"


def metadata(product, edition):
    return dict(
        provider="Open-Meteo / ECMWF / Copernicus",
        product=product,
        edition=edition,
        attribution="Open-Meteo.com; ECMWF / Copernicus ERA5",
        licence="CC BY 4.0; public hosted API evaluation/non-commercial terms",
        redistribution="permitted",
        timing=CONVENTION,
        units={
            "irradiance": "W/m²",
            "temperature": "°C",
            "humidity": "%",
            "wind": "m/s",
            "rain": "mm/h",
        },
    )


def hourly(raw, config):
    result = normalize({"raw": raw}, config.plant, config.weather)
    h = raw.get("hourly", {})
    units = raw.get("hourly_units", {})
    for i, t in enumerate(h.get("time", [])[:-1]):
        key = stamp(utc(t))
        if key not in result:
            continue
        for field, name, offset, expected in (
            ("wind_speed_10m", "wind_mps", 0, "m/s"),
            ("wind_gusts_10m", "gust_mps", 0, "m/s"),
            ("precipitation", "rain_mmph", 1, "mm"),
        ):
            if field not in h:
                continue
            if units.get(field) != expected:
                raise MissingData(f"Unexpected {field} unit")
            value = h[field][i + offset]
            if value is None or not math.isfinite(value) or value < 0:
                raise MissingData(f"Missing {field} at {key}")
            result[key][name] = value
    return result


def exact_times(start, end):
    a, b = utc(start), utc(end)
    if any((v.minute or v.second or v.microsecond) for v in (a, b)):
        raise ValueError("Environment boundaries must be exact UTC hours")
    hours = int((b - a).total_seconds() / 3600)
    if not 1 <= hours <= 8784 * 40:
        raise ValueError("Environment must span 1 hour to 40 years")
    return [stamp(a + timedelta(hours=i)) for i in range(hours)]


def prepare(
    store,
    design_id,
    start,
    end,
    information="persistence/1",
    offline=True,
    progress=None,
    cancelled=None,
):
    design = store.get("design", design_id)
    c = Config.from_dict(design["config"])
    w = c.weather
    times = exact_times(start, end)
    if information not in ("persistence/1", "archived-ifs/1"):
        raise ValueError("Choose causal day persistence or original archived forecast issues")
    if information == "archived-ifs/1" and utc(start) < datetime(2024, 3, 2, tzinfo=UTC):
        raise MissingData(
            "Individual ECMWF issues are not available before March 2024; choose an explicit persistence design scenario"
        )
    cursor, finish = (
        utc(start) - timedelta(days=2),
        utc(end) + timedelta(hours=c.scenario.horizon_hours),
    )
    truth, vintages, source_ids = {}, [], []
    common = dict(
        latitude=w.latitude,
        longitude=w.longitude,
        hourly=FIELDS + ",wind_speed_10m,wind_gusts_10m,precipitation",
        tilt=w.tilt,
        azimuth=w.azimuth,
        timezone="UTC",
        wind_speed_unit="ms",
    )

    def check(label):
        if cancelled and cancelled():
            raise CancelledOperation()
        if progress:
            progress(label)

    while cursor < finish:
        check(f"ERA5 reference · {cursor.date()}")
        following = min(cursor + timedelta(days=28), finish)
        sid, raw = fetch(
            store,
            ARCHIVE,
            {
                **common,
                "models": "era5",
                "start_date": cursor.date().isoformat(),
                "end_date": (following + timedelta(days=1)).date().isoformat(),
            },
            metadata("ERA5 hourly environment", "era5/v1"),
            offline,
        )
        truth.update(hourly(raw, c))
        source_ids.append(sid)
        cursor = following
    if information == "archived-ifs/1":
        cursor = utc(start).replace(hour=0) - timedelta(days=1)
        while cursor < utc(end):
            check(f"ECMWF issue · {cursor.date()}")
            sid, raw = fetch(
                store,
                RUNS,
                {
                    **common,
                    "models": "ecmwf_ifs",
                    "run": cursor.strftime("%Y-%m-%dT%H:%M"),
                    "forecast_days": 4,
                },
                metadata("ECMWF individual forecast issue", "ecmwf_ifs/v1"),
                offline,
            )
            vintages.append(
                dict(
                    id=sid,
                    source="ECMWF IFS original issue; hourly interpolation",
                    initialized_at=stamp(cursor),
                    available_at=stamp(cursor + timedelta(hours=w.publication_lag_hours)),
                    data=hourly(raw, c),
                )
            )
            source_ids.append(sid)
            cursor += timedelta(days=1)
    missing = [t for t in times if t not in truth]
    if missing:
        raise MissingData(f"Incomplete reference: {len(missing)} missing hours, first {missing[0]}")
    payload = dict(truth=truth, vintages=vintages)
    env = dict(
        schema_version=VERSION,
        design_id=design_id,
        site_revision=design["site_revision"],
        start=times[0],
        end=stamp(utc(end)),
        hours=len(times),
        information=information,
        reference="ERA5 reanalysis, not site measurements",
        timezone=w.timezone,
        conversion={
            "weather": design["config"]["weather"],
            "solar_kw": c.plant.solar_kw,
            "section_design": c.solar,
        },
        source_ids=sorted(set(source_ids)),
        normalized_sha256=store.raw(encode(payload)),
        convention=CONVENTION,
        publication_lag_hours=w.publication_lag_hours,
        assumptions=[
            "Current hourly mean treated as observed by scheduler",
            "Weather exposure does not invent a damage or cleaning mechanism",
            "Daily 00 UTC forecast cadence"
            if information == "archived-ifs/1"
            else "Same hour from last complete observed day repeated; causal teaching/design policy, not a historical weather forecast",
        ],
    )
    key = store.put("environment", env)
    # Validate every forecast horizon before a production study is admitted.
    weather(store, key, c)
    return {"id": key, **env, "resource": resource(payload, times)}


def resource(payload, times):
    monthly = {}
    for t in times:
        row = payload["truth"][t]
        cell = monthly.setdefault(t[:7], dict(hours=0, dc_kwh=0, tilted_kwh_m2=0))
        cell["hours"] += 1
        cell["dc_kwh"] += row["pv_kw"]
        cell["tilted_kwh_m2"] += row["irradiance_wm2"] / 1000
    return dict(
        months=monthly,
        dc_kwh=sum(v["dc_kwh"] for v in monthly.values()),
        scope="Reference conversion before optional section optics, faults, plant use and curtailment",
    )


def persistence(truth, times, horizon):
    issues = []
    for day in sorted({t[:10] for t in times}):
        boundary = utc(day)
        samples = {}
        for offset in range(24 + horizon):
            target = boundary + timedelta(hours=offset)
            observed = boundary - timedelta(days=1) + timedelta(hours=target.hour)
            key = stamp(observed)
            if key not in truth:
                raise MissingData(f"Persistence needs the previous complete day: missing {key}")
            samples[stamp(target)] = dict(truth[key])
        issues.append(
            dict(
                id=digest(dict(day=day, samples=samples, version="persistence/1")),
                source="Previous complete observed day, repeated by UTC hour; explicit persistence scenario",
                initialized_at=stamp(boundary),
                available_at=stamp(boundary),
                data=samples,
            )
        )
    return issues


def weather(store, environment_id, config):
    from methane.forecast import ForecastRequest, SavedForecastProvider
    from methane.solar import transform_weather

    env = store.get("environment", environment_id)
    payload = json.loads(store.read_raw(env["normalized_sha256"]))
    times = exact_times(env["start"], env["end"])
    # Radiation is preserved; changing capacity or losses recalculates the DC path.
    base = env["conversion"]["weather"]
    if any(
        getattr(config.weather, k) != base[k] for k in ("latitude", "longitude", "tilt", "azimuth")
    ):
        raise ValueError("Coordinates/orientation changed: obtain a compatible environment edition")
    for rows in [payload["truth"], *(v["data"] for v in payload["vintages"])]:
        for row in rows.values():
            row["pv_kw"] = dc_power(
                row["irradiance_wm2"], row["ambient_c"], config.plant, config.weather
            )
    vintages = (
        persistence(payload["truth"], times, config.scenario.horizon_hours)
        if env["information"] == "persistence/1"
        else payload["vintages"]
    )
    result = dict(
        mode="historical",
        times=times,
        truth=payload["truth"],
        vintages=vintages,
        reference=env["reference"],
        timezone=env["timezone"],
        snapshots=[
            {
                "id": environment_id,
                "source_ids": env["source_ids"],
                "normalized_sha256": env["normalized_sha256"],
            }
        ],
        attribution="; ".join(
            sorted({store.get("source", k)["attribution"] for k in env["source_ids"]})
        ),
        environment_id=environment_id,
        information=env["information"],
        forecast_cadence=env["assumptions"][-1],
    )
    provider = SavedForecastProvider.from_weather(result)
    for t in times:
        r = result["truth"][t]
        provider.horizon(
            ForecastRequest(
                t, config.scenario.horizon_hours, r["pv_kw"], r["ambient_c"], config.plant.solar_kw
            )
        )
    return transform_weather(result, config, config.solar) if config.solar else result


def import_measurements(store, source_id, design_id, start, end):
    """An explicit CSV contract; no interpolation, inferred timezone or guessed units."""
    source = store.get("source", source_id)
    c = Config.from_dict(store.get("design", design_id)["config"])
    required = {"irradiance_wm2": "W/m²", "ambient_c": "°C", "humidity_pct": "%"}
    if (
        any(source["units"].get(k) != v for k, v in required.items())
        or source["coverage"].get("interval_support")
        != "UTC interval start; hourly mean irradiance"
    ):
        raise ValueError(
            "Measurement metadata must declare the CSV units and exact interval support"
        )
    if source["coverage"].get("coordinates") != [c.weather.longitude, c.weather.latitude]:
        raise ValueError("Measurement coordinates do not match the design")
    rows = csv.DictReader(io.StringIO(store.read_raw(source["raw_sha256"]).decode("utf-8-sig")))
    truth = {}
    for row in rows:
        dt = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.minute or dt.second:
            raise ValueError("Measurements require offset-aware exact hourly timestamps")
        key = stamp(dt.astimezone(UTC))
        if key in truth:
            raise ValueError("Duplicate measurement interval")
        values = {k: float(row[k]) for k in required}
        if (
            not all(math.isfinite(v) for v in values.values())
            or values["irradiance_wm2"] < 0
            or not 0 <= values["humidity_pct"] <= 100
        ):
            raise ValueError("Invalid measurement value")
        values["pv_kw"] = dc_power(
            values["irradiance_wm2"], values["ambient_c"], c.plant, c.weather
        )
        if row.get("measured_dc_kw"):
            values["measured_dc_kw"] = float(row["measured_dc_kw"])
            if not math.isfinite(values["measured_dc_kw"]) or values["measured_dc_kw"] < 0:
                raise ValueError("Invalid measured DC")
        truth[key] = values
    times = exact_times(start, end)
    if any(t not in truth for t in times):
        raise MissingData("Measurement file has missing study intervals")
    persistence(truth, times, c.scenario.horizon_hours)
    env = dict(
        schema_version=VERSION,
        design_id=design_id,
        site_revision=store.get("design", design_id)["site_revision"],
        start=times[0],
        end=stamp(utc(end)),
        hours=len(times),
        information="persistence/1",
        reference="Imported site measurements; supplied calibration and siting metadata",
        timezone=c.weather.timezone,
        conversion={
            "weather": c.to_dict()["weather"],
            "solar_kw": c.plant.solar_kw,
            "section_design": c.solar,
        },
        source_ids=[source_id],
        normalized_sha256=store.raw(encode(dict(truth=truth, vintages=[]))),
        convention=source["timing"],
        publication_lag_hours=0,
        assumptions=["Previous complete observed day persistence"],
    )
    return {"id": store.put("environment", env), **env}


def calibration(store, environment_id, training_end):
    env = store.get("environment", environment_id)
    truth = json.loads(store.read_raw(env["normalized_sha256"]))["truth"]
    pairs = [
        (t, v["pv_kw"], v["measured_dc_kw"])
        for t, v in sorted(truth.items())
        if "measured_dc_kw" in v and env["start"] <= t < env["end"]
    ]
    train = [(x, y) for t, x, y in pairs if utc(t) < utc(training_end) and x > 1]
    test = [(x, y) for t, x, y in pairs if utc(t) >= utc(training_end) and x > 1]
    if len(train) < 12 or len(test) < 12:
        raise ValueError(
            "Calibration needs at least 12 informative training and 12 held-out hourly DC measurements"
        )
    factor = sum(x * y for x, y in train) / sum(x * x for x, _ in train)
    score = lambda points, f: (sum((f * x - y) ** 2 for x, y in points) / len(points)) ** 0.5  # noqa: E731
    result = dict(
        schema_version="site-calibration/1",
        environment_id=environment_id,
        training_end=stamp(utc(training_end)),
        training_count=len(train),
        test_count=len(test),
        dc_scale=factor,
        heldout_rmse_before_kw=score(test, 1),
        heldout_rmse_after_kw=score(test, factor),
        scope="One fitted multiplicative DC correction; not a causal diagnosis, probability distribution or automatic dispatch change",
        deployment="Create a reviewed parameter/world edition; original environment and runs unchanged",
    )
    return {"id": store.put("measurement", result), **result}
