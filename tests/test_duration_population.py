import copy
from dataclasses import replace

import pytest

from methane.autonomy import DEFAULT, Beliefs, validate
from methane.duration_population import AUTONOMY_VERSION, default_model, estimate
from methane.services.uncertain_planning import quantile


def options():
    return {
        **copy.deepcopy(DEFAULT),
        "version": AUTONOMY_VERSION,
        "duration_model": default_model(),
    }


def packet(order="job", factor=1, **changes):
    return dict(
        id=order + "/0",
        order_id=order,
        asset_id="cleaner",
        group="cleaning",
        nominal_hours=1,
        elapsed_hours=factor,
        started_at=0,
        available_at=2,
        completed_at=factor,
        censored=False,
        interrupted=False,
        **changes,
    )


def test_completed_likelihood_marginalises_job_noise_and_groups_phases():
    o = options()
    row = packet()
    b = Beliefs(o)
    r = b.update(2, [row, {**row, "id": "job/return"}], [])
    item = r["equipment_durations"]["cleaner"]["cleaning"]
    # Densities at factor 1: 1/.4 and 1/.5; one trial, not two.
    assert item["posterior_weights"] == pytest.approx([0, 5 / 9, 4 / 9, 0])
    assert item["independent_jobs"] == 1
    assert quantile(item, 0.95) > 1.2  # Next job has fresh variation.
    assert quantile(item["job_conditionals"]["job"], 0.95) == pytest.approx(1)
    assert r["durations"]["cleaning"]["weights"] == [0.25] * 4  # Other equipment stays prior.


def test_censoring_is_replaced_and_not_counted_twice_for_active_prediction():
    b = Beliefs(options())
    row = {**packet(), "censored": True, "completed_at": None, "elapsed_hours": 1.1}
    a = b.update(2, [row], [])
    c = b.update(3, [{**row, "available_at": 3}], [])
    v = c["equipment_durations"]["cleaner"]["cleaning"]
    assert a["equipment_durations"]["cleaner"]["cleaning"]["weights"] == v["weights"]
    assert v["job_conditionals"]["job"]["weights"] == [0.25] * 4
    assert quantile(v["job_conditionals"]["job"], 0.1) > 1.1
    with pytest.raises(ValueError, match="future"):
        b.update(4, [{**row, "available_at": 10}], [])


def test_mixture_quantile_handles_overlapping_uniforms_and_atoms():
    assert quantile(dict(bins=[[0, 2], [1, 3]], weights=[0.5, 0.5]), 0.5) == pytest.approx(1.5)
    assert quantile(dict(bins=[[1, 1], [2, 2]], weights=[0.7, 0.3]), 0.5) == pytest.approx(1)
    assert quantile(dict(bins=[[1, 1], [2, 2]], weights=[0.7, 0.3]), 0.5, 1) == pytest.approx(2)


def test_explicit_support_rejects_unbounded_or_incompatible_evidence():
    o = options()
    validate(o)
    o["duration_model"]["groups"]["repair"]["job_multiplier_bounds"] = [1, 5]
    with pytest.raises(ValueError, match="support"):
        validate(o)
    item = default_model()["groups"]["cleaning"]
    v = estimate(item, [packet(factor=5)], [0.5, 2], 2, 24)
    assert v["unsupported"] == ["job"]
    assert v["status"] == "outside model support"


def execute(factor=1.5, seed=7):
    from test_uncertain_services import config, spec

    from methane.config import Config
    from methane.simulation import run
    from methane.uncertainty import resolve
    from methane.weather import synthetic

    c = config(12)
    c = replace(
        c,
        scenario=replace(c.scenario, seed=seed),
        service_system=replace(c.service_system, outcome_randomness="target-action-request/1"),
    )
    s = spec(factor)
    s["autonomy"] = options()
    world = resolve(s, c.to_dict())[0]
    assert world["status"] == "resolved", world
    actual = Config.from_dict(world["config"])
    weather = synthetic(actual)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample["pv_kw"] = 500
    r = run(actual, weather=weather, strategies=["Greedy"], uncertainty=world)
    assert r["status"] == "complete", r.get("failures")
    return r


def test_private_equipment_and_job_clocks_reconcile_without_early_information():
    from methane.reference import audit

    a, b = execute(0.75), execute(1.5)
    assert a["records"]["Greedy"][0]["decision"] == b["records"]["Greedy"][0]["decision"]
    for r in (a, b):
        assert all(
            "retrospective_job_clocks" not in row["field_operations"]
            for row in r["records"]["Greedy"]
        )
        checked = audit(r)
        assert checked["passed"], checked


def test_job_draws_ignore_candidate_search_and_change_only_for_accepted_requests():
    from test_uncertain_services import config

    from methane.sensing import Diagnosis
    from methane.services.job_clock import JobClock
    from methane.services.plant import PlantServices

    c = config()
    rt = PlantServices(c.field_operations, c.service_system, 7, 450, autonomy=options())
    rt.prepare(0, Diagnosis(450), 500)
    plan = rt._build(rt.orders[0])
    clock = JobClock(default_model(), {k: 1 for k in options()["duration_bounds"]}, 7)
    a = clock.prepare([plan])
    assert a == clock.prepare([plan])
    assert clock.retrospective() == {}
    clock.commit(a)
    assert clock.prepare([plan])[1] != a[1]
    assert a[1][plan.order.order_id]["factors"]["cleaning"] != 1


