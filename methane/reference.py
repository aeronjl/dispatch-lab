"""Independent hourly reference: standard library only, no production-model imports.

Uses 42-digit Decimal arithmetic, explicit rounded molecular weights and a
separately derived thermal solution. It verifies the declared illustrative
model, not plant calibration. Stored residuals and component audits are ignored.
"""

import argparse
import gzip
import hashlib
import json
import math
import runpy
from datetime import datetime, timedelta
from decimal import Decimal, localcontext
from pathlib import Path

VERSION = "dispatch-lab/reference/2"


def D(value):
    result = Decimal(int(value) if isinstance(value, bool) else str(value))
    if not result.is_finite():
        raise ValueError("Reference input must be finite")
    return result


def initial(p, ambient):
    return dict(
        battery_kwh=p["battery_kwh"] * p["initial_soc"],
        h2_kg=p["initial_h2_kg"],
        co2_kg=p["initial_co2_kg"],
        temperature_c=ambient,
        electrolyser_on=False,
        reactor_on=False,
        commitment_hours=0,
    )


def interval(p, before, action, pv, ambient, delivery, service_kw=0):
    """Reference output for one hourly interval. No clipping/corrective allocation."""
    if p["dt_hours"] != 1:
        raise ValueError("Reference plant checker requires hourly intervals")
    with localcontext() as context:
        context.prec = 42
        q = {k: D(v) for k, v in p.items()}
        b = {k: D(v) for k, v in before.items()}
        a = {k: D(v) for k, v in action.items()}
        on = a["electrolyser_kw"] > D("0.00001")
        running = a["methane_kg"] > D("0.00001")
        start_e, start_r = (
            on and not before["electrolyser_on"],
            running and not before["reactor_on"],
        )
        eta = q["roundtrip_efficiency"].sqrt()
        cell_in, cell_out = eta * a["charge_kw"], a["discharge_kw"] / eta
        energy = b["battery_kwh"] + cell_in - cell_out
        loss = a["charge_kw"] - cell_in + cell_out - a["discharge_kw"]
        h2 = a["electrolyser_kw"] / q["specific_energy_kwh_per_kg"]
        # CO2 + 4 H2 -> CH4 + 2 H2O; MW = 44, 2, 16, 18 kg/kmol.
        extent = a["methane_kg"] / 16
        hydrogen_used, co2_used, water = extent * 4 * 2, extent * 44, extent * 2 * 18
        accepted = min(D(delivery), q["co2_capacity_kg"] - b["co2_kg"])
        reaction = extent * D(165000) / 3600
        net_heat = a["heater_kw"] + reaction - a["cooling_kw"]
        c, ua, amb = q["thermal_capacity_kwh_per_k"], q["heat_loss_kw_per_k"], D(ambient)
        if ua:
            equilibrium = amb + net_heat / ua
            temperature = equilibrium + (b["temperature_c"] - equilibrium) * (-ua / c).exp()
        else:
            temperature = b["temperature_c"] + net_heat / c
        heat_loss = net_heat - c * (temperature - b["temperature_c"])
        startup = D(start_e) * q["start_energy_kwh"]
        demand = (
            a["electrolyser_kw"]
            + startup
            + a["heater_kw"]
            + a["cooling_kw"] * q["cooling_electric_fraction"]
            + D(running) * q["auxiliary_kw"]
            + a["methane_kg"] * q["methane_electric_kwh_per_kg"]
            + D(service_kw)
        )
        commitment = (
            max(0, (p["minimum_run_hours"] if start_r else before["commitment_hours"]) - 1)
            if running
            else 0
        )
        state = dict(
            battery_kwh=float(energy),
            h2_kg=float(b["h2_kg"] + h2 - hydrogen_used),
            co2_kg=float(b["co2_kg"] + accepted - co2_used),
            temperature_c=float(temperature),
            electrolyser_on=on,
            reactor_on=running,
            commitment_hours=commitment,
        )
        flows = dict(
            h2_produced_kg=h2,
            h2_consumed_kg=hydrogen_used,
            co2_consumed_kg=co2_used,
            co2_delivered_kg=accepted,
            co2_rejected_kg=D(delivery) - accepted,
            water_produced_kg=water,
            electrolysis_stoichiometric_water_kg=h2 * 9,
            startup_kwh=startup,
            battery_loss_kwh=loss,
            reaction_heat_kwh=reaction,
            heat_loss_kwh=heat_loss,
            demand_kw=demand,
            curtailed_kwh=D(pv) + a["discharge_kw"] - a["charge_kw"] - demand,
            electrolyser_start=D(start_e),
            reactor_start=D(start_r),
        )
        return {"state": state, "applied": dict(action), **{k: float(v) for k, v in flows.items()}}


def service_accounts(prices, rows):
    """Independent Decimal event accounting; no production economic adapter imports."""
    records = [r["field_operations"] for r in rows if "field_operations" in r]
    events = [e for r in records for e in r["resource_events"] if e["kind"] == "consume"]
    zero = D(0)

    def quantity(resource):
        return sum((D(e["amount"]) for e in events if e["resource"] == resource), zero)

    def product(q, rate):
        return zero if not q else None if rate is None else D(q) * D(rate)

    def add(*values):
        return None if any(v is None for v in values) else sum(values, zero)

    def maximum(*values):
        return None if any(v is None for v in values) else max(values)

    allocated, dependent, cash, pools = {}, zero, zero, {}

    def charge(component, value):
        allocated[component] = add(allocated.get(component, zero), value)

    material_names = set(prices["materials"]) | {
        e["resource"].split(":", 1)[1]
        for e in events
        if e["resource"].startswith(("stock:", "upstream:"))
    }
    for material in material_names:
        p = prices["materials"].get(material, {"pool": None, "eur_per_unit": None})
        pool, rate = p["pool"], p["eur_per_unit"]
        if pool and prices["assets"][pool]["provision"] != "owned":
            rate = 0
        used = product(quantity("stock:" + material), rate)
        rejected_q = sum(
            (
                D(e["rejected"])
                for r in records
                for e in r.get("support_effects", [])
                if e["kind"] == "restock" and e["material"] == material
            ),
            zero,
        )
        rejected = product(rejected_q, rate)
        cash = add(cash, product(quantity("upstream:" + material), rate))
        if prices["initial_stock_purchase"] and records:
            initial = next(
                (
                    D(s["initial"])
                    for s in records[0]["state"]["executive"]["resources"]
                    if s["resource"] == "stock:" + material
                ),
                zero,
            )
            cash = add(cash, product(initial, rate))
        charge(pool or "service_materials", rejected)
        dependent = add(dependent, rejected)
        if pool:
            pools[pool] = add(pools.get(pool, zero), used)
        else:
            charge("service_materials", used)
            dependent = add(dependent, used)
    for key, p in prices["assets"].items():
        hours = D(sum(bool(r["assets"].get(key)) for r in records))
        if not hours:
            continue
        if prices["schema_version"] == "dispatch-lab/service-economics/2":
            asset_ids = {
                "cleaner": "PLANT-01/CLEAN-01",
                "rover": "PLANT-01/ROVER-01",
                "dock": "PLANT-01/DOCK-01",
                "reset": "PLANT-01/ELY-01/RESET",
                "fixed_reader": "PLANT-01/ELY-01/CONTACT",
                "portable": "SERVICE/PORTABLE-CLEAN-01",
            }
            active = sum(
                (
                    D(e["end"]) - D(e["start"])
                    for r in records
                    for e in r["mission_events"]
                    if e["kind"] == "interval" and e["asset_id"] == asset_ids[key]
                ),
                zero,
            )
        else:
            active = sum((D(r.get(key + "_hours", 0)) for r in records), zero)
        fraction = hours / D(8760) / D(p["life_years"])
        body = (
            None
            if p["capital_eur"] is None
            else D(p["capital_eur"]) - D(p["replaceable_capital_eur"])
        )
        capital = add(
            body,
            *(
                None if p[k] is None else D(p[k])
                for k in (
                    "installation_eur",
                    "mapping_eur",
                    "access_eur",
                    "payload_eur",
                    "references_eur",
                )
            ),
        )
        charge(key, product(fraction, capital))
        if prices["initial_asset_purchase"]:
            cash = add(cash, capital, D(p["replaceable_capital_eur"]))
        annual = add(
            *(
                product(hours / 8760, p[k])
                for k in (
                    "scheduled_maintenance_eur_per_year",
                    "software_communications_eur_per_year",
                )
            )
        )
        retainer = product(hours, p["retainer_eur_per_hour"])
        operating = product(active, p["service_eur_per_active_hour"])
        charge(key, add(annual, retainer, operating))
        cash = add(cash, annual, retainer, operating)
        dependent = add(dependent, operating)
        if p["provision"] == "owned":
            wear = maximum(product(active, p["wear_eur_per_hour"]), pools.get(key, zero))
            dependent = add(dependent, wear)
            charge(key, maximum(fraction * D(p["replaceable_capital_eur"]), wear))
    rates = prices["rates"]
    travel = sum(
        (
            D(e["amount"])
            for e in events
            if e["resource"] == "crew-hours" and e["phase"] in ("travel", "return", "transfer")
        ),
        zero,
    )
    labour = add(
        product(quantity("crew-hours"), rates["crew_eur_per_hour"]),
        product(quantity("remote-hours"), rates["remote_eur_per_hour"]),
        product(sum((D(r["human_visits"]) for r in records), zero), rates["callout_eur"]),
        product(travel, rates["vehicle_eur_per_travel_hour"]),
    )
    charge("human_service", labour)
    return dict(
        components=allocated,
        allocated=add(*allocated.values()),
        decision=add(dependent, labour),
        expenditure=add(cash, labour),
    )


def economics(p, c, rows, service_economics=None):
    """Separate economic ledger; no use of production capital/marginal/allocation."""
    with localcontext() as context:
        context.prec = 42
        p, c = {k: D(v) for k, v in p.items()}, {k: D(v) for k, v in c.items()}
        hours, fraction = D(len(rows)), D(len(rows)) / 8760

        def total(key):
            return sum((D(r[key]) for r in rows), D(0))

        solar = p["solar_kw"] * c["solar_eur_per_kw"]
        cells = p["battery_kwh"] * c["battery_eur_per_kwh"]
        converter = p["battery_kwh"] * p["battery_c_rate"] * c["battery_power_eur_per_kw"]
        ely = p["electrolyser_kw"] * c["electrolyser_eur_per_kw"]
        reactor = c["methanator_eur"] * p["methane_max_kgph"] / 10
        hydrogen = c["hydrogen_storage_eur"] * p["h2_capacity_kg"] / 60
        co2 = c["co2_storage_eur"] * p["co2_capacity_kg"] / 1000
        stack = ely * c["stack_share"]
        catalyst = reactor * c["reactor_replaceable_share"]
        discharge = sum((D(r["applied"]["discharge_kw"]) for r in rows), D(0))
        ely_hours = sum((D(r["state"]["electrolyser_on"]) for r in rows), D(0))
        reactor_hours = sum((D(r["state"]["reactor_on"]) for r in rows), D(0))
        battery_wear = (
            discharge
            / p["roundtrip_efficiency"].sqrt()
            * c["battery_eur_per_kwh"]
            / c["battery_cycles"]
        )
        stack_wear = (
            stack
            * (ely_hours + total("electrolyser_start") * c["start_equivalent_hours"])
            / c["stack_operating_hours"]
        )
        reactor_wear = (
            catalyst
            * (reactor_hours + total("reactor_start") * c["reactor_start_equivalent_hours"])
            / c["reactor_operating_hours"]
        )
        consumables = total("h2_produced_kg") * c["consumables_eur_per_kg"]
        water_m3 = total("h2_produced_kg") * c["water_litres_per_kg"] / 1000
        water_cost = water_m3 * c["water_eur_per_m3"]
        feed = total("co2_consumed_kg") * c["co2_eur_per_kg"]
        incidents = sum(bool(r.get("incident")) for r in rows)
        charged_incidents = sum(
            bool(r.get("incident"))
            for r in rows
            if r.get("intervention_accounting", "legacy-alarm-allowance/1")
            == "legacy-alarm-allowance/1"
        )
        parts = {
            "solar": solar * fraction / c["solar_years"],
            "battery": max(cells * fraction / c["battery_calendar_years"], battery_wear)
            + converter * fraction / c["other_equipment_years"],
            "electrolyser": max(stack * fraction / c["stack_calendar_years"], stack_wear)
            + (ely - stack) * fraction / c["other_equipment_years"]
            + consumables
            + water_cost
            + charged_incidents * (c["repair_eur_per_incident"] + c["visit_eur_per_incident"]),
            "reactor": max(catalyst * fraction / c["methane_assets_years"], reactor_wear)
            + (reactor - catalyst) * fraction / c["methane_assets_years"],
            "hydrogen": hydrogen * fraction / c["methane_assets_years"],
            "co2": co2 * fraction / c["methane_assets_years"] + feed,
            "site": (
                (solar + cells + converter + ely + reactor + hydrogen + co2)
                * c["installation_fraction"]
                + c["site_setup_eur"]
            )
            * fraction
            / c["other_equipment_years"]
            + c["fixed_opex_eur_per_year"] * fraction,
        }
        variable = battery_wear + stack_wear + reactor_wear + consumables + water_cost + feed
        process_parts, process_variable = dict(parts), variable
        service_rows = [r["field_operations"] for r in rows if "field_operations" in r]

        def usage(key):
            return sum((D(r.get(key, 0)) for r in service_rows), D(0))

        for asset in ("cleaner", "rover", "dock", "fixed_reader", "reset"):
            owned = sum(r["assets"].get(asset, False) for r in service_rows)
            if not owned:
                continue
            base = c[asset + "_eur"] * D(owned) / 8760 / c["field_asset_years"]
            share = c["field_replaceable_share"] if asset in ("cleaner", "rover") else D(0)
            wear = usage(asset + "_hours") * c.get(asset + "_wear_eur_per_hour", D(0))
            supplies = (
                (usage("cleaning_kits_used") - usage("portable_kits_used")) * c["cleaning_kit_eur"]
                if asset == "cleaner"
                else D(0)
            )
            standing = (
                D(len(service_rows)) / 8760 * c["field_maintenance_eur_per_year"]
                if asset == "dock"
                else D(0)
            )
            parts[asset] = base * (1 - share) + max(base * share, wear) + supplies + standing
            variable += wear + supplies
        if service_rows:
            service = (
                usage("human_visits") * c["visit_eur_per_incident"]
                + usage("service_kits_used") * c["repair_eur_per_incident"]
                + usage("calibration_kits_used") * c.get("calibration_kit_eur", D(0))
                + usage("human_hours") * c["human_service_eur_per_hour"]
                + usage("portable_kits_used") * c["cleaning_kit_eur"]
            )
            parts["human_service"] = service
            variable += service
        service_views = None
        if service_economics is not None:
            service_views = service_accounts(service_economics, rows)
            parts = {**process_parts, **service_views["components"]}
            variable = (
                None
                if service_views["decision"] is None
                else process_variable + service_views["decision"]
            )
        life = [r["lifecycle"]["accounting"] for r in rows if r.get("lifecycle")]
        if life:
            a, b = life[0]["before"], life[-1]["after"]

            def period_fraction(s):
                return D(s["hours"]) / 8760

            def wear(s):
                return (
                    stack
                    / c["stack_operating_hours"]
                    * (
                        D(s["electrolyser_hours"])
                        + D(s["electrolyser_starts"]) * c["start_equivalent_hours"]
                    )
                )

            def pool(s, asset, calendar):
                return max(
                    calendar * period_fraction(s),
                    wear(s) if asset == "electrolyser" else D(0),
                    D(s["consumed_parts"].get(asset, 0)),
                )

            if "solar" in life[0]["condition_assets"]:
                parts["solar"] += (
                    pool(b, "solar", solar / c["solar_years"])
                    - pool(a, "solar", solar / c["solar_years"])
                    - solar * fraction / c["solar_years"]
                )
            if "electrolyser" in life[0]["condition_assets"]:
                parts["electrolyser"] += (
                    pool(b, "electrolyser", stack / c["stack_calendar_years"])
                    - pool(a, "electrolyser", stack / c["stack_calendar_years"])
                    - max(stack * fraction / c["stack_calendar_years"], stack_wear)
                )
            parts["project_service"] = D(b["maintenance_eur"]) - D(a["maintenance_eur"])
            scope = life[0]["construction_fractions"]
            basis = (
                sum(
                    D(scope[k]) * v
                    for k, v in (
                        ("solar", solar),
                        ("battery", cells + converter),
                        ("electrolyser", ely),
                        ("reactor", reactor),
                    )
                )
                * c["installation_fraction"]
            )
            parts["site"] += (
                (
                    D(b["construction_eur_hours"])
                    - D(a["construction_eur_hours"])
                    - basis * D(len(rows))
                )
                / c["other_equipment_years"]
                / 8760
            )

            def dependent(s):
                return (
                    D(s["maintenance_eur"])
                    + D(s["consumed_parts"].get("solar", 0))
                    + max(wear(s), D(s["consumed_parts"].get("electrolyser", 0)))
                )

            if variable is not None:
                variable += dependent(b) - dependent(a) - wear(b) + wear(a)
        methane = sum((D(r["applied"]["methane_kg"]) for r in rows), D(0))
        value = methane * c["methane_eur_per_kg"]
        allocated = None if any(v is None for v in parts.values()) else sum(parts.values())
        return {
            "components": {k: float(v) if v is not None else None for k, v in parts.items()},
            "total_eur": float(allocated) if allocated is not None else None,
            "variable_and_wear_eur": float(variable) if variable is not None else None,
            "assumed_value_eur": float(value),
            "assumed_contribution_eur": float(value - variable) if variable is not None else None,
            "water_input_m3": float(water_m3),
            "eur_per_kg_ch4": float(allocated / methane)
            if allocated is not None and methane > D("1e-8")
            else None,
            "incidents": incidents,
            "hours": int(hours),
            **(
                {
                    "service_views": {
                        k: None if v is None else float(v)
                        for k, v in service_views.items()
                        if k != "components"
                    }
                }
                if service_views
                else {}
            ),
        }


