"""Read-only projections retain original operands and selection identities."""

import copy
import errno
import json

import pytest

from methane import studies
from methane import study_presentation as presentation
from methane.provenance import digest


def seal(value):
    return {**value, "integrity_sha256": digest(value)}


@pytest.fixture
def publication(tmp_path):
    identifier, report_id, case_id, attempt_id = "a" * 32, "b" * 32, "c" * 24, "d" * 32
    work = {
        "orders": [
            {
                "id": "repair",
                "kind": "replacement",
                "status": "verified",
                "completed_hour": 3,
                "verified_at_hour": 4,
                "observations": "large observation history" * 10000,
            }
        ],
        "executive": {
            "resources": [
                {"resource": "stock:spare", "ending": 2, "reserved": 1, "unit": "part"},
                {"resource": "upstream:water", "ending": 90, "reserved": 0, "unit": "L"},
                {"resource": "crew-hours", "ending": 7, "reserved": 1, "unit": "h"},
            ],
            "decisions": [{"evidence": "past decision" * 10000}],
        },
    }
    entry = seal(
        {
            "case_id": case_id,
            "attempt_id": attempt_id,
            "status": "complete",
            "computation": {"recorded_vectors": ["original" * 10000]},
            "metrics": {
                "Greedy": {
                    "methane_kg": 21.5,
                    "total_eur": None,
                    "ending": {"battery_kwh": 42.25, "h2_kg": 2.75},
                    "service_outcomes": {"unverified_restorations": 0},
                    "service_work": work,
                }
            },
        }
    )
    case = {
        "case_id": case_id,
        "controller": "Greedy",
        "label": "Recorded fixture",
        "entry": entry,
        "config": {"unchanged": 1},
        "attempts": [attempt_id],
    }
    value = seal(
        {
            "edition_id": identifier,
            "report_id": report_id,
            "published_at": "2026-09-12T00:00:00Z",
            "status": "complete",
            "completed_cases": 1,
            "total_cases": 1,
            "completed_pairs": 0,
            "total_pairs": 0,
            "cases": [case],
        }
    )
    folder = studies.location(identifier, tmp_path)
    path = folder / "reports" / (report_id + ".json")
    studies.write_once(path, value)
    attempt_path = folder / "attempts" / attempt_id / ("case-" + case_id + ".json")
    studies.write_once(attempt_path, entry)
    return value, path, attempt_path


def test_projection_retains_display_operands_without_copying_detailed_histories(publication):
    original, _, _ = publication
    before = digest(original)
    result = presentation.project(original)
    entry = result["cases"][0]["entry"]
    assert "integrity_sha256" not in result and "integrity_sha256" not in entry
    assert (
        result["presentation"]["original_report_integrity_sha256"] == original["integrity_sha256"]
    )
    assert (
        entry["original_entry_integrity_sha256"]
        == original["cases"][0]["entry"]["integrity_sha256"]
    )
    assert "computation" not in entry
    m = entry["metrics"]["Greedy"]
    assert m["ending"] == {"battery_kwh": 42.25, "h2_kg": 2.75}
    assert m["methane_kg"] == 21.5 and m["total_eur"] is None
    assert m["service_outcomes_available"]
    assert "observations" not in m["service_work"]["orders"][0]
    assert [r["resource"] for r in m["service_work"]["executive"]["resources"]] == [
        "stock:spare",
        "upstream:water",
    ]
    assert len(json.dumps(result)) < len(json.dumps(original)) / 100
    m["ending"]["battery_kwh"] = -100
    assert digest(original) == before


