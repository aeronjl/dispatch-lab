"""Conditional section treatment from public observations and registered work.

No executive, fault state, random ledger or successful-outcome receipt enters
this calculation. It reuses the execution surface/solar kernels, but its future
work is a hypothesis of uninterrupted continuation, never an observed effect.
"""

import copy
from dataclasses import asdict
from datetime import timedelta
from math import isfinite

from methane.forecast import IncompleteWeather
from methane.services.adapters import schedule
from methane.services.contracts import nonnegative
from methane.services.coupling import identity
from methane.services.surface import Patch, Surface
from methane.solar_model import interval, validate
from methane.timebase import utc

VERSION = "conditional-section-treatment/1"
ACTIONS = ("clean-section", "portable-clean-section")


def _surface(design, config, options, snapshot):
    result = Surface([s["capacity_kw"] for s in design["sections"]], config, options)
    if set(snapshot) != set(result.sections):
        raise ValueError("Observed surface must contain every current array section")
    for key, values in snapshot.items():
        patches = tuple(Patch(**p) for p in values)
        if (
            not patches
            or patches[0].start_m2 != 0
            or abs(patches[-1].end_m2 - result.sections[key][-1].end_m2) > 1e-8
            or any(a.end_m2 != b.start_m2 for a, b in zip(patches, patches[1:], strict=False))
        ):
            raise ValueError("Observed patches must partition the declared section area")
        result.sections[key] = patches
    return result


