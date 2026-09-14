"""Component fixtures, independent archive audits, docs, benchmarks and TLC."""

import argparse
import hashlib
import json
import os
import platform
import statistics
import subprocess
import time
from pathlib import Path

from methane.audit import PhysicalAuditError, check, physical
from methane.battery import (
    IMPLEMENTATIONS,
    Battery,
    BatteryInput,
    BatteryParameters,
    BatteryState,
)
from methane.components import assemble
from methane.config import Config, Scenario
from methane.contracts import SPECS
from methane.evidence import load
from methane.physics import State, transition
from methane.reactor import ThermalInput, step
from methane.weather import deliveries

ROOT = Path(__file__).resolve().parent.parent
TLC_SHA256 = "936a262061c914694dfd669a543be24573c45d5aa0ff20a8b96b23d01e050e88"


def field_unit(key):
    for suffix, unit in (
        ("_kwh", "kWh"),
        ("_kw", "kW"),
        ("_kg", "kg"),
        ("_c", "°C"),
        ("_hours", "h"),
    ):
        if key.endswith(suffix):
            return unit
    return "dimensionless"


def audit_archive(result):
    """Recompute from actions and independent before-state, never trusting stored residuals."""
    if result["config"].get("lifecycle"):
        from methane.reference import audit

        checked = audit(result)
        return dict(
            run_id=result["run_id"],
            provenance="recorded" if "provenance" in result else "unavailable (legacy)",
            passed=checked["passed"],
            audits=checked["checks"],
            checker=checked["checker"],
            failures=checked["failures"],
            scope=checked["scope"],
        )
    c = Config.from_dict(result["config"])
    components = assemble(c.plant, c.models)
    reports = []
    expected_controllers = result.get("provenance", {}).get("strategies", list(result["records"]))
    reports.append(
        check(
            "controller_trace_count",
            "site",
            len(set(expected_controllers).symmetric_difference(result["records"])),
            "count",
        )
    )
    for controller, rows in result["records"].items():
        if result["status"] == "complete":
            reports.append(
                check("complete_interval_count", controller, len(rows) - c.scenario.hours, "count")
            )
        if not rows:
            continue
        before = State.initial(
            c.plant, result["weather"]["truth"][result["weather"]["times"][0]]["ambient_c"]
        )
        for i, row in enumerate(rows):
            capacity = (
                result.get("retrospective_truth_by_controller", {}).get(controller)
                or result.get("retrospective_truth", [{}] * len(rows))
            )[i].get("capacity_kw", c.plant.electrolyser_kw)
            try:
                after, expected = transition(
                    c.plant,
                    before,
                    row["applied"],
                    row["pv_kw"],
                    row["ambient_c"],
                    row["co2_delivered_kg"] + row["co2_rejected_kg"],
                    components=components,
                    capacity=capacity,
                    requested=row.get("requested"),
                    service_kw=row.get("service_kw", 0),
                )
            except PhysicalAuditError as exc:
                reports.extend({**audit, "interval": i} for audit in exc.audits)
                break
            capacity = (
                result.get("retrospective_truth_by_controller", {}).get(controller)
                or result.get("retrospective_truth", [{}] * len(rows))
            )[i].get("capacity_kw", c.plant.electrolyser_kw)
            audits = physical(
                c.plant,
                before,
                {
                    **expected,
                    "requested": row.get("requested", row["applied"]),
                    "forced_trip": row.get("forced_trip", False),
                },
                interval=i,
                capacity=capacity,
            )
            sample = result["weather"]["truth"][result["weather"]["times"][i]]
            sample = {
                **sample,
                "pv_kw": sample["pv_kw"]
                * (1 - row.get("field_operations", {}).get("soiling_before", 0)),
            }
            for key in ("pv_kw", "ambient_c"):
                audits.append(
                    check(
                        "recorded_input_" + key,
                        controller,
                        row[key] - sample[key],
                        field_unit(key),
                        abs(sample[key]),
                        interval=i,
                    )
                )
            scheduled = deliveries(c.plant, c.scenario, i, 1)[0]
            audits.append(
                check(
                    "recorded_delivery",
                    "co2",
                    row["co2_delivered_kg"] + row["co2_rejected_kg"] - scheduled,
                    "kg",
                    scheduled,
                    interval=i,
                )
            )
            for key, value in vars(after).items():
                audits.append(
                    check(
                        "stored_state_" + key,
                        controller,
                        float(row["state"][key]) - float(value),
                        field_unit(key),
                        abs(float(value)),
                        interval=i,
                    )
                )
            for key, value in expected.items():
                if isinstance(value, (int, float)) and (
                    key in row or key not in ("service_kw", "process_demand_kw")
                ):
                    audits.append(
                        check(
                            "stored_" + key,
                            controller,
                            row[key] - value,
                            field_unit(key),
                            abs(value),
                            interval=i,
                        )
                    )
            reports.extend(audits)
            recorded = row.get("battery_record")
            if result.get("provenance", {}).get("implementations", {}).get("battery"):
                expected_identity = components.battery.identity()
                audits = [
                    check(
                        "battery_implementation_identity",
                        "battery",
                        int(
                            result["provenance"]["implementations"]["battery"] != expected_identity
                        ),
                        "identity",
                        interval=i,
                    )
                ]
                if recorded is None:
                    audits.append(
                        check("battery_record_present", "battery", 1, "record", interval=i)
                    )
                else:
                    reference = expected["battery_record"]
                    for key in (
                        "schema_version",
                        "model_id",
                        "model_version",
                        "implementation_id",
                        "parameters",
                        "before",
                        "inputs",
                    ):
                        audits.append(
                            check(
                                "battery_record_" + key,
                                "battery",
                                int(recorded.get(key) != reference[key]),
                                "identity",
                                interval=i,
                            )
                        )
                    for group in ("after", "flows"):
                        for key, value in reference[group].items():
                            audits.append(
                                check(
                                    "battery_record_" + key,
                                    "battery",
                                    recorded.get(group, {}).get(key, float("nan")) - value,
                                    "kWh",
                                    abs(value),
                                    interval=i,
                                )
                            )
                    audits.append(
                        check(
                            "battery_record_audits",
                            "battery",
                            int(recorded.get("audits") != reference["audits"]),
                            "identity",
                            interval=i,
                        )
                    )
                reports.extend(audits)
            for component in ("electrolyser", "hydrogen", "co2", "reactor"):
                if component not in result.get("provenance", {}).get("implementations", {}):
                    continue
                recorded_component = row.get("component_records", {}).get(component)
                expected_component = expected["component_records"][component]

                def compare_record(actual, reference, path, component=component, i=i):
                    if isinstance(reference, dict):
                        if not isinstance(actual, dict) or set(actual) != set(reference):
                            reports.append(
                                check(
                                    "component_record_shape_" + path,
                                    component,
                                    1,
                                    "record",
                                    interval=i,
                                )
                            )
                            return
                        for key, value in reference.items():
                            compare_record(actual[key], value, path + "/" + key)
                    elif isinstance(reference, (float, int)):
                        delta = (
                            float(actual) - float(reference)
                            if isinstance(actual, (float, int))
                            else float("nan")
                        )
                        reports.append(
                            check(
                                "component_record_" + path,
                                component,
                                delta,
                                field_unit(path),
                                abs(float(reference)),
                                interval=i,
                            )
                        )
                    elif actual != reference:
                        reports.append(
                            check("component_record_" + path, component, 1, "identity", interval=i)
                        )

                compare_record(recorded_component, expected_component, component)
            before = after
    return {
        "run_id": result["run_id"],
        "provenance": "recorded" if "provenance" in result else "unavailable (legacy)",
        "passed": result["status"] == "complete" and all(a["passed"] for a in reports),
        "audits": reports,
    }


