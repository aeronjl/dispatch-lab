"""Read-only job ownership, real isolated calculation, cancellation and bounds."""

import copy
import time

import pytest
from fastapi import HTTPException
from test_service_alternatives import request, source

from methane import service_alternatives_service as service
from methane.model_service import register


@pytest.fixture(autouse=True)
def clean_workers():
    service.cleanup()
    yield
    service.cleanup()


def selection(key="generation-1"):
    result, orders, _ = source()
    token = register(result)
    values = dict(token=token, run_id=result["run_id"], key=key, controller="teaching", hour=0)
    return result, values, request(orders[0])


def call(values, operation, **changes):
    return service.handle(service.Request(**{**values, "operation": operation, **changes}))


def wait(values, job):
    end = time.monotonic() + 15
    while time.monotonic() < end:
        reply = call(values, "poll", job_id=job)
        if reply["status"] != "running":
            return reply
        time.sleep(0.05)
    pytest.fail("Service comparison did not finish within the test budget")


def test_describe_and_real_isolated_comparison_preserve_context_and_run():
    result, values, alternative = selection()
    before = copy.deepcopy(result)
    description = call(values, "describe")
    assert description["status"] == "available"
    assert len(description["orders"]) == 2
    assert description["orders"][0]["shared_visit"]
    assert "snapshot" not in description and "catalogue" not in description
    response = call(values, "start", alternative=alternative)
    assert response["status"] == "running"
    finished = wait(values, response["job_id"])
    assert finished["status"] == "complete", finished
    assert finished["key"] == values["key"]
    assert tuple(finished["selection"]) == (values["run_id"], "teaching", 0)
    assert finished["baseline"]["summary"]["service_decision_eur"] == pytest.approx(530)
    assert finished["alternative"]["summary"]["service_decision_eur"] == pytest.approx(530)
    assert result == before
    entry = service._jobs[response["job_id"]]
    assert entry["worker"].returncode == 0
    packet_text = (service.Path(entry["directory"].name) / "input.json").read_text()
    assert '"retrospective_truth"' not in packet_text and '"records"' not in packet_text


def test_old_archive_and_invalid_inputs_never_start_a_worker():
    result, values, alternative = selection()
    del result["records"]["teaching"][0]["field_operations"]["planning_snapshot"]
    missing = call(values, "start", alternative=alternative)
    assert missing["status"] == "unavailable"
    assert "not saved" in missing["error"]
    assert not service._jobs
    _, values, alternative = selection()
    invalid = call(values, "start", alternative={**alternative, "delay_hours": -1})
    assert invalid["status"] == "unavailable"
    assert not service._jobs


def test_stale_selection_and_other_readers_cannot_poll_or_cancel_a_job():
    _, values, alternative = selection()
    started = call(values, "start", alternative=alternative)
    for changed in ({"key": "generation-2"}, {"hour": 1}, {"controller": "other"}):
        for operation in ("poll", "cancel"):
            with pytest.raises(HTTPException) as caught:
                call({**values, **changed}, operation, job_id=started["job_id"])
            assert caught.value.status_code == 410
    _, other, _ = selection()
    with pytest.raises(HTTPException):
        call(other, "poll", job_id=started["job_id"])
    with pytest.raises(HTTPException):
        call({**values, "token": "unknown-reader"}, "describe")


def test_cancel_before_start_is_a_tombstone_and_changed_inputs_need_new_generation():
    _, values, alternative = selection()
    assert call(values, "cancel")["status"] == "cancelled"
    assert call(values, "start", alternative=alternative)["status"] == "cancelled"
    assert not service._jobs
    values["key"] = "next-generation"
    started = call(values, "start", alternative=alternative)
    repeat = call(values, "start", alternative=alternative)
    assert repeat["job_id"] == started["job_id"]
    assert len(service._jobs) == 1
    for operation in ("start", "poll"):
        with pytest.raises(HTTPException) as caught:
            call(
                values,
                operation,
                alternative={**alternative, "delay_hours": 2},
                job_id=started["job_id"],
            )
        assert caught.value.status_code == 409
    cancelled = call(values, "cancel", job_id=started["job_id"])
    assert cancelled["status"] == "cancelled"
    assert service._jobs[started["job_id"]]["worker"].poll() is not None
    assert call(values, "poll", job_id=started["job_id"])["status"] == "cancelled"


def test_new_generation_stops_prior_worker_and_outer_deadline_is_explicit():
    _, values, alternative = selection()
    first = call(values, "start", alternative=alternative)
    newer = {**values, "key": "next-generation"}
    second = call(newer, "start", alternative=alternative)
    assert service._jobs[first["job_id"]]["worker"].poll() is not None
    assert service._jobs[first["job_id"]]["stopped"] == "cancelled"
    # Exercise the same callback as the independent wall-time timer.
    service._expire(second["job_id"])
    expired = call(newer, "poll", job_id=second["job_id"])
    assert expired["status"] == "time-limit"
    assert "baseline" not in expired


def test_http_boundary_rejects_caller_run_objects_prices_and_unknown_operations():
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    app = FastAPI()
    app.add_api_route("/service", service.handle, methods=["POST"])
    _, values, alternative = selection()
    with TestClient(app) as client:
        ok = client.post("/service", json={**values, "operation": "describe"})
        assert ok.status_code == 200 and ok.json()["status"] == "available"
        for extra in ({"prices": {}}, {"result": {}}, {"operation": "execute"}, {"hour": True}):
            bad = client.post(
                "/service",
                json={**values, "operation": "start", "alternative": alternative, **extra},
            )
            assert bad.status_code == 422
