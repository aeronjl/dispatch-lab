"""Three economic views of recorded finite-logistics service work.

No simulation or private fault state is consulted. Inputs are complete, versioned
price assumptions and the public mission/resource ledger. Prices are illustrative
unless their author supplies another explicitly scoped basis.
"""

import copy
import hashlib
import json
from dataclasses import asdict, dataclass, fields
from math import isfinite

VERSION = "dispatch-lab/service-economics/1"
ACTIVITY_VERSION = "dispatch-lab/service-economics/2"
ASSETS = ("cleaner", "rover", "dock", "fixed_reader", "reset", "portable")
VIEWS = ("allocated", "decision", "expenditure")


def identity(value):
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def amount(value, name, *, nullable=False):
    if value is None and nullable:
        return
    if isinstance(value, bool) or not isinstance(value, (float, int)) or not isfinite(value):
        raise ValueError(f"{name} must be finite and numeric")
    if value < 0:
        raise ValueError(f"{name} must be nonnegative")


@dataclass(frozen=True)
class AssetPrice:
    provision: str
    capital_eur: float | None
    life_years: float
    replaceable_capital_eur: float
    wear_eur_per_hour: float | None
    installation_eur: float | None
    mapping_eur: float | None
    access_eur: float | None
    payload_eur: float | None
    references_eur: float | None
    scheduled_maintenance_eur_per_year: float | None
    software_communications_eur_per_year: float | None
    retainer_eur_per_hour: float | None
    service_eur_per_active_hour: float | None

    def __post_init__(self):
        if self.provision not in ("owned", "contracted", "shared"):
            raise ValueError("Unknown service provision")
        for f in fields(self):
            if f.name != "provision":
                amount(
                    getattr(self, f.name),
                    f.name,
                    nullable=f.name not in ("life_years", "replaceable_capital_eur"),
                )
        if self.life_years <= 0:
            raise ValueError("Ownership life must be positive")
        if self.capital_eur is not None and self.replaceable_capital_eur > self.capital_eur:
            raise ValueError("Replaceable capital must be a subset of purchased equipment")
        if self.provision == "owned":
            if self.retainer_eur_per_hour != 0 or self.service_eur_per_active_hour != 0:
                raise ValueError("Purchased equipment cannot also carry a provision subscription")
        elif any(
            getattr(self, k) != 0
            for k in (
                "capital_eur",
                "replaceable_capital_eur",
                "wear_eur_per_hour",
                "scheduled_maintenance_eur_per_year",
                "payload_eur",
                "references_eur",
            )
        ):
            raise ValueError(
                "Contract/shared provision includes hardware, payload, references, wear and maintenance"
            )


def illustrative(costs, *, version=VERSION):
    """Complete editable fixture, not vendor quotes or an ownership recommendation."""
    if version not in (VERSION, ACTIVITY_VERSION):
        raise ValueError("Unknown service price model")
    assets = {}
    for key in ASSETS:
        cap = getattr(costs, key + "_eur", 0)
        assets[key] = asdict(
            AssetPrice(
                provision="contracted" if key == "portable" else "owned",
                capital_eur=cap,
                life_years=costs.field_asset_years,
                replaceable_capital_eur=cap * costs.field_replaceable_share
                if key in ("cleaner", "rover")
                else min(1000, cap)
                if key == "dock"
                else 0,
                wear_eur_per_hour=getattr(costs, key + "_wear_eur_per_hour", 0),
                installation_eur=2000 if key in ("cleaner", "rover", "dock") else 500,
                mapping_eur=1000 if key in ("cleaner", "rover") else 0,
                access_eur=2000 if key == "cleaner" else 0,
                payload_eur=2000 if key == "rover" else 0,
                references_eur=500 if key in ("rover", "fixed_reader") else 0,
                scheduled_maintenance_eur_per_year=costs.field_maintenance_eur_per_year
                if key == "dock"
                else 0,
                software_communications_eur_per_year=600 if key in ("cleaner", "rover") else 0,
                retainer_eur_per_hour=0,
                service_eur_per_active_hour=10 if key == "portable" else 0,
            )
        )
    return {
        "schema_version": version,
        "basis": "Illustrative EUR assumptions; procurement at upstream release, with no refund for rejected deliveries. No actual vendor invoices.",
        "source": "assumption:field-service-prices/2",
        "initial_asset_purchase": False,
        "initial_stock_purchase": False,
        "assets": assets,
        "materials": {
            "cleaning": {"eur_per_unit": costs.cleaning_kit_eur, "unit": "kit", "pool": None},
            "module": {"eur_per_unit": costs.repair_eur_per_incident, "unit": "kit", "pool": None},
            "calibration": {"eur_per_unit": costs.calibration_kit_eur, "unit": "kit", "pool": None},
            "water": {"eur_per_unit": costs.water_eur_per_m3 / 1000, "unit": "L", "pool": None},
            "brush": {"eur_per_unit": 100, "unit": "kit", "pool": "cleaner"},
            "maintenance": {"eur_per_unit": 50, "unit": "kit", "pool": None},
            "hardware:cleaner": {"eur_per_unit": 800, "unit": "module", "pool": "cleaner"},
            "hardware:rover": {"eur_per_unit": 2500, "unit": "module", "pool": "rover"},
            "hardware:dock": {"eur_per_unit": 1000, "unit": "module", "pool": "dock"},
            "hardware:portable": {"eur_per_unit": 250, "unit": "module", "pool": "portable"},
        },
        "rates": {
            "crew_eur_per_hour": costs.human_service_eur_per_hour,
            "remote_eur_per_hour": 60,
            "callout_eur": costs.visit_eur_per_incident,
            "vehicle_eur_per_travel_hour": 20,
        },
    }


