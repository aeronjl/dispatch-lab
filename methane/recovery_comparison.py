"""Repeatable recovery qualification on matched seeds and European seasons.

Create a new immutable programme, run/resume its saved Studies, then publish a
new report revision. Historical windows use cached original weather envelopes;
missing inputs remain incomplete. No case is dropped because a policy fails.
"""

import argparse
import copy
import html
import json
import threading
import time
from dataclasses import replace
from pathlib import Path
from uuid import uuid4

from methane.autonomy import DEFAULT
from methane.autonomy_studies import ARMS
from methane.autonomy_studies import fixture as original_fixture
from methane.config import Config
from methane.duration_population import AUTONOMY_VERSION, default_model
from methane.faults import FaultPolicy
from methane.provenance import digest
from methane.recovery import LOOP_VERSION, RecoveryPolicy
from methane.services.controller import VERIFICATION_VERSION
from methane.studies import STORE, archive_for, create, entry_for, read_manifest, run_edition
from methane.uncertainty import VERSION as UNCERTAINTY_VERSION
from methane.uncertainty_studies import protocol

VERSION = "recovery-comparison-programme/1"
ROOT = Path(__file__).resolve().parents[1] / "research/recovery-comparison"
CONDITIONS = (
    "null",
    "normal-service",
    "persistent-damage",
    "failed-remedy",
    "interruption",
    "support-outage",
    "forecast-stress",
)
SITES = {
    "London": (51.5074, -0.1278, "Europe/London"),
    "Seville": (37.3891, -5.9845, "Europe/Madrid"),
    "Copenhagen": (55.6761, 12.5683, "Europe/Copenhagen"),
}


def fixture(condition, basis=None):
    c = Config.from_dict(basis) if basis else original_fixture()
    if c.service_system is None or c.service_policy is None:
        raise ValueError(
            "This qualification requires a configured service system and coordinated policy"
        )
    c = replace(
        c,
        scenario=replace(
            c.scenario,
            hours=48,
            horizon_hours=12,
            solver_seconds=0.25,
            fault_start_hour=2,
            capacity_fraction=0.25,
            variability=0.15,
        ),
        field_operations=replace(
            c.field_operations,
            cleaner_enabled=condition in ("normal-service", "interruption", "null"),
            rover_battery_kwh=10,
            cleaner_battery_kwh=10,
            human_lead_hours=1,
            service_kits=3,
            repair_success_probability=0.8,
        ),
        service_system=replace(
            c.service_system,
            visit_bundling_enabled=True,
            crew_response_lead_hours=0,
            crew_travel_hours=0.25,
            crew_shift_duration_hours=24,
            crew_hours_per_period=24,
        ),
        service_policy=replace(
            c.service_policy,
            version=VERIFICATION_VERSION,
            maximum_wait_hours=12,
            comparison_seconds=2,
            maximum_candidates=3,
        ),
        recovery_policy=RecoveryPolicy(version=LOOP_VERSION, maximum_wait_hours=12),
        faults=FaultPolicy(capacity_cause="equipment-damage"),
    )
    if condition in ("normal-service", "interruption", "null"):
        c = replace(c, scenario=replace(c.scenario, fault_start_hour=1000, capacity_fraction=1))
    if condition == "null":
        c = replace(
            c,
            scenario=replace(c.scenario, hours=12, variability=0, solver_seconds=2),
            sensors=replace(c.sensors, noise_fraction=0),
            field_operations=replace(
                c.field_operations, mission_failure_probability=0, repair_success_probability=1
            ),
        )
    if condition == "failed-remedy":
        c = replace(c, field_operations=replace(c.field_operations, repair_success_probability=0))
    if condition == "interruption":
        c = replace(
            c, field_operations=replace(c.field_operations, mission_failure_probability=0.7)
        )
    if condition == "forecast-stress":
        c = replace(c, scenario=replace(c.scenario, forecast_bias=0.5, variability=0.4))
    return c


