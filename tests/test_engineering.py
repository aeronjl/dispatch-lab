"""Independent references and explicit contract/trace verification."""

import copy
import itertools
import json
import math
from dataclasses import replace
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.integrate import solve_ivp

from methane.audit import PhysicalAuditError
from methane.config import Config, Plant, Scenario
from methane.physics import State, transition
from methane.provenance import digest, experiment_identity, manifest, seal, verify
from methane.reactor import ThermalInput, operating_transition, step
from methane.simulation import run
from methane.solar import default_design, interval
from methane.weather import synthetic


def test_pre_refactor_physical_fixture():
    fixture = json.loads((Path(__file__).parent / "fixtures/engineering-baseline.json").read_text())
    c = Config.from_dict(fixture["config"])
    state = State.initial(c.plant, fixture["rows"][0]["ambient_c"])
    for row in fixture["rows"]:
        state, actual = transition(
            c.plant, state, row["applied"], row["pv_kw"], row["ambient_c"], row["co2_delivered_kg"]
        )
        assert vars(state) == pytest.approx(row["state"], abs=1e-8)
        for key in ("heat_loss_kwh", "reaction_heat_kwh", "water_produced_kg"):
            assert actual[key] == pytest.approx(row[key], abs=1e-8)
    weather = synthetic(c)
    for t, expected in zip(weather["times"], fixture["solar"], strict=True):
        actual = interval(
            default_design(c.plant, c.weather), weather["truth"][t], t, c.plant, c.weather
        )
        assert actual["output_kw"] == pytest.approx(expected["output_kw"], abs=1e-8)


@settings(max_examples=100, deadline=None)
@given(
    temp=st.floats(-20, 400),
    ambient=st.floats(-20, 40),
    heat=st.floats(0, 60),
    methane=st.floats(0, 10),
    cooling=st.floats(0, 40),
    duration=st.floats(0.01, 2),
)
def test_thermal_independent_ode_and_substeps(temp, ambient, heat, methane, cooling, duration):
    p = Plant()
    whole = step(p, ThermalInput(temp, ambient, heat, methane, cooling, duration))
    heat_rate = heat + methane / duration * (165 / 16 / 3.6) - cooling
    numerical = solve_ivp(
        lambda _, y: [(heat_rate - 0.08 * (y[0] - ambient)) / 0.3],
        [0, duration],
        [temp],
        rtol=1e-10,
        atol=1e-10,
    )
    assert whole.state.temperature_c == pytest.approx(numerical.y[0, -1], abs=1e-6)
    first = step(p, ThermalInput(temp, ambient, heat, methane / 2, cooling, duration / 2))
    second = step(
        p,
        ThermalInput(first.state.temperature_c, ambient, heat, methane / 2, cooling, duration / 2),
    )
    assert whole.state.temperature_c == pytest.approx(second.state.temperature_c, abs=1e-8)


def test_zero_heat_loss_and_known_cooling():
    assert step(
        replace(Plant(), heat_loss_kw_per_k=0), ThermalInput(20, 20, 30, duration_hours=2)
    ).state.temperature_c == pytest.approx(220)
    assert step(Plant(), ThermalInput(300, 20)).state.temperature_c == pytest.approx(
        20 + 280 * math.exp(-0.08 / 0.3)
    )


def test_reactor_abstract_transition_conformance():
    for minimum in range(1, 5):
        for was_running, requested, heat, hot, begin, end, supply, failed in itertools.product(
            (False, True), repeat=8
        ):
            for remaining in range(minimum):
                if remaining and not was_running:
                    continue
                active = (requested or remaining > 0) and begin and end and supply and not failed
                mode, after, start, trip = operating_transition(
                    was_running, remaining, active, requested, heat, hot, minimum
                )
                assert 0 <= after < minimum
                assert (mode == "running") == active
                assert not active or begin and end and supply and not failed
                assert not start or after == minimum - 1 and not was_running
                assert active or after == 0
                assert not (remaining or requested) or active or trip and mode == "forced-trip"
                if active and was_running:
                    assert after == max(0, remaining - 1)


