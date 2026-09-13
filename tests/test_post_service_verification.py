"""Independent residual arithmetic and actual unverified-service follow-through."""

import copy
from dataclasses import asdict, replace

import pytest

from methane.config import Plant, Sensors
from methane.physics import ACTION_KEYS, State
from methane.policy import Policy
from methane.services.controller import VERIFICATION_VERSION, ServicePolicy
from methane.services.coupling import identity
from methane.services.verification import Followup, assess, capture


def packet(hour=5, *, requested=300, power=225, flow_bias=0):
    plant = Plant()
    state = replace(State.initial(plant), h2_kg=10)
    flow = power / plant.specific_energy_kwh_per_kg
    return dict(
        hour=hour,
        available_at=hour + 1,
        probe=True,
        capacity_estimate_kw=225,
        estimate=asdict(state),
        request={**dict.fromkeys(ACTION_KEYS, 0), "electrolyser_kw": requested},
        current=dict(pv_kw=750, ambient_c=20, delivery_kg=0, service_kw=0, isolated=False),
        prior_inventory_kg=10,
        observations=dict(
            power_kw=power,
            h2_inventory_kg=10 + flow,
            h2_outflow_kg=0,
            hydrogen_flow_kg=flow * (1 + flow_bias),
        ),
    )


def evidence(hour=5, **kwargs):
    return assess(Plant(), Sensors(noise_fraction=0), packet(hour, **kwargs))


def order(**kwargs):
    return dict(
        id="repair-1",
        kind="module-replacement",
        incident=1,
        created_hour=0,
        completed_hour=4.25,
        status="awaiting verification",
        **kwargs,
    )


def test_residuals_match_independent_hourly_arithmetic_and_ignore_bad_flow_meter():
    result = evidence(flow_bias=0.8)
    assert result["outcome"] == "tracking shortfall"
    assert result["operands"]["tracking_fraction"] == pytest.approx((300 - 225) / 300)
    assert result["operands"]["balance_error_kg"] == pytest.approx(0)
    assert result["resource_check"]["status"] == "feasible at recorded estimate"
    assert result["operands"]["balance_hydrogen_kg"] == pytest.approx(
        225 / Plant().specific_energy_kwh_per_kg
    )


@pytest.mark.parametrize(
    "condition,outcome",
    [
        ("no probe", "insufficient evidence"),
        ("below estimate", "insufficient evidence"),
        ("isolated", "inconclusive"),
        ("power shortage", "inconclusive"),
        ("full hydrogen", "inconclusive"),
        ("disagreeing inventory", "ambiguous"),
        ("excess power", "ambiguous"),
        ("tracks", "tracking supported"),
    ],
)
def test_low_activity_limits_and_ambiguity_do_not_authorise_another_repair(condition, outcome):
    p = packet()
    if condition == "no probe":
        p["probe"] = False
    elif condition == "below estimate":
        p["request"]["electrolyser_kw"] = 225
    elif condition == "isolated":
        p["current"]["isolated"] = True
    elif condition == "power shortage":
        p["current"]["pv_kw"] = 10
    elif condition == "full hydrogen":
        p["estimate"]["h2_kg"] = Plant().h2_capacity_kg
    elif condition == "disagreeing inventory":
        p["observations"]["h2_inventory_kg"] = 10
    else:
        p = packet(power=400 if condition == "excess power" else 300)
    assert assess(Plant(), Sensors(noise_fraction=0), p)["outcome"] == outcome


def test_noise_threshold_is_explicit_and_disabled_observation_is_not_healthy():
    p = packet(power=265)
    assert assess(Plant(), Sensors(noise_fraction=0.05), p)["outcome"] == "tracking supported"
    assert assess(Plant(), Sensors(noise_fraction=0), p)["outcome"] == "tracking shortfall"
    assert assess(Plant(), Sensors(enabled=False), p)["outcome"] == "insufficient evidence"


def test_actual_receipt_and_two_distinct_eligible_tests_are_required():
    tracker = Followup(2, 8)
    first = tracker.advance(5, [order()], evidence(4))
    assert first["attempts"][0]["tests"] == []  # Fractional return at 4.25; hour 4 is too early.
    first = tracker.advance(6, [order()], evidence(5))
    repeated = tracker.advance(6, [order()], evidence(5))
    assert repeated == first
    assert first["attempts"][0]["status"] == "awaiting verification"
    second = tracker.advance(8, [order()], evidence(7))
    assert second["attempts"][0]["status"] == "follow-up supported"
    assert len(second["attempts"][0]["qualifying"]) == 2
    assert order()["status"] == "awaiting verification"


