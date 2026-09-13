import copy
from dataclasses import replace

import pytest
from test_siting_production import fixture

from methane.autonomy_qualification import changed_paths, forecast_stress, local_policy, window
from methane.policy import Policy
from methane.recovery import RecoveryPolicy
from methane.services.verification_examples import fixture as service_fixture
from methane.siting.production import create, entries, execute, load_period
from methane.siting.store import Store, encode


def test_forecast_sensitivity_preserves_truth_and_publication(tmp_path):
    store = Store(tmp_path)
    design, eid = fixture(store)
    env = store.get("environment", eid)
    payload = {
        "truth": {"now": {"irradiance_wm2": 80}},
        "vintages": [
            {
                "available_at": "boundary",
                "issued_at": "earlier",
                "data": {"later": {"irradiance_wm2": 100, "ambient_c": 12}},
            }
        ],
    }
    env.update(information="archived-ifs/1", normalized_sha256=store.raw(encode(payload)))
    original = store.put("environment", env)
    key = forecast_stress(store, original, 1.5)
    changed = store.get("environment", key)
    result = __import__("json").loads(store.read_raw(changed["normalized_sha256"]))
    assert result["truth"] == payload["truth"]
    assert result["vintages"][0]["available_at"] == "boundary"
    assert result["vintages"][0]["data"]["later"] == {"irradiance_wm2": 150, "ambient_c": 12}
    assert store.get("environment", original) == env
    assert changed["source_ids"] == env["source_ids"]
    assert changed["parent_environment_id"] == original
    assert changed["transformation"]["factor"] == 1.5
    with pytest.raises(ValueError):
        forecast_stress(store, eid, 1.5)


def test_window_never_invents_coverage_or_forecasts(tmp_path):
    store = Store(tmp_path)
    _, eid = fixture(store)
    original = store.get("environment", eid)
    key = window(store, eid, original["start"], 24)
    new = store.get("environment", key)
    assert new["hours"] == 24
    assert new["normalized_sha256"] == original["normalized_sha256"]
    assert store.get("environment", eid) == original
    with pytest.raises(ValueError):
        window(store, eid, original["start"], 31)


def test_explicit_policy_frozen_executed_and_bound_to_continuation(tmp_path):
    store = Store(tmp_path)
    design, env = fixture(store, hours=4)
    policy = Policy(objective="methane", terminal_battery_value_kg_per_kwh=0.02).to_dict()
    expected = copy.deepcopy(policy)
    s = create(
        store,
        name="Isolated policy",
        partition_hours=2,
        cases=[
            dict(design_id=design, environment_id=env, controller="MPC · methane", policy=policy)
        ],
    )
    policy["terminal_battery_value_kg_per_kwh"] = 0.9
    assert s["schema_version"] == "site-yield-study/2"
    assert s["cases"][0]["policy"] == expected
    execute(store, s["id"])
    parts = entries(store, s["id"], "case-001")
    assert len(parts) == 2
    for item in parts:
        saved = load_period(store, item["period_sha256"])
        assert saved["provenance"]["controller_policies"]["MPC · methane"] == expected
    with pytest.raises(ValueError, match="objective"):
        create(
            store,
            name="Mislabelled",
            cases=[
                dict(design_id=design, environment_id=env, controller="Greedy", policy=expected)
            ],
        )


def test_local_service_ablation_only_changes_process_objective():
    c = replace(
        service_fixture("successful-procedure"),
        recovery_policy=RecoveryPolicy(version="scheduled-load-tests/4"),
    )
    methane = local_policy("MPC · methane", c)
    greedy = local_policy("Greedy", c)
    assert changed_paths(methane, greedy) == ["objective"]
    assert methane["recovery"]["version"] == "scheduled-load-tests/1"
    assert Policy(**methane).service is None
    assert c.recovery_policy.version == "scheduled-load-tests/4"
