"""Freeze existing recordings for a presentation; no simulation or claims are rerun."""

import gzip
import hashlib
import json
from pathlib import Path

from methane.control_view import describe
from methane.evidence import load
from methane.ui import playback_value

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "tools/submission-video/fixtures"
RECOVERY = ROOT / "build/release-1/release-example/offline/recorded-run.json.gz"


def write(name, value):
    path = OUT / name
    path.write_bytes(
        gzip.compress(json.dumps(value, allow_nan=False, separators=(",", ":")).encode(), mtime=0)
    )
    print(path.relative_to(ROOT), path.stat().st_size)


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    result = load(RECOVERY)
    rows = result["records"]["MPC · methane"]
    assert result["config"]["recovery_policy"]["version"] == "scheduled-load-tests/5"
    assert rows[14]["diagnosis_after"]["capacity_kw"] == 225
    assert rows[24]["diagnosis_after"]["capacity_kw"] == 450
    value = playback_value(result, register_contexts=False)
    value["offline_mode"] = True
    write(
        "recovery-motion.json.gz",
        {
            "source_run_id": result["run_id"],
            "source_integrity": result["integrity_sha256"],
            "archive_sha256": hashlib.sha256(RECOVERY.read_bytes()).hexdigest(),
            "note": "Archived release-1 controlled recovery example; not the preceding field-motion experiment. Original model and assumptions retained. Human replacement followed by observation-based tests; original service deadline miss remains recorded.",
            "props": {"value": value},
        },
    )
    write(
        "recovery-control.json.gz",
        {
            "source_run_id": result["run_id"],
            "source_integrity": result["integrity_sha256"],
            "views": {
                f"MPC · methane|{h}": describe(result, "MPC · methane", h) for h in range(13, 26)
            },
            "comparison_selection": None,
            "comparison": None,
            "note": "Recorded decisions and their actual observations. No new planning, simulated restoration substituted for observed recovery, or future truth supplied to the controller.",
        },
    )


if __name__ == "__main__":
    main()
