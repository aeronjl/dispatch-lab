"""Recorded-period investigations: immutable evidence, predictions and authored notes.

Retrospective execution summaries never enter the original-information planner.
Saved comparisons are produced by the server worker, never accepted from a browser.
"""

import copy
import html
import json
import math
from datetime import UTC, datetime
from typing import Literal

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, StrictInt

from methane.control_view import describe, selected
from methane.model_service import recorded_context
from methane.siting.store import Store, digest

COMPONENTS = ("solar", "battery", "electrolyser", "hydrogen", "co2", "reactor")


def identity(result):
    return dict(
        run_id=result["run_id"],
        recording_fingerprint=result.get("integrity_sha256") or digest(result),
        original_integrity=result.get("integrity_sha256"),
        original_source=result.get("provenance", {}).get("source", {}).get("content_hash"),
        model_version=result.get("model_version"),
        study_origin={
            k: v
            for k, v in result.get("study_origin", {}).items()
            if k not in ("hour", "component")
        },
        continuous_period=result.get("continuous_period"),
    )


def numeric(value):
    return value if isinstance(value, (int, float)) and math.isfinite(value) else None


def overview(result, controller):
    if controller not in result.get("records", {}):
        raise ValueError("Recorded controller unavailable")
    points = []
    for hour, row in enumerate(result["records"][controller]):
        applied, requested = row.get("applied", {}), row.get("requested", {})
        methane, target = numeric(applied.get("methane_kg")), numeric(requested.get("methane_kg"))
        d = row.get("decision", {})
        points.append(
            dict(
                hour=hour,
                time=row.get("local_time", row.get("time")),
                methane_kg=methane,
                shortfall_kg=max(0, target - methane)
                if target is not None and methane is not None
                else None,
                curtailed_kwh=numeric(row.get("curtailed_kwh")),
                forced_trip=row.get("forced_trip"),
                reactor_start=row.get("reactor_start"),
                bindings=copy.deepcopy(d.get("evidence", {}).get("bindings", {})),
                diagnosis=d.get("diagnosis", {}).get("status"),
                solver=d.get("plan", {}).get("solver", {}).get("status"),
                fallback=d.get("plan", {}).get("solver", {}).get("fallback_used"),
            )
        )
    return dict(
        source=identity(result),
        controller=controller,
        points=points,
        scope="Recorded execution, not sensor measurements. Shortfall is requested minus applied methane; low output alone does not establish a fault.",
    )


def period(points, start, end):
    if not 0 <= start < end <= len(points):
        raise ValueError("Select a non-empty period inside this recording; end is exclusive")
    rows = points[start:end]
    totals = {}
    for key in ("methane_kg", "shortfall_kg", "curtailed_kwh"):
        values = [r[key] for r in rows if r[key] is not None]
        totals[key] = sum(values) if len(values) == len(rows) else None
    totals["forced_trips"] = (
        sum(bool(r["forced_trip"]) for r in rows)
        if all(r["forced_trip"] is not None for r in rows)
        else None
    )
    totals["reactor_starts"] = (
        sum(bool(r["reactor_start"]) for r in rows)
        if all(r["reactor_start"] is not None for r in rows)
        else None
    )
    return dict(start=start, end=end, totals=totals, points=rows)


def save_comparison(result, controller, hour, inputs, output, store=None):
    store = store or Store()
    return store.put(
        "decision-comparison",
        dict(
            schema="decision-comparison/1",
            source=identity(result),
            controller=controller,
            hour=hour,
            original=describe(result, controller, hour),
            inputs=copy.deepcopy(inputs),
            output=copy.deepcopy(output),
            label="Conditional predictions; not realised outcomes",
        ),
    )


class Draft(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=160)
    question: str = Field(default="", max_length=2000)
    finding: str = Field(default="", max_length=6000)
    next_step: str = Field(default="", max_length=2000)
    start: int = Field(ge=0, strict=True)
    end: int = Field(ge=1, strict=True)
    focus_hour: int = Field(ge=0, strict=True)
    component: Literal["solar", "battery", "electrolyser", "hydrogen", "co2", "reactor"] = "battery"
    pins: list[StrictInt] = Field(default_factory=list, max_length=12)
    comparisons: list[str] = Field(default_factory=list, max_length=12)
    parent: str | None = None


def owned(store, kind, key, result, controller):
    value = store.get(kind, key)
    if value["source"] != identity(result) or value["controller"] != controller:
        raise ValueError("Saved evidence belongs to another recording or controller")
    return value


def save(result, controller, draft, store=None):
    store = store or Store()
    view = overview(result, controller)
    window = period(view["points"], draft.start, draft.end)
    if not draft.start <= draft.focus_hour < draft.end:
        raise ValueError("The focused decision must be inside the investigation period")
    if draft.parent:
        owned(store, "investigation", draft.parent, result, controller)
    pins = []
    for hour in dict.fromkeys(draft.pins):
        if type(hour) is not int or not draft.start <= hour < draft.end:
            raise ValueError("Pinned decisions must be inside the investigation period")
        pins.append(describe(result, controller, hour))
    comparisons = []
    for key in dict.fromkeys(draft.comparisons):
        item = owned(store, "decision-comparison", key, result, controller)
        if not draft.start <= item["hour"] < draft.end:
            raise ValueError("An alternative lies outside this investigation period")
        comparisons.append(dict(id=key, **item))
    record = dict(
        schema="expert-investigation/1",
        source=view["source"],
        controller=controller,
        created_at=datetime.now(UTC).isoformat(),
        draft=draft.model_dump(),
        period=window,
        evidence=pins,
        comparisons=comparisons,
        scope=view["scope"],
        interpretation="Question, finding and next step are authored interpretations, not automated causal findings.",
    )
    key = store.put("investigation", record)
    store.put(
        "investigation-index",
        dict(
            record_id=key,
            title=draft.title,
            source=record["source"],
            controller=controller,
            created_at=record["created_at"],
        ),
    )
    return dict(id=key, **record)


