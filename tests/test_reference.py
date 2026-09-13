import ast
import copy
from pathlib import Path

import pytest

from methane.config import Config, Scenario
from methane.reference import audit, economics, interval
from methane.simulation import run


def test_reference_has_no_production_dependencies():
    tree = ast.parse(Path("methane/reference.py").read_text())
    imports = [n.module for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)]
    imports += [a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names]
    assert not any(
        name and name.startswith(("methane", "plant", "economics", "scipy", "numpy"))
        for name in imports
    )


def test_reference_hand_calculated_chemistry_and_zero_loss():
    from dataclasses import asdict, replace

    from methane.config import Plant

    p = asdict(replace(Plant(), heat_loss_kw_per_k=0, roundtrip_efficiency=1))
    before = dict(
        battery_kwh=100,
        h2_kg=10,
        co2_kg=100,
        temperature_c=300,
        electrolyser_on=True,
        reactor_on=True,
        commitment_hours=2,
    )
    action = dict(
        electrolyser_kw=220, charge_kw=10, discharge_kw=0, heater_kw=0, cooling_kw=0, methane_kg=4
    )
    r = interval(p, before, action, 300, 20, 0)
    assert r["state"]["h2_kg"] == 12
    assert r["state"]["co2_kg"] == 89
    assert r["state"]["battery_kwh"] == 110
    assert r["water_produced_kg"] == 9
    assert r["electrolysis_stoichiometric_water_kg"] == 36
    assert r["reaction_heat_kwh"] == pytest.approx(11.4583333333333)
    assert r["state"]["temperature_c"] == pytest.approx(338.194444444444)
    assert r["curtailed_kwh"] == 64


@pytest.fixture(scope="module")
def example():
    return run(Config(scenario=Scenario(hours=18, horizon_hours=6)), strategies=["Greedy"])


def test_reference_archive_and_zero_output_economics(example):
    report = audit(example)
    assert report["passed"], [c for c in report["checks"] if not c["passed"]]
    assert (
        economics(example["config"]["plant"], example["config"]["costs"], [])["eur_per_kg_ch4"]
        is None
    )


@pytest.mark.parametrize("kind", ["state", "heat", "cost", "input", "start", "forecast", "missing"])
def test_reference_catches_corruption_without_trusting_residuals(example, kind):
    result = copy.deepcopy(example)
    row = result["records"]["Greedy"][12]
    if kind == "state":
        row["state"]["h2_kg"] += 1
    if kind == "heat":
        row["reaction_heat_kwh"] *= -1
    if kind == "cost":
        result["metrics"]["Greedy"]["components"]["battery"] += 100
    if kind == "input":
        row["pv_kw"] += 10
    if kind == "start":
        row["electrolyser_start"] = 1 - row["electrolyser_start"]
    if kind == "forecast":
        row["decision"]["forecast"]["source"]["available_at"] = "2099-01-01T00:00:00Z"
    if kind == "missing":
        result["records"]["Greedy"].pop()
    assert not audit(result)["passed"]


def test_reference_works_when_production_transition_and_costs_are_broken(example, monkeypatch):
    import methane.costing
    import methane.physics

    def broken(*args, **kwargs):
        raise RuntimeError("Production code must not be called")

    monkeypatch.setattr(methane.physics, "transition", broken)
    monkeypatch.setattr(methane.costing, "allocation", broken)
    assert audit(example)["passed"]
