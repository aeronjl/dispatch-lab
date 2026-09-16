"""Frozen, scoped measurement assessments; never a plant-readiness certificate."""

import math
from datetime import UTC, datetime

from pydantic import Field, model_validator

from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE
from methane.siting.contracts import Record
from methane.siting.store import encode

BOUNDARY = (
    "Retrospective comparison of a recorded design with supplied measurements. "
    "Evaluation is separate from development, but neither blind preregistration nor "
    "independence from earlier model selection is established. No parameter fitting, "
    "plant certification or automatic design change. Weather, actions, initial state "
    "and measurement boundaries require expert review."
)


class Protocol(Record):
    title: str = Field(min_length=1, max_length=160)
    study_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    case_id: str = Field(min_length=1)
    dataset_id: str = Field(pattern=r"^[a-f0-9]{64}$")
    start_hour: int = Field(ge=0, strict=True)
    split_hour: int = Field(ge=1, strict=True)
    end_hour: int = Field(ge=2, strict=True)
    minimum_coverage: float = Field(gt=0, le=1)
    minimum_pairs: int = Field(ge=1, strict=True)
    max_rmse: float = Field(ge=0)
    max_absolute_bias: float = Field(ge=0)
    comparable: bool = Field(strict=True)
    rationale: str = Field(min_length=1, max_length=4000)
    reviewer: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def boundaries(self):
        if not self.start_hour < self.split_hour < self.end_hour:
            raise ValueError("Use non-overlapping development then evaluation windows")
        if self.end_hour - self.start_hour > 744:
            raise ValueError("One qualification window is limited to 744 hours")
        if self.minimum_pairs > self.end_hour - self.split_hour:
            raise ValueError("Minimum pairs exceeds the evaluation window")
        if any(not s.strip() for s in (self.title, self.rationale, self.reviewer)):
            raise ValueError("Name the reviewer, scope and rationale for these criteria")
        return self


def freeze(store, data):
    from methane.siting import equipment, production

    p = Protocol(**data)
    study = production.inspect(store, p.study_id)
    case = next((c for c in study["cases"] if c["case_id"] == p.case_id), None)
    observed = store.get("equipment-observations", p.dataset_id)
    if not case or case["design_id"] != observed["design_id"]:
        raise ValueError("Qualification requires the exact observed design and recorded case")
    if p.end_hour > case["hours"]:
        raise ValueError("Qualification window exceeds the recorded case")
    value = dict(
        version="equipment-qualification-protocol/1",
        **p.model_dump(),
        design_id=case["design_id"],
        channel=observed["channel"],
        unit=observed["unit"],
        channel_definition=equipment.CHANNELS[observed["channel"]],
        simulation_source=study["manifest"]["source"],
        created_at=datetime.now(UTC).isoformat(),
        protocol_source=LOADED_SOURCE["content_hash"],
        capsule_raw_sha256=store.raw(encode(LOADED_CAPSULE)),
        boundary=BOUNDARY,
    )
    return dict(id=store.put("equipment-qualification-protocol", value), **value)


def statistics(rows, expected, uncertainty):
    valid = [r for r in rows if r.get("residual") is not None]
    residuals = [r["residual"] for r in valid]
    return dict(
        expected=expected,
        matched=len(valid),
        coverage=len(valid) / expected,
        bias=sum(residuals) / len(valid) if valid else None,
        rmse=math.sqrt(sum(v * v for v in residuals) / len(valid)) if valid else None,
        beyond_measurement_bound=sum(abs(v) > uncertainty for v in residuals),
        # This only ranks recorded discrepancies, not causal importance.
        largest_discrepancies=sorted(valid, key=lambda r: abs(r["residual"]), reverse=True)[:5],
    )


def evaluate(store, protocol_id):
    from methane.siting import equipment

    p = store.get("equipment-qualification-protocol", protocol_id)
    observed = store.get("equipment-observations", p["dataset_id"])
    comparison = equipment.compare(store, p["dataset_id"], p["study_id"], p["case_id"])
    if comparison["simulation_source"] != p["simulation_source"]:
        raise ValueError("Recorded simulation identity differs from the frozen protocol")
    if list(equipment.CHANNELS[p["channel"]]) != list(p["channel_definition"]):
        raise ValueError("Channel boundary changed; create a new reviewed protocol")
    by_hour = {r["hour"]: r for r in comparison["rows"]}
    rows = [
        dict(
            **by_hour.get(
                h,
                dict(hour=h, residual=None, status="No paired observation", trace=None),
            ),
            split="development" if h < p["split_hour"] else "evaluation",
        )
        for h in range(p["start_hour"], p["end_hour"])
    ]
    stats = {
        split: statistics(
            [r for r in rows if r["split"] == split], count, observed["uncertainty_absolute"]
        )
        for split, count in (
            ("development", p["split_hour"] - p["start_hour"]),
            ("evaluation", p["end_hour"] - p["split_hour"]),
        )
    }
    s = stats["evaluation"]
    enough = s["matched"] >= p["minimum_pairs"] and s["coverage"] >= p["minimum_coverage"]
    criteria = [
        dict(
            claim="Paired-hour coverage",
            value=s["coverage"],
            limit=p["minimum_coverage"],
            outcome="passed" if s["coverage"] >= p["minimum_coverage"] else "missing",
        ),
        dict(
            claim="Minimum paired hours",
            value=s["matched"],
            limit=p["minimum_pairs"],
            outcome="passed" if s["matched"] >= p["minimum_pairs"] else "missing",
        ),
    ]
    for key, limit in (("rmse", "max_rmse"), ("bias", "max_absolute_bias")):
        criteria.append(
            dict(
                claim="Evaluation " + key,
                value=s[key],
                limit=p[limit],
                outcome="missing"
                if not enough
                else "passed"
                if abs(s[key]) <= p[limit]
                else "failed",
            )
        )
    status = (
        "unsupported comparison"
        if not p["comparable"]
        else "incomplete evidence"
        if not enough
        else "outside declared criteria"
        if any(c["outcome"] == "failed" for c in criteria)
        else "within declared numerical criteria"
    )
    value = dict(
        version="equipment-qualification/1",
        title=p["title"],
        status=status,
        protocol_id=protocol_id,
        protocol=p,
        comparison_id=comparison["id"],
        study_ids=[p["study_id"]],
        study_id=p["study_id"],
        case_id=p["case_id"],
        design_id=p["design_id"],
        observation_metadata=comparison["observation_metadata"],
        unit=p["unit"],
        rows=rows,
        statistics=stats,
        criteria=criteria,
        qualification=comparison["qualification"],
        boundary=BOUNDARY,
        uncertainty_note="Measurement bounds are supplied assertions, not confidence intervals. Residuals and criteria are not reduced by those bounds; model/input uncertainty is separate.",
        uncertainty_exceeds_tolerance=observed["uncertainty_absolute"]
        > min(p["max_rmse"], p["max_absolute_bias"]),
        created_at=datetime.now(UTC).isoformat(),
        assessment_source=LOADED_SOURCE["content_hash"],
        capsule_raw_sha256=store.raw(encode(LOADED_CAPSULE)),
    )
    return dict(id=store.put("equipment-qualification", value), **value)


def current(store, result_id):
    r = store.get("equipment-qualification", result_id)
    return dict(
        id=result_id,
        **r,
        applicability="Current assessment implementation"
        if r["assessment_source"] == LOADED_SOURCE["content_hash"]
        else "Historical assessment implementation; original outcome retained",
    )
