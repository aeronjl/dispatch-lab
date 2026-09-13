"""Inspect-first versus direct intervention under declared contact hypotheses.

Inspection histories may change a remedy and its test window. Unobserved repair
success never changes a requested action or the controller's capacity estimate.
This planner has no execution effect port; a real controller must replan after
each actual observation and use the existing recovery verifier.
"""

import copy
from dataclasses import asdict
from math import ceil

from methane.cancellation import checkpoint
from methane.components import assemble
from methane.service_economics import report
from methane.services.adapters import schedule
from methane.services.conditional_work import GuardedWork, project, remedy
from methane.services.coupling import decision_key, identity
from methane.services.investigation_belief import MECHANISMS, findings, update
from methane.services.scenario_planning import Branch, solve

VERSION = "inspection-contingency-planning/1"
BOUNDED_TEST_VERSION = "inspection-contingency-planning/2"


def compare(
    runtime,
    plant,
    state,
    forecast,
    capacity,
    costs,
    assumptions,
    inspection_order,
    prices,
    *,
    prefix=(),
    objective="methane",
    seconds=2,
    test_hours=2,
    risk_weight=0,
    terminal_minimum=None,
    components=None,
    reference_forecast=None,
    test_target_kw=None,
):
    """Paired conditional schedules, without pretending to verify future recovery.

    Test requests use nameplate for the configured consecutive interval count,
    then return to the original estimate. Repair success is a latent branch of
    the existing qualified-procedure assumption, conditioned on a mechanism that
    the action can actually address. This is not a generic repair bonus.
    """
    runtime._require_prepared()
    components = components or assemble(plant)
    key = decision_key(runtime)
    if not 0 <= capacity < plant.electrolyser_kw:
        raise ValueError("Investigation requires an observed capacity shortfall")
    if type(test_hours) is not int or not 1 <= test_hours <= 8:
        raise ValueError("A verification window needs one to eight consecutive hourly requests")
    bounded = test_target_kw is not None
    target = plant.electrolyser_kw if test_target_kw is None else test_target_kw
    if (
        isinstance(target, bool)
        or not isinstance(target, (int, float))
        or not max(capacity, plant.min_kw - 1e-9) < target <= plant.electrolyser_kw
    ):
        raise ValueError(
            "Predicted test load must exceed observed capacity within operating bounds"
        )
    now = runtime.executive.at_hour
    if now != int(now):
        raise ValueError("Process investigation requires an hourly decision boundary")
    now = int(now)
    n = len(forecast["pv_kw"])
    if any(v != capacity for v in forecast.get("electrolyser_capacity_kw", [capacity] * n)):
        raise ValueError(
            "Existing future capacity commitments require joint preservation, not replacement by this investigation"
        )
    belief = update(assumptions, runtime._context, runtime.options)
    original = dict(
        decision_key=key,
        plant=asdict(plant),
        component_models=components.identities(),
        component_parameters={
            k: asdict(getattr(components, k).parameters) for k in components.identities()
        },
        state=asdict(state),
        forecast=copy.deepcopy(forecast),
        capacity_kw=capacity,
        costs=asdict(costs),
        prices=copy.deepcopy(prices),
        prefix=copy.deepcopy(prefix),
        belief=belief,
        inspection_order=inspection_order,
        objective=objective,
        seconds=seconds,
        test_hours=test_hours,
        **(dict(test_target_kw=target) if bounded else {}),
        risk_weight=risk_weight,
        terminal_minimum=terminal_minimum,
        reference_forecast=copy.deepcopy(reference_forecast),
    )
    result = dict(
        implementation_id=BOUNDED_TEST_VERSION if bounded else VERSION,
        inputs=original,
        input_id=identity(original),
        strategies={},
        scope="Original-information conditional prediction. Actual finding chooses a compatible remedy; no private fault identity or success draw enters. Consecutive test requests are planned, but confirmation and any later capacity upgrade require actual observations. Static contact hypotheses, finite noise quadrature and qualified-procedure reliability are illustrative assumptions. No general POMDP or global service-routing optimum is claimed.",
    )
    if belief["posterior"] is None:
        return {
            **result,
            "status": "incomplete",
            "reason": belief.get("reason")
            or "Current observation is outside the declared hypothesis support",
        }
    try:
        inspector, assessment = runtime.propose(inspection_order)
        if inspector.order.action != "read-trip-contact" or not assessment["feasible"]:
            raise ValueError("Inspection requires a currently feasible registered contact read")
        measured = next(b for _, b, s in schedule(inspector) if s.effect)
        finding_rows = findings(
            belief,
            "fixed" if inspector.asset.mobility == "fixed" else "mobile",
            runtime.options,
            measured_at=measured,
        )["branches"]
        interruption_probability = (
            runtime.config.mission_failure_probability if inspector.asset.battery_resource else 0
        )
        for event in finding_rows:
            event["joint"] = {
                k: v * (1 - interruption_probability) for k, v in event["joint"].items()
            }
            event["probability"] *= 1 - interruption_probability
        finding_rows = [event for event in finding_rows if event["probability"] > 0]
        if interruption_probability:
            finding_rows.append(
                dict(
                    finding="interrupted",
                    probability=interruption_probability,
                    joint={k: v * interruption_probability for k, v in belief["posterior"].items()},
                    posterior=copy.deepcopy(belief["posterior"]),
                    context="prediction",
                    measured_at=measured,
                    available_at=ceil(measured),
                    interruption_at=measured,
                    permitted_contact_reset=False,
                    scope="Registered mission failure at contact-read completion, before sampling. Its notification leaves the fault prior unchanged; rover retrieval and readiness remain outstanding.",
                )
            )
    except ValueError as exc:
        inspector = None
        finding_rows = []
        inspection_error = str(exc)
    prior_cost = report(prefix, prices, detailed=False)["views"]["decision"]["total_eur"]
    if prior_cost is None:
        return {
            **result,
            "status": "incomplete",
            "reason": "Original incurred service costs are incomplete",
        }
    for strategy in ("direct-intervention", "inspect-first"):
        checkpoint()
        cases = []
        branches = []
        bounds = {}
        errors = []
        projections = {}
        if strategy == "inspect-first" and inspector is None:
            result["strategies"][strategy] = dict(
                status="incomplete", conditions=[inspection_error], cases=[]
            )
            continue
        events = (
            finding_rows
            if strategy == "inspect-first"
            else [
                dict(
                    finding="not-inspected",
                    available_at=now,
                    context="prediction",
                    joint=belief["posterior"],
                )
            ]
        )
        for event in events:
            finding = event["finding"]
            action = "reset" if event.get("permitted_contact_reset") else "module-replacement"
            try:
                intervention = remedy(
                    runtime,
                    action,
                    requested_at=event["available_at"],
                    finding=event if strategy == "inspect-first" else None,
                    request_id="predicted-" + strategy + "-" + finding + "-" + action,
                )
                work = (
                    [GuardedWork(inspector, None, now, None, event.get("interruption_at"))]
                    if strategy == "inspect-first"
                    else []
                ) + [intervention]
                projected = project(
                    runtime,
                    work,
                    forecast,
                    prices,
                    prefix=prefix,
                    reference_forecast=reference_forecast,
                )
                projections[projected["projection_id"]] = projected
                remaining = copy.deepcopy(runtime.ledger.stock)
                for row in projected["projection"]["rows"]:
                    for resource, used in row["robot_use_kwh"].items():
                        remaining[resource] -= used
                    for quantity in row["stock_use"]:
                        remaining[quantity["resource"]] -= quantity["amount"]
                quote = projected["service_pricing"]
                if quote["status"] != "complete":
                    raise ValueError(
                        "Conditional procedure costs are unresolved: " + quote["status"]
                    )
                service_cost = quote["with_additions"]["decision"]["total_eur"] - prior_cost
                test_begin = ceil(intervention.plan.ending_at) - int(now)
                if test_begin + test_hours > n:
                    raise ValueError(
                        "Procedure, return and consecutive test requests exceed this horizon"
                    )
                effect = next(
                    ceil(b) - int(now) for _, b, s in schedule(intervention.plan) if s.effect
                )
            except ValueError as exc:
                errors.append(
                    dict(finding=finding, probability=sum(event["joint"].values()), reason=str(exc))
                )
                continue
            for hypothesis in assumptions.hypotheses:
                weight = event["joint"][hypothesis.hypothesis_id]
                if weight <= 0:
                    continue
                compatible = MECHANISMS[hypothesis.mechanism][
                    "reset_restores" if action == "reset" else "replacement_restores"
                ]
                chance = runtime.config.repair_success_probability if compatible else 0
                for restored, p in ((True, chance), (False, 1 - chance)):
                    if p <= 0:
                        continue
                    branch_id = f"{finding}:{hypothesis.hypothesis_id}:{'restored' if restored else 'unchanged'}"
                    f = copy.deepcopy(projected["forecast"])
                    # Forecast capacity remains the original controller estimate.
                    # Possible physical delivery is a separate latent interface.
                    f["electrolyser_capacity_kw"] = [capacity] * n
                    delivery = [
                        plant.electrolyser_kw if restored and t >= effect else capacity
                        for t in range(n)
                    ]
                    history = tuple(
                        "original-information" if now + t < event["available_at"] else finding
                        for t in range(n)
                    )
                    minimum = [0] * n
                    maximum = [capacity if capacity >= plant.min_kw else 0] * n
                    for t in range(test_begin, test_begin + test_hours):
                        minimum[t] = maximum[t] = target
                    bounds[branch_id] = dict(minimum=minimum, maximum=maximum)
                    branches.append(
                        Branch.create(
                            branch_id,
                            weight * p,
                            f,
                            history,
                            source=assumptions.source,
                            service_cost_eur=service_cost,
                            delivery_capacity_kw=delivery,
                        )
                    )
                    cases.append(
                        dict(
                            branch_id=branch_id,
                            probability=weight * p,
                            finding=finding,
                            mechanism_hypothesis=hypothesis.mechanism,
                            requested_remedy=action,
                            projection_id=projected["projection_id"],
                            restoration_hypothesis=restored,
                            test_start_hour=now + test_begin,
                            test_end_hour=now + test_begin + test_hours,
                            **(dict(test_target_kw=target) if bounded else {}),
                            ending_diagnostic_state="Unverified in this prediction; actual tracking observations required",
                            required_followup="Observe test; recover only on confirmation, otherwise retain derating and unresolved intervention work",
                            conditional_ending_service_stocks=remaining,
                            outstanding_recovery=copy.deepcopy(
                                projected["predicted_interruptions"]
                            ),
                            unselected_requests=[
                                copy.deepcopy(o)
                                for o in runtime.orders
                                if o["status"] == "queued"
                                and not (
                                    strategy == "inspect-first" and o["id"] == inspection_order
                                )
                            ],
                        )
                    )
        if errors:
            result["strategies"][strategy] = dict(
                status="incomplete",
                conditions=errors,
                cases=cases,
                projections=projections,
                reason="Every positive-probability finding needs a feasible continuation; no branch is discarded or renormalized",
            )
            continue
        try:
            evaluated = solve(
                plant,
                state,
                branches,
                capacity,
                costs,
                objective=objective,
                risk_weight=risk_weight,
                terminal_minimum=terminal_minimum,
                seconds=seconds,
                components=components,
                branch_requested_bounds=bounds,
            )
            result["strategies"][strategy] = dict(
                status=evaluated["status"],
                cases=cases,
                process=evaluated,
                branch_inputs=[asdict(b) for b in branches],
                requested_bounds=bounds,
                projections=projections,
            )
        except ValueError as exc:
            result["strategies"][strategy] = dict(
                status="incomplete", conditions=[str(exc)], cases=cases, projections=projections
            )
    result["status"] = (
        "complete"
        if all(s["status"] == "feasible" for s in result["strategies"].values())
        else "incomplete"
    )
    if decision_key(runtime) != key:
        raise RuntimeError("Service information changed during conditional comparison")
    result["comparison_id"] = identity(result)
    return result
