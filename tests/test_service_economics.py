"""Independent money/stock expectations and immutable executed-work repricing."""

import copy
from decimal import Decimal as D

import pytest

from methane.config import Costs
from methane.service_economics import illustrative, report, validate


def prices():
    p = illustrative(Costs())
    for a in p["assets"].values():
        for k in a:
            if k not in ("provision", "life_years"):
                a[k] = 0
    p["rates"] = dict(
        crew_eur_per_hour=80,
        remote_eur_per_hour=60,
        callout_eur=300,
        vehicle_eur_per_travel_hour=20,
    )
    return p


def row(events=(), *, assets=(), visits=0, active=None, stocks=(), rejected=()):
    return {
        "hour": 0,
        "field_operations": {
            "hour": 0,
            "assets": {k: True for k in assets},
            "resource_events": list(events),
            "crew_committed_hours": 0,
            "human_visits": visits,
            "human_hours": 999,
            "state": {"executive": {"resources": list(stocks)}},
            "support_effects": list(rejected),
            **(active or {}),
        },
    }


def consume(resource, amount, unit="h", phase="perform"):
    return dict(
        kind="consume",
        resource=resource,
        amount=amount,
        unit=unit,
        phase=phase,
        at_hour=0.5,
        mission_id="example-job",
    )


def test_crew_is_charged_once_including_travel_remote_is_separate():
    rows = [
        row(
            [
                consume("crew-hours", 0.5),
                consume("crew-hours", 0.25, phase="travel"),
                consume("remote-hours", 0.1),
            ],
            visits=1,
        )
    ]
    r = report(rows, prices())
    expected = D(".75") * 80 + D(".1") * 60 + 300 + D(".25") * 20
    assert expected == 371
    assert all(v["total_eur"] == float(expected) for v in r["views"].values())
    assert r["quantities"]["crew-hours"] == 0.75
    # The old hands-on scalar is deliberately unrelated: it must not be added.
    assert r["quantity_sources"]["crew-hours"] == [
        "/rows/0/field_operations/resource_events/0",
        "/rows/0/field_operations/resource_events/1",
    ]


def test_part_pool_excludes_ownership_subset_and_does_not_duplicate_procurement():
    p = prices()
    p["assets"]["cleaner"].update(
        capital_eur=1000, replaceable_capital_eur=200, life_years=10, wear_eur_per_hour=5
    )
    rows = [
        row(
            [consume("stock:hardware:cleaner", 1, "module")],
            assets=["cleaner"],
            active={"cleaner_hours": 0.5},
        )
    ]
    r = report(rows, p)
    assert r["views"]["allocated"]["total_eur"] == pytest.approx(float(D(800) / 87600 + 800))
    assert r["views"]["decision"]["total_eur"] == 800
    assert r["views"]["expenditure"]["total_eur"] == 0  # Consumed pre-existing spare.
    p["initial_asset_purchase"] = True
    assert report(rows, p)["views"]["expenditure"]["total_eur"] == 1000
    rows[0]["field_operations"]["resource_events"].append(
        consume("upstream:hardware:cleaner", 1, "module")
    )
    r = report(rows, p)
    assert r["views"]["expenditure"]["total_eur"] == 1800
    assert r["views"]["decision"]["total_eur"] == 800


def test_delivery_purchase_rejection_and_usage_are_separate():
    p = prices()
    rows = [
        row(
            [consume("upstream:water", 100, "L"), consume("stock:water", 20, "L")],
            stocks=[dict(resource="stock:water", unit="L", initial=40, ending=110)],
            rejected=[dict(kind="restock", material="water", rejected=10)],
        )
    ]
    r = report(rows, p)
    assert r["views"]["allocated"]["total_eur"] == pytest.approx(0.09)
    assert r["views"]["decision"]["total_eur"] == pytest.approx(0.09)
    assert r["views"]["expenditure"]["total_eur"] == pytest.approx(0.3)
    assert r["inventories"]["ending:water"] == 110
    p["initial_stock_purchase"] = True
    assert report(rows, p)["views"]["expenditure"]["total_eur"] == pytest.approx(0.42)


