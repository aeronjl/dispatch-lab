"""Opt-in fractional service fixture. None in Config retains legacy execution."""

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class ServiceSystem:
    implementation: str = "plant-service-contracts/1"
    inspector: str = "mobile"
    travel_hours: float = 0.5
    verification_hours: float = 0.25
    reset_hours: float = 0.25
    reader_kw: float = 0.2
    reset_kw: float = 0.1
    contact_unreadable_probability: float = 0.05
    contact_error_probability: float = 0.02
    contact_max_age_hours: float = 8
    communications_available: bool = True
    crew_available: bool = True
    calibration_reference_available: bool = True
    calibration_kits: int = 2
    cleaning_model: str = "lumped-dc/1"
    area_m2_per_kw: float = 5
    cleaning_area_m2ph: float = 1000
    initial_adhered_fraction: float = 0.01
    initial_damage_fraction: float = 0
    brush_life_m2: float = 50000
    brush_initial_condition: float = 1
    row_accessible: bool = True
    environment_source: str = "assumed"
    assumed_wind_mps: float = 3
    assumed_rain_mmph: float = 0
    cleaning_wind_limit_mps: float = 8
    cleaning_rain_limit_mmph: float = 0.1
    work_failure_fraction: float = 0.5
    support_model: str = "none"
    crew_shift_start_hour: int = 0
    crew_shift_duration_hours: int = 12
    crew_period_hours: int = 24
    crew_travel_hours: float = 1
    crew_response_lead_hours: float = 2
    crew_hours_per_period: float = 12
    remote_hours_per_period: float = 1
    retrieval_work_hours: float = 0.5
    robot_test_hours: float = 0.25
    robot_test_kw: float = 0.2
    robot_test_success_probability: float = 1
    support_delivery_hours: float = 0.5
    store_capacity_kits: int = 24
    supplier_kits: int = 24
    delivery_batch_kits: int = 4
    brush_spares: int = 2
    brush_change_hours: float = 0.5
    retrieval_enabled: bool = True
    replenishment_enabled: bool = True
    brush_replacement_enabled: bool = True
    portable_cleaner: str = "none"
    portable_area_m2ph: float = 1000
    portable_setup_hours: float = 0.5
    portable_power_kw: float = 0.5
    portable_loose_removal: float = 0.9
    portable_adhered_removal: float = 0.7
    portable_adhered_threshold: float = 0.05
    portable_water_l_per_m2: float = 0.5
    portable_rinse_l: float = 10
    portable_water_capacity_l: float = 1000
    portable_water_initial_l: float = 1000
    portable_upstream_water_l: float = 5000
    portable_water_delivery_l: float = 1000
    portable_min_ambient_c: float = 5
    inspection_model: str = "bounded-contact/1"
    inspection_noise_v: float = 0.1
    inspection_delay_hours: float = 0.0
    inspection_zero_limit_v: float = 2.0
    inspection_span_tolerance_fraction: float = 0.1
    inspection_low_v: float = 6.0
    inspection_high_v: float = 18.0
    inspection_wait_hours: float = 8.0
    visit_bundling_enabled: bool = False
    visit_max_jobs: int = 4
    crew_transfer_hours: float = 0.25
    crew_return_enabled: bool = False
    crew_return_pack_hours: float = 0.25
    crew_return_check_hours: float = 0.25
    equipment_recovery_enabled: bool = False
    remote_assistance_enabled: bool = True
    remote_wait_hours: float = 2
    remote_release_hours: float = 0.25
    remote_shift_start_hour: int = 0
    remote_shift_duration_hours: int = 12
    hardware_replacement_hours: float = 1
    hardware_spares: int = 2
    maintenance_enabled: bool = False
    maintenance_target: str = "resident"
    maintenance_first_due_hour: float = 720
    maintenance_interval_hours: float = 720
    maintenance_work_hours: float = 1
    maintenance_kits: int = 2
    dock_standby_kw: float = 0
    cleaning_policy: str = "legacy-condition"
    cleaning_first_due_hour: float = 0
    cleaning_period_hours: float = 168
    inspection_interface: str = "legacy-prepared"
    outcome_randomness: str = "legacy-reason/1"
    travel_time_factor: float = 1.0
    cleaning_time_factor: float = 1.0
    inspection_time_factor: float = 1.0
    repair_time_factor: float = 1.0
    supply_time_factor: float = 1.0
    support_time_factor: float = 1.0

    def __post_init__(self):
        for key in ("travel", "cleaning", "inspection", "repair", "supply", "support"):
            value = getattr(self, key + "_time_factor")
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
                or value <= 0
            ):
                raise ValueError("Service time factors must be positive and finite")
        if self.outcome_randomness not in ("legacy-reason/1", "target-action-request/1"):
            raise ValueError("Unknown service outcome randomness")
        # Preserve fractional hours/kW in setup even when a saved JSON value is
        # written as an integer. Gradio derives numeric precision from defaults.
        for key in (
            "maintenance_first_due_hour",
            "maintenance_interval_hours",
            "maintenance_work_hours",
            "dock_standby_kw",
            "cleaning_first_due_hour",
            "cleaning_period_hours",
        ):
            value = getattr(self, key)
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise ValueError(f"{key} must be a finite number")
            object.__setattr__(self, key, float(value))
        if self.cleaning_policy not in ("legacy-condition", "off", "condition", "periodic"):
            raise ValueError("Unknown cleaning policy")
        if (
            self.cleaning_policy in ("condition", "periodic")
            and self.cleaning_model != "section-optical/1"
        ):
            raise ValueError("Explicit section cleaning policies require section optics")
        if self.cleaning_period_hours <= 0:
            raise ValueError("Cleaning recurrence must be positive")
        if self.inspection_interface not in (
            "legacy-prepared",
            "accessible-port",
            "enclosed-contact",
        ):
            raise ValueError("Unknown contact inspection interface")
        if self.implementation != "plant-service-contracts/1":
            raise ValueError("Unknown service implementation")
        if self.inspector not in ("mobile", "fixed", "both", "none"):
            raise ValueError("Choose mobile, fixed, paired or no independent contact reader")
        if self.inspection_model not in ("bounded-contact/1", "referenced-contact/1"):
            raise ValueError("Unknown inspection mechanism")
        if self.inspector == "both" and self.inspection_model != "referenced-contact/1":
            raise ValueError("Paired inspection requires referenced contact sensing")
        if not 0 <= self.inspection_low_v < self.inspection_high_v <= 24:
            raise ValueError("Contact thresholds must satisfy 0 ≤ low < high ≤ 24 V")
        if self.inspection_span_tolerance_fraction >= 1:
            raise ValueError("Reference span tolerance must be below 1")
        if self.inspection_wait_hours <= 0:
            raise ValueError("Inspection wait limit must be positive")
        if self.cleaning_model not in ("lumped-dc/1", "section-optical/1"):
            raise ValueError("Unknown cleaning mechanism")
        if self.environment_source not in ("assumed", "weather"):
            raise ValueError("Choose declared assumed conditions or recorded weather")
        if self.support_model not in ("none", "logistics/1"):
            raise ValueError("Unknown support logistics mechanism")
        if self.visit_bundling_enabled and self.support_model != "logistics/1":
            raise ValueError("Combined crew visits require finite support logistics")
        if type(self.crew_return_enabled) is not bool:
            raise ValueError("Crew return permission must be boolean")
        if self.crew_return_enabled and self.support_model != "logistics/1":
            raise ValueError("Crew return requires finite support logistics")
        if min(self.crew_return_pack_hours, self.crew_return_check_hours) <= 0:
            raise ValueError("Crew packing and arrival checks must have positive duration")
        if self.equipment_recovery_enabled and self.support_model != "logistics/1":
            raise ValueError("Hardware recovery requires finite support logistics")
        if self.maintenance_enabled and self.support_model != "logistics/1":
            raise ValueError("Scheduled maintenance requires finite support logistics")
        if self.maintenance_target not in (
            "resident",
            "cleaner",
            "rover",
            "dock",
            "fixed_reader",
            "reset",
        ):
            raise ValueError("Choose resident hardware or a named maintenance target")
        if min(self.maintenance_interval_hours, self.maintenance_work_hours) <= 0:
            raise ValueError("Maintenance interval and work duration must be positive")
        if self.maintenance_kits != int(self.maintenance_kits):
            raise ValueError("Maintenance kits must be a whole number")
        if self.maintenance_enabled and self.maintenance_kits > self.store_capacity_kits:
            raise ValueError("Initial maintenance supplies exceed store capacity")
        if self.visit_max_jobs != int(self.visit_max_jobs) or not 2 <= self.visit_max_jobs <= 8:
            raise ValueError("A combined visit allows between two and eight jobs")
        if self.crew_transfer_hours <= 0:
            raise ValueError("On-site crew transfer duration must be positive")
        if self.portable_cleaner not in ("none", "dry", "wet"):
            raise ValueError("Choose no portable cleaner, a dry brush or a wet brush")
        if self.portable_cleaner != "none" and (
            self.support_model != "logistics/1" or self.cleaning_model != "section-optical/1"
        ):
            raise ValueError(
                "Portable cleaning requires section optics and finite support logistics"
            )
        for key, value in asdict(self).items():
            if isinstance(value, (str, bool)):
                continue
            if not isfinite(value) or value < 0:
                raise ValueError(f"{key} must be finite and nonnegative")
        if min(self.travel_hours, self.verification_hours, self.reset_hours) <= 0:
            raise ValueError("Travel, verification and reset durations must be positive")
        for key in (
            "contact_unreadable_probability",
            "contact_error_probability",
            "initial_adhered_fraction",
            "initial_damage_fraction",
            "brush_initial_condition",
            "work_failure_fraction",
            "robot_test_success_probability",
            "portable_loose_removal",
            "portable_adhered_removal",
            "portable_adhered_threshold",
        ):
            if getattr(self, key) > 1:
                raise ValueError(f"{key} must be in [0, 1]")
        if (
            min(
                self.area_m2_per_kw,
                self.cleaning_area_m2ph,
                self.brush_life_m2,
                self.work_failure_fraction,
            )
            <= 0
        ):
            raise ValueError(
                "Area, treatment rate, brush life and failure fraction must be positive"
            )
        if int(self.calibration_kits) != self.calibration_kits:
            raise ValueError("Calibration kits must be a whole number")
        for key in (
            "crew_shift_start_hour",
            "crew_shift_duration_hours",
            "crew_period_hours",
            "store_capacity_kits",
            "supplier_kits",
            "delivery_batch_kits",
            "brush_spares",
            "remote_shift_start_hour",
            "remote_shift_duration_hours",
            "hardware_spares",
        ):
            if int(getattr(self, key)) != getattr(self, key):
                raise ValueError(f"{key} must be a whole number")
        if (
            min(
                self.crew_period_hours,
                self.crew_travel_hours,
                self.retrieval_work_hours,
                self.robot_test_hours,
                self.support_delivery_hours,
                self.brush_change_hours,
                self.delivery_batch_kits,
                self.remote_release_hours,
                self.hardware_replacement_hours,
            )
            <= 0
        ):
            raise ValueError("Support periods, durations and delivery batch must be positive")
        if self.crew_shift_start_hour + self.crew_shift_duration_hours > self.crew_period_hours:
            raise ValueError("Crew shift must fit inside its declared period")
        if self.remote_shift_start_hour + self.remote_shift_duration_hours > self.crew_period_hours:
            raise ValueError("Remote shift must fit inside the declared labour period")
        if (
            min(self.portable_area_m2ph, self.portable_setup_hours, self.portable_water_delivery_l)
            <= 0
        ):
            raise ValueError("Portable coverage, setup time and delivery lot must be positive")
        if self.portable_water_initial_l > self.portable_water_capacity_l:
            raise ValueError("Initial cleaning water exceeds its store capacity")
        if self.portable_cleaner == "wet" and self.portable_water_l_per_m2 <= 0:
            raise ValueError("Wet cleaning requires a positive water dose")
