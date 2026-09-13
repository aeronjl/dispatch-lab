"""Uncertainty experiments reuse immutable studies, workers, audits and exports."""

import copy
import math
import statistics

from methane.config import Config
from methane.provenance import digest
from methane.uncertainty import VERSION, catalogue, resolve

SCHEMA = "dispatch-lab/study-protocol/3"
METRICS = (
    "performance.one_step_pv_mae_kw",
    "performance.ending_solar_multiplier",
    "performance.solar_outside_support_hours",
    "methane_kg",
    "h2_produced_kg",
    "utilisation",
    "co2_rejected_kg",
    "field_energy_kwh",
    "soiling_loss_kwh",
    "fault_active_hours",
    "total_eur",
    "assumed_contribution_eur",
    "curtailed_kwh",
    "forced_downtime_hours",
    "reactor_starts",
    "electrolyser_starts",
    "false_alarms",
    "detection_delay_hours",
    "uncertain_hours",
    "limited_solves",
    "fallbacks",
    "ending.battery_kwh",
    "ending.h2_kg",
    "ending.co2_kg",
    "ending.temperature_c",
)


def default_spec(config):
    cat = catalogue(config)
    blocks = []
    for p in cat["parameters"]:
        if p["suggested_values"]:
            for path in p["values"]:
                blocks.append(
                    {
                        "id": path,
                        "paths": [path],
                        "kind": "values",
                        "rows": [[v] for v in p["suggested_values"]],
                        "visibility": "hidden" if p["hidden_supported"] else "disclosed",
                        "source": "assumption-review/" + cat["registry_edition"],
                        "rationale": p["suggestion_scope"],
                    }
                )
    return {
        "schema_version": VERSION,
        "seed": 20260913,
        "worlds": 40,
        "inner_seeds": [7, 17, 29],
        "design": "screening",
        "blocks": blocks,
        "measurements": {},
        "rationale": "Registered sensitivity assumptions, not calibrated confidence intervals. Matched one-block screening identifies priorities; interactions need a joint follow-up.",
    }


def protocol(basis=None, uncertainty=None):
    config = basis or Config().to_dict()
    return {
        "schema_version": SCHEMA,
        "study_id": "uncertainty",
        "revision": 1,
        "title": "Which assumptions change the decision?",
        "question": "Which controller conclusions survive uncertain plant, service, weather, observation and economic assumptions?",
        "rationale": "Separate persistent worlds from event seeds. Compare all policies within each world before combining results. Unknown capability and calibration gaps remain explicit.",
        "comparison": "Each case runs Greedy, methane MPC and economic MPC against the same physical world and seeded events. The controller receives its declared assumptions, never hidden sampled parameters.",
        "policy_tuning": "No fitting on evaluation outcomes. Solver limitations and fallbacks are reported per case.",
        "resolution": {
            "plant_basis": "Full chosen configuration, including enabled optional services",
            "variants": "Versioned explicit uncertainty blocks, resolved once before execution; invalid worlds retained",
        },
        "reference_config": copy.deepcopy(config),
        "uncertainty": uncertainty or default_spec(config),
        "tiers": {
            "reference": {
                "hours": config["scenario"]["hours"],
                "purpose": "User-authored uncertainty experiment",
                "solver_seconds": config["scenario"]["solver_seconds"],
            }
        },
        "policies": {
            "Greedy": {"objective": "greedy"},
            "MPC · methane": {"objective": "methane"},
            "MPC · economics": {"objective": "economics"},
        },
        "baseline_controller": "Greedy",
        "candidate_controller": "MPC · methane",
        "limits": [
            "Scenario ranges are observed extrema of evaluated cases, not coverage guarantees or confidence intervals.",
            "Probability summaries are conditional on the authored distributions, dependence assumptions and finite sample. They do not establish calibration.",
            "Unquantified assumptions remain fixed in a run and are listed as unresolved coverage, not assigned zero uncertainty.",
            "Selected conversion and service outcome parameters can be hidden. Opt-in autonomy adds six bounded private phase clocks and current-only support events. Other parameters without separate execution adapters remain rejected; estimator assumptions are explicit.",
            "Screening varies one dependent block at a time; it does not quantify interactions or a global variance decomposition.",
            "Shared random channels couple comparable external events. Usage-dependent work and failure exposure still follow each policy's actions.",
        ],
    }


