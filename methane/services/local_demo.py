"""Saved local-policy/interface examples; comparative evidence lives in Studies."""

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
from methane.service_economics import illustrative
from methane.services.configuration import ServiceSystem
from methane.services.inspection_demo import execute as inspection_run
from methane.services.inspection_demo import fixture as inspection_config
from methane.simulation import run
from methane.weather import synthetic

CASES = ("periodic", "partial", "prepared", "enclosed")


def execute(case):
    if case not in CASES:
        raise ValueError("Unknown local service example")
    if case in ("prepared", "enclosed"):
        c = inspection_config("trip")
        prices = illustrative(c.costs)
        prices["assets"]["rover"]["access_eur"] = 1500 if case == "prepared" else 0
        c = replace(
            c,
            service_economics=prices,
            service_system=replace(
                c.service_system,
                inspector="mobile",
                support_model="logistics/1",
                inspection_interface="accessible-port"
                if case == "prepared"
                else "enclosed-contact",
            ),
        )
        return inspection_run(c)
    c = Config(
        scenario=Scenario(hours=18, horizon_hours=6, solver_seconds=0.05),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=FieldOperations(
            enabled=True,
            rover_enabled=False,
            reset_enabled=False,
            human_fallback=False,
            initial_soiling_fraction=0.12,
            soiling_per_day=0.02,
            mission_failure_probability=1 if case == "partial" else 0,
        ),
        service_system=ServiceSystem(
            inspector="none",
            support_model="logistics/1",
            retrieval_enabled=False,
            cleaning_model="section-optical/1",
            cleaning_policy="periodic",
            cleaning_period_hours=4,
            work_failure_fraction=0.3,
        ),
    )
    c = replace(c, service_economics=illustrative(c.costs))
    w = synthetic(c)
    for mapping in (w["truth"], w["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=1000, irradiance_wm2=1000, ambient_c=20)
    w["reference"] = (
        "Illustrative constant 1,000 W/m² and 20°C local-cleaning mechanism example. Not measured weather or an annual value study."
    )
    return run(c, weather=w, strategies=["Greedy"])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--directory", type=Path, default=Path("build/services/local-policy/checked")
    )
    base = parser.parse_args().directory
    base.mkdir(parents=True, exist_ok=True)
    index = []
    for case in CASES:
        r = execute(case)
        a = audit(r)
        path = save(r, base)
        (base / (case + "-audit.json")).write_text(json.dumps(a, indent=2) + "\n")
        (base / (case + "-playback.html")).write_text(playback(r, LOADED_FILES))
        make(r, base / (case + "-reproduction.zip"))
        item = dict(
            case=case,
            archive=path.name,
            run_id=r["run_id"],
            status=r["status"],
            passed=a["passed"],
            checks=len(a["checks"]),
            failures=a["failures"],
            source=r["provenance"]["source"]["content_hash"],
            outcomes=r["metrics"]["Greedy"]["service_outcomes"],
        )
        index.append(item)
        print(json.dumps(item), flush=True)
    (base / "examples.json").write_text(json.dumps(index, indent=2) + "\n")
    if not all(r["status"] == "complete" and r["passed"] for r in index):
        raise SystemExit("Failed example; evidence retained")


if __name__ == "__main__":
    main()
