"""Mission completion, observed tests, fixed deadlines and bounded escalation."""

import copy
from dataclasses import replace

import pytest
from test_joint_recovery import scheduled
from test_post_service_verification import evidence, order, packet

from methane.config import Plant, Sensors
from methane.recovery import LOOP_VERSION, RecoveryPolicy
from methane.sensing import Diagnosis
from methane.services.recovery_loop import Scheduler
from methane.services.verification import assess


def loop(**changes):
    return Scheduler(RecoveryPolicy(version=LOOP_VERSION, maximum_wait_hours=4, **changes))


def receipt(**changes):
    return {**order(), "reported": dict(completed_at=4, available_at=4), **changes}


def begin(scheduler, hour, **kwargs):
    return scheduler.begin(Plant(), Sensors(noise_fraction=0), Diagnosis(225), hour=hour, **kwargs)


def test_whole_return_opens_separate_window_and_retains_original_miss():
    s = loop()
    begin(s, 0)
    s.finish()
    begin(s, 4, orders=[receipt()])
    missed = s.finish()
    assert missed["status"] == "escalation-required"
    assert not missed["receipts"]
    request = begin(s, 5, orders=[receipt()])
    assert request.due_hour == 9
    record = s.finish(scheduled(request, 5))
    episode = record["verification_loop"]["episodes"][0]
    assert episode["available_boundary"] == 5
    assert episode["original_diagnosis_deadline"] == 4
    assert episode["original_deadline_missed"]
    assert not record["verification_loop"]["escalation_required"]


def test_two_distinct_shortfalls_prompt_remedy_without_24_hour_pause():
    s = loop(retry_after_hours=24)
    request = begin(s, 5, orders=[receipt()])
    s.finish(scheduled(request, 5))
    request = begin(s, 6, orders=[receipt()], evidence=evidence(5, requested=270))
    assert request is not None and request.due_hour == 9
    s.finish(scheduled(request, 6))
    assert begin(s, 7, orders=[receipt()], evidence=evidence(6, requested=270)) is None
    result = s.finish()
    assert result["status"] == "awaiting-remedy"
    assert len(result["verification_loop"]["shortfall_tests"]) == 2
    assert begin(s, 8, orders=[receipt()]) is None
    assert s.finish()["status"] == "awaiting-remedy"


def test_resource_blocked_test_neither_supports_repair_nor_moves_deadline():
    s = loop()
    request = begin(s, 5, orders=[receipt()])
    s.finish(scheduled(request, 5))
    p = packet(5, requested=270)
    p["current"]["pv_kw"] = 0
    p["estimate"]["battery_kwh"] = 0
    test = assess(Plant(), Sensors(noise_fraction=0), p)
    assert test["outcome"] == "inconclusive"
    request = begin(s, 6, orders=[receipt()], evidence=test)
    result = s.finish()
    assert request.due_hour == 9
    assert result["verification_loop"]["shortfall_tests"] == []
    begin(s, 9, orders=[receipt()])
    first = s.finish()
    begin(s, 10, orders=[receipt()])
    later = s.finish()
    assert first["status"] == later["status"] == "escalation-required"
    assert first["verification_loop"]["episodes"] == later["verification_loop"]["episodes"]


def test_pending_remedy_does_not_compete_with_its_own_verification():
    s = loop()
    assert begin(s, 0, orders=[dict(id="repair", kind="reset", status="queued")]) is None
    assert s.finish()["status"] == "awaiting-procedure"


def test_later_incident_has_a_new_deadline_without_rewriting_the_old_episode():
    s = loop()
    begin(s, 0)
    s.finish()
    begin(s, 5, orders=[receipt()])
    s.finish()
    s.begin(Plant(), Sensors(), Diagnosis(450), hour=6, orders=[receipt()])
    confirmed = s.finish()
    assert confirmed["verification_loop"]["episodes"][0]["outcome"] == "observer confirmed"
    request = begin(s, 20, orders=[receipt()])
    assert request.due_hour == 24
    later = s.finish()
    assert later["verification_loop"]["original_diagnosis_deadline"] == 24
    assert later["verification_loop"]["episodes"] == confirmed["verification_loop"]["episodes"]


def test_disabling_sensing_does_not_claim_observed_recovery():
    s = loop()
    begin(s, 5, orders=[receipt()])
    s.finish()
    s.begin(Plant(), Sensors(enabled=False), Diagnosis(225), hour=6, orders=[receipt()])
    result = s.finish()
    assert result["verification_loop"]["episodes"][0]["outcome"] == "sensing disabled"


def test_future_receipts_or_evidence_cannot_change_earlier_request():
    a, b = loop(), loop()
    future = receipt(completed_hour=20)
    assert begin(a, 0).to_dict() == begin(b, 0, orders=[future]).to_dict()
    original = copy.deepcopy(evidence(2))
    a.finish()
    with pytest.raises(ValueError, match="preceding eligible"):
        begin(a, 1, evidence=original)


@pytest.mark.parametrize("case", ["successful-procedure", "failed-procedure", "power-shortage"])
def test_executed_loop_keeps_physics_and_observation_audit(case, tmp_path):
    from methane.reference import audit
    from methane.services.verification_examples import CONTROLLER, fixture, weather_for
    from methane.simulation import run

    c = fixture(case)
    c = replace(c, recovery_policy=replace(c.recovery_policy, version=LOOP_VERSION))
    result = run(c, weather=weather_for(c, case), strategies=[CONTROLLER])
    assert result["status"] == "complete", result["failures"]
    checked = audit(result)
    assert checked["passed"], [x for x in checked["checks"] if not x["passed"]][:5]
    records = [r["decision"]["recovery_planning"] for r in result["records"][CONTROLLER]]
    assert all(r["version"] == LOOP_VERSION for r in records)
    assert any(r["verification_loop"]["episodes"] for r in records)
    changed = copy.deepcopy(result)
    episode = next(
        r["decision"]["recovery_planning"]["verification_loop"]["episodes"][0]
        for r in changed["records"][CONTROLLER]
        if r["decision"]["recovery_planning"]["verification_loop"]["episodes"]
    )
    episode["due_hour"] += 1
    from methane.recovery_loop_reference import audit_run

    assert any(not c["passed"] for c in audit_run(changed))
    if case == "failed-procedure":
        assert any(r["status"] == "awaiting-remedy" for r in records)
    elif case == "successful-procedure":
        assert any(r["status"] == "scheduled" for r in records)
        import json
        import subprocess
        import sys

        from methane.bundle import make, unpack

        directory = unpack(make(result, tmp_path / "recording.zip"), tmp_path / "restored")
        checked = subprocess.run(
            [sys.executable, "-I", "-S", str(directory / "check_bundle.py"), str(directory)],
            capture_output=True,
            text=True,
            check=True,
        )
        assert json.loads(checked.stdout)["reference_passed"]
