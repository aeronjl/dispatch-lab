"""Seeded synthetic weather, observation-only forecasts, and paired experiments."""

from dataclasses import asdict, dataclass
from math import isfinite

import numpy as np

from controllers import greedy, plan
from plant import Plant, State, step


@dataclass(frozen=True)
class Scenario:
    days: int = 3
    daylight_hours: float = 12
    weather: str = "Broken clouds"
    variability: float = 0.25
    forecast_bias: float = 0.0
    seed: int = 7
    horizon_hours: int = 24
    fault_start_hour: int = 34
    fault_duration_hours: int = 8
    fault_capacity_fraction: float = 1.0

    def __post_init__(self):
        numeric = [v for v in vars(self).values() if isinstance(v, (float, int))]
        if not all(isfinite(x) for x in numeric):
            raise ValueError("Scenario values must be finite.")
        if self.days not in (2, 3, 5, 10) or self.horizon_hours not in (6, 12, 24, 48):
            raise ValueError("Unsupported duration or forecast horizon.")
        if not 4 <= self.daylight_hours <= 20 or not 0 <= self.variability <= 0.6:
            raise ValueError("Invalid daylight or cloud variability.")
        if self.weather not in ("Clear days", "Broken clouds", "Passing front"):
            raise ValueError("Unknown weather profile.")
        if not -0.6 <= self.forecast_bias <= 0.6:
            raise ValueError("Forecast bias must be between -0.6 and 0.6.")
        if not 0 <= self.fault_capacity_fraction <= 1:
            raise ValueError("Fault capacity must be a fraction in [0, 1].")
        if self.fault_start_hour < 0 or self.fault_duration_hours < 0 or self.seed < 0:
            raise ValueError("Fault timing and seed must be nonnegative.")


@dataclass(frozen=True)
class Weather:
    clear_kw: np.ndarray
    expected_cloud: np.ndarray
    actual_kw: np.ndarray


def make_weather(plant: Plant, scenario: Scenario):
    n = scenario.days * 24
    hours = np.arange(n) + 0.5
    sunrise = 12 - scenario.daylight_hours / 2
    phase = ((hours % 24) - sunrise) / scenario.daylight_hours
    clear_kw = plant.solar_kw * np.maximum(0, np.sin(np.pi * np.clip(phase, 0, 1)))
    clear_kw[phase >= 1] = 0
    if scenario.weather == "Clear days":
        expected = np.full(n, 0.95)
    elif scenario.weather == "Passing front":
        # The broad front is in the weather forecast; sub-hour/hour cloud variation is not.
        expected = 0.87 - 0.65 * np.exp(-0.5 * ((hours - 37) / 7) ** 2)
    else:
        expected = 0.74 + 0.09 * np.sin(hours / 11)
    rng = np.random.default_rng(scenario.seed)
    residual = np.zeros(n)
    for i in range(n):
        residual[i] = (0.65 * residual[i - 1] if i else 0) + rng.normal(
            0, scenario.variability * np.sqrt(1 - 0.65**2)
        )
    realised_cloud = np.clip(expected + residual, 0.03, 1)
    return Weather(clear_kw, expected, clear_kw * realised_cloud)


def forecast_at(weather: Weather, scenario: Scenario, t: int):
    """Only the current observation corrects the known synthetic forecast template.

    No future realised samples are read. Current-hour average PV is treated as
    measured (an hourly toy abstraction); forecast error applies to later hours.
    Residual cloud persistence decays with a three-hour time constant.
    """
    end = min(t + scenario.horizon_hours, len(weather.actual_kw))
    lead = np.arange(end - t)
    correction = 0.0
    if weather.clear_kw[t] > 1e-6:
        correction = weather.actual_kw[t] / weather.clear_kw[t] - weather.expected_cloud[t]
    cloud = np.clip(
        weather.expected_cloud[t:end] * (1 + scenario.forecast_bias)
        + correction * np.exp(-lead / 3),
        0.03,
        1,
    )
    forecast = weather.clear_kw[t:end] * cloud
    forecast[0] = weather.actual_kw[t]
    return forecast


def capacity_at(plant: Plant, scenario: Scenario, t: int):
    in_fault = (
        scenario.fault_start_hour <= t < (scenario.fault_start_hour + scenario.fault_duration_hours)
    )
    fraction = scenario.fault_capacity_fraction if in_fault else 1.0
    return plant.electrolyser_kw * fraction


def summarise(rows, plant: Plant):
    dt = plant.dt_hours
    total = lambda key: float(sum(r[key] for r in rows))  # noqa: E731
    initial = plant.battery_kwh * plant.initial_soc
    return {
        "hydrogen_kg": total("h2_kg"),
        "pv_kwh": total("pv_kw") * dt,
        "productive_kwh": total("productive_kw") * dt,
        "curtailed_kwh": total("curtailed_kw") * dt,
        "startup_kwh": total("startup_kwh"),
        "battery_loss_kwh": total("battery_loss_kwh"),
        "initial_battery_kwh": initial,
        "final_battery_kwh": rows[-1]["battery_kwh"],
        "battery_change_kwh": rows[-1]["battery_kwh"] - initial,
        "battery_throughput_kwh": (total("charge_kw") + total("discharge_kw")) * dt,
        "starts": int(total("started")),
        "utilisation": total("productive_kw") / (len(rows) * plant.electrolyser_kw),
        "max_balance_error_kwh": max(abs(r["balance_residual_kwh"]) for r in rows),
        "solver_seconds": total("solve_seconds"),
        "limited_solves": sum(r["controller_status"] == "time-limited" for r in rows),
        "fallbacks": sum(r["controller_status"] == "fallback" for r in rows),
    }


def run_experiment(plant: Plant, scenario: Scenario, progress=None):
    if plant.dt_hours != 1:
        raise ValueError("This weather and experiment runner currently use one-hour intervals.")
    weather = make_weather(plant, scenario)
    records, metrics = {}, {}
    n = len(weather.actual_kw)
    for name, controller in (("Greedy", greedy), ("Forecast MPC", plan)):
        state = State(plant.battery_kwh * plant.initial_soc)
        rows = []
        for t in range(n):
            capacity = capacity_at(plant, scenario, t)
            if name == "Greedy":
                decision = controller(plant, state, float(weather.actual_kw[t]), capacity)
            else:
                decision = controller(plant, state, forecast_at(weather, scenario, t), capacity)
                if progress and t % 4 == 0:
                    progress((t + 1) / n, desc=f"Planning hour {t + 1} of {n}")
            state, row = step(
                plant, state, decision.productive_kw, float(weather.actual_kw[t]), capacity
            )
            rows.append(
                {
                    "hour": t,
                    **row,
                    "controller_status": decision.status,
                    "solve_seconds": decision.seconds,
                    "solver_gap": decision.gap,
                }
            )
        records[name] = rows
        metrics[name] = summarise(rows, plant)
    return {
        "model_version": "0.1.0",
        "plant": asdict(plant),
        "scenario": asdict(scenario),
        "records": records,
        "metrics": metrics,
    }
