"""Read-only demand and obligation projections over versioned mission contracts.

These are conditional plans, not realised effects. No executive, effect port,
fault state or random ledger enters this module. The caller supplies only the
accepted plans and their observed execution cursors, or unaccepted candidates.
"""

from dataclasses import asdict, dataclass
from decimal import Decimal

from methane.services.adapters import claims, eligibility, schedule
from methane.services.contracts import MissionPlan, nonnegative
from methane.services.resources import Ledger

VERSION = "service-demand-projection/1"


@dataclass(frozen=True)
class Commitment:
    plan: MissionPlan
    stage_index: int = 0
    entered: bool = False

    def __post_init__(self):
        if type(self.stage_index) is not int or not 0 <= self.stage_index < len(self.plan.stages):
            raise ValueError("A live commitment needs a valid observed stage cursor")
        if type(self.entered) is not bool:
            raise ValueError("Stage entry must be an observed Boolean")


def D(value):
    return Decimal(str(value))


def horizon(commitments, at_hour, hours, *, standby_kw=0, isolation_resource=None):
    """Project remaining demands, with no assumed repair, delivery or return success.

    One-time supplies belong to stage entry. Already-entered stages do not use
    them twice. Rate consumption intersects each half-open hourly interval.
    Power peaks sum concurrent stages, never the independent peaks of each job.
    The terminal obligation records work after the horizon, including return.
    """
    nonnegative(at_hour, "projection origin")
    nonnegative(standby_kw, "standby power")
    if type(hours) is not int or not 1 <= hours <= 8760:
        raise ValueError("Projection horizon must be 1–8760 hourly intervals")
    items = tuple(commitments)
    identifiers = [c.plan.order.order_id for c in items]
    if len(identifiers) != len(set(identifiers)):
        raise ValueError("A commitment may enter the projection only once")
    origin, end = D(at_hour), D(at_hour) + hours
    stages, obligations = [], []
    for item in items:
        plan, cursor = item.plan, item.stage_index
        if D(plan.context.at_hour) > origin:
            raise ValueError("Commitment contains decision information from the future")
        slots = schedule(plan)
        start, stop, _ = slots[cursor]
        if origin >= D(stop) or (cursor > 0 and origin < D(start)):
            raise ValueError("Execution cursor does not match the projection origin")
        if item.entered and origin < D(start):
            raise ValueError("A future stage cannot already have been entered")
        if not item.entered and origin > D(start):
            raise ValueError("A stage in progress needs its observed entry state")
        for index, (a, b, stage) in enumerate(slots[cursor:], start=cursor):
            a, b = D(a), D(b)
            stages.append(
                (plan, index, max(origin, a), b, stage, not (index == cursor and item.entered))
            )
        time_until_completion = max(D(0), D(plan.ending_at) - end)
        if time_until_completion:
            obligations.append(
                dict(
                    order_id=plan.order.order_id,
                    asset_id=plan.asset.asset_id,
                    target_asset_id=plan.interface.target_asset_id,
                    action=plan.order.action,
                    planned_completion_at=plan.ending_at,
                    remaining_work_hours=float(
                        sum((max(D(0), D(b) - max(end, D(a))) for a, b, _ in slots), D(0))
                    ),
                    waiting_hours=float(max(D(0), D(plan.starting_at) - end)),
                    time_until_completion_hours=float(time_until_completion),
                    return_hours=float(
                        sum(
                            (
                                max(D(0), D(b) - max(end, D(a)))
                                for a, b, s in slots
                                if s.phase == "return"
                            ),
                            D(0),
                        )
                    ),
                    battery_resource=plan.asset.battery_resource,
                    battery_use_after_horizon_kwh=float(
                        sum(
                            (
                                max(D(0), D(b) - max(end, D(a))) * D(s.battery_kw)
                                for a, b, s in slots
                            ),
                            D(0),
                        )
                    ),
                    held_return_margin_kwh=plan.asset.return_reserve_kwh,
                )
            )
    rows = []
    for offset in range(hours):
        a, b = origin + offset, origin + offset + 1
        bus, batteries, quantities, events = D(standby_kw), {}, {}, []
        intervals, isolated, jobs = [], False, set()
        for plan, index, start, stop, stage, needs_entry in stages:
            left, right = max(a, start), min(b, stop)
            duration = max(D(0), right - left)
            if not duration:
                continue
            key = plan.order.order_id
            jobs.add(key)
            bus += duration * D(stage.bus_kw)
            intervals.append((left, right, D(stage.bus_kw)))
            resource = plan.asset.battery_resource
            if resource:
                batteries[resource] = batteries.get(resource, D(0)) + duration * D(stage.battery_kw)
            isolated |= bool(isolation_resource) and any(
                q.resource == isolation_resource and q.amount > 0 for q in stage.reservations
            )
            contributions = [(q, duration * D(q.amount), "rate") for q in stage.hourly_consumables]
            if needs_entry and a <= start < b:
                contributions += [(q, D(q.amount), "stage-entry") for q in stage.consumables]
            for quantity, amount, basis in contributions:
                qkey = (quantity.resource, quantity.unit)
                quantities[qkey] = quantities.get(qkey, D(0)) + amount
                events.append(
                    dict(
                        order_id=key,
                        stage_index=index,
                        phase=stage.phase,
                        resource=quantity.resource,
                        unit=quantity.unit,
                        amount=float(amount),
                        basis=basis,
                        at_hour=float(start) if basis == "stage-entry" else None,
                    )
                )
        points = {a, *(x for x, _, _ in intervals)}
        peak = D(standby_kw) + max(
            (sum((p for x, y, p in intervals if x <= t < y), D(0)) for t in points), default=D(0)
        )
        rows.append(
            dict(
                offset=offset,
                start_hour=float(a),
                end_hour=float(b),
                bus_kwh=float(bus),
                bus_peak_kw=float(peak),
                robot_use_kwh={k: float(v) for k, v in sorted(batteries.items())},
                stock_use=[
                    dict(resource=k, unit=u, amount=float(v))
                    for (k, u), v in sorted(quantities.items())
                ],
                stock_events=events,
                electrolyser_isolated=isolated,
                order_ids=sorted(jobs),
            )
        )
    return dict(
        implementation_id=VERSION,
        at_hour=at_hour,
        hours=hours,
        standby_kw=standby_kw,
        rows=rows,
        terminal_obligations=obligations,
        scope="Conditional remaining mission demand with successful continuation assumed, not execution or verified restoration. No future delivery, charging credit, repair benefit or observation outcome is invented. Return margin is held inventory, not consumed energy.",
    )


def assess_candidate(plan, ledger: Ledger, at_hour):
    """Resource feasibility without publication, reservation or a stochastic event."""
    if plan.context.at_hour != at_hour or plan.starting_at < at_hour:
        raise ValueError("Candidate requires the original current decision context")
    quantities, bookings = claims(plan)
    reasons = list(
        eligibility(plan.order, plan.asset, plan.interface, plan.capability, plan.context)
    )
    reasons.extend(
        reason
        for stage in plan.stages
        for requirement in stage.requirements
        if (reason := requirement.failure(plan.context))
    )
    reasons.extend(ledger.check(plan.order.order_id, quantities, bookings))
    return dict(
        order_id=plan.order.order_id,
        feasible=not reasons,
        reasons=list(dict.fromkeys(reasons)),
        requested_stocks=[asdict(q) for q in quantities],
        requested_capacity=[asdict(b) for b in bookings],
        scope="Current observed eligibility, inventory and declared concurrent capacity only. Future eligibility must be rechecked in execution. No future supply credit or probability of successful work is implied.",
    )