def optical_reference(parameters, sample, timestamp):
    """Independent scalar implementation of the documented section equations."""
    design = json.loads(parameters["design_json"])
    instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00")) + timedelta(minutes=30)
    day = instant.timetuple().tm_yday
    b = math.radians(360 * (day - 81) / 364)
    correction = 9.87 * math.sin(2 * b) - 7.53 * math.cos(b) - 1.5 * math.sin(b)
    hour_angle = math.radians(
        15
        * (instant.hour + instant.minute / 60 + parameters["longitude"] / 15 + correction / 60 - 12)
    )
    declination = math.radians(23.45 * math.sin(math.radians(360 * (284 + day) / 365)))
    latitude = math.radians(parameters["latitude"])
    up = math.sin(latitude) * math.sin(declination) + math.cos(latitude) * math.cos(
        declination
    ) * math.cos(hour_angle)
    east = -math.cos(declination) * math.sin(hour_angle)
    south = math.sin(latitude) * math.cos(declination) * math.cos(hour_angle) - math.cos(
        latitude
    ) * math.sin(declination)

    def plane(tilt, azimuth):
        t, z = math.radians(tilt), math.radians(azimuth)
        projection = max(
            0,
            -east * math.sin(t) * math.sin(z)
            + south * math.sin(t) * math.cos(z)
            + up * math.cos(t),
        )
        return 0.7 * projection / max(0.1, up) + 0.3 * (1 + math.cos(t)) / 2

    base = max(0.05, plane(parameters["tilt"], parameters["azimuth"]))
    radiation, ambient = sample["irradiance_wm2"], sample["ambient_c"]
    total = 0
    for section in design["sections"]:
        orientation = (
            plane(section["tilt"], section["azimuth"]) / base
            if up > 0
            else (1 + math.cos(math.radians(section["tilt"])))
            / (1 + math.cos(math.radians(parameters["tilt"])))
        )
        light = radiation * orientation * (1 - section["shade"]) * (1 - section["soiling"])
        temperature = ambient + (design["noct_c"] - 20) * light / 800
        watts = (
            section["capacity_kw"]
            * light
            / 1000
            * max(0, 1 + parameters["temperature_coefficient"] * (temperature - 25))
            * (1 - parameters["loss_fraction"])
        )
        total += watts if section["online"] else 0
    ref_temp = ambient + (parameters["noct_c"] - 20) * radiation / 800
    ref = min(
        parameters["solar_kw"],
        max(
            0,
            parameters["solar_kw"]
            * radiation
            / 1000
            * (1 - parameters["loss_fraction"])
            * max(0, 1 + parameters["temperature_coefficient"] * (ref_temp - 25)),
        ),
    )
    stressed = (
        total
        * (sample["pv_kw"] / ref if ref > 1e-8 else 1)
        * sample.get("lifecycle_factor", 1)
        * design["efficiency"]
    )
    return min(design["converter_kw"], stressed), max(0, stressed - design["converter_kw"])


def surface_reference(patches, operation):
    """Independent decimal interval-partition treatment of uniform initial strips."""
    low, high = D(operation["start_m2"]), D(operation["end_m2"])
    start_eff, end_eff = D(operation["efficacy_start"]), D(operation["efficacy_end"])
    result = []
    for start, end, loose, adhered, damaged in patches:
        boundaries = sorted({start, end, max(start, min(end, low)), max(start, min(end, high))})
        for a, b in zip(boundaries, boundaries[1:], strict=False):
            dose = (
                start_eff + (end_eff - start_eff) * ((a + b) / 2 - low) / (high - low)
                if a < high and b > low
                else D(0)
            )
            attached = (
                adhered * (1 - D(operation.get("adhered_removal", 0)))
                if a < high and b > low
                else adhered
            )
            result.append((a, b, loose * (1 - dose), attached, damaged))
    return result


def stock_bounds(checks, key, stock, capacity, unit, *, controller=None, hour=None):
    """Measure overrun in resource units, including replay rounding at zero.

    Decimal replay is exact for the rounded recorded operands, not for the
    producer's unrounded floating-point intermediates. A Boolean comparison
    would turn a tiny replay residual into a unit-sized failure. Keep the
    independent tolerance unchanged and report the actual boundary error.
    """
    compare(
        checks,
        "service.stock_bounds:" + key,
        max(D(0), -D(stock), D(stock) - D(capacity)),
        D(0),
        unit,
        controller=controller,
        hour=hour,
    )


def compare(checks, name, actual, expected, unit="", *, controller=None, hour=None):
    """Independent declared tolerance, not imported from the production audit."""
    if isinstance(expected, Decimal):
        expected = float(expected)
    if isinstance(actual, Decimal):
        actual = float(actual)
    try:
        residual = float(actual) - float(expected)
        tolerance = 1e-5 + 1e-8 * max(1, abs(float(expected)))
        passed = math.isfinite(residual) and abs(residual) <= tolerance
    except (TypeError, ValueError, OverflowError):
        residual, tolerance, passed = None, 1e-5, actual is None and expected is None
    checks.append(
        dict(
            check=name,
            controller=controller,
            hour=hour,
            passed=passed,
            residual=residual if residual is None or math.isfinite(residual) else None,
            expected=None
            if isinstance(expected, float) and not math.isfinite(expected)
            else expected,
            actual=None if isinstance(actual, float) and not math.isfinite(actual) else actual,
            unit=unit,
            tolerance=tolerance,
        )
    )


def check_actions(p, before, row, capacity, requested=None):
    checks = []

    def bounded(name, value, low, high, unit):
        compare(checks, name, max(low - value, value - high, 0), 0, unit)

    a, s = row["applied"], row["state"]
    for k, upper in (
        ("battery_kwh", p["battery_kwh"]),
        ("h2_kg", p["h2_capacity_kg"]),
        ("co2_kg", p["co2_capacity_kg"]),
    ):
        bounded(k, s[k], 0, upper, "kWh" if k == "battery_kwh" else "kg")
    for key, maximum, minimum in (
        ("charge_kw", p["battery_kwh"] * p["battery_c_rate"], 0),
        ("discharge_kw", p["battery_kwh"] * p["battery_c_rate"], 0),
        ("electrolyser_kw", capacity, p["electrolyser_kw"] * p["min_load_fraction"]),
        ("heater_kw", p["heater_max_kw"], 0),
        ("cooling_kw", p["cooling_max_kw"], 0),
        ("methane_kg", p["methane_max_kgph"], p["methane_min_kgph"]),
    ):
        bounded(
            key,
            a[key],
            minimum if a[key] > 1e-5 else 0,
            maximum,
            "kg" if key == "methane_kg" else "kW",
        )
        if requested is not None:
            bounded("requested_limit_" + key, a[key], 0, requested[key], "action")
    bounded("unused_energy", row["curtailed_kwh"], 0, math.inf, "kWh")
    compare(checks, "exclusive_battery", min(a["charge_kw"], a["discharge_kw"]), 0, "kW")
    compare(checks, "exclusive_thermal", min(a["heater_kw"], a["cooling_kw"]), 0, "kW")
    if s["reactor_on"]:
        for label, temp in (("begin", before["temperature_c"]), ("end", s["temperature_c"])):
            bounded(
                "production_temperature_" + label,
                temp,
                p["temperature_min_c"],
                p["temperature_max_c"],
                "°C",
            )
    if "forced_trip" in row:
        expected = not s["reactor_on"] and bool(
            before["commitment_hours"] or (requested or a)["methane_kg"] >= p["methane_min_kgph"]
        )
        compare(checks, "forced_trip", row["forced_trip"], expected, "boolean")
    return checks


def executed_service_spans(plan, options, visit_members=()):
    """Retrospective independent clocks from original recipe and actual factors.

    This reference is never a controller input. Public reservation spans retain
    their separate meaning and are checked by the existing reservation audits.
    """

    def stages(p):
        timing = p.get("timing")
        if not timing:
            return [(s, D(s["duration_hours"])) for s in p["stages"]]
        return [
            (
                s,
                D(s["duration_hours"])
                * D(
                    p.get("_reference_factors", {}).get(g, options.get(g + "_time_factor", 1))
                    if g
                    else 1
                ),
            )
            for s, g in zip(timing["nominal_stages"], timing["groups"], strict=True)
        ]

    start = D(plan["starting_at"])
    if plan.get("timing") and visit_members:
        start = D(visit_members[0]["starting_at"])
        for member in visit_members:
            if member["order"]["order_id"] == plan["order"]["order_id"]:
                break
            start += sum((d for _, d in stages(member)), D(0))
    for stage, duration in stages(plan):
        end = start + duration
        yield start, end, stage
        start = end


class InspectionReference:
    """Independent contact arithmetic, availability and evidence selection.

    Rebuilds packets from the declared physical fault inputs and named random
    stream, never from recorded classifications or production sensing code.
    """

    def __init__(self, config, *, commissioned_only=False):
        self.config = config
        self.o = config["service_system"]
        self.commissioned_only = commissioned_only
        self.packets = []
        self.missions = {}
        self.contact_procedures = []

    def classify(self, raw):
        a, z, b = (raw[k] for k in ("signal", "zero", "span"))
        if None in (a, z, b):
            return None, "unavailable", None, None
        a, z, b = D(a), D(z), D(b)
        corrected = 24 * (a - z) / (b - z) if b > z else None
        if abs(z) > D(self.o["inspection_zero_limit_v"]) or abs(b - z - 24) > 24 * D(
            self.o["inspection_span_tolerance_fraction"]
        ):
            return None, "uncertain", corrected, False
        value = (
            False
            if corrected <= D(self.o["inspection_low_v"])
            else True
            if corrected >= D(self.o["inspection_high_v"])
            else None
        )
        return value, "usable" if value is not None else "uncertain", corrected, True

    def interval(self, service, samples, hour, cleared, checks, controller):
        def ck(label, actual, expected, unit=""):
            if isinstance(expected, str):
                actual, expected = actual == expected, True
            compare(
                checks,
                "inspection." + label,
                actual,
                expected,
                unit,
                controller=controller,
                hour=hour,
            )

        self.missions.update({m["order"]["order_id"]: m for m in service["new_missions"]})
        for event in service["mission_events"]:
            if (
                event["kind"] == "stage_end"
                and event["phase"] == "perform"
                and self.missions[event["order_id"]]["order"]["action"]
                in ("reset", "module-replacement")
            ):
                self.contact_procedures.append(event["at_hour"])
        f, s = self.config["faults"], self.config["scenario"]
        fault_active = hour >= s["fault_start_hour"] and (
            f["lifecycle"] == "persistent"
            or hour < s["fault_start_hour"] + s["fault_duration_hours"]
        )
        latched = (
            fault_active
            and not cleared
            and s["capacity_fraction"] < 1
            and f["capacity_cause"] == "resettable-trip"
        )
        for trace in samples:
            reader, at, key = trace["reader"], trace["measured_at"], trace["order_id"]
            mission = self.missions[key]
            ck("sample_capability", mission["order"]["action"], "read-trip-contact")
            end = next(b for _, b, s in executed_service_spans(mission, self.o) if s["effect"])
            ck("sample_time", at, end, "h")
            ck("sample_interval", hour < at <= hour + 1, True)
            ck(
                "reader_platform",
                reader,
                "fixed" if mission["asset"]["mobility"] == "fixed" else "mobile",
            )
            active = hour >= f["inspection_fault_start_hour"]
            stuck = f["contact_stuck"] if active else "none"
            signal = 24 if (latched if stuck == "none" else stuck == "closed") else 0
            offset = (
                D(f[reader + "_reader_offset_v"])
                + max(D(0), D(at) - D(f["inspection_fault_start_hour"]))
                * D(f[reader + "_reader_drift_vph"])
                if active
                else D(0)
            )
            dropout = bool(active and f[reader + "_reader_dropout"])
            for k, v in dict(
                signal_v=signal, offset_v=offset, dropout=dropout, contact_stuck=stuck
            ).items():
                ck("physical." + k, trace["physical"][k], v)
            raw = {}
            for channel, base in (("signal", signal), ("zero", 0), ("span", 24)):
                token = f"referenced-contact/1/{s['seed']}/{reader}/{at:.12g}/{channel}"
                u = int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big") / 2**64
                error = (2 * u - 1) * math.sqrt(3) * self.o["inspection_noise_v"]
                raw[channel] = None if dropout else D(base) + offset + D(error)
                ck("noise." + channel, trace["noise_v"][channel], error, "V")
                ck("raw." + channel, trace["raw_v"][channel], raw[channel], "V")
            value, quality, corrected, reference_ok = self.classify(raw)
            ck("classified_value", trace["interpretation"]["value"], value)
            ck("classified_quality", trace["interpretation"]["quality"], quality)
            ck("corrected", trace["interpretation"]["corrected_v"], corrected, "V")
            ck("reference_ok", trace["interpretation"]["reference_ok"], reference_ok)
            available = math.ceil(at + self.o["inspection_delay_hours"])
            ck("publication", trace["available_at"], available, "h")
            source = f"referenced-contact/1/{reader}/{key}"
            self.packets.append(
                dict(
                    reader=reader,
                    order_id=key,
                    measured_at=at,
                    available_at=available,
                    raw=raw,
                    value=value,
                    quality=quality,
                    corrected=corrected,
                    reference_ok=reference_ok,
                    source_id=source,
                )
            )
        for tag, now in (("decision", hour), ("state", hour + 1)):
            view = service[tag]
            report = view["inspection"]
            ck(
                tag + ".evidence_model",
                report["model"],
                "commissioned-contact-evidence/1"
                if self.commissioned_only
                else "referenced-contact/1",
            )
            ck(tag + ".clock", report["at_hour"], now, "h")
            cutoff = max((t for t in self.contact_procedures if math.ceil(t) <= now), default=None)
            ck(tag + ".intervention_cutoff", report["invalidated_through_hour"], cutoff, "h")
            observed = [
                r
                for r in view["executive"]["observations"]
                if r["source_id"].startswith("referenced-contact/1/")
            ]
            eligible = [p for p in self.packets if p["available_at"] <= now]
            ck(tag + ".packet_count", len(observed), len(eligible) * 4)
            for p in eligible:
                expected_values = {
                    "contact-" + k + ":" + p["reader"]: v for k, v in p["raw"].items()
                }
                expected_values["trip-contact:" + p["reader"]] = p["value"]
                for channel, expected in expected_values.items():
                    found = [
                        r
                        for r in observed
                        if r["source_id"] == p["source_id"] and r["channel"] == channel
                    ]
                    ck(tag + ".observation_count", len(found), 1)
                    if found:
                        r = found[0]
                        ck(tag + ".value", r["value"], expected)
                        ck(tag + ".measured", r["measured_at"], p["measured_at"], "h")
                        ck(tag + ".available", r["available_at"], p["available_at"], "h")
                        ck(
                            tag + ".units",
                            r["unit"],
                            "boolean" if channel.startswith("trip-") else "V",
                        )
                        ck(
                            tag + ".quality",
                            r["quality"],
                            p["quality"]
                            if channel.startswith("trip-")
                            else "unavailable"
                            if expected is None
                            else "usable",
                        )
            work = [q for q in view["orders"] if q["kind"] in ("inspection", "inspection-confirm")]
            if work:
                incident = max(work, key=lambda q: q["created_hour"])["incident"]
                work = [q for q in work if q["incident"] == incident]
            readers = (
                ("fixed", "mobile")
                if self.o["inspector"] == "both"
                else (self.o["inspector"],)
                if self.o["inspector"] != "none"
                else ()
            )
            if self.o.get("inspection_interface") == "enclosed-contact":
                readers = ()
            if self.commissioned_only:
                commissioned = {
                    q.get(
                        "reader",
                        "fixed"
                        if q["kind"] == "inspection" and self.o["inspector"] in ("fixed", "both")
                        else "mobile",
                    )
                    for q in work
                }
                readers = tuple(r for r in readers if r in commissioned)
            ck(tag + ".channel_count", len(report["channels"]), len(readers))
            valid = []
            pending = False
            isolated = []
            for reader in readers:
                ids = {q["id"] for q in work if q["reader"] == reader}
                packets = [p for p in eligible if p["order_id"] in ids]
                p = max(packets, key=lambda x: x["measured_at"], default=None)
                quality = (
                    "missing"
                    if p is None
                    else "stale"
                    if (cutoff is not None and p["measured_at"] <= cutoff)
                    or now - p["measured_at"] > self.o["contact_max_age_hours"]
                    else p["quality"]
                )
                value = p["value"] if quality == "usable" else None
                found = next((c for c in report["channels"] if c["reader"] == reader), None)
                if found is None:
                    ck(tag + ".missing_expected_reader", False, True)
                    continue
                ck(tag + ".channel_quality", found["quality"], quality)
                ck(tag + ".channel_value", found["value"], value)
                if p is not None:
                    ck(tag + ".reference_ok", found["reference_ok"], p["reference_ok"])
                    ck(tag + ".acquisition_quality", found["acquisition_quality"], p["quality"])
                    for operand, expected in p["raw"].items():
                        ck(tag + ".display." + operand, found["raw_v"][operand], expected, "V")
                    ck(tag + ".display.corrected", found["corrected_v"], p["corrected"], "V")
                    ck(tag + ".display.measured", found["measured_at"], p["measured_at"], "h")
                    ck(tag + ".display.available", found["available_at"], p["available_at"], "h")
                    ck(tag + ".display.source", found["source_id"], p["source_id"])
                pending |= quality in ("missing", "stale")
                pending |= quality == "uncertain" and p is not None and p["reference_ok"] is True
                if quality == "usable":
                    valid.append(value)
                if p is not None and (p["reference_ok"] is False or p["quality"] == "unavailable"):
                    isolated.append(reader)
            usable = bool(valid) and not pending and all(v == valid[0] for v in valid)
            ck(tag + ".fusion_quality", report["quality"], "usable" if usable else "uncertain")
            ck(tag + ".fusion_value", report["value"], valid[0] if usable else None)
            ck(tag + ".isolation", report["isolated_readers"] == isolated, True)
        for mission in service["new_missions"]:
            if mission["order"]["action"] == "reset":
                report = service["decision"]["inspection"]
                ck(
                    "reset_evidence",
                    report["quality"] == "usable" and report["value"] is True,
                    True,
                )


