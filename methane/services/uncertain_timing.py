"""Bounded private task clocks and public reservation envelopes.

A reservation is a worst-duration resource commitment, not an observed finish
prediction. Only completed phase boundaries can shorten the public timeline.
The fixed-clock executive remains available for archives and ordinary runs.
"""

import copy
from dataclasses import asdict, replace
from decimal import Decimal

from methane.services.adapters import claims
from methane.services.contracts import Quantity, Stage
from methane.services.executive import Executive
from methane.services.resources import Booking

VERSION = "bounded-service-clock/1"
GROUPS = ("travel", "cleaning", "inspection", "repair", "supply", "support")
PATHS = {"service_system." + group + "_time_factor" for group in GROUPS}


def stage_from_dict(value):
    from methane.services.contracts import Requirement

    return Stage(
        **{
            **value,
            **{
                key: tuple(Quantity(**q) for q in value.get(key, ()))
                for key in ("consumables", "reservations", "hourly_consumables")
            },
            "requirements": tuple(Requirement(**r) for r in value.get("requirements", ())),
        }
    )


def group(plan, stage):
    if plan.order.action.startswith("charge"):
        return None  # Accepted charge intervals never change their timing or credit boundary.
    if stage.phase in ("travel", "return"):
        return "travel"
    if stage.phase != "perform":
        return "support"
    if plan.capability.effect_kind == "clean":
        return "cleaning"
    if plan.capability.effect_kind == "observe":
        return "inspection"
    if plan.capability.effect_kind in ("repair", "calibrate"):
        return "repair"
    return "supply"


def validate_contract(plan):
    value = plan.timing
    if (
        set(value) != {"version", "nominal_stages", "bounds", "groups", "nominal_start"}
        or value["version"] != VERSION
    ):
        raise ValueError("Unsupported service duration contract")
    if (
        not len(plan.stages)
        == len(value["nominal_stages"])
        == len(value["groups"])
        == len(value["bounds"])
    ):
        raise ValueError("A duration contract must describe every stage")
    for raw, interval, key in zip(
        value["nominal_stages"], value["bounds"], value["groups"], strict=True
    ):
        stage_from_dict(raw)
        if key not in (*GROUPS, None) or len(interval) != 2 or not 0 < interval[0] <= interval[1]:
            raise ValueError("Invalid duration support")


def scaled(stage, factor):
    """Coverage supplies follow work, labour and energy follow elapsed time."""
    rates = tuple(
        replace(q, amount=q.amount / factor)
        if q.resource.startswith("brush:") or q.resource in ("water:portable", "stock:water")
        else q
        for q in stage.hourly_consumables
    )
    return replace(
        stage,
        duration_hours=float(Decimal(str(stage.duration_hours)) * Decimal(str(factor))),
        hourly_consumables=rates,
    )


def envelope(plan, bounds):
    if plan.timing is not None or plan.order.action.startswith("charge"):
        return plan
    keys = [group(plan, stage) for stage in plan.stages]
    intervals = [list(bounds[key]) if key else [1, 1] for key in keys]
    # Phase boundaries are unknown. Hold each shared resource throughout the
    # envelope at its maximum simultaneous requirement. Stocks remain separately
    # held per stage, including unspent return energy.
    locks = {}
    for stage in plan.stages:
        for q in stage.reservations:
            if q.resource not in locks or q.amount > locks[q.resource].amount:
                locks[q.resource] = q
    peak = max(s.bus_kw for s in plan.stages)
    stages = tuple(
        replace(scaled(s, b[1]), reservations=tuple(locks.values()), bus_kw=peak)
        for s, b in zip(plan.stages, intervals, strict=True)
    )
    return replace(
        plan,
        stages=stages,
        timing=dict(
            version=VERSION,
            nominal_stages=[asdict(s) for s in plan.stages],
            bounds=intervals,
            groups=keys,
            nominal_start=plan.starting_at,
        ),
    )


def envelope_visit(visit, bounds):
    members, at = [], visit.starting_at
    for raw in visit.members:
        p = envelope(replace(raw, starting_at=at), bounds)
        members.append(p)
        at = p.ending_at
    return replace(visit, members=tuple(members))


def visit_reservations(visit):
    """One sequential crew can occupy each shared resource at most once.

    Keep per-job stock holds, and one whole-visit union of capacity reservations.
    This also covers an earlier-than-upper-bound transfer to the next job.
    """
    entries, capacities = [], {}
    for plan in visit.members:
        quantities, bookings = claims(plan)
        entries.append((plan.order.order_id, quantities, ()))
        for b in bookings:
            old = capacities.get(b.resource)
            if old is None or b.amount > old.amount:
                capacities[b.resource] = b
    entries.append(
        (
            visit.visit_id,
            (),
            tuple(
                Booking(key, visit.starting_at, visit.ending_at, b.amount, b.unit)
                for key, b in capacities.items()
            ),
        )
    )
    return tuple(entries)


