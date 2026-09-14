"""Isolated teaching adapters for the implemented field service system.

No selected run enters these functions. Measurements and process plans use the
production interfaces; retrospective fixture choices never enter an observer.
"""

import copy
from dataclasses import asdict, replace
from datetime import timedelta

from methane.config import Costs, Plant
from methane.learning import metric, result, series


def cleaning(v):
    from methane.services.surface import Patch, treat

    before = (Patch(0, 100, v["loose"], 0.08, 0.03),)
    extent = 100 * v["coverage"]
    after = (
        treat(before, 0, extent, v["efficacy"], v["efficacy"], 0.75 if v["method"] == "wet" else 0)
        if extent
        else before
    )
    transmission = sum(p.area * p.transmission for p in after) / 100
    expected = (1 - v["coverage"]) * before[0].transmission + v["coverage"] * (
        1 - v["loose"] * (1 - v["efficacy"])
    ) * (1 - 0.08 * (0.25 if v["method"] == "wet" else 1)) * 0.97
    return result(
        [
            metric("Transmission before", before[0].transmission),
            metric("Transmission after", transmission),
            metric("Treated area", extent, "m²"),
        ],
        [series("Transmission", [before[0].transmission, transmission])],
        [
            dict(stage="before", patches=[asdict(p) for p in before]),
            dict(stage="after", patches=[asdict(p) for p in after]),
        ],
        [dict(id="independent-area-balance", passed=abs(transmission - expected) < 1e-10)],
        patches=[asdict(p) for p in after],
        scope="Optical mechanism only. Wet water/operator consumption belongs to full mission execution; this fixture does not infer service energy or methane benefit.",
    )


def inspection(v):
    from methane.services.configuration import ServiceSystem
    from methane.services.inspection import SCOPE, sample

    options = replace(
        ServiceSystem(), inspection_noise_v=v["noise"], inspection_delay_hours=v["delay"]
    )
    # Only the sampling layer sees physical fixture inputs. Classification consumes raw voltage.
    _, trace = sample(
        dict(signal_v=v["signal"], offset_v=v["offset"], dropout=v["dropout"] == "yes"),
        "fixed",
        0,
        "learning-inspection",
        7,
        options,
    )
    eligible = trace["available_at"] <= v["clock"]
    measurement = (
        trace["interpretation"] if eligible else dict(quality="not yet available", value=None)
    )
    return result(
        [
            metric("Observation quality", measurement["quality"]),
            metric("Contact state", measurement["value"]),
            metric("Available boundary", trace["available_at"], "h"),
        ],
        [
            series(
                "Measured channels", list(trace["raw_v"].values()) if eligible else [None] * 3, "V"
            )
        ],
        [dict(decision_hour=v["clock"], eligible=eligible, observation=measurement)],
        [
            dict(
                id="availability-boundary", passed=eligible == (trace["available_at"] <= v["clock"])
            )
        ],
        observation=measurement,
        raw_measurement=trace["raw_v"] if eligible else None,
        retrospective_fixture=dict(
            **trace, scope="Retrospective teaching sensor inputs; not the controller observation"
        ),
        scope=SCOPE,
    )


def logistics(v):
    from methane.services.contracts import Quantity
    from methane.services.resources import Booking, Ledger, Resource, ResourceConflict

    ledger = Ledger(
        [Resource("kits", "kit", "stock", 5, v["stock"]), Resource("crew", "person", "capacity", 1)]
    )
    deliveries = []
    steps = []
    for hour in range(8):
        if hour == v["arrival"]:
            ledger.replenish(Quantity("kits", v["delivery"], "kit"), hour, "learning-delivery")
            deliveries.append(copy.deepcopy(ledger.events[-1]))
        if hour in (1, 3):
            key = f"job-{hour}"
            try:
                ledger.reserve(
                    key,
                    [Quantity("kits", 1, "kit")],
                    [Booking("crew", hour, hour + v["duration"], 1, "person")],
                    hour,
                )
                ledger.consume(key, Quantity("kits", 1, "kit"), hour, "perform")
                outcome = "reserved and kit consumed"
            except ResourceConflict as exc:
                outcome = str(exc)
            steps.append(
                dict(
                    hour=hour,
                    outcome=outcome,
                    stock=ledger.stock["kits"],
                    reservations=copy.deepcopy(ledger.bookings),
                )
            )
    steps = [{**s, "reservations": [asdict(b) for b in s["reservations"]]} for s in steps]
    checks = ledger.reconcile()
    return result(
        [
            metric("Ending kits", ledger.stock["kits"], "kit"),
            metric("Rejected delivery", sum(d["rejected"] for d in deliveries), "kit"),
            metric("Tasks supplied", sum(e["kind"] == "consume" for e in ledger.events)),
        ],
        [series("Stock at task requests", [v["stock"]] + [s["stock"] for s in steps], "kit")],
        steps,
        checks,
        ledger=ledger.events,
        scope="Two fixed task appointments at H1 and H3. Travel/lead time is represented by editable delivery time; tasks blocked by crew or stock are not silently rescheduled. Reservations and actual consumption are separate.",
    )


