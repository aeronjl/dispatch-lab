"""Service schedule comparisons from sealed original-information packets.

Preparation reads one selected decision and the preceding economic operands.
Evaluation receives that small packet, never a simulator, future rows, fault
schedule, repriced report, or a private mission outcome. It cannot execute work.
"""

import copy
from dataclasses import fields
from math import isfinite

from methane.cancellation import checkpoint
from methane.components import assemble
from methane.config import Costs, Plant
from methane.dispatch import plan as process_plan
from methane.physics import State
from methane.provenance import LOADED_SOURCE, digest
from methane.service_economics import report as cost_report
from methane.services import charge_control, coupling
from methane.services.adapters import claims
from methane.services.contracts import MissionPlan
from methane.services.coupling import identity
from methane.services.executive import Mission
from methane.services.pricing import recorded_inputs
from methane.services.snapshot import RecordedServices, plan

VERSION = "service-schedule-alternatives/2"
PACKET_VERSION = "service-alternative-inputs/1"


def _number(value, name, *, positive=False):
    if (
        isinstance(value, bool)
        or not isinstance(value, (int, float))
        or not isfinite(value)
        or value < 0
        or (positive and value == 0)
    ):
        raise ValueError(
            name + " must be finite and " + ("positive" if positive else "nonnegative")
        )
    return value


def _mission(value):
    # A recorded plan may also carry a named stochastic event identity. Only
    # the public recipe fields cross this planning interface.
    return plan(
        {f.name: copy.deepcopy(value[f.name]) for f in fields(MissionPlan) if f.name in value}
    )


def prepare(result, controller, hour):
    """Select original inputs on the server; no caller-supplied run or prices."""
    if type(hour) is not int or hour < 0:
        raise ValueError("Select a nonnegative integer decision interval")
    try:
        rows = result["records"][controller]
        row = rows[hour]
    except (KeyError, IndexError) as exc:
        raise ValueError("The selected recorded decision is unavailable") from exc
    decision, field = row["decision"], row.get("field_operations", {})
    snapshot = field.get("planning_snapshot")
    inputs = decision.get("service_planning_inputs")
    if not snapshot or not inputs:
        raise ValueError(
            "Original service planning information was not saved for this decision. "
            "Current documentation remains available; later execution cannot reconstruct it."
        )
    definitions = result.get("service_planning_catalogues", {}).get(snapshot["catalogue_id"])
    if definitions is None:
        raise ValueError("The original service catalogue is missing")
    runtime = RecordedServices(snapshot, definitions)
    if (
        row["hour"] != hour
        or runtime.executive.at_hour != hour
        or inputs.get("schema_version") != "service-process-planning-inputs/1"
        or inputs["forecast"].get("decision_hour") != hour
    ):
        raise ValueError("Original service and process decision boundaries disagree")
    config = result["config"]
    # Process dispatch historically uses a short, spaced-JSON hash; service
    # assumptions use the full provenance identity. Preserve both conventions.
    from methane.simulation import digest as process_price_id

    if inputs["cost_version"] != process_price_id(config["costs"]) or inputs[
        "service_cost_version"
    ] != (digest(config["service_economics"]) if config.get("service_economics") else None):
        raise ValueError("Original dispatch assumptions do not match their recorded identities")
    if not config.get("service_economics") or runtime.support is None:
        raise ValueError("A costed service alternative requires original finite-logistics prices")
    recovery = decision.get("recovery_planning", {})
    joint_request = (
        recovery.get("request")
        if recovery.get("version")
        in ("scheduled-load-tests/2", "scheduled-load-tests/3", "scheduled-load-tests/4")
        else None
    )
    if (decision.get("probe") or recovery.get("status") == "scheduled") and joint_request is None:
        raise ValueError(
            "This decision has a coupled recovery-test commitment. The service alternative "
            "adapter cannot yet preserve that test; no replacement prediction is produced."
        )
    prefix = recorded_inputs(rows[:hour])
    control = decision.get("service_control")
    if control and control["inputs"]["service_cost_prefix"]["prefix_id"] != prefix["prefix_id"]:
        raise ValueError("Original service cost history no longer matches this decision")
    visits = field.get("new_visits", [])
    grouped = {m["order"]["order_id"] for v in visits for m in v["members"]}
    fixed_charges, singles = [], []
    for value in field.get("new_missions", ()):
        m = _mission(value)
        if m.order.action.startswith("charge-"):
            fixed_charges.append(m.to_dict())
        elif m.order.order_id not in grouped:
            singles.append([m.order.order_id, m.starting_at])
    groups = [
        [
            [m["order"]["order_id"] for m in v["members"]],
            min(m["starting_at"] for m in v["members"]),
        ]
        for v in visits
    ]
    singles, groups = coupling_choices(singles, groups)
    queued = {o["id"] for o in runtime.orders if o["status"] == "queued"}
    chosen = {k for k, _ in singles} | {k for keys, _ in groups for k in keys}
    if chosen - queued:
        raise ValueError("Recorded selection was not in the original queued work")
    selected = next(
        (
            c["evaluation"]
            for c in (control or {}).get("candidates", ())
            if c["candidate_id"] == control.get("selected_candidate_id") and c.get("evaluation")
        ),
        None,
    )
    packet = dict(
        schema_version=PACKET_VERSION,
        run_id=result["run_id"],
        controller=controller,
        hour=hour,
        original_source=result.get("provenance", {}).get("source", {}).get("content_hash"),
        snapshot=copy.deepcopy(snapshot),
        catalogue=copy.deepcopy(definitions),
        inputs=copy.deepcopy(inputs),
        plant=copy.deepcopy(config["plant"]),
        models=copy.deepcopy(config.get("models")),
        costs=copy.deepcopy(config["costs"]),
        prices=copy.deepcopy(config["service_economics"]),
        seconds=config["scenario"]["solver_seconds"],
        prefix=prefix,
        original_schedule=dict(singles=singles, groups=groups),
        # Local charging is a recorded decision, not a future receipt. The
        # current charge is held in both local-schedule comparisons. The joint
        # controller instead retains its original absolute energy targets.
        fixed_charges=[] if control else fixed_charges,
        joint_charging=bool(control),
        targets=copy.deepcopy(control["inputs"]["targets"]) if control else [],
        obligations=copy.deepcopy(control["inputs"]["obligations"]) if control else [],
        **(
            dict(
                recovery_request={
                    **copy.deepcopy(joint_request),
                    **(
                        dict(accepted_start=recovery["commitment"]["start_hour"])
                        if recovery.get("commitment")
                        else {}
                    ),
                }
            )
            if joint_request is not None
            else {}
        ),
        recorded=dict(
            process_prediction=copy.deepcopy(decision["plan"]["predicted"]),
            process_solver=copy.deepcopy(decision["plan"]["solver"]),
            service_status=control["status"] if control else "local rule",
            service_fallback=control.get("fallback_used", False) if control else False,
            selected_evaluation=copy.deepcopy(selected),
        ),
    )
    packet["packet_id"] = identity(packet)
    return packet


