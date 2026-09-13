"""Predicted mission costs over the same price arithmetic as recorded service work.

Candidate quantities are separate from execution events. Incremental costs are
differences on the whole accumulated wear/parts pool, not an extra ownership or
replacement allowance added to the already incurred cost.
"""

import copy
from decimal import Decimal

from methane.service_economics import (
    ACTIVITY_VERSION,
    ASSETS,
    identity,
    price_quantities,
    quantities,
    validate,
)
from methane.services.adapters import schedule
from methane.services.core import ASSETS as ASSET_IDS
from methane.services.planning import horizon

VERSION = "service-decision-pricing/3"
PREFIX_VERSION = "service-cost-input-projection/1"


def projected_row(row):
    """One cost-interface record; retain its global interval index."""
    fields = {
        "hour",
        "assets",
        "human_visits",
        "charge_input_kwh",
        "fixed_service_kwh",
        "crew_committed_hours",
        "mission_events",
        "resource_events",
        "support_effects",
        *(key + "_hours" for key in ASSETS),
    }
    r = row.get("field_operations")
    if r is None:
        return {}
    item = {key: copy.deepcopy(value) for key, value in r.items() if key in fields}
    item["state"] = {
        "executive": {"resources": copy.deepcopy(r["state"]["executive"]["resources"])}
    }
    return {"field_operations": item}


def recorded_inputs(rows, *, activity=True):
    """Copy the exact recorded cost interface, excluding unrelated decision trees.

    Source indices are retained, so quantity references still resolve into the
    original run. Compare all operands and references against the complete input
    before returning: a future accounting dependency cannot silently be omitted.
    This is an economic input identity, not a hash of the entire physical trace.
    """
    projected = [projected_row(row) for row in rows]
    if quantities(rows, activity=activity) != quantities(projected, activity=activity):
        raise ValueError("Service cost projection does not preserve its original recorded operands")
    return dict(
        implementation_id=PREFIX_VERSION,
        prefix_id=identity(projected),
        hours=len(projected),
        rows=projected,
        scope="Recorded service-cost input fields with original row/event indices. Quantities, references, installed intervals and stock operands reconcile exactly with the full prefix. This identity excludes unrelated process traces and prior decision calculations; the original run retains them.",
    )


