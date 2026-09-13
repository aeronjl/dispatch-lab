"""Independent conditioning, execution mechanism checks and causal evidence epochs."""

from dataclasses import replace
from fractions import Fraction

import pytest

from methane.config import Plant, Scenario
from methane.faults import FaultPolicy, FaultState
from methane.services.configuration import ServiceSystem
from methane.services.contracts import Context, Reading
from methane.services.inspection import sample
from methane.services.investigation_belief import (
    MECHANISMS,
    Assumptions,
    Hypothesis,
    findings,
    illustrative,
    likelihood,
    update,
)


def options(**kw):
    return ServiceSystem(inspection_model="referenced-contact/1", inspection_noise_v=0, **kw)


def packet(signal=24, *, reader="fixed", at=1, o=None, dropout=False):
    return sample(
        dict(signal_v=signal, offset_v=0, dropout=dropout),
        reader,
        at,
        "sample-" + str(at),
        7,
        o or options(),
    )[0]


def test_contact_cannot_distinguish_latch_from_stuck_contact_or_upgrade_process_capacity():
    p = illustrative()
    o = options()
    ctx = Context(1, packet())
    r = update(p, ctx, o)
    assert r["posterior"] == pytest.approx(
        dict(latch=float(Fraction(5, 7)), damage=0, **{"shared-contact": float(Fraction(2, 7))})
    )
    assert r["status"] == "conditioned"
    assert "capacity_kw" not in r
    # Repeated display and duplicate transport copies do not reuse evidence.
    assert update(p, ctx, o) == r
    assert update(p, Context(1, (*ctx.readings, *ctx.readings)), o) == r
    # A second agreeing reader still cannot rule out the common contact error.
    both = update(p, Context(1, (*ctx.readings, *packet(reader="mobile"))), o)
    assert both["posterior"] == r["posterior"] and len(both["evidence"]) == 2


def test_future_finding_branches_have_independent_bayes_weights_and_explicit_timing():
    o = options(inspection_delay_hours=1.25)
    belief = update(illustrative(), Context(0, ()), o)
    r = findings(belief, "mobile", o, measured_at=2.5)
    closed, opened = r["branches"]
    assert closed["finding"] == "closed" and closed["probability"] == pytest.approx(0.7)
    assert closed["posterior"]["latch"] == pytest.approx(5 / 7)
    assert opened["finding"] == "open" and opened["probability"] == pytest.approx(0.3)
    assert closed["available_at"] == 4 and closed["context"] == "prediction"
    assert closed["permitted_contact_reset"] and not opened["permitted_contact_reset"]
    assert sum(b["probability"] for b in r["branches"]) == pytest.approx(1)
    assert all(b["joint"]["shared-contact"] <= 0.2 for b in r["branches"])


def test_missing_old_or_pre_intervention_measurements_do_not_become_healthy_evidence():
    p = illustrative()
    o = options(contact_max_age_hours=1)
    early = packet(at=1, o=o)
    r = update(p, Context(3, early), o)
    assert r["status"] == "prior only" and r["observations"][0]["applicable"] is False
    cutoff = Reading("contact-evidence-cutoff", 1, "h", 2, 2, "observed-intervention")
    ctx = Context(2, (*early, cutoff))
    expired = update(p, ctx, o)
    assert expired["status"] == "prior requires renewal" and expired["posterior"] is None
    assert expired["since_hour"] == 1
    renewed = replace(p, epoch_start_hour=1, source="assumption:declared-after-intervention")
    assert update(renewed, ctx, o)["status"] == "prior only"
    assert renewed.assumption_id != p.assumption_id
    assert update(p, Context(1, early[:1]), o)["status"] == "prior only"
    with pytest.raises(ValueError, match="unavailable"):
        Context(0, early)
    delayed = options(inspection_delay_hours=3, contact_max_age_hours=1)
    b = update(p, Context(0, ()), delayed)
    outcomes = findings(b, "fixed", delayed, measured_at=0.5)["branches"]
    assert len(outcomes) == 1 and outcomes[0]["finding"] == "unusable"
    assert outcomes[0]["posterior"] == b["posterior"]
    assert not outcomes[0]["permitted_contact_reset"]


def test_unsupported_packet_does_not_get_an_arbitrary_probability_floor():
    o = options()
    p = illustrative()
    r = update(p, Context(1, packet(dropout=True)), o)
    assert r["status"] == "unsupported observation" and r["posterior"] is None
    assert r["evidence"][0]["predictive_probability"] == 0
    with pytest.raises(ValueError, match="Unsupported current evidence"):
        findings(r, "fixed", o, measured_at=2)
    # Explicit dropout hypotheses make that same measurement interpretable.
    p = Assumptions(
        (
            Hypothesis("reader-out", "equipment-damage", 0.25, fixed_dropout=True),
            Hypothesis("latch", "resettable-trip", 0.75),
        ),
        "assumption:reader-gap",
    )
    r = update(p, Context(1, packet(dropout=True)), o)
    assert r["posterior"] == {"reader-out": 1, "latch": 0}


@pytest.mark.parametrize("mechanism", list(MECHANISMS))
def test_hypothesis_restoration_matches_separate_execution_mechanism(mechanism):
    description = MECHANISMS[mechanism]
    p = Plant()
    s = Scenario(fault_start_hour=0, capacity_fraction=0.5)
    for action, expected in [
        ("reset", description["reset_restores"]),
        ("module-replacement", description["replacement_restores"]),
    ]:
        for procedure_passed in (True, False):
            faults = FaultPolicy(
                capacity_cause="resettable-trip"
                if mechanism == "resettable-trip"
                else "equipment-damage",
                contact_stuck="closed" if mechanism == "damage-and-stuck-contact" else "none",
            )
            state = FaultState(p, s, faults)
            assert state.inspection_signal(0, "fixed", 0.5)["signal_v"] == description["signal_v"]
            state.service(action, 0, procedure_passed)
            assert state.truth(1)["capacity_kw"] == p.electrolyser_kw * (
                1 if expected and procedure_passed else 0.5
            )


def test_likelihood_exposes_reference_rejection_and_finite_quadrature():
    h = Hypothesis("drift", "resettable-trip", 1, fixed_offset_v=3)
    assert likelihood(h, "fixed", options()) == dict(closed=0, open=0, unusable=1)
    assert likelihood(h, "mobile", options()) == dict(closed=1, open=0, unusable=0)
    noisy = replace(options(), inspection_noise_v=4)
    r = likelihood(Hypothesis("latch", "resettable-trip", 1), "fixed", noisy, 3)
    assert sum(r.values()) == pytest.approx(1)
    assert r["unusable"] > 0
    assert all(abs(v * 27 - round(v * 27)) < 1e-10 for v in r.values())


def test_conflicting_operands_bad_units_and_changed_belief_identity_are_rejected():
    rows = packet()
    with pytest.raises(ValueError, match="Conflicting"):
        update(illustrative(), Context(1, (*rows, replace(rows[0], value=0))), options())
    with pytest.raises(ValueError, match="volts"):
        update(illustrative(), Context(1, (replace(rows[0], unit="kW"), *rows[1:])), options())
    r = update(illustrative(), Context(0, ()), options())
    r["posterior"]["latch"] = 1
    with pytest.raises(ValueError, match="identity"):
        findings(r, "fixed", options(), measured_at=1)