def test_persisted_views_are_source_bound_and_caller_isolated(publication, tmp_path):
    value, path, _ = publication
    before = path.read_bytes()
    first = presentation.published_view(value["edition_id"], tmp_path)
    first["cases"][0]["entry"]["status"] = "invented"
    second = presentation.published_view(value["edition_id"], tmp_path, value["report_id"])
    assert second["cases"][0]["entry"]["status"] == "complete"
    assert path.read_bytes() == before
    saved = presentation.verified(presentation.view_path(path))
    assert saved["source_report_sha256"] == presentation.sha(path)
    index = presentation.publications(value["edition_id"], tmp_path)
    index[0]["status"] = "invented"
    assert presentation.publications(value["edition_id"], tmp_path)[0]["status"] == "complete"
    with pytest.raises(ValueError, match="unavailable"):
        presentation.published_view(value["edition_id"], tmp_path, "e" * 32)


@pytest.mark.parametrize("target", ["original", "index", "view"])
def test_changed_files_cannot_reuse_a_previously_verified_view(publication, tmp_path, target):
    value, path, _ = publication
    presentation.published_view(value["edition_id"], tmp_path)
    # Populate warm cache, including the just-created derived artifact's stat.
    presentation.published_view(value["edition_id"], tmp_path)
    selected = {
        "original": path,
        "index": presentation.index_path(path),
        "view": presentation.view_path(path),
    }[target]
    damaged = json.loads(selected.read_text())
    damaged["status"] = "changed after verification"
    selected.write_text(json.dumps(damaged))
    with pytest.raises(ValueError, match="integrity|differs"):
        presentation.published_view(value["edition_id"], tmp_path)


def test_missing_or_misfiled_original_is_not_supplied_by_cached_view(publication, tmp_path):
    value, path, _ = publication
    presentation.published_view(value["edition_id"], tmp_path)
    path.unlink()
    with pytest.raises(ValueError, match="unavailable"):
        presentation.published_view(value["edition_id"], tmp_path, value["report_id"])
    other_path = path.with_name("e" * 32 + ".json")
    studies.write_once(other_path, value)
    with pytest.raises(ValueError, match="another report"):
        presentation.publications(value["edition_id"], tmp_path)


def test_read_only_stores_remain_readable_without_claiming_a_saved_view(
    publication, tmp_path, monkeypatch
):
    value, path, _ = publication

    def denied(*args):
        raise OSError(errno.EROFS, "Read-only store")

    monkeypatch.setattr(studies, "write_once", denied)
    result = presentation.published_view(value["edition_id"], tmp_path)
    assert result["cases"][0]["entry"]["metrics"]["Greedy"]["methane_kg"] == 21.5
    assert not presentation.view_path(path).exists()
    assert not presentation.index_path(path).exists()