class VisitReference:
    """Independent itinerary, reservation, interruption and callout accounting."""

    def __init__(self, config):
        self.o, self.f = config["service_system"], config["field_operations"]
        self.plans, self.visits, self.members = {}, {}, {}
        self.ends, self.finished, self.stopped, self.released = {}, {}, {}, {}

    def interval(self, record, hour, checks, controller):
        def ck(label, actual, expected=True, unit="boolean"):
            compare(
                checks, "visit." + label, actual, expected, unit, controller=controller, hour=hour
            )

        new = {p["order"]["order_id"]: p for p in record["new_missions"]}
        self.plans.update(new)
        reserves = {e["mission_id"]: e for e in record["resource_events"] if e["kind"] == "reserve"}
        for v in record.get("new_visits", []):
            key, jobs = v["visit_id"], v["members"]
            ck("unique_visit", key not in self.visits)
            self.visits[key] = v
            ck("implementation", v["implementation_id"] == "crew-visit/1")
            ck("member_count", 2 <= len(jobs) <= self.o["visit_max_jobs"])
            ids = [p["order"]["order_id"] for p in jobs]
            ck("unique_members", len(set(ids)) == len(ids))
            first, last = jobs[0], jobs[-1]
            start, at, point = D(first["starting_at"]), D(hour), first["asset"]["home"]
            end = D(last["starting_at"]) + sum(
                (D(s["duration_hours"]) for s in last["stages"]), D(0)
            )
            opening = (start // D(self.o["crew_period_hours"])) * D(
                self.o["crew_period_hours"]
            ) + D(self.o["crew_shift_start_hour"])
            ck(
                "whole_shift",
                opening <= start and end <= opening + D(self.o["crew_shift_duration_hours"]),
            )
            accompanying = {}
            for index, p in enumerate(jobs):
                job = p["order"]["order_id"]
                ck("unshared_job", job not in self.members)
                self.members[job] = (key, index)
                # The optional event envelope is checked separately against accepted
                # requests; the underlying versioned Visit still contains MissionPlans.
                core = {
                    k: value for k, value in new.get(job, {}).items() if k != "stochastic_event"
                }
                ck("recorded_member", job in new and core == p)
                ck(
                    "one_context",
                    p["context"] == first["context"] and p["context"]["at_hour"] == hour,
                )
                ck(
                    "departure_lead",
                    start >= D(p["order"]["requested_at"]) + D(self.o["crew_response_lead_hours"]),
                )
                ck("contiguous_start", p["starting_at"], at, "h")
                a = p["asset"]
                ck(
                    "human_crew",
                    a["autonomy"] == "human"
                    and a["mobility"] == "crew"
                    and a["home"] == first["asset"]["home"],
                )
                owned = [
                    {"resource": "asset:" + a["asset_id"], "amount": 1, "unit": "slot"},
                    *a["support_resources"],
                ]
                ck("same_crew", v["crew_resource"] in {q["resource"] for q in owned})
                for q in owned:
                    if q["resource"] in accompanying:
                        ck("consistent_tool", accompanying[q["resource"]] == q)
                    accompanying[q["resource"]] = q
                required = {}
                for number, s in enumerate(p["stages"]):
                    ck("route_continuity", s["from_point"] == point)
                    point = s["to_point"]
                    if point == first["asset"]["home"]:
                        ck(
                            "single_home_return",
                            index == len(jobs) - 1 and number == len(p["stages"]) - 1,
                        )
                    duration = D(s["duration_hours"])
                    if s["phase"] in ("travel", "return"):
                        expected = (
                            self.o["crew_travel_hours"]
                            if first["asset"]["home"] in (s["from_point"], s["to_point"])
                            else self.o["travel_hours"]
                            if any(
                                x.startswith("recovery/") for x in (s["from_point"], s["to_point"])
                            )
                            else self.o["crew_transfer_hours"]
                        )
                        ck(
                            "declared_transfer_duration",
                            duration,
                            D(expected) * D(p["timing"]["bounds"][number][1])
                            if p.get("timing")
                            else expected,
                            "h",
                        )
                        ck(
                            "travel_has_no_work",
                            not s["effect"]
                            and (
                                p["timing"]["nominal_stages"][number]["bus_kw"]
                                if p.get("timing")
                                else s["bus_kw"]
                            )
                            == s["battery_kw"]
                            == 0,
                        )
                    if s["effect"]:
                        action = p["order"]["action"]
                        expected = {
                            "module-replacement": self.f["human_work_hours"],
                            "flow-calibration": self.f["human_work_hours"],
                            "restock": self.o["support_delivery_hours"],
                            "retrieve": self.o["support_delivery_hours"],
                            "replace-brush": self.o["brush_change_hours"],
                        }.get(action)
                        if action == "routine-service":
                            expected = D(self.o["maintenance_work_hours"])
                        if action == "portable-clean-section":
                            area = next(
                                x["area_m2"]
                                for x in record["state"]["surface"]["sections"]
                                if x["id"] == p["interface"]["target_asset_id"]
                            )
                            expected = D(area) / D(self.o["portable_area_m2ph"])
                        ck(
                            "declared_work_duration",
                            duration,
                            D(expected) * D(p["timing"]["bounds"][number][1])
                            if p.get("timing")
                            else expected,
                            "h",
                        )
                    for q in s["consumables"]:
                        resource = (q["resource"], q["unit"])
                        required[resource] = required.get(resource, D(0)) + D(q["amount"])
                    for q in s["hourly_consumables"]:
                        resource = (q["resource"], q["unit"])
                        required[resource] = (
                            required.get(resource, D(0)) + D(q["amount"]) * duration
                        )
                    ck(
                        "one_crew_rate",
                        sum(
                            D(q["amount"])
                            for q in s["hourly_consumables"]
                            if q["resource"] == "crew-hours"
                        ),
                        1,
                        "h/h",
                    )
                    at += duration
                if p["order"]["deadline"] is not None:
                    ck("return_deadline", end <= D(p["order"]["deadline"]))
                reserved = reserves.get(job, {})
                ck("atomic_member_reservation", bool(reserved) and reserved["at_hour"] == hour)
                actual = {}
                for q in reserved.get("stocks", []):
                    resource = (q["resource"], q["unit"])
                    actual[resource] = actual.get(resource, D(0)) + D(q["amount"])
                ck("complete_resource_set", set(actual) == set(required))
                for resource, amount in required.items():
                    ck("reserved_" + resource[0], actual.get(resource), amount, resource[1])
                ck(
                    "no_duplicate_crew_booking",
                    not any(
                        b["resource"] == v["crew_resource"] for b in reserved.get("capacity", [])
                    ),
                )
            ck("returned_location", point == first["asset"]["home"])
            reserved = reserves.get(key, {})
            ck("atomic_visit_reservation", bool(reserved) and reserved["at_hour"] == hour)
            if any(p.get("timing") for p in jobs):
                for p in jobs:
                    for stage in p["stages"]:
                        if stage["bus_kw"] > accompanying.get("plant:service-power", {}).get(
                            "amount", 0
                        ):
                            accompanying["plant:service-power"] = dict(
                                resource="plant:service-power", amount=stage["bus_kw"], unit="kW"
                            )
                        for q in stage["reservations"]:
                            old = accompanying.get(q["resource"])
                            if old is None or q["amount"] > old["amount"]:
                                accompanying[q["resource"]] = q
            expected = sorted(
                (q["resource"], float(start), float(end), q["amount"], q["unit"])
                for q in accompanying.values()
            )
            actual = sorted(
                (b["resource"], b["start"], b["end"], b["amount"], b["unit"])
                for b in reserved.get("capacity", [])
            )
            ck("whole_visit_assets_and_tools", actual == expected)
        visits_count = 0
        events = sorted(
            record["mission_events"],
            key=lambda e: (e.get("at_hour", e.get("start")), 0 if e["kind"] == "stage_end" else 1),
        )
        for e in events:
            key = e["order_id"]
            p = self.plans[key]
            member = self.members.get(key)
            if (
                e["kind"] == "stage_start"
                and e["phase"] == "travel"
                and p["asset"]["autonomy"] == "human"
            ):
                visits_count += int(
                    member is None
                    or e["at_hour"] == self.visits[member[0]]["members"][0]["starting_at"]
                )
            if member is None:
                continue
            if e["kind"] == "interrupted":
                self.stopped[key] = e["at_hour"]
            if e["kind"] == "stage_start":
                ck("no_work_after_interruption", key not in self.stopped)
                if member[1]:
                    previous = self.visits[member[0]]["members"][member[1] - 1]["order"]["order_id"]
                    ck(
                        "preceding_job_executed",
                        previous in self.finished and self.finished[previous] <= e["at_hour"],
                    )
            if e["kind"] == "stage_end":
                count = self.ends.get(key, 0)
                ck("stage_count", count < len(p["stages"]))
                if count < len(p["stages"]):
                    expected = D(p["starting_at"]) + sum(
                        (D(s["duration_hours"]) for s in p["stages"][: count + 1]), D(0)
                    )
                    if p.get("timing"):
                        expected = list(
                            executed_service_spans(p, self.o, self.visits[member[0]]["members"])
                        )[count][1]
                    ck("stage_end", e["at_hour"], expected, "h")
                    ck("stage_order", e["phase"] == p["stages"][count]["phase"])
                    self.ends[key] = count + 1
                    if count + 1 == len(p["stages"]):
                        self.finished[key] = e["at_hour"]
        ck("one_callout_per_departure", record["human_visits"], visits_count, "count")
        for e in record["resource_events"]:
            if e["kind"] == "release" and e["mission_id"] in self.visits:
                ck("single_envelope_release", e["mission_id"] not in self.released)
                self.released[e["mission_id"]] = e["at_hour"]
        reports = record["state"]["executive"].get("visits", [])
        ck("visible_visit_count", len(reports), len(self.visits), "count")
        for key, v in self.visits.items():
            found = next((x for x in reports if x["visit_id"] == key), {})
            ids = [p["order"]["order_id"] for p in v["members"]]
            unfinished = [x for x in ids if x not in self.finished]
            stopped = [self.stopped[x] for x in ids if x in self.stopped]
            returned = self.finished[ids[-1]] if not unfinished else None
            ck("visible_members", found.get("members") == ids)
            for p, shown in zip(v["members"], found.get("planned_jobs", []), strict=False):
                ck("visible_job_start", shown["starting_at"], p["starting_at"], "h")
                expected = D(p["starting_at"]) + sum(
                    (D(s["duration_hours"]) for s in p["stages"]), D(0)
                )
                ck("visible_job_end", shown["ending_at"], expected, "h")
                ck(
                    "visible_job_identity",
                    shown["order_id"] == p["order"]["order_id"]
                    and shown["action"] == p["order"]["action"]
                    and shown["target"] == p["interface"]["target_asset_id"],
                )
            ck("visible_job_count", len(found.get("planned_jobs", [])), len(ids), "count")
            end = D(v["members"][-1]["starting_at"]) + sum(
                (D(s["duration_hours"]) for s in v["members"][-1]["stages"]), D(0)
            )
            ck("planned_return", found.get("planned_return_at"), end, "h")
            ck(
                "planned_crew_hours",
                found.get("planned_crew_hours"),
                end - D(v["members"][0]["starting_at"]),
                "h",
            )
            ck("visible_backlog", found.get("unfinished") == unfinished)
            ck("return_receipt", found.get("returned_at"), returned, "h")
            release = min(stopped) if stopped else returned
            ck("envelope_release_time", self.released.get(key), release, "h")
            if stopped:
                ck("interrupted_status", found.get("status") == "interrupted")


def service_variate(seed, event, channel):
    """Independently reconstruct the documented 53-bit service-event fraction."""
    if event.get("model") != "target-action-request/1":
        raise ValueError("Unknown service event model")
    if type(event.get("request")) is not int or event["request"] < 1:
        raise ValueError("Invalid service event ordinal")
    operands = [event["model"], seed, event["target"], event["action"], event["request"], channel]
    message = json.dumps(operands, ensure_ascii=True, separators=(",", ":")).encode()
    integer = int(hashlib.sha256(message).hexdigest()[:16], 16) // 2048
    return float(Decimal(integer) / Decimal(9007199254740992))


