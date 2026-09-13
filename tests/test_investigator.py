"""Observed investigation handoff, finite episodes and legacy separation."""

import copy
from dataclasses import asdict, replace

import pytest

from methane.config import Config
from methane.physics import State
from methane.policy import Policy
from methane.sensing import Diagnosis
from methane.services.contracts import Context
from methane.services.inspection import evidence, sample
from methane.services.investigator import InvestigationPolicy, Investigator, preview, proposal
from methane.services.plant import PlantServices
from methane.services.verification import RESET_TRACKER_VERSION, TRACKER_VERSION, Followup
from methane.services.verification_examples import CONTROLLER, fixture, weather_for
from methane.simulation import run


def config(**changes):
    c = fixture("successful-procedure")
    return replace(
        c,
        scenario=replace(c.scenario, hours=24, horizon_hours=12),
        field_operations=replace(c.field_operations, reset_enabled=True),
        service_system=replace(c.service_system, inspector="fixed"),
        service_policy=replace(c.service_policy, maximum_wait_hours=20),
        investigation_policy=InvestigationPolicy(comparison_seconds=0.5, **changes),
    )


def prepared(*, delegated=True):
    c = config()
    rt = PlantServices(c.field_operations, c.service_system, 7, 450)
    diagnosis = Diagnosis(
        225, active_incident=True, incidents=1, informative=True, tracking_residual=0.5
    )
    rt.prepare(0, diagnosis, 750, capacity_requests=not delegated)
    return c, rt, diagnosis


def test_config_and_policy_roundtrip_preserve_original_absence():
    old = Config().to_dict()
    assert "investigation_policy" not in old
    assert "investigation" not in Policy().to_dict()
    c = config()
    assert Config.from_dict(c.to_dict()) == c
    p = Policy(
        version="dispatch-lab/policy/4",
        service=c.service_policy,
        recovery=c.recovery_policy,
        investigation=c.investigation_policy,
    )
    assert Policy(**p.to_dict()) == p
    with pytest.raises(ValueError, match="version-4"):
        replace(p, version="dispatch-lab/policy/3")


@pytest.mark.parametrize(
    "field,value",
    [
        ("risk_weight", float("nan")),
        ("comparison_seconds", True),
        ("minimum_restoration_probability", 1.1),
        ("observation_wait_hours", 1.5),
        ("reader", "camera"),
    ],
)
def test_invalid_policy_is_rejected(field, value):
    with pytest.raises(ValueError):
        InvestigationPolicy(**{field: value})


def test_preview_does_not_commission_work_or_reserve_resources():
    c, rt, _ = prepared()
    before = copy.deepcopy((rt.public(), rt.orders, rt.ledger.events))
    p = proposal(rt, "inspection", 1, reader="fixed")
    virtual, packet = preview(rt, p)
    assert not rt.orders
    assert virtual.propose(p["id"])[1]["feasible"]
    assert packet["proposed_recipe"]["plan"]
    assert (rt.public(), rt.orders, rt.ledger.events) == before
    with pytest.raises(ValueError, match="cannot execute"):
        virtual.executive.advance(1)


def test_delegation_preserves_local_baseline_requests():
    _, local, _ = prepared(delegated=False)
    _, delegated, _ = prepared()
    assert any(q["kind"] == "inspection" for q in local.orders)
    assert not delegated.orders
    assert delegated.interval["capacity_request_policy"] == "observation-contingent-investigation/1"
    assert "capacity_request_policy" not in local.interval


def test_only_commissioned_readers_count_and_unrequested_packets_do_not_authorise_reset():
    c, _, _ = prepared()
    options = replace(c.service_system, inspector="both")
    packets, _ = sample(
        dict(signal_v=24, offset_v=0, dropout=False), "fixed", 0.5, "read-1", 7, options
    )
    orders = [dict(id="read-1", kind="inspection", incident=1, created_hour=0)]
    context = Context(1, packets)
    assert evidence(context, options, orders, commissioned_only=True)["quality"] == "usable"
    assert evidence(context, options, orders)["quality"] == "uncertain"
    assert evidence(context, options, [], commissioned_only=True)["value"] is None
    orders.append(dict(id="read-2", kind="inspection-confirm", incident=1, created_hour=0))
    assert evidence(context, options, orders, commissioned_only=True)["value"] is None


def test_reset_test_tracker_is_opt_in_and_requires_real_repeated_tests():
    from test_post_service_verification import evidence as test_evidence
    from test_post_service_verification import order

    q = order()
    q["kind"] = "reset"
    old = Followup(2, 12)
    new = Followup(2, 12, include_resets=True)
    for hour in (6, 7):
        a = old.advance(hour, [q], test_evidence(hour - 1))
        b = new.advance(hour, [q], test_evidence(hour - 1))
    assert a["implementation_id"] == TRACKER_VERSION and not a["attempts"]
    assert b["implementation_id"] == RESET_TRACKER_VERSION
    assert b["attempts"][0]["status"] == "follow-up supported"
    assert b["attempts"][0]["supported_at"] == 7


