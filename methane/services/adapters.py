"""Interchangeable fixed/mobile mission builders over the same work-order contract."""

from decimal import Decimal

from methane.services.contracts import MissionPlan, Quantity, Stage
from methane.services.resources import Booking, ResourceConflict


def schedule(plan):
    """Decimal addition preserves declared decimal-hour boundary times."""
    at = Decimal(str(plan.starting_at))
    result = []
    for stage in plan.stages:
        end = at + Decimal(str(stage.duration_hours))
        result.append((float(at), float(end), stage))
        at = end
    return tuple(result)


def eligibility(order, asset, interface, capability, context):
    reasons = []
    if order.interface_id != interface.interface_id:
        reasons.append("Requested interface does not match target")
    if order.action != capability.action or order.action not in interface.actions:
        reasons.append("Action is incompatible with target interface")
    if capability.capability_id not in asset.capabilities:
        reasons.append("Asset lacks the requested capability")
    if not set(interface.required_tools) <= set(asset.tools):
        reasons.append("Asset lacks required interface tools")
    for requirement in (*interface.requirements, *capability.requirements):
        reason = requirement.failure(context)
        if reason:
            reasons.append(reason)
    return tuple(reasons)


def work_stages(asset, interface, capability):
    point = interface.point
    locks = tuple(Quantity(key, 1, "slot") for key in interface.exclusive_resources)
    result = []
    if capability.prepare_hours:
        result.append(Stage("prepare", capability.prepare_hours, point, point, reservations=locks))
    battery_kw = capability.work_kw if asset.battery_resource else 0
    bus_kw = capability.work_kw if not asset.battery_resource else 0
    result.append(
        Stage(
            "perform",
            capability.work_hours,
            point,
            point,
            battery_kw=battery_kw,
            bus_kw=bus_kw,
            consumables=capability.consumables,
            reservations=(*locks, *capability.shared_resources),
            effect=True,
            hourly_consumables=capability.hourly_consumables,
        )
    )
    if capability.verify_hours:
        result.append(
            Stage(
                "verify",
                capability.verify_hours,
                point,
                point,
                battery_kw=battery_kw,
                bus_kw=bus_kw,
                reservations=locks,
            )
        )
    return tuple(result)


def fixed(order, asset, interface, capability, context, starting_at=None, access=None):
    reasons = eligibility(order, asset, interface, capability, context)
    if asset.mobility != "fixed" or asset.home != interface.point:
        reasons += ("Fixed asset is not installed at this service point",)
    if reasons:
        raise ResourceConflict(reasons)
    return MissionPlan(
        order,
        asset,
        interface,
        capability,
        context.at_hour if starting_at is None else starting_at,
        work_stages(asset, interface, capability),
        context,
        "fixed-service-adapter/1",
    )


def mobile(order, asset, interface, capability, context, starting_at=None, access=None):
    reasons = eligibility(order, asset, interface, capability, context)
    if asset.mobility == "fixed":
        reasons += ("Fixed asset cannot execute a mobile route",)
    if access is None:
        reasons += ("Mobile mission requires a declared access graph",)
    if reasons:
        raise ResourceConflict(reasons)
    outbound = access.route(asset.home, interface.point, asset.mobility, context)
    returning = access.route(interface.point, asset.home, asset.mobility, context)

    def travel(edges, phase):
        return tuple(
            Stage(
                phase,
                edge.hours,
                edge.origin,
                edge.destination,
                battery_kw=asset.travel_kw,
                reservations=(Quantity(edge.resource_id, 1, "slot"),) if edge.resource_id else (),
                requirements=edge.requirements,
            )
            for edge in edges
        )

    return MissionPlan(
        order,
        asset,
        interface,
        capability,
        context.at_hour if starting_at is None else starting_at,
        (
            *travel(outbound, "travel"),
            *work_stages(asset, interface, capability),
            *travel(returning, "return"),
        ),
        context,
        "mobile-service-adapter/1",
    )


BUILDERS = {"fixed-service-adapter/1": fixed, "mobile-service-adapter/1": mobile}


def claims(plan, *, include_asset_bookings=True):
    """Reserve actual material use plus unspent return margin, and shared occupancy."""
    slots = schedule(plan)
    quantities, bookings = [], []
    end = slots[-1][1]
    if include_asset_bookings:
        bookings.append(Booking("asset:" + plan.asset.asset_id, plan.starting_at, end, 1, "slot"))
    for start, stop, stage in slots:
        quantities.extend(stage.consumables)
        quantities.extend(
            Quantity(q.resource, q.amount * stage.duration_hours, q.unit)
            for q in stage.hourly_consumables
        )
        bookings.extend(
            Booking(q.resource, start, stop, q.amount, q.unit) for q in stage.reservations
        )
        if stage.bus_kw:
            bookings.append(Booking("plant:service-power", start, stop, stage.bus_kw, "kW"))
    if include_asset_bookings:
        bookings.extend(
            Booking(q.resource, plan.starting_at, end, q.amount, q.unit)
            for q in plan.asset.support_resources
        )
    if plan.asset.battery_resource:
        energy = sum(s.battery_kw * s.duration_hours for _, _, s in slots)
        quantities.append(
            Quantity(plan.asset.battery_resource, energy + plan.asset.return_reserve_kwh, "kWh")
        )
    return tuple(quantities), tuple(bookings)
