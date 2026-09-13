"""Solar previews conserve power, preserve source weather, and feed real dispatch."""

import copy
from dataclasses import replace

import pytest

from methane.config import Config, Scenario
from methane.simulation import run
from methane.solar import default_design, interval, preview, transform_weather, validate
from methane.weather import dc_power, synthetic


def fixture():
    config = Config(scenario=Scenario(hours=12, horizon_hours=6))
    weather = synthetic(config)
    return config, weather


def test_default_sections_reconcile_with_lumped_model():
    c, w = fixture()
    design = default_design(c.plant, c.weather)
    for time, sample in w["truth"].items():
        result = interval(design, sample, time, c.plant, c.weather)
        assert result["output_kw"] == pytest.approx(sample["pv_kw"], abs=1e-9)
        for section in result["sections"]:
            losses = sum(
                section[k]
                for k in (
                    "shade_loss_kw",
                    "soiling_loss_kw",
                    "temperature_loss_kw",
                    "electrical_loss_kw",
                    "offline_loss_kw",
                )
            )
            assert section["gross_kw"] - losses == pytest.approx(section["available_kw"])


def test_shading_soiling_isolation_and_converter_limits():
    c, weather = fixture()
    time = weather["times"][-1]
    sample = weather["truth"][time]
    base = default_design(c.plant, c.weather)
    original = interval(base, sample, time, c.plant, c.weather)
    design = copy.deepcopy(base)
    design["sections"][0]["online"] = False
    design["sections"][1]["shade"] = 0.7
    design["sections"][2]["soiling"] = 0.2
    design.update(converter_kw=50, efficiency=0.95)
    result = interval(design, sample, time, c.plant, c.weather)
    assert result["sections"][0]["available_kw"] == 0
    assert result["available_kw"] < original["available_kw"]
    assert result["output_kw"] <= 50
    assert result["output_kw"] == pytest.approx(
        result["available_kw"]
        + result["scenario_adjustment_kw"]
        - result["conversion_loss_kw"]
        - result["clipped_kw"]
    )


def test_orientation_changes_profile_and_night_stays_dark():
    c, weather = fixture()
    d = default_design(c.plant, c.weather)
    for section in d["sections"]:
        section["azimuth"] = -90
    changed = transform_weather(weather, c, d)
    noon = weather["times"][-1]
    assert changed["truth"][noon]["pv_kw"] != pytest.approx(weather["truth"][noon]["pv_kw"])
    for time, sample in weather["truth"].items():
        if sample["irradiance_wm2"] == 0:
            assert changed["truth"][time]["pv_kw"] == 0


def test_preview_immutable_capacity_and_round_trip():
    c, weather = fixture()
    source = run(c, weather=weather, strategies=["Greedy"])
    saved = copy.deepcopy(source)
    design = default_design(c.plant, c.weather)
    for section in design["sections"]:
        section["capacity_kw"] *= 0.5
    design["converter_kw"] *= 0.5
    draft = preview(source, design)
    assert draft["energy_kwh"] == pytest.approx(draft["recorded_energy_kwh"] * 0.5)
    new_config = replace(c, plant=replace(c.plant, solar_kw=500), solar=design)
    frozen = {**weather, "solar_reference_config": c.to_dict()}
    new = run(new_config, weather=frozen, strategies=["Greedy"])
    assert new["run_id"] != source["run_id"]
    assert sum(r["pv_kw"] for r in new["records"]["Greedy"]) == pytest.approx(draft["energy_kwh"])
    assert preview(new)["energy_kwh"] == pytest.approx(draft["energy_kwh"])
    assert Config.from_dict(new["config"]).solar == validate(design)
    assert source == saved
    # Restore a full-size design without compounding losses from the half-size run.
    restored = transform_weather(new["weather"], new_config, default_design(c.plant, c.weather))
    assert restored["truth"][weather["times"][-1]]["pv_kw"] == pytest.approx(
        weather["truth"][weather["times"][-1]]["pv_kw"]
    )


def test_forecast_vintages_transform_independently():
    c, weather = fixture()
    t = weather["times"][-1]
    sample = weather["truth"][t]
    v = {
        "initialized_at": "2026-07-09T00:00:00+00:00",
        "available_at": "2026-07-09T06:00:00+00:00",
        "data": {t: dict(sample)},
    }
    weather["vintages"] = [v]
    d = default_design(c.plant, c.weather)
    before = transform_weather(weather, c, d)
    weather["truth"][t]["pv_kw"] = 0
    after = transform_weather(weather, c, d)
    assert before["vintages"] == after["vintages"]
    assert before["vintages"][0]["available_at"] == v["available_at"]


def test_legacy_template_inversion_and_invalid_inputs():
    c, weather = fixture()
    for sample in weather["template"].values():
        sample.pop("irradiance_wm2")
    d = default_design(c.plant, c.weather)
    transformed = transform_weather(weather, c, d)
    for time, sample in weather["template"].items():
        assert transformed["template"][time]["pv_kw"] == pytest.approx(sample["pv_kw"], abs=1e-7)
    d["sections"][0]["tilt"] = float("nan")
    with pytest.raises(ValueError):
        validate(d)
    sample = {"irradiance_wm2": 1400, "ambient_c": 0}
    sample["pv_kw"] = dc_power(1400, 0, c.plant, c.weather)
    clipped = interval(
        default_design(c.plant, c.weather), sample, weather["times"][-1], c.plant, c.weather
    )
    assert clipped["output_kw"] == c.plant.solar_kw
    assert clipped["clipped_kw"] > 0