def resolve_cases(spec, basis, tier):
    from methane.policy import Policy
    from methane.studies import differences

    if tier not in spec["tiers"]:
        raise ValueError("Unknown uncertainty study tier")
    worlds = resolve(spec["uncertainty"], basis)
    cases = []
    if len(worlds) * len(spec["uncertainty"]["inner_seeds"]) > 512:
        raise ValueError(
            "At most 512 world/event cases per edition; split larger experiments into explicit editions"
        )
    for world in worlds:
        for seed in spec["uncertainty"]["inner_seeds"]:
            realization = copy.deepcopy(world)
            for key in ("config", "controller_config"):
                realization[key]["scenario"]["seed"] = seed
                realization[key]["rng_policy"] = "named-channels/1"
            realization["event_seed"] = seed
            policy_config = basis if world["error"] else realization["controller_config"]
            policies = {}
            for name, base_policy in spec["policies"].items():
                fields = copy.deepcopy(base_policy)
                recovery = copy.deepcopy(policy_config.get("recovery_policy"))
                service = (
                    policy_config.get("service_policy") if fields["objective"] != "greedy" else None
                )
                investigation = (
                    policy_config.get("investigation_policy")
                    if fields["objective"] != "greedy"
                    else None
                )
                if (
                    recovery
                    and recovery["version"]
                    in (
                        "scheduled-load-tests/2",
                        "scheduled-load-tests/3",
                        "scheduled-load-tests/4",
                    )
                    and fields["objective"] == "greedy"
                ):
                    recovery["version"] = "scheduled-load-tests/1"
                if recovery or service:
                    fields.update(
                        version="dispatch-lab/policy/4"
                        if investigation
                        else "dispatch-lab/policy/3"
                        if service
                        else "dispatch-lab/policy/2",
                        recovery=recovery,
                        service=service,
                        investigation=investigation,
                    )
                policies[name] = Policy(**fields).to_dict()
            identifier = digest({"protocol": digest(spec), "world": realization})[:24]
            cases.append(
                {
                    "case_id": identifier,
                    "label": f"World {world['index'] + 1} · event seed {seed}",
                    "condition": "uncertainty",
                    "seed": seed,
                    "battery_factor": 1,
                    "config": realization["config"],
                    "uncertainty_world": realization,
                    "policies": policies,
                    "changes_from_basis": differences(basis, realization["config"]),
                    "input_error": world["error"],
                    "input_status": world["status"],
                }
            )
    return cases


def metric(values, path):
    for part in path.split("."):
        values = values.get(part) if isinstance(values, dict) else None
    return values if type(values) in (int, float) and math.isfinite(values) else None


def distribution(values, probability=False):
    if not values:
        return {"n": 0, "minimum": None, "maximum": None, "mean": None}
    answer = {
        "n": len(values),
        "minimum": min(values),
        "maximum": max(values),
        "mean": statistics.fmean(values),
    }
    if probability:
        import numpy as np

        answer["sample_quantiles"] = dict(
            zip(
                ("p05", "p50", "p95"),
                map(float, np.quantile(values, [0.05, 0.5, 0.95])),
                strict=True,
            )
        )
        answer["quantile_scope"] = (
            "Finite conditional sample quantiles, not confidence bounds or guaranteed coverage"
        )
    return answer


