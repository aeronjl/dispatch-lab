"""Hourly field assets, work orders and bounded service capabilities.

Illustrative teaching fixture, not a vendor performance model. Scheduling consumes
observations only. Execution receives physical fault state; only named sensor
reports cross back. Effects and reports become available at the next boundary.
"""

import copy
import hashlib
from dataclasses import asdict, dataclass
from math import isfinite

import numpy as np

from methane.audit import check, require

VERSION = "field-operations/1"
ASSETS = {
    "cleaner": "PLANT-01/CLEAN-01",
    "rover": "PLANT-01/ROVER-01",
    "dock": "PLANT-01/DOCK-01",
    "reset": "PLANT-01/ELY-01/RESET",
}


@dataclass(frozen=True)
class FieldOperations:
    enabled: bool = False
    cleaner_enabled: bool = True
    rover_enabled: bool = True
    reset_enabled: bool = True
    human_fallback: bool = True
    route_open: bool = True
    dock_available: bool = True
    initial_soiling_fraction: float = 0.05
    soiling_per_day: float = 0.005
    cleaning_threshold: float = 0.04
    cleaning_removal_fraction: float = 0.9
    cleaner_battery_kwh: float = 2
    rover_battery_kwh: float = 2
    mission_power_kw: float = 0.2
    return_reserve_kwh: float = 0.2
    dock_kw: float = 1
    charging_efficiency: float = 0.9
    cleaning_hours: int = 2
    inspection_hours: int = 1
    human_lead_hours: int = 8
    human_work_hours: int = 2
    service_kits: int = 2
    cleaning_kits: int = 12
    mission_failure_probability: float = 0.05
    repair_success_probability: float = 0.95

    def __post_init__(self):
        for key, value in asdict(self).items():
            if not isinstance(value, bool) and (not isfinite(value) or value < 0):
                raise ValueError(f"{key} must be finite and nonnegative.")
        for key in ("initial_soiling_fraction", "cleaning_threshold"):
            if not 0 <= getattr(self, key) <= 0.3:
                raise ValueError(f"{key} must be in [0, .3].")
        for key in (
            "cleaning_removal_fraction",
            "mission_failure_probability",
            "repair_success_probability",
            "charging_efficiency",
        ):
            if not 0 <= getattr(self, key) <= 1:
                raise ValueError(f"{key} must be in [0, 1].")
        if self.charging_efficiency == 0:
            raise ValueError("Charging efficiency must be positive.")
        for key in (
            "cleaning_hours",
            "inspection_hours",
            "human_lead_hours",
            "human_work_hours",
            "service_kits",
            "cleaning_kits",
        ):
            if int(getattr(self, key)) != getattr(self, key):
                raise ValueError(f"{key} must be a whole number.")
        if min(self.cleaning_hours, self.inspection_hours, self.human_work_hours) < 1:
            raise ValueError("Work takes at least one hourly interval.")
        if self.return_reserve_kwh > min(self.cleaner_battery_kwh, self.rover_battery_kwh):
            raise ValueError("Return reserve exceeds a robot's battery capacity.")


