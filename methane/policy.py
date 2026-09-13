"""Explicit dispatch assumptions shared by studies, execution and numerical reruns."""

from dataclasses import asdict, dataclass
from math import isfinite


@dataclass(frozen=True)
class Policy:
    objective: str = "methane"
    terminal_battery_value_kg_per_kwh: float = 0.0
    version: str = "dispatch-lab/policy/1"
    recovery: object | None = None
    service: object | None = None
    investigation: object | None = None

    def __post_init__(self):
        if self.version not in (
            "dispatch-lab/policy/1",
            "dispatch-lab/policy/2",
            "dispatch-lab/policy/3",
            "dispatch-lab/policy/4",
        ):
            raise ValueError("Unsupported controller policy version")
        if self.objective not in ("greedy", "methane", "economics"):
            raise ValueError("Unknown planning objective")
        value = self.terminal_battery_value_kg_per_kwh
        if not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Terminal battery value must be 0–1 kg CH4 per kWh")
        if value and self.objective != "methane":
            raise ValueError("The methane-equivalent terminal value requires the methane objective")
        if self.recovery is not None:
            from methane.recovery import RecoveryPolicy

            if self.version not in (
                "dispatch-lab/policy/2",
                "dispatch-lab/policy/3",
                "dispatch-lab/policy/4",
            ):
                raise ValueError("Scheduled recovery requires an explicit version-2 policy")
            object.__setattr__(
                self,
                "recovery",
                self.recovery
                if isinstance(self.recovery, RecoveryPolicy)
                else RecoveryPolicy(**self.recovery),
            )
        if self.service is not None:
            from methane.services.controller import VERIFICATION_VERSION, ServicePolicy

            if (
                self.version not in ("dispatch-lab/policy/3", "dispatch-lab/policy/4")
                or self.objective == "greedy"
            ):
                raise ValueError("Coordinated services require an explicit version-3 MPC policy")
            object.__setattr__(
                self,
                "service",
                self.service
                if isinstance(self.service, ServicePolicy)
                else ServicePolicy(**self.service),
            )
            if self.service.version == VERIFICATION_VERSION and self.recovery is None:
                raise ValueError("Post-service follow-up requires scheduled recovery tests")
        if self.recovery is not None and self.recovery.version in (
            "scheduled-load-tests/2",
            "scheduled-load-tests/3",
        ):
            if self.service is None or self.service.version != "coordinated-services/3":
                raise ValueError("Joint recovery requires the version-3 service controller")
        if self.investigation is not None:
            from methane.services.investigator import InvestigationPolicy

            if (
                self.version != "dispatch-lab/policy/4"
                or self.service is None
                or self.service.version != "coordinated-services/3"
            ):
                raise ValueError(
                    "Investigation requires a version-4 policy with measured service follow-up"
                )
            object.__setattr__(
                self,
                "investigation",
                self.investigation
                if isinstance(self.investigation, InvestigationPolicy)
                else InvestigationPolicy(**self.investigation),
            )
            if self.investigation.version in (
                "observed-service-investigation/2",
                "observed-service-investigation/3",
            ) and (
                self.recovery is None
                or self.recovery.version not in ("scheduled-load-tests/2", "scheduled-load-tests/3")
            ):
                raise ValueError(
                    "Observed investigation continuations require joint work and recovery tests"
                )

    def to_dict(self):
        result = asdict(self)
        if self.version == "dispatch-lab/policy/1":
            result.pop("recovery")
        if self.version not in ("dispatch-lab/policy/3", "dispatch-lab/policy/4"):
            result.pop("service")
        if self.version != "dispatch-lab/policy/4":
            result.pop("investigation")
        return result


def resolve(names, policies, defaults):
    if policies is not None and set(policies) != set(names):
        raise ValueError("Every selected controller needs exactly one frozen policy")
    return {
        name: Policy(**policies[name]) if policies is not None else Policy(objective=defaults[name])
        for name in names
    }
