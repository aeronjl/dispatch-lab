"""Optional hourly plant interfaces, with disclosed assumptions and finite supplies.

The AC island feeds electrolysis, reactor and external process auxiliaries. Field
service and battery flows remain on the DC bus. Pressure is a compatibility
boundary, never a vessel thermodynamics or gas-quality certification model.
"""

import json
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from methane.researched_models import Research

VERSION = "plant-integration/1"


class Integration(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    version: Literal["plant-integration/1"] = VERSION
    ac_efficiency: float = Field(
        default=0.96, gt=0, le=1, description="DC-to-AC efficiency · assumed constant"
    )
    ac_capacity_kw: float = Field(
        default=600, ge=0, description="AC output limit · kW · assumed island converter"
    )
    dryer_kw: float = Field(
        default=12,
        ge=0,
        description="Dryer fleet while electrolysis is on · kW · 4 × ~3 kW, rev08; constant-load approximation",
    )
    heat_fraction: float = Field(
        default=0.25,
        ge=0,
        le=1,
        description="External heat duty / electrolyser productive load · assumed, OEM duty missing",
    )
    cooler_capacity_kw: float = Field(
        default=160,
        ge=0,
        description="External cooler thermal limit · kW · assumed, no ambient derating curve",
    )
    cooler_electric_fraction: float = Field(
        default=0.05, ge=0, description="Cooler electricity / rejected heat · assumed constant"
    )
    h2_supply_barg: float = Field(
        default=30,
        ge=0,
        le=31,
        description="Assumed regulated H₂ outlet · barg · published maximum 31 is not a guarantee",
    )
    h2_buffer_barg: float = Field(
        default=30,
        ge=0,
        description="Assumed regulated buffer interface · barg · no pressure/inventory relation",
    )
    reactor_feed_barg: float = Field(
        default=5,
        ge=0,
        description="Required H₂ and CO₂ feed · barg · assumed; reactor OEM unidentified",
    )
    co2_supply_barg: float = Field(
        default=6, ge=0, description="Assumed regulated CO₂ supply · barg"
    )
    compressor_kwh_per_kg: float = Field(
        default=0,
        ge=0,
        description="H₂ compression energy · kWh/kg · required if buffer exceeds supply; user assumption",
    )
    compressor_kgph: float = Field(
        default=0, ge=0, description="H₂ compression throughput · kg/h · assumed when enabled"
    )
    water_capacity_l: float = Field(
        default=500, gt=0, description="Purified-water tank · L · assumed"
    )
    initial_water_l: float = Field(
        default=250, ge=0, description="Initial purified-water stock · L · assumed"
    )
    water_l_per_kg: float = Field(
        default=9,
        ge=9,
        description="Purified water / hydrogen · L/kg · rounded 19.4/2.16 to stoichiometric 9; no recycling",
    )
    water_delivery_l: float = Field(
        default=300, ge=0, description="Disclosed purified-water delivery · L · assumed"
    )
    water_every_hours: int = Field(
        default=24,
        ge=1,
        description="Delivery interval · h · first arrival after this many elapsed hours",
    )
    water_delay_hours: int = Field(
        default=0, ge=0, description="Disclosed delivery delay · h · assumed"
    )
    installed_eur: float | None = Field(
        default=None,
        ge=0,
        description="Additional installed interfaces capital · EUR · quotation missing; excludes existing capital",
    )
    ownership_years: float = Field(
        default=15, gt=0, description="Interface ownership allocation · years · assumed"
    )
    fixed_eur_per_year: float | None = Field(
        default=None,
        ge=0,
        description="Additional standing maintenance · EUR/year · quotation missing",
    )

    research: Research | None = None

    def to_dict(self):
        value = self.model_dump()
        if self.research is None:
            value.pop("research")
        return value

    @model_validator(mode="after")
    def boundaries(self):
        if self.initial_water_l > self.water_capacity_l:
            raise ValueError("Initial purified water exceeds tank capacity")
        if self.h2_buffer_barg > self.h2_supply_barg and (
            self.compressor_kwh_per_kg <= 0 or self.compressor_kgph <= 0
        ):
            raise ValueError(
                "Higher hydrogen storage pressure requires explicit compression energy and throughput"
            )
        return self

    @property
    def compression(self):
        return self.h2_buffer_barg > self.h2_supply_barg

    @property
    def feed_ready(self):
        return min(self.h2_buffer_barg, self.co2_supply_barg) >= self.reactor_feed_barg


def settings(p):
    return (
        _settings(json.dumps(p.integration, sort_keys=True)) if p.integration is not None else None
    )


@lru_cache(maxsize=128)
def _settings(value):
    return Integration.model_validate_json(value)


def forecast(p, f, hour):
    s = settings(p)
    if s is None:
        return f
    n = len(f["pv_kw"])
    return {
        **f,
        "water_deliveries_l": [
            s.water_delivery_l
            if h - s.water_delay_hours > 0 and (h - s.water_delay_hours) % s.water_every_hours == 0
            else 0.0
            for h in range(hour, hour + n)
        ],
        "integration_information": "Disclosed interface assumptions and scheduled water arrivals; exact tank observation assumed. No hidden future supply or equipment truth.",
    }


def add_planning(m, p, state, f):
    """Bind the optional interface equations to existing component output ports."""
    s = settings(p)
    if s is None:
        return
    n = len(f["pv_kw"])
    arrivals = f.get("water_deliveries_l", [0] * n)
    if len(arrivals) != n or any(
        not isinstance(v, (float, int)) or not 0 <= v < float("inf") for v in arrivals
    ):
        raise ValueError("One finite nonnegative water delivery per planning interval is required")
    if not -1e-5 <= state.water_l <= s.water_capacity_l + 1e-5:
        raise ValueError("Water planning inventory outside tank capacity")
    m.upper[m.ids["water_l"]] = s.water_capacity_l
    from methane.researched_models import add_converter, cooling_limit, heat_fraction

    fraction = heat_fraction(p, s)
    for t, arrival in enumerate(arrivals):
        if fraction:
            m.upper[m.ids["electrolyser_kw"][t]] = min(
                m.upper[m.ids["electrolyser_kw"][t]], cooling_limit(s, f["ambient_c"][t]) / fraction
            )
        if s.compression:
            m.upper[m.ids["hydrogen_produced_kg"][t]] = s.compressor_kgph
        if not s.feed_ready:
            m.upper[m.ids["methane_kg"][t]] = 0
        ac = ac_terms(s, t, p)
        add_converter(m, s, t, ac)
        m.add(ac, hi=s.ac_capacity_kw)
        balance = [
            ("water_l", t, 1),
            ("water_accepted_l", t, -1),
            ("hydrogen_produced_kg", t, s.water_l_per_kg),
        ]
        if t:
            balance.append(("water_l", t - 1, -1))
        initial = state.water_l if t == 0 else 0
        m.add(balance, lo=initial, hi=initial)
        m.add([("water_accepted_l", t, 1), ("water_rejected_l", t, 1)], lo=arrival, hi=arrival)
        before_delivery = [("water_accepted_l", t, 1)] + ([("water_l", t - 1, 1)] if t else [])
        m.add(before_delivery, hi=s.water_capacity_l - initial)
        m.add([*before_delivery, ("water_full", t, -s.water_capacity_l)], lo=-initial)
        m.add([("water_rejected_l", t, 1), ("water_full", t, -arrival)], hi=0)


def ac_terms(s, t, p):
    from methane.researched_models import heat_fraction

    return [
        ("electrolyser_bus_kw", t, 1),
        ("reactor_bus_kw", t, 1),
        ("electrolyser_on", t, s.dryer_kw),
        ("electrolyser_kw", t, heat_fraction(p, s) * s.cooler_electric_fraction),
        ("hydrogen_produced_kg", t, s.compressor_kwh_per_kg if s.compression else 0),
    ]


def bus_terms(p, t):
    s = settings(p)
    if s and s.research and s.research.converter != "constant":
        return [("interface_dc_kw", t, 1)]
    return (
        [(k, i, v / s.ac_efficiency) for k, i, v in ac_terms(s, t, p)]
        if s
        else [("electrolyser_bus_kw", t, 1), ("reactor_bus_kw", t, 1)]
    )


def execute(p, before, a, ely_bus, reactor_bus, h2, water_delivery_l, ambient=20):
    from methane.audit import check, require

    s = settings(p)
    if s is None:
        return None
    from methane.researched_models import converter_input, cooling_limit, heat_fraction

    heat = a["electrolyser_kw"] * heat_fraction(p, s)
    dryer = s.dryer_kw if a["electrolyser_kw"] > 1e-7 else 0
    cooler = heat * s.cooler_electric_fraction
    compression = h2 * s.compressor_kwh_per_kg if s.compression else 0
    ac = ely_bus + reactor_bus + dryer + cooler + compression
    dc = converter_input(s, ac)
    accepted = min(water_delivery_l, s.water_capacity_l - before.water_l)
    used = h2 * s.water_l_per_kg
    end = before.water_l + accepted - used
    audits = [
        check("interface_ac_limit", "integration", max(0, ac - s.ac_capacity_kw), "kW"),
        check(
            "external_cooling_limit", "integration", max(0, heat - cooling_limit(s, ambient)), "kW"
        ),
        check(
            "feed_pressure_compatibility",
            "integration",
            0 if s.feed_ready else a["methane_kg"],
            "kg",
        ),
        check(
            "compression_throughput",
            "integration",
            max(0, h2 - s.compressor_kgph) if s.compression else 0,
            "kg",
        ),
        check("water_delivery_nonnegative", "integration", min(0, water_delivery_l), "L"),
        check(
            "water_inventory_bounds",
            "integration",
            max(
                0,
                -end,
                end - s.water_capacity_l,
                -before.water_l,
                before.water_l - s.water_capacity_l,
            ),
            "L",
        ),
        check("water_balance", "integration", end - before.water_l - accepted + used, "L"),
        check(
            "ac_conversion_balance"
            if not s.research or s.research.converter == "constant"
            else "converter_no_energy_gain",
            "integration",
            dc * s.ac_efficiency - ac
            if not s.research or s.research.converter == "constant"
            else max(0, ac - dc),
            "kWh",
        ),
    ]
    record = dict(
        version="plant-integration/2" if s.research else VERSION,
        parameters=s.to_dict(),
        before_water_l=before.water_l,
        water_delivery_l=water_delivery_l,
        water_accepted_l=accepted,
        water_rejected_l=water_delivery_l - accepted,
        water_consumed_l=used,
        ending_water_l=end,
        electrolyser_ac_kw=ely_bus,
        reactor_ac_kw=reactor_bus,
        dryer_kw=dryer,
        cooling_heat_kw=heat,
        cooler_kw=cooler,
        compression_kw=compression,
        ac_kw=ac,
        dc_kw=dc,
        conversion_loss_kwh=dc - ac,
        additional_dc_kw=dc - ely_bus - reactor_bus,
        feed_pressure_compatible=s.feed_ready,
        audits=audits,
        scope="Hourly constant conversion and duty; assumed regulated pressure interfaces and exact water meter. No gas-quality, pressure dynamics, ambient cooler curve or OEM interlock claim.",
    )
    if s.research:
        from methane.researched_models import HHV_KWH_PER_KG, SOURCES, converter_points, thermal

        r = s.research
        gross, feed = thermal(p)
        record.update(
            model_identity=r.version,
            ambient_c=ambient,
            effective_cooler_capacity_kw=cooling_limit(s, ambient),
            effective_heat_fraction=heat_fraction(p, s),
            h2_reference_enthalpy_kwh=h2 * HHV_KWH_PER_KG,
            productive_excess_heat_kwh=a["electrolyser_kw"] - h2 * HHV_KWH_PER_KG,
            startup_thermal_scope="Startup electricity remains a separate energy allowance; its heat allocation and cooldown are not identified.",
            reactor_gross_reaction_kwh=a["methane_kg"] * gross,
            reactor_feed_heating_kwh=a["methane_kg"] * feed,
            reactor_net_reaction_kwh=a["methane_kg"] * (gross - feed),
            converter_points_kw=[
                list(point)
                for point in converter_points(
                    s.ac_capacity_kw, s.ac_efficiency, r.converter_loss_scale
                )
            ]
            if r.converter != "constant"
            else None,
            source_ids=[source["id"] for source in SOURCES],
            scope=(
                "Selected hourly models are recorded in parameters.research. "
                + (
                    "PV-inverter analogue, off-or-2–100% loading, no standby. "
                    if r.converter != "constant"
                    else "Constant converter efficiency. "
                )
                + (
                    "Steady effective-UA ambient cooler. "
                    if r.cooler != "constant"
                    else "Constant cooler capacity. "
                )
                + (
                    "NIST heat at frozen reference temperature with 25°C feed and specified recuperation; rounded plant stoichiometry, no kinetics. "
                    if r.reactor_heat != "rounded-298"
                    else "Original rounded reaction heat. "
                )
                + "Transfer and support assumptions are not field calibration."
            ),
        )
        from methane.researched_models import recovery_budget

        record.update(
            {
                "reactor_" + key.removesuffix("_per_kg"): value * a["methane_kg"]
                for key, value in recovery_budget(p).items()
            }
        )
    require(audits, record)
    return record


def describe(value):
    from methane.researched_models import describe as research_description

    s = Integration(**(value or {}))
    return dict(
        version=VERSION,
        enabled=value is not None,
        values=s.to_dict(),
        research=research_description(s.research.model_dump() if s.research else None),
        fields=[
            dict(key=k, label=v.description, nullable=k in {"installed_eur", "fixed_eur_per_year"})
            for k, v in Integration.model_fields.items()
            if k not in {"version", "research"}
        ],
        feed_ready=s.feed_ready,
        limitations=[
            "Optional researched conversion and thermal equations are available below. Constant-model defaults, pressure interfaces and water logistics remain disclosed assumptions; none establishes a calibrated plant envelope.",
            "Dryer nominal load follows 4 × ~3 kW from Flex120 rev08. All four aggregate skids are treated as on together; no chiller load added on top of the dryer option.",
            "Internal electrolyser utilities are already included in its base load. Water consumption is charged once; no product-water recycling credit.",
            "Additional installed capital and annual maintenance are unpriced until supplied. Total allocated cost is undefined while either is missing.",
            "Vessels, gas quality, water treatment, pressure regulation, voltage/frequency dynamics, ventilation and safe hardware operation still require separate engineering evidence.",
        ],
    )
