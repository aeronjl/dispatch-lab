"""Project workflows retain physical authority in existing kernels and frozen studies."""

from copy import deepcopy

import pytest

from methane.config import Config
from methane.siting import production, projects
from methane.siting.catalogue import bootstrap
from methane.siting.environment import weather
from methane.siting.store import Store


@pytest.fixture
def workspace(tmp_path):
    store = Store(tmp_path)
    site = bootstrap(store)[0]
    value = projects.create(store, site["id"])
    return store, value


def test_revisions_preserve_original_and_reject_stale_writes(workspace):
    store, value = workspace
    key = value["project"]["id"]
    old = store.get("project", key)
    c = deepcopy(old["config"])
    c["plant"]["battery_kwh"] = 1200
    new = projects.revise(store, key, c)
    assert store.get("project", key) == old
    assert new["project"]["parent_id"] == key
    assert new["project"]["project_id"] == old["project_id"]
    assert projects.heads(store)[0]["id"] == new["project"]["id"]
    with pytest.raises(ValueError, match="another view"):
        projects.revise(store, key, c)
    assert projects.revise(store, new["project"]["id"], c)["project"]["id"] == new["project"]["id"]


def test_all_present_parameters_reachable_primary_units_and_validation(workspace):
    store, value = workspace
    view = value["preview"]
    paths = {f["path"] for f in view["fields"]}
    assert all(set(group) <= paths for group in view["primary"].values())
    assert "plant.roundtrip_efficiency" in [
        f["path"] for f in view["fields"] if "battery" in f["groups"]
    ]
    assert "scenario.solver_seconds" in paths
    assert "field_operations.dock_kw" in paths
    c = deepcopy(value["project"]["config"])
    c["plant"]["battery_kwh"] = -1
    with pytest.raises(ValueError):
        projects.revise(store, value["project"]["id"], c)
    c = deepcopy(value["project"]["config"])
    c["weather"]["latitude"] += 1
    with pytest.raises(ValueError, match="location"):
        projects.revise(store, value["project"]["id"], c)


def test_equipment_adds_only_supported_package_and_retains_support(workspace):
    _, value = workspace
    c = projects.equipment(value["project"]["config"], "cleaner", True)
    f = Config.from_dict(c).field_operations
    assert f.enabled and f.cleaner_enabled and not f.rover_enabled and not f.reset_enabled
    assert not f.human_fallback
    assert c["service_system"] is not None
    assert len(projects.preview(c)["fields"]) > len(value["preview"]["fields"])
    assert "Dock" in projects.preview(c)["equipment"][0]["requires"]
    with pytest.raises(ValueError, match="supported"):
        projects.equipment(c, "general-purpose-repair", True)


def test_weather_is_explicit_and_resize_comparison_reuses_original_information(workspace):
    store, value = workspace
    key = value["project"]["id"]
    with pytest.raises(ValueError, match="weather"):
        projects.run_project(store, key)
    run = projects.run_project(store, key, synthetic=True, hours=6, controller="Greedy")
    env = store.get("environment", run["environment_id"])
    assert "synthetic" in env["reference"] and "not historical" in env["reference"]
    c = Config.from_dict(value["project"]["config"])
    w = weather(store, run["environment_id"], c)
    assert len(w["truth"]) >= 6
    original = deepcopy(store.get("study", run["study_id"]))
    config = c.to_dict()
    config["plant"]["battery_kwh"] = 1200
    updated = projects.revise(store, key, config)
    result = projects.run_project(
        store,
        updated["project"]["id"],
        environment_id=run["environment_id"],
        baseline_study_id=run["study_id"],
    )
    paired = store.get("study", result["study_id"])
    assert len(paired["cases"]) == 2
    assert {v["environment_id"] for v in paired["cases"]} == {run["environment_id"]}
    assert {v["controller"] for v in paired["cases"]} == {"Greedy"}
    assert {v["config"]["scenario"]["seed"] for v in paired["cases"]} == {c.scenario.seed}
    assert paired["cases"][0]["config"]["plant"]["battery_kwh"] == 800
    assert paired["cases"][1]["config"]["plant"]["battery_kwh"] == 1200
    assert store.get("study", run["study_id"]) == original
    assert projects.read(store, updated["project"]["id"])["studies"]
    config["weather"]["tilt"] = 35
    updated = projects.revise(store, updated["project"]["id"], config)
    with pytest.raises(ValueError, match="orientation"):
        projects.run_project(store, updated["project"]["id"], environment_id=run["environment_id"])


def test_short_project_executes_and_replays_original_period(workspace):
    store, value = workspace
    run = projects.run_project(
        store, value["project"]["id"], synthetic=True, hours=2, controller="Greedy"
    )
    production.execute(store, run["study_id"])
    result = production.inspect(store, run["study_id"])
    assert result["state"]["status"] == "complete"
    period = production.load_period(store, result["cases"][0]["periods"][0]["period_sha256"])
    assert len(period["records"]["Greedy"]) == 2
    assert result["cases"][0]["summary"]["hours"] == 2
    assert (
        projects.perform(store, "project-from-study", run["study_id"], {})["project"]["id"]
        == value["project"]["id"]
    )