def coupling_choices(singles, groups):
    from methane.services.visit_planning import normalized

    return normalized(singles, groups)


def _change(packet, request):
    """A targeted change, with no automatic choice of a different job or amount."""
    schedule = copy.deepcopy(packet["original_schedule"])
    targets = copy.deepcopy(packet["targets"])
    kind = request.get("kind")
    if kind in ("postpone", "defer-cleaning"):
        if set(request) != {"kind", "order_id", "delay_hours"}:
            raise ValueError("Postponement requires exactly a work order and delay in hours")
        key, delay = request["order_id"], _number(request["delay_hours"], "Delay", positive=True)
        order = next((o for o in packet["snapshot"]["orders"] if o["id"] == key), None)
        if order is None or order["status"] != "queued":
            raise ValueError("Only work newly selected at this decision can be postponed")
        recipe = packet["snapshot"]["recipes"].get(key, {}).get("plan")
        if kind == "defer-cleaning" and (
            recipe is None or "clean" not in recipe["order"]["action"]
        ):
            raise ValueError("The selected work is not a cleaning procedure")
        found = False
        changed = []
        for name in ("singles", "groups"):
            values = []
            for keys, start in schedule[name]:
                members = [keys] if name == "singles" else list(keys)
                match = key in members
                found |= match
                values.append((keys, start + delay if match else start))
                if match:
                    changed.extend(members)
            schedule[name] = values
        if not found:
            raise ValueError("This work was not newly selected at the recorded decision")
        note = (
            "Postponed the complete shared itinerary"
            if len(changed) > 1
            else "Postponed the selected work"
        )
        note += "; previous commitments and all other selections are retained."
    elif kind == "procedure":
        from methane.services.procedures import selected

        if set(request) != {"kind", "order_id", "procedure_id"}:
            raise ValueError("A procedure change requires exactly a work order and saved procedure")
        key = request["order_id"]
        if not isinstance(key, str):
            raise ValueError("Select a recorded work order identifier")
        chosen = {k for k, _ in schedule["singles"]} | {
            k for keys, _ in schedule["groups"] for k in keys
        }
        if key not in chosen:
            raise ValueError("Only work newly selected at this decision can change procedure")
        choice = selected(packet["snapshot"], key, request["procedure_id"])
        schedule["procedures"] = {key: request["procedure_id"]}
        changed = [key]
        note = (
            "Changed the procedure to "
            + choice["label"]
            + ". "
            + choice["scope"]
            + " Original departure, other selections and accepted commitments remain. "
            "Any shared itinerary is rechecked with the replacement procedure."
        )
    elif kind == "reserve-energy":
        if set(request) != {"kind", "robot", "energy_kwh", "due_hour"}:
            raise ValueError("A reserve requires exactly a robot, energy and absolute deadline")
        if not packet["joint_charging"]:
            raise ValueError(
                "This local-service decision has no original joint charging policy. "
                "An energy-target comparison would change the policy as well as the choice."
            )
        target = charge_control.Target(
            request["robot"],
            request["energy_kwh"],
            request["due_hour"],
            "User-selected service reserve",
        )
        _number(target.energy_kwh, "Reserve energy")
        previous = next((t for t in targets if t["robot"] == target.robot), None)
        if previous and (
            target.energy_kwh < previous["energy_kwh"] or target.due_hour != previous["due_hour"]
        ):
            raise ValueError("An existing reserve commitment keeps its deadline and minimum energy")
        targets = [t for t in targets if t["robot"] != target.robot]
        targets.append(
            dict(
                robot=target.robot,
                energy_kwh=target.energy_kwh,
                due_hour=target.due_hour,
                reason=target.reason,
            )
        )
        changed, note = (
            [],
            "Raised or added a declared reserve; original work and other energy targets remain.",
        )
    else:
        raise ValueError("Unsupported service alternative: " + str(kind))
    return schedule, targets, changed, note


