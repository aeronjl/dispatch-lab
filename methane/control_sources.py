"""Freeze owner-selected project inputs or verified chronological boundaries."""

import copy

from methane.config import Config
from methane.model_service import recorded_context
from methane.provenance import LOADED_SOURCE
from methane.siting import production, projects
from methane.siting.environment import weather
from methane.siting.store import Store, digest


def catalogue():
    store = Store()
    return dict(
        projects=[
            dict(
                id=p["id"],
                name=p["name"],
                environments=projects.read(store, p["id"])["environments"],
            )
            for p in projects.heads(store)
        ],
        studies=[
            dict(
                id=s["id"],
                name=s["name"],
                cases=[
                    dict(
                        case_id=c["case_id"],
                        label=c["label"],
                        controller=c["controller"],
                        hours=c["hours"],
                        boundaries=[0]
                        + [
                            e["next_hour"]
                            for e in production.entries(store, s["id"], c["case_id"])
                            if e["next_hour"] < c["hours"]
                        ],
                    )
                    for c in s["cases"]
                ],
            )
            for s in store.list("study")
            if s["mode"] != "resource"
        ],
    )


def freeze(request):
    store = Store()
    study_id = request.study_id
    if request.project_id:
        if study_id or request.start_hour:
            raise ValueError("Choose a project start or a saved study checkpoint")
        created = projects.run_project(
            store,
            request.project_id,
            environment_id=request.environment_id or None,
            synthetic=request.synthetic,
            hours=request.hours,
            start=request.start,
            controller=request.controller,
        )
        study_id = created["study_id"]
    if study_id:
        study = store.get("study", study_id)
        case = next(
            (c for c in study["cases"] if c["case_id"] == (request.case_id or "case-001")), None
        )
        if not case or study["mode"] == "resource":
            raise ValueError("Choose an operating study case")
        if request.controller != case["controller"]:
            raise ValueError("Continuation retains the case's reference controller")
        checkpoint = None
        binding = digest(
            dict(
                case=case,
                environment=case["environment_id"],
                source=study["source"]["content_hash"],
            )
        )
        if request.start_hour:
            if study["source"]["content_hash"] != LOADED_SOURCE["content_hash"]:
                raise ValueError(
                    "Checkpoint implementation differs from this app. Restore its original source to continue; hour-zero experiments may use the current model."
                )
            entry = next(
                (
                    e
                    for e in production.entries(store, study_id, case["case_id"])
                    if e["next_hour"] == request.start_hour
                ),
                None,
            )
            if not entry:
                raise ValueError(
                    "Start at a saved committed checkpoint, not an estimated display state"
                )
            checkpoint = production.read_blob(store, entry["checkpoint_sha256"])
            if checkpoint["binding"] != binding:
                raise ValueError("Study checkpoint does not match its frozen case")
        inputs = dict(
            config=case["config"],
            weather=weather(store, case["environment_id"], Config.from_dict(case["config"])),
            controller=case["controller"],
            policies={case["controller"]: case["policy"]} if "policy" in case else None,
            uncertainty=case["uncertainty"],
            utilities=case.get("utilities"),
            checkpoint=checkpoint,
            binding=binding,
            total_hours=case["hours"],
            start_hour=request.start_hour,
            origin=dict(
                kind="project-study",
                study_id=study_id,
                case_id=case["case_id"],
                project_revision=(study.get("search") or {}).get("project_revision"),
                design_id=case["design_id"],
                environment_id=case["environment_id"],
            ),
        )
    else:
        source = recorded_context(request.token, request.run_id)
        if request.controller not in source["records"]:
            raise ValueError("Choose a recorded reference controller")
        original = source.get("control_reproduction")
        if original:
            inputs = copy.deepcopy(original["inputs"])
            if request.controller != inputs["controller"]:
                raise ValueError("Continuation retains the original controller")
            if request.start_hour:
                cp = original.get("ending_checkpoint")
                if not cp or cp["next_hour"] != request.start_hour:
                    raise ValueError("Choose the recording's saved ending checkpoint")
                if original["source_content_hash"] != LOADED_SOURCE["content_hash"]:
                    raise ValueError(
                        "Checkpoint implementation differs; restore original source to continue"
                    )
                inputs.update(checkpoint=cp, start_hour=request.start_hour)
            if (
                inputs.get("checkpoint")
                and original["source_content_hash"] != LOADED_SOURCE["content_hash"]
            ):
                raise ValueError(
                    "Checkpoint implementation differs; restore original source to continue"
                )
            inputs["origin"] = dict(kind="control-recording", run_id=source["run_id"])
        else:
            if (
                request.start_hour
                or source.get("continuous_period", {}).get("start_hour", 0)
                or any(r.get("site_utilities") for rows in source["records"].values() for r in rows)
            ):
                raise ValueError(
                    "This recording has site utilities or a continued initial state without a portable checkpoint. Choose its saved study and checkpoint."
                )
            provenance = source.get("provenance", {})
            inputs = dict(
                config=source["config"],
                weather=source["weather"],
                controller=request.controller,
                policies={request.controller: provenance["controller_policies"][request.controller]}
                if provenance.get("controller_policies")
                else None,
                uncertainty=provenance.get("uncertainty_world"),
                utilities=None,
                checkpoint=None,
                start_hour=0,
                total_hours=len(source["weather"]["times"]),
                origin=dict(kind="recording", run_id=source["run_id"]),
            )
            inputs["binding"] = digest(inputs)
    if inputs["start_hour"] + request.hours > inputs["total_hours"]:
        raise ValueError("Session hours exceed the remaining frozen weather window")
    inputs = copy.deepcopy(inputs)
    inputs["version"] = "dispatch-control-input/2"
    return inputs
