"""Independent arithmetic/lineage checks for conditional return-to-charge plans."""

import math


def audit_candidate(evaluation, snapshot):
    checks = []

    def check(key, passed):
        checks.append(
            dict(
                id="retrieval." + key,
                passed=bool(passed),
                method="Independent recorded-recipe and charging-boundary calculation",
            )
        )

    plans = {m["plan"]["order"]["order_id"]: m["plan"] for m in snapshot["missions"]}
    states = {m["plan"]["order"]["order_id"]: m["status"] for m in snapshot["missions"]}
    demand = evaluation["demand"]
    plans.update(
        {p["plan"]["order"]["order_id"]: p["plan"] for p in demand["proposals"] if "plan" in p}
    )
    visits = list(snapshot.get("visits", [])) + [
        p["visit"] for p in demand["proposals"] if "visit" in p
    ]
    for v in visits:
        plans.update({p["order"]["order_id"]: p for p in v["members"]})
    for value in evaluation.get("conditional_returns", []):
        check(
            "observed_abort",
            all(states.get(k) == "stranded" for k in value["observed_stranded_orders"]),
        )
        check("resource_projection", demand["state"] == "projected")
        boundaries = []
        for continuation in value["continuations"]:
            p = plans.get(continuation["order_id"])
            check("recorded_continuation", p is not None)
            if p is None:
                continue
            check(
                "qualified_retrieval",
                p["capability"]["implementation_id"] == "field-retrieval/1"
                and p["order"]["action"] == "retrieve"
                and "recovery-carrier" in p["asset"]["tools"],
            )
            end = p["starting_at"] + sum(s["duration_hours"] for s in p["stages"])
            for v in visits:
                if any(m["order"]["order_id"] == p["order"]["order_id"] for m in v["members"]):
                    end = max(
                        end,
                        max(
                            m["starting_at"] + sum(s["duration_hours"] for s in m["stages"])
                            for m in v["members"]
                        ),
                    )
            boundary = math.ceil(end - 1e-9)
            boundaries.append(boundary)
            check(
                "whole_mission_boundary",
                continuation["available_at"] == boundary
                and abs(continuation["complete_at"] - end) < 1e-8,
            )
        if value["available_at"] is not None:
            check(
                "combined_return_boundary",
                bool(boundaries) and value["available_at"] == max(boundaries),
            )
            check(
                "all_origins_covered",
                set(value["observed_stranded_orders"])
                <= {c["origin_order"] for c in value["continuations"]},
            )
        charging = evaluation.get("charging") or {}
        inputs = charging.get("inputs", {})
        inputs = inputs.get("charging", inputs)
        for battery in inputs.get("batteries", []):
            if battery["name"] == value["robot"]:
                check(
                    "no_charge_before_return",
                    all(
                        not available
                        or value["available_at"] is not None
                        and snapshot["at_hour"] + t >= value["available_at"]
                        for t, available in enumerate(battery["available"])
                    ),
                )
    return checks


def audit_run(result):
    checks = []
    for name, rows in result["records"].items():
        for row in rows:
            for candidate in row["decision"].get("service_control", {}).get("candidates", []):
                evaluation = candidate.get("evaluation", {})
                if evaluation.get("conditional_returns"):
                    items = audit_candidate(
                        evaluation, row["field_operations"]["planning_snapshot"]
                    )
                    checks.extend({**c, "controller": name, "interval": row["hour"]} for c in items)
    return checks
