"""Private service timing, independently reconciled resources and causal beliefs."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.autonomy import DEFAULT, Beliefs, SupportObservations
from methane.config import Config, Scenario
from methane.field_operations import FieldOperations
from methane.services.configuration import ServiceSystem
from methane.services.contracts import Reading
from methane.simulation import run
from methane.uncertainty import VERSION, resolve
from methane.weather import synthetic


def config(hours=12, factor=1):
    return Config(
        scenario=Scenario(hours=hours, horizon_hours=6, solver_seconds=0.05),
        field_operations=FieldOperations(
            enabled=True,
            initial_soiling_fraction=0.15,
            soiling_per_day=0,
            mission_failure_probability=0,
            rover_enabled=False,
            reset_enabled=False,
            human_fallback=False,
            cleaner_battery_kwh=10,
        ),
        service_system=ServiceSystem(inspector="none", cleaning_time_factor=factor),
    )


def spec(value=1.5, **kwargs):
    return dict(
        schema_version=VERSION,
        seed=1,
        worlds=1,
        inner_seeds=[7],
        design="factorial",
        rationale="Mechanism check, not calibration",
        autonomy=copy.deepcopy(DEFAULT),
        blocks=[
            dict(
                id="duration",
                paths=["service_system.cleaning_time_factor"],
                kind="values",
                rows=[[value]],
                visibility="hidden",
                source="test",
                rationale="test",
            )
        ],
        **kwargs,
    )


def execute(value=1.5, hours=12):
    world = resolve(spec(value), config(hours).to_dict())[0]
    assert world["status"] == "resolved", world
    actual = Config.from_dict(world["config"])
    weather = synthetic(actual)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample["pv_kw"] = 500
    r = run(actual, weather=weather, strategies=["Greedy"], uncertainty=world)
    assert r["status"] == "complete", r.get("failures")
    return r


def test_private_time_changes_completion_without_leaking_into_initial_decision():
    a, b = execute(1), execute(1.5)
    x, y = a["records"]["Greedy"], b["records"]["Greedy"]
    assert x[0]["decision"] == y[0]["decision"]
    assert x[0]["field_operations"]["decision"] == y[0]["field_operations"]["decision"]
    events = [
        e for r in y for e in r["field_operations"]["mission_events"] if e["kind"] == "interval"
    ]
    work = [e for e in events if e["phase"] == "perform" and "charge" not in e["order_id"].lower()]
    first = y[0]["field_operations"]["new_missions"][0]
    key = first["order"]["order_id"]
    durations = sum(
        Decimal(str(e["end"])) - Decimal(str(e["start"])) for e in work if e["order_id"] == key
    )
    assert durations == Decimal(3)  # 2 h recipe × private factor 1.5.
    energy = sum(Decimal(str(e["battery_kwh"])) for e in events if e["order_id"] == key)
    assert float(energy) == pytest.approx((0.5 + 3 + 0.25 + 0.5) * 0.2)
    assert all(a["passed"] for r in y for a in r["field_operations"]["audits"])
    clock = y[3]["decision"]["uncertainty_beliefs"]["durations"]["cleaning"]
    assert clock["censored_phases"] == 1
    assert clock["completed_phases"] == 0
    assert y[5]["decision"]["uncertainty_beliefs"]["durations"]["cleaning"]["completed_phases"] == 1


def test_elapsed_packets_replace_censoring_and_never_create_completed_trials():
    b = Beliefs(DEFAULT)
    row = dict(
        id="job/1",
        order_id="job",
        action="reset",
        group="repair",
        phase="perform",
        started_at=0,
        available_at=1,
        elapsed_hours=1,
        nominal_hours=1,
        completed_at=None,
        censored=True,
        interrupted=False,
    )
    for hour in (1, 2):
        r = b.update(hour, [{**row, "available_at": hour, "elapsed_hours": hour / 2}], [])
        assert r["durations"]["repair"]["censored_phases"] == 1
        assert r["durations"]["repair"]["completed_phases"] == 0
    with pytest.raises(ValueError, match="future"):
        b.update(3, [{**row, "completed_at": 4}], [])


def test_support_port_exposes_only_current_status_and_does_not_create_resources():
    original = Reading("crew-available", True, "boolean", 0, 0, "shift")
    a = SupportObservations([])
    b = SupportObservations(
        [dict(channel="crew-available", start=2, end=4, available=False, source="test")]
    )
    assert a.at(0, [original]) == b.at(0, [original])
    assert b.at(2, [replace(original, measured_at=2, available_at=2)])[0].value is False
    absent = replace(original, value=False)
    c = SupportObservations(
        [dict(channel="crew-available", start=0, end=1, available=True, source="test")]
    )
    assert c.at(0, [absent])[0].value is False


def test_unsupported_duration_is_retained_as_invalid_world():
    w = resolve(spec(3), config().to_dict())[0]
    assert w["status"] == "invalid-input"
    assert "support" in w["error"]


@pytest.mark.parametrize("inspector", ["fixed", "mobile"])
def test_uncertain_inspection_and_repair_wait_for_observed_acceptance(inspector):
    from methane.config import Plant
    from methane.faults import FaultPolicy, FaultState
    from methane.sensing import Diagnosis
    from methane.services.plant import PlantServices

    c = FieldOperations(
        enabled=True,
        cleaner_enabled=False,
        human_lead_hours=1,
        rover_battery_kwh=10,
        mission_failure_probability=0,
        repair_success_probability=1,
    )
    o = ServiceSystem(
        inspector=inspector, contact_error_probability=0, contact_unreadable_probability=0
    )
    rt = PlantServices(
        c,
        o,
        7,
        450,
        autonomy=DEFAULT,
        execution_options=replace(o, inspection_time_factor=1.5, repair_time_factor=2),
    )
    f = FaultState(
        Plant(),
        Scenario(fault_start_hour=0, capacity_fraction=0.5),
        FaultPolicy(capacity_cause="resettable-trip"),
    )
    d = Diagnosis(
        225,
        active_incident=True,
        incidents=1,
        informative=True,
        status="capacity loss",
        tracking_residual=0.5,
    )
    rows = []
    for h in range(8):
        rt.begin(h, d, 650)
        rows.append(rt.end(h, f, d))
    assert all(a["passed"] for r in rows for a in r["audits"])
    reading = next(r for r in rt.executive.observations() if r.channel == "trip-contact")
    assert reading.measured_at == (1.5 if inspector == "fixed" else 2)
    reset = [m for m in rt.executive.missions.values() if m.plan.order.action == "reset"]
    assert reset and reset[0].verified_at is None
    assert f.truth(20)["capacity_kw"] == 450


def test_new_timing_archive_keeps_original_information_for_replanning():
    from methane.reference import audit
    from methane.services.snapshot import RecordedServices

    r = execute()
    for row in r["records"]["Greedy"]:
        snap = row["field_operations"]["planning_snapshot"]
        restored = RecordedServices(snap, r["service_planning_catalogues"][snap["catalogue_id"]])
        restored.planned_demands(6)
    assert audit(r)["passed"]


def test_risk_planning_uses_shared_present_actions_and_retains_solver_outcomes():
    from datetime import UTC, datetime, timedelta

    from methane.config import Costs
    from methane.physics import State
    from methane.sensing import Diagnosis
    from methane.service_economics import ACTIVITY_VERSION, illustrative
    from methane.services.charge_control import evaluate
    from methane.services.plant import PlantServices

    c = config()
    options = replace(c.service_system, support_model="logistics/1")
    field = replace(c.field_operations, cleaner_enabled=False, initial_soiling_fraction=0)
    rt = PlantServices(field, options, 7, 450, autonomy=DEFAULT)
    rt.prepare(0, Diagnosis(450), 500)
    origin = datetime(2026, 4, 10, tzinfo=UTC)
    f = dict(
        decision_hour=0,
        times=[(origin + timedelta(hours=i)).isoformat() for i in range(6)],
        source=dict(id="test", initialized_at=origin.isoformat(), available_at=origin.isoformat()),
        pv_kw=[500] * 6,
        ambient_c=[20] * 6,
        deliveries_kg=[0] * 6,
    )
    result = evaluate(
        rt,
        c.plant,
        State.initial(c.plant, 20),
        f,
        450,
        c.costs,
        [],
        service_prices=illustrative(Costs(), version=ACTIVITY_VERSION),
        joint_work=True,
        seconds=5,
    )
    assert result["state"] == "feasible", result
    out = result["uncertainty_planning"]["outcome"]
    assert len(out["branches"]) == 6
    first = out["branches"][0]["requested_actions"][0]
    for branch in out["branches"]:
        assert branch["requested_actions"][0] == pytest.approx(first)
    assert out["shared_action_equalities"] > 0
    assert result["current_requests"] == []


def test_optical_uncertainty_run_uses_monitor_estimates_and_actual_coverage():
    from methane.config import Costs
    from methane.pv import dc_power
    from methane.reference import audit
    from methane.service_economics import ACTIVITY_VERSION, illustrative
    from methane.services.controller import ServicePolicy

    c = config(hours=8)
    c = replace(
        c,
        scenario=replace(c.scenario, solver_seconds=1),
        service_system=replace(
            c.service_system,
            support_model="logistics/1",
            cleaning_model="section-optical/1",
            cleaning_policy="condition",
        ),
        service_economics=illustrative(Costs(), version=ACTIVITY_VERSION),
        service_policy=ServicePolicy(maximum_candidates=2, comparison_seconds=3),
    )
    s = spec()
    s["autonomy"].update(mode="adaptive", surface_absolute_error=0.002)
    world = resolve(s, c.to_dict())[0]
    actual = Config.from_dict(world["config"])
    w = synthetic(actual)
    for mapping in (w["truth"], w["template"]):
        for sample in mapping.values():
            sample.update(
                irradiance_wm2=700,
                ambient_c=20,
                pv_kw=dc_power(700, 20, actual.plant, actual.weather),
            )
    result = run(actual, weather=w, strategies=["Greedy", "MPC · economics"], uncertainty=world)
    assert result["status"] == "complete", result.get("failures")
    rows = result["records"]["Greedy"]
    assert (
        rows[0]["field_operations"]["observed_surface_before"]
        != rows[0]["field_operations"]["surface_before"]
    )
    for row in rows:
        record = row["field_operations"]
        assert (
            record["planning_snapshot"]["optical"]["surface"] == record["observed_surface_before"]
        )
    assert any(r["field_operations"]["treated_area_m2"] > 0 for r in rows)
    a = audit(result)
    assert a["passed"], [x for x in a["checks"] if not x["passed"]][:12]


@pytest.mark.parametrize(
    "case", ["supplies", "interventions", "portable-transfer", "interrupted-portable"]
)
def test_first_system_shared_visits_supplies_human_work_and_interruption(case):
    from methane.reference import audit
    from methane.services.visits_demo import fixture

    c = fixture(case)
    c = replace(
        c,
        service_system=replace(
            c.service_system,
            crew_shift_start_hour=0,
            crew_shift_duration_hours=24,
            crew_hours_per_period=40,
        ),
    )
    s = dict(
        schema_version=VERSION,
        seed=9,
        worlds=1,
        inner_seeds=[7],
        design="factorial",
        rationale="Independent bounded service-system mechanism check",
        autonomy=copy.deepcopy(DEFAULT),
        blocks=[
            dict(
                id="times",
                paths=[
                    "service_system." + k + "_time_factor"
                    for k in ("travel", "cleaning", "inspection", "repair", "supply", "support")
                ],
                kind="values",
                rows=[[1.25] * 6],
                visibility="hidden",
                source="test",
                rationale="test",
            )
        ],
    )
    world = resolve(s, c.to_dict())[0]
    assert world["status"] == "resolved", world["error"]
    actual = Config.from_dict(world["config"])
    weather = synthetic(actual)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=1000, irradiance_wm2=1000, ambient_c=20)
    r = run(actual, weather=weather, strategies=["Greedy"], uncertainty=world)
    assert r["status"] == "complete", r["failures"]
    assert any(row["field_operations"]["mission_events"] for row in r["records"]["Greedy"])
    check = audit(r)
    assert check["passed"], [x for x in check["checks"] if not x["passed"]][:8]


def test_independent_uncertainty_checker_detects_changed_belief_and_future_packet():
    from methane.autonomy_reference import audit_run

    r = execute()
    assert all(c["passed"] for c in audit_run(r))
    changed = copy.deepcopy(r)
    changed["records"]["Greedy"][3]["decision"]["uncertainty_beliefs"]["durations"]["cleaning"][
        "mean_factor"
    ] += 0.2
    assert any(not c["passed"] and c["id"] == "autonomy.duration_mean" for c in audit_run(changed))
    changed = copy.deepcopy(r)
    changed["records"]["Greedy"][2]["field_operations"]["duration_observations"][0][
        "available_at"
    ] = 90
    assert any(
        not c["passed"] and c["id"] == "autonomy.interval_evidence_clock"
        for c in audit_run(changed)
    )


def test_reference_intervals_carry_ambiguity_and_censored_duration_quantiles():
    from methane.adaptation import DEFAULT as OBSERVER
    from methane.autonomy import BoundedPerformanceObserver
    from methane.services.uncertain_planning import information_histories, quantile

    observer = BoundedPerformanceObserver(OBSERVER, config().field_operations, DEFAULT, 7)
    a = observer.solar_observation(0, 100, 100)
    assert a["feasible_multiplier_interval"][0] <= 1 <= a["feasible_multiplier_interval"][1]
    b = observer.solar_observation(1, 100, 60)
    assert b["feasible_multiplier_interval"] is None
    assert "no constant" in b["model_evidence"]
    assert quantile(dict(bins=[[0.5, 2]], weights=[1]), 0.5, 1.5) == pytest.approx(1.75)
    with pytest.raises(ValueError, match="outside"):
        quantile(dict(bins=[[0.5, 2]], weights=[1]), 0.5, 2)
    histories = information_histories([dict(pv_kw=[0, 100, 100]), dict(pv_kw=[0, 50, 50])], 0.05)
    assert histories[0][:2] == histories[1][:2]
    assert histories[0][2] != histories[1][2]


def test_programme_matches_physical_inputs_and_keeps_noop_control():
    from methane.autonomy_studies import ARMS, fixture, specification
    from methane.uncertainty_studies import resolve_cases

    c = fixture()
    physical = []
    for arm in ARMS:
        s = specification(c, "slow-work", arm, 7)
        row = resolve_cases(s, c.to_dict(), "reference")[0]
        assert not row["input_error"]
        physical.append(row["config"])
    assert physical[0] == physical[1] == physical[2]
    noop = specification(c, "no-op", "risk-aware", 7)["uncertainty"]["autonomy"]
    assert noop["weather_factors"] == [1.0]
    assert all(b == [1, 1] for b in noop["duration_bounds"].values())


def test_offline_autonomy_report_has_original_operands_without_recalculation(tmp_path):
    import zipfile

    from methane.bundle import make

    r = execute(hours=6)
    p = tmp_path / "bundle.zip"
    make(r, p)
    with zipfile.ZipFile(p) as z:
        assert "checker/autonomy_reference.py" in z.namelist()
        report = z.read("autonomous-services.html").decode()
        assert "not calibrated confidence limits" in report
        assert "censored" in report and "mean_factor" in report


def test_uncertain_joint_recovery_keeps_delivery_branches_and_accepted_test():
    from test_joint_recovery import case
    from test_service_charging import runtime, service_prices

    from methane.config import Costs
    from methane.sensing import Diagnosis
    from methane.services.charge_control import Target, accept, evaluate
    from methane.services.snapshot import RecordedServices, capture

    p, state, f, _, request = case()
    f["decision_hour"] = 0
    rt, _ = runtime()
    rt.autonomy = {**copy.deepcopy(DEFAULT), "weather_factors": [1.0], "weather_weights": [1.0]}
    rt.prepare(0, Diagnosis(225), 270)
    rt.belief_record = Beliefs(rt.autonomy).update(0, [], [])
    frozen = capture(rt)
    restored = RecordedServices(frozen["snapshot"], frozen["catalogue"])
    out = evaluate(
        restored,
        p,
        state,
        f,
        225,
        Costs(),
        [Target("rover", 8, 3, "future-inspection")],
        service_prices=service_prices(),
        joint_work=True,
        recovery_request=request,
        seconds=5,
    )
    assert out["state"] == "feasible", out
    assert len(out["uncertainty_planning"]["outcome"]["branches"]) == 4
    assert out["current_requests"] == []
    assert out["recovery_planning"]["selected_start"] == 0
    assert capture(rt) == frozen  # Hypothesis calculations cannot modify the source.
    with pytest.raises(ValueError, match="stale"):
        accept(rt, out)  # A historical replan cannot be applied to a live executive.
    live = evaluate(
        rt,
        p,
        state,
        f,
        225,
        Costs(),
        [Target("rover", 8, 3, "future-inspection")],
        service_prices=service_prices(),
        joint_work=True,
        recovery_request=request,
        seconds=5,
    )
    assert live["state"] == "feasible", live
    assert accept(rt, live) == 0
    assert rt.ledger.stock["energy:rover"] == 0


def test_interruption_histories_retain_different_earlier_observations():
    from methane.services.uncertain_planning import information_histories, interruption_histories

    base = information_histories([dict(pv_kw=[0] * 6)] * 3, 0.05)
    histories = interruption_histories(
        base, [dict(stop_work_at={"robot": 1.2}), dict(stop_work_at={"robot": 3.1}), {}], 0
    )
    assert histories[0][:2] == histories[1][:2] == histories[2][:2]
    assert all(histories[0][i] != histories[1][i] for i in range(2, 6))
    assert all(histories[0][i] != histories[2][i] for i in range(2, 6))
    assert histories[1][3] == histories[2][3]
    assert histories[1][4] != histories[2][4]


def test_optical_risk_controller_runs_live_interruption_branches():
    from methane.autonomy_studies import fixture, specification
    from methane.reference import audit

    c = fixture()
    c = replace(c, scenario=replace(c.scenario, hours=8))
    world = resolve(specification(c, "reference", "risk-aware", 7)["uncertainty"], c.to_dict())[0]
    r = run(Config.from_dict(world["config"]), strategies=["MPC · economics"], uncertainty=world)
    assert r["status"] == "complete", r["failures"]
    checks = audit(r)
    assert checks["passed"], (
        checks.get("failures"),
        [x for x in checks["checks"] if not x["passed"]][:5],
    )
    evaluations = [
        candidate["evaluation"]["uncertainty_planning"]
        for row in r["records"]["MPC · economics"]
        for candidate in row["decision"]["service_control"]["candidates"]
        if candidate.get("evaluation", {}).get("uncertainty_planning")
    ]
    assert any(
        any(m.get("service_outcome") == "interrupted cleaning" for m in e.get("hypotheses", []))
        for e in evaluations
    )


def test_retrieval_drive_check_uses_execution_clock_not_reserved_upper_bound():
    from methane.reference import audit

    c = config(hours=20)
    c = replace(
        c,
        field_operations=replace(
            c.field_operations,
            human_fallback=True,
            mission_failure_probability=1,
            human_lead_hours=1,
        ),
        service_system=replace(
            c.service_system,
            support_model="logistics/1",
            crew_response_lead_hours=0,
            crew_travel_hours=0.25,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
            outcome_randomness="target-action-request/1",
        ),
    )
    u = spec(1.5)
    u["blocks"][0].update(paths=["service_system.support_time_factor"], rows=[[1.5]])
    world = resolve(u, c.to_dict())[0]
    actual = Config.from_dict(world["config"])
    weather = synthetic(actual)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample["pv_kw"] = 500
    result = run(actual, weather=weather, strategies=["Greedy"], uncertainty=world)
    assert result["status"] == "complete", result["failures"]
    checked = audit(result)
    assert any(c.get("check") == "hardware.drive_completion" for c in checked["checks"])
    assert checked["passed"], [c for c in checked["checks"] if not c["passed"]][:8]
    wrong = copy.deepcopy(result)
    for truth in wrong["retrospective_truth_by_controller"]["Greedy"]:
        for receipt in truth.get("hardware_execution", []):
            for effect in receipt["effects"]:
                if effect.get("kind") == "drive-test":
                    effect["completed_at"] += 0.125
    # If the storage shape changes, the check below must still prove a tamper was made.
    assert wrong != result
    assert not audit(wrong)["passed"]