def validate(value):
    value = copy.deepcopy(value)
    if set(value) != {
        "schema_version",
        "basis",
        "source",
        "initial_asset_purchase",
        "initial_stock_purchase",
        "assets",
        "materials",
        "rates",
    } or value["schema_version"] not in (VERSION, ACTIVITY_VERSION):
        raise ValueError("Supply a complete service economics version-1 definition")
    if not value["basis"] or not value["source"]:
        raise ValueError("Price assumptions require an explicit basis and source")
    for k in ("initial_asset_purchase", "initial_stock_purchase"):
        if not isinstance(value[k], bool):
            raise ValueError("Purchase timing must be an explicit boolean")
    if set(value["assets"]) != set(ASSETS):
        raise ValueError("Explicit provision assumptions are required for every supported asset")
    for key, item in value["assets"].items():
        if set(item) != {f.name for f in fields(AssetPrice)}:
            raise ValueError(f"Incomplete asset prices: {key}")
        AssetPrice(**item)
    if set(value["rates"]) != {
        "crew_eur_per_hour",
        "remote_eur_per_hour",
        "callout_eur",
        "vehicle_eur_per_travel_hour",
    }:
        raise ValueError("Incomplete labour and travel assumptions")
    for key, rate in value["rates"].items():
        amount(rate, key, nullable=True)
    for key, item in value["materials"].items():
        if set(item) != {"eur_per_unit", "unit", "pool"} or item["pool"] not in (None, *ASSETS):
            raise ValueError(f"Invalid material scope: {key}")
        if item["unit"] not in ("kit", "module", "L"):
            raise ValueError("Unknown material unit")
        amount(item["eur_per_unit"], key, nullable=True)
    return value


