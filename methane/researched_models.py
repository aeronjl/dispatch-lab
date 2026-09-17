"""Opt-in, source-scoped conversion and thermal models; hourly scheduling only.

Source equations and transfer assumptions are distinct. See docs/researched-models.md.
No fitted PEM or slurry-pilot coefficient is assigned to the AEM/generic reactor.
"""

from functools import lru_cache
from math import isfinite, sqrt
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

VERSION = "researched-interfaces/1"
HHV_KWH_PER_KG = 285.830 / (3.6 * 2.01588)
AC_FRACTIONS = (0.02, 0.05, 0.1, 0.2, 0.3, 0.5, 0.75, 1.0)
# A,B,C,D,E,F,H: NIST gas Shomate, shared domain 500–1000 K.
SHOMATE = {
    "ch4": (-0.703029, 108.4773, -42.52157, 5.862788, 0.678565, -76.84376, -74.87310),
    "co2": (24.99735, 55.18696, -33.69137, 7.948387, -0.136638, -403.6075, -393.5224),
    "h2": (33.066178, -11.363417, 11.432816, -2.772874, -0.158558, -9.980797, 0),
    "water": (30.09200, 6.832514, 6.793435, -2.534480, 0.082139, -250.8810, -241.8264),
}
SOURCES = [
    dict(
        id="pvwatts-v5",
        title="NREL PVWatts V5 · §12, equation 10 (2014)",
        url="https://docs.nlr.gov/docs/fy14osti/62641.pdf",
        boundary="PV inverter reference curve; transfer to a process AC island is an explicit analogue, not grid-forming equipment qualification.",
    ),
    *[
        dict(
            id="nist-" + name,
            title="NIST WebBook · " + name,
            url=f"https://webbook.nist.gov/cgi/cbook.cgi?ID={cas}&Mask={mask}",
            boundary="Reference thermochemistry; ideal gases, no kinetics or catalyst calibration.",
        )
        for name, cas, mask in [
            ("methane", "C74828", 1),
            ("carbon-dioxide", "C124389", 1),
            ("hydrogen", "C1333740", 1),
            ("water-vapour", "C7732185", 1),
            ("liquid-water", "C7732185", 2),
        ]
    ],
]


