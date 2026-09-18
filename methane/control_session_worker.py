"""One private simulator process, committed at each observation/action boundary."""

import copy
import signal
import sys
import time
from pathlib import Path

from methane.cancellation import CancelledOperation
from methane.config import Config
from methane.control_port import VERSION
from methane.control_storage import commit, committed, read, write
from methane.provenance import LOADED_SOURCE, experiment_identity, seal
from methane.siting.checkpoint import Continuation, unpack
from methane.siting.store import digest


def archive(inputs, meta, result, checkpoint, *, initial_state=None):
    """Portable owner archive. Private runtime never enters the public observation."""
    result["provenance"]["external_control"] = dict(
        contract=VERSION,
        session_id=meta["id"],
        origin=meta["origin"],
        input_sha256=meta["input_sha256"],
        scope="Recorded requests; no external agent re-inference",
    )
    result["experiment_id"] = experiment_identity(result["provenance"])
    result["run_id"] = meta["id"]
    result["control_reproduction"] = dict(
        version="dispatch-control-reproduction/1",
        inputs=inputs,
        ending_checkpoint=checkpoint,
        source_content_hash=meta["source_content_hash"],
        scope="Private retrospective reproduction inputs; never sent to the MCP client",
    )
    result["continuous_period"] = dict(
        schema_version="dispatch-lab/continuous-period/1",
        start_hour=inputs["start_hour"],
        stop_hour=meta["stop_hour"],
        total_hours=inputs["total_hours"],
        binding=inputs["binding"],
        initial_state=initial_state,
        scope="Global hourly boundaries; state and service commitments carried from saved checkpoint",
    )
    return seal(result)


class Gate:
    def __init__(self, root, inputs, continuation):
        self.root, self.inputs, self.continuation = root, inputs, continuation
        self.meta = read(root / "meta.json")
        self.previous = committed(root)
        saved = self.previous["recording"] if self.previous else {}
        name = inputs["controller"]
        self.rows = copy.deepcopy(saved.get("records", {}).get(name, []))
        self.prior_truth = saved.get("retrospective_truth", [])
        self.prior_events = saved.get("events", {}).get(name, [])
        self.receipts = self.previous["receipts"] if self.previous else []
        self.last = None
        self.service_prefix = (
            unpack(inputs["checkpoint"]["graph"])["service_cost_rows"]
            if inputs.get("checkpoint")
            else []
        )
        self.initial_state = saved.get("continuous_period", {}).get("initial_state")

    def cancelled(self):
        return (self.root / "stop").exists() or time.time() >= self.meta["expires_at"]

    def start(self, config, known, weather, provenance, name, services):
        from methane.documentation import snapshot
        from methane.field_operations import manifest as field_manifest
        from methane.simulation import ASSETS, FIELD_ASSETS

        if self.meta["source_content_hash"] != LOADED_SOURCE["content_hash"]:
            raise ValueError(
                "Application source changed. Restore the matching source before continuing this session."
            )
        self.config, self.name, self.services = config, name, services
        self.initial_state = self.initial_state or self.continuation.initial
        self.template = dict(
            schema_version="dispatch-lab/methane/3",
            model_version=__import__("methane").VERSION,
            provenance=copy.deepcopy(provenance),
            config=config.to_dict(),
            controller_config=known.to_dict(),
            documentation=snapshot(),
            weather=weather,
            asset_ids={
                **ASSETS,
                **(
                    services.manifest()["asset_ids"]
                    if services and hasattr(services, "manifest")
                    else FIELD_ASSETS
                    if config.field_operations.enabled
                    else {}
                ),
            },
            field_operations_model=services.manifest()
            if services and hasattr(services, "manifest")
            else field_manifest(config.field_operations),
        )

    def decide(self, public):
        revision = public["hour"]
        write(self.root / "observation.json", public)
        write(
            self.root / "state.json",
            dict(status="waiting", revision=revision, source=LOADED_SOURCE["content_hash"]),
        )
        command = self.root / f"command-{revision}.json"
        while not command.exists():
            if self.cancelled():
                raise CancelledOperation()
            time.sleep(0.05)
        if self.cancelled():
            raise CancelledOperation()
        selected = read(command)
        if selected["information_id"] != public["information_id"]:
            raise ValueError("Action refers to a different observation")
        write(self.root / "state.json", dict(status="executing", revision=revision))
        self.last = selected
        return dict(
            mode=selected["preview"]["mode"],
            plan=selected["preview"]["plan"],
            trace={
                k: selected[k]
                for k in (
                    "actor",
                    "reason",
                    "request_id",
                    "proposal_id",
                    "information_id",
                    "accepted_at",
                )
            }
            | dict(contract=VERSION, mode=selected["preview"]["mode"], session_id=self.meta["id"]),
        )

    def result(self, truth, events, template=None, status="in-progress"):
        from methane.simulation import summarise

        truth = self.prior_truth + truth
        events = self.prior_events + events + (self.services.messages if self.services else [])
        events = sorted(
            {digest(e): e for e in events if e["hour"] >= self.inputs["start_hour"]}.values(),
            key=lambda e: e["hour"],
        )
        result = copy.deepcopy(template or self.template)
        metrics = summarise(self.rows, self.config, truth, service_prefix=self.service_prefix)
        # Full-history performance metrics; preserve current executive's ending obligations.
        last_metrics = result.get("metrics", {}).get(self.name, {})
        if "performance" in last_metrics:
            from methane.adaptation import metrics as performance_metrics

            metrics["performance"] = performance_metrics(self.rows)
        if "service_control" in last_metrics:
            detail = copy.deepcopy(last_metrics["service_control"])
            decisions = [
                r["decision"]["service_control"]
                for r in self.rows
                if "service_control" in r["decision"]
            ]
            detail["fallback_intervals"] = sum(d["fallback_used"] for d in decisions)
            detail["candidate_solves"] = sum(
                sum("evaluation" in c for c in d["candidates"]) for d in decisions
            )
            metrics["service_control"] = detail
        result.update(
            status=status,
            records={self.name: self.rows},
            metrics={self.name: metrics},
            events={self.name: events},
            retrospective_truth=truth,
            retrospective_truth_by_controller={self.name: truth},
            service_accounting_prefix=self.service_prefix,
            failures=result.get("failures", {}),
        )
        if self.services and hasattr(self.services, "planning_catalogues"):
            result["service_planning_catalogues"] = self.services.planning_catalogues
        return archive(
            self.inputs,
            self.meta,
            result,
            self.continuation.output or self.continuation.checkpoint,
            initial_state=self.initial_state,
        )

    def completed(self, row, truth, events):
        self.rows.append(copy.deepcopy(row))
        self.receipts.append(
            dict(
                hour=row["hour"],
                time=row["time"],
                **{k: self.last[k] for k in ("request_id", "proposal_id", "actor", "reason")},
                requested=row["requested"],
                applied=row["applied"],
                observations=row["observations_after"],
                diagnosis=row["diagnosis_after"],
                execution_solver=row["execution_solver"],
                forced_trip=row["forced_trip"],
                audits_passed=all(a["passed"] for a in row["audits"]),
                scope="Applied commands and observed channels after the completed interval; not true internal state.",
            )
        )
        commit(self.root, self.continuation.output, self.result(truth, events), self.receipts)


