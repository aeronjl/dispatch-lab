"""Bounded data jobs, independent of the numerical worker and solar preview."""

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor

from methane.siting import environment

POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="sites-data")
LOCK = threading.RLock()
JOBS = {}


def launch(store, owner, data, offline):
    with LOCK:
        if any(j["status"] in ("pending", "running") for j in JOBS.values()):
            raise ValueError("A Sites data retrieval is already active; cancel or wait")
        key = uuid.uuid4().hex
        job = dict(id=key, owner=owner, status="pending", progress="Queued", cancelled=False)
        JOBS[key] = job
        while len(JOBS) > 16:
            del JOBS[next(iter(JOBS))]

    def work():
        job["status"] = "running"
        try:
            result = environment.prepare(
                store,
                **data,
                offline=offline,
                progress=lambda label: job.update(progress=label),
                cancelled=lambda: job["cancelled"],
            )
            job.update(status="cancelled" if job["cancelled"] else "complete", result=result)
        except Exception as exc:
            job.update(
                status="cancelled" if job["cancelled"] else "incomplete",
                error=f"{type(exc).__name__}: {exc}",
            )

    POOL.submit(work)
    return {k: v for k, v in job.items() if k != "owner"}


def poll(owner, key, cancel=False):
    job = JOBS.get(key)
    if job is None or job["owner"] != owner:
        raise ValueError("Sites data job expired or belongs to another context")
    if cancel:
        job["cancelled"] = True
    return {k: v for k, v in job.items() if k != "owner"}
