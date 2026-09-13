"""Joint tests, robot charging and persistent deadlines from original observations."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest
from test_service_charging import forecast, runtime, service_prices

from methane.config import Config, Costs, Plant, Sensors
from methane.physics import State
from methane.recovery import JOINT_VERSION, RecoveryPolicy, compare
from methane.sensing import Diagnosis
from methane.services.charging import Battery, Inputs
from methane.services.joint_recovery import Request, Scheduler, evaluate


def policy(**changes):
    return RecoveryPolicy(version=JOINT_VERSION, battery_reserve_fraction=0, **changes)


def case():
    p = replace(Plant(), battery_kwh=0, heater_max_kw=0, cooling_max_kw=0)
    state = replace(State.initial(p), electrolyser_on=True)
    f = forecast([270, 270, 10])
    battery = Battery("rover", 0, 10, 0.8, (True,) * 3, (0,) * 3, (0,) * 3, 8, 3)
    inputs = Inputs((battery,), (10,) * 3, (0, 3, 6, 9))
    request = Request(0, 225, 270, 2, 3, policy(), accepted_start=0)
    return p, state, f, inputs, request


def test_joint_charge_moves_out_of_accepted_test_window_and_reconciles_independently():
    p, state, f, inputs, request = case()
    original = copy.deepcopy((f, state, inputs, request))
    blocked = compare(
        p,
        state,
        Diagnosis(225),
        {**f, "service_kw": [10, 0, 0]},
        Costs(),
        request.policy,
        hour=0,
        target_kw=270,
        required_hours=2,
        due_hour=3,
        objective="methane",
        seconds=2,
        accepted_start=0,
    )
    assert blocked["plan"] is None
    result = evaluate(
        request, p, state, f, Costs(), objective="methane", seconds=2, charging_inputs=inputs
    )
    assert result["status"] == "scheduled", result
    assert result["selected_start"] == 0
    plan = result["plan"]
    assert [r["requested_kw"] for r in plan["charging"]] == pytest.approx([0, 0, 10])
    assert plan["charging"][-1]["after_kwh"] == pytest.approx(8)
    assert sum(r["charging_loss_kwh"] for r in plan["charging"]) == pytest.approx(
        float(Decimal(10) * Decimal("0.2"))
    )
    assert plan["incremental_service_decision_eur"] == 3
    branches = plan["recovery_outcomes"]["branches"]
    assert branches[0]["requested_actions"] == branches[1]["requested_actions"]
    assert branches[0]["charging_plan"] == branches[1]["charging_plan"]
    assert branches[0]["trajectory"][0]["h2_produced_kg"] == pytest.approx(270 / 55)
    assert branches[1]["trajectory"][0]["h2_produced_kg"] == pytest.approx(225 / 55)
    assert (f, state, inputs, request) == original
    assert Inputs.from_dict(inputs.to_dict()) == inputs
    assert Request.from_dict(request.to_dict()) == request


@pytest.mark.parametrize("change", ["deadline", "return-reserve", "no-solar", "unavailable"])
def test_shared_energy_limits_cannot_be_evaded_by_a_delivery_branch(change):
    p, state, f, inputs, request = case()
    b = inputs.batteries[0]
    if change == "deadline":
        b = replace(b, required_at_offset=1)
    elif change == "return-reserve":
        b = replace(b, use_kwh=(1, 0, 0), reserve_kwh=(1, 0, 0))
    elif change == "no-solar":
        f["pv_kw"][2] = 0
        b = replace(b, available=(False, False, True))
        p = replace(p, battery_kwh=800, initial_soc=1)
        state = replace(state, battery_kwh=800)
    else:
        b = replace(b, available=(True, True, False))
    result = evaluate(
        request,
        p,
        state,
        f,
        Costs(),
        objective="methane",
        seconds=2,
        charging_inputs=replace(inputs, batteries=(b,)),
    )
    assert result["plan"] is None


def scheduled(request, start):
    return dict(
        request_id=request.request_id,
        status="scheduled",
        selected_start=start,
        probe_now=start == request.hour,
        plan={"validated-fixture": True},
    )


def test_future_window_is_retained_then_consumed_by_real_consecutive_evidence():
    p, d, sensors = Plant(), Diagnosis(225), Sensors(noise_fraction=0)
    scheduler = Scheduler(policy())
    request = scheduler.begin(p, sensors, d, hour=0)
    result = scheduler.finish(scheduled(request, 2))
    assert result["commitment"]["accepted_at"] == 0
    for hour in (1, 2):
        request = scheduler.begin(p, sensors, d, hour=hour)
        assert request.accepted_start == 2 and request.due_hour == 12
        scheduler.finish(scheduled(request, 2))
    request = scheduler.begin(p, sensors, replace(d, recovery_count=1), hour=3)
    assert request.accepted_start == 3 and request.required_hours == 1
    assert scheduler.finish(scheduled(request, 3))["commitment"]["accepted_at"] == 0


def test_failed_tracking_receipts_and_unresolved_continuation_do_not_roll_deadlines():
    p, d, sensors = Plant(), Diagnosis(225), Sensors(noise_fraction=0)
    scheduler = Scheduler(policy(maximum_wait_hours=4, retry_after_hours=1))
    request = scheduler.begin(p, sensors, d, hour=0)
    scheduler.finish(scheduled(request, 0))
    assert scheduler.begin(p, sensors, d, hour=1) is None
    failed = scheduler.finish()
    assert failed["status"] == "waiting-for-retry" and failed["due_hour"] == 4
    receipt = dict(
        id="repair-1", kind="module-replacement", reported=dict(completed_at=1.5, available_at=2)
    )
    request = scheduler.begin(p, sensors, d, hour=2, orders=[receipt])
    assert request.due_hour == 4
    scheduler.finish(scheduled(request, 2))
    request = scheduler.begin(p, sensors, replace(d, recovery_count=1), hour=3, orders=[receipt])
    stopped = scheduler.finish()
    assert stopped["status"] == "unresolved" and stopped["commitment"] is None
    assert stopped["commitment_changes"] and not stopped["receipts"]
    assert scheduler.begin(p, sensors, d, hour=4) is None
    assert scheduler.finish()["status"] == "deadline-missed"
    # A genuinely new attempt follows the reported miss and retry boundary.
    request = scheduler.begin(p, sensors, d, hour=5)
    assert request.due_hour == 9


def test_stale_acceptance_and_future_receipts_are_rejected_or_unavailable():
    scheduler = Scheduler(policy())
    request = scheduler.begin(
        Plant(),
        Sensors(),
        Diagnosis(225),
        hour=0,
        orders=[dict(id="future", kind="reset", reported=dict(completed_at=1, available_at=2))],
    )
    with pytest.raises(ValueError, match="different request"):
        scheduler.finish(scheduled(replace(request, target_kw=300), 0))
    result = scheduler.finish(scheduled(request, 0))
    assert not result["receipts"]


def test_joint_candidate_is_accepted_through_real_service_port_without_early_charging():
    from methane.services.charge_control import RECOVERY_VERSION, Target, accept
    from methane.services.charge_control import evaluate as service_evaluate

    p, state, f, _, request = case()
    f["decision_hour"] = 0
    rt, _ = runtime()
    rt.prepare(0, Diagnosis(225), 270)
    result = service_evaluate(
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
        seconds=2,
    )
    assert result["state"] == "feasible", result
    assert result["implementation_id"] == RECOVERY_VERSION
    assert result["current_requests"] == []
    assert result["recovery_planning"]["selected_start"] == 0
    assert accept(rt, result) == 0
    assert rt.ledger.stock["energy:rover"] == 0


@pytest.fixture(scope="module")
def executed():
    from methane.services.verification_examples import CONTROLLER, fixture, weather_for
    from methane.simulation import run

    c = fixture("successful-procedure")
    c = replace(
        c,
        scenario=replace(c.scenario, hours=24),
        recovery_policy=replace(c.recovery_policy, version=JOINT_VERSION),
    )
    result = run(c, weather=weather_for(c, "successful-procedure"), strategies=[CONTROLLER])
    return result, CONTROLLER


def test_executed_joint_policy_records_one_consistent_plan_and_independent_checks(executed):
    from methane.reference import audit

    result, controller = executed
    assert result["status"] == "complete", result["failures"]
    rows = result["records"][controller]
    assert any(r["decision"]["probe"] for r in rows)
    for row in rows:
        d = row["decision"]
        assert d["probe_policy_revision"] == 4
        if d["recovery_planning"]["status"] == "scheduled":
            assert (
                d["recovery_planning"]["commitment"]["target_kw"]
                == d["recovery_planning"]["inputs"]["target_kw"]
            )
            assert d["service_control"]["inputs"]["recovery_request"]["hour"] == row["hour"]
            assert not d["service_control"]["fallback_used"]
    checked = audit(result)
    assert checked["passed"], [r for r in checked["checks"] if not r["passed"]][:10]
    assert any(r["check"] == "recovery.confirmation_counter" for r in checked["checks"])


def test_recorded_process_and_service_alternatives_preserve_joint_test(executed):
    from methane.services import alternatives
    from methane.simulation import what_if

    result, controller = executed
    original = copy.deepcopy(result)
    row = next(
        r
        for r in result["records"][controller]
        if r["decision"]["recovery_planning"]["status"] == "scheduled"
    )
    h = row["hour"]
    packet = alternatives.prepare(result, controller, h)
    assert (
        packet["recovery_request"]["accepted_start"]
        == row["decision"]["recovery_planning"]["selected_start"]
    )
    alt = what_if(result, controller, h, "electrolyser")
    if row["decision"]["probe"]:
        assert not alt["alternative_plan"]["actions"]
    assert result == original


def test_joint_policy_requires_a_service_controller():
    with pytest.raises(ValueError, match="Joint recovery"):
        Config(recovery_policy=policy())


def test_automatic_all_strategy_comparison_records_the_greedy_boundary_explicitly():
    from methane.services.joint_recovery_examples import fixture
    from methane.services.verification_examples import weather_for
    from methane.simulation import run

    c = fixture("normal-joint")
    c = replace(c, scenario=replace(c.scenario, hours=1))
    result = run(c, weather=weather_for(c, "successful-procedure"))
    assert result["status"] == "complete", result["failures"]
    policies = result["provenance"]["controller_policies"]
    assert policies["Greedy"]["recovery"]["version"] == "scheduled-load-tests/1"
    assert policies["MPC · methane"]["recovery"]["version"] == JOINT_VERSION
    assert "policy packages" in result["provenance"]["recovery_configuration_scope"]


def test_later_fault_schedule_cannot_change_earlier_joint_decisions():
    from methane.services.joint_recovery_examples import fixture
    from methane.services.verification_examples import CONTROLLER, weather_for
    from methane.simulation import run

    c = fixture("normal-joint")
    c = replace(c, scenario=replace(c.scenario, hours=5, fault_start_hour=7))
    later = replace(c, scenario=replace(c.scenario, fault_start_hour=8, capacity_fraction=0.3))
    a, b = [
        run(config, weather=weather_for(config, "successful-procedure"), strategies=[CONTROLLER])
        for config in (c, later)
    ]
    assert a["status"] == b["status"] == "complete"
    for x, y in zip(a["records"][CONTROLLER], b["records"][CONTROLLER], strict=True):
        assert x["requested"] == y["requested"]
        assert x["decision"]["recovery_planning"] == y["decision"]["recovery_planning"]
