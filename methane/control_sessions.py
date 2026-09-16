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
from methane.control_session_worker import read, write
from methane.model_service import recorded_context
from methane.provenance import LOADED_SOURCE

_lock = threading.RLock()
_workers = {}
_previews = threading.BoundedSemaphore(2)


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal[
        "create",
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
        worker = _workers.get(root.name)
        if worker is None or worker.poll() is not None:
            return dict(
                status="interrupted",
                revision=value["revision"],
                error="Worker stopped. Completed intervals remain available; create a new session to continue exploration.",
            )
        if (root / "stop").exists():
            value = {**value, "status": "stopping"}
    return value


def receipts(root):
    return [
        read(p)
        for p in sorted(root.glob("receipt-*.json"), key=lambda p: int(p.stem.split("-")[-1]))
    ]


def view(root, meta):
    s = state(root)
    public = read(root / "observation.json") if (root / "observation.json").exists() else None
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
        controller=meta["controller"],
        origin=meta["origin"],
        observation=public,
        receipts=receipts(root),
        scope="Fresh simulation from hour zero using frozen inputs and the current implementation. The source recording is unchanged. Services remain under the configured executive.",
    )


def create(request):
    source = recorded_context(request.token, request.run_id)
    if request.controller not in source["records"]:
        raise ValueError("Choose a recorded reference controller")
    # Site utility/checkpoint histories require a separately qualified session adapter.
    # Never silently drop limits or adopt a mid-history state as a new initial state.
    period = source.get("continuous_period", {})
    if period.get("start_hour", 0) or any(
        r.get("site_utilities") for rows in source["records"].values() for r in rows
    ):
        raise ValueError(
            "This recording carries site utilities or a continued initial state. Use a standard hour-zero plant run for interactive control."
        )
    if request.hours > source["config"]["scenario"]["hours"]:
        raise ValueError("Session hours exceed this recording's frozen weather window")
    hours = request.hours
    with _lock:
        if sum(p.poll() is None for p in _workers.values()) >= 2:
            raise ValueError("Two sessions are active; stop one before creating another")
        identifier, owner_key = secrets.token_hex(16), secrets.token_urlsafe(32)
        root = home() / identifier
        root.mkdir(parents=True, mode=0o700)
        meta = dict(
            id=identifier,
            origin=source["run_id"],
            controller=request.controller,
            hours=hours,
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
        provenance = source.get("provenance", {})
        write(
            root / "input.json",
            dict(
                config=source["config"],
                weather=source["weather"],
                controller=request.controller,
                policies={request.controller: provenance["controller_policies"][request.controller]}
                if provenance.get("controller_policies")
                else None,
                uncertainty=provenance.get("uncertainty_world"),
            ),
        )
        with (root / "worker.log").open("wb") as log:
            _workers[identifier] = subprocess.Popen(
                [sys.executable, "-m", "methane.control_session_worker", str(root)],
                cwd=Path(__file__).resolve().parents[1],
                stdout=log,
                stderr=log,
                start_new_session=True,
            )
        return {**view(root, meta), "owner_key": owner_key}


def waiting(root, meta, revision):
    s = state(root)
    if meta["paused"] or time.time() >= meta["expires_at"] or (root / "stop").exists():
        raise ValueError("Session paused, stopped or expired; no action accepted")
    if s["status"] != "waiting" or s["revision"] != revision or revision >= meta["hours"]:
        raise ValueError("Decision is no longer awaiting an action; refresh the observation")
    if (root / f"command-{revision}.json").exists():
        raise ValueError("An action has already been accepted for this interval")
    return read(root / "observation.json")


def dispatch(request, owner=False):
    if request.operation == "create":
        if not owner:
            raise HTTPException(403, "Only the app owner can create sessions")
        return create(request)
    with _lock:
        root, meta = authorize(request, owner)
        op = request.operation
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
    with _lock:
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
    return _handle(request, False)


def _handle(request, owner):
    try:
        return {**dispatch(request, owner), "key": request.key}
    except (ValueError, KeyError, TypeError) as exc:
        raise HTTPException(409, str(exc)) from exc


def recording(identifier, owner_key):
    root, _ = authorize(
        Request(operation="observe", session_id=identifier, credential=owner_key), True
    )
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
            (home() / identifier / "stop").touch()
            try:
                worker.wait(timeout=1)
            except subprocess.TimeoutExpired:
                worker.terminate()
                worker.wait(timeout=5)
    _workers.clear()