def reference_text():
    lines = [
        "# Component reference",
        "",
        "Generated by `python -m methane.engineering docs`; edit component metadata, not this file.",
        "",
        "These are illustrative models. Numerical checks and finite-state verification do not establish real-plant calibration.",
        "",
    ]
    for name, spec in SPECS.items():
        lines += [
            f"## {name.title()}",
            "",
            f"Model: `{spec.model_id}/{spec.version}`",
            "",
            spec.time_semantics,
            "",
            "| Parameter | Unit | Default | Range | Source |",
            "|---|---|---:|---|---|",
        ]
        lines += [
            f"| {p.label} (`{p.key}`) | {p.unit} | {p.default:g} | {p.lower:g}–{p.upper:g} | {p.source} |"
            for p in spec.parameters
        ]
        lines += [
            "",
            "Inputs: " + "; ".join(spec.inputs),
            "",
            "Outputs: " + "; ".join(spec.outputs),
            "",
            "Assumptions:",
            "",
        ] + ["- " + x for x in spec.assumptions]
        if spec.execution_interface:
            lines += [
                "",
                "Execution: `" + spec.execution_interface + "`",
                "",
                "Planning: `" + spec.planning_interface + "`",
                "",
                "Verification:",
                "",
            ]
            lines += ["- " + item for item in spec.verification]
        lines += [
            "",
            "References: "
            + (
                ", ".join(f"[source]({x})" for x in spec.references)
                or "Conservation-law fixture; assumptions above, no empirical calibration source."
            ),
            "",
        ]
        if name == "battery":
            lines += [
                "### Replaceable implementations",
                "",
                "Both implementations expose `Battery.step(state, inputs)` and `Battery.planning(state, durations)`. Planning returns local energy/charge/discharge/direction bounds and linear rows; it has no SciPy dependency. Execution returns ending state, losses and audits. No implicit clipping is permitted.",
                "",
            ]
            lines += [f"- `{k}`: {v.description}." for k, v in IMPLEMENTATIONS.items()]
            lines += [
                "",
                'Select `Config(models=Models(battery="loss-ledger/1"))` or use advanced experiment setup. Defaults and archives without a selection use `affine/1`; legacy records are never assigned new provenance.',
                "",
                "### Executed round-trip fixture",
                "",
                "200 kWh capacity, 1/h C-rate, 64% round-trip efficiency. Start at 20 kWh, charge at 100 kW for 0.5 h, then discharge at 64 kW for 0.5 h. Independently: 50 kWh enters, 40 kWh is stored; 32 kWh returns to the bus. Losses are 10 + 8 = 18 kWh, ending at 20 kWh.",
                "",
                "| Implementation | After charge kWh | After discharge kWh | Total loss kWh |",
                "|---|---:|---:|---:|",
            ]
            for key, kernel in IMPLEMENTATIONS.items():
                battery = Battery(BatteryParameters(200, 1, 0.64), kernel)
                first = battery.step(BatteryState(20), BatteryInput(100, 0, 0.5))
                second = battery.step(first.state, BatteryInput(0, 64, 0.5))
                lines.append(
                    f"| {key} | {first.state.energy_kwh:.6f} | {second.state.energy_kwh:.6f} | {dict(first.flows)['loss_kwh'] + dict(second.flows)['loss_kwh']:.6f} |"
                )
            lines += [
                "",
                "The battery inspector's **Trace this result** links displayed energy, SOC and losses to recorded interval inputs, requested/applied actions, asset ID, model/implementation version and source hashes. Battery records and lineage have their own `/1` schemas inside additive methane schema 3 fields. [Integration and verification](battery.md).",
                "",
            ]
    lines += [
        "## Executed reactor example",
        "",
        "Constant 60 kW heating from 20°C ambient, no production/cooling. This isolated fixture intentionally omits dispatch temperature limits.",
        "",
        "| Hours | Temperature °C | Heat lost kWh |",
        "|---:|---:|---:|",
    ]
    c = Config()
    for duration in (0.25, 0.5, 1, 2, 4):
        r = step(c.plant, ThermalInput(20, 20, 60, duration_hours=duration))
        lines.append(
            f"| {duration:g} | {r.state.temperature_c:.6f} | {dict(r.flows)['heat_loss_kwh']:.6f} |"
        )
    lines += [
        "",
        "The full-plant scheduler remains hourly. Formal assumptions are in [the reactor specification](../formal/README.md).",
        "",
        "Build artifacts contain executed plots, test counts from JUnit, measured timings and full TLC output; they are evidence for that specific build.",
        "",
    ]
    return "\n".join(lines)


