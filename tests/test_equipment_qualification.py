from copy import deepcopy

import pytest

from methane.siting import equipment, production, projects, reporting
from methane.siting import equipment_qualification as q
from methane.siting.catalogue import bootstrap
from methane.siting.store import Store


@pytest.fixture
def case(tmp_path):
    store = Store(tmp_path / "site")
    site = next(s for s in bootstrap(store) if s["country"] == "ES")
    p = projects.create(store, site["id"])
    p = equipment.attach(store, p["project"]["id"])
    run = projects.run_project(
        store, p["project"]["id"], synthetic=True, hours=4, controller="Greedy"
    )
    sid = run["study_id"]
    c = store.get("study", sid)["cases"][0]
    return store, sid, c


def dataset(case, values=(2, 3, 4, 0), **changes):
    store, _, c = case
    return equipment.observations(
        store,
        dict(
            design_id=c["design_id"],
            name="Independent synthetic meter fixture",
            channel="electrolyser_kw",
            unit="kW",
            asset="ELY-01 test only",
            origin="synthetic test",
            supplied_by="Software test",
            source_reference="Test fixture",
            method="No field measurements; independent residual arithmetic",
            uncertainty_absolute=2,
            redistribution="permitted",
            csv_text="timestamp,value,quality\n"
            + "".join(f"2025-07-10T0{i}:00:00Z,{v},valid\n" for i, v in enumerate(values)),
            **changes,
        ),
    )


def protocol(case, d, **changes):
    store, sid, c = case
    data = dict(
        title="Declared hourly error",
        study_id=sid,
        case_id=c["case_id"],
        dataset_id=d["id"],
        start_hour=0,
        split_hour=2,
        end_hour=4,
        minimum_coverage=1,
        minimum_pairs=2,
        max_rmse=3,
        max_absolute_bias=2,
        comparable=True,
        reviewer="Test author",
        rationale="Synthetic matched boundary; thresholds are test assertions, not a standard.",
    )
    return q.freeze(store, {**data, **changes})


def test_frozen_criteria_independent_statistics_and_preserved_editions(case):
    store, sid, _ = case
    p = protocol(case, dataset(case))
    original = deepcopy(store.get("equipment-qualification-protocol", p["id"]))
    a = q.evaluate(store, p["id"])
    assert a["status"] == "incomplete evidence"
    assert a["statistics"]["evaluation"]["rmse"] is None
    production.execute(store, sid)
    b = q.evaluate(store, p["id"])
    assert b["id"] != a["id"] and b["status"] == "within declared numerical criteria"
    assert b["statistics"]["development"]["bias"] == -2.5
    assert b["statistics"]["evaluation"]["bias"] == -2
    assert b["statistics"]["evaluation"]["rmse"] == pytest.approx(8**0.5)
    assert b["statistics"]["evaluation"]["beyond_measurement_bound"] == 1
    assert b["statistics"]["evaluation"]["largest_discrepancies"][0]["hour"] == 2
    assert b["statistics"]["evaluation"]["largest_discrepancies"][0]["trace"]
    assert b["qualification"].startswith("Synthetic")
    assert store.get("equipment-qualification-protocol", p["id"]) == original
    assert store.get("equipment-qualification", a["id"])["status"] == "incomplete evidence"


@pytest.mark.parametrize(
    "change",
    [
        dict(split_hour=4),
        dict(start_hour=2),
        dict(end_hour=5),
        dict(minimum_pairs=3),
        dict(max_rmse=float("nan")),
        dict(reviewer=" "),
        dict(minimum_coverage=0),
        dict(split_hour=True),
    ],
)
def test_invalid_protocols_rejected(case, change):
    with pytest.raises(ValueError):
        protocol(case, dataset(case), **change)


def test_missing_hours_uncertainty_and_unsupported_comparison(case):
    store, sid, _ = case
    production.execute(store, sid)
    short = protocol(case, dataset(case, values=(0, 0, 0)))
    r = q.evaluate(store, short["id"])
    assert r["status"] == "incomplete evidence"
    assert r["statistics"]["evaluation"]["coverage"] == 0.5
    d = dataset(case)
    p = protocol(case, d, max_rmse=1, max_absolute_bias=1)
    r = q.evaluate(store, p["id"])
    assert r["status"] == "outside declared criteria" and r["uncertainty_exceeds_tolerance"]
    p = protocol(case, d, comparable=False)
    assert q.evaluate(store, p["id"])["status"] == "unsupported comparison"


