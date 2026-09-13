"""Physical fault lifecycle. Neither diagnosis nor service scheduling receives this state."""

from dataclasses import dataclass
from math import isfinite

HARDWARE_MODEL = "actuator-interlock/1"
LEGACY_HARDWARE_MODEL = "recovery-gated/1"


@dataclass(frozen=True)
class FaultPolicy:
    hardware_model: str = HARDWARE_MODEL
    lifecycle: str = "persistent"
    capacity_cause: str = "equipment-damage"
    inspection_fault_start_hour: float = 0.0
    contact_stuck: str = "none"
    fixed_reader_offset_v: float = 0.0
    fixed_reader_drift_vph: float = 0.0
    fixed_reader_dropout: bool = False
    mobile_reader_offset_v: float = 0.0
    mobile_reader_drift_vph: float = 0.0
    mobile_reader_dropout: bool = False
    service_fault_start_hour: int = 0
    cleaner_service_fault: str = "none"
    rover_service_fault: str = "none"
    dock_service_fault: str = "none"
    portable_service_fault: str = "none"

    def __post_init__(self):
        if self.hardware_model not in (HARDWARE_MODEL, LEGACY_HARDWARE_MODEL):
            raise ValueError("Unknown service-hardware execution model")
        if self.lifecycle not in ("persistent", "transient", "legacy-timed"):
            raise ValueError("Choose persistent damage or an explicitly timed transient.")
        if self.capacity_cause not in ("equipment-damage", "resettable-trip"):
            raise ValueError("Unknown capacity-loss cause.")
        if self.contact_stuck not in ("none", "open", "closed"):
            raise ValueError("Choose no common contact failure, stuck open or stuck closed")
        for key in (
            "inspection_fault_start_hour",
            "fixed_reader_offset_v",
            "fixed_reader_drift_vph",
            "mobile_reader_offset_v",
            "mobile_reader_drift_vph",
        ):
            if not isfinite(getattr(self, key)):
                raise ValueError(f"{key} must be finite")
        if self.inspection_fault_start_hour < 0:
            raise ValueError("Inspection fault onset must be nonnegative")
        if (
            not isinstance(self.service_fault_start_hour, int)
            or isinstance(self.service_fault_start_hour, bool)
            or self.service_fault_start_hour < 0
        ):
            raise ValueError("Service hardware fault onset must be a nonnegative hourly boundary")
        for target in ("cleaner", "rover"):
            if getattr(self, target + "_service_fault") not in (
                "none",
                "control-hold",
                "drive-power-loss",
            ):
                raise ValueError("Unknown mobile service-hardware fault")
        if self.dock_service_fault not in ("none", "charger-power-loss"):
            raise ValueError("Unknown charging hardware fault")
        if self.portable_service_fault not in ("none", "pump-power-loss"):
            raise ValueError("Unknown portable hardware fault")


class FaultState:
    """One scheduled incident, with separate capacity and flow-channel effects.

    A reset only clears the declared latching module trip. Qualified human service
    replaces that module and calibrates the flow channel. Success is a simulator
    outcome, never a command to restore the controller's capacity estimate.
    """

    def __init__(self, plant, scenario, policy):
        self.plant, self.scenario, self.policy = plant, scenario, policy
        self.cleared = set()
        self.service_cleared = set()

    def service_hardware_truth(self, target, hour):
        if target not in ("cleaner", "rover", "dock", "portable"):
            raise ValueError("Unknown service-hardware target")
        cause = getattr(self.policy, target + "_service_fault")
        active = hour >= self.policy.service_fault_start_hour and target not in self.service_cleared
        return {
            "target": target,
            "cause": cause if active else "none",
            "active": bool(active and cause != "none"),
        }

    def service_hardware(self, target, action, hour, successful):
        if action not in ("hardware-replacement", "remote-release"):
            raise ValueError("Unsupported service-hardware procedure")
        before = self.service_hardware_truth(target, hour)
        if (
            successful
            and before["active"]
            and (
                action == "hardware-replacement"
                or (action == "remote-release" and before["cause"] == "control-hold")
            )
        ):
            self.service_cleared.add(target)
        return {
            "before": before,
            "after": self.service_hardware_truth(target, hour),
            "action": action,
            "effective_at": hour,
        }

    def truth(self, hour):
        s = self.scenario
        active = hour >= s.fault_start_hour
        if self.policy.lifecycle != "persistent":
            active &= hour < s.fault_start_hour + s.fault_duration_hours
        capacity = active and s.capacity_fraction < 1 and "capacity" not in self.cleared
        flow = active and s.flow_bias_fraction != 0 and "flow" not in self.cleared
        return {
            "hour": hour,
            "capacity_kw": self.plant.electrolyser_kw * (s.capacity_fraction if capacity else 1),
            "flow_bias_fraction": s.flow_bias_fraction if flow else 0,
            "injected_fault_active": bool(capacity or flow),
            "capacity_fault_active": bool(capacity),
            "flow_fault_active": bool(flow),
            "lifecycle": self.policy.lifecycle,
        }

    def inspect_panel(self, hour):
        # A declared dry-contact status indicator, not a generic fault-type oracle.
        latched = self.truth(hour)["capacity_fault_active"] and (
            self.policy.capacity_cause == "resettable-trip"
        )
        return {
            "channel": "module-trip dry contact",
            "latched": bool(latched),
            "available_at_hour": hour + 1,
            "scope": "Ideal status contact; no diagnosis of damage or sensor drift",
        }

    def inspection_signal(self, hour, reader, measured_at=None):
        """Private physical port, never passed to the service supervisor.

        A prepared reader excites the contact with an illustrative 24 V signal.
        Both readers share this contact; their references cannot detect a stuck
        contact that produces a plausible signal. Reader offset also affects its
        two internal reference measurements. Persistent faults have no timer repair.
        """
        if reader not in ("fixed", "mobile"):
            raise ValueError("Unknown contact reader")
        p = self.policy
        active = hour >= p.inspection_fault_start_hour
        closed = self.inspect_panel(hour)["latched"]
        stuck = p.contact_stuck if active else "none"
        if stuck != "none":
            closed = stuck == "closed"
        elapsed = max(
            0, (hour if measured_at is None else measured_at) - p.inspection_fault_start_hour
        )
        return dict(
            signal_v=24.0 if closed else 0.0,
            offset_v=(
                getattr(p, reader + "_reader_offset_v")
                + elapsed * getattr(p, reader + "_reader_drift_vph")
            )
            if active
            else 0.0,
            dropout=bool(active and getattr(p, reader + "_reader_dropout")),
            contact_stuck=stuck,
        )

    def service(self, kind, hour, successful):
        before = self.truth(hour)
        if successful and kind == "reset" and self.policy.capacity_cause == "resettable-trip":
            if before["capacity_fault_active"]:
                self.cleared.add("capacity")
        if successful and kind in ("human-service", "module-replacement"):
            if before["capacity_fault_active"]:
                self.cleared.add("capacity")
        if successful and kind in ("human-service", "flow-calibration"):
            if before["flow_fault_active"]:
                self.cleared.add("flow")
        return {
            "before": before,
            "after": self.truth(hour),
            "kind": kind,
            "effective_at_hour": hour + 1,
        }
