"""Forecast-aware opening of finite recovery windows; observations still confirm recovery."""

import copy

from methane.recovery import compare
from methane.services.recovery_loop import Scheduler as Loop

VERSION = "scheduled-load-tests/4"


def opening(
    plant,
    sensors,
    state,
    diagnosis,
    forecast,
    costs,
    policy,
    *,
    hour,
    boundary,
    seconds,
    components=None,
):
    hard = boundary + policy.maximum_wait_hours
    target = min(
        plant.electrolyser_kw,
        max(plant.min_kw, diagnosis.capacity_kw + plant.electrolyser_kw * sensors.probe_fraction),
    )
    result = None
    if target > diagnosis.capacity_kw and hour < hard:
        result = compare(
            plant,
            state,
            diagnosis,
            forecast,
            costs,
            policy,
            hour=hour,
            target_kw=target,
            required_hours=sensors.confirmation_hours,
            due_hour=hard,
            objective="methane",
            seconds=seconds,
            total_seconds=seconds,
            components=components,
            not_before_hour=max(hour, boundary),
        )
    selected = result.get("selected_start") if result else None
    # One additional confirmation-length grace period; never extend this opening later.
    due = min(hard, selected + 2 * sensors.confirmation_hours) if selected is not None else hard
    return dict(
        version="forecast-window-opening/1",
        opened_at=hour,
        available_boundary=boundary,
        hard_deadline=hard,
        due_hour=due,
        selected_start=selected,
        required_hours=sensors.confirmation_hours,
        forecast_source=copy.deepcopy(forecast.get("source")),
        forecast=copy.deepcopy(forecast),
        state_estimate=__import__("dataclasses").asdict(state),
        capacity_estimate_kw=diagnosis.capacity_kw,
        target_kw=target,
        comparison_status=result.get("status") if result else "no informative upward test",
        solver=result.get("solver") if result else None,
        scope="Deadline set once from the eligible forecast and estimated physical constraints. An unlocated/time-limited window retains the hard cap; no physical repair or recovery is inferred.",
    )


class Scheduler(Loop):
    def __init__(self, policy):
        super().__init__(policy)
        self.weather_context = None
        self.deadline_openings = []

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
        if (
            diagnosis.capacity_kw < plant.electrolyser_kw * 0.999
            and self.last_capacity is not None
            and self.last_capacity >= plant.electrolyser_kw * 0.999
        ):
            # A new observed incident gets its own finite deadline. Prior records remain frozen.
            self.original_deadline = None
            self.due_hour = None
            self.escalated = False
        self.weather_context = (state, forecast, costs, seconds, components)
        result = super().begin(plant, sensors, diagnosis, **kwargs)
        self.pending["deadline_openings"] = copy.deepcopy(self.deadline_openings)
        self.pending["version"] = VERSION
        self.weather_context = None
        return result

    def open_deadline(self, plant, sensors, diagnosis, hour, boundary):
        state, forecast, costs, seconds, components = self.weather_context
        record = opening(
            plant,
            sensors,
            state,
            diagnosis,
            forecast,
            costs,
            self.policy,
            hour=hour,
            boundary=boundary,
            seconds=seconds,
            components=components,
        )
        self.deadline_openings.append(record)
        return record["due_hour"]
