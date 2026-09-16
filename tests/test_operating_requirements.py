"""Outcome contracts: independent accounting, immutable inputs and usable reports."""

import zipfile
from copy import deepcopy

import pytest

from methane.config import Config
from methane.siting import production, projects, reporting, requirements, workflow
from methane.siting.catalogue import bootstrap
from methane.siting.store import Store


def brief(**changes):
    return requirements.Brief(name="Test needs", **changes).model_dump()


def rows(outputs, battery=None):
    return [
        dict(
            hour=i,
            applied=dict(methane_kg=v),
            state=dict(battery_kwh=(battery or [100] * len(outputs))[i], h2_kg=10, co2_kg=100),
            forced_trip=False,
        )
        for i, v in enumerate(outputs)
    ]


def test_window_shortfall_cannot_borrow_surplus_and_partial_window_is_prorated():
    result = requirements.check_rows(
        brief(methane_kg=10, shortfall_kg=2, window_hours=2),
        rows([1, 1, 9, 9, 3]),
        Config().to_dict()["plant"],
        5,
    )
    assert result["status"] == "unmet"
    assert result["shortfall_kg"] == 10
    assert result["windows"][-1] == dict(
        start=4, end=5, target=5, allowance=1, output=3, shortfall=2
    )
    assert result["checks"][0]["margin"] == -6
    assert result["checks"][0]["hour"] == 0


def test_boundary_reserves_include_start_and_explicit_warmup():
    plant = Config().to_dict()["plant"]
    plant["initial_soc"] = 0
    result = requirements.check_rows(brief(battery_kwh=50), rows([1, 1]), plant, 2)
    assert result["checks"][0]["actual"] == 0
    assert result["checks"][0]["detail"]["boundary_hour"] == 0
    assert result["status"] == "unmet"
    later = requirements.check_rows(brief(battery_kwh=50, after_hour=1), rows([1, 1]), plant, 2)
    assert later["status"] == "met"
    empty = requirements.check_rows(brief(battery_kwh=0, after_hour=2), rows([1, 1]), plant, 2)
    assert empty["status"] == "incomplete"


def test_missing_service_channels_and_partial_case_never_pass():
    plant = Config().to_dict()["plant"]
    result = requirements.check_rows(
        brief(dock_unserved_kwh=0, escalation_hours=0), rows([1, 1]), plant, 2
    )
    assert result["status"] == "unassessed"
    assert all(c["status"] == "missing" for c in result["checks"])
    assert (
        requirements.check_rows(brief(methane_kg=1), rows([1]), plant, 2)["status"] == "incomplete"
    )
    with pytest.raises(ValueError, match="consecutive"):
        requirements.check_rows(brief(battery_kwh=0), [rows([1, 1])[1]], plant, 2)


def test_service_totals_and_first_crossing_are_recorded_events():
    from methane.recovery import LOOP_VERSION

    r = rows([1, 1, 1])
    for i, item in enumerate(r):
        item["forced_trip"] = i == 1
        item["field_operations"] = {"standby": {"unserved_kwh": i}}
        item["decision"] = {
            "recovery_planning": {
                "status": "escalation-required" if i else "none",
                "version": LOOP_VERSION,
            }
        }
    result = requirements.check_rows(
        brief(forced_downtime_hours=0, dock_unserved_kwh=1, escalation_hours=1),
        r,
        Config().to_dict()["plant"],
        3,
    )
    assert [(c["actual"], c["hour"]) for c in result["checks"]] == [(1, 1), (3, 2), (2, 2)]
    assert result["status"] == "unmet"


@pytest.mark.parametrize(
    "changes",
    [
        {},
        dict(methane_kg=5, shortfall_kg=6),
        dict(shortfall_kg=1),
        dict(battery_kwh=-1),
        dict(battery_kwh=float("nan")),
        dict(battery_kwh=0, window_hours=1.5),
        dict(battery_kwh=0, unknown=5),
    ],
)
def test_invalid_brief_rejected(changes):
    with pytest.raises(ValueError):
        brief(**changes)


@pytest.fixture
def project(tmp_path):
    store = Store(tmp_path)
    return store, projects.create(store, bootstrap(store)[0]["id"])


