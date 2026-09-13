"""Battery checks against hand arithmetic, Decimal and independently assembled solves."""

import copy
from dataclasses import asdict, replace
from decimal import Decimal, localcontext

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.optimize import Bounds, LinearConstraint, milp

from methane.audit import PhysicalAuditError
from methane.battery import (
    IMPLEMENTATIONS,
    Battery,
    BatteryInput,
    BatteryParameters,
    BatteryState,
    from_plant,
)
from methane.battery_trace import trace
from methane.config import Config, Models, Plant, Scenario
from methane.engineering import audit_archive
from methane.provenance import seal, verify
from methane.simulation import run, what_if


@pytest.mark.parametrize("kernel", IMPLEMENTATIONS.values(), ids=IMPLEMENTATIONS)
def test_known_energy_ledger(kernel):
    battery = Battery(BatteryParameters(200, 1, 0.64), kernel)
    first = battery.step(BatteryState(20), BatteryInput(100, 0, 0.5))
    assert first.state.energy_kwh == pytest.approx(60)
    assert dict(first.flows)["loss_kwh"] == pytest.approx(10)
    second = battery.step(first.state, BatteryInput(0, 64, 0.5))
    assert second.state.energy_kwh == pytest.approx(20)
    assert dict(second.flows)["loss_kwh"] == pytest.approx(8)
    assert all(a["passed"] for a in (*first.audits, *second.audits))


@settings(max_examples=150, deadline=None)
@given(
    energy=st.floats(0, 800),
    request=st.floats(0, 400),
    duration=st.floats(0.01, 4),
    efficiency=st.floats(0.2, 1),
    charging=st.booleans(),
)
def test_decimal_reference_and_subdivision(energy, request, duration, efficiency, charging):
    with localcontext() as context:
        context.prec = 45
        e, dt, eta = Decimal(str(energy)), Decimal(str(duration)), Decimal(str(efficiency)).sqrt()
        power = min(
            Decimal(str(request)), (Decimal(800) - e) / eta / dt if charging else e * eta / dt
        )
        incoming, outgoing = (power * dt, Decimal(0)) if charging else (Decimal(0), power * dt)
        end = e + incoming * eta - outgoing / eta
        loss = incoming * (1 - eta) + outgoing * (1 / eta - 1)
    inputs = BatteryInput(
        float(power) if charging else 0, 0 if charging else float(power), duration
    )
    for kernel in IMPLEMENTATIONS.values():
        battery = Battery(BatteryParameters(800, 0.5, efficiency), kernel)
        whole = battery.step(BatteryState(energy), inputs)
        assert whole.state.energy_kwh == pytest.approx(float(end), abs=1e-8)
        assert dict(whole.flows)["loss_kwh"] == pytest.approx(float(loss), abs=1e-8)
        half = replace(inputs, duration_hours=duration / 2)
        first = battery.step(BatteryState(energy), half)
        second = battery.step(first.state, half)
        assert whole.state.energy_kwh == pytest.approx(second.state.energy_kwh, abs=1e-8)
        assert dict(whole.flows)["loss_kwh"] == pytest.approx(
            dict(first.flows)["loss_kwh"] + dict(second.flows)["loss_kwh"], abs=1e-8
        )


@pytest.mark.parametrize("kernel", IMPLEMENTATIONS.values(), ids=IMPLEMENTATIONS)
def test_boundaries_and_invalid_actions(kernel):
    battery = Battery(BatteryParameters(100, 1, 1), kernel)
    assert battery.step(BatteryState(0), BatteryInput(100)).state.energy_kwh == 100
    assert battery.step(BatteryState(100), BatteryInput(0, 100)).state.energy_kwh == 0
    assert (
        Battery(BatteryParameters(0, 1, 1), kernel)
        .step(BatteryState(0), BatteryInput())
        .state.energy_kwh
        == 0
    )
    for state, inputs in (
        (0, BatteryInput(0, 1)),
        (100, BatteryInput(1)),
        (50, BatteryInput(1, 1)),
        (0, BatteryInput(-1)),
        (0, BatteryInput(101)),
        (101, BatteryInput()),
        (0, BatteryInput(float("nan"))),
        (float("inf"), BatteryInput()),
    ):
        with pytest.raises(PhysicalAuditError):
            battery.step(BatteryState(state), inputs)
    for duration in (0, -1):
        with pytest.raises(ValueError):
            battery.step(BatteryState(0), BatteryInput(duration_hours=duration))
    with pytest.raises(ValueError):
        battery.planning(BatteryState(0), ())