def quantities(rows, *, activity=False):
    """Bind each sum to original ledger locations. Do not infer unrecorded labour."""
    q, refs, present, stocks = {}, {}, {}, {}

    def add(key, value, source):
        amount(value, key)
        q[key] = q.get(key, 0) + value
        if value:
            refs.setdefault(key, []).extend(source if isinstance(source, list) else [source])

    for i, row in enumerate(rows):
        r = row.get("field_operations")
        if r is None:
            continue
        if r.get("hour") != i:
            raise ValueError(
                "Service reports require a contiguous prefix from the run's first interval"
            )
        if "resource_events" not in r or "crew_committed_hours" not in r:
            raise ValueError(
                "Complete service economics requires recorded finite-logistics resources; legacy reports remain available"
            )
        base = f"/rows/{i}/field_operations"
        for key, enabled in r["assets"].items():
            if enabled:
                if key not in ASSETS:
                    raise ValueError(f"Asset {key} needs an explicit economic adapter")
                present[key] = present.get(key, 0) + 1
        for key in ("human_visits", "charge_input_kwh", "fixed_service_kwh"):
            add(key, r.get(key, 0), base + "/" + key)
        if activity:
            from methane.services.activity import quantities as activity_quantities

            hours, sources = activity_quantities(r, base)
            for key in ASSETS:
                add(key + "_hours", hours.get(key, 0), sources.get(key, base + "/mission_events"))
        else:
            for key in ASSETS:
                add(key + "_hours", r.get(key + "_hours", 0), base + "/" + key + "_hours")
        for j, e in enumerate(r["resource_events"]):
            if e["kind"] != "consume":
                continue
            resource, source = e["resource"], base + f"/resource_events/{j}"
            if resource in ("crew-hours", "remote-hours"):
                add(resource, e["amount"], source)
                if resource == "crew-hours" and e["phase"] in ("travel", "return", "transfer"):
                    add("crew-travel-hours", e["amount"], source)
            elif resource.startswith(("stock:", "upstream:")):
                group, material = resource.split(":", 1)
                key = ("used:" if group == "stock" else "purchased:") + material
                add(key, e["amount"], source)
                unit_key = "unit:" + material
                if unit_key in stocks and stocks[unit_key] != e["unit"]:
                    raise ValueError("Inconsistent material ledger units")
                stocks[unit_key] = e["unit"]
        for j, e in enumerate(r.get("support_effects", [])):
            if e["kind"] == "restock":
                add("rejected:" + e["material"], e["rejected"], base + f"/support_effects/{j}")
        for s in r["state"]["executive"]["resources"]:
            if s["resource"].startswith("stock:"):
                name = s["resource"].removeprefix("stock:")
                stocks["opening:" + name] = s["initial"]
                stocks["ending:" + name] = s["ending"]
                stocks["unit:" + name] = s["unit"]
    return q, refs, present, stocks


def report(rows, assumptions, *, detailed=True):
    """Return independent views; totals are undefined when an applicable price is missing."""
    a = validate(assumptions)
    q, refs, present, stocks = quantities(rows, activity=a["schema_version"] == ACTIVITY_VERSION)
    return price_quantities(
        q,
        refs,
        present,
        stocks,
        a,
        hours=len(rows),
        trace_id=identity(rows) if detailed else None,
        detailed=detailed,
    )


