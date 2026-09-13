import copy
import hashlib
import json
import math
import posixpath
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit

import pytest

from methane import documentation
from methane.config import Config, Scenario
from methane.offline_model import pages, table_chunks
from methane.provenance import LOADED_SOURCE, digest
from methane.simulation import run


@pytest.fixture(scope="module")
def recording():
    from methane.field_operations import FieldOperations

    return run(
        Config(
            scenario=Scenario(hours=2, horizon_hours=6),
            field_operations=FieldOperations(enabled=True),
        ),
        strategies=("Greedy",),
    )


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.targets = []

    def handle_starttag(self, tag, attrs):
        self.targets.extend(v for k, v in attrs if k in ("href", "src"))


def check_links(files, external=()):
    for name, body in files.items():
        if not name.endswith(".html"):
            continue
        parser = Links()
        parser.feed(body.decode())
        for target in parser.targets:
            address = urlsplit(target)
            if address.scheme:
                assert address.scheme == "https"
                continue
            if not address.path:
                continue
            path = posixpath.normpath(
                posixpath.join(posixpath.dirname(name), unquote(address.path))
            )
            assert path in files or path in external, (name, target)


def test_all_topics_retain_calculation_values_identity_and_original_inputs(recording, monkeypatch):
    from methane import dispatch, learning

    before = digest(recording)
    monkeypatch.setattr(dispatch, "plan", lambda *a, **kw: pytest.fail("Export ran a planner"))
    monkeypatch.setattr(
        learning, "evaluate", lambda *a, **kw: pytest.fail("Export ran a teaching fixture")
    )
    files = dict(pages(recording))
    manifest = json.loads(files["model/manifest.json"])
    assert manifest["rendered_input_hash"] == before
    assert manifest["original_recording_integrity"] == recording["integrity_sha256"]
    assert manifest["renderer_source"] == LOADED_SOURCE["content_hash"]
    calculations = [x for x in manifest["files"] if x["kind"] == "calculation-data"]
    assert len(calculations) == len(documentation.TOPICS) * 2
    for row in calculations:
        value = json.loads(files[row["path"]])
        topic = Path(row["path"]).stem.split("-")[-1]
        expected = documentation.recorded(recording, topic, value["controller"], value["interval"])[
            "calculation"
        ]
        assert value["calculation"] == json.loads(json.dumps(expected))
    assert digest(recording) == before
    for row in manifest["files"]:
        assert hashlib.sha256(files[row["path"]]).hexdigest() == row["sha256"]
    check_links(files, ("recorded-run.json.gz", "playback.html"))
    assert len(files["model-report.html"]) < 500000
    assert (
        max(len(v) for k, v in files.items() if k.endswith(".html") and k != "model-report.html")
        < 110000
    )
    assert b"Applicability and omitted behaviour" in files["model-report.html"]
    assert b"Current metadata has not been substituted" in b"".join(
        v for k, v in files.items() if k.endswith(".html")
    )


def test_exported_battery_operands_reconcile_independently(recording):
    files = dict(pages(recording))
    for name, raw in files.items():
        if not name.endswith("-battery.json"):
            continue
        c = json.loads(raw)["calculation"]
        nodes = {n["id"]: n for n in c["nodes"]}
        eta = math.sqrt(nodes["roundtrip"]["value"])
        expected = nodes["begin"]["value"] + nodes["duration"]["value"] * (
            nodes["charge"]["value"] * eta - nodes["discharge"]["value"] / eta
        )
        assert nodes["end"]["value"] == pytest.approx(expected)
        assert nodes["end"]["unit"] == "kWh"
        assert nodes["end"]["parents"]


def test_legacy_missing_explanations_and_examples_are_not_reconstructed(monkeypatch):
    from methane import learning
    from methane.evidence import load

    value = load(Path(__file__).parent / "fixtures/browser-demo-v2.json.gz")
    value["records"] = {k: rows[:1] for k, rows in value["records"].items()}
    value.pop("documentation", None)
    value.pop("learning_examples", None)
    monkeypatch.setattr(
        learning, "evaluate", lambda *a, **k: pytest.fail("Invented original example")
    )
    files = dict(pages(value))
    assert b"Original explanations unavailable" in files["model-report.html"]
    assert b"No saved learning outputs" in files["model-report.html"]
    assert json.loads(files["model/documentation.json"]) is None
    assert json.loads(files["model/manifest.json"])["original_recording_integrity"] is None
    assert not any("example-" in k for k in files)


def test_service_data_stays_complete_but_does_not_expand_into_the_overview(recording):
    from methane.provenance import seal

    value = copy.deepcopy(recording)
    row = value["records"]["Greedy"][0]
    row["field_operations"].update(
        {
            "hour": 0,
            "requested_service_kwh": 0,
            "applied_service_kwh": 0,
            "unapplied_service_kwh": 0,
            "decision": {"recorded_search": "large original detail " * 10000},
            "planning_snapshot": {"original": True},
            "mission_events": [{"kind": "inspection", "available_at": 1}],
        }
    )
    value = seal(value)
    before = digest(value)
    files = dict(pages(value))
    data_name = next(k for k in files if k.endswith("h0000-services.json"))
    assert json.loads(files[data_name])["field_operations"] == row["field_operations"]
    visible = b"".join(v for k, v in files.items() if k.endswith("services-1.html"))
    assert b"requested_service_kwh" in visible and b"available_at" in visible
    assert b"large original detail" not in visible
    assert b"large original detail" not in files["model-report.html"]
    assert digest(value) == before


def test_long_values_are_partitioned_and_escaped_without_truncation():
    value = "<&>" * 20000
    chunks = list(table_chunks([("recorded value", value)]))
    assert len(chunks) > 1 and max(len(c.encode()) for c in chunks) < 100000
    assert "<script" not in "".join(chunks)
    assert "".join(chunks).count("&lt;") == 20000
    assert "".join(chunks).count("&gt;") == 20000


def test_study_relative_links_and_shared_renderer_source(recording):
    files = dict(
        pages(
            recording,
            archive_href="../../edition/attempts/run.json.gz",
            source_href="../../model-report-source.json",
            include_source=False,
        )
    )
    assert "../../model-report-source.json" not in files
    check_links(
        files,
        ("../../edition/attempts/run.json.gz", "../../model-report-source.json", "playback.html"),
    )
    with pytest.raises(ValueError, match="relative"):
        dict(pages(recording, archive_href="javascript:alert(1)"))
    with pytest.raises(ValueError, match="included renderer"):
        dict(pages(recording, source_href="../escape.json"))
