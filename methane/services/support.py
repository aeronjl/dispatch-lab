"""Bounded recovery and supply logistics over the shared mission ledger.

Scheduling sees public work telemetry, stocks and declared labour calendars.
Relocation is distinct from an observed drive test. Supplier stock represents
the whole upstream pipeline, including reserved goods in transit, until receipt.
"""

import copy
from dataclasses import replace

from methane.faults import HARDWARE_MODEL
from methane.services.access import Access
from methane.services.adapters import eligibility, mobile
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
    available_boundary,
)
from methane.services.core import ASSETS
from methane.services.executive import Receipt
from methane.services.registry import Registry
from methane.services.resources import Resource, ResourceConflict

VERSION = "logistics/1"
KINDS = ("retrieve", "self-test", "restock", "replace-brush", "routine-service", "crew-return")
MATERIALS = ("cleaning", "module", "calibration", "brush")


def on_shift(hour, options):
    local = hour % options.crew_period_hours
    return (
        options.crew_shift_start_hour
        <= local
        < (options.crew_shift_start_hour + options.crew_shift_duration_hours)
    )


def fits_shift(start, end, options):
    opening = (
        start // options.crew_period_hours
    ) * options.crew_period_hours + options.crew_shift_start_hour
    return opening <= start and end <= opening + options.crew_shift_duration_hours + 1e-9


def extend(base, c, o, *, hardware_model=HARDWARE_MODEL):
    """Register compatible service capabilities without changing older registries."""
    assets, caps, faces = (
        list(base.assets.values()),
        list(base.capabilities.values()),
        list(base.interfaces.values()),
    )
    resources = [
        replace(r, capacity=o.store_capacity_kits) if r.resource_id.startswith("stock:") else r
        for r in base.resources.values()
    ]
    resources += [
        Resource("crew-hours", "h", "stock", o.crew_hours_per_period, o.crew_hours_per_period),
        Resource(
            "remote-hours", "h", "stock", o.remote_hours_per_period, o.remote_hours_per_period
        ),
        Resource("remote-operator", "person", "capacity", 1),
        Resource("stock:brush", "kit", "stock", o.store_capacity_kits, o.brush_spares),
        *(
            Resource("upstream:" + name, "kit", "stock", o.supplier_kits, o.supplier_kits)
            for name in MATERIALS
        ),
    ]
    source = Source(
        "support-logistics-fixture/1",
        "assumption",
        "docs/service-support.md",
        "Declared crew calendar, transit durations, typed supply pipeline and bounded drive test; not calibrated field reliability",
    )
    crew = Requirement("crew-available", "equals", True, "boolean", 1)
    route = Requirement("route-open", "equals", True, "boolean", 1)
    communications = Requirement("communications", "equals", True, "boolean", 1)
    crew_caps = ["restock", "replace-brush"]
    caps += [
        Capability(
            "restock",
            "restock",
            "supply",
            "typed-pipeline-delivery/1",
            o.support_delivery_hours,
            0,
            requirements=(crew, route),
            sources=(source,),
        ),
        Capability(
            "replace-brush",
            "replace-brush",
            "supply",
            "dock-brush-replacement/1",
            o.brush_change_hours,
            0,
            requirements=(crew,),
            sources=(source,),
        ),
    ]
    faces.append(
        Interface("SUPPORT/stores", "PLANT-01/STORES", "dock", ("restock",), ("delivery",))
    )
    for asset in list(assets):
        if not asset.battery_resource:
            continue
        name = next(k for k, v in ASSETS.items() if v == asset.asset_id)
        retrieve, test = "retrieve:" + name, "self-test:" + name
        crew_caps.append(retrieve)
        caps += [
            Capability(
                retrieve,
                "retrieve",
                "supply",
                "field-retrieval/1",
                o.support_delivery_hours,
                0,
                requirements=(crew, route),
                sources=(source,),
            ),
            Capability(
                test,
                "self-test",
                "observe",
                "supervised-drive-test/2"
                if hardware_model == HARDWARE_MODEL
                else "supervised-drive-test/1",
                o.robot_test_hours,
                0,
                o.robot_test_kw,
                requirements=(
                    communications,
                    Requirement("at-dock:" + name, "equals", True, "boolean", 1),
                ),
                acceptance=(Requirement("robot-ready:" + name, "equals", True, "boolean", 1),),
                shared_resources=(Quantity("remote-operator", 1, "person"),),
                hourly_consumables=(Quantity("remote-hours", 1, "h"),),
                sources=(source,),
            ),
        ]
        faces += [
            Interface(
                "SUPPORT/retrieve/" + name,
                asset.asset_id,
                "dock",
                ("retrieve",),
                ("recovery-carrier",),
            ),
            Interface(
                "SUPPORT/test/" + name, asset.asset_id, "dock", ("self-test",), ("drive-test",)
            ),
        ]
        assets[assets.index(asset)] = replace(
            asset, capabilities=(*asset.capabilities, test), tools=(*asset.tools, "drive-test")
        )
    faces.append(
        Interface(
            "SUPPORT/brush",
            ASSETS["cleaner"],
            "dock",
            ("replace-brush",),
            ("brush-tools",),
            requirements=(Requirement("at-dock:cleaner", "equals", True, "boolean", 1),),
            exclusive_resources=("asset:" + ASSETS["cleaner"],)
            if ASSETS["cleaner"] in base.assets
            else (),
        )
    )
    assets = [
        replace(
            a,
            capabilities=(*a.capabilities, *crew_caps),
            tools=(*a.tools, "delivery", "recovery-carrier", "brush-tools"),
        )
        if a.asset_id == ASSETS["crew"]
        else a
        for a in assets
    ]
    # The response lead is a wait before dispatch, not eight hours of driving.
    edges = [
        replace(e, hours=o.crew_travel_hours) if "crew" in e.mobility else e
        for e in base.access.edges
    ]
    from methane.services.access import Edge

    edges += [
        Edge("crew-dock-out", "site-gate", "dock", o.crew_travel_hours, ("crew",), (crew, route)),
        Edge("crew-dock-back", "dock", "site-gate", o.crew_travel_hours, ("crew",), (crew, route)),
    ]
    if o.visit_bundling_enabled:
        for target in ("electrolyser", "solar"):
            for a, b in (("dock", target), (target, "dock")):
                edges.append(
                    Edge(
                        f"crew-transfer/{a}/{b}",
                        a,
                        b,
                        o.crew_transfer_hours,
                        ("crew",),
                        (crew, route),
                        "route:" + target,
                    )
                )
    return Registry(assets, faces, caps, resources, Access(edges))


