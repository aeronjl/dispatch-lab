import copy
import zipfile

import pytest
from test_siting_production import fixture

from methane.siting import production, reporting, workflow
from methane.siting.store import Store


def test_template_new_edition_and_report_revisions_preserve_inputs_and_results(tmp_path):
    store = Store(tmp_path)
    design, environment = fixture(store, 2)
    original = production.create(
        store,
        name="Original",
        cases=[dict(design_id=design, environment_id=environment, seed=42)],
        partition_hours=1,
    )
    template = workflow.save_template(
        store,
        original["id"],
        name="Reusable",
        method="Match boundaries",
        limitations="Synthetic",
        question="Where is the bottleneck?",
    )
    assert template["recipe"]["cases"][0]["seed"] == 42
    new = production.create(store, **template["recipe"], template_id=template["id"])
    assert new["id"] != original["id"]
    assert production.state(store, new["id"])["status"] == "ready"
    assert new["template"]["record"]["original_source"] == original["source"]
    before = production.inspect(store, new["id"])
    writeup = reporting.draft(store, "study", new["id"])["writeup"]
    assert writeup["method"] == "Match boundaries"
    writeup["findings"] = "<script>untrusted narrative</script>"
    first = reporting.publish(store, "study", new["id"], writeup=writeup)
    frozen = store.get("publication", first["publication_id"])
    production.execute(store, new["id"])
    after = production.inspect(store, new["id"])
    assert after["cases"][0]["completed_hours"] == 2
    assert workflow.runtime_estimate(after)["status"] == "complete"
    assert all(p["elapsed_seconds"] > 0 for p in after["cases"][0]["periods"])
    revised = reporting.draft(store, "study", new["id"], first["publication_id"])["writeup"]
    revised["findings"] = "An incomplete snapshot remains incomplete"
    second = reporting.publish(
        store, "study", new["id"], writeup=revised, previous_publication_id=first["publication_id"]
    )
    assert second["publication_id"] != first["publication_id"]
    saved = store.get("publication", second["publication_id"])
    assert saved["record"]["cases"] == before["cases"]
    assert store.get("publication", first["publication_id"]) == frozen
    assert production.inspect(store, new["id"])["cases"] == after["cases"]
    with pytest.raises(ValueError, match="different result"):
        reporting.draft(store, "study", original["id"], first["publication_id"])
    archive = reporting.bundle(store, first["publication_id"])
    with zipfile.ZipFile(archive["path"]) as z:
        text = z.read("reports/" + first["publication_id"] + ".html").decode()
        assert "&lt;script&gt;" in text and "<script>untrusted" not in text
        assert "site-experiment-template/1" in z.read("study/" + new["id"] + ".json").decode()


def test_runtime_no_unmatched_or_invented_estimate():
    case = dict(
        config={"size": 1},
        controller="Greedy",
        hours=100,
        completed_hours=10,
        periods=[dict(start_hour=0, next_hour=10, elapsed_seconds=20)],
    )
    value = dict(cases=[case])
    assert workflow.runtime_estimate(value)["seconds"] == 180
    other = copy.deepcopy(case)
    other.update(controller="MPC · methane", periods=[], completed_hours=0)
    value["cases"].append(other)
    assert workflow.runtime_estimate(value)["unestimated_hours"] == 100
    assert workflow.runtime_estimate(value)["seconds"] is None
    assert workflow.runtime_estimate(value, 3)["seconds"] == 570
    for bad in (0, -1, float("nan"), float("inf")):
        with pytest.raises(ValueError):
            workflow.runtime_estimate(value, bad)
    case["periods"][0].pop("elapsed_seconds")
    assert workflow.runtime_estimate(dict(cases=[case]))["status"] == "unavailable"
