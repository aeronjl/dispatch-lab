"""Single allocation of replaceables; marginal proxies are a separate view."""

from dataclasses import asdict

from methane.config import Costs, Plant
from methane.field_operations import costing as field_costing
from methane.physics import CO2_PER_CH4


def capital(p, c):
    return {
        "solar": p.solar_kw * c.solar_eur_per_kw,
        "battery_cells": p.battery_kwh * c.battery_eur_per_kwh,
        "battery_power": p.battery_kw * c.battery_power_eur_per_kw,
        "electrolyser": p.electrolyser_kw * c.electrolyser_eur_per_kw,
        "reactor": c.methanator_eur * p.methane_max_kgph / 10,
        "hydrogen": c.hydrogen_storage_eur * p.h2_capacity_kg / 60,
        "co2": c.co2_storage_eur * p.co2_capacity_kg / 1000,
    }


def marginal(p, c):
    cap = capital(p, c)
    return {
        "electrolyser_kw": (
            c.water_litres_per_kg / 1000 * c.water_eur_per_m3 + c.consumables_eur_per_kg
        )
        / p.specific_energy_kwh_per_kg,
        "discharge_kw": c.battery_eur_per_kwh / (p.eta * c.battery_cycles),
        "electrolyser_on": cap["electrolyser"] * c.stack_share / c.stack_operating_hours,
        "electrolyser_start": cap["electrolyser"]
        * c.stack_share
        / c.stack_operating_hours
        * c.start_equivalent_hours,
        "reactor_on": cap["reactor"] * c.reactor_replaceable_share / c.reactor_operating_hours,
        "reactor_start": cap["reactor"]
        * c.reactor_replaceable_share
        / c.reactor_operating_hours
        * c.reactor_start_equivalent_hours,
        "methane_kg": CO2_PER_CH4 * c.co2_eur_per_kg,
    }


def decision_cost(p, c, rows, *, service_economics=None, service_report=None):
    rates = marginal(p, c)
    total = 0
    for r in rows:
        a = r["applied"]
        total += sum(a.get(k, 0) * v for k, v in rates.items())
        if r.get("lifecycle"):
            total -= a["electrolyser_kw"] * rates["electrolyser_kw"]
            total += r["h2_produced_kg"] * (
                c.water_litres_per_kg / 1000 * c.water_eur_per_m3 + c.consumables_eur_per_kg
            )
        total += rates["electrolyser_on"] * r["state"]["electrolyser_on"]
        total += rates["reactor_on"] * r["state"]["reactor_on"]
        total += rates["electrolyser_start"] * r["electrolyser_start"]
        total += rates["reactor_start"] * r["reactor_start"]
    if service_report is None:
        service_report = service_costs(c, rows, service_economics)
    service_total = service_report["variable_and_wear_eur"]
    total = None if service_total is None else total + service_total
    if total is not None and any(r.get("lifecycle") for r in rows):
        from methane.lifecycle.accounting import decision_adjustment

        total += decision_adjustment(p, c, rows)
    methane = sum(r["applied"]["methane_kg"] for r in rows)
    return {
        "variable_and_wear_eur": total,
        "assumed_value_eur": methane * c.methane_eur_per_kg,
        "assumed_contribution_eur": None
        if total is None
        else methane * c.methane_eur_per_kg - total,
    }


def service_costs(c, rows, assumptions=None, *, detailed=False, prefix=None):
    if assumptions is None:
        return field_costing(c, rows)
    from methane.service_economics import field_costs

    if prefix:
        from methane.siting.period_costs import services

        return services(rows, assumptions, prefix, detailed=detailed)
    return field_costs(rows, assumptions, detailed=detailed)