class ServiceRandomReference:
    """Accepted-request numbering, private draws and realised procedure thresholds."""

    def __init__(self, config):
        self.seed = config["scenario"]["seed"]
        self.options, self.config = config["service_system"], config["field_operations"]
        self.cause = config["faults"]["capacity_cause"]
        self.counts, self.events, self.draws = {}, {}, {}

    def interval(self, record, truth, hour, checks, controller):
        def check(label, passed):
            compare(
                checks, "service_random." + label, passed, True, controller=controller, hour=hour
            )

        check("private_draws_recorded", "service_randomness" in truth)
        check(
            "no_public_variates",
            "random_draws" not in record and "service_randomness" not in record["decision"],
        )
        for plan in record["new_missions"]:
            order = plan["order"]
            if order["action"].startswith("charge-"):
                continue
            key = (plan["interface"]["target_asset_id"], order["action"])
            check("unique_accepted_request", order["order_id"] not in self.events)
            number = self.counts.get(key, 0) + 1
            self.counts[key] = number
            expected = dict(
                model="target-action-request/1", target=key[0], action=key[1], request=number
            )
            check("accepted_identity", plan.get("stochastic_event") == expected)
            self.events[order["order_id"]] = expected
        for plan in record["decision"].get("planned_missions", []):
            check(
                "planned_identity",
                plan.get("stochastic_event") == self.events.get(plan["order"]["order_id"]),
            )
        for order in record["state"]["orders"]:
            check("public_identity", order.get("stochastic_event") == self.events.get(order["id"]))
        for draw in truth.get("service_randomness", []):
            event = self.events.get(draw["order_id"])
            check("draw_has_accepted_request", event is not None)
            if event is None:
                continue
            check("draw_identity", draw["event"] == event)
            check("draw_interval", draw["first_used_hour"] == hour)
            key = (draw["order_id"], draw["channel"])
            check("draw_recorded_once", key not in self.draws)
            expected = service_variate(self.seed, event, draw["channel"])
            check("exact_variate", draw["uniform"] == expected and 0 <= draw["uniform"] < 1)
            self.draws[key] = expected
        for effect in truth.get("service_effects", []):
            kind, order = effect["kind"], effect["order_id"]
            if kind == "hardware-procedure":
                check("hardware_draw_present", (order, "hardware-procedure") in self.draws)
                continue  # HardwareReference independently checks its outcome and compatibility.
            if kind not in ("reset", "module-replacement", "flow-calibration"):
                continue
            draw = self.draws.get((order, "repair"))
            check("procedure_draw_present", draw is not None)
            if draw is None:
                continue
            passed = draw < self.config["repair_success_probability"]
            check("procedure_threshold", effect.get("procedure_passed") is passed)
            clears_capacity = passed and (
                kind == "module-replacement"
                or (kind == "reset" and self.cause == "resettable-trip")
            )
            clears_flow = passed and kind == "flow-calibration"
            for field, cleared in (
                ("capacity_fault_active", clears_capacity),
                ("flow_fault_active", clears_flow),
            ):
                check(
                    "procedure_" + field,
                    effect["after"][field] == (effect["before"][field] and not cleared),
                )
        for reading in record["state"]["executive"]["observations"]:
            source = reading["source_id"]
            if source.startswith(("supervised-drive-test/1:", "supervised-drive-test/2:")):
                draw = self.draws.get((source.rsplit(":", 1)[-1], "drive-test"))
                check("drive_draw_present", draw is not None)
                if draw is not None and source.startswith("supervised-drive-test/1:"):
                    check(
                        "drive_threshold",
                        reading["value"] is (draw < self.options["robot_test_success_probability"]),
                    )


class HardwareReference:
    """Independent declared-fault lifecycle, procedure and observation reconstruction."""

    def __init__(self, config, manifest):
        self.o, self.f, self.c = (
            config["service_system"],
            config["faults"],
            config["field_operations"],
        )
        self.assets = manifest["asset_ids"]
        self.independent = self.f.get("hardware_model") == "actuator-interlock/1"
        self.manifest_model = manifest.get("hardware_model")
        self.seed = config["scenario"]["seed"]
        self.cleared, self.plans, self.observations, self.previous = set(), {}, {}, {}
        self.returned, self.tests = {}, {}

    def truth(self, name, hour):
        cause = (
            self.f.get(name + "_service_fault", "none")
            if hour >= self.f.get("service_fault_start_hour", 0) and name not in self.cleared
            else "none"
        )
        return {"target": name, "cause": cause, "active": cause != "none"}

    def interval(self, record, truth, hour, checks, controller):
        def check(label, value, expected=True, unit="boolean"):
            compare(
                checks, "hardware." + label, value, expected, unit, controller=controller, hour=hour
            )

        o = self.o
        kinds = (
            "remote-release",
            "hardware-test",
            "guided-return",
            "hardware-replacement",
            "pack-return",
        )
        orders = {q["id"]: q for q in record["state"]["orders"]}
        for plan in record["new_missions"]:
            key, action = plan["order"]["order_id"], plan["order"]["action"]
            self.plans[key] = plan
            check(
                "context_available",
                all(r["available_at"] <= hour for r in plan["context"]["readings"]),
            )
            if action not in kinds:
                continue
            request = orders[key]
            name = request["robot"]
            check(
                "compatible_capability", plan["capability"]["capability_id"] == action + ":" + name
            )
            check(
                "prepared_interface", plan["interface"]["implementation_id"] == "service-hardware/1"
            )
            check(
                "target_named",
                name in self.assets and plan["interface"]["target_asset_id"] == self.assets[name],
            )
            end = list(SupportReference.spans(plan))[-1][1]
            recipe = (plan.get("timing") or {}).get("nominal_stages", plan["stages"])
            body = next(s for s in recipe if s["effect"])
            duration = (
                o["remote_release_hours"]
                if action == "remote-release"
                else o["hardware_replacement_hours"]
                if action == "hardware-replacement"
                else o["verification_hours"]
                if action in ("guided-return", "pack-return")
                else o["robot_test_hours"]
            )
            check("configured_work_duration", body["duration_hours"], duration, "h")
            if action in ("remote-release", "hardware-replacement"):
                check(
                    "procedure_acceptance_binding",
                    [r["channel"] for r in plan["capability"]["acceptance"]]
                    == ["hardware-accepted:" + key],
                )
            if action == "hardware-replacement":
                check(
                    "typed_module",
                    list(body["consumables"])
                    == [{"resource": "stock:hardware:" + name, "amount": 1, "unit": "module"}],
                )
            elif name != "portable":
                opening = (D(hour) // D(o["crew_period_hours"])) * D(o["crew_period_hours"]) + D(
                    o["remote_shift_start_hour"]
                )
                check(
                    "remote_shift",
                    opening <= D(hour) and end <= opening + D(o["remote_shift_duration_hours"]),
                )
                check(
                    "communications_observed",
                    any(
                        r["channel"] == "communications"
                        and r["value"] is True
                        and r["quality"] == "usable"
                        and r["measured_at"] >= hour - 1
                        for r in plan["context"]["readings"]
                    ),
                )
            if action in ("guided-return", "pack-return"):
                origin = self.previous.get(request["origin_order"], {})
                # A current-supply interruption can precede dispatch at this
                # same boundary. Only an already-recorded interruption at or
                # before dispatch qualifies; later events cannot justify it.
                boundary_interruption = origin.get("status") in ("scheduled", "active") and any(
                    e["order_id"] == request["origin_order"]
                    and e["kind"] == "interrupted"
                    and D(e["at_hour"]) <= D(plan["starting_at"])
                    for e in record["mission_events"]
                )
                check(
                    "return_from_stranded_origin",
                    (origin.get("status") == "stranded" or boundary_interruption)
                    and request["origin_order"] not in self.returned,
                )
                check(
                    "return_uses_reported_location",
                    request["recovery_location"]
                    == {k: origin.get(k) for k in ("from_point", "to_point", "phase", "progress")},
                )
                returning = [s for s in recipe if s["phase"] == "return"]
                check("one_declared_return", len(returning), 1, "count")
                for s in returning:
                    check(
                        "return_duration",
                        s["duration_hours"],
                        o["crew_travel_hours"] if action == "pack-return" else o["travel_hours"],
                        "h",
                    )
                    check(
                        "return_endpoint",
                        s["from_point"] == "recovery/" + request["origin_order"]
                        and s["to_point"] == ("site-gate" if action == "pack-return" else "dock"),
                    )
                if action == "guided-return":
                    eligible = [
                        r
                        for r in self.observations.values()
                        if r["channel"] == "hardware-tracking:" + name and r["available_at"] <= hour
                    ]
                    check(
                        "guided_return_requires_tracking",
                        bool(eligible)
                        and max(eligible, key=lambda r: r["measured_at"])["value"] is True,
                    )

        if self.independent:
            check(
                "model_identity",
                record["version"]
                == (
                    "plant-service-contracts/12"
                    if self.o.get("crew_return_enabled")
                    else "plant-service-contracts/11"
                ),
            )
            check("manifest_physics_identity", self.manifest_model == "actuator-interlock/1")
            # Reconstruct forbidden work even if a trace omits both its rejection
            # receipt and its observation. The supplied receipt is not the oracle.
            for event in record["mission_events"]:
                if event["kind"] != "interval" or event["end"] <= event["start"]:
                    continue
                plan = self.plans[event["order_id"]]
                action = plan["order"]["action"]
                name = next(
                    (
                        n
                        for n in ("cleaner", "rover", "dock", "portable")
                        if self.assets.get(n) == plan["asset"]["asset_id"]
                    ),
                    None,
                )
                exempt = action in (
                    "remote-release",
                    "hardware-test",
                    "hardware-replacement",
                    "pack-return",
                    "crew-return",
                    "self-test",
                )
                dependent = (
                    name is not None
                    and not exempt
                    and (name != "dock" or action.startswith("charge-"))
                    and (name != "portable" or event["phase"] in ("prepare", "perform"))
                )
                if dependent:
                    check("no_work_with_failed_actuator", not self.truth(name, hour)["active"])

        procedures = {}
        for receipt in truth.get("hardware_execution", []):
            key = receipt["order_id"]
            plan = self.plans[key]
            action = plan["order"]["action"]
            check("receipt_in_interval", hour <= receipt["completed_at"] <= hour + 1)
            for effect in receipt["effects"]:
                kind = effect.get("kind")
                if kind not in (
                    "hardware-command",
                    "hardware-test",
                    "hardware-procedure",
                    "drive-test",
                ):
                    continue
                name = effect["target"]
                physical = self.truth(name, hour)
                if kind == "drive-test":
                    check("drive_model", self.independent)
                    check(
                        "drive_execution_identity",
                        plan["capability"]["implementation_id"] == "supervised-drive-test/2",
                    )
                    check("drive_private_operands", effect["private_state"] == physical)
                    check(
                        "drive_identity",
                        action == "self-test"
                        and plan["asset"]["asset_id"] == self.assets.get(name),
                    )
                    token = f"{self.seed}/{action}/{plan['order']['reason']}/drive-test"
                    draw = (
                        service_variate(self.seed, plan["stochastic_event"], "drive-test")
                        if self.o.get("outcome_randomness") == "target-action-request/1"
                        else int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
                        / 2**64
                    )
                    tracked = not physical["active"] and draw < o["robot_test_success_probability"]
                    check("drive_response", effect["tracked"], tracked)
                    end = next(b for _, b, s in executed_service_spans(plan, o) if s["effect"])
                    check("drive_completion", effect["completed_at"], end, "h")
                    check("drive_boundary", effect["available_at"], math.ceil(end), "h")
                    source = "supervised-drive-test/2:" + key
                    self.observations[source] = dict(
                        channel="hardware-tracking:" + name,
                        value=tracked,
                        unit="boolean",
                        measured_at=effect["completed_at"],
                        available_at=effect["available_at"],
                        source_id=source,
                        quality="usable",
                    )
                    continue
                if kind in ("hardware-command", "hardware-test"):
                    check("private_operands", effect["private_state"] == physical)
                    value = not physical["active"] if kind == "hardware-test" else False
                    measured = (
                        effect["completed_at"] if kind == "hardware-test" else effect["at_hour"]
                    )
                    boundary = (
                        max(hour + 1, math.ceil(measured))
                        if kind == "hardware-command"
                        else math.ceil(measured)
                    )
                    if kind == "hardware-command":
                        if self.independent:
                            check(
                                "command_target", self.assets.get(name) == plan["asset"]["asset_id"]
                            )
                            check(
                                "command_action",
                                action
                                not in (
                                    "remote-release",
                                    "hardware-test",
                                    "hardware-replacement",
                                    "pack-return",
                                    "self-test",
                                ),
                            )
                        check(
                            "unavailable_actuator_rejected",
                            physical["active"] and effect["command_accepted"] is False,
                        )
                        check(
                            "rejection_has_interruption",
                            any(
                                e["order_id"] == key
                                and e["kind"] == "interrupted"
                                and e["at_hour"] == measured
                                for e in record["mission_events"]
                            ),
                        )
                    else:
                        check("test_action", action == "hardware-test")
                        check("test_response", effect["tracked"], value)
                        end = next(b for _, b, s in executed_service_spans(plan, o) if s["effect"])
                        check("test_completion", measured, end, "h")
                        self.tests[key] = value
                    source = (
                        "service-hardware/1/test:"
                        if kind == "hardware-test"
                        else "service-command-feedback/1:"
                    ) + key
                    self.observations[source] = dict(
                        channel=(
                            "hardware-tracking:" if kind == "hardware-test" else "hardware-command:"
                        )
                        + name,
                        value=value,
                        unit="boolean",
                        measured_at=measured,
                        available_at=boundary,
                        source_id=source,
                        quality="usable",
                    )
                else:
                    token = f"{self.seed}/{action}/{plan['order']['reason']}/hardware-procedure"
                    draw = (
                        service_variate(self.seed, plan["stochastic_event"], "hardware-procedure")
                        if self.o.get("outcome_randomness") == "target-action-request/1"
                        else int.from_bytes(hashlib.sha256(token.encode()).digest()[:8], "big")
                        / 2**64
                    )
                    check(
                        "procedure_draw",
                        effect["successful"],
                        draw < self.c["repair_success_probability"],
                    )
                    check(
                        "procedure_identity",
                        effect["action"] == action
                        and action in ("remote-release", "hardware-replacement"),
                    )
                    check("procedure_boundary", effect["effective_at"], hour + 1, "h")
                    procedures[key] = effect
        for effect in truth["service_effects"]:
            if effect.get("kind") != "hardware-procedure":
                continue
            key = effect["order_id"]
            check("procedure_has_execution_receipt", key in procedures)
            if key not in procedures:
                continue
            p = procedures.pop(key)
            name, action = p["target"], p["action"]
            before = self.truth(name, hour)
            check("before_procedure", effect["before"] == before)
            if (
                p["successful"]
                and before["active"]
                and (action == "hardware-replacement" or before["cause"] == "control-hold")
            ):
                self.cleared.add(name)
            check("after_procedure", effect["after"] == self.truth(name, hour))
            check("procedure_effect_time", effect["effective_at"], hour + 1, "h")
        check("no_discarded_procedure", not procedures)
        for effect in record.get("support_effects", []):
            if effect["kind"] in ("retrieve", "guided-return", "pack-return", "crew-return"):
                for origin in effect.get("returned_orders", [effect["origin_order"]]):
                    self.returned[origin] = effect
        actual = {
            r["source_id"]: r
            for r in record["state"]["executive"]["observations"]
            if r["channel"].startswith(("hardware-command:", "hardware-tracking:"))
        }
        check(
            "eligible_observation_set",
            actual == {k: r for k, r in self.observations.items() if r["available_at"] <= hour + 1},
        )
        if self.independent:
            monitor = record["state"]["hardware"]
            check("monitor_identity", monitor["implementation_id"] == "actuator-interlock/1")
            check(
                "recovery_permission",
                monitor["recovery_enabled"] == o["equipment_recovery_enabled"],
            )
            expected_monitor = {}
            for name in ("cleaner", "rover", "dock", "portable"):
                if name not in self.assets:
                    continue
                feedback = max(
                    (
                        r
                        for r in actual.values()
                        if r["channel"] in ("hardware-command:" + name, "hardware-tracking:" + name)
                        and r["quality"] == "usable"
                    ),
                    key=lambda r: (r["measured_at"], r["available_at"]),
                    default=None,
                )
                expected_monitor[name] = dict(
                    status="unobserved"
                    if feedback is None
                    else "tracking confirmed"
                    if feedback["value"] is True
                    else "command or test failed",
                    feedback=feedback,
                    may_attempt=feedback is None or feedback["value"] is True,
                )
            check(
                "monitor_uses_only_eligible_feedback", monitor["observations"] == expected_monitor
            )
            for reading in record["state"]["executive"]["observations"]:
                if reading["channel"].startswith("robot-ready:") and reading[
                    "source_id"
                ].startswith("supervised-drive-test/2:"):
                    expected = self.observations.get(reading["source_id"])
                    check(
                        "drive_ready_matches_physical_test",
                        expected is not None
                        and {**expected, "channel": reading["channel"]} == reading,
                    )
        for telemetry in record["state"]["executive"]["orders"]:
            q = orders.get(telemetry["order_id"], {})
            if (
                q.get("kind") not in ("remote-release", "hardware-replacement")
                or telemetry["verified_at"] is None
            ):
                continue
            step = "field-probe" if q["kind"] == "remote-release" else "replacement-probe"
            linked = next(
                (
                    t
                    for t in orders.values()
                    if t.get("equipment_incident") == q.get("equipment_incident")
                    and t.get("equipment_step") == step
                ),
                {},
            )
            check("acceptance_uses_own_test", self.tests.get(linked.get("id")) is True)
        used = {}
        for event in record["resource_events"]:
            if event["kind"] == "consume" and event["resource"].startswith("stock:hardware:"):
                name = event["resource"].removeprefix("stock:hardware:")
                used[name] = used.get(name, D(0)) + D(event["amount"])
        check("module_usage_report", record["hardware_modules_used"] == used)
        self.previous = {q["order_id"]: q for q in record["state"]["executive"]["orders"]}


