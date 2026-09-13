"""Joint work/charging/process decisions over explicit public uncertainty.

Candidate recipes and safety reservations remain bounded by the full duration
support. Expected use and possible treatment effects are separate predictions.
No execution port or future support timetable is accepted here.
"""

import copy
import math
from dataclasses import replace
from time import perf_counter

from methane.cancellation import checkpoint
from methane.services.adapters import schedule
from methane.services.charging import Inputs
from methane.services.scenario_planning import Branch, solve
from methane.services.snapshot import RecordedServices, capture
from methane.services.uncertain_timing import GROUPS, envelope, group, scaled, stage_from_dict

VERSION = "uncertain-service-process-planning/1"


def nominal_only(options, runtime, belief):
    """A true null model has neither duration, weather nor completion uncertainty.

    Reuse the validated nominal solve, including its recovery outcome tree. Do
    not spend another time-limited solve choosing among equivalent optima.
    """
    return (
        all(pair == [1, 1] for pair in options["duration_bounds"].values())
        and options["weather_factors"] == [1]
        and not options["terminal_minimum"]
        and runtime.config.mission_failure_probability == 0
        and all(v["interrupted"] == 0 for v in belief["reliability"].values())
    )


def quantile(belief, q, elapsed=0):
    """Inverse CDF of a uniform mixture, including overlapping intervals/atoms."""
    if not 0 <= q <= 1:
        raise ValueError("Quantile must lie between zero and one")
    elapsed = max(elapsed, belief.get("minimum_elapsed_factor", 0))
    bins, weights = belief["bins"], belief["weights"]

    def cdf(x):
        return sum(
            w * (max(0, min(1, (x - a) / (b - a))) if b > a else float(x >= b))
            for (a, b), w in zip(bins, weights, strict=True)
        )

    initial = cdf(elapsed)
    if 1 - initial <= 1e-12:
        raise ValueError("Unfinished work is outside the duration belief support")
    target = initial + q * (1 - initial)
    lo, hi = elapsed, max(b for _, b in bins)
    for _ in range(64):
        middle = (lo + hi) / 2
        if cdf(middle) >= target:
            hi = middle
        else:
            lo = middle
    return hi


def prediction(plan, belief, q, now, cursor=0, entered=False):
    if plan.timing is None:
        plan = envelope(plan, belief["options"]["duration_bounds"])
    nominal = (
        [stage_from_dict(s) for s in plan.timing["nominal_stages"]]
        if plan.timing
        else list(plan.stages)
    )
    slots = schedule(plan)
    stages = []
    for i, raw in enumerate(nominal):
        if i < cursor:
            stages.append(plan.stages[i])
            continue
        key = group(plan, raw)
        elapsed = max(0, now - slots[i][0]) / raw.duration_hours if i == cursor and entered else 0
        from methane.duration_population import for_plan

        factor = quantile(for_plan(belief, plan, key), q, elapsed) if key else 1
        stages.append(scaled(raw, factor))
    return replace(plan, stages=tuple(stages))


def information_histories(profiles, error):
    """Conservative distinguishability from the *previous* observed power.

    Overlapping bounded measurement intervals share a history (transitively).
    Distinct histories cannot merge. Service timing is never revealed by a label.
    """
    n = len(profiles[0]["pv_kw"])
    histories = [["initial"] for _ in profiles]
    for t in range(1, n):
        parent = list(range(len(profiles)))

        def root(i, parent=parent):
            while parent[i] != i:
                i = parent[i]
            return i

        for i, a in enumerate(profiles):
            x = a["pv_kw"][t - 1]
            for j, b in enumerate(profiles[:i]):
                y = b["pv_kw"][t - 1]
                # Do not merge different earlier information. A zero/low signal
                # cannot identify a multiplicative weather regime.
                if (
                    histories[i][-1] == histories[j][-1]
                    and abs(x - y) <= error * (abs(x) + abs(y)) + 1e-8
                ):
                    parent[root(i)] = root(j)
        for i in range(len(profiles)):
            histories[i].append(histories[i][-1] + f"/{t}:{root(i)}")
    return histories


