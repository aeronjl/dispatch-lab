"""Predeclared, repeatable autonomy qualification using immutable Sites studies.

No network is required. Missing original inputs fail preparation visibly. Numerical
repeats, event seeds and weather windows retain separate identities. The programme
never tunes a case from its outcomes or reconstructs original evidence as current.
"""

import argparse
import json
import time
from dataclasses import replace
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

from methane.config import Config
from methane.policy import Policy
from methane.siting import production
from methane.siting.contracts import DeploymentDesign
from methane.siting.store import Store, atomic, digest, encode
from methane.timebase import stamp, utc

VERSION = "autonomy-qualification/1"
ORIGINAL = "e8c6eaafb5e3949a5f98b26fe955f79f4d4b2c6e403deb96d7fe8617f160b466"
ANNUAL = "568d21a1d25c8c751c1fcc3412eb8bf3ce14f8db7d9edec4502deefc4432ce6d"
ROOT = Path(__file__).resolve().parents[1] / "research" / "autonomy-qualification"
CONTROLLERS = ("Greedy", "MPC · methane", "MPC · economics")


def changed_paths(a, b, prefix=""):
    if isinstance(a, dict) and isinstance(b, dict):
        result = []
        for key in sorted(a.keys() | b.keys()):
            result.extend(changed_paths(a.get(key), b.get(key), prefix + "." + key))
        return result
    return [] if a == b else [prefix.lstrip(".")]


def window(store, environment_id, start, hours):
    """New window identity references the original radiation and publication bytes."""
    original = store.get("environment", environment_id)
    end = stamp(utc(start) + timedelta(hours=hours))
    if utc(start) < utc(original["start"]) or utc(end) > utc(original["end"]):
        raise ValueError("Requested window is outside saved reference coverage")
    value = {**original, "start": start, "end": end, "hours": hours}
    value["parent_environment_id"] = environment_id
    value["assumptions"] = [
        *original["assumptions"][:-1],
        "Window selected before execution; no claim of unseen-year validation",
        original["assumptions"][-1],
    ]
    return store.put("environment", value)


def forecast_stress(store, environment_id, factor):
    """Disclosed prediction-only sensitivity; truth and availability are unchanged."""
    env = store.get("environment", environment_id)
    if env["information"] != "archived-ifs/1" or factor <= 0:
        raise ValueError("Forecast stress requires original issues and a positive multiplier")
    payload = json.loads(store.read_raw(env["normalized_sha256"]))
    for vintage in payload["vintages"]:
        for sample in vintage["data"].values():
            sample["irradiance_wm2"] *= factor
    return store.put(
        "environment",
        {
            **env,
            "normalized_sha256": store.raw(encode(payload)),
            "parent_environment_id": environment_id,
            "transformation": {
                "version": "declared-forecast-radiation-multiplier/1",
                "factor": factor,
                "scope": "Predictions only; original issue and availability times retained",
            },
            "assumptions": [
                *env["assumptions"][:-1],
                f"Illustrative forecast irradiance multiplied by {factor}; not an original unmodified issue",
                env["assumptions"][-1],
            ],
        },
    )


def local_policy(controller, c):
    return Policy(
        objective={"Greedy": "greedy", "MPC · methane": "methane", "MPC · economics": "economics"}[
            controller
        ],
        version="dispatch-lab/policy/2",
        recovery=replace(c.recovery_policy, version="scheduled-load-tests/1"),
    ).to_dict()


