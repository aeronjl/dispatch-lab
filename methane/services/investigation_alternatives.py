"""Revisit a recorded investigation choice without receiving its later outcome.

This is a conditional horizon comparison, not a counterfactual execution of the
completed run. The worker gets the pre-selection snapshot and original belief;
subsequent observations, work receipts and fault truth never cross its port.
"""

import copy
from dataclasses import asdict

from methane.components import assemble
from methane.config import Costs, Models, Plant
from methane.physics import State
from methane.provenance import LOADED_SOURCE
from methane.services.coupling import identity
from methane.services.investigation_belief import Assumptions, Hypothesis
from methane.services.investigation_planning import compare as plan
from methane.services.investigator import InvestigationPolicy
from methane.services.snapshot import RecordedServices

VERSION = "recorded-investigation-alternatives/1"
STRATEGIES = ("inspect-first", "direct-intervention")
LABELS = {"inspect-first": "Inspect first", "direct-intervention": "Intervene directly"}


def _selected(result, controller, hour):
    if type(hour) is not int or hour < 0:
        raise ValueError("Select a nonnegative integer decision interval")
    try:
        row = result["records"][controller][hour]
    except (KeyError, IndexError) as exc:
        raise ValueError("The selected recorded decision is unavailable") from exc
    if row["hour"] != hour:
        raise ValueError("Recorded decision and selected hour disagree")
    investigation = row["decision"].get("service_control", {}).get("investigation", {})
    selections = [e["selection"] for e in investigation.get("episodes", ()) if e.get("selection")]
    if not selections:
        raise ValueError("No original investigation choice was saved for this decision")
    return row, investigation, selections[-1]


def describe(result, controller, hour):
    """Small navigation description; never repeat branch payloads in playback."""
    try:
        _, _, selection = _selected(result, controller, hour)
        origin = selection["inputs"]["snapshot"]["at_hour"]
        if type(origin) not in (int, float) or origin != int(origin) or not 0 <= origin <= hour:
            raise ValueError("Original investigation selection time is invalid")
        if origin != hour:
            return dict(origin_hour=int(origin), note="Return to the saved investigation choice")
        packet = prepare(result, controller, hour)
        return dict(
            origin_hour=hour,
            selection_id=packet["selection_id"],
            selected_strategy=packet["selected_strategy"],
            selected_label=LABELS[packet["selected_strategy"]],
            strategies=[
                dict(value=k, label=LABELS[k])
                for k in STRATEGIES
                if k != packet["selected_strategy"]
            ],
            note="Recalculate both choices from this original belief, forecast and prices. Later findings and actual repair outcomes are excluded.",
        )
    except (ValueError, KeyError, TypeError) as exc:
        return dict(unavailable=str(exc))


