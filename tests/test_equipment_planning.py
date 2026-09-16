"""Equipment applicability, evidence provenance and independent residual accounting."""

import csv
import io
import zipfile
from copy import deepcopy

import pytest

from methane.siting import equipment, production, projects, reporting
from methane.siting.catalogue import bootstrap
from methane.siting.store import Store


@pytest.fixture
def deployment(tmp_path):
    store = Store(tmp_path)
    site = next(s for s in bootstrap(store) if s["country"] == "ES")
    p = projects.create(store, site["id"])
    return store, equipment.attach(store, p["project"]["id"])


def imported(store, did, **changes):
    data = dict(
        design_id=did,
        name="Meter trial",
        channel="electrolyser_kw",
        unit="kW",
        asset="ELY-01 / example serial",
        origin="synthetic test",
        supplied_by="Test author",
        source_reference="Independent fixture",
        method="Hourly mean, supplied absolute error bound; synthetic test only",
        uncertainty_absolute=2,
        redistribution="permitted",
        csv_text="timestamp,value,quality\n2025-07-10T00:00:00Z,2,valid\n2025-07-10T01:00:00Z,3,valid\n",
    )
    return equipment.observations(store, {**data, **changes})


def test_reference_arithmetic_and_drift_are_explicit(deployment):
    store, p = deployment
    c = p["project"]["config"]
    assert c["plant"]["solar_kw"] == 1667 * 600 / 1000
    assert c["plant"]["electrolyser_kw"] == 4 * 112
    assert c["plant"]["electrolyser_kw"] / c["plant"][
        "specific_energy_kwh_per_kg"
    ] == pytest.approx(4 * 2.16)
    assert c["weather"]["temperature_coefficient"] == -0.29 / 100
    ctx = equipment.context(store, project_id=p["project"]["id"])
    assert ctx["assessment"]["status"] == "reference assumptions match"
    assert all(g["status"] == "not reviewed" for g in ctx["gates"])
    before = deepcopy(store.get("design", ctx["design_id"]))
    c["plant"]["electrolyser_kw"] = 500
    newer = projects.revise(store, p["project"]["id"], c)
    after = equipment.context(store, project_id=newer["project"]["id"])
    assert after["assessment"]["status"] == "review changed assumptions"
    assert (
        next(c for c in after["assessment"]["checks"] if c["path"] == "plant.electrolyser_kw")[
            "status"
        ]
        == "changed"
    )
    assert store.get("design", ctx["design_id"]) == before
    assert before["equipment_basis_id"] == after["basis_id"]


def test_commissioning_bound_to_design_and_model(deployment, monkeypatch):
    store, p = deployment
    ctx = equipment.context(store, project_id=p["project"]["id"])
    r = equipment.review(
        store,
        dict(
            design_id=ctx["design_id"],
            gate="equipment",
            outcome="incomplete",
            reviewer="Test engineer",
            artifact_name="Missing acceptance record",
            artifact_text="No manufacturer acceptance data supplied.",
            rationale="Await site records.",
        ),
    )
    same = equipment.context(store, project_id=p["project"]["id"])
    assert same["gates"][2]["status"] == "incomplete"
    assert store.read_raw(r["artifact_sha256"]).decode() == r["artifact_text"]
    monkeypatch.setattr(equipment, "identities", lambda c: {"changed": "model"})
    assert (
        equipment.context(store, project_id=p["project"]["id"])["gates"][2]["status"]
        == "stale model binding"
    )
    c = deepcopy(p["project"]["config"])
    c["plant"]["battery_kwh"] = 900
    newer = projects.revise(store, p["project"]["id"], c)
    assert (
        equipment.context(store, project_id=newer["project"]["id"])["gates"][2]["status"]
        == "not reviewed"
    )
    with pytest.raises(ValueError, match="Unknown commissioning"):
        equipment.review(
            store, {**{k: r[k] for k in equipment.Review.model_fields}, "gate": "unknown"}
        )


