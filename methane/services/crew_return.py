"""Observed interrupted crews finish their declared route without further jobs.

This conservative return follows the remaining accepted travel legs, skipping
all unfinished work. It is not emergency navigation or an optimal new route.
No repair, replenishment or robot recovery is credited by reaching home.
"""

import copy
from dataclasses import replace

from methane.services.adapters import eligibility, schedule
from methane.services.contracts import (
    Capability,
    Interface,
    MissionPlan,
    Quantity,
    Reading,
    Requirement,
    Source,
    Stage,
    WorkOrder,
)
from methane.services.core import ASSETS
from methane.services.registry import Registry
from methane.services.resources import ResourceConflict

VERSION = "interrupted-crew-return/1"
ADAPTER = "observed-crew-return-adapter/1"
ACTION = "crew-return"


def extend(base, options):
    assets, faces = list(base.assets.values()), list(base.interfaces.values())
    cap = Capability(
        ACTION,
        ACTION,
        "supply",
        VERSION,
        options.crew_return_check_hours,
        0,
        requirements=(
            Requirement("crew-available", "equals", True, "boolean", 1),
            Requirement("route-open", "equals", True, "boolean", 1),
        ),
        sources=(
            Source(
                VERSION,
                "assumption",
                "docs/crew-return.md",
                "Continue remaining declared travel legs and record arrival; no vehicle damage, injury, emergency routing or repair effect",
            ),
        ),
    )
    for i, asset in enumerate(assets):
        if asset.autonomy == "human" and asset.mobility == "crew":
            assets[i] = replace(asset, capabilities=(*asset.capabilities, ACTION))
            faces.append(
                Interface(
                    "SUPPORT/crew-return/" + asset.asset_id,
                    asset.asset_id,
                    asset.home,
                    (ACTION,),
                    implementation_id=VERSION,
                )
            )
    return Registry(
        assets, faces, (*base.capabilities.values(), cap), base.resources.values(), base.access
    )


def crew_asset(plan):
    return plan.asset.autonomy == "human" and plan.asset.mobility == "crew"


def unfinished(runtime):
    """Only observed stranded crews; prior failed attempts remain in the archive."""
    return [
        m
        for m in runtime.executive.missions.values()
        if crew_asset(m.plan)
        and (m.status == "stranded" or m.status == "blocked" and m.plan.order.action == ACTION)
        and not runtime.support.recovered(m)
    ]


def policy(runtime, hour):
    pending = [q for q in runtime.public()["orders"] if q["kind"] == ACTION]
    for mission in reversed(unfinished(runtime)):
        key = mission.plan.order.order_id
        if any(q["status"] in ("queued", "active", "scheduled") for q in pending):
            break  # The fixture has one shared crew, including the portable operator.
        # A stopped return has a new observed location and is a distinct request.
        if any(q.get("origin_order") == key for q in pending):
            continue
        public = next(q for q in runtime.executive.public()["orders"] if q["order_id"] == key)
        origins = [key]
        if mission.plan.order.action == ACTION:
            previous = next(q for q in runtime.orders if q["id"] == key)
            origins = [*previous["return_origins"], key]
        route, operands = remaining_route(runtime, mission)
        request = runtime.support.queue(
            ACTION,
            hour,
            "Observed crew interruption; return without completing abandoned work",
            origin_order=key,
            return_origins=origins,
            robot=next(n for n, value in ASSETS.items() if value == mission.plan.asset.asset_id),
            recovery_location={
                k: public[k] for k in ("from_point", "to_point", "phase", "progress")
            },
            location_model=VERSION,
            return_route=[
                dict(from_point=s.from_point, to_point=s.to_point, duration_hours=s.duration_hours)
                for s in route
            ],
            return_route_operands=operands,
        )
        pending.append(request)


def remaining_route(runtime, mission):
    """Retain only untravelled fractions of the already accepted itinerary."""
    key, ex = mission.plan.order.order_id, runtime.executive
    visit = ex.visits.get(ex.member_visits.get(key))
    plans = visit.members if visit else (mission.plan,)
    stop = mission.interrupted_at
    if stop is None:
        raise ValueError("Crew return needs an observed interruption time")
    stages, operands = [], []
    for plan in plans:
        for index, (a, b, stage) in enumerate(schedule(plan)):
            if stage.phase not in ("travel", "return") or b <= stop:
                continue
            duration = b - max(a, stop)
            origin = ("recovery/" + key) if a < stop < b else stage.from_point
            stages.append(
                replace(
                    stage,
                    phase="return",
                    duration_hours=duration,
                    from_point=origin,
                    bus_kw=0,
                    battery_kw=0,
                    consumables=(),
                    hourly_consumables=(),
                    effect=False,
                )
            )
            operands.append(
                dict(
                    order_id=plan.order.order_id,
                    stage_index=index,
                    original_start=a,
                    original_end=b,
                    interruption_at=stop,
                    remaining_hours=duration,
                )
            )
    return tuple(stages), operands


def build(runtime, order):
    ex = runtime.executive
    mission = ex.missions.get(order["origin_order"])
    if mission not in unfinished(runtime):
        raise ValueError("Crew return requires an unrecovered observed stranded crew")
    if any(
        m.status in ("active", "scheduled") and crew_asset(m.plan) for m in ex.missions.values()
    ):
        raise ValueError("The same crew already has an outstanding journey")
    stages, operands = remaining_route(runtime, mission)
    actor = runtime.registry.assets[mission.plan.asset.asset_id]
    # A shared visit carried every member's tools. Reserve them until arrival.
    visit = ex.visits.get(ex.member_visits.get(order["origin_order"]))
    if visit:
        resources = {
            q.resource: q
            for p in visit.members
            for q in (Quantity("asset:" + p.asset.asset_id, 1, "slot"), *p.asset.support_resources)
            if q.resource != "asset:" + actor.asset_id
        }
        actor = replace(actor, support_resources=tuple(resources.values()))
    if stages and stages[-1].to_point != actor.home:
        raise ValueError("Accepted itinerary does not finish at the crew's declared home")
    point = stages[0].from_point if stages else actor.home
    cap = runtime.registry.capabilities[ACTION]
    face = runtime.registry.interfaces["SUPPORT/crew-return/" + actor.asset_id]
    work = WorkOrder(
        order["id"],
        ACTION,
        face.interface_id,
        order["created_hour"],
        order["reason"],
        tuple(Reading(**r) for r in order["evidence"]),
    )
    failures = eligibility(work, actor, face, cap, runtime._context)
    if failures:
        raise ResourceConflict(failures)
    if stages:
        stages = (Stage("prepare", runtime.options.crew_return_pack_hours, point, point), *stages)
    # Arrival acknowledgement is the only effect, and therefore follows travel.
    stages = (*stages, Stage("perform", cap.work_hours, actor.home, actor.home, effect=True))
    plan = MissionPlan(work, actor, face, cap, ex.at_hour, stages, runtime._context, ADAPTER)
    return plan, copy.deepcopy(operands)
