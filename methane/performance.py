"""Representative backend latency budgets; browser transport/render checks remain separate."""

import argparse
import json
import statistics
import time
from pathlib import Path

from methane.config import Config, Scenario
from methane.evidence import load, save
from methane.lineage import economic, trace
from methane.provenance import LOADED_SOURCE, digest
from methane.simulation import run
from methane.solar import preview
from methane.ui import playback_value


def measure(call, repeats):
    values = []
    for _ in range(repeats):
        start = time.perf_counter()
        call()
        values.append((time.perf_counter() - start) * 1000)
    return {
        "samples_ms": values,
        "p95_ms": sorted(values)[min(len(values) - 1, int(len(values) * 0.95))],
        "median_ms": statistics.median(values),
    }


def benchmark(result):
    controller = next(iter(result["records"]))
    count = len(result["records"][controller])
    hour = max(0, count - 1)
    preview(result)
    checks = {
        "playback_payload": (measure(lambda: playback_value(result), 5), 2000),
        "cached_solar_preview": (measure(lambda: preview(result), 30), 100),
        "component_lineage": (measure(lambda: trace(result, controller, hour, "reactor"), 30), 20),
        "economic_lineage": (measure(lambda: economic(result, controller, count), 20), 100),
    }
    return dict(
        schema_version="dispatch-lab/performance-gates/1",
        source_content_hash=LOADED_SOURCE["content_hash"],
        run_id=result["run_id"],
        fixture_hours=count,
        config_sha256=digest(result["config"]),
        checks={
            key: {**timing, "budget_p95_ms": budget, "passed": timing["p95_ms"] <= budget}
            for key, (timing, budget) in checks.items()
        },
        passed=all(t["p95_ms"] <= limit for t, limit in checks.values()),
        scope="Warm backend operations on a saved run. Payload budget applies to initial load; browser gate separately measures changed design through transport while a batch worker is active.",
    )


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--archive", type=Path)
    p.add_argument("--hours", type=int, default=240)
    p.add_argument(
        "--out", type=Path, default=Path("build/engineering/current/performance-gates.json")
    )
    args = p.parse_args()
    if args.archive:
        result = load(args.archive)
    else:
        result = run(Config(scenario=Scenario(hours=args.hours)), strategies=["Greedy"])
        if result["status"] != "complete":
            raise ValueError("Performance fixture did not complete")
        archive = save(result)
        print("Fixture: " + str(archive), flush=True)
    report = benchmark(result)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, indent=2))
    print(
        json.dumps(
            {
                k: {"p95_ms": v["p95_ms"], "passed": v["passed"]}
                for k, v in report["checks"].items()
            },
            indent=2,
        )
    )
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
