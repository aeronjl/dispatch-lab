"""Matched field-study resolution and descriptive reporting, without execution truth.

Each arm is a separate numerical run: hardware changes cannot share one plant
configuration. The study engine retains source, inputs, attempts and publication.
This resolver accepts data patches, never executable scenario code.
"""

import copy
import json
import math
import re

from methane.policy import Policy
from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE, digest

SCHEMA = "dispatch-lab/study-protocol/2"
RESOLVER = "matched-field-workflow/1"
REPORTING = "field-study-reporting/5"
RESTORATION_COUNT = (
    "Ended reset, module replacement, flow calibration or hardware replacement procedures "
    "without recorded operating acceptance. Includes the executive's awaiting-verification "
    "state; does not assert physical success. Summaries without field-period outcomes retain "
    "their legacy count of completed-status tasks without acceptance."
)
BASIS_GROUPS = ("plant", "models", "sensors", "solar", "costs")
ARM_GROUPS = ("field_operations", "service_system", "service_economics")
ENVIRONMENT = {
    "field_operations": ("enabled", "initial_soiling_fraction", "soiling_per_day"),
    "service_system": (
        "outcome_randomness",
        "cleaning_model",
        "area_m2_per_kw",
        "initial_adhered_fraction",
        "initial_damage_fraction",
        "environment_source",
        "assumed_wind_mps",
        "assumed_rain_mmph",
    ),
}
REPORT_METRICS = {
    "capacity_restored_hour": "Physical capacity restored / hour",
    "capacity_confirmed_hour": "Post-restoration confidence available / hour",
    "recovery_confirmation_delay_hours": "Post-restoration confirmation delay / h",
    "recovery_probe_hours": "Requested load-test intervals / h",
    "recovery_deadline_misses": "Legacy scheduler test deadlines missed (versions 1–2)",
    "recovery_verification_windows": "Post-mission verification windows opened",
    "recovery_verification_deadline_misses": "Post-mission verification windows expired",
    "recovery_observer_confirmed_windows": "Observer-confirmed verification windows",
    "recovery_escalation_hours": "Recovery escalation intervals / h",
    "recovery_candidate_solves": "Recovery window solves",
    "service_fallback_intervals": "Service fallback intervals",
    "service_candidate_solves": "Service candidate solves",
    "service_missed_work_deadlines": "Missed original service deadlines",
    "service_repair_retries": "Repair retries after observed interruption",
    "soiling_loss_kwh": "Soiling loss / kWh",
    "curtailed_kwh": "Plant curtailment / kWh",
    "converter_clipped_kwh": "Converter clipping / kWh",
    "cleaning_treated_m2": "Area treated / m²",
    "cleaning_full_passes": "Full cleaning passes",
    "cleaning_water_l": "Cleaning water / L",
    "contact_usable_decision_hours": "Usable contact evidence / decision h",
    "contact_first_usable_hour": "First usable contact / hour from origin",
    "dock_unserved_kwh": "Unserved dock controls / kWh",
    "routine_completed": "Routine procedures completed",
    "site_visits": "Site visits",
    "crew_hours": "Committed crew / h",
    "remote_hours": "Remote supervision / h",
    "unfinished_orders": "Unfinished work orders",
    "completed_unverified_orders": "Ended restoration procedures awaiting verification",
    "fault_active_hours": "Physical fault active / h",
    "service_expenditure_eur": "Service expenditure / €",
    "service_allocated_eur": "Allocated service / €",
    "service_decision_eur": "Action-dependent service / €",
}


