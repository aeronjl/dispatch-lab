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
            if record.get("version") != "scheduled-load-tests/3":
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
                    "bounded-window", episode["due_hour"] == boundary + policy["maximum_wait_hours"]
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
    return checks
