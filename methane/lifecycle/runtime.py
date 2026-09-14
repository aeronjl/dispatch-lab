"""Boundary-timed work and condition, independently of dispatch optimisation.

Only eligible measurement packets and completed acceptance receipts enter policy.
Private acceptance failures and replacement variates are evaluated by execution.
"""

import copy
import hashlib
import json
import math
from dataclasses import replace

from methane.lifecycle.configuration import validate


def uniform(seed, asset, sequence, channel):
    raw = json.dumps(["site-lifecycle/1", seed, asset, sequence, channel]).encode()
    return int(hashlib.sha256(raw).hexdigest()[:13], 16) / 16**13


def condition_fraction(spec, state):
    if spec["asset"] == "solar":
        return min(0.95, spec["pv_loss_per_year"] * state["calendar_hours"] / 8766)
    return (
        spec["stack_mv_per_1000h"]
        * state["operating_hours"]
        / 1_000_000
        / spec["stack_reference_voltage"]
    )


class Runtime:
    def __init__(self, options, seed):
        self.options, self.seed = validate(options), seed
        self.hour = 0
        self.packages = {
            p["id"]: dict(
                status="waiting",
                phase="mobilisation",
                remaining=p["mobilisation_hours"],
                accepted_at=None,
                attempts=0,
            )
            for p in self.options["packages"]
        }
        self.conditions = {
            c["asset"]: dict(
                calendar_hours=c["initial_calendar_hours"],
                operating_hours=c["initial_operating_hours"],
                epoch=0,
                estimate=None,
                measurement=None,
                packets=[],
                stock=c["opening_spares"],
                supplier=c["supplier_spares"],
                deliveries=[],
                replacements=0,
                next_due=c["periodic_hours"],
            )
            for c in self.options["conditions"]
        }
        self.jobs, self.events = [], []
        self.active, self.crew_period, self.crew_remaining = None, -1, 0
        self.current = None
        self.accounts = dict(
            hours=0,
            electrolyser_hours=0,
            electrolyser_starts=0,
            construction_eur=0.0,
            construction_eur_hours=0.0,
            maintenance_eur=0.0,
            consumed_parts={},
        )

    def spec(self, asset):
        return next(c for c in self.options["conditions"] if c["asset"] == asset)

    def available(self):
        result = dict.fromkeys(("solar", "battery", "electrolyser", "reactor"), 1.0)
        for p in self.options["packages"]:
            if self.packages[p["id"]]["accepted_at"] is None:
                result[p["asset"]] -= p["fraction"]
        if self.active and self.active.startswith("replacement:"):
            job = self.job(self.active)
            if job["status"] == "working":
                result[job["asset"]] = 0
        return {k: max(0, v) for k, v in result.items()}

    def job(self, key):
        return next(j for j in self.jobs if j["id"] == key)

    def resources(self, hour):
        values = dict.fromkeys(
            ("access", "project-crew", "communications", "dock", "reference"), True
        )
        for event in self.options["outages"]:
            if event["start_hour"] <= hour < event["end_hour"]:
                values[event["resource"]] = False
        return values

    def _measure(self, hour, resources):
        for asset, state in self.conditions.items():
            spec = self.spec(asset)
            if hour % spec["sensor_period_hours"] == 0 and not spec["sensor_dropout"]:
                noise = (2 * uniform(self.seed, asset, hour, "condition") - 1) * spec[
                    "sensor_noise_fraction"
                ]
                state["packets"].append(
                    dict(
                        measured_at=hour,
                        available_at=hour + spec["sensor_delay_hours"],
                        value=max(0, condition_fraction(spec, state) + noise),
                        unit="fraction",
                        epoch=state["epoch"],
                        source="declared-condition-channel/1",
                        noise_bound=spec["sensor_noise_fraction"],
                    )
                )
            eligible = [
                p
                for p in state["packets"]
                if p["available_at"] <= hour and p["epoch"] == state["epoch"]
            ]
            eligible.sort(key=lambda p: p["measured_at"])
            if eligible and resources["communications"]:
                state["measurement"] = copy.deepcopy(eligible[-1])
                state["estimate"] = eligible[-1]["value"]
            for job in self.jobs:
                if job["asset"] != asset or job["status"] != "awaiting-verification":
                    continue
                measurement = state["measurement"]
                if measurement and measurement["measured_at"] >= job["completed_at"]:
                    job["status"] = (
                        "verified"
                        if measurement["value"] <= spec["replacement_threshold"]
                        else "failed-verification"
                    )
                    job["verified_at"] = hour
                    job["verification"] = copy.deepcopy(measurement)
                    self.events.append(
                        dict(kind=job["status"], asset=asset, hour=hour, job_id=job["id"])
                    )
                elif hour >= job["verification_due"]:
                    job["status"] = "verification-expired"
                    self.events.append(
                        dict(kind="verification-expired", asset=asset, hour=hour, job_id=job["id"])
                    )
            # Retain the latest eligible reading and not-yet-available packets only.
            state["packets"] = [p for p in state["packets"] if p["available_at"] > hour] + eligible[
                -1:
            ]

    def _deliver(self, hour, resources):
        events = []
        for asset, state in self.conditions.items():
            spec = self.spec(asset)
            for delivery in state["deliveries"]:
                if (
                    delivery["status"] == "in-transit"
                    and hour >= delivery["due"]
                    and resources["access"]
                ):
                    accepted = min(delivery["quantity"], spec["stock_capacity"] - state["stock"])
                    state["stock"] += accepted
                    delivery.update(
                        status="delivered",
                        delivered_at=hour,
                        accepted=accepted,
                        rejected=delivery["quantity"] - accepted,
                    )
                    events.append(
                        dict(kind="delivery", asset=asset, hour=hour, **copy.deepcopy(delivery))
                    )
        return events

    def _request(self, hour):
        if self.options["maintenance_policy"] == "none":
            return
        for asset, state in self.conditions.items():
            spec = self.spec(asset)
            pending = [
                j
                for j in self.jobs
                if j["asset"] == asset
                and j["status"] in ("waiting", "working", "awaiting-verification")
            ]
            failures = [
                j
                for j in self.jobs
                if j["asset"] == asset
                and j["status"] in ("failed-verification", "verification-expired", "work-expired")
            ]
            # Two unsuccessful remedies without an intervening success require review.
            recent = [j for j in self.jobs if j["asset"] == asset][-2:]
            if pending or len(recent) == 2 and all(j in failures for j in recent):
                continue
            periodic = self.options["maintenance_policy"] == "periodic"
            due = (
                hour >= state["next_due"]
                if periodic
                else state["estimate"] is not None
                and state["estimate"] >= spec["replacement_threshold"]
            )
            if not due or self.available()[asset] <= 0:
                continue
            key = f"replacement:{asset}:{len(self.jobs) + 1}"
            self.jobs.append(
                dict(
                    id=key,
                    asset=asset,
                    created_at=hour,
                    due_hour=hour + self.options["maximum_wait_hours"],
                    status="waiting",
                    remaining=spec["replacement_hours"],
                    observation=copy.deepcopy(state["measurement"]),
                    reason="Declared calendar service"
                    if periodic
                    else "Eligible measured condition exceeds threshold",
                )
            )

    def _select(self, hour, forecast, resources):
        if self.active:
            return self.active
        for p in self.options["packages"]:
            state = self.packages[p["id"]]
            if (
                state["status"] == "waiting"
                and p["earliest_hour"] <= hour
                and all(self.packages[d]["accepted_at"] is not None for d in p["depends_on"])
            ):
                self.active = p["id"]
                return self.active
        for job in self.jobs:
            if job["status"] != "waiting":
                continue
            state = self.conditions[job["asset"]]
            if state["stock"] < 1:
                continue
            if self.options["maintenance_policy"] == "forecast-window" and hour < job["due_hour"]:
                pv = forecast["pv_kw"]
                duration = max(1, math.ceil(job["remaining"]))
                permitted = [
                    i
                    for i in range(max(0, len(pv) - duration + 1))
                    if hour + i <= job["due_hour"]
                    and all(self.on_shift(hour + j) for j in range(i, i + duration))
                ]
                best = (
                    min(permitted, key=lambda i: (sum(pv[i : i + duration]), i)) if permitted else 0
                )
                job["planned_start"] = hour + best
                job["forecast_source"] = copy.deepcopy(forecast.get("source"))
                if best:
                    continue
            if not resources["reference"]:
                continue
            self.active = job["id"]
            return self.active
        return None

    def on_shift(self, hour):
        return (
            self.options["crew_shift_start"]
            <= hour % 24
            < self.options["crew_shift_start"] + self.options["crew_hours_per_day"]
        )

    def begin(self, hour, forecast):
        if hour != self.hour or self.current is not None:
            raise ValueError("Lifecycle decisions require the preceding committed boundary")
        event_start = len(self.events)
        resources = self.resources(hour)
        self._measure(hour, resources)
        arrivals = self._deliver(hour, resources)
        self.events.extend(arrivals)
        for job in self.jobs:
            if job["status"] == "waiting" and hour > job["due_hour"]:
                job.update(status="work-expired", expired_at=hour)
                self.events.append(
                    dict(kind="work-expired", asset=job["asset"], hour=hour, job_id=job["id"])
                )
                if self.active == job["id"]:
                    self.active = None
        self._request(hour)
        if hour // 24 != self.crew_period:
            self.crew_period, self.crew_remaining = hour // 24, self.options["crew_hours_per_day"]
        selected = self._select(hour, forecast, resources)
        crew = 0
        work = None
        reason = "No eligible work"
        if selected:
            work = (
                self.job(selected)
                if selected.startswith("replacement:")
                else self.packages[selected]
            )
            possible = (
                resources["access"]
                and resources["project-crew"]
                and resources["communications"]
                and self.on_shift(hour)
            )
            if possible:
                crew = min(1.0, self.crew_remaining, work["remaining"])
            reason = (
                "Work allocated" if crew else "Waiting for access, communications or project crew"
            )
            if crew and selected.startswith("replacement:") and work["status"] == "waiting":
                state = self.conditions[work["asset"]]
                if state["stock"] < 1:
                    raise ValueError("Replacement cannot consume unavailable stock")
                state["stock"] -= 1
                work.update(status="working", started_at=hour)
            elif crew and not selected.startswith("replacement:"):
                work["status"] = "working"
        purchase = []
        if self.options["replenishment"]:
            for asset, state in self.conditions.items():
                if (
                    state["stock"] < 1
                    and state["supplier"]
                    and not any(d["status"] == "in-transit" for d in state["deliveries"])
                ):
                    spec = self.spec(asset)
                    if spec["stock_capacity"]:
                        state["supplier"] -= 1
                        delivery = dict(
                            ordered_at=hour,
                            due=hour + spec["delivery_hours"],
                            quantity=1,
                            status="in-transit",
                        )
                        state["deliveries"].append(delivery)
                        purchase.append(
                            dict(asset=asset, eur=spec["replacement_part_eur"], **delivery)
                        )
        self.current = dict(
            hour=hour,
            selected=selected,
            crew_hours=crew,
            phase=work.get("phase", "replacement") if work else None,
            resources=resources,
            reason=reason,
            arrivals=arrivals,
            purchases=purchase,
            event_start=event_start,
            availability=self.available(),
            observations={a: copy.deepcopy(s["measurement"]) for a, s in self.conditions.items()},
            estimates={a: s["estimate"] for a, s in self.conditions.items()},
            before=copy.deepcopy(self.conditions),
        )
        return self.public()

    def public(self):
        return dict(
            version="site-lifecycle/1",
            hour=self.hour,
            availability=self.available(),
            packages={
                k: {n: v for n, v in s.items() if n != "attempts"} for k, s in self.packages.items()
            },
            jobs=copy.deepcopy(self.jobs),
            condition={
                a: dict(
                    estimate=s["estimate"],
                    measurement=copy.deepcopy(s["measurement"]),
                    stock=s["stock"],
                    supplier=s["supplier"],
                    deliveries=copy.deepcopy(s["deliveries"]),
                )
                for a, s in self.conditions.items()
            },
            current={
                k: copy.deepcopy(v)
                for k, v in (self.current or {}).items()
                if k not in ("before", "event_start")
            },
            labour_basis=self.options["labour_basis"],
        )

    def plant(self, nominal, physical=False):
        state = self.conditions.get("electrolyser")
        if not state:
            return nominal
        fraction = (
            condition_fraction(self.spec("electrolyser"), state)
            if physical
            else state["estimate"] or 0
        )
        return replace(
            nominal, specific_energy_kwh_per_kg=nominal.specific_energy_kwh_per_kg * (1 + fraction)
        )

    def solar_factor(self, physical=False):
        state = self.conditions.get("solar")
        loss = (
            condition_fraction(self.spec("solar"), state)
            if physical and state
            else (state["estimate"] or 0)
            if state
            else 0
        )
        return self.available()["solar"] * max(0, 1 - loss)

    def finish(self, row):
        if self.current is None:
            raise ValueError("No lifecycle decision to execute")
        c, now = self.current, self.hour
        crew, selected = c["crew_hours"], c["selected"]
        self.crew_remaining -= crew
        cash = dict(
            crew_eur=crew * self.options["crew_eur_per_hour"],
            callout_eur=0.0,
            equipment_eur=0.0,
            materials_eur=sum(p["eur"] for p in c["purchases"]),
            external_energy_kwh=0.0,
            external_energy_eur=0.0,
            opening_stock_eur=sum(
                c["opening_spares"] * c["replacement_part_eur"] for c in self.options["conditions"]
            )
            if now == 0
            else 0.0,
        )
        physical_outcomes = []
        if selected and crew:
            if selected.startswith("replacement:"):
                job = self.job(selected)
                if job["started_at"] == now:
                    cash["callout_eur"] = self.options["callout_eur"]
                job["remaining"] -= crew
                if job["remaining"] <= 1e-12:
                    spec, state = self.spec(job["asset"]), self.conditions[job["asset"]]
                    success = (
                        uniform(self.seed, job["asset"], state["replacements"], "replacement")
                        < spec["replacement_success_fraction"]
                    )
                    physical_outcomes.append(
                        dict(
                            asset=job["asset"],
                            job_id=selected,
                            success=success,
                            scope="Simulator truth; not a confirmation",
                        )
                    )
                    if success:
                        state["calendar_hours"] = state["operating_hours"] = 0
                    state.update(
                        epoch=state["epoch"] + 1,
                        measurement=None,
                        replacements=state["replacements"] + 1,
                        next_due=now + 1 + spec["periodic_hours"],
                    )
                    job.update(
                        status="awaiting-verification",
                        completed_at=now + 1,
                        verification_due=now + 1 + self.options["maximum_wait_hours"],
                    )
                    self.events.append(
                        dict(
                            kind="replacement-completed",
                            asset=job["asset"],
                            hour=now + 1,
                            job_id=selected,
                            scope="Procedure completion, not observed restoration",
                        )
                    )
                    self.active = None
            else:
                spec = next(p for p in self.options["packages"] if p["id"] == selected)
                work = self.packages[selected]
                cash["equipment_eur"] = crew * spec["equipment_eur_per_hour"]
                cash["external_energy_kwh"] = crew * spec["equipment_energy_kwh_per_hour"]
                cash["external_energy_eur"] = (
                    cash["external_energy_kwh"] * spec["external_energy_eur_per_kwh"]
                )
                if (
                    work["phase"] == "mobilisation"
                    and work["remaining"] == spec["mobilisation_hours"]
                ):
                    cash["materials_eur"] += spec["installation_material_eur"]
                    cash["callout_eur"] = self.options["callout_eur"]
                work["remaining"] -= crew
                if work["remaining"] <= 1e-12:
                    phase = work["phase"]
                    next_phase = {
                        "mobilisation": "installation",
                        "installation": "acceptance",
                        "rework": "acceptance",
                        "acceptance": "departure",
                        "departure": None,
                    }[phase]
                    if phase == "acceptance":
                        work["attempts"] += 1
                        if work["attempts"] <= spec["failed_acceptance_attempts"]:
                            next_phase = (
                                "rework" if work["attempts"] < spec["maximum_attempts"] else None
                            )
                            if next_phase is None:
                                work["status"] = "acceptance-failed"
                        else:
                            work["accepted_at"] = now + 1
                        self.events.append(
                            dict(
                                kind="accepted" if work["accepted_at"] else "acceptance-failed",
                                asset=spec["asset"],
                                package=selected,
                                hour=now + 1,
                                fraction=spec["fraction"],
                            )
                        )
                    if next_phase:
                        work.update(phase=next_phase, remaining=spec[next_phase + "_hours"])
                    else:
                        if work["accepted_at"] is not None:
                            work.update(status="departed", departed_at=now + 1)
                        self.active = None
        for asset, state in self.conditions.items():
            # Calendar exposure is independent of electrical operation, including isolation.
            state["calendar_hours"] += 1
            if asset == "electrolyser":
                state["operating_hours"] += (
                    int(row["applied"]["electrolyser_kw"] > 0)
                    + row["electrolyser_start"] * self.spec(asset)["start_equivalent_hours"]
                )
        self.hour += 1
        self.current = None
        record = dict(
            version="site-lifecycle/1",
            retrospective_work=physical_outcomes,
            consumption={
                "asset": self.job(selected)["asset"],
                "parts": 1,
                "part_value_eur": self.spec(self.job(selected)["asset"])["replacement_part_eur"],
            }
            if selected
            and selected.startswith("replacement:")
            and crew
            and self.job(selected)["started_at"] == now
            else None,
            accounting={
                "work_kind": "replacement"
                if selected and selected.startswith("replacement:")
                else "construction"
                if selected
                else None,
                "construction_fractions": {
                    a: sum(p["fraction"] for p in self.options["packages"] if p["asset"] == a)
                    for a in ("solar", "battery", "electrolyser", "reactor")
                },
                "condition_assets": [s["asset"] for s in self.options["conditions"]],
            },
            decision={
                k: copy.deepcopy(v) for k, v in c.items() if k not in ("before", "event_start")
            },
            after=self.public(),
            expenditure=cash,
            events=copy.deepcopy(self.events[c["event_start"] :]),
            retrospective_condition={
                a: dict(
                    before=condition_fraction(self.spec(a), c["before"][a]),
                    after=condition_fraction(self.spec(a), s),
                    calendar_hours=s["calendar_hours"],
                    operating_hours=s["operating_hours"],
                    replacements=s["replacements"],
                )
                for a, s in self.conditions.items()
            },
        )
        record["accounting"]["before"] = copy.deepcopy(self.accounts)
        self.accounts["hours"] += 1
        self.accounts["electrolyser_hours"] += int(row["applied"]["electrolyser_kw"] > 0)
        self.accounts["electrolyser_starts"] += row["electrolyser_start"]
        self.accounts["construction_eur_hours"] += self.accounts["construction_eur"]
        direct = sum(
            cash[k] for k in ("crew_eur", "callout_eur", "equipment_eur", "external_energy_eur")
        )
        if record["accounting"]["work_kind"] == "construction":
            self.accounts["construction_eur"] += (
                direct + cash["materials_eur"] - sum(p["eur"] for p in c["purchases"])
            )
        else:
            self.accounts["maintenance_eur"] += direct
        consumed = record["consumption"]
        if consumed:
            asset = consumed["asset"]
            self.accounts["consumed_parts"][asset] = (
                self.accounts["consumed_parts"].get(asset, 0) + consumed["part_value_eur"]
            )
        record["accounting"]["after"] = copy.deepcopy(self.accounts)
        return record