def test_contract_includes_tool_wear_and_replacement_but_not_operator_or_consumables():
    p = prices()
    p["assets"]["portable"].update(service_eur_per_active_hour=10, retainer_eur_per_hour=2)
    rows = [
        row(
            [
                consume("crew-hours", 0.5),
                consume("stock:hardware:portable", 1, "module"),
                consume("stock:water", 20, "L"),
            ],
            assets=["portable"],
            active={"portable_hours": 0.5},
        )
    ]
    r = report(rows, p)
    assert r["views"]["allocated"]["total_eur"] == pytest.approx(47.06)
    assert r["views"]["decision"]["total_eur"] == pytest.approx(45.06)
    assert r["views"]["expenditure"]["total_eur"] == 47
    assert any(e.get("provision_includes_part") for e in r["events"])
    p["assets"]["portable"]["capital_eur"] = 100
    with pytest.raises(ValueError, match="includes hardware"):
        validate(p)


def test_missing_applicable_price_is_undefined_and_known_subtotal_is_labelled():
    p = prices()
    p["rates"]["remote_eur_per_hour"] = None
    r = report([row([consume("remote-hours", 0.25)], visits=1)], p)
    assert r["status"] == "incomplete-prices"
    assert r["views"]["allocated"]["total_eur"] is None
    assert r["views"]["allocated"]["known_subtotal_eur"] == 300
    assert r["views"]["allocated"]["unpriced"] == ["remote-hours"]
    assert report([row()], p)["status"] == "complete"  # No applicable missing rate.


@pytest.mark.parametrize(
    "mutation", ["negative", "nan", "bool", "partial", "unit", "legacy", "window"]
)
def test_incomplete_or_unsupported_inputs_are_visible(mutation):
    p = prices()
    rows = [row([consume("stock:water", 2, "L")])]
    if mutation in ("negative", "nan", "bool"):
        p["rates"]["crew_eur_per_hour"] = {"negative": -1, "nan": float("nan"), "bool": True}[
            mutation
        ]
    if mutation == "partial":
        del p["assets"]["dock"]["mapping_eur"]
    if mutation == "unit":
        p["materials"]["water"]["unit"] = "kit"
    if mutation == "legacy":
        del rows[0]["field_operations"]["resource_events"]
    if mutation == "window":
        rows[0]["field_operations"]["hour"] = 4
    with pytest.raises(ValueError):
        report(rows, p)


@pytest.mark.parametrize("case", ["control-hold", "drive-power-loss", "pump-power-loss"])
def test_prices_change_reports_not_executed_work(case):
    from methane.services.hardware_demo import execute, fixture

    run = execute(fixture(case))
    rows = run["records"]["Greedy"]
    original = copy.deepcopy(rows)
    p = illustrative(Costs())
    a = report(rows, p)
    p["rates"]["remote_eur_per_hour"] = 120
    b = report(rows, p)
    assert rows == original
    assert a["trace_id"] == b["trace_id"] and a["assumption_id"] != b["assumption_id"]
    assert b["views"]["allocated"]["total_eur"] - a["views"]["allocated"][
        "total_eur"
    ] == pytest.approx(a["quantities"].get("remote-hours", 0) * 60)
    for view in a["views"].values():
        assert sum(view["components"].values()) == pytest.approx(view["total_eur"])
    assert a["quantities"].get("crew-hours", 0) == pytest.approx(
        sum(r["field_operations"]["crew_committed_hours"] for r in rows)
    )


def test_whole_plant_report_replaces_old_service_subtotal_and_saves_immutable_editions(tmp_path):
    import json

    from methane.costing import allocation
    from methane.service_economics import reprice_run, save_report
    from methane.services.hardware_demo import execute, fixture

    config = fixture("drive-power-loss")
    run = execute(config)
    original = copy.deepcopy(run)
    p = prices()
    value = reprice_run(run, p)
    c = value["controllers"]["Greedy"]
    old = allocation(config.plant, config.costs, run["records"]["Greedy"])
    assert c["allocated_eur"] == pytest.approx(
        old["total_eur"]
        - old["field_operations"]["total_eur"]
        + c["services"]["views"]["allocated"]["total_eur"]
    )
    assert c["decision_cost_eur"] == pytest.approx(
        old["variable_and_wear_eur"]
        - old["field_operations"]["variable_and_wear_eur"]
        + c["services"]["views"]["decision"]["total_eur"]
    )
    first = save_report(value, tmp_path)
    before = first.read_bytes()
    assert save_report(value, tmp_path) == first
    p["rates"]["crew_eur_per_hour"] += 10
    second = save_report(reprice_run(run, p), tmp_path)
    assert second != first and first.read_bytes() == before
    assert run == original
    assert "data:font/woff2;base64," in first.read_text()
    assert 'src="https:' not in first.read_text()
    from methane.source_capsule import decode

    capsule = tmp_path / (value["source_capsule_sha256"] + ".source.json")
    assert "methane/service_economics.py" in decode(json.loads(capsule.read_text()))
    broken = copy.deepcopy(value)
    broken["source_content_hash"] = "unavailable"
    with pytest.raises(ValueError, match="original loaded pricing source"):
        save_report(broken, tmp_path)