def test_unresolved_comparison_creates_no_live_requests_and_deadline_does_not_move(monkeypatch):
    c, rt, d = prepared()
    chooser = Investigator(c.investigation_policy, c.service_policy)
    monkeypatch.setattr(
        "methane.services.investigator.compare",
        lambda *a, **k: dict(status="incomplete", strategies={}, reason="No incumbent"),
    )
    forecast = dict(pv_kw=[750] * 12)
    original = copy.deepcopy(rt.public())
    r = chooser.step(
        rt, d, c.plant, State.initial(c.plant), forecast, 225, c.costs, c.service_economics
    )
    assert r["episodes"][0]["status"] == "selection unresolved"
    assert not rt.orders and rt.public() == original
    r2 = chooser.step(
        rt, d, c.plant, State.initial(c.plant), forecast, 225, c.costs, c.service_economics
    )
    assert r2["episodes"][0]["due_hour"] == r["episodes"][0]["due_hour"]


@pytest.fixture(scope="module")
def observed_case():
    c = config(mode="inspect-first")
    return run(c, weather=weather_for(c, "successful-procedure"), strategies=[CONTROLLER])


def test_actual_finding_precedes_reset_and_completed_read_is_not_recovery(observed_case):
    r = observed_case
    assert r["status"] == "complete", r["failures"]
    rows = r["records"][CONTROLLER]
    orders = rows[-1]["field_operations"]["state"]["orders"]
    read = next(o for o in orders if o["kind"] == "inspection")
    reset = next(o for o in orders if o["kind"] == "reset")
    assert reset["followup_of"] == read["id"]
    before = rows[int(reset["created_hour"]) - 1]["decision"]["service_control"]["investigation"]
    assert before["episodes"][-1]["status"] != "observer confirmed"
    decision = rows[int(reset["created_hour"])]["decision"]["service_control"]["investigation"]
    finding = decision["episodes"][-1]["finding"]
    assert finding["quality"] == "usable" and finding["value"] is True
    assert all(x["available_at"] <= reset["created_hour"] for x in finding["channels"])
    assert not any(o["id"].startswith("proposal") for o in orders)
    assert {o["reader"] for o in orders if o["kind"].startswith("inspection")} == {"fixed"}
    assert all("investigation" in row["decision"]["service_control"] for row in rows)


def test_actual_run_physics_and_original_frozen_policy_are_recorded(observed_case):
    from methane.reference import audit

    assert audit(observed_case)["passed"]
    stored = observed_case["config"]["investigation_policy"]
    assert stored == asdict(config(mode="inspect-first").investigation_policy)


def test_display_keeps_summary_and_pointer_without_repeating_branch_payloads(observed_case):
    from methane.ui import service_decision_view

    full = next(
        r["decision"]["service_control"]
        for r in observed_case["records"][CONTROLLER]
        if r["decision"]["service_control"]["investigation"]["episodes"]
    )
    before = copy.deepcopy(full)
    view = service_decision_view(full, "/original/decision")
    selection = view["investigation"]["episodes"][0]["selection"]
    assert "comparison" not in selection and "inputs" not in selection
    assert selection["selected"]["strategy"] == "inspect-first"
    assert (
        selection["full_calculation_path"]
        == "/original/decision/investigation/episodes/0/selection"
    )
    assert full == before


def test_followup_changes_remedy_after_actual_failed_tests():
    from methane.reference import audit

    c = config(mode="inspect-first")
    c = replace(
        c,
        scenario=replace(c.scenario, hours=32),
        service_policy=replace(c.service_policy, maximum_wait_hours=24),
        faults=replace(c.faults, capacity_cause="equipment-damage", contact_stuck="closed"),
    )
    result = run(c, weather=weather_for(c, "successful-procedure"), strategies=[CONTROLLER])
    assert result["status"] == "complete", result["failures"]
    rows = result["records"][CONTROLLER]
    orders = rows[-1]["field_operations"]["state"]["orders"]
    reset = next(o for o in orders if o["kind"] == "reset")
    replacement = next(o for o in orders if o["kind"] == "module-replacement")
    assert replacement["followup_of"] == reset["id"]
    original = rows[int(replacement["created_hour"])]["decision"]["service_control"][
        "investigation"
    ]["episodes"][-1]
    tests = original["post_service_evidence"]
    assert tests["order_id"] == reset["id"]
    assert tests["status"] == "follow-up supported"
    assert all(q["available_at"] <= replacement["created_hour"] for q in tests["qualifying"])
    assert len(tests["qualifying"]) >= c.sensors.confirmation_hours
    assert original["due_hour"] == original["created_hour"] + c.service_policy.maximum_wait_hours
    assert "no longer applicable" in original["belief_after_intervention"]
    assert audit(result)["passed"]
