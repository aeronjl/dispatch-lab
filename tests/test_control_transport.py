"""Bounded isolated workers, cancellation races, ownership and context binding."""

import copy
import time

import pytest
from fastapi import HTTPException
from test_control_view import load_result

from methane import control_service as service
from methane.model_service import register


@pytest.fixture
def result():
    return load_result()


@pytest.fixture(autouse=True)
def cleanup():
    service.cleanup()
    yield
    service.cleanup()


def context(result, key="first"):
    return dict(
        token=register(result), run_id=result["run_id"], controller="Greedy", hour=12, key=key
    )


def call(c, op, **kwargs):
    return service.handle(service.Request(**c, operation=op, **kwargs))


def test_real_worker_only_receives_original_information(result):
    result["config"]["scenario"]["solver_seconds"] = 0.05
    before = copy.deepcopy(result)
    c = context(result)
    description = call(c, "describe")
    assert description["comparison"]["available"]
    start = call(c, "start")
    assert call(c, "start")["job_id"] == start["job_id"]
    end = time.monotonic() + 15
    while time.monotonic() < end:
        reply = call(c, "poll", job_id=start["job_id"])
        if reply["status"] != "running":
            break
        time.sleep(0.05)
    assert reply["status"] == "complete", reply
    assert reply["key"] == c["key"]
    assert reply["information_id"] == description["comparison"]["information_id"]
    assert tuple(reply["selection"]) == (c["run_id"], c["controller"], c["hour"])
    packet = (
        service.Path(service._jobs[start["job_id"]]["directory"].name) / "input.json"
    ).read_text()
    assert '"retrospective_truth"' not in packet and '"observations_after"' not in packet
    assert result == before


def test_cancel_before_start_and_cross_selection_ownership(result):
    c = context(result)
    call(c, "cancel")
    assert call(c, "start")["status"] == "cancelled"
    assert not service._jobs
    c["key"] = "new-generation"
    start = call(c, "start")
    for op in ("poll", "cancel"):
        with pytest.raises(HTTPException) as exc:
            call({**c, "hour": 13}, op, job_id=start["job_id"])
        assert exc.value.status_code == 410
    call(c, "cancel", job_id=start["job_id"])
    assert call(c, "poll", job_id=start["job_id"])["status"] == "cancelled"
    assert service._jobs[start["job_id"]]["worker"].poll() is not None


def test_missing_decision_and_expired_context_do_not_launch_workers(result):
    c = context(result)
    assert call({**c, "hour": 9999}, "start")["status"] == "unavailable"
    with pytest.raises(HTTPException):
        call({**c, "token": "not-owned"}, "describe")
    assert not service._jobs