def field_period_outcomes(rows, reported, checks, controller):
    """Independently total checked receipts; legacy archives need no new metrics."""
    if reported is None:
        return
    service = [r["field_operations"] for r in rows]
    clips = [
        (
            r.get("component_records", {}).get("solar", {}).get("diagnostics", {}).get("detail")
            or {}
        ).get("clipped_kw")
        for r in rows
    ]
    contacts = [r["decision"].get("inspection") for r in service]
    eligible = [r["at_hour"] for r in contacts if r and r["quality"] == "usable"]
    expected = dict(
        cleaning_treated_m2=sum(D(r["treated_area_m2"]) for r in service)
        if all("treated_area_m2" in r for r in service)
        else None,
        cleaning_full_passes=sum(r["cleanings_completed"] for r in service),
        cleaning_water_l=sum(
            D(e["amount"])
            for r in service
            for e in r["resource_events"]
            if e["kind"] == "consume" and e["resource"] == "stock:water"
        ),
        converter_clipped_kwh=sum(D(v) for v in clips)
        if all(v is not None for v in clips)
        else None,
        contact_usable_decision_hours=len(eligible) if any(contacts) else None,
        contact_first_usable_hour=min(eligible) if eligible else None,
        dock_unserved_kwh=sum(D(r.get("standby", {}).get("unserved_kwh", 0)) for r in service)
        if any("standby" in r for r in service)
        else None,
        routine_completed=sum(
            e["kind"] == "routine-service" for r in service for e in r.get("support_effects", [])
        ),
    )
    for k, v in expected.items():
        compare(checks, "field_period." + k, reported.get(k), v, controller=controller)


class LocalServiceReference:
    """Reconstruct local cadence from phase events, independent of policy flags."""

    def __init__(self, config):
        self.o, self.c = config["service_system"], config["field_operations"]
        self.orders, self.clocks, self.finished = set(), {}, set()

    def interval(self, record, hour, checks, controller):
        def check(label, value, expected=True, unit="boolean"):
            compare(
                checks,
                "local_service." + label,
                value,
                expected,
                unit,
                controller=controller,
                hour=hour,
            )

        o = self.o
        rule = o.get("cleaning_policy", "legacy-condition")
        decision, state = record["decision"], record["state"]
        access = o.get("inspection_interface", "legacy-prepared")
        if access != "legacy-prepared":
            for public in (decision, state):
                check("contact_interface", public["inspection_interface"]["kind"] == access)
                check(
                    "contact_access",
                    public["inspection_interface"]["accessible"],
                    access == "accessible-port",
                )
            for plan in record["new_missions"]:
                if plan["order"]["interface_id"] == "ELY/contact":
                    check("contact_read_requires_access", access == "accessible-port")
                    req = plan["interface"]["requirements"]
                    check(
                        "contact_requirement_recorded",
                        any(
                            q["channel"] == "contact-port-accessible" and q["value"] is True
                            for q in req
                        ),
                    )
        if rule == "legacy-condition":
            return
        surface = {s["id"]: s for s in (decision.get("surface") or {}).get("sections", [])}
        if not self.clocks:
            self.clocks = {
                s: dict(
                    next_due_hour=D(o["cleaning_first_due_hour"]),
                    last_completed_hour=None,
                    completed_passes=0,
                )
                for s in surface
            }

        def clocks(public, now):
            policy = public["cleaning_policy"]
            check("rule", policy["mode"] == rule)
            check("recurrence", policy["recurrence_hours"], o["cleaning_period_hours"], "h")
            schedules = policy["schedules"]
            check(
                "section_set",
                {s["section"] for s in schedules}
                == (set(self.clocks) if rule == "periodic" else set()),
            )
            for s in schedules:
                expected = self.clocks[s["section"]]
                for key, value in expected.items():
                    check(
                        "clock_" + key,
                        s[key] is None if value is None else s[key],
                        True if value is None else value,
                        "h" if key.endswith("hour") else "count",
                    )
                check(
                    "overdue",
                    s["overdue_hours"],
                    max(D(0), D(now) - expected["next_due_hour"]),
                    "h",
                )

        clocks(decision, hour)
        orders = {
            q["id"]: q for q in state["orders"] if q["kind"] in ("cleaning", "portable-cleaning")
        }
        for key, q in orders.items():
            if key in self.orders:
                continue
            self.orders.add(key)
            check("request_enabled", rule != "off")
            check("request_rule", q.get("cleaning_rule") == rule)
            check("request_boundary", q["created_hour"], hour, "h")
            s = surface[q["section"]]
            check("surface_observation", q["measured_surface"] == s)
            if rule == "periodic":
                due = self.clocks[q["section"]]["next_due_hour"]
                check("request_when_due", D(hour) >= due)
                check("original_due", q["due_hour"], due, "h")
            else:
                check(
                    "condition_threshold",
                    s["removable_fraction"] >= self.c["cleaning_threshold"]
                    or (
                        q["kind"] == "portable-cleaning"
                        and o["portable_cleaner"] == "wet"
                        and s["adhered_fraction"] >= o["portable_adhered_threshold"]
                    ),
                )
        events = record["mission_events"]
        effects = {e["order_id"]: e for e in record.get("cleaning_policy_effects", [])}
        expected_effects = set()
        for e in events:
            key = e["order_id"]
            if (
                key not in orders
                or key in self.finished
                or e["kind"] != "stage_end"
                or e["phase"] != "perform"
            ):
                continue
            self.finished.add(key)
            end = D(e["at_hour"])
            interrupted = any(
                x["order_id"] == key
                and x["kind"] == "interrupted"
                and D(x["at_hour"]) <= end + D("1e-9")
                for x in events
            )
            if interrupted:
                continue
            expected_effects.add(key)
            q = orders[key]
            clock = self.clocks[q["section"]]
            effect = effects.get(key, {})
            for k, v in dict(
                completed_at=end,
                effective_at=math.ceil(end - D("1e-9")),
                previous_due_hour=clock["next_due_hour"],
                next_due_hour=end + D(o["cleaning_period_hours"]),
            ).items():
                check("completion_" + k, effect.get(k, -1), v, "h")
            check("completion_section", effect.get("section") == q["section"])
            clock.update(
                last_completed_hour=end,
                next_due_hour=end + D(o["cleaning_period_hours"]),
                completed_passes=clock["completed_passes"] + 1,
            )
        check("completion_set", set(effects) == expected_effects)
        clocks(state, hour + 1)


