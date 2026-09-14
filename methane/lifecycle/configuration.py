"""Versioned hypotheses, rather than implied vendor capabilities or known future health."""

from typing import Literal

from pydantic import Field, model_validator

from methane.siting.contracts import Record


class Package(Record):
    id: str = Field(min_length=1, max_length=80)
    asset: Literal["solar", "battery", "electrolyser", "reactor"]
    fraction: float = Field(gt=0, le=1)
    depends_on: list[str] = Field(default_factory=list)
    earliest_hour: int = Field(default=0, ge=0)
    method: Literal["manual", "prepared-array", "assisted-construction"] = "manual"
    mobilisation_hours: float = Field(default=1, gt=0, le=10000)
    installation_hours: float = Field(default=8, gt=0, le=10000)
    acceptance_hours: float = Field(default=1, gt=0, le=10000)
    rework_hours: float = Field(default=2, gt=0, le=10000)
    departure_hours: float = Field(default=1, gt=0, le=10000)
    failed_acceptance_attempts: int = Field(default=0, ge=0, le=20)
    maximum_attempts: int = Field(default=3, ge=1, le=21)
    equipment_eur_per_hour: float = Field(default=0, ge=0)
    equipment_energy_kwh_per_hour: float = Field(default=0, ge=0)
    external_energy_eur_per_kwh: float = Field(default=0, ge=0)
    installation_material_eur: float = Field(default=0, ge=0)
    evidence: str = "Illustrative work package; no calibrated construction-machine throughput"


class Condition(Record):
    asset: Literal["solar", "electrolyser"]
    initial_calendar_hours: float = Field(default=0, ge=0, le=1000000)
    initial_operating_hours: float = Field(default=0, ge=0, le=1000000)
    pv_loss_per_year: float = Field(default=0.005, ge=0, le=0.1)
    stack_mv_per_1000h: float = Field(default=4.8, ge=0, le=100)
    stack_reference_voltage: float = Field(default=1.9, gt=0)
    start_equivalent_hours: float = Field(default=0, ge=0, le=100)
    sensor_noise_fraction: float = Field(default=0.002, ge=0, le=0.1)
    sensor_delay_hours: int = Field(default=1, ge=1, le=168)
    sensor_period_hours: int = Field(default=24, ge=1, le=8766)
    sensor_dropout: bool = False
    replacement_threshold: float = Field(default=0.1, gt=0, le=0.8)
    periodic_hours: int = Field(default=8766, ge=1)
    replacement_hours: float = Field(default=4, gt=0, le=1000)
    replacement_part_eur: float = Field(ge=0)
    opening_spares: int = Field(default=1, ge=0, le=1000)
    stock_capacity: int = Field(default=2, ge=0, le=1000)
    supplier_spares: int = Field(default=4, ge=0, le=10000)
    delivery_hours: int = Field(default=24, ge=1)
    replacement_success_fraction: float = Field(default=1, ge=0, le=1)
    evidence: str = "Reduced literature-informed hypothesis; equipment calibration absent"

    @model_validator(mode="after")
    def stock(self):
        if self.opening_spares > self.stock_capacity:
            raise ValueError("Opening replacement stock exceeds capacity")
        return self


class Outage(Record):
    resource: Literal["access", "project-crew", "communications", "dock", "reference"]
    start_hour: int = Field(ge=0)
    end_hour: int = Field(gt=0)
    evidence: str = "Disclosed challenge; failure becomes observed at its start"

    @model_validator(mode="after")
    def interval(self):
        if self.end_hour <= self.start_hour:
            raise ValueError("Outage end must follow its start")
        return self


class Lifecycle(Record):
    version: Literal["site-lifecycle/1"] = "site-lifecycle/1"
    packages: list[Package] = Field(default_factory=list, max_length=100)
    conditions: list[Condition] = Field(default_factory=list, max_length=2)
    outages: list[Outage] = Field(default_factory=list, max_length=100)
    maintenance_policy: Literal["none", "periodic", "condition", "forecast-window"] = "condition"
    crew_hours_per_day: float = Field(default=8, gt=0, le=24)
    crew_shift_start: int = Field(default=8, ge=0, le=23)
    crew_eur_per_hour: float = Field(default=80, ge=0)
    callout_eur: float = Field(default=300, ge=0)
    maximum_wait_hours: int = Field(default=48, ge=1, le=8766)
    replenishment: bool = True
    evidence_ids: list[str] = Field(default_factory=list)
    labour_basis: Literal["dedicated-project-crew"] = "dedicated-project-crew"
    scope: str = "One explicitly additional contracted project crew, shared by construction and condition replacement; field-service crew remains separately allocated. No real certification or autonomous manipulation."

    @model_validator(mode="after")
    def dependencies(self):
        if any(p.id.startswith("replacement:") for p in self.packages):
            raise ValueError("Package id uses the reserved replacement prefix")
        ids = {p.id for p in self.packages}
        if len(ids) != len(self.packages) or len({c.asset for c in self.conditions}) != len(
            self.conditions
        ):
            raise ValueError("Duplicate lifecycle package or condition asset")
        if self.crew_shift_start + self.crew_hours_per_day > 24:
            raise ValueError("Project shift must fit in its declared UTC-relative day")
        for asset in ("solar", "battery", "electrolyser", "reactor"):
            if sum(p.fraction for p in self.packages if p.asset == asset) > 1 + 1e-12:
                raise ValueError("Commissioned fractions exceed nameplate")
        done = set()
        while len(done) < len(ids):
            ready = {p.id for p in self.packages if set(p.depends_on) <= done}
            if not ready - done:
                raise ValueError("Missing or cyclic commissioning prerequisite")
            done |= ready
        return self


def validate(value):
    return Lifecycle(**value).model_dump(mode="json")