def allocation(p, c, rows, *, with_lineage=False, service_economics=None, service_prefix=None):
    cap = capital(p, c)
    hours, y = len(rows), len(rows) / 8760
    total = lambda k: sum(r[k] for r in rows)  # noqa: E731
    discharge = sum(r["applied"]["discharge_kw"] for r in rows)
    ely_hours = sum(r["state"]["electrolyser_on"] for r in rows)
    reactor_hours = sum(r["state"]["reactor_on"] for r in rows)
    stack, replaceable = (
        cap["electrolyser"] * c.stack_share,
        cap["reactor"] * c.reactor_replaceable_share,
    )
    battery_calendar = cap["battery_cells"] / c.battery_calendar_years * y
    battery_usage = discharge * marginal(p, c)["discharge_kw"]
    stack_calendar = stack / c.stack_calendar_years * y
    stack_usage = (
        stack
        / c.stack_operating_hours
        * (ely_hours + total("electrolyser_start") * c.start_equivalent_hours)
    )
    reactor_calendar = replaceable / c.methane_assets_years * y
    reactor_usage = (
        replaceable
        / c.reactor_operating_hours
        * (reactor_hours + total("reactor_start") * c.reactor_start_equivalent_hours)
    )
    incidents = sum(r.get("incident", False) for r in rows)
    charged_incidents = sum(
        r.get("incident", False)
        for r in rows
        if r.get("intervention_accounting", "legacy-alarm-allowance/1")
        == "legacy-alarm-allowance/1"
    )
    field = service_costs(c, rows, service_economics, detailed=with_lineage, prefix=service_prefix)
    water = total("h2_produced_kg") * c.water_litres_per_kg / 1000
    components = {
        "solar": cap["solar"] / c.solar_years * y,
        "battery": max(battery_calendar, battery_usage)
        + cap["battery_power"] / c.other_equipment_years * y,
        "electrolyser": max(stack_calendar, stack_usage)
        + (cap["electrolyser"] - stack) / c.other_equipment_years * y
        + water * c.water_eur_per_m3
        + total("h2_produced_kg") * c.consumables_eur_per_kg
        + charged_incidents * (c.repair_eur_per_incident + c.visit_eur_per_incident),
        "reactor": max(reactor_calendar, reactor_usage)
        + (cap["reactor"] - replaceable) / c.methane_assets_years * y,
        "hydrogen": cap["hydrogen"] / c.methane_assets_years * y,
        "co2": cap["co2"] / c.methane_assets_years * y
        + total("co2_consumed_kg") * c.co2_eur_per_kg,
        "site": (sum(cap.values()) * c.installation_fraction + c.site_setup_eur)
        / c.other_equipment_years
        * y
        + c.fixed_opex_eur_per_year * y,
    }
    components.update(field["components"])
    lifecycle = None
    if any(r.get("lifecycle") for r in rows):
        from methane.lifecycle.accounting import allocation_adjustments

        adjustment, lifecycle = allocation_adjustments(
            p,
            c,
            cap,
            rows,
            {"stack": [stack_calendar, stack_usage, max(stack_calendar, stack_usage)]},
        )
        for key, amount in adjustment.items():
            components[key] = components.get(key, 0) + amount
    value = None if any(v is None for v in components.values()) else sum(components.values())
    methane = sum(r["applied"]["methane_kg"] for r in rows)
    result = {
        "hours": hours,
        **({"lifecycle": lifecycle} if lifecycle else {}),
        "components": components,
        "total_eur": value,
        "eur_per_kg_ch4": value / methane if value is not None and methane > 1e-8 else None,
        "water_input_m3": water,
        "incidents": incidents,
        "charged_incidents": charged_incidents,
        "field_operations": field,
        "allowances": {
            "battery": [battery_calendar, battery_usage, max(battery_calendar, battery_usage)],
            "stack": [stack_calendar, stack_usage, max(stack_calendar, stack_usage)],
            "reactor": [reactor_calendar, reactor_usage, max(reactor_calendar, reactor_usage)],
        },
        **decision_cost(p, c, rows, service_report=field),
    }

    if with_lineage:
        result["lineage"] = allocation_lineage(p, c, rows, cap, result)
    return result


_SAVED = object()