def specification(c, condition, arm, seeds):
    if arm not in ARMS:
        raise ValueError("Unknown service policy arm")
    options = {
        **copy.deepcopy(DEFAULT),
        "mode": arm,
        "version": AUTONOMY_VERSION,
        "duration_model": default_model(),
    }
    factors = [1.25] * 6
    if condition == "null":
        factors = [1] * 6
        options = {**copy.deepcopy(DEFAULT), "mode": arm}
        options.update(
            duration_bounds={k: [1, 1] for k in options["duration_bounds"]},
            weather_factors=[1],
            weather_weights=[1],
            solar_relative_error=0,
            surface_absolute_error=0,
        )
    uncertainty = dict(
        schema_version=UNCERTAINTY_VERSION,
        seed=20260913,
        worlds=1,
        inner_seeds=list(seeds),
        design="factorial",
        autonomy=options,
        rationale="Matched declared conditions; no empirical occurrence probabilities. Fixed, adaptive and risk-aware arms use the same physical equipment and per-job event streams.",
        blocks=[
            dict(
                id="persistent-service-factors",
                paths=["service_system." + k + "_time_factor" for k in DEFAULT["duration_bounds"]],
                kind="values",
                rows=[factors],
                visibility="hidden",
                source="Illustrative within-support equipment challenge",
                rationale="Constant equipment factor per run; fresh bounded accepted-job variation is separate",
            )
        ],
    )
    if condition == "support-outage":
        uncertainty["support_events"] = [
            dict(
                channel="communications",
                start=12,
                end=20,
                available=False,
                source="Declared outage, unavailable to the controller until observed",
            )
        ]
    s = protocol(c.to_dict(), uncertainty)
    s.update(
        title=f"Recovery comparison · {condition} · {arm}",
        question="Does adaptation improve observed service recovery beyond numerical variation, and under which resource constraints?",
        comparison="One physical configuration per condition. Match by event seed across the three service-uncertainty modes. All arms use the economic MPC objective, the same budgets, original prices and finite service candidates.",
        policies={"MPC · economics": {"objective": "economics"}},
        baseline_controller="MPC · economics",
        candidate_controller="MPC · economics",
    )
    if c.weather.mode == "historical":
        s["weather_source_hours"] = 240
    return s


def create_programme(
    basis=None, *, seeds=(7, 17, 29), conditions=CONDITIONS, seasonal=True, null_repeats=2
):
    if not seeds or null_repeats < 2:
        raise ValueError("Keep matched event seeds and at least two null numerical repetitions")
    directory = ROOT / uuid4().hex
    directory.mkdir(parents=True)
    p = dict(
        version=VERSION,
        created_at=time.time(),
        basis=basis,
        seeds=list(seeds),
        entries=[],
        protocol_scope="48-hour service exposure and seasonal windows; 12-hour null checks with two numerical repeats. Three fixed event seeds. These are controlled sensitivity cases, not annual costs, empirical event rates or field calibration. Failed, missing-data and unresolved cases remain in every report.",
        weather_scope="Nine European 2026 windows start on 10 January, April and July. Use the first 48 UTC hours of a saved ten-day ERA5/archived ECMWF envelope, retaining original publication boundaries and raw attribution. ERA5 is reanalysis, not site measurements.",
    )
    designs = [
        (condition, fixture(condition, basis), r)
        for condition in conditions
        for r in range(1, (null_repeats if condition == "null" else 1) + 1)
    ]
    if seasonal:
        for site, (lat, lon, zone) in SITES.items():
            for month in (1, 4, 7):
                c = fixture("persistent-damage", basis)
                c = replace(
                    c,
                    weather=replace(
                        c.weather,
                        mode="historical",
                        latitude=lat,
                        longitude=lon,
                        timezone=zone,
                        start=f"2026-{month:02}-10",
                        offline=True,
                    ),
                )
                designs.append((f"{site}-{month:02}", c, 1))
    for condition, c, repeat in designs:
        for arm in ARMS:
            spec = specification(c, condition, arm, seeds)
            m = create(basis=c.to_dict(), specification=spec)
            p["entries"].append(
                dict(condition=condition, arm=arm, repeat=repeat, edition_id=m["edition_id"])
            )
            print("Prepared", condition, arm, m["edition_id"], flush=True)
            (directory / "programme.json").write_text(json.dumps(p, indent=2) + "\n")
    return directory


