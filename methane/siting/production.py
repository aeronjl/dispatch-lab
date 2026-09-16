"""Bounded chronological studies: one solver worker, immutable hourly partitions.

A partition and its next checkpoint are committed by one append-only entry. A
cancelled interval is never represented as completed. Resumption uses the last
committed boundary and the original source capsule, not the current application.
"""

import copy
import fcntl
import gzip
import json
import os
import subprocess
import sys
import threading
import time
import uuid
from collections import OrderedDict
from datetime import UTC, datetime

from methane.config import Config
from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE, verify
from methane.siting.checkpoint import Continuation
from methane.siting.environment import weather
from methane.siting.store import ROOT, Store, atomic, digest, encode, identifier

LOCK = threading.RLock()
WORKERS = {}


def directory(store, study_id):
    store.get("study", study_id)
    return store.root / "execution" / identifier(study_id)


def create(
    store,
    *,
    name,
    cases,
    mode="design",
    partition_hours=168,
    purpose="Declared comparison",
    search=None,
    template_id=None,
    requirements_id=None,
):
    if mode not in ("resource", "design", "autonomous") or not 1 <= partition_hours <= 168:
        raise ValueError("Invalid study mode or partition size")
    if not 1 <= len(cases) <= 96:
        raise ValueError("A bounded study contains 1–96 declared cases")
    if requirements_id:
        from methane.siting.requirements import Brief

        Brief(**store.get("requirements", requirements_id))
    frozen = []
    for index, item in enumerate(cases):
        design = store.get("design", item["design_id"])
        env = store.get("environment", item["environment_id"])
        if design["site_revision"] != env["site_revision"]:
            raise ValueError("Environment is attached to a different site revision")
        c = Config.from_dict(design["config"])
        from dataclasses import replace

        c = replace(c, scenario=replace(c.scenario, seed=int(item.get("seed", c.scenario.seed))))
        controller = item.get("controller", "Greedy")
        if controller not in ("Greedy", "MPC · methane", "MPC · economics"):
            raise ValueError("Unknown production controller")
        policy = item.get("policy")
        if item.get("deployment_id"):
            from methane.learning_lab.workflow import deployed_policy

            policy = deployed_policy(store, c, controller, item["deployment_id"], policy)
        if policy is not None:
            from methane.policy import Policy
            from methane.simulation import STRATEGIES

            policy = Policy(**policy).to_dict()
            if policy["objective"] != STRATEGIES[controller]:
                raise ValueError("Explicit policy objective must match the displayed controller")
        role = item.get("role", "evaluation")
        if role not in ("design", "evaluation", "held-out"):
            raise ValueError("Unknown comparison period role")
        if mode == "autonomous" and (
            env["information"] != "archived-ifs/1"
            or c.sensors.ambiguity_policy != "retain-capacity/1"
        ):
            raise ValueError(
                "Autonomous replay requires original forecast issues and the explicit ambiguity-preserving observer"
            )
        world = item.get("uncertainty")
        if world is not None:
            from methane.uncertainty import validate_world

            validate_world(world)
            if digest(world["config"]) != digest(c.to_dict()):
                raise ValueError("Persistent uncertainty world does not match frozen physical case")
        frozen.append(
            dict(
                case_id=f"case-{index + 1:03}",
                design_id=item["design_id"],
                environment_id=item["environment_id"],
                config=c.to_dict(),
                utilities=design.get("utilities"),
                controller=controller,
                role=role,
                repetition=int(item.get("repetition", 1)),
                uncertainty=world,
                hours=env["hours"],
                label=item.get("label", design["name"]),
            )
        )
        if design.get("equipment_basis_id"):
            from methane.siting.equipment import applicability

            frozen[-1]["equipment_applicability"] = applicability(
                store, design["equipment_basis_id"], c.to_dict(), design["site_revision"]
            )
            frozen[-1]["equipment_applicability"]["commissioning_reviews_at_creation"] = [
                r for r in store.list("commissioning-review") if r["design_id"] == item["design_id"]
            ]
        if policy is not None:
            frozen[-1]["policy"] = policy
    value = dict(
        schema_version="site-yield-study/2"
        if any("policy" in c for c in frozen)
        else "site-yield-study/1",
        edition_nonce=uuid.uuid4().hex,
        created_at=datetime.now(UTC).isoformat(),
        name=name,
        mode=mode,
        purpose=purpose,
        cases=frozen,
        partition_hours=partition_hours,
        source=LOADED_SOURCE,
        source_capsule_sha256=LOADED_CAPSULE["sha256"],
        search=search,
        chronology="Continuous state within each case; each independent case resets to declared initial state. Years in one environment do not reset the plant.",
        information="Recorded forecast information; no perfect-foresight substitution",
        qualification="Hourly scheduling and bounded observation/service model. Not validated annual autonomy or certified delivered fuel.",
        uncertainty_scope="Cases/worlds are disclosed scenarios unless a separately supported probability model is attached; numerical repeats are not independent weather samples",
    )
    if template_id is not None:
        value["template"] = dict(id=template_id, record=store.get("template", template_id))
    if requirements_id:
        value["requirements_id"] = requirements_id
    key = store.put("study", value)
    d = directory(store, key)
    atomic(d / "source-capsule.json", encode(LOADED_CAPSULE))
    return {"id": key, **value}


