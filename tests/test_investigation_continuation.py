"""Actual finding-to-work handoffs and post-return tests, without outcome truth."""

import copy
import json
from dataclasses import replace

import pytest

from methane.physics import State
from methane.recovery import JOINT_VERSION
from methane.services.continuation import Continuation, completion, promote
from methane.services.coupling import identity
from methane.services.investigation_runs import CONTROLLER, fixture, weather_for
from methane.services.investigator import CONTINUATION_VERSION
from methane.services.planning import Commitment
from methane.services.snapshot import RecordedServices, capture
from methane.simulation import run


def inputs():
    cases = [
        dict(
            branch_id=name,
            finding="closed",
            probability=probability,
            requested_remedy="reset",
            test_start_hour=4,
            test_end_hour=6,
            test_target_kw=270,
            restoration_hypothesis=restored,
        )
        for name, probability, restored in (("trip", 0.5, True), ("stuck", 0.2, False))
    ]
    episode = dict(
        id="INV-1",
        due_hour=14,
        selected_strategy="inspect-first",
        selection=dict(
            selection_id="original-comparison",
            comparison=dict(strategies={"inspect-first": dict(cases=cases)}),
        ),
    )
    order = dict(
        id="reset-1",
        kind="reset",
        investigation_id="INV-1",
        created_hour=3,
        status="queued",
        followup_of="read-1",
    )
    evidence = dict(
        at_hour=3,
        finding=dict(
            quality="usable",
            value=True,
            channels=[dict(quality="usable", measured_at=2.5, available_at=3)],
        ),
    )
    return episode, order, evidence


def promoted():
    e, o, ev = inputs()
    return promote(e, o, finding="closed", evidence=ev, test_hours=2, test_target_kw=270)


def test_consensus_retains_both_latent_outcomes_and_original_prediction():
    e, o, ev = inputs()
    before = copy.deepcopy((e, o, ev))
    t = promote(e, o, finding="closed", evidence=ev, test_hours=2, test_target_kw=315)
    assert t.branch_ids == ("trip", "stuck")
    assert t.test_target_kw == 270 and t.predicted_test_start == 4
    assert t.created_hour == 3 and t.due_hour == 14
    assert Continuation.from_dict(json.loads(json.dumps(t.to_dict()))) == t
    assert (e, o, ev) == before
    e["selection"]["comparison"]["strategies"]["inspect-first"]["cases"][1]["test_start_hour"] = 5
    with pytest.raises(ValueError, match="unanimous"):
        promote(e, o, finding="closed", evidence=ev, test_hours=2, test_target_kw=270)


@pytest.mark.parametrize(
    "change",
    [
        "future reading",
        "future availability",
        "different finding",
        "missing evidence",
        "future request",
        "expired deadline",
    ],
)
def test_unavailable_or_unsupported_handoffs_are_rejected(change):
    e, o, ev = inputs()
    if change == "future reading":
        ev["finding"]["channels"][0]["measured_at"] = 4
    elif change == "future availability":
        ev["finding"]["channels"][0]["available_at"] = 4
    elif change == "different finding":
        ev["finding"]["value"] = False
    elif change == "missing evidence":
        ev["finding"]["channels"] = []
    elif change == "future request":
        o["created_hour"] = 4
    else:
        e["due_hour"] = 3
    with pytest.raises(ValueError):
        promote(e, o, finding="closed", evidence=ev, test_hours=2, test_target_kw=270)


