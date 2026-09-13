"""Causal decision records, paired strategies and immutable same-information replans."""

import copy
import hashlib
import json
from dataclasses import asdict, replace

from methane import VERSION
from methane.audit import PhysicalAuditError
from methane.cancellation import CancelledOperation, predicate
from methane.components import assemble
from methane.config import Config, Costs
from methane.costing import allocation
from methane.dispatch import execute, plan
from methane.faults import FaultState
from methane.field_operations import ASSETS as FIELD_ASSETS
from methane.field_operations import FieldRuntime
from methane.field_operations import manifest as field_manifest
from methane.forecast import SavedForecastProvider
from methane.physics import State
from methane.provenance import digest as provenance_digest
from methane.provenance import experiment_identity, manifest, seal
from methane.sensing import Diagnosis, observe, update
from methane.weather import forecast_at, local_stamp, prepare

STRATEGIES = {"Greedy": "greedy", "MPC · methane": "methane", "MPC · economics": "economics"}
ASSETS = {
    "solar": "PLANT-01/PV-01",
    "battery": "PLANT-01/BAT-01",
    "electrolyser": "PLANT-01/ELY-01",
    "hydrogen": "PLANT-01/H2-01",
    "co2": "PLANT-01/CO2-01",
    "reactor": "PLANT-01/METH-01",
    "site": "PLANT-01",
}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()[
        :16
    ]


def estimated_state(observation, p):
    return State(
        max(0, min(p.battery_kwh, observation["battery_kwh"])),
        max(0, min(p.h2_capacity_kg, observation["h2_inventory_kg"])),
        max(0, min(p.co2_capacity_kg, observation["co2_kg"])),
        observation["temperature_c"],
        observation["electrolyser_on"],
        observation["reactor_on"],
        observation["commitment_hours"],
    )


def initial_observation(state):
    return {
        "power_kw": 0,
        "hydrogen_flow_kg": 0,
        "h2_inventory_kg": state.h2_kg,
        "h2_outflow_kg": 0,
        **{k: v for k, v in asdict(state).items() if k != "h2_kg"},
    }


def evidence(p, state, forecast, planned, diagnosis, objective):
    a = planned["actions"][0]
    rows = planned["trajectory"]
    discharge = [i for i, r in enumerate(rows) if r["applied"]["discharge_kw"] > 0.01]
    heat = [i for i, r in enumerate(rows) if r["applied"]["heater_kw"] > 0.01]
    active = []
    if state.temperature_c < p.temperature_min_c:
        active.append("Reactor must warm before methane production")
    if state.commitment_hours:
        active.append(f"{state.commitment_hours} hours of minimum run remain")
    if state.h2_kg < p.methane_min_kgph * 0.5:
        active.append("Production depends on new electrolysis or hydrogen accumulation")
    if state.co2_kg < p.methane_min_kgph * 2.75:
        active.append("CO2 is below one minimum-production interval")
    if state.battery_kwh < 1:
        active.append("Battery begins empty; discharge is unavailable")
    if diagnosis.capacity_kw < p.electrolyser_kw * 0.95:
        active.append("Electrolyser capacity estimate is below nameplate")
    first = rows[0]
    bindings = {
        key: [] for key in ("solar", "battery", "electrolyser", "hydrogen", "co2", "reactor")
    }
    for key, value, lower, upper, label in (
        ("battery", first["state"]["battery_kwh"], 0, p.battery_kwh, "Ending battery energy"),
        ("hydrogen", first["state"]["h2_kg"], 0, p.h2_capacity_kg, "Ending hydrogen inventory"),
        ("co2", first["state"]["co2_kg"], 0, p.co2_capacity_kg, "Ending CO2 inventory"),
        (
            "electrolyser",
            a["electrolyser_kw"],
            p.min_kw,
            diagnosis.capacity_kw,
            "Electrolyser power",
        ),
        ("reactor", a["methane_kg"], p.methane_min_kgph, p.methane_max_kgph, "Methane output"),
        (
            "reactor",
            first["state"]["temperature_c"],
            p.temperature_min_c,
            p.temperature_max_c,
            "Ending reactor temperature",
        ),
    ):
        if abs(value - lower) < 1e-4:
            bindings[key].append(f"{label} reaches its lower bound ({lower:g})")
        if abs(value - upper) < 1e-4:
            bindings[key].append(f"{label} reaches its upper bound ({upper:g})")
    if first["curtailed_kwh"] > 0.01:
        bindings["solar"].append(
            f"{first['curtailed_kwh']:.1f} kWh of solar is unused in the first planned interval"
        )
    return {
        "objective": objective,
        "bindings": bindings,
        "constraints": active,
        "battery": {
            "energy_kwh": state.battery_kwh,
            "capacity_kwh": p.battery_kwh,
            "power_limit_kw": p.battery_kw,
            "planned_discharge_offsets": discharge,
            "planned_deficit_kwh": sum(max(0, r["demand_kw"] - r["pv_kw"]) for r in rows),
        },
        "electrolyser": {
            "estimated_capacity_kw": diagnosis.capacity_kw,
            "minimum_kw": p.min_kw,
            "hydrogen_headroom_kg": p.h2_capacity_kg - state.h2_kg,
            "requested_kw": a["electrolyser_kw"],
            "diagnosis": asdict(diagnosis),
        },
        "hydrogen": {
            "inventory_kg": state.h2_kg,
            "capacity_kg": p.h2_capacity_kg,
            "predicted_inflow_kg": sum(r["h2_produced_kg"] for r in rows),
            "predicted_use_kg": sum(r["h2_consumed_kg"] for r in rows),
        },
        "co2": {
            "inventory_kg": state.co2_kg,
            "capacity_kg": p.co2_capacity_kg,
            "deliveries_kg": forecast["deliveries_kg"],
            "predicted_use_kg": sum(r["co2_consumed_kg"] for r in rows),
        },
        "reactor": {
            "temperature_c": state.temperature_c,
            "production_band_c": [p.temperature_min_c, p.temperature_max_c],
            "commitment_hours": state.commitment_hours,
            "planned_heating_offsets": heat,
        },
        "solar": {
            "forecast_source": forecast["source"],
            "current_error_kw": forecast["current_forecast_error_kw"],
            "predicted_curtailment_kwh": sum(r["curtailed_kwh"] for r in rows),
        },
    }