@pytest.mark.parametrize(
    "changes",
    [
        {"unit": "MW"},
        {"channel": "true_fault"},
        {"uncertainty_absolute": float("nan")},
        {"csv_text": "timestamp,value,quality\n2025-07-10T00:00:00,2,valid\n"},
        {"csv_text": "timestamp,value,quality\n2025-07-10T00:00:00Z,NaN,valid\n"},
        {"csv_text": "timestamp,value,quality\n2025-07-10T00:00:00Z,2,missing\n"},
        {"csv_text": "timestamp,value,quality\n2025-07-10T00:00:00Z,,valid\n"},
        {"csv_text": "timestamp,value,quality\n2025-07-10T00:00:00Z,2,healthy\n"},
        {"csv_text": "timestamp,value,quality\n2025-07-10T00:00:00Z,2,valid,extra\n"},
        {
            "csv_text": "timestamp,value,quality\n2025-10-26T02:00:00+02:00,2,valid\n2025-10-26T01:00:00+01:00,2,valid\n"
        },
    ],
)
def test_ambiguous_observations_rejected(deployment, changes):
    store, p = deployment
    with pytest.raises(ValueError):
        imported(store, projects.design(store, p["project"]["id"]), **changes)


def test_offsets_normalize_without_conflating_dst_repeated_hours(deployment):
    store, p = deployment
    r = imported(
        store,
        projects.design(store, p["project"]["id"]),
        csv_text="timestamp,value,quality\n2025-10-26T02:00:00+02:00,2,valid\n2025-10-26T02:00:00+01:00,3,suspect\n",
    )
    assert [x["timestamp"] for x in r["rows"]] == [
        "2025-10-26T00:00:00+00:00",
        "2025-10-26T01:00:00+00:00",
    ]


def test_recorded_comparison_independent_statistics_trace_and_export(deployment, tmp_path):
    store, p = deployment
    did = projects.design(store, p["project"]["id"])
    accepted = equipment.review(
        store,
        dict(
            design_id=did,
            gate="site",
            outcome="incomplete",
            reviewer="Acceptance fixture",
            artifact_name="No parcel evidence",
            artifact_text="Synthetic software check only",
            rationale="Await site survey",
        ),
    )
    run = projects.run_project(
        store, p["project"]["id"], synthetic=True, hours=4, controller="Greedy"
    )
    sid = run["study_id"]
    original = deepcopy(store.get("study", sid))
    c = original["cases"][0]
    assert c["equipment_applicability"]["status"] == "reference assumptions match"
    assert (
        c["equipment_applicability"]["commissioning_reviews_at_creation"][0]["id"] == accepted["id"]
    )
    later_review = equipment.review(
        store,
        {
            **{k: accepted[k] for k in equipment.Review.model_fields},
            "rationale": "Later review must not alter the original run",
        },
    )
    did = c["design_id"]
    data = imported(store, did)
    pending = equipment.compare(store, data["id"], sid, c["case_id"])
    assert pending["matched"] == 0 and pending["rmse"] is None
    production.execute(store, sid)
    result = equipment.compare(store, data["id"], sid, c["case_id"])
    # Nighttime fixture has zero applied demand; deliberately nonzero fake meter.
    assert [r["simulated"] for r in result["rows"]] == [0, 0]
    assert result["bias"] == -2.5
    assert result["rmse"] == pytest.approx((13 / 2) ** 0.5)
    assert result["qualification"].startswith("Synthetic")
    t = result["rows"][0]["trace"]
    row = production.load_period(store, t["period_sha256"])["records"]["Greedy"][t["hour"]]
    assert row["applied"]["electrolyser_kw"] == result["rows"][0]["simulated"]
    assert store.get("study", sid) == original
    assert store.get("equipment-comparison", pending["id"])["matched"] == 0
    # No manufactured original context for an older record.
    frozen = equipment.context(store, study_id=sid, case_id=c["case_id"])
    assert frozen["assessment"] == c["equipment_applicability"]
    missing = imported(
        store,
        did,
        csv_text="timestamp,value,quality\n2025-07-10T00:00:00Z,0,valid\n2025-07-10T02:00:00Z,5,suspect\n2025-07-10T03:00:00Z,,missing\n",
    )
    partial = equipment.compare(store, missing["id"], sid, c["case_id"])
    assert partial["matched"] == 1 and partial["expected"] == 4 and partial["rmse"] == 0
    assert [r["status"] for r in partial["rows"]] == [
        "compared",
        "observation absent",
        "observation suspect",
        "observation missing",
    ]
    pub = reporting.publish(store, "equipment-comparison", result["id"])
    html = (store.root / "reports" / f"{pub['publication_id']}.html").read_text()
    assert "Synthetic exercise" in html and "Observed versus simulated" in html
    bundle = reporting.bundle(store, pub["publication_id"])["path"]
    with zipfile.ZipFile(bundle) as z:
        assert f"equipment-basis/{p['project']['equipment_basis_id']}.json" in z.namelist()
        assert f"equipment-observations/{data['id']}.json" in z.namelist()
        assert f"raw/{data['raw_sha256']}" in z.namelist()
        assert f"commissioning-review/{accepted['id']}.json" in z.namelist()
        assert f"commissioning-review/{later_review['id']}.json" not in z.namelist()
    restored = Store(tmp_path / "restored")
    reporting.restore(bundle, restored)
    assert restored.get("equipment-comparison", result["id"]) == store.get(
        "equipment-comparison", result["id"]
    )
    assert restored.get("equipment-basis", p["project"]["equipment_basis_id"])["reference"][
        "sources"
    ][0]["sha256"]
    private = imported(store, did, redistribution="reference-only")
    comparison = equipment.compare(store, private["id"], sid, c["case_id"])
    with pytest.raises(ValueError, match="reference-only"):
        reporting.publish(store, "equipment-comparison", comparison["id"])
    wrong = deepcopy(p["project"]["config"])
    wrong["plant"]["battery_kwh"] = 900
    other = projects.revise(store, p["project"]["id"], wrong)
    other_data = imported(store, projects.design(store, other["project"]["id"]))
    with pytest.raises(ValueError, match="exact recorded design"):
        equipment.compare(store, other_data["id"], sid, c["case_id"])


