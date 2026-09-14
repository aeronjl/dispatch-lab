"""Report policy machinery separately from physical and monetary outcomes."""

from collections import Counter


def summary(rows):
    records = [
        r["decision"]["experimental_policy"]
        for r in rows
        if r["decision"].get("experimental_policy")
    ]
    if not records:
        return {}
    penalties = [
        r["reserve_accounting"]["preference_penalty"]
        for r in records
        if r.get("reserve_accounting")
    ]
    return dict(
        experimental_policy=dict(
            decision_count=len(records),
            statuses=dict(Counter(r["status"] for r in records)),
            fallback_reasons=dict(Counter(r["reason"] for r in records if r.get("reason"))),
            mean_inference_ms=sum(r["elapsed_ms"] for r in records) / len(records),
            mean_planned_reserve_penalty=sum(penalties) / len(penalties) if penalties else None,
            scope="Machinery outcomes, not empirical policy value. Planned reserve penalties overlap in time and are not cash costs. Read methane, original decision costs, trips, service outcomes and ending inventories alongside this record.",
        )
    )
