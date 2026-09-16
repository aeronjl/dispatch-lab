"""Content-addressed local documents and original source bytes; append-only editions."""

import hashlib
import json
import os
import re
import tempfile
from pathlib import Path

ROOT = Path(
    os.environ.get("DISPATCH_SITES_ROOT", Path(__file__).resolve().parents[2] / "runs" / "sites")
)
KINDS = {
    "equipment-basis",
    "commissioning-review",
    "equipment-observations",
    "equipment-comparison",
    "requirements",
    "operating-assessment",
    "project",
    "site",
    "source",
    "assessment",
    "evidence",
    "design",
    "environment",
    "study",
    "cashflow",
    "recommendation",
    "measurement",
    "publication",
    "discovery",
    "template",
    "dataset",
    "training",
    "model",
    "deployment",
    "evaluation",
    "walkthrough",
    "difference",
    "investigation",
    "investigation-index",
    "decision-comparison",
}


def encode(value):
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()


def digest(value):
    return hashlib.sha256(encode(value)).hexdigest()


def identifier(value):
    if not isinstance(value, str) or re.fullmatch(r"[a-f0-9]{64}", value) is None:
        raise ValueError("Invalid saved record identity")
    return value


def atomic(path, raw):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, delete=False) as stream:
        temporary = Path(stream.name)
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    temporary.replace(path)


class Store:
    def __init__(self, root=ROOT):
        self.root = Path(root)

    def path(self, kind, key):
        if kind not in KINDS:
            raise ValueError("Unknown Sites record kind")
        return self.root / kind / (identifier(key) + ".json")

    def put(self, kind, value):
        if hasattr(value, "model_dump"):
            value = value.model_dump(mode="json")
        key = digest(value)
        path = self.path(kind, key)
        if path.exists():
            self.get(kind, key)
        else:
            atomic(path, encode(value))
        return key

    def get(self, kind, key):
        path = self.path(kind, key)
        value = json.loads(path.read_bytes())
        if digest(value) != key:
            raise ValueError("Saved Sites record integrity mismatch")
        return value

    def list(self, kind):
        if kind not in KINDS:
            raise ValueError("Unknown Sites record kind")
        return [
            {"id": p.stem, **self.get(kind, p.stem)}
            for p in sorted((self.root / kind).glob("*.json"))
        ]

    def raw(self, raw):
        key = hashlib.sha256(raw).hexdigest()
        path = self.root / "raw" / key
        if not path.exists():
            atomic(path, raw)
        elif hashlib.sha256(path.read_bytes()).hexdigest() != key:
            raise ValueError("Original source bytes have changed")
        return key

    def read_raw(self, key):
        raw = (self.root / "raw" / identifier(key)).read_bytes()
        if hashlib.sha256(raw).hexdigest() != key:
            raise ValueError("Original source bytes have changed")
        return raw
