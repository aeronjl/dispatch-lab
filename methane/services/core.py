"""Existing field hardware assembled through service contracts.

All rates, reliability and access assumptions are a teaching fixture. The fixed
reader and rover read the SAME declared trip contact, not arbitrary fault truth.
"""

from dataclasses import replace

from methane.faults import HARDWARE_MODEL
from methane.field_operations import ASSETS as LEGACY_ASSETS
from methane.services.access import Access, Edge
from methane.services.contracts import Asset, Capability, Interface, Quantity, Requirement, Source
from methane.services.registry import Registry
from methane.services.resources import Resource

ASSETS = {
    **LEGACY_ASSETS,
    "fixed_reader": "PLANT-01/ELY-01/CONTACT",
    "crew": "SERVICE/CREW-01",
    "portable": "SERVICE/PORTABLE-CLEAN-01",
}
ELY = "PLANT-01/ELY-01"
ISOLATION = "isolation:" + ELY


def definition(config, options, surface=None, *, hardware_model=HARDWARE_MODEL):
    c, o = config, options
    if o.inspector == "both" and not c.rover_enabled:
        raise ValueError("Paired inspection requires an enabled rover")
    if c.human_fallback and c.human_lead_hours <= 0:
        raise ValueError(
            "Fractional crew routes require a positive configured mobilisation duration"
        )
    source = Source(
        "fractional-field-fixture/1",
        "assumption",
        "docs/service-plant-integration.md",
        "Illustrative service durations, utilities and reliability; no vendor calibration or hazard certification",
    )
    route = Requirement("route-open", "equals", True, "boolean", 1)
    communication = Requirement("communications", "equals", True, "boolean", 1)
    crew = Requirement("crew-available", "equals", True, "boolean", 1)
    reference = Requirement("calibration-reference", "equals", True, "boolean", 1)
    dock = Requirement("dock-available", "equals", True, "boolean", 1)
    accepted_capacity = (Requirement("capacity-restored", "equals", True, "boolean", 1),)
    accepted_flow = (Requirement("flow-restored", "equals", True, "boolean", 1),)
    caps = [
        Capability(
            "inspection",
            "read-trip-contact",
            "observe",
            "bounded-contact-read/1",
            c.inspection_hours,
            o.verification_hours,
            o.reader_kw,
            sources=(source,),
            acceptance=(
                Requirement("trip-contact", "available", True, "boolean", o.contact_max_age_hours),
            ),
        ),
        Capability(
            "cleaning",
            "clean-array",
            "clean",
            "lumped-dc-cleaning/1",
            c.cleaning_hours,
            o.verification_hours,
            c.mission_power_kw,
            consumables=(Quantity("stock:cleaning", 1, "kit"),),
            sources=(source,),
        ),
        Capability(
            "reset",
            "reset",
            "repair",
            "bounded-module-reset/1",
            o.reset_hours,
            o.verification_hours,
            o.reset_kw,
            requirements=(
                communication,
                Requirement("trip-contact", "equals", True, "boolean", o.contact_max_age_hours),
            ),
            acceptance=accepted_capacity,
            sources=(source,),
        ),
        Capability(
            "module-replacement",
            "module-replacement",
            "repair",
            "qualified-module-replacement/1",
            c.human_work_hours,
            o.verification_hours,
            consumables=(Quantity("stock:module", 1, "kit"),),
            requirements=(crew,),
            acceptance=accepted_capacity,
            sources=(source,),
        ),
        Capability(
            "flow-calibration",
            "flow-calibration",
            "calibrate",
            "qualified-flow-calibration/1",
            c.human_work_hours,
            o.verification_hours,
            consumables=(Quantity("stock:calibration", 1, "kit"),),
            requirements=(crew, reference),
            acceptance=accepted_flow,
            sources=(source,),
        ),
    ]
    referenced = o.inspection_model == "referenced-contact/1"
    if referenced:
        from methane.services.inspection import VERSION as READER_VERSION

        reader = "fixed" if o.inspector in ("fixed", "both") else "mobile"
        caps[0] = replace(
            caps[0],
            implementation_id=READER_VERSION,
            requirements=(communication,),
            acceptance=(
                Requirement(
                    "trip-contact:" + reader, "available", True, "boolean", o.contact_max_age_hours
                ),
            ),
            sources=(
                *caps[0].sources,
                Source(
                    "referenced-contact-fixture/1",
                    "assumption",
                    "docs/inspection-sensing.md",
                    "Prepared 24 V test port, internal references and bounded reader errors; both readers share the contact",
                ),
            ),
        )
        if o.inspector == "both":
            caps.append(
                replace(
                    caps[0],
                    capability_id="inspection-confirm",
                    acceptance=(
                        Requirement(
                            "trip-contact:mobile",
                            "available",
                            True,
                            "boolean",
                            o.contact_max_age_hours,
                        ),
                    ),
                )
            )
    interfaces = [
        Interface("ELY/contact", ELY, "electrolyser", ("read-trip-contact",), ("contact-reader",)),
        Interface("ARRAY/brush", "PLANT-01/PV-01", "solar", ("clean-array",), ("brush",)),
        Interface(
            "ELY/reset",
            ELY,
            "electrolyser",
            ("reset",),
            ("reset-interface",),
            exclusive_resources=(ISOLATION,),
        ),
        Interface(
            "ELY/module",
            ELY,
            "electrolyser",
            ("module-replacement",),
            ("module-tools",),
            exclusive_resources=(ISOLATION,),
        ),
        Interface(
            "ELY/flow",
            ELY,
            "electrolyser",
            ("flow-calibration",),
            ("flow-reference",),
            exclusive_resources=(ISOLATION,),
        ),
    ]
    assets = []
    if c.cleaner_enabled:
        assets.append(
            Asset(
                ASSETS["cleaner"],
                "row-cleaner",
                "reference-row-cleaner/2",
                "dock",
                "tracked",
                ("cleaning",),
                ("brush",),
                "energy:cleaner",
                c.return_reserve_kwh,
                c.mission_power_kw,
                sources=(source,),
            )
        )
    if c.rover_enabled and o.inspector in ("mobile", "both"):
        assets.append(
            Asset(
                ASSETS["rover"],
                "ground-inspector",
                "reference-ground-inspector/2",
                "dock",
                "wheeled",
                ("inspection-confirm" if o.inspector == "both" else "inspection",),
                ("contact-reader",),
                "energy:rover",
                c.return_reserve_kwh,
                c.mission_power_kw,
                sources=(source,),
            )
        )
    if o.inspector in ("fixed", "both"):
        assets.append(
            Asset(
                ASSETS["fixed_reader"],
                "fixed-sensor",
                "fixed-trip-reader/1",
                "electrolyser",
                "fixed",
                ("inspection",),
                ("contact-reader",),
                sources=(source,),
            )
        )
    if c.reset_enabled:
        assets.append(
            Asset(
                ASSETS["reset"],
                "remote-actuator",
                "bounded-module-reset/1",
                "electrolyser",
                "fixed",
                ("reset",),
                ("reset-interface",),
                sources=(source,),
            )
        )
    if c.human_fallback:
        assets.append(
            Asset(
                ASSETS["crew"],
                "contracted-crew",
                "qualified-field-crew/1",
                "site-gate",
                "crew",
                ("module-replacement", "flow-calibration"),
                ("module-tools", "flow-reference"),
                autonomy="human",
                sources=(source,),
            )
        )
    robots = [a for a in assets if a.battery_resource]
    if robots:
        for asset in robots:
            name = next(k for k, v in ASSETS.items() if v == asset.asset_id)
            key = "charge-" + name
            caps.append(
                Capability(
                    key,
                    key,
                    "supply",
                    "dc-dock-charging/1",
                    1,
                    0,
                    c.dock_kw,
                    requirements=(dock,),
                    sources=(source,),
                )
            )
            interfaces.append(
                Interface(
                    "DOCK/" + name,
                    asset.asset_id,
                    "dock",
                    (key,),
                    ("charger",),
                    exclusive_resources=("asset:" + asset.asset_id,),
                )
            )
        assets.append(
            Asset(
                ASSETS["dock"],
                "charging-dock",
                "shared-dc-dock/2",
                "dock",
                "fixed",
                tuple(
                    "charge-" + next(k for k, v in ASSETS.items() if v == a.asset_id)
                    for a in robots
                ),
                ("charger",),
                sources=(source,),
            )
        )
    resources = [Resource("asset:" + a.asset_id, "slot", "capacity", 1) for a in assets]
    resources.extend(
        [
            Resource(
                "plant:service-power",
                "kW",
                "capacity",
                max(c.dock_kw, 0) + o.reader_kw + o.reset_kw,
            ),
            Resource(ISOLATION, "slot", "capacity", 1),
            Resource("route:solar", "slot", "capacity", 1),
            Resource("route:electrolyser", "slot", "capacity", 1),
            Resource("stock:cleaning", "kit", "stock", c.cleaning_kits, c.cleaning_kits),
            Resource("stock:module", "kit", "stock", c.service_kits, c.service_kits),
            Resource("stock:calibration", "kit", "stock", o.calibration_kits, o.calibration_kits),
        ]
    )
    for a in robots:
        name = next(k for k, v in ASSETS.items() if v == a.asset_id)
        capacity = getattr(c, name + "_battery_kwh")
        resources.append(Resource(a.battery_resource, "kWh", "stock", capacity, capacity))
    edges = []
    for target in ("solar", "electrolyser"):
        for start, end in (("dock", target), (target, "dock")):
            edges.append(
                Edge(
                    start + "/" + end,
                    start,
                    end,
                    o.travel_hours,
                    ("wheeled", "tracked"),
                    (route,),
                    "route:" + target,
                )
            )
    # Mobilisation is the configured lead duration; return travel is separate.
    edges.extend(
        [
            Edge(
                "crew-out",
                "site-gate",
                "electrolyser",
                c.human_lead_hours if c.human_fallback else 1,
                ("crew",),
                (route, crew),
            ),
            Edge(
                "crew-back", "electrolyser", "site-gate", o.travel_hours, ("crew",), (route, crew)
            ),
        ]
    )
    if surface is not None:
        targets = list(surface.sections)
        caps = [cap for cap in caps if cap.capability_id != "cleaning"]
        interfaces = [face for face in interfaces if face.interface_id != "ARRAY/brush"]
        cleaner_caps = []
        weather_requirements = (
            Requirement("row-accessible", "equals", True, "boolean", 1),
            Requirement("wind-mps", "at_most", o.cleaning_wind_limit_mps, "m/s", 1),
            Requirement("rain-mmph", "at_most", o.cleaning_rain_limit_mmph, "mm/h", 1),
        )
        resources.append(
            Resource(
                "brush:cleaner",
                "m2",
                "stock",
                o.brush_life_m2,
                o.brush_life_m2 * o.brush_initial_condition,
            )
        )
        for target in targets:
            key = "cleaning/" + target
            cleaner_caps.append(key)
            area = surface.section(target)["area_m2"]
            caps.append(
                Capability(
                    key,
                    "clean-section",
                    "clean",
                    "section-dry-brush/1",
                    area / o.cleaning_area_m2ph,
                    o.verification_hours,
                    c.mission_power_kw,
                    consumables=(Quantity("stock:cleaning", 1, "kit"),),
                    requirements=weather_requirements,
                    sources=(source,),
                    hourly_consumables=(Quantity("brush:cleaner", o.cleaning_area_m2ph, "m2"),),
                )
            )
            interfaces.append(
                Interface("ARRAY/" + target, target, "solar", ("clean-section",), ("brush",))
            )
        assets = [
            replace(a, capabilities=tuple(cleaner_caps)) if a.asset_id == ASSETS["cleaner"] else a
            for a in assets
        ]
    registry = Registry(assets, interfaces, caps, resources, Access(edges))
    if o.support_model != "none":
        from methane.services.support import extend

        registry = extend(registry, c, o, hardware_model=hardware_model)
    if o.portable_cleaner != "none":
        from methane.services.portable import extend as add_portable

        registry = add_portable(registry, c, o, surface)
    if o.equipment_recovery_enabled:
        from methane.services.hardware import extend as add_hardware

        registry = add_hardware(registry, c, o)
    if o.maintenance_enabled:
        from methane.services.maintenance import extend as add_maintenance

        registry = add_maintenance(registry, c, o)
    if o.dock_standby_kw:
        from methane.services.standby import extend as add_standby

        registry = add_standby(registry)
    if o.inspection_interface != "legacy-prepared":
        from methane.services.local_policy import interface

        registry = interface(registry)
    if o.crew_return_enabled:
        from methane.services.crew_return import extend as add_crew_return

        registry = add_crew_return(registry, o)
    return registry
