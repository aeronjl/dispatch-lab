"""Independent surface-area, optical and partial-mission acceptance checks."""

import copy
import json
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Config, Scenario, WeatherConfig
from methane.field_operations import FieldOperations
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.services.surface import Patch, treat
from methane.simulation import run
from methane.solar_model import default_design
from methane.weather import synthetic


def mean(patches, term="removable"):
    return sum(Decimal(str(p.area)) * Decimal(str(getattr(p, term))) for p in patches) / Decimal(
        str(patches[-1].end_m2)
    )


def config(**options):
    return Config(
        scenario=Scenario(hours=10, horizon_hours=6, solver_seconds=0.05),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=FieldOperations(
            enabled=True,
            rover_enabled=False,
            reset_enabled=False,
            human_fallback=False,
            initial_soiling_fraction=0.1,
            soiling_per_day=0,
            cleaning_removal_fraction=1,
            mission_failure_probability=0,
        ),
        service_system=ServiceSystem(
            cleaning_model="section-optical/1",
            inspector="none",
            initial_adhered_fraction=0.2,
            initial_damage_fraction=0.05,
            **options,
        ),
    )


def sunny(c):
    w = synthetic(c)
    for mapping in (w["truth"], w["template"]):
        for sample in mapping.values():
            sample.update(irradiance_wm2=1000, pv_kw=1000, ambient_c=20)
    return w


def test_partial_dry_brushing_changes_only_loose_loss_with_independent_area_arithmetic():
    before = (Patch(0, 1000, 0.1, 0.2, 0.05),)
    partial = treat(before, 0, 250, 0.8, 0.8)
    expected = (Decimal(250) * Decimal(".02") + Decimal(750) * Decimal(".1")) / 1000
    assert float(mean(partial)) == pytest.approx(float(expected))
    assert float(mean(partial, "adhered")) == 0.2
    assert float(mean(partial, "damaged")) == 0.05
    assert before[0].removable == 0.1
    with pytest.raises(ValueError, match="bounds"):
        treat(before, 0, 1001, 0.8, 0.8)


def test_partitioning_constant_efficacy_sweep_preserves_optical_inventory():
    before = (Patch(0, 1000, 0.1, 0.2, 0.05),)
    whole = treat(before, 0, 1000, 0.8, 0.8)
    split = before
    for a, b in ((0, 130), (130, 370), (370, 900), (900, 1000)):
        split = treat(split, a, b, 0.8, 0.8)
    assert float(mean(whole)) == pytest.approx(float(mean(split)))
    assert sum(p.area * p.transmission for p in whole) == pytest.approx(
        sum(p.area * p.transmission for p in split)
    )


@pytest.fixture(scope="module")
def optical_run():
    c = config()
    return run(c, weather=sunny(c), strategies=["Greedy"])


def test_optical_effects_apply_after_interval_and_full_audit_reconciles(optical_run):
    r = optical_run
    assert r["status"] == "complete", r["failures"]
    rows = r["records"]["Greedy"]
    # At zero temperature coefficient and no electrical losses, independent
    # transmission is (1-.1)*(1-.2)*(1-.05) = .684.
    assert rows[0]["pv_kw"] == pytest.approx(684)
    f = rows[0]["field_operations"]
    assert f["treated_area_m2"] == 500
    assert f["brush_wear_m2"] == 500
    assert f["cleanings_completed"] == 0
    assert f["soiling_after"] == pytest.approx(0.09)
    assert rows[1]["pv_kw"] == pytest.approx(1000 * 0.91 * 0.8 * 0.95)
    assert f["surface_events"][0]["effective_at"] == 1
    assert f["state"]["surface"]["sections"][-1]["adhered_fraction"] == pytest.approx(0.2)
    report = audit(r)
    assert report["passed"], [c for c in report["checks"] if not c["passed"]][:10]
    # Check the independent audit itself catches forged treatment or conversion.
    damaged = copy.deepcopy(r)
    damaged["records"]["Greedy"][0]["field_operations"]["surface_events"][0]["efficacy_start"] = 0.1
    assert not audit(damaged)["passed"]


def test_interruption_retains_completed_area_and_consumes_only_elapsed_resources():
    c = config(work_failure_fraction=0.3)
    c = replace(c, field_operations=replace(c.field_operations, mission_failure_probability=1))
    result = run(c, weather=sunny(c), strategies=["Greedy"])
    assert result["status"] == "complete", result["failures"]
    records = [r["field_operations"] for r in result["records"]["Greedy"]]
    assert sum(r["treated_area_m2"] for r in records) == pytest.approx(500)
    assert sum(r["robot_use_kwh"] for r in records) == pytest.approx(0.2)
    assert sum(r["cleaning_kits_used"] for r in records) == 1
    assert sum(r["cleanings_completed"] for r in records) == 0
    assert records[-1]["soiling_after"] == pytest.approx(0.09)
    assert records[-1]["state"]["robots"]["cleaner"]["status"] == "requires retrieval"
    assert audit(result)["passed"]