def report(manifest, histories, withdrawn=None):
    spec = manifest["protocol"]
    uspec = spec["uncertainty"]
    probability = uspec["design"] == "probability"
    baseline, candidate = spec["baseline_controller"], spec["candidate_controller"]
    cases, comparisons = [], []
    for case in manifest["cases"]:
        attempts = histories.get(case["case_id"], [])
        entry = attempts[-1] if attempts else {"status": "pending"}
        c = {
            **case,
            "entry": entry,
            "attempts": [
                {k: a.get(k) for k in ("attempt_id", "status", "started_at", "error", "run_id")}
                for a in attempts
            ],
        }
        if entry["status"] == "complete" and not withdrawn:
            a = entry["metrics"][baseline]
            c["delta"] = {
                "methane_kg": entry["metrics"][candidate]["methane_kg"] - a["methane_kg"],
                "battery_kwh": entry["metrics"][candidate]["ending"]["battery_kwh"]
                - a["ending"]["battery_kwh"],
                "forced_downtime_hours": entry["metrics"][candidate]["forced_downtime_hours"]
                - a["forced_downtime_hours"],
            }
            for name, b in entry["metrics"].items():
                if name == baseline:
                    continue
                comparisons.append(
                    {
                        "case_id": case["case_id"],
                        "world_id": case["uncertainty_world"]["world_id"],
                        "world_index": case["uncertainty_world"]["index"],
                        "seed": case["seed"],
                        "candidate": name,
                        "delta": {
                            k: metric(b, k) - metric(a, k)
                            if metric(b, k) is not None and metric(a, k) is not None
                            else None
                            for k in METRICS
                        },
                    }
                )
        cases.append(c)
    summaries = []
    for name in spec["policies"]:
        if name == baseline:
            continue
        rows = [r for r in comparisons if r["candidate"] == name]
        by_world = {}
        for r in rows:
            by_world.setdefault(r["world_id"], []).append(r)
        complete_worlds = {
            w: rs for w, rs in by_world.items() if len(rs) == len(uspec["inner_seeds"])
        }
        world_means = {
            k: [
                statistics.fmean(r["delta"][k] for r in rs)
                for rs in complete_worlds.values()
                if all(r["delta"][k] is not None for r in rs)
            ]
            for k in METRICS
        }
        summaries.append(
            {
                "candidate": name,
                "complete_pairs": len(rows),
                "complete_worlds": len(complete_worlds),
                "metrics": {
                    k: {
                        "paired_cases": distribution(
                            [r["delta"][k] for r in rows if r["delta"][k] is not None]
                        ),
                        "world_means": distribution(v, probability),
                    }
                    for k, v in world_means.items()
                },
                "rank_reversal": any(r["delta"]["methane_kg"] < -1e-5 for r in rows)
                and any(r["delta"]["methane_kg"] > 1e-5 for r in rows),
                "higher_methane_cases": sum(r["delta"]["methane_kg"] > 1e-5 for r in rows),
                "lower_methane_cases": sum(r["delta"]["methane_kg"] < -1e-5 for r in rows),
            }
        )
    screening = []
    if uspec["design"] == "screening":
        # Paired differences-of-differences with same exogenous seed and nominal world.
        for block in uspec["blocks"]:
            ids = {
                c["case_id"]
                for c in cases
                if any(d["block"] == block["id"] for d in c["uncertainty_world"]["draws"])
            }
            for name in spec["policies"]:
                base = {
                    r["seed"]: r["delta"]["methane_kg"]
                    for r in comparisons
                    if r["world_index"] == 0 and r["candidate"] == name
                }
                changes = [
                    r["delta"]["methane_kg"] - base[r["seed"]]
                    for r in comparisons
                    if r["case_id"] in ids and r["candidate"] == name and r["seed"] in base
                ]
                if changes:
                    screening.append(
                        {
                            "block": block["id"],
                            "candidate": name,
                            "matched_cases": len(changes),
                            "maximum_absolute_change_kg": max(map(abs, changes)),
                            "range_kg": [min(changes), max(changes)],
                        }
                    )
        screening.sort(key=lambda x: x["maximum_absolute_change_kg"], reverse=True)
    done = sum(c["entry"]["status"] == "complete" for c in cases)
    trajectory_ranges = {}
    for c in cases:
        if c["entry"]["status"] != "complete" or withdrawn:
            continue
        for name, rows in c["entry"].get("uncertainty_trajectory", {}).items():
            for row in rows:
                for key, value in row.items():
                    if key != "hour":
                        trajectory_ranges.setdefault(name, {}).setdefault(key, {}).setdefault(
                            row["hour"], []
                        ).append(value)
    trajectory_ranges = {
        name: {
            key: [
                {"hour": h, "minimum": min(v), "maximum": max(v), "cases": len(v)}
                for h, v in sorted(hours.items())
            ]
            for key, hours in outputs.items()
        }
        for name, outputs in trajectory_ranges.items()
    }
    selected = {p for b in uspec["blocks"] for p in b["paths"]}
    cat = catalogue(manifest["basis"])
    unresolved = [
        p["path"]
        for p in cat["parameters"]
        if p["active"]
        and p["representation"] in ("unquantified", "scenario-assumption", "scenario-values")
        and not any(path in selected for path in p["values"])
    ]
    finding = f"{done}/{len(cases)} world/event cases complete. " + (
        "Conditional probability experiment. "
        if probability
        else "Scenario experiment; no probabilities assigned to the resulting ranges. "
    )
    for summary in summaries:
        d = summary["metrics"]["methane_kg"]["paired_cases"]
        if d["n"]:
            finding += f"{summary['candidate']} minus {baseline}: methane differences {d['minimum']:+.2f} to {d['maximum']:+.2f} kg; {summary['complete_worlds']} worlds have every event seed complete. "
    return {
        "schema_version": "dispatch-lab/study-report/1",
        "edition_id": manifest["edition_id"],
        "manifest": manifest,
        "status": "withdrawn" if withdrawn else "complete" if done == len(cases) else "incomplete",
        "completed_pairs": done,
        "total_pairs": len(cases),
        "cases": cases,
        "aggregate": [],
        "finding": withdrawn["reason"] if withdrawn else finding,
        "interpretation_status": "Generated conditional comparisons; not empirical validation",
        "scope": "World means require all inner event seeds; paired-case summaries retain all complete pairs with their denominators. Neither represents unmodelled mechanisms. Invalid, failed or missing cases can bias complete-case distributions; inspect their counts before interpreting probability summaries. No output probabilities inferred from scenario counts.",
        "comparison_definition": "Candidate minus Greedy within identical world and event seed",
        "uncertainty": {
            "specification": uspec,
            "summaries": summaries,
            "comparisons": comparisons,
            "screening": screening,
            "unsampled_assumptions": unresolved,
            "catalogue_hash": cat["content_hash"],
            "trajectory_ranges": trajectory_ranges,
            "sampling_scope": "Between-block independence is assumed by probability sampling; use joint rows to preserve dependence. Screening ranking is measurement prioritisation, not a monetary value-of-information calculation.",
        },
    }