def projected_quantities(commitments, at_hour, hours, *, visits=(), activity=False):
    """Conditional continuation quantities; no fictitious recorded resource events."""
    items = tuple(commitments)
    profile = horizon(items, at_hour, hours)
    q, refs, units, conditions = {}, {}, {}, []

    def add(key, amount, source):
        value = Decimal(str(amount))
        q[key] = q.get(key, Decimal(0)) + value
        if value:
            refs.setdefault(key, []).append(source)

    grouped = {}
    for visit in visits:
        for plan in visit.members:
            key = plan.order.order_id
            if key in grouped:
                raise ValueError("A mission cannot belong to two candidate visits")
            grouped[key] = visit.starting_at
    names = {v: k for k, v in ASSET_IDS.items() if k in ASSETS}
    end = Decimal(str(at_hour)) + hours
    for item in items:
        plan = item.plan
        key, asset = plan.order.order_id, plan.asset
        if asset.asset_id not in names and asset.asset_id != ASSET_IDS["crew"]:
            raise ValueError("Candidate needs an explicit asset price binding: " + asset.asset_id)
        for index, (a, b, stage) in enumerate(schedule(plan)):
            if index < item.stage_index:
                continue
            left, right = max(Decimal(str(a)), Decimal(str(at_hour))), min(Decimal(str(b)), end)
            if right <= left:
                continue
            source = f"/predicted_missions/{key}/stages/{index}"
            name = names.get(asset.asset_id)
            if name and (activity or name in ("cleaner", "rover", "portable")):
                add(name + "_hours", right - left, source)
            entering = not (index == item.stage_index and item.entered) and at_hour <= a < float(
                end
            )
            if (
                entering
                and stage.phase == "travel"
                and asset.autonomy == "human"
                and (key not in grouped or a == grouped[key])
            ):
                add("human_visits", 1, source)
            # This registered procedure consumes a kit but transfers no stock
            # into a destination. Other supply adapters retain their explicit
            # acceptance condition; an unknown adapter is never priced as free.
            routine = (
                plan.capability.implementation_id == "routine-service/1"
                and plan.order.action == "routine-service"
            )
            # Dock use and input electricity are already explicit. Their cost
            # does not depend on accepting a purchased material at destination;
            # robot energy remains a separate conditional inventory prediction.
            dock_charge = (
                plan.capability.implementation_id == "dc-dock-charging/1"
                and plan.order.action in ("charge-cleaner", "charge-rover")
                and asset.asset_id == ASSET_IDS["dock"]
                and not any(s.consumables or s.hourly_consumables for s in plan.stages)
            )
            if (
                plan.capability.effect_kind == "supply"
                and stage.effect
                and not (routine or dock_charge)
                # Registered retrieval relocates an existing asset; it does not
                # deliver a consumable whose acceptance/headroom needs pricing.
                and plan.capability.implementation_id != "field-retrieval/1"
            ):
                conditions.append(
                    dict(
                        order_id=key,
                        condition="Supply acceptance and rejected quantity require a projected destination inventory",
                        source=source,
                    )
                )
        if plan.ending_at > float(end):
            conditions.append(
                dict(
                    order_id=key,
                    condition="Mission costs continue beyond the priced horizon",
                    source=f"/predicted_missions/{key}",
                )
            )
    for row in profile["rows"]:
        for e in row["stock_events"]:
            resource = e["resource"]
            source = f"/predicted_missions/{e['order_id']}/stages/{e['stage_index']}"
            if resource in ("crew-hours", "remote-hours"):
                add(resource, e["amount"], source)
                if resource == "crew-hours" and e["phase"] in ("travel", "return", "transfer"):
                    add("crew-travel-hours", e["amount"], source)
            elif resource.startswith(("stock:", "upstream:")):
                group, material = resource.split(":", 1)
                add(("used:" if group == "stock" else "purchased:") + material, e["amount"], source)
                key = "unit:" + material
                if key in units and units[key] != e["unit"]:
                    raise ValueError("Candidate material units do not agree")
                units[key] = e["unit"]
    return dict(
        quantities={k: float(v) for k, v in q.items()},
        sources=refs,
        units=units,
        conditions=conditions,
        projection=profile,
    )


