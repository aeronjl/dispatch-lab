"""Local owner/agent capabilities for bounded simulator workers. No hardware access."""

import hashlib
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from methane import control_port
from methane.control_storage import committed, lease, read, running, transaction, write
from methane.provenance import LOADED_SOURCE
from methane.siting.store import digest

_lock = threading.RLock()
_workers = {}
_previews = threading.BoundedSemaphore(2)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal[
        "create",
        "sources",
        "recover",
        "extend",
        "replay",
        "cancel_replay",
        "observe",
        "preview",
        "advance",
        "trace",
        "grant",
        "revoke",
        "pause",
        "resume",
        "stop",
    ]
    key: str = Field(default="", max_length=250)
    token: str = Field(default="", max_length=100)
    run_id: str = Field(default="", max_length=100)
    controller: str = Field(default="", max_length=100)
    project_id: str = Field(default="", max_length=64)
    environment_id: str = Field(default="", max_length=64)
    study_id: str = Field(default="", max_length=64)
    case_id: str = Field(default="", max_length=32)
    start_hour: int = Field(default=0, ge=0, strict=True)
    synthetic: bool = False
    start: str = Field(default="2025-07-10T00:00:00Z", max_length=40)
    session_id: str = Field(default="", max_length=32)
    credential: str = Field(default="", max_length=100)
    hours: int = Field(default=24, ge=1, le=72, strict=True)
    wall_seconds: int = Field(default=3600, ge=60, le=7200, strict=True)
    revision: int | None = Field(default=None, ge=0, strict=True)
    actions: control_port.Actions | None = None
    proposal_id: str = Field(default="", max_length=32)
    request_id: str = Field(default="", max_length=100)
    reason: str = Field(default="", max_length=2000)
    permission: Literal["observe", "preview", "advance"] = "observe"


def home():
    return Path(os.environ.get("DISPATCH_CONTROL_DIR", "runs/control-sessions")).resolve()


def folder(identifier):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid session identifier")
    path = home() / identifier
    if not (path / "meta.json").exists():
        raise ValueError("Session does not exist")
    return path


def hashed(value):
    return hashlib.sha256(value.encode()).hexdigest()


def authorize(request, owner=False):
    root = folder(request.session_id)
    meta = read(root / "meta.json")
    expected = meta["owner_hash"] if owner else meta.get("agent_hash")
    if (
        not request.credential
        or not expected
        or not secrets.compare_digest(expected, hashed(request.credential))
    ):
        raise HTTPException(403, "This control capability is invalid or revoked")
    if not owner:
        if time.time() >= meta["expires_at"]:
            raise HTTPException(403, "The agent capability has expired")
        needed = {"observe": 0, "trace": 0, "preview": 1, "advance": 2}.get(request.operation)
        if (
            needed is None
            or needed > {"observe": 0, "preview": 1, "advance": 2}[meta["permission"]]
        ):
            raise HTTPException(403, "This operation is outside the agent's permission")
    return root, meta


def state(root):
    path = root / "state.json"
    value = read(path) if path.exists() else dict(status="starting", revision=0)
    if value["status"] in ("starting", "waiting", "executing"):
        if not running(root):
            return dict(
                status="interrupted",
                revision=value["revision"],
                error="Worker stopped. Recover from the last committed interval; any uncommitted request will need a fresh preview.",
            )
        if (root / "stop").exists():
            value = {**value, "status": "stopping"}
    return value