def price_quantities(q, refs, present, stocks, assumptions, *, hours, trace_id=None, detailed=True):
    """Shared arithmetic over explicitly observed or projected economic operands.

    Callers must identify their quantity provenance; this function does not
    reinterpret a forecast as a recorded resource ledger.
    """
    a = validate(assumptions)
    lines, events = [], []

    def post(key, component, views, quantity, unit, rate, price_path, sources=(), formula=None):
        amount(quantity, key)
        line = dict(
            id=key,
            component=component,
            views=list(views),
            quantity=quantity,
            unit=unit,
            rate_eur=rate,
            price_path=price_path,
            sources=list(sources),
            amount_eur=0 if not quantity else None if rate is None else quantity * rate,
            formula=formula or "quantity × unit rate",
        )
        lines.append(line)
        return line["amount_eur"]

    def measured(key, component, views, rate, path, unit):
        return post(key, component, views, q.get(key, 0), unit, rate, path, refs.get(key, ()))

    pooled = {key: [] for key in ASSETS}
    material_keys = set(a["materials"]) | {
        key.split(":", 1)[1] for key in q if key.startswith(("used:", "purchased:", "rejected:"))
    }
    for key in sorted(material_keys):
        p = a["materials"].get(
            key, {"eur_per_unit": None, "unit": stocks.get("unit:" + key, "unknown"), "pool": None}
        )
        if "unit:" + key in stocks and p["unit"] != stocks["unit:" + key]:
            raise ValueError(f"Price unit does not match the ledger: {key}")
        pool = p["pool"]
        included = pool and a["assets"][pool]["provision"] != "owned"
        rate = 0 if included else p["eur_per_unit"]
        path = "/materials/" + key + "/eur_per_unit"
        used = measured(
            "used:" + key,
            pool or "service_materials",
            () if pool else ("allocated", "decision"),
            rate,
            path,
            p["unit"],
        )
        if pool:
            pooled[pool].append(used)
        purchased = measured(
            "purchased:" + key, pool or "service_materials", ("expenditure",), rate, path, p["unit"]
        )
        measured(
            "rejected:" + key,
            pool or "service_materials",
            ("allocated", "decision"),
            rate,
            path,
            p["unit"],
        )
        if q.get("purchased:" + key, 0):
            events.append(
                dict(
                    kind="procurement",
                    material=key,
                    amount_eur=purchased,
                    source_paths=refs["purchased:" + key],
                )
            )
        if a["initial_stock_purchase"]:
            post(
                "initial-stock:" + key,
                pool or "service_materials",
                ("expenditure",),
                stocks.get("opening:" + key, 0),
                p["unit"],
                rate,
                path,
                ("/rows/0/field_operations/state/executive/resources",),
            )

    for key, hours in present.items():
        p = a["assets"][key]
        prefix = "/assets/" + key + "/"
        owned = p["provision"] == "owned"
        sources = [f"/rows/*/field_operations/assets/{key}"]
        for term in (
            "capital_eur",
            "installation_eur",
            "mapping_eur",
            "access_eur",
            "payload_eur",
            "references_eur",
        ):
            value = p[term]
            if term == "capital_eur" and value is not None:
                value -= p["replaceable_capital_eur"]
            post(
                key + ":" + term,
                key,
                ("allocated",),
                hours / 8760 / p["life_years"],
                "ownership-life fraction",
                value,
                prefix + term,
                sources,
                "available hours / 8760 / life × cost; replaceable subset excluded from body",
            )
            if a["initial_asset_purchase"]:
                post(
                    key + ":purchase:" + term,
                    key,
                    ("expenditure",),
                    1,
                    "installation",
                    p[term],
                    prefix + term,
                    sources,
                )
        annual = ("scheduled_maintenance_eur_per_year", "software_communications_eur_per_year")
        for term in annual:
            post(
                key + ":" + term,
                key,
                ("allocated", "expenditure"),
                hours / 8760,
                "year",
                p[term],
                prefix + term,
                sources,
                "Time-prorated service charge, assumed billed continuously; no inferred maintenance task",
            )
        for term, quantity, unit, views in (
            ("retainer_eur_per_hour", hours, "available h", ("allocated", "expenditure")),
            ("service_eur_per_active_hour", q.get(key + "_hours", 0), "active h", VIEWS),
        ):
            post(
                key + ":" + term,
                key,
                views,
                quantity,
                unit,
                p[term],
                prefix + term,
                refs.get(key + "_hours", sources),
            )
        calendar = hours / 8760 / p["life_years"] * p["replaceable_capital_eur"]
        used = sum(pooled[key]) if all(v is not None for v in pooled[key]) else None
        use_hours = q.get(key + "_hours", 0)
        wear = (
            0
            if not use_hours
            else None
            if p["wear_eur_per_hour"] is None
            else use_hours * p["wear_eur_per_hour"]
        )
        dependent = max(wear, used) if wear is not None and used is not None else None
        allocated = max(calendar, dependent) if dependent is not None else None
        if owned:
            for view, value in (("allocated", allocated), ("decision", dependent)):
                post(
                    key + ":replaceables:" + view,
                    key,
                    (view,),
                    1,
                    "pool",
                    value,
                    prefix + "replaceable_capital_eur",
                    list(refs.get(key + "_hours", ())) + ["/materials/*/pool"],
                    "max(calendar, usage proxy, compatible parts consumed)"
                    if view == "allocated"
                    else "max(usage proxy, compatible parts consumed); excludes fixed ownership",
                )
                lines[-1]["operands"] = {
                    "calendar_eur": calendar,
                    "usage_eur": wear,
                    "parts_consumed_eur": used,
                    "part_lines": [
                        "used:" + m for m, item in a["materials"].items() if item["pool"] == key
                    ],
                }
        events.extend(
            dict(
                kind="part-use",
                asset=key,
                quantity=q.get("used:" + m, 0),
                material=m,
                provision_includes_part=not owned,
                source_paths=refs.get("used:" + m, []),
            )
            for m, item in a["materials"].items()
            if item["pool"] == key and q.get("used:" + m, 0)
        )

    for key, rate, unit in (
        ("crew-hours", "crew_eur_per_hour", "h"),
        ("remote-hours", "remote_eur_per_hour", "h"),
        ("human_visits", "callout_eur", "visit"),
        ("crew-travel-hours", "vehicle_eur_per_travel_hour", "vehicle h"),
    ):
        measured(key, "human_service", VIEWS, a["rates"][rate], "/rates/" + rate, unit)

    views = {}
    for view in VIEWS:
        selected = [line for line in lines if view in line["views"]]
        missing = [line["id"] for line in selected if line["amount_eur"] is None]
        subtotal = sum(line["amount_eur"] or 0 for line in selected)
        components = {}
        for line in selected:
            old = components.get(line["component"], 0)
            components[line["component"]] = (
                None if old is None or line["amount_eur"] is None else old + line["amount_eur"]
            )
        views[view] = dict(
            total_eur=None if missing else subtotal,
            known_subtotal_eur=subtotal,
            unpriced=missing,
            components=components,
        )
    result = dict(
        schema_version=a["schema_version"],
        assumption_id=identity(a),
        assumptions=a,
        trace_id=trace_id,
        hours=hours,
        quantities=q,
        quantity_sources=refs,
        inventories=stocks,
        lines=lines,
        events=events,
        views=views,
        status="incomplete-prices" if any(v["unpriced"] for v in views.values()) else "complete",
        basis=a["basis"],
        boundaries=[
            "Expenditure means modelled billable events under these assumptions, not observed invoices or bank payments.",
            "Pre-existing equipment and opening stocks are excluded from period expenditure unless their purchase switches are enabled; inventory remains explicit.",
            "Contract/shared provision includes hardware, payload, references, replacement parts and scheduled maintenance; site preparation, external consumables and human/vehicle work are priced separately.",
            "Replaceable capital is excluded from body ownership. Its allocation uses max(calendar, usage, used parts); decision cost uses max(usage, used parts). Procurement is a separate view, never added to allocation again.",
            "Electricity is already withdrawn from the plant bus. Production effects are in the physical trace; neither is charged again as purchased electricity or lost methane.",
            "Service charge prorating does not simulate a preventive maintenance visit. Shared provision does not by itself model another site's demand.",
        ],
    )
    if not detailed:
        for key in ("trace_id", "assumptions", "quantity_sources", "lines", "events"):
            result.pop(key, None)
    return result