def test_calibration_holdout_does_not_select_the_model_and_rejects_truth_inference():
    from methane.duration_calibration import VERSION, fit

    first = default_model()
    second = copy.deepcopy(first)
    second["groups"]["cleaning"]["job_multiplier_bounds"] = [0.9, 1.1]
    rows = []
    for i, factor in enumerate((0.95, 1.02, 1.07, 0.98, 1.03, 1.06)):
        r = packet(order=f"job{i}", factor=factor)
        r.update(started_at=i * 3, available_at=i * 3 + 2, completed_at=i * 3 + factor)
        rows.append(r)
    data = dict(
        version=VERSION,
        source=dict(id="observed-fixture", kind="simulated-observation", reference="test fixture"),
        observations=rows,
    )
    a = fit(data, [first, second], 9, options()["duration_bounds"])
    assert a["selected_model"] == second
    assert a["heldout"]["jobs"] == 3
    assert not set(a["training_ids"]) & set(a["heldout_ids"])
    changed = copy.deepcopy(data)
    changed["observations"][-1].update(elapsed_hours=1.9, completed_at=16.9)
    b = fit(changed, [first, second], 9, options()["duration_bounds"])
    assert a["training_scores"] == b["training_scores"]
    assert a["selected_model"] == b["selected_model"]
    assert b["status"] == "held-out model inadequacy"
    assert b["heldout"]["unsupported"] == ["job5"]
    changed["source"]["kind"] = "simulator-truth"
    with pytest.raises(ValueError, match="observations"):
        fit(changed, [first], 9, options()["duration_bounds"])


def test_null_planner_reuses_nominal_candidate_without_a_second_solve(monkeypatch):
    from types import SimpleNamespace

    from methane.config import Costs, Plant
    from methane.physics import State
    from methane.services import charge_control, uncertain_planning

    o = copy.deepcopy(DEFAULT)
    o.update(
        duration_bounds={k: [1, 1] for k in o["duration_bounds"]},
        weather_factors=[1],
        weather_weights=[1],
    )
    baseline = dict(state="feasible", score=123, process_plan={"requested": "nominal"})
    calls = []

    def original(*args, **kwargs):
        calls.append(kwargs)
        return copy.deepcopy(baseline)

    monkeypatch.setattr(charge_control, "evaluate", original)
    monkeypatch.setattr(
        uncertain_planning, "solve", lambda *a, **k: pytest.fail("Redundant null solve")
    )
    for mode in ("fixed", "adaptive", "risk-aware"):
        public = {**o, "mode": mode}
        rt = SimpleNamespace(
            autonomy=public,
            config=SimpleNamespace(mission_failure_probability=0),
            belief_record=Beliefs(public).record(),
        )
        result = uncertain_planning.evaluate(
            rt, Plant(), State.initial(Plant()), {}, 450, Costs(), []
        )
        assert result["process_plan"] == baseline["process_plan"]
        assert result["uncertainty_planning"]["status"] == "canonical-nominal"
    assert len(calls) == 3 and all(c["uncertain"] is False for c in calls)


def test_equipment_job_bundle_has_independent_offline_checker(tmp_path):
    import subprocess
    import sys

    from methane.bundle import make, unpack

    r = execute()
    path = make(r, tmp_path / "clock.zip")
    root = tmp_path / "restored"
    unpack(path, root)
    process = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(root / "check_bundle.py"),
            str(root),
            "--out",
            str(tmp_path / "check.json"),
        ],
        capture_output=True,
        text=True,
    )
    assert process.returncode == 0, process.stdout + process.stderr


@pytest.mark.parametrize("interruption", [0, 1])
def test_job_clock_scales_optical_coverage_and_brush_use_together(interruption):
    from test_surface_services import config, sunny
    from test_uncertain_services import spec

    from methane.config import Config
    from methane.reference import audit
    from methane.simulation import run
    from methane.uncertainty import resolve

    c = config(outcome_randomness="target-action-request/1", work_failure_fraction=0.3)
    c = replace(
        c,
        field_operations=replace(
            c.field_operations,
            mission_failure_probability=interruption,
            cleaning_kits=1,
            cleaner_battery_kwh=10,
        ),
    )
    s = spec(1.25)
    s["autonomy"] = options()
    world = resolve(s, c.to_dict())[0]
    actual = Config.from_dict(world["config"])
    result = run(actual, weather=sunny(actual), strategies=["Greedy"], uncertainty=world)
    assert result["status"] == "complete", result["failures"]
    fields = [r["field_operations"] for r in result["records"]["Greedy"]]
    areas = sum(f["treated_area_m2"] for f in fields)
    consumed = sum(
        e["amount"]
        for f in fields
        for e in f["resource_events"]
        if e["kind"] == "consume" and e["resource"] == "brush:cleaner"
    )
    # Reference section = 5,000 m² / three sections. A failed pass stops at 30%.
    expected = 5000 / 3 * (0.3 if interruption else 1)
    assert areas == pytest.approx(expected)
    assert consumed == pytest.approx(expected)
    events = [op for f in fields for op in f["surface_events"]]
    assert events and all(op["efficacy_start"] == pytest.approx(1) for op in events)
    checked = audit(result)
    assert checked["passed"], [c for c in checked["checks"] if not c["passed"]][:5]