def reprice(result, costs=None, *, service_economics=_SAVED):
    c = costs or Costs(**result["config"]["costs"])
    p = Plant(**result["config"]["plant"])
    from methane.provenance import LOADED_SOURCE, digest

    if service_economics is _SAVED:
        service_economics = result["config"].get("service_economics")
    if service_economics is not None:
        from methane.service_economics import validate

        service_economics = validate(service_economics)

    return {
        "schema_version": "dispatch-lab/cost-report/4"
        if service_economics is not None
        else "dispatch-lab/cost-report/3",
        "report_source_content_hash": LOADED_SOURCE["content_hash"],
        "dispatch_source_content_hash": result.get("provenance", {})
        .get("source", {})
        .get("content_hash"),
        "report_price_version": digest(asdict(c)),
        "dispatch_price_version": digest(
            result.get("controller_config", result["config"])["costs"]
        ),
        "dispatch_costs": result.get("controller_config", result["config"])["costs"].copy(),
        "service_economics": service_economics,
        "report_service_price_version": digest(service_economics)
        if service_economics is not None
        else None,
        "dispatch_service_price_version": digest(result["config"]["service_economics"])
        if result["config"].get("service_economics") is not None
        else None,
        "run_id": result["run_id"],
        "costs": asdict(c),
        "capital": capital(p, c),
        "basis": "Illustrative EUR; allocated cost and marginal decision proxies are separate",
        "controllers": {
            name: [
                allocation(
                    p,
                    c,
                    rows[:i],
                    service_economics=service_economics,
                    service_prefix=result.get("service_accounting_prefix"),
                )
                for i in range(len(rows) + 1)
            ]
            for name, rows in result["records"].items()
        },
    }


