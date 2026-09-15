"""Freeze one original-information policy fork and recorded Control views for film.

This is a presentation fixture, not a policy qualification study. Rebuilding the
movie replays these saved results; only this explicit command runs a comparison.
"""

import gzip
import hashlib
import json
from pathlib import Path

from methane.control_view import compare, describe, prepare

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = ROOT / "build/field-operations/0edb1cf9141204ab.json.gz"
EXCERPT = ROOT / "tests/fixtures/field-motion.json.gz"
OUTPUT = Path(__file__).parent / "fixtures/control-view.json.gz"


def main():
    raw = ARCHIVE.read_bytes()
    original = json.loads(gzip.decompress(raw))
    excerpt = json.loads(gzip.decompress(EXCERPT.read_bytes()))
    if (
        original["run_id"] != excerpt["source_run_id"]
        or original["integrity_sha256"] != excerpt["source_integrity"]
    ):
        raise ValueError(
            "The full archive and the motion excerpt must identify the same recorded run"
        )
    controller, hour = "MPC · methane", 16
    packet = prepare(original, controller, hour)
    comparison = compare(packet)
    if comparison["status"] != "complete":
        raise ValueError("Comparison incomplete; do not overwrite the film fixture")
    # Plans shown in the film. These remain the archived plans, including probes.
    views = {f"{controller}|{h}": describe(original, controller, h) for h in range(12, 18)}
    fixture = dict(
        schema="dispatch-demo-control-fixture/1",
        source_run_id=original["run_id"],
        source_integrity=original["integrity_sha256"],
        archive_sha256=hashlib.sha256(raw).hexdigest(),
        motion_excerpt_sha256=hashlib.sha256(EXCERPT.read_bytes()).hexdigest(),
        views=views,
        comparison_selection=dict(controller=controller, hour=hour),
        input_packet=packet,
        comparison=comparison,
        note="Saved current-model predictions from one archived decision's information. Other views retain archived plans. Fixed service schedule; no future realised weather, hidden fault state or post-decision observations in the comparison. Not a policy ranking or field validation.",
    )
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_bytes(
        gzip.compress(json.dumps(fixture, allow_nan=False, separators=(",", ":")).encode(), mtime=0)
    )
    print(OUTPUT.relative_to(ROOT))
    for name, value in comparison["predictions"].items():
        print(name, value["solver"]["status"], value["predicted"]["methane_kg"])


if __name__ == "__main__":
    main()
