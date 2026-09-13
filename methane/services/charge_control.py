"""Recorded service commitments and fixed energy targets to an executable charge.

This bounded controller coordinates the dock and process dispatch. It does not
select a repair method or infer future observations. A target must name why and
by when energy is needed; replanning cannot move that absolute deadline.
"""

import copy
from dataclasses import asdict, dataclass

from methane.services import charging
from methane.services.adapters import claims
from methane.services.contracts import identifier, nonnegative
from methane.services.core import ASSETS
from methane.services.coupling import decision_key, identity
from methane.services.coupling import evaluate as project
from methane.services.planning import Commitment
from methane.services.pricing import dock_cost_table

VERSION = "service-charge-controller-port/1"
WORK_VERSION = "service-work-charge-controller/1"
VISIT_VERSION = "service-work-charge-controller/2"
RECOVERY_VERSION = "service-work-charge-recovery-controller/1"


@dataclass(frozen=True)
class Target:
    robot: str
    energy_kwh: float
    due_hour: int
    reason: str

    def __post_init__(self):
        if self.robot not in ("cleaner", "rover"):
            raise ValueError("A charging target needs a supported robot")
        nonnegative(self.energy_kwh, "target energy")
        if type(self.due_hour) is not int or self.due_hour < 1:
            raise ValueError("Energy target deadline must be an absolute positive hourly boundary")
        identifier(self.reason, "charging target reason")


def _free(runtime, asset, start, end, additions=()):
    return not any(
        b.resource == "asset:" + asset and b.start < end and b.end > start
        for b in (*runtime.ledger.bookings, *additions)
    )