def test_followup_requires_actual_interruption_or_distinct_eligible_shortfalls():
    e, o, ev = inputs()
    previous = dict(o)
    o.update(id="replacement-2", kind="module-replacement", followup_of=previous["id"])
    ev.update(preceding_order=previous)

    def make():
        return promote(
            e,
            o,
            finding="observed-follow-up",
            evidence=ev,
            test_hours=2,
            test_target_kw=315,
            followup=True,
        )

    with pytest.raises(ValueError, match="Follow-up requires"):
        make()
    previous["status"] = "failed"
    t = make()
    assert t.origin == "observed-follow-up" and t.branch_ids == ()
    assert t.predicted_test_start is None and t.test_target_kw == 315
    previous["status"] = "awaiting verification"
    ev["post_service"] = dict(
        order_id=previous["id"],
        status="follow-up supported",
        supported_at=3,
        qualifying=[
            dict(evidence_id=f"test-{h}", hour=h, available_at=h + 1, outcome="tracking shortfall")
            for h in (1, 2)
        ],
    )
    assert make().origin == "observed-follow-up"
    ev["post_service"]["qualifying"][1]["available_at"] = 4
    with pytest.raises(ValueError, match="Follow-up requires"):
        make()


def test_bounded_comparison_preserves_common_requested_test_load():
    from test_investigation_planning import fixture as planning_fixture
    from test_visit_planning import forecast

    from methane.services.investigation_belief import illustrative
    from methane.services.investigation_planning import compare

    c, rt = planning_fixture()
    key = next(o["id"] for o in rt.orders if o["kind"] == "inspection")
    r = compare(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(12),
        225,
        c.costs,
        illustrative(),
        key,
        c.service_economics,
        seconds=2,
        test_target_kw=270,
    )
    assert r["status"] == "complete", r
    assert r["implementation_id"] == "inspection-contingency-planning/2"
    for arm in r["strategies"].values():
        for case in arm["cases"]:
            assert case["test_target_kw"] == 270
            branch = next(
                b for b in arm["process"]["branches"] if b["branch_id"] == case["branch_id"]
            )
            for h in range(case["test_start_hour"], case["test_end_hour"]):
                assert branch["requested_actions"][h]["electrolyser_kw"] == pytest.approx(270)
                assert branch["actions"][h]["electrolyser_kw"] == pytest.approx(
                    270 if case["restoration_hypothesis"] else 225
                )


def test_completion_includes_later_shared_jobs_and_observed_return_in_saved_context():
    from test_visit_planning import repair_fixture

    from methane.faults import FaultState

    c, rt, d = repair_fixture()
    repair = next(o for o in rt.orders if o["kind"] == "module-replacement")
    repair["investigation_id"] = "INV-1"
    keys = (repair["id"], *(o["id"] for o in rt.orders if o["id"] != repair["id"]))
    visit, _ = rt.propose_visit(keys, starting_at=0)
    t = replace(promoted(), work_order_id=repair["id"], action="module-replacement", created_hour=0)
    commitments = tuple(Commitment(p) for p in visit.members)
    r = completion(rt, t, commitments, [visit])
    assert r["boundary"] >= visit.ending_at
    assert "later jobs" in r["basis"]
    with pytest.raises(ValueError, match="neither"):
        completion(rt, t, ())
    rt.dispatch_selected((), charge=False, visit_groups=((keys, 0),))
    faults = FaultState(c.plant, c.scenario, c.faults)
    for h in range(r["boundary"]):
        if h:
            rt.prepare(h, d, 750)
            rt.dispatch_selected((), charge=False)
        rt.end(h, faults, d)
    rt.prepare(r["boundary"], d, 750)
    packet = capture(rt)
    restored = RecordedServices(
        **dict(snapshot=packet["snapshot"], definitions=packet["catalogue"])
    )
    assert completion(restored, t, ()) == completion(rt, t, ())
    assert completion(restored, t, ())["boundary"] == r["boundary"]
    # Older archives have no return receipt; no history is manufactured from a planned route.
    old = copy.deepcopy(packet["snapshot"])
    old.update(schema_version="service-planning-snapshot/2")
    old.pop("observed_visits")
    old.pop("observed_orders")
    old["snapshot_id"] = identity({k: v for k, v in old.items() if k != "snapshot_id"})
    older = RecordedServices(old, packet["catalogue"])
    with pytest.raises(ValueError, match="neither|observably returned"):
        completion(older, t, ())
    # Even a correctly hashed snapshot cannot claim a future return as an observation.
    invalid = copy.deepcopy(packet["snapshot"])
    invalid["observed_visits"][0]["returned_at"] = r["boundary"] + 1
    invalid["snapshot_id"] = identity({k: v for k, v in invalid.items() if k != "snapshot_id"})
    with pytest.raises(ValueError, match="future observed return"):
        RecordedServices(invalid, packet["catalogue"])


