"""Controlled same-information solver/formulation experiments, separate from playback."""

import argparse
import hashlib
import json
import math
import os
import subprocess
import sys
import time
import warnings
from dataclasses import asdict
from pathlib import Path
from types import SimpleNamespace

import numpy as np
import scipy
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

from methane.battery import IMPLEMENTATIONS, from_plant
from methane.components import assemble
from methane.config import Config
from methane.dispatch import prepare_model
from methane.evidence import load
from methane.physics import ACTION_KEYS, State
from methane.provenance import LOADED_CAPSULE, digest, source_identity
from methane.reference import check_actions, interval

PROBLEM_SCHEMA = "dispatch-lab/frozen-milp/1"


def freeze_problem(model, context):
    """Save the complete linear problem, not an approximation reconstructed by a worker.

    Context must say whether these operands were captured during execution or
    reconstructed afterwards from a saved implementation and recorded inputs.
    Infinity strings occur only in bounds; coefficients remain finite JSON numbers.
    """

    def values(items):
        return [float(x) if math.isfinite(x) else str(float(x)) for x in items]

    problem = {
        "n": model.n,
        "ids": {k: v.tolist() for k, v in model.ids.items()},
        **{k: values(getattr(model, k)) for k in ("lower", "upper", "lo", "hi")},
        **{k: list(map(float, getattr(model, k))) for k in ("objective", "integer", "values")},
        **{k: list(map(int, getattr(model, k))) for k in ("rows", "cols")},
    }
    value = dict(schema_version=PROBLEM_SCHEMA, problem=problem, context=context)
    return {**value, "integrity_sha256": digest(value), "problem_sha256": digest(problem)}


def thaw_problem(value):
    if value.get("schema_version") != PROBLEM_SCHEMA:
        raise ValueError("Unsupported frozen problem")
    signed = {k: value[k] for k in ("schema_version", "problem", "context")}
    if (
        digest(signed) != value["integrity_sha256"]
        or digest(value["problem"]) != value["problem_sha256"]
    ):
        raise ValueError("Frozen problem identity mismatch")
    p = value["problem"]
    m = SimpleNamespace(
        n=p["n"],
        ids={k: np.asarray(v, dtype=int) for k, v in p["ids"].items()},
        **{
            k: np.asarray(p[k], dtype=float)
            for k in ("lower", "upper", "lo", "hi", "objective", "integer", "values")
        },
        rows=np.asarray(p["rows"], dtype=int),
        cols=np.asarray(p["cols"], dtype=int),
    )
    if any(not np.all(np.isfinite(getattr(m, k))) for k in ("objective", "integer", "values")):
        raise ValueError("Frozen coefficients must be finite")
    return m


def work_budget(value):
    """Study-only settings. Production dispatch defaults are deliberately unchanged."""
    if set(value) - {"time_limit_seconds", "node_limit", "relative_gap"}:
        raise ValueError("Unknown computation budget field")
    seconds = value.get("time_limit_seconds")
    gap = value.get("relative_gap", 0.001)
    nodes = value.get("node_limit")
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not math.isfinite(seconds)
        or seconds <= 0
    ):
        raise ValueError("A positive finite wall-clock watchdog is required")
    if (
        isinstance(gap, bool)
        or not isinstance(gap, (int, float))
        or not math.isfinite(gap)
        or not 0 <= gap < 1
    ):
        raise ValueError("Relative gap must be finite and in [0, 1)")
    if nodes is not None and (type(nodes) is not int or not 0 <= nodes <= 2_147_483_647):
        raise ValueError("Node limit must be a non-negative HiGHS integer")
    return dict(time_limit_seconds=float(seconds), node_limit=nodes, relative_gap=float(gap))