def manifest(config):
    return {
        "implementation_id": VERSION,
        "asset_ids": ASSETS,
        "parameters": asdict(config),
        "capabilities": {
            "cleaner": "Remove a fraction of the lumped available-DC soiling loss",
            "rover": "Read a dry-contact module-trip indicator at the electrolyser",
            "reset": "One reset attempt per incident, only after a latched indication",
            "human-service": "Replace module and calibrate hydrogen-flow channel using one kit",
        },
        "access_edges": [
            ["dock", "solar"],
            ["dock", "electrolyser"],
            ["site-gate", "electrolyser"],
        ],
        "information_boundary": "Scheduler uses diagnosis, ideal soiling monitor, mission status and reported contact. Hidden fault effects stay in execution.",
        "timing": "One-hour phases. Completed effects and sensor reports first apply at the following decision boundary. No emergency response is modelled.",
        "power_policy": "A shared DC dock reserves at most measured solar power; no plant-battery charging at night. Future dock loads and cleaning benefits are not anticipated by process MPC.",
        "solar_scope": "Additional lumped available-DC loss, applied after the saved conversion. Not an optical/string model; base converter clipping is unchanged. No rain, snow or abrasion physics.",
        "assumptions": [
            "All hardware, cost and reliability inputs are illustrative",
            "Declared traversable routes; no locomotion or obstacle dynamics",
            "Initially full robot batteries are explicit initial inventories",
            "Cleaning and service kits are finite; no automatic resupply",
            "One rover and one cleaner may work concurrently; one electrolyser work chain per incident",
            "Failed robot missions require human follow-up; no invisible robot self-repair",
            "Work completion does not certify restored production; tracking probes still required",
            "Electrolyser is isolated during reset and hands-on service; isolation is an ideal interlock in this hourly model",
        ],
        "sources": [
            "https://www.exrobotics.com/our-products",
            "https://www.ecoppia.com/",
            "https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro",
        ],
    }


