"""Sealed offline learning inputs preserve information, gaps and source identity."""

import copy
import json

import pytest

from methane.services.coupling import identity
from methane.services.investigation_examples import evaluate, fixture, render


@pytest.mark.parametrize(
    "case, expected", [("fixed-reader", "complete"), ("late-crew", "incomplete")]
)
def test_learning_packet_round_trip_is_immutable_and_carries_no_private_fault_inputs(
    case, expected
):
    packet = json.loads(json.dumps(fixture(case)))
    before = copy.deepcopy(packet)
    assert not {"faults", "truth", "scenario", "random_draws"}.intersection(packet)
    result = evaluate(packet)
    assert packet == before
    assert result["source_matches"]
    assert result["comparison"]["status"] == expected
    assert result["packet_id"] == packet["packet_id"]
    if expected == "incomplete":
        assert "process" not in result["comparison"]["strategies"]["inspect-first"]
    report = render(
        [
            dict(
                packet=packet,
                result=result,
                packet_path="inputs.json",
                result_path="prediction.json",
            )
        ]
    )
    assert "Conditional predictions" in report and "Actual confirmation still required" in report
    assert "data:font/woff2;base64," in report
    assert "https://" not in report


def test_changed_packet_is_rejected_and_different_original_source_is_labelled():
    packet = fixture("fixed-reader")
    packet["forecast"]["pv_kw"][0] += 1
    with pytest.raises(ValueError, match="integrity"):
        evaluate(packet)
    packet = fixture("fixed-reader")
    packet["source"] = "explicit-other-build"
    packet["packet_id"] = identity({k: v for k, v in packet.items() if k != "packet_id"})
    result = evaluate(packet)
    assert not result["source_matches"]
    assert result["original_source"] == "explicit-other-build"
    assert result["calculation_source"] != result["original_source"]