def docs(check_only=False, junit=None):
    destination = ROOT / "docs/components.md"
    text = reference_text()
    if check_only:
        if not destination.exists() or destination.read_text() != text:
            raise SystemExit("Generated component reference is stale; run engineering docs.")
        return
    destination.write_text(text)
    out = ROOT / "build/engineering"
    out.mkdir(parents=True, exist_ok=True)
    import plotly.graph_objects as go

    durations = [i / 10 for i in range(1, 81)]
    c = Config()
    fig = go.Figure()
    for label, initial, heating in (("Warm-up: 60 kW", 20, 60), ("Passive cooling", 350, 0)):
        fig.add_scatter(
            x=durations,
            y=[
                step(
                    c.plant, ThermalInput(initial, 20, heating, duration_hours=t)
                ).state.temperature_c
                for t in durations
            ],
            name=label,
        )
    fig.update_layout(
        xaxis_title="Elapsed hours",
        yaxis_title="Temperature / °C",
        title="Isolated constant-input reactor; illustrative assumptions",
    )
    fig.write_html(out / "reactor.html", include_plotlyjs=True)
    if junit:
        from xml.etree import ElementTree

        from methane.provenance import digest, source_identity

        tree = ElementTree.parse(junit)
        (out / "tests.json").write_text(
            json.dumps(
                {
                    "junit_sha256": hashlib.sha256(Path(junit).read_bytes()).hexdigest(),
                    "source_at_report_generation": source_identity(),
                    "test_source_hash": digest(
                        {
                            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
                            for p in sorted((ROOT / "tests").glob("*.py"))
                        }
                    ),
                    "suites": [x.attrib for x in tree.iter("testsuite")],
                },
                indent=2,
            )
        )