class Research(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    version: Literal["researched-interfaces/1"] = VERSION
    converter: Literal["constant", "pvwatts-analogue/1"] = Field(
        default="pvwatts-analogue/1",
        description="Converter model · source curve or constant efficiency",
    )
    converter_loss_scale: float = Field(
        default=1,
        gt=0,
        le=3,
        description="Converter loss multiplier · 1 reproduces source knots; transfer assumption",
    )
    electrolysis_heat: Literal["fraction", "hhv-balance/1"] = Field(
        default="hhv-balance/1",
        description="Electrolysis heat · fixed fraction or reference-state energy balance",
    )
    external_heat_share: float = Field(
        default=1,
        ge=0,
        le=1,
        description="Share of productive electrolysis excess heat assigned to liquid cooler · assumed",
    )
    cooler: Literal["constant", "ambient-ua/1"] = Field(
        default="ambient-ua/1",
        description="Cooler envelope · constant or ambient-limited dry cooling",
    )
    coolant_c: float = Field(
        default=45,
        ge=-20,
        le=90,
        description="Effective cooler-side hot temperature · °C · assumed, not electrolyte temperature",
    )
    cooler_ua_kw_per_k: float = Field(
        default=6.4,
        gt=0,
        description="Effective cooler conductance · kW/K · assumed, 160 kW at 45−20 K",
    )
    reactor_heat: Literal["rounded-298", "nist-cold-feed/1"] = Field(
        default="nist-cold-feed/1",
        description="Reactor heat · original reference heat or NIST with cold-feed heating",
    )
    reactor_reference_c: float = Field(
        default=300,
        ge=226.85,
        le=726.85,
        description="Frozen reaction/product temperature · °C · reduced hourly model within 500–1000 K",
    )
    feed_recovery_fraction: float = Field(
        default=0,
        ge=0,
        le=1,
        description="Sensible recuperator effectiveness · assumed; limited by feed demand and available exhaust heat",
    )


def selected(p):
    from methane.integration import settings

    s = settings(p)
    return s.research if s else None


def validate_plant(p, s):
    r = s.research
    if not r:
        return
    if r.converter != "constant" and (s.ac_capacity_kw <= 0 or s.ac_efficiency > 0.99):
        raise ValueError(
            "PVWatts analogue requires positive AC capacity and nominal efficiency ≤ 0.99"
        )
    if r.electrolysis_heat == "hhv-balance/1" and p.specific_energy_kwh_per_kg < HHV_KWH_PER_KG:
        raise ValueError(
            "HHV heat model requires specific electricity ≥ liquid-water decomposition enthalpy; external heat input is not modelled"
        )
    if r.reactor_heat != "rounded-298" and not (
        500 <= p.temperature_min_c + 273.15 < p.temperature_max_c + 273.15 <= 1000
        and p.temperature_min_c <= r.reactor_reference_c <= p.temperature_max_c
    ):
        raise ValueError(
            "NIST reactor needs a production band within 500–1000 K and a reference temperature inside it"
        )


def enthalpy(species, kelvin):
    if not 500 <= kelvin <= 1000:
        raise ValueError("Outside common Shomate domain 500–1000 K")
    a, b, c, d, e, f, _ = SHOMATE[species]
    t = kelvin / 1000
    return a * t + b * t * t / 2 + c * t**3 / 3 + d * t**4 / 4 - e / t + f


@lru_cache(maxsize=128)
def reactor_coefficients(reference_c, recovery):
    h = {k: enthalpy(k, reference_c + 273.15) for k in SHOMATE}
    # Retain the plant's rounded 16 kg/kmol reaction extent, rather than silently
    # changing the meaning of its methane/material columns.
    gross = -(h["ch4"] + 2 * h["water"] - h["co2"] - 4 * h["h2"]) / (3.6 * 16)
    feed = (h["co2"] - SHOMATE["co2"][-1] + 4 * h["h2"]) / (3.6 * 16)
    exhaust = (h["ch4"] - SHOMATE["ch4"][-1] + 2 * (h["water"] - SHOMATE["water"][-1])) / (3.6 * 16)
    # No condensation credit or unidentified external heat. At 100% effectiveness
    # the smaller sensible-heat stream bounds recuperation; feed duty need not vanish.
    recovered = recovery * min(feed, exhaust)
    return gross, feed - recovered


def thermal(p):
    if hasattr(p, "reaction_kwh_per_kg"):
        return p.reaction_kwh_per_kg, p.feed_kwh_per_kg
    r = selected(p)
    return (
        reactor_coefficients(r.reactor_reference_c, r.feed_recovery_fraction)
        if r and r.reactor_heat != "rounded-298"
        else (165000 / 16 / 3600, 0.0)
    )


def recovery_budget(p):
    r = selected(p)
    if not r or r.reactor_heat == "rounded-298":
        return {}
    gross, cold = reactor_coefficients(r.reactor_reference_c, 0)
    _, perfect = reactor_coefficients(r.reactor_reference_c, 1)
    _, remaining = thermal(p)
    return dict(
        feed_duty_kwh_per_kg=cold,
        recoverable_sensible_kwh_per_kg=cold - perfect,
        recovered_kwh_per_kg=cold - remaining,
    )


def heat_fraction(p, s):
    r = s.research
    return (
        (1 - HHV_KWH_PER_KG / p.specific_energy_kwh_per_kg) * r.external_heat_share
        if r and r.electrolysis_heat == "hhv-balance/1"
        else s.heat_fraction
    )


def cooling_limit(s, ambient):
    r = s.research
    return (
        min(s.cooler_capacity_kw, r.cooler_ua_kw_per_k * max(0, r.coolant_c - ambient))
        if r and r.cooler == "ambient-ua/1"
        else s.cooler_capacity_kw
    )


@lru_cache(maxsize=128)
def converter_points(capacity, nominal, scale):
    points = []
    for fraction in AC_FRACTIONS:
        # Invert Eq.10: -.0162*z² + .9858*z - .0059 = .9637*Pac/Pac0.
        c = 0.0059 + 0.9637 * fraction
        z = 2 * c / (0.9858 + sqrt(0.9858**2 - 4 * 0.0162 * c))
        ac = capacity * fraction
        dc = capacity / nominal * z
        points.append((ac, ac + scale * (dc - ac)))
    return tuple(points)


def converter_input(s, ac):
    if not isfinite(ac) or ac < -1e-6:
        raise ValueError("Converter AC demand must be finite and nonnegative")
    if not s.research or s.research.converter == "constant":
        return ac / s.ac_efficiency
    if abs(ac) < 1e-7:
        return 0.0
    points = converter_points(s.ac_capacity_kw, s.ac_efficiency, s.research.converter_loss_scale)
    if ac < points[0][0] - 1e-5 or ac > points[-1][0] + 1e-5:
        raise ValueError("Converter demand outside off-or-2–100% research envelope")
    for (x0, y0), (x1, y1) in zip(points[:-1], points[1:], strict=True):
        if ac <= x1 + 1e-5:
            return y0 + (ac - x0) * (y1 - y0) / (x1 - x0)
    raise ValueError("Converter interval unavailable")


def prepare(m, p):
    from methane.integration import settings

    s = settings(p)
    if not s or not s.research or s.research.converter == "constant":
        return
    m.add_variable("interface_dc_kw")
    for j in range(len(AC_FRACTIONS) - 1):
        m.add_variable(f"converter_segment_{j}", upper=1, integer=True)
        m.add_variable(f"converter_fraction_{j}", upper=1)


def add_converter(m, s, t, ac_terms):
    if not s.research or s.research.converter == "constant":
        return
    points = converter_points(s.ac_capacity_kw, s.ac_efficiency, s.research.converter_loss_scale)
    ac, dc, selectors = list(ac_terms), [("interface_dc_kw", t, 1)], []
    for j, ((x0, y0), (x1, y1)) in enumerate(zip(points[:-1], points[1:], strict=True)):
        z, w = f"converter_segment_{j}", f"converter_fraction_{j}"
        m.add([(w, t, 1), (z, t, -1)], hi=0)
        ac.extend([(z, t, -x0), (w, t, -(x1 - x0))])
        dc.extend([(z, t, -y0), (w, t, -(y1 - y0))])
        selectors.append((z, t, 1))
    m.add(selectors, hi=1)
    m.add(ac, lo=0, hi=0)
    m.add(dc, lo=0, hi=0)


def describe(value):
    r = Research(**(value or {}))
    return dict(
        enabled=value is not None,
        values=r.model_dump(),
        sources=SOURCES,
        fields=[
            dict(
                key=k,
                label=f.description,
                choices=list(f.annotation.__args__)
                if getattr(f.annotation, "__origin__", None) is Literal
                else None,
            )
            for k, f in Research.model_fields.items()
            if k != "version"
        ],
        scope="Published equations with disclosed plant-transfer assumptions. No field calibration or equipment qualification. Converter curve is a PV-inverter analogue; cooler geometry, heat allocation and recuperation remain assumptions. All choices are disclosed to the planner; hidden variation is unsupported.",
    )


def preview(p):
    """Stateless, explicitly hypothetical teaching points from the selected model."""
    from methane.integration import settings

    s = settings(p)
    if not s:
        raise ValueError("Select plant interfaces before previewing their models")
    gross, feed = thermal(p)
    return dict(
        context="Learning preview · supplied design assumptions; no saved run changed",
        parameters=s.to_dict(),
        conversion=[
            dict(
                ac_kw=s.ac_capacity_kw * f,
                dc_kw=converter_input(s, s.ac_capacity_kw * f),
                loss_kw=converter_input(s, s.ac_capacity_kw * f) - s.ac_capacity_kw * f,
            )
            for f in AC_FRACTIONS
        ],
        cooling=[
            dict(
                ambient_c=t,
                capacity_kw=cooling_limit(s, t),
                electrolyser_limit_kw=min(
                    p.electrolyser_kw, cooling_limit(s, t) / heat_fraction(p, s)
                )
                if heat_fraction(p, s) > 0
                else p.electrolyser_kw,
            )
            for t in (5, 20, 30, 40, 45, 50)
        ],
        heat=dict(
            **recovery_budget(p),
            gross_kwh_per_kg=gross,
            feed_kwh_per_kg=feed,
            net_kwh_per_kg=gross - feed,
            electrolysis_cooler_kw=p.electrolyser_kw * heat_fraction(p, s),
        ),
        sources=SOURCES,
        boundary="Converter and cooler rows vary one input only. Production can be limited further by power, water, feedstock and temperature. Reactor heat uses a fixed reference temperature; it does not fit kinetics or thermal capacity.",
    )