def solar_design(config, transform):
    """Explicit common design transform, with every resolved input archived."""
    if (
        not isinstance(transform, dict)
        or not transform
        or set(transform) - {"converter_fraction", "capacity_factor"}
    ):
        raise ValueError("Solar study transform supports converter_fraction and capacity_factor")
    for value in transform.values():
        if (
            isinstance(value, bool)
            or not isinstance(value, (int, float))
            or not math.isfinite(value)
            or value <= 0
        ):
            raise ValueError("Solar transform operands must be finite and positive")
    if "capacity_factor" in transform:
        factor = transform["capacity_factor"]
        config["plant"]["solar_kw"] *= factor
        if config["solar"] is not None:
            for section in config["solar"]["sections"]:
                section["capacity_kw"] *= factor
            config["solar"]["converter_kw"] *= factor
    if "converter_fraction" not in transform:
        return
    if config["solar"] is None:
        from methane.config import Plant, WeatherConfig
        from methane.solar_model import default_design

        config["solar"] = default_design(
            Plant(**config["plant"]), WeatherConfig(**config["weather"])
        )
    config["solar"]["converter_kw"] = config["plant"]["solar_kw"] * transform["converter_fraction"]


def unique(items, label):
    ids = [item.get("id") for item in items]
    if not ids or any(not isinstance(k, str) or not re.fullmatch(r"[a-z0-9-]+", k) for k in ids):
        raise ValueError(f"{label} require nonempty stable identifiers")
    if len(ids) != len(set(ids)):
        raise ValueError(f"Duplicate {label} identifier")
    return ids


def patch(config, changes, *, scale=False):
    """Known paths only; replacements remain subject to complete Config validation."""
    if not isinstance(changes, dict):
        raise ValueError("Study patches must map parameter paths to values")
    for path, value in changes.items():
        parts = path.split(".")
        target = config
        for part in parts[:-1]:
            if not isinstance(target, dict) or part not in target:
                raise ValueError(f"Unknown study parameter: {path}")
            target = target[part]
        if not isinstance(target, dict) or parts[-1] not in target:
            raise ValueError(f"Unknown study parameter: {path}")
        if scale:
            before = target[parts[-1]]
            if any(
                isinstance(v, bool) or not isinstance(v, (int, float)) or not math.isfinite(v)
                for v in (before, value)
            ):
                raise ValueError(f"Study scaling requires finite numeric operands: {path}")
            value = before * value
        target[parts[-1]] = copy.deepcopy(value)


def matching_inputs(config):
    """The arm-varying service machinery is excluded; environmental loss is not."""
    return {
        **{
            k: config[k]
            for k in (
                "plant",
                "weather",
                "solar",
                "scenario",
                "sensors",
                "faults",
                "models",
                "rng_policy",
            )
        },
        **{group: {k: config[group][k] for k in keys} for group, keys in ENVIRONMENT.items()},
    }