def service_costs(v):
    from methane.service_economics import ACTIVITY_VERSION, identity, illustrative, price_quantities

    q = {
        "rover_hours": 4,
        "human_visits": 1,
        "crew-hours": 3,
        "remote-hours": 0.5,
        "used:hardware:rover": 1,
    }
    a = illustrative(Costs(), version=ACTIVITY_VERSION)
    a["rates"]["crew_eur_per_hour"] = v["crew_price"]
    a["assets"]["rover"]["wear_eur_per_hour"] = v["wear"]
    a["assets"]["rover"]["life_years"] = v["life"]
    a["materials"]["hardware:rover"]["eur_per_unit"] = v["part_price"]
    a["initial_asset_purchase"] = v["purchase"] == "yes"
    priced = price_quantities(
        q, {k: ["teaching:" + k] for k in q}, {"rover": 24}, {}, a, hours=24, trace_id=identity(q)
    )
    views = priced["views"]
    return result(
        [
            metric("Allocated cost", views["allocated"]["total_eur"], "EUR"),
            metric("Decision cost", views["decision"]["total_eur"], "EUR"),
            metric("Expenditure", views["expenditure"]["total_eur"], "EUR"),
        ],
        [
            series(
                "Cost views",
                [views[k]["total_eur"] for k in ("allocated", "decision", "expenditure")],
                "EUR",
            )
        ],
        priced["lines"],
        [
            dict(
                id="component-total-" + k,
                passed=abs(sum(view["components"].values()) - view["total_eur"]) < 1e-7,
            )
            for k, view in views.items()
        ],
        allocation=priced,
        physical_trace_id=identity(q),
        scope="Fixed authored quantities, not an executed plant mission. Repricing never changes these quantities; expenditure is a distinct view and must not be added to allocated cost.",
    )


def service_uncertainty(v):
    from methane.duration_population import default_model, estimate

    item = next(iter(default_model()["groups"].values()))
    rows = [
        dict(
            id=f"job-{i}",
            order_id=f"job-{i}",
            nominal_hours=1,
            elapsed_hours=v["duration"],
            censored=v["censored"] == "yes",
            available_at=i + 1,
        )
        for i in range(v["jobs"])
    ]
    eligible = [r for r in rows if r["available_at"] <= v["clock"]]
    outcome = estimate(item, eligible, [0.6, 1.8], v["clock"], 24)
    return result(
        [
            metric("Estimated next-job factor", outcome["mean_factor"]),
            metric("Independent observed jobs", outcome["independent_jobs"]),
            metric("Model applicability", outcome["status"]),
        ],
        [series("Posterior weights", outcome["posterior_weights"])],
        eligible,
        [
            dict(
                id="posterior-normalised", passed=abs(sum(outcome["posterior_weights"]) - 1) < 1e-10
            )
        ],
        posterior=outcome,
        scope="Finite illustrative persistent equipment factors and independent uniform job multipliers. An unfinished clock is censored evidence, not a completed duration. Out-of-support observations block model-based use; no field calibration is claimed.",
    )


