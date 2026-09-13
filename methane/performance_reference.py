"""Independent standard-library arithmetic checks for recorded performance updates.

These checks establish the declared recurrence and timing, not empirical accuracy.
They do not import the estimator or simulation kernels.
"""

from decimal import Decimal, localcontext


def audit_run(result):
    checks = []

    def check(name, actual, expected, controller, hour):
        with localcontext() as ctx:
            ctx.prec = 40
            if isinstance(expected, bool):
                passed = actual == expected
            else:
                passed = abs(Decimal(str(actual)) - Decimal(str(expected))) <= Decimal("1e-9")
        checks.append(
            dict(
                id="performance." + name,
                controller=controller,
                interval=hour,
                actual=actual,
                expected=expected,
                passed=passed,
                method="Independent Decimal recurrence and information-clock check",
            )
        )

    def D(x):
        return Decimal(str(x))

    world = result.get("provenance", {}).get("uncertainty_world", {})
    original = world.get("controller_config", result["config"])
    for name, rows in result["records"].items():
        solar, cleaning, count = (
            Decimal(1),
            D(original["field_operations"]["cleaning_removal_fraction"]),
            0,
        )
        for row in rows:
            record = row["decision"].get("performance_estimates")
            if record is None:
                continue
            h, options = row["hour"], record["options"]
            if "adaptation" in world:
                check("original_options", options == world["adaptation"], True, name, h)
            x = record["solar"]
            field = row.get("field_operations")
            supplied = row["pv_kw"]
            if field and not field.get("optical"):
                supplied /= 1 - field["soiling_before"]
            check("observed_power", x["measured_kw"], supplied, name, h)
            check("solar_clock", x["hour"], h, name, h)
            check("solar_before", x["before"], float(solar), name, h)
            ratio = D(x["measured_kw"]) / D(x["expected_kw"]) if x["expected_kw"] else None
            informative = x["expected_kw"] >= options["minimum_solar_kw"] and (
                D(options["solar_support"][0]) <= ratio <= D(options["solar_support"][1])
            )
            if informative:
                count += 1
                if count >= options["minimum_samples"] and options["mode"] == "adaptive":
                    solar += D(options["gain"]) * (ratio - solar)
            check("solar_count", x["informative_intervals"], count, name, h)
            check("solar_after", x["after"], float(solar), name, h)
            if record.get("services"):
                check("service_available", record["services"]["available_at"] <= h, True, name, h)
                check("service_prior", record["services"]["after"], float(cleaning), name, h)
            update = row.get("field_operations", {}).get("performance_update")
            if update:
                check("service_clock", update["available_at"], h + 1, name, h)
                check("service_before", update["before"], float(cleaning), name, h)
                p = update["inputs"]
                if p["passes"] > 0 and p["before"] > 1e-8:
                    left = (D(p["after"]) - D(p["accumulation"])) / D(p["before"])
                    if 0 <= left <= 1:
                        # Decimal supports fractional powers; no production formula imported.
                        estimate = 1 - left ** (Decimal(1) / D(p["passes"]))
                        check(
                            "surface_inverse", update["estimated_removal"], float(estimate), name, h
                        )
                        if options["mode"] == "adaptive":
                            cleaning += D(options["gain"]) * (estimate - cleaning)
                check("service_after", update["after"], float(cleaning), name, h)
    return checks
