"""Requested load tests, actual observations and finite recovery opportunities."""

import copy
from dataclasses import asdict, replace

import pytest

from methane.config import Config, Costs, Plant, Scenario, Sensors
from methane.dispatch import execute
from methane.faults import FaultPolicy
from methane.field_operations import FieldOperations
from methane.physics import State
from methane.policy import Policy
from methane.recovery import RecoveryPolicy, RecoveryScheduler, compare, outcomes
from methane.sensing import Diagnosis, observe, update
from methane.services.configuration import ServiceSystem
from methane.services.scenario_planning import Branch, solve
from methane.simulation import initial_observation, run, what_if
from methane.weather import synthetic


def forecast(pv, start=0):
    return dict(
        pv_kw=list(pv),
        ambient_c=[20] * len(pv),
        deliveries_kg=[0] * len(pv),
        times=[f"2026-07-10T{i + start:02d}:00:00Z" for i in range(len(pv))],
        source=dict(
            id="recovery-teaching/1",
            initialized_at="2026-07-10T00:00:00Z",
            available_at="2026-07-10T00:00:00Z",
        ),
    )


def diagnosis(capacity=225):
    return Diagnosis(
        capacity, active_incident=True, incidents=1, status="capacity loss", informative=True
    )


def test_shared_request_can_produce_different_delivery_without_clairvoyant_action():
    p = replace(Plant(), battery_kwh=0, heater_max_kw=0)
    f = forecast([400])
    state = State.initial(p)
    branches = tuple(
        Branch.create(
            name, 0.5, f, ("same",), source="assumption:test-delivery/1", delivery_capacity_kw=[cap]
        )
        for name, cap in [("tracks", 270), ("unchanged", 225)]
    )
    r = solve(
        p,
        state,
        branches,
        225,
        Costs(),
        requested_minimum=[270],
        requested_maximum=[270],
        seconds=2,
    )
    assert r["status"] == "feasible", r["solver"]
    assert r["current_action"]["electrolyser_kw"] == pytest.approx(270)
    assert [b["actions"][0]["electrolyser_kw"] for b in r["branches"]] == pytest.approx([270, 225])
    assert all(b["requested_actions"][0] == r["current_action"] for b in r["branches"])
    for branch, capacity in zip(r["branches"], [270, 225], strict=True):
        assert branch["trajectory"][0]["h2_produced_kg"] == pytest.approx(
            capacity / p.specific_energy_kwh_per_kg
        )
        _, actual = execute(p, state, r["current_action"], 400, 20, 0, capacity, Costs())
        assert actual["applied"]["electrolyser_kw"] == pytest.approx(capacity)
        assert actual["h2_produced_kg"] == pytest.approx(branch["trajectory"][0]["h2_produced_kg"])
        assert all(a["passed"] for a in actual["audits"])


def test_subminimum_delivery_is_off_and_does_not_invent_hydrogen():
    p = replace(Plant(), battery_kwh=0, heater_max_kw=0)
    b = Branch.create(
        "unavailable",
        1,
        forecast([400]),
        ("same",),
        source="assumption:subminimum/1",
        delivery_capacity_kw=[100],
    )
    r = solve(
        p,
        State.initial(p),
        [b],
        100,
        Costs(),
        requested_minimum=[145],
        requested_maximum=[145],
        seconds=2,
    )
    assert r["status"] == "feasible"
    assert r["current_action"]["electrolyser_kw"] == pytest.approx(145)
    assert r["branches"][0]["actions"][0]["electrolyser_kw"] == pytest.approx(0)
    assert r["branches"][0]["trajectory"][0]["h2_produced_kg"] == pytest.approx(0)


