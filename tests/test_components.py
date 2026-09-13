"""Independent planning consumers and hand-calculated component reference cases."""

import copy
from dataclasses import replace
from decimal import Decimal

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.optimize import Bounds, LinearConstraint, milp

from methane import electrolyser as ely
from methane import reactor
from methane import storage as gas
from methane.audit import PhysicalAuditError
from methane.components import assemble
from methane.config import Config, Models, Plant, Scenario
from methane.dispatch import Model
from methane.ports import PlanningBlock, Port
from methane.reference import audit
from methane.simulation import run, what_if


def solve_fragment(block, n, fixed, objective=None):
    """Translate portable rows directly to SciPy without the production Model adapter."""
    ids = {(key, t): i * n + t for i, (key, *_) in enumerate(block.bounds) for t in range(n)}
    lo = np.array([v for _, v, _, _ in block.bounds for t in range(n)], dtype=float)
    hi = np.array([v for _, _, v, _ in block.bounds for t in range(n)], dtype=float)
    integer = [int(v) for _, _, _, v in block.bounds for t in range(n)]
    for key, value in fixed.items():
        lo[ids[key]] = hi[ids[key]] = value
    matrix = np.zeros((len(block.rows), len(ids)))
    for i, row in enumerate(block.rows):
        for key, t, value in row.terms:
            matrix[i, ids[key, t]] += value
    obj = np.zeros(len(ids))
    for key, value in (objective or {}).items():
        obj[ids[key]] = value
    solved = milp(
        obj,
        integrality=integer,
        bounds=Bounds(lo, hi),
        constraints=LinearConstraint(
            matrix, [r.lower for r in block.rows], [r.upper for r in block.rows]
        ),
    )
    return solved, ids


@pytest.mark.parametrize("implementation", ely.IMPLEMENTATIONS)
def test_electrolyser_independent_conversion_and_start(implementation):
    component = ely.Electrolyser(ely.Parameters(500, 0.2, 50, 30), implementation)
    initial = ely.State(False)
    block = component.planning(initial, 300, (0.5, 0.5, 1))
    solved, ids = solve_fragment(block, 3, {("power", 0): 200, ("power", 1): 200, ("power", 2): 0})
    assert solved.success
    for t, dt in enumerate((0.5, 0.5, 1)):
        result = component.step(initial, ely.Inputs(solved.x[ids["power", t]], 300, dt))
        expected_h2 = (2, 2, 0)[t]
        expected_bus = (260, 200, 0)[t]
        assert dict(result.flows)["hydrogen_kg"] == pytest.approx(expected_h2)
        assert dict(result.flows)["water_kg"] == pytest.approx(expected_h2 * 9)
        assert dict(result.flows)["electricity_kw"] == pytest.approx(expected_bus)
        for key, field in (
            ("hydrogen", "hydrogen_kg"),
            ("electricity", "electricity_kw"),
            ("start", "start"),
        ):
            assert solved.x[ids[key, t]] == pytest.approx(dict(result.flows)[field])
        initial = result.state
    with pytest.raises(PhysicalAuditError):
        component.step(initial, ely.Inputs(99, 300))
    with pytest.raises(PhysicalAuditError):
        component.step(initial, ely.Inputs(301, 300))
    unavailable, _ = solve_fragment(component.planning(initial, 90, (1,)), 1, {("on", 0): 1})
    assert unavailable.status == 2


@settings(max_examples=40, deadline=None)
@given(st.integers(100, 400), st.integers(1, 8))
def test_electrolyser_decimal_reference(power, quarters):
    for impl in ely.IMPLEMENTATIONS:
        component = ely.Electrolyser(ely.Parameters(500, 0.2, 53, 37), impl)
        result = component.step(ely.State(), ely.Inputs(power, 500, quarters / 4))
        exact = Decimal(power) * Decimal(quarters) / 4 / Decimal(53)
        assert dict(result.flows)["hydrogen_kg"] == pytest.approx(float(exact), rel=1e-14)


@pytest.mark.parametrize("implementation", gas.IMPLEMENTATIONS)
@pytest.mark.parametrize("kind", ("hydrogen", "co2"))
def test_storage_planning_execution_and_delivery_order(implementation, kind):
    component = gas.Storage(gas.Parameters(100, kind), implementation)
    before = gas.State(90)
    block = component.planning(before, 2, (30, 20) if kind == "co2" else None)
    fixed = {("outflow", 0): 25, ("outflow", 1): 35}
    if kind == "hydrogen":
        fixed.update({("inflow", 0): 30, ("inflow", 1): 20})
    solved, ids = solve_fragment(block, 2, fixed)
    assert solved.success
    for t, inflow in enumerate((30, 20)):
        result = component.step(before, gas.Inputs(inflow, (25, 35)[t]))
        assert result.state.inventory_kg == pytest.approx(solved.x[ids["inventory", t]])
        # CO2 arrives before withdrawal. H2 flows concurrently without venting.
        assert result.state.inventory_kg == pytest.approx(
            ((75, 60) if kind == "co2" else (95, 80))[t]
        )
        assert dict(result.flows)["rejected_kg"] == pytest.approx(
            20 if kind == "co2" and t == 0 else 0
        )
        before = result.state
    with pytest.raises(PhysicalAuditError):
        component.step(gas.State(0), gas.Inputs(0, 1))
    if kind == "hydrogen":
        with pytest.raises(PhysicalAuditError):
            component.step(gas.State(100), gas.Inputs(1, 0))
        assert component.step(gas.State(0), gas.Inputs(5, 5)).state.inventory_kg == 0


