import copy
import json
import time
import zipfile
from datetime import UTC, datetime, timedelta

import pytest
from test_siting_production import fixture

from methane.learning_lab import datasets, deployment, editions, estimators, jobs, participants
from methane.learning_lab.fixtures import teaching_dataset
from methane.siting import production, reporting
from methane.siting.store import Store, encode
from methane.timebase import stamp


def test_recorded_episode_export_reconstruction_and_incomplete_channels(tmp_path):
    store = Store(tmp_path)
    design, eid = fixture(store, 72)
    environment = store.get("environment", eid)
    cases = []
    for day in range(3):
        env = copy.deepcopy(environment)
        start = datetime(2025, 1, 3, tzinfo=UTC) + timedelta(days=day)
        env.update(start=stamp(start), end=stamp(start + timedelta(days=1)), hours=24)
        cases.append(dict(design_id=design, environment_id=store.put("environment", env)))
    study = production.create(
        store, name="Observation export acceptance", cases=cases, partition_hours=12
    )
    production.execute(store, study["id"])
    selected = [
        dict(study_id=study["id"], case_id=c["case_id"], split=split)
        for c, split in zip(study["cases"], ("train", "validation", "test"), strict=True)
    ]
    data = datasets.freeze(store, selected, name="Three disjoint days")
    assert data["sample_count"] == 72
    assert datasets.reconstruct(store, data["id"])["status"] == "identical"
    result = estimators.fit(store, data["id"], task="solar_condition")
    assert result["status"] == "incomplete"
    assert result["rows_per_split"] == dict(train=0, validation=0, test=0)
    raw = json.loads(store.read_raw(data["observations_sha256"]))
    assert all("retrospective_truth" not in r["packet"] for r in raw)
    # A separately preserved simulated label never becomes a policy input.
    assert data["observations_sha256"] != data["labels_sha256"]
    scoring = json.loads(store.read_raw(data["labels_sha256"]))
    assert "capacity_kw" in scoring[0]["truth"]


def test_registered_run_cancel_resume_numerical_edition_and_offline_restoration(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "original")
    design, environment = fixture(store, 4)
    data = teaching_dataset(store)
    evaluation = estimators.fit(store, data["id"])
    registration = deployment.register(
        store, name="Observed PV / shadow", model_id=evaluation["model_id"]
    )
    study = production.create(
        store,
        name="Registered operation",
        cases=[
            dict(design_id=design, environment_id=environment, deployment_id=registration["id"])
        ],
        partition_hours=2,
    )
    save = production.save_period

    def stop_after_partition(s, result):
        key = save(s, result)
        production.cancel(s, study["id"])
        return key

    monkeypatch.setattr(production, "save_period", stop_after_partition)
    production.execute(store, study["id"])
    assert production.inspect(store, study["id"])["cases"][0]["completed_hours"] == 2
    first = production.entries(store, study["id"], "case-001")[0]
    monkeypatch.setattr(production, "save_period", save)
    (production.directory(store, study["id"]) / "cancel").unlink()
    production.execute(store, study["id"])
    assert production.entries(store, study["id"], "case-001")[0] == first
    actual = production.inspect(store, study["id"])
    assert actual["cases"][0]["completed_hours"] == 4
    assert actual["cases"][0]["summary"]["experimental_policy"]["decision_count"] == 4
    repeat = editions.repeat(store, study["id"])
    assert editions.compare(store, study["id"], repeat["id"])["status"] == "incomplete"
    production.execute(store, repeat["id"])
    compared = editions.compare(store, study["id"], repeat["id"])
    assert compared["missing_hours"] == []
    assert not compared["input_comparison"][0]["input_differences"]
    publication = reporting.publish(store, "study", study["id"])
    bundle = reporting.bundle(store, publication["publication_id"])
    restored = Store(tmp_path / "restored")
    reporting.restore(bundle["path"], restored)
    assert restored.get("model", evaluation["model_id"]) == store.get(
        "model", evaluation["model_id"]
    )
    assert restored.read_raw(data["observations_sha256"]) == store.read_raw(
        data["observations_sha256"]
    )
    restored_period = production.load_period(restored, first["period_sha256"])
    assert restored_period["records"]["Greedy"][0]["decision"]["experimental_policy"]
    assert reporting.bundle(store, publication["publication_id"])["reused"]
    # Old export is not replaced if its inventory changes later.
    progress = production.directory(store, study["id"]) / "progress.json"
    progress.write_bytes(encode(dict(status="changed metadata")))
    with pytest.raises(ValueError, match="existing export"):
        reporting.bundle(store, publication["publication_id"])


def test_evaluation_report_bundle_keeps_all_weights_and_no_network(tmp_path):
    store = Store(tmp_path / "source")
    data = teaching_dataset(store)
    result = estimators.fit(store, data["id"])
    draft = reporting.draft(store, "evaluation", result["id"])["writeup"]
    draft["findings"] = "<script>literal participant text</script>"
    publication = reporting.publish(store, "evaluation", result["id"], writeup=draft)
    bundle = reporting.bundle(store, publication["publication_id"])
    with zipfile.ZipFile(bundle["path"]) as archive:
        text = archive.read("reports/" + publication["publication_id"] + ".html").decode()
        assert "&lt;script&gt;" in text and "<script>literal" not in text
    restored = Store(tmp_path / "target")
    reporting.restore(bundle["path"], restored)
    assert (
        restored.get("evaluation", result["id"])["model"]["weights"] == result["model"]["weights"]
    )


def test_bounded_worker_lease_cancellation_and_saved_outcomes(tmp_path):
    store = Store(tmp_path)
    with production.worker_lease(store), pytest.raises(ValueError, match="worker holds"):
        jobs.launch(store, "fixture", {})
    job = jobs.launch(store, "fixture", {})
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        state = jobs.poll(store, job["id"])
        if state["status"] != "running":
            break
        time.sleep(0.1)
    assert state["status"] == "complete", state
    assert store.get("dataset", state["result"]["id"])["sample_count"] == 72
    job = jobs.launch(store, "train", dict(dataset_id=state["result"]["id"]))
    jobs.poll(store, job["id"], cancel=True)
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        state = jobs.poll(store, job["id"])
        if state["status"] != "running":
            break
        time.sleep(0.1)
    assert state["status"] == "cancelled", state


def test_participant_words_are_not_automated_evidence(tmp_path):
    store = Store(tmp_path)
    result = participants.record(
        store,
        participant="Test pseudonym",
        facilitator="test",
        basis="agent-rehearsal",
        responses=dict.fromkeys(participants.QUESTIONS, "Rehearsal only"),
        issues=[
            dict(
                question="evidence",
                misunderstanding="Synthetic mistaken for field evidence",
                severity="material",
                resolution="",
            )
        ],
    )
    assert result["status"] == "material confusion unresolved"
    assert result["basis"] == "agent-rehearsal"
    assert store.list("walkthrough")[0]["responses"]["evidence"] == "Rehearsal only"
