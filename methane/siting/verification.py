"""Independent chronological checks over saved periods; no production transitions used."""

from methane.reference import check_actions, initial, interval
from methane.siting.production import directory, entries, load_period
from methane.siting.store import atomic, encode
from methane.timebase import utc


def verify_case(store, study_id, case_id):
    manifest = store.get("study", study_id)
    case = next(c for c in manifest["cases"] if c["case_id"] == case_id)
    previous = None
    next_hour = 0
    checks = 0
    errors = []
    maxima = {}
    lifecycle_reference = None

    def equal(key, a, b, hour):
        nonlocal checks
        checks += 1
        error = abs(float(a) - float(b))
        maxima[key] = max(maxima.get(key, 0), error)
        if error > 1e-5 + 1e-8 * max(abs(float(a)), abs(float(b))) and len(errors) < 100:
            errors.append(dict(hour=hour, key=key, recorded=a, independent=b, error=error))

    for entry in entries(store, study_id, case_id):
        result = load_period(store, entry["period_sha256"])
        rows = result["records"][case["controller"]]
        p = result["config"]["plant"]
        if result["config"].get("lifecycle") and lifecycle_reference is None:
            from methane.lifecycle_reference import Reference

            lifecycle_reference = Reference(result["config"])
        if previous is None:
            previous = initial(p, rows[0]["ambient_c"])
        for key, value in previous.items():
            equal(
                "boundary." + key,
                result["continuous_period"]["initial_state"][key],
                value,
                next_hour,
            )
        for row, truth in zip(
            rows, result["retrospective_truth_by_controller"][case["controller"]], strict=True
        ):
            if row["hour"] != next_hour:
                raise ValueError("Missing or duplicated chronological interval")
            if lifecycle_reference is not None:
                for check in lifecycle_reference.interval(row, truth, case["controller"]):
                    checks += 1
                    if not check["passed"] and len(errors) < 100:
                        errors.append(check)
                p = row["lifecycle"]["physical_plant"]
            supplied = row["co2_delivered_kg"] + row["co2_rejected_kg"]
            expected = interval(
                p,
                previous,
                row["applied"],
                row["pv_kw"],
                row["ambient_c"],
                supplied,
                row.get("service_kw", 0),
            )
            for key, value in expected["state"].items():
                equal("state." + key, row["state"][key], value, next_hour)
            for key, value in expected.items():
                if key not in ("state", "applied"):
                    equal(key, row[key], value, next_hour)
            for check in check_actions(p, previous, row, truth["capacity_kw"], row["requested"]):
                checks += 1
                if not check["passed"] and len(errors) < 100:
                    errors.append({"hour": next_hour, **check})
            source = row["decision"]["forecast"]["source"]
            equal(
                "forecast_available",
                max(0, (utc(source["available_at"]) - utc(row["time"])).total_seconds()),
                0,
                next_hour,
            )
            previous = expected["state"]
            next_hour += 1
    value = dict(
        schema_version="site-independent-chronology/1",
        study_id=study_id,
        case_id=case_id,
        source=manifest["source"]["content_hash"],
        completed_hours=next_hour,
        expected_hours=case["hours"],
        checks=checks,
        max_absolute_errors=maxima,
        failures=errors,
        status="passed"
        if not errors and next_hour == case["hours"]
        else "incomplete"
        if next_hour != case["hours"]
        else "failed",
        scope="Independent 42-digit Decimal material/electrical/thermal integration, operating boundaries, checkpoint continuity and forecast publication. Does not establish calibration or independently verify every service mission mechanic.",
    )
    atomic(directory(store, study_id) / case_id / "independent-checks.json", encode(value))
    return value
