"""Independent clocks, capacity and chemistry checks for opt-in lifecycle execution."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Config, Plant
from methane.dispatch import plan
from methane.lifecycle.configuration import validate
from methane.lifecycle.runtime import Runtime
from methane.physics import State


def tick(runtime, power=0):
    view = runtime.begin(runtime.hour, {"pv_kw": [700] * 6, "source": {"id": "fixture"}})
    record = runtime.finish({"applied": {"electrolyser_kw": power}, "electrolyser_start": 0})
    return view, record


def package(**changes):
    return dict(
        id="array",
        asset="solar",
        fraction=0.5,
        mobilisation_hours=0.5,
        installation_hours=1,
        acceptance_hours=0.5,
        departure_hours=0.5,
        **changes,
    )


def test_acceptance_controls_capacity_and_temporary_equipment_leaves():
    runtime = Runtime(dict(packages=[package()], crew_shift_start=0, crew_hours_per_day=24), 7)
    frames = [tick(runtime) for _ in range(4)]
    assert [v["availability"]["solar"] for v, _ in frames] == [0.5, 0.5, 0.5, 1]
    assert sum(r["decision"]["crew_hours"] for _, r in frames) == 2.5
    assert runtime.packages["array"]["accepted_at"] == 3
    assert runtime.packages["array"]["departed_at"] == 4


def test_failed_acceptance_cannot_credit_capacity_or_rewrite_prior_decisions():
    a = Runtime(dict(packages=[package()], crew_shift_start=0, crew_hours_per_day=24), 7)
    b = Runtime(
        dict(
            packages=[package(failed_acceptance_attempts=1)],
            crew_shift_start=0,
            crew_hours_per_day=24,
        ),
        7,
    )
    for _ in range(3):
        av, _ = tick(a)
        bv, _ = tick(b)
        assert av == bv
    assert a.available()["solar"] == 1 and b.available()["solar"] == 0.5
    assert b.packages["array"]["phase"] == "rework"


def test_condition_units_and_eligible_measurement_are_independent():
    c = dict(
        asset="electrolyser",
        initial_operating_hours=20000,
        replacement_part_eur=120000,
        sensor_noise_fraction=0,
        sensor_delay_hours=2,
        sensor_period_hours=1,
    )
    runtime = Runtime(dict(conditions=[c], maintenance_policy="none"), 7)
    expected = float(Decimal("4.8") * Decimal(20000) / Decimal(1000000) / Decimal("1.9"))
    assert runtime.plant(Plant(), physical=True).specific_energy_kwh_per_kg == pytest.approx(
        55 * (1 + expected)
    )
    assert runtime.plant(Plant()).specific_energy_kwh_per_kg == 55
    for _ in range(2):
        view, _ = tick(runtime)
        assert view["condition"]["electrolyser"]["measurement"] is None
    view, _ = tick(runtime)
    assert view["condition"]["electrolyser"]["estimate"] == pytest.approx(expected)
    assert view["condition"]["electrolyser"]["measurement"]["available_at"] == 2


def test_known_future_outage_cannot_change_earlier_work():
    options = dict(packages=[package()], crew_shift_start=0, crew_hours_per_day=24)
    a = Runtime(options, 7)
    b = Runtime({**options, "outages": [dict(resource="access", start_hour=10, end_hour=20)]}, 7)
    assert [tick(a) for _ in range(6)] == [tick(b) for _ in range(6)]


@pytest.mark.parametrize("objective", ["greedy", "methane", "economics"])
def test_planner_respects_uncommissioned_equipment(objective):
    p = Plant()
    f = dict(
        pv_kw=[500] * 6,
        ambient_c=[20] * 6,
        deliveries_kg=[0] * 6,
        component_availability={"battery": [0] * 6, "electrolyser": [0] * 6, "reactor": [0] * 6},
    )
    result = plan(p, State.initial(p, 20), f, p.electrolyser_kw, Config().costs, objective, 0.2)
    assert result["actions"]
    assert all(
        all(abs(v) < 1e-7 for k, v in a.items() if k != "cooling_kw") for a in result["actions"]
    )


def test_unavailable_crew_preserves_work_and_stock():
    runtime = Runtime(
        dict(
            packages=[package()],
            crew_shift_start=0,
            crew_hours_per_day=1,
            outages=[dict(resource="access", start_hour=0, end_hour=2)],
        ),
        7,
    )
    for _ in range(24):
        tick(runtime)
    assert runtime.packages["array"]["remaining"] == 0.5
    assert runtime.packages["array"]["status"] == "waiting"
    tick(runtime)
    assert runtime.packages["array"]["phase"] == "installation"


def test_strict_configuration_and_absent_legacy_identity():
    assert "lifecycle" not in Config().to_dict()
    assert Config.from_dict(Config().to_dict()).to_dict() == Config().to_dict()
    with pytest.raises(ValueError, match="prerequisite"):
        validate(dict(packages=[{**package(), "depends_on": ["missing"]}]))
    with pytest.raises(ValueError, match="fractions"):
        validate(dict(packages=[{**package(), "fraction": 1}, {**package(), "id": "other"}]))


def test_integrated_stack_energy_and_no_initial_policy_truth():
    from methane.simulation import run
    from methane.weather import synthetic

    c = Config()
    c = replace(
        c,
        scenario=replace(c.scenario, hours=6, horizon_hours=6, solver_seconds=0.05),
        lifecycle=dict(
            maintenance_policy="none",
            conditions=[
                dict(
                    asset="electrolyser",
                    initial_operating_hours=20000,
                    replacement_part_eur=120000,
                    sensor_period_hours=1,
                    sensor_noise_fraction=0,
                )
            ],
        ),
    )
    w = synthetic(c)
    for table in (w["truth"], w["template"]):
        for sample in table.values():
            sample.update(pv_kw=700, irradiance_wm2=700, ambient_c=20)
    untouched = copy.deepcopy(c.to_dict())
    result = run(c, w, ["Greedy"])
    assert result["status"] == "complete"
    rows = result["records"]["Greedy"]
    assert rows[0]["decision"]["operating_plant"]["specific_energy_kwh_per_kg"] == 55
    for row in rows:
        sec = row["lifecycle"]["physical_plant"]["specific_energy_kwh_per_kg"]
        productive = row["applied"]["electrolyser_kw"]
        assert row["h2_produced_kg"] == pytest.approx(productive / sec)
        assert all(
            p is None or p["available_at"] <= row["hour"]
            for p in row["lifecycle"]["decision"]["observations"].values()
        )
    assert c.to_dict() == untouched
    from methane.reference import audit

    checked = audit(result)
    assert checked["passed"], (
        checked["failures"],
        [x for x in checked["checks"] if not x["passed"]][:5],
    )


def replacement_config(**changes):
    c = Config()
    return replace(
        c,
        scenario=replace(c.scenario, hours=14, horizon_hours=6, solver_seconds=0.05),
        lifecycle=dict(
            crew_shift_start=0,
            crew_hours_per_day=24,
            conditions=[
                dict(
                    asset="electrolyser",
                    initial_operating_hours=50000,
                    replacement_part_eur=120000,
                    sensor_period_hours=1,
                    sensor_noise_fraction=0,
                    replacement_hours=2,
                )
            ],
            **changes,
        ),
    )


def check_run(result):
    from methane.reference import audit

    assert result["status"] == "complete", result.get("failures")
    checked = audit(result)
    assert checked["passed"], (
        checked["failures"],
        [x for x in checked["checks"] if not x["passed"]][:3],
    )


def test_replacement_receipt_observation_stock_and_cash_reconcile():
    from methane.costing import allocation, reprice
    from methane.simulation import run
    from methane.weather import prepare

    c = replacement_config()
    result = run(c, prepare(c), ["Greedy"])
    check_run(result)
    rows = result["records"]["Greedy"]
    assert rows[1]["lifecycle"]["decision"]["availability"]["electrolyser"] == 0
    assert rows[2]["lifecycle"]["after"]["jobs"][0]["status"] == "awaiting-verification"
    assert rows[4]["lifecycle"]["after"]["jobs"][0]["status"] == "verified"
    report = allocation(c.plant, c.costs, rows, with_lineage=True)
    assert (
        report["lifecycle"]["cash_eur"] == 240460
    )  # Opening part, purchased replenishment, two crew hours and one callout.
    assert report["components"]["electrolyser"] >= 120000
    assert report["components"]["electrolyser"] < 120100  # Consumed part replaces the wear pool.
    original = copy.deepcopy(rows)
    priced = reprice(result, replace(c.costs, methane_eur_per_kg=10))
    assert result["records"]["Greedy"] == original
    assert priced["dispatch_costs"]["methane_eur_per_kg"] == c.costs.methane_eur_per_kg
    assert priced["controllers"]["Greedy"][-1]["lifecycle"]["cash_eur"] == 240460


@pytest.mark.parametrize("commission", [False, True])
def test_continuation_keeps_condition_work_and_allocation_pools(commission):
    from methane.costing import allocation
    from methane.simulation import run
    from methane.siting.checkpoint import Continuation
    from methane.siting.store import digest
    from methane.weather import prepare

    c = replacement_config()
    if commission:
        from methane.lifecycle.fixtures import illustrative

        c = illustrative(c, aged=True)
    w = prepare(c)
    whole = run(c, w, ["Greedy"])
    check_run(whole)
    binding = digest(dict(config=c.to_dict(), weather=w))
    first = Continuation(14, 5, binding)
    a = run(c, w, ["Greedy"], continuation=first)
    second = Continuation(14, 14, binding, checkpoint=copy.deepcopy(first.output))
    b = run(c, w, ["Greedy"], continuation=second)
    together = a["records"]["Greedy"] + b["records"]["Greedy"]
    for left, right in zip(together, whole["records"]["Greedy"], strict=True):
        for key in ("state", "applied", "lifecycle"):
            assert left[key] == right[key]
    pieces = [allocation(c.plant, c.costs, r["records"]["Greedy"]) for r in (a, b)]
    for key in ("electrolyser", "solar", "project_service", "site"):
        assert sum(r["components"][key] for r in pieces) == pytest.approx(
            whole["metrics"]["Greedy"]["components"][key]
        )


def test_missing_reference_expires_and_does_not_create_unbounded_work():
    runtime = Runtime(
        dict(
            conditions=[
                dict(
                    asset="electrolyser",
                    replacement_part_eur=1,
                    initial_operating_hours=50000,
                    sensor_period_hours=1,
                    sensor_noise_fraction=0,
                )
            ],
            maximum_wait_hours=2,
            outages=[dict(resource="reference", start_hour=0, end_hour=100)],
        ),
        7,
    )
    for _ in range(20):
        tick(runtime)
    assert len(runtime.jobs) == 2
    assert all(j["status"] == "work-expired" for j in runtime.jobs)
    assert runtime.conditions["electrolyser"]["stock"] == 1


def test_forecast_window_uses_complete_work_windows():
    runtime = Runtime(
        dict(
            conditions=[
                dict(
                    asset="electrolyser",
                    replacement_part_eur=1,
                    initial_operating_hours=50000,
                    sensor_period_hours=1,
                    sensor_noise_fraction=0,
                    replacement_hours=3,
                )
            ],
            maintenance_policy="forecast-window",
            crew_shift_start=0,
            crew_hours_per_day=24,
        ),
        7,
    )
    tick(runtime)
    view = runtime.begin(1, {"pv_kw": [10, 10, 10, 50], "source": {"id": "fixture"}})
    assert view["current"]["crew_hours"] == 1
    assert view["jobs"][0]["planned_start"] == 1


def test_lifecycle_pv_loss_precedes_converter_clipping():
    from methane.solar_model import default_design, interval

    c = Config()
    design = {**default_design(c.plant, c.weather), "converter_kw": 100}
    sample = dict(pv_kw=800, irradiance_wm2=1000, ambient_c=20)
    a = interval(design, sample, "2026-07-10T12:00:00Z", c.plant, c.weather)
    b = interval(
        design, {**sample, "lifecycle_factor": 0.5}, "2026-07-10T12:00:00Z", c.plant, c.weather
    )
    assert a["output_kw"] == b["output_kw"] == 100
    assert b["clipped_kw"] < a["clipped_kw"]
    assert b["lifecycle_loss_kw"] > 0