def resolve(spec, basis, tier):
    from methane.studies import complete_config, differences

    if spec.get("schema_version") != SCHEMA or spec.get("resolver") != RESOLVER:
        raise ValueError("Unsupported named field-study resolver")
    declared_metrics = spec.get("report_metrics", [])
    if len(set(declared_metrics)) != len(declared_metrics) or any(
        k not in REPORT_METRICS for k in declared_metrics
    ):
        raise ValueError("Study report metrics must be distinct supported outcome identifiers")
    complete_config(spec["reference_config"])
    basis = complete_config(basis)
    if tier not in spec["tiers"]:
        raise ValueError("Unknown study tier")
    arm_ids = unique(spec["arms"], "arm")
    unique(spec["conditions"], "condition")
    if spec["baseline_arm"] not in arm_ids or len(arm_ids) < 2:
        raise ValueError("A field study needs a baseline and at least one distinct arm")
    settings = spec["tiers"][tier]
    variants = settings["variants"]
    unique(variants, "variant")
    seeds = settings["seeds"]
    if (
        not seeds
        or len(seeds) != len(set(seeds))
        or any(type(s) is not int or s < 0 for s in seeds)
    ):
        raise ValueError("Study seeds must be unique nonnegative integers")
    for p in spec["policies"].values():
        if json.loads(json.dumps(Policy(**p).to_dict())) != json.loads(json.dumps(p)):
            raise ValueError(
                "Field study policies must freeze every assumption; implicit defaults are not allowed"
            )
    base = copy.deepcopy(spec["reference_config"])
    for key in BASIS_GROUPS:
        base[key] = copy.deepcopy(basis[key])
    base["rng_policy"] = "named-channels/1"
    cases = []
    for variant in variants:
        for condition in spec["conditions"]:
            for seed in seeds:
                shared = copy.deepcopy(base)
                patch(shared, variant.get("scale", {}), scale=True)
                patch(shared, variant.get("patch", {}))
                patch(shared, condition.get("patch", {}))
                for authored in (variant, condition):
                    if "solar_design" in authored:
                        solar_design(shared, authored["solar_design"])
                shared["scenario"].update(
                    hours=settings["hours"],
                    horizon_hours=settings["horizon_hours"],
                    solver_seconds=settings["solver_seconds"],
                    seed=seed,
                )
                shared = complete_config(shared)
                match = digest(matching_inputs(shared))
                group_id = digest(
                    {
                        "protocol": digest(spec),
                        "variant": variant["id"],
                        "condition": condition["id"],
                        "seed": seed,
                        "inputs": match,
                    }
                )[:24]
                for arm in spec["arms"]:
                    changes = arm.get("patch", {})
                    if any(k.split(".")[0] not in ARM_GROUPS for k in changes):
                        raise ValueError(
                            "Field arms may change service hardware, policy settings and prices; shared plant/weather/fault conditions belong in variants or conditions"
                        )
                    config = copy.deepcopy(shared)
                    patch(config, changes)
                    if (
                        config["service_economics"] is None
                        or not config["field_operations"]["enabled"]
                    ):
                        raise ValueError(
                            "Field comparisons require the same enabled environmental mechanism and explicit complete service prices"
                        )
                    config = complete_config(config)
                    if digest(matching_inputs(config)) != match:
                        raise ValueError(
                            "An arm cannot change the shared environmental-loss mechanism or exogenous inputs"
                        )
                    controller = arm["controller"]
                    if controller not in spec["policies"]:
                        raise ValueError("Arm names an undefined controller policy")
                    policy = {controller: copy.deepcopy(spec["policies"][controller])}
                    cases.append(
                        {
                            "case_id": digest(
                                {
                                    "group": group_id,
                                    "arm": arm["id"],
                                    "config": config,
                                    "policies": policy,
                                }
                            )[:24],
                            "group_id": group_id,
                            "matching_inputs_hash": match,
                            "label": f"{condition['label']} · {variant['label']} · seed {seed} · {arm['label']}",
                            "condition": condition["id"],
                            "variant": variant["id"],
                            "seed": seed,
                            "arm_id": arm["id"],
                            "arm_label": arm["label"],
                            "controller": controller,
                            "policies": policy,
                            "config": config,
                            "changes_from_basis": differences(basis, config),
                        }
                    )
    return cases


def restoration_backlog(metrics, orders):
    """Derive procedure completion from public telemetry, never repair truth."""
    if not metrics.get("service_outcomes"):
        return sum(q["status"] == "completed" and q.get("verified_at_hour") is None for q in orders)
    return sum(
        q["kind"] in ("reset", "module-replacement", "flow-calibration", "hardware-replacement")
        and q["status"] in ("completed", "awaiting verification")
        and q.get("completed_hour") is not None
        and q.get("verified_at_hour") is None
        for q in orders
    )


