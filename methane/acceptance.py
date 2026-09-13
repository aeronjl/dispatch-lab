"""Create one source-bound example and verify an extracted bundle offline in isolation."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from methane.bundle import make, unpack
from methane.config import Config, Scenario
from methane.evidence import save
from methane.reference import audit
from methane.simulation import run


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--directory", type=Path, default=Path("build/engineering/current"))
    p.add_argument("--hours", type=int, default=24)
    args = p.parse_args()
    out = args.directory
    out.mkdir(parents=True, exist_ok=True)
    result = run(Config(scenario=Scenario(hours=args.hours, horizon_hours=24)))
    archive = save(result)
    report = audit(result)
    (out / "independent-reference.json").write_text(json.dumps(report, indent=2, allow_nan=False))
    if not report["passed"]:
        raise ValueError("Acceptance example failed independent reference check")
    bundle = make(result, out / "reproduction.zip")
    root = unpack(bundle, out / "restored")
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str((root / "check_bundle.py").resolve()),
            str(root.resolve()),
            "--out",
            str((out / "offline-check.json").resolve()),
        ],
        check=True,
        stdout=subprocess.DEVNULL,
    )
    (out / "example.json").write_text(
        json.dumps(
            {
                "run_id": result["run_id"],
                "archive": str(archive),
                "bundle": str(bundle),
                "restored": str(root),
                "status": result["status"],
            },
            indent=2,
        )
    )
    print(archive)


if __name__ == "__main__":
    main()