def field_costs(rows, assumptions, *, detailed=False):
    """Compact compatibility port for the existing plant allocation and player."""
    result = report(rows, assumptions, detailed=detailed)
    allocated, decision = result["views"]["allocated"], result["views"]["decision"]
    return dict(
        schema_version=VERSION,
        assumption_id=result["assumption_id"],
        components=allocated["components"],
        total_eur=allocated["total_eur"],
        variable_and_wear_eur=decision["total_eur"],
        terms={},
        quantities=result["quantities"],
        unpriced=[
            dict(quantity=k, amount=None, unit="price", reason="Applicable price not supplied")
            for k in sorted({k for v in result["views"].values() for k in v["unpriced"]})
        ],
        views=result["views"],
        inventories=result["inventories"],
        status=result["status"],
        basis=result["basis"],
        boundaries=result["boundaries"],
        **({"calculation": result} if detailed else {}),
    )


def reprice_run(result, assumptions, costs=None):
    """Explicit report edition; replaces the old service subtotal, never adds both.

    This is a report on completed actions. It is not a service planning objective
    and is deliberately separate from the original saved dispatch-price identity.
    """
    from methane.config import Costs, Plant
    from methane.costing import allocation
    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE

    a = validate(assumptions)
    prices = costs or Costs(**result["config"]["costs"])
    plant = Plant(**result["config"]["plant"])
    controllers = {}
    for name, rows in result["records"].items():
        legacy = allocation(plant, prices, rows)
        services = report(rows, a)
        allocated = services["views"]["allocated"]["total_eur"]
        decision = services["views"]["decision"]["total_eur"]
        old = legacy["field_operations"]
        plant_only = legacy["total_eur"] - old["total_eur"]
        plant_decision = legacy["variable_and_wear_eur"] - old["variable_and_wear_eur"]
        total = None if allocated is None else plant_only + allocated
        variable = None if decision is None else plant_decision + decision
        methane = sum(r["applied"]["methane_kg"] for r in rows)
        controllers[name] = dict(
            allocated_eur=total,
            decision_cost_eur=variable,
            assumed_value_eur=methane * prices.methane_eur_per_kg,
            assumed_contribution_eur=None
            if variable is None
            else methane * prices.methane_eur_per_kg - variable,
            eur_per_kg_ch4=total / methane if total is not None and methane > 1e-8 else None,
            plant_allocation_excluding_services_eur=plant_only,
            plant_decision_excluding_services_eur=plant_decision,
            service_expenditure_eur=services["views"]["expenditure"]["total_eur"],
            services=services,
        )
    return dict(
        schema_version="dispatch-lab/service-cost-report/1",
        run_id=result["run_id"],
        source_content_hash=LOADED_SOURCE["content_hash"],
        source_capsule_sha256=LOADED_CAPSULE["sha256"],
        dispatch_source_content_hash=result.get("provenance", {})
        .get("source", {})
        .get("content_hash"),
        dispatch_price_version=identity(result["config"]["costs"]),
        report_price_version=identity({"plant": asdict(prices), "services": a}),
        report_costs={"plant": asdict(prices), "services": a},
        controllers=controllers,
        scope="Explicit repricing edition of recorded actions; original dispatch assumptions and physical trace are unchanged. Service expenditure is not a total plant cash-flow report.",
    )


