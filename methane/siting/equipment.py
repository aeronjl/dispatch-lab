"""Equipment evidence attached to immutable designs, never inferred calibration.

Evidence assessments do not impose OEM interlocks. Optional plant interfaces are
explicit design edits with their own reduced execution contract; real hardware
control remains outside the app.
"""

import csv
import io
import json
import math
from copy import deepcopy
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field

from methane.config import Config
from methane.integration import describe as describe_integration
from methane.provenance import LOADED_CAPSULE, LOADED_FILES, LOADED_SOURCE
from methane.siting.contracts import Record
from methane.siting.store import digest, encode
from methane.timebase import stamp, utc

CHANNELS = {
    "electrolyser_kw": (
        "electrolyser",
        "kW",
        "Hourly mean productive load EXCLUDING startup and external auxiliaries",
        "applied.electrolyser_kw",
    ),
    "h2_produced_kg": ("electrolyser", "kg", "Hydrogen produced during the hour", "h2_produced_kg"),
    "methane_kg": ("reactor", "kg", "Methane produced during the hour", "applied.methane_kg"),
    "battery_kwh": ("battery", "kWh", "Stored energy at the END of the hour", "state.battery_kwh"),
    "reactor_temperature_c": (
        "reactor",
        "°C",
        "Reactor temperature at the END of the hour",
        "state.temperature_c",
    ),
    "ambient_c": ("solar", "°C", "Hourly mean ambient temperature", "ambient_c"),
    "process_ac_kw": (
        "electrolyser",
        "kW",
        "Hourly mean combined process AC load, including external auxiliaries",
        "integration.ac_kw",
    ),
    "process_dc_kw": (
        "electrolyser",
        "kW",
        "Hourly mean DC input to the process AC island",
        "integration.dc_kw",
    ),
    "electrolyser_ac_kw": (
        "electrolyser",
        "kW",
        "Hourly mean electrolyser base AC load INCLUDING startup, excluding external auxiliaries",
        "integration.electrolyser_ac_kw",
    ),
    "external_cooling_kw": (
        "electrolyser",
        "kW",
        "Hourly mean external electrolyser heat rejection, thermal kW",
        "integration.cooling_heat_kw",
    ),
    "cooler_kw": (
        "electrolyser",
        "kW",
        "Hourly mean external cooler electric load",
        "integration.cooler_kw",
    ),
    "water_consumed_l": (
        "electrolyser",
        "L",
        "Purified water consumed during the hour",
        "integration.water_consumed_l",
    ),
    "water_l": (
        "electrolyser",
        "L",
        "Purified-water inventory at the END of the hour",
        "integration.ending_water_l",
    ),
}
BOUNDARY = "Recorded simulation versus supplied observations, not causal policy validation or automatic calibration. Inputs, weather, actions and initial states may differ. No hardware commands are issued."


def get_path(value, path):
    for part in path.split("."):
        if not isinstance(value, dict) or part not in value:
            return None
        value = value[part]
    return value


def reference():
    return json.loads(LOADED_FILES["docs/equipment-reference.json"])


def identities(config):
    from methane.components import assemble

    c = Config.from_dict(config)
    return {
        **assemble(c.plant, c.models).identities(),
        "execution_source_hash": digest(
            {
                k: v
                for k, v in LOADED_SOURCE["files"].items()
                if k.endswith(".py") and not k.startswith("tests/")
            }
        ),
    }


def proposal(store, project_id):
    p = store.get("project", project_id)
    config = deepcopy(p["config"])
    changes = []
    for b in reference()["bindings"]:
        node = config
        parts = b["path"].split(".")
        for part in parts[:-1]:
            node = node[part]
        old = node[parts[-1]]
        node[parts[-1]] = b["value"]
        if old != b["value"]:
            changes.append(dict(**b, previous=old))
    c = Config.from_dict(config)
    # Existing optional service/lifecycle mechanisms are not erased or endorsed.
    return dict(reference=reference(), config=c.to_dict(), changes=changes)


