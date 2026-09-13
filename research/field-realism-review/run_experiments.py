"""Execute the preregistered realism stress cases without editing production models.

Run with the project environment from the repository root. A second invocation
reuses only content-checked finished cases, never overwrites their archives.
These are conditional challenge cases, not sampled European field performance.
"""

import argparse
import copy
import gzip
import hashlib
import json
import sys
import time
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT.parent.parent))

from methane.config import Config, Plant, Scenario, Sensors, WeatherConfig
from methane.costing import allocation
from methane.evidence import save
from methane.faults import FaultPolicy
from methane.field_operations import FieldOperations
from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE, digest
from methane.reference import audit
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.weather import synthetic


def frozen(path, value):
    text = json.dumps(value, indent=2, allow_nan=False) + "\n"
    if path.exists():
        if path.read_text() != text:
            raise ValueError(f"Existing evidence differs: {path}")
    else:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)


def cases(protocol):
    for seed in protocol["seeds"]:
        for power in protocol["cleaning"]["available_unsoiled_dc_kw"]:
            for soil in protocol["cleaning"]["initial_loose_fraction"]:
                for arm in protocol["cleaning"]["arms"]:
                    yield dict(family="cleaning", seed=seed, power=power, soil=soil, arm=arm)
        for condition in protocol["recovery"]["conditions"]:
            for arm in protocol["recovery"]["arms"]:
                yield dict(family="recovery", seed=seed, power=650, condition=condition, arm=arm)


def inputs(case, protocol):
    cleaning = case["family"] == "cleaning"
    arm = case["arm"]
    field = FieldOperations(
        enabled=True,
        cleaner_enabled=cleaning and arm == "condition-cleaner",
        rover_enabled=not cleaning and arm == "mobile-assisted",
        reset_enabled=not cleaning and arm in ("fixed-assisted", "mobile-assisted")
        and case["condition"] != "reset-unavailable",
        human_fallback=(cleaning and arm == "portable-wet") or (not cleaning and arm != "no-service"),
        initial_soiling_fraction=case.get("soil", 0), soiling_per_day=0,
        human_lead_hours=1, human_work_hours=2,
    )
    options = ServiceSystem(
        inspector="none" if cleaning or arm in ("no-service", "human-only") else
        "fixed" if arm == "fixed-assisted" else "mobile",
        inspection_model="referenced-contact/1", inspection_interface="accessible-port",
        cleaning_model="section-optical/1", initial_adhered_fraction=0,
        support_model="logistics/1", crew_return_enabled=True,
        crew_shift_duration_hours=24, crew_hours_per_period=24,
        crew_available=case.get("condition") != "crew-unavailable",
        crew_response_lead_hours=2, crew_travel_hours=1,
        portable_cleaner="wet" if arm == "portable-wet" else "none",
        portable_adhered_threshold=protocol.get('portable_adhered_threshold',0), cleaning_policy="condition" if cleaning else "off",
        portable_water_capacity_l=4000, portable_water_initial_l=4000,
        dock_standby_kw=0.05,
        outcome_randomness="target-action-request/1",
    )
    c = Config(
        plant=Plant(initial_soc=0.5),
        scenario=Scenario(hours=protocol["hours"], horizon_hours=protocol["horizon_hours"],
                          seed=case["seed"], fault_start_hour=6,
                          capacity_fraction=1 if cleaning else 0.5, solver_seconds=0.05),
        sensors=Sensors(noise_fraction=0.02),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=field, service_system=options,
        faults=FaultPolicy(capacity_cause="equipment-damage" if case.get("condition") == "equipment-damage" else "resettable-trip"),
    )
    c = replace(c, service_economics=illustrative(c.costs, version=ACTIVITY_VERSION))
    weather = synthetic(c)
    for mapping in (weather["truth"], weather["template"]):
        for sample in mapping.values():
            sample.update(pv_kw=case["power"], irradiance_wm2=case["power"], ambient_c=20)
    weather["reference"] = "Declared constant-input stress fixture; not measured European weather"
    weather["attribution"] = "Dispatch Lab realism boundary review; 20°C ambient, constant irradiance, no implied site frequency"
    return c, weather