def prepare(store, *, basis=None, seeds=(7, 17, 29), pilot=False, root=ROOT):
    if not seeds or len(set(seeds)) != len(seeds):
        raise ValueError("Use distinct, nonempty event seeds")
    old = store.get("study", ORIGINAL)
    original_case = old["cases"][0]
    base = Config.from_dict(basis or original_case["config"])
    if base.service_system is None or base.recovery_policy is None or base.service_policy is None:
        raise ValueError("Qualification needs the configured service and recovery system")
    original_env = original_case["environment_id"]
    original_design = original_case["design_id"]
    # Validate source bytes and forecast coverage before launching any numerical work.
    from methane.siting.environment import weather

    weather(store, original_env, replace(base, scenario=replace(base.scenario, horizon_hours=24)))
    groups = {}
    labels = {}

    def add(
        group,
        arm,
        c,
        *,
        env=original_env,
        controller="MPC · methane",
        seed=7,
        repeat=1,
        policy=None,
        pair="reference",
    ):
        c = replace(c, scenario=replace(c.scenario, seed=seed))
        source = store.get("design", original_design)
        ed = store.get("environment", env)
        design = DeploymentDesign(
            **{
                **source,
                "name": f"Autonomy qualification / {group} / {arm}",
                "site_revision": ed["site_revision"],
                "config": c.to_dict(),
                "parent_id": original_design,
                "assumptions": [
                    *source["assumptions"],
                    "Predeclared conditional simulation challenge; not measured failure or repair statistics",
                ],
            }
        )
        did = store.put("design", design)
        row = dict(
            design_id=did,
            environment_id=env,
            controller=controller,
            seed=seed,
            repetition=repeat,
            label=f"{pair} / {arm} / seed {seed} / numerical {repeat}",
        )
        if policy is not None:
            row["policy"] = policy
        groups.setdefault(group, []).append(row)
        labels.setdefault(group, []).append(
            dict(
                arm=arm,
                pair=pair,
                seed=seed,
                repetition=repeat,
                changes_from_basis=changed_paths(base.to_dict(), c.to_dict()),
                explicit_policy=policy,
            )
        )

    # Preserve the original package comparison. The budget/horizon changes apply
    # only to methane MPC, so they do not confound changes in economic objective.
    for repeat in (1, 2):
        for controller in CONTROLLERS:
            add("counterexample", controller, base, controller=controller, repeat=repeat)
        for horizon, budget in ((6, 1.0), (24, 0.1), (24, 1.0)):
            c = replace(
                base, scenario=replace(base.scenario, horizon_hours=horizon, solver_seconds=budget)
            )
            add("counterexample", f"methane H{horizon} / {budget}s", c, repeat=repeat)
        for controller in CONTROLLERS:
            c = replace(base, scenario=replace(base.scenario, horizon_hours=24, solver_seconds=0.5))
            add(
                "local-service",
                controller,
                c,
                controller=controller,
                repeat=repeat,
                policy=local_policy(controller, c),
            )

    standard = replace(
        base,
        scenario=replace(base.scenario, horizon_hours=12, solver_seconds=0.3),
        sensors=replace(base.sensors, noise_fraction=0.02, ambiguity_policy="retain-capacity/1"),
        faults=replace(base.faults, capacity_cause="equipment-damage"),
        recovery_policy=replace(
            base.recovery_policy, version="scheduled-load-tests/4", maximum_wait_hours=24
        ),
    )
    for condition in ("capacity-loss", "failed-remedy", "flow-bias", "null"):
        c = standard
        if condition == "failed-remedy":
            c = replace(
                c, field_operations=replace(c.field_operations, repair_success_probability=0)
            )
        if condition == "flow-bias":
            c = replace(
                c, scenario=replace(c.scenario, capacity_fraction=1, flow_bias_fraction=0.3)
            )
        if condition == "null":
            c = replace(
                c,
                scenario=replace(c.scenario, capacity_fraction=1, fault_start_hour=10000),
                sensors=replace(c.sensors, noise_fraction=0),
            )
        for seed in (seeds[0],) if condition == "null" else seeds:
            for repeat in (1, 2) if condition == "null" else (1,):
                for arm in (
                    "retain / weather deadline",
                    "reduce / weather deadline",
                    "retain / fixed deadline",
                ):
                    candidate = (
                        replace(c, sensors=replace(c.sensors, ambiguity_policy="reduce-capacity/1"))
                        if arm.startswith("reduce")
                        else c
                    )
                    if arm.endswith("fixed deadline"):
                        candidate = replace(
                            candidate,
                            recovery_policy=replace(
                                candidate.recovery_policy, version="scheduled-load-tests/3"
                            ),
                        )
                    add("recovery", arm, candidate, seed=seed, repeat=repeat, pair=condition)

    stressed = forecast_stress(store, original_env, 1.5)
    sensitivities = {
        "reference": standard,
        "half initial battery": replace(
            standard, plant=replace(standard.plant, initial_soc=standard.plant.initial_soc / 2)
        ),
        "double thermal capacity": replace(
            standard,
            plant=replace(
                standard.plant,
                thermal_capacity_kwh_per_k=standard.plant.thermal_capacity_kwh_per_k * 2,
            ),
        ),
        "crew lead 24h": replace(
            standard, service_system=replace(standard.service_system, crew_response_lead_hours=24)
        ),
        "failed remedy": replace(
            standard,
            field_operations=replace(standard.field_operations, repair_success_probability=0),
        ),
        "forecast +50%": standard,
    }
    for seed in seeds:
        for condition, c in sensitivities.items():
            for controller in ("Greedy", "MPC · methane"):
                add(
                    "sensitivity",
                    controller,
                    c,
                    seed=seed,
                    controller=controller,
                    pair=condition,
                    env=stressed if condition == "forecast +50%" else original_env,
                )

    if not pilot:
        annual = store.get("study", ANNUAL)
        for anchor in annual["cases"]:
            w = Config.from_dict(anchor["config"]).weather
            c = replace(
                standard,
                weather=w,
                scenario=replace(
                    standard.scenario,
                    hours=168,
                    horizon_hours=24,
                    solver_seconds=0.2,
                    fault_start_hour=26,
                ),
            )
            for month in (1, 4, 7):
                env = window(
                    store, anchor["environment_id"], f"2025-{month:02}-10T00:00:00+00:00", 168
                )
                for controller in ("Greedy", "MPC · methane"):
                    add(
                        "seasonal",
                        controller,
                        c,
                        env=env,
                        controller=controller,
                        seed=seeds[0],
                        pair=f"{anchor['label'].split(' / ')[-1]} / month {month}",
                    )
    if pilot:
        groups = {k: v[:2] for k, v in groups.items()}
        labels = {k: labels[k][:2] for k in groups}
    path = Path(root) / uuid4().hex
    path.mkdir(parents=True)
    programme = dict(
        version=VERSION,
        original_study=ORIGINAL,
        annual_inputs=ANNUAL,
        basis=base.to_dict(),
        basis_hash=digest(base.to_dict()),
        seeds=list(seeds),
        pilot=pilot,
        created_at=time.time(),
        groups=[],
        store_root=str(store.root.resolve()),
        scope="Predeclared controlled simulation and seasonal design exposure; no empirical event rates, new-year holdout or deployment ROI claim",
    )
    for group, cases in groups.items():
        study = production.create(
            store,
            name=f"Autonomy qualification / {group}",
            cases=cases,
            mode="design",
            partition_hours=72,
            purpose="Controlled ablations include the historical observer; original forecasts are used except explicitly transformed stress and seasonal persistence. Do not infer qualified annual autonomy.",
        )
        programme["groups"].append(
            dict(
                name=group,
                study_id=study["id"],
                source=study["source"]["content_hash"],
                labels=labels[group],
            )
        )
    atomic(path / "programme.json", encode(programme))
    return path


