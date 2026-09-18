"""Run from a restored source bundle: python recompute.py RECORDED.json.gz COMPARISON.json."""

import argparse
import json
from pathlib import Path

from methane.config import Config
from methane.evidence import load, save
from methane.provenance import LOADED_SOURCE
from methane.reference import audit
from methane.simulation import run


def recompute(source, out):
    if source.get("provenance", {}).get("external_control"):
        if source.get("control_reproduction"):
            from methane.control_replay import replay

            result, report = replay(source)
            report["archive"] = str(save(result, Path(out).parent / "recomputed-runs"))
            Path(out).write_text(json.dumps(report, indent=2, allow_nan=False))
            return report
        raise ValueError(
            "External-control recording: use recorded playback and independent balance checks. Re-running an external agent is not supported; silently substituting the reference policy would change the experiment."
        )
    result = run(
        Config.from_dict(source["config"]),
        weather=source["weather"],
        strategies=source["records"],
        policies=source.get("provenance", {}).get("controller_policies"),
        uncertainty=source.get("uncertainty", {}).get("world"),
    )
    deltas = {}
    for name, rows in result["records"].items():
        original = source["records"].get(name, [])
        different = [
            i
            for i, (a, b) in enumerate(zip(original, rows, strict=False))
            if any(abs(a["applied"][key] - b["applied"][key]) > 1e-5 for key in a["applied"])
        ]
        deltas[name] = {
            "first_different_interval": different[0] if different else None,
            "different_intervals": len(different),
            "recorded_intervals": len(original),
            "recomputed_intervals": len(rows),
            "methane_delta_kg": result["metrics"][name]["methane_kg"]
            - source["metrics"][name]["methane_kg"],
            "cost_delta_eur": result["metrics"][name]["total_eur"]
            - source["metrics"][name]["total_eur"],
        }
    report = dict(
        schema_version="dispatch-lab/recomputation-comparison/1",
        recorded_run_id=source["run_id"],
        recomputed_run_id=result["run_id"],
        source_matches=source.get("provenance", {}).get("source", {}).get("content_hash")
        == LOADED_SOURCE["content_hash"],
        recorded_environment=source.get("provenance", {}).get("environment"),
        recomputed_environment=result["provenance"]["environment"],
        status=result["status"],
        independent_reference_passed=audit(result)["passed"],
        controllers=deltas,
        archive=str(save(result, Path(out).parent / "recomputed-runs")),
        note="Numerical recomputation, distinct from recorded playback. Time-limited optimization can choose different feasible schedules.",
    )
    Path(out).write_text(json.dumps(report, indent=2, allow_nan=False))
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("out", type=Path)
    args = parser.parse_args()
    report = recompute(load(args.archive), args.out)
    print(json.dumps(report, indent=2))
    if not report["independent_reference_passed"]:
        raise SystemExit(1)
