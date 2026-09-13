import copy
from dataclasses import replace

import pytest

from methane.config import Config, Costs, Scenario
from methane.costing import allocation, reprice
from methane.engineering import audit_archive
from methane.lineage import derived, economic, trace
from methane.provenance import digest, seal
from methane.simulation import run


@pytest.fixture(scope="module")
def result():
    return run(Config(scenario=Scenario(hours=14, horizon_hours=6)), strategies=["Greedy"])


def resolve(root, path):
    for part in path.lstrip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        root = root[int(part)] if isinstance(root, list) else root[part]
    return root


def test_every_record_node_resolves_and_is_detached(result):
    before = copy.deepcopy(result)
    for component in ("electrolyser", "hydrogen", "co2", "reactor", "solar"):
        evidence = trace(result, "Greedy", 12, component)
        assert evidence["status"] == "recorded"
        assert (
            evidence["implementation_file_sha256"]
            == result["provenance"]["source"]["files"][evidence["implementation_file"]]
        )
        ids = {n["id"] for n in evidence["nodes"]}
        for n in evidence["nodes"] + evidence["observed_nodes"]:
            assert resolve(result, n["source"]) == n["value"]
            assert set(n["parents"]) <= ids
        evidence["nodes"][0]["value"] = "mutated"
    assert before == result


def test_cost_nodes_resolve_reconcile_and_repricing_preserves_dispatch(result):
    before = copy.deepcopy(result)
    changed = replace(Costs(), methane_eur_per_kg=3, co2_eur_per_kg=0.9)
    evidence = economic(result, "Greedy", 14, changed)
    assert evidence["dispatch_price_version"] == digest(result["config"]["costs"])
    assert evidence["report_price_version"] == digest(vars(changed))
    ledger = evidence["report"]["lineage"]
    nodes = {n["id"]: n for n in ledger["nodes"]}
    context = {**ledger, "rows": result["records"]["Greedy"]}
    for n in nodes.values():
        assert set(n["parents"]) <= nodes.keys()
        if n["source"].startswith("/") and "*" not in n["source"] and n["source"] != "/rows":
            assert resolve(context, n["source"]) == n["value"]
    for n in nodes.values():
        if n["source"].startswith("/rows/*/"):
            path = n["source"].removeprefix("/rows/*/")
            values = []
            for row in context["rows"]:
                value = row
                for segment in path.split("/"):
                    value = value.get(segment, False)
                values.append(value)
            assert n["value"] == pytest.approx(sum(values))
    assert nodes["allocated_total"]["value"] == pytest.approx(
        sum(nodes[k]["value"] for k in nodes["allocated_total"]["parents"])
    )
    assert nodes["decision_cost"]["value"] == pytest.approx(
        sum(nodes[k]["value"] for k in nodes["decision_cost"]["parents"])
    )
    assert nodes["contribution"]["value"] == pytest.approx(
        nodes["assumed_value"]["value"] - nodes["decision_cost"]["value"]
    )
    report = reprice(result, changed)
    assert report["dispatch_costs"] == result["config"]["costs"]
    assert report["controllers"]["Greedy"][-1]["total_eur"] == evidence["report"]["total_eur"]
    assert before == result
    assert allocation(Config().plant, changed, [], with_lineage=True)["eur_per_kg_ch4"] is None


def test_derived_trace_and_legacy_unavailability(result):
    evidence = derived(result, "Greedy", 14)
    nodes = {n["id"]: n for n in evidence["nodes"]}
    assert nodes["cumulative_methane_kg"]["value"] == pytest.approx(
        result["metrics"]["Greedy"]["methane_kg"]
    )
    assert nodes["utilisation"]["value"] == pytest.approx(
        result["metrics"]["Greedy"]["utilisation"]
    )
    legacy = copy.deepcopy(result)
    del legacy["records"]["Greedy"][0]["component_records"]
    assert trace(legacy, "Greedy", 0, "reactor")["status"] == "unavailable"


def test_resealed_component_record_corruption_detected(result):
    assert audit_archive(result)["passed"]
    changed = copy.deepcopy(result)
    changed["records"]["Greedy"][0]["component_records"]["hydrogen"]["after"]["inventory_kg"] += 1
    seal(changed)
    assert not audit_archive(changed)["passed"]


def test_repricing_reports_current_allocator_not_original_source(result):
    from methane.provenance import LOADED_SOURCE

    old = copy.deepcopy(result)
    old["provenance"]["source"]["content_hash"] = "previous-code"
    old["provenance"]["source"]["files"]["methane/costing.py"] = "previous-allocator"
    report = economic(old, "Greedy", 14)
    assert report["source_file_sha256"] == LOADED_SOURCE["files"]["methane/costing.py"]
    assert report["report_source_content_hash"] == LOADED_SOURCE["content_hash"]
    assert report["dispatch_source_content_hash"] == "previous-code"
    prices = reprice(old)
    assert prices["report_source_content_hash"] == LOADED_SOURCE["content_hash"]
    assert prices["dispatch_source_content_hash"] == "previous-code"
