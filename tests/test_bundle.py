import copy
import gzip
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from methane.bundle import make, playback, unpack
from methane.bundle_runtime import check
from methane.config import Config, Scenario
from methane.provenance import LOADED_FILES, seal
from methane.simulation import run
from methane.source_capsule import decode


@pytest.fixture(scope="module")
def result():
    return run(Config(scenario=Scenario(hours=2, horizon_hours=6)), strategies=["Greedy"])


def test_archive_writer_preserves_content_and_previous_file_on_failure(
    result, tmp_path, monkeypatch
):
    from methane import evidence

    path = evidence.save(result, tmp_path)
    original = path.read_bytes()
    assert gzip.decompress(original) == json.dumps(result, allow_nan=False).encode()
    assert evidence.load(path) == json.loads(json.dumps(result, allow_nan=False))

    def failed_compression(*args, **kwargs):
        raise OSError("Interrupted compression")

    monkeypatch.setattr(evidence.gzip, "compress", failed_compression)
    with pytest.raises(OSError, match="Interrupted compression"):
        evidence.save(result, tmp_path)
    assert path.read_bytes() == original
    assert list(tmp_path.iterdir()) == [path]


def test_overlapping_and_failed_exports_publish_only_complete_files(result, tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    from methane import evidence

    real_save = evidence.save
    monkeypatch.setattr(evidence, "RUNS", tmp_path)
    monkeypatch.setattr(evidence, "save", lambda value: real_save(value, tmp_path))
    with ThreadPoolExecutor(max_workers=2) as pool:
        paths = list(pool.map(evidence.export, [result, result]))
    # Identical bytes may share a path; different ZIP timestamps are preserved
    # as separate complete artifacts, never replacements of a previous export.
    assert all(Path(p).is_file() for p in paths)
    path = tmp_path / Path(paths[0]).name
    original = path.read_bytes()
    with zipfile.ZipFile(path) as z:
        assert z.testzip() is None
        assert json.loads(z.read("methane-run-v3.json")) == json.loads(
            json.dumps(result, allow_nan=False)
        )
    original_write = zipfile.ZipFile.writestr

    def fail_after_archive(self, name, *args, **kwargs):
        if name == "economics-v2.json":
            raise OSError("Interrupted ZIP write")
        return original_write(self, name, *args, **kwargs)

    monkeypatch.setattr(zipfile.ZipFile, "writestr", fail_after_archive)
    with pytest.raises(OSError, match="Interrupted ZIP write"):
        evidence.export(result)
    assert path.read_bytes() == original
    assert not list(tmp_path.glob(".*"))


def test_same_physical_run_keeps_distinct_sealed_recordings(result, tmp_path):
    from concurrent.futures import ThreadPoolExecutor

    from methane.evidence import load, save

    records = []
    for attempt in range(3):
        value = copy.deepcopy(result)
        value["study"] = {"case_id": f"repeat-{attempt}"}
        records.append(seal(value))
    assert len({r["run_id"] for r in records}) == 1
    assert len({r["integrity_sha256"] for r in records}) == 3
    with ThreadPoolExecutor(max_workers=3) as pool:
        paths = list(pool.map(lambda r: save(r, tmp_path), records))
    assert len(set(paths)) == 3
    before = {p: p.read_bytes() for p in paths}
    assert [load(p)["study"]["case_id"] for p in paths] == [f"repeat-{i}" for i in range(3)]
    assert save(records[0], tmp_path) == paths[0]
    assert all(p.read_bytes() == data for p, data in before.items())


def test_legacy_archive_save_keeps_original_unsealed_shape(tmp_path):
    from methane.evidence import load, recording_key, save
    from methane.provenance import digest

    legacy = load(Path(__file__).parent / "fixtures/browser-demo-v2.json.gz")
    assert "integrity_sha256" not in legacy
    key = recording_key(legacy)
    assert key == digest(legacy)
    path = save(legacy, tmp_path)
    assert load(path) == legacy
    assert "integrity_sha256" not in load(path)


def test_bundle_does_not_replace_a_different_recording_at_same_target(result, tmp_path):
    first = make(result, tmp_path / "bundle.zip")
    original = first.read_bytes()
    changed = copy.deepcopy(result)
    changed["study"] = {"case_id": "another-recording"}
    changed = seal(changed)
    second = make(changed, tmp_path / "bundle.zip")
    assert first != second and first.read_bytes() == original
    with zipfile.ZipFile(second) as z:
        saved = json.loads(gzip.decompress(z.read("recorded-run.json.gz")))
    assert saved["integrity_sha256"] == changed["integrity_sha256"]


def test_repricing_exports_preserve_both_assumptions(result, tmp_path, monkeypatch):
    from dataclasses import replace

    from methane import evidence
    from methane.config import Costs

    real_save = evidence.save
    monkeypatch.setattr(evidence, "RUNS", tmp_path)
    monkeypatch.setattr(evidence, "save", lambda r: real_save(r, tmp_path))
    first = Path(evidence.export(result))
    original = first.read_bytes()
    second = Path(evidence.export(result, replace(Costs(), methane_eur_per_kg=2)))
    assert first != second and first.read_bytes() == original
    for path in (first, second):
        with zipfile.ZipFile(path) as z:
            assert (
                json.loads(z.read("methane-run-v3.json"))["integrity_sha256"]
                == result["integrity_sha256"]
            )


def test_bundle_clean_stdlib_offline_and_captured_bytes(result, tmp_path):
    bundle = make(result, tmp_path / "bundle.zip")
    root = unpack(bundle, tmp_path / "clean")
    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(root / "check_bundle.py"), str(root)],
        capture_output=True,
        text=True,
        check=True,
        cwd=tmp_path,
    )
    report = json.loads(completed.stdout)
    assert report["reference_passed"] and report["source_status"] == "captured"
    source = decode(result["provenance"]["source_capsule"])
    assert source["uv.lock"] == LOADED_FILES["uv.lock"]
    assert (root / "source/methane/reactor.py").read_bytes() == source["methane/reactor.py"]
    assert (root / "playback.html").is_file()
    assert "function createFieldScene" in (root / "playback.html").read_text()
    assert "onFrame:frame=>fieldScene?.render(frame)" in (root / "playback.html").read_text()
    assert (
        gzip.decompress((root / "recorded-run.json.gz").read_bytes())
        == json.dumps(result, allow_nan=False).encode()
    )
    (root / "source/methane/reactor.py").write_text("changed")
    with pytest.raises(ValueError, match="changed"):
        check(root)


