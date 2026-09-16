"""Conditional service schedules checked against the production planner.

This port evaluates declared work; it does not infer a repair benefit, choose a
fault hypothesis or reveal execution outcomes. The caller must supply the same
eligible forecast and estimated plant state used at the open decision boundary.
"""

import copy
import hashlib
import json
from dataclasses import asdict
from datetime import timedelta
from math import isfinite

from methane.audit import PhysicalAuditError
from methane.cancellation import checkpoint
from methane.dispatch import plan as process_plan
from methane.services import SOURCE_IDENTITY
from methane.services.adapters import claims
from methane.timebase import utc

VERSION = "service-process-demand-coupling/2"
TREATMENT_VERSION = "service-process-demand-coupling/3"
VISIT_VERSION = "service-process-demand-coupling/4"


def _treatment(runtime, forecast, reference, plans, stop_work_at=None):
    """Derive candidate power from eligible raw samples and public surface history."""
    from methane.services.cleaning_forecast import project
    from methane.services.planning import Commitment

    optical = runtime.optical
    if optical is None:
        raise ValueError("Predicted cleaning requires the section optical model")
    if any(
        reference.get(k) != forecast.get(k)
        for k in ("source", "times", "decision_hour", "ambient_c")
    ):
        raise ValueError("Cleaning reference must be the same eligible forecast issue and interval")
    prediction = project(
        optical.plant,
        optical.weather,
        optical.baseline,
        runtime.config,
        runtime.options,
        getattr(optical, "planning_surface", optical.surface).snapshot(),
        reference,
        [
            Commitment(m.plan, m.stage_index, m.entered)
            for m in runtime.executive.missions.values()
            if m.status in ("scheduled", "active")
        ]
        + [Commitment(p) for p in plans],
        brush_remaining_m2=runtime.ledger.stock["brush:cleaner"],
        observed_treatments=optical.observed_treatments()
        if hasattr(optical, "observed_treatments")
        else optical.surface.events,
        stop_work_at=stop_work_at,
    )
    if len(prediction["rows"]) != len(forecast["pv_kw"]) or any(
        abs(r["no_further_cleaning"]["output_kw"] - pv) > 1e-7
        for r, pv in zip(prediction["rows"], forecast["pv_kw"], strict=True)
    ):
        raise ValueError("Cleaning reference does not reproduce the original untreated DC forecast")
    result = copy.deepcopy(forecast)
    result["pv_kw"] = [r["predicted"]["output_kw"] for r in prediction["rows"]]
    result["surface_prediction"] = prediction["scope"]
    return result, prediction


