"""Numerically replay recorded requests, never ask an external agent to infer again."""

import copy
import sys
import uuid
from pathlib import Path

from methane.config import Config
from methane.control_storage import read, write
from methane.provenance import LOADED_SOURCE, experiment_identity, seal, verify
from methane.siting.checkpoint import Continuation
from methane.siting.store import digest
from methane.worker_budget import budget


class RecordedActions:
    def __init__(self, source):
        self.rows = next(iter(source["records"].values()))
        self.by_hour = {r["hour"]: r for r in self.rows}
        self.information = []

    def start(self, *args):
        pass

    def decide(self, public):
        original = self.by_hour[public["hour"]]
        external = original["decision"]["external_control"]
        before = external["information"]
        keys = ("observations", "estimate", "diagnosis", "forecast", "prices", "plant", "models")
        self.information.append(
            dict(
                hour=public["hour"],
                changed_fields=[k for k in keys if before.get(k) != public.get(k)],
                original_information_id=before["information_id"],
                current_information_id=public["information_id"],
            )
        )
        plan = copy.deepcopy(original["decision"]["plan"])
        plan["actions"][0] = copy.deepcopy(original["requested"])
        return dict(
            mode="manual",
            plan=plan,
            trace=dict(
                actor="recorded-action replay",
                reason="Replay the saved request; no new agent inference",
                original_attribution={
                    k: external.get(k)
                    for k in ("actor", "reason", "request_id", "proposal_id", "session_id")
                },
                information_id=public["information_id"],
                recorded_plan=True,
            ),
        )

    def completed(self, *args):
        pass


def replay(source, *, cancelled=None, progress=None):
    from methane.reference import audit
    from methane.simulation import run

    verify(source)
    reproduction = source.get("control_reproduction")
    if not reproduction:
        raise ValueError(
            "External-control recording lacks frozen replay inputs/checkpoints. Recorded playback remains available."
        )
    inputs = reproduction["inputs"]
    frozen_hash = source["provenance"]["external_control"].get("input_sha256")
    if frozen_hash != digest(inputs):
        raise ValueError("Recorded replay inputs do not match the original dispatch binding")
    if reproduction["source_content_hash"] != LOADED_SOURCE["content_hash"] and inputs.get(
        "checkpoint"
    ):
        raise ValueError("Continued runtime requires its original source for numerical replay")
    rows = next(iter(source["records"].values()))
    if not rows:
        raise ValueError("No completed requests to replay")
    expected = list(range(inputs["start_hour"], rows[-1]["hour"] + 1))
    if [r["hour"] for r in rows] != expected:
        raise ValueError("Recorded action history has missing or duplicate intervals")
    gate = RecordedActions(source)
    continuation = Continuation(
        inputs["total_hours"],
        rows[-1]["hour"] + 1,
        inputs["binding"],
        checkpoint=inputs.get("checkpoint"),
        utilities=inputs.get("utilities"),
    )
    result = run(
        Config.from_dict(inputs["config"]),
        weather=inputs["weather"],
        strategies=[inputs["controller"]],
        policies=inputs.get("policies"),
        uncertainty=inputs.get("uncertainty"),
        control=gate,
        continuation=continuation,
        cancelled=cancelled,
        progress=progress,
    )
    result["provenance"]["external_control"] = dict(
        contract="dispatch-control/2",
        mode="recorded-action replay",
        input_sha256=digest(inputs),
        origin=source["run_id"],
        recorded_integrity_sha256=source["integrity_sha256"],
    )
    result["experiment_id"] = experiment_identity(result["provenance"])
    result["run_id"] = uuid.uuid4().hex
    result["control_reproduction"] = dict(
        version="dispatch-control-reproduction/1",
        inputs=inputs,
        ending_checkpoint=continuation.output,
        source_content_hash=LOADED_SOURCE["content_hash"],
    )
    name = inputs["controller"]
    current = result["records"][name]
    differences = []
    for a, b in zip(rows, current, strict=False):
        changed = {
            k: b["applied"][k] - a["applied"][k]
            for k in a["applied"]
            if abs(b["applied"][k] - a["applied"][k]) > 1e-5
        }
        state = {
            k: float(b["state"][k]) - float(a["state"][k])
            for k in a["state"]
            if abs(float(b["state"][k]) - float(a["state"][k])) > 1e-5
        }
        if changed or state:
            differences.append(
                dict(hour=a["hour"], applied_delta=changed, ending_state_delta=state)
            )
    verification = audit(result)
    report = dict(
        version="dispatch-control-replay/1",
        recorded_run_id=source["run_id"],
        replay_run_id=result["run_id"],
        recorded_integrity_sha256=source["integrity_sha256"],
        status=result["status"],
        source_matches=reproduction["source_content_hash"] == LOADED_SOURCE["content_hash"],
        recorded_environment=source["provenance"]["environment"],
        replay_environment=result["provenance"]["environment"],
        recorded_intervals=len(rows),
        replayed_intervals=len(current),
        differences=differences,
        information=gate.information,
        independent_reference_passed=verification["passed"],
        independent_reference_scope=verification["scope"],
        independent_reference_failures=verification["failures"]
        + [c for c in verification["checks"] if not c["passed"]],
        methane_delta_kg=result["metrics"][name]["methane_kg"]
        - source["metrics"][name]["methane_kg"],
        scope="Numerical replay of recorded process requests. Services use the frozen reference executive and may differ under time-limited solving. Predictions in the replay trace remain the original saved proposals; compare information and applied outcomes. This is not external-agent re-inference or recorded playback.",
    )
    result["recorded_action_comparison"] = report
    return seal(result), report


def main(root):
    guard = budget(7200, root / "state.json", None, cpu=False)
    try:
        source = read(root / "source.json")
        result, report = replay(
            source,
            cancelled=lambda: (root / "cancel").exists(),
            progress=lambda f, desc: write(
                root / "state.json", dict(status="running", fraction=f, description=desc)
            ),
        )
        write(root / "recording.json", result)
        write(root / "state.json", {**report, "fraction": 1})
    except Exception as exc:
        write(root / "state.json", dict(status="failed", error=str(exc)))

    finally:
        guard.set()


if __name__ == "__main__":
    main(Path(sys.argv[1]))
