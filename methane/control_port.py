"""Observation-only, versioned dispatch port shared by operators and MCP agents."""

import copy
from dataclasses import asdict

from pydantic import BaseModel, ConfigDict, Field

from methane.components import assemble
from methane.config import Config, Costs
from methane.dispatch import execute, predicted
from methane.learning_lab.datasets import packet
from methane.physics import ACTION_KEYS, State
from methane.provenance import LOADED_SOURCE
from methane.siting.store import digest

VERSION = "dispatch-control/1"


class Actions(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False, strict=True)
    electrolyser_kw: float = Field(ge=0)
    charge_kw: float = Field(ge=0)
    discharge_kw: float = Field(ge=0)
    heater_kw: float = Field(ge=0)
    cooling_kw: float = Field(ge=0)
    methane_kg: float = Field(ge=0)


def observation(decision, plant, costs, models, time):
    public = packet(decision, time=time, prices=asdict(costs), plant=asdict(plant))
    # Model definitions are declared assumptions, never the hidden execution configuration.
    public.update(
        contract=VERSION,
        models=asdict(models),
        source_content_hash=LOADED_SOURCE["content_hash"],
        implementation=copy.deepcopy(decision.get("component_implementations")),
        policy=copy.deepcopy(decision.get("controller_policy")),
        objective=decision["planning_objective"],
        evidence=copy.deepcopy(decision["evidence"]),
        reference_plan=copy.deepcopy(decision["plan"]),
        recovery_protected=bool(decision.get("probe"))
        or decision.get("recovery_planning", {}).get("status") == "scheduled",
        scope="Process dispatch only. Services, repairs and recovery commitments remain with the configured reference executive. No real hardware actuation.",
        units={
            k: "kg CH4 in interval"
            if k == "methane_kg"
            else "kW thermal"
            if k in ("heater_kw", "cooling_kw")
            else "kW"
            for k in ACTION_KEYS
        },
    )
    public["information_id"] = digest(public)
    return public


def preview(public, actions=None):
    if actions is None:
        return dict(
            mode="reference",
            information_id=public["information_id"],
            requested=copy.deepcopy(public["reference_plan"]["actions"][0]),
            plan=copy.deepcopy(public["reference_plan"]),
            scope="Reference policy prediction; execution may differ when observations or resources differ.",
        )
    if public["recovery_protected"]:
        raise ValueError("A recovery commitment protects this interval; use the reference policy")
    requested = Actions.model_validate(actions).model_dump()
    c = Config.from_dict({"plant": public["plant"], "models": public["models"]})
    p, f = c.plant, public["forecast"]
    limits = dict(
        electrolyser_kw=p.electrolyser_kw,
        charge_kw=p.battery_kw,
        discharge_kw=p.battery_kw,
        heater_kw=p.heater_max_kw,
        cooling_kw=p.cooling_max_kw,
        methane_kg=p.methane_max_kgph,
    )
    for key, limit in limits.items():
        if requested[key] > limit:
            raise ValueError(f"{key} exceeds the declared equipment limit {limit:g}")
    if requested["charge_kw"] and requested["discharge_kw"]:
        raise ValueError("Charging and discharging cannot be requested together")
    if requested["electrolyser_kw"] and f.get("electrolyser_isolated", [False])[0]:
        raise ValueError("Electrolysis is isolated for service")
    if requested["methane_kg"] and f.get("reactor_isolated", [False])[0]:
        raise ValueError("The reactor is isolated for service")
    _, row = execute(
        p,
        State(**public["estimate"]),
        requested,
        f["pv_kw"][0],
        f["ambient_c"][0],
        f["deliveries_kg"][0],
        public["diagnosis"]["capacity_kw"],
        Costs(**public["prices"]),
        components=assemble(p, c.models),
        service_kw=f.get("service_kw", [0])[0],
        component_availability={k: v[0] for k, v in f.get("component_availability", {}).items()},
    )
    return dict(
        mode="manual",
        information_id=public["information_id"],
        requested=requested,
        plan=dict(
            actions=[requested],
            trajectory=[row],
            predicted=predicted(p, Costs(**public["prices"]), [row]),
            solver={
                **row["execution_solver"],
                "scope": "One-interval predicted feasibility projection",
            },
        ),
        scope="One-interval prediction using the starting estimate and contemporaneous forecast. Requested and predicted applied actions may differ. Physical execution rechecks actual limits.",
    )