@pytest.mark.parametrize(
    "conditions,reason",
    [
        ({"environment_source": "weather"}, "wind-mps"),
        ({"assumed_wind_mps": 9}, "wind-mps"),
        ({"assumed_rain_mmph": 1}, "rain-mmph"),
        ({"row_accessible": False}, "row-accessible"),
        ({"brush_initial_condition": 0.01}, "brush:cleaner"),
    ],
)
def test_unavailable_conditions_or_exhausted_brush_block_work(conditions, reason):
    c = config(**conditions)
    result = run(c, weather=sunny(c), strategies=["Greedy"])
    assert result["status"] == "complete", result["failures"]
    final = result["records"]["Greedy"][-1]["field_operations"]
    assert final["treated_area_m2"] == 0
    assert reason in final["state"]["orders"][0]["blocked"]
    assert final["soiling_after"] == 0.1


def test_cleaning_can_recover_light_without_recovering_available_dc_due_to_clipping():
    c = config()
    design = default_design(c.plant, c.weather)
    design["converter_kw"] = 500
    c = replace(c, solar=design)
    r = run(c, weather=sunny(c), strategies=["Greedy"])
    assert r["status"] == "complete", r["failures"]
    rows = r["records"]["Greedy"]
    assert rows[0]["solar_detail"]["clipped_kw"] == pytest.approx(184)
    assert rows[1]["solar_detail"]["clipped_kw"] > 184
    assert all(row["pv_kw"] == pytest.approx(500) for row in rows)
    assert rows[1]["field_operations"]["soiling_loss_kw"] == 0
    assert rows[0]["curtailed_kwh"] == 0  # Plant curtailment remains a separate bus result.
    assert audit(r)["passed"]


def test_future_realized_weather_cannot_change_earlier_cleaning_or_dispatch():
    c = config()
    baseline = sunny(c)
    altered = copy.deepcopy(baseline)
    for t in altered["times"][6:]:
        altered["truth"][t].update(irradiance_wm2=100, pv_kw=100)
    a = run(c, weather=baseline, strategies=["Greedy"])
    b = run(c, weather=altered, strategies=["Greedy"])
    for x, y in zip(a["records"]["Greedy"][:6], b["records"]["Greedy"][:6], strict=True):
        assert x["decision"] == y["decision"]
    assert json.dumps(a["field_operations_model"]["surface_model"]) == json.dumps(
        b["field_operations_model"]["surface_model"]
    )


def test_missing_forecast_radiation_is_an_explicit_incomplete_input():
    from methane.forecast import IncompleteWeather

    c = config()
    weather = sunny(c)
    del weather["template"][weather["times"][1]]["irradiance_wm2"]
    with pytest.raises(IncompleteWeather, match="missing radiation"):
        run(c, weather=weather, strategies=["Greedy"])


def test_zero_installed_area_has_no_cleaning_and_remains_auditable():
    c = config()
    c = replace(c, plant=replace(c.plant, solar_kw=0))
    result = run(c, strategies=["Greedy"])
    assert result["status"] == "complete"
    assert not result["records"]["Greedy"][-1]["field_operations"]["state"]["orders"]
    report = audit(result)
    assert report["passed"], [x for x in report["checks"] if not x["passed"]][:6]


def test_optical_audit_with_temperature_and_orientation_effects():
    c = config()
    c = replace(c, weather=replace(c.weather, loss_fraction=0.14, temperature_coefficient=-0.004))
    design = default_design(c.plant, c.weather)
    design["sections"][0].update(tilt=60, azimuth=-90, shade=0.2)
    design["sections"][1].update(tilt=10, azimuth=80)
    c = replace(c, solar=design)
    result = run(c, strategies=["Greedy"])
    assert result["status"] == "complete"
    report = audit(result)
    assert report["passed"], [x for x in report["checks"] if not x["passed"]][:6]


def test_forecast_error_compares_the_same_surface_conversion_basis():
    c = config()
    c = replace(c, scenario=replace(c.scenario, forecast_bias=0.2))
    weather = sunny(c)
    for sample in weather["template"].values():
        sample.update(pv_kw=400, irradiance_wm2=400)
    for sample in weather["truth"].values():
        sample.update(pv_kw=600, irradiance_wm2=600)
    result = run(c, weather=weather, strategies=["Greedy"])
    forecast = result["records"]["Greedy"][0]["decision"]["forecast"]
    assert forecast["source_forecast_error_kw"] == pytest.approx(-80)
    assert forecast["current_forecast_error_kw"] == pytest.approx(-80 * 0.684)