def attach(store, project_id):
    from methane.siting import projects

    p = store.get("project", project_id)
    site = store.get("site", p["site_revision"])
    if site["country"] not in {"GB", "ES", "DK", "DE", "FR", "NL", "IT", "PT"}:
        raise ValueError("This reference is scoped to the supported European sites")
    v = proposal(store, project_id)
    basis = dict(
        version="equipment-basis/1",
        reference=v["reference"],
        site_revision=p["site_revision"],
        model_identities=identities(v["config"]),
        selected_at=datetime.now(UTC).isoformat(),
    )
    return projects.revise(
        store, project_id, v["config"], equipment_basis_id=store.put("equipment-basis", basis)
    )


def applicability(store, key, config, site_revision):
    if not key:
        return dict(
            status="unidentified",
            checks=[],
            gaps=["No equipment basis was attached to this design."],
        )
    basis = store.get("equipment-basis", key)
    checks = [
        dict(
            **b,
            actual=get_path(config, b["path"]),
            status="matches" if get_path(config, b["path"]) == b["value"] else "changed",
        )
        for b in basis["reference"]["bindings"]
    ]
    models_match = basis["model_identities"] == identities(config)
    site_match = basis["site_revision"] == site_revision
    gaps = [
        dict(asset=a["id"], component=a["component"], detail=a["gaps"])
        for a in basis["reference"]["assets"]
    ]
    if config.get("service_system") or config.get("lifecycle"):
        gaps.append(
            dict(
                asset="SUPPORT-01",
                component="services",
                detail="Additional service or lifecycle mechanisms are configured; their capability and support assumptions need separate review.",
            )
        )
    return dict(
        basis_id=key,
        reference=basis["reference"],
        model_identities=basis["model_identities"],
        status="reference assumptions match"
        if site_match and models_match and all(c["status"] == "matches" for c in checks)
        else "review changed assumptions",
        site_matches=site_match,
        models_match=models_match,
        checks=checks,
        gaps=gaps,
        qualification="Specification-informed candidate; not commissioned or calibrated. Matching selected parameters does not establish site feasibility. Plant interfaces, if enabled, use a separate disclosed model. OEM envelopes and installed support evidence still require review.",
    )


def context(store, project_id=None, study_id=None, case_id=None):
    from methane.siting import production, projects

    if study_id:
        s = production.inspect(store, study_id)
        case = next((c for c in s["cases"] if c["case_id"] == case_id), None)
        if case is None:
            raise ValueError("Choose a recorded study case")
        did = case["design_id"]
        d = store.get("design", did)
        assessment = case.get("equipment_applicability") or dict(
            status="Original equipment explanations unavailable", checks=[], gaps=[]
        )
        basis_id = d.get("equipment_basis_id")
        # Older cases never receive current explanations as original evidence.
        model_ids = assessment.get("model_identities")
    else:
        if not project_id:
            raise ValueError("Choose a project or study case")
        p = store.get("project", project_id)
        did = projects.design(store, project_id)
        d = store.get("design", did)
        basis_id = p.get("equipment_basis_id")
        assessment = applicability(store, basis_id, p["config"], p["site_revision"])
        model_ids = identities(p["config"])
    basis = store.get("equipment-basis", basis_id) if basis_id else None
    reviews = [r for r in store.list("commissioning-review") if r["design_id"] == did]
    datasets = [r for r in store.list("equipment-observations") if r["design_id"] == did]
    gates = []
    for gate in (basis or {}).get("reference", {}).get("gates", []):
        history = sorted(
            [r for r in reviews if r["gate"] == gate["id"]], key=lambda r: r["recorded_at"]
        )
        latest = history[-1] if history else None
        gates.append(
            dict(
                **gate,
                latest=latest,
                status="not reviewed"
                if not latest
                else "stale model binding"
                if latest["model_identities"] != model_ids
                else latest["outcome"],
            )
        )
    return dict(
        design_id=did,
        basis_id=basis_id,
        site=store.get("site", d["site_revision"]),
        context="This run · original equipment basis"
        if study_id
        else "Current design · equipment basis",
        assessment=assessment,
        gates=gates,
        integration=describe_integration(d["config"]["plant"].get("integration")),
        datasets=[
            {
                k: r[k]
                for k in ("id", "name", "origin", "channel", "asset", "row_count", "start", "end")
            }
            for r in datasets
        ],
        comparisons=[
            {k: r[k] for k in ("id", "title", "status", "created_at", "study_id", "case_id")}
            for r in store.list("equipment-comparison")
            if r["design_id"] == did and (not study_id or r["study_id"] == study_id)
        ],
        channels={k: dict(component=v[0], unit=v[1], timing=v[2]) for k, v in CHANNELS.items()},
        evidence_plan=json.loads(LOADED_FILES["docs/equipment-evidence-plan.json"]),
        protocols=[
            r
            for r in store.list("equipment-qualification-protocol")
            if r["design_id"] == did
            and (not study_id or r["study_id"] == study_id and r["case_id"] == case_id)
        ],
        qualifications=[
            {k: r[k] for k in ("id", "title", "status", "created_at")}
            for r in store.list("equipment-qualification")
            if r["design_id"] == did
            and (not study_id or r["study_id"] == study_id and r["case_id"] == case_id)
        ],
        limitation="Reviews are user-authored acceptance records, not certifications. A different design requires a new review; historical records remain unchanged.",
    )


