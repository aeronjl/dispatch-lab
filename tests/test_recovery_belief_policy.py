"""Actual work and operating evidence remain separate from conditional confidence."""

import copy
from dataclasses import replace

import pytest

from methane.recovery import JOINT_VERSION
from methane.recovery_belief_reference import audit_run, digest
from methane.reference import audit, check_actions, interval
from methane.services.investigation_runs import CONTROLLER, fixture, weather_for
from methane.services.investigator import BELIEF_VERSION
from methane.simulation import run


def configured():
    c = fixture("damage-inspect")
    return replace(
        c,
        scenario=replace(c.scenario, solver_seconds=2),
        investigation_policy=replace(c.investigation_policy, version=BELIEF_VERSION),
        recovery_policy=replace(c.recovery_policy, version=JOINT_VERSION),
    )


@pytest.fixture(scope="module")
def actual():
    c = configured()
    return run(c, weather=weather_for(c, "successful-procedure"), strategies=[CONTROLLER])


def episodes(result):
    return [
        (row, episode)
        for row in result["records"][CONTROLLER]
        for episode in row["decision"]["service_control"]["investigation"]["episodes"]
    ]


def test_attempt_test_and_operating_confirmation_are_distinct(actual):
    assert actual["status"] == "complete", actual["failures"]
    checks = audit(actual)
    assert checks["passed"], (checks["failures"], [c for c in checks["checks"] if not c["passed"]])
    pairs = episodes(actual)
    assert any(
        e["followup_belief_gate"]["eligible"] for _, e in pairs if e.get("followup_belief_gate")
    )
    replacement_hour = next(
        o["created_hour"]
        for o in actual["records"][CONTROLLER][-1]["field_operations"]["state"]["orders"]
        if o["kind"] == "module-replacement"
    )
    assert any(
        0 < e["recovery_belief"]["restoration_probability"] < 1
        for row, e in pairs
        if row["hour"] < replacement_hour
    )
    assert any(
        e["recovery_belief"]["restoration_probability"] == 0
        for row, e in pairs
        if row["hour"] <= replacement_hour and e.get("followup_belief_gate")
    )
    # A replacement's declared probability can reach one before real load tests
    # justify restoring the operating estimate; no fixed solver timing is asserted.
    assert any(
        e["recovery_belief"]["restoration_probability"] == 1
        and row["decision"]["diagnosis"]["capacity_kw"] < 450
        and e["status"] != "observer confirmed"
        for row, e in pairs
    )
    assert pairs[-1][1]["status"] == "observer confirmed"


def test_display_is_compact_and_original_evidence_remains_immutable(actual):
    from methane.ui import service_decision_view

    row, e = episodes(actual)[-1]
    control = row["decision"]["service_control"]
    original = copy.deepcopy(control)
    view = service_decision_view(control, "/recorded/service")
    belief = view["investigation"]["episodes"][-1]["recovery_belief"]
    assert "history" not in belief and "posterior" not in belief
    assert belief["belief_id"] == e["recovery_belief"]["belief_id"]
    assert belief["full_calculation_path"].endswith("/recovery_belief")
    assert control == original


def test_per_controller_policy_is_the_original_dispatch_assumption(actual):
    # An explicit controller override can differ from the setup default. The
    # checker must follow captured controller policy, not infer it from setup.
    changed = copy.deepcopy(actual)
    changed["config"].pop("investigation_policy")
    checks = audit_run(changed, interval, check_actions)
    assert checks and all(c["passed"] for c in checks)
    changed["records"][CONTROLLER][0]["decision"]["service_control"].pop("investigation")
    assert any(not c["passed"] for c in audit_run(changed, interval, check_actions))


@pytest.mark.parametrize("mutation", ["operating packet", "procedure", "contact", "gate"])
def test_independent_checker_rejects_resealed_original_information_tampering(actual, mutation):
    changed = copy.deepcopy(actual)
    row, e = next((r, e) for r, e in episodes(changed) if e.get("followup_belief_gate"))
    belief = e["recovery_belief"]
    if mutation == "operating packet":
        event = next(h["event"] for h in belief["history"] if h["event"]["kind"] == "power")
        event["evidence"]["inputs"]["packet"]["estimate"]["battery_kwh"] += 1
    elif mutation == "procedure":
        event = next(h["event"] for h in belief["history"] if h["event"]["kind"] == "procedure")
        event["procedure"]["order_id"] = "unobserved-attempt"
    elif mutation == "contact":
        event = next(h["event"] for h in belief["history"] if h["event"]["kind"] == "contact")
        event["packet"]["operands_v"]["signal"] += 0.01
    else:
        e["followup_belief_gate"]["eligible"] = False
    belief["belief_id"] = digest({k: v for k, v in belief.items() if k != "belief_id"})
    checks = audit_run(changed, interval, check_actions)
    assert any(not c["passed"] for c in checks)


def test_future_realised_weather_cannot_change_earlier_beliefs(actual):
    c = configured()
    weather = weather_for(c, "successful-procedure")
    for i, sample in enumerate(weather["truth"].values()):
        if i >= 20:
            sample.update(pv_kw=0, irradiance_wm2=0)
    changed = run(c, weather=weather, strategies=[CONTROLLER])
    assert changed["status"] == "complete", changed["failures"]
    for a, b in zip(
        actual["records"][CONTROLLER][:20], changed["records"][CONTROLLER][:20], strict=True
    ):
        assert a["requested"] == pytest.approx(b["requested"])
        assert a["decision"]["diagnosis"] == b["decision"]["diagnosis"]
        left = [
            e["recovery_belief"]
            for e in a["decision"]["service_control"]["investigation"]["episodes"]
        ]
        right = [
            e["recovery_belief"]
            for e in b["decision"]["service_control"]["investigation"]["episodes"]
        ]
        assert left == right
