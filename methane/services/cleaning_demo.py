"""Reproducible optical-cleaning mechanism examples, not annual economics."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.config import Config, Scenario, WeatherConfig
from methane.evidence import save
from methane.field_operations import FieldOperations
from methane.provenance import LOADED_FILES
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.solar_model import default_design
from methane.weather import synthetic

CASES = ("no-cleaning", "dry-brush", "interrupted", "converter-clipping")


def run_case(name):
    if name not in CASES:
        raise ValueError("Unknown optical-cleaning example")
    config = Config(
        scenario=Scenario(hours=18, horizon_hours=6, solver_seconds=0.1),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=FieldOperations(
            enabled=True,
            cleaner_enabled=name != "no-cleaning",
            rover_enabled=False,
            reset_enabled=False,
            human_fallback=False,
            initial_soiling_fraction=0.1,
            soiling_per_day=0,
            cleaning_removal_fraction=1,
            mission_failure_probability=1 if name == "interrupted" else 0,
        ),
        service_system=ServiceSystem(
            cleaning_model="section-optical/1",
            inspector="none",
            initial_adhered_fraction=0.2,
            initial_damage_fraction=0.05,
            work_failure_fraction=0.3,
        ),
    )
    if name == "converter-clipping":
        design = default_design(config.plant, config.weather)
        design["converter_kw"] = 500
        config = replace(config, solar=design)
    weather = synthetic(config)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(irradiance_wm2=1000, pv_kw=1000, ambient_c=20)
    weather["reference"] = (
        "Teaching fixture: constant 1000 W/m² irradiance, reference 1000 kW DC and 20°C "
        "ambient, zero temperature coefficient and electrical losses; synthetic timestamps"
    )
    weather["attribution"] = (
        "Dispatch Lab illustrative constant-input mechanism fixture, not measured weather"
    )
    return run(config, weather=weather, strategies=["Greedy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/cleaning"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Partial cleaning: from surface to production",
        "",
        "Four reproducible 18-hour mechanism examples use constant irradiance and ambient temperature, the same plant, and Greedy dispatch. The cleaner is absent only in the no-cleaning case. The clipping case changes only converter capacity from 1000 to 500 kW; the interrupted case changes only seeded work failure from zero to certain at 30% of the pass. No future failure information reaches the supervisor. All performance and reliability assumptions are illustrative.",
        "",
        "| Case | Treated m² | End loose loss | Available DC kWh | Converter clipping kWh | Plant curtailment kWh | Service bus kWh | Methane kg | Ending cleaner | Independent audit |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    summaries = []
    for name in CASES:
        result = run_case(name)
        report = audit(result)
        archived = save(result, args.directory)
        (args.directory / f"{name}-playback.html").write_text(playback(result, LOADED_FILES))
        make(result, args.directory / f"{name}-reproduction.zip")
        (args.directory / f"{name}-audit.json").write_text(json.dumps(report, indent=2))
        rows = result["records"]["Greedy"]
        final = rows[-1]["field_operations"]
        robot = final["state"]["robots"].get("cleaner")
        row = dict(
            case=name,
            run_id=result["run_id"],
            archive=archived.name,
            status=result["status"],
            failures=result["failures"],
            treated_m2=sum(r["field_operations"]["treated_area_m2"] for r in rows),
            ending_loose_fraction=final["soiling_after"],
            available_dc_kwh=sum(r["pv_kw"] for r in rows),
            clipping_kwh=sum(r["solar_detail"]["clipped_kw"] for r in rows),
            curtailment_kwh=sum(r["curtailed_kwh"] for r in rows),
            service_bus_kwh=sum(r["service_kw"] for r in rows),
            methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
            ending_robot=robot,
            ending_brush_m2=final["brush_after_m2"],
            ending_plant=rows[-1]["state"],
            unresolved_orders=[
                o for o in final["state"]["orders"] if o["status"] not in ("verified", "completed")
            ],
            audit_passed=report["passed"],
        )
        summaries.append(row)
        lines.append(
            f"| [{name}]({name}-playback.html) | {row['treated_m2']:.1f} | {row['ending_loose_fraction']:.2%} | {row['available_dc_kwh']:.2f} | {row['clipping_kwh']:.2f} | {row['curtailment_kwh']:.2f} | {row['service_bus_kwh']:.3f} | {row['methane_kg']:.3f} | {robot['status'] if robot else 'Not installed'} | {'Passed' if report['passed'] else 'Failed'} |"
        )
    lines += [
        "",
        "At H0 the independent transmission calculation is 0.9 × 0.8 × 0.95 = 0.684. The first half-hour of work follows a half-hour journey and treats 500 m². H1 retains that improvement even when the work then fails. Adhered loss (20%) and damage (5%) remain unchanged. The clipped converter can recover light without recovering available DC. Curtailed electricity and methane are separate downstream results.",
        "",
        "Full-pass completion and partial treated area are different records. The interrupted cleaner remains stranded; retrieval is not yet implemented in this checkpoint. Initial robot energy is a finite inventory, so service bus energy alone is not the robot's complete energy use. Every archive retains initial/final stocks, work energy, accepted/rejected charging and event timing.",
        "",
        "The cases JSON retains unresolved work and all ending plant/robot inventories. Each reproduction ZIP includes original source, weather, configuration and a dependency-free checker. These are integration examples, not the generalised Studies programme or a cost-benefit study. No annual claims or hardware recommendations follow from constant irradiance. Brush replacement, support logistics and complete running-cost comparisons remain later programme work.",
    ]
    (args.directory / "report.md").write_text("\n".join(lines) + "\n")
    (args.directory / "cases.json").write_text(json.dumps(summaries, indent=2))
    print(args.directory / "report.md")


if __name__ == "__main__":
    main()
