from datetime import timedelta

import pytest

from methane.config import Config
from methane.forecast import ForecastRequest, SavedForecastProvider
from methane.siting.environment import exact_times, hourly, persistence
from methane.siting.sources import MissingData
from methane.timebase import stamp, utc


def test_calendar_leap_dst_and_no_fabricated_hours():
    assert len(exact_times("2024-01-01", "2025-01-01")) == 8784
    assert len(exact_times("2025-01-01", "2026-01-01")) == 8760
    assert len(exact_times("2024-03-30T23:00+00:00", "2024-04-01T00:00+01:00")) == 24
    with pytest.raises(ValueError):
        exact_times("2024-01-01T00:30Z", "2024-01-02")


def test_persistence_has_no_future_realisation_dependency():
    start = utc("2025-01-02")
    truth = {
        stamp(start + timedelta(hours=i)): dict(
            pv_kw=100 + i, ambient_c=20, irradiance_wm2=100, humidity_pct=60
        )
        for i in range(-24, 72)
    }
    times = exact_times(start.isoformat(), (start + timedelta(days=2)).isoformat())
    original = persistence(truth, times, 24)
    for t in list(truth):
        if utc(t) >= start:
            truth[t]["pv_kw"] = 999
    changed = persistence(truth, times, 24)
    assert original[0] == changed[0]
    assert original[1] != changed[1]
    p = SavedForecastProvider.from_weather(dict(mode="historical", vintages=original))
    assert (
        p.horizon(ForecastRequest(stamp(start), 24, 0, 20, 1000))["source"]["id"]
        == original[0]["id"]
    )
    with pytest.raises(MissingData):
        persistence({}, times, 24)


def test_preceding_radiation_and_unit_validation():
    raw = dict(
        hourly_units={"global_tilted_irradiance": "W/m²", "temperature_2m": "°C"},
        hourly=dict(
            time=["2025-01-01T00:00", "2025-01-01T01:00", "2025-01-01T02:00"],
            global_tilted_irradiance=[None, 100, 200],
            temperature_2m=[10, 20, 30],
            relative_humidity_2m=[50, 60, 70],
        ),
    )
    rows = hourly(raw, Config())
    assert rows[stamp(utc("2025-01-01"))]["irradiance_wm2"] == 100
    assert rows[stamp(utc("2025-01-01"))]["ambient_c"] == 10
    raw["hourly_units"]["global_tilted_irradiance"] = "J/m²"
    with pytest.raises(ValueError):
        hourly(raw, Config())


def test_forecast_gust_maximum_and_reanalysis_instant_are_distinct():
    raw = dict(
        hourly_units={
            "global_tilted_irradiance": "W/m²",
            "temperature_2m": "°C",
            "wind_gusts_10m": "m/s",
        },
        hourly=dict(
            time=["2025-01-01T00:00", "2025-01-01T01:00", "2025-01-01T02:00"],
            global_tilted_irradiance=[None, 100, 200],
            temperature_2m=[10, 20, 30],
            relative_humidity_2m=[50, 60, 70],
            wind_gusts_10m=[None, 4, 7],
        ),
    )
    first = stamp(utc("2025-01-01"))
    forecast = hourly(raw, Config(), gust_support="preceding-hour-max")
    assert forecast[first]["gust_mps"] == 4
    raw["hourly"]["wind_gusts_10m"][0] = 2
    assert hourly(raw, Config())[first]["gust_mps"] == 2
