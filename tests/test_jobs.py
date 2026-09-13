import os
import threading

from methane.config import Config, Scenario
from methane.jobs import isolated_run
from methane.provenance import experiment_identity, manifest
from methane.reference import audit
from methane.weather import synthetic


def test_isolated_worker_preserves_identity_and_reference():
    c = Config(scenario=Scenario(hours=2, horizon_hours=6))
    weather = synthetic(c)
    progress = []
    result = isolated_run(
        c, weather, progress=lambda value, desc: progress.append(value), strategies=["Greedy"]
    )
    assert result["status"] == "complete"
    assert result["provenance"]["solver"]["threads"] == 1
    assert os.environ.get("DISPATCH_BATCH_WORKER") is None
    expected = manifest(c, weather, ["Greedy"])
    expected["solver"]["threads"] = 1
    assert result["experiment_id"] == experiment_identity(expected)
    assert audit(result)["passed"]


def test_worker_cancel_is_explicit():
    c = Config(scenario=Scenario(hours=24, horizon_hours=6))
    cancel = threading.Event()
    cancel.set()
    result = isolated_run(c, synthetic(c), cancelled=cancel.is_set, strategies=["Greedy"])
    assert result["status"] == "cancelled"
    assert len(result["records"]["Greedy"]) < 24
