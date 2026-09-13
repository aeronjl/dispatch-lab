"""Repeatable qualification programme using immutable Studies, never ad hoc traces.

python -m methane.autonomy_studies create
python -m methane.autonomy_studies run PATH_TO_PROGRAMME_DIRECTORY
python -m methane.autonomy_studies report PATH_TO_PROGRAMME_DIRECTORY

Execution is sequential. Interrupted editions resume through the existing worker.
A new plant basis creates a new programme; original numerical inputs remain saved.
"""

import argparse
import copy
import html
import json
import time
from pathlib import Path
from uuid import uuid4

from methane.autonomy import DEFAULT
from methane.computation_studies import capture
from methane.config import Config, Costs, Scenario
from methane.field_operations import FieldOperations
from methane.provenance import digest
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.configuration import ServiceSystem
from methane.services.controller import ServicePolicy
from methane.studies import archive_for, create, entry_for, read_manifest, run_edition
from methane.uncertainty import VERSION
from methane.uncertainty_studies import protocol

ROOT = Path(__file__).resolve().parents[1] / "research/uncertainty-autonomy"
CASES = ("no-op", "reference", "slow-work", "weak-cleaning", "interruption", "support-outage")
ARMS = ("fixed", "adaptive", "risk-aware")


def fixture():
    return Config(
        scenario=Scenario(hours=12, horizon_hours=6, solver_seconds=2, variability=0.15),
        field_operations=FieldOperations(
            enabled=True,
            initial_soiling_fraction=0.18,
            soiling_per_day=0.003,
            mission_failure_probability=0.05,
            cleaner_battery_kwh=10,
        ),
        service_system=ServiceSystem(
            inspector="both",
            inspection_model="referenced-contact/1",
            cleaning_model="section-optical/1",
            cleaning_policy="condition",
            support_model="logistics/1",
            outcome_randomness="target-action-request/1",
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
        ),
        service_economics=illustrative(Costs(), version=ACTIVITY_VERSION),
        service_policy=ServicePolicy(
            maximum_wait_hours=6, maximum_candidates=3, comparison_seconds=4
        ),
    )


def specification(c, condition, arm, seed):
    if condition not in CASES or arm not in ARMS:
        raise ValueError("Unknown qualification condition or arm")
    options = copy.deepcopy(DEFAULT)
    options["mode"] = arm
    rows = {
        "no-op": [1, 0.9, 0.05, 0.14],
        "reference": [1, 0.9, 0.05, 0.14],
        "slow-work": [1.75, 0.9, 0.05, 0.14],
        "weak-cleaning": [1.5, 0.2, 0.05, 0.35],
        "interruption": [1.5, 0.4, 0.7, 0.25],
        "support-outage": [1.5, 0.9, 0.05, 0.14],
    }
    if condition == "no-op":
        options.update(
            duration_bounds={k: [1.0, 1.0] for k in options["duration_bounds"]},
            weather_factors=[1.0],
            weather_weights=[1.0],
            solar_relative_error=0.0,
            surface_absolute_error=0.0,
        )
    u = dict(
        schema_version=VERSION,
        seed=20260913,
        worlds=1,
        inner_seeds=[seed],
        design="factorial",
        rationale="Declared matched stress conditions, not sampled occurrence probabilities. No fitting on evaluation outcomes.",
        autonomy=options,
        blocks=[
            dict(
                id="stress",
                paths=[
                    "service_system.cleaning_time_factor",
                    "field_operations.cleaning_removal_fraction",
                    "field_operations.mission_failure_probability",
                    "weather.loss_fraction",
                ],
                kind="values",
                rows=[rows[condition]],
                visibility="hidden",
                source="Explicit qualification fixture; no site calibration",
                rationale="Match the physical world and event channels across all knowledge/policy arms",
            )
        ],
    )
    if condition == "support-outage":
        u["support_events"] = [
            dict(
                channel="communications",
                start=3,
                end=7,
                available=False,
                source="Declared communications interruption",
            )
        ]
    spec = protocol(c.to_dict(), u)
    spec.update(
        title="Uncertain service system · " + condition + " · " + arm,
        question="Do decisions and outcomes change beyond repeated-computation variation?",
        comparison="One physical world and one event seed. Programme report matches this edition against other arms and repeated numerical executions.",
        policies={"MPC · economics": {"objective": "economics"}},
        baseline_controller="MPC · economics",
        candidate_controller="MPC · economics",
    )
    return spec


