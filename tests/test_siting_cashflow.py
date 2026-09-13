from copy import deepcopy

import pytest
from test_siting_production import fixture

from methane.siting.cashflow import CashScenario, calculate, defaults, payback, report
from methane.siting.production import create, execute
from methane.siting.store import Store, digest


def test_discounted_cash_flow_independent_example():
    v = calculate(100, [dict(receipts_eur=80, cost_eur=10, accepted_kg=10)] * 2, 0.1)
    assert v["npv_eur"] == pytest.approx(-100 + 70 / 1.1 + 70 / 1.21)
    assert v["levelised_eur_per_kg"] == pytest.approx(
        (100 + 10 / 1.1 + 10 / 1.21) / (10 / 1.1 + 10 / 1.21)
    )
    assert v["discounted_payback"]["first_crossing_year"] == 2
    assert (
        calculate(100, [dict(receipts_eur=0, cost_eur=10, accepted_kg=0)], 0.1)[
            "levelised_eur_per_kg"
        ]
        is None
    )
    p = payback([-100, 10, -50, 30])
    assert (
        p["first_crossing_year"] == 1
        and p["sustained_recovery_year"] == 3
        and p["reversals"] == [2]
    )
    with pytest.raises(ValueError):
        CashScenario(price_basis="real", inflation=0.02)


def test_repricing_immutable_trace_and_missing_costs(tmp_path):
    store = Store(tmp_path)
    d, e = fixture(store, 6)
    s = create(
        store,
        name="Cash teaching trace",
        cases=[dict(design_id=d, environment_id=e)],
        partition_hours=3,
    )
    execute(store, s["id"])
    before = digest(store.get("study", s["id"]))
    a = defaults(store.get("design", d)["config"])
    with pytest.raises(ValueError, match="partial"):
        report(store, s["id"], "case-001", a)
    a["repeat_partial_period"] = True
    r = report(store, s["id"], "case-001", a)
    assert r["npv_eur"] is None and r["unpriced"]
    a["items"] = [{**i, "eur": i["eur"] or 0} for i in a["items"]]
    a["methane_acceptance_fraction"] = 1
    x = report(store, s["id"], "case-001", a)
    b = deepcopy(a)
    b["methane_eur_per_kg"] = 100
    y = report(store, s["id"], "case-001", b)
    assert x["physical_partition_hashes"] == y["physical_partition_hashes"]
    assert x["dispatch_price_version"] == y["dispatch_price_version"]
    assert x["price_version"] != y["price_version"]
    assert digest(store.get("study", s["id"])) == before
    assert x["initial_cash_eur"] == sum(i["eur"] for i in a["items"] if i["category"] == "initial")
