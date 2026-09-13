"""Coupled service checks: independent arithmetic and causal recovery boundaries."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Config, Costs, Plant, Scenario, Sensors
from methane.costing import reprice
from methane.faults import FaultPolicy, FaultState
from methane.field_operations import FieldOperations
from methane.reference import audit
from methane.sensing import Diagnosis
from methane.services.configuration import ServiceSystem
from methane.services.plant import PlantServices
from methane.simulation import run
from methane.weather import synthetic


def fixture(inspector="mobile", **options):
    c = FieldOperations(
        enabled=True,
        cleaner_enabled=False,
        human_lead_hours=1,
        mission_failure_probability=0,
        repair_success_probability=1,
    )
    o = ServiceSystem(
        inspector=inspector,
        contact_error_probability=0,
        contact_unreadable_probability=0,
        **options,
    )
    return c, o


def diagnosed():
    return Diagnosis(
        225,
        active_incident=True,
        incidents=1,
        informative=True,
        status="capacity loss",
        tracking_residual=0.5,
    )


def fault(cause="equipment-damage", bias=0):
    return FaultState(
        Plant(),
        Scenario(fault_start_hour=0, capacity_fraction=0.5, flow_bias_fraction=bias),
        FaultPolicy(capacity_cause=cause),
    )


@pytest.mark.parametrize(
    "inspector,bus,robot,report_hour", [("fixed", 0.25, 0, 1), ("mobile", 0, 0.45, 2)]
)
def test_same_request_different_adapter_power_and_observation(inspector, bus, robot, report_hour):
    c, o = fixture(inspector)
    c = replace(c, reset_enabled=False, human_fallback=False, dock_available=False)
    rt = PlantServices(c, o, 7, 450)
    f, d = fault(), diagnosed()
    records = []
    for h in range(4):
        rt.begin(h, d, 650)
        actual = rt.execute_interval(h, f)
        row = rt.end(h, f, d)
        records.append(row)
        assert actual == pytest.approx(row["fixed_service_kwh"])
        assert not row["retrospective_effects"]
        if h + 1 < report_hour:
            assert not row["state"]["executive"]["observations"]
    # Fixed: 0.2 * (1 + .25); mobile adds two half-hour journeys.
    expected_bus = Decimal(".2") * Decimal("1.25") if inspector == "fixed" else Decimal(0)
    expected_robot = Decimal(".2") * Decimal("2.25") if inspector == "mobile" else Decimal(0)
    assert (
        sum(r["applied_service_kwh"] for r in records) == pytest.approx(float(expected_bus)) == bus
    )
    assert sum(r["robot_use_kwh"] for r in records) == pytest.approx(float(expected_robot)) == robot
    reading = records[-1]["state"]["executive"]["observations"][0]
    assert reading["available_at"] == report_hour
    assert reading["value"] is False
    assert f.truth(100)["capacity_kw"] == 225


def test_effect_commit_and_verification_do_not_repair_an_already_executed_interval():
    c, o = fixture("fixed")
    rt, f = PlantServices(c, o, 7, 450), fault("resettable-trip", 0.4)
    d = diagnosed()
    rt.begin(0, d, 650)
    rt.end(0, f, d)
    # Contact measured at 1h; reset can be selected only now.
    assert rt.begin(1, d, 650) > 0
    assert rt.interval["electrolyser_isolated"]
    assert rt.execute_interval(1, f) > 0
    assert f.truth(1)["capacity_kw"] == 225  # execution port has not applied restoration
    row = rt.end(1, f, d)
    assert f.truth(2)["capacity_kw"] == 450 and f.truth(2)["flow_bias_fraction"] == 0.4
    assert row["retrospective_effects"][0]["effective_at_hour"] == 2
    assert (
        next(q for q in row["state"]["orders"] if q["kind"] == "reset")["status"]
        == "awaiting verification"
    )
    # Even an ideal diagnosis from interval [1,2) predates work completed at 1.25.
    good = Diagnosis(450, informative=True, status="tracking consistent")
    rt.executive.reconcile_verification(rt.context(2, good))
    assert (
        next(
            m for m in rt.executive.missions.values() if m.plan.order.action == "reset"
        ).verified_at
        is None
    )
    rt.begin(2, good, 650)
    row = rt.end(2, f, good)
    assert next(q for q in row["state"]["orders"] if q["kind"] == "reset")["verified_at_hour"] == 3


def test_specific_service_never_repairs_an_unrelated_fault():
    f = fault(bias=0.4)
    f.service("module-replacement", 0, True)
    assert f.truth(1)["capacity_kw"] == 450 and f.truth(1)["flow_bias_fraction"] == 0.4
    f = fault(bias=0.4)
    f.service("flow-calibration", 0, True)
    assert f.truth(1)["capacity_kw"] == 225 and f.truth(1)["flow_bias_fraction"] == 0


def test_charging_is_a_reserved_fixed_task_and_never_initial_credit():
    c, o = fixture()
    c = replace(c, cleaner_enabled=True, rover_enabled=False, soiling_per_day=0)
    rt, f, d = PlantServices(c, o, 3, 450), fault(), Diagnosis(450)
    rows = []
    for h in range(6):
        before = rt.energy.copy()
        requested = rt.begin(h, d, 650)
        assert rt.energy == before
        row = rt.end(h, f, d)
        rows.append(row)
        assert row["applied_service_kwh"] == pytest.approx(requested)
        assert all(a["passed"] for a in row["audits"])
    # 0.5 out + 2 work + .25 verification + .5 return = 3.25h @ .2kW.
    use = Decimal("3.25") * Decimal(".2")
    assert sum(r["robot_use_kwh"] for r in rows) == pytest.approx(float(use))
    assert sum(r["charge_input_kwh"] for r in rows) == pytest.approx(float(use / Decimal(".9")))
    assert rt.energy["cleaner"] == pytest.approx(2)
    charges = [
        m for m in rt.executive.missions.values() if m.plan.order.action.startswith("charge-")
    ]
    assert charges[0].plan.starting_at >= 4  # Cannot reserve robot still returning at 3.25h.
    assert rows[1]["soiling_after"] == 0.05
    assert rows[2]["soiling_after"] == pytest.approx(0.005)


def test_supply_loss_interrupts_fixed_read_without_unmetered_load_or_reset():
    c, o = fixture("fixed")
    c = replace(c, inspection_hours=2)
    rt, f, d = PlantServices(c, o, 3, 450), fault("resettable-trip"), diagnosed()
    rt.begin(0, d, 650)
    rt.end(0, f, d)
    assert rt.begin(1, d, 0) == 0
    assert rt.execute_interval(1, f) == 0
    row = rt.end(1, f, d)
    assert any(e["kind"] == "interrupted" for e in row["mission_events"])
    assert not row["state"]["executive"]["observations"]
    assert not any(q["kind"] == "reset" for q in row["state"]["orders"])


@pytest.mark.parametrize(
    "change,kind,reason",
    [
        ({"communications_available": False}, "reset", "communications"),
        ({"calibration_reference_available": False}, "flow-calibration", "calibration-reference"),
        ({"crew_available": False}, "flow-calibration", "crew-available"),
    ],
)
def test_missing_prerequisites_block_instead_of_implying_repair(change, kind, reason):
    c, o = fixture("fixed", **change)
    rt, f = PlantServices(c, o, 7, 450), fault("resettable-trip", 0.4)
    d = diagnosed()
    d.flow_isolated = True
    for h in range(3):
        rt.begin(h, d, 650)
        row = rt.end(h, f, d)
    q = next(q for q in row["state"]["orders"] if q["kind"] == kind)
    assert q["status"] == "queued" and reason in q["blocked"]
    assert not any(e["kind"] == kind for e in row["retrospective_effects"])


def test_unreadable_contact_is_unavailable_and_never_authorizes_reset():
    c, o = fixture("fixed")
    o = replace(o, contact_unreadable_probability=1)
    rt, f, d = PlantServices(c, o, 7, 450), fault("resettable-trip"), diagnosed()
    rt.begin(0, d, 650)
    first = rt.end(0, f, d)
    reading = first["state"]["executive"]["observations"][0]
    assert reading["value"] is None and reading["quality"] == "unavailable"
    rt.begin(1, d, 650)
    assert not any(q["kind"] == "reset" for q in rt.orders)


def test_scheduler_and_prior_readings_are_invariant_to_future_or_hidden_faults():
    c, o = fixture("fixed")
    a, b = [PlantServices(c, o, 7, 450) for _ in range(2)]
    d = diagnosed()
    a.begin(0, d, 650)
    b.begin(0, d, 650)
    assert a.interval["decision"] == b.interval["decision"]
    changed = FaultState(
        Plant(), Scenario(fault_start_hour=100, capacity_fraction=0.1), FaultPolicy()
    )
    a.end(0, fault(), d)
    b.end(0, changed, d)
    # Both contacts are unlatched: damage severity is not visible to the reader.
    assert a.public() == b.public()
    assert "capacity_fault_active" not in str(a.public())


@pytest.fixture(scope="module")
def coupled_run():
    c, o = fixture("fixed")
    config = Config(
        plant=Plant(h2_capacity_kg=200),
        field_operations=c,
        service_system=o,
        scenario=Scenario(
            hours=28,
            horizon_hours=6,
            solver_seconds=0.05,
            fault_start_hour=2,
            capacity_fraction=0.5,
            flow_bias_fraction=0.4,
        ),
        sensors=Sensors(noise_fraction=0),
    )
    weather = synthetic(config)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=650, ambient_c=20)
    return run(config, weather=weather, strategies=["Greedy", "MPC · methane"])


def test_coupled_accounting_repricing_isolation_and_backlog(coupled_run):
    r = coupled_run
    assert r["status"] == "complete", r["failures"]
    report = audit(r)
    assert report["passed"], [c for c in report["checks"] if not c["passed"]][:6]
    before = copy.deepcopy(r)
    costs = Costs(**r["config"]["costs"])
    repriced = reprice(r, replace(costs, fixed_reader_eur=6000, calibration_kit_eur=200))
    assert r == before
    for name, rows in r["records"].items():
        assert repriced["controllers"][name][-1]["total_eur"] > r["metrics"][name]["total_eur"]
        kinds = {o["kind"] for o in rows[-1]["field_operations"]["state"]["orders"]}
        assert "module-replacement" in kinds and "flow-calibration" in kinds
        for row in rows:
            f = row["field_operations"]
            assert row["service_kw"] == pytest.approx(
                f["charge_input_kwh"] + f["fixed_service_kwh"]
            )
            if f["electrolyser_isolated"]:
                assert row["applied"]["electrolyser_kw"] == 0
        assert r["metrics"][name]["field_operations"]["quantities"]["calibration_kits_used"] == 1


def test_configuration_roundtrip_and_legacy_selection():
    config = Config(service_system=ServiceSystem(inspector="fixed"))
    assert Config.from_dict(config.to_dict()) == config
    assert Config.from_dict({}).service_system is None
    assert Config().service_system is None