def test_audits_survive_invalid_actions():
    p = Plant()
    action = {
        "electrolyser_kw": 0,
        "charge_kw": 0,
        "discharge_kw": 10000,
        "heater_kw": 0,
        "cooling_kw": 0,
        "methane_kg": 0,
    }
    with pytest.raises(PhysicalAuditError) as error:
        transition(p, State.initial(p), action, 0, 20, 0)
    assert any(a["check_id"] == "battery_bounds" and not a["passed"] for a in error.value.audits)


def test_integrity_input_identity_and_legacy_policy():
    c = Config(scenario=Scenario(hours=2, horizon_hours=6))
    r = run(c, strategies=["Greedy"])
    assert verify(r) is r
    changed = copy.deepcopy(r)
    changed["records"]["Greedy"][0]["pv_kw"] += 1
    with pytest.raises(ValueError, match="integrity"):
        verify(changed)
    weather = synthetic(c)
    one = experiment_identity(manifest(c, weather, ["Greedy"]))
    weather["truth"][weather["times"][0]]["pv_kw"] += 1
    assert one != experiment_identity(manifest(c, weather, ["Greedy"]))
    assert Config.from_dict({}).rng_policy == "legacy/1"
    assert Config.from_dict(c.to_dict()).rng_policy == "named-channels/1"
    assert digest(r) != digest(seal(changed))


def test_independent_archive_audit_rejects_resealed_corruption():
    from methane.engineering import audit_archive

    r = run(Config(scenario=Scenario(hours=3, horizon_hours=6)), strategies=["Greedy"])
    assert audit_archive(r)["passed"]
    r["records"]["Greedy"][0]["state"]["h2_kg"] += 1
    seal(r)
    assert not audit_archive(r)["passed"]


