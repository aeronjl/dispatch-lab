"""Lifecycle, service causality, resource accounting and archive regression checks."""

import copy
from dataclasses import replace

import pytest

from methane.config import Config, Costs, Plant, Scenario, Sensors
from methane.costing import allocation, reprice
from methane.faults import FaultPolicy, FaultState
from methane.field_operations import FieldOperations, FieldRuntime
from methane.reference import audit as independent_audit
from methane.sensing import Diagnosis
from methane.simulation import run, what_if
from methane.weather import synthetic


@pytest.mark.parametrize("duration", [0, 1, 12])
def test_persistent_fault_ignores_duration_and_reset_cannot_repair_damage(duration):
    s = Scenario(
        fault_start_hour=3,
        fault_duration_hours=duration,
        capacity_fraction=0.5,
        flow_bias_fraction=0.4,
    )
    fault = FaultState(Plant(), s, FaultPolicy())
    assert not fault.truth(2)["injected_fault_active"]
    assert fault.truth(200)["capacity_kw"] == 225
    fault.service("reset", 201, True)
    assert fault.truth(202)["flow_bias_fraction"] == 0.4
    assert fault.truth(202)["capacity_kw"] == 225
    fault.service("human-service", 203, False)
    assert fault.truth(204)["capacity_kw"] == 225
    fault.service("human-service", 205, True)
    assert not fault.truth(206)["injected_fault_active"]


def test_explicit_transient_and_old_configuration_keep_exact_expiry():
    s = Scenario(fault_start_hour=3, fault_duration_hours=2, capacity_fraction=0.5)
    for lifecycle in ("transient", "legacy-timed"):
        f = FaultState(Plant(), s, FaultPolicy(lifecycle=lifecycle))
        assert f.truth(4)["injected_fault_active"]
        assert not f.truth(5)["injected_fault_active"]
    c = Config.from_dict({"scenario": vars(s)})
    assert c.faults.lifecycle == "legacy-timed" and not c.field_operations.enabled
    assert Config().faults.lifecycle == "persistent"


def test_reset_does_not_clear_a_biased_flow_channel():
    f = FaultState(
        Plant(),
        Scenario(fault_start_hour=0, capacity_fraction=0.5, flow_bias_fraction=0.4),
        FaultPolicy(capacity_cause="resettable-trip"),
    )
    assert f.inspect_panel(0)["latched"]
    f.service("reset", 0, True)
    assert f.truth(1)["capacity_kw"] == 450
    assert f.truth(1)["flow_bias_fraction"] == 0.4


def test_cleaning_delayed_effect_and_independent_energy_arithmetic():
    c = FieldOperations(
        enabled=True,
        soiling_per_day=0,
        mission_failure_probability=0,
        initial_soiling_fraction=0.1,
        cleaning_removal_fraction=0.8,
    )
    runtime = FieldRuntime(c, 7)
    fault = FaultState(Plant(), Scenario(), FaultPolicy())
    d = Diagnosis(450)
    rows = []
    for t in range(7):
        runtime.begin(t, d, 100)
        rows.append(runtime.end(t, fault, d))
    assert rows[1]["soiling_after"] == 0.1
    assert rows[2]["soiling_before"] == 0.1
    assert rows[2]["soiling_after"] == pytest.approx(0.02)
    assert rows[4]["state"]["orders"][0]["status"] == "completed"
    # 5 one-hour phases at .2 kW; grid-side charging replenishes 1/.9 kWh.
    assert sum(r["robot_use_kwh"] for r in rows) == pytest.approx(1)
    assert sum(r["charge_input_kwh"] for r in rows) == pytest.approx(1 / 0.9)
    assert rows[-1]["energy_after_kwh"]["cleaner"] == pytest.approx(2)
    assert all(a["passed"] for r in rows for a in r["audits"])


@pytest.mark.parametrize(
    "change,expected",
    [
        ({"mission_failure_probability": 1}, "failed"),
        ({"route_open": False}, "queued"),
        ({"cleaner_battery_kwh": 0.5}, "queued"),
    ],
)
def test_cleaning_failure_or_block_does_not_remove_soiling(change, expected):
    c = FieldOperations(enabled=True, soiling_per_day=0, **change)
    runtime = FieldRuntime(c, 7)
    f = FaultState(Plant(), Scenario(), FaultPolicy())
    for t in range(7):
        runtime.begin(t, Diagnosis(450), 0)
        row = runtime.end(t, f, Diagnosis(450))
    assert runtime.soiling == 0.05
    assert row["state"]["orders"][0]["status"] == expected
    assert row["charge_input_kwh"] == 0


