"""Read-only matched-comparison operands and scoped outcome descriptions.

No optimisation or model-state reconstruction. Repeated numerical runs are kept
separate from seed/scenario comparisons. Arithmetic deltas are not causal scores.
"""

from collections import defaultdict

from methane.autonomy_qualification import changed_paths

METRICS = (
    "methane_kg",
    "assumed_contribution_eur",
    "curtailed_kwh",
    "total_eur",
    "capacity_restored_hour",
    "capacity_confirmed_hour",
    "limited_solves",
    "fallbacks",
    "forced_downtime_hours",
    "uncertain_hours",
    "reactor_starts",
    "electrolyser_starts",
    "false_alarms",
    "detection_delay_hours",
    "recovery_confirmation_delay_hours",
    "recovery_probe_hours",
)


def compact(record):
    rows = record["timeline"]
    summary = record.get("summary") or {}
    max_capacity = record["config"]["plant"]["electrolyser_kw"]
    had_fault = any(r["truth_capacity_kw"] < max_capacity * 0.999 for r in rows)
    final_impaired = rows and rows[-1]["truth_capacity_kw"] < max_capacity * 0.999
    complete = record["hours"] == record["expected_hours"] and record.get("summary") is not None
    if not complete:
        outcome = "Incomplete exposure"
    elif final_impaired:
        outcome = "Capacity still impaired"
    elif had_fault and summary.get("capacity_confirmed_hour") is None:
        outcome = "Physical restoration; not confirmed"
    elif had_fault:
        outcome = "Restored and confirmed"
    else:
        outcome = "No simulated capacity loss"
    return {
        **{
            k: record.get(k)
            for k in (
                "study_id",
                "case_id",
                "source",
                "extractor_source",
                "controller",
                "environment_id",
                "group",
                "label",
                "physical_trace_hash",
                "executed_policy",
            )
        },
        "hours": record["hours"],
        "expected_hours": record["expected_hours"],
        "status": "complete" if complete else "incomplete",
        "outcome": outcome,
        "metrics": {k: summary.get(k) for k in METRICS},
        "ending": summary.get("ending"),
        "documentation_review": record.get("documentation_review"),
        "ending_services": record.get("field_terminal"),
        "products": summary.get("products"),
        "allocated_components": summary.get("components"),
        "service_economics": summary.get("field_operations"),
        "human_hours": sum(r["human_hours"] for r in rows),
        "human_visits": sum(r["human_visits"] for r in rows),
        "remote_hours": sum(r["remote_hours"] for r in rows),
        "final_estimate": rows[-1]["diagnosis"] if rows else None,
        "first_flow_isolation_hour": next(
            (r["hour"] + 1 for r in rows if r["diagnosis"].get("flow_isolated")), None
        ),
        "ending_true_flow_bias_fraction": rows[-1].get("truth_flow_bias_fraction")
        if rows
        else None,
        "checks": record.get("independent_check"),
        "periods": record["periods"],
        "evidence_scope": "Retrospective physical recovery and recorded diagnostic confirmation are different outcomes. Human work is disclosed; a restored asset is not evidence of autonomous physical repair.",
    }


def comparisons(records):
    groups = defaultdict(list)
    for r in records:
        label = r["label"]
        groups[(r["group"], label["pair"], label["seed"], label["repetition"])].append(r)
    out = []
    for key, cases in groups.items():
        baseline = cases[0]
        for alternative in cases[1:]:
            b, a = compact(baseline), compact(alternative)
            differences = changed_paths(baseline["config"], alternative["config"])
            policies = changed_paths(
                baseline.get("executed_policy"), alternative.get("executed_policy")
            )
            completed = a["status"] == b["status"] == "complete"
            out.append(
                dict(
                    group=key[0],
                    pair=key[1],
                    seed=key[2],
                    repetition=key[3],
                    baseline=b["case_id"],
                    alternative=a["case_id"],
                    baseline_arm=baseline["label"]["arm"],
                    alternative_arm=alternative["label"]["arm"],
                    same_environment=b["environment_id"] == a["environment_id"],
                    same_source=b["source"] == a["source"],
                    changed_config_paths=differences,
                    changed_policy_paths=policies,
                    complete=completed,
                    deltas={
                        m: a["metrics"][m] - b["metrics"][m]
                        if completed and a["metrics"][m] is not None and b["metrics"][m] is not None
                        else None
                        for m in METRICS
                    },
                    interpretation="Conditional recorded difference; not a causal attribution when multiple policy/configuration dimensions differ",
                )
            )
    return out


