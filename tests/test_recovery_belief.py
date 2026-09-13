"""Independent Bayes/transition arithmetic and causal procedure/test boundaries."""

import copy
import math
from dataclasses import asdict, replace
from fractions import Fraction

import pytest

from methane.config import Plant, Scenario, Sensors
from methane.faults import FaultPolicy, FaultState
from methane.physics import ACTION_KEYS, State
from methane.services.configuration import ServiceSystem
from methane.services.contracts import Context, Reading
from methane.services.inspection import sample
from methane.services.investigation_belief import Assumptions, Hypothesis, illustrative
from methane.services.recovery_belief import (
    Procedure,
    RecoveryBelief,
    contact_likelihood,
    log_power_likelihood,
)
from methane.services.verification import assess


def options(**kw):
    return ServiceSystem(inspection_model="referenced-contact/1", inspection_noise_v=0, **kw)


def contact(signal=24, at=1, *, available=None, reader="fixed", opts=None):
    readings, _ = sample(
        dict(signal_v=signal, offset_v=0, dropout=False),
        reader,
        at,
        "test-" + str(at),
        7,
        opts or options(),
    )
    return (
        tuple(replace(r, available_at=available) for r in readings)
        if available is not None
        else readings
    )


def make(*, prior=None, noise=0, chance=0.8, capacity=225, opts=None):
    return RecoveryBelief(
        prior or illustrative(),
        Plant(),
        Sensors(noise_fraction=noise),
        opts or options(),
        capacity,
        chance,
    )


def test_packet(hour, power, *, requested=450, noise=0, pv=750):
    plant = Plant()
    flow = power / plant.specific_energy_kwh_per_kg
    packet = dict(
        hour=hour,
        available_at=hour + 1,
        probe=True,
        capacity_estimate_kw=225,
        estimate=asdict(replace(State.initial(plant), h2_kg=10)),
        request={**dict.fromkeys(ACTION_KEYS, 0), "electrolyser_kw": requested},
        current=dict(pv_kw=pv, ambient_c=20, delivery_kg=0, service_kw=0, isolated=False),
        prior_inventory_kg=10,
        observations=dict(
            power_kw=power, h2_inventory_kg=10 + flow, h2_outflow_kg=0, hydrogen_flow_kg=flow
        ),
    )
    return assess(plant, Sensors(noise_fraction=noise), packet)


test_packet.__test__ = False


def probability(result, hypothesis, restored):
    return next(
        r["probability"]
        for r in result["posterior"]
        if (r["hypothesis"], r["restored"]) == (hypothesis, restored)
    )


def test_reset_transition_keeps_common_contact_error_and_does_not_verify_capacity():
    f = make()
    old = f.advance(Context(1, contact()))
    before = copy.deepcopy(old)
    assert probability(old, "latch", False) == pytest.approx(float(Fraction(5, 7)))
    r = f.advance(Context(3, ()), [Procedure("reset-1", "reset", 2.5)])
    assert r["restoration_probability"] == pytest.approx(float(Fraction(4, 7)))
    assert probability(r, "latch", False) == pytest.approx(float(Fraction(1, 7)))
    assert probability(r, "shared-contact", False) == pytest.approx(float(Fraction(2, 7)))
    # A still-closed contact permits an unsuccessful reset OR a stuck contact.
    r = f.advance(Context(4, contact(at=3.5)))
    assert r["restoration_probability"] == 0
    assert probability(r, "latch", False) == pytest.approx(float(Fraction(1, 3)))
    assert probability(r, "shared-contact", False) == pytest.approx(float(Fraction(2, 3)))
    assert old == before and "capacity_kw" not in r and "confirmed" not in r


def test_module_transition_then_actual_power_distinguishes_restoration_from_failed_work():
    prior = Assumptions((Hypothesis("stuck", "damage-and-stuck-contact", 1),), "assumption:stuck")
    f = make(prior=prior)
    r = f.advance(Context(2, ()), [Procedure("replace-1", "module-replacement", 1.5)])
    assert r["restoration_probability"] == pytest.approx(0.8)
    # The independent stuck contact is unchanged by module substitution.
    r = f.advance(Context(3, contact(at=2.5)))
    assert r["restoration_probability"] == pytest.approx(0.8)
    r = f.advance(Context(4, ()), test=test_packet(3, 225))
    assert r["restoration_probability"] == 0
    r = f.advance(Context(5, ()), [Procedure("replace-2", "module-replacement", 4.5)])
    assert r["restoration_probability"] == pytest.approx(0.8)
    r = f.advance(Context(6, ()), test=test_packet(5, 450))
    assert r["restoration_probability"] == pytest.approx(1)
    assert "capacity_kw" not in r  # This still does not upgrade the operating observer.


def test_delayed_information_conditions_its_original_state_without_rewriting_earlier_results():
    f = make()
    before = f.advance(Context(2, ()), [Procedure("reset", "reset", 1.5)])
    preserved = copy.deepcopy(before)
    assert before["restoration_probability"] == pytest.approx(0.4)
    after = f.advance(Context(3, contact(at=1, available=3)))
    assert after["restoration_probability"] == pytest.approx(4 / 7)
    assert [r["event"]["kind"] for r in after["history"]] == ["contact", "procedure"]
    assert before == preserved
    assert f.advance(Context(3, contact(at=1, available=3))) == after


