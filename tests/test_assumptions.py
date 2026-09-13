"""Evidence classification, archival honesty and documented mechanism boundaries."""

import copy
import json
from dataclasses import asdict

import pytest

from methane.assumptions import (
    flatten,
    freshness,
    reference_configuration,
    registry,
    report_html,
    snapshot,
    validate,
)
from methane.config import Config, Plant, Sensors
from methane.physics import State
from methane.provenance import LOADED_FILES, digest
from methane.sensing import observe
from methane.taxonomy import build, response
from methane.taxonomy import digest as taxonomy_digest


def test_inventory_covers_optional_contracts_and_has_no_calibration_claim():
    assert validate()
    r = registry()
    assert {p["path"] for p in r["parameters"]} == set(flatten(reference_configuration()))
    assert len(r["groups"]) == 19
    assert all(p["applicable_range"] is None for p in r["parameters"])
    assert not any(p["evidence_status"] == "Calibrated" for p in r["parameters"])
    assert set(r["categories"]) >= {"design", "equipment", "policy", "economic", "scenario"}


def test_absent_options_and_custom_values_do_not_acquire_default_measurements():
    c = Config().to_dict()
    c["plant"]["battery_kwh"] = 400
    r = snapshot(c)
    ps = {p["path"]: p for p in r["parameters"]}
    assert ps["plant.battery_kwh"]["value"] == 400
    assert ps["plant.battery_kwh"]["reference_default"] == 800
    assert not ps["service_system.travel_hours"]["present"]
    assert ps["service_system.travel_hours"]["value"] is None
    assert ps["service_system.travel_hours"]["reference_default"] == 0.5
    assert r["config_hash"] == digest(c)
    assert r["unreviewed_paths"] == []


def test_new_fields_visible_and_schema_changes_fail_freshness_gate():
    c = Config().to_dict()
    c["plant"]["new_efficiency"] = 0.8
    assert snapshot(c)["unreviewed_paths"] == ["plant.new_efficiency"]
    review = registry()
    review["parameters"].pop()
    with pytest.raises(ValueError, match="inventory changed"):
        validate(review)
    review = registry()
    review["parameters"][0]["reference_default"] = "changed"
    with pytest.raises(ValueError, match="defaults changed"):
        validate(review)


def test_implementation_changes_invalidate_only_applicable_mechanisms():
    changed = dict(LOADED_FILES)
    changed["methane/battery.py"] = b"changed"
    statuses = freshness(files=changed)
    assert statuses["battery"] == "stale"
    assert statuses["thermal"] == "reviewed"


def test_legacy_graph_keeps_original_review_missing():
    result = dict(run_id="old", config=Config().to_dict())
    g = build(result)
    g.pop("assumption_review")
    g["content_hash"] = taxonomy_digest({k: v for k, v in g.items() if k != "content_hash"})
    result["taxonomy"] = g
    before = copy.deepcopy(result)
    assert "assumption_review" not in response(result)["graph"]
    assert response(result, "Current catalogue")["graph"]["assumption_review"]["parameters"]
    assert result == before
    assert "No original assumption review" in report_html(None)


def test_snapshot_not_changed_by_editing_current_registry_copy():
    saved = snapshot(Config().to_dict())
    original = copy.deepcopy(saved)
    other = registry()
    other["groups"]["thermal"]["boundary"] = "edited"
    assert saved == original
    assert json.loads(json.dumps(saved)) == saved
    assert "Current review" in saved["context"]


def test_report_is_offline_readable_and_escapes_recorded_values():
    r = snapshot(Config().to_dict())
    r["parameters"][0]["value"] = "<script>bad</script>"
    text = report_html(r)
    assert "<script>bad" not in text and "&lt;script&gt;" in text
    assert "Evidence needed" in text and "Reference" not in text[:30]
    assert "fetch(" not in text


def test_repeated_object_paths_retain_values_not_fake_mean():
    assert flatten({"sections": [{"capacity": 1}, {"capacity": 2}]}) == {
        "sections.[].capacity": [1, 2]
    }


def test_characterises_existing_zero_throughput_metrology_gap():
    state = State(400, 30, 500, 300)
    row = dict(
        h2_produced_kg=0, h2_consumed_kg=0, applied={"electrolyser_kw": 0}, state=asdict(state)
    )
    values = [
        observe(Plant(), Sensors(), None, row, s, 0, rng_policy="named-channels/1")[
            "h2_inventory_kg"
        ]
        for s in range(10)
    ]
    assert values == [30] * 10
    assert "zero" in registry()["groups"]["sensing"]["boundary"]