def test_probe_success_ambiguity_changed_load_and_evidence_age_reset_the_sequence():
    for mode in ("tracks", "ambiguous", "different load", "old"):
        tracker = Followup(2, 3)
        tracker.advance(6, [order()], evidence(5))
        p = packet(
            7 if mode != "old" else 10,
            requested=350 if mode == "different load" else 300,
            power=300 if mode == "tracks" else 225,
        )
        if mode == "ambiguous":
            p["observations"]["h2_inventory_kg"] = 10
        result = tracker.advance(
            p["available_at"], [order()], assess(Plant(), Sensors(noise_fraction=0), p)
        )
        assert result["attempts"][0]["status"] == "awaiting verification"


def test_future_conflicting_and_modified_evidence_is_rejected():
    tracker = Followup(2, 8)
    with pytest.raises(ValueError, match="becoming available"):
        tracker.advance(5, [order()], evidence(5))
    tracker.advance(6, [order()], evidence(5))
    with pytest.raises(ValueError, match="Conflicting"):
        tracker.advance(6, [order()], evidence(5, power=300))
    altered = evidence(6)
    altered["outcome"] = "tracking supported"
    with pytest.raises(ValueError, match="integrity"):
        tracker.advance(7, [order()], altered)
    with pytest.raises(ValueError, match="backwards"):
        tracker.advance(5, [order()])


def test_a_new_attempt_cannot_make_the_previous_failed_tests_a_success():
    tracker = Followup(2, 8)
    tracker.advance(6, [order()], evidence(5))
    tracker.advance(8, [order()], evidence(7))
    old = {**order(), "status": "verified", "verified_at_hour": 12}
    new = {
        **order(),
        "id": "repair-2",
        "created_hour": 8,
        "completed_hour": 11.25,
        "followup_of": "repair-1",
    }
    result = tracker.advance(13, [old, new], evidence(12, power=300))
    assert result["attempts"][0]["status"] == "superseded by separate attempt"
    assert len(result["attempts"][0]["qualifying"]) == 2
    assert result["attempts"][1]["tests"][0]["outcome"] == "tracking supported"
    assert result["attempts"][1]["status"] == "awaiting verification"


def test_capture_cannot_include_later_weather_applied_actions_or_private_repair_truth():
    p = packet()
    row = dict(
        decision=dict(
            hour=p["hour"],
            probe=p["probe"],
            diagnosis={"capacity_kw": 225},
            estimate=p["estimate"],
            observations={"h2_inventory_kg": 10},
            forecast=dict(
                pv_kw=[750, 0],
                ambient_c=[20, 99],
                deliveries_kg=[0, 300],
                service_kw=[0, 100],
                electrolyser_isolated=[False, True],
            ),
        ),
        observations_after=p["observations"],
        requested=p["request"],
    )
    original = capture(row)
    row.update(
        applied={"electrolyser_kw": 99},
        fault_truth={"capacity_kw": 3},
        physical_effects={"successful_repair": True},
    )
    row["decision"]["forecast"]["pv_kw"][1] = 1000
    row["decision"]["diagnosis"]["hidden_fault_cause"] = "damage"
    assert capture(row) == original == p


def config(version=VERIFICATION_VERSION, *, success=0):
    from methane.services.verification_examples import fixture

    c = fixture("successful-procedure" if success else "failed-procedure")
    return replace(c, service_policy=replace(c.service_policy, version=version))


def test_policy_roundtrip_requires_explicit_test_protocol_and_preserves_old_defaults():
    from methane.config import Config

    c = config()
    assert Config.from_dict(c.to_dict()) == c
    p = Policy(
        version="dispatch-lab/policy/3", service=c.service_policy, recovery=c.recovery_policy
    )
    assert Policy(**p.to_dict()) == p
    with pytest.raises(ValueError, match="scheduled recovery"):
        replace(c, recovery_policy=None)
    with pytest.raises(ValueError, match="scheduled recovery"):
        Policy(version="dispatch-lab/policy/3", service=c.service_policy)
    with pytest.raises(ValueError, match="enabled sensors"):
        replace(c, sensors=replace(c.sensors, enabled=False))
    assert ServicePolicy().version == "coordinated-services/1"


