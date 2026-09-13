"""Capture allowlisted project bytes at process load, before any run is dispatched."""

import base64
import hashlib
import io
import json
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def capture():
    paths = [*ROOT.glob("*.py")]
    for directory in ("methane", "assets", "tests", "formal", "docs"):
        paths += [
            p
            for p in (ROOT / directory).rglob("*")
            if p.is_file()
            and "__pycache__" not in p.parts
            and p.suffix not in (".pyc", ".log")
            and "snapshots" not in p.parts
        ]
    for filename in (
        "pyproject.toml",
        "uv.lock",
        "package.json",
        "package-lock.json",
        "playwright.config.cjs",
        "README.md",
        ".github/workflows/checks.yml",
    ):
        if (ROOT / filename).is_file():
            paths.append(ROOT / filename)
    return {
        str(p.relative_to(ROOT)): p.read_bytes() for p in sorted(set(paths)) if not p.is_symlink()
    }


def encode(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, data in sorted(files.items()):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            z.writestr(info, data)
    raw = stream.getvalue()
    return dict(
        schema_version="dispatch-lab/source-capsule/1",
        sha256=hashlib.sha256(raw).hexdigest(),
        encoding="base64+zip",
        payload=base64.b64encode(raw).decode(),
        files={k: hashlib.sha256(v).hexdigest() for k, v in files.items()},
    )


def decode(capsule):
    raw = base64.b64decode(capsule["payload"], validate=True)
    if hashlib.sha256(raw).hexdigest() != capsule["sha256"]:
        raise ValueError("Source capsule hash mismatch")
    with zipfile.ZipFile(io.BytesIO(raw)) as z:
        names = z.namelist()
        if len(names) != len(set(names)) or set(names) != set(capsule["files"]):
            raise ValueError("Source capsule inventory mismatch")
        if sum(i.file_size for i in z.infolist()) > 100_000_000:
            raise ValueError("Source capsule exceeds allowed size")
        files = {}
        for name in names:
            path = Path(name)
            if path.is_absolute() or ".." in path.parts or "\\" in name:
                raise ValueError("Invalid capsule path")
            data = z.read(name)
            if hashlib.sha256(data).hexdigest() != capsule["files"][name]:
                raise ValueError("Source file hash mismatch")
            files[name] = data
    return files


def inventory_hash(files):
    return hashlib.sha256(
        json.dumps(files, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
