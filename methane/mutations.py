"""Intentional production-code faults, tested in disposable isolated copies."""

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MUTATIONS = (
    (
        "stoichiometry",
        "methane/reactor.py",
        '"hydrogen_kg": inputs.methane_kg * 0.5',
        '"hydrogen_kg": inputs.methane_kg * 0.6',
        "tests/test_engineering.py::test_pre_refactor_physical_fixture",
    ),
    (
        "missing battery loss",
        "methane/battery.py",
        "charge_loss = (1 - p.eta) * c * dt",
        "charge_loss = 0 * c * dt",
        "tests/test_battery.py::test_known_energy_ledger",
    ),
    (
        "battery planning efficiency",
        "methane/battery.py",
        "return _block(p, state, durations, 1, -p.eta, 1 / p.eta)",
        "return _block(p, state, durations, 1, -1.0, 1 / p.eta)",
        "tests/test_battery.py::test_standalone_planning_and_replay",
    ),
    (
        "heat-flow sign",
        "methane/reactor.py",
        "- inputs.cooling_kw",
        "+ inputs.cooling_kw",
        "tests/test_engineering.py::test_thermal_independent_ode_and_substeps",
    ),
    (
        "minimum-run off-by-one",
        "methane/reactor.py",
        "(minimum_run if start else commitment) - 1",
        "(minimum_run if start else commitment) - 2",
        "tests/test_engineering.py::test_reactor_abstract_transition_conformance",
    ),
    (
        "forecast look-ahead",
        "methane/forecast.py",
        'if utc(v["available_at"]) <= decision_time',
        "if True",
        "tests/test_methane.py::test_vintage_availability_boundary_and_dst",
    ),
)


def main():
    reports = []
    for name, path, before, after, test in MUTATIONS:
        with tempfile.TemporaryDirectory(prefix="dispatch-mutation-") as temp:
            root = Path(temp)
            for folder in ("methane", "tests", "assets"):
                shutil.copytree(
                    ROOT / folder,
                    root / folder,
                    ignore=shutil.ignore_patterns(
                        "__pycache__", "snapshots", "browser-demo-v2.json.gz"
                    ),
                )
            for file in [*ROOT.glob("*.py"), ROOT / "pyproject.toml", ROOT / "uv.lock"]:
                shutil.copy2(file, root / file.name)
            target = root / path
            source = target.read_text()
            if source.count(before) != 1:
                raise ValueError(f"Mutation {name} no longer matches exactly one expression.")
            target.write_text(source.replace(before, after, 1))
            completed = subprocess.run(
                [sys.executable, "-m", "pytest", "-q", test],
                cwd=root,
                env={**os.environ, "PYTHONPATH": str(root)},
                text=True,
                capture_output=True,
                timeout=90,
            )
            # Test failure is detection; collection/import errors are harness failures.
            detected = completed.returncode == 1 and "FAILED" in completed.stdout
            reports.append(
                {
                    "mutation": name,
                    "detected": detected,
                    "output": completed.stdout + completed.stderr,
                }
            )
    out = ROOT / "build/engineering"
    out.mkdir(parents=True, exist_ok=True)
    (out / "mutations.json").write_text(json.dumps(reports, indent=2))
    print(json.dumps([{k: v for k, v in r.items() if k != "output"} for r in reports], indent=2))
    if not all(r["detected"] for r in reports):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
