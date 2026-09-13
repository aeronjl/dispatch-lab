"""Standalone stdlib bundle checker. Usage: python -I -S check_bundle.py BUNDLE_DIRECTORY."""

import argparse
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def check(root):
    root = Path(root).resolve()
    manifest = json.loads((root / "bundle.json").read_text())
    if manifest.get("schema_version") != "dispatch-lab/reproduction-bundle/1":
        raise ValueError("Unknown bundle schema")
    for name, expected in manifest["files"].items():
        path = root / name
        if (
            Path(name).is_absolute()
            or ".." in Path(name).parts
            or not path.resolve().is_relative_to(root)
            or path.is_symlink()
        ):
            raise ValueError("Invalid bundle path")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError("Bundle file changed: " + name)
    result = json.loads(gzip.decompress((root / "recorded-run.json.gz").read_bytes()))
    if result.get("integrity_sha256") and result["integrity_sha256"] != digest(
        {k: v for k, v in result.items() if k != "integrity_sha256"}
    ):
        raise ValueError("Run integrity mismatch")
    checker = root / "checker/reference.py"
    spec = importlib.util.spec_from_file_location("dispatch_independent_reference", checker)
    reference = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(reference)
    physical = reference.audit(result)
    provenance = result.get("provenance", {})
    source = provenance.get("source", {})
    source_complete = manifest["source_status"] == "captured"
    if source_complete:
        for name, expected in source["files"].items():
            if hashlib.sha256((root / "source" / name).read_bytes()).hexdigest() != expected:
                raise ValueError("Original source mismatch: " + name)
        if (
            hashlib.sha256((root / "source/uv.lock").read_bytes()).hexdigest()
            != provenance["dependency_lock_hash"]
        ):
            raise ValueError("Original lock mismatch")
    return dict(
        schema_version="dispatch-lab/offline-verification/1",
        run_id=result["run_id"],
        bundle_inventory_hash=digest(manifest["files"]),
        source_status=manifest["source_status"],
        integrity_passed=True,
        reference_passed=physical["passed"],
        reference_checks=len(physical["checks"]),
        failures=[c for c in physical["checks"] if not c["passed"]],
        status="passed" if physical["passed"] else "incomplete-or-failed",
        scope="Recorded actions checked offline with an independent reference. No optimization rerun or claim of empirical calibration.",
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--out", type=Path)
    args = parser.parse_args()
    try:
        report = check(args.directory)
    except (ValueError, KeyError, OSError) as exc:
        report = {"status": "failed", "error": str(exc)}
    encoded = json.dumps(report, indent=2, allow_nan=False)
    if args.out:
        args.out.write_text(encoded)
    print(encoded)
    if report["status"] != "passed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
