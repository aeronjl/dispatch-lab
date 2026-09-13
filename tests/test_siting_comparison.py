import zipfile

import pytest
from test_siting_production import fixture

from methane.siting.comparison import dominates, recommend, search, weighted_quantile
from methane.siting.production import create, execute
from methane.siting.reporting import bundle, publish
from methane.siting.store import Store


def test_no_invented_probability_and_pareto_arithmetic():
    assert dominates(dict(cost=1, output=2), dict(cost=2, output=1))
    assert not dominates(dict(cost=1, output=2), dict(cost=1, output=2))
    assert weighted_quantile([(10, 0.1), (20, 0.4), (30, 0.5)], 0.1) == 10
    assert weighted_quantile([(10, 0.1), (20, 0.4), (30, 0.5)], 0.5) == 20


def test_search_and_offline_publication_preserve_incomplete_cases(tmp_path):
    store = Store(tmp_path)
    d, e = fixture(store, 4)
    s = search(
        store,
        design_ids=[d],
        environment_ids=[e],
        sizes={"battery_kwh": [400, 800]},
        controllers=["Greedy"],
        seeds=[7],
        budget=1,
    )
    assert len(s["cases"]) == 1 and s["search"]["exclusions"]
    execute(store, s["id"])
    waiting = create(store, name="Not executed", cases=[dict(design_id=d, environment_id=e)])
    r = recommend(store, [s["id"], waiting["id"]], conclusion="<script>no</script>")
    assert r["declared_cases"] == 2 and r["completed_cases"] == 1
    assert r["no_build"]["npv_eur"] == 0 and r["probabilities"] is None
    with pytest.raises(ValueError, match="supporting"):
        recommend(store, [s["id"]], probability_weights={})
    p = publish(store, "recommendation", r["id"])
    b = bundle(store, p["publication_id"])
    with zipfile.ZipFile(b["path"]) as z:
        text = z.read("reports/" + p["publication_id"] + ".html").decode()
        assert "&lt;script&gt;" in text and "<script>no</script>" not in text
        assert "manifest.json" in z.namelist()
        assert any(n.endswith("source-capsule.json") for n in z.namelist())
    assert not b["manifest"]["omissions"]


def test_resource_comparison_and_offline_restore(tmp_path):
    from methane.siting.production import inspect
    from methane.siting.reporting import restore

    store = Store(tmp_path / "original")
    d, e = fixture(store, 3)
    study = create(
        store, name="Resource", cases=[dict(design_id=d, environment_id=e)], mode="resource"
    )
    execute(store, study["id"])
    result = recommend(store, [study["id"]])
    assert result["completed_cases"] == 0  # No completed methane simulation.
    assert result["candidates"][0]["summary"]["resource"]
    pub = publish(store, "study", study["id"])
    archive = bundle(store, pub["publication_id"])
    fresh = Store(tmp_path / "restored")
    restore(archive["path"], fresh)
    assert inspect(fresh, study["id"])["cases"] == inspect(store, study["id"])["cases"]


def test_restricted_inputs_do_not_leak_through_forecasts_or_checkpoints(tmp_path):
    from methane.siting.production import inspect

    store = Store(tmp_path)
    d, e = fixture(store, 2)
    env = store.get("environment", e)
    src = store.get("source", env["source_ids"][0])
    src["redistribution"] = "reference-only"
    env["source_ids"] = [store.put("source", src)]
    e = store.put("environment", env)
    study = create(store, name="Restricted", cases=[dict(design_id=d, environment_id=e)])
    execute(store, study["id"])
    parts = inspect(store, study["id"])["cases"][0]["periods"]
    pub = publish(store, "study", study["id"])
    archive = bundle(store, pub["publication_id"])
    with zipfile.ZipFile(archive["path"]) as z:
        assert "raw/" + parts[0]["period_sha256"] not in z.namelist()
        assert "raw/" + env["normalized_sha256"] not in z.namelist()
        assert not any("entry-" in n for n in z.namelist())
    assert archive["manifest"]["omissions"]
