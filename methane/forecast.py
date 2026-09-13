"""Pure forecast selection. Receives the current sample and forecast issues, never future truth."""

import json
import math
from dataclasses import dataclass
from datetime import timedelta
from functools import lru_cache
from types import MappingProxyType

from methane.timebase import stamp, utc


class IncompleteWeather(ValueError):
    pass


def choose_vintage(vintages, decision_time):
    usable = [v for v in vintages if utc(v["available_at"]) <= decision_time]
    if not usable:
        raise IncompleteWeather(f"No forecast was available at {stamp(decision_time)}.")
    return max(usable, key=lambda v: (utc(v["initialized_at"]), utc(v["available_at"])))


@dataclass(frozen=True)
class ForecastRequest:
    time: str
    horizon_hours: int
    current_pv_kw: float
    current_ambient_c: float
    solar_limit_kw: float
    bias: float = 0
    seed: int = 7
    interval_index: int = 0
    include_samples: bool = False
    current_irradiance_wm2: float | None = None

    def __post_init__(self):
        if (
            self.horizon_hours < 1
            or int(self.horizon_hours) != self.horizon_hours
            or not all(
                math.isfinite(v)
                for v in (
                    self.current_pv_kw,
                    self.current_ambient_c,
                    self.solar_limit_kw,
                    self.bias,
                )
            )
            or min(self.current_pv_kw, self.solar_limit_kw) < 0
        ):
            raise ValueError(
                "Forecast request needs positive whole hours and finite current measurements"
            )
        instant = utc(self.time)
        if instant.minute or instant.second or instant.microsecond:
            raise ValueError("Forecast intervals must start on UTC hour boundaries")


@lru_cache(maxsize=8)
def _parsed(encoded):
    def freeze(value):
        if isinstance(value, dict):
            return MappingProxyType({k: freeze(v) for k, v in value.items()})
        if isinstance(value, list):
            return tuple(freeze(v) for v in value)
        return value

    return freeze(json.loads(encoded))


@dataclass(frozen=True)
class SavedForecastProvider:
    """Frozen JSON prevents callers from mutating issues during a run. No I/O in horizon()."""

    mode: str
    data_json: str

    @classmethod
    def from_weather(cls, weather):
        data = weather["template"] if weather["mode"] == "synthetic" else weather["vintages"]
        return cls(weather["mode"], json.dumps(data, sort_keys=True, allow_nan=False))

    def horizon(self, request: ForecastRequest):
        instant = utc(request.time)
        times = [stamp(instant + timedelta(hours=i)) for i in range(request.horizon_hours)]
        data = _parsed(self.data_json)
        if self.mode == "synthetic":
            samples = data
            source = dict(
                id=f"synthetic-{request.seed}-{request.interval_index}",
                source="Known synthetic template + current observation",
                initialized_at=stamp(instant),
                available_at=stamp(instant),
            )
        elif self.mode in ("forecast", "historical"):
            vintage = choose_vintage(data, instant)
            samples = vintage["data"]
            source = {k: vintage[k] for k in ("id", "source", "initialized_at", "available_at")}
        else:
            raise IncompleteWeather("Unknown saved forecast provider mode")
        missing = [t for t in times if t not in samples]
        if missing:
            raise IncompleteWeather(f"Forecast {source['id'][:12]} missing interval {missing[0]}.")
        values = [samples[t] for t in times]
        if any(
            not all(math.isfinite(v.get(k, float("nan"))) for k in ("pv_kw", "ambient_c"))
            or v["pv_kw"] < 0
            for v in values
        ):
            raise IncompleteWeather("Forecast has nonfinite or negative power data")
        residual = request.current_pv_kw - values[0]["pv_kw"] if self.mode == "synthetic" else 0
        pv = [
            max(
                0,
                min(
                    request.solar_limit_kw,
                    v["pv_kw"] * (1 + request.bias) + residual * math.exp(-i / 3),
                ),
            )
            for i, v in enumerate(values)
        ]
        ambient = [v["ambient_c"] for v in values]
        error = request.current_pv_kw - pv[0]
        prediction_sample = {**values[0], "pv_kw": pv[0]}
        pv[0], ambient[0] = request.current_pv_kw, request.current_ambient_c
        result = dict(
            times=times,
            pv_kw=pv,
            ambient_c=ambient,
            source=source,
            current_forecast_error_kw=error,
            abstraction="Current hourly mean PV treated as measured; future reference samples excluded",
        )
        if request.include_samples:
            result["current_prediction_sample"] = dict(prediction_sample)
            result["source_samples"] = [
                {
                    k: v.get(k)
                    for k in ("pv_kw", "ambient_c", "irradiance_wm2", "wind_mps", "rain_mmph")
                }
                for v in values
            ]
            result["source_samples"][0].update(
                pv_kw=request.current_pv_kw,
                ambient_c=request.current_ambient_c,
                irradiance_wm2=request.current_irradiance_wm2,
            )
        return result
