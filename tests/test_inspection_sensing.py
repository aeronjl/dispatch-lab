"""Referenced inspection: arithmetic, missing evidence and causal decisions."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Config, Plant, Scenario
from methane.faults import FaultPolicy, FaultState
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.services.contracts import Context, Reading
from methane.services.inspection import classify, evidence, noise, sample
from methane.services.inspection_demo import execute, fixture


@pytest.fixture(scope="module")
def cases():
    return {
        k: execute(fixture(k))
        for k in (
            "trip",
            "reader-drift",
            "reader-dropout",
            "shared-contact",
            "changed-contact",
            "late-evidence",
            "communications",
        )
    }


def services(result):
    return [r["field_operations"] for r in result["records"]["Greedy"]]


def test_reference_correction_and_decision_bands_match_independent_arithmetic():
    o = ServiceSystem(inspection_model="referenced-contact/1")
    expected = Decimal(24) * (Decimal(20) - 1) / (Decimal(25) - 1)
    result = classify(20, 1, 25, o)
    assert result["corrected_v"] == float(expected) == 19 and result["value"] is True
    for a, value in ((6, False), (18, True), (12, None)):
        assert classify(a, 0, 24, o)["value"] is value
    assert classify(27, 3, 27, o)["quality"] == "uncertain"
    assert classify(24, 0, 0, o)["corrected_v"] is None
    assert classify(None, 0, 24, o)["quality"] == "unavailable"


def test_named_noise_has_no_dependence_on_another_reader_or_task_draw():
    before = noise(42, "fixed", 2.5, "signal", 0.1)
    for n in range(100):
        noise(n, "mobile", 8, "span", 3)
    assert noise(42, "fixed", 2.5, "signal", 0.1) == before
    assert noise(42, "mobile", 2.5, "signal", 0.1) != before


def test_physical_drift_is_continuous_and_contact_fault_persists_through_reset():
    f = FaultState(
        Plant(),
        Scenario(fault_start_hour=0, capacity_fraction=0.5),
        FaultPolicy(
            capacity_cause="resettable-trip", fixed_reader_drift_vph=1, contact_stuck="closed"
        ),
    )
    assert f.inspection_signal(2, "fixed", 2.5)["offset_v"] == 2.5
    f.service("reset", 2, True)
    assert f.truth(3)["capacity_kw"] == 450
    assert f.inspection_signal(300, "mobile")["signal_v"] == 24


def test_packets_publish_after_delay_and_do_not_become_fresh_when_read_again():
    o = ServiceSystem(
        inspector="fixed",
        inspection_model="referenced-contact/1",
        inspection_noise_v=0,
        inspection_delay_hours=1.25,
        contact_max_age_hours=1,
    )
    packets, _ = sample(
        dict(signal_v=24, offset_v=0, dropout=False, contact_stuck="none"),
        "fixed",
        2.5,
        "SVC-1",
        42,
        o,
    )
    assert all(r.available_at == 4 for r in packets)
    with pytest.raises(ValueError, match="unavailable"):
        Context(3, packets)
    orders = [dict(id="SVC-1", kind="inspection", reader="fixed", created_hour=1, incident=1)]
    report = evidence(Context(4, packets), o, orders)
    assert report["channels"][0]["quality"] == "stale" and report["value"] is None


def test_dual_reference_disagreement_stays_ambiguous():
    o = ServiceSystem(
        inspector="both", inspection_model="referenced-contact/1", inspection_noise_v=0
    )
    packets = []
    orders = []
    for reader, v, kind in (("fixed", 24, "inspection"), ("mobile", 0, "inspection-confirm")):
        readings, _ = sample(dict(signal_v=v, offset_v=0, dropout=False), reader, 1, reader, 42, o)
        packets.extend(readings)
        orders.append(dict(id=reader, kind=kind, reader=reader, created_hour=0, incident=1))
    r = evidence(Context(1, tuple(packets)), o, orders)
    assert r["quality"] == "uncertain" and r["value"] is None and "disagree" in r["reason"]


def test_contact_between_bands_is_not_a_failed_reader_reference():
    o = ServiceSystem(
        inspector="both", inspection_model="referenced-contact/1", inspection_noise_v=0
    )
    packets, orders = [], []
    for reader, v, kind in (("fixed", 12, "inspection"), ("mobile", 24, "inspection-confirm")):
        readings, _ = sample(dict(signal_v=v, offset_v=0, dropout=False), reader, 1, reader, 42, o)
        packets.extend(readings)
        orders.append(dict(id=reader, kind=kind, reader=reader, created_hour=0, incident=1))
    report = evidence(Context(1, tuple(packets)), o, orders)
    assert report["quality"] == "uncertain" and report["value"] is None
    assert report["isolated_readers"] == []
    assert all(c["reference_ok"] for c in report["channels"])
    assert "between decision bands" in report["reason"]


@pytest.mark.parametrize("delay", [0, 3])
def test_recorded_intervention_invalidates_even_a_delayed_preprocedure_sample(delay):
    o = ServiceSystem(
        inspector="fixed",
        inspection_model="referenced-contact/1",
        inspection_noise_v=0,
        inspection_delay_hours=delay,
    )
    packets, _ = sample(dict(signal_v=24, offset_v=0, dropout=False), "fixed", 1, "old", 42, o)
    cutoff = Reading("contact-evidence-cutoff", 2.25, "h", 4, 4, "recorded-contact-procedure/1")
    orders = [dict(id="old", kind="inspection", reader="fixed", created_hour=0, incident=1)]
    report = evidence(Context(4, (*packets, cutoff)), o, orders)
    assert report["invalidated_through_hour"] == 2.25
    assert report["quality"] == "uncertain" and report["value"] is None
    assert report["channels"][0]["quality"] == "stale"
    assert report["channels"][0]["acquisition_quality"] == "usable"
    assert report["isolated_readers"] == []


def test_reset_invalidates_contact_evidence_without_repairing_the_reader(cases):
    rows = services(cases["reader-drift"])
    first = next(
        r for r in rows if r["state"]["inspection"]["invalidated_through_hour"] is not None
    )
    assert first["decision"]["inspection"]["quality"] == "usable"
    after = first["state"]["inspection"]
    assert after["quality"] == "uncertain" and after["value"] is None
    assert all(c["quality"] == "stale" for c in after["channels"])
    assert after["isolated_readers"] == ["fixed"]
    assert audit(cases["reader-drift"])["passed"]


def test_reader_drift_and_dropout_are_isolated_without_changing_plant_estimate_directly(cases):
    for case in ("reader-drift", "reader-dropout"):
        rows = services(cases[case])
        reports = [r["state"]["inspection"] for r in rows]
        paired = next(r for r in reports if r["quality"] == "usable")
        assert paired["isolated_readers"] == ["fixed"]
        assert paired["value"] is True and paired["channels"][1]["quality"] == "usable"
        resets = [m for r in rows for m in r["new_missions"] if m["order"]["action"] == "reset"]
        assert len(resets) == 1
        assert resets[0]["starting_at"] >= paired["channels"][1]["available_at"]
        assert all("inspection_samples" not in r for r in rows)
        assert all("fixed_reader_drift_vph" not in str(r["decision"]) for r in rows)
        assert audit(cases[case])["passed"]


def test_old_contact_evidence_does_not_trigger_substitution_during_consistent_reset_recovery(cases):
    for case in ("trip", "reader-drift", "reader-dropout"):
        assert not any(
            q["kind"] == "module-replacement" for q in services(cases[case])[-1]["state"]["orders"]
        )


def test_shared_contact_failure_survives_reset_and_requires_process_evidence_for_escalation(cases):
    result = cases["shared-contact"]
    rows = services(result)
    first = next(r for r in rows if r["state"]["inspection"]["quality"] == "usable")
    assert first["state"]["inspection"]["value"] is True
    assert first["state"]["inspection"]["isolated_readers"] == []
    reset = next(
        e
        for r in result["retrospective_truth_by_controller"]["Greedy"]
        for e in r["service_effects"]
        if e["kind"] == "reset"
    )
    assert reset["before"]["capacity_kw"] == reset["after"]["capacity_kw"] == 225
    replacement = next(
        q for r in rows for q in r["state"]["orders"] if q["kind"] == "module-replacement"
    )
    assert "Post-reset informative tracking" in replacement["reason"]
    assert replacement["created_hour"] > reset["effective_at_hour"]
    assert audit(result)["passed"]


def test_changed_contact_has_different_acquisition_times_and_does_not_select_reset(cases):
    rows = services(cases["changed-contact"])
    report = next(
        r["state"]["inspection"] for r in rows if "disagree" in r["state"]["inspection"]["reason"]
    )
    assert report["channels"][0]["measured_at"] < report["channels"][1]["measured_at"]
    assert not any(r["reset_attempts"] for r in rows)
    assert audit(cases["changed-contact"])["passed"]


def test_delayed_stale_or_blocked_inspection_keeps_unresolved_evidence_and_wait_limit(cases):
    for case in ("late-evidence", "communications"):
        rows = services(cases[case])
        jobs = rows[-1]["state"]["orders"]
        first = min(q["created_hour"] for q in jobs if q["kind"] == "inspection")
        replacement = next(q for q in jobs if q["kind"] == "module-replacement")
        assert replacement["created_hour"] >= first + 8
        assert not any(r["reset_attempts"] for r in rows)
        assert audit(cases[case])["passed"]


def test_future_reader_fault_does_not_change_earlier_decisions_or_public_observations():
    base = fixture("trip")
    base = replace(base, scenario=replace(base.scenario, hours=12))
    configs = [
        replace(
            base, faults=replace(base.faults, inspection_fault_start_hour=t, contact_stuck="open")
        )
        for t in (8, 100)
    ]
    a, b = (execute(c) for c in configs)
    for x, y in zip(a["records"]["Greedy"][:8], b["records"]["Greedy"][:8], strict=True):
        assert x["decision"] == y["decision"]
        assert x["field_operations"]["decision"] == y["field_operations"]["decision"]
        assert (
            x["field_operations"]["state"]["executive"]["observations"]
            == y["field_operations"]["state"]["executive"]["observations"]
        )


@pytest.mark.parametrize(
    "mutation",
    [
        "raw",
        "classification",
        "early-publication",
        "display",
        "fusion",
        "omitted-packet",
        "intervention-cutoff",
        "preprocedure-as-current",
        "reader-reference",
    ],
)
def test_independent_checker_rejects_forged_measurements_and_explanations(cases, mutation):
    result = copy.deepcopy(cases["reader-drift"])
    truth = next(
        r for r in result["retrospective_truth_by_controller"]["Greedy"] if r["inspection_samples"]
    )
    row = services(result)[truth["hour"]]
    trace = truth["inspection_samples"][0]
    if mutation == "raw":
        trace["raw_v"]["signal"] += 10
    if mutation == "classification":
        trace["interpretation"]["value"] = True
    if mutation == "early-publication":
        trace["available_at"] -= 1
    if mutation == "display":
        row["state"]["inspection"]["channels"][0]["raw_v"]["zero"] = 0
    if mutation == "fusion":
        row["state"]["inspection"]["value"] = True
    if mutation == "omitted-packet":
        truth["inspection_samples"] = []
    if mutation in ("intervention-cutoff", "preprocedure-as-current"):
        report = next(
            r["state"]["inspection"]
            for r in services(result)
            if r["state"]["inspection"]["invalidated_through_hour"] is not None
        )
        if mutation == "intervention-cutoff":
            report["invalidated_through_hour"] = None
        else:
            report["channels"][1].update(quality="usable", value=True)
    if mutation == "reader-reference":
        trace["interpretation"]["reference_ok"] = True
    assert not audit(result)["passed"]


def test_configuration_and_economic_limits_are_explicit(cases):
    with pytest.raises(ValueError, match="Paired inspection"):
        ServiceSystem(inspector="both")
    with pytest.raises(ValueError, match="Referenced reader faults"):
        Config(faults=FaultPolicy(fixed_reader_dropout=True))
    with pytest.raises(ValueError, match="thresholds"):
        ServiceSystem(inspection_low_v=19, inspection_high_v=18)
    with pytest.raises(ValueError, match="finite"):
        FaultPolicy(fixed_reader_offset_v=float("nan"))
    prices = cases["trip"]["metrics"]["Greedy"]["field_operations"]
    unpriced = {r["quantity"]: r["amount"] for r in prices["unpriced"]}
    assert (
        unpriced["internal_reader_references"] == 2
        and unpriced["prepared_contact_test_interface"] == 1
    )
    assert "fixed_reader" in prices["components"] and "rover" in prices["components"]
