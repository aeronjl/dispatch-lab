from dataclasses import replace
from datetime import UTC, datetime, timedelta

from methane.config import Config, Scenario
from methane.siting.catalogue import bootstrap
from methane.siting.contracts import DeploymentDesign
from methane.siting.environment import CONVENTION
from methane.siting.production import create, directory, execute, inspect, load_period
from methane.siting.sources import snapshot
from methane.siting.store import Store, encode
from methane.timebase import stamp
from methane.weather import prepare


def fixture(store, hours=30):
    sites = bootstrap(store)
    site = sites[0]
    c = Config(
        scenario=Scenario(hours=hours + 48, horizon_hours=6, solver_seconds=0.05),
        weather=replace(Config().weather, start="2025-01-01"),
    )
    w = prepare(c)
    design = store.put(
        "design",
        DeploymentDesign(
            site_revision=site["id"], name="Bounded production check", config=c.to_dict()
        ),
    )
    sid = snapshot(
        store,
        encode(w),
        provider="Dispatch Lab",
        product="Synthetic continuity fixture",
        edition="1",
        retrieved_at=datetime.now(UTC),
        request={},
        attribution="Dispatch Lab",
        licence="Test fixture",
        redistribution="permitted",
        timing=CONVENTION,
        source_url="fixture:continuity",
    )
    env = store.put(
        "environment",
        dict(
            schema_version="site-environment/1",
            design_id=design,
            site_revision=site["id"],
            start=stamp(datetime(2025, 1, 3, tzinfo=UTC)),
            end=stamp(datetime(2025, 1, 3, tzinfo=UTC) + timedelta(hours=hours)),
            hours=hours,
            information="persistence/1",
            reference="Synthetic hourly fixture, not weather evidence",
            timezone="Europe/London",
            conversion={
                "weather": c.to_dict()["weather"],
                "solar_kw": c.plant.solar_kw,
                "section_design": None,
            },
            source_ids=[sid],
            normalized_sha256=store.raw(encode(dict(truth=w["truth"], vintages=[]))),
            convention=CONVENTION,
            publication_lag_hours=0,
            assumptions=["Previous synthetic day persistence"],
        ),
    )
    return design, env


def test_partition_publication_resume_and_original_trace(tmp_path):
    store = Store(tmp_path)
    design, env = fixture(store)
    study = create(
        store,
        name="Continuity integration",
        cases=[dict(design_id=design, environment_id=env)],
        partition_hours=13,
    )
    execute(store, study["id"])
    value = inspect(store, study["id"])
    assert value["state"]["status"] == "complete"
    case = value["cases"][0]
    assert case["completed_hours"] == 30
    assert len(case["periods"]) == 3
    assert case["summary"]["hours"] == 30
    original = load_period(store, case["periods"][1]["period_sha256"])
    assert original["records"]["Greedy"][0]["hour"] == 13
    assert (
        original["continuous_period"]["initial_state"]
        == load_period(store, case["periods"][0]["period_sha256"])["records"]["Greedy"][-1]["state"]
    )
    before = {
        p.name: p.read_bytes() for p in (directory(store, study["id"]) / "case-001").glob("entry-*")
    }
    execute(store, study["id"])
    assert before == {
        p.name: p.read_bytes() for p in (directory(store, study["id"]) / "case-001").glob("entry-*")
    }
    assert case["summary"]["products"]["co2_captured_kg"] == 0


def test_resume_reconciles_a_crash_after_last_period(tmp_path):
    store = Store(tmp_path)
    d, e = fixture(store, 3)
    study = create(store, name="Crash boundary", cases=[dict(design_id=d, environment_id=e)])
    execute(store, study["id"])
    path = directory(store, study["id"]) / "case-001" / "summary.json"
    original = path.read_bytes()
    path.unlink()
    execute(store, study["id"])
    assert path.read_bytes() == original


def test_worker_lease_survives_independent_server_instances(tmp_path):
    import pytest

    from methane.siting.production import worker_lease

    with worker_lease(Store(tmp_path)):
        with pytest.raises(ValueError, match="holds"):
            worker_lease(Store(tmp_path))
    with worker_lease(Store(tmp_path)):
        pass


def test_thin_summary_matches_full_decision_operands(tmp_path):
    from methane.simulation import summarise
    from methane.siting.production import PeriodRows, entries

    store = Store(tmp_path)
    d, e = fixture(store, 6)
    study = create(store, name="Projection", cases=[dict(design_id=d, environment_id=e)])
    execute(store, study["id"])
    parts = entries(store, study["id"], "case-001")
    full = load_period(store, parts[0]["period_sha256"])
    thin = PeriodRows(store, parts, "Greedy")
    assert summarise(thin, Config.from_dict(full["config"]), thin.truth()) == summarise(
        full["records"]["Greedy"],
        Config.from_dict(full["config"]),
        full["retrospective_truth_by_controller"]["Greedy"],
    )
