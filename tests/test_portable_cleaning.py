"""Independent treatment, water, labour and compatibility examples."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.services.portable_demo import execute
from methane.services.portable_demo import fixture as config
from methane.services.surface import Patch, treat


@pytest.fixture(scope="module")
def wet():
    return execute(config())


def rows(result):
    return [r["field_operations"] for r in result["records"]["Greedy"]]


def test_wet_treatment_matches_independent_optical_expectation_without_repairing_damage():
    surface = (Patch(0, 100, 0.1, 0.2, 0.05),)
    dry = treat(surface, 0, 50, 0.9, 0.9)
    wet = treat(surface, 0, 50, 0.9, 0.9, 0.7)
    expected_dry = Decimal(".99") * Decimal(".8") * Decimal(".95")
    expected_wet = Decimal(".99") * Decimal(".94") * Decimal(".95")
    assert dry[0].transmission == pytest.approx(float(expected_dry))
    assert wet[0].transmission == pytest.approx(float(expected_wet))
    assert wet[1] == dry[1] == Patch(50, 100, 0.1, 0.2, 0.05)
    assert all(p.damaged == 0.05 for p in wet)
    split = treat(treat(surface, 0, 25, 0.9, 0.9, 0.7), 25, 50, 0.9, 0.9, 0.7)
    assert sum(p.area * p.transmission for p in split) == pytest.approx(
        sum(p.area * p.transmission for p in wet)
    )


def test_setup_water_partial_work_effects_and_crew_time_reconcile(wet):
    services = rows(wet)
    area = Decimal(5000) / 3
    water = Decimal(10) + area * Decimal(".5")
    assert sum(r["treated_area_m2"] for r in services) == pytest.approx(float(area))
    assert sum(r["water_used_l"] for r in services) == pytest.approx(float(water))
    assert services[3]["water_used_l"] == 260
    assert services[3]["treated_area_m2"] == 500
    assert services[2]["treated_area_m2"] == 0
    assert all(r["brush_wear_m2"] == 0 for r in services)
    expected_hours = Decimal(1) + Decimal(".5") + area / 1000 + Decimal(".25") + 1
    assert sum(r["portable_hours"] for r in services) == pytest.approx(float(expected_hours))
    report = audit(wet)
    assert report["passed"], [q for q in report["checks"] if not q["passed"]][:5]


def test_water_delivery_preserves_litre_units_and_records_rejected_excess(wet):
    services = rows(wet)
    effect = next(e for r in services for e in r["support_effects"] if e.get("material") == "water")
    assert effect["unit"] == "L"
    assert effect["quantity"] == 1000
    assert effect["accepted"] == pytest.approx(843.3333333333)
    assert effect["accepted"] + effect["rejected"] == 1000
    final = services[-1]["state"]["support"]
    assert final["water_l"] == 1000 and final["upstream"]["water"] == 4000
    assert final["upstream_units"]["water"] == "L"
    assert not any(r["water_used_l"] for r in services[6:])


@pytest.mark.parametrize("method", ["dry", "wet"])
def test_empty_water_does_not_silently_change_the_requested_treatment(method):
    r = execute(config(method, portable_water_initial_l=0, portable_upstream_water_l=0))
    s = rows(r)
    assert sum(x["water_used_l"] for x in s) == 0
    assert (sum(x["treated_area_m2"] for x in s) > 0) == (method == "dry")
    assert all(p["adhered"] == 0.2 for ps in s[-1]["surface_after"].values() for p in ps)
    assert audit(r)["passed"]


def test_wet_work_blocks_in_cold_weather_and_unavailable_crew():
    for r in (execute(config(), ambient=0), execute(config(crew_available=False))):
        assert sum(x["treated_area_m2"] for x in rows(r)) == 0
        assert sum(x["human_visits"] for x in rows(r)) == 0
        assert audit(r)["passed"]


def test_supply_does_not_repeat_deliveries_that_cannot_make_a_full_section_feasible():
    c = config(portable_water_capacity_l=100, portable_water_initial_l=0)
    r = execute(c)
    assert sum(x["human_visits"] for x in rows(r)) == 0
    assert any(
        q["kind"] == "portable-cleaning" and q["status"] == "queued"
        for q in rows(r)[-1]["state"]["orders"]
    )
    c = replace(config(portable_water_initial_l=0), plant=replace(c.plant, solar_kw=0))
    r = execute(c)
    assert not rows(r)[-1]["state"]["orders"]


def test_partial_failure_keeps_water_and_treatment_and_does_not_reuse_stranded_crew():
    c = config(work_failure_fraction=0.3)
    c = replace(c, field_operations=replace(c.field_operations, mission_failure_probability=1))
    r = execute(c)
    s = rows(r)
    assert sum(x["treated_area_m2"] for x in s) == pytest.approx(500)
    assert sum(x["water_used_l"] for x in s) == pytest.approx(260)
    assert sum(x["human_visits"] for x in s) == 1
    assert s[-1]["state"]["portable"]["status"] == "requires assistance"
    assert audit(r)["passed"]


def test_row_and_portable_tools_share_exclusive_work_surfaces():
    c = config("dry", crew_response_lead_hours=0)
    c = replace(c, field_operations=replace(c.field_operations, cleaner_enabled=True))
    r = execute(c)
    reservations = [e for s in rows(r) for e in s["resource_events"] if e["kind"] == "reserve"]
    slots = [
        b for e in reservations for b in e["capacity"] if b["resource"].startswith("work-area:")
    ]
    for i, a in enumerate(slots):
        for b in slots[i + 1 :]:
            if a["resource"] == b["resource"]:
                assert min(a["end"], b["end"]) <= max(a["start"], b["start"]) + 1e-8
    assert audit(r)["passed"]


@pytest.mark.parametrize(
    "field,value", [("water_used_l", 0), ("portable_hours", 99), ("brush_wear_m2", 500)]
)
def test_independent_checker_rejects_false_water_duration_or_brush_accounting(wet, field, value):
    r = copy.deepcopy(wet)
    rows(r)[3][field] = value
    assert not audit(r)["passed"]


def test_portable_configuration_requires_its_mechanisms():
    with pytest.raises(ValueError, match="section optics"):
        ServiceSystem(portable_cleaner="wet")
    with pytest.raises(ValueError, match="exceeds"):
        ServiceSystem(portable_water_initial_l=1001)
    c = config()
    with pytest.raises(ValueError, match="enabled contracted crew"):
        replace(c, field_operations=replace(c.field_operations, human_fallback=False))