def values(metrics):
    field = metrics.get("field_operations", {})
    views, quantities = field.get("views", {}), field.get("quantities", {})
    state = metrics.get("service_work") or {}
    orders = state.get("orders", [])
    return {
        **{
            k: metrics.get(k)
            for k in (
                "methane_kg",
                "curtailed_kwh",
                "forced_downtime_hours",
                "reactor_starts",
                "electrolyser_starts",
                "fault_active_hours",
                "detection_delay_hours",
                "false_alarms",
                "uncertain_hours",
                "field_energy_kwh",
                "soiling_loss_kwh",
                "utilisation",
                "total_eur",
                "assumed_contribution_eur",
                "limited_solves",
                "fallbacks",
                "capacity_restored_hour",
                "capacity_confirmed_hour",
                "recovery_confirmation_delay_hours",
                "recovery_probe_hours",
                "recovery_deadline_misses",
                "recovery_verification_windows",
                "recovery_verification_deadline_misses",
                "recovery_observer_confirmed_windows",
                "recovery_escalation_hours",
                "recovery_candidate_solves",
            )
        },
        **{
            k: (metrics.get("service_outcomes") or {}).get(k)
            for k in (
                "cleaning_treated_m2",
                "cleaning_full_passes",
                "cleaning_water_l",
                "converter_clipped_kwh",
                "contact_usable_decision_hours",
                "contact_first_usable_hour",
                "dock_unserved_kwh",
                "routine_completed",
            )
        },
        **{"ending_" + k: v for k, v in (metrics.get("ending") or {}).items()},
        **{
            "service_" + k: (metrics.get("service_control") or {}).get(k)
            for k in (
                "fallback_intervals",
                "candidate_solves",
                "missed_work_deadlines",
                "repair_retries",
            )
        },
        **{
            "service_" + k + "_eur": views.get(k, {}).get("total_eur")
            for k in ("allocated", "decision", "expenditure")
        },
        "site_visits": quantities.get("human_visits", 0),
        "crew_hours": quantities.get("crew-hours", 0),
        "remote_hours": quantities.get("remote-hours", 0),
        "unfinished_orders": sum(
            q["status"] not in ("completed", "verified", "cancelled") for q in orders
        ),
        "completed_unverified_orders": restoration_backlog(metrics, orders),
    }


