"""Release-2 boundaries: supported effects, observation clocks, teaching and lineage."""

import copy
from dataclasses import replace
from types import SimpleNamespace

import pytest
from test_lifecycle import check_run, replacement_config, tick

from methane.learning import evaluate
from methane.lifecycle.families import FAMILIES, assess, guard_service_asset
from methane.lifecycle.runtime import Runtime


@pytest.mark.parametrize("family", FAMILIES)
def test_every_family_has_a_bounded_or_unavailable_mechanism(family):
    status, _, requirements, _, _, implementation = FAMILIES[family]
    available = assess(family, requirements)
    missing = assess(family, ())
    assert available["eligible"] == bool(implementation)
    assert not missing["eligible"] and missing["missing"] == requirements
    if status == "evidence restricted":
        with pytest.raises(ValueError, match="no registered service mechanism"):
            guard_service_asset(SimpleNamespace(archetype=family, autonomy="autonomous"))
    if family == "service-module":
        assert not assess(family, requirements, automation="autonomous")["eligible"]
        with pytest.raises(ValueError, match="insertion"):
            guard_service_asset(SimpleNamespace(archetype=family, autonomy="autonomous"))


@pytest.mark.parametrize("topic", ["deployment", "condition", "hardware", "maintenance"])
def test_lifecycle_essay_executes_current_model_without_mutating_defaults(topic):
    result = evaluate(topic)
    assert result["status"] == "complete", result.get("error")
    assert result["steps"] and result["series"] and result["execution_identity"]
    assert all(c["passed"] for c in result["checks"])
    original = copy.deepcopy(result)
    result["steps"].clear()
    again = evaluate(topic)
    # Solver timings are not a physical comparison; maintenance uses Greedy here.
    assert again["metrics"] == original["metrics"]
    assert again["steps"]


def test_acceptance_failure_and_condition_delay_are_visible_in_examples():
    denied = evaluate("deployment", {"failed": 3})
    assert denied["status"] == "complete"
    assert denied["steps"][-1]["package"]["accepted_at"] is None
    delayed = evaluate("condition", {"delay": 6, "noise": 0})
    assert all(s["measurement"] is None for s in delayed["steps"][:6])
    assert delayed["steps"][6]["measurement"]["available_at"] == 6
    failed = evaluate("condition", {"success": "fails", "noise": 0})
    assert not any(j["status"] == "verified" for s in failed["steps"] for j in s["jobs"])
    assert evaluate("maintenance", {"hours": 24.5})["status"] == "incomplete"


def test_queued_replacement_rechecks_reference_at_actual_start():
    c = replacement_config(outages=[dict(resource="reference", start_hour=8, end_hour=9)])
    life = {**c.lifecycle, "crew_shift_start": 8, "crew_hours_per_day": 8}
    rt = Runtime(life, 7)
    for _ in range(8):
        tick(rt)
    assert rt.active is not None  # Chosen earlier while off shift.
    view, _ = tick(rt)
    assert view["current"]["crew_hours"] == 0
    assert rt.conditions["electrolyser"]["stock"] == 1
    view, _ = tick(rt)
    assert view["current"]["crew_hours"] == 1
    assert rt.jobs[0]["started_at"] == 9


@pytest.mark.parametrize(
    "resource", ["access", "communications", "reference", "dock", "project-crew"]
)
def test_support_outage_propagates_without_exposing_recovery_time(resource):
    from methane.lifecycle.fixtures import illustrative
    from methane.simulation import run
    from methane.weather import prepare

    c = illustrative(replacement_config(), aged=True)
    c = replace(
        c, lifecycle={**c.lifecycle, "outages": [dict(resource=resource, start_hour=2, end_hour=6)]}
    )
    r = run(c, prepare(c), ["Greedy"])
    check_run(r)
    for h, row in enumerate(r["records"]["Greedy"]):
        assert row["decision"]["lifecycle"]["current"]["resources"][resource] == (not 2 <= h < 6)
        assert "end_hour" not in repr(row["decision"]["lifecycle"])


def test_recorded_condition_operands_and_independent_accounting_detect_tampering():
    from methane.lineage import trace
    from methane.reference import audit
    from methane.simulation import run
    from methane.weather import prepare

    c = replacement_config(maintenance_policy="none")
    c = replace(c, sensors=replace(c.sensors, ambiguity_policy="retain-capacity/1"))
    r = run(c, prepare(c), ["Greedy"])
    check_run(r)
    from methane.engineering import audit_archive

    assert audit_archive(r)["passed"]
    row = r["records"]["Greedy"][0]
    t = trace(r, "Greedy", 0, "electrolyser")
    parameter = next(n for n in t["nodes"] if n["id"] == "parameters.specific_energy_kwh_per_kg")
    assert parameter["value"] == row["lifecycle"]["physical_plant"]["specific_energy_kwh_per_kg"]
    assert parameter["value"] > c.plant.specific_energy_kwh_per_kg
    altered = copy.deepcopy(r)
    altered["records"]["Greedy"][0]["lifecycle"]["accounting"]["condition_assets"] = []
    checked = audit(altered)
    assert not checked["passed"]
    assert any(
        x["id"] == "lifecycle.accounting.condition_assets" and not x["passed"]
        for x in checked["checks"]
    )


def test_project_work_waits_for_committed_field_target():
    from methane.lifecycle.fixtures import illustrative
    from methane.lifecycle.ports import apply_support
    from methane.services.contracts import Context, Reading
    from methane.services.plant import PlantServices

    c = illustrative(replacement_config(), aged=True)
    runtime = Runtime(c.lifecycle, 7)
    view = runtime.begin(0, {"pv_kw": [700] * 6}, occupied_assets=["solar"])
    assert view["current"]["crew_hours"] == 0
    services = PlantServices(
        c.field_operations, replace(c.service_system, cleaning_model="lumped-dc/1"), 7, 450
    )
    apply_support(runtime, services, 0)
    interface = services.registry.interfaces["ARRAY/brush"]
    requirement = next(r for r in interface.requirements if r.channel == "project-free:solar")
    assert requirement.failure(
        Context(0, (Reading("project-free:solar", False, "boolean", 0, 0, "test"),))
    )
