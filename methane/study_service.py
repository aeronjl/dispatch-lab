"""Capability-scoped study transport; execution remains in a bounded frozen worker."""

import copy
import json
import re
import secrets
import threading
from collections import OrderedDict
from urllib.parse import urlencode

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from methane import studies
from methane.config import Config

_contexts = OrderedDict()
_workers = {}
_lock = threading.RLock()


class Request(BaseModel):
    token: str = Field(max_length=100)
    run_id: str = Field(max_length=100)
    key: str = Field(max_length=200)
    operation: str = "list"
    protocol_id: str | None = Field(default=None, max_length=80)
    edition_id: str | None = Field(default=None, max_length=40)
    case_id: str | None = Field(default=None, max_length=40)
    tier: str = "reference"
    basis: str = "reference"
    controller: str | None = Field(default=None, max_length=100)
    metric: str = Field(default="methane_kg", max_length=100)
    report_id: str | None = Field(default=None, max_length=40)
    attempt_id: str | None = Field(default=None, max_length=80)
    uncertainty: dict | None = None
    preview_hash: str | None = Field(default=None, max_length=64)


def register(result):
    token = secrets.token_urlsafe(32)
    with _lock:
        resolved = Config.from_dict(result["config"]).to_dict()
        _contexts[token] = {
            "run_id": result["run_id"],
            "config": copy.deepcopy(resolved),
            "basis_origin": {
                "run_id": result["run_id"],
                "original_config_hash": studies.digest(result["config"]),
                "resolved_legacy_fields": studies.differences(result["config"], resolved),
            },
        }
        while len(_contexts) > 16:
            _contexts.popitem(last=False)
    return token


def context(token, run_id=None):
    with _lock:
        result = _contexts.get(token)
        if result is None or (run_id is not None and result["run_id"] != run_id):
            raise HTTPException(410, "Study context expired; reopen the active run")
        return result


def live_status(identifier):
    path = studies.location(identifier) / "progress.json"
    result = json.loads(path.read_text()) if path.exists() else {"status": "ready", "fraction": 0}
    worker = studies.active_worker()
    if result["status"] == "running" and (not worker or worker["edition_id"] != identifier):
        result = {
            **result,
            "status": "interrupted",
            "description": "Execution stopped. Resume to reuse verified completed cases.",
        }
    return result


def start(identifier, fresh=False):
    with _lock:
        if studies.active_worker():
            raise ValueError(
                "A study is already running. Resume or cancel it before starting another."
            )
        _workers[identifier] = studies.launch(identifier, fresh=fresh)


def readable(identifier, config, report_id=None):
    from methane.study_presentation import project, publications, published_view

    live = live_status(identifier)
    value = (
        project(studies.report(identifier))
        if live["status"] == "running" and not report_id
        else published_view(identifier, studies.STORE, report_id)
    )
    m = value["manifest"]
    withdrawn = studies.withdrawal(identifier)
    if withdrawn:
        value["status"] = "withdrawn"
        value["finding"] = withdrawn["reason"]
        value["interpretation_status"] = "Withdrawn calculation; raw traces retained"
        for case in value["cases"]:
            case.pop("delta", None)
        for comparison in value.get("comparisons", []):
            comparison.update(delta={}, status="withdrawn")
        value["aggregate"] = []
    value["current_plant_differences"] = studies.differences(m["basis"], config)
    value["source_matches_current"] = m["source_hash"] == studies.LOADED_SOURCE["content_hash"]
    value["progress"] = live_status(identifier)
    value["publications"] = [
        {k: p[k] for k in ("report_id", "published_at", "status")}
        for p in publications(identifier, studies.STORE)
    ]
    return value


