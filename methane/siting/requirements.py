"""Versioned outcome requirements. Assessment never changes recorded dispatch."""

from collections import defaultdict
from math import isfinite
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from methane.siting.store import digest, encode

VERSION = "operating-requirements/1"
ASSESSMENT = "operating-assessment/1"


class Brief(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    version: Literal["operating-requirements/1"] = VERSION
    name: str = Field(min_length=1, max_length=160)
    rationale: str = Field(default="", max_length=4000)
    after_hour: int = Field(default=0, ge=0, le=87600, strict=True)
    window_hours: int = Field(default=24, ge=1, le=168, strict=True)
    methane_kg: float | None = Field(default=None, gt=0)
    shortfall_kg: float = Field(default=0, ge=0)
    battery_kwh: float | None = Field(default=None, ge=0)
    hydrogen_kg: float | None = Field(default=None, ge=0)
    co2_kg: float | None = Field(default=None, ge=0)
    forced_downtime_hours: float | None = Field(default=None, ge=0)
    dock_unserved_kwh: float | None = Field(default=None, ge=0)
    escalation_hours: float | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def meaningful(self):
        if not self.name.strip():
            raise ValueError("Give the operating brief a name")
        if self.shortfall_kg and (self.methane_kg is None or self.shortfall_kg > self.methane_kg):
            raise ValueError("Allowed shortfall requires a production target and cannot exceed it")
        if all(getattr(self, k) is None for k in RULES):
            raise ValueError("Declare at least one requirement; blank means not assessed")
        return self


# Stable identifiers, not arbitrary expressions supplied by the browser.
RULES = {
    "methane_kg": ("Methane per window", "reactor", "kg"),
    "battery_kwh": ("Battery reserve", "battery", "kWh"),
    "hydrogen_kg": ("Hydrogen reserve", "hydrogen", "kg"),
    "co2_kg": ("CO₂ reserve", "co2", "kg"),
    "forced_downtime_hours": ("Forced trips", "reactor", "h"),
    "dock_unserved_kwh": ("Unserved dock energy", "services", "kWh"),
    "escalation_hours": ("Recovery escalation", "electrolyser", "h"),
}
BOUNDARIES = [
    "Outcome assessment only: requirements do not alter dispatch objectives or impose new controller constraints.",
    "Methane means modelled production, not delivery, quality certification or customer acceptance. Fixed windows begin at the declared assessment hour; the final window and its allowance are prorated. Surplus in another window cannot cancel a shortfall.",
    "Reserves use recorded physical inventories at every interval boundary, including the assessment start. These are retrospective simulated states, not controller observations.",
    "Service limits measure recorded forced trips, unserved dock energy and observer-based escalation. No incident in a case is not evidence of recovery capability. Missing channels stay unassessed.",
    "Ranges describe the selected scenarios and numerical repetitions, not probabilities or guarantees. Missing cases, unmatched exposure, different source versions and design/evaluation roles remain visible. No overall ranking is calculated.",
    "Allocation and ending inventories cover the entire case, including any excluded warm-up. Costs retain the original assumptions; reserves receive no speculative sale proceeds.",
]


def save(store, data):
    value = Brief(**data).model_dump(mode="json")
    return dict(id=store.put("requirements", value), **value)


def escalation(row):
    from methane.recovery import LOOP_VERSIONS

    value = (row.get("decision") or {}).get("recovery_planning") or {}
    if value.get("version") not in LOOP_VERSIONS:
        return None
    return int(value["status"] == "escalation-required")


def check_rows(brief, rows, plant, expected_hours):
    """Pure hourly accounting, independently testable without a solver or archive."""
    b = Brief(**brief)
    rows = list(rows)
    if [r["hour"] for r in rows] != list(range(len(rows))):
        raise ValueError("Assessment requires consecutive recorded hours from zero")
    if len(rows) > expected_hours:
        raise ValueError("Recorded hours exceed the declared case")
    active = rows[b.after_hour :]
    complete = len(rows) == expected_hours and bool(active)
    checks = []

    def add(key, actual, limit, hour, *, lower=False, detail=None):
        label, component, unit = RULES[key]
        margin = None if actual is None else actual - limit if lower else limit - actual
        checks.append(
            dict(
                key=key,
                label=label,
                component=component,
                unit=unit,
                actual=actual,
                limit=limit,
                margin=margin,
                relation=">=" if lower else "<=",
                hour=hour,
                status="missing" if actual is None else "met" if margin >= -1e-7 else "unmet",
                detail=detail,
            )
        )

    windows = []
    if b.methane_kg is not None:
        for start in range(b.after_hour, expected_hours, b.window_hours):
            end = min(expected_hours, start + b.window_hours)
            target = b.methane_kg * (end - start) / b.window_hours
            allowance = b.shortfall_kg * (end - start) / b.window_hours
            values = rows[start:end]
            valid = len(values) == end - start and all(
                isinstance(r.get("applied", {}).get("methane_kg"), (int, float)) for r in values
            )
            output = sum(r["applied"]["methane_kg"] for r in values) if valid else None
            windows.append(
                dict(
                    start=start,
                    end=end,
                    target=target,
                    allowance=allowance,
                    output=output,
                    shortfall=None if output is None else max(0, target - output),
                )
            )
        valid = [w for w in windows if w["output"] is not None]
        worst = (
            min(valid, key=lambda w: w["output"] - w["target"] + w["allowance"]) if valid else None
        )
        add(
            "methane_kg",
            worst["output"] if worst else None,
            worst["target"] - worst["allowance"] if worst else b.methane_kg - b.shortfall_kg,
            worst["start"] if worst else None,
            lower=True,
            detail="Worst absolute window margin; allowances and incomplete windows retained individually",
        )
        if len(valid) != len(windows):
            complete = False
    for key, state_key, initial in (
        ("battery_kwh", "battery_kwh", plant["battery_kwh"] * plant["initial_soc"]),
        ("hydrogen_kg", "h2_kg", plant["initial_h2_kg"]),
        ("co2_kg", "co2_kg", plant["initial_co2_kg"]),
    ):
        if getattr(b, key) is None:
            continue
        boundaries = [(0, initial)] if b.after_hour == 0 else []
        boundaries += [
            (r["hour"] + 1, r.get("state", {}).get(state_key))
            for r in rows[max(0, b.after_hour - 1) :]
        ]
        valid = bool(active) and bool(boundaries) and all(v is not None for _, v in boundaries)
        worst = min(boundaries, key=lambda x: x[1]) if valid else (None, None)
        add(
            key,
            worst[1],
            getattr(b, key),
            max(0, worst[0] - 1) if valid else None,
            lower=True,
            detail=dict(boundary_hour=worst[0], timing="Initial or ending physical inventory"),
        )
    for key, getter in (
        ("forced_downtime_hours", lambda r: r.get("forced_trip")),
        (
            "dock_unserved_kwh",
            lambda r: ((r.get("field_operations") or {}).get("standby") or {}).get("unserved_kwh"),
        ),
        (
            "escalation_hours",
            escalation,
        ),
    ):
        if getattr(b, key) is None:
            continue
        values = [getter(r) for r in active]
        valid = bool(values) and all(v is not None for v in values)
        total = sum(values) if valid else None
        crossing, running = None, 0
        if valid:
            for r, v in zip(active, values, strict=True):
                running += v
                if running > getattr(b, key) + 1e-7:
                    crossing = r["hour"]
                    break
        add(
            key,
            total,
            getattr(b, key),
            crossing,
            detail="Cumulative within assessed hours; zero events do not demonstrate service capability",
        )
    for item in checks:
        if item["actual"] is not None and not isfinite(item["actual"]):
            raise ValueError("Non-finite recorded operand")
    return dict(
        status="incomplete"
        if not complete
        else "unmet"
        if any(c["status"] == "unmet" for c in checks)
        else "unassessed"
        if any(c["status"] == "missing" for c in checks)
        else "met",
        checks=checks,
        windows=windows,
        assessed_hours=len(active),
        shortfall_kg=sum(w["shortfall"] for w in windows)
        if windows and all(w["shortfall"] is not None for w in windows)
        else None,
    )


def freeze(store, requirements_id, study_ids, title="Operating requirements comparison"):
    """Freeze only committed partitions before the worker starts; later progress is excluded."""
    from methane.siting.production import inspect

    Brief(**store.get("requirements", requirements_id))
    if not 1 <= len(study_ids) <= 24 or len(set(study_ids)) != len(study_ids):
        raise ValueError("Select 1–24 distinct studies")
    if not isinstance(title, str) or not title.strip() or len(title) > 160:
        raise ValueError("Comparison title must contain 1–160 characters")
    studies = [inspect(store, sid) for sid in study_ids]
    if sum(len(s["cases"]) for s in studies) > 192:
        raise ValueError("Assessment budget is 192 cases")
    if (
        sum(sum(p["interval_count"] for p in c["periods"]) for s in studies for c in s["cases"])
        > 100000
    ):
        raise ValueError("Assessment budget is 100,000 recorded intervals; select fewer studies")
    return dict(requirements_id=requirements_id, study_ids=study_ids, title=title, studies=studies)


def evaluate(store, *, requirements_id, study_ids, title, studies, progress=lambda text: None):
    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE
    from methane.siting.production import read_blob

    brief = store.get("requirements", requirements_id)
    candidates = []
    for study in studies:
        sid, manifest = study["id"], study["manifest"]
        # Job arguments are created by freeze on the server, not accepted from clients.
        if store.get("study", sid) != manifest:
            raise ValueError("Frozen manifest does not match its saved identity")
        for case in study["cases"]:
            progress(f"Assessing {manifest['name']} / {case['label']}")
            rows, refs = [], []
            for p in case["periods"]:
                progress(f"Reading {case['case_id']} / hour {p['start_hour']}")
                value = read_blob(store, p["period_sha256"])
                part = value.get("value", value)["records"][case["controller"]]
                if p["start_hour"] != len(rows) or len(part) != p["interval_count"]:
                    raise ValueError("Partition boundary mismatch")
                # Keep only assessment operands and recorded decision evidence in memory.
                for r in part:
                    rows.append(
                        {k: r[k] for k in ("hour", "applied", "state", "forced_trip") if k in r}
                        | {
                            "field_operations": {
                                "standby": (r.get("field_operations") or {}).get("standby", {})
                            },
                            "decision": {
                                k: r.get("decision", {})[k]
                                for k in ("recovery_planning", "evidence")
                                if k in r.get("decision", {})
                            },
                        }
                    )
                    refs.append(
                        dict(
                            kind="site-study",
                            edition_id=sid,
                            case_id=case["case_id"],
                            period_sha256=p["period_sha256"],
                            controller=case["controller"],
                            hour=r["hour"] - p["start_hour"],
                        )
                    )
            result = check_rows(brief, rows, case["config"]["plant"], case["hours"])
            if manifest["mode"] == "resource":
                result["status"] = "unassessed"
            for c in result["checks"]:
                hour = c["hour"]
                if hour is not None and hour < len(rows):
                    c["trace"] = dict(refs[hour], component=c["component"])
                    evidence = rows[hour].get("decision", {}).get("evidence", {})
                    c["recorded_context"] = dict(
                        constraints=evidence.get("constraints", []),
                        bindings=evidence.get("bindings", {}).get(c["component"], []),
                        scope="Original decision estimates/predicted bounds, not a causal attribution of this shortfall",
                    )
            env = store.get("environment", case["environment_id"])
            design = store.get("design", case["design_id"])
            site = store.get("site", design["site_revision"])
            candidates.append(
                dict(
                    **result,
                    id=sid + "/" + case["case_id"],
                    study_id=sid,
                    case_id=case["case_id"],
                    label=case["label"],
                    site=site["name"],
                    design_id=case["design_id"],
                    design_name=design["name"],
                    site_revision=design["site_revision"],
                    environment_id=case["environment_id"],
                    controller=case["controller"],
                    role=case["role"],
                    seed=case["config"]["scenario"]["seed"],
                    repetition=case["repetition"],
                    hours=case["hours"],
                    completed_hours=len(rows),
                    summary=case["summary"],
                    source=manifest["source"]["content_hash"],
                    policy_id=digest(case.get("policy")),
                    uncertainty=case.get("uncertainty"),
                    config_id=digest(case["config"]),
                    environment={k: env[k] for k in ("start", "end", "information", "reference")},
                    original_requirements_id=manifest.get("requirements_id"),
                    assessment_context="declared before execution"
                    if manifest.get("requirements_id") == requirements_id
                    else "retrospective assessment with a different or previously undeclared brief",
                    periods=case["periods"],
                    capacity_conflicts=capacity_conflicts(brief, case["config"]["plant"]),
                    search_exclusion_count=len(
                        (manifest.get("search") or {}).get("exclusions", [])
                    ),
                )
            )
    groups = aggregate(candidates)
    value = dict(
        version=ASSESSMENT,
        title=title,
        requirements_id=requirements_id,
        brief=brief,
        study_ids=study_ids,
        candidates=candidates,
        groups=groups,
        boundaries=BOUNDARIES,
        source=LOADED_SOURCE,
        capsule_raw_sha256=store.raw(encode(LOADED_CAPSULE)),
        exclusions=[
            dict(
                study_id=s["id"], excluded=(s["manifest"].get("search") or {}).get("exclusions", [])
            )
            for s in studies
        ],
    )
    return dict(id=store.put("operating-assessment", value), **value)


def capacity_conflicts(brief, plant):
    """Necessary nameplate bounds only; clearing these does not establish feasibility."""
    conflicts = []
    for key, capacity in (
        ("battery_kwh", plant["battery_kwh"]),
        ("hydrogen_kg", plant["h2_capacity_kg"]),
        ("co2_kg", plant["co2_capacity_kg"]),
        ("methane_kg", plant["methane_max_kgph"] * brief["window_hours"]),
    ):
        target = brief.get(key)
        if target is None:
            continue
        target -= brief["shortfall_kg"] if key == "methane_kg" else 0
        if target > capacity + 1e-7:
            conflicts.append(
                dict(
                    component=RULES[key][1],
                    requirement=key,
                    required=target,
                    nameplate_bound=capacity,
                    unit=RULES[key][2],
                    scope="Requirement exceeds the configured physical ceiling; independent of dispatch",
                )
            )
    return conflicts


def aggregate(candidates):
    """No probabilities, rankings or cross-source pooling. Missing exposure stays visible."""
    grouped, universe = defaultdict(list), set()
    for c in candidates:
        # Coordinates intentionally vary for site comparisons. Unknown world differences
        # stay distinct instead of being asserted to be matched draws across designs.
        cell = digest(
            dict(
                environment=c["environment"],
                seed=c["seed"],
                repetition=c["repetition"],
                uncertainty=c["uncertainty"],
            )
        )
        c["exposure_id"] = cell
        universe.add(cell)
        grouped[(c["design_id"], c["controller"], c["policy_id"], c["role"], c["source"])].append(c)
    groups = []
    for cases in grouped.values():
        present = {c["exposure_id"] for c in cases}

        def extent(values):
            valid = [v for v in values if v is not None]
            return (
                dict(min=min(valid), max=max(valid), recorded=len(valid), declared=len(values))
                if valid
                else None
            )

        groups.append(
            dict(
                design_id=cases[0]["design_id"],
                name=cases[0]["design_name"],
                site=cases[0]["site"],
                controller=cases[0]["controller"],
                role=cases[0]["role"],
                source=cases[0]["source"],
                counts={
                    k: sum(c["status"] == k for c in cases)
                    for k in ("met", "unmet", "incomplete", "unassessed")
                },
                case_ids=[c["id"] for c in cases],
                missing_exposures=sorted(universe - present),
                exposure_count=len(present),
                declared_exposure_count=len(universe),
                all_selected_requirements_met=present == universe
                and all(
                    c["status"] == "met" and not c.get("search_exclusion_count") for c in cases
                ),
                search_exclusions_present=any(c.get("search_exclusion_count") for c in cases),
                shortfall_kg=extent([c["shortfall_kg"] for c in cases]),
                allocated_eur=extent([(c["summary"] or {}).get("total_eur") for c in cases]),
                methane_kg=extent([(c["summary"] or {}).get("methane_kg") for c in cases]),
            )
        )
    return groups