def test_battery_limit_makes_the_earliest_consecutive_window_infeasible():
    p = replace(
        Plant(),
        battery_kwh=200,
        battery_c_rate=2,
        initial_soc=0,
        heater_max_kw=0,
        roundtrip_efficiency=1,
    )
    result = compare(
        p,
        State.initial(p),
        diagnosis(),
        forecast([540, 0, 540, 540]),
        Costs(),
        RecoveryPolicy(battery_reserve_fraction=0),
        hour=0,
        target_kw=270,
        required_hours=2,
        due_hour=4,
        objective="methane",
        seconds=2,
    )
    # At offset 1 there is no sunlight and the battery holds at most 200 kWh,
    # below the 270 kWh test. Only the two later sunny intervals can both track.
    assert result["status"] == "scheduled" and result["selected_start"] == 2
    assert [c["status"] for c in result["candidate_windows"]] == [
        "unresolved",
        "unresolved",
        "feasible",
    ]
    assert not result["probe_now"]
    assert result["plan"]["recovery_outcomes"]["shared_action_equalities"] == 24


def test_full_hydrogen_buffer_and_cold_reactor_preclude_the_test():
    p = replace(Plant(), initial_h2_kg=60, heater_max_kw=0)
    r = compare(
        p,
        State.initial(p),
        diagnosis(),
        forecast([600] * 4),
        Costs(),
        RecoveryPolicy(),
        hour=0,
        target_kw=270,
        required_hours=2,
        due_hour=4,
        objective="methane",
        seconds=2,
    )
    assert r["status"] == "unresolved" and r["plan"] is None
    assert len(r["candidate_windows"]) == 3


def test_only_actual_consecutive_observations_confirm_the_next_increment():
    p = replace(Plant(), heater_max_kw=0, h2_capacity_kg=200)
    sensors = Sensors(noise_fraction=0)
    scheduler = RecoveryScheduler(RecoveryPolicy(battery_reserve_fraction=0))
    d = diagnosis()
    state = State.initial(p)
    obs = initial_observation(state)
    prior_power = None
    for h in (0, 1):
        decision = scheduler.decide(
            p,
            sensors,
            state,
            d,
            forecast([600] * 4, h),
            Costs(),
            hour=h,
            objective="methane",
            seconds=2,
        )
        assert decision["probe_now"]
        assert decision["inputs"]["required_hours"] == 2 - h
        assert d.capacity_kw == 225  # Neither planning nor declaring a branch changes belief.
        requested = decision["plan"]["actions"][0]
        before = state
        state, row = execute(p, state, requested, 600, 20, 0, 450, Costs())
        next_obs = observe(p, sensors, before, row, 7, h)
        d, _, _ = update(
            p,
            sensors,
            d,
            obs,
            next_obs,
            requested["electrolyser_kw"],
            True,
            strict_probe=True,
            consecutive_probe_power=prior_power,
        )
        obs = next_obs
        prior_power = requested["electrolyser_kw"]
    assert d.capacity_kw == 270 and d.recovery_count == 0


@pytest.mark.parametrize(
    "interruption", ["not-probe", "different-load", "bad-tracking", "ambiguous"]
)
def test_strict_confirmation_rejects_interrupted_or_inconsistent_sequences(interruption):
    p = Plant()
    s = Sensors(noise_fraction=0)
    d = diagnosis()
    d.recovery_count = 1
    old = {"h2_inventory_kg": 0}
    obs = {
        "power_kw": 270,
        "hydrogen_flow_kg": 270 / 55,
        "h2_inventory_kg": 270 / 55,
        "h2_outflow_kg": 0,
    }
    probe, prior = True, 270
    if interruption == "not-probe":
        probe = False
    if interruption == "different-load":
        prior = 260
    if interruption == "bad-tracking":
        obs.update(power_kw=225, hydrogen_flow_kg=225 / 55, h2_inventory_kg=225 / 55)
    if interruption == "ambiguous":
        obs["h2_inventory_kg"] = 0
    got, _, _ = update(
        p, s, d, old, obs, 270, probe, strict_probe=True, consecutive_probe_power=prior
    )
    assert got.capacity_kw <= 225
    assert got.recovery_count <= 1