def test_freeze_evaluate_trace_export_and_future_revision(project, tmp_path):
    store, p = project
    b = requirements.save(store, brief(methane_kg=10, window_hours=1, battery_kwh=1))
    p = projects.revise(store, p["project"]["id"], p["project"]["config"], requirements_id=b["id"])
    run = projects.run_project(
        store, p["project"]["id"], synthetic=True, hours=2, controller="Greedy"
    )
    sid = run["study_id"]
    original = deepcopy(store.get("study", sid))
    assert original["requirements_id"] == b["id"]
    assert workflow.recipe(original)["requirements_id"] == b["id"]
    pending = requirements.freeze(store, b["id"], [sid])
    production.execute(store, sid)
    # A worker completing later cannot silently fill in an earlier frozen assessment.
    result = requirements.evaluate(store, **pending)
    assert result["candidates"][0]["status"] == "incomplete"
    result = requirements.evaluate(store, **requirements.freeze(store, b["id"], [sid]))
    candidate = result["candidates"][0]
    assert candidate["assessment_context"] == "declared before execution"
    assert candidate["status"] == "unmet"
    trace = candidate["checks"][0]["trace"]
    assert trace["component"] == "reactor" and trace["edition_id"] == sid
    part = production.load_period(store, trace["period_sha256"])
    assert part["records"]["Greedy"][trace["hour"]]["hour"] == candidate["checks"][0]["hour"]
    assert result["groups"][0]["counts"]["unmet"] == 1
    assert result["groups"][0]["shortfall_kg"]["max"] > 0
    newer = requirements.save(store, brief(battery_kwh=0))
    projects.revise(store, p["project"]["id"], p["project"]["config"], requirements_id=newer["id"])
    assert store.get("study", sid) == original
    other = requirements.evaluate(store, **requirements.freeze(store, newer["id"], [sid]))
    assert other["candidates"][0]["assessment_context"].startswith("retrospective")
    assert other["candidates"][0]["status"] == "met"
    pub = reporting.publish(store, "operating-assessment", result["id"])
    report = open(pub["path"]).read()
    assert "Battery reserve" in report and "Recorded" in report
    bundle = reporting.bundle(store, pub["publication_id"])
    with zipfile.ZipFile(bundle["path"]) as z:
        assert f"requirements/{b['id']}.json" in z.namelist()
        assert f"operating-assessment/{result['id']}.json" in z.namelist()
    restored = Store(tmp_path / "restored")
    reporting.restore(bundle["path"], restored)
    assert restored.get("operating-assessment", result["id"])["candidates"] == result["candidates"]
    assert restored.get("requirements", b["id"]) == store.get("requirements", b["id"])


def test_cross_case_coverage_and_sources_do_not_disappear():
    def c(design, seed, status="met", source="v1"):
        return dict(
            id=f"{design}/{seed}/{source}",
            design_id=design,
            design_name=design,
            site=design,
            controller="Greedy",
            policy_id="p",
            role="design",
            source=source,
            environment={"start": "a", "end": "b"},
            seed=seed,
            repetition=1,
            uncertainty=None,
            status=status,
            shortfall_kg=0,
            summary={"total_eur": 1, "methane_kg": 2},
        )

    values = [c("a", 1), c("a", 2, "incomplete"), c("b", 1), c("b", 1, source="v2")]
    groups = requirements.aggregate(values)
    assert len(groups) == 3
    assert all(not g["all_selected_requirements_met"] for g in groups)
    assert len(groups[1]["missing_exposures"]) == 1
    assert groups[0]["counts"]["incomplete"] == 1


def test_nameplate_conflicts_are_necessary_bounds_not_a_feasibility_claim():
    plant = Config().to_dict()["plant"]
    b = brief(battery_kwh=plant["battery_kwh"] + 1, methane_kg=plant["methane_max_kgph"] * 24 + 1)
    assert {x["component"] for x in requirements.capacity_conflicts(b, plant)} == {
        "battery",
        "reactor",
    }
    assert requirements.capacity_conflicts(brief(battery_kwh=0), plant) == []


def test_unknown_recovery_schema_and_null_service_records_are_not_healthy():
    r = rows([1])
    r[0]["field_operations"] = None
    r[0]["decision"] = {"recovery_planning": {"version": "unknown", "status": "fine"}}
    result = requirements.check_rows(
        brief(dock_unserved_kwh=0, escalation_hours=0), r, Config().to_dict()["plant"], 1
    )
    assert result["status"] == "unassessed"
    assert all(c["actual"] is None for c in result["checks"])
