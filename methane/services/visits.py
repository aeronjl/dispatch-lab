"""A shared crew itinerary composed of unchanged single-effect job contracts.

Every job keeps its request evidence, physical effect and acceptance test. The
visit owns the crew and accompanying tools until return or explicit interruption.
No future delivery, repair result or observation is credited at dispatch.
"""

from dataclasses import asdict, dataclass, replace

from methane.services.access import Access, Edge
from methane.services.adapters import claims
from methane.services.contracts import MissionPlan, Quantity, Stage, identifier
from methane.services.resources import Booking

VERSION = "crew-visit/1"


def travelling(edges, phase="travel"):
    return tuple(
        Stage(
            phase,
            edge.hours,
            edge.origin,
            edge.destination,
            reservations=(Quantity(edge.resource_id, 1, "slot"),) if edge.resource_id else (),
            requirements=edge.requirements,
        )
        for edge in edges
    )


def assets(plan):
    return (Quantity("asset:" + plan.asset.asset_id, 1, "slot"), *plan.asset.support_resources)


@dataclass(frozen=True)
class VisitPlan:
    visit_id: str
    crew_resource: str
    members: tuple[MissionPlan, ...]
    reason: str
    implementation_id: str = VERSION

    def __post_init__(self):
        identifier(self.visit_id, "visit")
        identifier(self.reason, "visit reason")
        if self.implementation_id != VERSION or len(self.members) < 2:
            raise ValueError("A crew visit needs at least two distinct jobs")
        if len({p.order.order_id for p in self.members}) != len(self.members):
            raise ValueError("A job cannot occur twice in one visit")
        first, last = self.members[0], self.members[-1]
        point, at = first.asset.home, first.starting_at
        for plan in self.members:
            if (
                plan.asset.autonomy != "human"
                or plan.asset.mobility != "crew"
                or plan.asset.home != first.asset.home
                or self.crew_resource not in {q.resource for q in assets(plan)}
            ):
                raise ValueError("Visit members require the same declared crew and home")
            if plan.context != first.context or abs(plan.starting_at - at) > 1e-9:
                raise ValueError("Visit jobs require one decision context and contiguous timing")
            if plan.stages[0].from_point != point:
                raise ValueError("Visit cannot teleport between jobs")
            for index, stage in enumerate(plan.stages):
                if stage.from_point != point:
                    raise ValueError("Visit route has a discontinuity")
                point = stage.to_point
                if point == first.asset.home and (
                    plan is not last or index != len(plan.stages) - 1
                ):
                    raise ValueError("One visit may return home only after its final job")
            if plan.order.deadline is not None and last.ending_at > plan.order.deadline:
                raise ValueError("Shared return exceeds a job's deadline")
            at = plan.ending_at
        if point != first.asset.home:
            raise ValueError("Visit requires a declared return home")

    @property
    def starting_at(self):
        return self.members[0].starting_at

    @property
    def ending_at(self):
        return self.members[-1].ending_at

    def to_dict(self):
        return {**asdict(self), "members": [p.to_dict() for p in self.members]}


def reservations(visit):
    if any(p.timing is not None for p in visit.members):
        from methane.services.uncertain_timing import visit_reservations

        return visit_reservations(visit)
    resources = {}
    for plan in visit.members:
        for q in assets(plan):
            if q.resource in resources and resources[q.resource] != q:
                raise ValueError("Accompanying resource has inconsistent visit requirements")
            resources[q.resource] = q
    envelope = tuple(
        Booking(q.resource, visit.starting_at, visit.ending_at, q.amount, q.unit)
        for q in resources.values()
    )
    return (
        (visit.visit_id, (), envelope),
        *((p.order.order_id, *claims(p, include_asset_bookings=False)) for p in visit.members),
    )


def compose(plans, access, crew_resource, visit_id, reason):
    """Retain task stages, replace repeated home journeys with declared transfers."""
    plans = tuple(plans)
    if len(plans) < 2:
        raise ValueError("A crew visit needs at least two jobs")
    edges = list(access.edges)
    # Retrieval's recorded field-to-dock corridor is assumed traversable in both
    # directions by the recovery crew. This adds no unobserved failure location.
    for p in plans:
        if p.order.action == "retrieve":
            for i, s in enumerate(p.stages):
                if (
                    s.phase == "return"
                    and s.from_point.startswith("recovery/")
                    and s.to_point == "dock"
                ):
                    edges.extend(
                        Edge(
                            f"{p.order.order_id}/retrieval/{i}/{n}",
                            a,
                            b,
                            s.duration_hours,
                            ("crew",),
                            p.capability.requirements,
                        )
                        for n, (a, b) in enumerate(
                            ((s.from_point, s.to_point), (s.to_point, s.from_point))
                        )
                    )
    routing = Access(edges)
    result, at, point = [], plans[0].context.at_hour, plans[0].asset.home
    for i, p in enumerate(plans):
        begin, end = 0, len(p.stages)
        while p.stages[begin].phase == "travel":
            begin += 1
        while p.stages[end - 1].phase == "return":
            end -= 1
        body = p.stages[begin:end]
        route = (
            p.stages[:begin]
            if i == 0
            else travelling(routing.route(point, body[0].from_point, "crew", p.context))
        )
        back = p.stages[end:] if i == len(plans) - 1 else ()
        member = replace(
            p, starting_at=at, stages=(*route, *body, *back), adapter_id="crew-visit-member/1"
        )
        result.append(member)
        at, point = member.ending_at, member.stages[-1].to_point
    return VisitPlan(visit_id, crew_resource, tuple(result), reason)