def trace(request):
    value = studies.read_manifest(request.edition_id, studies.STORE)
    case = next((c for c in value["cases"] if c["case_id"] == request.case_id), None)
    if not case:
        raise ValueError("No recorded calculation for this case")
    entry = studies.entry_for(request.edition_id, request.case_id, attempt_id=request.attempt_id)
    result = studies.archive_for(request.edition_id, entry)
    name = request.controller or next(iter(result["records"]))
    if name not in result["records"]:
        raise ValueError("Unknown controller")
    rows = result["records"][name]
    if request.metric == "methane_kg":
        terms = [
            {"interval": r["hour"], "value": r["applied"]["methane_kg"], "unit": "kg CH4"}
            for r in rows
        ]
        definition = "Sum of applied methane output. Terminal battery credit is excluded."
        value = sum(t["value"] for t in terms)
        unit = "kg CH4"
    elif request.metric == "battery_kwh":
        terms = [
            {"interval": r["hour"], "value": r["state"]["battery_kwh"], "unit": "kWh"}
            for r in rows[-1:]
        ]
        definition, value, unit = (
            "Battery inventory after the last executed interval.",
            terms[0]["value"] if terms else None,
            "kWh",
        )
    elif request.metric in ("crew_hours", "remote_hours"):
        resource = "crew-hours" if request.metric == "crew_hours" else "remote-hours"
        terms = [
            {"interval": r["hour"], "value": e["amount"], "unit": "h"}
            for r in rows
            for e in r.get("field_operations", {}).get("resource_events", [])
            if e["kind"] == "consume" and e["resource"] == resource
        ]
        definition = "Sum of recorded committed labour, including travel and transfer; no duplicate hands-on scalar."
        value, unit = sum(t["value"] for t in terms), "h"
    elif request.metric in (
        "service_allocated_eur",
        "service_decision_eur",
        "service_expenditure_eur",
    ):
        original = studies.service_calculation_for(request.edition_id, entry)
        if original["source_hash"] != result["provenance"]["source"]["content_hash"] or original[
            "original_service_cost_version"
        ] != result.get("service_cost_version"):
            raise ValueError("Service calculation does not belong to this archived run")
        calculation = original["controllers"][name]
        view = request.metric.removeprefix("service_").removesuffix("_eur")
        terms = [
            {"interval": line["id"], "value": line["amount_eur"], "unit": "EUR"}
            for line in calculation["lines"]
            if view in line["views"]
        ]
        definition = f"Sum of {view} service lines under this run's frozen assumptions. Missing applicable prices leave the total undefined."
        value, unit = calculation["views"][view]["total_eur"], "EUR"
    else:
        raise ValueError("Unknown study metric")
    return {
        "definition": definition,
        "value": value,
        "unit": unit,
        "operands": terms,
        "controller": name,
        "case_id": case["case_id"],
        "run_id": result["run_id"],
        "source_hash": result["provenance"]["source"]["content_hash"],
        "policy": result["provenance"]["controller_policies"][name],
        "original_decision_cost_version": result["decision_cost_version"],
        "original_service_cost_version": result.get("service_cost_version"),
        **({"calculation": calculation} if request.metric.startswith("service_") else {}),
        "weather_hash": case["weather_hash"],
        "audit": entry["independent_audit"],
        "uncertainty_world": result.get("uncertainty", {}).get("world"),
        "note": "Retrospective recorded physical calculation. Original dispatch assumptions remain frozen.",
    }


