"""Always-on physical checks, reusable against stored traces."""

from dataclasses import asdict, dataclass
from math import isfinite

ABSOLUTE = 1e-5
RELATIVE = 1e-8


@dataclass(frozen=True)
class Audit:
    check_id: str
    component: str
    interval: int | None
    passed: bool
    expected: str
    residual: float | None
    unit: str
    tolerance: float


def serializable_context(value):
    """Keep invalid numerical evidence explicit without emitting non-standard JSON."""
    if isinstance(value, float) and not isfinite(value):
        return {"nonfinite": str(value)}
    if isinstance(value, dict):
        return {key: serializable_context(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [serializable_context(item) for item in value]
    return value


class PhysicalAuditError(ValueError):
    def __init__(self, audits, context):
        self.audits, self.context = audits, serializable_context(context)
        super().__init__(
            "Physical audit failed: " + ", ".join(a["check_id"] for a in audits if not a["passed"])
        )


def check(key, component, residual, unit, scale=1, expected="residual = 0", interval=None):
    tolerance = ABSOLUTE + RELATIVE * max(1, abs(scale))
    finite = isfinite(residual)
    return asdict(
        Audit(
            key,
            component,
            interval,
            finite and abs(residual) <= tolerance,
            expected,
            residual if finite else None,
            unit,
            tolerance,
        )
    )


def physical(p, before, row, interval=None, capacity=None):
    s, a = row["state"], row["applied"]
    audits = [
        check(
            "service_power_bounds",
            "services",
            max(
                0,
                -row.get("service_kw", 0),
                row.get("service_kw", 0) - row["pv_kw"] - a["discharge_kw"],
            ),
            "kW",
            interval=interval,
        )
    ]
    for key, component, unit, scale in (
        ("electrical_residual_kwh", "site", "kWh", abs(row["pv_kw"]) + abs(row["demand_kw"])),
        (
            "thermal_residual_kwh",
            "reactor",
            "kWh",
            abs(row["reaction_heat_kwh"])
            + abs(row["heat_loss_kwh"])
            + a["heater_kw"]
            + a["cooling_kw"],
        ),
        ("h2_residual_kg", "hydrogen", "kg", p.h2_capacity_kg),
        ("co2_residual_kg", "co2", "kg", p.co2_capacity_kg),
        (
            "reaction_mass_residual_kg",
            "reactor",
            "kg",
            row["co2_consumed_kg"] + row["h2_consumed_kg"],
        ),
    ):
        audits.append(check(key, component, row[key], unit, scale, interval=interval))
    for key, component, value, lower, upper, unit in (
        ("battery_bounds", "battery", s["battery_kwh"], 0, p.battery_kwh, "kWh"),
        ("hydrogen_bounds", "hydrogen", s["h2_kg"], 0, p.h2_capacity_kg, "kg"),
        ("co2_bounds", "co2", s["co2_kg"], 0, p.co2_capacity_kg, "kg"),
        ("curtailment_nonnegative", "solar", row["curtailed_kwh"], 0, float("inf"), "kWh"),
    ):
        residual = max(lower - value, value - upper, 0) if isfinite(value) else float("nan")
        audits.append(
            check(
                key,
                component,
                residual,
                unit,
                upper if isfinite(upper) else row["pv_kw"],
                f"{lower} <= value <= {upper}",
                interval,
            )
        )
    audits.append(
        check(
            "battery_exclusive",
            "battery",
            min(a["charge_kw"], a["discharge_kw"]),
            "kW",
            p.battery_kw,
            interval=interval,
        )
    )
    for key, value in a.items():
        audits.append(
            check(
                "action_" + key,
                "site",
                min(0, value) if isfinite(value) else float("nan"),
                "kg" if key == "methane_kg" else "kW",
                interval=interval,
            )
        )
    for key, maximum, minimum, component in (
        (
            "electrolyser_kw",
            p.electrolyser_kw if capacity is None else capacity,
            p.min_kw,
            "electrolyser",
        ),
        ("charge_kw", p.battery_kw, 0, "battery"),
        ("discharge_kw", p.battery_kw, 0, "battery"),
        ("heater_kw", p.heater_max_kw, 0, "reactor"),
        ("cooling_kw", p.cooling_max_kw, 0, "reactor"),
        ("methane_kg", p.methane_max_kgph, p.methane_min_kgph, "reactor"),
    ):
        value = a[key]
        residual = max(0, value - maximum, minimum - value if value > 1e-5 else 0)
        audits.append(
            check(
                "operating_bounds_" + key,
                component,
                residual,
                "kg" if key == "methane_kg" else "kW",
                maximum,
                interval=interval,
            )
        )
    audits.append(
        check(
            "thermal_exclusive",
            "reactor",
            min(a["heater_kw"], a["cooling_kw"]),
            "kW",
            max(p.heater_max_kw, p.cooling_max_kw),
            interval=interval,
        )
    )
    expected_commitment = (
        max(0, (p.minimum_run_hours if not before.reactor_on else before.commitment_hours) - 1)
        if s["reactor_on"]
        else 0
    )
    audits.append(
        check(
            "commitment_transition",
            "reactor",
            s["commitment_hours"] - expected_commitment,
            "h",
            interval=interval,
        )
    )
    if s["reactor_on"]:
        for label, value in (("begin", before.temperature_c), ("end", s["temperature_c"])):
            audits.append(
                check(
                    "production_temperature_" + label,
                    "reactor",
                    max(p.temperature_min_c - value, value - p.temperature_max_c, 0),
                    "°C",
                    p.temperature_max_c,
                    interval=interval,
                )
            )
    if "forced_trip" in row:
        expected = bool(
            (before.commitment_hours or row["requested"]["methane_kg"] >= p.methane_min_kgph)
            and not s["reactor_on"]
        )
        audits.append(
            check(
                "explicit_trip",
                "reactor",
                int(expected != row["forced_trip"]),
                "boolean",
                interval=interval,
            )
        )
    if p.integration is not None:
        from methane.integration import execute as integrate

        stored = row.get("integration", {})
        computed = integrate(
            p,
            before,
            a,
            a["electrolyser_kw"] + row["startup_kwh"],
            a["heater_kw"]
            + a["cooling_kw"] * p.cooling_electric_fraction
            + a["methane_kg"] * p.methane_electric_kwh_per_kg
            + p.auxiliary_kw * s["reactor_on"],
            row["h2_produced_kg"],
            stored.get("water_delivery_l", 0),
            row["ambient_c"],
        )
        audits.extend({**item, "interval": interval} for item in computed["audits"])
        audits.append(
            check(
                "integration_record_identity",
                "integration",
                int(
                    stored.get("version") != computed["version"]
                    or stored.get("parameters") != computed["parameters"]
                    or stored.get("model_identity") != computed.get("model_identity")
                    or stored.get("source_ids") != computed.get("source_ids")
                    or stored.get("converter_points_kw") != computed.get("converter_points_kw")
                ),
                "boolean",
                interval=interval,
            )
        )
        for k, v in computed.items():
            if isinstance(v, (int, float)):
                audits.append(
                    check(
                        "recorded_integration_" + k,
                        "integration",
                        stored.get(k, float("nan")) - v,
                        "boolean"
                        if isinstance(v, bool)
                        else "L"
                        if k.endswith("_l")
                        else "kWh"
                        if k.endswith("_kwh")
                        else "kW",
                        interval=interval,
                    )
                )
        audits.extend(
            [
                check(
                    "integrated_bus_demand",
                    "site",
                    row["demand_kw"] - row.get("service_kw", 0) - computed["dc_kw"],
                    "kW",
                    interval=interval,
                ),
                check(
                    "water_state",
                    "integration",
                    s.get("water_l", float("nan")) - computed["ending_water_l"],
                    "L",
                    interval=interval,
                ),
            ]
        )
    return audits


def require(audits, context):
    if any(not a["passed"] for a in audits):
        raise PhysicalAuditError(audits, context)
