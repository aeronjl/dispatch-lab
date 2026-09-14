import copy
import json
from dataclasses import replace

import pytest

from methane.config import Config, Costs, Plant, Scenario
from methane.dispatch import plan
from methane.learning_lab.deployment import apply, register, validate
from methane.learning_lab.estimators import fit
from methane.learning_lab.fixtures import teaching_dataset
from methane.learning_lab.reserves import DEFAULTS, account, targets
from methane.physics import State
from methane.policy import Policy
from methane.simulation import run
from methane.siting.store import Store


def test_registered_inference_preserves_present_and_reports_missing_domain_timeout(tmp_path):
    store = Store(tmp_path)
    dataset = teaching_dataset(store)
    model = fit(store, dataset["id"])["model_id"]
    d = register(store, name="PV aid", model_id=model, mode="forecast-aid")
    d.pop("id")
    packet = json.loads(store.read_raw(dataset["observations_sha256"]))[0]["packet"]
    original = copy.deepcopy(packet["forecast"])
    candidate, trace = apply(d, packet, original)
    assert trace["status"] == "applied"
    assert candidate["pv_kw"][0] == original["pv_kw"][0]
    assert candidate["pv_kw"][1] != original["pv_kw"][1]
    assert packet["forecast"] == original
    d["budget_ms"] = 1e-12
    candidate, trace = apply(d, packet, original)
    assert candidate == original and trace["status"] == "fallback"
    d["model"]["weights"][0] = 1e99
    with pytest.raises(ValueError, match="identity"):
        validate(d)


def test_reserves_are_soft_saturating_preferences_and_not_physical_obligations(monkeypatch):
    monkeypatch.setenv("DISPATCH_BATCH_WORKER", "1")
    p = Plant(initial_soc=0, initial_co2_kg=0)
    state = State.initial(p)
    f = dict(
        pv_kw=[0.0, 0.0], ambient_c=[20.0, 20.0], deliveries_kg=[0.0, 0.0], reserve_policy=DEFAULTS
    )
    planned = plan(p, state, f, p.electrolyser_kw, Costs(), seconds=0.2)
    assert planned["actions"]
    assert all(a["methane_kg"] == 0 for a in planned["actions"])
    scored = account(p, state, f, planned["trajectory"])
    assert scored["preference_penalty"] > 0
    high = [{"state": {k: v + 1000 for k, v in scored["targets"].items()}}]
    assert account(p, state, f, high)["preference_penalty"] == 0
    assert (
        targets(p, replace(state, reactor_on=True), f, DEFAULTS)["h2_kg"][0]
        > targets(p, state, f, DEFAULTS)["h2_kg"][0]
    )


def test_real_simulation_records_policy_inputs_and_preserves_physics(tmp_path, monkeypatch):
    monkeypatch.setenv("DISPATCH_BATCH_WORKER", "1")
    store = Store(tmp_path)
    registered = register(store, name="Reserve hypothesis", mode="homeostatic")
    registered.pop("id")
    policy = Policy(version="dispatch-lab/policy/5", deployment=registered)
    result = run(
        Config(scenario=Scenario(hours=4, horizon_hours=6, solver_seconds=0.1)),
        strategies=["MPC · methane"],
        policies={"MPC · methane": policy.to_dict()},
    )
    rows = result["records"]["MPC · methane"]
    assert len(rows) == 4
    for r in rows:
        trace = r["decision"]["experimental_policy"]
        assert trace["status"] == "applied"
        assert trace["reserve_accounting"] is not None
        assert all(a["passed"] for a in r["audits"])
        assert "truth" not in trace["input"]
        assert trace["input"]["forecast"]["pv_kw"][0] == r["decision"]["forecast"]["pv_kw"][0]
    with pytest.raises(ValueError, match="requires an MPC|requires.*MPC|requires.*objective"):
        Policy(version="dispatch-lab/policy/5", deployment=registered, objective="greedy")


def test_old_policy_serialization_stays_unchanged():
    assert Policy().to_dict() == dict(
        objective="methane", terminal_battery_value_kg_per_kwh=0.0, version="dispatch-lab/policy/1"
    )
