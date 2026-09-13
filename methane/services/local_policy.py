"""Explicit local cleaning rules over the same physical capabilities and observations."""

import copy
from dataclasses import replace

from methane.services.contracts import Reading, Requirement, available_boundary
from methane.services.registry import Registry

VERSION = "local-cleaning-policy/1"
ACCESS = "contact-access/1"
KINDS = ("cleaning", "portable-cleaning")


def interface(base):
    """Only a compatible exposed contact admits the existing contact-reader payload."""
    faces = [
        replace(
            f,
            implementation_id=ACCESS,
            requirements=(
                *f.requirements,
                Requirement("contact-port-accessible", "equals", True, "boolean", 1),
            ),
        )
        if f.interface_id == "ELY/contact"
        else f
        for f in base.interfaces.values()
    ]
    return Registry(
        list(base.assets.values()),
        faces,
        list(base.capabilities.values()),
        list(base.resources.values()),
        base.access,
        builders=base.builders,
    )


def port_reading(options, hour):
    return Reading(
        "contact-port-accessible",
        options.inspection_interface == "accessible-port",
        "boolean",
        hour,
        hour,
        ACCESS,
    )


class CleaningPolicy:
    def __init__(self, runtime):
        self.rt = runtime
        self.mode = runtime.options.cleaning_policy
        self.seen = set()
        self.clocks = (
            {
                s["id"]: dict(
                    section=s["id"],
                    next_due_hour=runtime.options.cleaning_first_due_hour,
                    last_completed_hour=None,
                    completed_passes=0,
                )
                for s in getattr(
                    runtime.optical, "planning_surface", runtime.optical.surface
                ).public()["sections"]
            }
            if runtime.optical
            else {}
        )

    def busy(self, order):
        if order["kind"] not in KINDS:
            return False
        mission = self.rt.executive.missions.get(order["id"])
        return order["status"] == "queued" or (
            mission is not None
            and (
                mission.status in ("scheduled", "active", "awaiting verification")
                or (
                    mission.status == "stranded"
                    and not (self.rt.support and self.rt.support.recovered(mission))
                )
            )
        )

    def policy(self, hour):
        if self.mode == "off":
            return
        rt, o, c = self.rt, self.rt.options, self.rt.config
        sections = getattr(rt.optical, "planning_surface", rt.optical.surface).public()["sections"]
        for kind, enabled in (
            ("cleaning", c.cleaner_enabled),
            ("portable-cleaning", o.portable_cleaner != "none"),
        ):
            busy = [q for q in rt.orders if self.busy(q)]
            if not enabled or any(q["kind"] == kind for q in busy):
                continue
            occupied = {q["section"] for q in busy}
            eligible = [
                s
                for s in sections
                if s["id"] not in occupied
                and (
                    hour >= self.clocks[s["id"]]["next_due_hour"]
                    if self.mode == "periodic"
                    else s["removable_fraction"] >= c.cleaning_threshold
                    or (
                        kind == "portable-cleaning"
                        and o.portable_cleaner == "wet"
                        and s["adhered_fraction"] >= o.portable_adhered_threshold
                    )
                )
            ]
            if not eligible:
                continue
            target = (
                min(eligible, key=lambda s: (self.clocks[s["id"]]["next_due_hour"], s["id"]))
                if self.mode == "periodic"
                else max(
                    eligible,
                    key=lambda s: (
                        s["removable_fraction"]
                        * (
                            o.portable_loose_removal
                            if kind == "portable-cleaning"
                            else c.cleaning_removal_fraction
                        )
                        + (
                            s["adhered_fraction"] * o.portable_adhered_removal
                            if kind == "portable-cleaning" and o.portable_cleaner == "wet"
                            else 0
                        ),
                        s["id"],
                    ),
                )
            )
            reason = (
                "Periodic section pass is due; oldest due section first, then section identifier"
                if self.mode == "periodic"
                else "Current ideal surface estimate exceeds the compatible treatment threshold; largest treatable loss first"
            )
            metadata = dict(
                cleaning_policy=VERSION,
                cleaning_rule=self.mode,
                due_hour=self.clocks[target["id"]]["next_due_hour"]
                if self.mode == "periodic"
                else None,
                measured_surface=copy.deepcopy(target),
            )
            if kind == "portable-cleaning":
                metadata["method"] = "portable-" + o.portable_cleaner
            # Scarce supplies leave an explicit queued request; the executive
            # still checks energy, access, weather, staff and every reservation.
            rt._queue(kind, hour, 0, reason, target["id"], **metadata)

    def commit(self, hour):
        events = []
        for order in self.rt.orders:
            if order["kind"] not in KINDS or order["id"] in self.seen:
                continue
            mission = self.rt.executive.missions.get(order["id"])
            if mission is None or mission.work_completed_at is None:
                continue
            end = mission.work_completed_at
            if available_boundary(end) > hour:
                continue
            self.seen.add(order["id"])
            if mission.interrupted_at is not None and mission.interrupted_at <= end + 1e-9:
                continue
            state = self.clocks[order["section"]]
            event = dict(
                order_id=order["id"],
                section=order["section"],
                completed_at=end,
                effective_at=available_boundary(end),
                previous_due_hour=state["next_due_hour"],
                next_due_hour=end + self.rt.options.cleaning_period_hours,
                implementation_id=VERSION,
            )
            state.update(
                last_completed_hour=end,
                next_due_hour=event["next_due_hour"],
                completed_passes=state["completed_passes"] + 1,
            )
            events.append(event)
        return events

    def public(self):
        return dict(
            implementation_id=VERSION,
            mode=self.mode,
            first_due_hour=self.rt.options.cleaning_first_due_hour,
            recurrence_hours=self.rt.options.cleaning_period_hours,
            schedules=[
                {**s, "overdue_hours": max(0, self.rt.executive.at_hour - s["next_due_hour"])}
                for s in self.clocks.values()
            ]
            if self.mode == "periodic"
            else [],
            scope="Local rule using available ideal surface estimates or a declared recurrence. No future weather, price optimization or injected fault truth. Completed full passes reset recurrence; partial treatment remains in the physical surface but earns no full-pass credit.",
        )
