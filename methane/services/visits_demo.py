"""Reproducible multi-job crew workflows, before the full service Studies stage."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.config import Config, Scenario, Sensors, WeatherConfig
from methane.costing import reprice
from methane.evidence import save
from methane.field_operations import FieldOperations
from methane.provenance import LOADED_FILES
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.weather import synthetic

CASES = (
    "supplies",
    "separate-supplies",
    "interventions",
    "unsuccessful-interventions",
    "portable-transfer",
    "interrupted-portable",
    "short-shift",
    "empty-pipeline",
)


def fixture(case="supplies"):
    if case not in CASES:
        raise ValueError("Unknown crew visit fixture")
    c = Config(
        scenario=Scenario(hours=32, horizon_hours=6, solver_seconds=0.05),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        sensors=Sensors(noise_fraction=0),
        field_operations=FieldOperations(
            enabled=True,
            cleaner_enabled=False,
            rover_enabled=False,
            reset_enabled=False,
            service_kits=0,
            cleaning_kits=0,
            soiling_per_day=0,
            mission_failure_probability=0,
            repair_success_probability=1,
        ),
        service_system=ServiceSystem(
            inspector="none",
            support_model="logistics/1",
            visit_bundling_enabled=case != "separate-supplies",
            calibration_kits=0,
            crew_shift_duration_hours=16,
            crew_hours_per_period=16,
        ),
    )
    if case in ("interventions", "unsuccessful-interventions"):
        c = replace(
            c,
            scenario=replace(
                c.scenario, fault_start_hour=2, capacity_fraction=0.5, flow_bias_fraction=0.5
            ),
            field_operations=replace(
                c.field_operations,
                service_kits=2,
                cleaning_kits=0,
                repair_success_probability=0 if case.startswith("unsuccessful") else 1,
            ),
            service_system=replace(
                c.service_system,
                calibration_kits=2,
                crew_shift_start_hour=8,
                crew_shift_duration_hours=16,
            ),
        )
    if case in ("portable-transfer", "interrupted-portable"):
        c = replace(
            c,
            field_operations=replace(
                c.field_operations,
                cleaning_kits=6,
                initial_soiling_fraction=0.1,
                mission_failure_probability=1 if case.startswith("interrupted") else 0,
            ),
            service_system=replace(
                c.service_system,
                cleaning_model="section-optical/1",
                portable_cleaner="wet",
                calibration_kits=2,
            ),
        )
    if case == "short-shift":
        c = replace(c, service_system=replace(c.service_system, crew_shift_duration_hours=5))
    if case == "empty-pipeline":
        c = replace(c, service_system=replace(c.service_system, supplier_kits=0))
    return c


def execute(config):
    weather = synthetic(config)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(
                pv_kw=650 * config.plant.solar_kw / 1000, irradiance_wm2=650, ambient_c=20
            )
    weather["reference"] = (
        "Illustrative constant 650 W/m² and 20°C crew-visit fixture; not measured weather"
    )
    return run(config, weather=weather, strategies=["Greedy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/visits"))
    dest = parser.parse_args().directory
    dest.mkdir(parents=True, exist_ok=True)
    summaries = []
    lines = [
        "# One journey, separate jobs",
        "",
        "Eight saved 32-hour constant-irradiance workflow cases use Greedy production dispatch and the same local service rule. The supplies pair differs only in enabling combined visits. These fixtures test declared mechanics, not annual economics or empirical repair reliability.",
        "",
        "| Case | Visits | Committed crew h | Methane kg | Unfinished / acceptance pending | Independent audit |",
        "|---|---:|---:|---:|---:|---|",
    ]
    for name in CASES:
        result = execute(fixture(name))
        checked = audit(result)
        archive = save(result, dest)
        make(result, dest / (name + "-reproduction.zip"))
        (dest / (name + "-playback.html")).write_text(playback(result, LOADED_FILES))
        (dest / (name + "-audit.json")).write_text(json.dumps(checked, indent=2))
        rows = result["records"]["Greedy"]
        services = [r["field_operations"] for r in rows]
        final = services[-1]["state"]
        unresolved = [
            q["id"] for q in final["orders"] if q["status"] not in ("completed", "verified")
        ]
        summary = dict(
            case=name,
            run_id=result["run_id"],
            archive=archive.name,
            status=result["status"],
            failures=result["failures"],
            visits=sum(r["human_visits"] for r in services),
            crew_hours=sum(r["crew_committed_hours"] for r in services),
            methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
            ending_plant=rows[-1]["state"],
            ending_services=final,
            unresolved=unresolved,
            costs=reprice(result)["controllers"]["Greedy"][-1],
            audit_passed=checked["passed"],
        )
        summaries.append(summary)
        lines.append(
            f"| [{name}]({name}-playback.html) | {summary['visits']} | {summary['crew_hours']:.2f} | {summary['methane_kg']:.2f} | {len(unresolved)} | {'Passed' if checked['passed'] else 'Failed'} |"
        )
    lines += [
        "",
        "Three typed supplies take one 3.5-hour visit instead of three separate visits consuming 7.5 crew-hours. Each delivery retains its own receipt. A short shift splits the work; an empty pipeline blocks departure without granting future stock.",
        "",
        "The intervention pair combines a known delivery with a known module request when the crew shift opens. Repair success is private execution information and cannot change that original itinerary. A later flow diagnosis is a new request. The failed replacement remains unverified even after the crew returns.",
        "",
        "Portable treatment and a later delivery can share a crew. An interruption retains consumed water, labour and treated area while blocking the later delivery; neither the crew nor the tool is silently returned home. Compatible assistance remains separate programme work.",
        "",
        "Current callouts and hands-on/material charges follow actual events. Committed crew time is a separate resource measure, not a duplicate travel-labour charge. Full service economics, coordinated planning and published Studies are later stages. All ending inventories and unresolved orders are preserved in the saved cases and reproduction bundles.",
    ]
    (dest / "report.md").write_text("\n".join(lines) + "\n")
    (dest / "cases.json").write_text(json.dumps(summaries, indent=2) + "\n")
    print(dest / "report.md")
    if not all(x["audit_passed"] for x in summaries):
        raise SystemExit("A visit case failed independent verification")


if __name__ == "__main__":
    main()