class SupportReference:
    """Reconstruct support timing/eligibility from plans and receipts, not flags.

    This checks internal consistency of declared logistics. Test observations
    remain evidence inputs; it cannot establish real robot reliability.
    """

    def __init__(self, options, assets=None):
        self.o = options
        self.plans, self.returned, self.previous = {}, {}, {}
        self.crew_stops, self.crew_visits = {}, {}
        self.readings, self.consumed, self.effects = {}, {}, set()
        self.maintenance = {
            n: dict(
                next_due_hour=D(options["maintenance_first_due_hour"]),
                last_completed_hour=None,
                completed_count=0,
            )
            for n in ("cleaner", "rover", "dock", "fixed_reader", "reset")
            if options.get("maintenance_enabled")
            and n in (assets or {})
            and options["maintenance_target"] in ("resident", n)
        }

    def check_maintenance_state(self, public, at, check):
        if not self.o.get("maintenance_enabled"):
            return
        schedules = public["support"]["maintenance"]["schedules"]
        check("maintenance_target_set", [s["target"] for s in schedules] == list(self.maintenance))
        for s in schedules:
            expected = self.maintenance[s["target"]]
            for key, value in expected.items():
                check(
                    "maintenance_" + s["target"] + "_" + key,
                    s[key] is None if value is None else s[key],
                    True if value is None else value,
                    "h" if key.endswith("hour") else "count",
                )
            check(
                "maintenance_overdue",
                s["overdue_hours"],
                max(D(0), D(at) - expected["next_due_hour"]),
                "h",
            )

    @staticmethod
    def spans(plan):
        start = D(plan["starting_at"])
        for stage in plan["stages"]:
            end = start + D(stage["duration_hours"])
            yield start, end, stage
            start = end

    def check_crew_return(self, plan, request, record, check):
        """Independently derive skipped work and remaining travel from old recipes."""
        origin = request["origin_order"]
        original, stop = self.plans.get(origin), self.crew_stops.get(origin)
        check("crew_return_enabled", self.o.get("crew_return_enabled") is True)
        check("crew_return_observed_stop", original is not None and stop is not None)
        if original is None or stop is None:
            return
        check("crew_return_same_actor", plan["asset"]["asset_id"] == original["asset"]["asset_id"])
        check(
            "crew_return_human",
            original["asset"]["autonomy"] == "human" and original["asset"]["mobility"] == "crew",
        )
        check("crew_return_adapter", plan["adapter_id"] == "observed-crew-return-adapter/1")
        check(
            "crew_return_capability",
            plan["capability"]["implementation_id"] == "interrupted-crew-return/1",
        )
        check("crew_return_after_report", D(request["created_hour"]) >= math.ceil(stop))
        prior = self.previous.get(origin, {})
        observed = {k: prior.get(k) for k in ("from_point", "to_point", "phase", "progress")}
        # An interruption at the current boundary is in this interval's receipt
        # list; derive its location from the original schedule when not in the
        # previous public snapshot yet.
        if prior.get("status") != "stranded":
            slots = list(self.spans(original))
            current = next(((a, b, s) for a, b, s in slots if a <= stop < b), slots[-1])
            a, b, s = current
            observed = dict(
                from_point=s["from_point"],
                to_point=s["to_point"],
                phase=s["phase"],
                progress=float(min(D(1), max(D(0), (stop - a) / (b - a)))),
            )
        check("crew_return_location", request["recovery_location"] == observed)
        expected, operands = [], []
        members = self.crew_visits.get(origin, [original])
        expected_resources = {q["resource"]: q for q in original["asset"]["support_resources"]}
        if origin in self.crew_visits:
            expected_resources = {
                q["resource"]: q
                for member in members
                for q in (
                    {
                        "resource": "asset:" + member["asset"]["asset_id"],
                        "amount": 1,
                        "unit": "slot",
                    },
                    *member["asset"]["support_resources"],
                )
                if q["resource"] != "asset:" + plan["asset"]["asset_id"]
            }
        check(
            "crew_return_accompanying_resources",
            {q["resource"]: q for q in plan["asset"]["support_resources"]} == expected_resources,
        )
        for member in members:
            for i, (a, b, stage) in enumerate(self.spans(member)):
                if stage["phase"] not in ("travel", "return") or b <= stop:
                    continue
                left = max(a, stop)
                expected.append(
                    dict(
                        from_point="recovery/" + origin if a < stop < b else stage["from_point"],
                        to_point=stage["to_point"],
                        duration_hours=float(b - left),
                    )
                )
                operands.append(
                    dict(
                        order_id=member["order"]["order_id"],
                        stage_index=i,
                        original_start=float(a),
                        original_end=float(b),
                        interruption_at=float(stop),
                        remaining_hours=float(b - left),
                    )
                )
        check("crew_return_route_operands", request["return_route_operands"] == operands)
        check("crew_return_route", request["return_route"] == expected)
        stages = plan["stages"]
        movement = [s for s in stages if s["phase"] == "return"]
        check(
            "crew_return_only_remaining_motion",
            [{k: s[k] for k in ("from_point", "to_point", "duration_hours")} for s in movement]
            == expected,
        )
        check("crew_return_no_new_visit", not any(s["phase"] == "travel" for s in stages))
        check(
            "crew_return_no_material_or_power",
            all(not s["consumables"] and not s["bus_kw"] and not s["battery_kw"] for s in stages),
        )
        preparations = [s for s in stages if s["phase"] == "prepare"]
        check("crew_return_packing_count", len(preparations), int(bool(expected)), "count")
        for s in preparations:
            check(
                "crew_return_packing_hours",
                s["duration_hours"],
                self.o["crew_return_pack_hours"],
                "h",
            )
        last = stages[-1]
        check(
            "crew_return_arrival",
            last["phase"] == "perform"
            and last["effect"] is True
            and last["from_point"] == last["to_point"] == plan["asset"]["home"],
        )
        check(
            "crew_return_arrival_hours",
            last["duration_hours"],
            self.o["crew_return_check_hours"],
            "h",
        )
        point = expected[0]["from_point"] if expected else plan["asset"]["home"]
        for s in stages:
            check("crew_return_continuity", s["from_point"] == point)
            point = s["to_point"]
        original_order = next(q for q in record["state"]["orders"] if q["id"] == origin)
        origins = (
            [*original_order["return_origins"], origin]
            if original["order"]["action"] == "crew-return"
            else [origin]
        )
        check("crew_return_original_obligations", request["return_origins"] == origins)

    def interval(self, record, hour, checks, controller):
        def check(label, value, expected=True, unit="boolean"):
            compare(
                checks, "support." + label, value, expected, unit, controller=controller, hour=hour
            )

        o, now = self.o, D(hour)
        for event in record.get("mission_events", []):
            if event["kind"] == "interrupted":
                self.crew_stops[event["order_id"]] = D(event["at_hour"])
        for visit in record.get("new_visits", []):
            for member in visit["members"]:
                self.crew_visits[member["order"]["order_id"]] = visit["members"]
        self.check_maintenance_state(record["decision"], hour, check)
        bundled = {
            p["order"]["order_id"] for v in record.get("new_visits", []) for p in v["members"]
        }
        selection = record.get("selection", {})
        explicit = {}
        if selection.get("implementation_id") in (
            "service-selection-port/1",
            "service-selection-port/2",
            "service-selection-port/3",
        ):
            for item in selection.get("results", []):
                if item.get("accepted") is True:
                    key = item["order_id"]
                    check("unique_selection", key not in explicit)
                    explicit[key] = D(item["starting_at"])
        visits = {v["visit_id"]: v for v in record.get("new_visits", [])}
        selected_visits = set()
        if selection.get("implementation_id") == "service-selection-port/3":
            for group in selection.get("visit_groups", []):
                if group.get("accepted") is not True:
                    continue
                vid = group["visit_id"]
                check("unique_visit_selection", vid not in selected_visits)
                selected_visits.add(vid)
                visit = visits.get(vid)
                check("selected_visit_recorded", visit is not None)
                if visit is None:
                    continue
                members = visit["members"]
                check(
                    "selected_visit_orders",
                    group["order_ids"] == [p["order"]["order_id"] for p in members],
                )
                check("selected_visit_start", members[0]["starting_at"], group["starting_at"], "h")
                check(
                    "selected_visit_return",
                    list(self.spans(members[-1]))[-1][1],
                    group["returning_at"],
                    "h",
                )
                for member in members:
                    key = member["order"]["order_id"]
                    check("unique_selection", key not in explicit)
                    explicit[key] = D(member["starting_at"])
            check("selected_visit_coverage", selected_visits == set(visits))
        for vid, visit in visits.items():
            if D(visit["members"][0]["starting_at"]) > now:
                check("future_visit_authorized", vid in selected_visits)
        orders = {q["id"]: q for q in record["state"]["orders"]}
        executive = record["state"]["executive"]
        for plan in record["new_missions"]:
            if plan["order"]["action"] == "routine-service":
                request = orders[plan["order"]["order_id"]]
                schedule = self.maintenance[request["target"]]
                check(
                    "maintenance_requested_when_due",
                    D(request["created_hour"]) >= schedule["next_due_hour"],
                )
                check(
                    "maintenance_original_due", request["due_hour"], schedule["next_due_hour"], "h"
                )
                check(
                    "maintenance_cycle",
                    request["maintenance_cycle"],
                    schedule["completed_count"] + 1,
                    "count",
                )
                check(
                    "maintenance_work_duration",
                    plan["capability"]["work_hours"],
                    o["maintenance_work_hours"],
                    "h",
                )
                check("maintenance_supply_procedure", plan["capability"]["effect_kind"] == "supply")
            key, action = plan["order"]["order_id"], plan["order"]["action"]
            check("unique_mission", key not in self.plans)
            self.plans[key] = plan
            start, asset = D(plan["starting_at"]), plan["asset"]["asset_id"]
            check(
                "dispatch_boundary",
                start >= now if key in bundled or key in explicit else start == now,
            )
            if key in explicit:
                check("selected_start", start, explicit[key], "h")
            if plan["asset"]["autonomy"] == "human":
                end = list(self.spans(plan))[-1][1]
                opening = (start // D(o["crew_period_hours"])) * D(o["crew_period_hours"]) + D(
                    o["crew_shift_start_hour"]
                )
                check(
                    "crew_response_lead",
                    plan.get("adapter_id")
                    in ("observed-location-service-adapter/1", "observed-crew-return-adapter/1")
                    or start >= D(plan["order"]["requested_at"]) + D(o["crew_response_lead_hours"]),
                )
                check(
                    "crew_shift_including_return",
                    opening <= start < opening + D(o["crew_shift_duration_hours"])
                    and end <= opening + D(o["crew_shift_duration_hours"]) + D("1e-9"),
                )
            if plan["asset"].get("battery_resource") or action == "charge":
                target = plan["interface"]["target_asset_id"] if action == "charge" else asset
                stranded = [
                    k
                    for k, q in self.previous.items()
                    if q["asset_id"] == target and q["status"] == "stranded"
                ]
                assisting = o.get("equipment_recovery_enabled") and action in (
                    "remote-release",
                    "hardware-test",
                    "guided-return",
                )
                check(
                    "no_work_while_stranded", assisting or all(k in self.returned for k in stranded)
                )
                returns = [
                    v for k, v in self.returned.items() if self.previous[k]["asset_id"] == target
                ]
                if returns and action not in (
                    "charge",
                    "self-test",
                    "hardware-test",
                    "remote-release",
                    "guided-return",
                ):
                    latest = max(D(v["effective_at"]) for v in returns)
                    channel = (
                        "hardware-tracking:"
                        if o.get("equipment_recovery_enabled")
                        else "robot-ready:"
                    ) + returns[-1]["robot"]
                    evidence = [
                        r
                        for r in self.readings.values()
                        if r["channel"] == channel
                        and D(r["measured_at"]) >= latest
                        and D(r["available_at"]) <= start
                        and r["quality"] == "usable"
                    ]
                    check(
                        "observed_return_to_work",
                        bool(evidence)
                        and max(evidence, key=lambda r: r["measured_at"])["value"] is True,
                    )
            if action == "retrieve":
                request = orders[key]
                origin = self.previous.get(request["origin_order"], {})
                check(
                    "retrieval_has_stranded_origin",
                    origin.get("status") == "stranded"
                    and origin.get("asset_id") == plan["interface"]["target_asset_id"]
                    and request["origin_order"] not in self.returned,
                )
                check(
                    "retrieval_location",
                    request["recovery_location"]
                    == {k: origin.get(k) for k in ("from_point", "to_point", "phase", "progress")},
                )
            if action == "crew-return":
                self.check_crew_return(plan, orders[key], record, check)
            elif o.get("crew_return_enabled") and plan["asset"]["autonomy"] == "human":
                check(
                    "crew_not_duplicated",
                    plan.get("adapter_id") == "observed-location-service-adapter/1"
                    or all(
                        key in self.returned
                        for key, previous in self.previous.items()
                        if previous["status"] == "stranded"
                        and self.plans[key]["asset"]["autonomy"] == "human"
                    ),
                )

        expected_hours = {"crew-hours": D(0), "remote-hours": D(0)}
        water, portable_hours, portable_area = D(0), D(0), D(0)
        for event in record["mission_events"]:
            if event["kind"] != "interval":
                continue
            plan = self.plans[event["order_id"]]
            start, end = D(event["start"]), D(event["end"])
            matching = [
                s
                for a, b, s in executed_service_spans(
                    plan, o, self.crew_visits.get(event["order_id"], ())
                )
                if a - D("1e-9") <= start and end <= b + D("1e-9") and s["phase"] == event["phase"]
            ]
            check(
                "interval_inside_declared_stage",
                end > start and now <= start and end <= now + 1 and len(matching) == 1,
            )
            if plan["asset"]["autonomy"] == "human":
                expected_hours["crew-hours"] += end - start
            if plan["order"]["action"] == "self-test":
                expected_hours["remote-hours"] += end - start
            elif (
                o.get("equipment_recovery_enabled")
                and plan["asset"]["autonomy"] == "remote-operated"
            ):
                expected_hours["remote-hours"] += end - start
            if (
                o.get("equipment_recovery_enabled")
                or o.get("crew_return_enabled")
                and plan["order"]["action"] == "crew-return"
            ) and plan["asset"]["archetype"] == "portable-cleaner":
                portable_hours += end - start
            if plan["order"]["action"] == "portable-clean-section":
                if not o.get("equipment_recovery_enabled"):
                    portable_hours += end - start
                if event["phase"] == "perform":
                    area = (
                        (end - start)
                        * D(o["portable_area_m2ph"])
                        / D(o.get("cleaning_time_factor", 1))
                    )
                    portable_area += area
                    if o["portable_cleaner"] == "wet":
                        water += area * D(o["portable_water_l_per_m2"])
                elif event["phase"] == "prepare" and o["portable_cleaner"] == "wet":
                    water += (
                        (end - start)
                        * D(o["portable_rinse_l"])
                        / (D(o["portable_setup_hours"]) * D(o.get("support_time_factor", 1)))
                    )
        events = record["resource_events"]
        if o.get("portable_cleaner", "none") != "none":
            actual_water = sum(
                (
                    D(e["amount"])
                    for e in events
                    if e["kind"] == "consume" and e["resource"] == "stock:water"
                ),
                D(0),
            )
            check("portable_water_by_phase", actual_water, water, "L")
            check("portable_water_report", record["water_used_l"], water, "L")
            check("portable_tool_hours", record["portable_hours"], portable_hours, "h")
            areas = [
                D(op["end_m2"]) - D(op["start_m2"])
                for op in record["surface_events"]
                if op.get("method", "").startswith("portable-")
            ]
            check("portable_coverage_by_duration", sum(areas, D(0)), portable_area, "m2")
            for op in record["surface_events"]:
                if op.get("method", "").startswith("portable-"):
                    plan = self.plans[op["order_id"]]
                    start = next(
                        a
                        for a, _, s in executed_service_spans(
                            plan, o, self.crew_visits.get(plan["order"]["order_id"], ())
                        )
                        if s["effect"]
                    )
                    check(
                        "portable_area_start",
                        op["start_m2"],
                        (D(op["started_at"]) - start)
                        * D(o["portable_area_m2ph"])
                        / D(o.get("cleaning_time_factor", 1)),
                        "m2",
                    )
                    check(
                        "portable_area_end",
                        op["end_m2"],
                        (D(op["completed_at"]) - start)
                        * D(o["portable_area_m2ph"])
                        / D(o.get("cleaning_time_factor", 1)),
                        "m2",
                    )
        for event in events:
            if event["kind"] == "consume":
                key = (event["mission_id"], event["resource"])
                self.consumed[key] = self.consumed.get(key, D(0)) + D(event["amount"])
        for resource, field in (
            ("crew-hours", "crew_committed_hours"),
            ("remote-hours", "remote_hours"),
        ):
            used = sum(
                (
                    D(e["amount"])
                    for e in events
                    if e["kind"] == "consume" and e["resource"] == resource
                ),
                D(0),
            )
            check("duration_" + resource, used, expected_hours[resource], "h")
            check("reported_" + resource, record[field], expected_hours[resource], "h")
            arrivals = [e for e in events if e["kind"] == "replenish" and e["resource"] == resource]
            due = hour > 0 and hour % o["crew_period_hours"] == 0
            check("allowance_boundary_" + resource, len(arrivals), int(due), "count")
            for e in arrivals:
                check("allowance_time", e["at_hour"], hour, "h")
                check(
                    "allowance_amount",
                    e["offered"],
                    o[
                        "crew_hours_per_period"
                        if resource == "crew-hours"
                        else "remote_hours_per_period"
                    ],
                    "h",
                )
                check(
                    "allowance_source",
                    e["source_id"] == f"support-allocation-period/{hour // o['crew_period_hours']}",
                )

        for effect in record["support_effects"]:
            key, kind = effect["order_id"], effect["kind"]
            plan = self.plans[key]
            check("single_support_effect", key not in self.effects)
            self.effects.add(key)
            end = next(
                b
                for _, b, s in executed_service_spans(
                    plan, o, self.crew_visits.get(plan["order"]["order_id"], ())
                )
                if s["effect"]
            )
            check("effect_matches_action", kind == plan["order"]["action"])
            check("effect_completion", effect["completed_at"], end, "h")
            # The executive tolerates floating point representation at exact boundaries.
            boundary = math.ceil(float(end) - 1e-9)
            check("effect_eligibility", effect["effective_at"], boundary, "h")
            check("effect_not_backdated", boundary, hour + 1, "h")
            check(
                "effect_has_receipt",
                any(
                    e["kind"] == "stage_end"
                    and e["phase"] == "perform"
                    and e["order_id"] == key
                    and abs(D(e["at_hour"]) - end) < D("1e-8")
                    for e in record["mission_events"]
                ),
            )
            if kind in ("retrieve", "guided-return", "pack-return", "crew-return"):
                request = orders[key]
                check(
                    "retrieval_identifiers",
                    effect["origin_order"] == request["origin_order"]
                    and effect["robot"] == request["robot"]
                    and effect["location"] == request["recovery_location"],
                )
                check("not_previously_returned", effect["origin_order"] not in self.returned)
                origins = effect.get("returned_orders", [effect["origin_order"]])
                for origin in origins:
                    previous = self.previous.get(origin, {})
                    check(
                        "same_hardware_return",
                        (
                            previous.get("status") == "stranded"
                            or previous.get("status") == "blocked"
                            and self.plans[origin]["order"]["action"] == "crew-return"
                        )
                        and previous.get("asset_id") == plan["interface"]["target_asset_id"],
                    )
                    check("unique_return_receipt", origin not in self.returned)
                    self.returned[origin] = effect
                if kind == "crew-return":
                    check("crew_return_origins", origins == request["return_origins"])
            elif kind == "routine-service":
                target = orders[key]["target"]
                schedule = self.maintenance[target]
                check("maintenance_effect_target", effect["target"] == target)
                check(
                    "maintenance_previous_due",
                    effect["previous_due_hour"],
                    schedule["next_due_hour"],
                    "h",
                )
                next_due = end + D(o["maintenance_interval_hours"])
                check("maintenance_next_due", effect["next_due_hour"], next_due, "h")
                schedule.update(
                    next_due_hour=next_due,
                    last_completed_hour=end,
                    completed_count=schedule["completed_count"] + 1,
                )
            elif kind in ("restock", "replace-brush"):
                resource = "stock:" + effect["material"] if kind == "restock" else "brush:cleaner"
                receipts = [
                    e
                    for e in events
                    if e["kind"] == "replenish"
                    and e["resource"] == resource
                    and e["source_id"] == key
                ]
                check("one_stock_receipt", len(receipts), 1, "count")
                quantity = D(effect["quantity"]) if kind == "restock" else D(o["brush_life_m2"])
                for e in receipts:
                    check("receipt_time", e["at_hour"], boundary, "h")
                    check("receipt_quantity", e["offered"], quantity, e["unit"])
                    if kind == "restock":
                        check("delivery_accepted", effect["accepted"], e["accepted"], e["unit"])
                        check("delivery_rejected", effect["rejected"], e["rejected"], e["unit"])
                if kind == "restock":
                    check(
                        "delivery_left_pipeline",
                        self.consumed.get((key, "upstream:" + effect["material"]), 0),
                        quantity,
                        "L" if effect["material"] == "water" else "kit",
                    )
                else:
                    check(
                        "one_brush_installed", self.consumed.get((key, "stock:brush"), 0), 1, "kit"
                    )
                    check(
                        "discarded_brush_allowance",
                        self.consumed.get((key, "brush:cleaner"), 0),
                        effect["discarded_allowance_m2"],
                        "m2",
                    )

        check("returned_map", record["state"]["support"]["returned"] == self.returned)
        for key, q in orders.items():
            check(
                "recorded_return_boundary",
                q.get("retrieved_at") == self.returned.get(key, {}).get("effective_at"),
            )
            if key in self.returned:
                check(
                    "failed_work_preserved",
                    q["status"] == "failed"
                    and (
                        q["execution_status"] == "stranded"
                        or q["kind"] == "crew-return"
                        and q["execution_status"] == "blocked"
                    ),
                )
        for reading in executive["observations"]:
            if reading["channel"].startswith("hardware-tracking:") and (
                o.get("equipment_recovery_enabled")
                or reading["source_id"].startswith("supervised-drive-test/2:")
            ):
                if not reading["source_id"].startswith("supervised-drive-test/2:"):
                    self.readings[reading["source_id"]] = reading
                continue  # Reconstructed from private test operands by HardwareReference.
            if not reading["channel"].startswith("robot-ready:"):
                continue
            source = reading["source_id"]
            if source not in self.readings:
                plan = self.plans[source.rsplit(":", 1)[-1]]
                end = next(
                    b
                    for _, b, s in executed_service_spans(
                        plan, o, self.crew_visits.get(plan["order"]["order_id"], ())
                    )
                    if s["effect"]
                )
                check(
                    "drive_test_method",
                    plan["order"]["action"] == "self-test"
                    and source.startswith(("supervised-drive-test/1:", "supervised-drive-test/2:")),
                )
                check("drive_measurement_time", reading["measured_at"], end, "h")
                check(
                    "drive_availability", reading["available_at"], math.ceil(float(end) - 1e-9), "h"
                )
                self.readings[source] = reading
            check("immutable_drive_observation", reading == self.readings[source])
        self.check_maintenance_state(record["state"], hour + 1, check)
        self.previous = {q["order_id"]: q for q in executive["orders"]}