def receipts(root):
    saved = committed(root)
    if saved:
        return saved["receipts"]
    return [
        read(p)
        for p in sorted(root.glob("receipt-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
    ]


def view(root, meta):
    s = state(root)
    public = read(root / "observation.json") if (root / "observation.json").exists() else None
    saved = committed(root)
    next_hour = saved["next_hour"] if saved else meta.get("start_hour", 0)
    return dict(
        contract=control_port.VERSION,
        session_id=root.name,
        state=s,
        authority=dict(
            generation=meta["epoch"],
            paused=meta["paused"],
            agent_access=bool(meta.get("agent_hash")),
            permission=meta["permission"],
            scope="Process dispatch in this simulation only",
            hours=meta["hours"],
            expires_at=meta["expires_at"],
        ),
        continuation=dict(
            start_hour=meta.get("start_hour", 0),
            next_hour=next_hour,
            stop_hour=meta.get("stop_hour", meta["hours"]),
            total_hours=meta.get("total_hours", meta["hours"]),
            recoverable=bool(meta.get("input_sha256"))
            and not running(root)
            and next_hour < meta.get("stop_hour", meta["hours"]),
            extendable=bool(meta.get("input_sha256"))
            and not running(root)
            and next_hour == meta.get("stop_hour", meta["hours"])
            and next_hour < meta.get("total_hours", meta["hours"]),
        ),
        replay=replay_state(root),
        controller=meta["controller"],
        origin=meta["origin"],
        observation=public,
        receipts=receipts(root),
        scope="Frozen inputs and committed simulation state. Source records stay unchanged. Services remain under the configured executive.",
    )


def launch(root):
    # Inherited OS leases survive app restarts and fence duplicate workers.
    session_lease = lease(root / "worker.lock")
    slot = None
    try:
        for i in range(2):
            try:
                slot = lease(home() / f"slot-{i}.lock")
                break
            except ValueError:
                continue
        if slot is None:
            raise ValueError("Two sessions are active; stop one before creating another")
        with (root / "worker.log").open("ab") as log:
            _workers[root.name] = subprocess.Popen(
                [sys.executable, "-m", "methane.control_session_worker", str(root)],
                cwd=Path(__file__).resolve().parents[1],
                stdout=log,
                stderr=log,
                start_new_session=True,
                pass_fds=(session_lease.fileno(), slot.fileno()),
            )
    finally:
        session_lease.close()
        if slot:
            slot.close()


def create(request):
    from methane.control_sources import freeze

    inputs = freeze(request)
    with _lock:
        identifier, owner_key = secrets.token_hex(16), secrets.token_urlsafe(32)
        root = home() / identifier
        root.mkdir(parents=True, mode=0o700)
        start = inputs["start_hour"]
        meta = dict(
            id=identifier,
            origin=inputs["origin"].get("run_id", inputs["origin"]),
            controller=inputs["controller"],
            hours=request.hours,
            start_hour=start,
            stop_hour=start + request.hours,
            total_hours=inputs["total_hours"],
            input_sha256=digest(inputs),
            expires_at=time.time() + request.wall_seconds,
            created_at=time.time(),
            owner_hash=hashed(owner_key),
            agent_hash=None,
            permission="observe",
            paused=False,
            epoch=0,
            source_content_hash=LOADED_SOURCE["content_hash"],
        )
        write(root / "meta.json", meta)
        write(root / "input.json", inputs)
        write(root / "state.json", dict(status="starting", revision=start))
        launch(root)
        return {**view(root, meta), "owner_key": owner_key}


def restart(root, meta, request):
    if not meta.get("input_sha256"):
        raise ValueError("Legacy session has no committed runtime; its recording remains readable")
    if running(root):
        raise ValueError("Worker is still active; stop and wait before recovering")
    if meta["source_content_hash"] != LOADED_SOURCE["content_hash"]:
        raise ValueError(
            "Checkpoint implementation differs. Restore its original source to continue."
        )
    inputs = read(root / "input.json")
    if digest(inputs) != meta["input_sha256"]:
        raise ValueError("Frozen session inputs changed")
    saved = committed(root)
    boundary = saved["next_hour"] if saved else inputs["start_hour"]
    if request.operation == "extend":
        if boundary != meta["stop_hour"] or boundary + request.hours > meta["total_hours"]:
            raise ValueError(
                "Continue a completed session within its remaining frozen weather window"
            )
        meta["stop_hour"] += request.hours
        meta["hours"] += request.hours
    elif boundary >= meta["stop_hour"]:
        raise ValueError("All authorised intervals are committed; use Continue to authorise more")
    command = root / f"command-{boundary}.json"
    if command.exists():
        command.rename(root / f"uncommitted-{boundary}-{secrets.token_hex(8)}.json")
    meta.update(
        expires_at=time.time() + request.wall_seconds,
        epoch=meta["epoch"] + 1,
        agent_hash=None,
        permission="observe",
        paused=False,
    )
    write(root / "meta.json", meta)
    (root / "stop").unlink(missing_ok=True)
    write(root / "state.json", dict(status="starting", revision=boundary))
    launch(root)
    return view(root, meta)


def waiting(root, meta, revision):
    s = state(root)
    if meta["paused"] or time.time() >= meta["expires_at"] or (root / "stop").exists():
        raise ValueError("Session paused, stopped or expired; no action accepted")
    if (
        s["status"] != "waiting"
        or s["revision"] != revision
        or revision >= meta.get("stop_hour", meta["hours"])
    ):
        raise ValueError("Decision is no longer awaiting an action; refresh the observation")
    if (root / f"command-{revision}.json").exists():
        raise ValueError("An action has already been accepted for this interval")
    return read(root / "observation.json")


def dispatch(request, owner=False):
    if request.operation == "sources":
        if not owner:
            raise HTTPException(403, "Only the app owner can select projects")
        from methane.control_sources import catalogue

        return catalogue()
    if request.operation == "create":
        if not owner:
            raise HTTPException(403, "Only the app owner can create sessions")
        return create(request)
    root, _ = authorize(request, owner)
    with _lock, transaction(root):
        root, meta = authorize(request, owner)
        op = request.operation
        if op in ("recover", "extend"):
            return restart(root, meta, request)
        if op == "replay":
            return start_replay(root)
        if op == "cancel_replay":
            latest = replay_state(root)
            if latest:
                (root / "replays" / latest["id"] / "cancel").touch()
            return dict(status="cancellation requested")
        if op in ("observe", "trace"):
            return (
                view(root, meta)
                if op == "observe"
                else dict(
                    contract=control_port.VERSION, session_id=root.name, receipts=receipts(root)
                )
            )
        if op in ("grant", "revoke", "pause", "resume", "stop"):
            meta["epoch"] += 1
            value = {}
            if op == "grant":
                key = secrets.token_urlsafe(32)
                meta.update(agent_hash=hashed(key), permission=request.permission)
                value["agent_token"] = key
            if op == "revoke":
                meta["agent_hash"] = None
            if op in ("pause", "resume"):
                meta["paused"] = op == "pause"
            if op == "stop":
                (root / "stop").touch()
                meta["agent_hash"] = None
            write(root / "meta.json", meta)
            return {**view(root, meta), **value}
        if op == "advance":
            if not request.request_id or not request.reason.strip() or request.revision is None:
                raise ValueError("Advance needs a revision, unique request ID and reason")
            existing = root / f"command-{request.revision}.json"
            if existing.exists():
                previous = read(existing)
                if (
                    previous["request_id"],
                    previous["proposal_id"],
                    previous["actor"],
                    previous["epoch"],
                ) == (
                    request.request_id,
                    request.proposal_id,
                    "operator" if owner else "agent",
                    meta["epoch"],
                ):
                    return dict(
                        status="accepted", revision=request.revision, request_id=request.request_id
                    )
                raise ValueError("This interval already has a different accepted action")
            public = waiting(root, meta, request.revision)
            if not re.fullmatch(r"[a-f0-9]{32}", request.proposal_id):
                raise ValueError("Preview an action before advancing")
            proposal_path = root / f"proposal-{request.proposal_id}.json"
            if not proposal_path.exists():
                raise ValueError("Proposal does not belong to this session")
            proposal = read(proposal_path)
            if (
                proposal["epoch"] != meta["epoch"]
                or proposal["information_id"] != public["information_id"]
            ):
                raise ValueError("Proposal is stale; preview against the current observation")
            # Exactly one command file per decision under the app's transaction lock.
            write(
                existing,
                {
                    **proposal,
                    "actor": "operator" if owner else "agent",
                    "reason": request.reason,
                    "accepted_at": time.time(),
                    "request_id": request.request_id,
                },
            )
            return dict(status="accepted", revision=request.revision, request_id=request.request_id)
        public = waiting(root, meta, request.revision)
        epoch = meta["epoch"]
    # Solver work has a separate capacity limit, never blocks revoke/pause.
    if not _previews.acquire(blocking=False):
        raise ValueError("Two previews are running; retry shortly")
    try:
        result = control_port.preview(
            public, request.actions.model_dump() if request.actions else None
        )
    finally:
        _previews.release()
    with _lock, transaction(root):
        root, meta = authorize(request, owner)
        latest = waiting(root, meta, request.revision)
        if epoch != meta["epoch"] or latest["information_id"] != public["information_id"]:
            raise ValueError("Control context changed during preview; request a fresh preview")
        if len(list(root.glob("proposal-*.json"))) >= 1000:
            raise ValueError("Session preview budget exhausted")
        identifier = secrets.token_hex(16)
        proposal = dict(
            proposal_id=identifier,
            epoch=epoch,
            information_id=public["information_id"],
            preview=result,
        )
        write(root / f"proposal-{identifier}.json", proposal)
        return {
            **proposal,
            "revision": request.revision,
            "scope": "Prediction only; simulation has not advanced.",
        }


def handle(request: Request):
    return _handle(request, True)


def agent(request: Request):
    value = _handle(request, False)
    # Replay comparisons contain retrospective physical deltas and are owner-only.
    value.pop("replay", None)
    return value


def _handle(request, owner):
    try:
        return {**dispatch(request, owner), "key": request.key}
    except (ValueError, KeyError, TypeError, FileNotFoundError) as exc:
        raise HTTPException(409, str(exc)) from exc


def recording(identifier, owner_key, replay_id=None):
    root, _ = authorize(
        Request(operation="observe", session_id=identifier, credential=owner_key), True
    )
    if replay_id:
        if not re.fullmatch(r"[a-f0-9]{32}", replay_id):
            raise ValueError("Invalid replay edition")
        from methane.provenance import verify

        return verify(read(root / "replays" / replay_id / "recording.json"))
    saved = committed(root)
    if saved:
        return saved["recording"]
    if not (root / "recording.json").exists():
        raise ValueError("No completed interval is available yet")
    from methane.provenance import verify

    result = read(root / "recording.json")
    if not verify(result):
        raise ValueError("Recording integrity failed")
    return result


def cleanup():
    for identifier, worker in list(_workers.items()):
        if worker.poll() is None:
            if identifier.startswith("replay-"):
                worker.terminate()
                worker.wait(timeout=5)
                continue
            (home() / identifier / "stop").touch()
            try:
                worker.wait(timeout=1)
            except subprocess.TimeoutExpired:
                worker.terminate()
                worker.wait(timeout=5)
    _workers.clear()


def replay_state(root):
    pointer = root / "replay.json"
    if not pointer.exists():
        return None
    key = read(pointer)["id"]
    directory = root / "replays" / key
    s = read(directory / "state.json")
    if s["status"] == "running":
        try:
            with lease(root / "replay.lock"):
                s = dict(
                    status="interrupted",
                    error="Replay worker stopped; the original session is unchanged",
                )
        except ValueError:
            pass
    return {"id": key, **s}


def start_replay(root):
    saved = committed(root)
    if not saved:
        raise ValueError("Complete an interval before replaying recorded requests")
    key = secrets.token_hex(16)
    replay_root = root / "replays" / key
    with lease(root / "replay.lock") as handle:
        # Share the bounded worker budget with interactive sessions.
        slot = None
        for i in range(2):
            try:
                slot = lease(home() / f"slot-{i}.lock")
                break
            except ValueError:
                continue
        if slot is None:
            raise ValueError("Two workers are active; stop one before replaying")
        with slot:
            write(replay_root / "source.json", saved["recording"])
            write(replay_root / "state.json", dict(status="running", fraction=0))
            with (replay_root / "worker.log").open("ab") as log:
                _workers["replay-" + key] = subprocess.Popen(
                    [sys.executable, "-m", "methane.control_replay", str(replay_root)],
                    cwd=Path(__file__).resolve().parents[1],
                    stdout=log,
                    stderr=log,
                    start_new_session=True,
                    pass_fds=(handle.fileno(), slot.fileno()),
                )
            write(root / "replay.json", dict(id=key))
    return replay_state(root)