def test_age_admission_differs_from_forgetting_already_admitted_evidence():
    f = make(opts=options(contact_max_age_hours=1))
    before = f.advance(Context(1, contact(at=1)))
    after = f.advance(Context(4, contact(at=1)))
    assert before["posterior"] == after["posterior"]
    unobserved = make(opts=options(contact_max_age_hours=1)).advance(Context(4, contact(at=1)))
    assert unobserved["status"] == "prior only"


def test_unknown_intervention_and_simultaneous_contact_are_explicit():
    cutoff = Reading("contact-evidence-cutoff", 1.5, "h", 2, 2, "observed-work")
    f = make()
    r = f.advance(Context(2, (cutoff,)))
    assert r["posterior"] is None and r["status"] == "unmodelled intervention"
    r = f.advance(Context(2, (*contact(at=1.5), cutoff)), [Procedure("reset", "reset", 1.5)])
    assert r["restoration_probability"] == pytest.approx(0.4)
    assert any("timestamp" in h.get("reason", "") and not h["used"] for h in r["history"])


def test_power_sensor_point_mass_density_and_extreme_tail_are_distinct():
    assert log_power_likelihood(225, 225, 0) == 0
    assert log_power_likelihood(0, 0, 0.02) == 0
    assert log_power_likelihood(450, 225, 0) == -math.inf
    assert log_power_likelihood(225, 225, 0.02) == pytest.approx(
        -math.log(4.5 * math.sqrt(2 * math.pi))
    )
    # Log of a tiny zero-clipping probability remains finite, not invented zero.
    assert -1260 < log_power_likelihood(0, 225, 0.02) < -1250
    assert log_power_likelihood(0, 225, 0.02) == log_power_likelihood(0, 450, 0.02)


def test_log_odds_survive_underflow_and_later_contradictory_measurements():
    f = make(
        prior=Assumptions((Hypothesis("damage", "equipment-damage", 1),), "assumption:damage"),
        noise=0.02,
        chance=0.5,
    )
    f.advance(Context(1, ()), [Procedure("replace", "module-replacement", 0.5)])
    r = f.advance(Context(2, ()), test=test_packet(1, 450, noise=0.02))
    bad = next(x for x in r["posterior"] if not x["restored"])
    assert bad["probability"] == 0 and not bad["impossible"] and bad["log_probability"] < -1000
    for h in (2, 3, 4):
        r = f.advance(Context(h + 1, ()), test=test_packet(h, 150, noise=0.02))
    # Gaussian log likelihood ratio: (1250-ln2) + 3*(-1250/3-ln2)
    # = -4ln2, giving odds 1:16, calculated independently of the filter.
    assert r["restoration_probability"] == pytest.approx(float(Fraction(1, 17)), abs=1e-10)


def test_infeasible_and_inactive_tests_add_no_health_evidence():
    f = make(chance=0.5)
    original = f.advance(Context(1, ()), [Procedure("replace", "module-replacement", 0.5)])
    r = f.advance(Context(2, ()), test=test_packet(1, 0, pv=1))
    assert r["posterior"] == original["posterior"]
    assert not r["history"][-1]["used"]


def test_future_or_tampered_inputs_are_rejected_without_partially_advancing():
    f = make()
    baseline = f.advance(Context(1, contact()))
    with pytest.raises(ValueError, match="future procedure"):
        f.advance(Context(2, ()), [Procedure("reset", "reset", 3)])
    assert f.advance(Context(1, contact())) == baseline
    with pytest.raises(ValueError, match="future operating"):
        f.advance(Context(2, ()), test=test_packet(2, 225))
    bad = test_packet(1, 225)
    bad["outcome"] = "tracking supported"
    with pytest.raises(ValueError, match="integrity"):
        f.advance(Context(2, ()), test=bad)
    assert f.advance(Context(1, contact())) == baseline
    with pytest.raises(ValueError, match="original complete reader"):
        f.advance(Context(2, contact(signal=0)))
    with pytest.raises(ValueError, match="original complete reader"):
        f.advance(Context(2, contact(available=2)))
    with pytest.raises(ValueError, match="never outcome"):
        f.advance(Context(2, ()), [dict(action="reset", successful=True)])


@pytest.mark.parametrize(
    "mechanism", ["resettable-trip", "equipment-damage", "damage-and-stuck-contact"]
)
@pytest.mark.parametrize("action", ["reset", "module-replacement"])
def test_conditioned_contact_prediction_matches_independent_fault_execution(mechanism, action):
    h = Hypothesis("known", mechanism, 1)
    for success in (False, True):
        policy = FaultPolicy(
            capacity_cause="resettable-trip"
            if mechanism == "resettable-trip"
            else "equipment-damage",
            contact_stuck="closed" if mechanism == "damage-and-stuck-contact" else "none",
        )
        state = FaultState(Plant(), Scenario(fault_start_hour=0, capacity_fraction=0.5), policy)
        state.service(action, 0, success)
        restored = state.truth(1)["capacity_kw"] == 450
        predicted = contact_likelihood(h, restored, "fixed", options(), 3)
        category = "closed" if state.inspection_signal(1, "fixed", 1.5)["signal_v"] else "open"
        assert predicted[category] == 1