def formal(java, jar):
    jar = Path(jar).resolve()
    if hashlib.sha256(jar.read_bytes()).hexdigest() != TLC_SHA256:
        raise ValueError("TLC checksum does not match pinned 1.7.4 release.")
    out = ROOT / "build/engineering/formal"
    out.mkdir(parents=True, exist_ok=True)
    spec = ROOT / "formal/Reactor.tla"
    (out / "Reactor.tla").write_bytes(spec.read_bytes())
    reports = []
    for minimum in range(1, 5):
        cfg = out / f"Reactor-{minimum}.cfg"
        cfg.write_text(
            f"CONSTANT MinimumRun = {minimum}\nSPECIFICATION Spec\nINVARIANTS TypeOK SafeProduction Commitment ExplicitTrip StartCount StopCount ContinueCount\n"
        )
        command = [
            java,
            "-XX:+UseParallelGC",
            "-cp",
            str(jar),
            "tlc2.TLC",
            "-workers",
            "1",
            "-config",
            cfg.name,
            "-metadir",
            str(out / f"states-{minimum}"),
            "Reactor",
        ]
        start = time.perf_counter()
        completed = subprocess.run(command, cwd=out, text=True, capture_output=True, timeout=120)
        log = completed.stdout + completed.stderr
        passed = completed.returncode == 0 and "No error has been found" in log
        reports.append(
            {
                "minimum_run": minimum,
                "passed": passed,
                "seconds": time.perf_counter() - start,
                "command": command,
                "output": log,
            }
        )
    report = {
        "scope": "Finite-state abstraction only; not continuous/implementation proof",
        "spec_sha256": hashlib.sha256(spec.read_bytes()).hexdigest(),
        "tlc_sha256": TLC_SHA256,
        "java": subprocess.run([java, "-version"], capture_output=True, text=True).stderr,
        "cases": reports,
    }
    (out / "report.json").write_text(json.dumps(report, indent=2))
    if not all(r["passed"] for r in reports):
        raise SystemExit("TLC failed; inspect build/engineering/formal/report.json")
    return {"passed": True, "models": len(reports)}