def report(record):
    """Self-contained reading export; complete operands are in the adjacent JSON export."""

    def esc(value):
        return html.escape(str(value))

    draft = record["draft"]

    def table(headers, rows):
        return (
            "<table><thead><tr>"
            + "".join(f"<th>{esc(h)}</th>" for h in headers)
            + "</tr></thead><tbody>"
            + "".join("<tr>" + "".join(f"<td>{esc(v)}</td>" for v in row) + "</tr>" for row in rows)
            + "</tbody></table>"
        )

    parts = [
        f"<h1>{esc(draft['title'])}</h1>",
        f"<p>{esc(record['controller'])} · recorded H{draft['start']} → {draft['end']}</p>",
        f"<p>{esc(record['scope'])}</p>",
    ]
    for key, label in (
        ("question", "Question"),
        ("finding", "Interpretation"),
        ("next_step", "Next step"),
    ):
        parts.append(f"<h2>{label}</h2><p class='prose'>{esc(draft[key] or 'Not recorded')}</p>")
    parts.append(
        "<h2>Recorded period</h2>"
        + table(
            ["Quantity", "Value"],
            [(k, v if v is not None else "Missing") for k, v in record["period"]["totals"].items()],
        )
    )
    parts.append("<h2>Pinned decisions</h2>")
    for evidence in record["evidence"]:
        parts.append(
            f"<h3>H{evidence['hour']} · {esc(evidence['time'])}</h3><p>Recorded constraints; a binding limit does not establish causal importance.</p>"
        )
        parts.append(
            table(
                ["Equipment", "Recorded limits"],
                [(c, " · ".join(v)) for c, v in evidence["evidence"].get("bindings", {}).items()],
            )
        )
        parts.append(
            f"<p>Forecast: {esc(evidence['forecast_source'])}</p><p>Solver: {esc(evidence['solver'])}</p>"
        )
    parts.append("<h2>Alternatives — conditional predictions</h2>")
    for item in record["comparisons"]:
        output = item["output"]
        parts.append(f"<h3>Decision H{item['hour']}</h3><p>{esc(output['scope'])}</p>")
        parts.append(
            table(
                ["Alternative", "CH₄ kg", "Decision cost €", "Ending battery kWh", "Solver"],
                [
                    (
                        name,
                        (p.get("predicted") or {}).get("methane_kg", "Unavailable"),
                        (p.get("predicted") or {}).get("variable_and_wear_eur", "Unavailable"),
                        (p.get("predicted") or {})
                        .get("ending", {})
                        .get("battery_kwh", "Unavailable"),
                        p["solver"]["status"],
                    )
                    for name in output.get("order", output["predictions"])
                    for p in (output["predictions"][name],)
                ],
            )
        )
        parts.append(
            f"<p>Information: {esc(output['information_id'])}<br>Comparison source: {esc(output['replanner_source_content_hash'])}</p>"
        )
    parts.append(
        f"<h2>Original recording</h2><pre>{esc(json.dumps(record['source'], indent=2))}</pre><p>{esc(record['interpretation'])}</p>"
    )
    return (
        "<!doctype html><html lang='en'><meta charset='utf-8'><meta name='viewport' content='width=device-width'><title>"
        + esc(draft["title"])
        + "</title><style>body{background:#202020;color:#ead8bb;font:16px/1.6 system-ui,sans-serif;max-width:1000px;margin:40px auto;padding:24px}h1,h2,h3{color:#ffa32d;font-weight:500}table{border-collapse:collapse;width:100%;display:block;overflow:auto}td,th{padding:10px;border-bottom:1px solid #735637;text-align:left}p,pre{overflow-wrap:anywhere;white-space:pre-wrap}pre{font-size:12px}</style><main>"
        + "".join(parts)
        + "</main></html>"
    )


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=100)
    run_id: str = Field(max_length=100)
    key: str = Field(max_length=250)
    controller: str = Field(max_length=100)
    operation: Literal["overview", "period", "save", "load", "comparison"]
    start: int = Field(default=0, ge=0, strict=True)
    end: int = Field(default=1, ge=1, strict=True)
    id: str | None = Field(default=None, max_length=64)
    draft: Draft | None = None


def handle(request: Request):
    result = recorded_context(request.token, request.run_id)
    store = Store()
    try:
        selected(result, request.controller, 0)
        if request.operation == "overview":
            source = identity(result)
            saved = [
                dict(id=v["record_id"], title=v["title"], created_at=v["created_at"])
                for v in store.list("investigation-index")
                if v["source"] == source and v["controller"] == request.controller
            ]
            return {
                **overview(result, request.controller),
                "saved": sorted(saved, key=lambda v: v["created_at"], reverse=True),
                "key": request.key,
            }
        if request.operation == "period":
            return {
                **period(
                    overview(result, request.controller)["points"], request.start, request.end
                ),
                "key": request.key,
            }
        if request.operation == "save":
            if request.draft is None:
                raise ValueError("An investigation draft is required")
            record = save(result, request.controller, request.draft, store)
        elif request.operation == "comparison":
            record = owned(store, "decision-comparison", request.id, result, request.controller)
            return dict(key=request.key, id=request.id, record=record)
        else:
            record = dict(
                id=request.id,
                **owned(store, "investigation", request.id, result, request.controller),
            )
        return dict(key=request.key, record=record, html=report(record))
    except (ValueError, KeyError, IndexError, TypeError, FileNotFoundError) as exc:
        raise HTTPException(400, str(exc)) from exc
