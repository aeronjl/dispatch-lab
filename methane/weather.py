"""Saved forecast vintages and UTC interval normalization; no synthetic fallback."""

import hashlib
import json
import math
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import urlopen
from zoneinfo import ZoneInfo

import numpy as np

from methane.forecast import (
    ForecastRequest,
    SavedForecastProvider,
)
from methane.forecast import (
    IncompleteWeather as IncompleteWeather,
)
from methane.forecast import (
    choose_vintage as choose_vintage,
)
from methane.pv import dc_power
from methane.storage import DeliverySchedule
from methane.timebase import stamp, utc

CACHE = Path(__file__).resolve().parent.parent / "runs" / "weather"
FIELDS = "temperature_2m,relative_humidity_2m,global_tilted_irradiance"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0), ECMWF IFS / Copernicus ERA5"


def fetch(endpoint, params, offline=False, cache=CACHE):
    url = endpoint + "?" + urlencode(params)
    identity = hashlib.sha256(url.encode()).hexdigest()
    path = Path(cache) / f"{identity}.json"
    if path.exists():
        return json.loads(path.read_text())
    if offline:
        raise IncompleteWeather(f"Missing cached weather response {identity[:12]} (offline).")
    try:
        with urlopen(url, timeout=40) as response:
            raw = json.loads(response.read())
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise IncompleteWeather(f"Weather request failed: {exc}") from exc
    if raw.get("error"):
        raise IncompleteWeather(raw.get("reason", "Provider error"))
    saved = {
        "id": identity,
        "url": url,
        "retrieved_at": stamp(datetime.now(UTC)),
        "request": params,
        "attribution": ATTRIBUTION,
        "raw": raw,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        mode="w", dir=path.parent, prefix=identity, suffix=".tmp", delete=False
    ) as handle:
        json.dump(saved, handle, allow_nan=False)
        temporary = Path(handle.name)
    temporary.replace(path)
    return saved


def search_locations(query):
    if len(query.strip()) < 2:
        return []
    response = fetch(
        "https://geocoding-api.open-meteo.com/v1/search",
        {"name": query, "count": 10, "language": "en", "format": "json"},
    )
    return [
        x
        for x in response["raw"].get("results", [])
        if 34 <= x["latitude"] <= 72 and -25 <= x["longitude"] <= 45
    ]


def normalize(saved, p, w):
    """GTI at t+1 describes [t,t+1). Temperature/RH are sampled at t."""
    h = saved["raw"].get("hourly", {})
    units = saved["raw"].get("hourly_units", {})
    if units.get("global_tilted_irradiance") != "W/m²" or units.get("temperature_2m") != "°C":
        raise IncompleteWeather("Unexpected or absent irradiance/temperature units.")
    times = h.get("time", [])
    data = {}
    for i in range(len(times) - 1):
        start, end = utc(times[i]), utc(times[i + 1])
        if end - start != timedelta(hours=1):
            continue
        try:
            radiation = h["global_tilted_irradiance"][i + 1]
            ambient = h["temperature_2m"][i]
            humidity = h["relative_humidity_2m"][i]
        except (KeyError, IndexError):
            continue
        if any(v is None or not math.isfinite(v) for v in (radiation, ambient, humidity)):
            continue
        data[stamp(start)] = {
            "pv_kw": dc_power(radiation, ambient, p, w),
            "ambient_c": ambient,
            "humidity_pct": humidity,
            "irradiance_wm2": radiation,
        }
    return data


def forecast_run(initialized, p, w, days=4):
    params = {
        "latitude": w.latitude,
        "longitude": w.longitude,
        "hourly": FIELDS,
        "models": "ecmwf_ifs",
        "run": initialized.strftime("%Y-%m-%dT%H:%M"),
        "forecast_days": days,
        "tilt": w.tilt,
        "azimuth": w.azimuth,
        "timezone": "UTC",
    }
    saved = fetch("https://single-runs-api.open-meteo.com/v1/forecast", params, w.offline)
    saved = {
        **saved,
        "initialized_at": stamp(initialized),
        "available_at": stamp(initialized + timedelta(hours=w.publication_lag_hours)),
        "model": "ecmwf_ifs",
        "coordinates": [w.latitude, w.longitude],
        "units": saved["raw"].get("hourly_units", {}),
    }
    return {
        "id": saved["id"],
        "initialized_at": stamp(initialized),
        "available_at": stamp(initialized + timedelta(hours=w.publication_lag_hours)),
        "availability_basis": f"Assumed publication lag: {w.publication_lag_hours} hours",
        "source": "ECMWF IFS individual forecast run (provider interpolation to hourly)",
        "data": normalize(saved, p, w),
        "snapshot": saved,
    }


