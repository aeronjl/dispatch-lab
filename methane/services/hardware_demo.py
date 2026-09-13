"""Constant-power workflow fixtures for bounded service hardware recovery."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.costing import reprice
from methane.evidence import save
from methane.faults import FaultPolicy
from methane.provenance import LOADED_FILES
from methane.reference import audit
from methane.services.visits_demo import execute
from methane.services.visits_demo import fixture as visit_fixture

CASES = (
    "control-hold",
    "drive-power-loss",
    "charger-power-loss",
    "pump-power-loss",
    "remote-unavailable",
    "failed-replacement",
    "no-spares",
    "portable-abort",
    "interrupted-return",
    "no-remote-budget",
)


def fixture(case="control-hold"):
    if case not in CASES:
        raise ValueError("Unknown hardware fixture")
    c = visit_fixture("supplies")
    c = replace(
        c,
        scenario=replace(c.scenario, hours=36),
        field_operations=replace(
            c.field_operations,
            cleaner_enabled=True,
            cleaning_kits=6,
            service_kits=2,
            initial_soiling_fraction=0.1,
            repair_success_probability=0 if case == "failed-replacement" else 1,
        ),
        service_system=replace(
            c.service_system,
            cleaning_model="section-optical/1",
            equipment_recovery_enabled=True,
            visit_bundling_enabled=False,
            calibration_kits=2,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
            remote_shift_duration_hours=24,
            remote_hours_per_period=0 if case == "no-remote-budget" else 8,
            remote_assistance_enabled=case != "remote-unavailable",
            hardware_spares=0 if case == "no-spares" else 2,
        ),
        faults=FaultPolicy(
            service_fault_start_hour=1,
            cleaner_service_fault="control-hold"
            if case in ("control-hold", "remote-unavailable", "no-remote-budget")
            else "drive-power-loss"
            if case in ("drive-power-loss", "failed-replacement", "no-spares")
            else "none",
            dock_service_fault="charger-power-loss" if case == "charger-power-loss" else "none",
            portable_service_fault="pump-power-loss" if case == "pump-power-loss" else "none",
        ),
    )
    if case in ("pump-power-loss", "portable-abort"):
        c = replace(
            c,
            field_operations=replace(
                c.field_operations,
                cleaner_enabled=False,
                mission_failure_probability=1 if case == "portable-abort" else 0,
            ),
            service_system=replace(c.service_system, portable_cleaner="wet"),
        )
    if case == "interrupted-return":
        c = replace(
            c,
            faults=replace(
                c.faults, service_fault_start_hour=7, cleaner_service_fault="drive-power-loss"
            ),
            field_operations=replace(c.field_operations, mission_failure_probability=1),
            service_system=replace(c.service_system, travel_hours=1.5),
        )
    return c


__all__ = ["CASES", "fixture", "execute"]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/hardware"))
    base = parser.parse_args().directory
    base.mkdir(parents=True, exist_ok=True)
    summary = []
    lines = [
        "# The maintenance system also needs maintenance",
        "",
        "Ten saved 36-hour constant-power workflow cases use the same local supervisor and Greedy production dispatch. All rates, access and prepared function tests are illustrative assumptions. These are mechanism cases, not an empirical reliability result or a published service-value Study.",
        "",
        "| Case | Site visits | Remote hours | Replaced modules | Ending recovery state | Independent check |",
        "|---|---:|---:|---:|---|---|",
    ]
    for name in CASES:
        result = execute(fixture(name))
        checked = audit(result)
        path = save(result, base)
        make(result, base / (name + "-reproduction.zip"))
        (base / (name + "-playback.html")).write_text(playback(result, LOADED_FILES))
        (base / (name + "-audit.json")).write_text(json.dumps(checked, indent=2) + "\n")
        rows = result["records"]["Greedy"]
        services = [r["field_operations"] for r in rows]
        state = services[-1]["state"]
        counts = {}
        for row in services:
            for target, value in row["hardware_modules_used"].items():
                counts[target] = counts.get(target, 0) + value
        item = dict(
            case=name,
            run_id=result["run_id"],
            archive=path.name,
            status=result["status"],
            failures=result["failures"],
            audit_passed=checked["passed"],
            site_visits=sum(r["human_visits"] for r in services),
            remote_hours=sum(r["remote_hours"] for r in services),
            crew_hours=sum(r["crew_committed_hours"] for r in services),
            modules=counts,
            ending_plant=rows[-1]["state"],
            ending_services=state,
            unresolved=[
                q["id"]
                for q in state["orders"]
                if q["status"] not in ("completed", "verified", "cancelled")
            ],
            costs=reprice(result)["controllers"]["Greedy"][-1],
        )
        summary.append(item)
        recovery = (
            ", ".join(
                e["target"] + ": " + e["state"] for e in state["support"]["equipment"]["incidents"]
            )
            or "No incident observed"
        )
        lines.append(
            f"| [{name}]({name}-playback.html) | {item['site_visits']} | {item['remote_hours']:.2f} | {sum(counts.values())} | {recovery} | {'Passed' if checked['passed'] else 'Failed'} |"
        )
    lines += [
        "",
        "A mobile control hold permits release, a separate probe and a guided return. An open drive power stage survives the same release attempt and needs retrieval plus a compatible module. Its failed release remains unverified after the later successful replacement.",
        "",
        "A failed charger contributes no charging energy. A portable pump failure leaves its vehicle mobile: the existing operator can pack and return the tool, followed by a function test and compatible replacement. Packing creates no additional departure callout. Interrupted treatment remains in the surface and consumable ledgers.",
        "",
        "The interrupted-return case introduces drive-power loss during a guided journey. Later retrieval uses the new stopping point, and its return receipt links both interrupted work records. Unavailable spares, failed replacements and absent remote budgets retain their unresolved work. No procedure silently certifies readiness.",
        "",
        "Typed modules and existing unpriced support quantities require the full stage-3 economic assumptions. Physical production, ending inventories, original procedure/test links, failed attempts and cancellations remain available in each archive. These cases do not establish annual economic value, navigation fidelity or universal autonomous recovery.",
    ]
    (base / "cases.json").write_text(json.dumps(summary, indent=2) + "\n")
    (base / "report.md").write_text("\n".join(lines) + "\n")
    print(base / "report.md")
    if not all(r["audit_passed"] for r in summary):
        raise SystemExit("A hardware example failed independent verification")


if __name__ == "__main__":
    main()