def solve_block(battery, initial, durations, overrides, objective):
    """Independent consumer of the portable planning contract; no plant/dispatch model."""
    block = battery.planning(BatteryState(initial), durations)
    ids = {
        (name, t): i * len(durations) + t
        for i, (name, *_) in enumerate(block.bounds)
        for t in range(len(durations))
    }
    lower, upper, integer = [], [], []
    for _, lo, hi, binary in block.bounds:
        lower.extend([lo] * len(durations))
        upper.extend([hi] * len(durations))
        integer.extend([int(binary)] * len(durations))
    for port, (lo, hi) in overrides.items():
        lower[ids[port]], upper[ids[port]] = lo, hi
    matrix = np.zeros((len(block.rows), len(ids)))
    for i, row in enumerate(block.rows):
        for name, t, coefficient in row.terms:
            matrix[i, ids[name, t]] += coefficient
    obj = np.zeros(len(ids))
    for key, value in objective.items():
        obj[ids[key]] = value
    result = milp(
        obj,
        integrality=integer,
        bounds=Bounds(lower, upper),
        constraints=LinearConstraint(
            matrix, [r.lower for r in block.rows], [r.upper for r in block.rows]
        ),
    )
    return result, ids


@pytest.mark.parametrize("kernel", IMPLEMENTATIONS.values(), ids=IMPLEMENTATIONS)
def test_standalone_planning_and_replay(kernel):
    battery = Battery(BatteryParameters(200, 1, 0.64), kernel)
    result, ids = solve_block(
        battery,
        0,
        (0.5, 0.5),
        {("charge", 0): (0, 100), ("discharge", 0): (0, 0), ("charge", 1): (0, 0)},
        {("discharge", 1): -1},
    )
    assert result.success
    # 50 kWh input × 64% = 32 kWh output = 64 kW for half an hour.
    assert result.x[ids["discharge", 1]] == pytest.approx(64)
    assert result.x[ids["energy", 0]] == pytest.approx(40)
    state = BatteryState(0)
    for t in range(2):
        applied = battery.step(
            state, BatteryInput(result.x[ids["charge", t]], result.x[ids["discharge", t]], 0.5)
        )
        assert applied.state.energy_kwh == pytest.approx(result.x[ids["energy", t]], abs=1e-8)
        state = applied.state
    infeasible, _ = solve_block(
        battery, 50, (1,), {("charge", 0): (1, 1), ("discharge", 0): (1, 1)}, {}
    )
    assert infeasible.status == 2


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_swap_in_whole_plant_and_what_if(implementation):
    config = Config(
        models=Models(implementation),
        plant=replace(Plant(), initial_soc=0.5),
        scenario=Scenario(hours=3, horizon_hours=6),
    )
    result = run(config)
    assert result["status"] == "complete"
    assert audit_archive(result)["passed"]
    assert result["provenance"]["implementations"]["battery"]["implementation_id"] == implementation
    for rows in result["records"].values():
        for row in rows:
            assert row["battery_record"]["implementation_id"] == implementation
            assert (
                row["decision"]["component_implementations"]["battery"]["implementation_id"]
                == implementation
            )
            assert all(a["passed"] for a in row["battery_record"]["audits"])
    before = copy.deepcopy(result)
    alternative = what_if(result, "MPC · methane", 1, "battery")
    assert alternative["alternative_plan"]["actions"][0]["discharge_kw"] == pytest.approx(
        0, abs=1e-8
    )
    assert all(
        r["battery_record"]["implementation_id"] == implementation
        for r in alternative["alternative_plan"]["trajectory"]
    )
    assert result == before


