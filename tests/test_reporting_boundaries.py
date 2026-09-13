import copy

import pytest

from methane.recovery import LOOP_VERSION, outcomes
from methane.reference import D, stock_bounds


def test_rounded_brush_disposal_reports_the_actual_boundary_error():
    # Independent replay of the H184 operands in the retained 240 h seed-7 run.
    remainder = D("833.333333333380961") - D("833.3333333333935")
    checks = []
    stock_bounds(checks, "brush:cleaner", remainder, 50000, "m2", hour=184)
    assert checks[0]["actual"] == pytest.approx(1.2539e-11, abs=1e-20)
    assert checks[0]["unit"] == "m2" and checks[0]["passed"]
    assert checks[0]["tolerance"] == 1e-5 + 1e-8


@pytest.mark.parametrize("value", [-0.001, 50000.001])
def test_real_stock_deficits_and_excesses_still_fail(value):
    checks = []
    stock_bounds(checks, "brush:cleaner", value, 50000, "m2")
    assert not checks[0]["passed"]
    assert checks[0]["actual"] == pytest.approx(0.001)


def test_v3_counts_windows_once_and_keeps_escalation_intervals_separate():
    expired = dict(receipt_ids=["repair-1"], outcome="verification deadline missed")
    confirmed = dict(receipt_ids=["repair-2"], outcome="observer confirmed")
    snapshots = [
        ([], "escalation-required"),
        ([expired], "escalation-required"),
        ([expired], "escalation-required"),
        ([expired, confirmed], "inactive"),
    ]
    rows = [
        dict(
            hour=h,
            diagnosis_after=dict(capacity_kw=450),
            decision=dict(
                probe=False,
                recovery_planning=dict(
                    version=LOOP_VERSION, status=status, verification_loop=dict(episodes=episodes)
                ),
            ),
        )
        for h, (episodes, status) in enumerate(snapshots)
    ]
    original = copy.deepcopy(rows)
    result = outcomes(rows, [], 450)
    assert rows == original
    assert result["recovery_deadline_misses"] is None
    assert result["recovery_verification_windows"] == 2
    assert result["recovery_verification_deadline_misses"] == 1
    assert result["recovery_observer_confirmed_windows"] == 1
    assert result["recovery_escalation_hours"] == 3


def test_sensing_disabled_does_not_count_as_confirmed():
    rows = [
        dict(
            hour=0,
            diagnosis_after=dict(capacity_kw=450),
            decision=dict(
                probe=False,
                recovery_planning=dict(
                    version=LOOP_VERSION,
                    status="inactive",
                    verification_loop=dict(
                        episodes=[dict(receipt_ids=["repair-1"], outcome="sensing disabled")]
                    ),
                ),
            ),
        )
    ]
    assert outcomes(rows, [], 450)["recovery_observer_confirmed_windows"] == 0