@pytest.fixture(scope="module")
def actual_run():
    c = fixture("trip-inspect")
    c = replace(
        c,
        scenario=replace(c.scenario, hours=24),
        investigation_policy=replace(c.investigation_policy, version=CONTINUATION_VERSION),
        recovery_policy=replace(c.recovery_policy, version=JOINT_VERSION),
    )
    return run(c, weather=weather_for(c, "successful-procedure"), strategies=[CONTROLLER])


def test_actual_finding_commissions_work_before_accepting_its_test(actual_run):
    from methane.reference import audit

    assert actual_run["status"] == "complete", actual_run["failures"]
    assert audit(actual_run)["passed"]
    rows = actual_run["records"][CONTROLLER]
    nominated = [
        r for r in rows if r["decision"]["service_control"]["investigation"]["test_obligation"]
    ]
    assert nominated
    for row in nominated:
        inv = row["decision"]["service_control"]["investigation"]
        obligation = inv["test_obligation"]
        assert not inv["episodes"][-1].get("continuation_error")
        assert all(
            c["available_at"] <= obligation["created_hour"]
            for c in json.loads(obligation["evidence_json"])["finding"]["channels"]
        )
        test = inv["episodes"][-1].get("accepted_test")
        if test:
            assert test["start_hour"] >= test["not_before_hour"]
            assert test["end_hour"] <= test["due_hour"] <= obligation["due_hour"]
        assert obligation["due_hour"] == inv["episodes"][-1]["due_hour"]
    assert (
        rows[-1]["decision"]["service_control"]["investigation"]["episodes"][-1]["status"]
        == "observer confirmed"
    )


def test_policy_requires_joint_scheduler_and_default_absence_survives():
    from methane.config import Config

    c = fixture("trip-inspect")
    with pytest.raises(ValueError, match="joint"):
        replace(
            c, investigation_policy=replace(c.investigation_policy, version=CONTINUATION_VERSION)
        )
    assert "investigation_policy" not in Config().to_dict()


def test_original_information_alternatives_keep_the_work_return_prerequisite(actual_run):
    from methane.services import alternatives
    from methane.simulation import what_if

    original = copy.deepcopy(actual_run)
    row = next(
        r
        for r in actual_run["records"][CONTROLLER]
        if r["decision"]["service_control"]["investigation"]["test_obligation"]
        and r["decision"]["recovery_planning"]["status"] == "scheduled"
    )
    saved = row["decision"]["recovery_planning"]
    packet = alternatives.prepare(actual_run, CONTROLLER, row["hour"])
    assert packet["recovery_request"]["continuation"] == saved["request"]["continuation"]
    alternative = alternatives._evaluate(packet, packet["original_schedule"], packet["targets"])
    assert alternative["state"] == "feasible", alternative["constraints"]
    assert (
        alternative["recovery_planning"]["inputs"]["not_before_hour"]
        == saved["inputs"]["not_before_hour"]
    )
    assert alternative["recovery_planning"]["selected_start"] == saved["selected_start"]
    process = what_if(actual_run, CONTROLLER, row["hour"], "battery")["alternative_plan"]
    assert process["actions"], process["solver"]
    assert (
        process["recovery_planning"]["inputs"]["not_before_hour"]
        == saved["inputs"]["not_before_hour"]
    )
    assert actual_run == original
