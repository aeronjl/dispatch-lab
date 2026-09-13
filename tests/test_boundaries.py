import ast
import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from methane.config import Config, Scenario
from methane.forecast import ForecastRequest, IncompleteWeather, SavedForecastProvider
from methane.pv import Parameters, convert
from methane.solar_model import (
    ArrayCapacity,
    SolarContext,
    SolarInput,
    component_step,
    default_design,
)
from methane.storage import DeliverySchedule
from methane.weather import forecast_at, synthetic


def test_pure_component_dependency_firewall():
    forbidden = (
        "methane.config",
        "methane.physics",
        "methane.dispatch",
        "methane.simulation",
        "methane.ui",
        "methane.weather",
        "gradio",
        "scipy",
        "numpy",
        "urllib",
    )
    for file in (
        "battery",
        "electrolyser",
        "storage",
        "reactor",
        "solar_model",
        "pv",
        "forecast",
        "ports",
    ):
        tree = ast.parse(Path("methane", file + ".py").read_text())
        imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
        imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
        assert not any(name and name.startswith(forbidden) for name in imports), (file, imports)


def test_provider_isolated_from_future_truth_and_detached_outputs():
    config = Config(scenario=Scenario(hours=3, horizon_hours=6))
    weather = synthetic(config)
    provider = SavedForecastProvider.from_weather(weather)
    before = forecast_at(weather, config, 0, provider)
    for time in weather["times"][1:]:
        weather["truth"][time]["pv_kw"] = 999
    assert forecast_at(weather, config, 0, provider) == before
    weather["template"].clear()
    assert forecast_at(weather, config, 0, provider) == before
    before["pv_kw"][0] = -10
    assert forecast_at(weather, config, 0, provider)["pv_kw"][0] >= 0
    missing = SavedForecastProvider("historical", "[]")
    with pytest.raises(IncompleteWeather):
        missing.horizon(ForecastRequest("2026-04-01T00:00Z", 1, 0, 20, 1000))
    with pytest.raises(ValueError):
        ForecastRequest("2026-04-01T00:30Z", 1, 0, 20, 1000)


def test_delivery_order_is_pure_and_independent():
    schedule = DeliverySchedule(300, 24, 24)
    assert schedule.intervals(24, 25) == [0] * 24 + [300]
    with pytest.raises(ValueError):
        DeliverySchedule(300, 0)


def test_standalone_solar_reference_and_input_failures():
    # 800 W/m2, 20 C ambient, NOCT45 =>45 C panel. 20 K × -0.004 =>0.92.
    p = Parameters(1000, 0.1, 45, -0.004)
    assert convert(p, 800, 20) == pytest.approx(662.4)
    c = SolarContext(51.5, 0, 30, 0, 45, -0.004, 0.1)
    capacity = ArrayCapacity(1000)
    design = default_design(capacity, c)
    sample = {"irradiance_wm2": 800, "ambient_c": 20, "pv_kw": 662.4}
    inputs = SolarInput(
        json.dumps(design), json.dumps(sample), "2026-07-10T12:00:00+00:00", capacity, c
    )
    before = copy.deepcopy(inputs)
    result = component_step(inputs)
    assert dict(result.flows)["output_kw"] == pytest.approx(662.4)
    assert inputs == before
    with pytest.raises(ValueError):
        component_step(replace(inputs, sample_json=json.dumps({**sample, "irradiance_wm2": -1})))
    with pytest.raises(ValueError):
        convert(p, float("nan"), 20)
