"""Independent procedure clocks, scarce work, and actual dock-bus energy."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Config, Plant, Scenario
from methane.faults import FaultPolicy, FaultState
from methane.field_operations import FieldOperations
from methane.reference import audit
from methane.sensing import Diagnosis
from methane.service_economics import illustrative
from methane.services.configuration import ServiceSystem
from methane.services.contracts import Quantity
from methane.services.plant import PlantServices
from methane.services.standby import allocate
from methane.simulation import run
from methane.weather import synthetic


def fixture(**options):
    return Config(
        scenario=Scenario(hours=12, horizon_hours=6, solver_seconds=0.05),
        field_operations=FieldOperations(
            enabled=True,
            rover_enabled=False,
            reset_enabled=False,
            initial_soiling_fraction=0,
            soiling_per_day=0,
            mission_failure_probability=0,
        ),
        service_system=ServiceSystem(
            inspector="none",
            support_model="logistics/1",
            maintenance_enabled=True,
            maintenance_target="cleaner",
            maintenance_first_due_hour=0,
            maintenance_interval_hours=4,
            maintenance_work_hours=0.5,
            crew_response_lead_hours=0,
            crew_travel_hours=0.25,
            replenishment_enabled=False,
            **options,
        ),
    )


def runtime(c):
    return PlantServices(c.field_operations, c.service_system, 7, c.plant.electrolyser_kw)


def tick(rt, h, pv=1000, battery=0, faults=None):
    diagnosis = Diagnosis(450)
    faults = faults or FaultState(Plant(), Scenario(), FaultPolicy())
    requested = rt.begin(h, diagnosis, pv, available_battery_kw=battery)
    applied = rt.execute_interval(h, faults)
    return requested, applied, rt.end(h, faults, diagnosis)


def use_opening_robot_energy(rt):
    quantity = Quantity("energy:cleaner", 1, "kWh")
    rt.ledger.reserve("FIXTURE-USE", (quantity,), (), 0)
    rt.ledger.consume("FIXTURE-USE", quantity, 0, "fixture")
    rt.ledger.release("FIXTURE-USE", 0)


def test_actual_maintenance_clock_consumables_and_crew_reconcile():
    c = fixture()
    rt = runtime(c)
    rows = [tick(rt, h)[2] for h in range(9)]
    effects = [e for r in rows for e in r["support_effects"] if e["kind"] == "routine-service"]
    # Request H0 + .25 h travel + .5 h work, then recurrence from work end.
    first_end = Decimal(".25") + Decimal(".5")
    assert [e["completed_at"] for e in effects] == [float(first_end), 5.75]
    assert [e["next_due_hour"] for e in effects] == [4.75, 9.75]
    assert sum(r["crew_committed_hours"] for r in rows) == 2
    assert sum(r["human_visits"] for r in rows) == 2
    assert rt.ledger.stock["stock:maintenance"] == 0
    assert rows[0]["decision"]["support"]["maintenance"]["schedules"][0]["completed_count"] == 0
    assert rows[0]["state"]["support"]["maintenance"]["schedules"][0]["completed_count"] == 1
    assert rows[4]["state"]["support"]["maintenance"]["schedules"][0]["completed_count"] == 1
    assert all(r["soiling_after"] == 0 for r in rows)


@pytest.mark.parametrize(
    "changes,reason",
    [
        ({"maintenance_kits": 0}, "stock:maintenance"),
        ({"crew_available": False}, "crew-available"),
        ({"crew_hours_per_period": 0}, "crew-hours"),
    ],
)
def test_unavailable_resources_leave_due_work_visible(changes, reason):
    rt = runtime(fixture(**changes))
    rows = [tick(rt, h)[2] for h in range(3)]
    assert not any(r["support_effects"] for r in rows)
    pending = rows[-1]["state"]["orders"]
    assert len(pending) == 1 and reason in pending[0]["blocked"]
    schedule = rows[-1]["state"]["support"]["maintenance"]["schedules"][0]
    assert schedule["next_due_hour"] == 0 and schedule["overdue_hours"] == 3
    assert not sum(r["human_visits"] for r in rows)


def test_interruption_charges_partial_work_without_resetting_clock():
    c = fixture()
    rt = runtime(replace(c, service_system=replace(c.service_system, maintenance_work_hours=2.5)))
    row = tick(rt, 0)[2]
    key = row["new_missions"][0]["order"]["order_id"]
    rt.executive.interrupt(key, "Declared access withdrawn")
    later = tick(rt, 1)[2]
    assert rt.ledger.stock["stock:maintenance"] == 1
    assert row["crew_committed_hours"] == 1
    assert not row["support_effects"] and not later["support_effects"]
    assert later["state"]["support"]["maintenance"]["schedules"][0]["completed_count"] == 0
    assert later["state"]["orders"][0]["status"] == "failed"


def test_maintenance_excludes_robot_charging_while_work_is_active():
    c = fixture()
    c = replace(c, service_system=replace(c.service_system, maintenance_work_hours=2))
    rt = runtime(c)
    use_opening_robot_energy(rt)
    row = tick(rt, 0)[2]
    assert [m["order"]["action"] for m in row["new_missions"]] == ["routine-service"]
    assert row["charge_input_kwh"] == 0


@pytest.mark.parametrize(
    "pv,battery,installed,expected",
    [(0, 2, True, 1), (0, 0.5, True, 0), (0.6, 0.4, True, 1), (10, 10, False, 0)],
)
def test_full_rate_standby_grant(pv, battery, installed, expected):
    result = allocate(1, pv, battery, installed)
    assert result["applied_kwh"] == expected
    assert result["unserved_kwh"] == (1 if installed else 0) - expected
    assert result["control_available"] == (installed and expected == 1)


@pytest.mark.parametrize("value", [-1, float("nan"), True])
def test_invalid_standby_assumptions_are_rejected(value):
    with pytest.raises(ValueError):
        allocate(value, 1, 1, True)


def test_brownout_is_unserved_demand_and_cannot_start_charging():
    c = fixture(dock_standby_kw=2)
    c = replace(c, service_system=replace(c.service_system, maintenance_enabled=False))
    rt = runtime(c)
    use_opening_robot_energy(rt)
    request, applied, row = tick(rt, 0, pv=1, battery=0)
    assert request == applied == 0
    assert row["requested_service_kwh"] == row["unapplied_service_kwh"] == 2
    assert row["standby"]["control_available"] is False and not row["new_missions"]


@pytest.fixture(scope="module")
def coupled():
    c = fixture(dock_standby_kw=1)
    c = replace(c, plant=replace(c.plant, initial_soc=0.1), service_economics=illustrative(c.costs))
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for s in mapping.values():
            s.update(pv_kw=0, irradiance_wm2=0, ambient_c=20)
    result = run(c, weather=weather, strategies=["Greedy"])
    assert result["status"] == "complete", result["failures"]
    return result


def test_night_standby_uses_actual_plant_battery_and_independent_reference(coupled):
    rows = coupled["records"]["Greedy"]
    assert rows[0]["field_operations"]["standby"]["applied_kwh"] == 1
    assert all(
        r["applied"]["discharge_kw"] >= r["field_operations"]["standby"]["applied_kwh"] - 1e-7
        for r in rows
    )
    assert any(r["field_operations"]["standby"]["unserved_kwh"] == 1 for r in rows)
    report = audit(coupled)
    assert not report["failures"], report["failures"]
    assert report["passed"], [x for x in report["checks"] if not x["passed"]][:8]


def test_reference_detects_forged_standby_and_maintenance_clock(coupled):
    for path in ("standby", "maintenance"):
        changed = copy.deepcopy(coupled)
        row = changed["records"]["Greedy"][0]["field_operations"]
        if path == "standby":
            row["standby"]["applied_kwh"] += 0.2
        else:
            row["state"]["support"]["maintenance"]["schedules"][0]["next_due_hour"] += 1
        report = audit(changed)
        assert not report["passed"]
        assert any(path in x["check"] for x in report["checks"] if not x["passed"])


def test_routine_work_does_not_clear_injected_equipment_damage():
    c = fixture(equipment_recovery_enabled=True)
    rt = runtime(c)
    f = FaultState(
        c.plant,
        c.scenario,
        FaultPolicy(cleaner_service_fault="drive-power-loss", service_fault_start_hour=0),
    )
    rows = [tick(rt, h, faults=f)[2] for h in range(3)]
    assert any(e["kind"] == "routine-service" for r in rows for e in r["support_effects"])
    assert f.service_hardware_truth("cleaner", 3)["active"]
    assert all(not r["retrospective_effects"] for r in rows)


def test_failed_charger_power_stage_still_consumes_upstream_control_power():
    c = fixture(dock_standby_kw=0.25, equipment_recovery_enabled=True)
    rt = runtime(replace(c, service_system=replace(c.service_system, maintenance_enabled=False)))
    use_opening_robot_energy(rt)
    f = FaultState(
        c.plant,
        c.scenario,
        FaultPolicy(dock_service_fault="charger-power-loss", service_fault_start_hour=0),
    )
    request, applied, row = tick(rt, 0, faults=f)
    assert request == 1.25 and applied == 0.25
    assert row["standby"]["control_available"]
    assert row["charge_input_kwh"] == 0 and row["unapplied_service_kwh"] == 1
    assert row["fixed_service_kwh"] == 0.25


def test_finite_resupply_allows_due_work_only_after_recorded_receipt():
    c = fixture(maintenance_kits=0)
    o = replace(
        c.service_system,
        replenishment_enabled=True,
        delivery_batch_kits=1,
        supplier_kits=1,
        maintenance_interval_hours=100,
    )
    rt = runtime(replace(c, service_system=o))
    rows = [tick(rt, h)[2] for h in range(6)]
    effects = [e for r in rows for e in r["support_effects"]]
    delivery = next(e for e in effects if e["kind"] == "restock" and e["material"] == "maintenance")
    work = next(e for e in effects if e["kind"] == "routine-service")
    assert delivery["accepted"] == 1
    assert work["completed_at"] > delivery["effective_at"]
    assert rt.ledger.stock["upstream:maintenance"] == rt.ledger.stock["stock:maintenance"] == 0


def test_pending_due_work_is_not_retroactively_changed_by_future_faults():
    c = fixture()
    records = []
    for start in (4, 8):
        rt = runtime(c)
        f = FaultState(
            c.plant,
            c.scenario,
            FaultPolicy(service_fault_start_hour=start, cleaner_service_fault="drive-power-loss"),
        )
        records.append([tick(rt, h, faults=f)[2]["decision"] for h in range(3)])
    assert records[0] == records[1]


def test_shared_routine_visits_reconcile_declared_work_and_target_reservations():
    from methane.services.routine_demo import execute

    result = execute("routine")
    report = audit(result)
    assert report["passed"], (
        report["failures"] or [c for c in report["checks"] if not c["passed"]][:5]
    )
    visits = [v for r in result["records"]["Greedy"] for v in r["field_operations"]["new_visits"]]
    assert visits and any(len(v["members"]) > 1 for v in visits)