def price(commitments, candidates, assumptions, *, at_hour, hours, installed, prefix=(), visits=()):
    """Price existing obligations and additions without changing the source run.

    The caller supplies a complete recorded prefix and current installed assets.
    Supply disposition and costs after the horizon remain explicit conditions.
    Electricity stays in the coupled plant balance, not a duplicate cash charge.
    """
    a = validate(assumptions)
    if type(at_hour) is not int or len(prefix) != at_hour:
        raise ValueError("Candidate pricing requires the complete recorded prefix at this hour")
    if set(installed) - set(ASSETS):
        raise ValueError("Unknown installed service asset price binding")
    base, extra = tuple(commitments), tuple(candidates)
    observed = quantities(prefix, activity=a["schema_version"] == ACTIVITY_VERSION)
    outputs = []
    for items in (base, base + extra):
        predicted = projected_quantities(
            items, at_hour, hours, visits=visits, activity=a["schema_version"] == ACTIVITY_VERSION
        )
        q, refs, present, stocks = copy.deepcopy(observed)
        for key, amount in predicted["quantities"].items():
            q[key] = q.get(key, 0) + amount
        for key, sources in predicted["sources"].items():
            refs.setdefault(key, []).extend(sources)
        for key, unit in predicted["units"].items():
            if key in stocks and stocks[key] != unit:
                raise ValueError("Predicted quantity unit differs from recorded prefix")
            stocks[key] = unit
        for key in installed:
            present[key] = present.get(key, 0) + hours
        money = price_quantities(q, refs, present, stocks, a, hours=at_hour + hours)
        outputs.append(
            dict(
                quantities=q,
                quantity_sources=refs,
                decision=money["views"]["decision"],
                expenditure=money["views"]["expenditure"],
                lines=[
                    line
                    for line in money["lines"]
                    if "decision" in line["views"] or "expenditure" in line["views"]
                ],
                conditions=predicted["conditions"],
                predicted_quantities=predicted["quantities"],
            )
        )
    old, new = outputs

    def delta(view):
        before, after = old[view]["total_eur"], new[view]["total_eur"]
        return None if before is None or after is None else after - before

    missing = sorted(set(old["decision"]["unpriced"] + new["decision"]["unpriced"]))
    conditions = old["conditions"] + new["conditions"]
    return dict(
        implementation_id=VERSION,
        assumption_id=identity(a),
        assumptions=a,
        at_hour=at_hour,
        hours=hours,
        prefix_id=identity(prefix),
        without_additions=old,
        with_additions=new,
        incremental_decision_eur=None if conditions else delta("decision"),
        incremental_expenditure_eur=delta("expenditure"),
        known_decision_difference_eur=delta("decision"),
        status="conditional" if conditions else "incomplete-prices" if missing else "complete",
        unpriced=missing,
        conditions=conditions,
        scope="Predicted successful continuation, not realised events. Incremental decision cost is the difference of accumulated usage/parts pools and variable consumption; fixed ownership is excluded. Forecast electricity and lost output are not charged again. Supply disposition and work beyond the horizon need explicit continuations.",
    )


def dock_cost_table(commitments, assumptions, *, at_hour, hours, installed, prefix=(), visits=()):
    """Exact incremental dock usage costs on the recorded plus committed pool.

    Only additional dock-active hours vary. Energy and destination headroom
    belong to the joint charging model; no electricity purchase is added here.
    An unknown applicable price or unfinished supply disposition stays unknown.
    """
    a = validate(assumptions)
    if a["schema_version"] != ACTIVITY_VERSION:
        raise ValueError("Joint charging needs prices based on recorded dock activity")
    if "dock" not in installed:
        raise ValueError("Dock pricing requires its installed asset binding")
    commitments = tuple(commitments)
    quote = price(
        commitments,
        (),
        a,
        at_hour=at_hour,
        hours=hours,
        installed=installed,
        prefix=prefix,
        visits=visits,
    )
    result = dict(
        implementation_id="dock-incremental-cost-table/1",
        assumption_id=identity(a),
        prefix_id=identity(prefix),
        baseline=quote,
        status=quote["status"],
        incremental_decision_eur=None,
        unpriced=list(quote["unpriced"]),
    )
    if quote["status"] != "complete":
        return result
    base = quote["without_additions"]
    _, _, present, stocks = quantities(prefix, activity=True)
    for key in installed:
        present[key] = present.get(key, 0) + hours
    stocks.update(
        projected_quantities(commitments, at_hour, hours, visits=visits, activity=True)["units"]
    )
    table = []
    for count in range(hours + 1):
        q, refs = copy.deepcopy(base["quantities"]), copy.deepcopy(base["quantity_sources"])
        q["dock_hours"] = q.get("dock_hours", 0) + count
        refs.setdefault("dock_hours", []).append(f"/predicted_charging/active_hours/{count}")
        money = price_quantities(q, refs, present, stocks, a, hours=at_hour + hours)
        total = money["views"]["decision"]["total_eur"]
        if total is None:
            result.update(
                status="incomplete-prices", unpriced=money["views"]["decision"]["unpriced"]
            )
            return result
        table.append(max(0, total - base["decision"]["total_eur"]))
    result["incremental_decision_eur"] = table
    return result
