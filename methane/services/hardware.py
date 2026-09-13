"""Bounded service-hardware recovery, with observation-only procedure selection.

The private execution functions model a latched command hold and open power
stages. They do not model arbitrary jams, navigation, personnel injury or a
generic successful-repair oracle. Procedures and their tests are separate jobs.
"""

import copy
from dataclasses import asdict, replace

from methane.services.adapters import eligibility, mobile, work_stages
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

VERSION = "service-hardware/1"
ACTIONS = (
    "remote-release",
    "hardware-test",
    "guided-return",
    "hardware-replacement",
    "pack-return",
)
TARGETS = ("cleaner", "rover", "dock", "portable")


def remote_shift(start, end, o):
    opening = int(start // o.crew_period_hours) * o.crew_period_hours + o.remote_shift_start_hour
    return opening <= start and end <= opening + o.remote_shift_duration_hours + 1e-9


def extend(base, c, o):
    assets, caps, faces, resources = (
        list(base.assets.values()),
        list(base.capabilities.values()),
        list(base.interfaces.values()),
        list(base.resources.values()),
    )
    source = Source(
        "service-hardware-fixture/1",
        "assumption",
        "docs/service-hardware.md",
        "Prepared replaceable control/power modules, ideal command/encoder or load feedback and bounded human procedures; no empirical reliability or arbitrary repair claim",
    )
    communications = Requirement("communications", "equals", True, "boolean", 1)
    crew = Requirement("crew-available", "equals", True, "boolean", 1)
    crew_caps = []
    for i, asset in enumerate(assets):
        name = next((n for n in TARGETS if ASSETS[n] == asset.asset_id), None)
        if name is None:
            continue
        kinds = ["hardware-test"]
        if name in ("cleaner", "rover"):
            kinds += ["remote-release", "guided-return"]
        if name == "portable":
            kinds += ["pack-return"]
        assets[i] = replace(
            asset,
            capabilities=(*asset.capabilities, *(k + ":" + name for k in kinds)),
            tools=(*asset.tools, "service-test", "supervised-control"),
        )
        for kind in (*kinds, "hardware-replacement"):
            key = kind + ":" + name
            worker = kind in ("hardware-replacement", "pack-return") or name == "portable"
            duration = (
                o.hardware_replacement_hours
                if kind == "hardware-replacement"
                else o.remote_release_hours
                if kind == "remote-release"
                else o.robot_test_hours
            )
            caps.append(
                Capability(
                    key,
                    kind,
                    "repair"
                    if kind in ("hardware-replacement", "remote-release")
                    else "observe"
                    if kind == "hardware-test"
                    else "supply",
                    VERSION + "/" + kind,
                    duration,
                    0,
                    o.robot_test_kw if kind == "hardware-test" else 0,
                    consumables=(Quantity("stock:hardware:" + name, 1, "module"),)
                    if kind == "hardware-replacement"
                    else (),
                    requirements=(crew,) if worker else (communications,),
                    shared_resources=() if worker else (Quantity("remote-operator", 1, "person"),),
                    hourly_consumables=() if worker else (Quantity("remote-hours", 1, "h"),),
                    sources=(source,),
                    acceptance=(
                        Requirement("hardware-tracking:" + name, "equals", True, "boolean", 24),
                    )
                    if kind in ("remote-release", "hardware-replacement")
                    else (),
                )
            )
            faces.append(
                Interface(
                    "HARDWARE/" + key,
                    asset.asset_id,
                    asset.home,
                    (kind,),
                    ("module-service",) if kind == "hardware-replacement" else ("service-test",),
                    exclusive_resources=("asset:" + asset.asset_id,)
                    if kind == "hardware-replacement"
                    else (),
                    implementation_id=VERSION,
                )
            )
            if kind == "hardware-replacement":
                crew_caps.append(key)
        resources.append(
            Resource(
                "stock:hardware:" + name, "module", "stock", o.hardware_spares, o.hardware_spares
            )
        )
    assets = [
        replace(a, capabilities=(*a.capabilities, *crew_caps), tools=(*a.tools, "module-service"))
        if a.asset_id == ASSETS["crew"]
        else a
        for a in assets
    ]
    return Registry(assets, faces, caps, resources, base.access)


def before_stage(plan, stage, at, hour, faults):
    """Private ideal actuator interlock, evaluated only after dispatch.

    An open power stage or held command draws no motive energy. Failure is
    published at the next plant boundary; probe electronics have their own load.
    """
    action = plan.order.action
    if action == "crew-return":
        return None  # Packing/vehicle travel does not energise the cleaning pump.
    if action in ACTIONS and action != "guided-return":
        return None
    name = next((n for n in TARGETS if ASSETS[n] == plan.asset.asset_id), None)
    if name is None or (name == "dock" and not action.startswith("charge-")):
        return None
    if name == "portable" and stage.phase not in ("prepare", "perform"):
        return None  # A failed pump does not disable its operator's service vehicle.
    state = faults.service_hardware_truth(name, hour)
    if not state["active"]:
        return None
    return Receipt(
        "Service actuator did not accept the requested command; work stopped",
        (
            Reading(
                "hardware-command:" + name,
                False,
                "boolean",
                at,
                max(hour + 1, available_boundary(at)),
                "service-command-feedback/1:" + plan.order.order_id,
            ),
        ),
        (
            {
                "kind": "hardware-command",
                "target": name,
                "at_hour": at,
                "private_state": state,
                "command_accepted": False,
            },
        ),
        interrupted=True,
    )


def perform(plan, completed, faults, hour, success_probability, draw):
    name = next(n for n in TARGETS if ASSETS[n] == plan.interface.target_asset_id)
    action = plan.order.action
    boundary = available_boundary(completed)
    if action == "hardware-test":
        state = faults.service_hardware_truth(name, hour)
        tracked = not state["active"]
        return Receipt(
            "Prepared function test tracked"
            if tracked
            else "Prepared function test did not track; hardware remains unavailable",
            (
                Reading(
                    "hardware-tracking:" + name,
                    tracked,
                    "boolean",
                    completed,
                    boundary,
                    VERSION + "/test:" + plan.order.order_id,
                ),
            ),
            (
                {
                    "kind": "hardware-test",
                    "target": name,
                    "private_state": state,
                    "tracked": tracked,
                    "completed_at": completed,
                    "available_at": boundary,
                },
            ),
        )
    if action in ("remote-release", "hardware-replacement"):
        return Receipt(
            "Procedure completed; a separate function test is required",
            physical_effects=(
                {
                    "kind": "hardware-procedure",
                    "action": action,
                    "target": name,
                    "completed_at": completed,
                    "effective_at": boundary,
                    "successful": draw(plan, "hardware-procedure") < success_probability,
                },
            ),
        )
    return Receipt("Recorded physical return completed; function evidence is assessed separately")


class HardwareMonitor:
    """Availability from eligible command/test feedback, independent of repair permission.

    No observation permits an initial attempt; it is not a healthy diagnosis.
    This port never receives physical faults, their causes or their schedule.
    """

    def __init__(self, runtime):
        self.rt, self.o = runtime, runtime.options

    def feedback(self, name):
        values = [
            r
            for r in self.rt.executive.observations()
            if r.channel in ("hardware-command:" + name, "hardware-tracking:" + name)
            and r.quality == "usable"
        ]
        return max(values, key=lambda r: (r.measured_at, r.available_at), default=None)

    def operable(self, name):
        latest = self.feedback(name)
        return latest is None or latest.value is True

    def public(self):
        return {
            name: {
                "status": "unobserved"
                if (r := self.feedback(name)) is None
                else "tracking confirmed"
                if r.value is True
                else "command or test failed",
                "feedback": asdict(r) if r is not None else None,
                "may_attempt": self.operable(name),
            }
            for name in TARGETS
            if ASSETS[name] in self.rt.registry.assets
        }


class EquipmentSupport(HardwareMonitor):
    """Recovery workflow with no access to physical fault truth."""

    def __init__(self, runtime):
        super().__init__(runtime)
        self.incidents = {}

    def operable(self, name):
        incident = self.incidents.get(name)
        return super().operable(name) and (incident is None or incident["state"] == "ready")

    def stranded(self, name):
        return [
            m
            for m in self.rt.executive.missions.values()
            if m.plan.asset.asset_id == ASSETS[name]
            and m.status == "stranded"
            and not self.rt.support.recovered(m)
        ]

    def job(self, e, step):
        return next(
            (
                q
                for q in self.rt.orders
                if q.get("equipment_incident") == e["id"] and q.get("equipment_step") == step
            ),
            None,
        )

    def complete(self, q):
        if q is None:
            return False
        m = self.rt.executive.missions.get(q["id"])
        return (
            m is not None
            and m.completed_at is not None
            and available_boundary(m.completed_at) <= self.rt.executive.at_hour
        )

    def request(self, e, action, step, hour):
        prior = self.job(e, step)
        if prior is not None:
            return prior
        return self.rt._queue(
            action,
            hour,
            e["id"] + "/" + step,
            "Observed service-hardware recovery: " + step,
            robot=e["target"],
            equipment_incident=e["id"],
            equipment_step=step,
            origin_order=e["origin_order"],
            recovery_location=e["location"],
            recovery_section=e.get("section"),
        )

    def test_result(self, q):
        if not self.complete(q):
            return None
        readings = [
            r
            for r in self.rt.executive.observations()
            if r.source_id == VERSION + "/test:" + q["id"]
        ]
        return readings[-1].value if readings else None

    def readings(self):
        """Bind a procedure only to its own post-work test, never a later repair."""
        result = []
        for q in self.rt.orders:
            step = {"release": "field-probe", "replacement": "replacement-probe"}.get(
                q.get("equipment_step")
            )
            if step is None:
                continue
            test = next(
                (
                    t
                    for t in self.rt.orders
                    if t.get("equipment_incident") == q.get("equipment_incident")
                    and t.get("equipment_step") == step
                ),
                None,
            )
            if test is None:
                continue
            for r in self.rt.executive.observations():
                if r.source_id == VERSION + "/test:" + test["id"]:
                    result.append(
                        Reading(
                            "hardware-accepted:" + q["id"],
                            r.value,
                            r.unit,
                            r.measured_at,
                            r.available_at,
                            "procedure-test-link/1:" + test["id"],
                            r.quality,
                        )
                    )
        return tuple(result)

    def fallback(self, e, hour, reason):
        for q in self.rt.orders:
            mission = self.rt.executive.missions.get(q["id"])
            if (
                q.get("equipment_incident") == e["id"]
                and q["kind"] in ("remote-release", "hardware-test")
                and mission is not None
                and mission.status in ("active", "scheduled")
            ):
                self.rt.executive.interrupt(q["id"], reason)
            if q.get("equipment_incident") == e["id"] and q["status"] == "queued":
                q.update(status="cancelled", blocked=reason)
        e.update(
            state="retrieve" if self.stranded(e["target"]) else "replace",
            reason=reason,
            changed_at=hour,
        )

    def policy(self, hour):
        rt = self.rt
        for name in TARGETS:
            if ASSETS[name] not in rt.registry.assets:
                continue
            stranded, reading = self.stranded(name), self.feedback(name)
            e = self.incidents.get(name)
            bad = reading is not None and reading.value is False
            origin = (
                stranded[-1].plan.order.order_id
                if stranded
                else reading.source_id.split(":")[-1]
                if bad
                else None
            )
            if origin and (
                e is None
                or (e["state"] == "ready" and (stranded or reading.measured_at >= e["changed_at"]))
            ):
                telemetry = next(
                    (m for m in rt.executive.public()["orders"] if m["order_id"] == origin), None
                )
                location = (
                    {k: telemetry[k] for k in ("from_point", "to_point", "phase", "progress")}
                    if telemetry
                    else None
                )
                e = {
                    "id": name + "/" + origin,
                    "target": name,
                    "origin_order": origin,
                    "opened_at": hour,
                    "changed_at": hour,
                    "location": location,
                    "section": next(
                        (q.get("section") for q in rt.orders if q["id"] == origin), None
                    ),
                    "state": "pack"
                    if name == "portable" and stranded
                    else "remote"
                    if name in ("cleaner", "rover")
                    else "replace",
                    "reason": "Failed command or reported mission interruption; cause not identified",
                }
                self.incidents[name] = e
            if e is None or e["state"] in ("ready", "escalated"):
                continue
            state = e["state"]
            if state == "remote":
                if not self.o.remote_assistance_enabled:
                    self.fallback(e, hour, "Remote assistance disabled")
                    continue
                release = self.request(e, "remote-release", "release", hour)
                if self.complete(release):
                    test = self.request(e, "hardware-test", "field-probe", hour)
                    value = self.test_result(test)
                    if value is True:
                        e.update(
                            state="return" if stranded else "ready",
                            changed_at=hour,
                            reason="Prepared function test tracked after release",
                        )
                    elif value is False:
                        self.fallback(e, hour, "Function test did not track after remote release")
                if e["state"] == "remote" and hour - e["opened_at"] >= self.o.remote_wait_hours:
                    self.fallback(
                        e,
                        hour,
                        "Remote procedure could not establish readiness within its declared wait",
                    )
            elif state in ("return", "pack"):
                if state == "pack" and self.o.crew_return_enabled:
                    if e["origin_order"] in rt.support.returned:
                        e.update(
                            state="test-return",
                            changed_at=hour,
                            reason="Physical crew return recorded; tool test still required",
                        )
                    continue
                action = "pack-return" if state == "pack" else "guided-return"
                q = self.request(e, action, state, hour)
                motion = rt.executive.missions.get(q["id"])
                if e["origin_order"] in rt.support.returned:
                    e.update(
                        state="test-return",
                        changed_at=hour,
                        reason="Physical return recorded; test still required",
                    )
                elif state == "return" and motion is not None and motion.status == "stranded":
                    telemetry = next(
                        m for m in rt.executive.public()["orders"] if m["order_id"] == q["id"]
                    )
                    e.update(
                        origin_order=q["id"],
                        location={
                            k: telemetry[k] for k in ("from_point", "to_point", "phase", "progress")
                        },
                    )
                    self.fallback(
                        e, hour, "Guided return stopped; retrieve from the newly reported location"
                    )
                elif (
                    state == "return"
                    and hour - e["changed_at"] >= self.o.remote_wait_hours
                    and not self.complete(q)
                    and (motion is None or motion.status not in ("active", "scheduled"))
                ):
                    self.fallback(e, hour, "Guided return unavailable; physical retrieval required")
            elif state == "retrieve":
                if not self.o.retrieval_enabled:
                    e["reason"] = "Retrieval disabled; hardware remains at its reported location"
                elif not rt.support.pending("retrieve", origin_order=e["origin_order"]):
                    rt.support.queue(
                        "retrieve",
                        hour,
                        "Observed recovery could not establish a permitted self-return",
                        robot=name,
                        origin_order=e["origin_order"],
                        recovery_location=e["location"],
                        recovery_section=e.get("section"),
                    )
                if e["origin_order"] in rt.support.returned:
                    e.update(
                        state="test-return", changed_at=hour, reason="Physical retrieval recorded"
                    )
            elif state == "test-return":
                q = self.request(e, "hardware-test", "return-probe", hour)
                value = self.test_result(q)
                if value is not None:
                    e.update(
                        state="ready" if value else "replace",
                        changed_at=hour,
                        reason="Returned function test tracked"
                        if value
                        else "Returned function test failed; compatible module replacement required",
                    )
            elif state == "replace":
                q = self.request(e, "hardware-replacement", "replacement", hour)
                if self.complete(q):
                    e.update(
                        state="test-replacement",
                        changed_at=hour,
                        reason="Replacement procedure complete; readiness unproven",
                    )
            elif state == "test-replacement":
                q = self.request(e, "hardware-test", "replacement-probe", hour)
                value = self.test_result(q)
                if value is not None:
                    e.update(
                        state="ready" if value else "escalated",
                        changed_at=hour,
                        reason="Post-replacement function test tracked"
                        if value
                        else "Post-replacement test failed; no compatible further procedure established",
                    )

    def build(self, order):
        rt, o = self.rt, self.o
        kind, name = order["kind"], order["robot"]
        e = self.incidents.get(name)
        if e is None or order["equipment_incident"] != e["id"]:
            raise ValueError("Recovery request no longer matches the observed incident")
        key = kind + ":" + name
        cap, face = rt.registry.capabilities[key], rt.registry.interfaces["HARDWARE/" + key]
        if kind in ("remote-release", "hardware-replacement"):
            cap = replace(
                cap,
                acceptance=(
                    Requirement("hardware-accepted:" + order["id"], "equals", True, "boolean", 24),
                ),
            )
        work = WorkOrder(
            order["id"],
            kind,
            face.interface_id,
            order["created_hour"],
            order["reason"] + " / " + e["id"],
            tuple(Reading(**r) for r in order["evidence"]),
        )
        asset = rt.registry.assets[
            ASSETS["crew"] if kind == "hardware-replacement" else ASSETS[name]
        ]
        if kind == "hardware-replacement":
            if self.stranded(name) or not rt._available(ASSETS["crew"]):
                raise ValueError("Module service requires returned equipment and an available crew")
            return mobile(work, asset, face, cap, rt._context, access=rt.registry.access)
        if any(
            m.status in ("active", "scheduled") and m.plan.asset.asset_id == ASSETS[name]
            for m in rt.executive.missions.values()
        ):
            raise ValueError("Target already has active service work")
        stopped = self.stranded(name)
        point = "recovery/" + stopped[-1].plan.order.order_id if stopped else asset.home
        if kind in ("guided-return", "pack-return") and not stopped:
            raise ValueError(
                "Return requires the original equipment at its observed stopping point"
            )
        if kind == "guided-return":
            reading = self.feedback(name)
            if reading is None or reading.value is not True:
                raise ValueError("Guided return requires successful observed function tracking")
        face = replace(face, point=point)
        actor = replace(
            asset,
            home=point,
            mobility=asset.mobility if kind in ("guided-return", "pack-return") else "fixed",
            autonomy="human" if name == "portable" else "remote-operated",
        )
        reasons = eligibility(work, actor, face, cap, rt._context)
        if reasons:
            raise ResourceConflict(reasons)
        if kind in ("guided-return", "pack-return"):
            home = asset.home
            stages = (
                *(
                    (Stage("prepare", o.retrieval_work_hours, point, point),)
                    if kind == "pack-return"
                    else ()
                ),
                Stage(
                    "return",
                    o.crew_travel_hours if kind == "pack-return" else o.travel_hours,
                    point,
                    home,
                    battery_kw=asset.travel_kw,
                    requirements=(Requirement("route-open", "equals", True, "boolean", 1),),
                ),
                Stage("perform", o.verification_hours, home, home, effect=True),
            )
        else:
            stages = work_stages(actor, face, cap)
        plan = MissionPlan(
            work,
            actor,
            face,
            cap,
            rt.executive.at_hour,
            stages,
            rt._context,
            "observed-location-service-adapter/1",
        )
        if name == "portable":
            from methane.services.support import fits_shift

            if not fits_shift(plan.starting_at, plan.ending_at, o):
                raise ValueError("On-site crew recovery must fit its remaining declared shift")
        else:
            if not remote_shift(plan.starting_at, plan.ending_at, o):
                raise ValueError("Remote procedure must fit an available operator shift")
            if kind == "guided-return":
                plan = replace(
                    plan,
                    stages=tuple(
                        replace(
                            s,
                            reservations=(
                                *s.reservations,
                                Quantity("remote-operator", 1, "person"),
                            ),
                            hourly_consumables=(
                                *s.hourly_consumables,
                                Quantity("remote-hours", 1, "h"),
                            ),
                        )
                        for s in plan.stages
                    ),
                )
        return plan

    def public(self):
        return {
            "implementation_id": VERSION,
            "incidents": copy.deepcopy(list(self.incidents.values())),
            "limit": "Observed command, bounded release, compatible replacement and separate function test. No fault label, arbitrary mechanical repair or personnel injury model.",
        }
