"""Routine work on resident equipment; no hidden repair or remaining-life oracle.

The declared task is exterior/connector cleaning and a recorded mechanical
check. Its only persistent effect is completion of that scheduled procedure.
It consumes supplies and crew time and excludes simultaneous use of the target.
Actual condition improvement needs a separate degradation hypothesis.
"""

import copy
from dataclasses import replace

from methane.services.contracts import (
    Capability,
    Interface,
    Quantity,
    Reading,
    Requirement,
    Source,
    WorkOrder,
    available_boundary,
)
from methane.services.core import ASSETS
from methane.services.executive import Receipt
from methane.services.registry import Registry
from methane.services.resources import Resource

VERSION = "routine-service/1"
TARGETS = ("cleaner", "rover", "dock", "fixed_reader", "reset")


def selected(registry, options):
    return [
        n
        for n in TARGETS
        if ASSETS[n] in registry.assets and options.maintenance_target in ("resident", n)
    ]


def extend(base, config, options):
    assets, caps, faces, resources = (
        list(base.assets.values()),
        list(base.capabilities.values()),
        list(base.interfaces.values()),
        list(base.resources.values()),
    )
    source = Source(
        "routine-service-fixture/1",
        "assumption",
        "docs/routine-services.md",
        "Declared exterior/connector cleaning and mechanical check; no automatic repair, calibration, brush renewal or quantified life extension",
    )
    crew_caps = []
    for name in selected(base, options):
        target = base.assets[ASSETS[name]]
        key = "routine-service:" + name
        crew_caps.append(key)
        requirements = (Requirement("crew-available", "equals", True, "boolean", 1),)
        if target.battery_resource:
            requirements += (Requirement("at-dock:" + name, "equals", True, "boolean", 1),)
        caps.append(
            Capability(
                key,
                "routine-service",
                "supply",
                VERSION,
                options.maintenance_work_hours,
                0,
                consumables=(Quantity("stock:maintenance", 1, "kit"),),
                requirements=requirements,
                sources=(source,),
            )
        )
        faces.append(
            Interface(
                "MAINTENANCE/" + name,
                target.asset_id,
                target.home,
                ("routine-service",),
                ("routine-tools",),
                exclusive_resources=("asset:" + target.asset_id,),
                implementation_id=VERSION,
            )
        )
    assets = [
        replace(a, capabilities=(*a.capabilities, *crew_caps), tools=(*a.tools, "routine-tools"))
        if a.asset_id == ASSETS["crew"]
        else a
        for a in assets
    ]
    resources += [
        Resource(
            "stock:maintenance",
            "kit",
            "stock",
            options.store_capacity_kits,
            options.maintenance_kits,
        ),
        Resource(
            "upstream:maintenance", "kit", "stock", options.supplier_kits, options.supplier_kits
        ),
    ]
    return Registry(assets, faces, caps, resources, base.access)


class Maintenance:
    def __init__(self, runtime):
        self.rt = runtime
        self.schedules = {
            n: {
                "target": n,
                "next_due_hour": runtime.options.maintenance_first_due_hour,
                "last_completed_hour": None,
                "completed_count": 0,
            }
            for n in selected(runtime.registry, runtime.options)
        }
        self.pending = []

    def policy(self, hour):
        for name, state in self.schedules.items():
            if hour < state["next_due_hour"] or self.rt.support.pending(
                "routine-service", target=name
            ):
                continue
            self.rt.support.queue(
                "routine-service",
                hour,
                "Routine exterior/connector service is due; condition improvement is not assumed",
                target=name,
                due_hour=state["next_due_hour"],
                maintenance_cycle=state["completed_count"] + 1,
            )

    def build(self, order):
        rt = self.rt
        if not rt._available(ASSETS["crew"]):
            raise ValueError("A free contracted crew is required for scheduled maintenance")
        name = order["target"]
        if not rt._available(ASSETS[name], require_ready=False):
            raise ValueError("Maintenance target is in use or awaiting retrieval")
        # The original due date and request evidence remain frozen while the crew waits.
        work = WorkOrder(
            order["id"],
            "routine-service",
            "MAINTENANCE/" + name,
            order["created_hour"],
            f"Routine service / {name} / cycle {order['maintenance_cycle']}",
            tuple(Reading(**r) for r in order["evidence"]),
        )
        return rt.registry.build(work, ASSETS["crew"], "routine-service:" + name, rt._context)

    def perform(self, plan, completed):
        name = plan.order.interface_id.removeprefix("MAINTENANCE/")
        event = dict(
            kind="routine-service",
            target=name,
            order_id=plan.order.order_id,
            completed_at=completed,
            effective_at=available_boundary(completed),
            previous_due_hour=self.schedules[name]["next_due_hour"],
            next_due_hour=completed + self.rt.options.maintenance_interval_hours,
            implementation_id=VERSION,
        )
        self.pending.append(event)
        return Receipt(
            "Routine procedure completed; no repair, health certification or life extension inferred",
            physical_effects=(event,),
        )

    def commit(self, hour):
        events = self.pending
        self.pending = []
        for e in events:
            if e["effective_at"] != hour:
                raise ValueError("Maintenance completion crossed an uncommitted boundary")
            state = self.schedules[e["target"]]
            state.update(
                last_completed_hour=e["completed_at"],
                next_due_hour=e["next_due_hour"],
                completed_count=state["completed_count"] + 1,
            )
        return copy.deepcopy(events)

    def public(self):
        at = self.rt.executive.at_hour
        return dict(
            implementation_id=VERSION,
            schedules=[
                {**s, "overdue_hours": max(0, at - s["next_due_hour"])}
                for s in self.schedules.values()
            ],
            scope="Completion records the declared routine procedure. Faults, brush life, sensor drift and hardware health remain unchanged; no quantified avoided-failure benefit.",
        )