class FieldRuntime:
    def __init__(self, config, seed):
        self.config, self.seed = config, seed
        self.energy = {
            r: getattr(config, r + "_battery_kwh") if getattr(config, r + "_enabled") else 0
            for r in ("cleaner", "rover")
        }
        self.health = {
            r: "available" if getattr(config, r + "_enabled") else "disabled" for r in self.energy
        }
        self.soiling = config.initial_soiling_fraction
        self.kits, self.cleaning_kits = config.service_kits, config.cleaning_kits
        self.orders, self.seen_incidents, self.messages = [], set(), []
        self.interval = None

    def _draw(self, key):
        channel = int.from_bytes(hashlib.sha256(key.encode()).digest()[:4], "big")
        return float(np.random.default_rng(np.random.SeedSequence([self.seed, channel])).random())

    def _enqueue(self, kind, hour, reason, incident=0):
        order = {
            "id": f"WO-{len(self.orders) + 1:04}",
            "kind": kind,
            "created_hour": hour,
            "reason": reason,
            "incident": incident,
            "kind_sequence": 1 + sum(o["kind"] == kind for o in self.orders),
            "phase": "queued",
            "remaining": 0,
            "status": "queued",
            "reported": None,
        }
        self.orders.append(order)
        self.messages.append(
            {"hour": hour, "component": "services", "label": f"{kind}: work queued ({order['id']})"}
        )
        return order

    def _human(self, hour, reason, incident):
        if not self.config.human_fallback:
            self.messages.append(
                {
                    "hour": hour,
                    "component": "services",
                    "label": "Human service needed; fallback disabled",
                }
            )
            return
        if not any(o["kind"] == "human-service" and o["incident"] == incident for o in self.orders):
            self._enqueue("human-service", hour, reason, incident)

    def isolation_horizon(self, horizon):
        isolated = [False] * horizon
        for o in self.orders:
            if o["status"] != "active":
                continue
            if o["kind"] == "reset":
                isolated[0] = True
            elif o["kind"] == "human-service":
                offset = o["remaining"] if o["phase"] == "travel" else 0
                duration = self.config.human_work_hours if offset else o["remaining"]
                for t in range(offset, min(horizon, offset + duration)):
                    isolated[t] = True
        return isolated

    def begin(self, hour, diagnosis, available_pv):
        """Reserve tasks and dock energy from information available at this boundary."""
        c = self.config
        self.interval = {
            "version": VERSION,
            "hour": hour,
            "assets": {
                "cleaner": c.cleaner_enabled,
                "rover": c.rover_enabled,
                "dock": c.cleaner_enabled or c.rover_enabled,
            },
            "energy_before_kwh": self.energy.copy(),
            "soiling_before": self.soiling,
            "charge_input_kwh": 0.0,
            "charging_loss_kwh": 0.0,
            "robot_use_kwh": 0.0,
            "cleaner_hours": 0,
            "rover_hours": 0,
            "cleaning_kits_used": 0,
            "cleanings_completed": 0,
            "service_kits_used": 0,
            "human_visits": 0,
            "human_hours": 0,
            "reset_attempts": 0,
            "repair_attempts": 0,
            "retrospective_effects": [],
        }
        # No fault type, true capacity, severity or future fault schedule is an argument.
        if diagnosis.active_incident and diagnosis.incidents not in self.seen_incidents:
            self.seen_incidents.add(diagnosis.incidents)
            if c.rover_enabled and self.health["rover"] == "available":
                self._enqueue("inspection", hour, diagnosis.status, diagnosis.incidents)
            else:
                self._human(hour, diagnosis.status, diagnosis.incidents)
        if (
            c.cleaner_enabled
            and self.health["cleaner"] == "available"
            and self.soiling >= c.cleaning_threshold
            and self.cleaning_kits > 0
            and not any(
                o["kind"] == "cleaning" and o["status"] in ("queued", "active") for o in self.orders
            )
        ):
            self._enqueue("cleaning", hour, "Ideal soiling monitor exceeds threshold")
        for o in self.orders:
            if o["status"] != "queued":
                continue
            kind = o["kind"]
            if kind == "human-service":
                if self.kits < 1:
                    o["blocked"] = "No service kit; human resupply required"
                    continue
                if any(
                    x is not o and x["status"] == "active" and x["kind"] == kind
                    for x in self.orders
                ):
                    continue
                o.update(
                    status="active",
                    phase="travel" if c.human_lead_hours else "perform",
                    remaining=c.human_lead_hours or c.human_work_hours,
                )
            elif kind == "reset":
                o.update(status="active", phase="perform", remaining=1)
            else:
                robot = "cleaner" if kind == "cleaning" else "rover"
                duration = (c.cleaning_hours if robot == "cleaner" else c.inspection_hours) + 3
                if not c.route_open:
                    o["blocked"] = "Declared route unavailable; no automatic traversal"
                    if kind == "inspection":
                        o["status"] = "blocked"
                        self._human(hour, o["blocked"], o["incident"])
                    continue
                if self.health[robot] != "available":
                    o["blocked"] = "Robot needs human follow-up"
                    continue
                if any(
                    x is not o and x.get("robot") == robot and x["status"] == "active"
                    for x in self.orders
                ):
                    continue
                if self.energy[robot] + 1e-9 < duration * c.mission_power_kw + c.return_reserve_kwh:
                    o["blocked"] = "Insufficient mission energy including return reserve"
                    if kind == "inspection" and (
                        not c.dock_available
                        or getattr(c, robot + "_battery_kwh")
                        < duration * c.mission_power_kw + c.return_reserve_kwh
                    ):
                        o["status"] = "blocked"
                        self._human(hour, o["blocked"], o["incident"])
                    continue
                o.update(robot=robot, status="active", phase="travel", remaining=1)
            o.pop("blocked", None)
            o["started_hour"] = hour
        # Fixed priority at the shared dock: rover then cleaner. Charge idle assets only.
        remaining_power = min(c.dock_kw, max(0, available_pv)) if c.dock_available else 0
        for robot in ("rover", "cleaner"):
            if not getattr(c, robot + "_enabled") or self.health[robot] != "available":
                continue
            if any(o.get("robot") == robot and o["status"] == "active" for o in self.orders):
                continue
            capacity = getattr(c, robot + "_battery_kwh")
            energy_in = min(
                remaining_power, max(0, (capacity - self.energy[robot]) / c.charging_efficiency)
            )
            self.energy[robot] += energy_in * c.charging_efficiency
            remaining_power -= energy_in
            self.interval["charge_input_kwh"] += energy_in
            self.interval["charging_loss_kwh"] += energy_in * (1 - c.charging_efficiency)
        self.interval["electrolyser_isolated"] = any(
            o["status"] == "active"
            and o["phase"] == "perform"
            and o["kind"] in ("reset", "human-service")
            for o in self.orders
        )
        self.interval["decision"] = self.public()
        return self.interval["charge_input_kwh"]

    def public(self):
        return {
            "implementation_id": VERSION,
            "robots": {
                r: {"asset_id": ASSETS[r], "energy_kwh": self.energy[r], "status": self.health[r]}
                for r in self.energy
            },
            "soiling_estimate": self.soiling,
            "soiling_sensor": "ideal lumped-loss monitor",
            "service_kits": self.kits,
            "cleaning_kits": self.cleaning_kits,
            "orders": copy.deepcopy(self.orders),
        }

    def end(self, hour, faults, diagnosis):
        c, record = self.config, self.interval
        for o in list(self.orders):
            if o["status"] == "awaiting verification":
                if (
                    diagnosis.informative
                    and not diagnosis.active_incident
                    and not diagnosis.flow_isolated
                ):
                    o.update(status="verified", verified_at_hour=hour + 1)
                    self.messages.append(
                        {
                            "hour": hour,
                            "component": "services",
                            "label": f"{o['kind']}: operating recovery verified",
                        }
                    )
                continue
            if o["status"] != "active":
                continue
            kind, phase = o["kind"], o["phase"]
            if "robot" in o:
                robot = o["robot"]
                self.energy[robot] -= c.mission_power_kw
                record[robot + "_hours"] += 1
                record["robot_use_kwh"] += c.mission_power_kw
            if kind == "cleaning" and phase == "perform" and not o.get("kit_consumed"):
                self.cleaning_kits -= 1
                record["cleaning_kits_used"] += 1
                o["kit_consumed"] = True
            if kind == "human-service" and phase == "perform":
                record["human_hours"] += 1
                if not o.get("kit_consumed"):
                    self.kits -= 1
                    record["service_kits_used"] += 1
                    record["human_visits"] += 1
                    o["kit_consumed"] = True
            o["remaining"] -= 1
            if o["remaining"] > 0:
                continue
            if phase == "travel":
                duration = {
                    "cleaning": c.cleaning_hours,
                    "inspection": c.inspection_hours,
                    "human-service": c.human_work_hours,
                }[kind]
                o.update(phase="perform", remaining=duration)
            elif phase == "perform":
                if kind in ("cleaning", "inspection"):
                    failed = (
                        self._draw(f"mission:{kind}:{o['incident']}:{o['kind_sequence']}")
                        < c.mission_failure_probability
                    )
                    if failed:
                        self.health[o["robot"]] = "needs human follow-up"
                        o.update(
                            status="failed",
                            phase="stranded",
                            completed_hour=hour + 1,
                            reported="Mission incomplete; robot recovery requires a site visit",
                        )
                        if kind == "inspection":
                            self._human(hour + 1, "Inspection mission failed", o["incident"])
                        self.messages.append(
                            {
                                "hour": hour,
                                "component": "services",
                                "label": f"{kind}: mission failed; human follow-up needed",
                            }
                        )
                        continue
                if kind == "cleaning":
                    record["cleanings_completed"] += 1
                    self.soiling *= 1 - c.cleaning_removal_fraction
                    o["reported"] = "Cleaning completed; loss monitor updates next interval"
                elif kind == "inspection":
                    report = faults.inspect_panel(hour)
                    o["reported"] = report
                    if report["latched"] and c.reset_enabled:
                        self._enqueue(
                            "reset", hour + 1, "Observed latched module-trip contact", o["incident"]
                        )
                    else:
                        self._human(
                            hour + 1, "Inspection supplies no enabled reset path", o["incident"]
                        )
                else:
                    success = (
                        self._draw(f"repair:{kind}:{o['incident']}") < c.repair_success_probability
                    )
                    effect = faults.service(kind, hour, success)
                    record["retrospective_effects"].append({"order_id": o["id"], **effect})
                    record["repair_attempts"] += 1
                    record["reset_attempts"] += int(kind == "reset")
                    o["reported"] = "Work completed; operational verification pending"
                    o.update(status="awaiting verification", completed_hour=hour + 1)
                    if kind == "reset" and diagnosis.flow_isolated:
                        self._human(
                            hour + 1,
                            "An isolated flow channel needs calibration; reset cannot fix it",
                            o["incident"],
                        )
                    if kind == "reset" and faults.inspect_panel(hour)["latched"]:
                        o.update(
                            status="failed", reported="Trip contact remains latched after reset"
                        )
                        self._human(hour + 1, "Reset did not clear the trip contact", o["incident"])
                if kind in ("cleaning", "inspection"):
                    o.update(phase="verify", remaining=1)
                self.messages.append(
                    {
                        "hour": hour,
                        "component": "services",
                        "label": f"{kind}: work completed; results available H{hour + 1}",
                    }
                )
            elif phase == "verify":
                o.update(phase="return", remaining=1)
            elif phase == "return":
                o.update(status="completed", phase="docked", completed_hour=hour + 1)
        self.soiling = min(0.3, self.soiling + c.soiling_per_day / 24)
        record.update(
            energy_after_kwh=self.energy.copy(), soiling_after=self.soiling, state=self.public()
        )
        residual = (
            sum(self.energy.values())
            - sum(record["energy_before_kwh"].values())
            - record["charge_input_kwh"]
            + record["charging_loss_kwh"]
            + record["robot_use_kwh"]
        )
        record["audits"] = [
            check("field_energy_balance", "services", residual, "kWh", interval=hour)
        ]
        for r in self.energy:
            cap = getattr(c, r + "_battery_kwh")
            record["audits"].append(
                check(
                    "field_" + r + "_bounds",
                    "services",
                    max(0, -self.energy[r], self.energy[r] - cap),
                    "kWh",
                    interval=hour,
                )
            )
        require(record["audits"], record)
        return copy.deepcopy(record)