def solve_frozen(value, budget):
    """One isolated solver trial. Linear feasibility is not empirical validation."""
    m = thaw_problem(value)
    b = work_budget(budget)
    options = dict(
        time_limit=b["time_limit_seconds"], mip_rel_gap=b["relative_gap"], threads=1, random_seed=0
    )
    if b["node_limit"] is not None:
        options["node_limit"] = b["node_limit"]
    a = coo_matrix((m.values, (m.rows, m.cols)), shape=(len(m.lo), len(m.lower))).tocsc()
    load_before = list(os.getloadavg()) if hasattr(os, "getloadavg") else None
    begin = time.perf_counter()
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        result = milp(
            m.objective,
            integrality=m.integer,
            bounds=Bounds(m.lower, m.upper),
            constraints=LinearConstraint(a, m.lo, m.hi),
            options=options,
        )
    elapsed = time.perf_counter() - begin
    native = int(result.status)
    message = str(result.message)
    termination = {
        0: "optimal-within-tolerance",
        1: "limit-reached",
        2: "infeasible",
        3: "unbounded",
    }.get(native, "solver-error")
    if native == 1:
        if "time limit" in message.lower():
            termination = "time-limited"
        elif "iteration limit" in message.lower():
            termination = "iteration-limited"
        elif "solution limit" in message.lower():
            termination = "solution-limited"
    x = result.x
    valid_numbers = x is not None and np.all(np.isfinite(x))
    check = feasibility(m, x) if valid_numbers else None
    accepted = native in (0, 1) and check is not None and check["passed"]

    def optional(name):
        v = getattr(result, name, None)
        return float(v) if v is not None and np.isfinite(v) else None

    # SciPy vendors HiGHS; a separately installed highspy version is not its identity.
    try:
        from scipy.optimize._highspy import _core

        highs_version = _core._Highs().version()
    except (ImportError, AttributeError):
        highs_version = "unavailable"
    return dict(
        worker_source=source_identity()["content_hash"],
        problem_sha256=value["problem_sha256"],
        budget=b,
        options=options,
        native_status_code=native,
        termination=termination,
        message=message,
        seconds=elapsed,
        node_count=optional("mip_node_count"),
        objective_value=optional("fun"),
        objective_bound=optional("mip_dual_bound"),
        gap=optional("mip_gap"),
        linear_feasibility=check,
        accepted_incumbent=bool(accepted),
        vector=x.tolist() if valid_numbers else None,
        actions=[{k: float(x[m.ids[k][t]]) for k in ACTION_KEYS} for t in range(m.n)]
        if accepted
        else [],
        warnings=[str(w.message) for w in caught],
        environment=dict(
            python=sys.version,
            numpy=np.__version__,
            scipy=scipy.__version__,
            highs=highs_version,
            pid=os.getpid(),
            load_average_before=load_before,
            thread_environment={
                k: os.environ.get(k)
                for k in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS")
            },
        ),
        scope="Same frozen linear problem. Residual checks verify mathematical constraints, not independent physical correctness. No fallback is substituted for an unsuccessful trial.",
    )