def summarise(rows, config, truth_rows=None):
    from methane.recovery import outcomes as recovery_outcomes
    from methane.services.outcomes import calculate as field_outcomes

    p, s = config.plant, config.scenario
    total = lambda k: float(sum(r[k] for r in rows))  # noqa: E731
    confirmations = [r["hour"] for r in rows if r["incident"]]
    if truth_rows is None:
        physical = FaultState(p, s, config.faults)
        truth_rows = [physical.truth(r["hour"]) for r in rows]
    active_hours = {r["hour"] for r in truth_rows if r["injected_fault_active"]}
    detections = [h for h in confirmations if h in active_hours]
    return {
        **recovery_outcomes(rows, truth_rows, p.electrolyser_kw),
        "methane_kg": sum(r["applied"]["methane_kg"] for r in rows),
        "h2_produced_kg": total("h2_produced_kg"),
        "curtailed_kwh": total("curtailed_kwh"),
        "utilisation": sum(r["applied"]["methane_kg"] for r in rows)
        / max(1, len(rows) * p.methane_max_kgph),
        "reactor_starts": total("reactor_start"),
        "electrolyser_starts": total("electrolyser_start"),
        "forced_downtime_hours": sum(r["forced_trip"] for r in rows),
        "detection_delay_hours": min(detections) + 1 - s.fault_start_hour if detections else None,
        "false_alarms": sum(h not in active_hours for h in confirmations),
        "fault_active_hours": len(active_hours),
        "field_energy_kwh": sum(r.get("service_kw", 0) for r in rows),
        "soiling_loss_kwh": sum(
            r.get("field_operations", {}).get("soiling_loss_kw", 0) for r in rows
        ),
        "service_work": rows[-1].get("field_operations", {}).get("state") if rows else None,
        "service_outcomes": field_outcomes(rows),
        "uncertain_hours": sum(
            r["diagnosis_after"]["status"]
            in (
                "ambiguous",
                "suspected anomaly",
                "insufficient evidence",
                "derated; insufficient excitation",
            )
            for r in rows
        ),
        "fallbacks": sum(r["decision"]["plan"]["solver"]["status"] == "fallback" for r in rows),
        "limited_solves": sum(
            r["decision"]["plan"]["solver"]["status"] == "time-limited" for r in rows
        ),
        "ending": rows[-1]["state"] if rows else None,
        "co2_rejected_kg": total("co2_rejected_kg"),
        "max_balance_error": max(
            (
                abs(r[k])
                for r in rows
                for k in (
                    "electrical_residual_kwh",
                    "h2_residual_kg",
                    "co2_residual_kg",
                    "reaction_mass_residual_kg",
                    "thermal_residual_kwh",
                )
            ),
            default=0,
        ),
        **allocation(p, config.costs, rows, service_economics=config.service_economics),
    }


