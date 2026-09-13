"""Conditional plant uncertainty study. Not parameter estimation or a fleet study.

Run from repository: PYTHONPATH=. .venv/bin/python research/model-assumptions/run_stress.py
Existing results are reused only with the identical input, protocol and scientific
source hashes. Delete no files: a changed identity creates a separate edition.
Create a CANCEL file beside this script to stop between cases/solver intervals.
"""

import copy
import gzip
import json
import time
from dataclasses import replace
from pathlib import Path

from methane.config import Config, Scenario
from methane.costing import allocation
from methane.provenance import LOADED_SOURCE, digest
from methane.reference import audit
from methane.simulation import run
from methane.weather import synthetic

HERE = Path(__file__).resolve().parent
PROFILES = {
    "reference": {},
    "retentive": dict(
        thermal_capacity_kwh_per_k=0.15,
        heat_loss_kw_per_k=0.04,
        roundtrip_efficiency=0.95,
        specific_energy_kwh_per_kg=50,
        start_energy_kwh=20,
    ),
    "demanding": dict(
        thermal_capacity_kwh_per_k=0.6,
        heat_loss_kw_per_k=0.16,
        roundtrip_efficiency=0.85,
        specific_energy_kwh_per_kg=65,
        start_energy_kwh=80,
    ),
    "storage-constrained": dict(battery_kwh=400, h2_capacity_kg=30, co2_delivery_kg=150),
    "coupled-stress": dict(
        thermal_capacity_kwh_per_k=0.6,
        heat_loss_kw_per_k=0.16,
        roundtrip_efficiency=0.85,
        specific_energy_kwh_per_kg=65,
        start_energy_kwh=80,
        battery_kwh=400,
        h2_capacity_kg=30,
        co2_delivery_kg=150,
    ),
}


def main(extension=False):
    protocol = json.loads((HERE / "protocol.json").read_text())
    profiles = PROFILES
    if extension:
        protocol["amendment"] = json.loads((HERE / "thermal-extension.json").read_text())
        profiles = protocol["amendment"]["profiles"]
    identity = digest(
        dict(protocol=protocol, profiles=profiles, source=LOADED_SOURCE["content_hash"])
    )[:16]
    directory = HERE / "experiments" / identity
    directory.mkdir(parents=True, exist_ok=True)
    (directory / "runner.py.txt").write_text(Path(__file__).read_text())
    (directory / "manifest.json").write_text(
        json.dumps(dict(protocol=protocol, profiles=profiles, source=LOADED_SOURCE), indent=2)
    )
    items = []
    for seed in protocol["study"]["seeds"]:
        baseline = Config(
            scenario=Scenario(hours=48, horizon_hours=12, solver_seconds=0.2, seed=seed)
        )
        weather = synthetic(baseline)
        for profile, patch in profiles.items():
            if (HERE / "CANCEL").exists():
                break
            cfg = replace(baseline, plant=replace(baseline.plant, **patch))
            case = directory / f"{seed}-{profile}"
            case.mkdir(exist_ok=True)
            saved = case / "summary.json"
            if saved.exists():
                items.append(json.loads(saved.read_text()))
                continue
            started = time.perf_counter()
            summary = dict(
                seed=seed,
                profile=profile,
                config=cfg.to_dict(),
                weather_hash=digest(weather),
                source=LOADED_SOURCE["content_hash"],
            )
            try:
                result = run(
                    cfg,
                    weather=copy.deepcopy(weather),
                    strategies=protocol["study"]["strategies"],
                    cancelled=lambda: (HERE / "CANCEL").exists(),
                )
                verified = audit(result)
                with gzip.open(case / "result.json.gz", "wt") as f:
                    json.dump(result, f, allow_nan=False)
                (case / "audit.json").write_text(json.dumps(verified, indent=2))
                metrics = {}
                for name, rows in result["records"].items():
                    cost = allocation(cfg.plant, cfg.costs, rows)
                    metrics[name] = dict(
                        hours=len(rows),
                        methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
                        curtailment_kwh=sum(r["curtailed_kwh"] for r in rows),
                        reactor_starts=sum(r["reactor_start"] for r in rows),
                        electrolyser_starts=sum(r["electrolyser_start"] for r in rows),
                        ending_state=rows[-1]["state"] if rows else None,
                        costs=cost,
                        solver_limits=result["metrics"][name]["limited_solves"],
                        fallback_count=result["metrics"][name]["fallbacks"],
                        forced_downtime_hours=result["metrics"][name]["forced_downtime_hours"],
                    )
                summary.update(
                    status=result["status"],
                    run_id=result["run_id"],
                    audit_passed=verified["passed"],
                    metrics=metrics,
                )
            except Exception as exc:
                summary.update(status="failed", error=repr(exc))
            summary["seconds"] = time.perf_counter() - started
            saved.write_text(json.dumps(summary, indent=2, allow_nan=False))
            items.append(summary)
            (directory / "index.json").write_text(json.dumps(items, indent=2, allow_nan=False))
            print(seed, profile, summary["status"], round(summary["seconds"], 1), flush=True)
    (
        HERE / ("latest-thermal-extension.json" if extension else "latest-experiments.json")
    ).write_text(
        json.dumps(
            dict(directory=str(directory.relative_to(HERE)), cases=len(items), identity=identity),
            indent=2,
        )
    )


if __name__ == "__main__":
    import sys

    main("--thermal-extension" in sys.argv)