def test_report_escaping_and_zero_output():
    from methane.service_economics import html_report, reprice_run
    from methane.services.hardware_demo import execute, fixture

    config = fixture("control-hold")
    run = execute(config)
    run["records"]["Greedy"] = []
    p = prices()
    p["basis"] = '<script>alert("untrusted source")</script>'
    value = reprice_run(run, p)
    assert value["controllers"]["Greedy"]["eur_per_kg_ch4"] is None
    html = html_report(value)
    assert "<script>" not in html and "&lt;script&gt;" in html


@pytest.mark.parametrize("missing", [False, True])
def test_saved_run_integrates_prices_traces_and_independent_accounting(missing):
    from dataclasses import replace

    from methane.config import Config
    from methane.costing import reprice
    from methane.lineage import economic
    from methane.reference import audit
    from methane.service_economics import reprice_run
    from methane.services.hardware_demo import execute, fixture
    from methane.ui import report as ui_report

    base = fixture("drive-power-loss")
    p = illustrative(base.costs)
    if missing:
        p["rates"]["remote_eur_per_hour"] = None
    c = replace(base, service_economics=p)
    assert Config.from_dict(c.to_dict()) == c
    result = execute(c)
    assert result["status"] == "complete", result["failures"]
    checked = audit(result)
    assert checked["passed"], (
        checked["failures"] + [c for c in checked["checks"] if not c["passed"]]
    )[:4]
    frozen = copy.deepcopy(result)
    assert all(
        r["decision"]["service_cost_version"] == result["service_cost_version"]
        for r in result["records"]["Greedy"]
    )
    pricing = reprice(result)
    assert pricing["report_service_price_version"] == pricing["dispatch_service_price_version"]
    assert pricing["dispatch_service_price_version"] == result["service_cost_version"]
    frame = pricing["controllers"]["Greedy"][-1]
    assert "calculation" not in frame["field_operations"]
    assert frame["total_eur"] == result["metrics"]["Greedy"]["total_eur"]
    standalone = reprice_run(result, p)["controllers"]["Greedy"]
    assert (
        frame["total_eur"] == pytest.approx(standalone["allocated_eur"])
        if not missing
        else frame["total_eur"] is None
    )
    trace = economic(result, "Greedy", len(result["records"]["Greedy"]))
    assert trace["report"]["field_operations"]["calculation"]["lines"]
    node_ids = {n["id"] for n in trace["report"]["lineage"]["nodes"]}
    assert all(
        parent in node_ids for n in trace["report"]["lineage"]["nodes"] for parent in n["parents"]
    )
    assert ("Unpriced" in ui_report(result)) == missing
    alternative = copy.deepcopy(p)
    alternative["rates"]["remote_eur_per_hour"] = 180
    later = reprice(result, service_economics=alternative)
    assert later["report_service_price_version"] != later["dispatch_service_price_version"]
    assert result == frozen
    tampered = copy.deepcopy(result)
    tampered["metrics"]["Greedy"]["field_operations"]["views"]["expenditure"]["total_eur"] = 123456
    assert not audit(tampered)["passed"]


def test_full_accounting_configuration_requires_supported_execution():
    from dataclasses import replace

    from methane.config import Config
    from methane.services.hardware_demo import fixture

    with pytest.raises(ValueError, match="finite-logistics"):
        Config(service_economics=illustrative(Costs()))
    c = fixture("control-hold")
    p = illustrative(c.costs)
    cfg = replace(c, service_economics=p)
    p["rates"]["remote_eur_per_hour"] = 999
    assert cfg.service_economics["rates"]["remote_eur_per_hour"] == 60