class Review(Record):
    design_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    gate: str
    outcome: Literal["accepted by reviewer", "failed", "incomplete"]
    reviewer: str = Field(min_length=1, max_length=200)
    artifact_name: str = Field(min_length=1, max_length=300)
    artifact_text: str = Field(min_length=1, max_length=50000)
    rationale: str = Field(min_length=1, max_length=4000)


def review(store, data):
    r = Review(**data)
    if any(not v.strip() for v in (r.reviewer, r.artifact_name, r.artifact_text, r.rationale)):
        raise ValueError("A review requires a named reviewer, evidence artifact and rationale")
    d = store.get("design", r.design_id)
    if not d.get("equipment_basis_id"):
        raise ValueError("Attach an equipment basis before recording commissioning evidence")
    basis = store.get("equipment-basis", d["equipment_basis_id"])
    if r.gate not in {g["id"] for g in basis["reference"]["gates"]}:
        raise ValueError("Unknown commissioning gate")
    value = dict(
        version="commissioning-review/1",
        **r.model_dump(),
        basis_id=d["equipment_basis_id"],
        model_identities=identities(d["config"]),
        recorded_at=datetime.now(UTC).isoformat(),
        artifact_sha256=store.raw(r.artifact_text.encode()),
        scope="User-authored review; authenticity and sufficiency of the supplied artifact are not independently established.",
    )
    return dict(id=store.put("commissioning-review", value), **value)


class ObservationImport(Record):
    design_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(min_length=1, max_length=160)
    channel: str
    unit: str
    asset: str = Field(min_length=1, max_length=200)
    origin: Literal["site measurement", "synthetic test"]
    supplied_by: str = Field(min_length=1, max_length=200)
    source_reference: str = Field(min_length=1, max_length=2000)
    method: str = Field(min_length=1, max_length=2000)
    uncertainty_absolute: float = Field(ge=0)
    redistribution: Literal["permitted", "reference-only"] = "reference-only"
    csv_text: str = Field(min_length=1, max_length=200000)


