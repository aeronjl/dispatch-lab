"""Prepared contact readers and observation-only interpretation.

The sampling adapter accepts private signal operands; classify/evidence/policy
accept only measurements and declared thresholds. No physical repair result or
future fault schedule is passed to the supervisor.
"""

import hashlib
from math import sqrt

from methane.services.contracts import Reading, available_boundary

VERSION = "referenced-contact/1"
KINDS = ("inspection", "inspection-confirm")
SCOPE = "Reader references test the acquisition path. Both readers share one contact; agreement cannot exclude a common stuck contact or establish module health."


def classify(signal, zero, span, options):
    if any(v is None for v in (signal, zero, span)):
        return dict(
            value=None,
            quality="unavailable",
            reason="Reader did not return a complete measurement",
            corrected_v=None,
            offset_v=zero,
            reference_ok=None,
        )
    difference = span - zero
    valid = (
        abs(zero) <= options.inspection_zero_limit_v
        and abs(difference - 24) <= 24 * options.inspection_span_tolerance_fraction
    )
    corrected = 24 * (signal - zero) / difference if difference > 0 else None
    if not valid:
        return dict(
            value=None,
            quality="uncertain",
            reason="Reader reference inconsistent; channel isolated for this decision",
            corrected_v=corrected,
            offset_v=zero,
            reference_ok=False,
        )
    value = (
        False
        if corrected <= options.inspection_low_v
        else True
        if corrected >= options.inspection_high_v
        else None
    )
    return dict(
        value=value,
        quality="usable" if value is not None else "uncertain",
        reason="Contact voltage within a declared band"
        if value is not None
        else "Contact voltage between decision bands",
        corrected_v=corrected,
        offset_v=zero,
        reference_ok=True,
    )


def noise(seed, reader, measured_at, channel, sigma):
    # Independent bounded uniform draws with the declared standard deviation.
    key = f"{VERSION}/{seed}/{reader}/{measured_at:.12g}/{channel}"
    u = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64
    return (2 * u - 1) * sqrt(3) * sigma


def sample(physical, reader, completed, order_id, seed, options):
    source = f"{VERSION}/{reader}/{order_id}"
    available = available_boundary(completed + options.inspection_delay_hours)
    errors = {
        key: noise(seed, reader, completed, key, options.inspection_noise_v)
        for key in ("signal", "zero", "span")
    }
    raw = {
        key: None if physical["dropout"] else base + physical["offset_v"] + errors[key]
        for key, base in (("signal", physical["signal_v"]), ("zero", 0), ("span", 24))
    }
    decision = classify(raw["signal"], raw["zero"], raw["span"], options)
    readings = tuple(
        Reading(
            f"contact-{key}:{reader}",
            value,
            "V",
            completed,
            available,
            source,
            "usable" if value is not None else "unavailable",
        )
        for key, value in raw.items()
    )
    readings += (
        Reading(
            "trip-contact:" + reader,
            decision["value"],
            "boolean",
            completed,
            available,
            source,
            decision["quality"],
        ),
    )
    # The separate retrospective record is never returned by the public executive.
    trace = dict(
        model=VERSION,
        reader=reader,
        order_id=order_id,
        measured_at=completed,
        available_at=available,
        physical=physical,
        noise_v=errors,
        raw_v=raw,
        interpretation=decision,
    )
    return readings, trace


