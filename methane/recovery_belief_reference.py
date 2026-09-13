"""Portable, independent arithmetic for observed-recovery-belief/1.

Standard library only. Reconstructs finite reader quadrature, clipped Gaussian
power likelihoods, procedure transitions and Bayes updates from saved operands.
This checks the declared model, not the calibration of its probabilities.
"""

import hashlib
import itertools
import json
import math

VERSION = "dispatch-lab/recovery-belief-reference/1"
NEG = -math.inf


def digest(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def total(values):
    values = tuple(values)
    peak = max(values)
    return peak + math.log(math.fsum(math.exp(v - peak) for v in values)) if peak != NEG else NEG


def close(actual, expected):
    if expected == NEG:
        return actual is None
    return (
        isinstance(actual, (int, float))
        and math.isfinite(actual)
        and math.isclose(actual, expected, rel_tol=2e-10, abs_tol=2e-9)
    )


def classification(values, options):
    signal, zero, span = values
    if any(v is None for v in values):
        return "unusable"
    width = span - zero
    if (
        abs(zero) > options["inspection_zero_limit_v"]
        or abs(width - 24) > 24 * options["inspection_span_tolerance_fraction"]
        or width <= 0
    ):
        return "unusable"
    corrected = 24 * (signal - zero) / width
    if corrected <= options["inspection_low_v"]:
        return "open"
    return "closed" if corrected >= options["inspection_high_v"] else "unusable"


def contact(hypothesis, restored, reader, finding, options, points):
    if hypothesis[reader + "_dropout"]:
        return float(finding == "unusable")
    signal = (
        24
        if hypothesis["mechanism"] == "damage-and-stuck-contact"
        or (hypothesis["mechanism"] == "resettable-trip" and not restored)
        else 0
    )
    half_width = math.sqrt(3) * options["inspection_noise_v"]
    nodes = [(2 * (k + 0.5) / points - 1) * half_width for k in range(points)]
    offset = hypothesis[reader + "_offset_v"]
    successes = sum(
        classification((signal + offset + a, offset + b, 24 + offset + c), options) == finding
        for a, b, c in itertools.product(nodes, repeat=3)
    )
    return successes / points**3


def power(measured, mean, noise):
    if measured < 0:
        return NEG
    if mean == 0 or noise == 0:
        return 0.0 if abs(measured - mean) <= 1e-5 else NEG
    if measured:
        deviation = mean * noise
        return -(((measured - mean) / deviation) ** 2) / 2 - math.log(
            deviation * math.sqrt(2 * math.pi)
        )
    z = 1 / noise
    tail = math.erfc(z / math.sqrt(2)) / 2
    if tail:
        return math.log(tail)
    # Mills' expansion is used only where erfc underflows (z approximately 38+).
    # Its first twelve terms give far tighter accuracy than this check's tolerance.
    term, correction = 1.0, 1.0
    for k in range(1, 12):
        term *= -(2 * k - 1) / z**2
        correction += term
    return -z * z / 2 - math.log(z) - math.log(2 * math.pi) / 2 + math.log(correction)


def inspect(record):
    """Return explicit failed assertions; do not trust stored likelihoods or checks."""
    errors = []

    def require(condition, label):
        if not condition:
            errors.append(label)

    def weights_match(rows, weights, label):
        expected_keys = set(weights)
        require(len(rows) == len(weights), label + ": row count")
        require(
            {(r["hypothesis"], r["restored"]) for r in rows} == expected_keys, label + ": states"
        )
        for r in rows:
            key = r["hypothesis"], r["restored"]
            if key not in weights:
                continue
            value = weights[key]
            require(close(r["log_probability"], value), label + ": log weight")
            require(close(r["probability"], math.exp(value)), label + ": probability")
            require(r["impossible"] == (value == NEG), label + ": support")

    require(record["implementation_id"] == "observed-recovery-belief/1", "implementation")
    require(
        record["belief_id"] == digest({k: v for k, v in record.items() if k != "belief_id"}),
        "identity",
    )
    inputs = record["inputs"]
    p, sensors, options = inputs["plant"], inputs["sensors"], inputs["reader_options"]
    assumptions = inputs["assumptions"]
    hypotheses = assumptions["hypotheses"]
    weights = {
        (h["hypothesis_id"], restored): math.log(h["probability"])
        if not restored and h["probability"]
        else NEG
        for h in hypotheses
        for restored in (False, True)
    }
    history = record["history"]
    require(len({h["event_id"] for h in history}) == len(history), "unique events")
    require(
        history
        == sorted(
            history,
            key=lambda h: (
                h["event"]["at"],
                {"procedure": 0, "power": 1, "contact": 2}[h["event"]["kind"]],
                h["event_id"],
            ),
        ),
        "physical event order",
    )
    conflict = False
    for entry in history:
        event = entry["event"]
        require(
            assumptions["epoch_start_hour"]
            <= event["at"]
            <= event["available_at"]
            <= record["at_hour"],
            "event availability",
        )
        if event["kind"] == "procedure":
            proc = event["procedure"]
            require(
                proc["completed_at"] == event["at"]
                and math.ceil(event["at"]) == event["available_at"],
                "procedure timing",
            )
            require(
                set(proc) == {"order_id", "action", "completed_at"}, "procedure has no outcome port"
            )
            require(proc["action"] in ("reset", "module-replacement"), "procedure compatibility")
            require(entry["used"], "procedure transition used")
            weights_match(entry["before"], weights, "procedure before")
            for h in hypotheses:
                key = h["hypothesis_id"]
                chance = (
                    inputs["success_probability"]
                    if proc["action"] == "module-replacement" or h["mechanism"] == "resettable-trip"
                    else 0
                )
                old = weights[key, False]
                weights[key, True] = total(
                    (weights[key, True], old + math.log(chance) if chance else NEG)
                )
                weights[key, False] = old + math.log1p(-chance) if chance < 1 else NEG
            weights_match(entry["after"], weights, "procedure after")
            continue
        likelihoods = {}
        if event["kind"] == "contact":
            if any(
                h["event"]["kind"] == "procedure" and h["event"]["at"] == event["at"]
                for h in history
            ):
                require(not entry["used"], "unknown simultaneous contact ordering")
                continue
            packet = event["packet"]
            require(
                classification(
                    tuple(packet["operands_v"][k] for k in ("signal", "zero", "span")), options
                )
                == packet["finding"],
                "contact classification",
            )
            require(
                packet["measured_at"] == event["at"]
                and packet["available_at"] == event["available_at"],
                "contact timing",
            )
            for h in hypotheses:
                for restored in (False, True):
                    likelihood = contact(
                        h,
                        restored,
                        packet["reader"],
                        packet["finding"],
                        options,
                        assumptions["quadrature_points"],
                    )
                    likelihoods[h["hypothesis_id"], restored] = (
                        math.log(likelihood) if likelihood else NEG
                    )
        else:
            test = event["evidence"]
            packet = test["inputs"]["packet"]
            require(
                test["inputs"]["plant"] == p and test["inputs"]["sensors"] == sensors,
                "test model binding",
            )
            require(
                packet["hour"] == event["at"]
                and packet["available_at"] == event["available_at"] == event["at"] + 1,
                "power timing",
            )
            if test["resource_check"]["status"] != "feasible at recorded estimate":
                require(not entry["used"], "uninformative test excluded")
                continue
            require(
                test["operands"]["requested_kw"] == packet["request"]["electrolyser_kw"],
                "requested operand",
            )
            require(
                test["operands"]["measured_kw"] == packet["observations"]["power_kw"],
                "measured operand",
            )
            for key in weights:
                mean = min(
                    packet["request"]["electrolyser_kw"],
                    p["electrolyser_kw"] if key[1] else inputs["impaired_capacity_kw"],
                )
                minimum = p["electrolyser_kw"] * p["min_load_fraction"]
                mean = 0 if mean < minimum - 1e-5 else mean
                likelihoods[key] = power(
                    packet["observations"]["power_kw"], mean, sensors["noise_fraction"]
                )
        terms = {k: weights[k] + likelihoods[k] for k in weights}
        normalization = total(terms.values())
        if normalization == NEG:
            conflict = True
            require(not entry["used"], "unsupported observation rejected")
            break
        require(entry["used"], "supported observation used")
        weights_match(entry["before"], weights, "observation before")
        require(close(entry["log_predictive_likelihood"], normalization), "predictive likelihood")
        require(len(entry["log_likelihoods"]) == len(weights), "likelihood count")
        for term in entry["log_likelihoods"]:
            value = likelihoods[term["hypothesis"], term["restored"]]
            require(
                close(term["value"], value) and term["zero_likelihood"] == (value == NEG),
                "likelihood operand",
            )
        weights = {k: v - normalization for k, v in terms.items()}
        weights_match(entry["after"], weights, "observation after")
    if conflict or record["status"] == "unmodelled intervention":
        require(
            record["posterior"] is None and record["restoration_probability"] is None,
            "unsupported probability absent",
        )
        if conflict and record["status"] != "unmodelled intervention":
            require(record["status"] == "unsupported observation", "unsupported status")
    else:
        require(record["status"] == ("conditioned" if history else "prior only"), "status")
        weights_match(record["posterior"], weights, "posterior")
        require(
            close(
                record["restoration_probability"],
                math.exp(total(v for k, v in weights.items() if k[1])),
            ),
            "restoration probability",
        )
    return errors


def audit_run(result, reference_interval, reference_limits):
    """Bind numerical histories to original public work and observation records.

    The hourly reference is passed in by the standalone parent checker. It is
    independent of execution and is used to check admitted operating tests.
    """
    checks = []
    config = (
        result.get("provenance", {})
        .get("uncertainty_world", {})
        .get("controller_config", result["config"])
    )
    for controller, rows in result["records"].items():
        original_policy = (
            result.get("provenance", {})
            .get("controller_policies", {})
            .get(controller, {})
            .get("investigation")
            or {}
        )
        by_hour = {row["hour"]: row for row in rows}
        plans, procedures, admitted, beliefs = {}, {}, {}, {}
        for row in rows:
            hour = row["hour"]
            service = row.get("field_operations", {})
            investigation = row["decision"].get("service_control", {}).get("investigation", {})
            if original_policy.get("version") == "observed-service-investigation/3":
                checks.append(
                    dict(
                        check="recovery_belief.policy_record",
                        controller=controller,
                        hour=hour,
                        passed=investigation.get("implementation_id") == original_policy["version"],
                    )
                )
            # All current work events become observable only at a later decision.
            # Their registration follows the check, so current/future completions
            # cannot be used to justify this decision's probability.
            for episode in investigation.get("episodes", ()):
                record = episode.get("recovery_belief")
                if record is None:
                    if investigation.get("implementation_id") == "observed-service-investigation/3":
                        checks.append(
                            dict(
                                check="recovery_belief.present",
                                controller=controller,
                                hour=hour,
                                passed=False,
                            )
                        )
                    continue
                errors = inspect(record)

                def require(condition, label, errors=errors):
                    if not condition:
                        errors.append(label)

                now = record["at_hour"]
                inputs = record["inputs"]
                require(now <= hour, "decision availability")
                require(inputs["plant"] == config["plant"], "original plant")
                # These explicit inactive values are omitted by the versioned
                # archive writer. This is its documented encoding, not a guess
                # about an older implementation or missing observations.
                original_sensors = {"ambiguity_policy": "reduce-capacity/1", **config["sensors"]}
                original_reader = {
                    "crew_return_enabled": False,
                    "crew_return_pack_hours": 0.25,
                    "crew_return_check_hours": 0.25,
                    **config["service_system"],
                }
                # New reader-option records include the inactive fixed-clock defaults.
                # Their absence in older records remains the older schema.
                timing = tuple(
                    k + "_time_factor"
                    for k in ("travel", "cleaning", "inspection", "repair", "supply", "support")
                )
                if any(k in inputs["reader_options"] for k in timing):
                    for key in timing:
                        original_reader.setdefault(key, 1)
                require(inputs["sensors"] == original_sensors, "original sensor model")
                require(inputs["reader_options"] == original_reader, "original reader model")
                require(
                    inputs["success_probability"]
                    == config["field_operations"]["repair_success_probability"],
                    "original procedure reliability",
                )
                require(
                    original_policy.get("version") == "observed-service-investigation/3",
                    "original controller policy",
                )
                prior = dict(original_policy["assumptions"])
                prior["epoch_start_hour"] = episode["created_hour"]
                require(digest(inputs["assumptions"]) == digest(prior), "original prior")
                initial_decision = by_hour[episode["created_hour"]]["decision"]
                require(
                    close(
                        inputs["impaired_capacity_kw"], initial_decision["diagnosis"]["capacity_kw"]
                    ),
                    "original observed capacity",
                )
                original = by_hour[now]
                observations = original["field_operations"]["decision"]["executive"]["observations"]
                for entry in record["history"]:
                    event = entry["event"]
                    event_key = episode["id"], entry["event_id"]
                    if event["kind"] == "procedure":
                        proc = event["procedure"]
                        require(procedures.get(proc["order_id"]) == proc, "original attempted work")
                    elif event["kind"] == "contact" and event_key not in admitted:
                        packet = event["packet"]
                        require(
                            now - event["at"] <= inputs["reader_options"]["contact_max_age_hours"],
                            "age at first admission",
                        )
                        for channel, value in packet["operands_v"].items():
                            require(
                                any(
                                    r["channel"] == "contact-" + channel + ":" + packet["reader"]
                                    and r["source_id"] == packet["source_id"]
                                    and r["measured_at"] == packet["measured_at"]
                                    and r["available_at"] == packet["available_at"]
                                    and r["value"] == value
                                    and r["unit"] == "V"
                                    for r in observations
                                ),
                                "original contact operand",
                            )
                    elif event["kind"] == "power":
                        test = event["evidence"]
                        source = by_hour[event["at"]]
                        decision = source["decision"]
                        forecast = decision["forecast"]
                        expected = dict(
                            hour=source["hour"],
                            available_at=source["hour"] + 1,
                            probe=decision["probe"],
                            capacity_estimate_kw=decision["diagnosis"]["capacity_kw"],
                            estimate=decision["estimate"],
                            request={
                                k: source["requested"][k]
                                for k in (
                                    "charge_kw",
                                    "discharge_kw",
                                    "electrolyser_kw",
                                    "heater_kw",
                                    "cooling_kw",
                                    "methane_kg",
                                )
                            },
                            current=dict(
                                pv_kw=forecast["pv_kw"][0],
                                ambient_c=forecast["ambient_c"][0],
                                delivery_kg=forecast["deliveries_kg"][0],
                                service_kw=forecast.get("service_kw", [0])[0],
                                isolated=forecast.get("electrolyser_isolated", [False])[0],
                            ),
                            prior_inventory_kg=decision["observations"]["h2_inventory_kg"],
                            observations={
                                k: source["observations_after"][k]
                                for k in (
                                    "power_kw",
                                    "h2_inventory_kg",
                                    "h2_outflow_kg",
                                    "hydrogen_flow_kg",
                                )
                            },
                        )
                        require(test["inputs"]["packet"] == expected, "original operating packet")
                        if entry["used"]:
                            request, current, p = (
                                expected["request"],
                                expected["current"],
                                inputs["plant"],
                            )
                            require(
                                expected["probe"]
                                and inputs["sensors"]["enabled"]
                                and not current["isolated"]
                                and request["electrolyser_kw"]
                                > expected["capacity_estimate_kw"] + 1e-5,
                                "informative test",
                            )
                            calculated = reference_interval(
                                p,
                                expected["estimate"],
                                request,
                                current["pv_kw"],
                                current["ambient_c"],
                                current["delivery_kg"],
                                current["service_kw"],
                            )
                            require(
                                all(
                                    c["passed"]
                                    for c in reference_limits(
                                        p, expected["estimate"], calculated, p["electrolyser_kw"]
                                    )
                                ),
                                "independent test feasibility",
                            )
                    if event_key in admitted:
                        require(admitted[event_key] == event, "immutable admitted event")
                    else:
                        admitted[event_key] = event
                gate = episode.get("followup_belief_gate")
                beliefs[record["belief_id"]] = record
                if gate:
                    source = beliefs.get(gate["belief_id"])
                    require(source is not None and gate["at_hour"] <= now, "original gate decision")
                    if source:
                        probability = source["restoration_probability"]
                        impairment = None if probability is None else 1 - probability
                        require(gate["impairment_probability"] == impairment, "gate probability")
                        require(
                            gate["threshold"] == original_policy["followup_impairment_probability"],
                            "gate threshold",
                        )
                        require(
                            gate["eligible"]
                            == (impairment is not None and impairment >= gate["threshold"]),
                            "gate outcome",
                        )
                checks.append(
                    dict(
                        check="recovery_belief.arithmetic_and_original_inputs",
                        controller=controller,
                        hour=hour,
                        passed=not errors,
                        failures=sorted(set(errors)),
                    )
                )
            plans.update({p["order"]["order_id"]: p for p in service.get("new_missions", ())})
            for event in service.get("mission_events", ()):
                plan = plans.get(event["order_id"])
                if (
                    event["kind"] == "stage_end"
                    and event.get("phase") == "perform"
                    and plan
                    and plan["order"]["action"] in ("reset", "module-replacement")
                ):
                    procedures[event["order_id"]] = dict(
                        order_id=event["order_id"],
                        action=plan["order"]["action"],
                        completed_at=event["at_hour"],
                    )
    return checks