def save_blob(store, value):
    return store.raw(gzip.compress(encode(value), mtime=0))


def read_blob(store, key):
    return json.loads(gzip.decompress(store.read_raw(key)))


def save_period(store, result):
    value = copy.deepcopy(result)
    refs = {}
    for key in ("weather", "documentation", "learning_examples", "taxonomy"):
        refs[key] = save_blob(store, value.pop(key))
    refs["source_capsule"] = save_blob(store, value["provenance"].pop("source_capsule"))
    return save_blob(
        store, dict(schema_version="site-period-storage/1", value=value, references=refs)
    )


def load_period(store, key):
    saved = read_blob(store, key)
    value = saved["value"]
    for name, reference in saved["references"].items():
        if name == "source_capsule":
            value["provenance"][name] = read_blob(store, reference)
        else:
            value[name] = read_blob(store, reference)
    return verify(value)


def entries(store, study_id, case_id):
    manifest = store.get("study", study_id)
    if case_id not in {c["case_id"] for c in manifest["cases"]}:
        raise ValueError("Unknown site-study case")
    d = directory(store, study_id) / case_id
    return [json.loads(p.read_bytes()) for p in sorted(d.glob("entry-*.json"))]


def state(store, study_id):
    d = directory(store, study_id)
    path = d / "progress.json"
    result = json.loads(path.read_bytes()) if path.exists() else dict(status="ready", fraction=0)
    if result["status"] == "running":
        try:
            os.kill(result["pid"], 0)
        except PermissionError:
            # An OS visibility restriction does not establish that the worker died.
            result["process_visibility"] = "unavailable; retain recorded running state"
        except (ProcessLookupError, KeyError):
            result.update(
                status="interrupted", description="Resume from the last committed checkpoint"
            )
    return result


def cancel(store, study_id):
    atomic(directory(store, study_id) / "cancel", b"cancel\n")
    return dict(
        status="cancellation requested",
        note="Current numerical solve observes its bounded cancellation checks; committed periods are retained",
    )


