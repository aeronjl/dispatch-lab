"""Finite recovery obligations, distinct from forecast-selected load appointments.

Version 4 remains available with its original semantics. This implementation uses
the existing joint planner to locate each appointment; it never spends an extra
solve on choosing an outer deadline or infers restoration from a service receipt.
"""

import copy

from methane.recovery import OBLIGATION_VERSION
from methane.services.recovery_loop import Scheduler as Loop


def remaining_tests(plant, sensors, diagnosis, *, consecutive=0):
    """Necessary informative intervals, not a prediction of resources or success."""
    capacity = diagnosis.capacity_kw
    targets = []
    while capacity < plant.electrolyser_kw * 0.999:
        following = min(
            plant.electrolyser_kw,
            max(plant.min_kw, capacity + plant.electrolyser_kw * sensors.probe_fraction),
        )
        if following <= capacity or len(targets) >= 1000:
            raise ValueError(
                "Recovery probe schedule exceeds 1,000 increments or numerical precision; "
                "increase probe_fraction. Inputs have not been adjusted."
            )
        capacity = following
        targets.append(capacity)
    prefix = min(max(0, consecutive), sensors.confirmation_hours - 1) if targets else 0
    return dict(
        capacity_estimate_kw=diagnosis.capacity_kw,
        nameplate_kw=plant.electrolyser_kw,
        increment_kw=plant.electrolyser_kw * sensors.probe_fraction,
        confirmation_hours=sensors.confirmation_hours,
        targets_kw=targets,
        increases_remaining=len(targets),
        consecutive_prefix=prefix,
        minimum_informative_intervals=len(targets) * sensors.confirmation_hours - prefix,
        scope="Necessary successful tracking only; excludes waiting, interrupted tests and failed remedies. Not a guarantee of recovery.",
    )


class Scheduler(Loop):
    def __init__(self, policy):
        if policy.version != OBLIGATION_VERSION:
            raise ValueError("Separate appointments require recovery version 5")
        super().__init__(policy)
        self.deadline_openings = []
        self.weather_context = None

    def open_deadline(self, plant, sensors, diagnosis, hour, boundary):
        record = dict(
            version="recovery-obligation-opening/1",
            opened_at=hour,
            available_boundary=boundary,
            due_hour=boundary + self.policy.maximum_wait_hours,
            hard_deadline=boundary + self.policy.maximum_wait_hours,
            remaining=remaining_tests(plant, sensors, diagnosis),
            forecast_source=copy.deepcopy(self.weather_context.get("source")),
            scope="Finite outer obligation fixed from the eligible diagnosis or completed mission boundary. Individual appointments are selected jointly with service work and charging. Later forecasts cannot move this deadline.",
        )
        self.deadline_openings.append(record)
        return record["due_hour"]

    def begin(
        self,
        plant,
        sensors,
        diagnosis,
        *,
        state,
        forecast,
        costs,
        seconds,
        components=None,
        **kwargs,
    ):
        self.weather_context = forecast
        prefix = diagnosis.recovery_count if self.previous_probe else 0
        remaining = remaining_tests(plant, sensors, diagnosis, consecutive=prefix)
        request = super().begin(plant, sensors, diagnosis, **kwargs)
        due = self.pending.get("due_hour")
        hour = kwargs["hour"]
        self.pending.update(
            version=OBLIGATION_VERSION,
            deadline_openings=copy.deepcopy(self.deadline_openings),
            recovery_obligation=dict(
                version="recovery-obligation-progress/1",
                hour=hour,
                due_hour=due,
                remaining=remaining,
                minimum_completion_boundary=hour + remaining["minimum_informative_intervals"],
                necessary_time_fits=due is None
                or hour + remaining["minimum_informative_intervals"] <= due,
                appointment_forecast_source=copy.deepcopy(forecast.get("source")),
                scope="The deadline concerns the whole recovery episode; an appointment concerns one increment. Insufficient remaining time stays visible and does not silently extend an obligation. Operating constraints and observation checks still govern execution.",
            ),
        )
        self.weather_context = None
        return request

    def finish(self, evaluated=None):
        result = super().finish(evaluated)
        result["version"] = OBLIGATION_VERSION
        result["test_appointment"] = copy.deepcopy(result.get("commitment"))
        if result["test_appointment"]:
            result["test_appointment"]["scope"] = (
                "One forecast-selected load increment; successful measured tracking is still required. This appointment does not redefine the outer recovery deadline."
            )
        return result