def project(
    plant,
    weather,
    design,
    config,
    options,
    snapshot,
    forecast,
    commitments,
    *,
    brush_remaining_m2,
    observed_treatments=(),
    stop_work_at=None,
):
    """Predict available DC and loss breakdown for declared remaining cleaning.

    ``forecast`` is the saved *reference* PV/radiation forecast, before section
    conversion. Current surface is an explicitly ideal observation in this
    fixture. A partly executed pass needs its recorded earlier treatment to
    recover its frozen brush efficacy; it cannot be inferred from later truth.
    Remaining brush is current measured allowance, with no future replacement
    credit. Portable water, electricity, access and shared resource feasibility
    are checked separately by the service executive/demand projection.
    """
    nonnegative(brush_remaining_m2, "current brush allowance")
    design = validate(design)
    now = forecast.get("decision_hour")
    nonnegative(now, "forecast decision hour")
    if now != int(now):
        raise ValueError("Cleaning forecasts require an hourly decision boundary")
    n = len(forecast.get("times", ()))
    if not n or any(
        len(forecast.get(k, ())) != n for k in ("source_samples", "pv_kw", "ambient_c")
    ):
        raise IncompleteWeather(
            "Cleaning prediction needs every saved radiation/reference interval"
        )
    clock = utc(forecast["times"][0])
    if (
        clock.minute
        or clock.second
        or clock.microsecond
        or any(utc(t) != clock + timedelta(hours=i) for i, t in enumerate(forecast["times"]))
    ):
        raise ValueError("Cleaning forecast times must be consecutive UTC hourly boundaries")
    source = forecast.get("source", {})
    if (
        not source.get("id")
        or not source.get("initialized_at")
        or not source.get("available_at")
        or not utc(source["initialized_at"]) <= utc(source["available_at"]) <= clock
    ):
        raise ValueError("Cleaning forecast must identify an eligible saved issue")
    for i, sample in enumerate(forecast["source_samples"]):
        for key, value in (
            ("irradiance_wm2", sample.get("irradiance_wm2")),
            ("pv_kw", forecast["pv_kw"][i]),
            ("ambient_c", forecast["ambient_c"][i]),
        ):
            if (
                isinstance(value, bool)
                or not isinstance(value, (int, float))
                or not isfinite(value)
            ):
                raise IncompleteWeather("Missing finite cleaning forecast input: " + key)
            if key != "ambient_c" and value < 0:
                raise ValueError("Radiation and reference power must be nonnegative")
    commitments = tuple(commitments)
    stop_work_at = dict(stop_work_at or {})
    if set(stop_work_at) - {c.plan.order.order_id for c in commitments} or any(
        not isfinite(v) or v < now for v in stop_work_at.values()
    ):
        raise ValueError("Conditional interruption must name current work and a future boundary")
    if len({c.plan.order.order_id for c in commitments}) != len(commitments):
        raise ValueError("A cleaning commitment cannot appear twice")
    treatments = tuple(copy.deepcopy(observed_treatments))
    previous = {}
    for event in treatments:
        if event["completed_at"] > now or event["effective_at"] > now:
            raise ValueError("A treatment observation is unavailable at this decision")
        key = event["order_id"]
        if key in previous and previous[key]["efficacy_start"] != event["efficacy_start"]:
            raise ValueError("Recorded pass efficacy must stay fixed within an order")
        if (
            event["efficacy_start"] != event["efficacy_end"]
            or not 0 <= event["efficacy_start"] <= 1
        ):
            raise ValueError("The current execution model requires a constant pass efficacy")
        if key not in previous or event["completed_at"] > previous[key]["completed_at"]:
            previous[key] = event
    surface = _surface(design, config, options, snapshot)
    untreated = _surface(design, config, options, snapshot)
    passes = []
    for commitment in commitments:
        plan = commitment.plan
        if plan.context.at_hour > now:
            raise ValueError("A mission contains future decision information")
        if plan.order.action not in ACTIONS:
            continue
        stages = schedule(plan)
        if commitment.stage_index >= len(stages):
            raise ValueError("Invalid observed execution cursor")
        begin, end, _ = stages[commitment.stage_index]
        if now >= end or (commitment.stage_index > 0 and now < begin):
            raise ValueError("Cleaning cursor does not belong to the current decision")
        if (commitment.entered and now < begin) or (not commitment.entered and now > begin):
            raise ValueError("Cleaning stage entry disagrees with its observed cursor")
        section = plan.interface.target_asset_id
        if section not in surface.sections:
            raise ValueError("Cleaning mission targets an absent surface section")
        for index, (a, b, stage) in enumerate(stages):
            if (
                index < commitment.stage_index
                or stage.phase != "perform"
                or not stage.effect
                or b <= now
            ):
                continue
            portable = plan.order.action == "portable-clean-section"
            rate = options.portable_area_m2ph if portable else options.cleaning_area_m2ph
            if plan.timing:
                rate = surface.section(section)["area_m2"] / (b - a)
            if abs((b - a) * rate - surface.section(section)["area_m2"]) > 1e-6:
                raise ValueError("Cleaning duration/rate does not cover its declared section")
            observed = previous.get(plan.order.order_id)
            if a < now and observed is None:
                raise ValueError("An ongoing pass needs its original observed efficacy")
            if (
                observed is not None
                and not plan.timing
                and (
                    observed["section"] != section
                    or observed["started_at"] < a - 1e-8
                    or abs(observed["end_m2"] - (min(now, b) - a) * rate) > 1e-6
                )
            ):
                raise ValueError("Observed treatment does not match this pass and boundary")
            area_offset = 0
            if plan.timing and observed is not None:
                if (
                    observed["section"] != section
                    or not 0 <= observed["end_m2"] <= surface.section(section)["area_m2"]
                ):
                    raise ValueError("Observed coverage does not belong to the declared section")
                area_offset = observed["end_m2"]
                a = now
                rate = (surface.section(section)["area_m2"] - area_offset) / (b - now)
            passes.append(
                dict(
                    order_id=plan.order.order_id,
                    section=section,
                    start=a,
                    end=min(b, stop_work_at.get(plan.order.order_id, b)),
                    rate=rate,
                    area_offset=area_offset,
                    portable=portable,
                    efficacy=observed["efficacy_start"] if observed else None,
                )
            )
    for i, a in enumerate(passes):
        for b in passes[i + 1 :]:
            if a["section"] == b["section"] and max(now, a["start"], b["start"]) < min(
                a["end"], b["end"]
            ):
                raise ValueError("Two cleaning passes cannot occupy the same section")
    passes.sort(key=lambda p: (p["start"], p["order_id"]))
    inputs = dict(
        plant=asdict(plant),
        weather=asdict(weather),
        design=design,
        config=asdict(config),
        options=asdict(options),
        observed_surface=snapshot,
        forecast=forecast,
        commitments=[
            dict(plan=c.plan.to_dict(), stage_index=c.stage_index, entered=c.entered)
            for c in commitments
        ],
        brush_remaining_m2=brush_remaining_m2,
        observed_treatments=treatments,
        **(dict(stop_work_at=stop_work_at) if stop_work_at else {}),
    )
    rows, operations, brush = [], [], float(brush_remaining_m2)
    for i, time in enumerate(forecast["times"]):
        sample = {
            **forecast["source_samples"][i],
            "pv_kw": forecast["pv_kw"][i],
            "ambient_c": forecast["ambient_c"][i],
        }
        active = interval(surface.design(design), sample, time, plant, weather)
        baseline = interval(untreated.design(design), sample, time, plant, weather)
        row = dict(
            offset=i,
            hour=now + i,
            time=time,
            before=surface.snapshot(),
            predicted=active,
            no_further_cleaning=baseline,
            available_dc_change_kw=active["output_kw"] - baseline["output_kw"],
        )
        for work in passes:
            a, b = max(now + i, work["start"]), min(now + i + 1, work["end"])
            if b <= a:
                continue
            area = (b - a) * work["rate"]
            if work["efficacy"] is None:
                work["efficacy"] = (
                    options.portable_loose_removal
                    if work["portable"]
                    else config.cleaning_removal_fraction * brush / options.brush_life_m2
                )
            if not work["portable"]:
                brush -= area
                if brush < -1e-7:
                    raise ValueError(
                        "Future cleaning exceeds observed brush allowance; no replacement credit"
                    )
            efficacy = work["efficacy"]
            event = surface.clean(
                dict(
                    order_id=work["order_id"],
                    section=work["section"],
                    start_m2=work["area_offset"] + (a - work["start"]) * work["rate"],
                    end_m2=min(
                        surface.section(work["section"])["area_m2"],
                        work["area_offset"] + (b - work["start"]) * work["rate"],
                    ),
                    efficacy_start=efficacy,
                    efficacy_end=efficacy,
                    started_at=a,
                    completed_at=b,
                    effective_at=now + i + 1,
                    method="portable-" + options.portable_cleaner
                    if work["portable"]
                    else "dry-brush",
                    adhered_removal=options.portable_adhered_removal
                    if work["portable"] and options.portable_cleaner == "wet"
                    else 0,
                )
            )
            operations.append(event)
        surface.advance(1)
        untreated.advance(1)
        row.update(after=surface.snapshot(), brush_after_m2=max(0, brush))
        rows.append(row)
    return dict(
        implementation_id=VERSION,
        input_id=identity(inputs),
        inputs=copy.deepcopy(inputs),
        context="prediction",
        rows=rows,
        predicted_treatments=operations,
        ending_surface=surface.snapshot(),
        ending_brush_m2=max(0, brush),
        scope="Conditional uninterrupted continuation of declared cleaning. Ideal current surface observation; past pass efficacy must be recorded. No future repair, brush replacement, rain washing or successful-return evidence is assumed. Solar conversion includes temperature and clipping; plant curtailment and methane value require a separate coupled dispatch calculation. No probability or empirical efficacy validation is implied.",
    )
