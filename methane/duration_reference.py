"""Standard-library recalculation of saved equipment/job clocks and posteriors."""

import hashlib
import json
import math


def prepare(result):
    options = result.get("provenance", {}).get("uncertainty_world", {}).get("autonomy", {})
    model = options.get("duration_model")
    if model is None:
        return result, []
    checks, records = [], {}
    seed = result["config"]["scenario"]["seed"]
    physical = result["config"]["service_system"]

    def check(key, value, name, hour):
        checks.append(
            dict(
                id="duration_population." + key,
                passed=bool(value),
                controller=name,
                interval=hour,
                method="Independent named-draw and finite-posterior calculation",
            )
        )

    for name, rows in result["records"].items():
        counts, factors, seen, converted = {}, {}, {}, []
        for row in rows:
            h, field = row["hour"], row.get("field_operations", {})
            truth = result["retrospective_truth_by_controller"][name][h].get(
                "service_job_clocks", {}
            )
            for plan in field.get("new_missions", []):
                order = plan["order"]["order_id"]
                key = (plan["interface"]["target_asset_id"], plan["order"]["action"])
                number = counts.get(key, 0) + 1
                counts[key] = number
                values = {}
                for group, item in model["groups"].items():
                    token = ["target-action-request/1", seed, *key, number, "duration:" + group]
                    raw = json.dumps(token, ensure_ascii=True, separators=(",", ":")).encode()
                    u = (int.from_bytes(hashlib.sha256(raw).digest()[:8], "big") >> 11) / 2**53
                    a, b = item["job_multiplier_bounds"]
                    persistent = physical[group + "_time_factor"]
                    values[group] = persistent * (a + (b - a) * u)
                    check("persistent_support", persistent in item["persistent_factors"], name, h)
                    if order in truth:
                        recorded = truth[order]["draws"][group]
                        check("draw", abs(recorded["uniform"] - u) < 1e-14, name, h)
                        check(
                            "factor",
                            abs(recorded["applied_factor"] - values[group]) < 1e-12,
                            name,
                            h,
                        )
                if plan.get("timing"):
                    check("truth_recorded", order in truth, name, h)
                factors[order] = values

            # Annotate only the checker's view; archives and controller records stay untouched.
            def annotate(p, factors=factors):
                return {**p, "_reference_factors": factors[p["order"]["order_id"]]}

            new_field = {
                **field,
                "new_missions": [annotate(p) for p in field.get("new_missions", [])],
            }
            if "new_visits" in field:
                new_field["new_visits"] = [
                    {**v, "members": [annotate(p) for p in v["members"]]}
                    for v in field["new_visits"]
                ]
            converted.append({**row, "field_operations": new_field})
            belief = row["decision"].get("uncertainty_beliefs", {})
            for asset, groups in belief.get("equipment_durations", {}).items():
                for group, value in groups.items():
                    packets = [
                        p for p in seen.values() if p["asset_id"] == asset and p["group"] == group
                    ]
                    check("availability", all(p["available_at"] <= h for p in packets), name, h)
                    item = model["groups"][group]
                    jobs = {}
                    for p in packets:
                        j = jobs.setdefault(p["order_id"], {"exact": None, "lower": 0})
                        ratio = p["elapsed_hours"] / p["nominal_hours"]
                        if p["censored"]:
                            j["lower"] = max(j["lower"], ratio)
                        else:
                            j["exact"] = ratio
                    weights = list(item["prior_weights"])
                    for job in jobs.values():
                        likelihood = []
                        for persistent in item["persistent_factors"]:
                            a, b = [persistent * x for x in item["job_multiplier_bounds"]]
                            if job["exact"] is not None:
                                likelihood.append(
                                    (1 / (b - a) if b > a else 1)
                                    if a - 1e-7 <= job["exact"] <= b + 1e-7
                                    else 0
                                )
                            else:
                                likelihood.append(
                                    max(0, min(1, (b - job["lower"]) / (b - a)))
                                    if b > a
                                    else int(b > job["lower"])
                                )
                        w = [x * y for x, y in zip(weights, likelihood, strict=False)]
                        if sum(w):
                            weights = [x / sum(w) for x in w]
                    if not value["unsupported"]:
                        check(
                            "posterior",
                            all(
                                math.isclose(a, b, abs_tol=1e-9)
                                for a, b in zip(weights, value["posterior_weights"], strict=False)
                            ),
                            name,
                            h,
                        )
                    check("job_count", value["independent_jobs"] == len(jobs), name, h)
                    check(
                        "no_completed_censoring",
                        value["completed_phases"] == sum(not p["censored"] for p in packets),
                        name,
                        h,
                    )
            for p in field.get("duration_observations", []):
                seen[p["id"]] = p
        records[name] = converted
    return {**result, "records": records}, checks