def _run(
    config=None,
    weather=None,
    strategies=None,
    progress=None,
    cancelled=None,
    policies=None,
    uncertainty=None,
):
    execution_config = config or Config()
    c = execution_config
    if uncertainty is not None:
        from methane.uncertainty import VERSION as UNCERTAINTY_VERSION

        if (
            uncertainty.get("schema_version") != UNCERTAINTY_VERSION
            or uncertainty.get("status") != "resolved"
            or provenance_digest(uncertainty["config"]) != provenance_digest(c.to_dict())
        ):
            raise ValueError("Uncertainty world does not match the supplied physical configuration")
        from methane.uncertainty import validate_world

        validate_world(uncertainty)
        c = Config.from_dict(uncertainty["controller_config"])
    p, s = c.plant, c.scenario
    components = assemble(p, c.models)
    battery = components.battery
    physical_components = (
        assemble(execution_config.plant, execution_config.models) if uncertainty else components
    )
    measurement_channels = uncertainty.get("measurements", {}) if uncertainty else {}
    weather = weather or prepare(execution_config, progress)
    if execution_config.solar and weather.get("solar_design") != execution_config.solar:
        from methane.solar import transform_weather

        weather = transform_weather(weather, execution_config, execution_config.solar)
    from methane.adaptation import DEFAULT, Observer, required, split_weather
    from methane.pv import dc_power

    performance_active = required(uncertainty)
    if performance_active:
        weather = split_weather(weather, execution_config, c)
    provider = SavedForecastProvider.from_weather(weather)
    optical_mode = (
        c.field_operations.enabled
        and c.service_system is not None
        and c.service_system.cleaning_model == "section-optical/1"
    )
    if optical_mode:
        from methane.forecast import ForecastRequest
        from methane.services.optical import OpticalArray
        from methane.solar import source_config
        from methane.solar_model import default_design

        raw_weather = weather.get("solar_reference_weather", weather)
        raw_prediction_weather = (
            split_weather(
                raw_weather, replace(execution_config, solar=None), replace(c, solar=None)
            )
            if performance_active
            else raw_weather
        )
        raw_provider = SavedForecastProvider.from_weather(raw_prediction_weather)
        raw_config = source_config({"weather": weather, "config": execution_config.to_dict()})
    names = list(strategies or STRATEGIES)
    from methane.policy import Policy, resolve

    resolved_policies = resolve(names, policies, STRATEGIES)
    if policies is None and (c.recovery_policy is not None or c.service_policy is not None):
        resolved_policies = {
            name: Policy(
                objective=p.objective,
                version="dispatch-lab/policy/4"
                if c.investigation_policy is not None
                else "dispatch-lab/policy/3"
                if c.service_policy is not None
                else "dispatch-lab/policy/2",
                recovery=replace(c.recovery_policy, version="scheduled-load-tests/1")
                if c.recovery_policy is not None
                and c.recovery_policy.version
                in ("scheduled-load-tests/2", "scheduled-load-tests/3")
                and p.objective == "greedy"
                else c.recovery_policy,
                service=c.service_policy if p.objective != "greedy" else None,
                investigation=c.investigation_policy if p.objective != "greedy" else None,
            )
            for name, p in resolved_policies.items()
        }
    provenance = manifest(execution_config, weather, names)
    if uncertainty is not None:
        provenance["uncertainty_world"] = copy.deepcopy(uncertainty)
        provenance["controller_config"] = c.to_dict()
    if policies is not None or c.recovery_policy is not None or c.service_policy is not None:
        provenance["controller_policies"] = {
            name: policy.to_dict() for name, policy in resolved_policies.items()
        }
        if (
            policies is None
            and c.recovery_policy is not None
            and c.recovery_policy.version in ("scheduled-load-tests/2", "scheduled-load-tests/3")
        ):
            provenance["recovery_configuration_scope"] = (
                "Joint work/charging/tests apply to coordinated MPC strategies. Greedy retains the independent version-1 recovery scheduler and local service rule; this compares policy packages, not an isolated change in process objective. Exact per-controller policies are recorded."
            )
    failures = {}
    records, metrics, events, truth_by_controller = {}, {}, {}, {}
    service_planning_catalogues = {}
    decision_cost_version = digest(asdict(c.costs))
    service_cost_version = (
        provenance_digest(c.service_economics) if c.service_economics is not None else None
    )
    for k, name in enumerate(names):
        policy = resolved_policies[name]
        service_controller = None
        if policy.service is not None:
            from methane.service_economics import ACTIVITY_VERSION
            from methane.services.controller import (
                VERIFICATION_VERSION,
                VISIT_VERSION,
                ServiceController,
            )

            if not (
                c.field_operations.enabled
                and c.service_system
                and c.service_system.support_model == "logistics/1"
                and c.service_economics
                and c.service_economics.get("schema_version") == ACTIVITY_VERSION
            ):
                raise ValueError(
                    "Coordinated service policy needs finite-logistics services and activity-based prices"
                )
            if (
                policy.service.version in (VISIT_VERSION, VERIFICATION_VERSION)
                and not c.service_system.visit_bundling_enabled
            ):
                raise ValueError("Joint-visit service planning requires enabled visit bundling")
            if policy.service.version == VERIFICATION_VERSION and not c.sensors.enabled:
                raise ValueError("Post-service follow-up requires enabled sensors")
            service_controller = ServiceController(
                policy.service, investigation=policy.investigation
            )
        recovery_scheduler = None
        joint_recovery_scheduler = None
        if policy.recovery is not None:
            from methane.recovery import JOINT_VERSIONS, LOOP_VERSION, RecoveryScheduler

            if policy.recovery.version in JOINT_VERSIONS:
                from methane.services.joint_recovery import Scheduler

                if policy.recovery.version == LOOP_VERSION:
                    from methane.services.recovery_loop import Scheduler

                joint_recovery_scheduler = Scheduler(policy.recovery)
            else:
                recovery_scheduler = RecoveryScheduler(policy.recovery)
        observer = (
            Observer(
                uncertainty.get("adaptation", {**DEFAULT, "mode": "fixed"}), c.field_operations
            )
            if performance_active
            else None
        )
        if uncertainty and uncertainty.get("autonomy"):
            from methane.autonomy import BoundedPerformanceObserver, SupportObservations

            observer = BoundedPerformanceObserver(
                uncertainty.get(
                    "adaptation",
                    {
                        **DEFAULT,
                        "mode": "fixed"
                        if uncertainty["autonomy"]["mode"] == "fixed"
                        else "adaptive",
                    },
                ),
                c.field_operations,
                uncertainty["autonomy"],
                s.seed,
            )
        previous_recovery = None
        state = State.initial(
            execution_config.plant, weather["truth"][weather["times"][0]]["ambient_c"]
        )
        observation = initial_observation(state)
        if measurement_channels:
            from methane.uncertainty import measure

            observation, _ = measure(observation, measurement_channels, s.seed, -1)
        diagnosis = Diagnosis(p.electrolyser_kw)
        rows, event_list = [], []
        previous_issue = None
        physical_faults = FaultState(
            execution_config.plant, execution_config.scenario, execution_config.faults
        )
        services = FieldRuntime(c.field_operations, s.seed) if c.field_operations.enabled else None
        if services is not None and c.service_system is not None:
            from methane.services.plant import PlantServices

            services = PlantServices(
                c.field_operations,
                c.service_system,
                s.seed,
                p.electrolyser_kw,
                hardware_model=c.faults.hardware_model,
                record_planning=True,
                execution_config=execution_config.field_operations if uncertainty else None,
                execution_options=execution_config.service_system if uncertainty else None,
                autonomy=uncertainty.get("autonomy") if uncertainty else None,
                support_observations=SupportObservations(uncertainty.get("support_events", []))
                if uncertainty and uncertainty.get("autonomy")
                else None,
                optical=OpticalArray(
                    c.plant if performance_active else raw_config.plant,
                    c.weather if performance_active else raw_config.weather,
                    c.solar or default_design(p, c.weather),
                    c.field_operations,
                    c.service_system,
                )
                if optical_mode
                else None,
            )
        physical_optical = None
        if optical_mode and performance_active:
            physical_optical = OpticalArray(
                execution_config.plant,
                execution_config.weather,
                execution_config.solar
                or default_design(execution_config.plant, execution_config.weather),
                execution_config.field_operations,
                execution_config.service_system,
            )
            physical_optical.surface = services.optical.surface
        controller_truth = []
        for t in range(s.hours):
            if cancelled and cancelled():
                break
            if progress and t % 4 == 0:
                progress(
                    (k * s.hours + t) / (len(names) * s.hours),
                    desc=f"{name} · hour {t + 1}/{s.hours}",
                )
            try:
                coordinated = None
                service_planning_inputs = None
                raw_forecast = None
                if observer and services is not None and c.service_system is not None:
                    services.config = observer.field_estimate()
                    if services.optical:
                        services.optical.performance_prior = (
                            services.config.cleaning_removal_fraction
                        )
                if (
                    services is not None
                    and getattr(services, "autonomy", None)
                    and services.optical
                ):
                    from methane.services.cleaning_forecast import _surface

                    snapshot, packet = observer.monitors.surface(
                        t, services.optical.surface.snapshot()
                    )
                    services.optical.planning_surface = _surface(
                        services.optical.baseline, services.config, services.options, snapshot
                    )
                    services.surface_observation = packet
                forecast = forecast_at(weather, c, t, provider)
                if observer and not optical_mode:
                    from methane.adaptation import current_nominal
                    from methane.forecast import ForecastRequest

                    current_sample = weather["truth"][weather["times"][t]]
                    nominal_now = current_nominal(current_sample, weather["times"][t], c)
                    # The synthetic weather correction uses nominal contemporaneous conversion;
                    # conversion mismatch is separately estimated, never counted twice.
                    base_forecast = provider.horizon(
                        ForecastRequest(
                            weather["times"][t],
                            s.horizon_hours,
                            nominal_now,
                            current_sample["ambient_c"],
                            c.solar["converter_kw"] if c.solar else p.solar_kw,
                            s.forecast_bias,
                            s.seed,
                            t,
                        )
                    )
                    base_forecast["source_forecast_error_kw"] = base_forecast[
                        "current_forecast_error_kw"
                    ]
                    base_forecast["conversion_residual_kw"] = current_sample["pv_kw"] - nominal_now
                    base_forecast["current_forecast_error_kw"] += base_forecast[
                        "conversion_residual_kw"
                    ]
                    base_forecast["pv_kw"][0] = current_sample["pv_kw"]
                    base_forecast["deliveries_kg"] = forecast["deliveries_kg"]
                    observer.solar_observation(t, nominal_now, current_sample["pv_kw"])
                    forecast = observer.forecast(
                        base_forecast, c.solar["converter_kw"] if c.solar else p.solar_kw
                    )
                base_pv = forecast["pv_kw"][0]
                if services:
                    n = len(forecast["pv_kw"])
                    forecast["unserviced_pv_kw"] = list(forecast["pv_kw"])
                    if optical_mode:
                        current = raw_weather["truth"][weather["times"][t]]
                        raw_forecast = raw_provider.horizon(
                            ForecastRequest(
                                weather["times"][t],
                                s.horizon_hours,
                                dc_power(
                                    current["irradiance_wm2"], current["ambient_c"], p, c.weather
                                )
                                if observer
                                else current["pv_kw"],
                                current["ambient_c"],
                                raw_config.plant.solar_kw,
                                s.forecast_bias,
                                s.seed,
                                t,
                                include_samples=True,
                                current_irradiance_wm2=current.get("irradiance_wm2"),
                            )
                        )
                        optical_rows = services.optical.convert(raw_forecast)
                        forecast = {
                            **raw_forecast,
                            "deliveries_kg": forecast["deliveries_kg"],
                            "pv_kw": [r["dirty"]["output_kw"] for r in optical_rows],
                            "unserviced_pv_kw": [r["clean"]["output_kw"] for r in optical_rows],
                            "source_forecast_error_kw": raw_forecast["current_forecast_error_kw"],
                            "current_forecast_error_kw": services.optical.current_forecast_error(
                                raw_forecast, optical_rows[0]["dirty"]["output_kw"]
                            ),
                            "forecast_error_basis": "Available DC through the same current surface and converter; source reference error retained separately",
                            "surface_before": getattr(
                                services.optical, "planning_surface", services.optical.surface
                            ).snapshot(),
                            "surface_prediction": "Bounded removable-surface measurement plus assumed accumulation; no future cleaning assumed"
                            if services.autonomy
                            else "Current ideal surface estimate plus loose accumulation; no future cleaning assumed",
                        }
                        base_pv = forecast["unserviced_pv_kw"][0]
                        solar_record = services.optical.record(
                            optical_rows[0],
                            weather["reference"],
                            [x["id"] for x in weather.get("snapshots", [])],
                        )
                        if observer:
                            actual_forecast = copy.deepcopy(raw_forecast)
                            from methane.adaptation import nominal_sample

                            sample = nominal_sample(current, raw_config, execution_config)
                            actual_forecast["source_samples"][0] = sample
                            actual_forecast["pv_kw"][0] = sample["pv_kw"]
                            physical_row = physical_optical.convert(
                                {
                                    **actual_forecast,
                                    "times": actual_forecast["times"][:1],
                                    "source_samples": actual_forecast["source_samples"][:1],
                                    "pv_kw": actual_forecast["pv_kw"][:1],
                                    "ambient_c": actual_forecast["ambient_c"][:1],
                                }
                            )[0]
                            forecast["conversion_residual_kw"] = (
                                physical_row["dirty"]["output_kw"]
                                - optical_rows[0]["dirty"]["output_kw"]
                            )
                            forecast["current_forecast_error_kw"] += forecast[
                                "conversion_residual_kw"
                            ]
                            observer.solar_observation(
                                t,
                                optical_rows[0]["dirty"]["output_kw"],
                                physical_row["dirty"]["output_kw"],
                            )
                            forecast = observer.forecast(forecast)
                            forecast["pv_kw"][0] = physical_row["dirty"]["output_kw"]
                            # Scheduled cleaning is calculated from the same adjusted source.
                            current_factor = (
                                physical_row["dirty"]["output_kw"]
                                / optical_rows[0]["dirty"]["output_kw"]
                                if optical_rows[0]["dirty"]["output_kw"] > 1e-8
                                else 1
                            )
                            raw_forecast["pv_kw"] = [
                                v * (current_factor if i == 0 else observer.solar)
                                for i, v in enumerate(raw_forecast["pv_kw"])
                            ]
                            revised_rows = services.optical.convert(raw_forecast)
                            forecast["pv_kw"] = [r["dirty"]["output_kw"] for r in revised_rows]
                            optical_rows[0] = physical_row
                            base_pv = physical_row["clean"]["output_kw"]
                            solar_record = physical_optical.record(
                                physical_row,
                                weather["reference"],
                                [x["id"] for x in weather.get("snapshots", [])],
                            )
                        service_entry = services.prepare if service_controller else services.begin
                        dock_kw = service_entry(
                            t,
                            diagnosis,
                            forecast["pv_kw"][0],
                            environment=current,
                            **(
                                dict(capacity_requests=False)
                                if policy.investigation is not None
                                else {}
                            ),
                            available_battery_kw=min(
                                p.battery_kw, max(0, observation["battery_kwh"]) * p.eta
                            ),
                        )
                    else:
                        forecast["pv_kw"] = [
                            v
                            * (
                                1
                                - min(
                                    0.3,
                                    services.soiling + i * c.field_operations.soiling_per_day / 24,
                                )
                            )
                            for i, v in enumerate(forecast["pv_kw"])
                        ]
                        service_entry = services.prepare if service_controller else services.begin
                        dock_kw = service_entry(
                            t,
                            diagnosis,
                            forecast["pv_kw"][0],
                            **(
                                dict(capacity_requests=False)
                                if policy.investigation is not None
                                else {}
                            ),
                            **(
                                {
                                    "available_battery_kw": min(
                                        p.battery_kw, max(0, observation["battery_kwh"]) * p.eta
                                    )
                                }
                                if c.service_system is not None
                                else {}
                            ),
                        )
                    if c.service_system is not None:
                        if getattr(services, "belief_record", None) and observer:
                            services.belief_record["performance"] = observer.record()
                        service_planning_inputs = {
                            "schema_version": "service-process-planning-inputs/1",
                            "estimate": asdict(estimated_state(observation, p)),
                            "capacity_kw": diagnosis.capacity_kw,
                            "forecast": {**copy.deepcopy(forecast), "decision_hour": t},
                            "reference_forecast": {
                                **copy.deepcopy(raw_forecast),
                                "decision_hour": t,
                            }
                            if raw_forecast is not None
                            else None,
                            "objective": policy.objective,
                            "terminal_battery_value": policy.terminal_battery_value_kg_per_kwh,
                            "cost_version": decision_cost_version,
                            "service_cost_version": service_cost_version,
                        }
                    if service_controller:
                        from methane.services.controller import VERIFICATION_VERSION
                        from methane.services.verification import capture as capture_load_test

                        forecast["decision_hour"] = t
                        if raw_forecast is not None:
                            raw_forecast["decision_hour"] = t
                        coordinated = service_controller.decide(
                            services,
                            p,
                            estimated_state(observation, p),
                            forecast,
                            diagnosis.capacity_kw,
                            c.costs,
                            c.service_economics,
                            prefix=rows,
                            objective=policy.objective,
                            seconds=s.solver_seconds,
                            components=components,
                            reference_forecast=raw_forecast,
                            terminal_battery_value=policy.terminal_battery_value_kg_per_kwh,
                            recovery_scheduler=joint_recovery_scheduler,
                            **(
                                dict(diagnosis=diagnosis)
                                if policy.investigation is not None
                                or joint_recovery_scheduler is not None
                                else {}
                            ),
                            **(
                                dict(
                                    sensors=c.sensors,
                                    observed_interval=capture_load_test(rows[-1]) if rows else None,
                                )
                                if policy.service.version == VERIFICATION_VERSION
                                else {}
                            ),
                        )
                        forecast = coordinated["forecast"]
                        dock_kw = coordinated["service_kw"]
                    else:
                        forecast["service_kw"] = [dock_kw] + [0] * (n - 1)
                    forecast["electrolyser_isolated"] = services.isolation_horizon(n)
                    if not service_controller:
                        forecast["field_assumption"] = (
                            "Current measured soiling with linear accumulation; no future cleaning benefit or dock demand anticipated. Service policy fixed for this replan."
                        )
                    if (
                        recovery_scheduler is not None
                        and c.service_system is not None
                        and not service_controller
                    ):
                        demands = services.planned_demands(n)
                        forecast["service_kw"] = [r["bus_kwh"] for r in demands["rows"]]
                        forecast["service_commitments"] = demands
                        forecast["field_assumption"] = (
                            "Current accepted service commitments and granted standby are projected; "
                            "continuation remains conditional on actual power/access. No future "
                            "cleaning benefit, replenishment or unaccepted charge is credited."
                        )
                estimate = estimated_state(observation, p)
                policy = resolved_policies[name]
                objective = policy.objective
                planned = (
                    coordinated["plan"]
                    if coordinated and coordinated["plan"] is not None
                    else plan(
                        p,
                        estimate,
                        forecast,
                        diagnosis.capacity_kw,
                        c.costs,
                        objective,
                        s.solver_seconds,
                        battery=battery,
                        components=components,
                        terminal_battery_value=policy.terminal_battery_value_kg_per_kwh,
                    )
                )
                probe = False
                capacity_used = diagnosis.capacity_kw
                recovery = None
                if joint_recovery_scheduler is not None:
                    recovery = joint_recovery_scheduler.finish(coordinated.get("recovery_planning"))
                    if recovery["plan"] is not None:
                        planned = recovery["plan"]
                        probe = recovery["probe_now"]
                        if probe:
                            capacity_used = recovery["inputs"]["target_kw"]
                elif recovery_scheduler is not None:
                    recovery = recovery_scheduler.decide(
                        p,
                        c.sensors,
                        estimate,
                        diagnosis,
                        forecast,
                        c.costs,
                        hour=t,
                        objective=objective,
                        seconds=s.solver_seconds,
                        components=components,
                        service_decision=services.interval["decision"] if services else None,
                        terminal_battery_value=policy.terminal_battery_value_kg_per_kwh,
                    )
                    if recovery["plan"] is not None:
                        planned = recovery["plan"]
                        probe = recovery["probe_now"]
                        if probe:
                            capacity_used = recovery["inputs"]["target_kw"]
                elif (
                    c.sensors.enabled
                    and diagnosis.capacity_kw < p.electrolyser_kw * 0.999
                    and not forecast.get("electrolyser_isolated", [False])[0]
                ):
                    target = min(
                        p.electrolyser_kw,
                        max(
                            p.min_kw,
                            diagnosis.capacity_kw + p.electrolyser_kw * c.sensors.probe_fraction,
                        ),
                    )
                    headroom = p.h2_capacity_kg - estimate.h2_kg
                    # Only test with present solar and storage headroom; feasibility checks thermal commitments.
                    if (
                        forecast["pv_kw"][0] >= target + p.start_energy_kwh + p.heater_max_kw
                        and headroom >= target / p.specific_energy_kwh_per_kg
                    ):
                        candidate = plan(
                            p,
                            estimate,
                            forecast,
                            target,
                            c.costs,
                            objective,
                            s.solver_seconds,
                            allow_fallback=False,
                            minimum_ely=target,
                            dependable_capacity=diagnosis.capacity_kw,
                            battery=battery,
                            components=components,
                            terminal_battery_value=policy.terminal_battery_value_kg_per_kwh,
                        )
                        if candidate["actions"]:
                            planned, probe, capacity_used = candidate, True, target
                decision = {
                    "controller_policy": policy.to_dict(),
                    "hour": t,
                    "observations": copy.deepcopy(observation),
                    "estimate": asdict(estimate),
                    "diagnosis": asdict(diagnosis),
                    "forecast": forecast,
                    "plan": planned,
                    "capacity_used_kw": capacity_used,
                    "probe": probe,
                    "planning_objective": objective,
                    "probe_policy_revision": 4
                    if joint_recovery_scheduler is not None
                    else 3
                    if recovery_scheduler is not None
                    else 2,
                    "evidence": evidence(p, estimate, forecast, planned, diagnosis, objective),
                    "policy": objective,
                    "policy_version": VERSION,
                    "cost_version": decision_cost_version,
                    "service_cost_version": service_cost_version,
                    "component_implementations": components.identities(),
                }
                if observer:
                    decision["performance_estimates"] = observer.record()
                if services is not None and getattr(services, "belief_record", None):
                    decision["uncertainty_beliefs"] = copy.deepcopy(services.belief_record)
                if recovery is not None:
                    decision["recovery_planning"] = {
                        key: copy.deepcopy(value)
                        for key, value in recovery.items()
                        if key != "plan"
                    }
                    if recovery["status"] != "inactive":
                        decision["evidence"]["constraints"].append(
                            f"Recovery load test is scheduled for hour {recovery['selected_start']}; capacity remains unconfirmed until actual tracking observations"
                            if recovery["status"] == "scheduled"
                            else "Recovery test: " + recovery["status"].replace("-", " ")
                        )
                if coordinated:
                    decision["service_control"] = copy.deepcopy(coordinated["decision"])
                if policy.terminal_battery_value_kg_per_kwh:
                    decision["evidence"]["terminal_battery"] = {
                        "value_kg_ch4_per_kwh": policy.terminal_battery_value_kg_per_kwh,
                        "predicted_ending_kwh": planned["trajectory"][-1]["state"]["battery_kwh"],
                        "applied_by_optimizer": planned["solver"]["status"] != "fallback",
                        "note": "Linear continuation assumption at the forecast horizon; not methane produced, sale proceeds or a safety reserve. Greedy fallback does not optimize this value.",
                    }
                if services:
                    decision["field_operations"] = copy.deepcopy(services.interval["decision"])
                if service_planning_inputs is not None:
                    decision["service_planning_inputs"] = service_planning_inputs
                before = state
                interval_truth = physical_faults.truth(t)
                service_kw = forecast.get("service_kw", [0])[0]
                if services is not None and c.service_system is not None:
                    service_kw = services.execute_interval(t, physical_faults)
                try:
                    state, row = execute(
                        execution_config.plant,
                        state,
                        planned["actions"][0],
                        forecast["pv_kw"][0],
                        forecast["ambient_c"][0],
                        forecast["deliveries_kg"][0],
                        interval_truth["capacity_kw"],
                        execution_config.costs,
                        battery=physical_components.battery,
                        components=physical_components,
                        service_kw=service_kw,
                    )
                except PhysicalAuditError as exc:
                    failures[name] = {"hour": t, "audits": exc.audits, "context": exc.context}
                    break
                for audit in row["audits"]:
                    audit["interval"] = t
                observed = observe(
                    execution_config.plant,
                    execution_config.sensors,
                    before,
                    row,
                    s.seed,
                    t,
                    interval_truth["flow_bias_fraction"],
                    c.rng_policy,
                )
                if measurement_channels:
                    observed, measurement_truth = measure(observed, measurement_channels, s.seed, t)
                    interval_truth["measurement_errors"] = measurement_truth
                diagnosis, incident, diagnostic_event = update(
                    p,
                    c.sensors,
                    diagnosis,
                    observation,
                    observed,
                    row["requested"]["electrolyser_kw"],
                    probe,
                    **(
                        dict(
                            strict_probe=True,
                            consecutive_probe_power=rows[-1]["requested"]["electrolyser_kw"]
                            if rows and rows[-1]["decision"]["probe"]
                            else None,
                        )
                        if recovery_scheduler is not None or joint_recovery_scheduler is not None
                        else {}
                    ),
                )
                observed["usable_hydrogen_inflow_kg"] = (
                    max(
                        0,
                        observed["h2_inventory_kg"]
                        - observation["h2_inventory_kg"]
                        + observed["h2_outflow_kg"],
                    )
                    if diagnosis.flow_isolated
                    else observed["hydrogen_flow_kg"]
                )
                observed["hydrogen_inflow_source"] = (
                    "inventory mass balance" if diagnosis.flow_isolated else "flow sensor"
                )
                row.update(
                    hour=t,
                    time=weather["times"][t],
                    local_time=local_stamp(weather["times"][t], c.weather.timezone),
                    decision=decision,
                    observations_after=observed,
                    diagnosis_after=asdict(diagnosis),
                    incident=incident,
                    humidity_pct=weather["truth"][weather["times"][t]]["humidity_pct"],
                    irradiance_wm2=weather["truth"][weather["times"][t]]["irradiance_wm2"],
                    solar_detail=weather["truth"][weather["times"][t]].get("solar_detail"),
                )
                from methane.solar import execution_record

                row["component_records"]["solar"] = (
                    solar_record if optical_mode else execution_record(weather, execution_config, t)
                )
                if optical_mode:
                    row["solar_detail"] = optical_rows[0]["dirty"]
                    row["audits"].extend(solar_record["audits"])
                row["intervention_accounting"] = (
                    "legacy-alarm-allowance/1"
                    if c.faults.lifecycle == "legacy-timed" and not services
                    else "recorded-work/1"
                )
                if services:
                    service_record = services.end(t, physical_faults, diagnosis)
                    interval_truth["service_effects"] = service_record.pop("retrospective_effects")
                    if "random_draws" in service_record:
                        interval_truth["service_randomness"] = service_record.pop("random_draws")
                    if "retrospective_job_clocks" in service_record:
                        interval_truth["service_job_clocks"] = service_record.pop(
                            "retrospective_job_clocks"
                        )
                    if "hardware_execution" in service_record:
                        interval_truth["hardware_execution"] = service_record.pop(
                            "hardware_execution"
                        )
                    if "inspection_samples" in service_record:
                        interval_truth["inspection_samples"] = service_record.pop(
                            "inspection_samples"
                        )
                    service_record.update(
                        unserviced_pv_kw=base_pv,
                        soiling_loss_kw=base_pv - row["pv_kw"],
                        available_pv_kw=row["pv_kw"],
                    )
                    if optical_mode:
                        service_record["optical"] = dict(
                            baseline_design=services.optical.baseline,
                            source=optical_rows[0]["sample"],
                            parameters=solar_record["parameters"],
                            clean=optical_rows[0]["clean"],
                            dirty=optical_rows[0]["dirty"],
                        )
                    if observer and c.service_system is not None:
                        from methane.adaptation import surface_observation

                        packet = surface_observation(service_record, services)
                        service_record["performance_update"] = observer.service_observation(
                            t, packet
                        )
                    row["field_operations"] = service_record
                    row["audits"].extend(service_record["audits"])
                controller_truth.append(interval_truth)
                rows.append(row)

                def event(component, label, event_list=event_list, t=t):
                    event_list.append({"hour": t, "component": component, "label": label})

                if observer and observer.solar_record["status"] == "outside model support":
                    event("solar", "Solar observation outside performance-model support")
                if (
                    observer
                    and abs(observer.solar_record["after"] - observer.solar_record["before"]) > 0.02
                ):
                    event("solar", "Solar performance estimate revised")
                if (
                    observer
                    and observer.service_record
                    and abs(observer.service_record["after"] - observer.service_record["before"])
                    > 0.02
                ):
                    event("services", "Cleaning effectiveness estimate revised")
                if row["reactor_start"]:
                    event("reactor", "Methanator started")
                if row["electrolyser_start"]:
                    event("electrolyser", "Electrolyser started")
                if row["forced_trip"]:
                    event("reactor", "Forced shutdown")
                if diagnostic_event:
                    event("electrolyser", diagnostic_event)
                elif diagnosis.status in ("suspected anomaly", "ambiguous"):
                    event(
                        "electrolyser",
                        "Ambiguous observation"
                        if diagnosis.status == "ambiguous"
                        else "Anomaly under investigation",
                    )
                if probe:
                    event(
                        "electrolyser",
                        "Scheduled capacity test"
                        if recovery_scheduler is not None or joint_recovery_scheduler is not None
                        else "Safe capacity probe",
                    )
                if recovery is not None:
                    key = (
                        recovery["status"],
                        recovery.get("selected_start"),
                        recovery.get("inputs", {}).get("target_kw"),
                    )
                    if key != previous_recovery and recovery["status"] != "inactive":
                        event(
                            "electrolyser",
                            f"Recovery test scheduled for hour {recovery['selected_start']}"
                            if recovery["status"] == "scheduled"
                            else "Recovery test: " + recovery["status"],
                        )
                    previous_recovery = key
                if forecast["source"]["id"] != previous_issue:
                    # Synthetic templates update hourly; show only material forecast errors there.
                    if (
                        weather["mode"] != "synthetic"
                        or abs(forecast["current_forecast_error_kw"]) > p.solar_kw * 0.1
                    ):
                        event("solar", "Forecast updated")
                previous_issue = forecast["source"]["id"]
                if row["co2_delivered_kg"] or row["co2_rejected_kg"]:
                    event(
                        "co2",
                        "CO2 delivery" + ("; excess rejected" if row["co2_rejected_kg"] else ""),
                    )
                observation = observed
            except CancelledOperation:
                break
            except PhysicalAuditError as exc:
                failures[name] = {"hour": t, "audits": exc.audits, "context": exc.context}
                break
        if services:
            event_list.extend(services.messages)
            event_list.sort(key=lambda e: e["hour"])
            if c.service_system is not None:
                service_planning_catalogues.update(services.planning_catalogues)
        truth_by_controller[name] = controller_truth
        records[name], metrics[name], events[name] = (
            rows,
            summarise(rows, execution_config, controller_truth),
            event_list,
        )
        if observer:
            from methane.adaptation import metrics as performance_metrics

            metrics[name]["performance"] = performance_metrics(rows)
        if service_controller is not None:
            decisions = [
                r["decision"]["service_control"] for r in rows if "service_control" in r["decision"]
            ]
            metrics[name]["service_control"] = {
                "implementation_id": policy.service.version,
                "fallback_intervals": sum(d["fallback_used"] for d in decisions),
                "candidate_solves": sum(
                    sum("evaluation" in c for c in d["candidates"]) for d in decisions
                ),
                "unresolved_obligations": sum(
                    o["status"] not in ("completed", "verified")
                    for o in service_controller.obligations.values()
                ),
                "missed_work_deadlines": sum(
                    o["deadline_missed_at"] is not None
                    for o in service_controller.obligations.values()
                ),
                "repair_retries": sum(
                    max(0, len(o["attempts"]) - 1) for o in service_controller.obligations.values()
                ),
                "ending_energy_targets": copy.deepcopy(service_controller.energy_targets),
                "scope": "Obligations are observed through the last decision boundary; final-interval verification may arrive afterwards. No unresolved item is counted as successful recovery.",
            }
            if service_controller.verifier is not None:
                metrics[name]["service_control"]["post_service_verification"] = copy.deepcopy(
                    service_controller.verification
                )
            if service_controller.investigator is not None:
                investigations = copy.deepcopy(
                    list(service_controller.investigator.episodes.values())
                )
                metrics[name]["service_control"]["investigations"] = investigations
                metrics[name]["service_control"]["unresolved_investigations"] = sum(
                    e["status"] != "observer confirmed" for e in investigations
                )
                metrics[name]["service_control"]["unresolved_obligations"] += metrics[name][
                    "service_control"
                ]["unresolved_investigations"]
                metrics[name]["service_control"]["missed_investigation_deadlines"] = sum(
                    e["deadline_missed_at"] is not None for e in investigations
                )
                metrics[name]["service_control"]["missed_work_deadlines"] += metrics[name][
                    "service_control"
                ]["missed_investigation_deadlines"]
                service_orders = services.public()["orders"]
                metrics[name]["service_control"]["repair_retries"] += sum(
                    max(
                        0,
                        sum(
                            o.get("investigation_id") == e["id"]
                            and o["kind"] in ("reset", "module-replacement")
                            for o in service_orders
                        )
                        - 1,
                    )
                    for e in investigations
                )
        if cancelled and cancelled():
            break
    status = (
        "invalid"
        if failures
        else "complete"
        if all(len(records.get(name, [])) == s.hours for name in names)
        else "cancelled"
    )
    result = {
        "schema_version": "dispatch-lab/methane/3",
        "provenance": provenance,
        "experiment_id": experiment_identity(provenance),
        "failures": failures,
        "model_version": VERSION,
        "config": execution_config.to_dict(),
        "asset_ids": {
            **ASSETS,
            **(
                services.manifest()["asset_ids"]
                if services is not None and c.service_system is not None
                else FIELD_ASSETS
                if c.field_operations.enabled
                else {}
            ),
        },
        "decision_cost_version": decision_cost_version,
        "service_cost_version": service_cost_version,
        "records": records,
        "metrics": metrics,
        "events": events,
        "retrospective_truth": next(iter(truth_by_controller.values()), []),
        "retrospective_truth_controller": next(iter(truth_by_controller), None),
        "retrospective_truth_by_controller": truth_by_controller,
        "field_operations_model": services.manifest()
        if services is not None and c.service_system is not None
        else field_manifest(c.field_operations),
        "weather": weather,
        "status": status,
    }
    if uncertainty is not None:
        result["controller_config"] = c.to_dict()
    from methane.uncertainty import snapshot as uncertainty_snapshot

    result["uncertainty"] = uncertainty_snapshot(result["config"], uncertainty)
    if service_planning_catalogues:
        result["service_planning_catalogues"] = service_planning_catalogues
    if any(p.service is not None for p in resolved_policies.values()):
        result["field_operations_model"]["dispatch_policies"] = {
            name: p.to_dict() for name, p in resolved_policies.items()
        }
        result["field_operations_model"]["power_policy"] = (
            "MPC controllers with an explicit coordinated-services policy jointly choose work, charging and production under recorded forecasts; Greedy and policies without that option retain the local service rule. Version 2 also proposes shared crew visits. Actual service loads, public hardware feedback and physical interlocks still constrain execution. Each decision identifies its policy, conditional plan and fallback."
        )
    # Identity omits nondeterministic solve timings but includes all physics and decision settings.
    result["run_id"] = digest(
        {
            "config": result["config"],
            "version": VERSION,
            "experiment_id": result["experiment_id"],
            "weather": [x["id"] for x in weather["snapshots"]],
            "actions": {n: [r["applied"] for r in rs] for n, rs in records.items()},
        }
    )
    from methane.documentation import default_examples, snapshot

    result["documentation"] = snapshot()
    result["learning_examples"] = default_examples()
    from methane.taxonomy import snapshot as taxonomy_snapshot

    result["taxonomy"] = taxonomy_snapshot(result)
    return seal(result)


