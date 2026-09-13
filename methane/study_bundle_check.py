"""Standalone study bundle integrity and independent physical/accounting check.

Run with no packages or network: python -I -S check_study.py EXTRACTED_DIRECTORY
"""

import argparse
import gzip
import hashlib
import json
import runpy
from pathlib import Path


def check(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "bundle.json").read_text())
    for name, expected in manifest["files"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root) or not path.is_file():
            raise ValueError("Missing or unsafe bundle member: " + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Modified bundle member: " + name)
    reference = runpy.run_path(str(root / "checker/reference.py"))["audit"]
    report_name = f"{manifest['edition_id']}/reports/{manifest['report_id']}.json"
    report = (
        json.loads((root / report_name).read_text()) if report_name in manifest["files"] else None
    )
    entries = {
        manifest["edition_id"] + "/" + c["entry"]["archive"]: c["entry"]
        for c in (report or {}).get("cases", [])
        if c.get("entry", {}).get("archive")
    }
    results = []
    for item in manifest["archives"]:
        if item["path"] not in manifest["files"]:
            raise ValueError("Archive is outside the verified inventory")
        result = json.loads(gzip.decompress((root / item["path"]).read_bytes()))
        packet = result.get("study", {}).get("computation")
        entry = entries.get(item["path"], {})
        if (packet is not None or entry.get("computation") is not None) and (
            packet != entry.get("computation") or not entry
        ):
            raise ValueError("Computation summary differs from its sealed original recording")
        a = reference(result)
        results.append(
            {
                "run_id": result["run_id"],
                "status": item["status"],
                "reference_passed": a["passed"],
                "computation_summary": "matched" if packet is not None else "not applicable",
            }
        )
    return {
        "integrity_passed": True,
        "archives": results,
        "complete_archives_passed": all(
            r["reference_passed"] for r in results if r["status"] == "complete"
        ),
        "note": "Hashes establish integrity, not authenticity. Reference checks do not establish plant calibration. Incomplete runs remain explicit.",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()
    value = check(args.directory)
    print(json.dumps(value, indent=2))
    raise SystemExit(0 if value["complete_archives_passed"] else 1)
