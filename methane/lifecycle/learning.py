"""Independent teaching contexts using the production executive and kernels."""

from dataclasses import replace

from methane.config import Config
from methane.learning import metric, result, series
from methane.lifecycle.families import FAMILIES, assess, catalogue
from methane.lifecycle.runtime import Runtime, condition_fraction


def deployment(v):
    runtime = Runtime(
        dict(
            crew_shift_start=0,
            crew_hours_per_day=v["crew"],
            packages=[
                dict(
                    id="array",
                    asset="solar",
                    fraction=1,
                    installation_hours=v["work"],
                    failed_acceptance_attempts=v["failed"],
                    equipment_eur_per_hour=40,
                    equipment_energy_kwh_per_hour=2,
                    external_energy_eur_per_kwh=0.25,
                    installation_material_eur=500,
                )
            ],
            outages=[dict(resource="access", start_hour=2, end_hour=2 + v["blocked"])]
            if v["blocked"]
            else [],
        ),
        7,
    )
    steps = []
    for h in range(120):
        view = runtime.begin(h, dict(pv_kw=[500] * 24))
        row = runtime.finish(dict(applied=dict(electrolyser_kw=0), electrolyser_start=0))
        steps.append(
            dict(
                hour=h,
                capacity_kw=500 * view["availability"]["solar"],
                package=view["packages"]["array"],
                package_after=row["after"]["packages"]["array"],
                crew_hours=view["current"]["crew_hours"],
                cost_eur=sum(a for k, a in row["expenditure"].items() if k.endswith("_eur")),
                external_kwh=row["expenditure"]["external_energy_kwh"],
                reason=view["current"]["reason"],
            )
        )
    return result(
        [
            metric("Accepted boundary", steps[-1]["package"]["accepted_at"], "h"),
            metric("Project labour", sum(s["crew_hours"] for s in steps), "h"),
            metric("Capital expenditure", sum(s["cost_eur"] for s in steps), "EUR"),
        ],
        [series("Accepted capacity", [s["capacity_kw"] for s in steps], "kW")],
        steps,
        [
            dict(
                id="capacity_requires_acceptance",
                passed=all(
                    s["capacity_kw"] == 0 or s["package"]["accepted_at"] <= s["hour"] for s in steps
                ),
            )
        ],
        scope="120-hour work-package example. Capacity is credited after acceptance; invoices and temporary departure are separate. No coupled methane production is computed here.",
    )


def condition(v):
    solar = v["asset"] == "solar"
    spec = dict(
        asset=v["asset"],
        replacement_part_eur=850000 if solar else 120000,
        initial_calendar_hours=v["age"] if solar else 0,
        initial_operating_hours=0 if solar else v["age"],
        pv_loss_per_year=0.005 * v["rate"],
        stack_mv_per_1000h=4.8 * v["rate"],
        sensor_delay_hours=v["delay"],
        sensor_period_hours=1,
        sensor_noise_fraction=v["noise"],
        replacement_threshold=v["threshold"],
        replacement_hours=2,
        replacement_success_fraction=int(v["success"] == "succeeds"),
    )
    runtime = Runtime(dict(conditions=[spec], crew_shift_start=0, crew_hours_per_day=24), 7)
    steps = []
    for h in range(24):
        view = runtime.begin(h, dict(pv_kw=[500] * 24))
        power = 100 * view["availability"]["electrolyser"]
        physics = condition_fraction(runtime.spec(v["asset"]), runtime.conditions[v["asset"]])
        row = runtime.finish(dict(applied=dict(electrolyser_kw=power), electrolyser_start=0))
        observed = view["condition"][v["asset"]]
        steps.append(
            dict(
                hour=h,
                physical_condition=physics,
                estimate=observed["estimate"],
                measurement=observed["measurement"],
                stock=observed["stock"],
                availability=view["availability"][v["asset"]],
                jobs=row["after"]["jobs"],
                procedure=row["events"],
                requested_work=view["current"]["reason"],
            )
        )
    return result(
        [
            metric("Ending measured condition", steps[-1]["estimate"], "fraction"),
            metric("Procedures completed", runtime.conditions[v["asset"]]["replacements"]),
            metric("Verified procedures", sum(j["status"] == "verified" for j in runtime.jobs)),
            metric("Remaining stock", runtime.conditions[v["asset"]]["stock"], "part"),
        ],
        [
            series("Retrospective condition", [s["physical_condition"] for s in steps], "fraction"),
            series("Eligible estimate", [s["estimate"] for s in steps], "fraction"),
        ],
        steps,
        [
            dict(
                id="no_future_reading",
                passed=all(
                    s["measurement"] is None or s["measurement"]["available_at"] <= s["hour"]
                    for s in steps
                ),
            )
        ],
        scope="Declared ageing and observation channel, with fixed operating activity. A procedure is followed by measured verification. Private physical condition is explicitly retrospective; future readings do not enter the executive.",
    )


