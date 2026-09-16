"""Read-only decision views and process-policy forks of original information.

No later observation, realised weather, or simulator fault truth enters a fork.
The displayed recorded execution is deliberately outside the worker packet.
"""

import copy
import hashlib
import json
from dataclasses import asdict

from methane.components import assemble
from methane.config import Config, Costs, Plant
from methane.dispatch import plan
from methane.physics import State

VERSION = "dispatch-lab/control-view/1"
POLICIES = {"Greedy": "greedy", "MPC · methane": "methane", "MPC · economics": "economics"}
SCOPE = (
    "Process dispatch comparison. All three start from the same recorded estimate, "
    "forecast, capacity estimate and original dispatch prices. Recorded service power, "
    "isolation and deliveries stay fixed. Robot scheduling is not re-optimised. "
    "These are current-model predictions, not alternative realised histories."
)
ALTERNATIVES = {
    "battery": "Prevent battery discharge",
    "electrolyser": "Keep electrolysis off",
    "reactor": "Delay reactor start",
    "co2": "Delay next CO₂ delivery by 24 h",
}


def prepare_alternative(result, controller, hour, alternative="policies"):
    packet = prepare(result, controller, hour)
    if alternative == "policies":
        return packet
    if alternative not in ALTERNATIVES:
        raise ValueError("Unknown decision alternative")
    d = selected(result, controller, hour)["decision"]
    packet.update(
        alternative=alternative,
        objective=d.get("planning_objective", d.get("policy", "methane")),
    )
    packet.pop("information_id")
    packet["information_id"] = digest(packet)
    return packet


def compare_alternative(packet, progress=lambda _: None):
    """Re-solve both sides on the current model; change only the declared restriction."""
    c = Config.from_dict({"plant": packet["plant"], "models": packet["models"]})
    components = assemble(c.plant, c.models)
    predictions = {}
    note = "Only the selected interval is restricted."
    for label, alternative in (
        ("Reference dispatch", None),
        (ALTERNATIVES[packet["alternative"]], packet["alternative"]),
    ):
        progress(f"Calculating {label}")
        forecast = copy.deepcopy(packet["forecast"])
        if alternative == "co2":
            deliveries = forecast.get("deliveries_kg", [])
            index = next((i for i, value in enumerate(deliveries) if value > 0), None)
            if index is None:
                note = "No CO₂ delivery occurs in this horizon; the alternative has no effect."
            else:
                quantity, deliveries[index] = deliveries[index], 0
                if index + 24 < len(deliveries):
                    deliveries[index + 24] += quantity
                    note = "The next delivery moves by 24 hours; later deliveries are unchanged."
                else:
                    note = "The next delivery moves 24 hours later, beyond this forecast horizon."
        if alternative == "reactor" and packet["state"]["reactor_on"]:
            note = "The reactor is already running; preventing a new start has no effect."
        prediction = plan(
            c.plant,
            State(**packet["state"]),
            forecast,
            packet["capacity_kw"],
            Costs(**packet["costs"]),
            packet["objective"],
            packet["seconds"],
            alternative=alternative,
            allow_fallback=False,
            minimum_ely=0 if alternative == "electrolyser" else packet["minimum_ely"],
            dependable_capacity=packet["dependable_capacity"],
            components=components,
            terminal_battery_value=packet["terminal_battery_value"],
        )
        predictions[label] = dict(
            information_id=packet["information_id"],
            predicted=prediction.get("predicted"),
            solver=prediction["solver"],
            points=series({"forecast": forecast, "plan": prediction}, packet["hour"]),
            basis="Current-model reference" if alternative is None else "Declared restriction",
        )
    from methane.provenance import LOADED_SOURCE

    if packet["alternative"] == "electrolyser" and packet["minimum_ely"]:
        note += " This deliberately suspends the selected interval's load probe."
    return dict(
        status="complete"
        if all(p["predicted"] is not None for p in predictions.values())
        else "incomplete",
        scope="Both sides are current-model predictions from the original estimate, forecast and frozen prices. Service commitments stay fixed. "
        + note,
        information_id=packet["information_id"],
        cost_version=packet["cost_version"],
        initial=packet["state"],
        forecast_source=packet["forecast"].get("source"),
        original_source=packet["original_source"],
        original_model_version=packet["original_model_version"],
        replanner_source_content_hash=LOADED_SOURCE["content_hash"],
        implementation=components.identities(),
        comparison_version="dispatch-lab/decision-alternative/1",
        terminal_battery_value=packet["terminal_battery_value"],
        predictions=predictions,
        order=list(predictions),
    )


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def selected(result, controller, hour):
    rows = result.get("records", {}).get(controller, ())
    if type(hour) is not int or not 0 <= hour < len(rows):
        raise ValueError("Recorded decision is unavailable for this selection")
    return rows[hour]