def test_reactor_fragment_heat_gases_and_commitment():
    component = reactor.Reactor(reactor.Parameters(heat_loss_kw_per_k=0))
    before = reactor.ReactorState(250)
    block = component.planning(before, (20, 20), (1, 1))
    fixed = {
        (key, t): v for t in range(2) for key, v in [("methane", 3), ("heater", 0), ("cooling", 0)]
    }
    solved, ids = solve_fragment(block, 2, fixed)
    assert solved.success
    for t in range(2):
        result = component.execute(
            before, reactor.ThermalInput(before.temperature_c, 20, methane_kg=3)
        )
        # 3 kg * 165 MJ/kmol /16 kg/kmol /3.6 MJ/kWh = 8.59375 kWh.
        assert dict(result.flows)["reaction_heat_kwh"] == pytest.approx(8.59375)
        assert result.state.temperature_c == pytest.approx(250 + (t + 1) * 8.59375 / 0.3)
        assert result.state.temperature_c == pytest.approx(solved.x[ids["temperature", t]])
        assert dict(result.flows)["hydrogen_kg"] == 1.5
        assert dict(result.flows)["co2_kg"] == 8.25
        assert dict(result.flows)["electricity_kw"] == 5
        assert result.state.commitment_hours == 3 - t
        before = result.state
    trip = component.execute(before, reactor.ThermalInput(before.temperature_c, 20))
    assert dict(trip.flows)["forced_trip"] == 1
    assert trip.state.commitment_hours == 0
    cold, _ = solve_fragment(
        component.planning(reactor.ReactorState(20), (20,), (1,)), 1, {("methane", 0): 3}
    )
    assert cold.status == 2
    committed = component.planning(before, (20,), (1,))
    off, _ = solve_fragment(committed, 1, {("on", 0): 0})
    assert off.status == 2
    with pytest.raises(ValueError):
        reactor.Parameters(minimum_run_hours=1.5)
    with pytest.raises(ValueError):
        component.execute(before, reactor.ThermalInput(20, 20))


def test_unit_mismatch_and_unknown_implementation_fail_closed():
    m = Model(1)
    with pytest.raises(ValueError, match="unit mismatch"):
        m.add_component(
            PlanningBlock((("x", 0, 1, False),), (), (Port("x", "kg", "Mass"),)), {"x": "charge_kw"}
        )
    for key in ("battery", "electrolyser", "hydrogen", "co2", "reactor"):
        with pytest.raises(ValueError):
            Models(**{key: "unavailable/99"})


@pytest.mark.parametrize("alternative", (False, True))
def test_whole_plant_swap_records_and_what_if(alternative):
    models = (
        Models(electrolyser="yield-ledger/1", hydrogen="ledger/1", co2="ledger/1")
        if alternative
        else Models()
    )
    config = Config(
        models=models,
        plant=replace(Plant(), initial_soc=0.5),
        scenario=Scenario(hours=3, horizon_hours=6),
    )
    result = run(config)
    assert result["status"] == "complete"
    report = audit(result)
    assert report["passed"], report
    for rows in result["records"].values():
        for row in rows:
            for key in ("electrolyser", "hydrogen", "co2", "reactor"):
                record = row["component_records"][key]
                assert record["implementation_id"] == getattr(models, key)
                assert (
                    row["decision"]["component_implementations"][key]
                    == assemble(config.plant, models).identities()[key]
                )
                assert all(a["passed"] for a in record["audits"])
    original = copy.deepcopy(result)
    alt = what_if(result, "MPC · methane", 1, "electrolyser")
    assert alt["alternative_plan"]["actions"][0]["electrolyser_kw"] == pytest.approx(0)
    for row in alt["alternative_plan"]["trajectory"]:
        assert row["component_records"]["electrolyser"]["implementation_id"] == models.electrolyser
    assert result == original


def test_component_parameter_ranges_match_generated_metadata():
    from methane.contracts import ELECTROLYSER, HYDROGEN

    for parameter in ELECTROLYSER.parameters:
        with pytest.raises(ValueError):
            ely.Parameters(**{parameter.key: parameter.upper + 1})
    with pytest.raises(ValueError):
        gas.Parameters(HYDROGEN.parameters[0].upper + 1)