class Support:
    """Plant adapter helper. Has no fault-state or future-weather input."""

    def __init__(self, runtime):
        self.rt, self.o = runtime, runtime.options
        self.returned = {}
        self.events = []
        self.equipment = None
        if self.o.equipment_recovery_enabled:
            from methane.services.hardware import EquipmentSupport

            self.equipment = EquipmentSupport(runtime)
        self.period = 0
        self.materials = (
            (*MATERIALS, "water") if "stock:water" in runtime.ledger.specs else MATERIALS
        )
        self.maintenance = None
        if self.o.maintenance_enabled:
            from methane.services.maintenance import Maintenance

            self.maintenance = Maintenance(runtime)
            self.materials = (*self.materials, "maintenance")

    def begin(self, hour):
        period = int(hour // self.o.crew_period_hours)
        if period != self.period:
            for key, amount in (
                ("crew-hours", self.o.crew_hours_per_period),
                ("remote-hours", self.o.remote_hours_per_period),
            ):
                self.rt.ledger.replenish(
                    Quantity(key, amount, "h"), hour, f"support-allocation-period/{period}"
                )
            self.period = period

    def on_shift(self, hour):
        return on_shift(hour, self.o)

    def recovered(self, mission):
        return mission.plan.order.order_id in self.returned

    def stranded(self, name):
        return [
            m
            for m in self.rt.executive.missions.values()
            if m.plan.asset.asset_id == ASSETS[name]
            and m.status == "stranded"
            and not self.recovered(m)
        ]

    def at_dock(self, name):
        return not self.stranded(name) and not any(
            m.plan.asset.asset_id == ASSETS[name]
            and m.status in ("active", "scheduled")
            and not (
                m.plan.stages[m.stage_index].from_point == "dock"
                and m.plan.stages[m.stage_index].to_point == "dock"
            )
            for m in self.rt.executive.missions.values()
        )

    def ready(self, name):
        if self.equipment:
            return self.equipment.operable(name)
        if self.rt.hardware and not self.rt.hardware.operable(name):
            return False
        returns = [v for v in self.returned.values() if v["robot"] == name]
        if not returns:
            return not self.stranded(name)
        last = max(v["effective_at"] for v in returns)
        readings = [
            r
            for r in self.rt.executive.observations()
            if r.channel == "robot-ready:" + name
            and r.measured_at >= last
            and r.quality == "usable"
        ]
        return bool(readings and max(readings, key=lambda r: r.measured_at).value is True)

    def readings(self, hour):
        return tuple(
            Reading(
                "at-dock:" + n,
                self.at_dock(n),
                "boolean",
                hour,
                hour,
                "recorded-service-location/1",
            )
            for n in ("cleaner", "rover")
        )

    def pending(self, kind, **match):
        return any(
            q["kind"] == kind
            and all(q.get(k) == v for k, v in match.items())
            and (
                q["id"] not in self.rt.executive.missions
                or self.rt.executive.missions[q["id"]].status != "completed"
            )
            for q in self.rt.orders
        )

    def queue(self, kind, hour, reason, **fields):
        incident = fields.get("origin_order", f"{kind}/{len(self.rt.orders) + 1}")
        return self.rt._queue(kind, hour, incident, reason, **fields)

    def policy(self, hour):
        if self.o.crew_return_enabled:
            from methane.services.crew_return import policy

            policy(self.rt, hour)
        if self.equipment:
            self.equipment.policy(hour)
        if self.maintenance:
            self.maintenance.policy(hour)
        for name in () if self.equipment else ("cleaner", "rover"):
            stranded = self.stranded(name)
            if stranded and self.o.retrieval_enabled:
                mission = stranded[-1]
                origin = mission.plan.order.order_id
                if not self.pending("retrieve", origin_order=origin):
                    telemetry = next(
                        x for x in self.rt.executive.public()["orders"] if x["order_id"] == origin
                    )
                    self.queue(
                        "retrieve",
                        hour,
                        "Reported mission abort requires physical retrieval",
                        robot=name,
                        origin_order=origin,
                        recovery_location={
                            k: telemetry[k] for k in ("from_point", "to_point", "phase", "progress")
                        },
                        recovery_section=next(
                            (q.get("section") for q in self.rt.orders if q["id"] == origin), None
                        ),
                    )
            if (
                self.at_dock(name)
                and not self.ready(name)
                and ASSETS[name] in self.rt.registry.assets
                and not self.pending("self-test", robot=name)
            ):
                self.queue(
                    "self-test",
                    hour,
                    "Returned robot needs observed drive tracking before work",
                    robot=name,
                )
        if (
            self.o.brush_replacement_enabled
            and self.rt.optical
            and ASSETS["cleaner"] in self.rt.registry.assets
        ):
            required = max(
                (s["area_m2"] for s in self.rt.optical.surface.public()["sections"]), default=0
            )
            if (
                self.rt.ledger.available("brush:cleaner") < required
                and self.at_dock("cleaner")
                and not self.pending("replace-brush")
            ):
                self.queue(
                    "replace-brush",
                    hour,
                    "Remaining brush allowance cannot finish a section pass",
                    robot="cleaner",
                )
        if self.o.replenishment_enabled:
            for name in self.materials:
                if name == "brush" and not self.rt.optical:
                    continue
                # Water is ordered when a compatible full section plus setup no
                # longer fits the actual store. It is a volume, never a kit.
                needed = (
                    (
                        max(
                            (s["area_m2"] for s in self.rt.optical.surface.public()["sections"]),
                            default=0,
                        )
                        * self.o.portable_water_l_per_m2
                        + self.o.portable_rinse_l
                    )
                    if name == "water"
                    else 1
                )
                if name == "water" and self.o.portable_cleaner != "wet":
                    continue
                if name == "water" and (
                    not self.rt.optical.surface.sections
                    or needed > self.rt.ledger.specs["stock:water"].capacity + 1e-9
                ):
                    # A delivery cannot make an absent surface or an undersized
                    # full-section store usable. Keep the blocked work visible.
                    continue
                if self.rt.ledger.available("stock:" + name) < needed and not self.pending(
                    "restock", material=name
                ):
                    self.queue(
                        "restock",
                        hour,
                        "On-site typed stock is exhausted",
                        material=name,
                        quantity=self.o.portable_water_delivery_l
                        if name == "water"
                        else self.o.delivery_batch_kits,
                    )

    def decorate(self, plan):
        """Charge every actual crew hour, including travel, to its finite allowance."""
        if plan.asset.autonomy != "human":
            return plan
        if (
            plan.adapter_id
            not in ("observed-location-service-adapter/1", "observed-crew-return-adapter/1")
            and plan.starting_at < plan.order.requested_at + self.o.crew_response_lead_hours
        ):
            raise ValueError("Crew response lead has not elapsed")
        if not fits_shift(plan.starting_at, plan.ending_at, self.o):
            raise ValueError("Entire crew visit including return must fit a declared shift")
        return replace(
            plan,
            stages=tuple(
                replace(
                    s, hourly_consumables=(*s.hourly_consumables, Quantity("crew-hours", 1, "h"))
                )
                for s in plan.stages
            ),
        )

    def build(self, order, *, decorate=True):
        rt, o = self.rt, self.o
        kind, name = order["kind"], order.get("robot")
        if kind == "crew-return":
            from methane.services.crew_return import build

            if not o.crew_return_enabled:
                raise ValueError("Observed crew return is disabled")
            plan, _ = build(rt, order)
            return self.decorate(plan) if decorate else plan
        if kind == "routine-service":
            if self.maintenance is None:
                raise ValueError("Scheduled maintenance is disabled")
            plan = self.maintenance.build(order)
            return self.decorate(plan) if decorate else plan
        if kind == "self-test":
            key, face, asset = "self-test:" + name, "SUPPORT/test/" + name, ASSETS[name]
            if not self.at_dock(name):
                raise ValueError("Robot has not returned to the dock")
            if not rt._available(asset, require_ready=False):
                raise ValueError("Robot is occupied or unavailable for a drive test")
        else:
            key, face, asset = (
                ("retrieve:" + name, "SUPPORT/retrieve/" + name, ASSETS["crew"])
                if kind == "retrieve"
                else (
                    kind,
                    "SUPPORT/stores" if kind == "restock" else "SUPPORT/brush",
                    ASSETS["crew"],
                )
            )
            if asset not in rt.registry.assets:
                raise ValueError("No contracted crew is enabled")
            if not rt._available(asset):
                raise ValueError("Crew is occupied or stranded; no duplicate visit may depart")
        cap, interface = rt.registry.capabilities[key], rt.registry.interfaces[face]
        if kind == "restock":
            cap = replace(
                cap,
                consumables=(
                    Quantity(
                        "upstream:" + order["material"],
                        order["quantity"],
                        rt.ledger.specs["upstream:" + order["material"]].unit,
                    ),
                ),
            )
        elif kind == "replace-brush":
            cap = replace(
                cap,
                consumables=(
                    Quantity("stock:brush", 1, "kit"),
                    Quantity("brush:cleaner", rt.ledger.stock["brush:cleaner"], "m2"),
                ),
            )
        work = WorkOrder(
            order["id"],
            kind,
            face,
            order["created_hour"],
            f"{order['reason']} / robot {name or '-'} / occurrence {order['sequence']}",
            tuple(Reading(**r) for r in order["evidence"]),
        )
        platform = rt.registry.assets[asset]
        if kind == "self-test":
            platform = replace(platform, autonomy="remote-operated")
        if kind == "retrieve":
            failures = eligibility(work, platform, interface, cap, rt._context)
            if failures:
                raise ResourceConflict(failures)
            point = "recovery/" + order["origin_order"]
            stages = (
                Stage("travel", o.crew_travel_hours, "site-gate", point),
                Stage("prepare", o.retrieval_work_hours, point, point),
                Stage("return", o.travel_hours, point, "dock"),
                Stage("perform", o.support_delivery_hours, "dock", "dock", effect=True),
                Stage("return", o.crew_travel_hours, "dock", "site-gate"),
            )
            plan = MissionPlan(
                work,
                platform,
                interface,
                cap,
                rt.executive.at_hour,
                stages,
                rt._context,
                "declared-recovery-adapter/1",
            )
        else:
            plan = mobile(work, platform, interface, cap, rt._context, access=rt.registry.access)
        return self.decorate(plan) if decorate else plan

    def dispatch_visit(self, hour, available_pv):
        """Oldest-ready-first baseline; no future-job prediction or route optimality claim."""
        from methane.services.visits import compose

        rt, selected, visit = self.rt, [], None
        if not self.o.visit_bundling_enabled or not rt._available(ASSETS["crew"]):
            return
        for order in rt.orders:
            if order["status"] != "queued":
                continue
            if hour < order["created_hour"] + self.o.crew_response_lead_hours:
                continue
            try:
                raw = rt._build(order)
                if raw.asset.autonomy != "human" or raw.asset.mobility != "crew":
                    continue
                candidate = [*selected, raw]
                if len(candidate) == 1:
                    from methane.services.adapters import claims

                    single = self.decorate(raw)
                    rt.ledger.reserve_batch(
                        ((raw.order.order_id, *claims(single)),), hour, dry_run=True
                    )
                    selected = candidate
                    continue
                draft = compose(
                    candidate,
                    rt.registry.access,
                    "asset:" + ASSETS["crew"],
                    f"VISIT-{len(rt.executive.visits) + 1:04}",
                    "Combine currently feasible queued work; one crew journey, separate job evidence and acceptance",
                )
                if not fits_shift(draft.starting_at, draft.ending_at, self.o):
                    raise ValueError(
                        "Entire combined visit including return must fit a declared shift"
                    )
                draft = replace(draft, members=tuple(self.decorate(p) for p in draft.members))
                if rt.autonomy:
                    from methane.services.uncertain_timing import envelope_visit

                    draft = envelope_visit(draft, rt.autonomy["duration_bounds"])
                    if not fits_shift(draft.starting_at, draft.ending_at, self.o):
                        raise ValueError("Uncertain visit including return exceeds the crew shift")
                if rt._peak(hour, draft.members) > available_pv + 1e-9:
                    raise ValueError("Current solar cannot supply the combined service rate")
                rt.executive.check_visit(draft)
                selected, visit = candidate, draft
                if len(selected) >= self.o.visit_max_jobs:
                    break
            except (ValueError, KeyError) as exc:
                order["visit_blocked"] = str(exc)
        if visit is None:
            return
        rt.executive.submit_visit(visit)
        for index, plan in enumerate(visit.members):
            order = next(q for q in rt.orders if q["id"] == plan.order.order_id)
            order.update(visit_id=visit.visit_id, visit_index=index)
            order.pop("visit_blocked", None)
            rt._accepted(order, plan, hour)
        rt.interval["new_visits"].append(visit.to_dict())

    def perform(self, plan, completed, draw, *, hardware_state=None):
        """Called only from execution; returns deferred resource/location effects."""
        if plan.order.action == "routine-service":
            return self.maintenance.perform(plan, completed)
        order = next(q for q in self.rt.orders if q["id"] == plan.order.order_id)
        kind, name = order["kind"], order.get("robot")
        event = {
            "kind": kind,
            "order_id": order["id"],
            "completed_at": completed,
            "effective_at": available_boundary(completed),
        }
        if kind == "self-test":
            passed = draw(plan, "drive-test") < self.o.robot_test_success_probability
            if hardware_state is not None:
                passed = passed and not hardware_state["active"]
            reading = Reading(
                "robot-ready:" + name,
                passed,
                "boolean",
                completed,
                available_boundary(completed),
                (
                    "supervised-drive-test/2:"
                    if hardware_state is not None
                    else "supervised-drive-test/1:"
                )
                + order["id"],
            )
            return Receipt(
                "Drive test tracked" if passed else "Drive test failed; robot remains unavailable",
                (reading,)
                if hardware_state is None
                else (reading, replace(reading, channel="hardware-tracking:" + name)),
                ()
                if hardware_state is None
                else (
                    {
                        "kind": "drive-test",
                        "target": name,
                        "private_state": hardware_state,
                        "tracked": passed,
                        "completed_at": completed,
                        "available_at": available_boundary(completed),
                    },
                ),
            )
        if kind in ("retrieve", "crew-return"):
            event.update(
                robot=name, origin_order=order["origin_order"], location=order["recovery_location"]
            )
            if kind == "crew-return":
                event["returned_orders"] = order["return_origins"]
        if kind == "restock":
            event.update(material=order["material"], quantity=order["quantity"])
            if order["material"] == "water":
                event["unit"] = "L"
        if kind == "replace-brush":
            event.update(
                robot="cleaner",
                discarded_allowance_m2=next(
                    q.amount for q in plan.capability.consumables if q.resource == "brush:cleaner"
                ),
            )
        self.events.append(event)
        return Receipt(
            "Support work complete; effect eligible at next decision boundary",
            physical_effects=(event,),
        )

    def commit(self, hour):
        effects = []
        for event in self.events:
            if event["effective_at"] != hour:
                raise ValueError("Support effect crossed an uncommitted boundary")
            if event["kind"] == "crew-return":
                for origin in event["returned_orders"]:
                    self.returned[origin] = copy.deepcopy(event)
            elif event["kind"] in ("retrieve", "guided-return", "pack-return"):
                origins = [event["origin_order"]]
                if self.equipment:
                    origins = [
                        m.plan.order.order_id
                        for m in self.rt.executive.missions.values()
                        if m.status == "stranded"
                        and m.plan.asset.asset_id == ASSETS[event["robot"]]
                        and not self.recovered(m)
                    ]
                    event["returned_orders"] = origins
                for origin in origins:
                    self.returned[origin] = copy.deepcopy(event)
            elif event["kind"] == "restock":
                accepted = self.rt.ledger.replenish(
                    Quantity(
                        "stock:" + event["material"], event["quantity"], event.get("unit", "kit")
                    ),
                    hour,
                    event["order_id"],
                )
                event.update(accepted=accepted.amount, rejected=event["quantity"] - accepted.amount)
            elif event["kind"] == "replace-brush":
                self.rt.ledger.replenish(
                    Quantity("brush:cleaner", self.o.brush_life_m2, "m2"), hour, event["order_id"]
                )
            effects.append(copy.deepcopy(event))
        self.events = []
        if self.maintenance:
            effects.extend(self.maintenance.commit(hour))
        return effects

    def public(self):
        ledger = self.rt.ledger
        result = dict(
            implementation_id=VERSION,
            calendar_basis="Hours from simulation origin; declared repeating labour availability, not inferred local business hours",
            returned=copy.deepcopy(self.returned),
            crew_hours_remaining=ledger.stock["crew-hours"],
            remote_hours_remaining=ledger.stock["remote-hours"],
            upstream={n: ledger.stock["upstream:" + n] for n in self.materials},
            upstream_units={n: ledger.specs["upstream:" + n].unit for n in self.materials},
            water_l=ledger.stock.get("stock:water"),
            brush_spares=ledger.stock["stock:brush"],
            limitation="Mission-abort retrieval and bounded supervised drive test. This does not repair arbitrary mechanical damage. Combined visits retain separate job outcomes and reserve all supplies before departure; failed support-equipment recovery remains programme work."
            if self.o.visit_bundling_enabled
            else "Mission-abort retrieval and bounded supervised drive test. This does not repair arbitrary mechanical damage. Crew visits are separate; enable combined visits to share eligible journeys. Failed support-equipment recovery remains programme work.",
        )
        if self.equipment:
            result["equipment"] = self.equipment.public()
            result["hardware_spares"] = {
                k.removeprefix("stock:hardware:"): v
                for k, v in ledger.stock.items()
                if k.startswith("stock:hardware:")
            }
            result["limitation"] = (
                "Finite assistance, declared packing/return, compatible control/power-module replacement and separate function tests. No arbitrary mechanical repair or personnel injury model."
            )
        if self.maintenance:
            result["maintenance"] = self.maintenance.public()
        if self.o.crew_return_enabled:
            result["crew_return"] = dict(
                implementation_id="interrupted-crew-return/1",
                scope="Return follows the remaining accepted travel legs, skipping unfinished jobs. Active return labour is metered; waiting off-shift and vehicle fuel are not separately priced. No injury, rescue, vehicle damage or emergency routing model.",
            )
        return result
