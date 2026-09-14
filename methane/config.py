"""Versioned, validated, illustrative operating and economic assumptions."""

from dataclasses import asdict, dataclass, field
from math import isfinite
from zoneinfo import ZoneInfo

from economics import Costs as HydrogenCosts
from methane.contracts import BATTERY, REACTOR
from methane.faults import FaultPolicy
from methane.field_operations import FieldOperations
from methane.services.configuration import ServiceSystem
from plant import Plant as HydrogenPlant


@dataclass(frozen=True)
class Plant(HydrogenPlant):
    h2_capacity_kg: float = 60
    initial_h2_kg: float = 0
    co2_capacity_kg: float = 1000
    initial_co2_kg: float = 500
    co2_delivery_kg: float = 300
    co2_delivery_every_hours: int = 24
    methane_max_kgph: float = 10
    methane_min_kgph: float = 3
    temperature_min_c: float = 250
    temperature_max_c: float = 400
    thermal_capacity_kwh_per_k: float = 0.3
    heat_loss_kw_per_k: float = 0.08
    heater_max_kw: float = 60
    cooling_max_kw: float = 40
    auxiliary_kw: float = 2
    methane_electric_kwh_per_kg: float = 1
    cooling_electric_fraction: float = 0.1
    minimum_run_hours: int = 4

    def __post_init__(self):
        super().__post_init__()
        for parameter in (*REACTOR.parameters, *BATTERY.parameters):
            parameter.validate(getattr(self, parameter.key))
        if self.dt_hours != 1:
            raise ValueError("v0.2 uses one-hour scheduling intervals.")
        for key in (
            "h2_capacity_kg",
            "co2_capacity_kg",
            "methane_max_kgph",
            "thermal_capacity_kwh_per_k",
            "co2_delivery_every_hours",
        ):
            if getattr(self, key) <= 0:
                raise ValueError(f"{key} must be positive.")
        for key in (
            "initial_h2_kg",
            "initial_co2_kg",
            "co2_delivery_kg",
            "heat_loss_kw_per_k",
            "heater_max_kw",
            "cooling_max_kw",
            "auxiliary_kw",
            "methane_electric_kwh_per_kg",
            "cooling_electric_fraction",
        ):
            if getattr(self, key) < 0:
                raise ValueError(f"{key} must be nonnegative.")
        if not 0 <= self.initial_h2_kg <= self.h2_capacity_kg:
            raise ValueError("Initial hydrogen exceeds its tank.")
        if not 0 <= self.initial_co2_kg <= self.co2_capacity_kg:
            raise ValueError("Initial CO2 exceeds its tank.")
        if not 0 < self.methane_min_kgph <= self.methane_max_kgph:
            raise ValueError("Invalid methane turndown.")
        if not -50 < self.temperature_min_c < self.temperature_max_c < 1500:
            raise ValueError("Invalid reactor temperature band.")
        if self.minimum_run_hours < 1 or int(self.minimum_run_hours) != self.minimum_run_hours:
            raise ValueError("Minimum run must be a positive whole number of hours.")
        if int(self.co2_delivery_every_hours) != self.co2_delivery_every_hours:
            raise ValueError("Delivery interval must be whole hours.")


@dataclass(frozen=True)
class Costs(HydrogenCosts):
    methanator_eur: float = 200000
    hydrogen_storage_eur: float = 60000
    co2_storage_eur: float = 40000
    methane_assets_years: float = 20
    reactor_replaceable_share: float = 0.2
    reactor_operating_hours: float = 60000
    reactor_start_equivalent_hours: float = 2
    co2_eur_per_kg: float = 0.15
    methane_eur_per_kg: float = 1
    cleaner_eur: float = 15000
    rover_eur: float = 80000
    dock_eur: float = 5000
    field_asset_years: float = 8
    field_replaceable_share: float = 0.2
    cleaner_wear_eur_per_hour: float = 0.5
    rover_wear_eur_per_hour: float = 2
    field_maintenance_eur_per_year: float = 3000
    cleaning_kit_eur: float = 5
    human_service_eur_per_hour: float = 80
    fixed_reader_eur: float = 3000
    reset_eur: float = 1500
    calibration_kit_eur: float = 100

    def __post_init__(self):
        super().__post_init__()
        if self.methane_assets_years <= 0 or self.reactor_operating_hours <= 0:
            raise ValueError("Asset lives must be positive.")
        if not 0 <= self.reactor_replaceable_share <= 1:
            raise ValueError("Replaceable reactor share must be in [0, 1].")
        if self.field_asset_years <= 0 or not 0 <= self.field_replaceable_share <= 1:
            raise ValueError("Invalid field asset life or replaceable share.")