def create_programme(basis=None, cases=CASES, seeds=(7,), repeats=2):
    if repeats < 2:
        raise ValueError("Qualification requires at least two numerical repetitions")
    c = Config.from_dict(basis) if basis else fixture()
    directory = ROOT / uuid4().hex
    directory.mkdir(parents=True)
    value = dict(
        version="uncertain-services-qualification/1",
        basis=c.to_dict(),
        cases=list(cases),
        seeds=list(seeds),
        repetitions=repeats,
        tolerance=1e-6,
        entries=[],
        scope="Numerical repetitions are not independent environmental seeds. Short scheduling windows and declared stress cases cannot establish annual cost or field reliability.",
    )
    for repeat in range(1, repeats + 1):
        for case in cases:
            for seed in seeds:
                for arm in ARMS:
                    edition = create(
                        basis=c.to_dict(), specification=specification(c, case, arm, seed)
                    )
                    value["entries"].append(
                        dict(
                            condition=case,
                            arm=arm,
                            seed=seed,
                            repeat=repeat,
                            edition_id=edition["edition_id"],
                        )
                    )
                    (directory / "programme.json").write_text(json.dumps(value, indent=2) + "\n")
    return directory


def report(directory):
    value = json.loads((directory / "programme.json").read_text())
    records = []
    for item in value["entries"]:
        record = copy.deepcopy(item)
        manifest = read_manifest(item["edition_id"])
        case = manifest["cases"][0]
        try:
            entry = entry_for(item["edition_id"], case["case_id"])
        except ValueError as exc:
            entry = dict(
                status="pending" if "no execution yet" in str(exc) else "invalid", error=str(exc)
            )
        record.update(status=entry.get("status", "pending"), source=manifest["source_hash"])
        if entry.get("archive"):
            result = archive_for(item["edition_id"], entry)
            controller = next(iter(result["records"]))
            packet = capture(result, controller, 0)
            world = case["uncertainty_world"]
            physical = copy.deepcopy(world["config"])
            record.update(
                physical_hash=digest(
                    dict(
                        config=physical,
                        weather=manifest["cases"][0].get("weather_hash"),
                        seed=item["seed"],
                    )
                ),
                inputs_hash=packet["inputs"],
                weather_hash=packet["weather"],
                vectors=packet["vectors"],
                work=packet["work"],
                solvers=packet["solvers"],
                selections=packet["selections"],
                archive=entry["archive"],
                run_id=result["run_id"],
                failures=result.get("failures"),
                audit_passed=entry.get("independent_audit", {}).get("passed"),
                metrics=entry.get("metrics"),
                methane_kg=sum(r["applied"]["methane_kg"] for r in result["records"][controller]),
            )
            rows = result["records"][controller]
            if rows:
                record["ending"] = rows[-1]["state"]
                record["unfinished_work"] = [
                    o
                    for o in rows[-1]["field_operations"]["state"]["orders"]
                    if o["status"] not in ("completed", "verified")
                ]
            record["risk_solves"] = []

            def walk(x, record=record):
                if isinstance(x, dict):
                    if x.get("version") == "uncertain-service-process-planning/1":
                        out = x.get("outcome", {})
                        record["risk_solves"].append(
                            dict(
                                status=x["status"],
                                solver=out.get("solver"),
                                branches=len(out.get("branches", [])),
                            )
                        )
                    for v in x.values():
                        walk(v)
                elif isinstance(x, list):
                    for v in x:
                        walk(v)

            for r in rows:
                walk(r["decision"].get("service_control", {}))
        records.append(record)
    groups = []
    for condition in value["cases"]:
        for seed in value["seeds"]:
            members = [r for r in records if r["condition"] == condition and r["seed"] == seed]
            physical_match = len({r.get("physical_hash") for r in members}) == 1 and all(
                r.get("physical_hash") for r in members
            )
            for arm in ARMS:
                selected = [r for r in members if r["arm"] == arm]
                complete = len(selected) == value["repetitions"] and all(
                    r["status"] == "complete" and r.get("vectors") for r in selected
                )
                identical = (
                    complete
                    and len({(r["source"], r["inputs_hash"], r["weather_hash"]) for r in selected})
                    == 1
                )
                difference = None
                if identical:
                    difference = max(
                        (
                            abs(float(a[k]) - float(b[k]))
                            for r in selected[1:]
                            for a, b in zip(selected[0]["vectors"], r["vectors"], strict=True)
                            for k in a
                        ),
                        default=0,
                    )
                stable = (
                    identical
                    and difference <= value["tolerance"]
                    and all(r["work"] == selected[0]["work"] for r in selected)
                )
                groups.append(
                    dict(
                        condition=condition,
                        seed=seed,
                        arm=arm,
                        complete=complete,
                        matched_physical_inputs=physical_match,
                        repeated_inputs_match=identical,
                        stable_in_sample=stable,
                        maximum_trace_difference=difference,
                        methane_range=[
                            min(r["methane_kg"] for r in selected),
                            max(r["methane_kg"] for r in selected),
                        ]
                        if complete
                        else None,
                        feasible_joint_solves=sum(
                            s["status"] == "feasible"
                            for r in selected
                            for s in r.get("risk_solves", [])
                        ),
                        unresolved_joint_solves=sum(
                            s["status"] != "feasible"
                            for r in selected
                            for s in r.get("risk_solves", [])
                        ),
                        fallback_intervals=sum(
                            bool(s["fallback_used"])
                            for r in selected
                            for s in r.get("selections", [])
                        ),
                    )
                )
    output = dict(version=value["version"], scope=value["scope"], groups=groups, records=records)
    (directory / "qualification.json").write_text(
        json.dumps(output, indent=2, allow_nan=False) + "\n"
    )
    rows = "".join(
        "<tr>"
        + "".join(
            "<td>" + html.escape(str(v)) + "</td>"
            for v in (
                g["condition"],
                g["arm"],
                g["seed"],
                g["methane_range"],
                g["stable_in_sample"],
                g["feasible_joint_solves"],
                g["unresolved_joint_solves"],
                g["fallback_intervals"],
            )
        )
        + "</tr>"
        for g in groups
    )
    body = (
        """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Uncertain service system · qualification</title><style>@font-face{font-family:Departure;src:url(../../../assets/fonts/DepartureMono-Regular.woff2)}body{background:#202020;color:#ffad43;font:16px/1.6 Departure,monospace;max-width:1200px;margin:5vh auto;padding:24px}h1{font-size:28px}a{color:inherit}table{border-collapse:collapse;width:100%;font-size:13px}td,th{padding:8px;border-bottom:1px solid #795424;text-align:left}.scroll{overflow:auto}p{max-width:85ch}</style><h1>Uncertain work, observed evidence and joint planning</h1><p>This is a controlled numerical qualification of the implemented scheduling sandbox. Repetition does not establish realism. Service durations, observation budgets and scenario weights remain disclosed assumptions.</p><p>Every numerical attempt belongs to an immutable Study edition. The JSON report retains original source/input identities, requested and applied actions, ending inventories, unfinished work, solver status and fallbacks. A stable sample is neither proof of determinism nor proof of optimality.</p><div class="scroll"><table><thead><tr><th>Condition</th><th>Arm</th><th>Seed</th><th>Methane range / kg</th><th>Stable repeats</th><th>Feasible joint candidates</th><th>Unresolved candidates</th><th>Fallback intervals</th></tr></thead><tbody>"""
        + rows
        + """</tbody></table></div><p>Interpret policy differences only when the physical inputs match, repeats are complete and within-arm numerical variation is smaller than the reported difference. The no-op condition tests whether policy machinery alone changes the trace. Unresolved solver branches and unfinished jobs are retained; no MPC dominance requirement is imposed.</p><p><a href="qualification.json">Full recorded accounting</a> · <a href="programme.json">Frozen programme and edition identifiers</a> · <a href="../mechanisms.html">Mechanisms, assumptions and remaining work</a></p>"""
    )
    (directory / "report.html").write_text(body)
    return output


def execute(directory):
    value = json.loads((directory / "programme.json").read_text())
    for i, item in enumerate(value["entries"]):
        started = time.perf_counter()
        print(
            f"{i + 1}/{len(value['entries'])} {item['condition']} {item['arm']} repeat {item['repeat']}",
            flush=True,
        )
        run_edition(item["edition_id"])
        print(f"Finished attempt in {time.perf_counter() - started:.1f}s", flush=True)
    report(directory)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create", "run", "report"])
    parser.add_argument("directory", type=Path, nargs="?")
    parser.add_argument("--basis", type=Path)
    args = parser.parse_args()
    if args.command == "create":
        print(create_programme(json.loads(args.basis.read_text()) if args.basis else None))
    elif args.command == "run":
        execute(args.directory)
    else:
        report(args.directory)
