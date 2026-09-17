"""Progressive component inspection over authoritative versioned Python records."""

import json
import threading
from dataclasses import asdict, fields, replace
from datetime import timedelta
from pathlib import Path

import gradio as gr

from methane.battery import IMPLEMENTATIONS
from methane.battery_trace import trace as battery_trace
from methane.config import Config, Costs, Models, Plant, Scenario, Sensors, WeatherConfig
from methane.contracts import BATTERY, REACTOR, SPECS
from methane.costing import allocation, reprice
from methane.electrolyser import IMPLEMENTATIONS as ELY_IMPLEMENTATIONS
from methane.evidence import RUNS, batch, export, load, markdown_report, save
from methane.faults import FaultPolicy
from methane.lineage import (
    derived as derived_trace,
)
from methane.lineage import (
    economic as economic_trace,
)
from methane.lineage import (
    trace as component_trace,
)
from methane.preview_service import register as register_preview
from methane.provenance import seal
from methane.services.configuration import ServiceSystem
from methane.simulation import run, what_if
from methane.solar import preview as solar_preview
from methane.solar import validate as validate_solar
from methane.storage import IMPLEMENTATIONS as GAS_IMPLEMENTATIONS
from methane.weather import IncompleteWeather, local_stamp, search_locations, stamp, utc
from ui_theme import ASSETS

CANCELLATIONS = {}


def service_decision_view(control, path):
    """Render recorded summaries; full operands remain in the registered run/archive."""
    view = {k: v for k, v in control.items() if k not in ("inputs", "candidates")}
    view["full_calculation_path"] = path
    if control.get("investigation"):
        investigation = control["investigation"]
        view["investigation"] = {k: v for k, v in investigation.items() if k != "episodes"}
        view["investigation"]["episodes"] = []
        for index, episode in enumerate(investigation["episodes"]):
            item = {k: v for k, v in episode.items() if k != "selection"}
            if episode.get("selection"):
                selection = episode["selection"]
                item["selection"] = {
                    k: selection[k]
                    for k in ("selection_id", "candidates", "selected", "restoration_requirement")
                }
                item["selection"]["full_calculation_path"] = (
                    f"{path}/investigation/episodes/{index}/selection"
                )
            if episode.get("recovery_belief"):
                belief = episode["recovery_belief"]
                item["recovery_belief"] = {
                    k: belief[k]
                    for k in (
                        "implementation_id",
                        "belief_id",
                        "at_hour",
                        "status",
                        "reason",
                        "restoration_probability",
                        "scope",
                    )
                }
                item["recovery_belief"]["inputs"] = {
                    k: belief["inputs"][k] for k in ("impaired_capacity_kw", "success_probability")
                }
                item["recovery_belief"]["full_calculation_path"] = (
                    f"{path}/investigation/episodes/{index}/recovery_belief"
                )
            view["investigation"]["episodes"].append(item)
    view["candidates"] = []
    for candidate in control.get("candidates", []):
        item = {k: v for k, v in candidate.items() if k != "evaluation"}
        evaluation = candidate.get("evaluation")
        if evaluation:
            item["evaluation"] = {
                k: evaluation[k]
                for k in (
                    "implementation_id",
                    "input_key",
                    "state",
                    "score",
                    "mission_decision_eur",
                    "constraints",
                    "scope",
                )
                if k in evaluation
            }
            if evaluation.get("process_plan"):
                item["evaluation"]["process_plan"] = {
                    k: evaluation["process_plan"][k]
                    for k in ("predicted", "solver")
                    if k in evaluation["process_plan"]
                }
        view["candidates"].append(item)
    return view


def wire_payload(value):
    """An immutable JSON scalar avoids Gradio deep-snapshotting a whole run.

    The renderer decodes once per payload update. Numerical and archive APIs
    retain their structured objects; no operand or provenance is omitted.
    """
    return json.dumps(value, separators=(",", ":"), allow_nan=False)


def playback_value(result, register_contexts=True):
    from methane.model_service import register as register_model
    from methane.study_service import register as register_study

    p = result["config"]["plant"]
    period = result.get("continuous_period")
    display_result = result
    if period:
        times = [r["time"] for r in next(iter(result["records"].values()))]
        display_result = {**result, "weather": {**result["weather"], "times": times}}
    frames, view_records = {}, {}
    for name, rows in result["records"].items():
        values = {
            "methane_kg": 0,
            "h2_kg": p["initial_h2_kg"],
            "co2_kg": p["initial_co2_kg"],
            "battery_kwh": p["battery_kwh"] * p["initial_soc"],
            "curtailed_kwh": 0,
            "local_time": local_stamp(
                result["weather"]["times"][0], result["config"]["weather"]["timezone"]
            ),
        }
        if period:
            values.update(
                {k: period["initial_state"][k] for k in ("h2_kg", "co2_kg", "battery_kwh")}
            )
            values["local_time"] = local_stamp(
                rows[0]["time"], result["config"]["weather"]["timezone"]
            )
        frames[name] = [dict(values)]
        view_records[name] = []
        for row in rows:
            # Derive display telemetry for early v0.2 archives without editing the source run.
            observation = dict(row["observations_after"])
            isolated = row["diagnosis_after"]["flow_isolated"]
            observation.setdefault(
                "usable_hydrogen_inflow_kg",
                max(
                    0,
                    observation["h2_inventory_kg"]
                    - row["decision"]["observations"]["h2_inventory_kg"]
                    + observation["h2_outflow_kg"],
                )
                if isolated
                else observation["hydrogen_flow_kg"],
            )
            observation.setdefault(
                "hydrogen_inflow_source", "inventory mass balance" if isolated else "flow sensor"
            )
            decision = {
                **row["decision"],
                "plan": {
                    k: v
                    for k, v in row["decision"]["plan"].items()
                    if k not in ("trajectory", "actions")
                },
            }
            decision.pop("service_planning_inputs", None)
            field_view = None
            if "service_control" in decision:
                pointer = (
                    "/records/"
                    + name.replace("~", "~0").replace("/", "~1")
                    + "/"
                    + str(len(view_records[name]))
                )
                decision["service_control"] = service_decision_view(
                    decision["service_control"], pointer + "/decision/service_control"
                )
                if "field_operations" in decision:
                    decision["field_operations"] = {
                        k: v
                        for k, v in decision["field_operations"].items()
                        if k
                        not in (
                            "service_control",
                            "charging_evaluation",
                            "coupled_evaluation",
                            "service_supervisor",
                        )
                    }
                    decision["field_operations"]["service_control"] = decision["service_control"]
                field = row.get("field_operations")
                if field:
                    field_decision = {
                        k: v
                        for k, v in field["decision"].items()
                        if k
                        not in (
                            "service_control",
                            "charging_evaluation",
                            "coupled_evaluation",
                            "service_supervisor",
                        )
                    }
                    field_decision["service_control"] = decision["service_control"]
                    field_view = {**field, "decision": field_decision}
            if row.get("field_operations", {}).get("planning_snapshot"):
                field_view = dict(field_view or row["field_operations"])
                snapshot = field_view.pop("planning_snapshot")
                field_view["planning_context"] = {
                    "snapshot_id": snapshot["snapshot_id"],
                    "at_hour": snapshot["at_hour"],
                    "schema_version": snapshot["schema_version"],
                }
            audit_summary = {
                "passed": sum(a["passed"] for a in row.get("audits", [])),
                "total": len(row.get("audits", [])),
            }
            view_records[name].append(
                {
                    **{
                        k: v
                        for k, v in row.items()
                        if k not in ("audits", "battery_record", "component_records")
                    },
                    "audit_summary": audit_summary,
                    "decision": decision,
                    "observations_after": observation,
                    **({"field_operations": field_view} if field_view is not None else {}),
                }
            )
            values = {
                "methane_kg": values["methane_kg"] + row["applied"]["methane_kg"],
                "h2_kg": row["observations_after"]["h2_inventory_kg"],
                "co2_kg": row["state"]["co2_kg"],
                "battery_kwh": row["state"]["battery_kwh"],
                "curtailed_kwh": values["curtailed_kwh"] + row["curtailed_kwh"],
                "local_time": local_stamp(
                    stamp(utc(row["time"]) + timedelta(hours=1)),
                    result["config"]["weather"]["timezone"],
                ),
            }
            frames[name].append(values)
    weather = {k: result["weather"][k] for k in ("reference", "attribution", "forecast_cadence")}
    return {
        **{
            k: result[k] for k in ("run_id", "config", "asset_ids", "events", "retrospective_truth")
        },
        "retrospective_truth_by_controller": result.get("retrospective_truth_by_controller", {}),
        "field_operations_model": result.get("field_operations_model"),
        "taxonomy": result.get("taxonomy") if not register_contexts else None,
        "records": view_records,
        "preview_token": register_preview(display_result) if register_contexts else None,
        "model_token": register_model(result) if register_contexts else None,
        "control_repository": str(Path(__file__).resolve().parents[1])
        if register_contexts
        else None,
        "study_token": register_study(result) if register_contexts else None,
        "component_specs": {k: v.to_dict() for k, v in SPECS.items()},
        "provenance_summary": {
            "status": "recorded" if "provenance" in result else "unavailable (legacy archive)",
            "experiment_id": result.get("experiment_id"),
            "weather_content_hash": result.get("provenance", {}).get("weather_content_hash"),
            "source": result.get("provenance", {}).get("source", {}).get("content_hash"),
            "components": result.get("provenance", {}).get("components"),
        },
        "frames": frames,
        "weather": weather,
        "solar": solar_preview(display_result),
        "continuous_period": period,
        **(
            {
                "events": {
                    name: [
                        {
                            **event,
                            "global_hour": event["hour"],
                            "hour": event["hour"] - period["start_hour"],
                        }
                        for event in values
                    ]
                    for name, values in result["events"].items()
                }
            }
            if period
            else {}
        ),
        "start_local": local_stamp(
            display_result["weather"]["times"][0], result["config"]["weather"]["timezone"]
        ),
    }