def observations(store, data):
    m = ObservationImport(**data)
    d = store.get("design", m.design_id)
    if not d.get("equipment_basis_id"):
        raise ValueError("Attach an equipment basis before importing observations")
    if m.channel not in CHANNELS or m.unit != CHANNELS[m.channel][1]:
        raise ValueError("Choose a supported channel and its exact unit; no implicit conversion")
    for v in (m.name, m.asset, m.supplied_by, m.source_reference, m.method):
        if not v.strip():
            raise ValueError("Observation provenance fields must not be blank")
    reader = csv.DictReader(io.StringIO(m.csv_text))
    if reader.fieldnames != ["timestamp", "value", "quality"]:
        raise ValueError("CSV columns must be timestamp,value,quality in that order")
    rows = []
    seen = set()
    for raw in reader:
        if None in raw or None in raw.values():
            raise ValueError("Each observation must have exactly three CSV fields")
        t = datetime.fromisoformat(raw["timestamp"].replace("Z", "+00:00"))
        if t.tzinfo is None or t.minute or t.second or t.microsecond:
            raise ValueError("Each timestamp requires an explicit offset and exact hourly boundary")
        t = t.astimezone(UTC)
        if t.minute or t in seen:
            raise ValueError("Duplicate or non-hourly UTC observation")
        seen.add(t)
        quality = raw["quality"]
        if quality not in ("valid", "suspect", "missing"):
            raise ValueError("Quality must be valid, suspect or missing")
        value = float(raw["value"]) if raw["value"].strip() else None
        if quality != "missing" and value is None or quality == "missing" and value is not None:
            raise ValueError("Missing rows require blank values; valid/suspect rows require values")
        if value is not None and (
            not math.isfinite(value)
            or value < 0
            and m.channel not in {"ambient_c", "reactor_temperature_c"}
        ):
            raise ValueError(
                "Observation values must be finite; negative values require a temperature channel"
            )
        rows.append(dict(timestamp=stamp(t), value=value, quality=quality))
    if not 1 <= len(rows) <= 744:
        raise ValueError("Import 1–744 hourly observations per dataset")
    rows.sort(key=lambda r: r["timestamp"])
    if utc(rows[-1]["timestamp"]) - utc(rows[0]["timestamp"]) > timedelta(hours=743):
        raise ValueError("One comparison window is limited to 744 hours")
    value = dict(
        version="equipment-observations/1",
        **m.model_dump(exclude={"csv_text"}),
        rows=rows,
        row_count=len(rows),
        start=rows[0]["timestamp"],
        end=rows[-1]["timestamp"],
        raw_sha256=store.raw(m.csv_text.encode()),
        recorded_at=datetime.now(UTC).isoformat(),
        timing="Timestamp is UTC-normalized interval START; inventory channels refer to that interval's END. No resampling or interpolation.",
        qualification="Origin, uncertainty and method are supplied assertions, not independently authenticated site evidence.",
    )
    return dict(id=store.put("equipment-observations", value), **value)


def compare(store, dataset_id, study_id, case_id):
    from methane.siting import production

    observed = store.get("equipment-observations", dataset_id)
    s = production.inspect(store, study_id)
    c = next((c for c in s["cases"] if c["case_id"] == case_id), None)
    if not c or c["design_id"] != observed["design_id"]:
        raise ValueError("Observed asset/configuration must match the exact recorded design")
    env = store.get("environment", c["environment_id"])
    first = utc(env["start"])
    hours = {int((utc(r["timestamp"]) - first).total_seconds() / 3600): r for r in observed["rows"]}
    if min(hours) < 0 or max(hours) >= c["hours"]:
        raise ValueError("Observation timestamps lie outside the recorded case window")
    channel = CHANNELS[observed["channel"]]
    predictions = {}
    # Decode only committed partitions intersecting this bounded observation window.
    for entry in c["periods"]:
        if entry["next_hour"] <= min(hours) or entry["start_hour"] > max(hours):
            continue
        period = production.load_period(store, entry["period_sha256"])
        for i, r in enumerate(period["records"][c["controller"]]):
            h = entry["start_hour"] + i
            if min(hours) <= h <= max(hours):
                predictions[h] = dict(
                    value=get_path(r, channel[3]),
                    trace=dict(
                        kind="site-study",
                        edition_id=study_id,
                        case_id=case_id,
                        period_sha256=entry["period_sha256"],
                        controller=c["controller"],
                        hour=i,
                        component=channel[0],
                    ),
                )
    rows = []
    for h in range(min(hours), max(hours) + 1):
        o = hours.get(
            h, dict(timestamp=stamp(first + timedelta(hours=h)), value=None, quality="absent")
        )
        p = predictions.get(h, {})
        included = o["quality"] == "valid" and p.get("value") is not None
        rows.append(
            dict(
                hour=h,
                **o,
                simulated=p.get("value"),
                residual=p["value"] - o["value"] if included else None,
                trace=p.get("trace"),
                status="compared"
                if included
                else "simulation unavailable"
                if p.get("value") is None
                else "observation " + o["quality"],
            )
        )
    residuals = [r["residual"] for r in rows if r["residual"] is not None]
    value = dict(
        version="equipment-comparison/1",
        title=observed["name"] + " / recorded operation",
        design_id=c["design_id"],
        dataset_id=dataset_id,
        study_id=study_id,
        study_ids=[study_id],
        case_id=case_id,
        created_at=datetime.now(UTC).isoformat(),
        comparison_source=LOADED_SOURCE["content_hash"],
        capsule_raw_sha256=store.raw(encode(LOADED_CAPSULE)),
        simulation_source=s["manifest"]["source"],
        observation_metadata={k: v for k, v in observed.items() if k != "rows"},
        channel=observed["channel"],
        unit=channel[1],
        rows=rows,
        matched=len(residuals),
        expected=len(rows),
        status="complete comparison" if len(residuals) == len(rows) else "incomplete comparison",
        bias=sum(residuals) / len(residuals) if residuals else None,
        rmse=math.sqrt(sum(r * r for r in residuals) / len(residuals)) if residuals else None,
        boundary=BOUNDARY,
        equipment_applicability=c.get("equipment_applicability"),
        qualification="Synthetic exercise; no field evidence"
        if observed["origin"] == "synthetic test"
        else "User-supplied measurements; provenance and comparability require expert review",
    )
    return dict(id=store.put("equipment-comparison", value), **value)


