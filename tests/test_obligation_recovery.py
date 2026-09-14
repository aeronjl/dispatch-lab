"""Regression: one increment's appointment must not expire the full recovery."""

import copy
from dataclasses import replace

import pytest
from test_joint_recovery import scheduled
from test_recovery_loop import receipt

from methane.config import Config, Plant, Sensors
from methane.physics import State
from methane.recovery import OBLIGATION_VERSION, RecoveryPolicy
from methane.sensing import Diagnosis
from methane.services.obligation_recovery import Scheduler, remaining_tests


def begin(s, hour, capacity=218.4, **kwargs):
    p = Plant()
    return s.begin(
        p,
        Sensors(noise_fraction=0),
        Diagnosis(capacity),
        hour=hour,
        state=State.initial(p, 20),
        forecast=kwargs.pop("forecast", {"source": {"id": "original"}, "pv_kw": [500] * 24}),
        costs=Config().costs,
        seconds=0.1,
        **kwargs,
    )


def scheduler(wait=24):
    return Scheduler(
        RecoveryPolicy(version=OBLIGATION_VERSION, maximum_wait_hours=wait, retry_after_hours=1)
    )


def test_saved_failure_needs_six_increments_not_one_appointment():
    p, sensors = Plant(), Sensors()
    r = remaining_tests(p, sensors, Diagnosis(218.4), consecutive=1)
    assert r["targets_kw"] == pytest.approx([263.4, 308.4, 353.4, 398.4, 443.4, 450])
    assert r["increases_remaining"] == 6 and r["minimum_informative_intervals"] == 11
    s = scheduler()
    request = begin(s, 20)
    out = s.finish(scheduled(request, 20))
    assert out["test_appointment"]["end_hour"] == 22
    assert out["recovery_obligation"]["due_hour"] == 44
    for hour, capacity in [(22, 263.4), (24, 308.4), (26, 353.4), (28, 398.4), (30, 443.4)]:
        req = begin(s, hour, capacity)
        out = s.finish(scheduled(req, hour))
        assert req.due_hour == 44
        assert out["recovery_obligation"]["necessary_time_fits"]
    begin(s, 32, 450)
    assert s.finish()["status"] == "inactive"


def test_forecast_change_and_missed_appointment_never_roll_deadline():
    s = scheduler(4)
    req = begin(s, 0)
    s.finish(scheduled(req, 1))
    begin(s, 2, forecast={"source": {"id": "later"}, "pv_kw": [0] * 24})
    out = s.finish()
    assert out["due_hour"] == 4
    assert not out["recovery_obligation"]["necessary_time_fits"]
    opening = copy.deepcopy(out["deadline_openings"])
    begin(s, 4)
    assert s.finish()["status"] == "escalation-required"
    begin(s, 5)
    out = s.finish()
    assert out["status"] == "escalation-required" and out["deadline_openings"] == opening


def test_new_receipt_creates_distinct_attempt_and_preserves_original_miss():
    s = scheduler(4)
    begin(s, 0)
    s.finish()
    begin(s, 5, orders=[receipt()])
    out = s.finish()
    e = out["verification_loop"]["episodes"][0]
    assert e["due_hour"] == 9 and e["original_diagnosis_deadline"] == 4
    assert e["original_deadline_missed"]
    begin(s, 6, orders=[receipt()])
    out = s.finish()
    assert len(out["deadline_openings"]) == 2


def test_forecast_and_future_receipt_do_not_change_opening():
    a, b = scheduler(), scheduler()
    ra = begin(a, 0)
    rb = begin(b, 0, orders=[receipt(completed_hour=20)])
    assert ra.to_dict() == rb.to_dict()
    assert a.finish() == b.finish()


@pytest.mark.parametrize("fraction", [1e-6, 1e-20])
def test_excessive_or_unrepresentable_probe_sequence_fails_explicitly(fraction):
    with pytest.raises(ValueError, match="Inputs have not been adjusted"):
        remaining_tests(Plant(), Sensors(probe_fraction=fraction), Diagnosis(218.4))


@pytest.mark.parametrize("case", ["successful-procedure", "failed-procedure", "power-shortage"])
def test_executed_v5_is_independently_audited(case):
    from methane.reference import audit
    from methane.services.verification_examples import CONTROLLER, fixture, weather_for
    from methane.simulation import run

    c = fixture(case)
    c = replace(c, recovery_policy=replace(c.recovery_policy, version=OBLIGATION_VERSION))
    out = run(c, weather=weather_for(c, case), strategies=[CONTROLLER])
    assert out["status"] == "complete", out["failures"]
    checked = audit(out)
    assert checked["passed"], [x for x in checked["checks"] if not x["passed"]][:10]
