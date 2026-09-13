"""The organising graph must not invent capabilities or original archive evidence."""

import copy
import gzip
import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from methane.config import Config
from methane.model_service import register
from methane.services.configuration import ServiceSystem
from methane.services.core import definition
from methane.simulation import ASSETS
from methane.taxonomy import build, digest, report, response, snapshot, validate
from methane.taxonomy_service import Request, document


def fixture(registry=True):
    c = Config()
    return dict(
        run_id="taxonomy-test",
        config=c.to_dict(),
        asset_ids=dict(ASSETS),
        field_operations_model={
            "definitions": definition(c.field_operations, ServiceSystem()).manifest()
        }
        if registry
        else {},
    )


def test_complete_domains_families_configuration_and_registry_coverage():
    r = fixture()
    g = build(r)
    assert len(g["domains"]) == 12
    assert len(g["family_review"]["families"]) == 14
    ids = {n["id"] for n in g["nodes"]}
    assert {"configuration:" + k for k in r["config"]} <= ids
    assert {"family:" + f["id"] for f in g["family_review"]["families"]} <= ids
    for group, field in [
        ("assets", "asset_id"),
        ("interfaces", "interface_id"),
        ("capabilities", "capability_id"),
        ("resources", "resource_id"),
        ("access", "edge_id"),
    ]:
        assert g["coverage"][group] == [
            v[field] for v in r["field_operations_model"]["definitions"][group]
        ]
    assert all(n["status"] != "configured" for n in g["nodes"] if n["depth"] == "concept")
    assert all(not n.get("implementation") for n in g["nodes"] if n["kind"] == "family")


def test_component_to_interface_capability_actor_support_and_review_is_connected():
    g = build(fixture())
    triples = {(e["source"], e["relation"], e["target"]) for e in g["edges"]}
    assert (ASSETS["electrolyser"], "has_interface", "interfaces:ELY/contact") in triples
    assert ("capabilities:inspection", "compatible_with", "interfaces:ELY/contact") in triples
    assert ("PLANT-01/ROVER-01", "offers", "capabilities:inspection") in triples
    assert ("PLANT-01/ROVER-01", "depends_on", "resources:energy:rover") in triples
    assert ("PLANT-01/ROVER-01", "member_of", "family:ground-inspector") in triples
    assert ("PLANT-01/ROVER-01", "located_at", "place:dock") in triples
    assert all("not a scheduled" in e["note"] for e in g["edges"] if e["relation"] == "services")


def test_shared_resource_is_one_identity_and_collision_does_not_alias_asset():
    g = build(fixture())
    ids = [n["id"] for n in g["nodes"]]
    assert ids.count("resources:energy:rover") == 1
    assert "resources:asset:PLANT-01/ROVER-01" in ids
    assert "PLANT-01/ROVER-01" in ids


def test_missing_original_and_legacy_assets_do_not_acquire_modern_capabilities():
    r = fixture(False)
    r["asset_ids"]["rover"] = "PLANT-01/ROVER-01"
    original = copy.deepcopy(r)
    assert response(r)["graph"] is None
    g = response(r, "Current catalogue")["graph"]
    assert not any(e["relation"] == "offers" for e in g["edges"])
    assert next(n for n in g["nodes"] if n["id"] == "PLANT-01/ROVER-01")["depth"] == "unavailable"
    assert r == original
    assert "Original catalogue unavailable" in report(r)


def test_snapshot_immutability_evidence_scope_and_broken_references():
    r = fixture()
    r["taxonomy"] = snapshot(r)
    old = copy.deepcopy(r["taxonomy"])
    r["config"]["plant"]["battery_kwh"] = 500
    assert response(r)["graph"] == old
    assert response(r, "Current catalogue")["graph"] != old
    assert not any(n.get("review_applies_to_execution") for n in old["nodes"])
    broken = copy.deepcopy(old)
    broken["edges"][0]["target"] = "missing"
    with pytest.raises(ValueError, match="Unresolved"):
        validate(broken)
    broken = copy.deepcopy(old)
    broken["nodes"][0]["label"] = "Changed"
    with pytest.raises(ValueError, match="content changed"):
        validate(broken)
    r = fixture()
    r["field_operations_model"]["definitions"]["assets"][0]["battery_resource"] = "missing"
    with pytest.raises(ValueError, match="Unresolved service"):
        build(r)


def test_containment_cycles_are_rejected_even_with_updated_hash():
    g = build(fixture())
    g["edges"].append(
        dict(source=ASSETS["solar"], relation="contains", target=ASSETS["site"], note="")
    )
    g["content_hash"] = digest({k: v for k, v in g.items() if k != "content_hash"})
    with pytest.raises(ValueError, match="Cyclic"):
        validate(g)


def test_transport_run_binding_context_and_generation():
    r = fixture()
    r["taxonomy"] = snapshot(r)
    token = register(r)
    request = Request(token=token, run_id=r["run_id"], key="selection-42")
    result = document(request)
    assert result["key"] == "selection-42"
    assert result["run_id"] == r["run_id"]
    assert result["graph"] == r["taxonomy"]
    with pytest.raises(HTTPException) as e:
        document(request.model_copy(update={"run_id": "another-run"}))
    assert e.value.status_code == 410
    with pytest.raises(HTTPException) as e:
        document(request.model_copy(update={"context": "reconstruct original"}))
    assert e.value.status_code == 422


def test_offline_report_retains_links_original_ids_and_scopes():
    r = fixture()
    r["taxonomy"] = snapshot(r)
    page = report(r)
    assert 'href="#PLANT-01/ELY-01"' in page
    assert "No execution capability, reliability, capacity or cost is assumed" in page
    assert "Original catalogue captured" in page
    assert "not a scheduled or successful repair" in page
    assert "Current catalogue" not in page


def test_existing_archive_can_be_read_without_migration():
    p = Path("tests/fixtures/browser-demo-v2.json.gz")
    raw = p.read_bytes()
    r = json.loads(gzip.decompress(raw))
    assert response(r)["graph"] is None
    validate(build(r))
    assert p.read_bytes() == raw