def execute(directory, limit=None, protocol_path=ROOT / "protocol.json"):
    protocol = json.loads(protocol_path.read_text())
    frozen(directory / "protocol.json", protocol)
    frozen(directory / "source.json", LOADED_SOURCE)
    frozen(directory / "source-capsule.json", LOADED_CAPSULE)
    planned = []
    for case in cases(protocol):
        if any(case.get(k) != v for k,v in protocol.get('case_filter',{}).items()):
            continue
        c, weather = inputs(case, protocol)
        item = dict(case=case, config=asdict(c), weather=weather)
        item["case_id"] = digest(item)[:20]
        planned.append(item)
    frozen(directory / "cases.json", planned)
    count = len(planned)
    for index, packet in enumerate(planned):
        if limit is not None and index >= limit:
            return
        if (directory / 'CANCEL').exists():
            return
        key = packet["case_id"]
        target = directory / "cases" / key
        target.mkdir(parents=True, exist_ok=True)
        frozen(target / "input.json", packet)
        if (target / "summary.json").exists():
            old = json.loads((target / "summary.json").read_text())
            assert old["input_id"] == digest(packet)
            if old.get("archive"):
                assert hashlib.sha256((target / old["archive"]).read_bytes()).hexdigest() == old["archive_sha256"]
            print(json.dumps({"reused": key}), flush=True)
            continue
        started = time.perf_counter()
        summary = dict(case_id=key, case=packet["case"], input_id=digest(packet), source=LOADED_SOURCE["content_hash"])
        try:
            result = run(Config.from_dict(packet["config"]), weather=copy.deepcopy(packet["weather"]), strategies=["Greedy"])
            saved = save(result, target)
            reference = audit(result)
            frozen(target / "audit.json", reference)
            rows = result["records"]["Greedy"]
            cost = allocation(Plant(**result["config"]["plant"]), c=Config.from_dict(result["config"]).costs,
                              rows=rows, service_economics=packet["config"]["service_economics"])
            frozen(target / "cost.json", cost)
            end = rows[-1] if rows else {}
            summary.update(status=result["status"], failures=result["failures"], archive=saved.name,
                           archive_sha256=hashlib.sha256(saved.read_bytes()).hexdigest(),
                           audit_passed=reference["passed"], independent_checks=len(reference.get("checks", [])),
                           hours=len(rows), methane_kg=sum(r["applied"]["methane_kg"] for r in rows),
                           available_dc_kwh=sum(r["pv_kw"] for r in rows), curtailment_kwh=sum(r["curtailed_kwh"] for r in rows),
                           service_bus_kwh=sum(r["service_kw"] for r in rows),
                           treated_m2=sum(r["field_operations"].get("treated_area_m2", 0) for r in rows),
                           ending_plant=end.get("state"), ending_service=end.get("field_operations",{}).get("state"),
                           costs={k:v for k,v in cost.items() if k not in ("lineage", "field_operations")},
                           service_cost=cost.get("field_operations"), metrics=result["metrics"]["Greedy"])
        except Exception as exc:
            summary.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        summary["seconds"] = time.perf_counter() - started
        frozen(target / "summary.json", summary)
        (directory / "progress.json").write_text(json.dumps({"completed":index+1,"total":count,"case":key,"status":summary["status"]}))
        print(json.dumps({"completed":index+1,"total":count,"case":packet["case"],"status":summary["status"],"error":summary.get("error")}),flush=True)
    frozen(directory / "complete.json", {"case_ids":[p["case_id"] for p in planned],"source":LOADED_SOURCE["content_hash"],"protocol_id":digest(protocol)})


if __name__ == "__main__":
    parser=argparse.ArgumentParser();parser.add_argument("--directory",type=Path,default=ROOT/"experiments"/"primary")
    parser.add_argument("--limit",type=int)
    parser.add_argument("--protocol",type=Path,default=ROOT/'protocol.json')
    args=parser.parse_args()
    execute(args.directory, args.limit, args.protocol)