def repeat_problem(path, out, budgets, repetitions):
    """Rotate budget order; retain every fresh-process trial, including watchdogs."""
    if type(repetitions) is not int or repetitions < 2:
        raise ValueError("Use at least two repetitions")
    path, out = Path(path).resolve(), Path(out).resolve()
    value = json.loads(path.read_text())
    thaw_problem(value)
    budgets = [work_budget(b) for b in budgets]
    if not budgets:
        raise ValueError("At least one computation budget is required")
    out.mkdir(parents=True, exist_ok=False)
    (out / "problem.json").write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")
    (out / "source-capsule.json").write_text(json.dumps(LOADED_CAPSULE) + "\n")
    source = source_identity()
    protocol = dict(
        schema_version="dispatch-lab/computation-repeat-protocol/1",
        budgets=budgets,
        repetitions=repetitions,
        problem_sha256=value["problem_sha256"],
        source=source,
        source_capsule_sha256=LOADED_CAPSULE["sha256"],
        scope="Controlled decision-level study, not a complete trajectory or service-candidate comparison. Fixed one-thread solver, seed 0; ambient machine load is observed, not controlled. Budget order rotates each repetition.",
    )
    (out / "protocol.json").write_text(json.dumps(protocol, indent=2) + "\n")
    rows = []
    for repetition in range(repetitions):
        for offset in range(len(budgets)):
            index = (repetition + offset) % len(budgets)
            b = budgets[index]
            name = f"repeat-{repetition:02d}-budget-{index:02d}"
            trial = out / (name + ".json")
            command = [
                sys.executable,
                "-m",
                "methane.solver_study",
                "--frozen-worker",
                str(out / "problem.json"),
                "--budget-json",
                json.dumps(b),
                "--worker-output",
                str(trial),
            ]
            env = {
                **os.environ,
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "DISPATCH_BATCH_WORKER": "1",
            }
            with (out / (name + ".log")).open("w") as log:
                try:
                    done = subprocess.run(
                        command,
                        env=env,
                        stdout=log,
                        stderr=log,
                        timeout=b["time_limit_seconds"] + 15,
                        check=False,
                    )
                    result = (
                        json.loads(trial.read_text())
                        if done.returncode == 0 and trial.exists()
                        else dict(
                            termination="worker-error",
                            accepted_incumbent=False,
                            returncode=done.returncode,
                        )
                    )
                except subprocess.TimeoutExpired:
                    result = dict(termination="external-watchdog", accepted_incumbent=False)
            result.update(repetition=repetition, budget_index=index)
            result["worker_source_matches"] = result.get("worker_source") == source["content_hash"]
            if result.get("accepted_incumbent") and not result["worker_source_matches"]:
                result["accepted_incumbent"] = False
                result["exclusion_reason"] = "Worker source changed during this protocol"
            rows.append(result)
            (out / "progress.json").write_text(
                json.dumps(
                    dict(completed=len(rows), total=repetitions * len(budgets), trials=rows),
                    indent=2,
                    allow_nan=False,
                )
                + "\n"
            )
            print(name, result["termination"], flush=True)
    groups = []
    for index, budget in enumerate(budgets):
        trials = [r for r in rows if r["budget_index"] == index]
        actions = [r["actions"] for r in trials if r["accepted_incumbent"]]
        first = [[a[0][k] for k in ACTION_KEYS] for a in actions]
        spread = (
            dict(zip(ACTION_KEYS, np.ptp(first, axis=0).tolist(), strict=True)) if first else None
        )
        groups.append(
            dict(
                budget=budget,
                completed=len(trials),
                accepted=len(actions),
                first_action_range=spread,
                all_first_actions_within_1e_minus4=bool(first)
                and len(actions) == len(trials)
                and max(spread.values()) <= 1e-4,
                exact_action_trajectories=len({digest(a) for a in actions}),
                objective_values=[r.get("objective_value") for r in trials],
                node_counts=[r.get("node_count") for r in trials],
                terminations=[r["termination"] for r in trials],
            )
        )
    report = dict(
        schema_version="dispatch-lab/computation-repeat-report/1",
        protocol=protocol,
        context=value["context"],
        trials=rows,
        budgets=groups,
        interpretation="Repeated solves use identical matrix, bounds and objective. Equal objective values do not imply equal actions. A node budget is measured work, not a cross-platform determinism guarantee. Missing/invalid incumbents and both watchdogs remain visible; no fallback is invented.",
    )
    (out / "report.json").write_text(json.dumps(report, indent=2, allow_nan=False) + "\n")
    lines = [
        "# Repeated frozen-decision solves",
        "",
        report["interpretation"],
        "",
        protocol["scope"],
        "",
        "| Time/watchdog s | Node limit | Accepted | Stable first action within 0.0001 | Distinct exact schedules | Terminations |",
        "|---:|---:|---:|---|---:|---|",
    ]
    for g in groups:
        b = g["budget"]
        lines.append(
            f"| {b['time_limit_seconds']} | {b['node_limit']} | {g['accepted']}/{g['completed']} | {g['all_first_actions_within_1e_minus4']} | {g['exact_action_trajectories']} | {', '.join(g['terminations'])} |"
        )
    lines += [
        "",
        "The JSON report preserves the complete vectors, residuals, objective bounds, native messages, load averages, actual bundled solver version and original problem context. This is one decision, not evidence of stable whole-run policy rankings.",
    ]
    (out / "report.md").write_text("\n".join(lines) + "\n")
    (out / "artifact-hashes.json").write_text(
        json.dumps(
            {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in sorted(out.iterdir())
                if p.is_file() and p.name != "artifact-hashes.json"
            },
            indent=2,
        )
        + "\n"
    )
    return report


def matrix(model):
    return coo_matrix(
        (model.values, (model.rows, model.cols)), shape=(len(model.lo), len(model.lower))
    ).toarray()


def equivalence(models):
    """Compare linear feasible sets after positive row scaling, with explicit tolerance."""
    normalized = []
    for m in models:
        a = matrix(m)
        scale = np.max(np.abs(a), axis=1)
        scale[scale == 0] = 1
        normalized.append((a / scale[:, None], np.asarray(m.lo) / scale, np.asarray(m.hi) / scale))
    same = all(
        np.array_equal(getattr(models[0], k), getattr(models[1], k))
        for k in ("lower", "upper", "integer", "objective")
    )
    same = same and all(
        np.allclose(a, b, rtol=1e-12, atol=1e-12) for a, b in zip(*normalized, strict=True)
    )
    return {
        "equivalent_within_tolerance": bool(same),
        "normalized_absolute_tolerance": 1e-12,
        "normalized_relative_tolerance": 1e-12,
        "variables": len(models[0].lower),
        "constraints": len(models[0].lo),
    }


