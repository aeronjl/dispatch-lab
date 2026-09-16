"""One private simulator process, paused at each observation/action boundary."""

import copy
import json
import signal
import sys
import time
from pathlib import Path

from methane.cancellation import CancelledOperation
from methane.config import Config
from methane.control_port import VERSION
from methane.provenance import LOADED_SOURCE, experiment_identity, seal
from methane.siting.store import atomic, encode


def read(path):
    return json.loads(path.read_bytes())


def write(path, value):
    atomic(path, encode(value))


class Gate:
    def __init__(self, root):
        self.root, self.rows = root, []
        self.meta = read(root / "meta.json")
        self.last = None

    def cancelled(self):
        return (self.root / "stop").exists() or time.time() >= self.meta["expires_at"]

    def start(self, config, known, weather, provenance, name, services):
        from methane.documentation import snapshot
        from methane.field_operations import manifest as field_manifest
        from methane.simulation import ASSETS, FIELD_ASSETS

        if self.meta["source_content_hash"] != LOADED_SOURCE["content_hash"]:
            raise ValueError(
                "Application source changed. Restart the app before creating a control session."
            )

        self.config, self.name = config, name
        provenance = copy.deepcopy(provenance)
        provenance["external_control"] = dict(
            contract=VERSION, session_id=self.meta["id"], origin=self.meta["origin"]
        )
        self.template = dict(
            schema_version="dispatch-lab/methane/3",
            model_version=__import__("methane").VERSION,
            provenance=provenance,
            experiment_id=experiment_identity(provenance),
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

    def completed(self, row, truth, events):
        from methane.simulation import summarise

        self.rows.append(copy.deepcopy(row))
        result = dict(
            **self.template,
            run_id=self.meta["id"],
            status="in-progress",
            records={self.name: self.rows},
            metrics={self.name: summarise(self.rows, self.config, truth)},
            events={self.name: events},
            retrospective_truth=truth,
            retrospective_truth_by_controller={self.name: truth},
            failures={},
        )
        write(self.root / "recording.json", seal(result))
        # Agents see command delivery and observed channels, never execution state/truth.
        receipt = dict(
            hour=row["hour"],
            time=row["time"],
            request_id=self.last["request_id"],
            proposal_id=self.last["proposal_id"],
            actor=self.last["actor"],
            reason=self.last["reason"],
            requested=row["requested"],
            applied=row["applied"],
            observations=row["observations_after"],
            diagnosis=row["diagnosis_after"],
            execution_solver=row["execution_solver"],
            forced_trip=row["forced_trip"],
            audits_passed=all(a["passed"] for a in row["audits"]),
            scope="Applied commands and observed channels after the completed interval; not true internal state.",
        )
        write(self.root / f"receipt-{row['hour']}.json", receipt)


def main(root):
    from methane.simulation import run
    from methane.siting.checkpoint import Continuation

    gate = Gate(root)
    inputs = read(root / "input.json")
    config = Config.from_dict(inputs["config"])
    # An independent wall deadline survives a lost UI connection. Last completed artifacts remain.
    signal.alarm(max(1, int(gate.meta["expires_at"] - time.time()) + 2))
    try:
        result = run(
            config,
            weather=inputs["weather"],
            strategies=[inputs["controller"]],
            policies=inputs.get("policies"),
            uncertainty=inputs.get("uncertainty"),
            cancelled=gate.cancelled,
            control=gate,
            continuation=Continuation(config.scenario.hours, gate.meta["hours"], gate.meta["id"]),
        )
        # Preserve the same session lineage in the final ordinary reproduction archive.
        result["provenance"]["external_control"] = gate.template["provenance"]["external_control"]
        result["experiment_id"] = experiment_identity(result["provenance"])
        result["run_id"] = gate.meta["id"]
        write(root / "recording.json", seal(result))
        write(root / "state.json", dict(status=result["status"], revision=len(gate.rows)))
    except Exception as exc:
        write(root / "state.json", dict(status="failed", revision=len(gate.rows), error=str(exc)))


if __name__ == "__main__":
    main(Path(sys.argv[1]))