def series(decision, hour):
    """Compact, timed predictions only. Missing points stay missing."""
    forecast = decision.get("forecast", {})
    trajectory = decision.get("plan", {}).get("trajectory", ())
    actions = decision.get("plan", {}).get("actions", ())
    return [
        dict(
            hour=hour + i,
            time=forecast.get("times", [])[i] if i < len(forecast.get("times", [])) else None,
            pv_kw=pv,
            service_kw=forecast.get("service_kw", [0] * len(forecast["pv_kw"]))[i],
            deliveries_kg=forecast.get("deliveries_kg", [])[i]
            if i < len(forecast.get("deliveries_kg", []))
            else None,
            action=trajectory[i].get("applied", {})
            if i < len(trajectory)
            else actions[i]
            if i < len(actions)
            else {},
            state=trajectory[i].get("state", {}) if i < len(trajectory) else {},
            demand_kw=trajectory[i].get("demand_kw") if i < len(trajectory) else None,
        )
        for i, pv in enumerate(forecast.get("pv_kw", ()))
    ]


def prepare(result, controller, hour):
    """Construct a minimal worker packet using information available at the decision."""
    d = selected(result, controller, hour)["decision"]
    c = Config.from_dict(result.get("controller_config", result["config"]))
    p = Plant(**d["operating_plant"]) if d.get("operating_plant") else c.plant
    recovery = d.get("recovery_planning", {})
    if recovery.get("status") == "scheduled":
        raise ValueError(
            "This decision contains a conditional, multi-interval recovery test. "
            "Its recorded plan is available; a three-policy process fork cannot preserve "
            "that test's contingent constraints. Use the recorded recovery alternatives."
        )
    if not d.get("forecast", {}).get("pv_kw") or not d.get("estimate"):
        raise ValueError("Original forecast or starting estimate was not saved")
    probe = bool(d.get("probe"))
    if probe and d.get("probe_policy_revision", 0) < 2:
        raise ValueError("This older probe has no recorded dependable-capacity contract")
    packet = dict(
        schema_version=VERSION,
        plant=asdict(p),
        models=asdict(c.models),
        state=copy.deepcopy(d["estimate"]),
        forecast=copy.deepcopy(d["forecast"]),
        capacity_kw=d["capacity_used_kw"],
        costs=copy.deepcopy(result["config"]["costs"]),
        cost_version=d.get("cost_version", result.get("decision_cost_version")),
        seconds=c.scenario.solver_seconds,
        minimum_ely=d["capacity_used_kw"] if probe else 0,
        dependable_capacity=d["diagnosis"]["capacity_kw"] if probe else None,
        # A configured methane terminal allowance remains explicit, not a sale.
        terminal_battery_value=d.get("controller_policy", {}).get(
            "terminal_battery_value_kg_per_kwh", 0
        ),
        hour=hour,
        original_source=result.get("provenance", {}).get("source", {}).get("content_hash"),
        original_model_version=result.get("model_version"),
        original_components=copy.deepcopy(d.get("component_implementations")),
    )
    packet["information_id"] = digest(packet)
    return packet