def identity(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def decision_key(runtime):
    """Public current state and assumptions; no private fault or random variates."""
    runtime._require_prepared()
    return identity(
        dict(
            state=runtime.public(),
            context=asdict(runtime._context),
            plant_services=asdict(runtime.config),
            options=asdict(runtime.options),
            available_service_pv_kw=runtime._available_service_pv,
            source=SOURCE_IDENTITY,
        )
    )


def evaluate(
    runtime,
    plant,
    state,
    forecast,
    capacity_kw,
    costs,
    selections=(),
    *,
    objective="methane",
    seconds=0.5,
    complete_new_work=True,
    components=None,
    service_prices=None,
    recorded_prefix=(),
    outcome_branches=None,
    risk_weight=0,
    terminal_minimum=None,
    project_only=False,
    reference_forecast=None,
    outcome_references=None,
    visit_groups=(),
):
    """Read-only feasibility and conditional production for a candidate recipe set.

    Mandatory work must finish within the horizon by default. Existing accepted
    obligations may continue beyond it and stay explicitly reported. Fixed tools
    remain solar-only, matching execution; their peaks cannot be paid with mean
    energy or an invented robot charging credit. No service benefit is forecast.
    """
    checkpoint()
    if objective not in ("greedy", "methane", "economics"):
        raise ValueError("Unknown process objective")
    if not isinstance(complete_new_work, bool):
        raise ValueError("Completion requirement must be boolean")
    if type(project_only) is not bool or (project_only and outcome_branches is not None):
        raise ValueError("Demand-only projection cannot also solve outcome branches")
    if outcome_references is not None and (reference_forecast is None or outcome_branches is None):
        raise ValueError("Outcome cleaning references require raw reference and outcome branches")
    if (
        isinstance(seconds, bool)
        or not isinstance(seconds, (int, float))
        or not isfinite(seconds)
        or seconds <= 0
    ):
        raise ValueError("Solver time must be positive and finite")
    context_key = decision_key(runtime)
    n = len(forecast.get("pv_kw", ()))
    if n < 1:
        raise ValueError("A service comparison needs an eligible forecast horizon")
    for name in ("pv_kw", "ambient_c", "deliveries_kg"):
        values = forecast.get(name, ())
        if len(values) != n or any(
            isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v)
            for v in values
        ):
            raise ValueError("Forecast intervals must have matching finite values: " + name)
        if name != "ambient_c" and any(v < 0 for v in values):
            raise ValueError("Power and feedstock forecasts must be nonnegative")
    now = runtime.executive.at_hour
    if type(forecast.get("decision_hour")) not in (int, float) or forecast["decision_hour"] != now:
        raise ValueError("Forecast must identify the original service decision hour")
    source, times = forecast.get("source", {}), forecast.get("times", ())
    if (
        len(times) != n
        or not source.get("id")
        or not source.get("available_at")
        or not source.get("initialized_at")
    ):
        raise ValueError("Forecast requires saved identity, publication timing and every interval")
    clock = utc(times[0])
    if clock.minute or clock.second or clock.microsecond:
        raise ValueError("Forecast intervals must start on UTC hour boundaries")
    if (
        utc(source["initialized_at"]) > utc(source["available_at"])
        or utc(source["available_at"]) > clock
    ):
        raise ValueError("Forecast issue is not available at the selected decision time")
    if any(utc(t) != clock + timedelta(hours=i) for i, t in enumerate(times)):
        raise ValueError("Forecast must contain consecutive hourly intervals")
    from methane.services.visit_planning import check_journeys, normalized
    from methane.services.visits import reservations as visit_reservations

    choices, groups = normalized(selections, visit_groups)
    result = dict(
        implementation_id=TREATMENT_VERSION if reference_forecast is not None else VERSION,
        decision_key=context_key,
        at_hour=now,
        input_key=identity(
            dict(
                plant=plant.to_dict(),
                state=asdict(state),
                forecast=forecast,
                capacity_kw=capacity_kw,
                costs=asdict(costs),
                objective=objective,
            )
        ),
        selections=[dict(order_id=key, starting_at=start) for key, start in choices],
        state="infeasible",
        constraints=[],
        proposals=[],
        projection=None,
        process_plan=None,
        forecast=None,
        assumptions=dict(
            complete_new_work_within_horizon=complete_new_work,
            outcome="Successful continuation, with no repair, cleaning, supply or information benefit credited",
            service_costs="Not priced by this feasibility port; process decision economics are reported separately",
            power="Hourly mean PV scheduling abstraction; active fixed service peaks require solar power",
            terminal="Remaining accepted work and return energy are reported, without inventory resale credits",
        ),
    )
    if groups:
        result.update(
            implementation_id=VISIT_VERSION,
            visit_groups=[dict(order_ids=list(keys), starting_at=start) for keys, start in groups],
            visit_proposals=[],
        )
    plans = []
    for key, start in choices:
        checkpoint()
        try:
            candidate, assessment = runtime.propose(key, starting_at=start)
        except (ValueError, KeyError) as exc:
            result["constraints"].append(dict(condition="proposal", order_id=key, reason=str(exc)))
            continue
        plans.append(candidate)
        result["proposals"].append(dict(plan=candidate.to_dict(), assessment=assessment))
        result["constraints"].extend(
            dict(condition="current resources or eligibility", order_id=key, reason=reason)
            for reason in assessment["reasons"]
        )
        if complete_new_work and candidate.ending_at > now + n:
            result["constraints"].append(
                dict(
                    condition="new work completion",
                    order_id=key,
                    ending_at=candidate.ending_at,
                    horizon_end=now + n,
                    reason="New work and return extend beyond the comparison boundary",
                )
            )
    single_plans = tuple(plans)
    visits = []
    for index, (keys, start) in enumerate(groups):
        checkpoint()
        try:
            visit, assessment = runtime.propose_visit(keys, starting_at=start, index=index)
        except (ValueError, KeyError) as exc:
            result["constraints"].append(
                dict(condition="visit proposal", order_ids=list(keys), reason=str(exc))
            )
            continue
        visits.append(visit)
        plans.extend(visit.members)
        result["visit_proposals"].append(dict(plan=visit.to_dict(), assessment=assessment))
        result["constraints"].extend(
            dict(condition="visit eligibility or resources", order_ids=list(keys), reason=reason)
            for reason in assessment["reasons"]
        )
        if complete_new_work and visit.ending_at > now + n:
            result["constraints"].append(
                dict(
                    condition="new visit completion",
                    order_ids=list(keys),
                    ending_at=visit.ending_at,
                    horizon_end=now + n,
                    reason="Shared work and crew return exceed the comparison boundary",
                )
            )
    if result["constraints"]:
        return result
    try:
        check_journeys(single_plans, visits)
    except ValueError as exc:
        result["constraints"].append(dict(condition="crew return dependency", reason=str(exc)))
        return result
    try:
        runtime.ledger.reserve_batch(
            [
                *((p.order.order_id, *claims(p)) for p in single_plans),
                *(batch for visit in visits for batch in visit_reservations(visit)),
            ],
            now,
            dry_run=True,
        )
    except ValueError as exc:
        result["constraints"].append(dict(condition="joint resources", reason=str(exc)))
        return result
    projection = runtime.planned_demands(n, candidates=plans)
    result["projection"] = projection
    if reference_forecast is not None:
        forecast, treatment = _treatment(runtime, forecast, reference_forecast, plans)
        result["cleaning_prediction"] = treatment
        result["input_key"] = identity(
            dict(original_input_key=result["input_key"], treatment=treatment["input_id"])
        )
        result["assumptions"]["outcome"] = treatment["scope"]
    if service_prices is not None:
        if runtime.support is None:
            raise ValueError(
                "Complete candidate prices require recorded finite-logistics execution"
            )
        from methane.services.planning import Commitment
        from methane.services.pricing import price

        if now != int(now):
            raise ValueError("Costed service decisions require an hourly recorded prefix")
        quote = price(
            [
                Commitment(m.plan, m.stage_index, m.entered)
                for m in runtime.executive.missions.values()
                if m.status in ("scheduled", "active")
            ],
            [Commitment(p) for p in plans],
            service_prices,
            at_hour=int(now),
            hours=n,
            installed=[key for key, enabled in runtime.interval["assets"].items() if enabled],
            prefix=recorded_prefix,
            visits=(*runtime.executive.visits.values(), *visits),
        )
        result["service_pricing"] = quote
        result["input_key"] = identity(
            dict(
                process_input_key=result["input_key"],
                service_price_id=quote["assumption_id"],
                service_prefix_id=quote["prefix_id"],
            )
        )
        result["assumptions"]["service_costs"] = quote["scope"]
    standby = projection["standby_kw"]
    if abs(max(0, forecast["pv_kw"][0] - standby) - runtime._available_service_pv) > 1e-8:
        raise ValueError("Forecast current power does not match the prepared service decision")
    for row, pv in zip(projection["rows"], forecast["pv_kw"], strict=True):
        active_peak = row["bus_peak_kw"] - standby
        available = max(0, pv - standby)
        if active_peak > available + 1e-9:
            result["constraints"].append(
                dict(
                    condition="active service solar power",
                    offset=row["offset"],
                    required_kw=active_peak,
                    available_kw=available,
                    order_ids=row["order_ids"],
                    reason="Declared tool/charger peak exceeds forecast solar supply",
                )
            )
    if result["constraints"]:
        return result
    coupled = copy.deepcopy(forecast)
    coupled["service_kw"] = [row["bus_kwh"] for row in projection["rows"]]
    prior_isolation = forecast.get("electrolyser_isolated", [False] * n)
    if len(prior_isolation) != n or any(type(x) is not bool for x in prior_isolation):
        raise ValueError("Isolation forecast must contain one Boolean per interval")
    coupled["electrolyser_isolated"] = [
        a or row["electrolyser_isolated"]
        for a, row in zip(prior_isolation, projection["rows"], strict=True)
    ]
    coupled["field_assumption"] = result["assumptions"]["outcome"]
    result["forecast"] = coupled
    checkpoint()
    if project_only:
        result["state"] = "projected"
        result["assumptions"]["process_feasibility"] = "Not solved by this demand-only response"
        if decision_key(runtime) != context_key:
            raise RuntimeError("Service decision changed while the demand was being projected")
        return result
    if outcome_branches is not None:
        from methane.services.scenario_planning import Branch, solve

        variants = tuple(outcome_branches)
        if reference_forecast is not None and (
            outcome_references is None or set(outcome_references) != {b.branch_id for b in variants}
        ):
            raise ValueError("Every outcome needs its own original raw cleaning reference")
        prepared = []
        quote = result.get("service_pricing")
        if quote is None or quote["incremental_decision_eur"] is None:
            result["state"] = "unresolved"
            result["constraints"].append(
                dict(
                    condition="service decision prices",
                    reason="Outcome comparison requires a complete candidate cost and continuation basis",
                )
            )
            return result
        for branch in variants:
            f = branch.forecast
            if f.get("source") != forecast.get("source") or f.get("times") != forecast.get("times"):
                raise ValueError(
                    "Outcome branches must derive from the original forecast issue and window"
                )
            if any(
                f.get(key, [None])[0] != forecast[key][0]
                for key in ("pv_kw", "ambient_c", "deliveries_kg")
            ):
                raise ValueError("Outcome branches cannot replace current plant observations")
            if branch.service_cost_eur:
                raise ValueError(
                    "Coupled mission costs come from the selected recipes, not a second allowance"
                )
            if reference_forecast is not None:
                f, treatment = _treatment(runtime, f, outcome_references[branch.branch_id], plans)
                result.setdefault("outcome_cleaning_predictions", {})[branch.branch_id] = treatment
            for row, pv in zip(projection["rows"], f["pv_kw"], strict=True):
                required = row["bus_peak_kw"] - standby
                available = max(0, pv - standby)
                if required > available + 1e-9:
                    result["constraints"].append(
                        dict(
                            condition="outcome service solar power",
                            branch_id=branch.branch_id,
                            offset=row["offset"],
                            required_kw=required,
                            available_kw=available,
                            reason="Selected fixed work cannot continue under this declared weather outcome",
                        )
                    )
            f["service_kw"] = coupled["service_kw"]
            f["electrolyser_isolated"] = coupled["electrolyser_isolated"]
            prepared.append(
                Branch.create(
                    branch.branch_id,
                    branch.probability,
                    f,
                    branch.information,
                    source=branch.source,
                    service_cost_eur=quote["incremental_decision_eur"],
                    delivery_capacity_kw=branch.delivery_capacity_kw,
                )
            )
        if result["constraints"]:
            return result
        outcome_plan = solve(
            plant,
            state,
            prepared,
            capacity_kw,
            costs,
            objective=objective,
            seconds=seconds,
            components=components,
            risk_weight=risk_weight,
            terminal_minimum=terminal_minimum,
        )
        result["input_key"] = identity(
            dict(
                original_input_key=result["input_key"],
                branches=[asdict(b) for b in prepared],
                risk_weight=risk_weight,
                terminal_minimum=terminal_minimum,
                **(
                    {
                        "cleaning_inputs": {
                            k: v["input_id"]
                            for k, v in result["outcome_cleaning_predictions"].items()
                        }
                    }
                    if reference_forecast is not None
                    else {}
                ),
            )
        )
        result["outcome_plan"] = outcome_plan
        result["state"] = outcome_plan["status"]
        if decision_key(runtime) != context_key:
            raise RuntimeError("Service decision changed while the candidate was being evaluated")
        return result
    try:
        planned = process_plan(
            plant,
            state,
            coupled,
            capacity_kw,
            costs,
            objective,
            seconds,
            allow_fallback=False,
            components=components,
        )
    except PhysicalAuditError as exc:
        result["state"] = "unresolved"
        result["constraints"].append(
            dict(condition="process trajectory verification", reason=str(exc), audits=exc.audits)
        )
        return result
    result["process_plan"] = planned
    if not planned["actions"]:
        result["state"] = "unresolved"
        result["constraints"].append(
            dict(
                condition="process planning",
                reason="No validated incumbent; no feasible combined schedule established",
                solver=planned["solver"],
            )
        )
        return result
    result["state"] = "feasible"
    if decision_key(runtime) != context_key:
        raise RuntimeError("Service decision changed while the candidate was being evaluated")
    return result


def accept(runtime, result):
    """Apply only a still-current feasible recipe; execution rechecks resources."""
    if (
        result.get("implementation_id") not in (VERSION, TREATMENT_VERSION, VISIT_VERSION)
        or result.get("state") != "feasible"
    ):
        raise ValueError("Only a feasible combined schedule may be selected")
    if decision_key(runtime) != result["decision_key"]:
        raise ValueError("Service comparison belongs to a stale decision")
    power = runtime.dispatch_selected(
        [(r["order_id"], r["starting_at"]) for r in result["selections"]],
        charge=False,
        projection_hours=result["projection"]["hours"],
        **(
            dict(visit_groups=[(g["order_ids"], g["starting_at"]) for g in result["visit_groups"]])
            if result.get("visit_groups")
            else {}
        ),
    )
    runtime.interval["decision"]["coupled_evaluation"] = copy.deepcopy(result)
    return power
