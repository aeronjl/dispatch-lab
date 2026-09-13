"""Current-information recipes for future shared crew visits.

Composition shares only journeys and held resources. Work effects, measurements,
stock acceptance and outcome draws remain with the existing executive.
"""

from dataclasses import asdict, replace

from methane.services.contracts import nonnegative
from methane.services.core import ASSETS
from methane.services.visits import compose, reservations

VERSION = "crew-visit-planning/1"


def check_journeys(singles, visits):
    """Do not promise a second departure before observing the first return.

    A shared itinerary owns its crew through all jobs; distinct departures need
    separate decision boundaries. Otherwise a projection could promise work
    that the current execution readiness gate correctly refuses to dispatch.
    """
    crew = "asset:" + ASSETS["crew"]
    journeys = [
        plan.order.order_id
        for plan in singles
        if plan.asset.asset_id == ASSETS["crew"]
        or any(q.resource == crew for q in plan.asset.support_resources)
    ] + [v.visit_id for v in visits]
    if len(journeys) > 1:
        raise ValueError(
            "One crew journey per candidate: combine compatible jobs in one visit, "
            "or wait for an observed return before scheduling another departure"
        )


def normalized(selections, groups):
    """Reject duplicate work before a caller can accept any reservation."""
    singles = tuple(selections)
    visits = tuple((tuple(keys), start) for keys, start in groups)
    all_keys = [key for key, _ in singles]
    for keys, start in visits:
        if len(keys) < 2:
            raise ValueError("A proposed visit requires at least two jobs")
        nonnegative(start, "visit starting time")
        all_keys.extend(keys)
    if len(set(all_keys)) != len(all_keys):
        raise ValueError("A work order may enter a candidate only once")
    return singles, visits


def propose(runtime, order_ids, starting_at, *, index=0):
    """Compose registered recipes without dispatching work or drawing outcomes."""
    runtime._require_prepared()
    _, groups = normalized((), ((order_ids, starting_at),))
    keys, start = groups[0]
    now, options = runtime.executive.at_hour, runtime.options
    if runtime.support is None or not options.visit_bundling_enabled:
        raise ValueError("Shared visits require enabled finite crew support and visit bundling")
    if len(keys) > options.visit_max_jobs:
        raise ValueError("Proposed visit exceeds the configured job limit")
    if start < now:
        raise ValueError("A proposed visit cannot depart before this decision")
    if type(index) is not int or index < 0:
        raise ValueError("Visit index must be a nonnegative integer")
    if not runtime._available(ASSETS["crew"]):
        raise ValueError("Crew is occupied or stranded; a future return is not assumed")
    orders = {q["id"]: q for q in runtime.orders}
    raw = []
    for key in keys:
        order = orders.get(key)
        if order is None or order["status"] != "queued":
            raise ValueError("A proposed visit requires currently queued work")
        if start < order["created_hour"] + options.crew_response_lead_hours:
            raise ValueError("Every visit request must satisfy its crew response lead")
        raw.append(runtime._build(order))
    visit = compose(
        raw,
        runtime.registry.access,
        "asset:" + ASSETS["crew"],
        f"VISIT-{len(runtime.executive.visits) + index + 1:04}",
        "Planned shared journey for recorded queued work; separate effects and acceptance",
    )
    # The baseline composer starts at its observation context. Shift timing,
    # never observations, before applying calendar and finite-labour checks.
    delta = start - now
    visit = replace(
        visit,
        members=tuple(replace(p, starting_at=p.starting_at + delta) for p in visit.members),
    )
    visit = replace(visit, members=tuple(runtime.support.decorate(p) for p in visit.members))
    if getattr(runtime, "autonomy", None):
        from methane.services.support import fits_shift
        from methane.services.uncertain_timing import envelope_visit

        visit = envelope_visit(visit, runtime.autonomy["duration_bounds"])
        if not fits_shift(visit.starting_at, visit.ending_at, options):
            raise ValueError("Uncertain visit including return exceeds the crew shift")
    reasons = []
    for member in visit.members:
        reasons.extend(
            reason
            for stage in member.stages
            for requirement in stage.requirements
            if (reason := requirement.failure(member.context))
        )
    try:
        runtime.executive.check_visit(visit)
    except ValueError as exc:
        reasons.append(str(exc))
    peak = runtime._peak(now, visit.members)
    if peak > runtime._available_service_pv + 1e-9:
        reasons.append("Current solar cannot supply the combined service rate")
    batches = reservations(visit)
    assessment = dict(
        implementation_id=VERSION,
        visit_id=visit.visit_id,
        feasible=not reasons,
        reasons=list(dict.fromkeys(reasons)),
        order_ids=list(keys),
        starting_at=visit.starting_at,
        returning_at=visit.ending_at,
        current_service_peak_kw=peak,
        requested_stocks=[
            dict(order_id=owner, **asdict(q)) for owner, stock, _ in batches for q in stock
        ],
        requested_capacity=[
            dict(owner=owner, **asdict(b)) for owner, _, bookings in batches for b in bookings
        ],
        scope="Shared crew/tools and current stock reserved before departure. Future access, weather, work success and return remain conditional; each job keeps its own effect and acceptance.",
    )
    return visit, assessment


def accept(runtime, order_ids, starting_at):
    """Rebuild a recipe; accept the whole visit or reserve none of its jobs."""
    visit, assessment = propose(runtime, order_ids, starting_at)
    if not assessment["feasible"]:
        raise ValueError("; ".join(assessment["reasons"]))
    runtime.executive.submit_visit(visit)
    for index, plan in enumerate(visit.members):
        order = next(q for q in runtime.orders if q["id"] == plan.order.order_id)
        order.update(visit_id=visit.visit_id, visit_index=index)
        order.pop("visit_blocked", None)
        runtime._accepted(order, plan, runtime.executive.at_hour)
    runtime.interval["new_visits"].append(visit.to_dict())
    return visit