@dataclass(frozen=True)
class Sensors:
    enabled: bool = True
    noise_fraction: float = 0.02
    discrepancy_fraction: float = 0.10
    confirmation_hours: int = 2
    probe_fraction: float = 0.10
    ambiguity_policy: str = "reduce-capacity/1"

    def __post_init__(self):
        if self.ambiguity_policy not in ("reduce-capacity/1", "retain-capacity/1"):
            raise ValueError("Unknown ambiguous-residual capacity policy.")
        if not 0 <= self.noise_fraction <= 0.1 or not 0.01 <= self.discrepancy_fraction <= 0.5:
            raise ValueError("Invalid sensor noise/threshold.")
        if self.confirmation_hours < 1 or int(self.confirmation_hours) != self.confirmation_hours:
            raise ValueError("Confirmation intervals must be positive integers.")
        if not 0 < self.probe_fraction <= 0.25:
            raise ValueError("Probe fraction must be in (0, .25].")


@dataclass(frozen=True)
class Scenario:
    hours: int = 72
    horizon_hours: int = 24
    seed: int = 7
    forecast_bias: float = 0
    variability: float = 0.25
    fault_start_hour: int = 34
    fault_duration_hours: int = 12
    capacity_fraction: float = 1
    flow_bias_fraction: float = 0
    delivery_delay_hours: int = 0
    solver_seconds: float = 0.5

    def __post_init__(self):
        if not all(isfinite(v) for v in vars(self).values()):
            raise ValueError("Scenario values must be finite.")
        if not 1 <= self.hours <= 240 or self.horizon_hours not in (6, 12, 24, 48):
            raise ValueError("Use 1–240 hours and a 6/12/24/48-hour horizon.")
        if not 0 <= self.capacity_fraction <= 1 or not -0.9 <= self.flow_bias_fraction <= 2:
            raise ValueError("Invalid fault severity.")
        if not -0.6 <= self.forecast_bias <= 0.6 or not 0 <= self.variability <= 0.6:
            raise ValueError("Invalid forecast stress.")
        for key in (
            "hours",
            "horizon_hours",
            "seed",
            "fault_start_hour",
            "fault_duration_hours",
            "delivery_delay_hours",
        ):
            if getattr(self, key) < 0 or int(getattr(self, key)) != getattr(self, key):
                raise ValueError(f"{key} must be a nonnegative integer.")
        if not 0.01 <= self.solver_seconds <= 10:
            raise ValueError("Solver time must be .01–10 seconds.")


@dataclass(frozen=True)
class WeatherConfig:
    mode: str = "synthetic"
    latitude: float = 51.5074
    longitude: float = -0.1278
    timezone: str = "Europe/London"
    start: str = "2026-07-10"
    tilt: float = 30
    azimuth: float = 0
    loss_fraction: float = 0.14
    noct_c: float = 45
    temperature_coefficient: float = -0.004
    publication_lag_hours: int = 6
    offline: bool = False

    def __post_init__(self):
        if self.mode not in ("synthetic", "forecast", "historical"):
            raise ValueError("Unknown weather mode.")
        if not 34 <= self.latitude <= 72 or not -25 <= self.longitude <= 45:
            raise ValueError("This release uses a European coordinate bounding box.")
        if not 0 <= self.tilt <= 90 or not -180 <= self.azimuth <= 180:
            raise ValueError("Invalid panel orientation.")
        if not 0 <= self.loss_fraction < 1 or not 20 <= self.noct_c <= 80:
            raise ValueError("Invalid PV conversion assumptions.")
        if not -0.02 <= self.temperature_coefficient <= 0:
            raise ValueError("Invalid panel temperature coefficient.")
        if not 0 <= self.publication_lag_hours <= 24:
            raise ValueError("Invalid publication lag.")
        ZoneInfo(self.timezone)


