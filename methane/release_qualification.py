"""Release-1 frozen qualification: saved counterexamples and matched numerical repeats."""

import argparse
import json
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from methane.autonomy_qualification import ORIGINAL, local_policy, report, run_programme
from methane.config import Config
from methane.documentation import check_freshness
from methane.siting import production
from methane.siting.store import Store, atomic, digest, encode

ROOT = Path(__file__).resolve().parents[1] / "research" / "release-1"


def prepare(store, *, root=ROOT):
    check_freshness()
    from methane.assumptions import validate

    validate()
    old_path = ROOT.parent / "autonomy-qualification/report.json"
    old = json.loads(old_path.read_bytes())
    cases = []
    labels = []
    # Every recorded version-4 case is covered, including successful sensor/no-fault
    # controls, failed remedies and all nine seasonal windows. No outcome filtering.
    for previous in old["cases"]:
        if (previous.get("executed_policy") or {}).get("recovery", {}).get(
            "version"
        ) != "scheduled-load-tests/4":
            continue
        study = store.get("study", previous["study_id"])
        case = next(c for c in study["cases"] if c["case_id"] == previous["case_id"])
        c = Config.from_dict(case["config"])
        c = replace(c, recovery_policy=replace(c.recovery_policy, version="scheduled-load-tests/5"))
        design = store.get("design", case["design_id"])
        did = store.put(
            "design",
            {
                **design,
                "parent_id": case["design_id"],
                "config": c.to_dict(),
                "name": "Release 1 / saved counterexample",
            },
        )
        policy = json.loads(json.dumps(previous["executed_policy"]))
        policy["recovery"]["version"] = "scheduled-load-tests/5"
        cases.append(
            dict(
                design_id=did,
                environment_id=case["environment_id"],
                controller=case["controller"],
                seed=c.scenario.seed,
                repetition=case["repetition"],
                policy=policy,
                label="v5 / " + case["label"],
            )
        )
        labels.append(
            {
                **previous["label"],
                "arm": "version 5 / " + previous["label"]["arm"],
                "original_study": previous["study_id"],
                "original_case": previous["case_id"],
                "original_outcome": previous["outcome"],
                "pair": previous["group"] + " / " + previous["label"]["pair"],
            }
        )
    basecase = store.get("study", ORIGINAL)["cases"][0]
    base = Config.from_dict(basecase["config"])
    base = replace(
        base,
        scenario=replace(base.scenario, horizon_hours=12, solver_seconds=1.0),
        sensors=replace(base.sensors, ambiguity_policy="retain-capacity/1"),
        recovery_policy=replace(
            base.recovery_policy, version="scheduled-load-tests/5", maximum_wait_hours=24
        ),
    )
    groups = [("saved-failures", cases, labels)]
    for name, controllers in [
        ("matched-local", ("Greedy", "MPC · methane", "MPC · economics")),
        ("matched-joint", ("MPC · methane", "MPC · economics")),
    ]:
        cases = []
        labels = []
        for seed in (7, 17, 29):
            c = replace(base, scenario=replace(base.scenario, seed=seed))
            d = store.get("design", basecase["design_id"])
            did = store.put(
                "design",
                {
                    **d,
                    "name": "Release 1 / " + name,
                    "parent_id": basecase["design_id"],
                    "config": c.to_dict(),
                },
            )
            for repeat in (1, 2, 3):
                for controller in controllers:
                    case = dict(
                        design_id=did,
                        environment_id=basecase["environment_id"],
                        controller=controller,
                        seed=seed,
                        repetition=repeat,
                        label=f"{controller} / seed {seed} / numerical {repeat}",
                    )
                    if name == "matched-local":
                        case["policy"] = local_policy(controller, c)
                    cases.append(case)
                    labels.append(dict(arm=controller, pair=name, seed=seed, repetition=repeat))
        groups.append((name, cases, labels))
    programme = dict(
        version="release-one-qualification/1",
        store_root=str(store.root.resolve()),
        original_publication_sha256=digest(old),
        basis=base.to_dict(),
        groups=[],
        acceptance={
            "saved_cases": "All 59 version-4 cases, without selection on recovery or production outcome; exact original horizons, budgets and inputs, policy version alone changed.",
            "matched": "Three independent numerical executions per each of three event seeds. Common local service policy isolates process objective; common joint v5 service compares methane/economic MPC separately. These groups are not pooled.",
            "numerical_gate": "Report within-arm ranges for methane, contribution, recovery confirmation and solver outcomes. A controller benefit is qualified only if its direction exceeds the paired numerical spread in every declared seed; otherwise unresolved.",
            "boundaries": "No empirical reliability, unseen-year weather validation, certified recovery deadline or deployment ROI. Existing annual windows are seasonal exposure only.",
        },
    )
    path = Path(root) / uuid4().hex
    path.mkdir(parents=True)
    for name, cases, labels in groups:
        study = production.create(
            store,
            name="Release 1 / " + name,
            cases=cases,
            mode="design",
            partition_hours=72,
            purpose="Predeclared release qualification; originals preserved, physics and observation separation independently audited.",
        )
        programme["groups"].append(
            dict(
                name=name,
                study_id=study["id"],
                source=study["source"]["content_hash"],
                labels=labels,
            )
        )
    atomic(path / "programme.json", encode(programme))
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=["prepare", "run", "report"])
    parser.add_argument("path", nargs="?", type=Path)
    args = parser.parse_args()
    if args.operation == "prepare":
        print(prepare(Store()), flush=True)
    elif args.path is None:
        parser.error("Supply the frozen programme directory")
    elif args.operation == "run":
        run_programme(args.path)
    else:
        print(report(args.path), flush=True)


if __name__ == "__main__":
    main()