def markdown(value):
    u = value["uncertainty"]
    p = value["manifest"]["protocol"]
    lines = [
        f"# {p['title']}",
        "",
        value["finding"],
        "",
        value["scope"],
        "",
        "## Uncertainty and information",
        "",
        u["specification"]["rationale"],
        "",
        u["sampling_scope"],
        "",
        "| Block | Knowledge | Representation | Source |",
        "|---|---|---|---|",
    ]
    lines += [
        f"| {b['id']} | {b['visibility']} | {b['kind']} | {b['source']} |"
        for b in u["specification"]["blocks"]
    ]
    lines += [
        "",
        "## Matched outcomes",
        "",
        "| Candidate | Metric | Complete pairs | Observed difference range | Complete-world mean range |",
        "|---|---|---:|---|---|",
    ]
    for s in u["summaries"]:
        for metric_name, ds in s["metrics"].items():
            a, b = ds["paired_cases"], ds["world_means"]
            lines.append(
                f"| {s['candidate']} | {metric_name} | {a['n']} | {a['minimum']} to {a['maximum']} | {b['minimum']} to {b['maximum']} |"
            )
    lines += [
        "",
        "## Measurement priorities",
        "",
        "Matched one-block changes in controller methane advantage; interactions remain untested.",
        "",
    ]
    lines += [
        f"- {r['block']}, {r['candidate']}: up to {r['maximum_absolute_change_kg']:.3f} kg change ({r['matched_cases']} matched cases)."
        for r in u["screening"]
    ]
    lines += ["", "## Every case", "", "| Case | Status | Failure or limitation |", "|---|---|---|"]
    lines += [
        f"| {c['label']} | {c['entry']['status']} | {c['entry'].get('error') or c.get('input_error') or ''} |"
        for c in value["cases"]
    ]
    lines += [
        "",
        "## Unsampled assumptions",
        "",
        ", ".join(u["unsampled_assumptions"]),
        "",
        "## Limits",
        "",
    ]
    lines += ["- " + x for x in p["limits"]]
    lines += [
        "",
        "The reproduction bundle freezes every draw, controller assumption, event seed, source version and numerical attempt. Repricing a trace never changes its original dispatch assumptions.",
    ]
    return "\n".join(lines) + "\n"