def handle(request: Request):
    source = context(request.token, request.run_id)
    try:
        op = request.operation
        if op.startswith("uncertainty-"):
            from methane.uncertainty import catalogue
            from methane.uncertainty_studies import default_spec, protocol

            basis = source["config"]
            if op == "uncertainty-catalogue":
                answer = {"catalogue": catalogue(basis), "specification": default_spec(basis)}
            elif op in ("uncertainty-preview", "uncertainty-create"):
                if request.uncertainty is None:
                    raise ValueError("Supply an uncertainty specification")
                spec = protocol(basis, request.uncertainty)
                cases = studies.resolve_cases(spec, basis, "reference")
                preview_hash = studies.digest({"protocol": spec, "cases": cases})
                if op == "uncertainty-preview":
                    answer = {
                        "preview_hash": preview_hash,
                        "cases": len(cases),
                        "invalid": [
                            {"label": c["label"], "error": c["input_error"]}
                            for c in cases
                            if c["input_error"]
                        ],
                        "worlds": len({c["uncertainty_world"]["world_id"] for c in cases}),
                        "controllers": list(spec["policies"]),
                        "hours": basis["scenario"]["hours"],
                        "draws": [
                            c["uncertainty_world"]
                            for c in cases[:: len(spec["uncertainty"]["inner_seeds"])]
                        ],
                    }
                else:
                    if request.preview_hash != preview_hash:
                        raise ValueError(
                            "Inputs changed; review the newly resolved uncertainty preview"
                        )
                    with _lock:
                        if studies.active_worker():
                            raise ValueError(
                                "A study is already running; finish or cancel it first"
                            )
                        manifest = studies.create(
                            basis=basis,
                            action="current-plant",
                            specification=spec,
                            basis_origin=source["basis_origin"],
                        )
                        start(manifest["edition_id"])
                    answer = readable(manifest["edition_id"], basis)
            else:
                raise ValueError("Unknown uncertainty operation")
        elif op == "list":
            answer = {
                "editions": studies.list_editions(),
                "protocol": studies.protocol(),
                "protocols": studies.protocols(),
            }
        elif op == "preview":
            if request.basis not in ("reference", "current-plant"):
                raise ValueError("Unknown plant basis")
            spec = (
                studies.read_manifest(request.edition_id)["protocol"]
                if request.edition_id
                else studies.protocol(request.protocol_id)
                if request.protocol_id
                else studies.protocol()
            )
            basis = (
                source["config"] if request.basis == "current-plant" else spec["reference_config"]
            )
            cases = studies.resolve_cases(spec, basis, request.tier)
            field = spec["schema_version"] == "dispatch-lab/study-protocol/2"
            answer = {
                "preview": {
                    "kind": "field" if field else "battery",
                    **(
                        dict(computation=spec["tiers"][request.tier]["computation"])
                        if spec.get("resolver") == "repeated-field-computation/1"
                        else {}
                    ),
                    "protocol_hash": studies.digest(spec),
                    "cases": len(cases),
                    "pairs": len(cases) // len(spec["arms"]) * (len(spec["arms"]) - 1)
                    if field
                    else len(cases),
                    "hours": spec["tiers"][request.tier]["hours"],
                    "policies": list(spec["policies"]),
                    "arms": spec.get("arms", []),
                    "resolved_cases": [
                        {k: c[k] for k in ("case_id", "label", "changes_from_basis")} for c in cases
                    ]
                    if field
                    else [],
                    "batteries": []
                    if field
                    else [
                        c["resolved_battery"]
                        for c in cases[
                            :: len(spec["conditions"]) * len(spec["tiers"][request.tier]["seeds"])
                        ]
                    ],
                    "basis_changes": studies.differences(spec["reference_config"], basis),
                    "basis_origin": source["basis_origin"]
                    if request.basis == "current-plant"
                    else None,
                    "resolution": spec["resolution"],
                    "purpose": spec["tiers"][request.tier]["purpose"],
                }
            }
        elif op in ("create", "reproduce"):
            if request.basis not in ("reference", "current-plant"):
                raise ValueError("Unknown plant basis")
            with _lock:
                if studies.active_worker():
                    raise ValueError("A study is already running; finish or cancel it first")
                manifest = studies.create(
                    basis=source["config"] if request.basis == "current-plant" else None,
                    tier=request.tier,
                    parent=request.edition_id,
                    action="reproduce" if op == "reproduce" else request.basis,
                    basis_origin=source["basis_origin"]
                    if request.basis == "current-plant"
                    else None,
                    protocol_id=request.protocol_id,
                )
                start(manifest["edition_id"])
            answer = readable(manifest["edition_id"], source["config"])
        elif op in ("resume", "fresh"):
            start(request.edition_id, fresh=op == "fresh")
            answer = readable(request.edition_id, source["config"])
        elif op == "cancel":
            studies.read_manifest(request.edition_id)
            (studies.location(request.edition_id) / "cancel").touch()
            answer = {
                "progress": {
                    "status": "cancelling",
                    "description": "Cancellation requested; partial results and remaining cases will be retained.",
                }
            }
        elif op in ("view", "status"):
            answer = readable(
                request.edition_id, source["config"], request.report_id if op == "view" else None
            )
        elif op == "service-record":
            answer = {"service_record": service_record(request)}
        elif op == "trace":
            answer = {"trace": trace(request)}
        elif op == "export":
            studies.read_manifest(request.edition_id)
            publication = studies.stored_report(request.edition_id, report_id=request.report_id)
            report_id = publication.get("report_id")
            if not report_id:
                raise ValueError("Wait for a saved study report before exporting")
            destination = studies.STORE / (request.edition_id + "-" + report_id + ".zip")
            destination = studies.export(request.edition_id, destination, report_id=report_id)
            answer = {
                "download_url": f"/dispatch/study-download/{request.edition_id}?"
                + urlencode(
                    {
                        "report_id": report_id,
                        "token": request.token,
                        "artifact": destination.name,
                    }
                )
            }
        else:
            raise ValueError("Unknown study operation")
        return {**answer, "key": request.key}
    except (ValueError, OSError, KeyError, TypeError) as exc:
        return {"key": request.key, "error": str(exc)}


