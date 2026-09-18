"""Frozen, cancellable training/data/export workers sharing the Sites CPU lease."""

import json
import os
import shutil
import subprocess
import sys
import threading
import time
import uuid

from methane.processes import peak_memory_bytes, spawn
from methane.siting.store import Store, atomic, encode, identifier

WORKERS = {}
LOCK = threading.RLock()
BUDGET = dict(
    wall_seconds=120,
    maximum_observations=100000,
    minimum_free_bytes=512 * 1024**2,
    numerical_workers=1,
    maximum_memory_bytes=2 * 1024**3,
    memory_limit_scope="Windows process-commit cap; POSIX sampled peak RSS; 0.1 s wall/memory watchdog",
    blas_threads=1,
    scope="One heavy training, dataset, export or numerical study worker per Sites store. Interactive calculations keep their separate existing limits.",
)


def launch(store, operation, arguments, *, wall_seconds=120):
    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE
    from methane.siting.production import worker_lease
    from methane.source_capsule import decode

    if operation not in ("dataset", "train", "export", "fixture", "requirements"):
        raise ValueError("Unknown bounded worker operation")
    if type(wall_seconds) is not int or not 1 <= wall_seconds <= 600:
        raise ValueError("Worker wall budget is 1–600 seconds")
    store.root.mkdir(parents=True, exist_ok=True)
    if shutil.disk_usage(store.root).free < BUDGET["minimum_free_bytes"]:
        raise ValueError("Insufficient free disk for a new worker; preserve existing evidence")
    with LOCK, worker_lease(store) as lease:
        source = store.root / "frozen-source" / LOADED_CAPSULE["sha256"]
        for name, raw in decode(LOADED_CAPSULE).items():
            target = source / name
            if not target.exists() or target.read_bytes() != raw:
                atomic(target, raw)
        record = dict(
            version="learning-job/1",
            operation=operation,
            arguments=arguments,
            nonce=uuid.uuid4().hex,
            source=LOADED_SOURCE["content_hash"],
            source_capsule_sha256=LOADED_CAPSULE["sha256"],
            capsule_raw_sha256=store.raw(encode(LOADED_CAPSULE)),
            budget={**BUDGET, "wall_seconds": wall_seconds},
        )
        key = store.put("training", record)
        # A learning worker shares the store lease with studies. Replace the
        # previous holder's descriptor while owning the lease; a stale study PID
        # or descriptor must not be interpreted as this training job's liveness.
        atomic(store.root / "active-worker.json", encode(dict(kind="learning", job_id=key)))
        root = store.root / "learning-jobs" / key
        root.mkdir(parents=True, exist_ok=True)
        atomic(
            root / "state.json",
            encode(dict(id=key, status="running", description="Starting frozen worker")),
        )
        env = {
            **os.environ,
            "PYTHONPATH": str(source),
            "DISPATCH_SITES_ROOT": str(store.root.resolve()),
            "DISPATCH_BATCH_WORKER": "1",
            "DISPATCH_HEAVY_WORKER": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
        }
        with (root / "worker.log").open("w") as log:
            proc = spawn(
                "methane.learning_lab.jobs",
                [store.root.resolve(), key],
                cwd=source,
                env=env,
                stdout=log,
                stderr=log,
                leases=(lease,),
            )
        WORKERS[key] = proc

        def monitor():
            deadline = time.monotonic() + wall_seconds
            reason = None
            while proc.poll() is None:
                if (root / "cancel").exists() or time.monotonic() >= deadline:
                    reason = "cancelled" if (root / "cancel").exists() else "time-limited"
                    proc.terminate()
                    try:
                        proc.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        proc.kill()
                        proc.wait()
                    break
                time.sleep(0.1)
            state = json.loads((root / "state.json").read_bytes())
            if reason or state["status"] == "running":
                atomic(
                    root / "state.json",
                    encode(
                        dict(
                            id=key,
                            status=reason or "incomplete",
                            description=reason
                            or f"Worker exited {proc.returncode}; inspect saved log",
                            result=None,
                            log=str(root / "worker.log"),
                        )
                    ),
                )

        threading.Thread(target=monitor, daemon=True, name="learning-worker-monitor").start()
        return dict(id=key, status="running", budget=record["budget"])


def poll(store, key, cancel=False):
    store.get("training", key)
    root = store.root / "learning-jobs" / identifier(key)
    if cancel:
        atomic(root / "cancel", b"cancel")
    state = json.loads((root / "state.json").read_bytes())
    process = WORKERS.get(key)
    if state["status"] == "complete" and process is not None and process.poll() is None:
        return dict(
            id=key, status="running", description="Closing worker and releasing its resource lease"
        )
    return state


def work(store, key):
    from methane.worker_budget import budget

    record = store.get("training", key)
    seconds = record["budget"]["wall_seconds"]
    root = store.root / "learning-jobs" / key
    guard = budget(seconds, root / "state.json", record["budget"].get("maximum_memory_bytes"))
    started = time.monotonic()

    def progress(message):
        if (root / "cancel").exists() or time.monotonic() - started > seconds:
            raise InterruptedError("Worker cancelled or wall budget exhausted")
        atomic(root / "state.json", encode(dict(id=key, status="running", description=message)))

    try:
        progress("Reading frozen inputs")
        args = record["arguments"]
        if record["operation"] == "requirements":
            from methane.siting.requirements import evaluate

            result, kind = evaluate(store, **args, progress=progress), "operating-assessment"
        elif record["operation"] == "train":
            from methane.learning_lab.estimators import fit

            result = fit(
                store, **args, progress=progress, cancelled=lambda: (root / "cancel").exists()
            )
            kind = "evaluation"
        elif record["operation"] == "dataset":
            from methane.learning_lab.datasets import freeze

            result, kind = freeze(store, **args), "dataset"
        elif record["operation"] == "fixture":
            from methane.learning_lab.fixtures import teaching_dataset

            result, kind = teaching_dataset(store, **args), "dataset"
        else:
            from methane.siting.reporting import bundle

            result, kind = bundle(store, **args), "bundle"
            result["publication_id"] = args["publication_id"]
        atomic(root / "result.json", encode(result))
        atomic(
            root / "state.json",
            encode(
                dict(
                    id=key,
                    status="complete",
                    description="Saved immutable result",
                    result={
                        k: result[k]
                        for k in ("id", "model_id", "publication_id", "path", "status", "reason")
                        if k in result
                    },
                    result_kind=kind,
                    elapsed_seconds=time.monotonic() - started,
                    maximum_rss_bytes=peak_memory_bytes(),
                )
            ),
        )
    except Exception as exc:
        atomic(
            root / "state.json",
            encode(
                dict(
                    id=key,
                    status="cancelled"
                    if isinstance(exc, InterruptedError)
                    else "time-limited"
                    if isinstance(exc, TimeoutError)
                    else "incomplete",
                    description=f"{type(exc).__name__}: {exc}",
                )
            ),
        )

    finally:
        guard.set()


if __name__ == "__main__":
    work(Store(sys.argv[1]), sys.argv[2])
