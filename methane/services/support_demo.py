"""Saved bounded logistics examples; not complete service economics."""

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
from methane.weather import synthetic

CASES = ("retrieval", "failed-drive-test", "unavailable-crew", "finite-supply", "brush-replacement")


def run_case(name):
    if name not in CASES:
        raise ValueError("Unknown support example")
    c = Config(
        scenario=Scenario(hours=18, horizon_hours=6, solver_seconds=0.05),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=FieldOperations(
            enabled=True,
            rover_enabled=False,
            reset_enabled=False,
            initial_soiling_fraction=0.1,
            soiling_per_day=0,
            mission_failure_probability=1 if name in CASES[:3] else 0,
        ),
        service_system=ServiceSystem(
            inspector="none",
            cleaning_model="section-optical/1",
            support_model="logistics/1",
            work_failure_fraction=0.3,
            robot_test_success_probability=0 if name == "failed-drive-test" else 1,
            crew_available=name != "unavailable-crew",
            brush_initial_condition=0.01 if name == "brush-replacement" else 1,
        ),
    )
    if name == "finite-supply":
        c = replace(
            c,
            field_operations=replace(c.field_operations, cleaning_kits=0, service_kits=0),
            service_system=replace(
                c.service_system,
                store_capacity_kits=1,
                supplier_kits=4,
                calibration_kits=0,
                brush_spares=0,
            ),
        )
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=1000, irradiance_wm2=1000, ambient_c=20)
    weather["reference"] = (
        "Illustrative constant 1000 W/m² / 1000 kW reference DC / 20°C support fixture; not measured weather"
    )
    weather["attribution"] = "Dispatch Lab synthetic teaching fixture"
    return run(c, weather=weather, strategies=["Greedy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/support"))
    args = parser.parse_args()
    args.directory.mkdir(parents=True, exist_ok=True)
    summaries = []
    lines = [
        "# Recovery requires support and evidence",
        "",
        "Five reproducible 18-hour mechanism examples use a fixed seed, Greedy plant dispatch and constant irradiance. Reliability, labour, travel and supply assumptions are illustrative. The three recovery cases share a deliberately certain cleaning abort at 30% of each pass; only drive-test success or crew availability changes. The other cases exercise finite delivery and brush replacement. These are not annual economics or a published matched Studies experiment.",
        "",
        "| Case | Treated m² | Crew committed h | Remote h | Visits | Returned | Ending cleaner | Independent audit |",
        "|---|---:|---:|---:|---:|---:|---|---|",
    ]
    for name in CASES:
        result = run_case(name)
        report = audit(result)
        archive = save(result, args.directory)
        (args.directory / f"{name}-playback.html").write_text(playback(result, LOADED_FILES))
        make(result, args.directory / f"{name}-reproduction.zip")
        (args.directory / f"{name}-audit.json").write_text(json.dumps(report, indent=2))
        rows = result["records"]["Greedy"]
        services = [r["field_operations"] for r in rows]
        final = services[-1]["state"]

        def total(key, values=services):
            return sum(r.get(key, 0) for r in values)

        summary = dict(
            case=name,
            run_id=result["run_id"],
            archive=archive.name,
            status=result["status"],
            failures=result["failures"],
            treated_m2=total("treated_area_m2"),
            crew_hours=total("crew_committed_hours"),
            remote_hours=total("remote_hours"),
            visits=total("human_visits"),
            ending_robot=final["robots"]["cleaner"],
            support=final["support"],
            resources=final["executive"]["resources"],
            ending_plant=rows[-1]["state"],
            support_effects=[e for s in services for e in s["support_effects"]],
            unresolved_orders=[
                q for q in final["orders"] if q["status"] not in ("verified", "completed")
            ],
            methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
            audit_passed=report["passed"],
        )
        summaries.append(summary)
        lines.append(
            f"| [{name}]({name}-playback.html) | {summary['treated_m2']:.1f} | {summary['crew_hours']:.2f} | {summary['remote_hours']:.2f} | {summary['visits']} | {len(final['support']['returned'])} | {summary['ending_robot']['status']} | {'Passed' if report['passed'] else 'Failed'} |"
        )
    lines += [
        "",
        "In the retrieval fixture, unloading completes at H5.5 and is eligible at H6; a quarter-hour drive test supplies the first passing recovery evidence at H7. A later cleaning attempt deliberately fails again. Ending backlog is therefore retained, including the second retrieval blocked by the remaining shift. A successful return does not rewrite the failed original mission.",
        "",
        "The failed-test case returns physically but cannot resume work. The unavailable-crew case remains stranded. Finite supply delivers four kits into capacity one: one accepted and three explicitly rejected. Brush replacement consumes a spare, discards 500 m² of unused old allowance and installs a new 50,000 m² allowance at H4.",
        "",
        "Full original source, weather, configuration, resource events and checks are saved in each reproduction bundle. Cases JSON keeps failed work, unfinished support, ending plant inventories, labour and upstream supplies. The independent checker verifies declared balances and chronology, not actual repair reliability. The fuller pricing and Studies work remains stage 3; remote hours, brush replacements and rejected supplies are explicitly unpriced in this checkpoint.",
    ]
    (args.directory / "report.md").write_text("\n".join(lines) + "\n")
    (args.directory / "cases.json").write_text(json.dumps(summaries, indent=2))
    print(args.directory / "report.md")
    if not all(s["audit_passed"] for s in summaries):
        raise SystemExit("A mechanism example failed its independent audit")


if __name__ == "__main__":
    main()
