"""Small installed-runtime acceptance; no weather network or policy research."""

import json
import platform
import sys
import time
from dataclasses import replace


def check():
    import pyproj
    import rasterio
    import scipy
    import shapely

    from methane.config import Config
    from methane.jobs import isolated_run
    from methane.paths import data_path
    from methane.processes import lease
    from methane.provenance import LOADED_SOURCE
    from methane.siting.store import Store
    from methane.weather import prepare

    config = Config()
    config = replace(
        config, scenario=replace(config.scenario, hours=2, horizon_hours=6, solver_seconds=0.1)
    )
    weather = prepare(config)
    with lease(data_path("desktop-smoke") / "check.lock"):
        result = isolated_run(config, weather, strategies=["Greedy", "MPC · methane"])
    assert len(result["records"]["Greedy"]) == 2
    assert len(result["records"]["MPC · methane"]) == 2
    from methane.learning_lab.jobs import launch, poll

    store = Store(data_path("desktop-smoke") / "learning")
    job = launch(store, "fixture", {})
    deadline = time.monotonic() + 90
    while (state := poll(store, job["id"]))["status"] == "running":
        if time.monotonic() > deadline:
            raise TimeoutError("Installed teaching worker did not finish")
        time.sleep(0.1)
    assert state["status"] == "complete", state
    from methane import control_service
    from methane import control_sessions as sessions
    from methane.control_storage import read
    from methane.model_service import register

    context = dict(
        token=register(result),
        run_id=result["run_id"],
        key="desktop-preview",
        controller="Greedy",
        hour=0,
    )
    try:
        comparison = control_service.handle(control_service.Request(**context, operation="start"))
        deadline = time.monotonic() + 60
        while comparison["status"] == "running":
            assert time.monotonic() < deadline, "Packaged preview exceeded its check budget"
            time.sleep(0.1)
            comparison = control_service.handle(
                control_service.Request(**context, operation="poll", job_id=comparison["job_id"])
            )
        assert comparison.get("predictions"), comparison
    finally:
        control_service.cleanup()

    created = sessions.handle(
        sessions.Request(
            operation="create",
            token=register(result),
            run_id=result["run_id"],
            controller="Greedy",
            hours=1,
        )
    )
    owner = dict(session_id=created["session_id"], credential=created["owner_key"])

    def request(operation, **kwargs):
        return sessions.handle(sessions.Request(**owner, operation=operation, **kwargs))

    def until(predicate):
        deadline = time.monotonic() + 60
        while True:
            value = request("observe")
            if predicate(value):
                return value
            if time.monotonic() > deadline:
                raise TimeoutError("Packaged control worker did not reach its committed boundary")
            assert value["state"]["status"] not in ("failed", "interrupted"), value["state"]
            time.sleep(0.05)

    try:
        until(lambda value: value["state"]["status"] == "waiting")
        proposal = request("preview", revision=0)
        request(
            "advance",
            revision=0,
            proposal_id=proposal["proposal_id"],
            request_id="desktop-check-first",
            reason="Installed runtime acceptance",
        )
        until(lambda value: value["state"]["status"] == "complete")
        sessions._workers[owner["session_id"]].wait(timeout=10)
        request("replay")
        replay = until(lambda value: value["replay"]["status"] != "running")["replay"]
        assert replay["status"] == "complete", replay
        assert replay["source_matches"] and replay["differences"] == [], replay
        assert replay["independent_reference_passed"], replay
        metadata = read(sessions.folder(owner["session_id"]) / "meta.json")
        assert metadata["source_content_hash"] == LOADED_SOURCE["content_hash"]
    finally:
        sessions.cleanup()
    report = dict(
        status="passed",
        platform=platform.platform(),
        python=sys.version,
        source=LOADED_SOURCE,
        records=2,
        learning=state,
        control_preview_and_replay=replay,
        isolated_preview_status=comparison["status"],
        libraries=dict(
            scipy=scipy.__version__,
            pyproj=pyproj.__version__,
            rasterio=rasterio.__version__,
            shapely=shapely.__version__,
        ),
    )
    path = data_path("desktop-smoke") / "report.json"
    path.write_text(json.dumps(report, indent=2))
    print(json.dumps({"status": "passed", "report": str(path)}))