def html_report(value):
    """Offline reading of a preserved report edition; no browser-side accounting."""
    import base64
    import html

    from methane.provenance import LOADED_FILES

    esc = html.escape
    money = lambda x: "Unpriced" if x is None else f"€{x:,.2f}"  # noqa: E731
    font = base64.b64encode(LOADED_FILES["assets/fonts/DepartureMono-Regular.woff2"]).decode()
    body = [
        '<main><p class="eyebrow">Dispatch Lab · Recorded service economics</p>',
        "<h1>What did keeping the plant operating cost?</h1>",
        "<p>Three views of the same executed work. These are illustrative assumptions applied to a saved physical trace. They do not establish the economic value of robotics; that requires matched comparison studies.</p>",
        '<p class="identity">Run '
        + esc(value["run_id"])
        + "<br>Report price identity "
        + esc(value["report_price_version"])
        + "</p>",
        "<p>" + esc(value["scope"]) + "</p>",
    ]
    for name, c in value["controllers"].items():
        s = c["services"]
        body += ["<section><h2>" + esc(name) + '</h2><div class="totals">']
        labels = {
            "allocated": (
                "Period allocation",
                "Ownership, service charges, consumable use and replaceable allowance.",
            ),
            "decision": (
                "Action-dependent costs",
                "Usage, parts and work attributable to actions; fixed ownership and retainers excluded.",
            ),
            "expenditure": (
                "Modelled service expenditure",
                "Assumed billings and procurement events. Pre-existing assets/stocks are not new purchases.",
            ),
        }
        for view, (label, note) in labels.items():
            v = s["views"][view]
            body.append(
                "<div><h3>"
                + label
                + "</h3><strong>"
                + money(v["total_eur"])
                + "</strong><p>"
                + note
                + "</p>"
            )
            if v["unpriced"]:
                body.append(
                    "<p>Known subtotal "
                    + money(v["known_subtotal_eur"])
                    + "; missing "
                    + esc(", ".join(v["unpriced"]))
                    + ".</p>"
                )
            body.append("</div>")
        body += [
            "</div><p>Total plant allocation including this service report: <b>"
            + money(c["allocated_eur"])
            + "</b>. Assumed operating contribution: <b>"
            + money(c["assumed_contribution_eur"])
            + "</b>. The old service subtotal is replaced once.</p>",
            "<h3>Work and ending resources</h3><p>Site visits "
            + str(s["quantities"].get("human_visits", 0))
            + " · crew hours "
            + f"{s['quantities'].get('crew-hours', 0):.2f}"
            + " · remote hours "
            + f"{s['quantities'].get('remote-hours', 0):.2f}"
            + "</p>",
            "<table><thead><tr><th>Material</th><th>Opening</th><th>Ending</th><th>Unit</th></tr></thead><tbody>",
        ]
        for key, opening in s["inventories"].items():
            if not key.startswith("opening:"):
                continue
            material = key.removeprefix("opening:")
            body.append(
                "<tr><td>"
                + esc(material)
                + "</td><td>"
                + f"{opening:g}"
                + "</td><td>"
                + f"{s['inventories']['ending:' + material]:g}"
                + "</td><td>"
                + esc(s["inventories"]["unit:" + material])
                + "</td></tr>"
            )
        body += ["</tbody></table><h3>Accounting boundaries</h3><ul>"]
        body += ["<li>" + esc(x) + "</li>" for x in s["boundaries"]]
        body += [
            "</ul><details><summary>Follow the calculation lines</summary><p>Every figure below was calculated in Python. Source paths identify the original interval and resource event. A maximum allowance retains its individual operands.</p>"
        ]
        for line in s["lines"]:
            if not line["quantity"]:
                continue
            body.append(
                "<article><h4>"
                + esc(line["id"])
                + " · "
                + money(line["amount_eur"])
                + "</h4><p>"
                + esc(", ".join(line["views"]) or "Operand for the replaceable pool")
                + "</p><pre>"
                + esc(json.dumps(line, indent=2))
                + "</pre></article>"
            )
        body += [
            "</details><details><summary>Original inputs and report identities</summary><pre>"
            + esc(
                json.dumps(
                    {
                        "trace_id": s["trace_id"],
                        "assumption_id": s["assumption_id"],
                        "assumptions": s["assumptions"],
                        "report_source": value["source_content_hash"],
                        "dispatch_source": value["dispatch_source_content_hash"],
                        "dispatch_price_version": value["dispatch_price_version"],
                    },
                    indent=2,
                )
            )
            + "</pre></details></section>"
        ]
    body.append("</main>")
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Recorded service economics · Dispatch Lab</title><style>'
        + "@font-face{font-family:Departure;src:url(data:font/woff2;base64,"
        + font
        + ') format("woff2")}*{box-sizing:border-box}body{margin:0;background:#20201e;color:#d5c5a8;font:14px/1.65 Departure,monospace}main{max-width:1180px;margin:auto;padding:5vw}h1,h2,h3,h4,strong,summary{color:#ffa32e}h1{font-size:30px;line-height:1.3;max-width:850px}h2{font-size:22px;margin-top:55px}h3{font-size:15px}p{max-width:950px}.eyebrow{font-size:11px;letter-spacing:.12em}.identity{font-size:11px;overflow-wrap:anywhere}.totals{display:grid;grid-template-columns:repeat(3,1fr);gap:24px;border-block:1px solid #664d29;padding:20px 0}.totals strong{font-size:28px}.totals p{font-size:12px}table{border-collapse:collapse;width:100%;font-size:12px}td,th{text-align:left;padding:8px;border-bottom:1px solid #4b402d}details{margin:24px 0;border-top:1px solid #664d29;padding-top:16px}summary{cursor:pointer}summary:focus-visible{outline:2px solid #ffa32e}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:11px/1.65 Departure,monospace}article{border-bottom:1px solid #4b402d;padding:12px 0}@media(max-width:700px){main{padding:24px 16px}.totals{grid-template-columns:1fr}h1{font-size:24px}}'
        + "</style><body>"
        + "".join(body)
        + "</body></html>"
    )


