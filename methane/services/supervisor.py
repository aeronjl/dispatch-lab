"""Bounded selection of declared service schedules under a common outcome tree.

The executive creates requests from observations. This layer schedules those
requests; it cannot invent successful repairs or the value of unknown findings.
Required procedures are explicit obligations, not claims of verified recovery.
"""

import copy
import itertools
from dataclasses import asdict, dataclass
from math import isfinite
from time import perf_counter

from methane.cancellation import checkpoint
from methane.services.contracts import identifier, nonnegative
from methane.services.coupling import accept, decision_key, evaluate, identity

VERSION = "service-schedule-supervisor/1"
TREATMENT_VERSION = "service-schedule-supervisor/2"


@dataclass(frozen=True)
class Candidate:
    candidate_id: str
    selections: tuple[tuple[str, float], ...]

    def __post_init__(self):
        identifier(self.candidate_id, "service candidate")
        if type(self.selections) is not tuple or any(type(x) is not tuple for x in self.selections):
            raise ValueError("Candidate selections must be immutable order/start pairs")
        seen = set()
        for key, start in self.selections:
            identifier(key, "work order")
            nonnegative(start, "candidate start")
            if key in seen:
                raise ValueError("A work order may enter a candidate only once")
            seen.add(key)


def schedules(orders, start_hours, *, required=(), limit=128):
    """Enumerate a complete small search space, rejecting a silently truncated one.

    Optional orders include deferral; required orders must be scheduled. Choices
    are current registered recipes. Charging, new remedy selection and contingent
    follow-up missions require their own proposals and are not fabricated here.
    """
    orders, starts, required = tuple(orders), tuple(start_hours), set(required)
    if len(orders) != len(set(orders)) or required - set(orders):
        raise ValueError("Required orders must belong to the unique candidate work set")
    if type(limit) is not int or not 1 <= limit <= 128:
        raise ValueError("Candidate limit must be 1–128")
    if not starts or len(starts) != len(set(starts)):
        raise ValueError("Supply distinct candidate start hours")
    for key in orders:
        identifier(key, "work order")
    for start in starts:
        nonnegative(start, "candidate start")
    options = [starts if key in required else (None, *starts) for key in orders]
    size = 1
    for values in options:
        size *= len(values)
    if size > limit:
        raise ValueError(f"The declared search contains {size} schedules; limit is {limit}")
    return tuple(
        Candidate(
            f"schedule-{i:03d}",
            tuple(
                (key, start) for key, start in zip(orders, values, strict=True) if start is not None
            ),
        )
        for i, values in enumerate(itertools.product(*options))
    )


def _resources(runtime, projection, floors):
    """Conservative ending stocks with no unearned delivery or charge credit."""
    ending = dict(runtime.ledger.stock)
    for row in projection["rows"]:
        for key, value in row["robot_use_kwh"].items():
            ending[key] -= value
        for value in row["stock_use"]:
            ending[value["resource"]] -= value["amount"]
    violations = [
        dict(
            condition="ending service reserve", resource=key, required=value, predicted=ending[key]
        )
        for key, value in floors.items()
        if ending[key] < value - 1e-9
    ]
    return ending, violations


