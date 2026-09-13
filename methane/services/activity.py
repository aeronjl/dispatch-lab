"""Economic activity from recorded mission intervals, independent of summary counters."""

from decimal import Decimal

from methane.services.contracts import nonnegative
from methane.services.core import ASSETS

VERSION = "service-activity-quantities/1"


def quantities(record, path="/field_operations"):
    if "mission_events" not in record:
        raise ValueError("Activity-based service pricing needs original mission interval events")
    names = {v: k for k, v in ASSETS.items() if k != "crew"}
    hours, sources = {}, {}
    occupied = {}
    for i, event in enumerate(record["mission_events"]):
        if event.get("kind") != "interval":
            continue
        asset = event["asset_id"]
        if asset == ASSETS["crew"]:
            continue  # Labour is metered independently by crew-hours consumption.
        if asset not in names:
            raise ValueError("Activity needs an explicit asset price binding: " + asset)
        start, end = event["start"], event["end"]
        nonnegative(start, "activity start")
        nonnegative(end, "activity end")
        if not record["hour"] <= start < end <= record["hour"] + 1:
            raise ValueError("Activity interval must lie inside its recorded plant hour")
        windows = occupied.setdefault(asset, [])
        if any(max(start, a) < min(end, b) for a, b in windows):
            raise ValueError("One service asset cannot have overlapping active intervals")
        windows.append((start, end))
        name = names[asset]
        hours[name] = hours.get(name, Decimal(0)) + Decimal(str(end)) - Decimal(str(start))
        sources.setdefault(name, []).append(path + f"/mission_events/{i}")
    return {k: float(v) for k, v in hours.items()}, sources
