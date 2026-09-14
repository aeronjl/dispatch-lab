"""Portable independent lifecycle accounting: standard library, no execution imports.

Decimal counters and explicit work-state transitions check recorded execution.
This verifies reduced mechanisms and information timing, not field capability.
"""

import hashlib
import json
from decimal import Decimal


def d(value):
    return Decimal(str(value))


def random_value(seed, asset, sequence, channel):
    payload = json.dumps(["site-lifecycle/1", seed, asset, sequence, channel]).encode()
    return d(int(hashlib.sha256(payload).hexdigest()[:13], 16)) / d(16**13)


class Reference:
    def __init__(self, config):
        self.c, self.p = config["lifecycle"], config["plant"]
        self.seed = config["scenario"]["seed"]
        self.age = {
            s["asset"]: [d(s["initial_calendar_hours"]), d(s["initial_operating_hours"]), 0]
            for s in self.c["conditions"]
        }
        self.stock = {s["asset"]: s["opening_spares"] for s in self.c["conditions"]}
        self.packages = {
            s["id"]: dict(
                phase="mobilisation", left=d(s["mobilisation_hours"]), accepted=None, attempts=0
            )
            for s in self.c["packages"]
        }
        self.period, self.crew = -1, d(0)
        self.started = set()
        self.jobs = {}
        self.readings, self.measurements = {}, {}
        self.estimates = {s["asset"]: None for s in self.c["conditions"]}
        self.accounts = dict(
            hours=0,
            electrolyser_hours=0,
            electrolyser_starts=0,
            construction_eur=d(0),
            construction_eur_hours=d(0),
            maintenance_eur=d(0),
            consumed_parts={},
        )

    def condition(self, spec):
        calendar, usage, _ = self.age[spec["asset"]]
        if spec["asset"] == "solar":
            return min(d(".95"), d(spec["pv_loss_per_year"]) * calendar / d(8766))
        return (
            d(spec["stack_mv_per_1000h"]) * usage / d(1000000) / d(spec["stack_reference_voltage"])
        )

    def interval(self, row, truth, controller=None):
        checks = []
        h = row["hour"]

        def check(key, actual, expected=True):
            numeric = not isinstance(actual, (bool, dict, list, str, type(None)))
            passed = abs(d(actual) - d(expected)) <= d(".000001") if numeric else actual == expected
            checks.append(
                dict(
                    id="lifecycle." + key,
                    passed=passed,
                    controller=controller,
                    hour=h,
                    method="Independent Decimal counters, work/observation boundaries and cash operands",
                    actual=actual,
                    expected=float(expected) if isinstance(expected, Decimal) else expected,
                )
            )

        r = row["lifecycle"]
        view, after = r["decision"], r["after"]
        check(
            "accounting.condition_assets",
            r["accounting"]["condition_assets"],
            [s["asset"] for s in self.c["conditions"]],
        )
        check(
            "accounting.construction_fractions",
            r["accounting"]["construction_fractions"],
            {
                a: sum(s["fraction"] for s in self.c["packages"] if s["asset"] == a)
                for a in ("solar", "battery", "electrolyser", "reactor")
            },
        )
        check(
            "accounting.work_kind",
            r["accounting"]["work_kind"],
            "replacement"
            if view["selected"] and view["selected"].startswith("replacement:")
            else "construction"
            if view["selected"]
            else None,
        )
        check("boundary", after["hour"], h + 1)
        check("completed_boundary_has_no_pending_decision", after["current"], {})
        check("controller_copy", row["decision"]["lifecycle"]["current"], view)
        states = dict.fromkeys(
            ("access", "project-crew", "communications", "dock", "reference"), True
        )
        for outage in self.c["outages"]:
            if outage["start_hour"] <= h < outage["end_hour"]:
                states[outage["resource"]] = False
        check("current_support", view["resources"], states)
        if h // 24 != self.period:
            self.period, self.crew = h // 24, d(self.c["crew_hours_per_day"])
        work = view["selected"]
        is_replacement = bool(work and work.startswith("replacement:"))
        package = next((s for s in self.c["packages"] if s["id"] == work), None)
        public_jobs = {j["id"]: j for j in row["decision"]["lifecycle"]["jobs"]}
        consumed = None
        crew = d(view["crew_hours"])
        permitted = (
            all(states[k] for k in ("access", "project-crew", "communications"))
            and self.c["crew_shift_start"]
            <= h % 24
            < self.c["crew_shift_start"] + self.c["crew_hours_per_day"]
        )
        check("crew_permission", not crew or permitted)
        check("crew_limit", d(0) <= crew <= min(d(1), self.crew))
        self.crew -= crew
        cash = dict(
            crew_eur=crew * d(self.c["crew_eur_per_hour"]),
            callout_eur=d(0),
            materials_eur=d(0),
            equipment_eur=d(0),
            external_energy_kwh=d(0),
            external_energy_eur=d(0),
            opening_stock_eur=sum(
                d(s["opening_spares"]) * d(s["replacement_part_eur"]) for s in self.c["conditions"]
            )
            if h == 0
            else d(0),
        )
        for receipt in view["arrivals"]:
            spec = next(s for s in self.c["conditions"] if s["asset"] == receipt["asset"])
            check("arrival_clock", h >= receipt["due"] and states["access"])
            accepted = min(receipt["quantity"], spec["stock_capacity"] - self.stock[spec["asset"]])
            check("accepted_stock", receipt["accepted"], accepted)
            check("rejected_stock", receipt["rejected"], receipt["quantity"] - accepted)
            self.stock[spec["asset"]] += accepted
        for purchase in view["purchases"]:
            spec = next(s for s in self.c["conditions"] if s["asset"] == purchase["asset"])
            check("order_clock", purchase["due"], h + spec["delivery_hours"])
            check("purchase_price", purchase["eur"], spec["replacement_part_eur"])
            cash["materials_eur"] += d(spec["replacement_part_eur"])
        availability = dict.fromkeys(("solar", "battery", "electrolyser", "reactor"), d(1))
        for spec in self.c["packages"]:
            if self.packages[spec["id"]]["accepted"] is None:
                availability[spec["asset"]] -= d(spec["fraction"])
        if is_replacement:
            job = public_jobs[work]
            spec = next(s for s in self.c["conditions"] if s["asset"] == job["asset"])
            if job["status"] == "working":
                availability[job["asset"]] = d(0)
            if crew:
                check("reference_at_start", work in self.started or states["reference"])
                if work not in self.started:
                    check("spare_at_start", self.stock[job["asset"]] >= 1)
                    self.stock[job["asset"]] -= 1
                    consumed = dict(
                        asset=job["asset"], parts=1, part_value_eur=spec["replacement_part_eur"]
                    )
                    self.started.add(work)
                    self.jobs[work] = d(spec["replacement_hours"])
                    cash["callout_eur"] = d(self.c["callout_eur"])
                    if self.c["maintenance_policy"] != "periodic":
                        packet = job["observation"]
                        check(
                            "work_observation",
                            packet is not None
                            and packet["available_at"] <= job["created_at"]
                            and packet["value"] >= spec["replacement_threshold"],
                        )
                self.jobs[work] -= crew
                check("replacement_work_budget", self.jobs[work] >= 0)
        if crew:
            target = public_jobs[work]["asset"] if is_replacement else package["asset"]
            check("exclusive_target", target not in view.get("occupied_assets", []))
        if package and crew:
            state = self.packages[work]
            check(
                "dependency",
                h >= package["earliest_hour"]
                and all(self.packages[k]["accepted"] is not None for k in package["depends_on"]),
            )
            check("phase", view["phase"], state["phase"])
            check("work_limit", crew <= state["left"])
            cash["equipment_eur"] = crew * d(package["equipment_eur_per_hour"])
            cash["external_energy_kwh"] = crew * d(package["equipment_energy_kwh_per_hour"])
            cash["external_energy_eur"] = cash["external_energy_kwh"] * d(
                package["external_energy_eur_per_kwh"]
            )
            if work not in self.started:
                self.started.add(work)
                cash["callout_eur"] = d(self.c["callout_eur"])
                cash["materials_eur"] += d(package["installation_material_eur"])
            state["left"] -= crew
            if state["left"] <= 0:
                phase = state["phase"]
                following = {
                    "mobilisation": "installation",
                    "installation": "acceptance",
                    "rework": "acceptance",
                    "acceptance": "departure",
                    "departure": None,
                }[phase]
                if phase == "acceptance":
                    state["attempts"] += 1
                    if state["attempts"] <= package["failed_acceptance_attempts"]:
                        following = (
                            "rework" if state["attempts"] < package["maximum_attempts"] else None
                        )
                    else:
                        state["accepted"] = h + 1
                if following:
                    state.update(phase=following, left=d(package[following + "_hours"]))
                elif state["accepted"] is not None:
                    check("departure", after["packages"][work]["departed_at"], h + 1)
        for key, expected in availability.items():
            check("availability." + key, view["availability"][key], max(d(0), expected))
        for spec in self.c["packages"]:
            check(
                "acceptance." + spec["id"],
                after["packages"][spec["id"]]["accepted_at"],
                self.packages[spec["id"]]["accepted"],
            )
        check("cash_fields", set(r["expenditure"]) == set(cash))
        for key, expected in cash.items():
            check("cash." + key, r["expenditure"][key], expected)
        check("consumption", r["consumption"], consumed)
        for boundary in ("before", "after"):
            if boundary == "after":
                self.accounts["hours"] += 1
                self.accounts["electrolyser_hours"] += int(row["applied"]["electrolyser_kw"] > 0)
                self.accounts["electrolyser_starts"] += row["electrolyser_start"]
                self.accounts["construction_eur_hours"] += self.accounts["construction_eur"]
                direct = sum(
                    cash[k]
                    for k in ("crew_eur", "callout_eur", "equipment_eur", "external_energy_eur")
                )
                if package:
                    self.accounts["construction_eur"] += (
                        direct + cash["materials_eur"] - sum(d(p["eur"]) for p in view["purchases"])
                    )
                else:
                    self.accounts["maintenance_eur"] += direct
                if consumed:
                    a = consumed["asset"]
                    self.accounts["consumed_parts"][a] = self.accounts["consumed_parts"].get(
                        a, d(0)
                    ) + d(consumed["part_value_eur"])
            for key, expected in self.accounts.items():
                if key == "consumed_parts":
                    check(
                        "account_parts_keys." + boundary,
                        set(r["accounting"][boundary][key]) == set(expected),
                    )
                    for asset, amount in expected.items():
                        check(
                            "account_parts." + boundary + asset,
                            r["accounting"][boundary][key][asset],
                            amount,
                        )
                else:
                    check("account." + boundary + key, r["accounting"][boundary][key], expected)
        physical = dict(self.p)
        for spec in self.c["conditions"]:
            asset = spec["asset"]
            before = self.condition(spec)
            check(
                "condition.before." + asset, truth["lifecycle_condition"][asset]["before"], before
            )
            if asset == "electrolyser":
                physical["specific_energy_kwh_per_kg"] = float(
                    d(self.p["specific_energy_kwh_per_kg"]) * (1 + before)
                )
            epoch = self.age[asset][2]
            if h % spec["sensor_period_hours"] == 0 and not spec["sensor_dropout"]:
                noise = (2 * random_value(self.seed, asset, h, "condition") - 1) * d(
                    spec["sensor_noise_fraction"]
                )
                self.readings[asset, h, epoch] = float(max(d(0), before + noise))
            eligible = [
                k
                for k in self.readings
                if k[0] == asset and k[2] == epoch and k[1] + spec["sensor_delay_hours"] <= h
            ]
            if eligible and states["communications"]:
                self.measurements[asset] = max(eligible, key=lambda k: k[1])
                self.estimates[asset] = self.readings[self.measurements[asset]]
            packet = view["observations"][asset]
            expected_packet = self.measurements.get(asset)
            check("observation_presence." + asset, packet is not None, expected_packet is not None)
            if packet and expected_packet:
                check("observation_value." + asset, packet["value"], self.readings[expected_packet])
                check("observation_latest." + asset, packet["measured_at"], expected_packet[1])
            if packet:
                check(
                    "observation.clock." + asset,
                    packet["available_at"] <= h
                    and packet["available_at"]
                    == packet["measured_at"] + spec["sensor_delay_hours"],
                )
            estimate = view["estimates"][asset]
            check("estimate.observation_binding." + asset, estimate, self.estimates[asset])
            if asset == "electrolyser":
                check(
                    "controller_energy_estimate",
                    row["decision"]["operating_plant"]["specific_energy_kwh_per_kg"],
                    d(self.p["specific_energy_kwh_per_kg"]) * (1 + d(estimate or 0)),
                )
            for outcome in truth.get("lifecycle_work", []):
                if outcome["asset"] == asset:
                    check("completion_work", self.jobs[outcome["job_id"]], 0)
                    success = random_value(self.seed, asset, self.age[asset][2], "replacement") < d(
                        spec["replacement_success_fraction"]
                    )
                    check("physical_outcome", outcome["success"], success)
                    if success:
                        self.age[asset][:2] = [d(0), d(0)]
                    self.age[asset][2] += 1
                    self.measurements.pop(asset, None)
            self.age[asset][0] += 1
            if asset == "electrolyser":
                self.age[asset][1] += int(row["applied"]["electrolyser_kw"] > 0) + d(
                    row["electrolyser_start"]
                ) * d(spec["start_equivalent_hours"])
            check(
                "condition.after." + asset,
                truth["lifecycle_condition"][asset]["after"],
                self.condition(spec),
            )
            check(
                "calendar." + asset,
                truth["lifecycle_condition"][asset]["calendar_hours"],
                self.age[asset][0],
            )
            check(
                "usage." + asset,
                truth["lifecycle_condition"][asset]["operating_hours"],
                self.age[asset][1],
            )
            check("stock." + asset, after["condition"][asset]["stock"], self.stock[asset])
        for key in self.p:
            check("physical_parameter." + key, r["physical_plant"][key], physical[key])
        for asset, keys in {
            "battery": ("charge_kw", "discharge_kw"),
            "electrolyser": ("electrolyser_kw",),
            "reactor": ("heater_kw", "methane_kg"),
        }.items():
            limits = dict(
                charge_kw=self.p["battery_kwh"] * self.p["battery_c_rate"],
                discharge_kw=self.p["battery_kwh"] * self.p["battery_c_rate"],
                electrolyser_kw=self.p["electrolyser_kw"],
                heater_kw=self.p["heater_max_kw"],
                methane_kg=self.p["methane_max_kgph"],
            )
            for key in keys:
                check(
                    "applied_capacity." + key,
                    d(row["applied"][key]) <= d(limits[key]) * availability[asset] + d(".000001"),
                )
        return checks


def audit_run(result):
    checks = []
    for name, rows in result["records"].items():
        ref = Reference(result["config"])
        for row, truth in zip(rows, result["retrospective_truth_by_controller"][name], strict=True):
            checks.extend(ref.interval(row, truth, name))
    return checks