def charging(v):
    from methane.physics import State
    from methane.services.charging import Battery, solve
    from methane.timebase import stamp, utc

    p = replace(Plant(), battery_kwh=0, initial_h2_kg=0, heater_max_kw=0, cooling_max_kw=0)
    forecast = dict(
        pv_kw=[v["power"], 0, 0],
        ambient_c=[20] * 3,
        deliveries_kg=[0] * 3,
        times=[stamp(utc("2026-01-01") + timedelta(hours=i)) for i in range(3)],
        source={
            "id": "charging-learning/1",
            "initialized_at": "2026-01-01T00:00:00Z",
            "available_at": "2026-01-01T00:00:00Z",
        },
    )
    b = Battery(
        "rover",
        v["initial"],
        10,
        v["efficiency"],
        (True, False, False),
        (0, 0, v["use"]),
        (0, 0, 0),
        v["use"],
        2,
    )
    solved = solve(
        p, State.initial(p), forecast, 0, Costs(), [b], [10] * 3, [0, 3, 6, 9], seconds=1
    )
    if solved["plan"] is None:
        return result(
            [metric("Plan status", solved["status"])],
            solver=solved["solver"],
            scope="No validated plan meets the stated departure energy and dock/PV limits. Inputs have not been adjusted.",
        )
    rows = solved["plan"]["charging"]
    end = rows[-1]["after_kwh"]
    supplied = sum(r["requested_kw"] for r in rows)
    loss = sum(r["charging_loss_kwh"] for r in rows)
    return result(
        [
            metric("Bus electricity", supplied, "kWh"),
            metric("Charging loss", loss, "kWh"),
            metric("Ending rover energy", end, "kWh"),
        ],
        [series("Rover energy", [v["initial"]] + [r["after_kwh"] for r in rows], "kWh")],
        rows,
        [
            dict(
                id="independent-charge-balance",
                passed=abs(v["initial"] + supplied - loss - v["use"] - end) < 1e-7,
            )
        ],
        solver=solved["solver"],
        scope="One connected rover during H0, departure use at H2, no later sunlight. This implemented dock only uses available PV. End-of-interval charging cannot fund departure at that interval start.",
    )


def recovery(v):
    from methane.reference import audit
    from methane.services.verification_examples import CONTROLLER, fixture, weather_for
    from methane.simulation import run

    case = v["case"]
    c = fixture(case)
    c = replace(
        c,
        scenario=replace(c.scenario, hours=36),
        sensors=replace(c.sensors, ambiguity_policy="retain-capacity/1"),
        recovery_policy=replace(
            c.recovery_policy, version="scheduled-load-tests/5", maximum_wait_hours=v["deadline"]
        ),
    )
    r = run(c, weather=weather_for(c, case), strategies=[CONTROLLER])
    if r["status"] != "complete":
        raise ValueError(str(r["failures"]))
    rows = r["records"][CONTROLLER]
    checked = audit(r)
    if not checked["passed"]:
        raise ValueError(
            "Teaching execution failed independent audit: " + str(checked["failures"])[:400]
        )
    steps = [
        dict(
            hour=row["hour"],
            estimate_kw=row["diagnosis_after"]["capacity_kw"],
            requested_kw=row["requested"]["electrolyser_kw"],
            applied_kw=row["applied"]["electrolyser_kw"],
            recovery=row["decision"]["recovery_planning"],
            mission_events=row["field_operations"]["mission_events"],
        )
        for row in rows
    ]
    return result(
        [
            metric("Ending capacity estimate", steps[-1]["estimate_kw"], "kW"),
            metric("Methane", sum(row["applied"]["methane_kg"] for row in rows), "kg"),
            metric("Final recovery state", steps[-1]["recovery"]["status"]),
        ],
        [
            series("Capacity estimate", [s["estimate_kw"] for s in steps], "kW"),
            series("Requested load", [s["requested_kw"] for s in steps], "kW"),
        ],
        steps,
        [
            dict(
                id="production-independent-audit",
                passed=checked["passed"],
                checks=len(checked["checks"]),
            )
        ],
        scope="Coupled synthetic execution with an assumed human module replacement, finite support and observed tests. The selected fixture controls simulator outcomes; controller inputs exclude that choice. A completed mission does not prove repair. The window is not extended to ensure success.",
    )


ADAPTERS = dict(
    cleaning=cleaning,
    inspection=inspection,
    logistics=logistics,
    service_costs=service_costs,
    service_uncertainty=service_uncertainty,
    charging=charging,
    recovery=recovery,
)