def run_programme(path):
    p = json.loads((Path(path) / "programme.json").read_bytes())
    store = Store(p["store_root"])
    for group in p["groups"]:
        if (Path(path) / "cancel").exists():
            return
        key = group["study_id"]
        if production.state(store, key)["status"] == "complete":
            continue
        production.launch(store, key)
        while True:
            status = production.state(store, key)
            print(group["name"], status, flush=True)
            if status["status"] not in ("running", "ready"):
                break
            if (Path(path) / "cancel").exists():
                production.cancel(store, key)
            time.sleep(10)
        # Missing/invalid cases remain visible; do not suppress the remaining groups.


def case_evidence(store, study_id, case_id):
    manifest = store.get("study", study_id)
    case = next(x for x in manifest["cases"] if x["case_id"] == case_id)
    path = production.directory(store, study_id) / case_id / "summary.json"
    summary = json.loads(path.read_bytes()) if path.exists() else None
    rows, truth = [], []
    evidence = []
    for entry in production.entries(store, study_id, case_id):
        r = production.load_period(store, entry["period_sha256"])
        rows.extend(r["records"][case["controller"]])
        truth.extend(r["retrospective_truth_by_controller"][case["controller"]])
        evidence.append(
            dict(
                period_sha256=entry["period_sha256"],
                run_id=r["run_id"],
                archive_sha256=r["archive_sha256"] if "archive_sha256" in r else None,
            )
        )
    timeline = []
    for row, physical in zip(rows, truth, strict=True):
        d, field = row["decision"], row.get("field_operations", {})
        timeline.append(
            dict(
                hour=row["hour"],
                time=row["time"],
                pv_kw=row["pv_kw"],
                applied=row["applied"],
                requested=row["requested"],
                state=row["state"],
                diagnosis=row["diagnosis_after"],
                truth_capacity_kw=physical["capacity_kw"],
                solver=d["plan"]["solver"],
                forecast_source=d["forecast"]["source"],
                probe=d["probe"],
                mode=row["mode"],
                curtailed_kwh=row["curtailed_kwh"],
                forced_trip=row["forced_trip"],
                service_kw=row.get("service_kw", 0),
                mission_events=field.get("mission_events", []),
                new_missions=field.get("new_missions", []),
                human_hours=field.get("human_hours", 0),
                human_visits=field.get("human_visits", 0),
                remote_hours=field.get("remote_hours", 0),
                reactor_heat_loss_kwh=row["heat_loss_kwh"],
                reaction_heat_kwh=row["reaction_heat_kwh"],
                recovery=d.get("recovery_planning"),
                service_control=d.get("service_control"),
            )
        )
    return dict(
        study_id=study_id,
        case_id=case_id,
        source=manifest["source"]["content_hash"],
        controller=case["controller"],
        config=case["config"],
        policy=case.get("policy"),
        environment_id=case["environment_id"],
        summary=summary,
        hours=len(rows),
        expected_hours=case["hours"],
        timeline=timeline,
        periods=evidence,
        physical_trace_hash=digest(
            [dict(hour=r["hour"], applied=r["applied"], state=r["state"]) for r in rows]
        ),
        field_terminal=rows[-1].get("field_operations", {}).get("state") if rows else None,
        boundary="States are end-of-interval. Truth is retrospective; decisions contain only recorded information. Ending inventories have no speculative sale value.",
    )


