"""Operator-assisted portable treatment through the same service contracts.

The contracted tool travels with one crew. Coverage and water are explicit;
there is no contact-force, panel-temperature shock or arbitrary damage repair.
"""

from dataclasses import replace

from methane.services.access import Access, Edge
from methane.services.contracts import Asset, Capability, Interface, Quantity, Requirement, Source
from methane.services.registry import Registry
from methane.services.resources import Resource

ASSET = "SERVICE/PORTABLE-CLEAN-01"
CREW = "SERVICE/CREW-01"
ACTION = "portable-clean-section"
VERSION = "portable-cleaning/1"


def extend(base, config, o, surface):
    if not config.human_fallback or CREW not in base.assets:
        raise ValueError("Portable cleaning requires an enabled contracted crew")
    if surface is None:
        raise ValueError("Portable cleaning requires section optical surfaces")
    assets, caps, interfaces, resources = (
        list(base.assets.values()),
        list(base.capabilities.values()),
        list(base.interfaces.values()),
        list(base.resources.values()),
    )
    source = Source(
        "portable-cleaning-fixture/1",
        "assumption",
        "docs/portable-cleaning.md",
        "Illustrative contracted tool, operator, coverage, water dose and treatment efficacy; no vendor calibration",
    )
    crew = Requirement("crew-available", "equals", True, "boolean", 1)
    route = Requirement("route-open", "equals", True, "boolean", 1)
    wet = o.portable_cleaner == "wet"
    requirements = (
        crew,
        Requirement("row-accessible", "equals", True, "boolean", 1),
        Requirement("wind-mps", "at_most", o.cleaning_wind_limit_mps, "m/s", 1),
        Requirement("rain-mmph", "at_most", o.cleaning_rain_limit_mmph, "mm/h", 1),
        *(
            (Requirement("ambient-c", "at_least", o.portable_min_ambient_c, "°C", 1),)
            if wet
            else ()
        ),
    )
    portable_caps = []
    for key in surface.sections:
        capability = "portable-cleaning/" + key
        portable_caps.append(capability)
        caps.append(
            Capability(
                capability,
                ACTION,
                "clean",
                "portable-" + o.portable_cleaner + "-brush/1",
                surface.section(key)["area_m2"] / o.portable_area_m2ph,
                o.verification_hours,
                o.portable_power_kw,
                prepare_hours=o.portable_setup_hours,
                consumables=(Quantity("stock:cleaning", 1, "kit"),),
                requirements=requirements,
                sources=(source,),
                hourly_consumables=(
                    Quantity("stock:water", o.portable_water_l_per_m2 * o.portable_area_m2ph, "L"),
                )
                if wet
                else (),
            )
        )
        lock = "work-area:" + key
        resources.append(Resource(lock, "slot", "capacity", 1))
        # The portable and resident tools share the same declared work surface.
        interfaces = [
            replace(face, exclusive_resources=(*face.exclusive_resources, lock))
            if face.target_asset_id == key
            else face
            for face in interfaces
        ]
        interfaces.append(
            Interface(
                "PORTABLE/" + key,
                key,
                "solar",
                (ACTION,),
                ("wet-brush" if wet else "dry-brush",),
                exclusive_resources=(lock,),
            )
        )
    assets.append(
        Asset(
            ASSET,
            "portable-cleaner",
            VERSION,
            "site-gate",
            "crew",
            tuple(portable_caps),
            ("wet-brush" if wet else "dry-brush",),
            autonomy="human",
            support_resources=(Quantity("asset:" + CREW, 1, "slot"),),
            sources=(source,),
        )
    )
    resources += [
        Resource("asset:" + ASSET, "slot", "capacity", 1),
        Resource(
            "stock:water", "L", "stock", o.portable_water_capacity_l, o.portable_water_initial_l
        ),
        Resource(
            "upstream:water", "L", "stock", o.portable_upstream_water_l, o.portable_upstream_water_l
        ),
    ]
    resources = [
        replace(r, capacity=r.capacity + o.portable_power_kw)
        if r.resource_id == "plant:service-power"
        else r
        for r in resources
    ]
    edges = [
        *base.access.edges,
        Edge(
            "portable-out",
            "site-gate",
            "solar",
            o.crew_travel_hours,
            ("crew",),
            (crew, route),
            "route:solar",
        ),
        Edge(
            "portable-back",
            "solar",
            "site-gate",
            o.crew_travel_hours,
            ("crew",),
            (crew, route),
            "route:solar",
        ),
    ]
    return Registry(assets, interfaces, caps, resources, Access(edges))


def prepare(plan, options):
    """Setup flush has its own rate; the final visual check does not run the pump."""
    if plan.order.action != ACTION:
        return plan
    stages = []
    for stage in plan.stages:
        if stage.phase == "prepare" and options.portable_cleaner == "wet":
            stage = replace(
                stage,
                hourly_consumables=(
                    *stage.hourly_consumables,
                    Quantity("stock:water", options.portable_rinse_l / stage.duration_hours, "L"),
                ),
            )
        if stage.phase == "verify":
            stage = replace(stage, bus_kw=0)
        stages.append(stage)
    return replace(plan, stages=tuple(stages))


def policy(runtime, hour):
    """Local condition rule; no future weather, fault type or repair truth."""
    o, c = runtime.options, runtime.config
    if any(
        q["kind"] == "portable-cleaning"
        and (
            q["status"] == "queued"
            or (
                q["id"] in runtime.executive.missions
                and runtime.executive.missions[q["id"]].status
                in ("scheduled", "active", "awaiting verification", "stranded")
                and not (
                    runtime.support
                    and runtime.support.recovered(runtime.executive.missions[q["id"]])
                )
            )
        )
        for q in runtime.orders
    ):
        return
    eligible = [
        s
        for s in runtime.optical.surface.public()["sections"]
        if s["removable_fraction"] >= c.cleaning_threshold
        or (o.portable_cleaner == "wet" and s["adhered_fraction"] >= o.portable_adhered_threshold)
    ]
    if not eligible:
        return
    target = max(
        eligible,
        key=lambda s: (
            (
                s["removable_fraction"] * o.portable_loose_removal
                + s["adhered_fraction"] * o.portable_adhered_removal * (o.portable_cleaner == "wet")
            ),
            s["id"],
        ),
    )
    runtime._queue(
        "portable-cleaning",
        hour,
        0,
        "Ideal section monitor exceeds the compatible portable-treatment threshold",
        target["id"],
        method="portable-" + o.portable_cleaner,
    )