def evaluate(
    runtime,
    plant,
    state,
    forecast,
    capacity_kw,
    costs,
    targets,
    *,
    service_prices,
    recorded_prefix=(),
    objective="methane",
    seconds=0.5,
    components=None,
    alternative=None,
    terminal_battery_value=0,
    selections=(),
    joint_work=False,
    reference_forecast=None,
    visit_groups=(),
    recovery_request=None,
    uncertain=True,
):
    """Read-only current-information charge/production planning with exact usage cost.

    Future access means conditional completion of accepted missions, never
    evidence of a successful return. Departure consumption is conservatively
    funded at the beginning of its hourly interval. The actual current charge
    is rebuilt and rechecked by the executive before any energy is delivered.
    """
    if uncertain and getattr(runtime, "autonomy", None):
        from methane.services.uncertain_planning import evaluate as evaluate_uncertainty

        return evaluate_uncertainty(
            runtime,
            plant,
            state,
            forecast,
            capacity_kw,
            costs,
            targets,
            service_prices=service_prices,
            recorded_prefix=recorded_prefix,
            objective=objective,
            seconds=seconds,
            components=components,
            alternative=alternative,
            terminal_battery_value=terminal_battery_value,
            selections=selections,
            joint_work=joint_work,
            reference_forecast=reference_forecast,
            visit_groups=visit_groups,
            recovery_request=recovery_request,
        )
    key = decision_key(runtime)
    now, n, targets = runtime.executive.at_hour, len(forecast.get("pv_kw", ())), tuple(targets)
    if now != int(now):
        raise ValueError("Charge planning requires an hourly decision boundary")
    if (not targets and not joint_work) or len({t.robot for t in targets}) != len(targets):
        raise ValueError("Supply one distinct absolute target per selected robot")
    if any(t.due_hour > now + n or (t.due_hour <= now and not joint_work) for t in targets):
        raise ValueError("Original target deadline is overdue or beyond the selected horizon")
    if type(joint_work) is not bool or ((selections or visit_groups) and not joint_work):
        raise ValueError("New mission selections require the explicit joint-work interface")
    if recovery_request is not None:
        from methane.services.joint_recovery import Request

        if (
            not joint_work
            or not isinstance(recovery_request, Request)
            or recovery_request.hour != now
            or recovery_request.capacity_kw != capacity_kw
        ):
            raise ValueError(
                "Joint recovery must belong to the current work decision and observed capacity"
            )
    from methane.services.visit_planning import normalized

    selections, visit_groups = normalized(selections, visit_groups)
    if runtime.support is None:
        raise ValueError("Joint charging requires recorded finite-logistics economics")
    if objective not in ("methane", "economics"):
        raise ValueError("Charging requires an explicit planning objective")
    demand = project(
        runtime,
        plant,
        state,
        forecast,
        capacity_kw,
        costs,
        selections,
        objective=objective,
        seconds=seconds,
        components=components,
        project_only=True,
        service_prices=service_prices if joint_work else None,
        recorded_prefix=recorded_prefix,
        reference_forecast=reference_forecast,
        **(dict(visit_groups=visit_groups) if visit_groups else {}),
    )
    result = dict(
        implementation_id=RECOVERY_VERSION
        if recovery_request is not None
        else VISIT_VERSION
        if visit_groups
        else WORK_VERSION
        if joint_work
        else VERSION,
        decision_key=key,
        at_hour=now,
        hours=n,
        targets=[asdict(t) for t in targets],
        state="unresolved",
        demand=demand,
        charging=None,
        current_requests=[],
        constraints=[],
        scope="Conditional saved-information plan. Only this hour's charge may be accepted; later charging, return and energy targets remain predictions. No physical recovery or observation is inferred.",
    )
    if demand["state"] != "projected":
        result["constraints"] = copy.deepcopy(demand["constraints"])
        return result
    commitments = tuple(
        Commitment(m.plan, m.stage_index, m.entered)
        for m in runtime.executive.missions.values()
        if m.status in ("scheduled", "active")
    )
    additions = tuple(
        Commitment(runtime.propose(key, starting_at=start)[0]) for key, start in selections
    )
    from methane.services.visits import reservations as visit_reservations

    visits = tuple(
        runtime.propose_visit(keys, starting_at=start, index=index)[0]
        for index, (keys, start) in enumerate(visit_groups)
    )
    extra_bookings = (
        *(b for c in additions for b in claims(c.plan)[1]),
        *(b for visit in visits for _, _, bookings in visit_reservations(visit) for b in bookings),
    )
    additions += tuple(Commitment(p) for visit in visits for p in visit.members)
    commitments += additions
    completion_boundary = None
    if recovery_request is not None and recovery_request.continuation is not None:
        from methane.services.continuation import completion

        try:
            prerequisite = completion(runtime, recovery_request.continuation, commitments, visits)
        except ValueError as exc:
            result["constraints"].append(
                dict(condition="post-service test prerequisite", reason=str(exc))
            )
            return result
        completion_boundary = prerequisite["boundary"]
        result["test_prerequisite"] = prerequisite
    mission_cost = 0
    if joint_work:
        mission_quote = demand["service_pricing"]
        result["mission_pricing"] = mission_quote
        if (
            mission_quote["status"] != "complete"
            or mission_quote["incremental_decision_eur"] is None
        ):
            result["constraints"].append(
                dict(condition="mission decision prices", reason=mission_quote["status"])
            )
            return result
        mission_cost = mission_quote["incremental_decision_eur"]
    if not targets:
        from methane.dispatch import plan

        recovery = None
        if recovery_request is not None:
            from methane.services.joint_recovery import evaluate as evaluate_recovery

            recovery = evaluate_recovery(
                recovery_request,
                plant,
                state,
                demand["forecast"],
                costs,
                objective=objective,
                seconds=seconds,
                components=components,
                alternative=alternative,
                terminal_battery_value=terminal_battery_value,
                completion_boundary=completion_boundary,
            )
            result["recovery_planning"] = recovery
            planned = recovery["plan"]
            if planned is None:
                result["constraints"].append(
                    dict(
                        condition="combined recovery test and service work",
                        reason=recovery["status"],
                    )
                )
                return result
        else:
            planned = plan(
                plant,
                state,
                demand["forecast"],
                capacity_kw,
                costs,
                objective,
                seconds,
                allow_fallback=False,
                components=components,
                terminal_battery_value=terminal_battery_value,
            )
        result.update(
            process_plan=planned, forecast=demand["forecast"], mission_decision_eur=mission_cost
        )
        if planned["actions"]:
            result.update(
                state="feasible",
                score=planned["solver"]["objective_value"]
                + mission_cost * (1 if objective == "economics" else 0.001),
            )
        return result
    dock_installed = ASSETS["dock"] in runtime.registry.assets
    quote = (
        dock_cost_table(
            commitments,
            service_prices,
            at_hour=int(now),
            hours=n,
            installed=[k for k, v in runtime.interval["assets"].items() if v],
            prefix=recorded_prefix,
            visits=(*runtime.executive.visits.values(), *visits),
        )
        if dock_installed
        else dict(
            status="complete",
            assumption_id=identity(service_prices),
            prefix_id=identity(recorded_prefix),
            incremental_decision_eur=[0] * (n + 1),
            scope="No installed dock; no charging or dock cost can be credited",
        )
    )
    result["pricing"] = quote
    if quote["status"] != "complete":
        result["constraints"].append(
            dict(condition="complete decision prices", reason=quote["status"])
        )
        return result
    c, rows = runtime.config, demand["projection"]["rows"]
    dock_ok = (
        c.dock_available
        and ASSETS["dock"] in runtime.registry.assets
        and (runtime._standby is None or runtime._standby["control_available"])
        and runtime.hardware_operable("dock")
    )
    dock = [
        min(c.dock_kw, max(0, demand["forecast"]["pv_kw"][t] - r["bus_peak_kw"]))
        if dock_ok and _free(runtime, ASSETS["dock"], now + t, now + t + 1, extra_bookings)
        else 0
        for t, r in enumerate(rows)
    ]
    batteries = []
    from methane.services.retrieval_planning import return_boundary

    returns = []
    for target in targets:
        name, asset, resource = target.robot, ASSETS[target.robot], "energy:" + target.robot
        if asset not in runtime.registry.assets:
            raise ValueError("Charging target asset is not installed: " + name)
        if joint_work and target.energy_kwh > getattr(c, name + "_battery_kwh"):
            result["state"] = "infeasible"
            result["constraints"].append(
                dict(
                    condition="energy target exceeds installed battery capacity",
                    reason=f"{name} requires {target.energy_kwh:g} kWh; installed capacity is {getattr(c, name + '_battery_kwh'):g} kWh. The requested target is unchanged.",
                )
            )
            return result
        retrieval = return_boundary(
            runtime, name, commitments, (*runtime.executive.visits.values(), *visits)
        )
        if retrieval:
            returns.append(retrieval)
        available = tuple(
            (
                retrieval is None
                or retrieval["available_at"] is not None
                and now + t >= retrieval["available_at"]
            )
            and _free(runtime, asset, now + t, now + t + 1, extra_bookings)
            for t in range(n)
        )
        use = tuple(r["robot_use_kwh"].get(resource, 0) for r in rows)
        reserve = tuple(
            sum(
                item.plan.asset.return_reserve_kwh
                for item in commitments
                if item.plan.asset.battery_resource == resource and item.plan.ending_at > now + t
            )
            for t in range(n)
        )
        batteries.append(
            charging.Battery(
                name,
                runtime.ledger.stock[resource],
                getattr(c, name + "_battery_kwh"),
                c.charging_efficiency,
                available,
                use,
                reserve,
                target.energy_kwh,
                max(1, int(target.due_hour - now)),
            )
        )
    if returns:
        result["conditional_returns"] = returns
    if recovery_request is not None:
        from methane.services.joint_recovery import evaluate as evaluate_recovery

        charge_inputs = charging.Inputs(
            tuple(batteries), tuple(dock), tuple(quote["incremental_decision_eur"])
        )
        recovery = evaluate_recovery(
            recovery_request,
            plant,
            state,
            demand["forecast"],
            costs,
            objective=objective,
            seconds=seconds,
            components=components,
            alternative=alternative,
            terminal_battery_value=terminal_battery_value,
            charging_inputs=charge_inputs,
            completion_boundary=completion_boundary,
        )
        result["recovery_planning"] = recovery
        planned = recovery["plan"]
        outcome = dict(
            implementation_id=RECOVERY_VERSION,
            status="feasible" if planned else "unresolved",
            plan=planned,
            solver=planned["solver"]
            if planned
            else dict(status=recovery["status"], valid_incumbent=False),
            inputs=dict(
                charging=charge_inputs.to_dict(),
                recovery=recovery_request.to_dict(),
                forecast=copy.deepcopy(demand["forecast"]),
            ),
        )
    else:
        outcome = charging.solve(
            plant,
            state,
            demand["forecast"],
            capacity_kw,
            costs,
            batteries,
            dock,
            quote["incremental_decision_eur"],
            objective=objective,
            seconds=seconds,
            components=components,
            alternative=alternative,
            terminal_battery_value=terminal_battery_value,
        )
    result["charging"] = outcome
    result["missed_target_deadlines"] = [asdict(t) for t in targets if t.due_hour <= now]
    result["target_timing"] = (
        "Original deadlines are retained. An overdue unmet target requests catch-up by the next interval boundary; that does not satisfy its original deadline."
    )
    result["input_key"] = identity(
        dict(
            process=demand["input_key"],
            targets=result["targets"],
            prices=quote["assumption_id"],
            prefix=quote["prefix_id"],
            numerical_inputs=outcome["inputs"],
        )
    )
    if decision_key(runtime) != key:
        raise RuntimeError("Service decision changed during charging evaluation")
    if outcome["status"] != "feasible":
        result["constraints"].append(
            dict(condition="joint dispatch and charging", reason=outcome["solver"]["status"])
        )
        return result
    result["current_requests"] = [
        dict(robot=r["robot"], power_kw=r["requested_kw"])
        for r in outcome["plan"]["charging"]
        if r["offset"] == 0 and r["requested_kw"] > 0
    ]
    for request in result["current_requests"]:
        try:
            _, assessment = runtime.propose_charge(request["robot"], request["power_kw"])
            result["constraints"].extend(
                dict(condition="current charge eligibility", reason=r)
                for r in assessment["reasons"]
            )
        except ValueError as exc:
            result["constraints"].append(
                dict(condition="current charge eligibility", reason=str(exc))
            )
    if not result["constraints"]:
        result["state"] = "feasible"
        result["score"] = outcome["solver"]["objective_value"] + mission_cost * (
            1 if objective == "economics" else 0.001
        )
        result["mission_decision_eur"] = mission_cost
        result["forecast"] = copy.deepcopy(outcome["plan"]["forecast"])
        result["process_plan"] = {
            k: copy.deepcopy(outcome["plan"][k])
            for k in ("actions", "trajectory", "predicted", "solver")
        }
    return result


def accept(runtime, result):
    """Accept only current-hour recipes; retain the conditional plan for inspection."""
    if (
        result.get("implementation_id")
        not in (VERSION, WORK_VERSION, VISIT_VERSION, RECOVERY_VERSION)
        or result.get("state") != "feasible"
    ):
        raise ValueError("Only a feasible charging plan can be selected")
    if decision_key(runtime) != result["decision_key"]:
        raise ValueError("Charging comparison belongs to a stale decision")
    power = runtime.dispatch_selected(
        [(s["order_id"], s["starting_at"]) for s in result["demand"]["selections"]],
        charge=False,
        projection_hours=result["hours"],
        charge_requests=[(r["robot"], r["power_kw"]) for r in result["current_requests"]],
        **(
            dict(
                visit_groups=[
                    (g["order_ids"], g["starting_at"]) for g in result["demand"]["visit_groups"]
                ]
            )
            if result["demand"].get("visit_groups")
            else {}
        ),
    )
    runtime.interval["decision"]["charging_evaluation"] = copy.deepcopy(result)
    return power
