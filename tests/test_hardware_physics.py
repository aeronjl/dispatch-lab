"""Recovery permission cannot change fault physics or confer evidence of health."""

import copy
from dataclasses import replace

import pytest

from methane.config import Config, Plant, Scenario
from methane.faults import HARDWARE_MODEL, LEGACY_HARDWARE_MODEL, FaultPolicy, FaultState
from methane.field_operations import FieldOperations
from methane.reference import audit
from methane.sensing import Diagnosis
from methane.services.configuration import ServiceSystem
from methane.services.hardware_demo import execute, fixture
from methane.services.plant import PlantServices


def charging(
    recovery=False, support="logistics/1", model=HARDWARE_MODEL, cause="charger-power-loss"
):
    c = FieldOperations(
        enabled=True,
        cleaner_enabled=False,
        rover_enabled=True,
        human_fallback=False,
        reset_enabled=False,
        dock_kw=10,
        rover_battery_kwh=10,
        charging_efficiency=0.8,
    )
    o = ServiceSystem(support_model=support, equipment_recovery_enabled=recovery)
    rt = PlantServices(c, o, 7, 450, hardware_model=model)
    rt.ledger.__init__(
        [
            replace(r, initial=0) if r.resource_id == "energy:rover" else r
            for r in rt.ledger.specs.values()
        ]
    )
    d = Diagnosis(450)
    f = FaultState(Plant(), Scenario(), FaultPolicy(hardware_model=model, dock_service_fault=cause))
    rt.prepare(0, d, 10)
    original = copy.deepcopy(rt.public())
    rt.dispatch_selected((), charge_requests=(("rover", 10),), charge=False)
    return rt, d, f, original, rt.end(0, f, d)


@pytest.mark.parametrize(
    "recovery,support", [(False, "none"), (False, "logistics/1"), (True, "logistics/1")]
)
def test_charger_fault_rejects_identical_request_with_or_without_recovery(recovery, support):
    rt, d, _, before, row = charging(recovery, support)
    assert before["hardware"]["observations"]["dock"]["status"] == "unobserved"
    assert row["requested_service_kwh"] == 10
    assert (
        row["applied_service_kwh"]
        == row["charge_input_kwh"]
        == row["energy_after_kwh"]["rover"]
        == 0
    )
    assert row["unapplied_service_kwh"] == 10
    assert any(e["kind"] == "interrupted" for e in row["mission_events"])
    assert row["hardware_execution"]
    assert not row["hardware_modules_used"]
    assert not rt.hardware_operable("dock")
    rt.prepare(1, d, 10)
    with pytest.raises(ValueError, match="Observed dock hardware"):
        rt.propose_charge("rover", 10)
    assert "private_state" not in str(row["state"])


def test_fault_truth_does_not_change_the_prior_charge_selection():
    healthy = charging(cause="none")
    failed = charging()
    assert healthy[3] == failed[3]
    assert healthy[4]["new_missions"] == failed[4]["new_missions"]
    assert healthy[4]["charge_input_kwh"] == 10
    assert healthy[4]["energy_after_kwh"]["rover"] == 8


def test_legacy_archives_retain_explicitly_old_recovery_gating():
    current = Config().to_dict()
    old = copy.deepcopy(current)
    old["faults"].pop("hardware_model")
    parsed = Config.from_dict(old)
    assert parsed.faults.hardware_model == LEGACY_HARDWARE_MODEL
    assert parsed.to_dict() == old
    assert Config.from_dict(current).to_dict() == current
    for enabled, expected in ((False, 10), (True, 0)):
        rt, _, _, before, row = charging(enabled, model=parsed.faults.hardware_model)
        assert row["charge_input_kwh"] == expected
        assert "hardware" not in before
        assert rt.version == (
            "plant-service-contracts/7" if enabled else "plant-service-contracts/3"
        )


@pytest.fixture(scope="module")
def failed_drive():
    c = fixture("drive-power-loss")
    c = replace(c, service_system=replace(c.service_system, equipment_recovery_enabled=False))
    return execute(c)


