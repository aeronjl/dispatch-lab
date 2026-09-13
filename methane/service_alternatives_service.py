"""Cancellable service comparisons, bound to run/decision/client generation."""

import json
import os
import secrets
import subprocess
import sys
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path
from time import monotonic
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field

from methane.model_service import recorded_context
from methane.services import investigation_alternatives
from methane.services.alternatives import _change, prepare
from methane.services.coupling import identity

_jobs = OrderedDict()
_cancelled = OrderedDict()
_lock = threading.RLock()
_MAX_JOBS = 16
_MAX_WORKERS = 2


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=100)
    run_id: str = Field(max_length=100)
    key: str = Field(max_length=250)
    controller: str = Field(max_length=100)
    hour: int = Field(ge=0, strict=True)
    operation: Literal["describe", "start", "poll", "cancel"]
    alternative: dict = Field(default_factory=dict)
    job_id: str | None = Field(default=None, max_length=100)


def _context(request):
    return (request.token, request.run_id, request.controller, request.hour, request.key)


def _stop(entry, status="cancelled"):
    if entry.get("timer"):
        entry["timer"].cancel()
    worker = entry["worker"]
    if worker.poll() is None:
        worker.terminate()
        try:
            worker.wait(timeout=0.5)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait(timeout=1)
    entry["stopped"] = status


def cleanup():
    with _lock:
        for entry in _jobs.values():
            _stop(entry)
            entry["directory"].cleanup()
        _jobs.clear()
        _cancelled.clear()


def _reap():
    for entry in _jobs.values():
        if entry["worker"].poll() is None and monotonic() > entry["deadline"]:
            _stop(entry, "time-limit")
        if entry["worker"].poll() is None:
            try:
                recorded_context(entry["context"][0], entry["context"][1])
            except HTTPException:
                _stop(entry, "expired")


def _expire(identifier):
    # Enforce the wall budget even after the reader closes the pane.
    with _lock:
        entry = _jobs.get(identifier)
        if entry and entry["worker"].poll() is None:
            _stop(entry, "time-limit")


def _reply(entry, job_id):
    base = dict(key=entry["context"][-1], job_id=job_id, selection=entry["context"][1:4])
    if entry["stopped"]:
        return {
            **base,
            "status": entry["stopped"],
            "error": "No replacement result is published for a stopped comparison.",
        }
    root = Path(entry["directory"].name)
    if entry["worker"].poll() is None:
        progress = root / "progress.txt"
        return {
            **base,
            "status": "running",
            "progress": progress.read_text()
            if progress.exists()
            else "Starting isolated comparison",
        }
    result = root / "result.json"
    if result.exists():
        return {**json.loads(result.read_text()), **base}
    return {
        **base,
        "status": "failed",
        "error": "Service comparison worker failed; no replacement prediction is available.",
    }


def describe(packet):
    selected = {k for k, _ in packet["original_schedule"]["singles"]} | {
        k for keys, _ in packet["original_schedule"]["groups"] for k in keys
    }
    orders = []
    for order in packet["snapshot"]["orders"]:
        if order["id"] not in selected:
            continue
        recipe = packet["snapshot"]["recipes"][order["id"]]["plan"]
        orders.append(
            dict(
                order_id=order["id"],
                kind=order["kind"],
                action=recipe["order"]["action"] if recipe else None,
                target=recipe["interface"]["target_asset_id"] if recipe else None,
                shared_visit=next(
                    (
                        list(keys)
                        for keys, _ in packet["original_schedule"]["groups"]
                        if order["id"] in keys
                    ),
                    None,
                ),
                procedures=[
                    {k: v for k, v in choice.items() if k != "plan"}
                    for choice in packet["snapshot"]
                    .get("procedure_choices", {})
                    .get(order["id"], ())
                ],
            )
        )
    return dict(
        status="available",
        packet_id=packet["packet_id"],
        hours=len(packet["inputs"]["forecast"]["pv_kw"]),
        orders=orders,
        energy_targets=packet["targets"],
        reserve_available=packet["joint_charging"],
        procedures_recorded="procedure_choices" in packet["snapshot"],
        robots=[
            dict(
                name=name,
                capacity_kwh=packet["snapshot"]["config"][name + "_battery_kwh"],
                initial_kwh=packet["snapshot"]["resources"]["stock"]["energy:" + name],
            )
            for name in ("cleaner", "rover")
            if packet["snapshot"]["installed"].get(name)
        ],
        forecast_source=packet["inputs"]["forecast"]["source"],
        note="Alternatives use original forecasts, estimates and dispatch prices. Previously accepted work stays committed. Moving one shared-visit job moves its complete itinerary.",
    )


