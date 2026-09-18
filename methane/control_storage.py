"""Private control checkpoints and process leases; never an agent observation API."""

import fcntl
import json
from contextlib import contextmanager

from methane.provenance import seal, verify
from methane.siting.store import atomic, digest, encode


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    atomic(path, encode(value))


def committed(root):
    path = root / "commit.json"
    if not path.exists():
        return None
    value = read(path)
    if value["sha256"] != digest(value["value"]):
        raise ValueError("Control checkpoint transaction integrity mismatch")
    value = value["value"]
    verify(value["recording"])
    if value["checkpoint"]["next_hour"] != value["next_hour"]:
        raise ValueError("Control checkpoint and receipt boundary disagree")
    return value


def commit(root, checkpoint, recording, receipts):
    value = dict(
        schema_version="dispatch-control-commit/1",
        next_hour=checkpoint["next_hour"],
        checkpoint=checkpoint,
        recording=seal(recording),
        receipts=receipts,
    )
    # The single replacement is the commit. Never restore from a loose command or row.
    write(root / "commit.json", dict(value=value, sha256=digest(value)))


def lease(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = path.open("a+b")
    try:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        handle.close()
        raise ValueError("A worker still owns this session; wait for it to stop") from None
    return handle


def running(root):
    try:
        with lease(root / "worker.lock"):
            return False
    except ValueError:
        return True


@contextmanager
def transaction(root):
    """Serialise owner/agent commands even across two local app processes."""
    with (root / "commands.lock").open("a+b") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        yield