def interruption_histories(histories, metadata, at_hour):
    """Retain who interrupted and when it was observed: histories have memory."""
    result = copy.deepcopy(histories)
    for i, meta in enumerate(metadata):
        for order_id, at in sorted(meta.get("stop_work_at", {}).items()):
            boundary = math.ceil(at - 1e-9)
            for t in range(len(result[i])):
                if at_hour + t >= boundary:
                    result[i][t] += f"/reported-interruption:{order_id}@{boundary}"
    return result


def evaluate(runtime, plant, state, forecast, capacity_kw, costs, targets, **kwargs):
    from methane.services import charge_control
    from methane.services.coupling import evaluate as project
    from methane.services.coupling import identity

    started = perf_counter()
    seconds = kwargs.get("seconds", 0.5)
    # The existing port builds and verifies the current finite-resource recipe,
    # charging obligations and any accepted recovery-test window.
    baseline = charge_control.evaluate(
        runtime,
        plant,
        state,
        forecast,
        capacity_kw,
        costs,
        targets,
        **{**kwargs, "seconds": max(0.01, seconds * 0.35), "uncertain": False},
    )
    if baseline["state"] != "feasible":
        baseline["uncertainty_planning"] = dict(
            version=VERSION,
            status="unresolved",
            reason="No validated resource/charging baseline",
            assumptions=copy.deepcopy(runtime.autonomy),
        )
        return baseline
    options, belief = runtime.autonomy, runtime.belief_record
    if belief is None:
        raise ValueError("Uncertainty planning requires recorded current beliefs")
    belief = copy.deepcopy(belief)
    if options["mode"] == "fixed" and "duration_model" not in options:
        for item in belief["durations"].values():
            item["weights"] = [1 / len(item["bins"])] * len(item["bins"])
        belief["reliability"] = {}
    solar = (belief.get("performance") or {}).get("solar") or {}
    contradicted = [
        asset + "/" + key
        for asset, groups in belief.get("equipment_durations", {}).items()
        for key, item in groups.items()
        if item.get("unsupported")
    ]
    if contradicted and options["mode"] != "fixed":
        baseline.update(state="unresolved", current_requests=[])
        baseline["uncertainty_planning"] = dict(
            version=VERSION,
            status="model-inadequacy",
            assumptions=copy.deepcopy(options),
            reason="Observed duration contradicts the equipment/job model: "
            + ", ".join(contradicted),
        )
        return baseline
    if (
        options["mode"] != "fixed"
        and "feasible_multiplier_interval" in solar
        and solar["feasible_multiplier_interval"] is None
    ):
        baseline.update(state="unresolved", current_requests=[])
        baseline["uncertainty_planning"] = dict(
            version=VERSION,
            status="model-inadequacy",
            reason=solar["model_evidence"],
            assumptions=copy.deepcopy(options),
        )
        baseline["constraints"].append(
            dict(condition="unexplained reference observations", reason=solar["model_evidence"])
        )
        return baseline
    if nominal_only(options, runtime, belief):
        baseline["uncertainty_planning"] = dict(
            version=VERSION,
            status="canonical-nominal",
            assumptions=copy.deepcopy(options),
            belief_id=identity(belief),
            reason="All duration factors and weather factors are one, interruption probability is zero, and no additional terminal constraint is requested. Reused the validated nominal candidate and its recovery tree.",
            hypotheses=[],
            outcome={},
        )
        return baseline
    selected = kwargs.get("selections", ())
    visits = kwargs.get("visit_groups", ())
    frozen = capture(runtime)
    profiles, metadata = [], []
    # Two common quantiles explicitly describe a shared slow/fast service regime.
    # This dependence assumption is recorded; it is not inferred from marginal fits.
    qs = (0.25, 0.75) if options["mode"] == "risk-aware" else (0.5,)
    weather = (
        list(zip(options["weather_factors"], options["weather_weights"], strict=True))
        if options["mode"] == "risk-aware"
        else [(1.0, 1.0)]
    )
    for q in qs:
        for multiplier, weight in weather:
            checkpoint()
            clone = RecordedServices(frozen["snapshot"], frozen["catalogue"])
            clone.duration_envelope = lambda p, q=q, clone=clone: prediction(
                p, belief, q, clone.executive.at_hour
            )
            for mission in clone.executive.missions.values():
                if mission.status in ("scheduled", "active"):
                    mission.plan = prediction(
                        mission.plan,
                        belief,
                        q,
                        clone.executive.at_hour,
                        mission.stage_index,
                        mission.entered,
                    )
            factors = {key: quantile(belief["durations"][key], q) for key in GROUPS}
            clone.options = replace(
                clone.options,
                cleaning_area_m2ph=clone.options.cleaning_area_m2ph / factors["cleaning"],
                portable_area_m2ph=clone.options.portable_area_m2ph / factors["cleaning"],
            )
            # A visit keeps its full support envelope; variable within-visit timing
            # still affects physical execution, observation and actual cost.
            if visits:
                clone.duration_envelope = runtime.duration_envelope
            try:
                candidate = project(
                    clone,
                    plant,
                    state,
                    forecast,
                    capacity_kw,
                    costs,
                    selected,
                    project_only=True,
                    objective=kwargs.get("objective", "methane"),
                    service_prices=kwargs["service_prices"],
                    recorded_prefix=kwargs.get("recorded_prefix", ()),
                    reference_forecast=kwargs.get("reference_forecast"),
                    visit_groups=visits,
                )
                if candidate["state"] != "projected":
                    raise ValueError(str(candidate["constraints"]))
            except ValueError as exc:
                baseline.update(state="unresolved", current_requests=[])
                baseline["uncertainty_planning"] = dict(
                    version=VERSION,
                    status="unresolved",
                    reason=str(exc),
                    assumptions=copy.deepcopy(options),
                )
                return baseline
            f = copy.deepcopy(candidate["forecast"])
            f["pv_kw"] = [
                v if i == 0 else min(plant.solar_kw, v * multiplier)
                for i, v in enumerate(f["pv_kw"])
            ]
            known = baseline["demand"]["forecast"]
            for key, default in (
                ("pv_kw", 0),
                ("service_kw", 0),
                ("electrolyser_isolated", False),
                ("ambient_c", 20),
                ("deliveries_kg", 0),
            ):
                f.setdefault(key, [default] * len(f["pv_kw"]))
                f[key][0] = known.get(key, [default] * len(f["pv_kw"]))[0]
            profiles.append(f)
            metadata.append(
                dict(
                    service_quantile=q,
                    duration_factors=factors,
                    weather_factor=multiplier,
                    weight=weight / len(qs),
                    service_cost_eur=candidate["service_pricing"]["incremental_decision_eur"],
                    projection=candidate["projection"],
                )
            )
    # Add a mechanically bounded interrupted-cleaning branch. Covered material
    # remains treated; no successful return or downstream repair is inferred.
    if options["mode"] == "risk-aware" and runtime.optical:
        from methane.services.coupling import _treatment

        original_profiles, original_metadata = profiles, metadata
        profiles, metadata = [], []
        for f, meta in zip(original_profiles, original_metadata, strict=True):
            clone = RecordedServices(frozen["snapshot"], frozen["catalogue"])
            q = meta["service_quantile"]
            clone.duration_envelope = lambda p, q=q, clone=clone: prediction(
                p, belief, q, clone.executive.at_hour
            )
            for mission in clone.executive.missions.values():
                if mission.status in ("scheduled", "active"):
                    mission.plan = prediction(
                        mission.plan,
                        belief,
                        q,
                        clone.executive.at_hour,
                        mission.stage_index,
                        mission.entered,
                    )
            additions = [clone.propose(key, starting_at=start)[0] for key, start in selected]
            jobs = additions + [
                m.plan
                for m in clone.executive.missions.values()
                if m.status in ("scheduled", "active")
            ]
            stops, robots, failure_probabilities = {}, set(), []
            for p in jobs:
                if p.order.action != "clean-section":
                    continue
                a, b, _ = next((a, b, stage) for a, b, stage in schedule(p) if stage.effect)
                at = a + (b - a) * runtime.options.work_failure_fraction
                if at < runtime.executive.at_hour:
                    continue
                stops[p.order.order_id] = at
                robots.add(p.asset.asset_id)
                estimate = belief["reliability"].get("cleaning")
                failure_probabilities.append(
                    1 - estimate["mean_completion_probability"]
                    if estimate
                    else runtime.config.mission_failure_probability
                )
            probability = min(1, sum(failure_probabilities))
            if not stops or probability <= 0:
                profiles.append(f)
                metadata.append(meta)
                continue
            if probability < 1:
                profiles.append(f)
                metadata.append(
                    {
                        **meta,
                        "weight": meta["weight"] * (1 - probability),
                        "service_outcome": "continued cleaning",
                    }
                )
            interrupted, _ = _treatment(
                clone, forecast, kwargs["reference_forecast"], additions, stops
            )
            interrupted["pv_kw"] = [
                f["pv_kw"][0] if i == 0 else min(plant.solar_kw, v * meta["weather_factor"])
                for i, v in enumerate(interrupted["pv_kw"])
            ]
            # Retain the reserved utility and cost envelope, including resources
            # held for return. It is a conservative budget, not invented usage.
            interrupted.update(
                service_kw=list(f["service_kw"]),
                electrolyser_isolated=list(f["electrolyser_isolated"]),
            )
            profiles.append(interrupted)
            metadata.append(
                {
                    **meta,
                    "weight": meta["weight"] * probability,
                    "service_outcome": "interrupted cleaning",
                    "stop_work_at": stops,
                    "stranded_assets": sorted(robots),
                    "failure_weight_basis": "Union-bound mission interruption allowance; simultaneous interruption is a conservative stress assumption, not a calibrated joint event distribution",
                }
            )
    histories = information_histories(profiles, options["solar_relative_error"])
    # Distinguish a reported interruption only after its physical interval.
    histories = interruption_histories(histories, metadata, runtime.executive.at_hour)

    charge_inputs = None
    if baseline.get("charging"):
        inputs = baseline["charging"]["inputs"]
        if "charging" in inputs:
            charge_inputs = Inputs.from_dict(inputs["charging"])
        else:
            charge_inputs = Inputs.from_dict(
                dict(
                    batteries=inputs["batteries"],
                    dock_available_kw=inputs["dock_available_kw"],
                    incremental_cost_by_active_hours=inputs["incremental_cost_by_active_hours"],
                )
            )
    if charge_inputs:
        from methane.services.core import ASSETS

        batteries = []
        for battery in charge_inputs.batteries:
            interruptions = [
                min(m["stop_work_at"].values())
                for m in metadata
                if ASSETS.get(battery.name) in m.get("stranded_assets", ())
            ]
            if interruptions:
                boundary = math.ceil(min(interruptions) - runtime.executive.at_hour - 1e-9)
                battery = replace(
                    battery,
                    available=tuple(v and t < boundary for t, v in enumerate(battery.available)),
                )
            batteries.append(battery)
        charge_inputs = replace(charge_inputs, batteries=tuple(batteries))
    original_recovery = baseline.get("recovery_planning")
    recovery = (
        original_recovery.get("plan", {}).get("recovery_outcomes") if original_recovery else None
    )
    recoveries = recovery["branches"] if recovery else [None]
    branches = []
    for i, (f, m, h) in enumerate(zip(profiles, metadata, histories, strict=True)):
        for j, r in enumerate(recoveries):
            branches.append(
                Branch.create(
                    f"weather-service-{i}/delivery-{j}",
                    m["weight"] * (r["probability"] if r else 1),
                    baseline["demand"]["forecast"],
                    h,
                    source=options["source"],
                    service_cost_eur=m["service_cost_eur"],
                    delivery_capacity_kw=r["delivery_capacity_kw"] if r else None,
                    hypothesis_forecast=f,
                )
            )
    remaining = seconds - (perf_counter() - started)
    if remaining <= 0:
        outcome = dict(
            status="unresolved", solver=dict(status="comparison-budget", valid_incumbent=False)
        )
    else:
        terminal = dict(options["terminal_minimum"])
        if recovery:
            for k, v in recovery["terminal_minimum"].items():
                terminal[k] = max(terminal.get(k, 0), v)
        outcome = solve(
            plant,
            state,
            branches,
            capacity_kw,
            costs,
            objective=kwargs.get("objective", "methane"),
            risk_weight=options["risk_weight"] if options["mode"] == "risk-aware" else 0,
            seconds=remaining,
            components=kwargs.get("components"),
            alternative=kwargs.get("alternative"),
            terminal_minimum=terminal,
            terminal_battery_value=kwargs.get("terminal_battery_value", 0),
            charging_inputs=charge_inputs,
            requested_minimum=recovery["requested_minimum"] if recovery else None,
            requested_maximum=recovery["requested_maximum"] if recovery else None,
        )
    baseline["uncertainty_planning"] = dict(
        version=VERSION,
        status=outcome["status"],
        assumptions=copy.deepcopy(options),
        belief_id=identity(belief),
        hypotheses=metadata,
        outcome=outcome,
        scope="Full public support reserves resources. Within-support use/cleaning and weather regimes are predictions; no repair success is credited. Two common duration quantiles impose an explicitly assumed shared slow/fast regime. Future observed power distinguishes only nonoverlapping error intervals, one decision later. Service timing does not reveal the branch. Charging obligations use conservative reserved consumption; this is bounded candidate search, not fleet optimality.",
    )
    if outcome["status"] != "feasible":
        baseline.update(state="unresolved", current_requests=[])
        baseline["constraints"].append(
            dict(condition="joint uncertainty solve", reason=outcome["solver"]["status"])
        )
        return baseline
    selected_branch = min(
        outcome["branches"],
        key=lambda r: abs(
            metadata[int(r["branch_id"].split("/")[0].split("-")[-1])]["weather_factor"] - 1
        ),
    )
    process = dict(
        actions=selected_branch["requested_actions"],
        trajectory=selected_branch["trajectory"],
        predicted=selected_branch["predicted"],
        solver=outcome["solver"],
    )
    baseline.update(
        state="feasible",
        score=outcome["solver"]["objective_value"],
        process_plan=process,
        forecast=copy.deepcopy(selected_branch["forecast"]),
    )
    fleet = selected_branch.get("charging_plan")
    if fleet:
        baseline["current_requests"] = [
            dict(robot=r["robot"], power_kw=r["requested_kw"])
            for r in fleet["charging"]
            if r["offset"] == 0 and r["requested_kw"] > 0
        ]
        baseline["charging"].update(
            status="feasible",
            solver=outcome["solver"],
            plan={**process, **fleet, "forecast": baseline["forecast"]},
        )
    if original_recovery:
        original_recovery["plan"] = {
            **process,
            **(fleet or {}),
            "forecast": baseline["forecast"],
            "recovery_outcomes": outcome,
        }
    baseline["input_key"] = identity(
        dict(
            original=baseline.get("input_key", baseline["demand"]["input_key"]),
            uncertainty=baseline["uncertainty_planning"],
        )
    )
    return baseline