class BoundedExecutive(Executive):
    def __init__(self, ledger, effect_port, factors):
        super().__init__(ledger, effect_port)
        self._factors = dict(factors)
        self._execution_plans, self._contracts = {}, {}
        self._integrating = False

    def _physical_plan(self, plan, starting_at=None):
        if plan.timing is None:
            return plan
        value = plan.timing
        stages = []
        for raw, bounds, key in zip(
            value["nominal_stages"], value["bounds"], value["groups"], strict=True
        ):
            factor = self._factors[key] if key else 1
            if not bounds[0] <= factor <= bounds[1]:
                raise ValueError(
                    "Actual task duration lies outside its declared reservation support"
                )
            stages.append(scaled(stage_from_dict(raw), factor))
        return replace(
            plan,
            stages=tuple(stages),
            starting_at=plan.starting_at if starting_at is None else starting_at,
            timing=None,
        )

    def submit(self, plan):
        physical = self._physical_plan(plan)
        key = super().submit(plan)
        self._contracts[key], self._execution_plans[key] = plan, physical
        return key

    def submit_visit(self, visit):
        physical, at = {}, visit.starting_at
        for p in visit.members:
            actual = self._physical_plan(p, at)
            physical[p.order.order_id] = actual
            at = actual.ending_at
        key = super().submit_visit(visit)
        self._contracts.update({p.order.order_id: p for p in visit.members})
        self._execution_plans.update(physical)
        return key

    def _observed_plan(self, key):
        original, mission = self._contracts[key], self.missions[key]
        if original.timing is None:
            return original
        starts = [e for e in mission.events if e["kind"] == "stage_start"]
        ends = [e for e in mission.events if e["kind"] == "stage_end"]
        stages = list(original.stages)
        for i, end in enumerate(ends):
            stages[i] = replace(
                stages[i],
                duration_hours=float(
                    Decimal(str(end["at_hour"])) - Decimal(str(starts[i]["at_hour"]))
                ),
            )
        # Earlier actual starts inside a shared visit are public only once seen.
        beginning = starts[0]["at_hour"] if starts else original.starting_at
        return replace(original, starting_at=beginning, stages=tuple(stages))

    def advance(self, until, context):
        self._integrating = True
        try:
            for key, mission in self.missions.items():
                mission.plan = self._execution_plans[key]
            super().advance(until, context)
        finally:
            self._integrating = False
            for key, mission in self.missions.items():
                mission.plan = self._observed_plan(key)
        return self.public()

    def public(self):
        if self._integrating:
            # super().advance ends by requesting a view. Do not ever return its
            # private clocks, even to an internal caller that later serialises it.
            return {}
        value = super().public()
        value["version"] = VERSION
        for order in value["orders"]:
            mission = self.missions[order["order_id"]]
            if mission.plan.timing:
                order["progress_basis"] = (
                    "Elapsed fraction of declared upper duration; not measured work completion"
                )
                order["duration_contract"] = copy.deepcopy(mission.plan.timing)
                order["observed_phase_boundaries"] = copy.deepcopy(
                    [e for e in mission.events if e["kind"] in ("stage_start", "stage_end")]
                )
                order["finish_upper_at"] = (
                    mission.plan.ending_at if mission.completed_at is None else None
                )
        return value

    def observed_durations(self):
        """Completed durations and right-censoring only; never future endpoints."""
        rows = []
        for key, mission in self.missions.items():
            original = self._contracts[key]
            if original.timing is None:
                continue
            starts = [e for e in mission.events if e["kind"] == "stage_start"]
            ends = [e for e in mission.events if e["kind"] == "stage_end"]
            for i, start in enumerate(starts):
                completed = ends[i]["at_hour"] if i < len(ends) else None
                now = (
                    completed
                    if completed is not None
                    else mission.interrupted_at
                    if mission.interrupted_at is not None
                    else self.at_hour
                )
                rows.append(
                    dict(
                        id=f"{key}/{i}",
                        order_id=key,
                        action=original.order.action,
                        group=original.timing["groups"][i],
                        phase=original.stages[i].phase,
                        started_at=start["at_hour"],
                        available_at=self.at_hour,
                        elapsed_hours=max(0, now - start["at_hour"]),
                        nominal_hours=original.timing["nominal_stages"][i]["duration_hours"],
                        completed_at=completed,
                        censored=completed is None,
                        interrupted=mission.interrupted_at is not None,
                        basis="Observed phase clock; interrupted or unfinished work is right-censored",
                    )
                )
        return rows
