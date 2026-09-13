from dataclasses import replace

import pytest

from methane.battery import IMPLEMENTATIONS, from_plant
from methane.config import Costs, Plant
from methane.dispatch import prepare_model, solve
from methane.physics import State
from methane.solver_study import equivalence, feasibility


def test_frozen_problem_retains_infinity_and_detects_changed_operands():
    import copy
    import json

    from methane.solver_study import freeze_problem, thaw_problem

    p, state, forecast = fixture()
    model = prepare_model(p, state, forecast, 0, Costs())
    frozen = freeze_problem(model, {"kind": "independent two-interval example"})
    restored = thaw_problem(json.loads(json.dumps(frozen, allow_nan=False)))
    assert equivalence([model, restored])["equivalent_within_tolerance"]
    broken = copy.deepcopy(frozen)
    broken["problem"]["objective"][0] += 1
    with pytest.raises(ValueError, match="identity mismatch"):
        thaw_problem(broken)


def test_frozen_solve_reconciles_independently_bounded_optimum(tmp_path):
    import json
    import subprocess
    import sys

    from methane.solver_study import freeze_problem

    p, state, forecast = fixture()
    model = prepare_model(p, state, forecast, 0, Costs())
    # The production application can already have a differently sized native
    # thread scheduler. Exercise the declared fresh-worker interface, not an
    # in-process thread-setting change during the rest of the test suite.
    problem = tmp_path / "problem.json"
    output = tmp_path / "result.json"
    problem.write_text(json.dumps(freeze_problem(model, {"kind": "test"})))
    subprocess.run(
        [
            sys.executable,
            "-m",
            "methane.solver_study",
            "--frozen-worker",
            str(problem),
            "--worker-output",
            str(output),
            "--budget-json",
            '{"time_limit_seconds": 2}',
        ],
        check=True,
        capture_output=True,
        timeout=15,
    )
    result = json.loads(output.read_text())
    assert result["accepted_incumbent"] and result["linear_feasibility"]["passed"]
    assert result["actions"][0]["methane_kg"] == pytest.approx(0)
    assert result["actions"][1]["methane_kg"] == pytest.approx(10)
    assert result["objective_value"] - result["objective_bound"] < 1e-6
    assert result["options"]["threads"] == 1
    assert result["environment"]["highs"] != "unavailable"


@pytest.mark.parametrize(
    "budget",
    [
        {"time_limit_seconds": True},
        {"time_limit_seconds": float("nan")},
        {"time_limit_seconds": 0},
        {"time_limit_seconds": 1, "node_limit": True},
        {"time_limit_seconds": 1, "node_limit": -1},
        {"time_limit_seconds": 1, "node_limit": 1.5},
        {"time_limit_seconds": 1, "relative_gap": float("inf")},
        {"time_limit_seconds": 1, "unknown": 1},
    ],
)
def test_computation_budget_rejects_invalid_inputs(budget):
    from methane.solver_study import work_budget

    with pytest.raises(ValueError):
        work_budget(budget)


def test_iteration_limit_is_not_misreported_as_time_limit(monkeypatch):
    from types import SimpleNamespace

    from methane import solver_study

    p, state, forecast = fixture()
    model = prepare_model(p, state, forecast, 0, Costs())
    x, _ = model.solve(2)
    monkeypatch.setattr(
        solver_study,
        "milp",
        lambda *a, **k: SimpleNamespace(
            status=1,
            message="Iteration limit reached. (HiGHS Status 16)",
            x=x,
            fun=float(model.objective @ x),
            mip_node_count=10,
        ),
    )
    result = solver_study.solve_frozen(
        solver_study.freeze_problem(model, {}), {"time_limit_seconds": 2, "node_limit": 10}
    )
    assert result["termination"] == "iteration-limited"
    assert result["accepted_incumbent"]
    assert result["gap"] is None and result["objective_bound"] is None
    assert result["node_count"] == 10
    # A native status and finite vector do not establish feasibility.
    x[model.ids["methane_kg"][0]] = 100
    result = solver_study.solve_frozen(
        solver_study.freeze_problem(model, {}), {"time_limit_seconds": 2}
    )
    assert not result["accepted_incumbent"]
    assert not result["linear_feasibility"]["passed"]
    assert result["actions"] == []


def test_repeat_protocol_uses_isolated_processes_and_retains_all_trials(tmp_path):
    import hashlib
    import json

    from methane.solver_study import freeze_problem, repeat_problem

    p, state, forecast = fixture()
    model = prepare_model(p, state, forecast, 0, Costs())
    path = tmp_path / "problem.json"
    path.write_text(json.dumps(freeze_problem(model, {"kind": "analytic fixture"})))
    report = repeat_problem(path, tmp_path / "trials", [{"time_limit_seconds": 2}], 2)
    assert len(report["trials"]) == 2
    assert len({r["environment"]["pid"] for r in report["trials"]}) == 2
    assert all(r["accepted_incumbent"] and r["worker_source_matches"] for r in report["trials"])
    assert all(
        r["problem_sha256"] == report["protocol"]["problem_sha256"] for r in report["trials"]
    )
    assert report["budgets"][0]["first_action_range"]["methane_kg"] == pytest.approx(0)
    capsule = json.loads((tmp_path / "trials/source-capsule.json").read_text())
    assert capsule["sha256"] == report["protocol"]["source_capsule_sha256"]
    hashes = json.loads((tmp_path / "trials/artifact-hashes.json").read_text())
    assert (
        hashes["report.json"]
        == hashlib.sha256((tmp_path / "trials/report.json").read_bytes()).hexdigest()
    )
    with pytest.raises(FileExistsError):
        repeat_problem(path, tmp_path / "trials", [{"time_limit_seconds": 2}], 2)


def fixture():
    p = replace(
        Plant(),
        battery_kwh=0,
        initial_h2_kg=5,
        heat_loss_kw_per_k=0,
        heater_max_kw=0,
        cooling_max_kw=0,
        minimum_run_hours=1,
    )
    return p, State.initial(p, 300), dict(pv_kw=[0, 12], ambient_c=[20, 20], deliveries_kg=[0, 0])


def test_independently_bounded_plant_optimum():
    p, state, forecast = fixture()
    for key in IMPLEMENTATIONS:
        actions, info = solve(p, state, forecast, 0, Costs(), seconds=2, battery=from_plant(p, key))
        assert info["valid_incumbent"]
        assert info["status"] == "solved"
        # First interval has no power. Second: 5 kg H2 / 0.5 = 10 kg CH4,
        # requiring exactly 2 + 10 = 12 kWh. Temperature ends below 400°C.
        assert actions[0]["methane_kg"] == pytest.approx(0)
        assert actions[1]["methane_kg"] == pytest.approx(10)
        assert info["objective_value"] - info["objective_bound"] < 1e-6


def test_formulation_equivalence_and_cross_feasibility():
    p, state, forecast = fixture()
    models = [
        prepare_model(p, state, forecast, 0, Costs(), battery=from_plant(p, key))
        for key in IMPLEMENTATIONS
    ]
    assert equivalence(models)["equivalent_within_tolerance"]
    for m in models:
        x, _ = m.solve(2)
        assert all(feasibility(other, x)["passed"] for other in models)
    models[1].objective[0] += 1
    assert not equivalence(models)["equivalent_within_tolerance"]