def report(manifest, histories, withdrawn=None):
    spec = manifest["protocol"]
    cases, matched = [], {}
    for case in manifest["cases"]:
        attempts = histories.get(case["case_id"], [])
        entry = attempts[-1] if attempts else {"status": "pending"}
        row = {
            **case,
            "entry": entry,
            "attempts": [
                {k: a.get(k) for k in ("attempt_id", "status", "started_at", "error", "run_id")}
                for a in attempts
            ],
        }
        if entry.get("metrics") and case["controller"] in entry["metrics"]:
            row["outcomes"] = values(entry["metrics"][case["controller"]])
        cases.append(row)
        matched.setdefault(case["group_id"], {})[case["arm_id"]] = row
    comparisons, groups = [], {}
    for members in matched.values():
        baseline = members[spec["baseline_arm"]]
        for arm in spec["arms"]:
            if arm["id"] == spec["baseline_arm"]:
                continue
            candidate = members[arm["id"]]
            matched_inputs = (
                candidate["matching_inputs_hash"] == baseline["matching_inputs_hash"]
                and candidate.get("weather_hash") == baseline.get("weather_hash")
                and baseline.get("weather_hash") is not None
            )
            complete = all(c["entry"]["status"] == "complete" for c in (candidate, baseline))
            status = (
                "withdrawn"
                if withdrawn
                else "unmatched-inputs"
                if not matched_inputs
                else "complete"
                if complete
                else "incomplete"
            )
            item = {
                "group_id": baseline["group_id"],
                "condition": baseline["condition"],
                "variant": baseline["variant"],
                "seed": baseline["seed"],
                "arm_id": arm["id"],
                "arm_label": arm["label"],
                "baseline_case_id": baseline["case_id"],
                "candidate_case_id": candidate["case_id"],
                "status": status,
                "delta": {},
            }
            if status == "complete":
                item["delta"] = {
                    k: b - baseline["outcomes"][k]
                    if isinstance(b, (int, float))
                    and isinstance(baseline["outcomes"].get(k), (int, float))
                    else None
                    for k, b in candidate["outcomes"].items()
                }
                groups.setdefault((item["condition"], item["variant"], arm["id"]), []).append(item)
            comparisons.append(item)
    aggregate = []
    for (condition, variant, arm), rows in groups.items():
        metrics = {}
        for key in rows[0]["delta"]:
            available = [r["delta"][key] for r in rows if r["delta"][key] is not None]
            metrics[key] = {
                "available_pairs": len(available),
                "total_pairs": len(rows),
                "mean": sum(available) / len(available) if available else None,
                "range": [min(available), max(available)] if available else None,
            }
        aggregate.append(
            {
                "condition": condition,
                "variant": variant,
                "arm_id": arm,
                "pairs": len(rows),
                "metrics": metrics,
            }
        )
    completed = sum(c["entry"]["status"] == "complete" for c in cases)
    paired = sum(c["status"] == "complete" for c in comparisons)
    finding = (
        f"{paired} of {len(comparisons)} matched comparisons have complete physical traces. "
        "Differences below are each service arm minus the declared baseline. "
        "Costs with missing prices remain undefined; ending resources and outstanding work are retained."
    )
    return {
        "schema_version": "dispatch-lab/study-report/2",
        "edition_id": manifest["edition_id"],
        "manifest": manifest,
        "reporting": {
            "implementation_id": REPORTING,
            "source_hash": LOADED_SOURCE["content_hash"],
            "source_capsule_sha256": LOADED_CAPSULE["sha256"],
            "metric_definitions": {
                "completed_unverified_orders": RESTORATION_COUNT,
                "recovery": "Physical restoration is the first decision hour at nameplate after a retrospective capacity loss. Post-restoration confidence is the next decision boundary after a full-capacity estimate, following an observed derating. Missing restoration or confirmation leaves delay undefined. Probe intervals count actual requested tests. Deadline/solve counts are undefined for policies without a scheduled-test model. These are model outcomes, not empirical accuracy or certification.",
            },
            "scope": "Derived from recorded attempts; reporting source is separate from execution source.",
        },
        "status": "withdrawn"
        if withdrawn
        else "complete"
        if completed == len(cases) and paired == len(comparisons)
        else "incomplete",
        "completed_cases": completed,
        "total_cases": len(cases),
        "completed_pairs": paired,
        "total_pairs": len(comparisons),
        "cases": cases,
        "comparisons": comparisons,
        "aggregate": aggregate,
        "question_outcomes": [
            {
                "condition": g["condition"],
                "variant": g["variant"],
                "arm_id": g["arm_id"],
                "metric": k,
                "label": REPORT_METRICS[k],
                **g["metrics"][k],
            }
            for g in aggregate
            for k in spec.get("report_metrics", [])
        ],
        "finding": withdrawn["reason"] if withdrawn else finding,
        "interpretation_status": "Generated descriptive findings; no causal narrative review recorded",
        "scope": "Short model-based workflow evidence for these frozen configurations and random streams. No annual hardware value or empirical reliability is established.",
        "comparison_definition": spec["comparison"],
    }


