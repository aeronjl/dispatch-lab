"""Standard-library checks of recorded post-mission verification boundaries."""

import math


def audit_run(result):
    checks = []
    for controller, rows in result["records"].items():
        orders = {
            o["id"]: o
            for row in rows
            for o in (row.get("field_operations") or {}).get("state", {}).get("orders", [])
        }
        prior = {}
        for row in rows:
            record = row["decision"].get("recovery_planning", {})
            if record.get("version") not in (
                "scheduled-load-tests/3",
                "scheduled-load-tests/4",
                "scheduled-load-tests/5",
            ):
                continue
            loop = record["verification_loop"]
            policy = result["provenance"]["controller_policies"][controller]["recovery"]

            def check(name, passed, hour=row["hour"], controller=controller):
                checks.append(
                    dict(
                        id="recovery-loop." + name,
                        passed=bool(passed),
                        controller=controller,
                        interval=hour,
                        method="Independent public receipt and deadline arithmetic",
                    )
                )

            for episode in loop["episodes"]:
                key = tuple(episode["receipt_ids"])
                boundary = episode["available_boundary"]
                check(
                    "bounded-window",
                    (boundary <= episode["due_hour"] <= boundary + policy["maximum_wait_hours"])
                    if record["version"] == "scheduled-load-tests/4"
                    else episode["due_hour"] == boundary + policy["maximum_wait_hours"],
                )
                check("available-before-opening", boundary <= episode["opened_at"] <= row["hour"])
                for identity in key:
                    order = orders[identity]
                    check(
                        "whole-mission-return",
                        math.ceil(order["completed_hour"] - 1e-9) <= boundary,
                    )
                    check("receipt-available", order["reported"]["available_at"] <= boundary)
                fixed = {
                    k: episode[k]
                    for k in (
                        "opened_at",
                        "available_boundary",
                        "due_hour",
                        "original_diagnosis_deadline",
                    )
                }
                check("immutable-window", prior.setdefault(key, fixed) == fixed)
            if record["status"] in ("escalation-required", "awaiting-procedure", "awaiting-remedy"):
                check(
                    "no-unapproved-test",
                    not record["probe_now"] and record.get("commitment") is None,
                )
            check(
                "distinct-shortfalls",
                len({t["evidence_id"] for t in loop["shortfall_tests"]})
                == len(loop["shortfall_tests"]),
            )
            check(
                "eligible-shortfalls",
                all(t["available_at"] <= row["hour"] for t in loop["shortfall_tests"]),
            )
            if record["version"] == "scheduled-load-tests/5":
                for opening in record["deadline_openings"]:
                    check(
                        "whole-obligation-deadline",
                        opening["due_hour"]
                        == opening["available_boundary"] + policy["maximum_wait_hours"],
                    )
                progress = record["recovery_obligation"]
                r = progress["remaining"]
                # Independent forward arithmetic, separate from the scheduling implementation.
                capacity, count = r["capacity_estimate_kw"], 0
                while capacity < r["nameplate_kw"] * 0.999 and count <= 1000:
                    capacity = min(
                        r["nameplate_kw"],
                        max(
                            result["config"]["plant"]["electrolyser_kw"]
                            * result["config"]["plant"]["min_load_fraction"],
                            capacity + r["increment_kw"],
                        ),
                    )
                    count += 1
                check("remaining-increases", count == r["increases_remaining"])
                check(
                    "remaining-informative-intervals",
                    r["minimum_informative_intervals"]
                    == count * r["confirmation_hours"] - r["consecutive_prefix"],
                )
                appointment = record.get("test_appointment")
                if appointment:
                    check(
                        "appointment-within-obligation",
                        appointment["end_hour"] <= appointment["due_hour"],
                    )
                    check(
                        "appointment-is-commitment",
                        all(appointment[k] == v for k, v in record["commitment"].items()),
                    )
    return checks
