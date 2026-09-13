"""Reproducible coupled integration example, not a field-economics study."""

import argparse
import json
from pathlib import Path

from methane.bundle import make, playback
from methane.config import Config, Plant, Scenario, Sensors
from methane.evidence import save
from methane.field_operations import FieldOperations
from methane.provenance import LOADED_FILES
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.weather import synthetic


def run_case(inspector):
    c = Config(
        plant=Plant(h2_capacity_kg=200),
        scenario=Scenario(
            hours=32,
            horizon_hours=6,
            fault_start_hour=2,
            capacity_fraction=0.5,
            flow_bias_fraction=0.4,
            solver_seconds=0.1,
        ),
        sensors=Sensors(noise_fraction=0),
        field_operations=FieldOperations(
            enabled=True,
            human_lead_hours=1,
            mission_failure_probability=0,
            repair_success_probability=1,
        ),
        service_system=ServiceSystem(
            inspector=inspector, contact_unreadable_probability=0, contact_error_probability=0
        ),
    )
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=650, ambient_c=20)
    weather["reference"] = (
        "Integration fixture: constant 650 kW available DC and 20 C ambient; synthetic timestamps and context"
    )
    weather["attribution"] = (
        "Dispatch Lab illustrative constant-power fixture, not observed or downloaded weather"
    )
    return run(c, weather=weather, strategies=["Greedy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/coupled"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    lines = [
        "# Coupled fractional service example",
        "",
        "This checks integration and information timing. It does not establish annual hardware value or calibrated reliability. Both cases use the same 32-hour constant-power fixture, diagnosed capacity loss and flow bias; service policies see no injected truth. Read errors and repair failures are disabled here so the two execution paths are easy to inspect.",
        "",
        "| Reader | Methane kg | Service electricity kWh | Site visits | Module / calibration kits | Ending robot energy kWh | Independent audit |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    summaries = []
    for inspector in ("mobile", "fixed"):
        result = run_case(inspector)
        report = audit(result)
        saved = save(result, args.directory)
        (args.directory / (inspector + "-playback.html")).write_text(playback(result, LOADED_FILES))
        make(result, args.directory / (inspector + "-reproduction.zip"))
        (args.directory / (inspector + "-audit.json")).write_text(json.dumps(report, indent=2))
        rows = result["records"]["Greedy"]
        final = rows[-1]["field_operations"]
        metrics = result["metrics"]["Greedy"]
        q = metrics["field_operations"]["quantities"]
        methane = sum(r["applied"]["methane_kg"] for r in rows)
        lines.append(
            f"| {inspector} | {methane:.3f} | {sum(r['service_kw'] for r in rows):.3f} | {q['human_visits']:g} | {q['service_kits_used']:g} / {q['calibration_kits_used']:g} | {sum(final['energy_after_kwh'].values()):.3f} | {'Passed' if report['passed'] else 'Failed'} |"
        )
        summaries.append(
            dict(
                reader=inspector,
                run_id=result["run_id"],
                archive=saved.name,
                status=result["status"],
                audit_passed=report["passed"],
                orders=final["state"]["orders"],
            )
        )
    lines += [
        "",
        "Each procedure restores only its compatible physical channel. Work completion, next-boundary effects, return travel and operating verification are separately timestamped. The full records retain unresolved orders and estimated state; complete means every requested simulation interval ran, not that every recovery was verified.",
        "",
        "[Mobile playback](mobile-playback.html) · [Fixed playback](fixed-playback.html). The matching reproduction ZIPs contain original source, parameters, weather, missions, declared observations, ledgers and a dependency-free independent checker.",
        "",
        "The mobile fixture owns an initially full 2 kWh rover battery; the fixed case does not. This ending-inventory difference is explicit. Cleaning still uses the original lumped post-conversion proxy. Full logistics costs, visit bundling, section cleaning and coordinated maintenance planning remain programme work.",
    ]
    (args.directory / "report.md").write_text("\n".join(lines) + "\n")
    (args.directory / "cases.json").write_text(json.dumps(summaries, indent=2))
    print(args.directory / "report.md")


if __name__ == "__main__":
    main()