def what_if(result, controller, hour, alternative):
    if alternative not in ("battery", "electrolyser", "reactor", "co2"):
        raise ValueError("Unknown alternative.")
    c = Config.from_dict(result.get("controller_config", result["config"]))
    row = result["records"][controller][int(hour)]
    d = row["decision"]
    forecast = copy.deepcopy(d["forecast"])
    note = (
        "Predicted from original observations, forecast and frozen costs; realised future excluded."
    )
    if d.get("field_operations"):
        note += " The original service schedule and isolation constraints are held fixed. Service scheduling is not re-optimised; predicted decision costs exclude this fixed service workload."
    if alternative == "co2":
        next_delivery = next((i for i, v in enumerate(forecast["deliveries_kg"]) if v > 0), None)
        if next_delivery is None:
            note += " No delivery is scheduled inside this horizon; no change."
        else:
            amount = forecast["deliveries_kg"][next_delivery]
            forecast["deliveries_kg"][next_delivery] = 0
            if next_delivery + 24 < len(forecast["deliveries_kg"]):
                forecast["deliveries_kg"][next_delivery + 24] += amount
            else:
                note += " Delayed delivery lies beyond this prediction horizon."
    if alternative == "reactor" and d["estimate"]["reactor_on"]:
        note += " Reactor is already running; preventing a new start has no effect this interval."
    recovery = d.get("recovery_planning", {})
    if recovery.get("status") == "scheduled":
        from methane.recovery import RecoveryPolicy, compare

        original = recovery["inputs"]
        joint_inputs = {}
        if original["policy"]["version"] in ("scheduled-load-tests/2", "scheduled-load-tests/3"):
            joint_inputs["accepted_start"] = recovery["commitment"]["start_hour"]
            if "not_before_hour" in original:
                joint_inputs["not_before_hour"] = original["not_before_hour"]
            if "charging_inputs" in original:
                from methane.services.charging import Inputs

                joint_inputs["charging_inputs"] = Inputs.from_dict(original["charging_inputs"])
                forecast["service_kw"] = copy.deepcopy(original["fixed_service_kw"])
        revised = compare(
            c.plant,
            State(**d["estimate"]),
            Diagnosis(**d["diagnosis"]),
            forecast,
            Costs(**result["config"]["costs"]),
            RecoveryPolicy(**original["policy"]),
            hour=original["hour"],
            target_kw=original["target_kw"],
            required_hours=original["required_hours"],
            due_hour=original["due_hour"],
            objective=original["objective"],
            seconds=original["seconds"],
            components=assemble(c.plant, c.models),
            alternative=alternative,
            terminal_battery_value=original["terminal_battery_value"],
            **joint_inputs,
        )
        alt = revised["plan"] or dict(
            actions=[],
            trajectory=[],
            predicted=None,
            solver=dict(
                status="unresolved",
                valid_incumbent=False,
                fallback_used=False,
                reason=revised["status"],
            ),
        )
        alt["recovery_planning"] = {key: value for key, value in revised.items() if key != "plan"}
        note += (
            " The accepted test window, load, deadlines, robot energy targets and delivery hypotheses are retained. Dock charging and process actions are replanned together; the original dock load is replaced, not added again. Predictions do not confirm physical recovery."
            if joint_inputs
            else " The original load-test target, deadline, reserve and delivery hypotheses are retained; the alternative can move the test window. Predictions do not confirm physical recovery."
        )
    else:
        alt = plan(
            c.plant,
            State(**d["estimate"]),
            forecast,
            d["capacity_used_kw"],
            Costs(**result["config"]["costs"]),
            d.get(
                "planning_objective",
                "methane" if d["probe"] and d["policy"] == "greedy" else d["policy"],
            ),
            c.scenario.solver_seconds,
            alternative,
            allow_fallback=False,
            minimum_ely=d["capacity_used_kw"]
            if d["probe"] and alternative != "electrolyser"
            else 0,
            dependable_capacity=d["diagnosis"]["capacity_kw"]
            if d["probe"] and d.get("probe_policy_revision", 1) >= 2
            else None,
            components=assemble(c.plant, c.models),
            terminal_battery_value=d.get("controller_policy", {}).get(
                "terminal_battery_value_kg_per_kwh", 0
            ),
        )
    from methane.provenance import LOADED_SOURCE

    return {
        "replanner_source_content_hash": LOADED_SOURCE["content_hash"],
        "original_source_content_hash": result.get("provenance", {})
        .get("source", {})
        .get("content_hash"),
        "key": f"{result['run_id']}|{controller}|{hour}|{alternative}",
        "run_id": result["run_id"],
        "controller": controller,
        "hour": hour,
        "alternative": alternative,
        "label": "PREDICTION / SAME INFORMATION",
        "note": note,
        "original": d["plan"]["predicted"],
        "original_solver": d["plan"]["solver"],
        "alternative_plan": alt,
        "forecast_source": d["forecast"]["source"],
        "cost_version": d["cost_version"],
    }


def run(
    config=None,
    weather=None,
    strategies=None,
    progress=None,
    cancelled=None,
    policies=None,
    uncertainty=None,
):
    token = predicate.set(cancelled)
    try:
        return _run(config, weather, strategies, progress, cancelled, policies, uncertainty)
    finally:
        predicate.reset(token)