def test_multiblock_inventory_uses_end_of_hour(deployment):
    store, p = deployment
    did = projects.design(store, p["project"]["id"])
    env = projects.synthetic_environment(store, did, "2025-07-10T00:00:00Z", 4)
    s = production.create(
        store,
        name="Blocks",
        cases=[dict(design_id=did, environment_id=env, controller="Greedy")],
        partition_hours=2,
    )
    production.execute(store, s["id"])
    case = production.inspect(store, s["id"])["cases"][0]
    values = []
    for entry in case["periods"]:
        r = production.load_period(store, entry["period_sha256"])
        values.extend(x["state"]["battery_kwh"] for x in r["records"]["Greedy"])
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["timestamp", "value", "quality"])
    for i, v in enumerate(values):
        w.writerow([f"2025-07-10T0{i}:00:00Z", v, "valid"])
    obs = imported(store, did, channel="battery_kwh", unit="kWh", csv_text=buf.getvalue())
    r = equipment.compare(store, obs["id"], s["id"], case["case_id"])
    assert r["matched"] == 4 and r["rmse"] == 0
    assert r["rows"][2]["trace"]["hour"] == 0
    assert r["rows"][2]["trace"]["period_sha256"] == case["periods"][1]["period_sha256"]


def test_removing_basis_preserves_config_and_old_originals(deployment):
    store, p = deployment
    original = deepcopy(p["project"]["config"])
    new = projects.revise(store, p["project"]["id"], original, equipment_basis_id=None)
    assert new["project"]["config"] == original
    assert store.get("project", p["project"]["id"])["equipment_basis_id"]
    run = projects.run_project(
        store, new["project"]["id"], synthetic=True, hours=1, controller="Greedy"
    )
    ctx = equipment.context(store, study_id=run["study_id"], case_id="case-001")
    assert ctx["assessment"]["status"] == "Original equipment explanations unavailable"
    assert ctx["basis_id"] is None
