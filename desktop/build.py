"""Prepare a relocatable, locked Python payload; no developer runtime at launch.

Run with uv run python desktop/build.py. This is a build-host operation, not an
installer action. Existing payloads are retained under build/desktop/history.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PYTHON = "3.12.13"
sys.path.insert(0, str(ROOT))


def run(args):
    result = subprocess.run(args, cwd=ROOT, capture_output=True, text=True)
    if result.returncode:
        raise RuntimeError(result.stderr.strip() or result.stdout.strip())
    return result.stdout.strip()


def write_source(destination):
    from methane.provenance import LOADED_CAPSULE, LOADED_FILES, LOADED_SOURCE

    destination.mkdir(parents=True)
    for name, content in LOADED_FILES.items():
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    manifest = dict(
        format="dispatch-desktop-source/1",
        revision=LOADED_SOURCE["revision"],
        dirty=LOADED_SOURCE["dirty"],
        content_hash=LOADED_SOURCE["content_hash"],
        source_capsule_sha256=LOADED_CAPSULE["sha256"],
        files={k: hashlib.sha256(v).hexdigest() for k, v in LOADED_FILES.items()},
    )
    (destination / "dispatch-release.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--source-only", action="store_true")
    args = parser.parse_args()
    build = ROOT / "build" / "desktop"
    payload = build / "payload"
    history = build / "history" / str(time.time_ns())
    if args.source_only:
        if not (payload / "python").is_dir():
            parser.error("Build the runtime before refreshing its source")
        history.mkdir(parents=True)
        if (payload / "source").exists():
            (payload / "source").rename(history / "source")
    else:
        if payload.exists():
            history.mkdir(parents=True)
            payload.rename(history / "payload")
        payload.mkdir(parents=True)
        uv = shutil.which("uv")
        if not uv:
            parser.error("uv is required on the build host")
        run([uv, "python", "install", PYTHON])
        executable = Path(run([uv, "python", "find", "--managed-python", PYTHON]))
        source = executable.parent if os.name == "nt" else executable.parent.parent
        shutil.copytree(
            source,
            payload / "python",
            symlinks=True,
            ignore=shutil.ignore_patterns("__pycache__", "*.pyc"),
        )
        # uv's Windows standalone build uses ordinary layout, not an isolated
        # embeddable _pth layout. Retain all standard-library/native dependencies.
        packaged = payload / "python" / ("python.exe" if os.name == "nt" else "bin/python3.12")
        requirements = build / "requirements.txt"
        run(
            [
                uv,
                "export",
                "--locked",
                "--no-dev",
                "--no-emit-project",
                "--format",
                "requirements-txt",
                "--output-file",
                str(requirements),
            ]
        )
        run(
            [
                uv,
                "pip",
                "sync",
                "--python",
                str(packaged),
                "--require-hashes",
                "--break-system-packages",
                str(requirements),
            ]
        )
        # Scripts with build-host shebangs are not used. Runtime entry points are
        # explicit private-interpreter commands, never pip/uv or package executables.
        info = json.loads(
            run(
                [
                    str(packaged),
                    "-c",
                    "import sys,platform,json; print(json.dumps(dict(python=sys.version,platform=platform.platform(),machine=platform.machine())))",
                ]
            )
        )
        runtime = dict(
            format="dispatch-desktop-runtime/1",
            **info,
            lock_sha256=hashlib.sha256((ROOT / "uv.lock").read_bytes()).hexdigest(),
        )
        runtime["dependencies"] = json.loads(
            run(
                [
                    str(packaged),
                    "-c",
                    "import importlib.metadata as m,json; print(json.dumps(sorted([dict(name=d.metadata['Name'],version=d.version,license_expression=d.metadata.get('License-Expression'),license=d.metadata.get('License'),wheel=d.read_text('WHEEL')) for d in m.distributions()], key=lambda d:d['name'].lower())))",
                ]
            )
        )
        (payload / "runtime.json").write_text(json.dumps(runtime, indent=2))
    manifest = write_source(payload / "source")
    size = sum(p.stat().st_size for p in payload.rglob("*") if p.is_file())
    report = dict(
        payload_bytes=size,
        source_content_hash=manifest["content_hash"],
        interpreter=PYTHON,
        source_capsule_sha256=manifest["source_capsule_sha256"],
    )
    (build / "payload-report.json").write_text(json.dumps(report, indent=2))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