def report(path):
    from methane.siting.verification import verify_case

    path = Path(path)
    p = json.loads((path / "programme.json").read_bytes())
    store = Store(p["store_root"])
    rows = []
    for group in p["groups"]:
        study = store.get("study", group["study_id"])
        for case, label in zip(study["cases"], group["labels"], strict=True):
            record = case_evidence(store, group["study_id"], case["case_id"])
            check = verify_case(store, group["study_id"], case["case_id"])
            record.update(group=group["name"], label=label, independent_check=check)
            rows.append(record)
    revision = uuid4().hex
    out = path / "reports" / revision
    out.mkdir(parents=True)
    atomic(out / "results.json", encode(dict(version=VERSION, programme=digest(p), cases=rows)))
    # Compact publication and interpretation are generated separately from these
    # original operands. No report generation invokes the optimiser.
    return out


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("operation", choices=("prepare", "run", "report", "original"))
    parser.add_argument("path", nargs="?", type=Path)
    parser.add_argument("--basis", type=Path)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.operation == "prepare":
        print(
            prepare(
                Store(),
                basis=json.loads(args.basis.read_bytes()) if args.basis else None,
                pilot=args.pilot,
            ),
            flush=True,
        )
    elif args.operation == "original":
        if args.path is None or args.path.exists():
            raise ValueError("Provide a new path for the original evidence extraction")
        store = Store()
        atomic(
            args.path,
            encode(
                [
                    case_evidence(store, ORIGINAL, c["case_id"])
                    for c in store.get("study", ORIGINAL)["cases"]
                ]
            ),
        )
    elif args.path is None:
        parser.error("Provide the saved programme directory")
    elif args.operation == "run":
        run_programme(args.path)
    else:
        print(report(args.path))


if __name__ == "__main__":
    main()