def test_failed_probe_waits_and_only_an_available_new_procedure_receipt_reopens_it():
    p = Plant()
    d = diagnosis()
    s = RecoveryScheduler(RecoveryPolicy())
    s.previous_probe = True
    s.last_capacity = 225
    args = dict(
        plant=p,
        sensors=Sensors(noise_fraction=0),
        state=State.initial(p),
        diagnosis=d,
        forecast=forecast([600] * 4, 1),
        costs=Costs(),
        hour=1,
        objective="methane",
        seconds=2,
    )
    pending = dict(
        orders=[dict(id="reset-1", kind="reset", reported=dict(completed_at=1.5, available_at=2))]
    )
    wait = s.decide(**args, service_decision=pending)
    assert wait["status"] == "waiting-for-retry" and not s.seen_receipts
    args.update(hour=2, forecast=forecast([600] * 4, 2))
    reopened = s.decide(**args, service_decision=pending)
    assert reopened["probe_now"] and reopened["receipts"][0]["order_id"] == "reset-1"
    # The receipt reports a performed procedure, without any success truth.
    assert d.capacity_kw == 225


def test_policy_opt_in_is_frozen_and_legacy_serialization_is_unchanged():
    assert Policy().to_dict() == dict(
        objective="methane", terminal_battery_value_kg_per_kwh=0, version="dispatch-lab/policy/1"
    )
    settings = {"battery_reserve_fraction": 0.2}
    p = Policy(version="dispatch-lab/policy/2", recovery=settings)
    settings["battery_reserve_fraction"] = 0.9
    assert p.recovery.battery_reserve_fraction == 0.2
    assert Policy(**p.to_dict()) == p
    with pytest.raises(ValueError, match="version-2"):
        Policy(recovery={})


def test_setup_opt_in_roundtrips_and_explicit_study_policies_take_precedence():
    assert "recovery_policy" not in Config().to_dict()
    c = Config(scenario=Scenario(hours=3, horizon_hours=6), recovery_policy={})
    assert Config.from_dict(c.to_dict()) == c
    r = run(c, strategies=["Greedy"])
    assert r["status"] == "complete"
    assert r["provenance"]["controller_policies"]["Greedy"]["recovery"] == asdict(RecoveryPolicy())
    assert all(row["decision"]["probe_policy_revision"] == 3 for row in r["records"]["Greedy"])
    explicit = run(
        c, strategies=["Greedy"], policies={"Greedy": Policy(objective="greedy").to_dict()}
    )
    assert explicit["status"] == "complete"
    assert all(
        row["decision"]["probe_policy_revision"] == 2 for row in explicit["records"]["Greedy"]
    )


def test_an_isolated_flow_sensor_does_not_veto_independent_recovery_evidence():
    p, sensors = Plant(), Sensors(noise_fraction=0)
    d = diagnosis()
    d.flow_isolated = True
    d.flow_count = 3
    prior = {"h2_inventory_kg": 0}
    for h in range(2):
        obs = dict(
            power_kw=270,
            hydrogen_flow_kg=2 * 270 / 55,
            h2_inventory_kg=(h + 1) * 270 / 55,
            h2_outflow_kg=0,
        )
        d, _, _ = update(
            p,
            sensors,
            d,
            prior,
            obs,
            270,
            True,
            strict_probe=True,
            consecutive_probe_power=270 if h else None,
        )
        prior = obs
    assert d.capacity_kw == 270
    assert d.flow_isolated and d.active_incident