def test_future_evaluation_values_do_not_change_development_statistics(case):
    store, sid, _ = case
    production.execute(store, sid)
    a = q.evaluate(store, protocol(case, dataset(case))["id"])
    b = q.evaluate(store, protocol(case, dataset(case, (2, 3, 8, 10)))["id"])
    assert a["statistics"]["development"] == b["statistics"]["development"]
    assert a["statistics"]["evaluation"]["bias"] != b["statistics"]["evaluation"]["bias"]


def test_preservation_export_and_reference_only_gate(case, tmp_path, monkeypatch):
    store, sid, _ = case
    production.execute(store, sid)
    p = protocol(case, dataset(case))
    r = q.evaluate(store, p["id"])
    pub = reporting.publish(store, "equipment-qualification", r["id"])
    html = (store.root / "reports" / (pub["publication_id"] + ".html")).read_text()
    assert "Scoped equipment assessment" in html and "Synthetic exercise" in html
    restored = Store(tmp_path / "restored")
    reporting.restore(reporting.bundle(store, pub["publication_id"])["path"], restored)
    assert q.current(restored, r["id"]) == q.current(store, r["id"])
    assert restored.get("equipment-qualification-protocol", p["id"]) == store.get(
        "equipment-qualification-protocol", p["id"]
    )
    monkeypatch.setattr(q, "LOADED_SOURCE", {"content_hash": "different"})
    assert q.current(restored, r["id"])["applicability"].startswith("Historical")
    private = deepcopy(store.get("equipment-observations", p["dataset_id"]))
    private["redistribution"] = "reference-only"
    key = store.put("equipment-observations", private)
    restricted = protocol(case, {"id": key})
    report = q.evaluate(store, restricted["id"])
    with pytest.raises(ValueError, match="reference-only"):
        reporting.publish(store, "equipment-qualification", report["id"])


def test_new_channels_preserve_units_and_missing_legacy_boundaries(case):
    store, sid, c = case
    production.execute(store, sid)
    old = dataset(case)
    data = {k: v for k, v in old.items() if k in equipment.ObservationImport.model_fields}
    data["csv_text"] = "timestamp,value,quality\n2025-07-10T00:00:00Z,-5,valid\n"
    data.update(channel="ambient_c", unit="°C")
    assert equipment.observations(store, data)["rows"][0]["value"] == -5
    data.update(channel="process_ac_kw", unit="kW")
    with pytest.raises(ValueError):
        equipment.observations(store, data)
    data["csv_text"] = data["csv_text"].replace("-5", "5")
    d = equipment.observations(store, data)
    r = equipment.compare(store, d["id"], sid, c["case_id"])
    assert r["matched"] == 0 and r["rows"][0]["simulated"] is None
    assert "EXCLUDING startup" in equipment.CHANNELS["electrolyser_kw"][2]


def test_integrated_water_meter_compares_to_original_inventory(tmp_path):
    store = Store(tmp_path)
    site = next(s for s in bootstrap(store) if s["country"] == "ES")
    p = equipment.attach(store, projects.create(store, site["id"])["project"]["id"])
    p = equipment.save_integration(store, p["project"]["id"], {"initial_water_l": 123})
    sid = projects.run_project(
        store, p["project"]["id"], synthetic=True, hours=4, controller="Greedy"
    )["study_id"]
    c = store.get("study", sid)["cases"][0]
    production.execute(store, sid)
    d = dataset((store, sid, c))
    inputs = {k: v for k, v in d.items() if k in equipment.ObservationImport.model_fields}
    inputs.update(
        channel="water_l",
        unit="L",
        csv_text="timestamp,value,quality\n2025-07-10T00:00:00Z,120,valid\n",
    )
    water = equipment.observations(store, inputs)
    r = equipment.compare(store, water["id"], sid, c["case_id"])
    assert r["rows"][0]["simulated"] == 123
    assert r["rows"][0]["residual"] == 3
    assert r["rows"][0]["trace"]["component"] == "electrolyser"
