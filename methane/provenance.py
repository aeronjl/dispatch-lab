"""Input identity, content integrity and explicit recomputation provenance."""

import copy
import hashlib
import json
import platform
import subprocess
from importlib.metadata import version
from pathlib import Path

from methane.audit import ABSOLUTE, RELATIVE
from methane.components import assemble
from methane.contracts import SPECS
from methane.source_capsule import capture, encode

ROOT = Path(__file__).resolve().parent.parent
RNG_POLICY = "named-channels/1"


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


LOADED_FILES = capture()
LOADED_CAPSULE = encode(LOADED_FILES)


def source_identity():
    files = {
        name: hashlib.sha256(data).hexdigest()
        for name, data in LOADED_FILES.items()
        if name.endswith(".py") or name.startswith("assets/")
    }
    release = ROOT / "dispatch-release.json"
    if release.exists():
        manifest = json.loads(release.read_text())
        expected = {
            k: v
            for k, v in manifest["files"].items()
            if k.endswith(".py") or k.startswith("assets/")
        }
        if files != expected:
            raise ValueError("Installed executable source differs from its release manifest")
        revision, dirty = manifest["revision"], manifest["dirty"]
    else:
        try:
            revision = subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, stderr=subprocess.DEVNULL, text=True
            ).strip()
        except (subprocess.CalledProcessError, FileNotFoundError):
            revision = "unavailable"
        try:
            dirty = bool(
                subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True)
            )
        except (subprocess.CalledProcessError, FileNotFoundError):
            dirty = None
    return {"revision": revision, "dirty": dirty, "content_hash": digest(files), "files": files}


LOADED_SOURCE = source_identity()
LOADED_LOCK = hashlib.sha256(LOADED_FILES["uv.lock"]).hexdigest()


def manifest(config, weather, strategies):
    environment = {name: version(name) for name in ("numpy", "scipy", "gradio")}
    environment.update(
        python=platform.python_version(), platform=platform.platform(), machine=platform.machine()
    )
    snapshots = [
        {
            "request_id": x.get("id"),
            "payload_hash": digest(x.get("raw", x)),
            "metadata": {k: v for k, v in x.items() if k != "raw"},
        }
        for x in weather.get("snapshots", [])
    ]
    return {
        "version": "dispatch-lab/provenance/1",
        "source": copy.deepcopy(LOADED_SOURCE),
        "source_capsule": copy.deepcopy(LOADED_CAPSULE),
        "dependency_lock_hash": LOADED_LOCK,
        "environment": environment,
        "components": {k: v.to_dict() for k, v in SPECS.items()},
        "implementations": assemble(config.plant, config.models).identities(),
        "rng_policy": config.rng_policy,
        "seed": config.scenario.seed,
        "solver": {
            "interface": "scipy.optimize.milp",
            "planning_seconds": config.scenario.solver_seconds,
            "execution_seconds": 0.5,
            "relative_gap": 0.001,
            "integrality_tolerance": 1e-5,
            "threads": 1,
        },
        "audit_tolerances": {"absolute": ABSOLUTE, "relative": RELATIVE},
        "weather_content_hash": digest(weather),
        "snapshots": snapshots,
        "config": config.to_dict(),
        "strategies": list(strategies),
        "recomputation": "Time-limited solving is not guaranteed bitwise reproducible; playback uses recorded actions.",
    }


def experiment_identity(manifest):
    # Dirty/revision metadata is retained for audit; content identifies executable source.
    value = {**manifest, "source": {"content_hash": manifest["source"]["content_hash"]}}
    if "source_capsule" in value:
        value["source_capsule"] = {
            k: v for k, v in value["source_capsule"].items() if k != "payload"
        }
    return digest(value)


def seal(result):
    result["integrity_sha256"] = digest(
        {k: v for k, v in result.items() if k != "integrity_sha256"}
    )
    return result


def verify(result):
    if result.get("schema_version") == "dispatch-lab/methane/3":
        expected = digest({k: v for k, v in result.items() if k != "integrity_sha256"})
        if result.get("integrity_sha256") != expected:
            raise ValueError("Archive integrity check failed: payload has changed.")
        if digest(result["weather"]) != result["provenance"]["weather_content_hash"]:
            raise ValueError("Archive weather does not match its manifest.")
        if result["config"] != result["provenance"]["config"]:
            raise ValueError("Archive configuration does not match its manifest.")
        if experiment_identity(result["provenance"]) != result.get("experiment_id"):
            raise ValueError("Archive experiment identity does not match its manifest.")
    return result