def costing(costs, rows):
    """Quantities come from executed work. Calendar/usage replaceables charged once."""
    records = [r["field_operations"] for r in rows if "field_operations" in r]
    quantities = {
        k: sum(r.get(k, 0) for r in records)
        for k in (
            "cleaner_hours",
            "rover_hours",
            "cleaning_kits_used",
            "service_kits_used",
            "calibration_kits_used",
            "human_visits",
            "human_hours",
            "charge_input_kwh",
            "robot_use_kwh",
            "portable_hours",
            "portable_kits_used",
            "water_used_l",
        )
    }
    years = len(records) / 8760
    unpriced = []
    if any("support_effects" in r for r in records):
        quantities.update(
            remote_hours=sum(r.get("remote_hours", 0) for r in records),
            crew_committed_hours=sum(r.get("crew_committed_hours", 0) for r in records),
            brushes_replaced=sum(
                e["kind"] == "replace-brush" for r in records for e in r.get("support_effects", [])
            ),
            rejected_supply_kits=sum(
                e.get("rejected", 0)
                for r in records
                for e in r.get("support_effects", [])
                if e["kind"] == "restock" and e.get("unit", "kit") == "kit"
            ),
            rejected_cleaning_water_l=sum(
                e.get("rejected", 0)
                for r in records
                for e in r.get("support_effects", [])
                if e["kind"] == "restock" and e.get("unit") == "L" and e.get("material") == "water"
            ),
        )
        for key, unit in (
            ("remote_hours", "h"),
            ("brushes_replaced", "brush"),
            ("rejected_supply_kits", "kit"),
            ("rejected_cleaning_water_l", "L"),
        ):
            if quantities[key]:
                unpriced.append(
                    dict(
                        quantity=key,
                        amount=quantities[key],
                        unit=unit,
                        reason="No separate procurement/remote rate in this cost model",
                    )
                )
    components, terms = {}, {}
    maintenance_kits = sum(
        e["amount"]
        for r in records
        for e in r.get("resource_events", [])
        if e["kind"] == "consume" and e["resource"] == "stock:maintenance"
    )
    if maintenance_kits:
        quantities["maintenance_kits"] = maintenance_kits
        unpriced.append(
            dict(
                quantity="maintenance_kits",
                amount=maintenance_kits,
                unit="kit",
                reason="Routine supplies require the complete service accounting assumptions",
            )
        )
    hardware_used = {}
    for record in records:
        for name, amount in record.get("hardware_modules_used", {}).items():
            hardware_used[name] = hardware_used.get(name, 0) + amount
    for name, amount in hardware_used.items():
        quantities["hardware_modules_" + name] = amount
        unpriced.append(
            dict(
                quantity="hardware_modules_" + name,
                amount=amount,
                unit="module",
                reason="A typed service-hardware replacement needs its own procurement and wear cost basis",
            )
        )
    referenced = [r for r in records if r.get("state", {}).get("inspection")]
    reader_count = sum(
        any(r["assets"].get(key) for r in referenced) for key in ("rover", "fixed_reader")
    )
    if reader_count:
        unpriced += [
            dict(
                quantity="prepared_contact_test_interface",
                amount=1,
                unit="interface",
                reason="Prepared port installation needs a separate scoped cost assumption",
            ),
            dict(
                quantity="internal_reader_references",
                amount=reader_count,
                unit="reader",
                reason="Reference hardware and servicing are not separately priced yet",
            ),
        ]
    for key, unit in (("portable_hours", "tool h"), ("water_used_l", "L")):
        if quantities[key]:
            unpriced.append(
                dict(
                    quantity=key,
                    amount=quantities[key],
                    unit=unit,
                    reason="Portable tool hire and cleaning-water procurement rates remain to be supplied",
                )
            )
    variable = 0
    for asset in ("cleaner", "rover", "dock", "fixed_reader", "reset"):
        owned_hours = sum(r["assets"].get(asset, False) for r in records)
        if not owned_hours:
            continue
        capital = getattr(costs, asset + "_eur")
        share = costs.field_replaceable_share if asset in ("cleaner", "rover") else 0
        ownership = capital * (1 - share) / costs.field_asset_years * owned_hours / 8760
        calendar = capital * share / costs.field_asset_years * owned_hours / 8760
        usage = quantities.get(asset + "_hours", 0) * getattr(
            costs, asset + "_wear_eur_per_hour", 0
        )
        consumables = (
            (quantities["cleaning_kits_used"] - quantities["portable_kits_used"])
            * costs.cleaning_kit_eur
            if asset == "cleaner"
            else 0
        )
        maintenance = costs.field_maintenance_eur_per_year * years if asset == "dock" else 0
        components[asset] = ownership + max(calendar, usage) + consumables + maintenance
        terms[asset] = dict(
            capital_eur=capital,
            owned_hours=owned_hours,
            ownership_eur=ownership,
            replaceable_calendar_eur=calendar,
            replaceable_usage_eur=usage,
            replaceable_charged_eur=max(calendar, usage),
            consumables_eur=consumables,
            standing_maintenance_eur=maintenance,
        )
        variable += usage + consumables
    human = (
        quantities["human_visits"] * costs.visit_eur_per_incident
        + quantities["service_kits_used"] * costs.repair_eur_per_incident
        + quantities["calibration_kits_used"] * costs.calibration_kit_eur
        + quantities["human_hours"] * costs.human_service_eur_per_hour
        + quantities["portable_kits_used"] * costs.cleaning_kit_eur
    )
    if records:
        components["human_service"] = human
        terms["human_service"] = dict(
            visits_eur=quantities["human_visits"] * costs.visit_eur_per_incident,
            parts_eur=quantities["service_kits_used"] * costs.repair_eur_per_incident,
            calibration_eur=quantities["calibration_kits_used"] * costs.calibration_kit_eur,
            labour_eur=quantities["human_hours"] * costs.human_service_eur_per_hour,
            portable_materials_eur=quantities["portable_kits_used"] * costs.cleaning_kit_eur,
        )
    return dict(
        components=components,
        quantities=quantities,
        terms=terms,
        unpriced=unpriced,
        variable_and_wear_eur=variable + human,
        total_eur=sum(components.values()),
        basis="Illustrative; electricity is physical bus demand, not purchased twice. Repair/visit charged on executed work, never on an alarm. Standing maintenance excludes recorded labour and kits.",
    )
