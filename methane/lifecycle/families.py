"""Executable Release-2 capability boundaries; a family name never grants a repair."""

import copy

VERSION = "field-family-dispositions/1"

# The physical modules still enforce their own interfaces, resources and observations.
# These declarations narrow eligibility; they never replace those checks.
FAMILIES = {
    "row-cleaner": (
        "bounded implementation",
        "Dry loose-soiling treatment",
        ["prepared rows", "brush and return energy", "permitted weather"],
        "cleaning",
        "No permanent-damage repair or arbitrary geometry",
        "services/optical.py",
    ),
    "portable-cleaner": (
        "bounded implementation",
        "Operator wet/dry surface treatment",
        ["operator", "water for wet work", "access"],
        "cleaning",
        "No autonomous operator replacement",
        "services/portable.py",
    ),
    "ground-inspector": (
        "bounded implementation",
        "Read a prepared trip contact",
        ["compatible contact", "reader references", "access and return energy"],
        "inspection",
        "No general camera-based diagnosis",
        "services/inspection.py",
    ),
    "aerial-inspector": (
        "evidence restricted",
        "Aerial inspection",
        ["flight and payload model", "weather and airspace limits", "reserve and dock model"],
        "hardware",
        "Flight coverage and modality-specific observations are not implemented",
        None,
    ),
    "contact-inspector": (
        "evidence restricted",
        "Contact integrity inspection",
        ["adhesion and reachable surfaces", "thickness observation model", "corrosion mechanism"],
        "hardware",
        "No wall-crawler or thickness mechanism",
        None,
    ),
    "grounds": (
        "evidence restricted",
        "Vegetation management",
        ["growth and optical/access coupling", "terrain and coverage", "cutting and disposal"],
        "hardware",
        "No growth, mower coverage or treatment effect",
        None,
    ),
    "sampler": (
        "evidence restricted",
        "Sampling and analysis",
        [
            "sample/purge transport",
            "contamination and reference standards",
            "analyzer observation model",
        ],
        "hardware",
        "No sample chain or chemical analyzer; gas quality remains outside scope",
        None,
    ),
    "calibration": (
        "evidence restricted",
        "Automatic instrument service",
        ["identified sensor procedure", "traceable references", "channel isolation and acceptance"],
        "hardware",
        "Human flow calibration exists separately; an automatic station is not established",
        None,
    ),
    "fixed-sensor": (
        "bounded implementation",
        "Prepared contact/reference reader",
        ["compatible contact", "reference and power", "communications"],
        "inspection",
        "Shared contact can create common-mode error; no generic perfect health sensor",
        "services/inspection.py",
    ),
    "remote-actuator": (
        "bounded implementation",
        "Compatible latched reset",
        [
            "prepared reset interface",
            "permitted isolated state",
            "power and operating verification",
        ],
        "recovery",
        "Reset cannot fix permanent damage or sensor bias",
        "services/procedures.py",
    ),
    "manipulator": (
        "evidence restricted",
        "Mobile manipulation",
        [
            "reach/tool/torque interface",
            "supervision and isolation",
            "staged procedure and verification",
        ],
        "hardware",
        "No general automated removal or installation mechanism",
        None,
    ),
    "service-module": (
        "bounded human implementation",
        "Qualified module replacement",
        ["compatible module and isolation", "crew and spare", "post-work operating test"],
        "recovery",
        "Prepared robot insertion is restricted; the implemented replacement is human work",
        "services/procedures.py",
    ),
    "construction": (
        "bounded work-package implementation",
        "Assisted installation work",
        ["declared work package", "project crew and access", "acceptance and departure"],
        "deployment",
        "No calibrated autonomous construction machine throughput",
        "lifecycle/runtime.py",
    ),
    "deployable-array": (
        "bounded work-package implementation",
        "Prepared array deployment",
        [
            "declared capacity/work package",
            "project crew and access",
            "acceptance and operational interface",
        ],
        "deployment",
        "No validated transport geometry, supplier rate or cleaning compatibility inferred",
        "lifecycle/runtime.py",
    ),
}


def catalogue():
    return dict(
        version=VERSION,
        scope="Executable model coverage, distinct from commercial feasibility and empirical validation",
        families=[
            dict(
                id=key,
                disposition=values[0],
                effect=values[1],
                prerequisites=values[2],
                topic=values[3],
                boundary=values[4],
                implementation=values[5],
            )
            for key, values in FAMILIES.items()
        ],
    )


def assess(family, available=(), *, automation="declared"):
    if family not in FAMILIES:
        raise ValueError("Unknown reviewed hardware family")
    status, effect, required, topic, boundary, implementation = FAMILIES[family]
    missing = [p for p in required if p not in available]
    restricted = implementation is None or family == "service-module" and automation == "autonomous"
    return dict(
        version=VERSION,
        family=family,
        effect=effect,
        eligible=not restricted and not missing,
        status="evidence restricted"
        if restricted
        else "missing prerequisites"
        if missing
        else "bounded model available",
        missing=missing,
        boundary=boundary,
        implementation=implementation,
        topic=topic,
        scope="Eligibility screen only; the execution adapter rechecks the actual interface, resources and observations",
    )


def guard_service_asset(asset):
    """Do not admit a decorative future-family asset to a generic service adapter."""
    if asset.archetype in FAMILIES:
        status = FAMILIES[asset.archetype][0]
        if status == "evidence restricted" or asset.archetype in (
            "construction",
            "deployable-array",
        ):
            raise ValueError(
                asset.archetype
                + ": no registered service mechanism; "
                + FAMILIES[asset.archetype][4]
            )
        if asset.archetype == "service-module" and asset.autonomy != "human":
            raise ValueError("Autonomous module insertion remains evidence restricted")


def snapshot():
    return copy.deepcopy(catalogue())