def constant_weather(c):
    w = synthetic(c)
    for mapping in (w["truth"], w["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=650, ambient_c=20)
    return w


@pytest.fixture(scope="module")
def repaired_run():
    c = Config(
        plant=Plant(h2_capacity_kg=200),
        sensors=Sensors(noise_fraction=0),
        scenario=Scenario(
            hours=32,
            horizon_hours=6,
            solver_seconds=0.1,
            fault_start_hour=2,
            fault_duration_hours=1,
            capacity_fraction=0.5,
        ),
        field_operations=FieldOperations(
            enabled=True,
            human_lead_hours=2,
            mission_failure_probability=0,
            repair_success_probability=1,
        ),
    )
    return run(c, weather=constant_weather(c))


def test_repaired_run_balances_isolation_costs_and_no_early_trust(repaired_run):
    r = repaired_run
    assert r["status"] == "complete"
    for name, rows in r["records"].items():
        truth = r["retrospective_truth_by_controller"][name]
        repaired = [i for i, x in enumerate(truth) if x.get("service_effects")]
        assert repaired
        t = repaired[0]
        assert truth[t]["capacity_kw"] == 225
        assert truth[t + 1]["capacity_kw"] == 450
        assert rows[t]["diagnosis_after"]["capacity_kw"] < 450
        assert rows[t + 1]["decision"]["diagnosis"]["capacity_kw"] < 450
        for row in rows:
            f = row["field_operations"]
            if f["electrolyser_isolated"]:
                assert row["applied"]["electrolyser_kw"] == 0
            assert row["service_kw"] == f["charge_input_kwh"]
            assert row["pv_kw"] + row["applied"]["discharge_kw"] == pytest.approx(
                row["demand_kw"] + row["applied"]["charge_kw"] + row["curtailed_kwh"]
            )
            assert all(a["passed"] for a in row["audits"])
        m = r["metrics"][name]
        assert m["charged_incidents"] == 0
        assert m["field_operations"]["quantities"]["human_visits"] == 1
        assert m["field_operations"]["quantities"]["service_kits_used"] == 1
        assert sum(m["components"].values()) == pytest.approx(m["total_eur"])
    a = independent_audit(r)
    assert a["passed"], [c for c in a["checks"] if not c["passed"]][:8]


def test_fault_truth_and_cost_repricing_do_not_leak_into_whatif(repaired_run):
    before = copy.deepcopy(repaired_run)
    name = "Greedy"
    hour = next(
        i
        for i, r in enumerate(before["records"][name])
        if r["field_operations"]["electrolyser_isolated"]
    )
    alternative = what_if(before, name, hour, "electrolyser")
    assert alternative["alternative_plan"]["trajectory"][0]["applied"]["electrolyser_kw"] == 0
    repriced = reprice(before, replace(Costs(**before["config"]["costs"]), rover_eur=160000))
    assert repriced["controllers"][name][-1]["total_eur"] > before["metrics"][name]["total_eur"]
    assert before == repaired_run
    ledger = allocation(
        Plant(**before["config"]["plant"]),
        Costs(**before["config"]["costs"]),
        before["records"][name],
        with_lineage=True,
    )
    nodes = {n["id"]: n for n in ledger["lineage"]["nodes"]}
    assert sum(nodes[k]["value"] for k in nodes["decision_cost"]["parents"]) == pytest.approx(
        ledger["variable_and_wear_eur"]
    )


def test_no_diagnosis_means_no_magic_inspection_or_service():
    c = FieldOperations(enabled=True, cleaner_enabled=False)
    runtime = FieldRuntime(c, 7)
    fault = FaultState(Plant(), Scenario(fault_start_hour=0, capacity_fraction=0.5), FaultPolicy())
    for t in range(20):
        runtime.begin(t, Diagnosis(450, status="diagnosis disabled"), 650)
        runtime.end(t, fault, Diagnosis(450))
    assert not runtime.orders
    assert fault.truth(20)["capacity_kw"] == 225


def test_failed_human_service_consumes_resources_without_repair():
    c = FieldOperations(
        enabled=True,
        cleaner_enabled=False,
        rover_enabled=False,
        human_lead_hours=1,
        human_work_hours=1,
        repair_success_probability=0,
    )
    runtime = FieldRuntime(c, 7)
    fault = FaultState(Plant(), Scenario(fault_start_hour=0, capacity_fraction=0.5), FaultPolicy())
    d = Diagnosis(225, active_incident=True, incidents=1)
    for t in range(4):
        runtime.begin(t, d, 650)
        r = runtime.end(t, fault, d)
    assert fault.truth(100)["capacity_kw"] == 225
    assert runtime.kits == c.service_kits - 1
    assert r["state"]["orders"][0]["status"] == "awaiting verification"


def test_inspection_only_changes_information_until_reset_executes():
    c = FieldOperations(
        enabled=True,
        cleaner_enabled=False,
        mission_failure_probability=0,
        repair_success_probability=1,
    )
    rt = FieldRuntime(c, 7)
    f = FaultState(
        Plant(),
        Scenario(fault_start_hour=0, capacity_fraction=0.5),
        FaultPolicy(capacity_cause="resettable-trip"),
    )
    d = Diagnosis(225, active_incident=True, incidents=1)
    for t in range(2):
        rt.begin(t, d, 650)
        rt.end(t, f, d)
        assert f.truth(t + 1)["capacity_kw"] == 225
    assert rt.orders[-1]["kind"] == "reset" and rt.orders[-1]["created_hour"] == 2
    rt.begin(2, d, 650)
    assert rt.interval["electrolyser_isolated"]
    rt.end(2, f, d)
    assert f.truth(3)["capacity_kw"] == 450
