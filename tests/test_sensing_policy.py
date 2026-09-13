"""The ambiguity ablation changes one inference, not its available information."""

import copy
from dataclasses import asdict, replace
from decimal import Decimal

import pytest

from methane import studies
from methane.config import Config, Plant, Sensors
from methane.learning import evaluate
from methane.reference import ambiguous_capacity
from methane.sensing import Diagnosis, update


def readings(power=135, inflow=2, inventory=20):
    return {
        "power_kw": power,
        "hydrogen_flow_kg": power / 55,
        "h2_inventory_kg": inventory + inflow,
        "h2_outflow_kg": 0,
    }


def test_ambiguity_at_minimum_load_does_not_prove_a_new_capacity_ceiling():
    p, previous = Plant(), {"h2_inventory_kg": 20}
    # Rounded operands from the preserved hour-19 counterexample. The balance
    # differs from electrical flow, despite successful tracking at minimum load.
    observed = readings(power=137.66663791951325, inflow=2.2050299115304828)
    d = Diagnosis(218.2811476886853, incidents=1, active_incident=True)
    original = copy.deepcopy([d, previous, observed])
    old, old_incident, _ = update(p, Sensors(), d, previous, observed, 135)
    new, new_incident, event = update(
        p, Sensors(ambiguity_policy="retain-capacity/1"), d, previous, observed, 135
    )
    # Independent decimal arithmetic, not a call into the observer's residuals.
    limit = Decimal("137.66663791951325") * Decimal("0.90")
    assert old.capacity_kw == pytest.approx(float(limit))
    assert float(limit) < p.min_kw
    assert old.status == new.status == "ambiguous"
    assert new.capacity_kw == d.capacity_kw > p.min_kw
    assert not old_incident and not new_incident and event is None
    assert new.incidents == 1 and new.active_incident
    assert [d, previous, observed] == original
    old_state, new_state = asdict(old), asdict(new)
    for key in ("capacity_kw", "uncertainty"):
        old_state.pop(key)
        new_state.pop(key)
    assert old_state == new_state


@pytest.mark.parametrize("capacity", [0, 100, 225, 450])
@pytest.mark.parametrize("requested_kw", [0, 134, 135, 300])
def test_hold_is_not_recovery_and_low_excitation_stays_uninformative(capacity, requested_kw):
    d = Diagnosis(capacity, recovery_count=1, incidents=2, active_incident=True)
    result, incident, event = update(
        Plant(),
        Sensors(ambiguity_policy="retain-capacity/1"),
        d,
        {"h2_inventory_kg": 20},
        readings(power=requested_kw, inflow=15),
        requested_kw,
        probe=True,
        strict_probe=True,
        consecutive_probe_power=requested_kw,
    )
    assert result.capacity_kw == capacity
    assert not incident and event is None
    assert result.recovery_count == 0
    assert result.informative == (requested_kw >= 135)
    assert result.incidents == 2


@pytest.mark.parametrize("kind", ["capacity", "flow", "recovery", "normal", "disabled"])
def test_unambiguous_evidence_keeps_existing_confirmation_semantics(kind):
    d = Diagnosis(405 if kind == "recovery" else 450)
    pairs = [copy.deepcopy(d), copy.deepcopy(d)]
    previous = {"h2_inventory_kg": 0}
    for hour in range(4):
        power = 225 if kind == "capacity" else 450
        observation = readings(
            power=power, inflow=power / 55, inventory=previous["h2_inventory_kg"]
        )
        if kind == "flow":
            observation["hydrogen_flow_kg"] *= 1.5
        answers = []
        for index, policy in enumerate(("reduce-capacity/1", "retain-capacity/1")):
            answers.append(
                update(
                    Plant(),
                    Sensors(noise_fraction=0, enabled=kind != "disabled", ambiguity_policy=policy),
                    pairs[index],
                    previous,
                    observation,
                    450,
                    probe=kind == "recovery",
                    strict_probe=True,
                    consecutive_probe_power=450 if hour else None,
                )
            )
        assert answers[0] == answers[1]
        pairs = [answer[0] for answer in answers]
        previous = observation
    if kind == "capacity":
        assert pairs[0].capacity_kw == 225 and pairs[0].incidents == 1
    if kind == "flow":
        assert pairs[0].flow_isolated and pairs[0].incidents == 1
    if kind == "recovery":
        assert pairs[0].capacity_kw == 450


def test_version_is_frozen_without_changing_legacy_configurations():
    old = studies.protocol("field-recovery-tests")["reference_config"]
    assert "ambiguity_policy" not in old["sensors"]
    assert Config.from_dict(old).to_dict() == old
    new = replace(
        Config.from_dict(old),
        sensors=replace(Sensors(**old["sensors"]), ambiguity_policy="retain-capacity/1"),
    )
    assert new.to_dict()["sensors"]["ambiguity_policy"] == "retain-capacity/1"
    assert Config.from_dict(new.to_dict()) == new
    with pytest.raises(ValueError, match="Unknown ambiguous"):
        Sensors(ambiguity_policy="assume-repaired")


def test_diagnosis_cases_offer_a_separate_learning_ablation_and_no_future_information():
    answers = {
        mode: evaluate("diagnosis", {"fault": "ambiguous", "ambiguity_policy": mode})
        for mode in ("reduce-capacity/1", "retain-capacity/1")
    }
    old, new = (answers[k]["steps"] for k in answers)
    assert old[:3] == new[:3]
    assert old[3]["diagnosis"]["capacity_kw"] < new[3]["diagnosis"]["capacity_kw"] == 450
    assert new[3]["diagnosis"]["status"] == "ambiguous"
    normal = evaluate("diagnosis", {"fault": "normal", "ambiguity_policy": "retain-capacity/1"})
    assert normal["steps"][:3] == new[:3]
    assert all(answer["status"] == "complete" for answer in answers.values())


def test_independent_hold_invariant_rejects_fabricated_capacity_or_confirmation():
    c = Config(sensors=Sensors(ambiguity_policy="retain-capacity/1"))
    before = Diagnosis(225, incidents=1)
    previous, observed = {"h2_inventory_kg": 20}, readings(inflow=15)
    after, _, _ = update(c.plant, c.sensors, before, previous, observed, 135)
    fixture = {
        "config": c.to_dict(),
        "records": {
            "test": [
                {
                    "hour": 0,
                    "requested": {"electrolyser_kw": 135},
                    "decision": {"observations": previous, "diagnosis": asdict(before)},
                    "observations_after": observed,
                    "diagnosis_after": asdict(after),
                }
            ]
        },
    }
    checks = []
    ambiguous_capacity(fixture, checks)
    assert len(checks) == 3 and all(c["passed"] for c in checks)
    for key, value in (("capacity_kw", 120), ("status", "tracking consistent"), ("incidents", 2)):
        changed = copy.deepcopy(fixture)
        changed["records"]["test"][0]["diagnosis_after"][key] = value
        checks = []
        ambiguous_capacity(changed, checks)
        assert not all(c["passed"] for c in checks)