def choose(
    runtime,
    plant,
    state,
    forecast,
    capacity_kw,
    costs,
    candidates,
    branches,
    service_prices,
    *,
    required_by=None,
    service_reserves=None,
    recorded_prefix=(),
    objective="methane",
    risk_weight=0,
    terminal_minimum=None,
    seconds_per_candidate=0.5,
    wall_seconds=30,
    components=None,
    progress=None,
    reference_forecast=None,
    outcome_references=None,
):
    """Rank only validated feasible candidates using the same declared information.

    The objective is the scenario MILP objective, including its documented start/
    cost tie-breaks. A best incumbent is not proof of the best possible service
    schedule. Unsolved candidates and an exhausted total budget remain visible.
    No live state is mutated. If nothing is feasible, selection stays empty and
    the caller must retain commitments and use its declared fallback/escalation.
    """
    checkpoint()
    key = decision_key(runtime)
    candidates, branches = tuple(candidates), tuple(branches)
    if not 1 <= len(candidates) <= 128 or len({c.candidate_id for c in candidates}) != len(
        candidates
    ):
        raise ValueError("Supply 1–128 distinct service schedules")
    if (
        isinstance(wall_seconds, bool)
        or not isinstance(wall_seconds, (int, float))
        or not isfinite(wall_seconds)
        or wall_seconds <= 0
    ):
        raise ValueError("The comparison time budget must be positive and finite")
    if (
        isinstance(seconds_per_candidate, bool)
        or not isinstance(seconds_per_candidate, (int, float))
        or not isfinite(seconds_per_candidate)
        or seconds_per_candidate <= 0
    ):
        raise ValueError("The per-candidate solver limit must be positive and finite")
    required, floors = dict(required_by or {}), dict(service_reserves or {})
    queued = {o["id"] for o in runtime.orders if o["status"] == "queued"}
    if set(required) - queued:
        raise ValueError("A required procedure must name a current queued work order")
    now = runtime.executive.at_hour
    for deadline in required.values():
        nonnegative(deadline, "procedure deadline")
        if deadline < now or deadline > now + len(forecast["pv_kw"]):
            raise ValueError("A required procedure deadline must lie within the comparison horizon")
    for resource, floor in floors.items():
        nonnegative(floor, "service reserve")
        if resource not in runtime.ledger.stock:
            raise ValueError("A reserve must name a declared service stock: " + resource)
    original = dict(
        decision_key=key,
        candidates=[asdict(c) for c in candidates],
        branches=[asdict(b) for b in branches],
        required_by=required,
        service_reserves=floors,
        terminal_minimum=terminal_minimum,
        objective=objective,
        risk_weight=risk_weight,
        plant=asdict(plant),
        state=asdict(state),
        forecast=forecast,
        capacity_kw=capacity_kw,
        costs=asdict(costs),
        service_prices=service_prices,
        recorded_prefix=recorded_prefix,
        seconds_per_candidate=seconds_per_candidate,
        wall_seconds=wall_seconds,
        **(
            dict(reference_forecast=reference_forecast, outcome_references=outcome_references)
            if reference_forecast is not None
            else {}
        ),
    )
    input_id = identity(original)
    results, best, started, budget_exhausted = [], None, perf_counter(), False
    for i, candidate in enumerate(candidates):
        checkpoint()
        remaining = wall_seconds - (perf_counter() - started)
        if remaining <= 0:
            budget_exhausted = True
            results.extend(
                dict(
                    candidate_id=c.candidate_id,
                    status="not-evaluated",
                    reason="Total comparison time budget exhausted",
                )
                for c in candidates[i:]
            )
            break
        missing = sorted(set(required) - {k for k, _ in candidate.selections})
        if missing:
            results.append(
                dict(
                    candidate_id=candidate.candidate_id,
                    status="infeasible",
                    constraints=[dict(condition="required procedure omitted", order_ids=missing)],
                )
            )
        else:
            evaluated = evaluate(
                runtime,
                plant,
                state,
                forecast,
                capacity_kw,
                costs,
                candidate.selections,
                objective=objective,
                seconds=min(seconds_per_candidate, remaining),
                components=components,
                service_prices=service_prices,
                recorded_prefix=recorded_prefix,
                outcome_branches=branches,
                risk_weight=risk_weight,
                terminal_minimum=terminal_minimum,
                reference_forecast=reference_forecast,
                outcome_references=outcome_references,
            )
            constraints = []
            for proposal in evaluated["proposals"]:
                plan = proposal["plan"]
                order = plan["order"]["order_id"]
                if order in required:
                    # Timelines are derived from the registered recipe, never a user completion claim.
                    completion = plan["starting_at"] + sum(
                        s["duration_hours"] for s in plan["stages"]
                    )
                    if completion > required[order] + 1e-9:
                        constraints.append(
                            dict(
                                condition="procedure deadline",
                                order_id=order,
                                completion_at=completion,
                                required_by=required[order],
                            )
                        )
            ending = None
            if evaluated["projection"] is not None:
                ending, reserve_conditions = _resources(runtime, evaluated["projection"], floors)
                constraints.extend(reserve_conditions)
            status = "infeasible" if constraints else evaluated["state"]
            row = dict(
                candidate_id=candidate.candidate_id,
                status=status,
                evaluation=evaluated,
                constraints=constraints,
                ending_service_stocks=ending,
                score=None,
            )
            if status == "feasible":
                row["score"] = evaluated["outcome_plan"]["solver"]["objective_value"]
                if best is None or (row["score"], candidate.candidate_id) < (
                    best["score"],
                    best["candidate_id"],
                ):
                    best = row
            results.append(row)
        if progress:
            progress(
                dict(
                    completed=i + 1,
                    total=len(candidates),
                    candidate_id=candidate.candidate_id,
                    status=results[-1]["status"],
                )
            )
        if decision_key(runtime) != key:
            raise ValueError("Service comparison belongs to a stale decision")
    checkpoint()
    if decision_key(runtime) != key:
        raise ValueError("Service comparison belongs to a stale decision")
    return dict(
        implementation_id=TREATMENT_VERSION if reference_forecast is not None else VERSION,
        input_id=input_id,
        decision_key=key,
        status="selected"
        if best
        else "unresolved"
        if any(r["status"] in ("unresolved", "not-evaluated") for r in results)
        else "no-feasible-candidate",
        selected_candidate_id=best["candidate_id"] if best else None,
        current_action=copy.deepcopy(best["evaluation"]["outcome_plan"]["current_action"])
        if best
        else None,
        candidates=results,
        budget_exhausted=budget_exhausted,
        seconds=perf_counter() - started,
        objective=objective,
        risk_weight=risk_weight,
        required_by=required,
        service_reserves=floors,
        terminal_minimum=terminal_minimum,
        scope="Best validated incumbent among declared schedules, not a global optimum. Procedure completion includes return but does not establish an informative finding or verified recovery. Predictions assume mission continuation; service outcomes and subsequent remedies are not inferred. No future replenishment/charging credit. Unresolved candidates remain visible; no automatic fallback is claimed."
        + (
            " Cleaning coverage, brush allowance, accumulation and solar conversion are predicted from current surface observations and each outcome's original raw forecast; actual failure can interrupt that continuation."
            if reference_forecast is not None
            else ""
        ),
    )


def commit(runtime, selection):
    """Accept a still-current selected recipe and record the complete comparison."""
    if (
        selection.get("implementation_id") not in (VERSION, TREATMENT_VERSION)
        or selection.get("status") != "selected"
    ):
        raise ValueError("Only a selected service comparison can be committed")
    if decision_key(runtime) != selection["decision_key"]:
        raise ValueError("Service comparison belongs to a stale decision")
    selected = next(
        r
        for r in selection["candidates"]
        if r["candidate_id"] == selection["selected_candidate_id"]
    )
    if selected["status"] != "feasible":
        raise ValueError("Selected candidate must remain feasible")
    power = accept(runtime, selected["evaluation"])
    runtime.interval["decision"]["service_supervisor"] = copy.deepcopy(selection)
    return power
