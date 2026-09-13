"""Reproducible portable-treatment fixtures and source-preserving reports."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.config import Config, Scenario, WeatherConfig
from methane.costing import reprice
from methane.evidence import save
from methane.field_operations import FieldOperations
from methane.provenance import LOADED_FILES
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.weather import synthetic

CASES = ("no-cleaning", "dry", "wet", "no-water", "interrupted")


def fixture(method="wet", **options):
    return Config(
        scenario=Scenario(hours=18, horizon_hours=6, solver_seconds=0.05),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=FieldOperations(
            enabled=True,
            cleaner_enabled=False,
            rover_enabled=False,
            reset_enabled=False,
            initial_soiling_fraction=0.1,
            soiling_per_day=0,
            mission_failure_probability=0,
        ),
        service_system=ServiceSystem(
            inspector="none",
            cleaning_model="section-optical/1",
            support_model="logistics/1",
            portable_cleaner=method,
            initial_adhered_fraction=0.2,
            initial_damage_fraction=0.05,
            **options,
        ),
    )


def execute(config, ambient=20):
    weather = synthetic(config)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=1000, irradiance_wm2=1000, ambient_c=ambient)
    weather["reference"] = (
        "Illustrative constant 1000 W/m² irradiance, 1000 kW reference DC and declared ambient temperature; no measured weather"
    )
    weather["attribution"] = "Dispatch Lab synthetic portable-treatment fixture"
    return run(config, weather=weather, strategies=["Greedy"])


def run_case(name):
    if name not in CASES:
        raise ValueError("Unknown portable-treatment fixture")
    c = fixture(
        "none" if name == "no-cleaning" else "dry" if name == "dry" else "wet",
        work_failure_fraction=0.3,
    )
    if name == "no-water":
        c = replace(
            c,
            service_system=replace(
                c.service_system, portable_water_initial_l=0, portable_upstream_water_l=0
            ),
        )
    if name == "interrupted":
        c = replace(c, field_operations=replace(c.field_operations, mission_failure_probability=1))
    return execute(c)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/portable"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    summaries = []
    lines = [
        "# Portable cleaning: light, water and operator time",
        "",
        "Five saved 18-hour mechanism examples share the plant, constant irradiance and surface condition. Treatment or water/failure assumptions change explicitly. All use Greedy plant dispatch and the same local service rule. These are illustrative integration examples; full installation economics and published Studies comparisons remain separate programme work.",
        "",
        "| Case | Treated m² | Water used L | Crew h | Site visits | Available DC kWh | Methane kg | Independent checks |",
        "|---|---:|---:|---:|---:|---:|---:|---|",
    ]
    for name in CASES:
        result = run_case(name)
        checked = audit(result)
        archive = save(result, args.directory)
        (args.directory / f"{name}-playback.html").write_text(playback(result, LOADED_FILES))
        make(result, args.directory / f"{name}-reproduction.zip")
        (args.directory / f"{name}-audit.json").write_text(json.dumps(checked, indent=2))
        rows = result["records"]["Greedy"]
        records = [r["field_operations"] for r in rows]
        end = records[-1]["state"]
        costs = reprice(result)
        summary = dict(
            case=name,
            run_id=result["run_id"],
            archive=archive.name,
            status=result["status"],
            failures=result["failures"],
            treated_m2=sum(r["treated_area_m2"] for r in records),
            water_l=sum(r.get("water_used_l", 0) for r in records),
            crew_h=sum(r["crew_committed_hours"] for r in records),
            visits=sum(r["human_visits"] for r in records),
            available_dc_kwh=sum(r["pv_kw"] for r in rows),
            methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
            curtailment_kwh=sum(r["curtailed_kwh"] for r in rows),
            ending_plant=rows[-1]["state"],
            ending_services=end,
            costs=costs,
            audit_passed=checked["passed"],
            unresolved_orders=[
                q for q in end["orders"] if q["status"] not in ("completed", "verified")
            ],
        )
        summaries.append(summary)
        lines.append(
            f"| [{name}]({name}-playback.html) | {summary['treated_m2']:.1f} | {summary['water_l']:.2f} | {summary['crew_h']:.2f} | {summary['visits']} | {summary['available_dc_kwh']:.2f} | {summary['methane_kg']:.2f} | {'Passed' if checked['passed'] else 'Failed'} |"
        )
    lines += [
        "",
        "A full reference section is 5,000/3 m². Wet treatment needs 10 litres of setup rinse plus 0.5 litres/m², or 843.33 litres. The first half-hour of treatment follows half an hour of setup and retains 500 m² of coverage at H4. A configured interruption at that boundary retains the same 260 litres already consumed and leaves the tool/operator awaiting assistance.",
        "",
        "On a fully treated patch, initial transmission is 0.9 × 0.8 × 0.95 = 0.684. Dry brushing gives 0.99 × 0.8 × 0.95 = 0.7524; the wet method gives 0.99 × 0.94 × 0.95 = 0.88407. Permanent damage remains 5%. These are declared loss-factor calculations, not measured cleaning efficacy. Increased available DC need not increase methane when the downstream plant already reaches its limit.",
        "",
        "Finite water triggers a separate delivery visit. The crew cannot deliver and clean concurrently. The declared shift, response lead and return duration leave unfinished work visible at the end. These local scheduling restrictions motivate later visit bundling and service-aware planning; they do not establish the best service design.",
        "",
        "The JSON keeps ending plant/service stocks, surface condition, unresolved work and cost reports. Operator labour, visits and material kits are priced once at existing illustrative rates. Portable hire, used water and rejected-water procurement remain explicitly unpriced pending the complete stage-3 economics. No annual value or hardware recommendation follows from these short constant-weather examples.",
    ]
    (args.directory / "report.md").write_text("\n".join(lines) + "\n")
    (args.directory / "cases.json").write_text(json.dumps(summaries, indent=2))
    print(args.directory / "report.md")
    if not all(c["audit_passed"] for c in summaries):
        raise SystemExit("An example failed its independent checks")


if __name__ == "__main__":
    main()
