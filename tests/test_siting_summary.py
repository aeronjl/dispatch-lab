from dataclasses import replace

import pytest
from test_siting_production import fixture

from methane.config import Config
from methane.lifecycle.fixtures import illustrative
from methane.service_economics import ACTIVITY_VERSION
from methane.service_economics import illustrative as prices
from methane.services.configuration import ServiceSystem
from methane.simulation import summarise
from methane.siting import production, summary
from methane.siting.store import Store, digest


@pytest.mark.parametrize("finite_prices", [False, True])
def test_single_read_summary_preserves_every_total_and_terminal_state(
    tmp_path, monkeypatch, finite_prices
):
    monkeypatch.setenv("DISPATCH_BATCH_WORKER", "1")
    store = Store(tmp_path)
    design, environment = fixture(store, 24)
    saved = store.get("design", design)
    c = illustrative(
        Config.from_dict(saved["config"]), commission=True, aged=True, policy="condition"
    )
    c = replace(
        c,
        service_system=ServiceSystem(
            cleaning_model="section-optical/1", support_model="logistics/1"
        ),
    )
    if finite_prices:
        c = replace(c, service_economics=prices(c.costs, version=ACTIVITY_VERSION))
    saved["config"] = c.to_dict()
    design = store.put("design", saved)
    study = production.create(
        store,
        name="Report equivalence",
        cases=[dict(design_id=design, environment_id=environment)],
        partition_hours=7,
    )
    production.execute(store, study["id"])
    case = study["cases"][0]
    items = production.entries(store, study["id"], case["case_id"])
    sequence = production.PeriodRows(store, items, case["controller"])
    original = list(sequence)
    before = digest(original)
    expected = summarise(original, c, list(sequence.truth()))
    expected.update(
        products=production.products(original),
        calendar=production.calendar(original),
        scope="Entire continuous case; allocation evaluated once, not added from partition allowances",
    )
    calls = []
    read = production.read_blob
    monkeypatch.setattr(production, "read_blob", lambda s, k: (calls.append(k), read(s, k))[1])
    actual = summary.calculate(store, study["id"], case)
    assert actual == expected
    assert digest(original) == before
    assert len(calls) == len(items)
    from methane.cancellation import CancelledOperation

    with pytest.raises(CancelledOperation):
        summary.calculate(store, study["id"], case, cancelled=lambda: True)
    assert actual["service_work"] == original[-1]["field_operations"]["state"]
    assert (
        actual["lifecycle"]["ending_condition"] == original[-1]["lifecycle"]["after"]["condition"]
    )
    monkeypatch.setattr(production, "entries", lambda *args: items[:-1])
    with pytest.raises(ValueError, match="every declared interval"):
        summary.calculate(store, study["id"], case)