def _evaluate(packet, schedule, targets):
    runtime = RecordedServices(packet["snapshot"], packet["catalogue"])
    for order, procedure in schedule.get("procedures", {}).items():
        runtime.choose_procedure(order, procedure)
    original_key = coupling.decision_key(runtime)
    for value in packet["fixed_charges"]:
        m = plan(value)
        if m.context != runtime._context or m.starting_at != packet["hour"]:
            raise ValueError("Fixed current charging must use the original decision context")
        # Freeze a recorded choice in this private planning copy, never in the
        # execution runtime. Consumption/receipts remain conditional predictions.
        runtime.ledger.reserve(m.order.order_id, *claims(m), runtime.executive.at_hour)
        runtime.executive.missions[m.order.order_id] = Mission(m)
    inputs = packet["inputs"]
    plant, costs = Plant(**packet["plant"]), Costs(**packet["costs"])
    args = (
        runtime,
        plant,
        State(**inputs["estimate"]),
        copy.deepcopy(inputs["forecast"]),
        inputs["capacity_kw"],
        costs,
    )
    common = dict(
        service_prices=packet["prices"],
        recorded_prefix=packet["prefix"]["rows"],
        objective=inputs["objective"],
        seconds=packet["seconds"],
        components=assemble(plant, packet["models"]),
        reference_forecast=copy.deepcopy(inputs["reference_forecast"]),
        visit_groups=schedule["groups"],
    )
    if packet["joint_charging"]:
        recovery_args = {}
        if packet.get("recovery_request"):
            from methane.services.joint_recovery import Request

            recovery_args["recovery_request"] = Request.from_dict(packet["recovery_request"])
        evaluated = charge_control.evaluate(
            *args,
            [charge_control.Target(**t) for t in targets],
            selections=schedule["singles"],
            joint_work=True,
            terminal_battery_value=inputs["terminal_battery_value"],
            **recovery_args,
            **common,
        )
    else:
        demand = coupling.evaluate(
            *args, selections=schedule["singles"], project_only=True, **common
        )
        evaluated = dict(
            state="unresolved", demand=demand, constraints=copy.deepcopy(demand["constraints"])
        )
        if demand["state"] == "projected":
            planned = process_plan(
                plant,
                State(**inputs["estimate"]),
                demand["forecast"],
                inputs["capacity_kw"],
                costs,
                inputs["objective"],
                packet["seconds"],
                allow_fallback=False,
                components=common["components"],
                terminal_battery_value=inputs["terminal_battery_value"],
            )
            evaluated.update(
                process_plan=planned, state="feasible" if planned["actions"] else "unresolved"
            )
    evaluated["original_snapshot_decision_key"] = original_key
    return evaluated


