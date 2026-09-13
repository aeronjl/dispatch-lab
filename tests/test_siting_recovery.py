from datetime import timedelta

from methane.config import Config, Plant, Sensors
from methane.physics import State
from methane.recovery import RecoveryPolicy
from methane.sensing import Diagnosis
from methane.services.weather_recovery import Scheduler, opening
from methane.timebase import stamp, utc


def test_forecast_aware_deadline_uses_a_feasible_daylight_window_once():
    p = Plant(initial_soc=0)
    state = State.initial(p, 20)
    sensors = Sensors(noise_fraction=0, ambiguity_policy="retain-capacity/1")
    diagnosis = Diagnosis(100)
    f = dict(
        pv_kw=[0] * 6 + [450] * 6,
        ambient_c=[20] * 12,
        deliveries_kg=[0] * 12,
        source={
            "id": "saved-before-decision",
            "initialized_at": "2025-01-01T00:00Z",
            "available_at": "2025-01-01T00:00Z",
        },
        times=[stamp(utc("2025-01-01") + timedelta(hours=i)) for i in range(12)],
    )
    policy = RecoveryPolicy(version="scheduled-load-tests/4", maximum_wait_hours=24)
    value = opening(
        p, sensors, state, diagnosis, f, Config().costs, policy, hour=0, boundary=0, seconds=0.2
    )
    assert value["selected_start"] == 6
    assert value["due_hour"] == 10 and value["hard_deadline"] == 24
    scheduler = Scheduler(policy)
    request = scheduler.begin(
        p, sensors, diagnosis, state=state, forecast=f, costs=Config().costs, seconds=0.2, hour=0
    )
    assert request.due_hour == 10
    scheduler.finish()
    changed = {**f, "pv_kw": [0] * 12}
    scheduler.begin(
        p,
        sensors,
        diagnosis,
        state=state,
        forecast=changed,
        costs=Config().costs,
        seconds=0.2,
        hour=1,
    )
    assert scheduler.due_hour == 10
    assert len(scheduler.deadline_openings) == 1


def test_no_feasible_test_keeps_finite_cap_and_truth_is_not_an_input():
    p = Plant(initial_soc=0)
    f = dict(
        pv_kw=[0] * 12,
        ambient_c=[20] * 12,
        deliveries_kg=[0] * 12,
        source={
            "id": "night",
            "initialized_at": "2025-01-01T00:00Z",
            "available_at": "2025-01-01T00:00Z",
        },
        times=[stamp(utc("2025-01-01") + timedelta(hours=i)) for i in range(12)],
    )
    v = opening(
        p,
        Sensors(),
        State.initial(p, 20),
        Diagnosis(100),
        f,
        Config().costs,
        RecoveryPolicy(version="scheduled-load-tests/4", maximum_wait_hours=24),
        hour=0,
        boundary=0,
        seconds=0.1,
    )
    assert v["selected_start"] is None and v["due_hour"] == 24
    assert "fault" not in v and "recovery_time" not in v
