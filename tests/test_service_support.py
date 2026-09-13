"""Recovery, finite labour/supply and observed return-to-work acceptance checks."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Config, Scenario, WeatherConfig
from methane.field_operations import FieldOperations
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.services.support import fits_shift, on_shift
from methane.simulation import run
from methane.weather import synthetic


def fixture(**options):
    c = Config(
        scenario=Scenario(hours=18, horizon_hours=6, solver_seconds=0.05),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=FieldOperations(
            enabled=True,
            rover_enabled=False,
            reset_enabled=False,
            initial_soiling_fraction=0.1,
            soiling_per_day=0,
            mission_failure_probability=1,
        ),
        service_system=ServiceSystem(
            inspector="none",
            cleaning_model="section-optical/1",
            support_model="logistics/1",
            work_failure_fraction=0.3,
            **options,
        ),
    )
    return c


def execute(c):
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=1000, irradiance_wm2=1000, ambient_c=20)
    result = run(c, weather=weather, strategies=["Greedy"])
    assert result["status"] == "complete", result["failures"]
    return result


def service(result):
    return [r["field_operations"] for r in result["records"]["Greedy"]]


@pytest.fixture(scope="module")
def recovered():
    return execute(fixture())


def test_retrieval_preserves_failed_work_and_waits_for_a_new_drive_observation(recovered):
    rows = service(recovered)
    assert rows[0]["treated_area_m2"] == pytest.approx(500)
    effect = next(e for r in rows for e in r["support_effects"] if e["kind"] == "retrieve")
    # Independent schedule: request at H1, response lead 2h, travel 1h,
    # pack .5h, return to dock .5h, unload .5h. Physical receipt at 5.5 -> H6.
    expected = Decimal(1) + Decimal(2) + Decimal(1) + Decimal(".5") * 3
    assert effect["completed_at"] == float(expected) == 5.5
    assert effect["effective_at"] == 6
    original = effect["origin_order"]
    assert rows[4]["state"]["robots"]["cleaner"]["status"] == "requires retrieval"
    assert rows[5]["state"]["robots"]["cleaner"]["status"] == "awaiting drive test"
    assert rows[6]["state"]["robots"]["cleaner"]["status"] == "available"
    assert rows[6]["remote_hours"] == 0.25
    old = next(o for o in rows[6]["state"]["orders"] if o["id"] == original)
    assert old["status"] == "failed" and old["retrieved_at"] == 6
    assert old["progress"] == pytest.approx(0.3)
    assert sum(r["crew_committed_hours"] for r in rows[:7]) == pytest.approx(3.5)
    assert sum(r["human_visits"] for r in rows[:7]) == 1
    report = audit(recovered)
    assert report["passed"], [x for x in report["checks"] if not x["passed"]][:6]


@pytest.mark.parametrize(
    "options,reason",
    [
        ({"crew_hours_per_period": 0}, "crew-hours"),
        ({"crew_shift_duration_hours": 4}, "fit a declared shift"),
        ({"crew_available": False}, "crew-available"),
    ],
)
def test_finite_or_unavailable_crew_cannot_teleport_the_robot_home(options, reason):
    result = execute(fixture(**options))
    rows = service(result)
    assert not any(r["support_effects"] for r in rows)
    assert rows[-1]["state"]["robots"]["cleaner"]["status"] == "requires retrieval"
    reasons = [
        q.get("blocked", "")
        for row in rows
        for q in row["state"]["orders"]
        if q["kind"] == "retrieve"
    ]
    assert any(reason in r for r in reasons)
    assert sum(r["human_visits"] for r in rows) == 0


@pytest.mark.parametrize(
    "options",
    [
        {"remote_hours_per_period": 0},
        {"communications_available": False},
        {"robot_test_success_probability": 0},
    ],
)
def test_relocation_alone_cannot_restore_an_available_robot(options):
    rows = service(execute(fixture(**options)))
    assert rows[-1]["state"]["robots"]["cleaner"]["status"] == "awaiting drive test"
    assert sum(len(r["support_effects"]) for r in rows) == 1
    assert sum(r["treated_area_m2"] for r in rows) == pytest.approx(500)


def test_brush_replacement_discards_unused_allowance_then_installs_one_finite_spare():
    c = fixture(brush_initial_condition=0.01)
    c = replace(c, field_operations=replace(c.field_operations, mission_failure_probability=0))
    result = execute(c)
    rows = service(result)
    effect = next(e for r in rows for e in r["support_effects"] if e["kind"] == "replace-brush")
    assert effect["discarded_allowance_m2"] == 500
    assert effect["effective_at"] == 4
    assert rows[2]["brush_after_m2"] == 500
    assert rows[3]["brush_after_m2"] == 50000
    assert rows[3]["brush_wear_m2"] == 0
    assert rows[3]["state"]["support"]["brush_spares"] == 1
    assert rows[4]["treated_area_m2"] > 0
    report = audit(result)
    assert report["passed"], [x for x in report["checks"] if not x["passed"]][:6]


def test_delivery_accounts_for_rejected_stock_and_finite_typed_upstream_supply():
    c = fixture(store_capacity_kits=1, supplier_kits=4, calibration_kits=0, brush_spares=0)
    c = replace(
        c,
        field_operations=replace(
            c.field_operations, cleaning_kits=0, service_kits=0, mission_failure_probability=0
        ),
    )
    result = execute(c)
    rows = service(result)
    e = next(
        e
        for r in rows
        for e in r["support_effects"]
        if e["kind"] == "restock" and e["material"] == "cleaning"
    )
    assert e["quantity"] == 4 and e["accepted"] == 1 and e["rejected"] == 3
    assert rows[e["effective_at"] - 1]["state"]["support"]["upstream"]["cleaning"] == 0
    assert not any(r["cleaning_kits_used"] for r in rows[: e["effective_at"]])
    report = audit(result)
    assert report["passed"], [x for x in report["checks"] if not x["passed"]][:6]
    altered = copy.deepcopy(result)
    row = altered["records"]["Greedy"][e["effective_at"] - 1]["field_operations"]
    event = next(
        x
        for x in row["resource_events"]
        if x["kind"] == "replenish" and x["resource"] == "stock:cleaning"
    )
    event["accepted"] = 4
    assert not audit(altered)["passed"]


def test_calendar_boundaries_and_return_time_are_explicit():
    o = ServiceSystem(crew_shift_start_hour=8, crew_shift_duration_hours=8)
    assert not on_shift(7, o) and on_shift(8, o) and not on_shift(16, o)
    assert fits_shift(8, 16, o) and not fits_shift(8, 16.01, o)
    assert not fits_shift(23, 25, o)
    assert fits_shift(32, 40, o)
    with pytest.raises(ValueError, match="fit inside"):
        ServiceSystem(crew_shift_start_hour=20, crew_shift_duration_hours=8)


def test_period_labor_replenishment_is_recorded_and_never_backdated():
    c = fixture()
    c = replace(c, scenario=replace(c.scenario, hours=28))
    result = execute(c)
    rows = service(result)
    events = [
        e
        for r in rows
        for e in r["resource_events"]
        if e["kind"] == "replenish" and e["resource"] == "crew-hours"
    ]
    assert len(events) == 1 and events[0]["at_hour"] == 24
    assert events[0]["offered"] == 12
    assert events[0]["accepted"] + events[0]["rejected"] == 12
    assert audit(result)["passed"]


@pytest.mark.parametrize(
    "change", ["effect-time", "return-flag", "labour", "drive-time", "drive-value", "crew-lead"]
)
def test_independent_audit_rejects_forged_support_history(recovered, change):
    changed = copy.deepcopy(recovered)
    rows = service(changed)
    if change == "effect-time":
        rows[5]["support_effects"][0]["effective_at"] = 5
    elif change == "return-flag":
        rows[4]["state"]["orders"][0]["retrieved_at"] = 5
    elif change == "labour":
        rows[3]["crew_committed_hours"] = 0
    elif change in ("drive-time", "drive-value"):
        for r in rows[6:]:
            for reading in r["state"]["executive"]["observations"]:
                if reading["channel"] == "robot-ready:cleaner":
                    reading["measured_at" if change == "drive-time" else "value"] = (
                        5 if change == "drive-time" else False
                    )
    else:
        plan = rows[3]["new_missions"][0]
        plan["order"]["requested_at"] = 3
    report = audit(changed)
    assert not report["passed"]
    assert any(not c["passed"] and c["check"].startswith("support.") for c in report["checks"])