def evidence(context, options, orders, *, commissioned_only=False):
    if type(commissioned_only) is not bool:
        raise ValueError("Reader commissioning mode must be Boolean")
    change = context.latest("contact-evidence-cutoff")
    cutoff = change.value if change is not None and change.quality == "usable" else None
    work = [q for q in orders if q["kind"] in KINDS]
    if work:
        incident = max(work, key=lambda q: q["created_hour"])["incident"]
        work = [q for q in work if q["incident"] == incident]
    names = (
        ("fixed", "mobile")
        if options.inspector == "both"
        else (options.inspector,)
        if options.inspector != "none"
        else ()
    )
    if options.inspection_interface == "enclosed-contact":
        names = ()

    def reader_for(order):
        return order.get(
            "reader",
            "fixed"
            if options.inspector in ("fixed", "both") and order["kind"] == "inspection"
            else "mobile",
        )

    if commissioned_only:
        requested = {reader_for(q) for q in work}
        names = tuple(name for name in names if name in requested)
    channels = []
    for reader in names:
        ids = {
            q["id"]
            for q in work
            if (
                reader_for(q)
                if commissioned_only
                else q.get("reader", "fixed" if options.inspector == "fixed" else "mobile")
            )
            == reader
        }
        packets = [
            r
            for r in context.readings
            if r.channel == "contact-signal:" + reader and r.source_id.rsplit("/", 1)[-1] in ids
        ]
        signal = max(packets, key=lambda r: (r.measured_at, r.available_at), default=None)
        if signal is None:
            channels.append(
                dict(
                    reader=reader,
                    quality="missing",
                    value=None,
                    reason="Awaiting eligible measurement",
                )
            )
            continue
        packet = {
            r.channel.split(":")[0].removeprefix("contact-"): r.value
            for r in context.readings
            if r.source_id == signal.source_id
            and r.measured_at == signal.measured_at
            and r.channel.startswith("contact-")
        }
        result = classify(packet.get("signal"), packet.get("zero"), packet.get("span"), options)
        result["acquisition_quality"] = result["quality"]
        if cutoff is not None and signal.measured_at <= cutoff:
            result.update(
                value=None,
                quality="stale",
                reason="Contact sample predates a recorded intervention; current contact state is unverified",
            )
        elif context.at_hour - signal.measured_at > options.contact_max_age_hours:
            result.update(
                value=None,
                quality="stale",
                reason="Measurement older than the declared evidence limit",
            )
        channels.append(
            dict(
                reader=reader,
                **result,
                raw_v=packet,
                measured_at=signal.measured_at,
                available_at=signal.available_at,
                source_id=signal.source_id,
            )
        )
    valid = [c for c in channels if c["quality"] == "usable"]
    ambiguous_voltage = any(
        c["quality"] == "uncertain" and c.get("reference_ok") is True for c in channels
    )
    pending = ambiguous_voltage or any(c["quality"] in ("missing", "stale") for c in channels)
    agree = bool(valid) and all(c["value"] == valid[0]["value"] for c in valid)
    usable = agree and not pending
    reason = (
        "Contact voltage between decision bands; reset evidence is ambiguous"
        if ambiguous_voltage
        else "Awaiting current reader evidence"
        if pending or not channels
        else "Readers disagree; reset evidence is ambiguous"
        if valid and not agree
        else "No usable contact channel"
        if not valid
        else "Contact evidence supported by " + ", ".join(c["reader"] for c in valid)
    )
    return dict(
        model="commissioned-contact-evidence/1" if commissioned_only else VERSION,
        at_hour=context.at_hour,
        invalidated_through_hour=cutoff,
        quality="usable" if usable else "uncertain",
        value=valid[0]["value"] if usable else None,
        reason=reason,
        channels=channels,
        isolated_readers=[
            c["reader"]
            for c in channels
            if c.get("reference_ok") is False or c.get("acquisition_quality") == "unavailable"
        ],
        scope=SCOPE
        + (
            " Only explicitly commissioned readers contribute; all commissioned current-incident readers must settle before a reset is permitted."
            if commissioned_only
            else ""
        ),
    )


def reading(report):
    measured = min(
        (c["measured_at"] for c in report["channels"] if c["quality"] == "usable"),
        default=report["at_hour"],
    )
    return Reading(
        "trip-contact",
        report["value"],
        "boolean",
        measured,
        report["at_hour"],
        report["model"] + "/evidence",
        report["quality"],
    )


def policy(runtime, hour, diagnosis):
    """Finite local investigation; no claim of optimal information gathering."""
    if not diagnosis.active_incident or diagnosis.capacity_kw >= runtime.nameplate_kw * 0.95:
        return
    o, incident = runtime.options, diagnosis.incidents
    readers = (
        ("fixed", "mobile")
        if o.inspector == "both"
        else (o.inspector,)
        if o.inspector != "none"
        else ()
    )
    if o.inspection_interface == "enclosed-contact":
        readers = ()  # Known incompatibility selects another compatible procedure.
    for i, reader in enumerate(readers):
        runtime._queue(
            KINDS[i],
            hour,
            incident,
            "Observed electrical shortfall; acquire referenced contact evidence",
            reader=reader,
        )
    work = [q for q in runtime.orders if q["kind"] in KINDS and q["incident"] == incident]
    report = evidence(runtime._context, o, work)
    reset_orders = [q for q in runtime.orders if q["kind"] == "reset" and q["incident"] == incident]
    if reset_orders:
        reset = reset_orders[0]
        mission = runtime.executive.missions.get(reset["id"])
        if mission and mission.work_completed_at is not None:
            if (
                hour > available_boundary(mission.work_completed_at)
                and diagnosis.informative
                and diagnosis.tracking_residual > 0.1
            ):
                runtime._queue(
                    "module-replacement",
                    hour,
                    incident,
                    "Post-reset informative tracking still falls short; contact agreement did not establish physical recovery",
                    inspection_evidence=report,
                )
        elif hour - reset["created_hour"] >= o.inspection_wait_hours:
            runtime._queue(
                "module-replacement",
                hour,
                incident,
                "Permitted reset has not completed within the declared wait; qualified intervention remains a separate compatible attempt",
                inspection_evidence=report,
            )
        # Ageing pre-reset evidence does not invalidate a successfully tracking
        # recovery probe or justify another invasive action by itself.
        return
    settled = bool(report["channels"]) and all(
        c["quality"] not in ("missing", "stale") for c in report["channels"]
    )
    timed_out = not work or hour - min(q["created_hour"] for q in work) >= o.inspection_wait_hours
    if report["quality"] == "usable" and report["value"] and runtime.config.reset_enabled:
        runtime._queue(
            "reset",
            hour,
            incident,
            report["reason"] + "; bounded reset permitted; shared contact failure remains possible",
            inspection_evidence=report,
        )
    elif settled or timed_out:
        runtime._queue(
            "module-replacement",
            hour,
            incident,
            "Derated process tracking persists; contact evidence cannot select reset. Investigative module substitution does not establish the cause",
            inspection_evidence=report,
        )