def report(result):
    return markdown_report(
        [{"case": "Current run", "status": result["status"], "metrics": result["metrics"]}]
    )


def default_result():
    path = RUNS / "demo.json.gz"
    if path.exists():
        return load(path)
    result = run(Config())
    saved = save(result)
    path.write_bytes(saved.read_bytes())
    return result


def build_app(default=None, *, start_project=False):
    default = default or default_result()
    initial = Config.from_dict(default["config"])
    if "faults" not in default["config"]:
        initial = replace(initial, faults=FaultPolicy())
    elif initial.field_operations.enabled and initial.service_system is not None:
        # New setup starts with corrected physics; `default` still contains the
        # untouched recorded run. Explicit archive/setup loading retains its model.
        initial = replace(
            initial, faults=replace(initial.faults, hardware_model="actuator-interlock/1")
        )
    widgets, widget_keys = [], []

    def setup_value(data, group, key):
        if group == "investigation_policy" and key == "followup_impairment_probability":
            value = (data.get(group) or {}).get(key)
            return 0.5 if value is None else value
        if group in ("recovery_policy", "service_policy", "investigation_policy"):
            from methane.recovery import RecoveryPolicy
            from methane.services.controller import ServicePolicy
            from methane.services.investigator import CONTINUATION_VERSION, InvestigationPolicy

            defaults = {
                "recovery_policy": RecoveryPolicy,
                "service_policy": ServicePolicy,
                "investigation_policy": lambda: InvestigationPolicy(version=CONTINUATION_VERSION),
            }

            return (
                data.get(group) is not None
                if key == "enabled"
                else (data.get(group) or asdict(defaults[group]()))[key]
            )
        if group == "service_economics":
            from methane.service_economics import illustrative

            if key == "enabled":
                return data.get(group) is not None
            value = data.get(group) or illustrative(Costs(**data["costs"]))
            for part in key.split("."):
                value = value.get(part) if isinstance(value, dict) else None
            return value
        if group == "service_system" and data.get(group) is None:
            return "legacy/1" if key == "implementation" else getattr(ServiceSystem(), key)
        if group == "service_system" and key in (
            "crew_return_enabled",
            "crew_return_pack_hours",
            "crew_return_check_hours",
        ):
            return data[group].get(key, getattr(ServiceSystem(), key))
        if group == "faults" and key == "hardware_model":
            return data[group].get(key, "recovery-gated/1")
        if group == "sensors" and key == "ambiguity_policy":
            return data[group].get(key, "reduce-capacity/1")
        return data[group][key]

    def parameter(group, key):
        value = setup_value(initial.to_dict(), group, key)
        metadata = next(
            (
                x
                for x in (*REACTOR.parameters, *BATTERY.parameters)
                if group == "plant" and x.key == key
            ),
            None,
        )
        label = f"{metadata.label} / {metadata.unit}" if metadata else key.replace("_", " ")
        if group == "recovery_policy":
            label = {
                "enabled": "Schedule recovery tests (experimental)",
                "version": "Recovery test coordination",
                "tracking_success_probability": "Assumed tracking probability",
                "risk_weight": "Worst-case objective weight",
                "battery_reserve_fraction": "Ending battery reserve / fraction",
            }.get(key, label)
        if group == "service_policy":
            label = {
                "enabled": "Coordinate service work with MPC (experimental)",
                "version": "Service scheduling alternatives",
                "maximum_wait_hours": "Original work deadline / hours after request",
                "retry_after_hours": "Wait after repair interruption or failed tests / hours",
                "maximum_repair_attempts": "Maximum repair attempts per obligation",
                "charging_wait_hours": "Charging deadline / hours after need",
                "robot_reserve_fraction": "Operating robot reserve / fraction",
                "maximum_candidates": "Candidate schedules / maximum",
                "comparison_seconds": "Total comparison budget / seconds",
            }.get(key, label)
        if group == "investigation_policy":
            label = {
                "enabled": "Plan investigations from returned evidence",
                "version": "Investigation follow-through",
                "mode": "Investigation strategy",
                "reader": "Investigation reader",
                "minimum_restoration_probability": "Minimum assumed restoration probability",
                "risk_weight": "Investigation worst-case weight",
                "comparison_seconds": "Investigation comparison budget / seconds",
                "observation_wait_hours": "Wait for the finding / hours",
                "followup_impairment_probability": "Further repair: minimum assumed impairment probability",
            }.get(key, label)
        if group == "service_economics":
            label = (
                "Use complete service accounting"
                if key == "enabled"
                else key.replace("_", " ").replace(".", " / ")
            )
        if isinstance(value, bool):
            widget = gr.Checkbox(value, label=label)
        elif group == "investigation_policy" and key == "followup_impairment_probability":
            widget = gr.Number(
                value,
                minimum=0,
                maximum=1,
                label=label,
                info="A further repair also needs repeated resource-feasible operating shortfalls. This conditional probability does not verify recovery.",
                visible=initial.investigation_policy is not None
                and initial.investigation_policy.version == "observed-service-investigation/3",
            )
        elif group == "investigation_policy" and key in ("version", "mode", "reader"):
            choices = {
                "version": [
                    (
                        "Observed remedies; separate operating tests (version 1)",
                        "observed-service-investigation/1",
                    ),
                    (
                        "Remedies with nominated operating tests (version 2)",
                        "observed-service-investigation/2",
                    ),
                    (
                        "Carry uncertainty through work and tests (version 3)",
                        "observed-service-investigation/3",
                    ),
                ],
                "mode": [
                    ("Compare inspection and direct intervention", "planned"),
                    ("Inspect first", "inspect-first"),
                    ("Direct qualified intervention", "direct-intervention"),
                ],
                "reader": [
                    ("Installed fixed reader", "fixed"),
                    ("Mobile inspection rover", "mobile"),
                ],
            }
            widget = gr.Dropdown(choices[key], value=value, label=label)
        elif group == "recovery_policy" and key == "version":
            widget = gr.Dropdown(
                [
                    ("After service selection (version 1)", "scheduled-load-tests/1"),
                    (
                        "Joint work, charging and tests for MPC (version 2)",
                        "scheduled-load-tests/2",
                    ),
                    (
                        "Bounded post-mission verification and escalation (version 3)",
                        "scheduled-load-tests/3",
                    ),
                    (
                        "Forecast-aware bounded verification (legacy version 4)",
                        "scheduled-load-tests/4",
                    ),
                    (
                        "Separate recovery deadline and test appointments (version 5)",
                        "scheduled-load-tests/5",
                    ),
                ],
                value=value,
                label=label,
                info="Joint tests require shared visits and measured repair follow-up (service version 3). Greedy keeps the independent test scheduler and local service rule; recorded policies distinguish this comparison.",
            )
        elif group == "service_policy" and key == "version":
            widget = gr.Dropdown(
                [
                    ("Individual jobs (version 1)", "coordinated-services/1"),
                    ("Individual and shared crew visits (version 2)", "coordinated-services/2"),
                    (
                        "Shared visits and measured repair follow-up (version 3)",
                        "coordinated-services/3",
                    ),
                ],
                value=value,
                label=label,
            )
        elif group == "sensors" and key == "ambiguity_policy":
            widget = gr.Dropdown(
                [
                    ("Reduce estimate (original rule)", "reduce-capacity/1"),
                    ("Retain prior estimate (experimental)", "retain-capacity/1"),
                ],
                value=value,
                label="When electrical and inventory channels disagree",
            )
        elif group == "service_system" and key in (
            "implementation",
            "inspector",
            "cleaning_model",
            "environment_source",
            "support_model",
            "portable_cleaner",
            "inspection_model",
            "maintenance_target",
            "cleaning_policy",
            "inspection_interface",
            "outcome_randomness",
        ):
            choices = {
                "outcome_randomness": [
                    ("Original request text", "legacy-reason/1"),
                    ("Target / action / request", "target-action-request/1"),
                ],
                "cleaning_policy": [
                    ("Original condition rule / archive compatibility", "legacy-condition"),
                    ("No cleaning requests", "off"),
                    ("Current surface condition", "condition"),
                    ("Recurring full section passes", "periodic"),
                ],
                "inspection_interface": [
                    ("Original prepared-contact assumption", "legacy-prepared"),
                    ("Accessible contact test port", "accessible-port"),
                    ("Enclosed contact / human access required", "enclosed-contact"),
                ],
                "maintenance_target": [
                    ("All installed resident hardware", "resident"),
                    ("Row cleaner", "cleaner"),
                    ("Inspection rover", "rover"),
                    ("Dock", "dock"),
                    ("Fixed reader", "fixed_reader"),
                    ("Reset controller", "reset"),
                ],
                "implementation": [
                    ("Whole-hour baseline", "legacy/1"),
                    ("Fractional service contracts", "plant-service-contracts/1"),
                ],
                "inspector": [
                    ("Mobile contact reader", "mobile"),
                    ("Fixed contact reader", "fixed"),
                    ("Fixed and mobile referenced readers", "both"),
                    ("No independent reader", "none"),
                ],
                "inspection_model": [
                    ("Bounded contact baseline", "bounded-contact/1"),
                    ("Voltage and reference checks", "referenced-contact/1"),
                ],
                "cleaning_model": [
                    ("Lumped available-DC proxy", "lumped-dc/1"),
                    ("Section optical coverage", "section-optical/1"),
                ],
                "environment_source": [
                    ("Explicit assumed wind/rain", "assumed"),
                    ("Recorded weather / missing blocks work", "weather"),
                ],
                "support_model": [
                    ("No recovery logistics", "none"),
                    ("Finite crew, supplies and recovery", "logistics/1"),
                ],
                "portable_cleaner": [
                    ("Not supplied", "none"),
                    ("Operator-assisted dry brush", "dry"),
                    ("Operator-assisted wet brush", "wet"),
                ],
            }[key]
            widget = gr.Dropdown(
                choices,
                value=value,
                label={
                    "maintenance_target": "Scheduled maintenance targets",
                    "cleaning_policy": "Local cleaning rule",
                    "inspection_interface": "Contact inspection access",
                    "outcome_randomness": "Service outcome matching",
                    "implementation": "Service execution",
                    "inspector": "Contact reader",
                    "cleaning_model": "Cleaning mechanism",
                    "environment_source": "Service weather",
                    "support_model": "Support logistics",
                    "portable_cleaner": "Contracted portable cleaner",
                    "inspection_model": "Inspection mechanism",
                }[key],
                visible=key != "outcome_randomness" or initial.service_system is not None,
            )
        elif group == "faults" and key == "hardware_model":
            widget = gr.Dropdown(
                [
                    ("Independent actuator faults", "actuator-interlock/1"),
                    ("Legacy recovery-gated faults (reproduction)", "recovery-gated/1"),
                ],
                value=value,
                label="Service hardware physics",
                info="Independent physics applies faults with either recovery policy. Legacy retains saved behaviour and must not rank recovery policies under hardware faults.",
            )
        elif group == "faults" and key in ("lifecycle", "capacity_cause"):
            choices = (
                [
                    ("Persistent / repair required", "persistent"),
                    ("Transient / clears after duration", "transient"),
                    ("Archived timed behaviour", "legacy-timed"),
                ]
                if key == "lifecycle"
                else [
                    ("Equipment damage / replacement", "equipment-damage"),
                    ("Latched module trip / reset permitted", "resettable-trip"),
                ]
            )
            widget = gr.Dropdown(choices, value=value, label=label)
        elif group == "faults" and key.endswith("_service_fault"):
            choices = {
                "cleaner_service_fault": ["none", "control-hold", "drive-power-loss"],
                "rover_service_fault": ["none", "control-hold", "drive-power-loss"],
                "dock_service_fault": ["none", "charger-power-loss"],
                "portable_service_fault": ["none", "pump-power-loss"],
            }[key]
            widget = gr.Dropdown(choices, value=value, label=label)
        elif group == "models":
            widget = gr.Dropdown(
                list(
                    {
                        "battery": IMPLEMENTATIONS,
                        "electrolyser": ELY_IMPLEMENTATIONS,
                        "hydrogen": GAS_IMPLEMENTATIONS,
                        "co2": GAS_IMPLEMENTATIONS,
                        "reactor": ("analytic/1",),
                    }[key]
                ),
                value=value,
                label=key.title() + " implementation",
                info="Equivalent physical models; choice is frozen for each run.",
            )
        elif group == "faults" and key == "contact_stuck":
            widget = gr.Dropdown(
                [
                    ("No shared contact fault", "none"),
                    ("Contact stuck open", "open"),
                    ("Contact stuck closed", "closed"),
                ],
                value=value,
                label="Shared contact fault / retrospective scenario",
            )
        elif group == "weather" and key == "mode":
            widget = gr.Dropdown(
                [
                    ("Synthetic / seeded", "synthetic"),
                    ("Save current ECMWF forecast", "forecast"),
                    ("Historical / ERA5 reference", "historical"),
                ],
                value=value,
                label="Weather source",
            )
        elif key == "horizon_hours":
            widget = gr.Dropdown([6, 12, 24, 48], value=value, label="Planning horizon / hours")
        elif group == "service_economics" and key.endswith(".provision"):
            widget = gr.Dropdown(["owned", "contracted", "shared"], value=value, label=label)
        elif isinstance(value, str):
            widget = gr.Textbox(value, label=label)
        else:
            widget = gr.Number(
                value,
                label=label,
                precision=0
                if isinstance(value, int)
                and group
                not in (
                    "service_economics",
                    "recovery_policy",
                    "service_policy",
                    "investigation_policy",
                )
                else None,
                placeholder="Unpriced" if group == "service_economics" else None,
            )
        widgets.append(widget)
        widget_keys.append((group, key))
        return widget

    def service_prices_from_values(values, base):
        import copy

        from methane.service_economics import illustrative, validate

        enabled = base.get("service_economics") is not None
        data = copy.deepcopy(base.get("service_economics") or illustrative(Costs(**base["costs"])))
        for key, definition in illustrative(Costs(**base["costs"]))["materials"].items():
            if key not in data["materials"]:
                data["materials"][key] = {**definition, "eur_per_unit": None}
        for (group, key), value in zip(widget_keys, values, strict=True):
            if group != "service_economics":
                continue
            if key == "enabled":
                enabled = value
                continue
            parts = key.split(".")
            target = data
            for part in parts[:-1]:
                target = target[part]
            target[parts[-1]] = value
        return validate(data) if enabled else None

    def config_from_values(values, base=None):
        data = Config.from_dict(base).to_dict() if base else initial.to_dict()
        if data.get("service_system") is None:
            data["service_system"] = {**asdict(ServiceSystem()), "implementation": "legacy/1"}
        for (group, key), value in zip(widget_keys, values, strict=True):
            if group in (
                "service_economics",
                "recovery_policy",
                "service_policy",
                "investigation_policy",
            ):
                continue
            original = setup_value(initial.to_dict(), group, key)
            if value is None:
                raise ValueError(key.replace("_", " ") + " is required.")
            if isinstance(original, int) and not isinstance(original, bool):
                if value != int(value):
                    raise ValueError(f"{key} must be a whole number.")
                value = int(value)
            data[group][key] = value
        if data["service_system"]["implementation"] == "legacy/1":
            data["service_system"] = None
        data["service_economics"] = service_prices_from_values(values, data)
        from methane.recovery import RecoveryPolicy

        recovery = data.get("recovery_policy") or asdict(RecoveryPolicy())
        enabled = data.get("recovery_policy") is not None
        for (group, key), value in zip(widget_keys, values, strict=True):
            if group == "recovery_policy":
                if key == "enabled":
                    enabled = value
                else:
                    recovery[key] = value
        if enabled:
            for key in ("maximum_wait_hours", "retry_after_hours"):
                if recovery[key] is None or recovery[key] != int(recovery[key]):
                    raise ValueError(key.replace("_", " ") + " must be a whole number")
                recovery[key] = int(recovery[key])
            data["recovery_policy"] = asdict(RecoveryPolicy(**recovery))
        else:
            data.pop("recovery_policy", None)
        from methane.services.controller import ServicePolicy

        service = data.get("service_policy") or asdict(ServicePolicy())
        enabled = data.get("service_policy") is not None
        for (group, key), value in zip(widget_keys, values, strict=True):
            if group == "service_policy":
                if key == "enabled":
                    enabled = value
                else:
                    service[key] = value
        if enabled:
            for key in (
                "maximum_wait_hours",
                "retry_after_hours",
                "maximum_repair_attempts",
                "charging_wait_hours",
                "maximum_candidates",
            ):
                if service[key] is None or service[key] != int(service[key]):
                    raise ValueError(key.replace("_", " ") + " must be a whole number")
                service[key] = int(service[key])
            data["service_policy"] = asdict(ServicePolicy(**service))
        else:
            data.pop("service_policy", None)
        from methane.services.investigator import CONTINUATION_VERSION, InvestigationPolicy

        investigation = data.get("investigation_policy") or asdict(
            InvestigationPolicy(version=CONTINUATION_VERSION)
        )
        enabled = data.get("investigation_policy") is not None
        for (group, key), value in zip(widget_keys, values, strict=True):
            if group == "investigation_policy":
                if key == "enabled":
                    enabled = value
                else:
                    investigation[key] = value
        if enabled:
            waiting = investigation["observation_wait_hours"]
            if investigation["version"] != "observed-service-investigation/3":
                investigation["followup_impairment_probability"] = None
            if waiting is None or waiting != int(waiting):
                raise ValueError("Wait for the finding must be a whole number of hours")
            investigation["observation_wait_hours"] = int(waiting)
            data["investigation_policy"] = asdict(InvestigationPolicy(**investigation))
        else:
            data.pop("investigation_policy", None)
        if data.get("solar"):
            previous = sum(s["capacity_kw"] for s in data["solar"]["sections"])
            for section in data["solar"]["sections"]:
                section["capacity_kw"] = data["plant"]["solar_kw"] * (
                    section["capacity_kw"] / previous if previous else 1 / 3
                )
        return Config.from_dict(data)

    def simulate(source, *values, progress=gr.Progress()):  # noqa: B008
        try:
            config = config_from_values(values, source["config"])
            result = run(config, progress=progress)
            return (
                result,
                gr.HTML(
                    value=wire_payload(playback_value(result)),
                    economics=wire_payload(reprice(result)),
                ),
                report(result),
                export(result),
                gr.Tabs(selected="operation"),
                "Run complete. Decision assumptions are frozen."
                if result["status"] == "complete"
                else f"{result['status'].upper()}: completed prefix retained; inspect archive failures before using results.",
                config.to_dict(),
            )
        except (ValueError, IncompleteWeather) as exc:
            # Preserve the last complete run and explicitly report incomplete weather.
            return (
                gr.skip(),
                gr.skip(),
                gr.skip(),
                gr.skip(),
                gr.skip(),
                f"INCOMPLETE / NOT RUN: {exc}. Previous simulation remains displayed.",
                gr.skip(),
            )

    def replan_callback(result, evt: gr.EventData):
        data = evt._data
        if data.get("run_id") != result["run_id"]:
            return gr.skip()
        answer = what_if(result, data["controller"], int(data["hour"]), data["alternative"])
        # Echo the opaque client selection generation to reject a late response even
        # after navigating away and back to the same run/controller/hour.
        answer["key"] = data.get("key", answer["key"])
        return gr.HTML(answer=answer)

    def decision_detail_callback(result, evt: gr.EventData):
        data = evt._data
        if data.get("run_id") != result["run_id"]:
            return gr.skip()
        try:
            hour = int(data["hour"])
            if hour < 0:
                raise ValueError("Negative decision interval")
            row = result["records"][data["controller"]][hour]
        except (KeyError, ValueError, IndexError, TypeError):
            return gr.HTML(
                decision_answer={"key": data.get("key"), "error": "Decision unavailable"}
            )
        return gr.HTML(
            decision_answer={
                "key": data["key"],
                "controller": data["controller"],
                "hour": hour,
                "run_id": result["run_id"],
                "trajectory": row["decision"]["plan"]["trajectory"],
                "audits": row.get("audits", []),
                "battery_trace": battery_trace(result, data["controller"], hour),
                "component_traces": {
                    k: component_trace(result, data["controller"], hour, k)
                    for k in ("electrolyser", "hydrogen", "co2", "reactor", "solar")
                },
                "derived_trace": derived_trace(result, data["controller"], hour + 1),
                "economic_trace": economic_trace(
                    result,
                    data["controller"],
                    hour + 1,
                    Costs(**data["prices"]) if data.get("prices") else None,
                    service_economics=data.get(
                        "service_prices", result["config"].get("service_economics")
                    ),
                ),
            }
        )

    def solar_preview_callback(result, evt: gr.EventData):
        data = evt._data
        if data.get("run_id") != result["run_id"]:
            return gr.skip()
        try:
            response = solar_preview(result, data["design"])
        except (ValueError, KeyError, TypeError) as exc:
            response = {"error": str(exc)}
        return gr.HTML(solar_answer={**response, "key": data["key"]})

    def solar_run_callback(source, evt: gr.EventData, progress=gr.Progress()):  # noqa: B008
        data = evt._data
        if data.get("run_id") != source["run_id"]:
            return [gr.skip()] * (8 + len(widgets))
        try:
            design = validate_solar(data["design"])
            config_data = Config.from_dict(source["config"]).to_dict()
            config_data["solar"] = design
            config_data["plant"]["solar_kw"] = sum(s["capacity_kw"] for s in design["sections"])
            config = Config.from_dict(config_data)
            saved_weather = {
                **source["weather"],
                "solar_reference_config": source["weather"].get(
                    "solar_reference_config", source["config"]
                ),
            }
            result = run(config, weather=saved_weather, progress=progress)
            result["parent_run_id"] = source["run_id"]
            seal(result)
            return [
                result,
                gr.HTML(
                    value=wire_payload(playback_value(result)),
                    economics=wire_payload(reprice(result)),
                ),
                report(result),
                export(result),
                config.to_dict(),
                "Solar design applied in a new run using the same saved weather and forecast issues.",
                config.to_dict(),
                gr.Tabs(selected="operation"),
                *[setup_value(config_data, group, key) for group, key in widget_keys],
            ]
        except (ValueError, IncompleteWeather) as exc:
            return [
                gr.skip(),
                gr.HTML(solar_answer={"key": data["key"], "error": str(exc)}),
                *[gr.skip()] * (6 + len(widgets)),
            ]

    def price_callback(result, *values):
        cost_values = {
            key: value
            for (group, key), value in zip(widget_keys, values, strict=True)
            if group == "costs"
        }
        if any(value is None for value in cost_values.values()):
            raise gr.Error("Enter a numeric value for every cost assumption before repricing.")
        try:
            costs = Costs(**cost_values)
            service_prices = service_prices_from_values(values, result["config"])
            pricing = reprice(result, costs, service_economics=service_prices)
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc
        p = Plant(**result["config"]["plant"])
        updated = {
            **result,
            "metrics": {
                name: {
                    **result["metrics"][name],
                    **allocation(
                        p,
                        costs,
                        rows,
                        service_economics=service_prices,
                        service_prefix=result.get("service_accounting_prefix"),
                    ),
                }
                for name, rows in result["records"].items()
            },
        }
        return (
            gr.HTML(economics=wire_payload(pricing)),
            "Cost report repriced. Recorded actions and decision costs remain frozen; run again to change dispatch.",
            report(updated),
            export(result, costs, service_economics=service_prices),
        )

    def run_batch(config_dict, suite, request: gr.Request, progress=gr.Progress()):  # noqa: B008
        token = threading.Event()
        CANCELLATIONS[request.session_hash] = token
        try:
            for entries in batch(Config.from_dict(config_dict), suite, token, progress):
                path = RUNS / "batches" / f"ui-{request.session_hash}.json"
                path.write_text(json.dumps(entries, indent=2))
                yield markdown_report(entries), str(path)
        finally:
            CANCELLATIONS.pop(request.session_hash, None)

    def cancel_batch(request: gr.Request):
        token = CANCELLATIONS.get(request.session_hash)
        if not token:
            return "No batch is running for this session."
        token.set()
        return "Cancellation requested. The current interval finishes and remaining cases are recorded as cancelled."

    with gr.Blocks(title="Dispatch Lab / Autonomous methane") as demo:
        state = gr.State(default)
        run_config = gr.State(initial.to_dict())
        with gr.Tabs(selected="operation", elem_id="workspace-tabs") as screens:
            with gr.Tab("Plant simulation", id="operation"):
                scene = gr.HTML(
                    wire_payload(playback_value(default)),
                    economics=wire_payload(reprice(default)),
                    project_start=start_project,
                    answer=None,
                    decision_answer=None,
                    solar_answer=None,
                    html_template=(ASSETS / "methane.html")
                    .read_text()
                    .replace("<!-- SOLAR WORKSPACE -->", (ASSETS / "solar.html").read_text())
                    .replace("<!-- MODEL WORKSPACE -->", (ASSETS / "model.html").read_text())
                    .replace("<!-- TAXONOMY WORKSPACE -->", (ASSETS / "taxonomy.html").read_text())
                    .replace("<!-- STUDIES WORKSPACE -->", (ASSETS / "studies.html").read_text())
                    .replace("<!-- SITES WORKSPACE -->", (ASSETS / "sites.html").read_text())
                    .replace("<!-- PROJECT WORKSPACE -->", (ASSETS / "project.html").read_text()),
                    css_template=(ASSETS / "plant-scene.css").read_text()
                    + (ASSETS / "methane.css").read_text()
                    + (ASSETS / "field-scene.css").read_text()
                    + (ASSETS / "control-view.css").read_text()
                    + (ASSETS / "investigation.css").read_text()
                    + (ASSETS / "agent-control.css").read_text()
                    + (ASSETS / "solar.css").read_text()
                    + (ASSETS / "model.css").read_text()
                    + (ASSETS / "lifecycle.css").read_text()
                    + (ASSETS / "taxonomy.css").read_text()
                    + (ASSETS / "studies.css").read_text()
                    + (ASSETS / "sites.css").read_text()
                    + (ASSETS / "equipment.css").read_text()
                    + (ASSETS / "requirements.css").read_text()
                    + (ASSETS / "project.css").read_text()
                    + (ASSETS / "vendor/maplibre/maplibre-gl.css").read_text(),
                    js_on_load=(ASSETS / "playback.js").read_text().split("function frameAt")[0]
                    + (ASSETS / "field-operations.js").read_text()
                    + (ASSETS / "service-alternatives.js").read_text()
                    + (ASSETS / "control-view.js").read_text()
                    + (ASSETS / "investigation.js").read_text()
                    + (ASSETS / "agent-control.js").read_text()
                    + (ASSETS / "field-scene.js").read_text()
                    + (ASSETS / "methane.js").read_text()
                    + (ASSETS / "solar.js").read_text()
                    + (ASSETS / "lifecycle.js").read_text()
                    + (ASSETS / "model.js").read_text()
                    + (ASSETS / "taxonomy.js").read_text()
                    + (ASSETS / "studies.js").read_text()
                    + (ASSETS / "learning-lab.js").read_text()
                    + (ASSETS / "sites-studies.js").read_text()
                    + (ASSETS / "sites.js").read_text()
                    + (ASSETS / "literature.js").read_text()
                    + (ASSETS / "equipment.js").read_text()
                    + (ASSETS / "requirements.js").read_text()
                    + (ASSETS / "project.js").read_text()
                    + "\nmountMethane(element, props, watch, trigger);",
                    apply_default_css=False,
                    elem_id="methane-playback",
                )
                # HTML.__getattr__ treats any quoted JS word as a custom event.
                # Its unset constructor `inputs` can therefore become a bound
                # callback in get_config(), pulling the entire Blocks/state graph
                # into each root-response deepcopy. This value is not callable:
                # it has no reactive input components or custom `inputs` event.
                scene.inputs = None
            with gr.Tab(
                "Analysis", id="analysis", elem_id="analysis-screen", elem_classes="m-screen"
            ):
                with gr.Row(elem_classes="m-screen-toolbar"):
                    analysis_back = gr.Button("← Simulation", size="sm")
                    gr.Markdown("## Analysis")
                with gr.Tabs():
                    with gr.Tab("Run report"):
                        summary = gr.Markdown(report(default), elem_classes="methane-report")
                        archive = gr.File(
                            export(default), label="Download run and evidence", interactive=False
                        )
                        bundle_button = gr.Button("Prepare reproduction bundle")
                        bundle_file = gr.File(
                            label="Source, locked environment and offline playback",
                            interactive=False,
                        )
                    with gr.Tab("Experiments"):
                        gr.Markdown(
                            "Compare policies under the last run’s assumptions. Completed cases are reused; unsuccessful attempts remain in the evidence."
                        )
                        suite = gr.Dropdown(
                            [
                                ("18 synthetic experiments", "synthetic"),
                                ("9 historical windows", "historical"),
                                ("Diagnosis disabled / 18 cases", "ablation"),
                                ("Thermal sensitivity / 6 cases", "thermal"),
                            ],
                            value="synthetic",
                            label="Evidence suite",
                        )
                        with gr.Row():
                            batch_button = gr.Button("Run / resume suite")
                            cancel = gr.Button("Cancel suite")
                        batch_status = gr.Markdown("")
                        batch_report = gr.Markdown("", elem_classes="methane-report")
                        batch_file = gr.File(label="Batch results JSON", interactive=False)
                    with gr.Tab("Saved runs"):
                        saved_run = gr.File(file_types=[".gz"], label="Versioned methane JSON.gz")
                        restore = gr.Button("Load saved run")
                    with gr.Tab("Guide"):
                        gr.Markdown(
                            (
                                Path(__file__).resolve().parent.parent / "docs" / "guided-demo.md"
                            ).read_text()
                        )
            with gr.Tab(
                "Experiment setup", id="setup", elem_id="setup-screen", elem_classes="m-screen"
            ):
                with gr.Row(elem_classes="m-screen-toolbar"):
                    back = gr.Button("← Simulation", size="sm")
                    gr.Markdown("## Experiment setup")
                gr.Markdown(
                    "Start with the plant and scenario. Advanced settings expose the operating assumptions. Run all three policies against the same conditions."
                )
                preset = gr.Dropdown(
                    [
                        "Normal operation",
                        "Autonomy story / four days",
                        "Field services / no intervention",
                        "Field services / human only",
                        "Field services / repairable damage",
                        "Field services / resettable trip",
                        "Flow sensor bias",
                        "Delayed CO2 supply",
                    ],
                    value="Normal operation",
                    label="Start from a scenario",
                )
                with gr.Row():
                    with gr.Column():
                        gr.Markdown("### Plant size")
                        for key in (
                            "solar_kw",
                            "battery_kwh",
                            "electrolyser_kw",
                            "h2_capacity_kg",
                            "co2_capacity_kg",
                            "methane_max_kgph",
                        ):
                            parameter("plant", key)
                    with gr.Column():
                        gr.Markdown("### Conditions and control")
                        for key in (
                            "hours",
                            "horizon_hours",
                            "seed",
                            "forecast_bias",
                            "variability",
                        ):
                            parameter("scenario", key)
                        parameter("sensors", "enabled")
                    with gr.Column():
                        gr.Markdown("### Weather and location")
                        parameter("weather", "mode")
                        query = gr.Textbox(
                            label="Find a European location",
                            placeholder="London, Seville, Copenhagen…",
                        )
                        search = gr.Button("Search location")
                        locations = gr.Dropdown(label="Search results", choices=[])
                        location_state = gr.State([])
                        lat = parameter("weather", "latitude")
                        lon = parameter("weather", "longitude")
                        zone = parameter("weather", "timezone")
                        parameter("weather", "start")
                        parameter("weather", "offline")
                gr.Markdown(
                    "All default equipment values and prices are **illustrative assumptions**, not a calibrated industrial plant. Current forecasts are saved scenarios; historical truth is labelled ERA5 reanalysis. Start dates apply to synthetic and historical modes."
                )
                with gr.Accordion(
                    "Operating dynamics / storage, reactor and solar conversion", open=False
                ):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Electrical and hydrogen")
                            for component in ("battery", "electrolyser", "hydrogen"):
                                parameter("models", component)
                            for key in (
                                "battery_c_rate",
                                "min_load_fraction",
                                "start_energy_kwh",
                                "specific_energy_kwh_per_kg",
                                "roundtrip_efficiency",
                                "initial_soc",
                                "initial_h2_kg",
                            ):
                                parameter("plant", key)
                        with gr.Column():
                            gr.Markdown("### Methanator and feedstock")
                            for component in ("co2", "reactor"):
                                parameter("models", component)
                            for key in (
                                "initial_co2_kg",
                                "co2_delivery_kg",
                                "co2_delivery_every_hours",
                                "methane_min_kgph",
                                "temperature_min_c",
                                "temperature_max_c",
                                "thermal_capacity_kwh_per_k",
                                "heat_loss_kw_per_k",
                                "heater_max_kw",
                                "cooling_max_kw",
                                "auxiliary_kw",
                                "methane_electric_kwh_per_kg",
                                "cooling_electric_fraction",
                                "minimum_run_hours",
                            ):
                                parameter("plant", key)
                        with gr.Column():
                            gr.Markdown("### Solar and forecast conversion")
                            for key in (
                                "tilt",
                                "azimuth",
                                "loss_fraction",
                                "noct_c",
                                "temperature_coefficient",
                                "publication_lag_hours",
                            ):
                                parameter("weather", key)
                            gr.Markdown(
                                "UTC interval [t,t+1) uses radiation stamped t+1. Archived ECMWF issues refresh daily at 00 UTC, with a six-hour assumed publication lag. Current hourly mean PV is treated as measured; later realised weather is excluded from decisions."
                            )
                with gr.Accordion(
                    "Autonomy stress / injected faults and diagnostic assumptions", open=False
                ):
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("### Retrospective injected conditions")
                            parameter("faults", "lifecycle")
                            parameter("faults", "capacity_cause")
                            gr.Markdown(
                                "Persistent faults ignore duration and remain until successful service. A reset only clears a declared latched trip; it cannot repair damage or sensor bias. Timed transients represent temporary disturbances, not self-repair. Saved runs retain their original semantics."
                            )
                            for key in (
                                "fault_start_hour",
                                "fault_duration_hours",
                                "capacity_fraction",
                                "flow_bias_fraction",
                                "delivery_delay_hours",
                                "solver_seconds",
                            ):
                                parameter("scenario", key)
                        with gr.Column():
                            gr.Markdown("### Controller observations")
                            for key in (
                                "noise_fraction",
                                "discrepancy_fraction",
                                "confirmation_hours",
                                "probe_fraction",
                                "ambiguity_policy",
                            ):
                                parameter("sensors", key)
                            gr.Markdown(
                                "Capacity loss and flow-sensor bias are withheld from the controller. Electricity and independent inventory mass balance support bounded diagnosis. Battery, CO₂ and temperature channels are ideal sensors in this version."
                            )
                            gr.Markdown(
                                "The experimental ambiguity rule keeps the preceding capacity estimate without declaring health or recovery. It changes only that response; noise thresholds, confirmation and recovery timing are unchanged."
                            )
                            recovery_enabled = parameter("recovery_policy", "enabled")
                            with gr.Group(
                                visible=initial.recovery_policy is not None
                            ) as recovery_options:
                                gr.Markdown(
                                    "Reserve consecutive load tests using the original forecast and two explicit delivery hypotheses. This applies to all production strategies; Greedy uses an MPC subplanner during test episodes. A performed repair does not confirm recovery. Probabilities and reserves below are illustrative assumptions."
                                )
                                for key in (
                                    "version",
                                    "maximum_wait_hours",
                                    "retry_after_hours",
                                    "battery_reserve_fraction",
                                    "tracking_success_probability",
                                    "risk_weight",
                                ):
                                    parameter("recovery_policy", key)
                            recovery_enabled.change(
                                lambda enabled: gr.update(visible=enabled),
                                [recovery_enabled],
                                [recovery_options],
                                queue=False,
                            )
                with gr.Accordion(
                    "Field operations / robots, recovery and human service", open=False
                ):
                    gr.Markdown(
                        "Optional versioned service layer. Specifications and costs are illustrative. Choose legacy or fractional work, lumped or section-level cleaning, and declared inspection and recovery capabilities below. Observations and restored capability become available at the next plant decision boundary."
                    )
                    parameter("field_operations", "enabled")
                    service_execution = parameter("service_system", "implementation")
                    coordinated_enabled = parameter("service_policy", "enabled")
                    with gr.Group(
                        visible=initial.service_policy is not None
                    ) as coordinated_options:
                        gr.Markdown(
                            "MPC chooses compatible work and charging alongside production; Greedy retains its local service rule. Requires enabled fractional services, finite logistics and complete activity-based accounting. Deadlines remain fixed, interrupted repairs have bounded retries, and unverified work stays visible. Version 2 also compares shared crew visits and requires visit bundling below. Each job retains separate verification; an interrupted visit can prevent later jobs. Predictions do not assume restored plant capacity."
                        )
                        for key in (
                            "version",
                            "maximum_wait_hours",
                            "retry_after_hours",
                            "maximum_repair_attempts",
                            "charging_wait_hours",
                            "robot_reserve_fraction",
                            "maximum_candidates",
                            "comparison_seconds",
                        ):
                            parameter("service_policy", key)
                        investigation_enabled = parameter("investigation_policy", "enabled")
                        with gr.Group(
                            visible=initial.investigation_policy is not None
                        ) as investigation_options:
                            gr.Markdown(
                                "Use returned contact evidence to choose a compatible remedy. Requires referenced contact sensing and measured service follow-up; nominated tests and recovery beliefs also require joint recovery tests. The default prior is illustrative: 50% resettable trip, 30% damage and 20% damage with a stuck contact. It is not learned fault incidence. The recovery belief carries declared procedure probabilities through actual observations; the other modes leave the static prior inapplicable after intervention. Recorded custom priors remain unchanged by these controls."
                            )
                            investigation_version = parameter("investigation_policy", "version")
                            for key in (
                                "mode",
                                "reader",
                                "minimum_restoration_probability",
                                "risk_weight",
                                "comparison_seconds",
                                "observation_wait_hours",
                            ):
                                parameter("investigation_policy", key)
                            belief_threshold = parameter(
                                "investigation_policy", "followup_impairment_probability"
                            )
                            investigation_version.change(
                                lambda version: gr.update(
                                    visible=version == "observed-service-investigation/3"
                                ),
                                [investigation_version],
                                [belief_threshold],
                                queue=False,
                            )
                        investigation_enabled.change(
                            lambda enabled: gr.update(visible=enabled),
                            [investigation_enabled],
                            [investigation_options],
                            queue=False,
                        )
                    coordinated_enabled.change(
                        lambda enabled: gr.update(visible=enabled),
                        [coordinated_enabled],
                        [coordinated_options],
                        queue=False,
                    )
                    service_matching = parameter("service_system", "outcome_randomness")
                    service_execution.change(
                        lambda implementation: gr.update(visible=implementation != "legacy/1"),
                        [service_execution],
                        [service_matching],
                        queue=False,
                    )
                    gr.Markdown(
                        "Referenced inspection uses a prepared 24 V contact test port and internal reader references. Reader faults below are retrospective scenario assumptions, withheld from the controller. Agreement cannot rule out a shared stuck contact."
                    )
                    with gr.Row():
                        with gr.Column():
                            for key in (
                                "inspection_model",
                                "inspection_interface",
                                "inspection_noise_v",
                                "inspection_delay_hours",
                                "inspection_zero_limit_v",
                                "inspection_span_tolerance_fraction",
                                "inspection_low_v",
                                "inspection_high_v",
                                "inspection_wait_hours",
                            ):
                                parameter("service_system", key)
                        with gr.Column():
                            for key in (
                                "inspection_fault_start_hour",
                                "contact_stuck",
                                "fixed_reader_offset_v",
                                "fixed_reader_drift_vph",
                                "fixed_reader_dropout",
                                "mobile_reader_offset_v",
                                "mobile_reader_drift_vph",
                                "mobile_reader_dropout",
                            ):
                                parameter("faults", key)
                    gr.Markdown(
                        "Fractional contracts offer the original lumped proxy or section optical cleaning, with separate replacement and calibration tasks. Declared access, contact-read errors, finite utilities and operating verification are recorded. Legacy runs keep their original semantics."
                    )
                    with gr.Row():
                        with gr.Column():
                            for key in (
                                "inspector",
                                "travel_hours",
                                "verification_hours",
                                "reset_hours",
                                "reader_kw",
                                "reset_kw",
                            ):
                                parameter("service_system", key)
                        with gr.Column():
                            for key in (
                                "contact_unreadable_probability",
                                "contact_error_probability",
                                "contact_max_age_hours",
                                "communications_available",
                                "crew_available",
                                "calibration_reference_available",
                                "calibration_kits",
                            ):
                                parameter("service_system", key)
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("Section cleaning / optional optical mechanism")
                            for key in (
                                "cleaning_model",
                                "cleaning_policy",
                                "cleaning_first_due_hour",
                                "cleaning_period_hours",
                                "area_m2_per_kw",
                                "cleaning_area_m2ph",
                                "initial_adhered_fraction",
                                "initial_damage_fraction",
                                "brush_life_m2",
                                "brush_initial_condition",
                                "row_accessible",
                                "work_failure_fraction",
                            ):
                                parameter("service_system", key)
                        with gr.Column():
                            gr.Markdown("Work conditions / declared assumptions")
                            for key in (
                                "environment_source",
                                "assumed_wind_mps",
                                "assumed_rain_mmph",
                                "cleaning_wind_limit_mps",
                                "cleaning_rain_limit_mmph",
                            ):
                                parameter("service_system", key)
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown("Support availability / hours from run origin")
                            for key in (
                                "support_model",
                                "crew_shift_start_hour",
                                "crew_shift_duration_hours",
                                "crew_period_hours",
                                "crew_travel_hours",
                                "visit_bundling_enabled",
                                "visit_max_jobs",
                                "crew_transfer_hours",
                                "crew_return_enabled",
                                "crew_return_pack_hours",
                                "crew_return_check_hours",
                                "crew_response_lead_hours",
                                "crew_hours_per_period",
                                "remote_hours_per_period",
                            ):
                                parameter("service_system", key)
                        with gr.Column():
                            gr.Markdown("Recovery and supervised return to work")
                            for key in (
                                "retrieval_enabled",
                                "retrieval_work_hours",
                                "robot_test_hours",
                                "robot_test_kw",
                                "robot_test_success_probability",
                                "equipment_recovery_enabled",
                                "remote_assistance_enabled",
                                "remote_wait_hours",
                                "remote_release_hours",
                                "remote_shift_start_hour",
                                "remote_shift_duration_hours",
                                "hardware_replacement_hours",
                                "hardware_spares",
                            ):
                                parameter("service_system", key)
                            for key in (
                                "hardware_model",
                                "service_fault_start_hour",
                                "cleaner_service_fault",
                                "rover_service_fault",
                                "dock_service_fault",
                                "portable_service_fault",
                            ):
                                parameter("faults", key)
                        with gr.Column():
                            gr.Markdown("Finite supplies and brush replacement")
                            for key in (
                                "replenishment_enabled",
                                "support_delivery_hours",
                                "store_capacity_kits",
                                "supplier_kits",
                                "delivery_batch_kits",
                                "brush_spares",
                                "brush_replacement_enabled",
                                "brush_change_hours",
                            ):
                                parameter("service_system", key)
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown(
                                "Portable cleaning / requires section optics and support logistics"
                            )
                            for key in (
                                "portable_cleaner",
                                "portable_area_m2ph",
                                "portable_setup_hours",
                                "portable_power_kw",
                                "portable_loose_removal",
                                "portable_adhered_removal",
                                "portable_adhered_threshold",
                                "portable_min_ambient_c",
                            ):
                                parameter("service_system", key)
                        with gr.Column():
                            gr.Markdown("Cleaning water / finite stock and typed supply")
                            for key in (
                                "portable_water_l_per_m2",
                                "portable_rinse_l",
                                "portable_water_capacity_l",
                                "portable_water_initial_l",
                                "portable_upstream_water_l",
                                "portable_water_delivery_l",
                            ):
                                parameter("service_system", key)
                    with gr.Row():
                        with gr.Column():
                            gr.Markdown(
                                "Scheduled routine work / requires finite support logistics. Completion does not imply repair or life extension."
                            )
                            for key in (
                                "maintenance_enabled",
                                "maintenance_target",
                                "maintenance_first_due_hour",
                                "maintenance_interval_hours",
                                "maintenance_work_hours",
                                "maintenance_kits",
                            ):
                                parameter("service_system", key)
                        with gr.Column():
                            gr.Markdown(
                                "Dock control electricity / upstream of the charging power stage. A full-rate grant is required; active charging remains solar-only."
                            )
                            parameter("service_system", "dock_standby_kw")
                    groups = {
                        "Capabilities and access": (
                            "cleaner_enabled",
                            "rover_enabled",
                            "reset_enabled",
                            "human_fallback",
                            "route_open",
                            "dock_available",
                        ),
                        "Cleaning and mission energy": (
                            "initial_soiling_fraction",
                            "soiling_per_day",
                            "cleaning_threshold",
                            "cleaning_removal_fraction",
                            "cleaner_battery_kwh",
                            "rover_battery_kwh",
                            "mission_power_kw",
                            "return_reserve_kwh",
                            "dock_kw",
                            "charging_efficiency",
                        ),
                        "Work and reliability": (
                            "cleaning_hours",
                            "inspection_hours",
                            "human_lead_hours",
                            "human_work_hours",
                            "service_kits",
                            "cleaning_kits",
                            "mission_failure_probability",
                            "repair_success_probability",
                        ),
                    }
                    with gr.Row():
                        for label, keys in groups.items():
                            with gr.Column():
                                gr.Markdown("### " + label)
                                for key in keys:
                                    parameter("field_operations", key)
                with gr.Accordion(
                    "Economic assumptions / component costs and decision value", open=False
                ):
                    gr.Markdown(
                        "Repricing updates the displayed cost report. Economic dispatch always retains the assumptions from its original run. New asset capital scales with the configured reference capacity; replaceable allowances are charged once using the larger of calendar and usage allocation."
                    )
                    groups = {
                        "Solar and battery": [
                            "solar_eur_per_kw",
                            "solar_years",
                            "battery_eur_per_kwh",
                            "battery_power_eur_per_kw",
                            "battery_calendar_years",
                            "battery_cycles",
                        ],
                        "Electrolyser and reactor": [
                            "electrolyser_eur_per_kw",
                            "stack_share",
                            "stack_calendar_years",
                            "stack_operating_hours",
                            "start_equivalent_hours",
                            "methanator_eur",
                            "reactor_replaceable_share",
                            "reactor_operating_hours",
                            "reactor_start_equivalent_hours",
                        ],
                        "Storage, input and methane value": [
                            "hydrogen_storage_eur",
                            "co2_storage_eur",
                            "methane_assets_years",
                            "co2_eur_per_kg",
                            "methane_eur_per_kg",
                            "water_litres_per_kg",
                            "water_eur_per_m3",
                            "consumables_eur_per_kg",
                        ],
                        "Field assets and running costs": [
                            "cleaner_eur",
                            "rover_eur",
                            "dock_eur",
                            "fixed_reader_eur",
                            "reset_eur",
                            "calibration_kit_eur",
                            "field_asset_years",
                            "field_replaceable_share",
                            "cleaner_wear_eur_per_hour",
                            "rover_wear_eur_per_hour",
                            "field_maintenance_eur_per_year",
                            "cleaning_kit_eur",
                            "human_service_eur_per_hour",
                        ],
                        "Shared plant and interventions": [
                            "other_equipment_years",
                            "installation_fraction",
                            "site_setup_eur",
                            "fixed_opex_eur_per_year",
                            "repair_eur_per_incident",
                            "visit_eur_per_incident",
                        ],
                    }
                    with gr.Row():
                        for label, keys in groups.items():
                            with gr.Column():
                                gr.Markdown(f"### {label}")
                                for key in keys:
                                    parameter("costs", key)
                    with gr.Group(elem_classes=["service-economic-assumptions"]):
                        gr.Markdown("### Complete service accounting")
                        service_toggle = parameter("service_economics", "enabled")
                        with gr.Group(
                            visible=True if initial.service_economics is not None else "hidden"
                        ) as service_editor:
                            gr.Markdown(
                                "Requires recorded finite logistics. Provision covers equipment, payload, references, replacement parts and scheduled maintenance for contracted/shared assets. Set their owned capital and wear fields to zero. Site preparation, external consumables and labour remain separate. Blank prices are explicitly unpriced; totals then remain undefined."
                            )
                            with gr.Tabs():
                                with gr.Tab("Work and materials"):
                                    with gr.Row():
                                        with gr.Column():
                                            for key in (
                                                "crew_eur_per_hour",
                                                "remote_eur_per_hour",
                                                "callout_eur",
                                                "vehicle_eur_per_travel_hour",
                                            ):
                                                parameter("service_economics", "rates." + key)
                                        with gr.Column():
                                            from methane.service_economics import illustrative

                                            for key in illustrative(Costs())["materials"]:
                                                parameter(
                                                    "service_economics",
                                                    "materials." + key + ".eur_per_unit",
                                                )
                                    parameter("service_economics", "initial_asset_purchase")
                                    parameter("service_economics", "initial_stock_purchase")
                                    parameter("service_economics", "basis")
                                    parameter("service_economics", "source")
                                from methane.service_economics import (
                                    ASSETS as SERVICE_ASSETS,
                                )
                                from methane.service_economics import (
                                    AssetPrice,
                                )

                                for asset in SERVICE_ASSETS:
                                    with gr.Tab(asset.replace("_", " ").capitalize()):
                                        asset_widgets = {}
                                        with gr.Row():
                                            for half in (
                                                list(fields(AssetPrice))[:8],
                                                list(fields(AssetPrice))[8:],
                                            ):
                                                with gr.Column():
                                                    for f in half:
                                                        asset_widgets[f.name] = parameter(
                                                            "service_economics",
                                                            "assets." + asset + "." + f.name,
                                                        )
                                        covered = (
                                            "capital_eur",
                                            "replaceable_capital_eur",
                                            "wear_eur_per_hour",
                                            "scheduled_maintenance_eur_per_year",
                                            "payload_eur",
                                            "references_eur",
                                        )

                                        def provision_values(mode, covered=covered):
                                            return [
                                                gr.update(
                                                    value=None
                                                    if mode == "owned" and k == "capital_eur"
                                                    else 0,
                                                    interactive=mode == "owned",
                                                )
                                                for k in covered
                                            ]

                                        asset_widgets["provision"].input(
                                            provision_values,
                                            [asset_widgets["provision"]],
                                            [asset_widgets[k] for k in covered],
                                            queue=False,
                                        )
                        service_toggle.change(
                            lambda enabled: gr.update(visible=True if enabled else "hidden"),
                            [service_toggle],
                            [service_editor],
                            queue=False,
                        )
                    reprice_button = gr.Button("Reprice completed run")
                with gr.Row():
                    run_button = gr.Button("RUN EXPERIMENT →", variant="primary")
                status = gr.Markdown(
                    "Run assumptions are frozen. Edit setup and run again to apply changes."
                )
                with gr.Accordion("Configuration / exact reproducible values", open=False):
                    config_json = gr.JSON(initial.to_dict())
        preset_keys = [
            "hours",
            "forecast_bias",
            "capacity_fraction",
            "flow_bias_fraction",
            "delivery_delay_hours",
            "fault_start_hour",
            "fault_duration_hours",
        ]
        preset_outputs = [widgets[widget_keys.index(("scenario", key))] for key in preset_keys]
        preset_outputs += [
            widgets[widget_keys.index(pair)]
            for pair in (
                ("faults", "lifecycle"),
                ("faults", "capacity_cause"),
                ("field_operations", "enabled"),
                ("field_operations", "cleaner_enabled"),
                ("field_operations", "rover_enabled"),
                ("field_operations", "reset_enabled"),
                ("field_operations", "human_fallback"),
            )
        ]

        def apply_preset(name):
            values = {
                "hours": 72,
                "forecast_bias": 0,
                "capacity_fraction": 1,
                "flow_bias_fraction": 0,
                "delivery_delay_hours": 0,
                "fault_start_hour": 34,
                "fault_duration_hours": 12,
            }
            if name == "Autonomy story / four days":
                values.update(hours=96, forecast_bias=0.35, capacity_fraction=0.5)
            elif name == "Flow sensor bias":
                values["flow_bias_fraction"] = 0.4
            elif name == "Delayed CO2 supply":
                values["delivery_delay_hours"] = 24
            field = name.startswith("Field services")
            if field:
                values.update(hours=96, capacity_fraction=0.5, fault_start_hour=10)
            cause = "resettable-trip" if name.endswith("resettable trip") else "equipment-damage"
            robots = name not in ("Field services / no intervention", "Field services / human only")
            human = name != "Field services / no intervention"
            return [values[key] for key in preset_keys] + [
                "persistent",
                cause,
                field,
                robots,
                robots,
                robots,
                human,
            ]

        preset.change(apply_preset, preset, preset_outputs, queue=False, api_name=False)

        def bundle_callback(result):
            from methane.bundle import make

            return str(make(result, RUNS / (result["run_id"] + "-reproduction.zip")))

        bundle_button.click(
            bundle_callback, state, bundle_file, concurrency_limit=1, api_name="export_reproduction"
        )
        scene.select(
            decision_detail_callback,
            state,
            scene,
            api_name="inspect_decision",
            queue=False,
            show_progress="hidden",
        )
        scene.submit(
            replan_callback,
            state,
            scene,
            api_name="replan_decision",
            show_progress="hidden",
            concurrency_limit=1,
            concurrency_id="interactive-replan",
        )
        scene.input(
            solar_preview_callback,
            state,
            scene,
            api_name="preview_solar",
            queue=False,
            show_progress="hidden",
        )
        scene.apply(
            solar_run_callback,
            state,
            [state, scene, summary, archive, run_config, status, config_json, screens, *widgets],
            api_name="apply_solar_design",
            concurrency_limit=1,
        )
        scene.edit(
            lambda: gr.Tabs(selected="setup"),
            outputs=screens,
            queue=False,
            api_name=False,
            show_progress="hidden",
        )
        scene.expand(
            lambda: gr.Tabs(selected="analysis"),
            outputs=screens,
            queue=False,
            api_name=False,
            show_progress="hidden",
        )
        for return_button in (back, analysis_back):
            return_button.click(
                lambda: gr.Tabs(selected="operation"), outputs=screens, queue=False, api_name=False
            ).then(
                fn=None,
                js="() => requestAnimationFrame(() => document.querySelector('.m-menu-toggle')?.focus())",
            )
        run_button.click(
            simulate,
            [state, *widgets],
            [state, scene, summary, archive, screens, status, run_config],
            api_name="simulate_methane",
            concurrency_limit=1,
        ).then(lambda c: c, run_config, config_json)
        reprice_button.click(
            price_callback,
            [state, *widgets],
            [scene, status, summary, archive],
            api_name="reprice_methane",
        )
        batch_button.click(
            run_batch,
            [run_config, suite],
            [batch_report, batch_file],
            api_name="batch_methane",
            concurrency_limit=1,
            concurrency_id="batch",
        )
        cancel.click(cancel_batch, outputs=batch_status, queue=False, api_name=False)

        def lookup(text):
            matches = search_locations(text)
            choices = [
                (f"{x['name']}, {x.get('country', '')}", str(i)) for i, x in enumerate(matches)
            ]
            return gr.Dropdown(choices=choices, value=None), matches

        search.click(lookup, query, [locations, location_state])

        def choose(index, matches):
            if index is None:
                return gr.skip(), gr.skip(), gr.skip()
            item = matches[int(index)]
            return item["latitude"], item["longitude"], item.get("timezone", "Europe/London")

        locations.change(choose, [locations, location_state], [lat, lon, zone])

        def restore_run(path):
            r = load(path)
            editable = Config.from_dict(r["config"]).to_dict()
            if not any(r["records"].values()):
                raise gr.Error(
                    "This archive has no completed intervals. Its cancellation remains in the batch report."
                )
            return (
                r,
                gr.HTML(value=wire_payload(playback_value(r)), economics=wire_payload(reprice(r))),
                report(r),
                export(r),
                r["config"],
                "Saved run and its editable setup values restored.",
                r["config"],
                *[setup_value(editable, group, key) for group, key in widget_keys],
            )

        restore.click(
            restore_run,
            saved_run,
            [state, scene, summary, archive, run_config, status, config_json, *widgets],
        )

        def replay_study(current, evt: gr.EventData):
            from methane import studies

            request = evt._data
            if request.get("run_id") != current["run_id"]:
                return tuple(gr.skip() for _ in range(7 + len(widgets)))
            if request.get("kind") == "control-session":
                from methane.control_sessions import recording

                r = recording(request["session_id"], request["owner_key"])
            elif request.get("kind") == "site-study":
                from methane.siting.production import entries, load_period
                from methane.siting.store import Store

                site_store = Store()
                admitted = entries(site_store, request["edition_id"], request["case_id"])
                if request["period_sha256"] not in {e["period_sha256"] for e in admitted}:
                    raise gr.Error("Period does not belong to this site study case")
                r = load_period(site_store, request["period_sha256"])
            else:
                entry = studies.entry_for(
                    request["edition_id"], request["case_id"], attempt_id=request.get("attempt_id")
                )
                r = studies.archive_for(request["edition_id"], entry)
            name, hour = request["controller"], int(request["hour"])
            if name not in r["records"] or not 0 <= hour < len(r["records"][name]):
                raise gr.Error("This study interval is not available for recorded playback")
            editable = Config.from_dict(r["config"]).to_dict()
            view = playback_value(r)
            view["study_origin"] = {
                k: request.get(k)
                for k in (
                    "edition_id",
                    "case_id",
                    "controller",
                    "hour",
                    "component",
                    "report_id",
                    "kind",
                )
            }
            if request.get("kind") == "control-session":
                view.pop("study_origin", None)
            return (
                r,
                gr.HTML(value=wire_payload(view), economics=wire_payload(reprice(r))),
                report(r),
                export(r),
                r["config"],
                "Recorded run opened; no decisions recomputed.",
                r["config"],
                *[setup_value(editable, group, key) for group, key in widget_keys],
            )

        scene.retry(
            replay_study,
            state,
            [state, scene, summary, archive, run_config, status, config_json, *widgets],
            api_name="replay_study_case",
            queue=False,
            show_progress="hidden",
        )
    # Catch accidental omission of editable fields during UI development.
    for group, cls in (
        ("models", Models),
        ("service_system", ServiceSystem),
        ("plant", Plant),
        ("costs", Costs),
        ("sensors", Sensors),
        ("faults", FaultPolicy),
        ("scenario", Scenario),
        ("weather", WeatherConfig),
    ):
        missing = (
            {f.name for f in fields(cls)}
            - {key for g, key in widget_keys if g == group}
            - {"dt_hours"}
        )
        if group == "plant":
            # Structured interfaces are edited in Equipment & evidence and retained
            # by config_from_values when ordinary setup fields change.
            missing -= {"integration"}
        if group == "service_system":
            # These execution factors are edited with their required public bounds
            # in Studies → uncertainty, never as unqualified ordinary setup values.
            from methane.services.uncertain_timing import PATHS

            missing -= {p.split(".")[1] for p in PATHS}
        if missing:
            raise ValueError(f"Missing editable fields in {group}: {sorted(missing)}")
    return demo