def prepare(config, progress=None):
    p, w, s = config.plant, config.weather, config.scenario
    if w.mode == "synthetic":
        return synthetic(config)
    start = utc(w.start).replace(hour=0, minute=0, second=0, microsecond=0)
    vintages = []
    if w.mode == "forecast":
        now = datetime.now(UTC)
        init = now - timedelta(hours=w.publication_lag_hours)
        init = init.replace(hour=init.hour // 6 * 6, minute=0, second=0, microsecond=0)
        run = forecast_run(init, p, w, min(16, math.ceil((s.hours + s.horizon_hours + 24) / 24)))
        vintages = [run]
        start = now.replace(minute=0, second=0, microsecond=0)
        truth = dict(run["data"])
        # Saved forecast is a scenario baseline, NOT realised weather.
        rng = np.random.default_rng(s.seed)
        truth = {
            t: {
                **row,
                "pv_kw": max(0, min(p.solar_kw, row["pv_kw"] * (1 + rng.normal(0, s.variability)))),
            }
            for t, row in truth.items()
        }
        reference = "Saved forecast + seeded stress; not observed weather"
        snapshots = [run["snapshot"]]
    else:
        end = start + timedelta(hours=s.hours)
        saved = fetch(
            "https://archive-api.open-meteo.com/v1/archive",
            {
                "latitude": w.latitude,
                "longitude": w.longitude,
                "hourly": FIELDS,
                "models": "era5",
                "start_date": start.strftime("%Y-%m-%d"),
                "end_date": (end + timedelta(days=1)).strftime("%Y-%m-%d"),
                "tilt": w.tilt,
                "azimuth": w.azimuth,
                "timezone": "UTC",
            },
            w.offline,
        )
        truth = normalize(saved, p, w)
        snapshots = [saved]
        # Explicit daily 00 UTC issue cadence: avoids silently stitching forecast hours.
        # At 00–05 UTC, yesterday's forecast is the latest available saved issue.
        init = start - timedelta(days=1)
        while init < end:
            if progress:
                progress(0, desc=f"Saving ECMWF issue {init.date()}")
            run = forecast_run(init, p, w, 4)
            vintages.append(run)
            snapshots.append(run["snapshot"])
            init += timedelta(days=1)
        reference = "ERA5 reanalysis historical reference; not site measurements"
    times = [stamp(start + timedelta(hours=i)) for i in range(s.hours)]
    missing = [t for t in times if t not in truth]
    if missing:
        raise IncompleteWeather(
            f"Reference missing {len(missing)} hourly intervals; first: {missing[0]}"
        )
    result = {
        "mode": w.mode,
        "times": times,
        "truth": truth,
        "vintages": vintages,
        "reference": reference,
        "snapshots": snapshots,
        "timezone": w.timezone,
        "attribution": ATTRIBUTION,
        "forecast_cadence": "saved single issue" if w.mode == "forecast" else "daily 00 UTC issues",
    }
    # Validate all horizons now: missing forecasts yield an incomplete run, never substitutions.
    for t in range(s.hours):
        forecast_at(result, config, t)
    return result


def synthetic(config):
    p, s, w = config.plant, config.scenario, config.weather
    n = s.hours + s.horizon_hours
    start = utc(w.start)
    h = np.arange(n) + 0.5
    clear = np.maximum(0, np.sin(((h % 24) - 6) / 12 * np.pi))
    expected = np.clip(0.74 + 0.09 * np.sin(h / 11), 0, 1)
    rng = np.random.default_rng(s.seed)
    residual = 0
    truth, template = {}, {}
    for i in range(n):
        residual = 0.65 * residual + rng.normal(0, s.variability * np.sqrt(1 - 0.65**2))
        ambient = float(18 + 6 * np.sin((h[i] - 9) * np.pi / 12))
        t = stamp(start + timedelta(hours=i))
        rad = float(1000 * clear[i] * np.clip(expected[i] + residual, 0.03, 1))
        truth[t] = {
            "pv_kw": dc_power(rad, ambient, p, w),
            "ambient_c": ambient,
            "irradiance_wm2": rad,
            "humidity_pct": 60,
        }
        template[t] = {
            "pv_kw": dc_power(float(1000 * clear[i] * expected[i]), ambient, p, w),
            "irradiance_wm2": float(1000 * clear[i] * expected[i]),
            "ambient_c": ambient,
        }
    return {
        "mode": "synthetic",
        "times": list(truth)[: s.hours],
        "truth": truth,
        "template": template,
        "vintages": [],
        "snapshots": [],
        "timezone": w.timezone,
        "reference": "Seeded synthetic reference",
        "attribution": "Illustrative synthetic weather",
        "forecast_cadence": "hourly template plus present-observation correction",
    }


def local_stamp(value, timezone):
    return utc(value).astimezone(ZoneInfo(timezone)).isoformat()


def deliveries(p, scenario, t, n):
    return DeliverySchedule(
        p.co2_delivery_kg, p.co2_delivery_every_hours, scenario.delivery_delay_hours
    ).intervals(t, n)


def forecast_at(weather, config, t, provider=None):
    """Archive adapter supplies only the current reference sample to the pure provider."""
    try:
        time = weather["times"][t]
        current = weather["truth"][time]
    except (KeyError, IndexError) as exc:
        raise IncompleteWeather(f"Missing current weather interval {t}") from exc
    s = config.scenario
    request = ForecastRequest(
        time,
        s.horizon_hours,
        current["pv_kw"],
        current["ambient_c"],
        config.solar["converter_kw"] if config.solar else config.plant.solar_kw,
        s.forecast_bias,
        s.seed,
        t,
    )
    forecast = (provider or SavedForecastProvider.from_weather(weather)).horizon(request)
    from methane.integration import forecast as integration_forecast

    return integration_forecast(
        config.plant,
        {**forecast, "deliveries_kg": deliveries(config.plant, s, t, s.horizon_hours)},
        t,
    )
