"""Offline release matrix. Independent processes do not share mutable solver models."""

import argparse
import json
import time
from concurrent.futures import ProcessPoolExecutor, as_completed
from dataclasses import replace
from pathlib import Path

from methane.config import Config
from methane.evidence import cases, markdown_report, save
from methane.simulation import run
from methane.weather import IncompleteWeather


def evaluate(item):
    label, config = item
    start = time.perf_counter()
    try:
        result = run(config)
        return {
            "case": label,
            "status": result["status"],
            "archive": str(save(result)),
            "run_id": result["run_id"],
            "experiment_id": result["experiment_id"],
            "metrics": result["metrics"],
            "failures": result.get("failures"),
            "seconds": time.perf_counter() - start,
        }
    except IncompleteWeather as exc:
        return {"case": label, "status": "incomplete-data", "error": str(exc)}
    except Exception as exc:
        return {"case": label, "status": "failed", "error": f"{type(exc).__name__}: {exc}"}


def audit_saved_matrix():
    from methane.engineering import audit_archive
    from methane.evidence import load
    from methane.provenance import LOADED_SOURCE

    out = Path("build/engineering")
    matrix = json.loads((out / "release-matrix.json").read_text())
    results = []
    for case in matrix:
        if "archive" not in case:
            results.append({"case": case["case"], "status": case["status"], "audited": False})
            continue
        try:
            report = audit_archive(load(case["archive"]))
            results.append(
                {
                    "case": case["case"],
                    "run_id": report["run_id"],
                    "audited": True,
                    "passed": report["passed"],
                    "checks": len(report["audits"]),
                    "failures": [a for a in report["audits"] if not a["passed"]],
                }
            )
        except Exception as exc:
            results.append(
                {"case": case["case"], "audited": True, "passed": False, "error": str(exc)}
            )
    complete_matrix = len(matrix) == 51
    passed = complete_matrix and all(r.get("passed", False) for r in results)
    report = {
        "checker_source": LOADED_SOURCE,
        "complete_matrix": complete_matrix,
        "passed": passed,
        "results": results,
    }
    (out / "release-audits.json").write_text(json.dumps(report, indent=2))
    print(
        f"{sum(r.get('passed', False) for r in results)}/{len(matrix)} archives passed; complete matrix: {complete_matrix}"
    )
    if not passed:
        raise SystemExit(1)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Independently check the saved matrix without solving again",
    )
    if parser.parse_args().audit:
        audit_saved_matrix()
        return
    base = Config()
    base = replace(base, weather=replace(base.weather, offline=True))
    matrix = [
        (suite + " / " + label, cfg)
        for suite in ("synthetic", "ablation", "thermal", "historical")
        for label, cfg in cases(base, suite)
    ]
    out = Path("build/engineering")
    out.mkdir(parents=True, exist_ok=True)
    results = []
    with ProcessPoolExecutor(max_workers=3) as pool:
        jobs = {pool.submit(evaluate, item): i for i, item in enumerate(matrix)}
        for future in as_completed(jobs):
            result = future.result()
            result["case_index"] = jobs[future]
            results.append(result)
            results.sort(key=lambda x: x["case_index"])
            (out / "release-matrix.json").write_text(json.dumps(results, indent=2))
            (out / "release-matrix.md").write_text(markdown_report(results))
            print(
                f"{len(results)}/{len(matrix)} · {result['case']} · {result['status']}", flush=True
            )
    if any(r["status"] in ("failed", "invalid") for r in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