def _summary(packet, schedule, evaluated):
    demand = evaluated.get("demand", {})
    process = evaluated.get("process_plan") or {}
    projection = demand.get("projection") or {}
    prediction = process.get("predicted")
    quote = demand.get("service_pricing") or {}
    prior = cost_report(packet["prefix"]["rows"], packet["prices"], detailed=False)["views"][
        "decision"
    ]["total_eur"]
    service_cost = quote.get("with_additions", {}).get("decision", {}).get("total_eur")
    charging = (evaluated.get("charging") or {}).get("plan") or {}
    extra_dock = charging.get("comparison_economics", {}).get("additional_dock_decision_eur", 0)
    if prior is not None and service_cost is not None and quote.get("status") == "complete":
        service_cost = service_cost - prior + extra_dock
    else:
        service_cost = None
    total = (
        prediction["variable_and_wear_eur"] + service_cost
        if prediction and service_cost is not None
        else None
    )
    stocks = copy.deepcopy(packet["snapshot"]["resources"]["stock"])
    for row in projection.get("rows", ()):
        for key, used in row["robot_use_kwh"].items():
            stocks[key] -= used
        for q in row["stock_use"]:
            stocks[q["resource"]] -= q["amount"]
    for row in charging.get("charging", ()):
        stocks["energy:" + row["robot"]] += row["requested_kw"] - row["charging_loss_kwh"]
    for value in packet["fixed_charges"]:
        m = plan(value)
        stocks["energy:" + m.order.action.removeprefix("charge-")] += (
            sum(s.duration_hours * s.bus_kw for s in m.stages)
            * packet["snapshot"]["config"]["charging_efficiency"]
        )
    chosen = {k for k, _ in schedule["singles"]} | {
        k for keys, _ in schedule["groups"] for k in keys
    }
    backlog = [
        copy.deepcopy(o)
        for o in packet["snapshot"]["orders"]
        if o["status"] == "queued" and o["id"] not in chosen
    ]
    completion = {
        p["plan"]["order"]["order_id"]: plan(p["plan"]).ending_at
        for p in demand.get("proposals", ())
    }
    for visit in demand.get("visit_proposals", ()):
        v = visit["plan"]
        for m in v["members"]:
            completion[m["order"]["order_id"]] = max(plan(p).ending_at for p in v["members"])
    # Accepted work is also a conditional continuation. A completed or
    # verified obligation instead has an already observed satisfaction time;
    # do not turn that known result back into an apparent missed deadline.
    for mission in packet["snapshot"]["missions"]:
        if mission["status"] in ("active", "scheduled"):
            m = plan(mission["plan"])
            completion[m.order.order_id] = m.ending_at
    for visit in packet["snapshot"]["visits"]:
        end = max(plan(m).ending_at for m in visit["members"])
        for m in visit["members"]:
            key = m["order"]["order_id"]
            if key in completion:
                completion[key] = max(completion[key], end)
    deadlines = deadline_evidence(packet["obligations"], completion)
    return dict(
        state=evaluated["state"],
        prediction=prediction,
        solver=process.get("solver"),
        service_decision_eur=service_cost,
        cost_status="complete" if total is not None else "incomplete",
        cost_conditions=quote.get("conditions", []) if total is None else [],
        total_decision_eur=total,
        assumed_contribution_eur=prediction["assumed_value_eur"] - total
        if total is not None
        else None,
        ending_service_stocks=stocks
        if projection.get("rows") and evaluated["state"] == "feasible"
        else None,
        service_stock_units={
            r["resource_id"]: r["unit"]
            for r in packet["catalogue"]["resources"]
            if r["kind"] == "stock"
        },
        unselected_work=backlog,
        original_obligations=deadlines,
        terminal_work=projection.get("terminal_obligations"),
        scope="Conditional horizon prediction. No future repair, inspection finding or supply receipt is credited. Costs include remaining work and dock use, exclude sunk expenditure and fixed ownership, and use original dispatch prices. No inventory resale value. Original deadlines and unselected work stay visible.",
    )


