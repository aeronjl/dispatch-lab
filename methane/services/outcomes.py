"""Descriptive field outcomes from recorded execution and eligible observations.

These are period totals, not claims about annual value or physical reliability.
No controller consumes this retrospective aggregation.
"""

VERSION = "field-period-outcomes/1"


def calculate(rows):
    records = [r.get("field_operations") for r in rows]
    if not records or any(
        not r or not r.get("version", "").startswith("plant-service-contracts/") for r in records
    ):
        return None
    details = [
        r.get("component_records", {}).get("solar", {}).get("diagnostics", {}).get("detail") or {}
        for r in rows
    ]
    contacts = [
        r for r in records if (r["decision"].get("inspection") or {}).get("quality") == "usable"
    ]
    optical = all("treated_area_m2" in r for r in records)
    return dict(
        implementation_id=VERSION,
        cleaning_treated_m2=sum(r["treated_area_m2"] for r in records) if optical else None,
        cleaning_full_passes=sum(r["cleanings_completed"] for r in records),
        cleaning_water_l=sum(r.get("water_used_l", 0) for r in records),
        converter_clipped_kwh=sum(d["clipped_kw"] for d in details)
        if all("clipped_kw" in d for d in details)
        else None,
        contact_usable_decision_hours=len(contacts)
        if any(r["decision"].get("inspection") for r in records)
        else None,
        contact_first_usable_hour=contacts[0]["decision"]["inspection"]["at_hour"]
        if contacts
        else None,
        dock_unserved_kwh=sum(r.get("standby", {}).get("unserved_kwh", 0) for r in records)
        if any("standby" in r for r in records)
        else None,
        routine_completed=sum(
            e["kind"] == "routine-service" for r in records for e in r.get("support_effects", [])
        ),
        scope="Applied hourly totals. Contact hours count eligible decision evidence, not retrospective truth or unique samples. Missing optical, standby or referenced sensing mechanisms remain undefined; no annualization.",
    )
