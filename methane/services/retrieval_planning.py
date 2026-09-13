"""Conditional charging after a qualified, already nominated retrieval.

This port does not predict new failures or invent a retrieval crew. The caller
must first validate the combined mission/resource projection. Readiness for new
robot work still requires the separately observed drive check.
"""

import math

from methane.services.core import ASSETS

VERSION = "conditional-retrieval-charging/1"


def return_boundary(runtime, robot, commitments, visits=()):
    stranded = {
        m.plan.order.order_id
        for m in runtime.executive.missions.values()
        if m.plan.asset.asset_id == ASSETS[robot]
        and m.status == "stranded"
        and not runtime.support.recovered(m)
    }
    if not stranded:
        return None
    entries = []
    for item in commitments:
        plan = item.plan
        order = next((o for o in runtime.orders if o["id"] == plan.order.order_id), None)
        if (
            not order
            or order["kind"] != "retrieve"
            or order.get("robot") != robot
            or order.get("origin_order") not in stranded
        ):
            continue
        if (
            plan.order.action != "retrieve"
            or plan.capability.implementation_id != "field-retrieval/1"
            or plan.interface.target_asset_id != ASSETS[robot]
            or plan.asset.asset_id != ASSETS["crew"]
            or plan.capability.capability_id not in runtime.registry.capabilities
            or "recovery-carrier" not in plan.asset.tools
            or not order.get("recovery_location")
        ):
            continue
        complete = plan.ending_at
        for visit in visits:
            if any(p.order.order_id == plan.order.order_id for p in visit.members):
                complete = max(complete, max(p.ending_at for p in visit.members))
        entries.append(
            dict(
                order_id=plan.order.order_id,
                origin_order=order["origin_order"],
                starting_at=plan.starting_at,
                complete_at=complete,
                available_at=math.ceil(complete - 1e-9),
                actor=plan.asset.asset_id,
                capability=plan.capability.capability_id,
            )
        )
    covered = {e["origin_order"] for e in entries}
    possible = stranded <= covered
    return dict(
        version=VERSION,
        robot=robot,
        status="conditional" if possible else "unavailable",
        observed_stranded_orders=sorted(stranded),
        continuations=entries,
        available_at=max(e["available_at"] for e in entries) if possible else None,
        reason="Charging can follow whole-mission return only if every nominated retrieval completes; the shared demand projection checks crew, route, power, stocks and prices. No robot-ready or repair-success credit."
        if possible
        else "No complete qualified retrieval commitment covers the observed stranded work; charging remains unavailable.",
    )