def prepare(result, controller, hour):
    row, investigation, selection = _selected(result, controller, hour)
    if identity({k: v for k, v in selection.items() if k != "selection_id"}) != selection.get(
        "selection_id"
    ):
        raise ValueError("Original investigation selection integrity mismatch")
    captured = selection["inputs"]
    runtime = RecordedServices(captured["snapshot"], captured["catalogue"])
    if runtime.executive.at_hour != hour:
        raise ValueError(
            f"Return to original investigation decision H{runtime.executive.at_hour:g}"
        )
    original = selection.get("comparison", {})
    if not original.get("inputs") or identity(original["inputs"]) != original.get("input_id"):
        raise ValueError("Original investigation calculation inputs are missing or inconsistent")
    inputs = original["inputs"]
    config = result["config"]
    process = row["decision"].get("service_planning_inputs", {})
    if any(
        inputs[k] != config[v]
        for k, v in (("plant", "plant"), ("costs", "costs"), ("prices", "service_economics"))
    ):
        raise ValueError("Original investigation plant or dispatch prices are inconsistent")
    if any(
        inputs[k] != process.get(v)
        for k, v in (
            ("state", "estimate"),
            ("capacity_kw", "capacity_kw"),
            ("forecast", "forecast"),
            ("reference_forecast", "reference_forecast"),
        )
    ):
        raise ValueError("Investigation inputs do not match the original process decision")
    if inputs["forecast"]["decision_hour"] != hour or inputs["belief"]["at_hour"] != hour:
        raise ValueError("Investigation forecast and observation boundaries disagree")
    policy = InvestigationPolicy(**investigation["policy"])
    declared = asdict(policy.assumptions)
    recorded_assumptions = inputs["belief"]["assumptions"]
    # The incident binds its own prior epoch; all probability/reader assumptions
    # and the selection rule still come from the recorded controller policy.
    declared["epoch_start_hour"] = recorded_assumptions["epoch_start_hour"]
    if (
        identity(declared) != identity(recorded_assumptions)
        or any(inputs[k] != getattr(policy, k) for k in ("risk_weight",))
        or inputs["seconds"] != policy.comparison_seconds
        or selection["restoration_requirement"] != policy.minimum_restoration_probability
    ):
        raise ValueError("Original investigation assumptions do not match their recorded policy")
    choice = (selection.get("selected") or {}).get("strategy")
    if choice not in STRATEGIES:
        raise ValueError(
            "The original choice was unresolved; there is no selected strategy to replace"
        )
    # Allowlist only pre-selection information. In particular, never include
    # the enclosing episode (which later contains findings and recovery truth).
    packet = dict(
        schema_version=VERSION,
        run_id=result["run_id"],
        controller=controller,
        hour=hour,
        original_source=result.get("provenance", {}).get("source", {}).get("content_hash"),
        selection_id=selection["selection_id"],
        selected_strategy=choice,
        snapshot=copy.deepcopy(captured["snapshot"]),
        catalogue=copy.deepcopy(captured["catalogue"]),
        proposed_request=copy.deepcopy(captured["proposed_request"]),
        proposed_recipe=copy.deepcopy(captured["proposed_recipe"]),
        inputs=copy.deepcopy(inputs),
        models=copy.deepcopy(config.get("models")),
        policy=asdict(policy),
        seconds=inputs["seconds"],
        recorded=copy.deepcopy(original),
    )
    packet["packet_id"] = identity(packet)
    return packet


def validate_request(packet, request):
    if (
        set(request) != {"kind", "selection_id", "strategy"}
        or request.get("kind") != "investigation"
    ):
        raise ValueError("An investigation alternative requires its saved selection and strategy")
    if request["selection_id"] != packet["selection_id"]:
        raise ValueError("Investigation alternative belongs to another original selection")
    if request["strategy"] not in STRATEGIES or request["strategy"] == packet["selected_strategy"]:
        raise ValueError("Choose the other recorded investigation strategy")


def summary(arm, requirement):
    """Probability-weighted reporting only after every branch is feasible.

    Expected inventories/starts are statistics, not a physically executable
    trajectory. Individual cases retain their thermal traces and obligations.
    """
    process = arm.get("process", {})
    feasible = arm.get("status") == "feasible" and bool(process.get("branches"))
    restoration = (
        sum(c["probability"] for c in arm.get("cases", ()) if c["restoration_hypothesis"])
        if feasible
        else None
    )
    out = dict(
        state=arm.get("status", "incomplete"),
        solver=process.get("solver"),
        conditions=arm.get("conditions", []),
        reason=arm.get("reason"),
        restoration_probability=restoration,
        restoration_requirement=requirement,
        eligible=feasible and restoration + 1e-10 >= requirement,
        expected=None,
        worst=process.get("worst"),
    )
    if not feasible:
        return out
    branches = process["branches"]
    if abs(sum(b["probability"] for b in branches) - 1) > 1e-8:
        raise ValueError("A complete investigation prediction requires all probability mass")

    def mean(fn):
        return sum(b["probability"] * fn(b) for b in branches)

    costs = mean(lambda b: b["service_decision_eur"] + b["predicted"]["variable_and_wear_eur"])
    out["expected"] = dict(
        **process["expected"],
        reactor_starts=mean(lambda b: b["predicted"]["reactor_starts"]),
        ending={
            k: mean(lambda b, key=k: b["predicted"]["ending"][key])
            for k in ("battery_kwh", "h2_kg", "co2_kg", "temperature_c")
        },
        service_decision_eur=mean(lambda b: b["service_decision_eur"]),
        total_decision_eur=costs,
    )
    return out