def save_integration(store, project_id, values):
    from methane.integration import Integration
    from methane.siting import projects

    p = store.get("project", project_id)
    c = deepcopy(p["config"])
    if values is None:
        c["plant"].pop("integration", None)
    else:
        c["plant"]["integration"] = Integration(**values).to_dict()
    return projects.revise(store, project_id, Config.from_dict(c).to_dict())


def integration_trace(store, study_id, case_id, hour):
    from methane.siting import production

    s = production.inspect(store, study_id)
    c = next((c for c in s["cases"] if c["case_id"] == case_id), None)
    if c is None or type(hour) is not int or not 0 <= hour < c["hours"]:
        raise ValueError("Select an interval within this recorded case")
    entry = next((e for e in c["periods"] if e["start_hour"] <= hour < e["next_hour"]), None)
    if entry is None:
        return dict(status="This interval has not been recorded", hour=hour)
    period = production.load_period(store, entry["period_sha256"])
    index = hour - entry["start_hour"]
    row = period["records"][c["controller"]][index]
    return dict(
        status="Recorded execution"
        if row.get("integration")
        else "This run has no recorded plant-interface model; current assumptions have not been substituted",
        hour=hour,
        timestamp=row.get("time"),
        record=row.get("integration"),
        source=period.get("provenance", {}).get("source"),
        decision=row["decision"].get("evidence", {}),
        trace=dict(
            kind="site-study",
            edition_id=study_id,
            case_id=case_id,
            period_sha256=entry["period_sha256"],
            controller=c["controller"],
            hour=index,
            component="electrolyser",
        ),
    )


def perform(store, operation, key, data):
    if operation.startswith("equipment-literature-"):
        from methane.literature.service import perform as literature

        return literature(store, operation, key, data)

    if operation.startswith("equipment-qualification"):
        from methane.siting import equipment_qualification as qualification

        if operation == "equipment-qualification-freeze":
            return qualification.freeze(store, data)
        if operation == "equipment-qualification-evaluate":
            return qualification.evaluate(store, key)
        if operation == "equipment-qualification-result":
            return qualification.current(store, key)
    if operation == "equipment-integration-preview":
        from methane.researched_models import preview

        c = deepcopy(store.get("project", key)["config"])
        c["plant"]["integration"] = data["values"]
        return preview(Config.from_dict(c).plant)
    if operation == "equipment-integration-save":
        return save_integration(store, key, data["values"])
    if operation == "equipment-integration-trace":
        return integration_trace(store, **data)
    if operation == "equipment-result":
        return dict(id=key, **store.get("equipment-comparison", key))
    if operation == "equipment-proposal":
        return proposal(store, key)
    if operation == "equipment-attach":
        return attach(store, key)
    if operation == "equipment-context":
        return context(store, **data)
    if operation == "equipment-review":
        return review(store, data)
    if operation == "equipment-observations":
        return observations(store, data)
    if operation == "equipment-compare":
        return compare(store, **data)
    raise ValueError("Unknown equipment planning operation")