def test_actual_execution_repeats_a_failed_substitution_then_escalates_without_moving_deadline():
    from methane.reference import audit
    from methane.simulation import run
    from methane.weather import synthetic

    c = config()
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=750, irradiance_wm2=750, ambient_c=20)
    result = run(c, weather=weather, strategies=["MPC · methane"])
    assert result["status"] == "complete", result.get("failures")
    assert audit(result)["passed"]
    rows = result["records"]["MPC · methane"]
    decisions = [r["decision"]["service_control"] for r in rows]
    attempts = decisions[-1]["verification"]["attempts"]
    assert len(attempts) == 2, [(a["order_id"], a["status"], a["tests"]) for a in attempts]
    assert attempts[0]["status"] == "superseded by separate attempt"
    assert attempts[1]["status"] == "follow-up supported"
    obligations = [d["obligations"] for d in decisions if d["obligations"]]
    assert len({o[0]["due_hour"] for o in obligations}) == 1
    assert obligations[-1][0]["status"] == "escalation-required"
    assert len(obligations[-1][0]["attempts"]) == 2
    assert rows[-1]["diagnosis_after"]["capacity_kw"] < c.plant.electrolyser_kw
    for attempt in attempts:
        qualifying = attempt["qualifying"]
        assert len(qualifying) >= c.sensors.confirmation_hours
        assert all(t["hour"] >= attempt["completed_at"] for t in qualifying)
    # Every recorded verdict has its original operands and can be recalculated.
    for decision in decisions:
        saved = decision["verification"]["previous_test"]
        if saved is not None:
            assert (
                assess(c.plant, c.sensors, saved["inputs"]["packet"])["evidence_id"]
                == saved["evidence_id"]
            )
    from methane.costing import reprice

    original_id = identity(rows)
    reprice(result)
    assert identity(rows) == original_id


def test_runtime_followup_rechecks_current_completion_and_preserves_receipt():
    from methane.faults import FaultState
    from methane.sensing import Diagnosis
    from methane.services.plant import PlantServices

    c = config()
    rt = PlantServices(c.field_operations, c.service_system, 7, 450)
    d = Diagnosis(225, active_incident=True, incidents=1, informative=True, tracking_residual=0.5)
    fault = FaultState(c.plant, replace(c.scenario, fault_start_hour=0), c.faults)
    key = None
    for hour in range(9):
        rt.prepare(hour, d, 750)
        key = key or next(o["id"] for o in rt.orders if o["kind"] == "module-replacement")
        if hour < 8:
            rt.dispatch_selected(((key, 0),) if hour == 0 else (), charge=False)
            rt.end(hour, fault, d)
    public = rt.public()["orders"]
    original = copy.deepcopy(public[0])
    tracker = Followup(2, 8)
    tracker.advance(6, public, evidence(5))
    assessment = tracker.advance(8, public, evidence(7))
    new = rt.followup_unverified(key, assessment)
    assert new["created_hour"] == 8 and new["followup_of"] == key
    assert new["obligation_origin"] == key
    assert new["verification_evidence"]["assessment_id"] == assessment["assessment_id"]
    assert rt.public()["orders"][0] == original
    with pytest.raises(ValueError, match="successor"):
        rt.followup_unverified(key, assessment)
    altered = copy.deepcopy(assessment)
    altered["at_hour"] = 9
    with pytest.raises(ValueError, match="current observation"):
        rt.followup_unverified(key, altered)


def test_supported_tracking_is_confirmed_without_a_second_substitution():
    from methane.services.verification_examples import evaluate, render

    result, summary = evaluate("successful-procedure")
    assert result["status"] == "complete"
    assert summary["independent_check"]["passed"]
    assert summary["metrics"]["service_control"]["repair_retries"] == 0
    assert len(summary["verification"]["attempts"]) == 1
    assert summary["verification"]["attempts"][0]["status"] == "observer confirmed"
    assert summary["ending_estimate"]["capacity_kw"] == Plant().electrolyser_kw
    output = render([summary])
    assert "Recorded operation" in output and "Original model documentation" in output
    assert "not an empirical probability" in output
    assert "<script" not in output and "<link" not in output
    assert "ending inventories" in output


def test_another_execution_requires_a_new_output_directory(tmp_path, monkeypatch):
    from methane.services import verification_examples

    original = tmp_path / "summary.json"
    original.write_text("original evidence")
    monkeypatch.setattr("sys.argv", ["verification-examples", "--directory", str(tmp_path)])
    with pytest.raises(SystemExit) as exc:
        verification_examples.main()
    assert exc.value.code == 2
    assert original.read_text() == "original evidence"
