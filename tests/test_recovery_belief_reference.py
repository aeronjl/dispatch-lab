"""Separate arithmetic, archived operands and tamper checks for recovery uncertainty."""

import copy
import json
import math
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from test_recovery_belief import contact, make, test_packet

from methane.recovery_belief_reference import digest, inspect, power
from methane.services.contracts import Context
from methane.services.recovery_belief import Procedure


@pytest.mark.parametrize("noise", [0, 0.02, 0.1])
@pytest.mark.parametrize("chance", [0, 0.8, 1])
def test_independent_reader_transitions_and_operating_arithmetic(noise, chance):
    f = make(noise=noise, chance=chance)
    records = [f.advance(Context(1, contact()))]
    records.append(f.advance(Context(2, ()), [Procedure("reset", "reset", 1.5)]))
    records.append(f.advance(Context(3, contact(at=2.5))))
    records.append(f.advance(Context(4, ()), test=test_packet(3, 225, noise=noise)))
    records.append(f.advance(Context(5, ()), [Procedure("replace", "module-replacement", 4.5)]))
    records.append(f.advance(Context(6, ()), test=test_packet(5, 450, noise=noise)))
    for record in records:
        assert inspect(json.loads(json.dumps(record))) == []


def test_extreme_gaussian_tail_and_reviving_underflowed_display_probability():
    # Independent normal-table value and large-z Mills-ratio evaluation.
    assert power(0, 225, 1) == pytest.approx(math.log(0.15865525393145707))
    assert power(0, 225, 0.02) == pytest.approx(-1254.8313611394199, abs=1e-9)
    f = make(noise=0.02, chance=0.5)
    f.advance(Context(1, ()), [Procedure("replace", "module-replacement", 0.5)])
    r = f.advance(Context(2, ()), test=test_packet(1, 450, noise=0.02))
    assert inspect(r) == []
    for h in (2, 3, 4):
        r = f.advance(Context(h + 1, ()), test=test_packet(h, 150, noise=0.02))
        assert inspect(r) == []
    assert r["restoration_probability"] == pytest.approx(1 / 17)


@pytest.mark.parametrize("mutation", ["probability", "likelihood", "procedure", "future"])
def test_checker_does_not_accept_resealed_false_arithmetic(mutation):
    f = make()
    f.advance(Context(1, contact()))
    r = f.advance(Context(2, ()), [Procedure("reset", "reset", 1.5)])
    if mutation == "probability":
        r["restoration_probability"] += 0.1
    elif mutation == "likelihood":
        r["history"][0]["log_likelihoods"][0]["value"] = -1
    elif mutation == "procedure":
        r["history"][-1]["event"]["procedure"]["action"] = "module-replacement"
    else:
        r["history"][-1]["event"]["available_at"] = 4
    r["belief_id"] = digest({k: v for k, v in r.items() if k != "belief_id"})
    assert inspect(r)


def test_dependency_free_checker_and_input_immutability(tmp_path):
    f = make()
    r = f.advance(Context(1, contact()))
    original = copy.deepcopy(r)
    assert not inspect(r)
    assert r == original
    data = tmp_path / "belief.json"
    data.write_text(json.dumps(r))
    checker = Path(__file__).resolve().parents[1] / "methane/recovery_belief_reference.py"
    completed = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-c",
            "import json,runpy,sys; checker=runpy.run_path(sys.argv[1]); assert not checker['inspect'](json.load(open(sys.argv[2])))",
            str(checker),
            str(data),
        ],
        capture_output=True,
        text=True,
    )
    assert completed.returncode == 0, completed.stderr


def test_policy_threshold_is_opt_in_and_legacy_defaults_keep_their_meaning():
    from methane.services.investigator import (
        BELIEF_VERSION,
        CONTINUATION_VERSION,
        InvestigationPolicy,
    )

    original = InvestigationPolicy(version=CONTINUATION_VERSION)
    assert original.followup_impairment_probability is None
    current = replace(original, version=BELIEF_VERSION)
    assert current.followup_impairment_probability == 0.5
    with pytest.raises(ValueError, match="probability gate"):
        replace(current, version=CONTINUATION_VERSION)
    for value in (-0.1, 1.1, True, math.nan):
        with pytest.raises(ValueError, match="probability"):
            replace(current, followup_impairment_probability=value)
