"""Independent expectations and causal recovery boundaries for service equipment."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Plant, Scenario
from methane.faults import FaultPolicy, FaultState
from methane.reference import audit
from methane.services.hardware import remote_shift
from methane.services.hardware_demo import CASES, execute, fixture


def rows(result):
    return [r["field_operations"] for r in result["records"]["Greedy"]]


def orders(result):
    return rows(result)[-1]["state"]["orders"]


@pytest.fixture(scope="module")
def cases():
    return {name: execute(fixture(name)) for name in CASES}


@pytest.mark.parametrize("name", CASES)
def test_complete_hardware_workflow_reconciles(name, cases):
    r = cases[name]
    assert r["status"] == "complete", r["failures"]
    result = audit(r)
    assert result["passed"], (
        result["failures"] or [q for q in result["checks"] if not q["passed"]][:5]
    )
    assert {q["version"] for q in rows(r)} == {"plant-service-contracts/11"}


def test_remote_release_cannot_replace_an_open_power_stage_or_a_future_fault():
    c = fixture()
    for cause in ("control-hold", "drive-power-loss"):
        fault = FaultState(
            Plant(),
            Scenario(),
            FaultPolicy(
                lifecycle="transient", service_fault_start_hour=4, cleaner_service_fault=cause
            ),
        )
        fault.service_hardware("cleaner", "hardware-replacement", 3, True)
        assert fault.service_hardware_truth("cleaner", 4)["active"]
        assert fault.service_hardware_truth("cleaner", 1000)["active"]
        fault.service_hardware("cleaner", "remote-release", 1000, True)
        assert fault.service_hardware_truth("cleaner", 1001)["active"] == (
            cause == "drive-power-loss"
        )
        fault.service_hardware("rover", "hardware-replacement", 1001, True)
        assert fault.service_hardware_truth("cleaner", 1002)["active"] == (
            cause == "drive-power-loss"
        )
        fault.service_hardware("cleaner", "hardware-replacement", 1002, True)
        assert not fault.service_hardware_truth("cleaner", 1003)["active"]
    assert remote_shift(0, 12, c.service_system)
    assert not remote_shift(23, 25, c.service_system)


def test_hold_recovery_spends_operator_time_and_returns_before_readiness(cases):
    r = cases["control-hold"]
    service = rows(r)
    returned = next(
        e for row in service for e in row["support_effects"] if e["kind"] == "guided-return"
    )
    # H5 departure + .5h recorded return + .25h completion, eligible at H6.
    assert returned["completed_at"] == float(Decimal(5) + Decimal(".5") + Decimal(".25"))
    assert returned["effective_at"] == 6
    assert sum(row["human_visits"] for row in service) == 0
    assert sum(row["remote_hours"] for row in service) == float(Decimal(".25") * 3 + Decimal(".75"))
    assert service[5]["state"]["robots"]["cleaner"]["status"] == "awaiting drive test"
    assert service[8]["state"]["robots"]["cleaner"]["status"] == "available"
    assert not any(row["hardware_modules_used"] for row in service)


def test_a_failed_release_stays_unverified_after_a_successful_replacement(cases):
    jobs = orders(cases["drive-power-loss"])
    release = next(q for q in jobs if q["kind"] == "remote-release")
    repaired = next(q for q in jobs if q["kind"] == "hardware-replacement")
    assert release["verified_at_hour"] is None
    assert repaired["verified_at_hour"] is not None
    assert (
        sum(
            row["hardware_modules_used"].get("cleaner", 0)
            for row in rows(cases["drive-power-loss"])
        )
        == 1
    )
    for name, state in (("failed-replacement", "escalated"), ("no-spares", "replace")):
        last = rows(cases[name])[-1]["state"]
        assert last["support"]["equipment"]["incidents"][0]["state"] == state
        assert last["robots"]["cleaner"]["status"] != "available"


def test_charger_failure_does_not_create_charge_and_returns_only_after_load_test(cases):
    service = rows(cases["charger-power-loss"])
    failed = next(
        i
        for i, row in enumerate(service)
        if any(
            e["kind"] == "interrupted" and e["order_id"].startswith("CHARGE-")
            for e in row["mission_events"]
        )
    )
    ready = next(
        i
        for i, row in enumerate(service[failed:], failed)
        if row["state"]["support"]["equipment"]["incidents"]
        and row["state"]["support"]["equipment"]["incidents"][0]["state"] == "ready"
    )
    assert all(row["charge_input_kwh"] == 0 for row in service[failed:ready])
    assert any(row["charge_input_kwh"] > 0 for row in service[ready:])
    assert sum(row["hardware_modules_used"].get("dock", 0) for row in service) == 1


def test_portable_return_keeps_original_work_and_does_not_add_a_callout(cases):
    r = cases["pump-power-loss"]
    service = rows(r)
    first = next(q for q in orders(r) if q["kind"] == "portable-cleaning")
    assert first["status"] == "failed" and first["from_point"] == "solar"
    assert first["retrieved_at"] == 6
    packing = next(q for q in orders(r) if q["kind"] == "pack-return")
    events = [e for row in service for e in row["mission_events"] if e["order_id"] == packing["id"]]
    assert not any(e["kind"] == "stage_start" and e["phase"] == "travel" for e in events)
    assert sum(e["end"] - e["start"] for e in events if e["kind"] == "interval") == 1.75
    assert sum(row["hardware_modules_used"].get("portable", 0) for row in service) == 1
    stopped = rows(cases["portable-abort"])
    assert any(row["treated_area_m2"] > 0 for row in stopped)
    assert any(
        q.get("retrieved_at") is not None and q["status"] == "failed"
        for q in orders(cases["portable-abort"])
    )


def test_private_cause_cannot_change_actions_before_the_discriminating_test(cases):
    a, b = cases["control-hold"], cases["drive-power-loss"]
    for ra, rb in zip(a["records"]["Greedy"][:4], b["records"]["Greedy"][:4], strict=True):
        assert ra["decision"]["field_operations"] == rb["decision"]["field_operations"]
        assert ra["requested"] == rb["requested"]
    for r in (a, b):
        for record in rows(r):
            assert "hardware_execution" not in record
            assert "private_state" not in str(record["decision"])
        assert any(
            t.get("hardware_execution") for t in r["retrospective_truth_by_controller"]["Greedy"]
        )


@pytest.mark.parametrize(
    "options",
    [
        {"remote_hours_per_period": 0},
        {"remote_shift_duration_hours": 0},
        {"communications_available": False},
        {"remote_release_hours": 4},
    ],
)
def test_unavailable_or_overlong_remote_help_escalates_without_free_work(options):
    c = fixture("control-hold")
    r = execute(replace(c, service_system=replace(c.service_system, **options)))
    service = rows(r)
    assert any(e["kind"] == "retrieve" for row in service for e in row["support_effects"])
    assert not any(e["kind"] == "guided-return" for row in service for e in row["support_effects"])
    if (
        options.get("remote_hours_per_period") == 0
        or options.get("remote_shift_duration_hours") == 0
        or options.get("communications_available") is False
    ):
        assert sum(row["remote_hours"] for row in service) == 0
    assert audit(r)["passed"]


def test_a_new_fault_during_guided_return_retains_the_new_stranding_location():
    c = fixture("control-hold")
    c = replace(
        c,
        faults=replace(
            c.faults, service_fault_start_hour=7, cleaner_service_fault="drive-power-loss"
        ),
        field_operations=replace(c.field_operations, mission_failure_probability=1),
        service_system=replace(c.service_system, travel_hours=1.5),
    )
    r = execute(c)
    service = rows(r)
    guided = next(q for q in orders(r) if q["kind"] == "guided-return")
    assert guided["status"] == "failed" and 0 < guided["progress"] < 1
    receipt = next(e for row in service for e in row["support_effects"] if e["kind"] == "retrieve")
    assert receipt["origin_order"] == guided["id"]
    assert len(receipt["returned_orders"]) == 2
    assert all(
        next(q for q in orders(r) if q["id"] == key).get("retrieved_at") == receipt["effective_at"]
        for key in receipt["returned_orders"]
    )
    a = audit(r)
    assert a["passed"], a["failures"] or [x for x in a["checks"] if not x["passed"]][:5]


@pytest.mark.parametrize(
    "change",
    [
        "private-cause",
        "observation-time",
        "remote-hours",
        "module-count",
        "false-acceptance",
        "return-location",
    ],
)
def test_reference_rejects_forged_hardware_evidence(cases, change):
    r = copy.deepcopy(cases["drive-power-loss"])
    s = rows(r)
    if change == "private-cause":
        effect = next(
            e
            for t in r["retrospective_truth_by_controller"]["Greedy"]
            for receipt in t.get("hardware_execution", [])
            for e in receipt["effects"]
            if e.get("kind") == "hardware-command"
        )
        effect["private_state"]["cause"] = "control-hold"
    elif change == "observation-time":
        reading = next(
            q
            for row in s
            for q in row["state"]["executive"]["observations"]
            if q["channel"].startswith("hardware-tracking:")
        )
        reading["measured_at"] = 0
    elif change == "remote-hours":
        next(row for row in s if row["remote_hours"])["remote_hours"] = 0
    elif change == "module-count":
        next(row for row in s if row["hardware_modules_used"])["hardware_modules_used"] = {}
    elif change == "false-acceptance":
        q = next(
            q for q in s[-1]["state"]["executive"]["orders"] if q["action"] == "remote-release"
        )
        q["verified_at"] = 35
    else:
        e = next(e for row in s for e in row["support_effects"] if e["kind"] == "retrieve")
        e["location"]["progress"] = 0.99
    a = audit(r)
    assert not a["passed"]
    assert any(
        not q["passed"] and q["check"].startswith(("support.", "hardware.")) for q in a["checks"]
    )