def benchmark(hours=72, repeats=5):
    from methane.simulation import run
    from methane.solar import preview

    c = Config(scenario=Scenario(hours=hours))
    runs = []
    for _ in range(repeats):
        start = time.perf_counter()
        r = run(c)
        runs.append(
            {
                "seconds": time.perf_counter() - start,
                "status": r["status"],
                "experiment_id": r["experiment_id"],
                "metrics": r["metrics"],
            }
        )
    preview_ms = []
    for _ in range(100):
        start = time.perf_counter()
        preview(r)
        preview_ms.append((time.perf_counter() - start) * 1000)
    return {
        "environment": platform.platform(),
        "hours": hours,
        "runs": runs,
        "median_seconds": statistics.median(x["seconds"] for x in runs),
        "preview_ms_cold": preview_ms[0],
        "preview_ms_p95_warm": sorted(preview_ms[1:])[93],
        "note": "Backend only; browser and transport measured by Playwright",
    }


def battery_fixture():
    """Executable example with hand-calculated expected outputs and timings."""
    from methane.provenance import source_identity

    implementations = {}
    for key, kernel in IMPLEMENTATIONS.items():
        battery = Battery(BatteryParameters(200, 1, 0.64), kernel)
        first = battery.step(BatteryState(20), BatteryInput(100, 0, 0.5))
        second = battery.step(first.state, BatteryInput(0, 64, 0.5))
        measurements = []
        for _ in range(1000):
            start = time.perf_counter()
            battery.step(BatteryState(20), BatteryInput(100, 0, 0.5))
            measurements.append((time.perf_counter() - start) * 1000)
        implementations[key] = {
            **battery.identity(),
            "charge": battery.record(BatteryState(20), BatteryInput(100, 0, 0.5), first),
            "discharge": battery.record(first.state, BatteryInput(0, 64, 0.5), second),
            "step_p95_ms": sorted(measurements)[949],
            "timing_samples": len(measurements),
            "passed": abs(first.state.energy_kwh - 60) < 1e-8
            and abs(second.state.energy_kwh - 20) < 1e-8
            and abs(dict(first.flows)["loss_kwh"] + dict(second.flows)["loss_kwh"] - 18) < 1e-8,
        }
    return {
        "passed": all(x["passed"] for x in implementations.values()),
        "expected": {"after_charge_kwh": 60, "after_discharge_kwh": 20, "loss_kwh": 18},
        "implementations": implementations,
        "source": source_identity(),
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    d = sub.add_parser("docs")
    d.add_argument("--check", action="store_true")
    d.add_argument("--junit")
    a = sub.add_parser("audit")
    a.add_argument("archive")
    f = sub.add_parser("formal")
    f.add_argument("--java", default=os.environ.get("JAVA", "java"))
    f.add_argument("--jar", required=True)
    b = sub.add_parser("benchmark")
    b.add_argument("--hours", type=int, default=72)
    b.add_argument("--repeats", type=int, default=5)
    c = sub.add_parser("component")
    c.add_argument("name", choices=SPECS)
    args = parser.parse_args()
    if args.command == "docs":
        docs(args.check, args.junit)
        return
    if args.command == "formal":
        result = formal(args.java, args.jar)
    elif args.command == "audit":
        result = audit_archive(load(args.archive))
    elif args.command == "benchmark":
        result = benchmark(args.hours, args.repeats)
    elif args.name == "battery":
        result = battery_fixture()
    elif args.name == "reactor":
        r = step(Config().plant, ThermalInput(20, 20, 60))
        result = {"temperature_c": r.state.temperature_c, **dict(r.flows)}
    else:
        from methane.solar import default_design, interval
        from methane.weather import synthetic

        c = Config()
        w = synthetic(c)
        t = w["times"][12]
        result = interval(default_design(c.plant, c.weather), w["truth"][t], t, c.plant, c.weather)
    out = ROOT / "build/engineering"
    out.mkdir(parents=True, exist_ok=True)
    name = args.name if args.command == "component" else args.command
    (out / f"{name}.json").write_text(json.dumps(result, indent=2))
    print(
        json.dumps(
            {k: v for k, v in result.items() if k not in ("audits", "runs", "metrics")}, indent=2
        )
    )
    if result.get("passed") is False:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
