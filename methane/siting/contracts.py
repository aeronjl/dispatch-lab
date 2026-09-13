"""Strict versioned boundaries; geographical evidence is not a permission or quote."""

from datetime import datetime
from typing import Literal
from zoneinfo import ZoneInfo

from pydantic import BaseModel, ConfigDict, Field, model_validator


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)


class SourceSnapshot(Record):
    schema_version: Literal["site-source/1"] = "site-source/1"
    provider: str = Field(min_length=1, max_length=250)
    product: str = Field(min_length=1, max_length=250)
    edition: str = Field(min_length=1, max_length=250)
    retrieved_at: datetime
    request: dict
    raw_sha256: str = Field(pattern=r"^[a-f0-9]{64}$")
    attribution: str = Field(min_length=1, max_length=2000)
    licence: str = Field(min_length=1, max_length=2000)
    redistribution: Literal["permitted", "reference-only", "unknown"] = "unknown"
    coverage: dict = Field(default_factory=dict)
    units: dict = Field(default_factory=dict)
    timing: str = Field(min_length=1, max_length=2000)
    source_url: str = Field(min_length=1, max_length=3000)

    @model_validator(mode="after")
    def timezone_required(self):
        if self.retrieved_at.tzinfo is None:
            raise ValueError("Retrieval time requires an explicit UTC offset")
        return self


class SiteCandidate(Record):
    schema_version: Literal["site-candidate/1"] = "site-candidate/1"
    site_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    name: str = Field(min_length=1, max_length=160)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    timezone: str = "Europe/London"
    geometry: dict
    crs: Literal["EPSG:4326"] = "EPSG:4326"
    origin: str = Field(min_length=1, max_length=1000)
    parent_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def geometry_valid(self):
        from methane.siting.geometry import geographic

        geographic(self.geometry)
        ZoneInfo(self.timezone)
        return self


class Evidence(Record):
    schema_version: Literal["site-evidence/1"] = "site-evidence/1"
    site_id: str = Field(pattern=r"^[a-zA-Z0-9_-]{1,80}$")
    subject: Literal[
        "land",
        "terrain",
        "protection",
        "flood",
        "water",
        "grid",
        "co2",
        "offtake",
        "access",
        "service",
        "cost",
        "measurement",
        "solar",
        "planning",
    ]
    status: Literal["measured", "reported", "modelled", "assumed", "unresolved"]
    assertion: str = Field(min_length=1, max_length=5000)
    source_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    source_url: str | None = Field(default=None, max_length=3000)
    value: object = None
    unit: str = Field(default="", max_length=100)
    valid_from: datetime | None = None
    valid_until: datetime | None = None
    supplied_by: str = Field(min_length=1, max_length=250)
    uncertainty: str = Field(min_length=1, max_length=2000)

    @model_validator(mode="after")
    def evidence_valid(self):
        for value in (self.valid_from, self.valid_until):
            if value is not None and value.tzinfo is None:
                raise ValueError("Evidence dates require timezone offsets")
        if self.valid_from and self.valid_until and self.valid_until < self.valid_from:
            raise ValueError("Evidence validity ends before it begins")
        if self.status in ("measured", "reported", "modelled") and not self.source_id:
            raise ValueError("Sourced evidence requires a saved source snapshot")
        return self


class ScreeningPolicy(Record):
    schema_version: Literal["site-screening/1"] = "site-screening/1"
    name: str = "Declared avoidance policy"
    excluded_land_classes: list[int] = Field(default_factory=list)
    maximum_slope_degrees: float = Field(default=10, ge=0, le=90)
    setback_m: float = Field(default=0, ge=0, le=10000)
    pv_kw_per_m2: float = Field(default=0.04, gt=0, le=0.3)
    equipment_footprint_m2: float = Field(default=500, ge=0)
    assumption: str = "Illustrative screening assumptions; not engineering setbacks or permission"


class DeploymentDesign(Record):
    schema_version: Literal["deployment-design/1"] = "deployment-design/1"
    site_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    name: str = Field(min_length=1, max_length=160)
    config: dict
    assessment_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")
    evidence_ids: list[str] = Field(default_factory=list)
    layout: list[dict] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    parent_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{64}$")

    @model_validator(mode="after")
    def plant_valid(self):
        from methane.config import Config

        Config.from_dict(self.config)
        return self
