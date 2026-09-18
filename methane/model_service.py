"""Read-only documentation transport and bounded, cancellable teaching workers."""

import json
import os
import secrets
import subprocess
import tempfile
import threading
from collections import OrderedDict
from pathlib import Path

from fastapi import HTTPException
from pydantic import BaseModel, Field

from methane.documentation import catalogue, read
from methane.learning import evaluate
from methane.model_topics import TOPICS
from methane.processes import spawn

_contexts = OrderedDict()
_jobs = OrderedDict()
_cancelled = OrderedDict()
_lock = threading.RLock()


class Request(BaseModel):
    token: str = Field(max_length=100)
    run_id: str = Field(max_length=100)
    key: str = Field(max_length=250)
    topic: str = Field(max_length=40)
    context: str = "Current model"
    controller: str | None = None
    hour: int = Field(default=0, ge=0)
    inputs: dict = Field(default_factory=dict)
    prices: dict | None = None
    service_prices: dict | None = None
    operation: str = "start"
    job_id: str | None = None


def register(result):
    token = secrets.token_urlsafe(32)
    with _lock:
        _contexts[token] = result  # Every consumer is read-only; no additional archive-sized copy.
        while len(_contexts) > 8:
            old, _ = _contexts.popitem(last=False)
            for job in _jobs.values():
                if job["token"] == old:
                    _stop(job)
    return token


def recorded_context(token, run_id):
    """Resolve a server-owned run for read-only inspectors and calculations."""
    with _lock:
        result = _contexts.get(token)
        if result is None or result["run_id"] != run_id:
            raise HTTPException(410, "Documentation context expired; reopen the saved run.")
        return result


def source(request):
    result = recorded_context(request.token, request.run_id)
    if request.topic not in TOPICS:
        raise HTTPException(400, "Unknown topic")
    return result


def document(request: Request):
    result = source(request)
    try:
        return {
            **read(
                result,
                request.topic,
                request.context,
                request.controller,
                request.hour,
                request.prices,
                **(
                    {"service_prices": request.service_prices}
                    if "service_prices" in request.model_fields_set
                    else {}
                ),
            ),
            "key": request.key,
        }
    except (ValueError, KeyError, IndexError) as exc:
        return {"key": request.key, "status": "unavailable", "error": str(exc)}


def example(request: Request):
    source(request)
    if TOPICS[request.topic]["explicit_calculation"]:
        raise HTTPException(400, "This example requires the isolated calculation action")
    try:
        answer = evaluate(request.topic, request.inputs)
    except ValueError as exc:
        answer = {"status": "incomplete", "error": str(exc)}
    return {**answer, "key": request.key, "source": catalogue()["source"]}


def _stop(job):
    worker = job["worker"]
    if worker.poll() is None:
        worker.terminate()
        try:
            worker.wait(timeout=1)
        except subprocess.TimeoutExpired:
            worker.kill()
            worker.wait()
    job["cancelled"] = True


def job(request: Request):
    source(request)
    with _lock:
        request_id = (request.token, request.key)
        if request.operation == "cancel" and request.job_id is None:
            _cancelled[request_id] = True
            while len(_cancelled) > 128:
                _cancelled.popitem(last=False)
            for entry in _jobs.values():
                if (entry["token"], entry["key"]) == request_id:
                    _stop(entry)
            return {"key": request.key, "status": "cancelled"}
        if request.operation == "start":
            if request_id in _cancelled:
                return {"key": request.key, "status": "cancelled"}
            if not TOPICS[request.topic]["explicit_calculation"]:
                raise HTTPException(400, "This example does not require a worker")
            # One active teaching job per reader, two globally. Never occupy the app solver thread.
            for entry in _jobs.values():
                if entry["token"] == request.token and entry["worker"].poll() is None:
                    _stop(entry)
            if sum(j["worker"].poll() is None for j in _jobs.values()) >= 2:
                return {
                    "key": request.key,
                    "status": "busy",
                    "error": "Two teaching calculations are active; try again shortly.",
                }
            from methane.learning import validate

            try:
                values = validate(request.topic, request.inputs)
            except ValueError as exc:
                return {"key": request.key, "status": "incomplete", "error": str(exc)}
            directory = tempfile.TemporaryDirectory(prefix="dispatch-learning-")
            root = Path(directory.name)
            (root / "input.json").write_text(json.dumps({"topic": request.topic, "inputs": values}))
            env = {
                **os.environ,
                "OMP_NUM_THREADS": "1",
                "OPENBLAS_NUM_THREADS": "1",
                "MKL_NUM_THREADS": "1",
                "VECLIB_MAXIMUM_THREADS": "1",
                "DISPATCH_BATCH_WORKER": "1",
            }
            log = (root / "worker.log").open("w")
            worker = spawn(
                "methane.learning_worker",
                [root],
                cwd=Path(__file__).resolve().parent.parent,
                env=env,
                stdout=log,
                stderr=log,
            )
            log.close()
            identifier = secrets.token_urlsafe(20)
            _jobs[identifier] = {
                "worker": worker,
                "directory": directory,
                "token": request.token,
                "topic": request.topic,
                "key": request.key,
                "cancelled": False,
            }
            while len(_jobs) > 16:
                _, old = _jobs.popitem(last=False)
                _stop(old)
                old["directory"].cleanup()
            return {"key": request.key, "status": "running", "job_id": identifier}
        entry = _jobs.get(request.job_id)
        if not entry or entry["token"] != request.token or entry["topic"] != request.topic:
            raise HTTPException(410, "Teaching calculation unavailable")
        if request.operation == "cancel":
            _stop(entry)
        if entry["cancelled"]:
            return {"key": request.key, "status": "cancelled"}
        root = Path(entry["directory"].name)
        if entry["worker"].poll() is None:
            progress = (
                (root / "progress.txt").read_text()
                if (root / "progress.txt").exists()
                else "Starting isolated calculation"
            )
            return {
                "key": request.key,
                "status": "running",
                "progress": progress,
                "job_id": request.job_id,
            }
        if (root / "result.json").exists():
            return {
                **json.loads((root / "result.json").read_text()),
                "key": request.key,
                "source": catalogue()["source"],
            }
        return {
            "key": request.key,
            "status": "failed",
            "error": "Teaching worker failed: " + (root / "worker.log").read_text()[-1200:],
        }