def numerical_spreads(records):
    groups = defaultdict(list)
    for r in records:
        label = r["label"]
        groups[(r["group"], label["pair"], label["seed"], label["arm"])].append(r)
    out = []
    for key, rows in groups.items():
        if len(rows) < 2:
            continue
        repetitions = [r["label"]["repetition"] for r in rows]
        if len(set(repetitions)) != len(rows):
            raise ValueError("Duplicate numerical repetitions cannot become independent evidence")
        identical_inputs = all(
            r["config"] == rows[0]["config"]
            and r["environment_id"] == rows[0]["environment_id"]
            and r.get("executed_policy") == rows[0].get("executed_policy")
            and r["source"] == rows[0]["source"]
            for r in rows
        )
        if not identical_inputs:
            raise ValueError("Numerical repeats have different frozen inputs/policies/source")
        valid = [r for r in rows if r.get("summary") and r["hours"] == r["expected_hours"]]
        spreads = {}
        for metric in METRICS:
            values = [r["summary"].get(metric) for r in valid]
            spreads[metric] = (
                max(values) - min(values)
                if len(valid) == len(rows) and values and all(v is not None for v in values)
                else None
            )
        out.append(
            dict(
                group=key[0],
                pair=key[1],
                seed=key[2],
                arm=key[3],
                repetitions=repetitions,
                completed=len(valid),
                declared=len(rows),
                exact_physical_trace_identity=len({r["physical_trace_hash"] for r in valid}) == 1
                if len(valid) == len(rows)
                else None,
                spreads=spreads,
            )
        )
    return out


def sensitivity_differences(records):
    groups = defaultdict(dict)
    for r in records:
        if r["group"] == "sensitivity":
            key = (r["label"]["seed"], r["controller"])
            condition = r["label"]["pair"]
            if condition in groups[key]:
                raise ValueError("Duplicate matched sensitivity case")
            groups[key][condition] = r
    out = []
    for (seed, controller), cases in groups.items():
        baseline = cases["reference"]
        for condition, candidate in cases.items():
            if condition == "reference":
                continue
            valid = all(
                r.get("summary") and r["hours"] == r["expected_hours"]
                for r in (baseline, candidate)
            )
            out.append(
                dict(
                    seed=seed,
                    controller=controller,
                    condition=condition,
                    baseline=baseline["case_id"],
                    alternative=candidate["case_id"],
                    complete=valid,
                    methane_delta=candidate["summary"]["methane_kg"]
                    - baseline["summary"]["methane_kg"]
                    if valid
                    else None,
                    contribution_delta=candidate["summary"]["assumed_contribution_eur"]
                    - baseline["summary"]["assumed_contribution_eur"]
                    if valid
                    else None,
                    changed_config_paths=changed_paths(baseline["config"], candidate["config"]),
                    same_environment=baseline["environment_id"] == candidate["environment_id"],
                    no_parameter_change=baseline["config"] == candidate["config"]
                    and baseline["environment_id"] == candidate["environment_id"],
                )
            )
    return out


def recovery_windows(record):
    """Necessary test-count screen, with an optimistic existing confirmation prefix.

    Applicable to the recorded fixed-increment v4 scheduler. This is not a
    feasibility proof: resource failures and intervening darkness can only add
    time, and no future observation or repair truth enters the calculation.
    """
    from math import ceil

    c = record["config"]
    if (c.get("recovery_policy") or {}).get("version") != "scheduled-load-tests/4":
        return []
    p, sensors = c["plant"], c["sensors"]
    nameplate = p["electrolyser_kw"]
    increment = nameplate * sensors["probe_fraction"]
    minimum = nameplate * p["min_load_fraction"]
    openings = {}
    for r in record["timeline"]:
        for opening in (r.get("recovery") or {}).get("deadline_openings", []):
            key = (opening["opened_at"], opening["available_boundary"])
            openings[key] = opening
    out = []
    for opening in openings.values():
        cap = opening["capacity_estimate_kw"]
        target = min(nameplate, max(minimum, cap + increment))
        steps = (
            0
            if cap >= nameplate * 0.999
            else 1 + max(0, ceil((nameplate - target - 1e-8) / increment))
        )
        # Even grant all but the last observation of the first step for free.
        lower_bound = 0 if steps == 0 else 1 + (steps - 1) * sensors["confirmation_hours"]
        duration = opening["due_hour"] - opening["opened_at"]
        out.append(
            dict(
                opened_at=opening["opened_at"],
                due_hour=opening["due_hour"],
                hard_deadline=opening["hard_deadline"],
                capacity_estimate_kw=cap,
                target_kw=target,
                configured_increase_kw=increment,
                required_increases=steps,
                optimistic_minimum_intervals=lower_bound,
                available_intervals=duration,
                shorter_than_test_count=duration < lower_bound,
                scope="Fixed-increment v4 test-count screen; optimistic first-step prefix, no assumption that resources or tracking will permit those tests",
            )
        )
    return out