def save_report(value, directory):
    """An immutable economic edition alongside, never overwriting, the source run."""
    from pathlib import Path

    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    if (
        value["source_content_hash"] != LOADED_SOURCE["content_hash"]
        or value["source_capsule_sha256"] != LOADED_CAPSULE["sha256"]
    ):
        raise ValueError("Saving this edition requires its original loaded pricing source")
    capsule = directory / (LOADED_CAPSULE["sha256"] + ".source.json")
    encoded = json.dumps(LOADED_CAPSULE, sort_keys=True, separators=(",", ":"))
    if capsule.exists():
        if capsule.read_text() != encoded:
            raise ValueError("Preserved pricing source capsule has changed")
    else:
        with capsule.open("x") as f:
            f.write(encoded)
    identifier = identity(value)[:24]
    for suffix, text in (
        ("json", json.dumps(value, indent=2, allow_nan=False) + "\n"),
        ("html", html_report(value)),
    ):
        path = directory / (identifier + "." + suffix)
        if path.exists():
            if path.read_text() != text:
                raise ValueError("Existing report edition has different content")
        else:
            with path.open("x") as f:
                f.write(text)
    return directory / (identifier + ".html")


def main():
    import argparse
    import gzip
    from pathlib import Path

    from methane.config import Costs
    from methane.provenance import verify

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    parser.add_argument("--assumptions", type=Path)
    parser.add_argument("--directory", type=Path, default=Path("build/services/economics/reports"))
    args = parser.parse_args()
    result = verify(json.loads(gzip.decompress(args.archive.read_bytes())))
    assumptions = (
        json.loads(args.assumptions.read_text())
        if args.assumptions
        else illustrative(Costs(**result["config"]["costs"]))
    )
    print(save_report(reprice_run(result, assumptions), args.directory))


if __name__ == "__main__":
    main()