def observation_limits(prior, current, plant):
    """Independent Decimal 3-sigma error propagation, in native units.

    Constant inventory offset cancels between readings. The same sampled drift
    rate contributes once for their elapsed-time difference. Other channels are
    explicitly independent under observation uncertainty version 1.
    """
    a, b = prior.get("measurement_uncertainty", {}), current.get("measurement_uncertainty", {})

    def variance(channel):
        record = b.get(channel, {})
        return (
            D(record.get("noise_sd", 0)) ** 2
            + D(record.get("bias_sd", 0)) ** 2
            + (D(record.get("elapsed_hours", 0)) * D(record.get("drift_sd_per_hour", 0))) ** 2
        )

    tank, old = b.get("h2_inventory_kg", {}), a.get("h2_inventory_kg", {})
    inventory = (
        D(tank.get("noise_sd", 0)) ** 2
        + D(old.get("noise_sd", 0)) ** 2
        + (
            (D(tank.get("elapsed_hours", 0)) - D(old.get("elapsed_hours", 0)))
            * D(tank.get("drift_sd_per_hour", 0))
        )
        ** 2
    )
    balance, power = inventory + variance("h2_outflow_kg"), variance("power_kw")
    return (
        3 * power.sqrt(),
        3 * (balance + power / D(plant["specific_energy_kwh_per_kg"]) ** 2).sqrt(),
        3 * (balance + variance("hydrogen_flow_kg")).sqrt(),
    )


def combined_observation_limit(sensors, scale, extra_three_sigma):
    return max(
        D(sensors["discrepancy_fraction"]) * scale,
        ((3 * D(sensors["noise_fraction"]) * scale) ** 2 + extra_three_sigma**2).sqrt(),
    )


def ambiguous_capacity(result, checks):
    """Necessary invariant of the opt-in hold policy, using independent decimals.

    Disagreement is uncertainty, so it cannot change a capacity estimate or
    create a confirmed incident in that interval. This is not full diagnosis.
    """
    sensors = result.get("controller_config", result["config"])["sensors"]
    if not sensors["enabled"] or sensors.get("ambiguity_policy") != "retain-capacity/1":
        return
    p = result.get("controller_config", result["config"])["plant"]
    minimum = D(p["electrolyser_kw"]) * D(p["min_load_fraction"])
    specific = D(p["specific_energy_kwh_per_kg"])
    for name, rows in result["records"].items():
        for row in rows:
            if D(row["requested"]["electrolyser_kw"]) < minimum - D("0.00001"):
                continue
            decision, observed = row["decision"], row["observations_after"]
            inflow = (
                D(observed["h2_inventory_kg"])
                - D(decision["observations"]["h2_inventory_kg"])
                + D(observed["h2_outflow_kg"])
            )
            electrical = D(observed["power_kw"]) / specific
            # Leave equality at the float/decimal threshold outside this claim.
            _, extra_balance, _ = observation_limits(decision["observations"], observed, p)
            if abs(inflow - electrical) <= combined_observation_limit(
                sensors, max(electrical, minimum / specific), extra_balance
            ) + D("1e-8"):
                continue
            before, after = decision["diagnosis"], row["diagnosis_after"]
            context = dict(controller=name, hour=row["hour"])
            compare(
                checks,
                "diagnosis.ambiguous_capacity_held",
                after["capacity_kw"],
                before["capacity_kw"],
                "kW",
                **context,
            )
            compare(
                checks,
                "diagnosis.ambiguous_status",
                after["status"] == "ambiguous",
                True,
                **context,
            )
            compare(
                checks,
                "diagnosis.ambiguous_not_confirmed",
                after["incidents"],
                before["incidents"],
                **context,
            )


def recovery_tests(result, checks):
    """Independent necessary evidence for a scheduled capacity confirmation.

    Recompute the consecutive electrical/balance test from saved observations;
    do not call the diagnosing or planning implementation. This does not certify
    the physical equipment, infer an unseen fault or validate branch probabilities.
    """
    if not any(
        row["decision"].get("probe_policy_revision") in (3, 4)
        for rows in result["records"].values()
        for row in rows
    ):
        return
    p, sensors = (
        result.get("controller_config", result["config"])["plant"],
        result.get("controller_config", result["config"])["sensors"],
    )
    minimum = D(p["electrolyser_kw"]) * D(p["min_load_fraction"])
    required = sensors["confirmation_hours"]
    for name, rows in result["records"].items():
        last_power = None
        count = 0
        for row in rows:
            decision = row["decision"]
            if decision.get("probe_policy_revision") not in (3, 4):
                last_power = None
                count = 0
                continue
            before, after = decision["diagnosis"], row["diagnosis_after"]
            prior, observed = decision["observations"], row["observations_after"]
            requested = D(row["requested"]["electrolyser_kw"])
            power = D(observed["power_kw"])
            expected = power / D(p["specific_energy_kwh_per_kg"])
            balance = (
                D(observed["h2_inventory_kg"])
                - D(prior["h2_inventory_kg"])
                + D(observed["h2_outflow_kg"])
            )
            extra_power, extra_balance, extra_flow = observation_limits(prior, observed, p)
            good = (
                bool(decision["probe"])
                and requested >= minimum - D("0.00001")
                and (
                    requested - power
                    <= combined_observation_limit(sensors, max(requested, D(1)), extra_power)
                    and abs(balance - expected)
                    <= combined_observation_limit(
                        sensors,
                        max(expected, minimum / D(p["specific_energy_kwh_per_kg"])),
                        extra_balance,
                    )
                )
            )
            flow_bad = abs(D(observed["hydrogen_flow_kg"]) - balance) > combined_observation_limit(
                sensors, max(abs(balance), minimum / D(p["specific_energy_kwh_per_kg"])), extra_flow
            )
            new_flow_isolation = (
                flow_bad and not before["flow_isolated"] and before["flow_count"] + 1 >= required
            )
            if good and not new_flow_isolation:
                count = (
                    count + 1
                    if last_power is not None and abs(last_power - requested) <= D("0.00001")
                    else 1
                )
            else:
                count = 0
            last_power = requested if good and not new_flow_isolation else None
            if D(after["capacity_kw"]) > D(before["capacity_kw"]) + D("0.00001"):
                compare(
                    checks,
                    "recovery.consecutive_evidence",
                    count >= required,
                    True,
                    controller=name,
                    hour=row["hour"],
                )
                compare(
                    checks,
                    "recovery.tested_capacity",
                    after["capacity_kw"],
                    min(D(p["electrolyser_kw"]), requested),
                    "kW",
                    controller=name,
                    hour=row["hour"],
                )
            if count >= required:
                count = 0
            compare(
                checks,
                "recovery.confirmation_counter",
                after["recovery_count"],
                count,
                "intervals",
                controller=name,
                hour=row["hour"],
            )
            for receipt in decision.get("recovery_planning", {}).get("receipts", []):
                compare(
                    checks,
                    "recovery.receipt_available",
                    receipt["report"]["available_at"] <= row["hour"],
                    True,
                    controller=name,
                    hour=row["hour"],
                )