def deadline_evidence(obligations, completion):
    """Keep known satisfaction distinct from conditional procedure completion."""
    deadlines = []
    for obligation in obligations:
        key = obligation.get("current_order_id")
        end = completion.get(key)
        satisfied = (
            obligation.get("satisfied_at")
            if obligation["status"] in ("verified", "completed")
            else None
        )
        observed = satisfied is not None
        boundary = satisfied if observed else end
        deadlines.append(
            dict(
                obligation=obligation,
                observed_satisfied_at=satisfied,
                predicted_completion_at=end,
                met=boundary <= obligation["due_hour"] if boundary is not None else False,
                basis="Observed satisfaction"
                if observed
                else "Conditional work completion; recovery verification remains unknown"
                if end is not None
                else "Completion not established",
            )
        )
    return deadlines


def compare(packet, request, *, progress=None):
    """Recalculate both schedules with the same implementation and information."""
    packet, request = copy.deepcopy(packet), copy.deepcopy(request)
    if packet.get("schema_version") != PACKET_VERSION or identity(
        {k: v for k, v in packet.items() if k != "packet_id"}
    ) != packet.get("packet_id"):
        raise ValueError("Original service comparison packet integrity mismatch")
    runtime = RecordedServices(packet["snapshot"], packet["catalogue"])
    schedule, targets, changed, note = _change(packet, request)
    answer = dict(
        implementation_id=VERSION,
        packet_id=packet["packet_id"],
        run_id=packet["run_id"],
        controller=packet["controller"],
        hour=packet["hour"],
        request=request,
        label="Conditional predictions / original information",
        original_source=packet["original_source"],
        replanner_source=LOADED_SOURCE["content_hash"],
        same_application_source=packet["original_source"] == LOADED_SOURCE["content_hash"],
        same_service_source=runtime.source_matches,
        snapshot_id=runtime.snapshot_id,
        cost_version=packet["inputs"]["cost_version"],
        service_cost_version=packet["inputs"]["service_cost_version"],
        forecast_source=packet["inputs"]["forecast"]["source"],
        objective=packet["inputs"]["objective"],
        hours=len(packet["inputs"]["forecast"]["pv_kw"]),
        changed_order_ids=changed,
        note=note,
        recorded=packet["recorded"],
        context_note="Recorded predictions remain separate from recalculated baselines. Source differences identify current-model replanning; solver timing or a different incumbent can change a recalculation. No later realised information is supplied.",
    )
    for name, choices, reserves in (
        ("baseline", packet["original_schedule"], packet["targets"]),
        ("alternative", schedule, targets),
    ):
        checkpoint()
        if progress:
            progress("Calculating " + name + " schedule from the original information")
        try:
            evaluated = _evaluate(packet, choices, reserves)
            summary = _summary(packet, choices, evaluated)
        except ValueError as exc:
            evaluated = dict(
                state="infeasible",
                constraints=[dict(condition="service comparison", reason=str(exc))],
            )
            summary = dict(state="infeasible", prediction=None, solver=None)
        answer[name] = dict(
            schedule=choices, targets=reserves, evaluation=evaluated, summary=summary
        )
    both = all(answer[k]["summary"]["state"] == "feasible" for k in ("baseline", "alternative"))
    priced = all(
        answer[k]["summary"].get("cost_status") == "complete" for k in ("baseline", "alternative")
    )
    answer["status"] = "complete" if both and priced else "incomplete"
    answer["differences"] = None
    if both:
        a, b = (answer[k]["summary"] for k in ("baseline", "alternative"))
        answer["differences"] = dict(
            methane_kg=b["prediction"]["methane_kg"] - a["prediction"]["methane_kg"],
            reactor_starts=b["prediction"]["reactor_starts"] - a["prediction"]["reactor_starts"],
            decision_eur=b["total_decision_eur"] - a["total_decision_eur"]
            if a.get("total_decision_eur") is not None and b.get("total_decision_eur") is not None
            else None,
        )
    answer["comparison_id"] = identity(answer)
    return answer