def describe(result, controller, hour):
    row = selected(result, controller, hour)
    d = row["decision"]
    previous = selected(result, controller, hour - 1)["decision"] if hour else None
    points = series(d, hour)
    # Align by absolute hour AND timestamp. Different/missing vintages are not fabricated.
    prior = {p["hour"]: p for p in series(previous, hour - 1)} if previous else {}
    aligned = [
        prior.get(p["hour"])
        if p["time"] is not None and prior.get(p["hour"], {}).get("time") == p["time"]
        else None
        for p in points
    ]
    try:
        packet = prepare(result, controller, hour)
        comparison = dict(available=True, information_id=packet["information_id"], scope=SCOPE)
    except (ValueError, KeyError, TypeError) as exc:
        comparison = dict(available=False, reason=str(exc), scope=SCOPE)
    return copy.deepcopy(
        dict(
            status="available",
            schema_version=VERSION,
            controller=controller,
            hour=hour,
            interval=[hour, hour + 1],
            time=row.get("local_time", row.get("time")),
            estimate=d.get("estimate"),
            observations_before=d.get("observations"),
            observations_after=row.get("observations_after"),
            requested=row.get("requested"),
            applied=row.get("applied"),
            forced_trip=row.get("forced_trip"),
            unmet_action=row.get("unmet_action"),
            diagnosis_before=d.get("diagnosis"),
            diagnosis_after=row.get("diagnosis_after"),
            probe=d.get("probe"),
            recovery=d.get("recovery_planning"),
            recovery_loop=d.get("recovery_loop"),
            external_control=d.get("external_control"),
            objective=d.get("planning_objective", d.get("evidence", {}).get("objective")),
            evidence=d.get("evidence", {}),
            forecast_source=d.get("forecast", {}).get("source"),
            previous_forecast_source=previous.get("forecast", {}).get("source")
            if previous
            else None,
            points=points,
            previous=aligned,
            predicted=d.get("plan", {}).get("predicted"),
            solver=d.get("plan", {}).get("solver"),
            events=[e for e in result.get("events", {}).get(controller, ()) if e["hour"] == hour],
            comparison=comparison,
            original_model_version=result.get("model_version"),
            original_components=d.get("component_implementations"),
            cost_version=d.get("cost_version", result.get("decision_cost_version")),
        )
    )


def compare(packet, progress=lambda _: None):
    """All policies receive identical immutable operands; results never replace a run."""
    c = Config.from_dict({"plant": packet["plant"], "models": packet["models"]})
    components = assemble(c.plant, c.models)
    predictions = {}
    for label, objective in POLICIES.items():
        progress(f"Calculating {label} ({len(predictions) + 1} of 3)")
        prediction = plan(
            c.plant,
            State(**packet["state"]),
            copy.deepcopy(packet["forecast"]),
            packet["capacity_kw"],
            Costs(**packet["costs"]),
            objective,
            packet["seconds"],
            # The general fallback does not retain probe lower bounds.
            allow_fallback=not packet["minimum_ely"],
            minimum_ely=packet["minimum_ely"],
            dependable_capacity=packet["dependable_capacity"],
            components=components,
            terminal_battery_value=packet["terminal_battery_value"]
            if objective == "methane"
            else 0,
        )
        predictions[label] = dict(
            information_id=packet["information_id"],
            objective=objective,
            predicted=prediction.get("predicted"),
            solver=prediction["solver"],
            points=series({"forecast": packet["forecast"], "plan": prediction}, packet["hour"]),
            basis="Forecast rollout of a local rule"
            if objective == "greedy"
            else "Optimised horizon",
        )
    from methane.provenance import LOADED_SOURCE

    return dict(
        replanner_source_content_hash=LOADED_SOURCE["content_hash"],
        status="complete"
        if all(p["predicted"] is not None for p in predictions.values())
        else "incomplete",
        scope=SCOPE,
        information_id=packet["information_id"],
        cost_version=packet["cost_version"],
        original_source=packet["original_source"],
        original_model_version=packet["original_model_version"],
        implementation=components.identities(),
        comparison_version=VERSION,
        forecast_source=packet["forecast"].get("source"),
        initial=packet["state"],
        terminal_battery_value=packet["terminal_battery_value"],
        predictions=predictions,
        order=list(predictions),
    )