def execute(store, study_id):
    from methane.simulation import run

    manifest = store.get("study", study_id)
    d = directory(store, study_id)
    if manifest["source"]["content_hash"] != LOADED_SOURCE["content_hash"]:
        raise ValueError("Execution source does not match the study capsule")
    total = sum(c["hours"] for c in manifest["cases"])
    completed = 0
    stop = lambda: (d / "cancel").exists()  # noqa: E731

    def progress(status, description, done=None):
        atomic(
            d / "progress.json",
            encode(
                dict(
                    status=status,
                    description=description,
                    fraction=(completed if done is None else done) / total,
                    pid=os.getpid(),
                    updated_at=datetime.now(UTC).isoformat(),
                )
            ),
        )

    progress("running", "Opening frozen environments")
    try:
        for case in manifest["cases"]:
            if stop():
                break
            previous = entries(store, study_id, case["case_id"])
            start = previous[-1]["next_hour"] if previous else 0
            completed += start
            if start == case["hours"] and (d / case["case_id"] / "summary.json").exists():
                continue
            config = Config.from_dict(case["config"])
            progress("running", f"{case['label']} · validating saved weather")
            w = weather(store, case["environment_id"], config)
            if manifest["mode"] == "resource":
                from methane.siting.environment import resource

                r = resource({"truth": w["truth"]}, w["times"])
                summary = dict(
                    hours=case["hours"],
                    methane_kg=None,
                    total_eur=None,
                    ending=None,
                    calendar=r["months"],
                    resource=r,
                    curtailed_kwh=None,
                    scope="Resource conversion only; dispatch, methane and economics not calculated",
                )
                atomic(d / case["case_id"] / "summary.json", encode(summary))
                completed += case["hours"]
                continue
            binding = digest(
                dict(
                    case=case,
                    environment=case["environment_id"],
                    source=manifest["source"]["content_hash"],
                )
            )
            checkpoint = read_blob(store, previous[-1]["checkpoint_sha256"]) if previous else None
            while start < case["hours"] and not stop():
                started = time.perf_counter()
                end = min(case["hours"], start + manifest["partition_hours"])
                cont = Continuation(
                    case["hours"],
                    end,
                    binding,
                    checkpoint=checkpoint,
                    utilities=case.get("utilities"),
                )
                before = completed
                result = run(
                    config,
                    w,
                    [case["controller"]],
                    progress=lambda f, desc, before=before, end=end, start=start: progress(
                        "running", desc, before + f * (end - start)
                    ),
                    cancelled=stop,
                    uncertainty=case["uncertainty"],
                    policies={case["controller"]: case["policy"]} if "policy" in case else None,
                    continuation=cont,
                )
                rows = result["records"][case["controller"]]
                if rows:
                    next_hour = rows[-1]["hour"] + 1
                    # The entry is the transaction commit; unreferenced blobs after a crash are harmless.
                    entry = dict(
                        schema_version="site-period-entry/1",
                        start_hour=start,
                        next_hour=next_hour,
                        checkpoint_sha256=save_blob(store, cont.output),
                        period_sha256=save_period(store, result),
                        summary_sha256=save_blob(store, summary_records(result)),
                        status=result["status"],
                        interval_count=len(rows),
                        first_time=rows[0]["time"],
                        last_time=rows[-1]["time"],
                        metrics=result["metrics"][case["controller"]],
                    )
                    entry["elapsed_seconds"] = time.perf_counter() - started
                    atomic(d / case["case_id"] / f"entry-{start:08}.json", encode(entry))
                    checkpoint = cont.output
                    completed += next_hour - start
                    start = next_hour
                if result["status"] == "invalid":
                    progress(
                        "invalid", "Physical audit failed; original interval evidence retained"
                    )
                    return
                if not rows or stop():
                    break
            if start == case["hours"]:
                progress("running", f"{case['label']} · reconciling the complete chronology")
                from methane.cancellation import CancelledOperation
                from methane.siting.summary import calculate

                try:
                    summary = calculate(
                        store,
                        study_id,
                        case,
                        progress=lambda done, total, label=case["label"]: progress(
                            "running", f"{label} · reconciling recorded hours {done}/{total}"
                        ),
                        cancelled=stop,
                    )
                except CancelledOperation:
                    progress("cancelled", "Recorded hours saved; resume to finish reconciliation")
                    return
                atomic(d / case["case_id"] / "summary.json", encode(summary))
        progress(
            "cancelled" if stop() else "complete",
            "Saved committed checkpoints" if stop() else "All declared cases completed",
        )
    except Exception as exc:
        progress("incomplete", f"{type(exc).__name__}: {exc}")
        raise