def markdown(value):
    spec, manifest = value["manifest"]["protocol"], value["manifest"]
    fmt = lambda x: "Undefined" if x is None else f"{x:+.3f}"  # noqa: E731
    lines = [
        f"# {spec['title']}",
        "",
        spec["question"],
        "",
        "## Finding",
        "",
        value["finding"],
        "",
        f"{value['completed_cases']}/{value['total_cases']} complete cases. {value['interpretation_status']}.",
        "",
    ]
    if value.get("interpretation"):
        lines += [
            "## Interpretation",
            "",
            "\n\n".join(value["interpretation"]["paragraphs"]),
            "",
            value["interpretation"]["scope"],
            "",
        ]
    lines += [
        "## Across completed seeds",
        "",
        "| Condition / variant | Arm | Pairs | Mean Δ methane kg | Methane range kg | Mean Δ allocated € | Priced pairs |",
        "|---|---|---:|---:|---|---:|---:|",
    ]
    for group in value["aggregate"]:
        methane, cost = group["metrics"]["methane_kg"], group["metrics"]["total_eur"]
        extent = " to ".join(fmt(v) for v in methane["range"] or [])
        lines.append(
            f"| {group['condition']} / {group['variant']} | {group['arm_id']} | {group['pairs']} | {fmt(methane['mean'])} | {extent} | {fmt(cost['mean'])} | {cost['available_pairs']}/{cost['total_pairs']} |"
        )
    lines += [
        "",
        "Arithmetic means and observed ranges; conditions are not pooled and no confidence interval is inferred.",
        "",
    ]
    if value.get("question_outcomes"):
        lines += [
            "## Question-specific outcomes",
            "",
            "| Condition / variant | Arm | Outcome | Mean difference | Range | Available pairs |",
            "|---|---|---|---:|---|---:|",
        ]
        for row in value["question_outcomes"]:
            extent = " to ".join(fmt(x) for x in row["range"] or [])
            lines.append(
                f"| {row['condition']} / {row['variant']} | {row['arm_id']} | {row['label']} | {fmt(row['mean'])} | {extent} | {row['available_pairs']}/{row['total_pairs']} |"
            )
        lines += [
            "",
            "Each value is candidate minus baseline over the same period. Missing measurements or mechanisms remain undefined. These outcomes do not establish a unique cause of a production difference.",
            "",
        ]
    lines += [
        "## Method",
        "",
        spec["rationale"],
        "",
        spec["comparison"],
        "",
        spec["policy_tuning"],
        "",
        *[f"- **{k.replace('_', ' ')}:** {v}" for k, v in spec["resolution"].items()],
        "",
        f"Protocol revision {spec['revision']}; resolver {spec['resolver']}; tier {manifest['tier']}; source `{manifest['source_hash']}`.",
        "",
        *(
            [
                f"Reporting implementation `{value['reporting']['implementation_id']}`; reporting source `{value['reporting']['source_hash']}`. Numerical execution retains the source above.",
                "",
                value["reporting"]["metric_definitions"]["completed_unverified_orders"],
                "",
            ]
            if value.get("reporting")
            else []
        ),
        "## Matched outcomes",
        "",
        "| Condition / variant / seed | Arm | Status | Δ methane kg | Δ allocated € | Δ crew h | Δ outstanding orders |",
        "|---|---|---|---:|---:|---:|---:|",
    ]
    for c in value["comparisons"]:
        d = c["delta"]
        lines.append(
            f"| {c['condition']} / {c['variant']} / {c['seed']} | {c['arm_label']} | {c['status']} | "
            + " | ".join(
                fmt(d.get(k))
                for k in ("methane_kg", "total_eur", "crew_hours", "unfinished_orders")
            )
            + " |"
        )
    lines += ["", "## Every case", "", "| Case | Status | Attempts | Error |", "|---|---|---:|---|"]
    for c in value["cases"]:
        lines.append(
            f"| {c['label']} | {c['entry']['status']} | {len(c['attempts'])} | {str(c['entry'].get('error', '')).replace('|', '/')} |"
        )
    lines += [
        "",
        "## Limits",
        "",
        *[f"- {s}" for s in spec["limits"]],
        "",
        value["scope"],
        "",
        "## Reproduce or extend",
        "",
        "Each arm has its own complete configuration and archive. Weather bytes, fault and sensor seeds, prices, policies, executable source and attempts are frozen. Reproduction uses the original source; a different plant creates a new edition. Recorded playback never reruns decisions.",
        "",
    ]
    if value.get("computation"):
        from methane.computation_studies import markdown as computation_markdown

        lines += [computation_markdown(value["computation"])]
    return "\n".join(lines)
