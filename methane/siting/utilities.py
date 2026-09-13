"""Disclosed site supply contracts for the qualified off-grid operating mode."""

from typing import Literal

from pydantic import Field, model_validator

from methane.siting.contracts import Record


class Delivery(Record):
    hour: int = Field(ge=0)
    kg: float = Field(ge=0)


class Utilities(Record):
    schema_version: Literal["site-utilities/1"] = "site-utilities/1"
    electrical_mode: Literal["off-grid"] = "off-grid"
    water_lph: float | None = Field(default=None, ge=0)
    co2_deliveries: list[Delivery] | None = None
    evidence_ids: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(
        default_factory=lambda: [
            "Off-grid DC bus; mapped grid proximity is not an import connection",
            "Unspecified water rate means an explicitly unconstrained supply, not measured availability",
            "Water supply is an interval throughput, with no stored water, recycling or pump model",
            "Listed CO2 deliveries are disclosed commitments, not hidden random future outcomes",
            "Gas delivery/acceptance is a separate cash scenario",
        ]
    )

    @model_validator(mode="after")
    def unique(self):
        if self.co2_deliveries is not None and len({d.hour for d in self.co2_deliveries}) != len(
            self.co2_deliveries
        ):
            raise ValueError("Combine multiple CO2 deliveries at one interval explicitly")
        return self


def supply_limit(plant, costs, utilities):
    if utilities.water_lph is None:
        return plant.electrolyser_kw
    if costs.water_litres_per_kg <= 0:
        raise ValueError("Finite water supply requires a positive total water-use assumption")
    return min(
        plant.electrolyser_kw,
        utilities.water_lph / costs.water_litres_per_kg * plant.specific_energy_kwh_per_kg,
    )


def forecast(f, plant, costs, utilities, hour):
    n = len(f["pv_kw"])
    result = {**f, "electrolyser_supply_limit_kw": [supply_limit(plant, costs, utilities)] * n}
    if utilities.co2_deliveries is not None:
        deliveries = {d.hour: d.kg for d in utilities.co2_deliveries}
        result["deliveries_kg"] = [deliveries.get(hour + i, 0) for i in range(n)]
    result["site_supply"] = dict(
        schema_version=utilities.schema_version,
        water_lph=utilities.water_lph,
        water_litres_per_kg=costs.water_litres_per_kg,
        estimated_electrolyser_supply_limit_kw=supply_limit(plant, costs, utilities),
        delivery_basis="Disclosed site delivery schedule"
        if utilities.co2_deliveries is not None
        else "Existing periodic CO2 fixture",
        evidence_ids=utilities.evidence_ids,
        scope="Supply constraint separate from estimated equipment capacity",
    )
    return result


def applied(row, plant, costs, utilities):
    used = row["h2_produced_kg"] * costs.water_litres_per_kg
    if utilities.water_lph is not None and used > utilities.water_lph + 1e-6:
        raise ValueError("Applied electrolysis exceeded the declared water supply")
    return dict(
        water_consumed_l=used,
        water_available_l=utilities.water_lph,
        water_unused_l=utilities.water_lph - used if utilities.water_lph is not None else None,
        water_stoichiometric_kg=row["electrolysis_stoichiometric_water_kg"],
        scope="Total water-use allowance bounds electrolysis; stoichiometric consumption separately recorded. No water inventory or recycling credit.",
    )