def summary_records(result):
    """Project numerical-summary operands; full original decisions remain separately saved."""
    records = {}
    for name, rows in result["records"].items():
        records[name] = []
        for row in rows:
            r = {k: v for k, v in row.items() if not isinstance(v, (dict, list))}
            r.update({k: row[k] for k in ("state", "applied", "diagnosis_after")})
            d = row["decision"]
            r["decision"] = {"probe": d["probe"], "plan": {"solver": d["plan"]["solver"]}}
            if "experimental_policy" in d:
                r["decision"]["experimental_policy"] = {
                    key: d["experimental_policy"][key]
                    for key in ("status", "reason", "elapsed_ms", "reserve_accounting")
                    if key in d["experimental_policy"]
                }
            if "recovery_planning" in d:
                r["decision"]["recovery_planning"] = d["recovery_planning"]
            if "field_operations" in row:
                r["field_operations"] = row["field_operations"]
            if "lifecycle" in row:
                r["lifecycle"] = row["lifecycle"]
            detail = (
                row.get("component_records", {})
                .get("solar", {})
                .get("diagnostics", {})
                .get("detail")
            )
            r["component_records"] = {
                "solar": {
                    "diagnostics": {
                        "detail": {"clipped_kw": detail["clipped_kw"]}
                        if detail and "clipped_kw" in detail
                        else {}
                    }
                }
            }
            records[name].append(r)
    return {
        "records": records,
        "retrospective_truth_by_controller": result["retrospective_truth_by_controller"],
    }


class PeriodRows:
    """Repeatable lazy sequence; at most one decoded interval partition is cached."""

    def __init__(self, store, items, controller, truth=False):
        self.store, self.items, self.controller, self.is_truth = store, items, controller, truth
        self.cache = OrderedDict()

    def __len__(self):
        return sum(i["interval_count"] for i in self.items)

    def part(self, item):
        key = item["period_sha256"]
        if key not in self.cache:
            # Summary calculations need rows only; avoid inflating source/weather essays.
            value = read_blob(self.store, item.get("summary_sha256", key))
            if "value" in value:
                value = value["value"]
            self.cache.clear()
            self.cache[key] = value
        r = self.cache[key]
        return (
            r["retrospective_truth_by_controller"][self.controller]
            if self.is_truth
            else r["records"][self.controller]
        )

    def __iter__(self):
        for item in self.items:
            yield from self.part(item)

    def __getitem__(self, key):
        if isinstance(key, slice):
            a, b, c = key.indices(len(self))
            return [r for i, r in enumerate(self) if i >= a and i < b and (i - a) % c == 0]
        key = key if key >= 0 else len(self) + key
        for item in self.items:
            if key < item["interval_count"]:
                return self.part(item)[key]
            key -= item["interval_count"]
        raise IndexError(key)

    def truth(self):
        return PeriodRows(self.store, self.items, self.controller, True)


def products(rows):
    totals = {
        k: 0.0
        for k in (
            "methane_gross_kg",
            "hydrogen_gross_kg",
            "hydrogen_consumed_kg",
            "co2_accepted_kg",
            "co2_consumed_kg",
            "co2_rejected_kg",
            "water_consumed_kg",
            "water_produced_kg",
            "energy_stored_kwh",
            "dc_kwh",
        )
    }
    for r in rows:
        totals["methane_gross_kg"] += r["applied"]["methane_kg"]
        for key, field in (
            ("hydrogen_gross_kg", "h2_produced_kg"),
            ("hydrogen_consumed_kg", "h2_consumed_kg"),
            ("co2_accepted_kg", "co2_delivered_kg"),
            ("co2_consumed_kg", "co2_consumed_kg"),
            ("co2_rejected_kg", "co2_rejected_kg"),
            ("water_consumed_kg", "electrolysis_stoichiometric_water_kg"),
            ("water_produced_kg", "water_produced_kg"),
            ("dc_kwh", "pv_kw"),
        ):
            totals[key] += r[field]
        totals["energy_stored_kwh"] += r["applied"]["charge_kw"]
    return {
        **totals,
        "co2_supplied_kg": totals["co2_accepted_kg"] + totals["co2_rejected_kg"],
        "hydrogen_net_produced_kg": totals["hydrogen_gross_kg"] - totals["hydrogen_consumed_kg"],
        "hydrogen_sold_kg": 0,
        "co2_captured_kg": 0,
        "methane_accepted_kg": None,
        "scope": "Methane acceptance belongs to a separate offtake scenario; no hydrogen export or CO2 capture mechanism. Initial inventories and terminal inventories are separate stocks.",
    }


