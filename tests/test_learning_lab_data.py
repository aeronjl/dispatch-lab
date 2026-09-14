import copy
import json

import pytest

from methane.learning_lab.datasets import packet, validate_splits
from methane.learning_lab.estimators import examples, fit, predict
from methane.learning_lab.fixtures import teaching_dataset
from methane.siting.store import Store, digest, encode


def test_packet_excludes_truth_actions_and_future_information():
    decision = dict(
        hour=0,
        observations={"power_kw": 100, "private_fault": "sensor"},
        forecast={"pv_kw": [20, 100], "ambient_c": [20, 21]},
        plan={"actions": [{"electrolyser_kw": 5}]},
    )
    args = dict(time="2025-01-01T00:00:00Z", prices={}, plant={})
    before = packet(decision, **args)
    decision.update(truth={"fault": "equipment"}, future_recovery=5)
    decision["observations"]["private_fault"] = "different"
    decision["plan"] = {"actions": [{"electrolyser_kw": 500}]}
    assert packet(decision, **args) == before
    decision["forecast"]["source"] = {"available_at": "2025-01-01T01:00:00Z"}
    with pytest.raises(ValueError, match="available"):
        packet(decision, **args)


def test_split_blocks_overlapping_weather_even_with_different_seeds(tmp_path):
    d = teaching_dataset(Store(tmp_path))
    episodes = copy.deepcopy(d["episodes"])
    episodes[1].update(start=episodes[0]["start"], end=episodes[0]["end"], seed=999)
    with pytest.raises(ValueError, match="Leakage"):
        validate_splits(episodes)
    with pytest.raises(ValueError, match="Leakage"):
        validate_splits(d["episodes"], ["equipment"])


def test_fitting_has_explicit_holdout_domain_intervals_and_separate_labels(tmp_path):
    store = Store(tmp_path)
    d = teaching_dataset(store)
    result = fit(store, d["id"], task="pv")
    assert result["status"] == "complete"
    assert result["comparisons"]["fixed"]["mae"] == 0
    assert result["comparisons"]["fixed"]["coverage"] == 1
    assert result["comparisons"]["ridge"]["mae"] > 0  # Never require learning to win.
    model = result["model"]
    with pytest.raises(ValueError, match="domain"):
        predict(model, [10000, 100, 20, 0])
    value = store.get("dataset", d["id"])
    value["labels_sha256"] = store.raw(encode([{"private": "different truth"}]))
    changed = fit(store, store.put("dataset", value), task="pv")
    assert changed["model"]["weights"] == model["weights"]
    assert changed["outcomes"] == result["outcomes"]


def test_missing_condition_channels_and_censored_work_are_not_invented(tmp_path):
    store = Store(tmp_path)
    d = teaching_dataset(store, missing=True)
    result = fit(store, d["id"], task="solar_condition")
    assert result["exclusions"]
    duration = fit(store, d["id"], task="duration")
    assert duration["status"] == "incomplete"
    samples = json.loads(store.read_raw(d["observations_sha256"]))
    samples[0]["packet"]["duration_observations"] = [
        dict(id="job/0", censored=True, nominal_hours=2, elapsed_hours=9)
    ]
    rows, exclusions = examples(samples, "duration")
    assert not rows
    assert exclusions[0]["lower_hours"] == 9


def test_prediction_does_not_depend_on_later_test_observations(tmp_path):
    store = Store(tmp_path)
    d = teaching_dataset(store)
    a = fit(store, d["id"])
    data = store.get("dataset", d["id"])
    samples = json.loads(store.read_raw(data["observations_sha256"]))
    samples[-1]["packet"]["forecast"]["pv_kw"][0] = 9999
    samples[-1]["packet_id"] = digest(samples[-1]["packet"])
    data["observations_sha256"] = store.raw(encode(samples))
    b = fit(store, store.put("dataset", data))
    for strategy in ("fixed", "adaptive", "ridge"):
        assert a["outcomes"][strategy][:-1] == b["outcomes"][strategy][:-1]
    assert a["model"]["weights"] == b["model"]["weights"]


def test_training_cancellation_leaves_no_partial_model(tmp_path):
    store = Store(tmp_path)
    d = teaching_dataset(store)
    with pytest.raises(InterruptedError):
        fit(store, d["id"], cancelled=lambda: True)
    assert store.list("model") == []
