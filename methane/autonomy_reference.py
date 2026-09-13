"""Independent, standard-library checks of saved uncertainty evidence.

Checks arithmetic and causal availability under declared assumptions, not empirical
coverage, calibration, safe real-plant operation or optimal fleet management.
"""

from decimal import Decimal


def audit_run(result):
    checks = []

    def check(key, passed, controller, hour, detail=None):
        checks.append(
            dict(
                id="autonomy." + key,
                passed=bool(passed),
                controller=controller,
                interval=hour,
                method="Independent observation-clock and finite-model arithmetic",
                detail=detail,
            )
        )

    for controller, rows in result["records"].items():
        seen = {}
        for row in rows:
            h, decision = row["hour"], row["decision"]
            belief = decision.get("uncertainty_beliefs")
            if belief is None:
                continue
            check("clock", belief["hour"] == h, controller, h)
            check("evidence_set", set(belief["evidence_ids"]) == set(seen), controller, h)
            for family, value in belief["durations"].items():
                if "duration_model" in belief["options"]:
                    continue  # Equipment-specific posteriors have their own independent checker.
                packets = [p for p in seen.values() if p["group"] == family]
                check(
                    "duration_availability",
                    all(
                        p["available_at"] <= h
                        and p["started_at"] <= h
                        and (p["completed_at"] is None or p["completed_at"] <= h)
                        for p in packets
                    ),
                    controller,
                    h,
                )
                check(
                    "no_completed_censoring",
                    value["completed_phases"] == sum(not p["censored"] for p in packets),
                    controller,
                    h,
                )
                weights, bins = value["weights"], value["bins"]
                check(
                    "duration_simplex",
                    len(weights) == len(bins)
                    and all(0 <= w <= 1 for w in weights)
                    and abs(sum(weights) - 1) < 1e-8,
                    controller,
                    h,
                )
                check(
                    "duration_mean",
                    abs(
                        sum(w * (a + b) / 2 for w, (a, b) in zip(weights, bins, strict=True))
                        - value["mean_factor"]
                    )
                    < 1e-8,
                    controller,
                    h,
                )
                jobs = {}
                for packet in packets:
                    entry = jobs.setdefault(packet["order_id"], {"exact": None, "lower": 0})
                    factor = float(
                        Decimal(str(packet["elapsed_hours"]))
                        / Decimal(str(packet["nominal_hours"]))
                    )
                    if packet["censored"]:
                        entry["lower"] = max(entry["lower"], factor)
                    else:
                        entry["exact"] = factor
                check(
                    "correlated_phases_grouped",
                    value["independent_jobs"] == len(jobs),
                    controller,
                    h,
                )
                counts = [belief["options"]["duration_prior_strength"] / len(bins)] * len(bins)
                for job in jobs.values():
                    if job["exact"] is not None:
                        index = next(
                            (
                                i
                                for i, (a, b) in enumerate(bins)
                                if a - 1e-8 <= job["exact"] <= b + 1e-8
                            ),
                            None,
                        )
                        likelihood = [int(i == index) for i in range(len(bins))]
                    else:
                        likelihood = [
                            max(0, b - max(a, job["lower"])) / (b - a)
                            if b > a
                            else int(b > job["lower"])
                            for a, b in bins
                        ]
                    total = sum(w * x for w, x in zip(weights, likelihood, strict=True))
                    if total:
                        counts = [
                            c + w * x / total
                            for c, w, x in zip(counts, weights, likelihood, strict=True)
                        ]
                total = sum(counts)
                residual = max(abs(w - c / total) for w, c in zip(weights, counts, strict=True))
                check(
                    "reported_fit_convergence",
                    not value["fit_converged"] or residual < 1e-7,
                    controller,
                    h,
                    dict(residual=residual),
                )
            for item in belief["reliability"].values():
                a, b = item["alpha"], item["beta"]
                check(
                    "completion_mean",
                    abs(item["mean_completion_probability"] - a / (a + b)) < 1e-9,
                    controller,
                    h,
                )
                check(
                    "completion_variance",
                    abs(item["variance"] - a * b / ((a + b) ** 2 * (a + b + 1))) < 1e-9,
                    controller,
                    h,
                )
            solar = (decision.get("performance_estimates") or {}).get("solar", {})
            measurement = solar.get("reference_measurement")
            if measurement:
                check("reference_clock", measurement["available_at"] <= h, controller, h)
            field = row.get("field_operations") or {}
            for packet in field.get("duration_observations", []):
                check("interval_evidence_clock", packet["available_at"] == h + 1, controller, h)
                seen[packet["id"]] = packet
            snap = field.get("planning_snapshot", {})
            if field.get("observed_surface_before") is not None:
                check(
                    "observed_surface_in_snapshot",
                    snap["optical"]["surface"] == field["observed_surface_before"],
                    controller,
                    h,
                )
                check(
                    "observed_surface_in_forecast",
                    decision["forecast"]["surface_before"] == field["observed_surface_before"],
                    controller,
                    h,
                )

            # Recursively inspect every retained candidate, including non-selected solves.
            def walk(value, controller=controller, h=h):
                if isinstance(value, dict):
                    if (
                        value.get("version") == "uncertain-service-process-planning/1"
                        and value.get("outcome", {}).get("status") == "feasible"
                    ):
                        branches = value["outcome"]["branches"]
                        for t in range(len(branches[0]["requested_actions"])):
                            histories = {}
                            for branch in branches:
                                action = branch["requested_actions"][t]
                                history = branch["information"][t]
                                old = histories.setdefault(history, action)
                                check(
                                    "nonanticipative_actions",
                                    all(abs(action[k] - old[k]) < 1e-5 for k in action),
                                    controller,
                                    h,
                                )
                        for branch in branches:
                            known = branch.get("original_information_forecast", branch["forecast"])
                            check(
                                "same_original_forecast",
                                known
                                == branches[0].get(
                                    "original_information_forecast", branches[0]["forecast"]
                                ),
                                controller,
                                h,
                            )
                    for child in value.values():
                        walk(child)
                elif isinstance(value, list):
                    for child in value:
                        walk(child)

            walk(decision.get("service_control", {}))
    return checks