def test_invalid_trace_preserves_prefix(monkeypatch):
    import methane.simulation as simulation
    from methane.audit import check

    original = simulation.execute
    count = 0

    def faulty(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise PhysicalAuditError(
                [check("injected", "reactor", 1, "kg")], {"example": float("nan")}
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(simulation, "execute", faulty)
    r = simulation.run(Config(scenario=Scenario(hours=3, horizon_hours=6)), strategies=["Greedy"])
    assert r["status"] == "invalid"
    assert len(r["records"]["Greedy"]) == 1
    assert r["failures"]["Greedy"]["hour"] == 1
    verify(r)
    assert r["failures"]["Greedy"]["context"]["example"] == {"nonfinite": "nan"}


@settings(max_examples=15, deadline=None)
@given(inputs=st.lists(st.tuples(st.floats(0, 1000), st.floats(0, 450)), min_size=2, max_size=12))
def test_generated_operating_sequences(inputs):
    from methane.dispatch import execute

    c = Config()
    state = State.initial(c.plant)
    for pv, power in inputs:
        requested = dict(
            electrolyser_kw=power,
            charge_kw=0,
            discharge_kw=0,
            heater_kw=60,
            cooling_kw=0,
            methane_kg=0,
        )
        state, row = execute(c.plant, state, requested, pv, 20, 0, 450, c.costs)
        assert all(a["passed"] for a in row["audits"])


def test_solver_outcomes_and_invalid_incumbent(monkeypatch):
    from types import SimpleNamespace

    import numpy as np

    import methane.dispatch as dispatch

    m = dispatch.Model(1)
    for status, label in ((2, "infeasible"), (3, "unbounded"), (4, "solver-error")):
        monkeypatch.setattr(
            dispatch,
            "milp",
            lambda *args, status=status, label=label, **kw: SimpleNamespace(
                status=status, x=None, message=label
            ),
        )
        _, info = m.solve(0.1)
        assert info["status"] == label
    monkeypatch.setattr(
        dispatch,
        "milp",
        lambda *args, **kw: SimpleNamespace(
            status=0, x=np.full(len(m.lower), np.nan), message="invalid"
        ),
    )
    assert m.solve(0.1)[1]["status"] == "invalid-incumbent"


def test_preview_transport_isolated_and_scoped():
    from fastapi import HTTPException

    from methane.preview_service import PreviewRequest, calculate, register

    r = run(Config(scenario=Scenario(hours=3, horizon_hours=6)), strategies=["Greedy"])
    source = copy.deepcopy(r)
    token = register(r)
    design = default_design(Config().plant, Config().weather)
    response = calculate(PreviewRequest(token=token, run_id=r["run_id"], key="one", design=design))
    response["frames"][0]["output_kw"] = 123
    assert (
        calculate(PreviewRequest(token=token, run_id=r["run_id"], key="two", design=design))[
            "frames"
        ][0]["output_kw"]
        != 123
    )
    assert r == source
    with pytest.raises(HTTPException):
        calculate(PreviewRequest(token=token, run_id="different-run", key="three", design=design))


def test_archive_audit_reports_impossible_action():
    from methane.engineering import audit_archive

    r = run(Config(scenario=Scenario(hours=2, horizon_hours=6)), strategies=["Greedy"])
    r["records"]["Greedy"][0]["applied"]["discharge_kw"] = 10000
    seal(r)
    assert not audit_archive(r)["passed"]


def test_nonfinite_transition_input_is_auditable():
    from methane.physics import ACTION_KEYS

    action = dict.fromkeys(ACTION_KEYS, 0.0)
    with pytest.raises(PhysicalAuditError) as error:
        transition(Plant(), State.initial(Plant()), action, float("nan"), 20, 0)
    assert error.value.audits[0]["check_id"] == "finite_input_pv_kw"
    json.dumps(error.value.context, allow_nan=False)


def test_complete_archive_cannot_omit_intervals():
    from methane.engineering import audit_archive

    r = run(Config(scenario=Scenario(hours=2, horizon_hours=6)), strategies=["Greedy"])
    r["records"]["Greedy"].pop()
    seal(r)
    assert not audit_archive(r)["passed"]


def test_invalid_physical_candidate_enters_feasible_fallback(monkeypatch):
    import methane.dispatch as dispatch
    from methane.audit import check

    c = Config()
    state = State.initial(c.plant)
    forecast = {"pv_kw": [400.0], "ambient_c": [20.0], "deliveries_kg": [0.0]}
    original = dispatch.trajectory
    count = 0

    def rejected_once(*args, **kwargs):
        nonlocal count
        count += 1
        if count == 1:
            raise PhysicalAuditError(
                [check("production_temperature_begin", "reactor", 0.00014, "°C")], {}
            )
        return original(*args, **kwargs)

    monkeypatch.setattr(dispatch, "trajectory", rejected_once)
    result = dispatch.plan(c.plant, state, forecast, 450, c.costs)
    assert result["solver"]["fallback_used"]
    assert result["solver"]["reason"] == "invalid-trajectory"
    assert result["solver"]["audits"][0]["residual"] == 0.00014
    assert result["actions"]
    original(c.plant, state, result["actions"], forecast)


def test_invalid_greedy_candidate_returns_explicit_safe_off(monkeypatch):
    import methane.dispatch as dispatch
    from methane.audit import check

    def rejected(*args, **kwargs):
        raise PhysicalAuditError([check("injected", "reactor", 1, "kg")], {})

    monkeypatch.setattr(dispatch, "transition", rejected)
    c = Config()
    action, solver = dispatch.greedy_action(c.plant, State.initial(c.plant), 400, 20, 0, 450)
    assert solver["status"] == "safe-off"
    assert not any(action.values())


def test_preview_http_serialization_retains_operands_and_generation():
    import json

    from methane.preview_service import PreviewRequest, calculate, register, response
    from methane.solar import design_for

    c = Config()
    result = dict(run_id="serialization-fixture", config=c.to_dict(), weather=synthetic(c))
    request = PreviewRequest(
        token=register(result),
        run_id=result["run_id"],
        key="generation-2",
        design=design_for(result),
    )
    expected = calculate(request)
    http = response(request)
    assert json.loads(http.body) == expected
    assert http.media_type == "application/json"
    assert "preview;dur=" in http.headers["server-timing"]
    assert "serialize;dur=" in http.headers["server-timing"]
