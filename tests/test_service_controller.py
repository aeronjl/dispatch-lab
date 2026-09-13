"""Operational coordination, work obligations and observation-only retries."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from methane.cancellation import CancelledOperation, predicate
from methane.config import Config, Costs, Scenario
from methane.faults import FaultState
from methane.field_operations import FieldOperations
from methane.physics import State
from methane.policy import Policy
from methane.reference import audit
from methane.sensing import Diagnosis
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.configuration import ServiceSystem
from methane.services.controller import ServiceController, ServicePolicy
from methane.services.plant import PlantServices
from methane.simulation import run


def config(**kwargs):
    return Config(
        scenario=Scenario(hours=10, horizon_hours=6, solver_seconds=0.1),
        field_operations=FieldOperations(enabled=True, mission_failure_probability=0),
        service_system=ServiceSystem(
            support_model="logistics/1", outcome_randomness="target-action-request/1"
        ),
        service_economics=illustrative(Costs(), version=ACTIVITY_VERSION),
        service_policy=ServicePolicy(
            maximum_wait_hours=6, maximum_candidates=4, comparison_seconds=0.5
        ),
        **kwargs,
    )


def runtime():
    c = replace(
        config(),
        field_operations=FieldOperations(
            enabled=True,
            cleaner_enabled=False,
            rover_enabled=False,
            reset_enabled=False,
            mission_failure_probability=0,
            repair_success_probability=1,
        ),
        service_system=ServiceSystem(
            support_model="logistics/1",
            inspector="none",
            crew_response_lead_hours=0,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
            outcome_randomness="target-action-request/1",
        ),
    )
    rt = PlantServices(c.field_operations, c.service_system, 7, 450)
    diagnosis = Diagnosis(
        225,
        active_incident=True,
        incidents=1,
        status="capacity loss",
        informative=True,
        tracking_residual=0.5,
    )
    rt.prepare(0, diagnosis, 500)
    return c, rt, diagnosis


def forecast(hour=0, n=6, pv=500):
    origin = datetime(2026, 4, 10, tzinfo=UTC)
    return dict(
        decision_hour=hour,
        times=[(origin + timedelta(hours=hour + i)).isoformat() for i in range(n)],
        source=dict(
            id="control-fixture", initialized_at=origin.isoformat(), available_at=origin.isoformat()
        ),
        pv_kw=[pv] * n,
        ambient_c=[20] * n,
        deliveries_kg=[0] * n,
    )


def test_policy_roundtrip_is_explicit_and_legacy_serialization_is_preserved():
    c = config()
    assert Config.from_dict(c.to_dict()) == c
    assert "service_policy" not in Config().to_dict()
    assert "service" not in Policy().to_dict()
    p = Policy(version="dispatch-lab/policy/3", service=c.service_policy)
    assert Policy(**p.to_dict()) == p
    with pytest.raises(ValueError, match="version-3"):
        Policy(service=c.service_policy)
    with pytest.raises(ValueError, match="version-3"):
        Policy(objective="greedy", version="dispatch-lab/policy/3", service=c.service_policy)
    with pytest.raises(ValueError, match="accounting"):
        Config(service_policy=ServicePolicy())


@pytest.mark.parametrize(
    "patch",
    [
        {"maximum_candidates": 0},
        {"comparison_seconds": float("nan")},
        {"robot_reserve_fraction": 1.1},
        {"maximum_repair_attempts": True},
    ],
)
def test_invalid_policy_inputs_are_rejected(patch):
    with pytest.raises(ValueError):
        ServicePolicy(**patch)


def test_interrupted_repair_gets_distinct_attempt_and_keeps_original_deadline():
    c, rt, d = runtime()
    controller = ServiceController(c.service_policy)
    controller._work(rt)
    key = rt.orders[0]["id"]
    due = controller.obligations[key]["due_hour"]
    original = copy.deepcopy(rt.orders[0])
    fault = FaultState(c.plant, replace(c.scenario, fault_start_hour=0), c.faults)
    rt.dispatch_selected(((key, 1),), charge=False)
    rt.end(0, fault, d)
    rt.executive.interrupt(key, "Observed cancellation before departure")
    for hour in (1, 2, 3):
        rt.prepare(hour, d, 500)
        controller._work(rt)
        if hour < 3:
            assert len(rt.orders) == 1
            rt.dispatch_selected((), charge=False)
            rt.end(hour, fault, d)
    assert len(rt.orders) == 2
    retry = rt.orders[1]
    assert retry["retry_of"] == key and retry["obligation_origin"] == key
    assert retry["created_hour"] == 3 and retry["sequence"] == 2
    assert controller.obligations[key]["due_hour"] == due
    assert rt.orders[0]["created_hour"] == original["created_hour"]
    with pytest.raises(ValueError, match="successor"):
        rt.retry_failed(key, "Duplicate")
    # A second observed interruption exhausts the configured total attempt cap.
    rt.dispatch_selected(((retry["id"], 4),), charge=False)
    rt.end(3, fault, d)
    assert retry["id"] in rt.executive.missions, rt.interval["selection"]
    rt.executive.interrupt(retry["id"], "Second observed interruption")
    rt.prepare(4, d, 500)
    controller._work(rt)
    assert controller.obligations[key]["status"] == "escalation-required"
    assert len(rt.orders) == 2


def test_completed_but_unverified_procedure_is_not_declared_failed_for_retry():
    c, rt, d = runtime()
    key = rt.orders[0]["id"]
    fault = FaultState(c.plant, replace(c.scenario, fault_start_hour=0), c.faults)
    for hour in range(5):
        if hour:
            rt.prepare(hour, d, 500)
        rt.dispatch_selected(((key, 0),) if hour == 0 else (), charge=False)
        rt.end(hour, fault, d)
    rt.prepare(5, d, 500)
    assert rt.public()["orders"][0]["status"] == "awaiting verification"
    with pytest.raises(ValueError, match="observed"):
        rt.retry_failed(key, "Unconfirmed does not prove failed")
    controller = ServiceController(c.service_policy)
    controller._work(rt)
    assert controller.obligations[key]["status"] == "awaiting verification"


def test_due_work_is_selected_with_no_oracle_repair_benefit():
    c, rt, d = runtime()
    controller = ServiceController(c.service_policy)
    result = controller.decide(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(),
        225,
        c.costs,
        c.service_economics,
        seconds=1,
    )
    assert result["decision"]["selected_candidate_id"].startswith(rt.orders[0]["id"])
    assert result["decision"]["fallback_used"] is False
    assert result["decision"]["inputs"]["capacity_kw"] == 225
    assert "faults" not in result["decision"]["inputs"]
    assert "recovery_hour" not in result["decision"]["inputs"]
    assert len(rt.executive.missions) == 1
    assert result["decision"]["inputs"]["obligations"][0]["due_hour"] == 6


def test_no_incumbent_falls_back_to_current_essential_work(monkeypatch):
    c, rt, d = runtime()
    controller = ServiceController(c.service_policy)
    monkeypatch.setattr(
        "methane.services.charge_control.evaluate",
        lambda *a, **k: dict(
            state="unresolved", constraints=[dict(reason="Time limit without incumbent")]
        ),
    )
    result = controller.decide(
        rt, c.plant, State.initial(c.plant), forecast(), 225, c.costs, c.service_economics
    )
    assert result["decision"]["fallback_used"] and result["plan"] is None
    assert len(rt.executive.missions) == 1
    assert result["forecast"]["electrolyser_isolated"] == rt.isolation_horizon(6)


def test_cancellation_never_commits_new_missions():
    c, rt, d = runtime()
    controller = ServiceController(c.service_policy)
    token = predicate.set(lambda: True)
    try:
        with pytest.raises(CancelledOperation):
            controller.decide(
                rt, c.plant, State.initial(c.plant), forecast(), 225, c.costs, c.service_economics
            )
    finally:
        predicate.reset(token)
    assert not rt.executive.missions


def test_past_charge_deadline_is_retained_after_an_unfunded_interval():
    c = config()
    rt = PlantServices(c.field_operations, c.service_system, 7, 450)
    # No work requested; observed low inventory creates a fixed service target.
    rt.ledger.__init__(
        [
            replace(r, initial=0) if r.resource_id == "energy:rover" else r
            for r in rt.ledger.specs.values()
        ]
    )
    rt.prepare(0, Diagnosis(450), 0)
    controller = ServiceController(replace(c.service_policy, charging_wait_hours=1))
    targets = controller._targets(rt, 6)
    assert next(t for t in targets if t.robot == "rover").due_hour == 1
    fault = FaultState(c.plant, c.scenario, c.faults)
    rt.dispatch_selected((), charge=False)
    rt.end(0, fault, Diagnosis(450))
    rt.prepare(1, Diagnosis(450), 0)
    targets = controller._targets(rt, 6)
    target = next(t for t in targets if t.robot == "rover")
    assert target.due_hour == 1
    # The established numerical charging tests cover power infeasibility; this
    # test checks the controller cannot silently push an unmet original clock.
    assert (
        rt.ledger.stock["energy:rover"] == 0 and controller.energy_targets["rover"]["due_hour"] == 1
    )


@pytest.fixture(scope="module")
def operational_run():
    c = config()
    return run(c, strategies=["Greedy", "MPC · methane"])


def test_simulation_records_joint_control_and_preserves_greedy_baseline(operational_run):
    r = operational_run
    assert r["status"] == "complete", r["failures"]
    assert all("service_control" not in x["decision"] for x in r["records"]["Greedy"])
    controlled = r["records"]["MPC · methane"]
    assert all(
        x["decision"]["controller_policy"]["service"]["version"] == "coordinated-services/1"
        for x in controlled
    )
    assert all(x["decision"]["forecast"]["decision_hour"] == x["hour"] for x in controlled)
    assert all(
        x["decision"]["service_control"] == x["field_operations"]["decision"]["service_control"]
        for x in controlled
    )
    assert "service_control" in r["metrics"]["MPC · methane"]
    report = audit(r)
    assert report["passed"], [c for c in report["checks"] if not c["passed"]][:5]


def test_future_fault_settings_do_not_enter_service_decision_inputs():
    c = replace(config(), scenario=Scenario(hours=2, horizon_hours=6, solver_seconds=0.1))
    original = run(c, strategies=["MPC · methane"])
    altered = run(
        replace(
            c,
            faults=replace(c.faults, capacity_cause="resettable-trip"),
            scenario=replace(c.scenario, fault_start_hour=30, capacity_fraction=0.1),
        ),
        strategies=["MPC · methane"],
    )
    for a, b in zip(
        original["records"]["MPC · methane"], altered["records"]["MPC · methane"], strict=True
    ):
        assert (
            a["decision"]["service_control"]["inputs"] == b["decision"]["service_control"]["inputs"]
        )


def test_coordination_study_freezes_policy_package_and_matches_shared_inputs():
    from methane.field_studies import values
    from methane.studies import protocol, resolve_cases

    spec = protocol("field-coordination")
    cases = resolve_cases(spec, spec["reference_config"], "smoke")
    assert len(cases) == 12
    groups = {}
    for case in cases:
        groups.setdefault(case["group_id"], []).append(case)
        assert Config.from_dict(case["config"]).to_dict() == case["config"]
        p = case["policies"][case["controller"]]
        assert Policy(**p).to_dict() == p
    for members in groups.values():
        assert len(members) == 3
        assert len({m["matching_inputs_hash"] for m in members}) == 1
        assert {m["arm_id"] for m in members} == {"local", "coordinated", "economics"}
    assert values({})["service_fallback_intervals"] is None
    assert values({"service_control": {"fallback_intervals": 0}})["service_fallback_intervals"] == 0


def test_stranded_crew_cannot_be_recreated_by_queuing_a_retry():
    c, rt, d = runtime()
    controller = ServiceController(c.service_policy)
    controller._work(rt)
    first = rt.orders[0]["id"]
    rt.dispatch_selected(((first, 0),), charge=False)
    fault = FaultState(c.plant, c.scenario, c.faults)
    rt.end(0, fault, d)
    rt.executive.interrupt(first, "Observed interruption after departure")
    assert rt.executive.missions[first].status == "stranded"
    for hour in range(1, 4):
        rt.prepare(hour, d, 500)
        controller._work(rt)
        if hour < 3:
            rt.dispatch_selected((), charge=False)
            rt.end(hour, fault, d)
    assert len(rt.orders) == 2
    with pytest.raises(ValueError, match="awaiting retrieval"):
        rt.propose(rt.orders[1]["id"])
    assert controller.obligations[first]["due_hour"] == 6
    assert rt.executive.missions[first].status == "stranded"


def test_feasible_original_deadline_has_priority_over_a_cheaper_late_start(monkeypatch):
    c, rt, d = runtime()
    controller = ServiceController(replace(c.service_policy, comparison_seconds=5))

    def evaluated(*args, **kwargs):
        choices = kwargs["selections"]
        start = choices[0][1] if choices else 0
        return dict(
            state="feasible",
            score=-1000 * start,
            forecast=forecast(n=10),
            process_plan=dict(actions=[]),
            current_requests=[],
            test_selections=choices,
        )

    monkeypatch.setattr("methane.services.charge_control.evaluate", evaluated)
    monkeypatch.setattr(
        "methane.services.charge_control.accept",
        lambda runtime, result: runtime.dispatch_selected(result["test_selections"], charge=False),
    )
    result = controller.decide(
        rt, c.plant, State.initial(c.plant), forecast(n=10), 225, c.costs, c.service_economics
    )
    decision = result["decision"]
    chosen = next(
        r for r in decision["candidates"] if r["candidate_id"] == decision["selected_candidate_id"]
    )
    assert chosen["progressing_obligations"] == [rt.orders[0]["id"]]
    assert chosen["unmet_deadlines"] == []
    assert any(
        r["evaluation"]["score"] < chosen["evaluation"]["score"] and r["unmet_deadlines"]
        for r in decision["candidates"]
    )


def test_independent_support_check_requires_explicit_future_start_authorization():
    from dataclasses import asdict

    from methane.reference import SupportReference

    c, rt, d = runtime()
    rt.dispatch_selected(((rt.orders[0]["id"], 1),), charge=False)
    row = rt.end(0, FaultState(c.plant, c.scenario, c.faults), d)

    def check(record):
        checks = []
        SupportReference(asdict(c.service_system), record["assets"]).interval(
            record, 0, checks, "fixture"
        )
        return [x for x in checks if not x["passed"]]

    assert check(row) == []
    unauthorized = copy.deepcopy(row)
    unauthorized.pop("selection")
    assert any(x["check"] == "support.dispatch_boundary" for x in check(unauthorized))
    mismatched = copy.deepcopy(row)
    mismatched["selection"]["results"][0]["starting_at"] = 2
    assert any(x["check"] == "support.selected_start" for x in check(mismatched))


def test_playback_projects_summaries_without_changing_recorded_calculations(operational_run):
    import json

    from methane.provenance import verify
    from methane.ui import playback_value

    original = operational_run
    before = original["integrity_sha256"]
    view = playback_value(original, register_contexts=False)
    name = "MPC · methane"
    for raw, displayed in zip(original["records"][name], view["records"][name], strict=True):
        full = raw["decision"]["service_control"]
        brief = displayed["decision"]["service_control"]
        assert "inputs" not in brief
        assert brief["input_id"] == full["input_id"]
        assert brief["full_calculation_path"].endswith("/decision/service_control")
        assert displayed["field_operations"]["decision"]["service_control"] == brief
        assert "charging_evaluation" not in displayed["field_operations"]["decision"]
        for a, b in zip(full["candidates"], brief["candidates"], strict=True):
            assert a["candidate_id"] == b["candidate_id"] and a["status"] == b["status"]
            if a.get("evaluation", {}).get("process_plan"):
                assert (
                    a["evaluation"]["process_plan"]["predicted"]
                    == b["evaluation"]["process_plan"]["predicted"]
                )
                assert "trajectory" not in b["evaluation"]["process_plan"]
        assert len(json.dumps(brief)) < len(json.dumps(full))
    assert original["integrity_sha256"] == before
    verify(original)
