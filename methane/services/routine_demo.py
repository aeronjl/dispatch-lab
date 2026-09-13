"""Reproducible routine-work and dock-energy mechanism examples, not a value study."""

import argparse
import json
from dataclasses import replace
from pathlib import Path

from methane.bundle import make, playback
from methane.config import Config, Scenario
from methane.evidence import save
from methane.field_operations import FieldOperations
from methane.provenance import LOADED_FILES
from methane.reference import audit
from methane.service_economics import illustrative
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.weather import synthetic

CASES = ("routine", "night-reserve", "unavailable-support")


def fixture(case="routine"):
    if case not in CASES:
        raise ValueError("Unknown routine-work teaching fixture")
    c = Config(
        scenario=Scenario(hours=24, horizon_hours=6, solver_seconds=0.05),
        field_operations=FieldOperations(
            enabled=True,
            rover_enabled=False,
            initial_soiling_fraction=0,
            soiling_per_day=0,
            mission_failure_probability=0,
        ),
        service_system=ServiceSystem(
            inspector="fixed",
            support_model="logistics/1",
            maintenance_enabled=True,
            maintenance_first_due_hour=1,
            maintenance_interval_hours=8,
            maintenance_work_hours=0.5,
            maintenance_kits=2,
            supplier_kits=4,
            delivery_batch_kits=2,
            crew_response_lead_hours=0,
            crew_travel_hours=0.25,
            visit_bundling_enabled=True,
            dock_standby_kw=0.25,
        ),
    )
    c = replace(c, service_economics=illustrative(c.costs))
    if case == "night-reserve":
        c = replace(
            c,
            scenario=replace(c.scenario, hours=12),
            plant=replace(c.plant, initial_soc=0.1),
            service_system=replace(c.service_system, dock_standby_kw=1),
        )
    elif case == "unavailable-support":
        c = replace(
            c, service_system=replace(c.service_system, crew_available=False, maintenance_kits=0)
        )
    return c


def execute(case):
    c = fixture(case)
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(
                pv_kw=0 if case == "night-reserve" else 1000,
                irradiance_wm2=0 if case == "night-reserve" else 1000,
                ambient_c=20,
            )
    return run(c, weather=weather, strategies=["Greedy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/routine"))
    base = parser.parse_args().directory
    base.mkdir(parents=True, exist_ok=True)
    index = []
    for case in CASES:
        result = execute(case)
        checked = audit(result)
        path = save(result, base)
        (base / (case + "-audit.json")).write_text(json.dumps(checked, indent=2) + "\n")
        (base / (case + "-playback.html")).write_text(playback(result, LOADED_FILES))
        make(result, base / (case + "-reproduction.zip"))
        rows = [r["field_operations"] for r in result["records"]["Greedy"]]
        index.append(
            dict(
                case=case,
                run_id=result["run_id"],
                archive=path.name,
                source=result["provenance"]["source"]["content_hash"],
                status=result["status"],
                checks=len(checked["checks"]),
                passed=checked["passed"],
                failures=checked["failures"],
                completed=sum(
                    e["kind"] == "routine-service" for r in rows for e in r["support_effects"]
                ),
                visits=sum(r["human_visits"] for r in rows),
                crew_hours=sum(r["crew_committed_hours"] for r in rows),
                standby_kwh=sum(r["standby"]["applied_kwh"] for r in rows),
                unserved_standby_kwh=sum(r["standby"]["unserved_kwh"] for r in rows),
                ending_schedule=rows[-1]["state"]["support"]["maintenance"],
                methane_kg=result["metrics"]["Greedy"]["methane_kg"],
            )
        )
        print(json.dumps(index[-1]), flush=True)
    (base / "examples.json").write_text(json.dumps(index, indent=2) + "\n")
    if not all(x["status"] == "complete" and x["passed"] for x in index):
        raise SystemExit("Example verification failed; original artifacts retained")


if __name__ == "__main__":
    main()