def hardware(v):
    requirements = FAMILIES[v["family"]][2]
    response = assess(
        v["family"], requirements if v["support"] == "present" else (), automation=v["automation"]
    )
    return result(
        [
            metric("Disposition", response["status"]),
            metric("Missing prerequisites", len(response["missing"])),
            metric("Available mechanism", response["eligible"]),
        ],
        sequences=[
            series(
                "Declared prerequisite present",
                [int(p not in response["missing"]) for p in requirements],
                "boolean",
            )
        ],
        steps=[response],
        prerequisites=requirements,
        assessment=response,
        families=catalogue(),
        checks=[
            dict(
                id="restricted_never_admitted",
                passed=response["status"] != "evidence restricted" or not response["eligible"],
            )
        ],
        scope=response["boundary"] + ". " + response["scope"],
    )


def maintenance(v):
    from methane.learning import report_progress
    from methane.simulation import run
    from methane.weather import prepare

    if v["hours"] != int(v["hours"]):
        raise ValueError("Comparison hours must be a whole number")
    base = Config()
    base = replace(
        base,
        scenario=replace(
            base.scenario,
            hours=int(v["hours"]),
            horizon_hours=6,
            forecast_bias=v["stress"],
            solver_seconds=0.05,
            seed=7,
        ),
    )
    weather = prepare(base)
    cases = []
    for policy in ("none", "periodic", "condition", "forecast-window"):
        report_progress("Comparing maintenance: " + policy)
        c = replace(
            base,
            lifecycle=dict(
                maintenance_policy=policy,
                crew_shift_start=0,
                crew_hours_per_day=24,
                conditions=[
                    dict(
                        asset="electrolyser",
                        initial_operating_hours=v["age"],
                        replacement_part_eur=v["part"],
                        periodic_hours=24,
                        replacement_hours=4,
                    )
                ],
            ),
        )
        r = run(c, weather, ["Greedy"])
        m = r["metrics"]["Greedy"]
        cases.append(
            dict(
                policy=policy,
                status=r["status"],
                methane_kg=m["methane_kg"],
                ending=m["ending"],
                allocated_eur=m["total_eur"],
                contribution_eur=m["assumed_contribution_eur"],
                lifecycle=m["lifecycle"],
                fallbacks=m["fallbacks"],
                failures=r.get("failures"),
                trajectory=[
                    dict(
                        hour=x["hour"],
                        methane_kg=x["applied"]["methane_kg"],
                        condition=x["lifecycle"]["after"]["condition"],
                    )
                    for x in r["records"]["Greedy"]
                ],
            )
        )
    return result(
        [metric(c["policy"] + " methane", c["methane_kg"], "kg") for c in cases],
        [series(c["policy"], [x["methane_kg"] for x in c["trajectory"]], "kg CH₄") for c in cases],
        cases,
        [dict(id="all_cases_retained", passed=len(cases) == 4)],
        cases=cases,
        scope="Four matched synthetic maintenance policies with the same Greedy process rule and fixed seed. Window and ending inventories are retained. This does not establish annual benefit, empirical degradation or a globally optimal maintenance schedule.",
    )


ADAPTERS = dict(
    deployment=deployment, condition=condition, hardware=hardware, maintenance=maintenance
)