def test_recovery_metrics_distinguish_physical_time_from_observation_availability():
    truth = [dict(hour=h, capacity_kw=225 if 1 <= h < 3 else 450) for h in range(6)]
    rows = [
        dict(
            hour=h,
            diagnosis_after=dict(capacity_kw=225 if 1 <= h < 4 else 450),
            decision=dict(probe=h in (3, 4)),
        )
        for h in range(6)
    ]
    got = outcomes(rows, truth, 450)
    assert got == dict(
        capacity_restored_hour=3,
        capacity_confirmed_hour=5,
        recovery_confirmation_delay_hours=2,
        recovery_probe_hours=2,
        recovery_deadline_misses=None,
        recovery_candidate_solves=None,
    )
    # The first successful interval alone is not a completed confirmation.
    partial = outcomes(rows[:4], truth[:4], 450)
    assert partial["capacity_restored_hour"] == 3
    assert partial["capacity_confirmed_hour"] is None
    assert partial["recovery_confirmation_delay_hours"] is None
    no_fault = outcomes(rows[:1], truth[:1], 450)
    assert no_fault["capacity_restored_hour"] is None
    assert no_fault["capacity_confirmed_hour"] is None
    rows[3]["decision"]["recovery_planning"] = dict(status="scheduled", candidate_windows=[{}, {}])
    rows[4]["decision"]["recovery_planning"] = dict(status="deadline-missed")
    scheduled = outcomes(rows, truth, 450)
    assert scheduled["recovery_deadline_misses"] == 1
    assert scheduled["recovery_candidate_solves"] == 2


def test_prospective_study_holds_hardware_and_inputs_fixed_between_policies():
    from methane import studies

    spec = studies.protocol("field-recovery-tests")
    cases = studies.resolve_cases(spec, spec["reference_config"], "reference")
    assert len(cases) == 24
    for group in {case["group_id"] for case in cases}:
        pair = [case for case in cases if case["group_id"] == group]
        assert len(pair) == 2
        assert pair[0]["config"] == pair[1]["config"]
        assert pair[0]["matching_inputs_hash"] == pair[1]["matching_inputs_hash"]
        assert {Policy(**next(iter(c["policies"].values()))).version for c in pair} == {
            "dispatch-lab/policy/1",
            "dispatch-lab/policy/2",
        }
        for case in pair:
            assert case["config"]["service_system"]["inspector"] == "fixed"
            assert not case["config"]["field_operations"]["human_fallback"]
    variants = spec["tiers"]["sensitivity"]["variants"]
    assert {v["id"] for v in variants} == {
        "reference",
        "small-plant",
        "small-battery",
        "noisy-sensors",
    }


@pytest.fixture(scope="module")
def recovered_run():
    c = Config(
        plant=Plant(h2_capacity_kg=200),
        sensors=Sensors(noise_fraction=0, probe_fraction=0.25),
        scenario=Scenario(
            hours=20,
            horizon_hours=6,
            solver_seconds=0.15,
            fault_start_hour=2,
            capacity_fraction=0.5,
        ),
        faults=FaultPolicy(capacity_cause="resettable-trip"),
        field_operations=FieldOperations(
            enabled=True,
            cleaner_enabled=False,
            human_fallback=False,
            initial_soiling_fraction=0,
            soiling_per_day=0,
            mission_failure_probability=0,
            repair_success_probability=1,
        ),
        service_system=ServiceSystem(
            inspector="fixed",
            support_model="logistics/1",
            contact_error_probability=0,
            contact_unreadable_probability=0,
        ),
    )
    w = synthetic(c)
    for mapping in (w["truth"], w["template"]):
        for v in mapping.values():
            v.update(pv_kw=650, ambient_c=20)
    policies = {
        "Scheduled tests": Policy(
            objective="greedy",
            version="dispatch-lab/policy/2",
            recovery=asdict(RecoveryPolicy(battery_reserve_fraction=0)),
        ).to_dict()
    }
    return run(c, weather=w, strategies=list(policies), policies=policies)