@dataclass(frozen=True)
class Models:
    battery: str = "affine/1"
    electrolyser: str = "specific-energy/1"
    hydrogen: str = "balance/1"
    co2: str = "balance/1"
    reactor: str = "analytic/1"

    def __post_init__(self):
        from methane.battery import IMPLEMENTATIONS

        if self.battery not in IMPLEMENTATIONS:
            raise ValueError(f"Unknown battery implementation: {self.battery}")
        from methane.electrolyser import IMPLEMENTATIONS as ELY
        from methane.storage import IMPLEMENTATIONS as GAS

        if (
            self.electrolyser not in ELY
            or self.hydrogen not in GAS
            or self.co2 not in GAS
            or self.reactor != "analytic/1"
        ):
            raise ValueError("Unknown component implementation")


@dataclass(frozen=True)
class Config:
    rng_policy: str = "named-channels/1"
    plant: Plant = field(default_factory=Plant)
    costs: Costs = field(default_factory=Costs)
    sensors: Sensors = field(default_factory=Sensors)
    scenario: Scenario = field(default_factory=Scenario)
    weather: WeatherConfig = field(default_factory=WeatherConfig)
    solar: dict | None = None
    models: Models = field(default_factory=Models)
    faults: FaultPolicy = field(default_factory=FaultPolicy)
    field_operations: FieldOperations = field(default_factory=FieldOperations)
    service_system: ServiceSystem | None = None
    service_economics: dict | None = None
    recovery_policy: object | None = None
    service_policy: object | None = None
    investigation_policy: object | None = None

    def __post_init__(self):
        if self.investigation_policy is not None:
            from methane.services.investigator import InvestigationPolicy

            object.__setattr__(
                self,
                "investigation_policy",
                self.investigation_policy
                if isinstance(self.investigation_policy, InvestigationPolicy)
                else InvestigationPolicy(**self.investigation_policy),
            )
            version = (
                self.service_policy.get("version")
                if isinstance(self.service_policy, dict)
                else getattr(self.service_policy, "version", None)
            )
            if (
                version != "coordinated-services/3"
                or self.service_system is None
                or self.service_system.inspection_model != "referenced-contact/1"
            ):
                raise ValueError(
                    "Investigation requires referenced contact sensing and measured service follow-up"
                )
        if self.service_policy is not None:
            from methane.service_economics import ACTIVITY_VERSION
            from methane.services.controller import (
                VERIFICATION_VERSION,
                VISIT_VERSION,
                ServicePolicy,
            )

            object.__setattr__(
                self,
                "service_policy",
                self.service_policy
                if isinstance(self.service_policy, ServicePolicy)
                else ServicePolicy(**self.service_policy),
            )
            if not (
                self.field_operations.enabled
                and self.service_system
                and self.service_system.support_model == "logistics/1"
                and self.service_economics
                and self.service_economics.get("schema_version") == ACTIVITY_VERSION
            ):
                raise ValueError(
                    "Coordinated service planning requires enabled fractional services, finite logistics and activity-based service accounting"
                )
            if (
                self.service_policy.version in (VISIT_VERSION, VERIFICATION_VERSION)
                and not self.service_system.visit_bundling_enabled
            ):
                raise ValueError("Joint-visit service planning requires enabled visit bundling")
            if self.service_policy.version == VERIFICATION_VERSION and (
                self.recovery_policy is None or not self.sensors.enabled
            ):
                raise ValueError(
                    "Post-service follow-up requires scheduled recovery tests and enabled sensors"
                )
        if self.recovery_policy is not None:
            from methane.recovery import RecoveryPolicy

            object.__setattr__(
                self,
                "recovery_policy",
                self.recovery_policy
                if isinstance(self.recovery_policy, RecoveryPolicy)
                else RecoveryPolicy(**self.recovery_policy),
            )
            if self.recovery_policy.version in (
                "scheduled-load-tests/2",
                "scheduled-load-tests/3",
                "scheduled-load-tests/4",
                "scheduled-load-tests/5",
            ) and (
                self.service_policy is None
                or self.service_policy.version != "coordinated-services/3"
                or not self.sensors.enabled
            ):
                raise ValueError(
                    "Joint recovery requires version-3 coordinated services and enabled sensors"
                )
        if (
            self.investigation_policy is not None
            and self.investigation_policy.version
            in ("observed-service-investigation/2", "observed-service-investigation/3")
            and (
                self.recovery_policy is None
                or self.recovery_policy.version
                not in (
                    "scheduled-load-tests/2",
                    "scheduled-load-tests/3",
                    "scheduled-load-tests/4",
                    "scheduled-load-tests/5",
                )
            )
        ):
            raise ValueError(
                "Observed investigation continuations require joint work and recovery tests"
            )
        if self.rng_policy not in ("legacy/1", "named-channels/1"):
            raise ValueError("Unknown random-stream policy.")
        if (
            self.faults.hardware_model == "actuator-interlock/1"
            and any(
                getattr(self.faults, n + "_service_fault") != "none"
                for n in ("cleaner", "rover", "dock", "portable")
            )
            and (not self.field_operations.enabled or self.service_system is None)
        ):
            raise ValueError(
                "Independent service-hardware faults require enabled fractional field operations"
            )
        if (
            self.field_operations.enabled
            and self.service_system
            and self.service_system.portable_cleaner != "none"
            and not self.field_operations.human_fallback
        ):
            raise ValueError("Portable cleaning requires an enabled contracted crew")
        if self.service_economics is not None:
            from methane.service_economics import validate

            if not (
                self.field_operations.enabled
                and self.service_system
                and self.service_system.support_model == "logistics/1"
            ):
                raise ValueError(
                    "Complete service accounting requires enabled finite-logistics services"
                )
            object.__setattr__(self, "service_economics", validate(self.service_economics))
        inspection_fields = (
            "inspection_fault_start_hour",
            "contact_stuck",
            "fixed_reader_offset_v",
            "fixed_reader_drift_vph",
            "fixed_reader_dropout",
            "mobile_reader_offset_v",
            "mobile_reader_drift_vph",
            "mobile_reader_dropout",
        )
        if any(
            getattr(self.faults, k) != getattr(FaultPolicy(), k) for k in inspection_fields
        ) and not (
            self.field_operations.enabled
            and self.service_system
            and self.service_system.inspection_model == "referenced-contact/1"
        ):
            raise ValueError(
                "Referenced reader faults require enabled field operations and referenced contact sensing"
            )
        if self.solar is not None:
            from methane.solar import validate

            design = validate(self.solar)
            if abs(sum(s["capacity_kw"] for s in design["sections"]) - self.plant.solar_kw) > 1e-5:
                raise ValueError("Solar section capacities must sum to the plant's solar capacity.")
            object.__setattr__(self, "solar", design)

    def to_dict(self):
        value = asdict(self)
        timing = tuple(
            k + "_time_factor"
            for k in ("travel", "cleaning", "inspection", "repair", "supply", "support")
        )
        if self.service_system and all(getattr(self.service_system, k) == 1 for k in timing):
            for k in timing:
                value["service_system"].pop(k)
        if self.sensors.ambiguity_policy == "reduce-capacity/1":
            # Absence retains the original diagnosis and complete study inputs.
            value["sensors"].pop("ambiguity_policy")
        if (
            self.service_system
            and not self.service_system.crew_return_enabled
            and (
                self.service_system.crew_return_pack_hours == 0.25
                and self.service_system.crew_return_check_hours == 0.25
            )
        ):
            # Absence means the original no-return behaviour, with no active
            # duration assumption. Preserve existing complete study fixtures.
            for key in ("crew_return_enabled", "crew_return_pack_hours", "crew_return_check_hours"):
                value["service_system"].pop(key)
        if self.faults.hardware_model == "recovery-gated/1":
            value["faults"].pop("hardware_model")
        if self.recovery_policy is None:
            value.pop("recovery_policy")
        if self.service_policy is None:
            value.pop("service_policy")
        if self.investigation_policy is None:
            value.pop("investigation_policy")
        return value

    @classmethod
    def from_dict(cls, value):
        return cls(
            recovery_policy=value.get("recovery_policy"),
            service_policy=value.get("service_policy"),
            investigation_policy=value.get("investigation_policy"),
            solar=value.get("solar"),
            service_economics=value.get("service_economics"),
            service_system=ServiceSystem(**value["service_system"])
            if value.get("service_system") is not None
            else None,
            rng_policy=value.get("rng_policy", "legacy/1"),
            faults=FaultPolicy(
                **{
                    "hardware_model": "recovery-gated/1",
                    **value.get("faults", {"lifecycle": "legacy-timed"}),
                }
            ),
            **{
                k: t(**value.get(k, {}))
                for k, t in (
                    ("models", Models),
                    ("plant", Plant),
                    ("costs", Costs),
                    ("sensors", Sensors),
                    ("scenario", Scenario),
                    ("weather", WeatherConfig),
                    ("field_operations", FieldOperations),
                )
            },
        )