def test_derived_record_is_published_whole_and_concurrent_readers_share_it(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    path = tmp_path / "view.json"
    ready = Barrier(2)
    write = studies.write_once

    def delayed_write(destination, value):
        # Even during a slow write, the published filename must stay absent.
        write(destination, value)
        assert not path.exists()
        ready.wait(timeout=5)

    monkeypatch.setattr(studies, "write_once", delayed_write)
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(
            pool.map(lambda _: presentation.write_derived(path, {"value": 42}), range(2))
        )
    assert results[0] == results[1] == presentation.verified(path)
    assert list(tmp_path.iterdir()) == [path]


def test_targeted_attempt_read_does_not_load_unrelated_cases(publication, tmp_path):
    value, _, path = publication
    c = value["cases"][0]
    path.with_name("case-" + "f" * 24 + ".json").write_text("not valid JSON")
    assert studies.entry_for(value["edition_id"], c["case_id"], tmp_path) == c["entry"]
    with pytest.raises(ValueError):
        studies.history(value["edition_id"], tmp_path)
    with pytest.raises(ValueError, match="Invalid study case"):
        studies.entry_for(value["edition_id"], "../escape", tmp_path)


def test_service_transport_pins_original_publication_attempt_and_controller(
    publication, tmp_path, monkeypatch
):
    from methane.config import Config
    from methane.study_service import Request, handle, register

    value, _, attempt_path = publication
    c = value["cases"][0]
    monkeypatch.setattr(studies, "STORE", tmp_path)
    token = register({"run_id": "viewer", "config": Config().to_dict()})
    fields = dict(
        token=token,
        run_id="viewer",
        key="selected-2",
        operation="service-record",
        edition_id=value["edition_id"],
        report_id=value["report_id"],
        case_id=c["case_id"],
        attempt_id=c["entry"]["attempt_id"],
        controller="Greedy",
    )
    answer = handle(Request(**fields))
    assert answer["key"] == "selected-2"
    assert answer["service_record"]["work"] == c["entry"]["metrics"]["Greedy"]["service_work"]
    assert (
        answer["service_record"]["original_entry_integrity_sha256"]
        == c["entry"]["integrity_sha256"]
    )
    for patch, error in [
        ({"attempt_id": "e" * 32}, "does not belong"),
        ({"case_id": "f" * 24}, "does not belong"),
        ({"controller": "missing"}, "no service history"),
        ({"attempt_id": None}, "Select a recorded"),
    ]:
        assert error in handle(Request(**(fields | patch)))["error"]
    # A self-consistent replacement attempt must not masquerade as the original
    # attempt copied into a publication, even if its identifiers are unchanged.
    changed = copy.deepcopy(c["entry"])
    changed.pop("integrity_sha256")
    changed["metrics"]["Greedy"]["service_work"]["orders"][0]["status"] = "changed"
    attempt_path.write_text(json.dumps(seal(changed)))
    assert "originally published attempt" in handle(Request(**fields))["error"]


def test_offline_html_links_full_originals_and_keeps_only_display_metrics(publication, monkeypatch):
    value, _, _ = publication
    monkeypatch.setattr(
        studies,
        "markdown",
        lambda _: (
            "# Preserved study\n\nAn authored explanation.\n\n| Value | Unit |\n| --- | --- |\n| 21.5 | kg |"
        ),
    )
    before = digest(value)
    result = studies.offline_html(value)
    assert len(result) < 10000
    assert 'class="table-scroll" tabindex="0"' in result and "overflow-x:auto" in result
    assert value["report_id"] + ".json" in result
    c = value["cases"][0]
    attempt_link = f"attempts/{c['entry']['attempt_id']}/case-{c['case_id']}.json"
    assert "../" + attempt_link in result
    assert "large observation history" not in result
    assert "42.25" in result and "21.5" in result
    exported = studies.offline_html(value, playback_links=True)
    assert value["edition_id"] + "/" + attempt_link in exported
    assert value["edition_id"] + "/reports/" + value["report_id"] + ".json" in exported
    assert digest(value) == before


def test_index_uses_published_counts_and_distinguishes_unfinished_work(
    publication, tmp_path, monkeypatch
):
    value, path, _ = publication
    manifest = {
        "edition_id": value["edition_id"],
        "created_at": value["published_at"],
        "tier": "smoke",
        "action": "reference",
        "parent_edition_id": None,
        "source_hash": "original-source",
        "protocol": {"title": "Recorded study", "study_id": "test"},
    }
    (path.parent.parent / "manifest.json").write_text("fixture")
    monkeypatch.setattr(studies, "read_manifest", lambda *a: manifest)
    monkeypatch.setattr(
        studies, "report", lambda *a: pytest.fail("Listing reran or loaded full histories")
    )
    monkeypatch.setattr(studies, "active_worker", lambda *a: None)
    row = studies.list_editions(tmp_path)[0]
    assert row["completed_cases"] == 1 and row["summary_scope"] == "latest-publication"
    assert row["status"] == "complete" and row["report_id"] == value["report_id"]
    progress_path = path.parent.parent / "progress.json"
    progress_path.write_text(json.dumps({"status": "running"}))
    assert studies.list_editions(tmp_path)[0]["status"] == "interrupted"
    monkeypatch.setattr(studies, "active_worker", lambda *a: {"edition_id": value["edition_id"]})
    assert studies.list_editions(tmp_path)[0]["status"] == "running"
    studies.write_once(path.parent.parent / "withdrawal.json", {"reason": "Recorded qualification"})
    assert studies.list_editions(tmp_path)[0]["status"] == "withdrawn"