def test_retrieval_and_a_lucky_test_do_not_repair_the_drive(failed_drive):
    rows = [r["field_operations"] for r in failed_drive["records"]["Greedy"]]
    assert failed_drive["status"] == "complete", failed_drive["failures"]
    assert any(e["kind"] == "retrieve" for r in rows for e in r["support_effects"])
    tests = [
        r
        for r in rows[-1]["state"]["executive"]["observations"]
        if r["channel"] == "robot-ready:cleaner"
    ]
    assert tests and all(r["value"] is False for r in tests)
    assert rows[-1]["state"]["robots"]["cleaner"]["status"] != "available"
    assert not any(r["hardware_modules_used"] for r in rows)
    assert rows[0]["treated_area_m2"] > 0
    assert all(r["treated_area_m2"] == 0 for r in rows[1:])
    report = audit(failed_drive)
    assert report["passed"], (
        report["failures"] or [q for q in report["checks"] if not q["passed"]][:10]
    )


def test_mobile_inspector_power_loss_is_not_exempt_from_independent_physics():
    c = fixture("drive-power-loss")
    c = replace(
        c,
        field_operations=replace(c.field_operations, cleaner_enabled=False, rover_enabled=True),
        service_system=replace(
            c.service_system, equipment_recovery_enabled=False, inspector="mobile"
        ),
        faults=replace(
            c.faults, cleaner_service_fault="none", rover_service_fault="drive-power-loss"
        ),
        scenario=replace(c.scenario, fault_start_hour=0, capacity_fraction=0.5),
    )
    result = execute(c)
    assert result["status"] == "complete", result["failures"]
    effects = [
        e
        for t in result["retrospective_truth_by_controller"]["Greedy"]
        for r in t.get("hardware_execution", [])
        for e in r["effects"]
    ]
    assert any(e.get("kind") == "hardware-command" and e["target"] == "rover" for e in effects)
    report = audit(result)
    assert report["passed"], (
        report["failures"] or [q for q in report["checks"] if not q["passed"]][:10]
    )


def test_incompatible_runtime_model_is_explicit_instead_of_silently_ignoring_faults():
    with pytest.raises(ValueError, match="enabled fractional"):
        Config(faults=FaultPolicy(dock_service_fault="charger-power-loss"))
    rt = PlantServices(FieldOperations(enabled=True), ServiceSystem(), 7, 450)
    d = Diagnosis(450)
    rt.begin(0, d, 10)
    with pytest.raises(ValueError, match="different hardware models"):
        rt.end(
            0, FaultState(Plant(), Scenario(), FaultPolicy(hardware_model=LEGACY_HARDWARE_MODEL)), d
        )


@pytest.mark.parametrize(
    "case,target",
    [("control-hold", "cleaner"), ("pump-power-loss", "portable"), ("charger-power-loss", "dock")],
)
def test_other_actuators_also_fail_without_the_recovery_workflow(case, target):
    c = fixture(case)
    c = replace(c, service_system=replace(c.service_system, equipment_recovery_enabled=False))
    result = execute(c)
    assert result["status"] == "complete", result["failures"]
    effects = [
        e
        for t in result["retrospective_truth_by_controller"]["Greedy"]
        for r in t.get("hardware_execution", [])
        for e in r["effects"]
    ]
    assert any(e.get("kind") == "hardware-command" and e["target"] == target for e in effects)
    report = audit(result)
    assert report["passed"], (
        report["failures"] or [q for q in report["checks"] if not q["passed"]][:10]
    )


def test_independent_audit_rejects_work_with_fault_even_without_failure_receipts(failed_drive):
    forged = copy.deepcopy(failed_drive)
    row = forged["records"]["Greedy"][1]["field_operations"]
    truth = forged["retrospective_truth_by_controller"]["Greedy"][1]
    truth["hardware_execution"] = []
    interrupted = next(e for e in row["mission_events"] if e["kind"] == "interrupted")
    row["mission_events"].append(
        dict(
            order_id=interrupted["order_id"],
            asset_id=interrupted["asset_id"],
            kind="interval",
            start=1,
            end=2,
            phase="perform",
            battery_kwh=0.2,
            bus_kwh=0,
        )
    )
    report = audit(forged)
    assert any(
        q["check"] == "hardware.no_work_with_failed_actuator" and not q["passed"]
        for q in report["checks"]
    )


def test_independent_audit_rejects_false_post_retrieval_readiness(failed_drive):
    forged = copy.deepcopy(failed_drive)
    for row in forged["records"]["Greedy"]:
        for reading in row["field_operations"]["state"]["executive"]["observations"]:
            if reading["channel"] == "robot-ready:cleaner":
                reading["value"] = True
    report = audit(forged)
    assert any(
        q["check"] == "hardware.drive_ready_matches_physical_test" and not q["passed"]
        for q in report["checks"]
    )