def allocation_lineage(p, c, rows, cap, result):
    """Capture the numerical allocation's operands and formulae, not an attribution score."""
    nodes = []

    def add(key, value, unit, source, parents=(), formula=None):
        nodes.append(
            dict(
                id=key,
                value=value,
                unit=unit,
                source=source,
                parents=list(parents),
                formula=formula,
            )
        )

    for group, values in (("plant", asdict(p)), ("prices", asdict(c))):
        for key, value in values.items():
            add(group + "." + key, value, "parameter", f"/{group}/{key}")
    add("hours", len(rows), "h", "/rows", "", "Number of recorded one-hour intervals")
    add("years", len(rows) / 8760, "year", "derived", ("hours",), "hours / 8760")
    quantities = {
        "discharge": (
            "applied/discharge_kw",
            sum(r["applied"]["discharge_kw"] for r in rows),
            "kWh",
        ),
        "electrolyser_hours": (
            "state/electrolyser_on",
            sum(r["state"]["electrolyser_on"] for r in rows),
            "h",
        ),
        "reactor_hours": ("state/reactor_on", sum(r["state"]["reactor_on"] for r in rows), "h"),
        "electrolyser_starts": (
            "electrolyser_start",
            sum(r["electrolyser_start"] for r in rows),
            "count",
        ),
        "reactor_starts": ("reactor_start", sum(r["reactor_start"] for r in rows), "count"),
        "h2": ("h2_produced_kg", sum(r["h2_produced_kg"] for r in rows), "kg"),
        "co2_used": ("co2_consumed_kg", sum(r["co2_consumed_kg"] for r in rows), "kg"),
        "methane": ("applied/methane_kg", sum(r["applied"]["methane_kg"] for r in rows), "kg"),
        "incidents": ("incident", sum(r.get("incident", False) for r in rows), "count"),
    }
    for key, (path, value, unit) in quantities.items():
        add(
            key,
            value,
            unit,
            "/rows/*/" + path,
            (),
            "Sum over the selected recorded interval range; exact source field is retained",
        )
    add(
        "charged_incidents",
        result["charged_incidents"],
        "count",
        "/rows/*/incident",
        (),
        "Count incident only for legacy-alarm-allowance/1 rows; zero for recorded-work/1",
    )
    capitals = {
        "solar": ("plant.solar_kw", "prices.solar_eur_per_kw"),
        "battery_cells": ("plant.battery_kwh", "prices.battery_eur_per_kwh"),
        "battery_power": (
            "plant.battery_kwh",
            "plant.battery_c_rate",
            "prices.battery_power_eur_per_kw",
        ),
        "electrolyser": ("plant.electrolyser_kw", "prices.electrolyser_eur_per_kw"),
        "reactor": ("plant.methane_max_kgph", "prices.methanator_eur"),
        "hydrogen": ("plant.h2_capacity_kg", "prices.hydrogen_storage_eur"),
        "co2": ("plant.co2_capacity_kg", "prices.co2_storage_eur"),
    }
    for key, parents in capitals.items():
        divisor = {"reactor": 10, "hydrogen": 60, "co2": 1000}.get(key, 1)
        add("capital." + key, cap[key], "EUR", "derived", parents, f"product(parents) / {divisor}")
    allowance_parents = {
        "battery": (
            "capital.battery_cells",
            "years",
            "prices.battery_calendar_years",
            "discharge",
            "prices.battery_eur_per_kwh",
            "plant.roundtrip_efficiency",
            "prices.battery_cycles",
        ),
        "stack": (
            "capital.electrolyser",
            "prices.stack_share",
            "years",
            "prices.stack_calendar_years",
            "electrolyser_hours",
            "electrolyser_starts",
            "prices.start_equivalent_hours",
            "prices.stack_operating_hours",
        ),
        "reactor": (
            "capital.reactor",
            "prices.reactor_replaceable_share",
            "years",
            "prices.methane_assets_years",
            "reactor_hours",
            "reactor_starts",
            "prices.reactor_start_equivalent_hours",
            "prices.reactor_operating_hours",
        ),
    }
    formulas = {
        "battery": (
            "capital.battery_cells × years / prices.battery_calendar_years",
            "discharge × prices.battery_eur_per_kwh / (sqrt(plant.roundtrip_efficiency) × prices.battery_cycles)",
        ),
        "stack": (
            "capital.electrolyser × prices.stack_share × years / prices.stack_calendar_years",
            "capital.electrolyser × prices.stack_share × (electrolyser_hours + electrolyser_starts × prices.start_equivalent_hours) / prices.stack_operating_hours",
        ),
        "reactor": (
            "capital.reactor × prices.reactor_replaceable_share × years / prices.methane_assets_years",
            "capital.reactor × prices.reactor_replaceable_share × (reactor_hours + reactor_starts × prices.reactor_start_equivalent_hours) / prices.reactor_operating_hours",
        ),
    }
    for key, (calendar, usage, charged) in result["allowances"].items():
        for part, value, formula in zip(
            ("calendar", "usage"), (calendar, usage), formulas[key], strict=True
        ):
            add(f"allowance.{key}.{part}", value, "EUR", "derived", allowance_parents[key], formula)
        add(
            f"allowance.{key}.charged",
            charged,
            "EUR",
            "derived",
            (f"allowance.{key}.calendar", f"allowance.{key}.usage"),
            "max(calendar, usage); charged once",
        )
    component_formulas = {
        "solar": (
            "capital.solar * years / prices.solar_years",
            ("capital.solar", "years", "prices.solar_years"),
        ),
        "battery": (
            "allowance.battery.charged + capital.battery_power * years / prices.other_equipment_years",
            (
                "allowance.battery.charged",
                "capital.battery_power",
                "years",
                "prices.other_equipment_years",
            ),
        ),
        "electrolyser": (
            "allowance.stack.charged + capital.electrolyser*(1-prices.stack_share)*years/prices.other_equipment_years + h2*prices.water_litres_per_kg/1000*prices.water_eur_per_m3 + h2*prices.consumables_eur_per_kg + charged_incidents*(prices.repair_eur_per_incident+prices.visit_eur_per_incident)",
            (
                "allowance.stack.charged",
                "capital.electrolyser",
                "prices.stack_share",
                "years",
                "prices.other_equipment_years",
                "h2",
                "prices.water_litres_per_kg",
                "prices.water_eur_per_m3",
                "prices.consumables_eur_per_kg",
                "charged_incidents",
                "prices.repair_eur_per_incident",
                "prices.visit_eur_per_incident",
            ),
        ),
        "reactor": (
            "allowance.reactor.charged + capital.reactor*(1-prices.reactor_replaceable_share)*years/prices.methane_assets_years",
            (
                "allowance.reactor.charged",
                "capital.reactor",
                "prices.reactor_replaceable_share",
                "years",
                "prices.methane_assets_years",
            ),
        ),
        "hydrogen": (
            "capital.hydrogen*years/prices.methane_assets_years",
            ("capital.hydrogen", "years", "prices.methane_assets_years"),
        ),
        "co2": (
            "capital.co2*years/prices.methane_assets_years + co2_used*prices.co2_eur_per_kg",
            (
                "capital.co2",
                "years",
                "prices.methane_assets_years",
                "co2_used",
                "prices.co2_eur_per_kg",
            ),
        ),
        "site": (
            "(sum(capital)*prices.installation_fraction+prices.site_setup_eur)*years/prices.other_equipment_years + prices.fixed_opex_eur_per_year*years",
            tuple("capital." + k for k in cap)
            + (
                "prices.installation_fraction",
                "prices.site_setup_eur",
                "years",
                "prices.other_equipment_years",
                "prices.fixed_opex_eur_per_year",
            ),
        ),
    }
    service_lines = result["field_operations"].get("calculation", {}).get("lines", [])
    for line in service_lines:
        lid = "service." + line["id"]
        add(lid + ".quantity", line["quantity"], line["unit"], line["sources"])
        add(lid + ".rate", line["rate_eur"], "EUR/unit", "/service_economics" + line["price_path"])
        add(
            lid,
            line["amount_eur"],
            "EUR",
            "derived",
            (lid + ".quantity", lid + ".rate"),
            line["formula"],
        )
        if line.get("operands"):
            nodes[-1]["operands"] = line["operands"]
    if service_lines:
        for key in result["field_operations"]["components"]:
            component_formulas[key] = (
                "sum(service allocation lines)",
                tuple(
                    "service." + line["id"]
                    for line in service_lines
                    if line["component"] == key and "allocated" in line["views"]
                ),
            )
    for asset, terms in result["field_operations"]["terms"].items():
        # All operands are retained alongside the exact per-interval usage records.
        ids = []
        for key, value in terms.items():
            term_id = f"field.{asset}.{key}"
            add(
                term_id,
                value,
                "h" if key == "owned_hours" else "EUR",
                "/rows/*/field_operations",
                tuple("prices." + k for k in asdict(c)),
                "field_operations.costing; quantities and price operands retained",
            )
            if key not in (
                "capital_eur",
                "owned_hours",
                "replaceable_calendar_eur",
                "replaceable_usage_eur",
            ):
                ids.append(term_id)
        component_formulas[asset] = (
            "sum(charged terms); max(calendar, usage) replaceables once",
            tuple(ids),
        )
    if result["field_operations"].get("period_difference"):
        for key, operands in result["field_operations"]["period_difference"]["components"].items():
            parents = []
            for side in ("before", "after"):
                node = "service_period." + key + "." + side
                add(
                    node,
                    operands[side],
                    "EUR",
                    "/service_accounting_prefix and recorded period",
                    (),
                    "Cumulative service allocation at the named boundary under original prices",
                )
                parents.append(node)
            component_formulas[key] = (
                "after − before; cumulative wear pool retained",
                tuple(parents),
            )
    if result.get("lifecycle"):
        for key, amount in result["lifecycle"]["allocation_adjustments"].items():
            identity = "lifecycle.adjustment." + key
            add(
                identity,
                amount,
                "EUR",
                "/rows/*/lifecycle/accounting",
                (),
                "Difference of cumulative allocation pools; max(wear, calendar, consumed parts), never their sum. Construction invoices replace the declared installation share and accrue allocation from their date.",
            )
            nodes[-1]["operands"] = result["lifecycle"]["allocation_boundary"]
            formula, parents = component_formulas.get(key, ("0", ()))
            component_formulas[key] = (formula + " + " + identity, (*parents, identity))
    for key, value in result["components"].items():
        formula, parents = component_formulas[key]
        add("allocation." + key, value, "EUR", "derived", parents, formula)
    add(
        "allocated_total",
        result["total_eur"],
        "EUR",
        "derived",
        tuple("allocation." + k for k in result["components"]),
        "sum(component allocations)",
    )
    add(
        "unit_cost",
        result["eur_per_kg_ch4"],
        "EUR/kg CH₄",
        "derived",
        ("allocated_total", "methane"),
        "allocated_total / methane; undefined at zero output",
    )
    rates = marginal(p, c)
    operands = [n["id"] for n in nodes if n["id"].startswith(("plant.", "prices.", "capital."))]
    contributions = []
    paths = {
        "electrolyser_on": "state/electrolyser_on",
        "reactor_on": "state/reactor_on",
        "electrolyser_start": "electrolyser_start",
        "reactor_start": "reactor_start",
    }
    for key, rate in rates.items():
        add(
            "rate." + key,
            rate,
            "EUR/unit",
            "derived",
            operands,
            "marginal() variable input or usage allowance; fixed ownership excluded",
        )
        path = paths.get(key, "applied/" + key)
        quantity = sum(
            (
                r["applied"].get(key, 0)
                if key not in paths
                else r["state"][key]
                if path.startswith("state/")
                else r[key]
            )
            for r in rows
        )
        qid = "decision_quantity." + key
        add(
            qid,
            quantity,
            "unit",
            "/rows/*/" + path,
            (),
            "Sum of the indicated recorded hourly field",
        )
        cid = "decision_cost." + key
        contributions.append(cid)
        add(cid, quantity * rate, "EUR", "derived", (qid, "rate." + key), "quantity × rate")
    if result["field_operations"]["components"]:
        add(
            "decision_cost.services",
            result["field_operations"]["variable_and_wear_eur"],
            "EUR",
            "/rows/*/field_operations",
            tuple("service." + line["id"] for line in service_lines if "decision" in line["views"])
            if service_lines
            else tuple(
                "field." + a + "." + k
                for a, t in result["field_operations"]["terms"].items()
                for k in t
            ),
            "Sum of service decision lines; excludes fixed ownership and standing charges"
            if service_lines
            else "Robot usage wear + cleaning consumables + actual human visit, labour and kits; excludes ownership and standing maintenance",
        )
        contributions.append("decision_cost.services")
    if result.get("lifecycle"):
        from methane.lifecycle.accounting import decision_adjustment

        correction = sum(
            r["h2_produced_kg"]
            * (c.water_litres_per_kg / 1000 * c.water_eur_per_m3 + c.consumables_eur_per_kg)
            - r["applied"]["electrolyser_kw"] * rates["electrolyser_kw"]
            for r in rows
            if r.get("lifecycle")
        )
        add(
            "decision_cost.lifecycle",
            decision_adjustment(p, c, rows) + correction,
            "EUR",
            "/rows/*/lifecycle/accounting and h2_produced_kg",
            (),
            "Use actual hydrogen input consumption; replace wear with max(wear, consumed parts); add project maintenance resources. Excludes construction capital and opening stock cash.",
        )
        contributions.append("decision_cost.lifecycle")
    add(
        "decision_cost",
        result["variable_and_wear_eur"],
        "EUR",
        "derived",
        contributions,
        "sum(action-sensitive costs); separate from allocated total",
    )
    add(
        "assumed_value",
        result["assumed_value_eur"],
        "EUR",
        "derived",
        ("methane", "prices.methane_eur_per_kg"),
        "methane × assumed price",
    )
    add(
        "contribution",
        result["assumed_contribution_eur"],
        "EUR",
        "derived",
        ("assumed_value", "decision_cost"),
        "assumed value − action-sensitive costs",
    )
    return dict(
        schema_version="dispatch-lab/cost-ledger/1",
        nodes=nodes,
        plant=asdict(p),
        prices=asdict(c),
        row_count=len(rows),
    )