def test_legacy_source_unavailability_not_fabricated(result, tmp_path):
    legacy = copy.deepcopy(result)
    del legacy["provenance"]["source_capsule"]
    from methane.provenance import experiment_identity

    legacy["experiment_id"] = experiment_identity(legacy["provenance"])
    seal(legacy)
    root = unpack(make(legacy, tmp_path / "legacy.zip"), tmp_path / "legacy")
    assert check(root)["source_status"].startswith("unavailable")
    assert not (root / "source").exists()


def test_bundle_paths_cannot_escape_or_follow_symlink(tmp_path):
    path = tmp_path / "bad.zip"
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("../outside", "bad")
    with pytest.raises(ValueError):
        unpack(path, tmp_path / "output")
    assert not (tmp_path / "outside").exists()

    root = tmp_path / "output"
    root.mkdir(exist_ok=True)
    (root / "link").symlink_to(tmp_path, target_is_directory=True)
    with zipfile.ZipFile(path, "w") as z:
        z.writestr("link/outside", "bad")
    with pytest.raises(ValueError):
        unpack(path, root)
    assert not (tmp_path / "outside").exists()


def test_renderer_assets_without_service_animation_are_supported(result):
    original = {k: v for k, v in LOADED_FILES.items() if not k.startswith("assets/field-scene.")}
    assert "function createFieldScene" not in playback(result, original)