def run_programme(directory):
    p = json.loads((directory / "programme.json").read_text())
    for i, entry in enumerate(p["entries"]):
        if (directory / "cancel").exists():
            break
        print(f"{i + 1}/{len(p['entries'])} {entry['condition']} {entry['arm']}", flush=True)
        started = time.perf_counter()
        finished = threading.Event()
        cancel_path = STORE / entry["edition_id"] / "cancel"
        cancel_path.unlink(missing_ok=True)

        def cancellation(finished=finished, cancel_path=cancel_path):
            while not finished.wait(0.25):
                if (directory / "cancel").exists():
                    cancel_path.touch()
                    return

        monitor = threading.Thread(target=cancellation, daemon=True)
        monitor.start()
        try:
            run_edition(entry["edition_id"])
        finally:
            finished.set()
            monitor.join()
        print(f"Completed attempt in {time.perf_counter() - started:.1f}s", flush=True)
    return report(directory)


def report(directory):
    p = json.loads((directory / "programme.json").read_text())
    records = []
    null_traces = {}
    for entry in p["entries"]:
        manifest = read_manifest(entry["edition_id"])
        for case in manifest["cases"]:
            record = {
                **entry,
                "seed": case["seed"],
                "case_id": case["case_id"],
                "source_hash": manifest["source_hash"],
                "weather_hash": case.get("weather_hash"),
                "input_status": case.get("input_status"),
                "physical_hash": digest(case["config"]),
            }
            try:
                attempt = entry_for(entry["edition_id"], case["case_id"])
            except ValueError as exc:
                attempt = dict(status="pending", error=str(exc))
            record.update(
                status=attempt["status"],
                error=attempt.get("error") or case.get("input_error"),
                metrics=attempt.get("metrics"),
                audit=attempt.get("independent_audit"),
            )
            if attempt.get("archive"):
                r = archive_for(entry["edition_id"], attempt)
                name = next(iter(r["records"]))
                rows = r["records"][name]
                operations = [row["field_operations"] for row in rows]
                trace = [{k: row[k] for k in ("requested", "applied", "state")} for row in rows]
                if entry["condition"] == "null":
                    null_traces[(entry["edition_id"], case["case_id"])] = trace
                decisions = [row["decision"].get("service_control", {}) for row in rows]
                record.update(
                    run_id=r["run_id"],
                    archive=str(STORE / entry["edition_id"] / attempt["archive"]),
                    trace_hash=digest(trace),
                    methane_kg=sum(row["applied"]["methane_kg"] for row in rows),
                    ending=rows[-1]["state"] if rows else None,
                    work_orders=operations[-1]["state"]["orders"] if operations else [],
                    mission_counts={
                        kind: sum(
                            m["order"]["action"] == kind
                            for f in operations
                            for m in f["new_missions"]
                        )
                        for kind in sorted(
                            {m["order"]["action"] for f in operations for m in f["new_missions"]}
                        )
                    },
                    fallback_intervals=sum(bool(d.get("fallback_used")) for d in decisions),
                    canonical_candidates=sum(
                        c.get("evaluation", {}).get("uncertainty_planning", {}).get("status")
                        == "canonical-nominal"
                        for d in decisions
                        for c in d.get("candidates", [])
                    ),
                    conditional_returns=sum(
                        bool(c.get("evaluation", {}).get("conditional_returns"))
                        for d in decisions
                        for c in d.get("candidates", [])
                    ),
                    verification=[
                        dict(
                            hour=row["hour"],
                            status=row["decision"]["recovery_planning"]["status"],
                            loop=row["decision"]["recovery_planning"].get("verification_loop"),
                        )
                        for row in rows
                        if row["decision"].get("recovery_planning", {}).get("verification_loop")
                    ],
                )
                record["solver_statuses"] = {}
                for d in decisions:
                    for candidate in d.get("candidates", []):
                        ev = candidate.get("evaluation", {})
                        status = ev.get("state", candidate.get("status", "unknown"))
                        record["solver_statuses"][status] = (
                            record["solver_statuses"].get(status, 0) + 1
                        )
            records.append(record)
    null = [r for r in records if r["condition"] == "null"]
    matching = []
    for condition in sorted({r["condition"] for r in records}):
        for seed in p["seeds"]:
            group = [r for r in records if r["condition"] == condition and r["seed"] == seed]
            matching.append(
                dict(
                    condition=condition,
                    seed=seed,
                    physical_inputs_match=len({r["physical_hash"] for r in group}) == 1,
                    weather_inputs_match=len({r["weather_hash"] for r in group}) == 1,
                    complete=all(r["status"] == "complete" for r in group),
                )
            )
    output = dict(
        version=VERSION,
        programme=p,
        records=records,
        matching=matching,
        null_trace_identical_by_seed={
            str(seed): len({r.get("trace_hash") for r in null if r["seed"] == seed}) == 1
            and all(r["status"] == "complete" for r in null if r["seed"] == seed)
            for seed in p["seeds"]
        },
        null_numerical_spread={
            str(seed): trace_spread(
                [
                    null_traces[(r["edition_id"], r["case_id"])]
                    for r in null
                    if r["seed"] == seed and (r["edition_id"], r["case_id"]) in null_traces
                ]
            )
            for seed in p["seeds"]
        },
    )
    revision = uuid4().hex
    (directory / "reports").mkdir(exist_ok=True)
    path = directory / "reports" / revision
    path.with_suffix(".json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    lines = []
    for r in records:
        jobs = (
            ", ".join(k + ": " + str(v) for k, v in r.get("mission_counts", {}).items())
            or "None recorded"
        )
        lines.append(
            "<tr>"
            + "".join(
                "<td>" + html.escape(str(v)) + "</td>"
                for v in (
                    r["condition"],
                    r["arm"],
                    r["seed"],
                    r["repeat"],
                    r["status"],
                    round(r["methane_kg"], 2) if "methane_kg" in r else "—",
                    jobs,
                    r.get("fallback_intervals", "—"),
                    r.get("error") or "",
                )
            )
            + "</tr>"
        )
    body = """<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>Recovery comparison</title><style>@font-face{font-family:Departure;src:url(../../../../assets/fonts/DepartureMono-Regular.woff2)}body{background:#202020;color:#ffad43;font:16px/1.6 Departure,monospace;margin:4vh auto;max-width:1300px;padding:24px}a{color:inherit}table{border-collapse:collapse;font-size:12px}td,th{padding:8px;border-bottom:1px solid #795424;text-align:left}.scroll{overflow:auto}p{max-width:90ch}</style><h1>Recovery under uncertain work and weather</h1>"""
    body += (
        "<p>"
        + html.escape(p["protocol_scope"])
        + "</p><p>"
        + html.escape(p["weather_scope"])
        + "</p><p>Read physical matches, unfinished work and numerical limitations before interpreting an advantage. Every case retains its original Study report, source and operands. No ranking or overall trust score is inferred.</p>"
    )
    body += (
        "<p>Null traces identical within each seed across modes and numerical repeats: "
        + html.escape(str(output["null_trace_identical_by_seed"]))
        + '</p><div class="scroll"><table><tr><th>Condition</th><th>Arm</th><th>Seed</th><th>Repeat</th><th>Status</th><th>Methane / kg</th><th>Accepted missions</th><th>Fallback intervals</th><th>Gap</th></tr>'
        + "".join(lines)
        + "</table></div>"
    )
    body += f'<p><a href="{revision}.json">Complete metrics, inventories, verification episodes and evidence identities</a> · <a href="../programme.json">Frozen programme</a></p>'
    path.with_suffix(".html").write_text(body)
    return path.with_suffix(".html")


def calibrate(directory):
    """Separate clock-observation exercise; never fit on comparison outcomes."""
    from methane.duration_calibration import VERSION as DATA_VERSION
    from methane.duration_calibration import fit
    from methane.evidence import save
    from methane.reference import audit
    from methane.simulation import run
    from methane.uncertainty import resolve
    from methane.weather import synthetic

    observations, sources = [], []
    for seed in (7, 17, 29):
        c = fixture("normal-service")
        c = replace(
            c,
            scenario=replace(c.scenario, hours=240, seed=seed),
            field_operations=replace(
                c.field_operations,
                soiling_per_day=0.04,
                mission_failure_probability=0.1,
                cleaning_kits=24,
            ),
            service_policy=None,
            recovery_policy=None,
        )
        u = specification(c, "normal-service", "adaptive", (seed,))["uncertainty"]
        world = resolve(u, c.to_dict())[0]
        actual = Config.from_dict(world["config"])
        r = run(actual, weather=synthetic(actual), strategies=["Greedy"], uncertainty=world)
        checked = audit(r)
        path = save(r, STORE.parent / "duration-calibration" / directory.name)
        sources.append(
            dict(
                run_id=r["run_id"],
                archive=str(path),
                status=r["status"],
                independent_check_passed=checked["passed"],
                source_hash=r["provenance"]["source"]["content_hash"],
            )
        )
        if r["status"] != "complete" or not checked["passed"]:
            continue
        # Only observed packets are copied. No private clock, draw or effect
        # value enters this dataset. Run prefixes keep independent equipment
        # episodes and accepted job identities separate.
        rows = r["records"]["Greedy"]
        for row in rows:
            for raw in row["field_operations"].get("duration_observations", []):
                if raw["group"] is None:
                    continue
                item = copy.deepcopy(raw)
                for key in ("id", "order_id", "asset_id"):
                    item[key] = r["run_id"] + "/" + item[key]
                observations.append(item)
        print("Clock observation run", seed, r["status"], checked["passed"], flush=True)
    candidates = []
    for width in (0.1, 0.2, 0.3):
        m = default_model()
        for group in m["groups"].values():
            group["job_multiplier_bounds"] = [1 - width, 1 + width]
        m["source"] = (
            f"Predeclared illustrative uniform job-width candidate ±{width:g}; persistent grid held fixed"
        )
        candidates.append(m)
    data = dict(
        version=DATA_VERSION,
        source=dict(
            id="separate-simulated-clock-observations",
            kind="simulated-observation",
            reference=digest(sources),
        ),
        observations=observations,
    )
    protocol = dict(
        dataset=data,
        candidates=candidates,
        cutoff=120,
        bounds=copy.deepcopy(DEFAULT["duration_bounds"]),
    )
    edition = uuid4().hex
    folder = directory / "calibration" / edition
    folder.mkdir(parents=True)
    (folder / "protocol.json").write_text(json.dumps(protocol, indent=2, allow_nan=False) + "\n")
    try:
        output = fit(data, candidates, 120, protocol["bounds"])
    except ValueError as exc:
        output = dict(status="incomplete", error=str(exc), dataset_id=digest(data))
    output["source_runs"] = sources
    (folder / "result.json").write_text(json.dumps(output, indent=2, allow_nan=False) + "\n")
    return folder / "result.json"


def trace_spread(traces):
    """Maximum across all mode/repeat pairs, separated by operand and unit."""
    if not traces:
        return dict(status="missing", traces=0)
    if len({len(t) for t in traces}) != 1:
        return dict(status="incomplete", traces=len(traces), lengths=[len(t) for t in traces])
    spread = {}
    for hour in range(len(traces[0])):
        for category, values in traces[0][hour].items():
            for key in values:
                numbers = [float(t[hour][category][key]) for t in traces]
                path = category + "." + key
                difference = max(numbers) - min(numbers)
                if path not in spread or difference > spread[path]["maximum_difference"]:
                    spread[path] = dict(maximum_difference=difference, hour=hour)
    return dict(status="compared", traces=len(traces), operands=spread)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["create", "run", "report", "calibrate"])
    parser.add_argument("directory", type=Path, nargs="?")
    parser.add_argument("--basis", type=Path)
    parser.add_argument("--pilot", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        print(
            create_programme(
                json.loads(args.basis.read_text()) if args.basis else None,
                **dict(seeds=(7,), conditions=("null", "persistent-damage"), seasonal=False)
                if args.pilot
                else {},
            )
        )
    elif args.command == "run":
        print(run_programme(args.directory))
    elif args.command == "calibrate":
        print(calibrate(args.directory))
    else:
        print(report(args.directory))


if __name__ == "__main__":
    main()