def feasibility(m, x):
    if x is None:
        return None
    activity = matrix(m) @ x
    residual = max(
        float(np.max(np.maximum(m.lower - x, 0))),
        float(np.max(np.maximum(x - m.upper, 0))),
        float(np.max(np.maximum(np.asarray(m.lo) - activity, 0))),
        float(np.max(np.maximum(activity - np.asarray(m.hi), 0))),
        float(np.max(np.abs(x[m.integer == 1] - np.round(x[m.integer == 1])))),
    )
    return {"passed": residual <= 1e-5, "maximum_violation": residual, "tolerance": 1e-5}


def study(result, controller, hour, budgets=(0.5, 5.0)):
    c = Config.from_dict(result["config"])
    d = result["records"][controller][hour]["decision"]
    forecast = d["forecast"]
    models = [
        prepare_model(
            c.plant,
            State(**d["estimate"]),
            forecast,
            d["capacity_used_kw"],
            c.costs,
            d.get("planning_objective", d["policy"]),
            minimum_ely=d["capacity_used_kw"] if d["probe"] else 0,
            dependable_capacity=d["diagnosis"]["capacity_kw"] if d["probe"] else None,
            components=assemble(c.plant, c.models, battery_override=from_plant(c.plant, key)),
            terminal_battery_value=d.get("controller_policy", {}).get(
                "terminal_battery_value_kg_per_kwh", 0
            ),
        )
        for key in IMPLEMENTATIONS
    ]
    rows = []
    for budget in budgets:
        for key, m in zip(IMPLEMENTATIONS, models, strict=True):
            x, info = m.solve(budget)
            actions = (
                []
                if x is None
                else [{k: float(max(0, x[m.ids[k][t]])) for k in ACTION_KEYS} for t in range(m.n)]
            )
            checks = []
            state = dict(d["estimate"])
            methane = 0
            for t, action in enumerate(actions):
                reference = interval(
                    asdict(c.plant),
                    state,
                    action,
                    forecast["pv_kw"][t],
                    forecast["ambient_c"][t],
                    forecast["deliveries_kg"][t],
                )
                checks.extend(
                    check_actions(asdict(c.plant), state, reference, d["capacity_used_kw"])
                )
                methane += action["methane_kg"]
                state = reference["state"]
            rows.append(
                {
                    "implementation": key,
                    "budget_seconds": budget,
                    "solver": info,
                    "actions": actions,
                    "predicted_methane_kg": methane if actions else None,
                    "ending": state if actions else None,
                    "independent_physics_passed": all(a["passed"] for a in checks)
                    if actions
                    else None,
                    "cross_formulation_feasibility": {
                        other: feasibility(mm, x)
                        for other, mm in zip(IMPLEMENTATIONS, models, strict=True)
                    },
                }
            )
    bounds = [
        r["solver"].get("objective_bound")
        for r in rows
        if r["solver"].get("objective_bound") is not None
    ]
    strongest_lower = max(bounds) if bounds else None
    for row in rows:
        value = row["solver"].get("objective_value")
        row["absolute_gap_to_best_recorded_bound"] = (
            None if value is None or strongest_lower is None else max(0, value - strongest_lower)
        )
    return {
        "schema_version": "dispatch-lab/solver-study/1",
        "run_id": result["run_id"],
        "controller": controller,
        "hour": hour,
        "input_hash": digest(
            {
                "estimate": d["estimate"],
                "forecast": forecast,
                "costs": result["config"]["costs"],
                "capacity": d["capacity_used_kw"],
            }
        ),
        "same_information": {
            "estimate": d["estimate"],
            "forecast": forecast,
            "costs": result["config"]["costs"],
        },
        "formulations": equivalence(models),
        "solves": rows,
        "checker_source": source_identity(),
        "interpretation": "All solves use one recorded state, forecast and cost basis. Bounds apply to the same minimization objective, including tie-breaks. A longer budget is a reference attempt, not an optimality guarantee. Whole-run differences also compound changed subsequent state.",
    }


