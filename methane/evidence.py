"""Restartable experiment matrix, thermal sensitivities and versioned archives."""

import argparse
import csv
import gzip
import hashlib
import io
import json
import os
import signal
import tempfile
import threading
import zipfile
from contextlib import contextmanager
from dataclasses import replace
from pathlib import Path

from methane.config import Config
from methane.costing import reprice
from methane.jobs import isolated_run
from methane.provenance import digest, experiment_identity, manifest, verify
from methane.simulation import run
from methane.weather import IncompleteWeather, prepare

RUNS = Path(__file__).resolve().parent.parent / "runs" / "methane-v2"


@contextmanager
def staging(path):
    """Prepare a complete file without replacing any previously published artifact."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix="." + path.name, delete=False) as f:
        temporary = Path(f.name)
    try:
        yield temporary
    finally:
        temporary.unlink(missing_ok=True)


def publish_completed(temporary, path):
    """Atomic create, exact-byte reuse, or a distinct content-addressed sibling.

    A stable physical run identifier is not the identity of a sealed recording.
    Hard-link creation keeps concurrent readers from seeing a partial artifact
    and cannot overwrite an existing file. Both files are on the same filesystem.
    """
    temporary, path = Path(temporary), Path(path)

    def sha(file):
        with file.open("rb") as stream:
            return hashlib.file_digest(stream, "sha256").hexdigest()

    identity = sha(temporary)
    candidates = (path, path.with_name(path.stem[:120] + "-" + identity + path.suffix))
    for candidate in candidates:
        try:
            os.link(temporary, candidate)
            return candidate
        except FileExistsError:
            if sha(candidate) == identity:
                return candidate
    raise FileExistsError("Different content occupies both artifact paths; previous files retained")


def recording_key(result):
    """Legacy storage gets a current content key, never an invented original seal."""
    return (
        result["integrity_sha256"]
        if result.get("schema_version") == "dispatch-lab/methane/3"
        else digest(result)
    )


def save(result, root=RUNS):
    verify(result)
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{result['run_id']}-{recording_key(result)}.json.gz"
    # Encode once in C rather than sending millions of tiny encoder fragments
    # through TextIOWrapper and gzip. Parsed content and its integrity seal are unchanged.
    data = json.dumps(result, allow_nan=False).encode("utf-8")
    with staging(path) as temporary:
        temporary.write_bytes(gzip.compress(data, compresslevel=6, mtime=0))
        return publish_completed(temporary, path)


def load(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        result = json.load(f)
    if result.get("schema_version") not in ("dispatch-lab/methane/2", "dispatch-lab/methane/3"):
        raise ValueError("Expected methane schema 2 or 3; legacy hydrogen retains its own reader.")
    return verify(result)


_SAVED = object()


def export(result, report_costs=None, *, service_economics=_SAVED):
    save(result)
    prices = reprice(
        result,
        report_costs,
        **({} if service_economics is _SAVED else {"service_economics": service_economics}),
    )
    path = RUNS / f"{result['run_id']}-{recording_key(result)}-report-{digest(prices)}.zip"
    with (
        staging(path) as temporary,
        zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as z,
    ):
        z.writestr(
            "methane-run-v3.json"
            if result["schema_version"].endswith("/3")
            else "methane-run-v2.json",
            json.dumps(result, allow_nan=False),
        )
        from methane.taxonomy import report as taxonomy_report

        z.writestr("site-catalogue.html", taxonomy_report(result))
        if result.get("taxonomy"):
            z.writestr("site-catalogue.json", json.dumps(result["taxonomy"], allow_nan=False))
        z.writestr("economics-v2.json", json.dumps(prices, allow_nan=False))
        if prices.get("service_economics") is not None:
            from methane.provenance import LOADED_CAPSULE
            from methane.service_economics import html_report, reprice_run

            services = reprice_run(result, prices["service_economics"], report_costs)
            z.writestr("service-economics.json", json.dumps(services, allow_nan=False))
            z.writestr("service-economics.html", html_report(services))
            z.writestr("service-pricing-source.json", json.dumps(LOADED_CAPSULE))
        table = io.StringIO()
        fields = [
            "controller",
            "hour",
            "time_utc",
            "methane_kg",
            "h2_produced_kg",
            "h2_inventory_kg",
            "co2_inventory_kg",
            "battery_kwh",
            "reactor_temperature_c",
            "curtailed_kwh",
            "co2_rejected_kg",
            "forced_trip",
            "diagnosis",
            "solver_status",
        ]
        writer = csv.DictWriter(table, fields)
        writer.writeheader()
        for name, rows in result["records"].items():
            for r in rows:
                writer.writerow(
                    dict(
                        zip(
                            fields,
                            [
                                name,
                                r["hour"],
                                r["time"],
                                r["applied"]["methane_kg"],
                                r["h2_produced_kg"],
                                r["state"]["h2_kg"],
                                r["state"]["co2_kg"],
                                r["state"]["battery_kwh"],
                                r["state"]["temperature_c"],
                                r["curtailed_kwh"],
                                r["co2_rejected_kg"],
                                r["forced_trip"],
                                r["diagnosis_after"]["status"],
                                r["decision"]["plan"]["solver"]["status"],
                            ],
                            strict=True,
                        )
                    )
                )
        z.writestr("hourly-methane-v2.csv", table.getvalue())
        if result.get("field_operations_model"):
            z.writestr(
                "field-operations-v1.json",
                json.dumps(
                    {
                        "model": result["field_operations_model"],
                        "records": {
                            name: [
                                {"hour": r["hour"], **r["field_operations"]}
                                for r in rows
                                if "field_operations" in r
                            ]
                            for name, rows in result["records"].items()
                        },
                        "retrospective_truth_by_controller": result.get(
                            "retrospective_truth_by_controller", {}
                        ),
                    },
                    allow_nan=False,
                ),
            )
        for snapshot in result["weather"]["snapshots"]:
            z.writestr(f"weather/{snapshot['id']}.json", json.dumps(snapshot))
        z.writestr(
            "README.txt",
            "Dispatch Lab v0.2 hourly scheduling sandbox. All costs/plant parameters illustrative.\nJSON preserves forecasts, decisions, raw weather, asset IDs and frozen decision costs.\nCSV methane_kg is interval CH4 output; h2_produced_kg is separate upstream production.\nERA5 is reanalysis; saved live forecasts plus stress are scenarios, not observations.\nReplay: python -m methane.evidence --replay archive.zip\n",
        )
        z.close()
        return str(publish_completed(temporary, path))


def cases(base=None, suite="synthetic"):
    c = base or Config()
    scenarios = {
        "normal": {},
        "forecast overestimate": {"forecast_bias": 0.35},
        "capacity loss": {"capacity_fraction": 0.5},
        "flow sensor bias": {"flow_bias_fraction": 0.4},
        "combined forecast and fault": {"forecast_bias": 0.35, "capacity_fraction": 0.5},
        "delayed CO2": {"delivery_delay_hours": 24},
    }
    if suite in ("synthetic", "all", "ablation"):
        for label, settings in scenarios.items():
            for seed in (7, 19, 42):
                cfg = replace(
                    c,
                    scenario=replace(
                        c.scenario,
                        hours=72,
                        seed=seed,
                        forecast_bias=0,
                        capacity_fraction=1,
                        flow_bias_fraction=0,
                        delivery_delay_hours=0,
                    ),
                    weather=replace(c.weather, mode="synthetic"),
                )
                cfg = replace(cfg, scenario=replace(cfg.scenario, **settings))
                if suite == "ablation":
                    cfg = replace(cfg, sensors=replace(cfg.sensors, enabled=False))
                yield (
                    f"{label} / seed {seed}" + (" / diagnosis OFF" if suite == "ablation" else ""),
                    cfg,
                )
    if suite in ("historical", "all"):
        for name, lat, lon, zone in (
            ("London", 51.5074, -0.1278, "Europe/London"),
            ("Seville", 37.3891, -5.9845, "Europe/Madrid"),
            ("Copenhagen", 55.6761, 12.5683, "Europe/Copenhagen"),
        ):
            for start in ("2026-01-10", "2026-04-10", "2026-07-10"):
                yield (
                    f"{name} / {start}",
                    replace(
                        c,
                        scenario=replace(
                            c.scenario,
                            hours=240,
                            seed=7,
                            capacity_fraction=1,
                            flow_bias_fraction=0,
                            forecast_bias=0,
                            delivery_delay_hours=0,
                        ),
                        weather=replace(
                            c.weather,
                            mode="historical",
                            latitude=lat,
                            longitude=lon,
                            timezone=zone,
                            start=start,
                        ),
                    ),
                )
    if suite == "thermal":
        for field in ("thermal_capacity_kwh_per_k", "heat_loss_kw_per_k"):
            for factor in (0.5, 1, 1.5):
                yield (
                    f"{field} × {factor}",
                    replace(c, plant=replace(c.plant, **{field: getattr(c.plant, field) * factor})),
                )


def batch(base=None, suite="synthetic", cancel=None, progress=None):
    cancel = cancel or threading.Event()
    specs = list(cases(base, suite))
    output = []
    root = RUNS / "batches"
    root.mkdir(parents=True, exist_ok=True)
    for i, (label, config) in enumerate(specs):
        if cancel.is_set():
            output.append({"case": label, "status": "cancelled", "config": config.to_dict()})
            yield output
            continue
        try:
            weather = prepare(config)
            expected = manifest(config, weather, ("Greedy", "MPC · methane", "MPC · economics"))
            expected["solver"]["threads"] = 1
            key = experiment_identity(expected)
        except IncompleteWeather as exc:
            output.append(
                {
                    "case": label,
                    "status": "incomplete-data",
                    "error": str(exc),
                    "config": config.to_dict(),
                }
            )
            yield output
            continue
        index = root / f"{key}.json"
        if cancel.is_set():
            output.append({"case": label, "status": "cancelled", "config": config.to_dict()})
            continue
        previous = json.loads(index.read_text()) if index.exists() else None
        if previous:
            entry = previous
            # Only complete cached runs are reusable. Missing/incomplete work is retried.
            if entry["status"] == "complete" and Path(entry["archive"]).exists():
                try:
                    cached = load(entry["archive"])
                    reusable = (
                        cached.get("experiment_id") == key and cached.get("status") == "complete"
                    )
                except (ValueError, OSError, KeyError):
                    reusable = False
                if not reusable:
                    previous = None
            else:
                reusable = False
            if reusable:
                output.append({**entry, "case": label, "reused": True})
                yield output
                continue
        try:
            result = isolated_run(config, weather, cancelled=cancel.is_set, progress=progress)
            archive = save(result)
            entry = {
                "case": label,
                "status": result["status"],
                "run_id": result["run_id"],
                "archive": str(archive),
                "metrics": result["metrics"],
                "failures": result.get("failures", {}),
                "config": config.to_dict(),
            }
        except IncompleteWeather as exc:
            entry = {
                "case": label,
                "status": "incomplete-data",
                "error": str(exc),
                "config": config.to_dict(),
            }
        except (
            Exception
        ) as exc:  # Preserve failed experiment evidence; never count it as a success.
            entry = {
                "case": label,
                "status": "failed",
                "error": f"{type(exc).__name__}: {exc}",
                "config": config.to_dict(),
            }
        if previous and previous["status"] != "complete":
            entry["attempts"] = previous.get("attempts", []) + [
                {"status": previous["status"], "error": previous.get("error")}
            ]
        index.write_text(json.dumps(entry, indent=2, allow_nan=False))
        output.append(entry)
        if progress:
            progress((i + 1) / len(specs), desc=f"{i + 1}/{len(specs)} cases complete")
        yield output
    report = root / f"report-{suite}.json"
    report.write_text(json.dumps(output, indent=2, allow_nan=False))
    yield output


def markdown_report(entries):
    columns = [
        "Experiment / controller",
        "Status",
        "CH₄ kg",
        "Use %",
        "Curtail kWh",
        "Starts / trips",
        "Detection h",
        "False alarms",
        "Limited / fallback",
        "Allocated €",
        "Contribution €",
        "Ending H₂ / CO₂ kg",
        "Battery kWh",
    ]
    lines = [
        "| " + " | ".join(columns) + " |",
        "|" + "|".join(["---", "---"] + ["---:"] * (len(columns) - 2)) + "|",
    ]

    def row(values):
        lines.append(
            "| "
            + " | ".join(str(value).replace("|", "/").replace("\n", " ") for value in values)
            + " |"
        )

    for entry in entries:
        for attempt in entry.get("attempts", []):
            row(
                [
                    entry["case"] + " / previous attempt",
                    attempt["status"] + ": " + str(attempt.get("error", "")),
                    *(["—"] * (len(columns) - 2)),
                ]
            )
        if not entry.get("metrics"):
            row(
                [
                    entry["case"],
                    entry["status"] + ": " + str(entry.get("error", "")),
                    *(["—"] * (len(columns) - 2)),
                ]
            )
        for name, m in entry.get("metrics", {}).items():
            end = m["ending"] or {"h2_kg": 0, "co2_kg": 0, "battery_kwh": 0}
            delay = m["detection_delay_hours"]
            row(
                [
                    entry["case"] + " / " + name,
                    entry["status"],
                    f"{m['methane_kg']:.1f}",
                    f"{m['utilisation'] * 100:.1f}",
                    f"{m['curtailed_kwh']:.0f}",
                    f"{m['reactor_starts']:.0f} / {m['forced_downtime_hours']}",
                    delay if delay is not None else "—",
                    m["false_alarms"],
                    f"{m['limited_solves']} / {m['fallbacks']}",
                    f"{m['total_eur']:.0f}" if m["total_eur"] is not None else "Unpriced",
                    f"{m['assumed_contribution_eur']:.1f}"
                    if m["assumed_contribution_eur"] is not None
                    else "Unpriced",
                    f"{end['h2_kg']:.1f} / {end['co2_kg']:.1f}",
                    f"{max(0, end['battery_kwh']):.1f}",
                ]
            )
    service_rows = [
        (entry["case"], name, m)
        for entry in entries
        for name, m in entry.get("metrics", {}).items()
        if m.get("field_operations", {}).get("components")
    ]
    if service_rows:
        lines.extend(
            [
                "",
                "Recorded field operations (ending work remains unresolved unless verified):",
                "",
                "| Experiment / controller | Dock kWh | Visits / service kits | Allocated services € | Ending robot kWh | Open / failed work |",
                "|---|---:|---:|---:|---:|---:|",
            ]
        )
        for case, name, m in service_rows:
            field = m["field_operations"]
            quantities = field["quantities"]
            state = m.get("service_work") or {}
            orders = state.get("orders", [])
            row(
                [
                    case + " / " + name,
                    f"{quantities.get('charge_input_kwh', 0):.2f}",
                    f"{quantities.get('human_visits', 0)} / {quantities.get('service_kits_used', quantities.get('used:module', 0))}",
                    f"{field['total_eur']:.2f}" if field["total_eur"] is not None else "Unpriced",
                    " / ".join(f"{r['energy_kwh']:.2f}" for r in state.get("robots", {}).values()),
                    sum(o["status"] not in ("completed", "verified") for o in orders),
                ]
            )
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--suite",
        choices=["synthetic", "historical", "ablation", "thermal", "all"],
        default="synthetic",
    )
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--replay", type=Path)
    args = parser.parse_args()
    if args.replay:
        with zipfile.ZipFile(args.replay) as z:
            source = json.loads(
                z.read(
                    "methane-run-v3.json"
                    if "methane-run-v3.json" in z.namelist()
                    else "methane-run-v2.json"
                )
            )
        verify(source)
        result = run(
            Config.from_dict(source["config"]),
            weather=source["weather"],
            strategies=source["records"],
            policies=source.get("provenance", {}).get("controller_policies"),
            uncertainty=source.get("uncertainty", {}).get("world"),
        )
        print(export(result))
    else:
        config = Config()
        config = replace(config, weather=replace(config.weather, offline=args.offline))
        cancellation = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: cancellation.set())
        seen = 0
        for entries in batch(config, args.suite, cancel=cancellation):
            if len(entries) != seen:
                seen = len(entries)
                print(seen, entries[-1]["case"], entries[-1]["status"], flush=True)
        report = RUNS / "batches" / f"report-{args.suite}.md"
        report.write_text(markdown_report(entries))
        print(report)


if __name__ == "__main__":
    main()