def test_real_run_records_tests_and_confirms_recovery_without_repair_truth(recovered_run):
    r = recovered_run
    assert r["status"] == "complete", r["failures"]
    rows = r["records"]["Scheduled tests"]
    truth = r["retrospective_truth_by_controller"]["Scheduled tests"]
    reset = next(t["hour"] for t in truth if t.get("service_effects"))
    confirmed = next(
        row["hour"]
        for row in rows
        if row["diagnosis_after"]["capacity_kw"] >= 449.99 and row["hour"] > reset
    )
    assert confirmed > reset
    assert any(row["decision"]["recovery_planning"]["receipts"] for row in rows)
    assert any(row["decision"]["probe"] for row in rows)
    assert all(a["passed"] for row in rows for a in row["audits"])
    assert all(
        row["decision"]["controller_policy"]["version"] == "dispatch-lab/policy/2" for row in rows
    )
    from methane.reference import audit

    independent = audit(r)
    assert independent["passed"], [x for x in independent["checks"] if not x["passed"]][:6]


def test_independent_checker_rejects_fabricated_early_confirmation(recovered_run):
    from methane.reference import audit

    broken = copy.deepcopy(recovered_run)
    rows = broken["records"]["Scheduled tests"]
    first = next(
        row
        for row in rows
        if row["decision"]["probe"] and row["diagnosis_after"]["recovery_count"] == 1
    )
    first["diagnosis_after"]["capacity_kw"] = 450
    got = audit(broken)
    assert not got["passed"]
    assert any(
        not c["passed"] and c["check"] == "recovery.consecutive_evidence" for c in got["checks"]
    )


def test_what_if_uses_original_test_observations_and_retains_the_source_run(recovered_run):
    before = copy.deepcopy(recovered_run)
    rows = recovered_run["records"]["Scheduled tests"]
    hour = next(row["hour"] for row in rows if row["decision"]["probe"])
    alt = what_if(recovered_run, "Scheduled tests", hour, "electrolyser")
    assert recovered_run == before
    assert "original load-test target" in alt["note"]
    assert (
        alt["alternative_plan"]["recovery_planning"]["inputs"]
        == rows[hour]["decision"]["recovery_planning"]["inputs"]
    )
    if alt["alternative_plan"]["actions"]:
        assert alt["alternative_plan"]["actions"][0]["electrolyser_kw"] == pytest.approx(0)


def test_future_weather_and_support_failure_cannot_change_earlier_tests(recovered_run):
    c = Config.from_dict(recovered_run["config"])
    c = replace(c, scenario=replace(c.scenario, hours=12, solver_seconds=2))
    policies = recovered_run["provenance"]["controller_policies"]
    weather = copy.deepcopy(recovered_run["weather"])
    changed_weather = copy.deepcopy(weather)
    for timestamp in changed_weather["times"][8:]:
        changed_weather["truth"][timestamp].update(pv_kw=0, ambient_c=5)
    changed_config = replace(
        c,
        faults=replace(
            c.faults, service_fault_start_hour=8, dock_service_fault="charger-power-loss"
        ),
    )
    original = run(c, weather=weather, strategies=list(policies), policies=policies)
    changed = run(
        changed_config, weather=changed_weather, strategies=list(policies), policies=policies
    )
    assert original["status"] == changed["status"] == "complete"
    left, right = original["records"]["Scheduled tests"], changed["records"]["Scheduled tests"]
    assert any(row["decision"]["probe"] for row in left[:8])
    for a, b in zip(left[:8], right[:8], strict=True):
        assert a["requested"] == pytest.approx(b["requested"], abs=1e-6)
        assert a["diagnosis_after"] == pytest.approx(b["diagnosis_after"], abs=1e-6)
        assert a["decision"]["forecast"] == b["decision"]["forecast"]
        for key in ("probe", "probe_power_kw", "probe_policy_revision"):
            assert a["decision"].get(key) == b["decision"].get(key)
        for key in ("status", "selected_start", "inputs", "receipts"):
            assert a["decision"]["recovery_planning"].get(key) == b["decision"][
                "recovery_planning"
            ].get(key)