def main(root):
    from methane.simulation import run

    meta, inputs = read(root / "meta.json"), read(root / "input.json")
    saved = committed(root)
    revision = saved["next_hour"] if saved else inputs["start_hour"]
    signal.alarm(max(1, int(meta["expires_at"] - time.time()) + 2))
    try:
        if digest(inputs) != meta["input_sha256"]:
            raise ValueError("Frozen session inputs changed")
        continuation = Continuation(
            inputs["total_hours"],
            meta["stop_hour"],
            inputs["binding"],
            checkpoint=saved["checkpoint"] if saved else inputs.get("checkpoint"),
            utilities=inputs.get("utilities"),
        )
        gate = Gate(root, inputs, continuation)
        result = run(
            Config.from_dict(inputs["config"]),
            weather=inputs["weather"],
            strategies=[inputs["controller"]],
            policies=inputs.get("policies"),
            uncertainty=inputs.get("uncertainty"),
            cancelled=gate.cancelled,
            control=gate,
            continuation=continuation,
        )
        revision = inputs["start_hour"] + len(gate.rows)
        if gate.rows:
            final = gate.result(
                result["retrospective_truth"],
                result["events"][gate.name],
                result,
                status=result["status"],
            )
            commit(root, continuation.output or continuation.checkpoint, final, gate.receipts)
        write(root / "state.json", dict(status=result["status"], revision=revision))
    except Exception as exc:
        saved = committed(root)
        write(
            root / "state.json",
            dict(
                status="failed", revision=saved["next_hour"] if saved else revision, error=str(exc)
            ),
        )


if __name__ == "__main__":
    main(Path(sys.argv[1]))