def describe_selection(result, controller, hour):
    investigation = investigation_alternatives.describe(result, controller, hour)
    try:
        response = describe(prepare(result, controller, hour))
    except (ValueError, KeyError, IndexError, TypeError) as exc:
        if investigation.get("selection_id") or "origin_hour" in investigation:
            response = dict(
                status="available",
                orders=[],
                robots=[],
                energy_targets=[],
                reserve_available=False,
                note=investigation["note"],
                schedule_unavailable=str(exc),
            )
        else:
            return dict(status="unavailable", error=str(exc))
    return {**response, "investigation": investigation}


def handle(request: Request):
    result = recorded_context(request.token, request.run_id)
    context = _context(request)
    with _lock:
        _reap()
        if request.operation == "cancel":
            if request.job_id:
                entry = _jobs.get(request.job_id)
                if entry is None or entry["context"] != context:
                    raise HTTPException(410, "Cannot cancel a comparison from another selection")
            # Cancellation may arrive before the start response/job ID. Keep
            # a tombstone so an out-of-order start cannot revive this generation.
            _cancelled[context] = True
            while len(_cancelled) > 128:
                _cancelled.popitem(last=False)
            for identifier, entry in _jobs.items():
                if entry["context"] == context and (
                    not request.job_id or request.job_id == identifier
                ):
                    _stop(entry)
            return dict(key=request.key, status="cancelled")
        if request.operation == "poll":
            entry = _jobs.get(request.job_id)
            if entry is None or entry["context"] != context:
                raise HTTPException(
                    410, "Service comparison belongs to another selection or has expired"
                )
            if request.alternative and identity(request.alternative) != entry["alternative_id"]:
                raise HTTPException(409, "Changed inputs require a new calculation generation")
            return _reply(entry, request.job_id)
        if context in _cancelled:
            return dict(key=request.key, status="cancelled")
        if request.operation == "start":
            for identifier, entry in _jobs.items():
                if entry["context"] == context:
                    if entry["alternative_id"] != identity(request.alternative):
                        raise HTTPException(
                            409, "Changed inputs require a new calculation generation"
                        )
                    return _reply(entry, identifier)
        try:
            if request.operation == "describe":
                return {
                    **describe_selection(result, request.controller, request.hour),
                    "key": request.key,
                }
            if request.alternative.get("kind") == "investigation":
                packet = investigation_alternatives.prepare(
                    result, request.controller, request.hour
                )
                investigation_alternatives.validate_request(packet, request.alternative)
            else:
                packet = prepare(result, request.controller, request.hour)
                _change(packet, request.alternative)
        except (ValueError, KeyError, IndexError, TypeError) as exc:
            return dict(key=request.key, status="unavailable", error=str(exc))
        for entry in _jobs.values():
            if entry["context"][0] == request.token and entry["worker"].poll() is None:
                _stop(entry)
        if sum(e["worker"].poll() is None for e in _jobs.values()) >= _MAX_WORKERS:
            return dict(
                key=request.key,
                status="busy",
                error="Two service comparisons are active; retry shortly.",
            )
        directory = tempfile.TemporaryDirectory(prefix="dispatch-service-comparison-")
        root = Path(directory.name)
        try:
            (root / "input.json").write_text(
                json.dumps(dict(packet=packet, alternative=request.alternative), allow_nan=False)
            )
            env = {
                **os.environ,
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "VECLIB_MAXIMUM_THREADS": "1",
                "DISPATCH_BATCH_WORKER": "1",
            }
            with (root / "worker.log").open("w") as log:
                worker = subprocess.Popen(
                    [sys.executable, "-m", "methane.service_alternatives_worker", str(root)],
                    cwd=Path(__file__).resolve().parent.parent,
                    env=env,
                    stdout=log,
                    stderr=log,
                )
        except Exception:
            directory.cleanup()
            raise
        identifier = secrets.token_urlsafe(20)
        _jobs[identifier] = dict(
            context=context,
            worker=worker,
            directory=directory,
            stopped=None,
            alternative_id=identity(request.alternative),
            # Two bounded solves plus startup/postsolve allowance. This is
            # wall time for the comparison, distinct from each solver limit.
            deadline=monotonic() + max(30, 2 * packet["seconds"] + 15),
        )
        timer = threading.Timer(max(30, 2 * packet["seconds"] + 15), _expire, (identifier,))
        timer.daemon = True
        _jobs[identifier]["timer"] = timer
        timer.start()
        while len(_jobs) > _MAX_JOBS:
            _, old = _jobs.popitem(last=False)
            _stop(old)
            old["directory"].cleanup()
        return dict(key=request.key, status="running", job_id=identifier)