def test_recorded_lineage_and_resealed_corruption():
    from methane.costing import reprice
    from methane.ui import playback_value

    result = run(
        Config(
            plant=replace(Plant(), initial_soc=0.5), scenario=Scenario(hours=2, horizon_hours=6)
        ),
        strategies=["Greedy"],
    )
    original = copy.deepcopy(result)
    lineage = trace(result, "Greedy", 1)
    nodes = {n["id"]: n for n in lineage["nodes"]}
    assert nodes["end"]["value"] == result["records"]["Greedy"][1]["state"]["battery_kwh"]
    assert nodes["begin"]["value"] == result["records"]["Greedy"][0]["state"]["battery_kwh"]
    assert nodes["display_soc"]["value"] == pytest.approx(nodes["end"]["value"] / 8)
    assert (
        lineage["implementation_file_sha256"]
        == result["provenance"]["source"]["files"]["methane/battery.py"]
    )
    assert all(set(n["parents"]) <= nodes.keys() for n in nodes.values())
    view = playback_value(result)
    assert "battery_record" not in view["records"]["Greedy"][1]
    assert view["frames"]["Greedy"][2]["battery_kwh"] == nodes["end"]["value"]
    reprice(result)
    assert result == original
    lineage["audits"][0]["passed"] = False
    assert result == original
    result["records"]["Greedy"][1]["battery_record"]["inputs"]["charge_kw"] += 1
    verify(seal(result))
    assert not audit_archive(result)["passed"]


def test_legacy_config_and_trace_are_not_upgraded():
    from pathlib import Path

    from methane.evidence import load

    result = load(Path(__file__).parent / "fixtures/browser-demo-v2.json.gz")
    before = copy.deepcopy(result)
    assert Config.from_dict(result["config"]).models.battery == "affine/1"
    assert trace(result, "Greedy", 0)["status"] == "unavailable"
    assert result == before
    with pytest.raises(ValueError, match="Unknown battery"):
        Config(models=Models("missing/99"))


def test_invalid_replacement_fails_loudly():
    from methane.contracts import ComponentResult

    class Broken:
        implementation_id = "broken/1"

        def execute(self, p, state, inputs):
            return ComponentResult(BatteryState(state.energy_kwh + 1), (("loss_kwh", 0),))

    with pytest.raises(PhysicalAuditError):
        Battery(BatteryParameters(), Broken()).step(BatteryState(0), BatteryInput())


def test_parameter_contract_is_immutable():
    from dataclasses import FrozenInstanceError

    battery = from_plant(Plant())
    with pytest.raises(FrozenInstanceError):
        battery.parameters.capacity_kwh = 900
    assert asdict(battery.parameters)["capacity_kwh"] == 800
    for efficiency in (0, 1.1, float("nan")):
        with pytest.raises(ValueError):
            BatteryParameters(roundtrip_efficiency=efficiency)


@pytest.mark.parametrize("implementation", IMPLEMENTATIONS)
def test_fallback_preserves_selected_battery(implementation, monkeypatch):
    import methane.dispatch as dispatch
    from methane.physics import State

    c = Config()
    battery = from_plant(c.plant, implementation)
    monkeypatch.setattr(
        dispatch,
        "solve",
        lambda *a, **kw: (None, {"status": "time-limited", "valid_incumbent": False}),
    )
    forecast = {"pv_kw": [500.0], "ambient_c": [20.0], "deliveries_kg": [0.0]}
    result = dispatch.plan(c.plant, State.initial(c.plant), forecast, 450, c.costs, battery=battery)
    assert result["solver"]["fallback_used"]
    assert result["trajectory"][0]["battery_record"]["implementation_id"] == implementation
    state, row = dispatch.execute(
        c.plant,
        State.initial(c.plant),
        result["actions"][0],
        500,
        20,
        0,
        450,
        c.costs,
        battery=battery,
    )
    assert row["execution_solver"]["fallback_used"]
    assert row["battery_record"]["implementation_id"] == implementation
    assert state.battery_kwh == 0