def service_record(request):
    from methane.study_presentation import published_view

    if not request.case_id or not request.attempt_id or not request.controller:
        raise ValueError("Select a recorded case, attempt and controller")
    published_entry = None
    if request.report_id:
        value = published_view(request.edition_id, studies.STORE, request.report_id)
        case = next((c for c in value["cases"] if c["case_id"] == request.case_id), None)
        if case is None or case["entry"].get("attempt_id") != request.attempt_id:
            raise ValueError("Selected attempt does not belong to this publication")
        published_entry = case["entry"]["original_entry_integrity_sha256"]
    entry = studies.entry_for(
        request.edition_id, request.case_id, studies.STORE, request.attempt_id
    )
    if published_entry is not None and entry["integrity_sha256"] != published_entry:
        raise ValueError("Case attempt differs from the originally published attempt")
    metrics = (entry.get("metrics") or {}).get(request.controller)
    if metrics is None or metrics.get("service_work") is None:
        raise ValueError("This recorded controller has no service history")
    return {
        "edition_id": request.edition_id,
        "report_id": request.report_id,
        "case_id": request.case_id,
        "attempt_id": request.attempt_id,
        "controller": request.controller,
        "original_entry_integrity_sha256": entry["integrity_sha256"],
        "work": metrics["service_work"],
        "scope": "Original signed case-attempt service record; not current simulator state or a replan.",
    }


def download(edition_id: str, token: str, report_id: str, artifact: str | None = None):
    context(token)
    studies.read_manifest(edition_id)
    if studies.withdrawal(edition_id):
        raise HTTPException(409, "This edition was withdrawn; inspect its recorded qualification")
    publication = studies.stored_report(edition_id, report_id=report_id)
    stem = edition_id + "-" + publication["report_id"]
    name = artifact or (stem + ".zip")
    if re.fullmatch(re.escape(stem) + r"(?:-[0-9a-f]{64})?\.zip", name) is None:
        raise HTTPException(400, "Artifact does not belong to this study publication")
    path = studies.STORE / name
    if not path.exists():
        raise HTTPException(404, "Prepare the study bundle first")
    return FileResponse(
        path, filename=f"dispatch-study-{edition_id[:8]}.zip", media_type="application/zip"
    )