def first_divergence(first, second, controller):
    for i, (a, b) in enumerate(
        zip(first["records"][controller], second["records"][controller], strict=True)
    ):
        if any(abs(a["requested"][k] - b["requested"][k]) > 1e-4 for k in ACTION_KEYS):
            return i
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", nargs="?")
    parser.add_argument("--frozen-worker")
    parser.add_argument("--worker-output")
    parser.add_argument("--budget-json")
    parser.add_argument("--repeat-problem")
    parser.add_argument("--repetitions", type=int, default=5)
    parser.add_argument(
        "--work-budgets", help="JSON file containing a list of study computation budgets"
    )
    parser.add_argument("--other")
    parser.add_argument("--controller", default="MPC · methane")
    parser.add_argument("--hour", type=int)
    parser.add_argument("--budgets", type=float, nargs="+", default=[0.5, 5])
    parser.add_argument("--out", default="build/engineering/solver-study")
    args = parser.parse_args()
    if args.frozen_worker:
        if not args.worker_output or not args.budget_json:
            parser.error("A frozen worker requires --worker-output and --budget-json")
        result = solve_frozen(
            json.loads(Path(args.frozen_worker).read_text()), json.loads(args.budget_json)
        )
        Path(args.worker_output).write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
        return
    if args.repeat_problem:
        if not args.work_budgets:
            parser.error("A repeated problem requires --work-budgets")
        repeat_problem(
            args.repeat_problem,
            args.out,
            json.loads(Path(args.work_budgets).read_text()),
            args.repetitions,
        )
        return
    if not args.archive:
        parser.error("Provide an archive, or --repeat-problem with --work-budgets")
    result = load(args.archive)
    other = load(args.other) if args.other else None
    divergence = first_divergence(result, other, args.controller) if other else None
    hour = args.hour if args.hour is not None else (divergence or 0)
    report = study(result, args.controller, hour, tuple(args.budgets))
    if other:
        a = result["records"][args.controller][hour]["decision"]
        b = other["records"][args.controller][hour]["decision"]
        report["original_comparison"] = {
            "other_run_id": other["run_id"],
            "first_requested_action_divergence": divergence,
            "same_estimate_at_selected_hour": a["estimate"] == b["estimate"],
            "same_forecast_at_selected_hour": a["forecast"] == b["forecast"],
            "original_solvers": [a["plan"]["solver"], b["plan"]["solver"]],
            "whole_run_methane_kg": [
                result["metrics"][args.controller]["methane_kg"],
                other["metrics"][args.controller]["methane_kg"],
            ],
        }
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.with_suffix(".json").write_text(json.dumps(report, indent=2, allow_nan=False))
    lines = [
        "# Controlled battery solver comparison",
        "",
        report["interpretation"],
        "",
        f"Recorded decision: `{result['run_id']}` / {args.controller} / interval {hour}. Linear formulations equivalent within 1e-12: **{report['formulations']['equivalent_within_tolerance']}**.",
        "",
        "| Formulation | Budget s | Status | Objective | Bound | Gap | Predicted methane kg | Independent physics |",
        "|---|---:|---|---:|---:|---:|---:|---|",
    ]
    for r in report["solves"]:
        s = r["solver"]
        lines.append(
            f"| {r['implementation']} | {r['budget_seconds']} | {s['status']} | {s.get('objective_value')} | {s.get('objective_bound')} | {s.get('gap')} | {r['predicted_methane_kg']} | {r['independent_physics_passed']} |"
        )
    if other:
        original = report["original_comparison"]
        lines += [
            "",
            f"The original runs first requested different actions at interval {divergence}. At the selected interval their estimates match: {original['same_estimate_at_selected_hour']}; forecasts match: {original['same_forecast_at_selected_hour']}. Their whole-run methane totals were {original['whole_run_methane_kg']} kg. Original solver details and all controlled actions are retained in the JSON report.",
        ]
    lines += [
        "",
        "Positive row scaling leaves the mathematical feasible set unchanged. Solver branch/search paths and wall-clock cutoffs can change the incumbent. Different applied actions then change subsequent inventories and later decisions. Comparing later whole-run states is not a controlled test of component physics.",
        "",
        "This report measures the observed effects; it does not assume that longer solves always improve a single stochastic wall-clock run or certify an optimum without a matching bound.",
    ]
    out.with_suffix(".md").write_text("\n".join(lines) + "\n")
    print(
        json.dumps(
            {
                "report": str(out),
                "equivalent": report["formulations"]["equivalent_within_tolerance"],
                "hour": hour,
            }
        )
    )
    if not report["formulations"]["equivalent_within_tolerance"] or any(
        r["independent_physics_passed"] is False for r in report["solves"]
    ):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
