"""Publish a separately identified audit; never rewrite original Study judgments."""

import gzip
import hashlib
import json
from pathlib import Path

from methane.provenance import LOADED_SOURCE
from methane.reference import audit
from methane.studies import archive_for, entry_for, read_manifest

ROOT = Path(__file__).resolve().parent
programme = ROOT / "ce1a7e25c58742cbbfcefe51ba236fe3"
source = LOADED_SOURCE["content_hash"]
checker = hashlib.sha256(Path("methane/reference.py").read_bytes()).hexdigest()
dest = programme / "additional-audits" / checker[:16]
dest.mkdir(parents=True, exist_ok=False)
entries = []
for e in json.loads((programme / "programme.json").read_text())["entries"]:
    m = read_manifest(e["edition_id"])
    old = entry_for(e["edition_id"], m["cases"][0]["case_id"])
    r = archive_for(e["edition_id"], old)
    new = audit(r)
    artifact = e["edition_id"] + ".json.gz"
    (dest / artifact).write_bytes(gzip.compress(json.dumps(new, allow_nan=False).encode(), mtime=0))
    entries.append(
        dict(
            **e,
            run_id=r["run_id"],
            original_source=m["source_hash"],
            original_edition_status=old["status"],
            physical_execution_status=r["status"],
            original_archive=old["archive"],
            original_archive_integrity=old["archive_integrity"],
            original_audit=old["independent_audit"],
            current_audit_passed=new["passed"],
            checks=len(new["checks"]),
            failed_checks=[c for c in new["checks"] if not c["passed"]],
            artifact=artifact,
            artifact_sha256=hashlib.sha256((dest / artifact).read_bytes()).hexdigest(),
        )
    )
    print(
        e["condition"],
        e["arm"],
        e["repeat"],
        old["status"],
        "additional audit",
        new["passed"],
        flush=True,
    )
summary = dict(
    version="additional-independent-audit/1",
    reader_source=source,
    checker_sha256=checker,
    explanation="The original checker compared a drive-test execution duration with a public upper reservation duration. The revised independent checker derives actual timing from the captured nominal recipe and original actual world factor. No physical trace, controller decision, original archive or original Study judgment has been modified. New judgments carry their own identity.",
    scope="Arithmetic and information-boundary audit; no evidence of successful recovery, calibrated timing or a better policy follows from a passed check.",
    entries=entries,
)
(dest / "summary.json").write_text(json.dumps(summary, indent=2, allow_nan=False) + "\n")
print(dest / "summary.json")