def calendar(rows):
    months = {}
    for row in rows:
        key = row["time"][:7]
        m = months.setdefault(
            key, dict(hours=0, methane_kg=0, curtailed_kwh=0, forced_trips=0, starts=0)
        )
        m["hours"] += 1
        m["methane_kg"] += row["applied"]["methane_kg"]
        m["curtailed_kwh"] += row["curtailed_kwh"]
        m["forced_trips"] += row["forced_trip"]
        m["starts"] += row["reactor_start"]
        m["ending"] = row["state"]
    return months


def worker_lease(store):
    """An inherited OS lock survives server restarts and releases on worker death."""
    store.root.mkdir(parents=True, exist_ok=True)
    lease = (store.root / "worker.lock").open("a+b")
    try:
        fcntl.flock(lease.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        lease.close()
        raise ValueError("A Sites worker holds this store; wait or cancel its study") from None
    return lease


def launch(store, study_id):
    from methane.source_capsule import decode

    with LOCK:
        for proc in WORKERS.values():
            if proc.poll() is None:
                raise ValueError(
                    "A Sites worker is already running; cancel or wait before starting another"
                )
        d = directory(store, study_id)
        capsule = json.loads((d / "source-capsule.json").read_bytes())
        if capsule["sha256"] != store.get("study", study_id)["source_capsule_sha256"]:
            raise ValueError("Study source capsule mismatch")
        source = store.root / "frozen-source" / capsule["sha256"]
        for name, data in decode(capsule).items():
            target = source / name
            if not target.exists() or target.read_bytes() != data:
                atomic(target, data)
        (d / "cancel").unlink(missing_ok=True)
        env = {
            **os.environ,
            "PYTHONPATH": str(source),
            "DISPATCH_SITES_ROOT": str(store.root.resolve()),
            "DISPATCH_BATCH_WORKER": "1",
            "OMP_NUM_THREADS": "1",
            "OPENBLAS_NUM_THREADS": "1",
            "MKL_NUM_THREADS": "1",
            "VECLIB_MAXIMUM_THREADS": "1",
        }
        lease = worker_lease(store)
        env["DISPATCH_SITES_LEASE_FD"] = str(lease.fileno())
        with lease, (d / ("worker-" + uuid.uuid4().hex + ".log")).open("w") as log:
            proc = subprocess.Popen(
                [sys.executable, "-m", "methane.siting.production", study_id],
                cwd=source,
                env=env,
                stdout=log,
                stderr=log,
                pass_fds=(lease.fileno(),),
            )
        WORKERS[study_id] = proc
        atomic(
            d / "progress.json",
            encode(
                dict(
                    status="running",
                    pid=proc.pid,
                    fraction=0,
                    description="Starting frozen continuous worker",
                )
            ),
        )
        return state(store, study_id)


def inspect(store, study_id):
    manifest = store.get("study", study_id)
    values = []
    for case in manifest["cases"]:
        items = entries(store, study_id, case["case_id"])
        path = directory(store, study_id) / case["case_id"] / "summary.json"
        values.append(
            {
                **case,
                "completed_hours": items[-1]["next_hour"]
                if items
                else case["hours"]
                if path.exists() and manifest["mode"] == "resource"
                else 0,
                "summary": json.loads(path.read_bytes()) if path.exists() else None,
                "periods": [
                    {k: v for k, v in i.items() if k not in ("metrics", "checkpoint_sha256")}
                    for i in items
                ],
            }
        )
    return dict(id=study_id, manifest=manifest, state=state(store, study_id), cases=values)


if __name__ == "__main__":
    execute(Store(ROOT), sys.argv[1])
