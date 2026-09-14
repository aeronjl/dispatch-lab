"""Explicit availability and contemporaneous PV operands at planner boundaries."""

import copy


def forecast(runtime, value):
    result = copy.deepcopy(value)
    n = len(result["pv_kw"])
    available = runtime.available()
    result["component_availability"] = {k: [v] * n for k, v in available.items()}
    result["lifecycle"] = runtime.public()
    result["lifecycle"]["prediction_scope"] = (
        "Accepted capacity and observed condition held through the horizon; no unobserved acceptance, successful replacement or future outage is credited"
    )
    return result


def solar_samples(runtime, value):
    """Availability and irreversible conversion loss precede the shared converter."""
    result = copy.deepcopy(value)
    for i, sample in enumerate(result["source_samples"]):
        sample["lifecycle_factor"] = runtime.solar_factor(physical=i == 0)
    return result


def apply_support(runtime, services, hour):
    """Publish only present support indications. Outage end times stay private."""
    from dataclasses import replace

    if services is None:
        return
    states = runtime.resources(hour)
    from methane.services.contracts import Requirement

    for key, interface in list(services.registry.interfaces.items()):
        if interface.point in ("solar", "electrolyser"):
            channel = "project-free:" + interface.point
            if not any(r.channel == channel for r in interface.requirements):
                services.registry.interfaces[key] = replace(
                    interface,
                    requirements=(
                        *interface.requirements,
                        Requirement(channel, "equals", True, "boolean", 1),
                    ),
                )
    services.lifecycle_availability = runtime.available()
    base = getattr(services, "lifecycle_support_baseline", None)
    if base is None:
        base = services.lifecycle_support_baseline = dict(
            route_open=services.config.route_open,
            dock_available=services.config.dock_available,
            communications_available=services.options.communications_available,
            calibration_reference_available=services.options.calibration_reference_available,
        )
    services.config = replace(
        services.config,
        route_open=base["route_open"] and states["access"],
        dock_available=base["dock_available"] and states["dock"],
    )
    services.options = replace(
        services.options,
        communications_available=base["communications_available"] and states["communications"],
        calibration_reference_available=base["calibration_reference_available"]
        and states["reference"],
    )


def field_busy(services):
    """Committed missions, including return, hold their target; no private outcome."""
    if services is None:
        return ()
    return sorted(
        {
            m.plan.interface.point
            for m in services.executive.missions.values()
            if m.status in ("scheduled", "active")
            and m.plan.interface.point in ("solar", "electrolyser")
        }
    )