def compare(packet, request, *, progress=None):
    if packet.get("schema_version") != VERSION or identity(
        {k: v for k, v in packet.items() if k != "packet_id"}
    ) != packet.get("packet_id"):
        raise ValueError("Original investigation packet integrity mismatch")
    validate_request(packet, request)
    packet = copy.deepcopy(packet)
    runtime = RecordedServices(packet["snapshot"], packet["catalogue"])
    original = packet["inputs"]
    request_order = packet["proposed_request"]
    if (
        request_order["id"] != original["inspection_order"]
        or request_order["created_hour"] != packet["hour"]
    ):
        raise ValueError("Original proposed inspection and decision boundary disagree")
    runtime.orders.append(copy.deepcopy(request_order))
    runtime.recipes[request_order["id"]] = copy.deepcopy(packet["proposed_recipe"])
    assumptions = copy.deepcopy(original["belief"]["assumptions"])
    assumptions["hypotheses"] = tuple(Hypothesis(**h) for h in assumptions["hypotheses"])
    plant = Plant(**original["plant"])
    if progress:
        progress(
            "Comparing inspection and direct intervention using the saved original information"
        )
    comparison = plan(
        runtime,
        plant,
        State(**original["state"]),
        original["forecast"],
        original["capacity_kw"],
        Costs(**original["costs"]),
        Assumptions(**assumptions),
        original["inspection_order"],
        original["prices"],
        components=assemble(plant, Models(**(packet["models"] or {}))),
        **{
            k: copy.deepcopy(original[k])
            for k in (
                "prefix",
                "objective",
                "seconds",
                "test_hours",
                "risk_weight",
                "terminal_minimum",
                "reference_forecast",
                "test_target_kw",
            )
            if k in original
        },
    )
    requirement = packet["policy"]["minimum_restoration_probability"]
    answer = dict(
        implementation_id=VERSION,
        kind="investigation",
        packet_id=packet["packet_id"],
        run_id=packet["run_id"],
        controller=packet["controller"],
        hour=packet["hour"],
        hours=len(original["forecast"]["pv_kw"]),
        request=copy.deepcopy(request),
        original_source=packet["original_source"],
        replanner_source=LOADED_SOURCE["content_hash"],
        same_application_source=packet["original_source"] == LOADED_SOURCE["content_hash"],
        same_service_source=runtime.source_matches,
        snapshot_id=runtime.snapshot_id,
        selection_id=packet["selection_id"],
        forecast_source=original["forecast"]["source"],
        original_prices=dict(
            process=identity(original["costs"]), service=identity(original["prices"])
        ),
        service_stock_units={
            r["resource_id"]: r["unit"]
            for r in packet["catalogue"]["resources"]
            if r["kind"] == "stock"
        },
        objective=original["objective"],
        risk_weight=original["risk_weight"],
        comparison=comparison,
        recorded=packet["recorded"],
        note="Conditional predictions under the original assumptions. Actual future findings, recovery observations and physical fault identity are excluded. Expected values average possible branches; they are not a single executable plan.",
        context_note="Both strategies are recalculated with the current implementation and original information. Recorded predictions remain separate; finite solver limits can change a numerical rerun. Work completion is not operating confirmation. A strategy below the recorded restoration requirement is shown as ineligible, never silently accepted.",
    )
    for label, strategy in (
        ("baseline", packet["selected_strategy"]),
        ("alternative", request["strategy"]),
    ):
        arm = comparison.get("strategies", {}).get(
            strategy, dict(status="incomplete", reason=comparison.get("reason"))
        )
        answer[label] = dict(
            strategy=strategy, label=LABELS[strategy], summary=summary(arm, requirement)
        )
    answer["status"] = (
        "complete"
        if all(answer[k]["summary"]["state"] == "feasible" for k in ("baseline", "alternative"))
        else "incomplete"
    )
    answer["comparison_id"] = identity(answer)
    return answer
