"""Saved, matched inspection mechanism examples; not a hardware-value study."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.config import Config, Plant, Scenario, Sensors, WeatherConfig
from methane.costing import reprice
from methane.evidence import save
from methane.faults import FaultPolicy
from methane.field_operations import FieldOperations
from methane.provenance import LOADED_FILES
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.weather import synthetic

CASES = (
    "normal",
    "trip",
    "reader-drift",
    "reader-dropout",
    "shared-contact",
    "changed-contact",
    "late-evidence",
    "communications",
)


def fixture(case="trip"):
    if case not in CASES:
        raise ValueError("Unknown inspection fixture")
    c = Config(
        plant=Plant(initial_soc=0.5),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        scenario=Scenario(
            hours=32,
            horizon_hours=6,
            fault_start_hour=2,
            capacity_fraction=0.5,
            solver_seconds=0.05,
        ),
        sensors=Sensors(noise_fraction=0),
        field_operations=FieldOperations(
            enabled=True,
            cleaner_enabled=False,
            mission_failure_probability=0,
            repair_success_probability=1,
            human_lead_hours=1,
        ),
        service_system=ServiceSystem(
            inspector="both", inspection_model="referenced-contact/1", inspection_noise_v=0
        ),
        faults=FaultPolicy(capacity_cause="resettable-trip"),
    )
    if case == "normal":
        c = replace(c, scenario=replace(c.scenario, capacity_fraction=1))
    if case == "reader-drift":
        c = replace(c, faults=replace(c.faults, fixed_reader_drift_vph=1))
    if case == "reader-dropout":
        c = replace(c, faults=replace(c.faults, fixed_reader_dropout=True))
    if case == "shared-contact":
        c = replace(
            c, faults=replace(c.faults, capacity_cause="equipment-damage", contact_stuck="closed")
        )
    if case == "changed-contact":
        c = replace(
            c, faults=replace(c.faults, inspection_fault_start_hour=5, contact_stuck="open")
        )
    if case == "late-evidence":
        c = replace(c, service_system=replace(c.service_system, inspection_delay_hours=12))
    if case == "communications":
        c = replace(c, service_system=replace(c.service_system, communications_available=False))
    return c


def execute(config):
    weather = synthetic(config)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(
                pv_kw=650 * config.plant.solar_kw / 1000, irradiance_wm2=650, ambient_c=20
            )
    weather["reference"] = (
        "Illustrative constant 650 W/m² reference irradiance and 20°C inspection fixture; 650 kW reference DC at 1,000 kW array rating with zero conversion/temperature loss; no measured weather"
    )
    return run(config, weather=weather, strategies=["Greedy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/inspection"))
    dest = parser.parse_args().directory
    dest.mkdir(parents=True, exist_ok=True)
    summaries = []
    lines = [
        "# What does a contact inspection establish?",
        "",
        "Eight saved 32-hour constant-power examples use the same plant, Greedy dispatch and local service rule. Named changes are declared scenario assumptions. The fixed and rover readers share one prepared contact but have separate measurement channels and reference tests. No empirical reliability or annual hardware-value claim follows.",
        "",
        "| Case | Resets | Module substitutions | Site visits | CH₄ kg | Final process estimate | Independent checks |",
        "|---|---:|---:|---:|---:|---|---|",
    ]
    for case in CASES:
        result = execute(fixture(case))
        checked = audit(result)
        archive = save(result, dest)
        make(result, dest / f"{case}-reproduction.zip")
        (dest / f"{case}-playback.html").write_text(playback(result, LOADED_FILES))
        (dest / f"{case}-audit.json").write_text(json.dumps(checked, indent=2))
        rows = result["records"]["Greedy"]
        services = [r["field_operations"] for r in rows]
        summary = dict(
            case=case,
            run_id=result["run_id"],
            archive=archive.name,
            status=result["status"],
            failures=result["failures"],
            resets=sum(r["reset_attempts"] for r in services),
            substitutions=sum(r["service_kits_used"] for r in services),
            visits=sum(r["human_visits"] for r in services),
            methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
            ending_estimate=rows[-1]["diagnosis_after"],
            ending_plant=rows[-1]["state"],
            ending_services=services[-1]["state"],
            costs=reprice(result)["controllers"]["Greedy"][-1],
            audit_passed=checked["passed"],
        )
        summaries.append(summary)
        lines.append(
            f"| [{case}]({case}-playback.html) | {summary['resets']} | {summary['substitutions']} | {summary['visits']} | {summary['methane_kg']:.2f} | {summary['ending_estimate']['status']} | {'Passed' if checked['passed'] else 'Failed'} |"
        )
    lines += [
        "",
        "The drifting reader fails its internal reference check; a usable rover read can still support a reset. Complete dropout remains missing measurement content, never zero volts. Delayed evidence keeps its original measurement time and is withheld until its publication boundary. A changed contact can produce valid but disagreeing readings at different acquisition times.",
        "",
        "The shared-contact case deliberately defeats reader redundancy: both reference checks pass while the contact is stuck closed over a damaged module. A reset cannot repair that damage. Later informative process tracking supports escalation to a qualified substitution; no contact observation directly restores the process estimate.",
        "",
        "These examples retain unresolved inspections and delayed verification. A single local investigative rule is not an information-optimal controller. Existing ownership, energy, crew and mission wear are recorded; prepared-port and internal-reference hardware remain explicitly unpriced until the complete economics stage. Full service Studies publications and richer sensing modalities remain programme work.",
    ]
    (dest / "report.md").write_text("\n".join(lines) + "\n")
    (dest / "cases.json").write_text(json.dumps(summaries, indent=2))
    print(dest / "report.md")
    if not all(c["audit_passed"] for c in summaries):
        raise SystemExit("An inspection example failed independent checks")


if __name__ == "__main__":
    main()