def audit(result):
    """Read the archive directly. No Config, model, costing, weather or audit helper imports."""
    p, scenario = result["config"]["plant"], result["config"]["scenario"]
    checks, failures = [], []
    try:
        if result["config"].get("lifecycle"):
            companion = runpy.run_path(str(Path(__file__).with_name("lifecycle_reference.py")))
            checks.extend(companion["audit_run"](result))
        if any(
            c.get("evaluation", {}).get("conditional_returns")
            for rows in result["records"].values()
            for row in rows
            for c in row["decision"].get("service_control", {}).get("candidates", [])
        ):
            companion = runpy.run_path(str(Path(__file__).with_name("retrieval_reference.py")))
            checks.extend(companion["audit_run"](result))
        if (
            result.get("provenance", {})
            .get("uncertainty_world", {})
            .get("autonomy", {})
            .get("duration_model")
        ):
            companion = runpy.run_path(str(Path(__file__).with_name("duration_reference.py")))
            result, duration_checks = companion["prepare"](result)
            checks.extend(duration_checks)
        if any(
            r["decision"].get("performance_estimates")
            for rows in result["records"].values()
            for r in rows
        ):
            companion = runpy.run_path(str(Path(__file__).with_name("performance_reference.py")))
            checks.extend(companion["audit_run"](result))
        if any(
            r["decision"].get("uncertainty_beliefs")
            for rows in result["records"].values()
            for r in rows
        ):
            companion = runpy.run_path(str(Path(__file__).with_name("autonomy_reference.py")))
            checks.extend(companion["audit_run"](result))
        recovery_tests(result, checks)
        if any(
            row["decision"].get("recovery_planning", {}).get("version")
            in ("scheduled-load-tests/3", "scheduled-load-tests/4", "scheduled-load-tests/5")
            for rows in result["records"].values()
            for row in rows
        ):
            companion = runpy.run_path(str(Path(__file__).with_name("recovery_loop_reference.py")))
            checks.extend(companion["audit_run"](result))
        ambiguous_capacity(result, checks)
        if any(
            (policy.get("investigation") or {}).get("version") == "observed-service-investigation/3"
            for policy in result.get("provenance", {}).get("controller_policies", {}).values()
        ) or any(
            row["decision"]
            .get("service_control", {})
            .get("investigation", {})
            .get("implementation_id")
            == "observed-service-investigation/3"
            for rows in result["records"].values()
            for row in rows
        ):
            companion = runpy.run_path(
                str(Path(__file__).with_name("recovery_belief_reference.py"))
            )
            checks.extend(companion["audit_run"](result, interval, check_actions))
    except (KeyError, TypeError, ValueError, ArithmeticError, OSError) as exc:
        failures.append(
            dict(scope="scheduled recovery evidence", error=f"{type(exc).__name__}: {exc}")
        )
    weather = result["weather"]
    service_prices = result["config"].get("service_economics")
    if service_prices is not None:
        price_version = hashlib.sha256(
            json.dumps(
                service_prices, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        compare(
            checks,
            "service_price_identity",
            result.get("service_cost_version") == price_version,
            True,
        )
        for controller, records in result["records"].items():
            for row in records:
                compare(
                    checks,
                    "decision_service_prices",
                    row["decision"].get("service_cost_version") == price_version,
                    True,
                    controller=controller,
                    hour=row["hour"],
                )
    expected_controllers = result.get("provenance", {}).get("strategies", list(result["records"]))
    compare(
        checks,
        "controller_set",
        len(set(expected_controllers) ^ set(result["records"])),
        0,
        "count",
    )
    for name, rows in result["records"].items():
        p = result["config"]["plant"]
        if result["status"] == "complete":
            compare(
                checks, "interval_count", len(rows), scenario["hours"], "count", controller=name
            )
        before = initial(p, weather["truth"][weather["times"][0]]["ambient_c"])
        independent_rows = []
        service_config = result["config"].get("field_operations", {})
        soiling = (
            service_config.get("initial_soiling_fraction", 0)
            if service_config.get("enabled")
            else 0
        )
        field_energy = {
            a: service_config.get(a + "_battery_kwh", 0)
            if service_config.get(a + "_enabled")
            else 0
            for a in ("cleaner", "rover")
        }
        service_system = result["config"].get("service_system")
        random_reference = (
            ServiceRandomReference(result["config"])
            if service_system
            and service_system.get("outcome_randomness") == "target-action-request/1"
            else None
        )
        inspection_reference = (
            InspectionReference(
                result["config"],
                commissioned_only=bool(
                    result.get("provenance", {})
                    .get("controller_policies", {})
                    .get(name, {})
                    .get("investigation")
                ),
            )
            if service_system and service_system.get("inspection_model") == "referenced-contact/1"
            else None
        )
        support_reference = (
            SupportReference(service_system, result["field_operations_model"]["asset_ids"])
            if service_system and service_system.get("support_model") == "logistics/1"
            else None
        )
        hardware_reference = (
            HardwareReference(result["config"], result["field_operations_model"])
            if service_system
            and (
                service_system.get("equipment_recovery_enabled")
                or result["config"].get("faults", {}).get("hardware_model")
                == "actuator-interlock/1"
            )
            else None
        )
        visit_reference = (
            VisitReference(result["config"])
            if service_system and service_system.get("visit_bundling_enabled")
            else None
        )
        local_service_reference = (
            LocalServiceReference(result["config"])
            if service_system
            and (
                service_system.get("cleaning_policy", "legacy-condition") != "legacy-condition"
                or service_system.get("inspection_interface", "legacy-prepared")
                != "legacy-prepared"
            )
            else None
        )
        if service_system and service_system["inspector"] not in ("mobile", "both"):
            field_energy["rover"] = 0
        service_specs = {
            r["resource_id"]: r
            for r in result.get("field_operations_model", {})
            .get("definitions", {})
            .get("resources", [])
            if r["kind"] == "stock"
        }
        service_stocks = {k: D(r["initial"]) for k, r in service_specs.items()}
        surface_state, brush_pass = {}, {}
        surface_jobs = set()
        optical_surface = (
            service_system and service_system.get("cleaning_model") == "section-optical/1"
        )
        if optical_surface:
            for key, patches in result["field_operations_model"]["surface_model"][
                "initial"
            ].items():
                area = D(patches[-1]["end_m2"])
                surface_state[key] = [
                    (
                        D(0),
                        area,
                        D(service_config["initial_soiling_fraction"]),
                        D(service_system["initial_adhered_fraction"]),
                        D(service_system["initial_damage_fraction"]),
                    )
                ]
        if optical_surface and not surface_state:
            soiling = 0
        capacity_cleared = flow_cleared = False
        for i, row in enumerate(rows):
            try:
                p = row.get("lifecycle", {}).get("physical_plant", result["config"]["plant"])
                sample = weather["truth"][weather["times"][i]]
                delayed = i - scenario["delivery_delay_hours"]
                delivery = (
                    p["co2_delivery_kg"]
                    if delayed > 0 and delayed % p["co2_delivery_every_hours"] == 0
                    else 0
                )
                adjusted_pv = sample["pv_kw"] * (1 - soiling)
                service = row.get("field_operations")
                if service:
                    if local_service_reference:
                        local_service_reference.interval(service, i, checks, name)
                    if inspection_reference:
                        compare(
                            checks,
                            "inspection.decision_copy",
                            row["decision"]["field_operations"] == service["decision"],
                            True,
                            controller=name,
                            hour=i,
                        )
                        inspection_reference.interval(
                            service,
                            result["retrospective_truth_by_controller"][name][i].get(
                                "inspection_samples", []
                            ),
                            i,
                            capacity_cleared,
                            checks,
                            name,
                        )
                    if support_reference:
                        support_reference.interval(service, i, checks, name)
                    if random_reference:
                        random_reference.interval(
                            service,
                            result["retrospective_truth_by_controller"][name][i],
                            i,
                            checks,
                            name,
                        )
                    if hardware_reference:
                        hardware_reference.interval(
                            service,
                            result["retrospective_truth_by_controller"][name][i],
                            i,
                            checks,
                            name,
                        )
                    if visit_reference:
                        visit_reference.interval(service, i, checks, name)
                    if service.get("version") in (
                        "plant-service-contracts/1",
                        "plant-service-contracts/2",
                        "plant-service-contracts/3",
                        "plant-service-contracts/4",
                        "plant-service-contracts/5",
                        "plant-service-contracts/6",
                        "plant-service-contracts/7",
                        "plant-service-contracts/8",
                        "plant-service-contracts/9",
                        "plant-service-contracts/10",
                        "plant-service-contracts/11",
                        "plant-service-contracts/12",
                    ):
                        for event in service["resource_events"]:
                            kind = event["kind"]
                            if kind not in ("consume", "replenish"):
                                continue
                            key = event["resource"]
                            spec = service_specs[key]
                            compare(
                                checks,
                                "service.stock_unit:" + key,
                                event["unit"] == spec["unit"],
                                True,
                                controller=name,
                                hour=i,
                            )
                            if kind == "consume":
                                if key == "brush:cleaner" and event["mission_id"] not in brush_pass:
                                    brush_pass[event["mission_id"]] = (
                                        service_stocks[key]
                                        / D(service_system["brush_life_m2"])
                                        * D(service_config["cleaning_removal_fraction"])
                                    )
                                service_stocks[key] -= D(event["amount"])
                            else:
                                accepted = min(
                                    D(event["offered"]), D(spec["capacity"]) - service_stocks[key]
                                )
                                compare(
                                    checks,
                                    "service.accepted:" + key,
                                    event["accepted"],
                                    accepted,
                                    spec["unit"],
                                    controller=name,
                                    hour=i,
                                )
                                compare(
                                    checks,
                                    "service.rejected:" + key,
                                    event["rejected"],
                                    D(event["offered"]) - accepted,
                                    spec["unit"],
                                    controller=name,
                                    hour=i,
                                )
                                service_stocks[key] += accepted
                            stock_bounds(
                                checks,
                                key,
                                service_stocks[key],
                                spec["capacity"],
                                spec["unit"],
                                controller=name,
                                hour=i,
                            )
                        for balance in service["state"]["executive"]["resources"]:
                            compare(
                                checks,
                                "service.stock_ending:" + balance["resource"],
                                balance["ending"],
                                service_stocks[balance["resource"]],
                                balance["unit"],
                                controller=name,
                                hour=i,
                            )
                        event_bus = sum(
                            (
                                D(e["bus_kwh"])
                                for e in service["mission_events"]
                                if e["kind"] == "interval"
                            ),
                            D(0),
                        )
                        if service_system.get("dock_standby_kw"):
                            standby = service["standby"]
                            installed = "dock" in result["field_operations_model"]["asset_ids"]
                            demand = D(service_system["dock_standby_kw"]) if installed else D(0)
                            pv = D(row["pv_kw"])
                            battery_power = min(
                                D(p["battery_kwh"]) * D(p["battery_c_rate"]),
                                max(D(0), D(before["battery_kwh"]))
                                * D(p["roundtrip_efficiency"]).sqrt(),
                            )
                            supplied = demand if demand <= pv + battery_power + D("1e-9") else D(0)
                            expected_standby = dict(
                                requested_kwh=demand,
                                applied_kwh=supplied,
                                unserved_kwh=demand - supplied,
                                pv_available_kw=pv,
                                battery_available_kw=battery_power,
                            )
                            for key, value in expected_standby.items():
                                compare(
                                    checks,
                                    "service.standby_" + key,
                                    standby[key],
                                    value,
                                    "kW" if key.endswith("kw") else "kWh",
                                    controller=name,
                                    hour=i,
                                )
                            compare(
                                checks,
                                "service.standby_controls",
                                standby["control_available"],
                                installed and supplied == demand,
                                controller=name,
                                hour=i,
                            )
                            event_bus += supplied
                        event_robot = sum(
                            (
                                D(e["battery_kwh"])
                                for e in service["mission_events"]
                                if e["kind"] == "interval"
                            ),
                            D(0),
                        )
                        compare(
                            checks,
                            "service.event_bus_energy",
                            service["applied_service_kwh"],
                            event_bus,
                            "kWh",
                            controller=name,
                            hour=i,
                        )
                        compare(
                            checks,
                            "service.event_robot_energy",
                            service["robot_use_kwh"],
                            event_robot,
                            "kWh",
                            controller=name,
                            hour=i,
                        )
                        compare(
                            checks,
                            "service.unapplied_request",
                            service["unapplied_service_kwh"],
                            D(service["requested_service_kwh"]) - event_bus,
                            "kWh",
                            controller=name,
                            hour=i,
                        )
                    if optical_surface:
                        surface_jobs.update(
                            p["order"]["order_id"]
                            for p in service["new_missions"]
                            if p["order"]["action"] == "clean-section"
                        )
                        solar = row["component_records"]["solar"]
                        encoded = json.loads(solar["parameters"]["design_json"])
                        baseline = service["optical"]["baseline_design"]
                        for j, section in enumerate(encoded["sections"]):
                            key = f"PV-{j + 1:02d}"
                            patches = surface_state.get(key)
                            if patches:
                                transmission = (
                                    sum(
                                        (b - a) * (1 - loose) * (1 - adhered) * (1 - damaged)
                                        for a, b, loose, adhered, damaged in patches
                                    )
                                    / patches[-1][1]
                                )
                                expected_soil = (
                                    1 - (1 - D(baseline["sections"][j]["soiling"])) * transmission
                                )
                                compare(
                                    checks,
                                    "surface.optical_binding:" + key,
                                    section["soiling"],
                                    expected_soil,
                                    controller=name,
                                    hour=i,
                                )
                        adjusted_pv, clipped = optical_reference(
                            solar["parameters"], service["optical"]["source"], row["time"]
                        )
                        compare(
                            checks,
                            "surface.available_pv",
                            row["pv_kw"],
                            adjusted_pv,
                            "kW",
                            controller=name,
                            hour=i,
                        )
                        compare(
                            checks,
                            "surface.converter_clipping",
                            row["solar_detail"]["clipped_kw"],
                            clipped,
                            "kW",
                            controller=name,
                            hour=i,
                        )
                        for operation in service["surface_events"]:
                            compare(
                                checks,
                                "surface.effect_boundary",
                                operation["effective_at"],
                                i + 1,
                                controller=name,
                                hour=i,
                            )
                            portable = operation.get("method", "").startswith("portable-")
                            for term in ("efficacy_start", "efficacy_end"):
                                compare(
                                    checks,
                                    "surface.brush_efficacy",
                                    operation[term],
                                    service_system["portable_loose_removal"]
                                    if portable
                                    else brush_pass[operation["order_id"]],
                                    controller=name,
                                    hour=i,
                                )
                            if portable:
                                compare(
                                    checks,
                                    "surface.portable_method",
                                    operation["method"]
                                    == "portable-" + service_system["portable_cleaner"],
                                    True,
                                    controller=name,
                                    hour=i,
                                )
                                compare(
                                    checks,
                                    "surface.adhered_treatment",
                                    operation["adhered_removal"],
                                    service_system["portable_adhered_removal"]
                                    if service_system["portable_cleaner"] == "wet"
                                    else 0,
                                    controller=name,
                                    hour=i,
                                )
                            surface_state[operation["section"]] = surface_reference(
                                surface_state[operation["section"]], operation
                            )
                        area = sum(
                            D(op["end_m2"]) - D(op["start_m2"]) for op in service["surface_events"]
                        )
                        compare(
                            checks,
                            "surface.covered_area",
                            service["treated_area_m2"],
                            area,
                            "m2",
                            controller=name,
                            hour=i,
                        )
                        compare(
                            checks,
                            "surface.brush_wear",
                            service["brush_wear_m2"],
                            sum(
                                D(op["end_m2"]) - D(op["start_m2"])
                                for op in service["surface_events"]
                                if not op.get("method", "").startswith("portable-")
                            ),
                            "m2",
                            controller=name,
                            hour=i,
                        )
                        compare(
                            checks,
                            "surface.brush_ledger_coverage",
                            sum(
                                D(op["end_m2"]) - D(op["start_m2"])
                                for op in service["surface_events"]
                                if not op.get("method", "").startswith("portable-")
                            ),
                            sum(
                                D(e["amount"])
                                for e in service["resource_events"]
                                if e["kind"] == "consume"
                                and e["resource"] == "brush:cleaner"
                                and e["mission_id"] in surface_jobs
                            ),
                            "m2",
                            controller=name,
                            hour=i,
                        )
                    compare(
                        checks,
                        "service.soiling_before",
                        service["soiling_before"],
                        soiling,
                        controller=name,
                        hour=i,
                    )
                    compare(
                        checks,
                        "service.bus_load",
                        row.get("service_kw"),
                        service["charge_input_kwh"] + service.get("fixed_service_kwh", 0),
                        controller=name,
                        hour=i,
                    )
                    compare(
                        checks,
                        "service.robot_energy_before",
                        sum(service["energy_before_kwh"].values()),
                        sum(field_energy.values()),
                        controller=name,
                        hour=i,
                    )
                    energy_end = (
                        sum(field_energy.values())
                        + service["charge_input_kwh"] * service_config["charging_efficiency"]
                        - service["robot_use_kwh"]
                    )
                    compare(
                        checks,
                        "service.robot_energy_after",
                        sum(service["energy_after_kwh"].values()),
                        energy_end,
                        controller=name,
                        hour=i,
                    )
                    compare(
                        checks,
                        "service.charging_loss",
                        service["charging_loss_kwh"],
                        service["charge_input_kwh"] * (1 - service_config["charging_efficiency"]),
                        controller=name,
                        hour=i,
                    )
                    if service["electrolyser_isolated"]:
                        compare(
                            checks,
                            "service.isolation",
                            row["applied"]["electrolyser_kw"],
                            0,
                            controller=name,
                            hour=i,
                        )
                    field_energy = service["energy_after_kwh"]
                    if optical_surface:
                        for key, patches in surface_state.items():
                            surface_state[key] = [
                                (
                                    a,
                                    b,
                                    min(D(".3"), loose + D(service_config["soiling_per_day"]) / 24),
                                    adhered,
                                    damaged,
                                )
                                for a, b, loose, adhered, damaged in patches
                            ]
                            observed = service["surface_after"][key]
                            for position, term in (
                                (2, "removable"),
                                (3, "adhered"),
                                (4, "damaged"),
                            ):
                                expected_fraction = (
                                    sum((p[1] - p[0]) * p[position] for p in surface_state[key])
                                    / surface_state[key][-1][1]
                                )
                                recorded_fraction = sum(
                                    (D(p["end_m2"]) - D(p["start_m2"])) * D(p[term])
                                    for p in observed
                                ) / D(observed[-1]["end_m2"])
                                compare(
                                    checks,
                                    "surface.after:" + key + ":" + term,
                                    recorded_fraction,
                                    expected_fraction,
                                    controller=name,
                                    hour=i,
                                )
                        soiling = (
                            float(
                                sum(
                                    (b - a) * loose
                                    for patches in surface_state.values()
                                    for a, b, loose, _, _ in patches
                                )
                                / sum(p[-1][1] for p in surface_state.values())
                            )
                            if surface_state
                            else 0
                        )
                    else:
                        soiling = min(
                            0.3,
                            soiling
                            * (1 - service_config["cleaning_removal_fraction"])
                            ** service["cleanings_completed"]
                            + service_config["soiling_per_day"] / 24,
                        )
                    compare(
                        checks,
                        "service.soiling_after",
                        service["soiling_after"],
                        soiling,
                        controller=name,
                        hour=i,
                    )
                expected = interval(
                    p,
                    before,
                    row["applied"],
                    adjusted_pv,
                    sample["ambient_c"],
                    delivery,
                    service_kw=row.get("service_kw", 0),
                )
                policy = result["config"].get("faults", {"lifecycle": "legacy-timed"})
                fault = i >= scenario["fault_start_hour"] and (
                    policy["lifecycle"] == "persistent"
                    or i < scenario["fault_start_hour"] + scenario["fault_duration_hours"]
                )
                capacity = p["electrolyser_kw"] * (
                    scenario["capacity_fraction"] if fault and not capacity_cleared else 1
                )
                recorded_truth = result.get("retrospective_truth_by_controller", {}).get(name)
                if recorded_truth:
                    truth = recorded_truth[i]
                    compare(
                        checks,
                        "fault.capacity",
                        truth["capacity_kw"],
                        capacity,
                        controller=name,
                        hour=i,
                    )
                    compare(
                        checks,
                        "fault.flow_bias",
                        truth["flow_bias_fraction"],
                        scenario["flow_bias_fraction"] if fault and not flow_cleared else 0,
                        controller=name,
                        hour=i,
                    )
                    for effect in truth.get("service_effects", []):
                        if effect.get("kind") == "hardware-procedure" and hardware_reference:
                            continue  # Checked against the service hardware's separate fault state.
                        compare(
                            checks,
                            "repair.boundary",
                            effect["effective_at_hour"],
                            i + 1,
                            controller=name,
                            hour=i,
                        )
                        if (
                            effect["before"]["capacity_fault_active"]
                            and not effect["after"]["capacity_fault_active"]
                        ):
                            allowed = effect["kind"] in ("human-service", "module-replacement") or (
                                effect["kind"] == "reset"
                                and policy["capacity_cause"] == "resettable-trip"
                            )
                            compare(
                                checks,
                                "repair.compatibility",
                                allowed,
                                True,
                                controller=name,
                                hour=i,
                            )
                            capacity_cleared = True
                        if (
                            effect["before"]["flow_fault_active"]
                            and not effect["after"]["flow_fault_active"]
                        ):
                            compare(
                                checks,
                                "repair.flow_compatibility",
                                effect["kind"] in ("human-service", "flow-calibration"),
                                True,
                                controller=name,
                                hour=i,
                            )
                            flow_cleared = True
                action_checks = check_actions(
                    p,
                    before,
                    {**expected, "forced_trip": row["forced_trip"]},
                    capacity,
                    row["requested"],
                )
                checks.extend({**c, "controller": name, "hour": i} for c in action_checks)
                for k, v in expected["state"].items():
                    compare(checks, "state." + k, row["state"].get(k), v, controller=name, hour=i)
                for k, v in expected.items():
                    if k not in ("state", "applied"):
                        compare(checks, k, row.get(k), v, controller=name, hour=i)
                for k in ("pv_kw", "ambient_c"):
                    compare(
                        checks,
                        "weather." + k,
                        row.get(k),
                        adjusted_pv if k == "pv_kw" else sample[k],
                        controller=name,
                        hour=i,
                    )
                source = row["decision"]["forecast"]["source"]
                available = datetime.fromisoformat(source["available_at"].replace("Z", "+00:00"))
                decision = datetime.fromisoformat(row["time"].replace("Z", "+00:00"))
                compare(
                    checks,
                    "forecast_available",
                    max(0, (available - decision).total_seconds()),
                    0,
                    "s",
                    controller=name,
                    hour=i,
                )
                independent_rows.append(
                    {
                        **expected,
                        "incident": row.get("incident", False),
                        **{
                            k: row[k]
                            for k in ("intervention_accounting", "field_operations", "lifecycle")
                            if k in row
                        },
                    }
                )
                before = expected["state"]
            except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
                failures.append(dict(controller=name, hour=i, error=f"{type(exc).__name__}: {exc}"))
                break
        try:
            costs = economics(
                result["config"]["plant"],
                result["config"]["costs"],
                independent_rows,
                result["config"].get("service_economics"),
            )
            metrics = result["metrics"][name]
            field_period_outcomes(rows, metrics.get("service_outcomes"), checks, name)
            for k, v in costs.items():
                if k == "components":
                    for component, value in v.items():
                        compare(
                            checks,
                            "cost." + component,
                            metrics[k].get(component),
                            value,
                            "EUR",
                            controller=name,
                        )
                elif k == "service_views":
                    for view, value in v.items():
                        compare(
                            checks,
                            "service_cost." + view,
                            metrics["field_operations"]["views"][view]["total_eur"],
                            value,
                            "EUR",
                            controller=name,
                        )
                else:
                    compare(checks, "cost." + k, metrics.get(k), v, controller=name)
            for metric, source in (
                ("methane_kg", None),
                ("h2_produced_kg", "h2_produced_kg"),
                ("curtailed_kwh", "curtailed_kwh"),
                ("reactor_starts", "reactor_start"),
                ("electrolyser_starts", "electrolyser_start"),
            ):
                compare(
                    checks,
                    metric,
                    metrics.get(metric),
                    sum(
                        r[source] if source else r["applied"]["methane_kg"]
                        for r in independent_rows
                    ),
                    controller=name,
                )
        except (KeyError, TypeError, ValueError, ArithmeticError) as exc:
            failures.append(dict(controller=name, error=f"{type(exc).__name__}: {exc}"))
    return {
        "checker": VERSION,
        "run_id": result.get("run_id"),
        "status": result["status"],
        "passed": result["status"] == "complete"
        and not failures
        and all(c["passed"] for c in checks),
        "checks": checks,
        "failures": failures,
        "scope": "Independent hourly physics, declared operating limits, weather availability and economic accounting. Version-3 scheduled recovery additionally checks necessary consecutive electrical/balance evidence and receipt availability. Opt-in retain-capacity diagnosis checks that an ambiguous informative interval holds capacity and creates no confirmed incident. Investigation version 3 additionally checks declared recovery-belief arithmetic, original observation/work bindings and admitted operating-test feasibility. These necessary conditions do not diagnose hidden faults, fully reconstruct the observer or empirically calibrate probabilities. Other diagnosis incident flags and service success outcomes remain input evidence, not independently diagnosed or empirically validated. Field energy, soiling, compatible repair boundaries and recorded service costs are checked.",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive")
    parser.add_argument("--out", default="build/engineering/reference.json")
    args = parser.parse_args()
    with gzip.open(args.archive, "rt") as f:
        result = json.load(f)
    report = audit(result)
    path = Path(args.out)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, indent=2, allow_nan=False))
    print(json.dumps({k: v for k, v in report.items() if k != "checks"}))
    if not report["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
