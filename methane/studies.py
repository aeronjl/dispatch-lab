"""Versioned study protocols, immutable editions and evidence-backed publications.

The manifest, resolved inputs and completed case attempts are append-only.
Progress is operational state. Every finished/resumed execution publishes a new
report revision, retaining failed attempts and the original report editions.
"""

import argparse
import copy
import fcntl
import gzip
import hashlib
import html
import json
import os
import re
import subprocess
import sys
import time
import uuid
import zipfile
from datetime import UTC, datetime
from pathlib import Path

from methane.config import Config
from methane.provenance import LOADED_CAPSULE, LOADED_FILES, LOADED_SOURCE, digest
from methane.source_capsule import decode

ROOT = Path(__file__).resolve().parent.parent
STORE = Path(os.environ.get("DISPATCH_STUDY_STORE", ROOT / "runs" / "studies"))
PROTOCOL_PATH = "docs/studies/battery-reserves-v9.json"
PROTOCOLS = {
    "battery-reserves": PROTOCOL_PATH,
    "field-recovery": "docs/studies/field-recovery-v4.json",
    "field-cleaning": "docs/studies/field-cleaning-v3.json",
    "field-information": "docs/studies/field-information-v2.json",
    "field-support": "docs/studies/field-support-v3.json",
    "field-provision": "docs/studies/field-provision-v2.json",
    "field-interface": "docs/studies/field-interface-v2.json",
    "field-recovery-tests": "docs/studies/field-recovery-tests-v1.json",
    "field-coordination": "docs/studies/field-coordination-v1.json",
    "field-computation": "docs/studies/field-computation-v2.json",
}


def now():
    return datetime.now(UTC).isoformat()


def protocol(identifier=None):
    if identifier == "uncertainty":
        from methane.uncertainty_studies import protocol as uncertainty_protocol

        return uncertainty_protocol()
    if identifier is not None and identifier not in PROTOCOLS:
        raise ValueError("Unknown study protocol")
    return json.loads(LOADED_FILES[PROTOCOLS[identifier] if identifier else PROTOCOL_PATH])


def protocols():
    return [protocol(k) for k in PROTOCOLS]


def case_policies(spec, case):
    return (
        case["policies"]
        if spec["schema_version"]
        in ("dispatch-lab/study-protocol/2", "dispatch-lab/study-protocol/3")
        else spec["policies"]
    )


def comparison_names(spec):
    names = (spec.get("baseline_controller"), spec.get("candidate_controller"))
    if len(set(names)) != 2 or set(names) != set(spec["policies"]):
        raise ValueError(
            "A paired study needs explicit, distinct baseline and candidate identities"
        )
    return names


def withdrawal(identifier, root=STORE):
    path = location(identifier, root) / "withdrawal.json"
    return json.loads(path.read_text()) if path.exists() else None


def write_once(path, value):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    data = json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2, allow_nan=False) + "\n"
    with path.open("x", encoding="utf-8") as f:
        f.write(data)


def atomic(path, value):
    path = Path(path)
    temporary = path.with_suffix(".tmp-" + uuid.uuid4().hex)
    temporary.write_text(json.dumps(value, ensure_ascii=False, allow_nan=False))
    temporary.replace(path)


def location(identifier, root=STORE):
    if not re.fullmatch(r"[a-f0-9]{32}", identifier):
        raise ValueError("Invalid study edition identifier")
    return Path(root) / identifier


def complete_config(value):
    # JSON preserves the immutable tuple contents as arrays in saved priors.
    # Compare their serialized form while still rejecting implicit defaults.
    supplied = json.loads(json.dumps(value, allow_nan=False))
    resolved = json.loads(json.dumps(Config.from_dict(value).to_dict(), allow_nan=False))
    if resolved != supplied:
        raise ValueError(
            "A study needs a complete configuration; implicit defaults are not allowed"
        )
    return resolved


def differences(before, after, prefix=""):
    rows = []
    for key in sorted(set(before) | set(after)):
        a, b = before.get(key), after.get(key)
        path = f"{prefix}.{key}" if prefix else key
        if key not in before or key not in after:
            rows.append(
                {
                    "parameter": path,
                    "before": a,
                    "after": b,
                    "before_present": key in before,
                    "after_present": key in after,
                }
            )
        elif isinstance(a, dict) and isinstance(b, dict):
            rows.extend(differences(a, b, path))
        elif a != b:
            rows.append({"parameter": path, "before": a, "after": b})
    return rows


def resolve_cases(spec, basis, tier):
    from methane.policy import Policy

    if spec["schema_version"] == "dispatch-lab/study-protocol/3":
        from methane.uncertainty_studies import resolve_cases as uncertainty_resolve

        return uncertainty_resolve(spec, complete_config(basis), tier)
    if spec["schema_version"] == "dispatch-lab/study-protocol/2":
        from methane.computation_studies import RESOLVER as COMPUTATION_RESOLVER
        from methane.computation_studies import resolve as computation_resolve
        from methane.field_studies import resolve

        if spec.get("resolver") == COMPUTATION_RESOLVER:
            return computation_resolve(spec, basis, tier)
        return resolve(spec, basis, tier)
    if spec["schema_version"] != "dispatch-lab/study-protocol/1":
        raise ValueError("Unsupported study protocol")
    basis = complete_config(basis)
    if tier not in spec["tiers"]:
        raise ValueError("Unknown study tier")
    settings = spec["tiers"][tier]
    comparison_names(spec)
    for policy in spec["policies"].values():
        Policy(**policy)
    if basis["plant"]["battery_kwh"] <= 0:
        raise ValueError("This capacity study requires a positive basis battery capacity")
    cases = []
    for factor in settings["battery_factors"]:
        for condition in spec["conditions"]:
            for seed in settings["seeds"]:
                config = copy.deepcopy(basis)
                config["rng_policy"] = "named-channels/1"
                config["weather"] = copy.deepcopy(spec["reference_config"]["weather"])
                config["scenario"] = copy.deepcopy(spec["reference_config"]["scenario"])
                config["scenario"].update(
                    hours=settings["hours"],
                    horizon_hours=24,
                    seed=seed,
                    forecast_bias=condition["forecast_bias"],
                    capacity_fraction=1,
                    flow_bias_fraction=0,
                    delivery_delay_hours=0,
                    solver_seconds=settings["solver_seconds"],
                )
                config["plant"]["battery_kwh"] *= factor
                config["plant"]["battery_c_rate"] /= factor
                config = complete_config(config)
                identifier = digest({"protocol": digest(spec), "config": config})[:24]
                cases.append(
                    {
                        "case_id": identifier,
                        "label": f"{condition['label']} · seed {seed} · battery ×{factor:g}",
                        "condition": condition["id"],
                        "seed": seed,
                        "battery_factor": factor,
                        "config": config,
                        "changes_from_basis": differences(basis, config),
                        "resolved_battery": {
                            "capacity_kwh": config["plant"]["battery_kwh"],
                            "power_kw": basis["plant"]["battery_kwh"]
                            * basis["plant"]["battery_c_rate"],
                            "initial_kwh": config["plant"]["battery_kwh"]
                            * config["plant"]["initial_soc"],
                        },
                    }
                )
    return cases


def read_manifest(identifier, root=STORE):
    path = location(identifier, root)
    value = json.loads((path / "manifest.json").read_text())
    expected = value.pop("integrity_sha256")
    if digest(value) != expected or value["edition_id"] != identifier:
        raise ValueError("Study manifest integrity failure")
    value["integrity_sha256"] = expected
    if digest(value["protocol"]) != value["protocol_hash"]:
        raise ValueError("Study protocol integrity failure")
    return value


def prepare_source(directory, capsule):
    files = decode(capsule)
    source = Path(directory) / "source"
    for name, data in files.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != data:
                raise ValueError("Frozen study source was modified")
        else:
            target.write_bytes(data)
    return source


def create(
    basis=None,
    tier="reference",
    parent=None,
    action="reference",
    root=STORE,
    basis_origin=None,
    *,
    protocol_id=None,
    specification=None,
):
    from methane.weather import prepare

    if action not in ("reference", "current-plant", "reproduce"):
        raise ValueError("Unknown study action")
    old = read_manifest(parent, root) if parent else None
    if action == "reproduce" and old is None:
        raise ValueError("Reproduction requires a source edition")
    withdrawn_parent = old and withdrawal(parent, root)
    if withdrawn_parent and action == "reproduce":
        raise ValueError(
            "This edition was withdrawn; create a replacement with the current protocol"
        )
    if old and (protocol_id is not None or specification is not None):
        raise ValueError(
            "A child edition retains its parent's protocol; choose a new root edition to change it"
        )
    if protocol_id is not None and specification is not None:
        raise ValueError("Choose a named protocol or an explicit specification")
    selected = (
        specification
        if specification is not None
        else protocol(protocol_id)
        if protocol_id
        else protocol()
    )
    spec = copy.deepcopy(old["protocol"] if old and not withdrawn_parent else selected)
    if action == "reproduce":
        basis, tier = copy.deepcopy(old["basis"]), old["tier"]
        capsule = json.loads((location(parent, root) / "source-capsule.json").read_text())
        if capsule["sha256"] != old["source_capsule_sha256"]:
            raise ValueError("Original source capsule identity does not match")
        cases = copy.deepcopy(old["cases"])
        source_hash = old["source_hash"]
    else:
        basis = complete_config(basis or spec["reference_config"])
        cases = resolve_cases(spec, basis, tier)
        capsule, source_hash = LOADED_CAPSULE, LOADED_SOURCE["content_hash"]
    identifier = uuid.uuid4().hex
    directory = location(identifier, root)
    directory.mkdir(parents=True, exist_ok=False)
    write_once(directory / "source-capsule.json", capsule)
    prepare_source(directory, capsule)
    written = set()
    uncertainty_weather = {}
    for case in cases:
        if case.get("uncertainty_world", {}).get("status") == "invalid-input":
            case["input_status"] = "invalid-input"
            continue
        if action == "reproduce":
            if not case.get("weather_hash"):
                continue
            weather = json.loads(
                (location(parent, root) / "inputs" / (case["weather_hash"] + ".json")).read_text()
            )
            if digest(weather) != case["weather_hash"]:
                raise ValueError("Original weather input was modified")
        else:
            try:
                if spec.get("resolver") == "repeated-field-computation/1":
                    from methane.computation_studies import weather as computation_weather

                    weather = computation_weather(
                        Config.from_dict(case["config"]), spec["weather_fixture"]
                    )
                elif case.get("uncertainty_world"):
                    # Freeze one source retrieval per weather input set, even if
                    # edition preparation crosses a forecast publication boundary.
                    cfg = Config.from_dict(case["config"])
                    key = digest(
                        {
                            "weather": case["config"]["weather"],
                            "solar_kw": cfg.plant.solar_kw,
                            "scenario": {
                                k: case["config"]["scenario"][k]
                                for k in ("hours", "horizon_hours", "seed", "variability")
                            },
                        }
                    )
                    if key not in uncertainty_weather:
                        uncertainty_weather[key] = prepare(cfg)
                    weather = copy.deepcopy(uncertainty_weather[key])
                    if cfg.solar:
                        from methane.solar import transform_weather

                        weather = transform_weather(weather, cfg, cfg.solar)
                    from methane.adaptation import required, split_weather

                    if required(case["uncertainty_world"]):
                        weather = split_weather(
                            weather,
                            cfg,
                            Config.from_dict(case["uncertainty_world"]["controller_config"]),
                        )
                else:
                    weather = prepare(Config.from_dict(case["config"]))
            except (ValueError, RuntimeError) as exc:
                case.update(input_status="incomplete-data", input_error=str(exc), weather_hash=None)
                continue
            case.update(input_status="complete", weather_hash=digest(weather))
        if case["weather_hash"] not in written:
            write_once(directory / "inputs" / (case["weather_hash"] + ".json"), weather)
            written.add(case["weather_hash"])
    manifest = {
        "schema_version": "dispatch-lab/study-edition/1",
        "edition_id": identifier,
        "created_at": now(),
        "action": action,
        "parent_edition_id": parent,
        "protocol": spec,
        "protocol_hash": digest(spec),
        "tier": tier,
        "basis": basis,
        "basis_origin": old.get("basis_origin") if action == "reproduce" else basis_origin,
        "basis_changes": differences(spec["reference_config"], basis),
        "source_hash": source_hash,
        "source_capsule_sha256": capsule["sha256"],
        "cases": cases,
        "environment": environment(),
        "original_environment": old["environment"] if action == "reproduce" else None,
    }
    manifest["integrity_sha256"] = digest(manifest)
    write_once(directory / "manifest.json", manifest)
    return manifest


def environment():
    import platform
    from importlib.metadata import version

    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        **{k: version(k) for k in ("numpy", "scipy", "gradio")},
    }


def archive_for(identifier, entry, root=STORE):
    path = location(identifier, root) / entry["archive"]
    if not path.resolve().is_relative_to(location(identifier, root).resolve()):
        raise ValueError("Invalid study archive path")
    from methane.evidence import load

    result = load(path)
    if result["integrity_sha256"] != entry["archive_integrity"]:
        raise ValueError("Study archive identity mismatch")
    if result.get("study", {}).get("computation") != entry.get("computation"):
        raise ValueError("Computation summary does not match its sealed original recording")
    evidence = entry.get("independent_audit")
    if evidence:
        artifact = (location(identifier, root) / evidence["artifact"]).resolve()
        if not artifact.is_relative_to(location(identifier, root).resolve()):
            raise ValueError("Invalid study audit path")
        if hashlib.sha256(artifact.read_bytes()).hexdigest() != evidence["artifact_sha256"]:
            raise ValueError("Independent study audit artifact was modified")
    if entry.get("service_calculation"):
        calculation = service_calculation_for(identifier, entry, root)
        if calculation["source_hash"] != result["provenance"]["source"][
            "content_hash"
        ] or calculation["original_service_cost_version"] != result.get("service_cost_version"):
            raise ValueError("Saved service calculation does not belong to this run")
        if any(
            calculation["controllers"][name]["views"] != metrics["field_operations"]["views"]
            for name, metrics in result["metrics"].items()
        ):
            raise ValueError("Saved service calculation does not reconcile with recorded totals")
    return result


def service_calculation_for(identifier, entry, root=STORE):
    """Original once-per-run calculation, never reconstructed using newer pricing code."""
    reference = entry.get("service_calculation")
    if reference is None:
        raise ValueError(
            "This attempt has no saved service calculation. Original totals and executable source remain available; missing steps are not reconstructed as original evidence."
        )
    directory = location(identifier, root).resolve()
    path = (directory / reference["artifact"]).resolve()
    if not path.is_relative_to(directory) or not path.is_file():
        raise ValueError("Invalid saved service-calculation path")
    raw = path.read_bytes()
    if hashlib.sha256(raw).hexdigest() != reference["artifact_sha256"]:
        raise ValueError("Saved service calculation was modified")
    value = json.loads(gzip.decompress(raw))
    if (
        value["run_id"] != entry["run_id"]
        or value["source_hash"] != reference["source_hash"]
        or value["original_service_cost_version"] != reference["original_service_cost_version"]
    ):
        raise ValueError("Saved service-calculation identity mismatch")
    return value


def history(identifier, root=STORE, case_id=None):
    directory = location(identifier, root)
    if case_id is not None and (
        not isinstance(case_id, str) or not re.fullmatch(r"[a-f0-9]+", case_id)
    ):
        raise ValueError("Invalid study case identifier")
    histories = {}
    pattern = f"attempts/*/case-{case_id}.json" if case_id else "attempts/*/case-*.json"
    for path in sorted(directory.glob(pattern)):
        record = json.loads(path.read_text())
        seal = record.pop("integrity_sha256")
        if digest(record) != seal:
            raise ValueError("Case attempt integrity failure")
        record["integrity_sha256"] = seal
        histories.setdefault(record["case_id"], []).append(record)
    return histories


def entry_for(identifier, case_id, root=STORE, attempt_id=None):
    records = history(identifier, root, case_id).get(case_id, [])
    if attempt_id:
        records = [r for r in records if r["attempt_id"] == attempt_id]
    if not records:
        raise ValueError("This study case has no execution yet")
    return records[-1]


def stored_report(identifier, root=STORE, report_id=None):
    paths = list((location(identifier, root) / "reports").glob("*.json"))
    if report_id:
        paths = [p for p in paths if p.stem == report_id]
    if not paths:
        if report_id:
            raise ValueError("Report revision unavailable")
        return report(identifier, root)
    values = [json.loads(p.read_text()) for p in paths]
    value = max(values, key=lambda v: v["published_at"])
    expected = value.pop("integrity_sha256")
    if digest(value) != expected:
        raise ValueError("Published study report integrity failure")
    value["integrity_sha256"] = expected
    reporting_source(value, root)
    return value


def reporting_source(value, root=STORE, *, preserve=False):
    """Retain a report derivation without substituting it for the run's source."""
    identity = value.get("reporting")
    if identity is None:
        return None
    sha = identity.get("source_capsule_sha256", "")
    if not isinstance(sha, str) or not re.fullmatch(r"[0-9a-f]{64}", sha):
        raise ValueError("Invalid reporting source identity")
    path = location(value["edition_id"], root) / "reporting" / (sha + ".json")
    if not path.exists():
        if not preserve or sha != LOADED_CAPSULE["sha256"]:
            raise ValueError("Original reporting source is unavailable")
        path.parent.mkdir(exist_ok=True)
        write_once(path, LOADED_CAPSULE)
    capsule = json.loads(path.read_text())
    if capsule.get("sha256") != sha:
        raise ValueError("Reporting source capsule identity mismatch")
    files = decode(capsule)
    source_hash = digest(
        {
            name: hashlib.sha256(data).hexdigest()
            for name, data in files.items()
            if name.endswith(".py") or name.startswith("assets/")
        }
    )
    if source_hash != identity.get("source_hash"):
        raise ValueError("Reporting source content identity mismatch")
    return path


def run_edition(identifier, root=STORE, fresh=False):
    from methane.evidence import save
    from methane.provenance import seal
    from methane.reference import audit
    from methane.simulation import run

    manifest = read_manifest(identifier, root)
    directory = location(identifier, root)
    if manifest["source_hash"] != LOADED_SOURCE["content_hash"]:
        raise ValueError("Execute this study using its frozen source directory")
    expected = manifest.get("original_environment") or manifest["environment"]
    actual = environment()
    if any(actual[k] != expected[k] for k in ("python", "numpy", "scipy", "gradio")):
        raise ValueError(
            "Original dependency versions are required; restore the saved lock before rerunning"
        )
    attempt = datetime.now(UTC).strftime("%Y%m%dT%H%M%S%f") + "-" + uuid.uuid4().hex[:8]
    attempt_dir = directory / "attempts" / attempt
    attempt_dir.mkdir(parents=True, exist_ok=False)
    write_once(
        attempt_dir / "start.json", {"started_at": now(), "fresh": fresh, "environment": actual}
    )
    histories = history(identifier, root)

    def cancelled():
        return (directory / "cancel").exists()

    for index, case in enumerate(manifest["cases"]):
        previous = histories.get(case["case_id"], [])
        reusable = False
        if not fresh and previous and previous[-1]["status"] == "complete":
            try:
                saved = archive_for(identifier, previous[-1], root)
                reusable = (
                    saved["status"] == "complete"
                    and saved["config"] == case["config"]
                    and saved["provenance"]["source"]["content_hash"] == manifest["source_hash"]
                    and saved["provenance"]["weather_content_hash"] == case["weather_hash"]
                    and saved["provenance"].get("controller_policies")
                    == case_policies(manifest["protocol"], case)
                )
            except (ValueError, OSError, KeyError):
                reusable = False
        if reusable:
            continue
        record = {
            "case_id": case["case_id"],
            "attempt_id": attempt,
            "started_at": now(),
            "status": "cancelled" if cancelled() else "running",
        }

        def progress(fraction, desc="", index=index, case=case):
            atomic(
                directory / "progress.json",
                {
                    "status": "running",
                    "attempt_id": attempt,
                    "fraction": (index + fraction) / len(manifest["cases"]),
                    "description": case["label"] + " · " + desc,
                },
            )

        if not cancelled():
            try:
                if case["input_status"] != "complete":
                    record.update(
                        status="invalid-input"
                        if case["input_status"] == "invalid-input"
                        else "incomplete-data",
                        error=case.get("input_error"),
                    )
                else:
                    weather = json.loads(
                        (directory / "inputs" / (case["weather_hash"] + ".json")).read_text()
                    )
                    if digest(weather) != case["weather_hash"]:
                        raise ValueError("Study weather input integrity failure")
                    policies = case_policies(manifest["protocol"], case)
                    execution_started = time.perf_counter()
                    result = run(
                        Config.from_dict(case["config"]),
                        weather=weather,
                        strategies=list(policies),
                        policies=policies,
                        progress=progress,
                        cancelled=cancelled,
                        **(
                            {"uncertainty": case["uncertainty_world"]}
                            if "uncertainty_world" in case
                            else {}
                        ),
                    )
                    if manifest["protocol"].get("resolver") == "repeated-field-computation/1":
                        from methane.computation_studies import capture as capture_computation

                        record["computation"] = capture_computation(
                            result, case["controller"], time.perf_counter() - execution_started
                        )
                    check = audit(result)
                    if case.get("uncertainty_world"):
                        record["uncertainty_trajectory"] = {
                            name: [
                                {
                                    "hour": row["hour"] + 1,
                                    **{
                                        k: row["state"][k]
                                        for k in ("battery_kwh", "h2_kg", "co2_kg", "temperature_c")
                                    },
                                    "methane_kg": row["applied"]["methane_kg"],
                                }
                                for row in rows
                            ]
                            for name, rows in result["records"].items()
                        }
                    if manifest["protocol"]["schema_version"] == "dispatch-lab/study-protocol/2":
                        from methane.service_economics import report as service_report

                        calculation = {
                            "schema_version": "dispatch-lab/study-service-calculation/1",
                            "run_id": result["run_id"],
                            "source_hash": LOADED_SOURCE["content_hash"],
                            "original_service_cost_version": result["service_cost_version"],
                            "controllers": {
                                name: service_report(rows, result["config"]["service_economics"])
                                for name, rows in result["records"].items()
                            },
                        }
                        calculation_path = attempt_dir / (
                            "service-calculation-" + case["case_id"] + ".json.gz"
                        )
                        calculation_bytes = gzip.compress(
                            json.dumps(calculation, allow_nan=False).encode(), mtime=0
                        )
                        with calculation_path.open("xb") as f:
                            f.write(calculation_bytes)
                        record["service_calculation"] = {
                            "artifact": str(calculation_path.relative_to(directory)),
                            "artifact_sha256": hashlib.sha256(calculation_bytes).hexdigest(),
                            "source_hash": calculation["source_hash"],
                            "original_service_cost_version": calculation[
                                "original_service_cost_version"
                            ],
                        }
                    check_path = attempt_dir / ("audit-" + case["case_id"] + ".json.gz")
                    check_bytes = gzip.compress(
                        json.dumps(check, allow_nan=False).encode(), mtime=0
                    )
                    with check_path.open("xb") as f:
                        f.write(check_bytes)
                    result["study"] = {
                        "edition_id": identifier,
                        "case_id": case["case_id"],
                        "attempt_id": attempt,
                        "protocol_hash": manifest["protocol_hash"],
                    }
                    if record.get("computation") is not None:
                        result["study"]["computation"] = copy.deepcopy(record["computation"])
                    seal(result)
                    path = save(result, attempt_dir / "archives" / case["case_id"])
                    record.update(
                        status=result["status"]
                        if check["passed"] or result["status"] != "complete"
                        else "invalid",
                        archive=str(path.relative_to(directory)),
                        archive_integrity=result["integrity_sha256"],
                        run_id=result["run_id"],
                        metrics=result["metrics"],
                        independent_audit={
                            "passed": check["passed"],
                            "source_hash": LOADED_SOURCE["content_hash"],
                            "artifact": str(check_path.relative_to(directory)),
                            "artifact_sha256": hashlib.sha256(check_bytes).hexdigest(),
                        },
                        events=event_evidence(result),
                    )
                    if not check["passed"] and (
                        result["status"] == "complete"
                        or any(not item["passed"] for item in check["checks"])
                        or check.get("failures")
                    ):
                        record["error"] = (
                            "Independent reference check failed; completed prefix retained."
                        )
                    elif not check["passed"]:
                        record["audit_note"] = (
                            "Complete-run verification is unavailable for this incomplete run. "
                            "The recorded prefix has no failed numerical checks; cancellation "
                            "does not certify the unexecuted remainder."
                        )
                    if previous and previous[-1].get("archive"):
                        try:
                            original = archive_for(identifier, previous[-1], root)
                            record["numerical_comparison"] = numerical_comparison(original, result)
                        except (ValueError, OSError):
                            record["comparison_note"] = (
                                "Previous archive is unavailable or modified"
                            )
                    if manifest["action"] == "reproduce":
                        try:
                            old = entry_for(manifest["parent_edition_id"], case["case_id"], root)
                            record["numerical_comparison"] = numerical_comparison(
                                archive_for(manifest["parent_edition_id"], old, root), result
                            )
                        except (ValueError, OSError):
                            record["comparison_note"] = (
                                "Original execution unavailable; original inputs were still preserved"
                            )
            except Exception as exc:
                record.update(status="failed", error=f"{type(exc).__name__}: {exc}")
        record["finished_at"] = now()
        record["integrity_sha256"] = digest(record)
        write_once(attempt_dir / ("case-" + case["case_id"] + ".json"), record)
        progress(1, record["status"])
    publication = publish(identifier, root)
    atomic(
        directory / "progress.json",
        {
            "status": publication["status"],
            "fraction": 1,
            "description": "Study write-up saved",
            "report_id": publication["report_id"],
        },
    )
    write_once(
        attempt_dir / "finished.json", {"finished_at": now(), "report_id": publication["report_id"]}
    )
    return publication


def numerical_comparison(before, after):
    result = {}
    for name, rows in after["records"].items():
        old = before["records"].get(name, [])
        changed = [
            i
            for i, (a, b) in enumerate(zip(old, rows, strict=False))
            if any(abs(a["applied"][k] - b["applied"][k]) > 1e-5 for k in a["applied"])
        ]
        result[name] = {
            "first_different_interval": changed[0] if changed else None,
            "different_intervals": len(changed),
            "recorded_intervals": len(old),
            "recomputed_intervals": len(rows),
            "methane_delta_kg": after["metrics"][name]["methane_kg"]
            - before["metrics"][name]["methane_kg"],
        }
    return result


def event_evidence(result):
    names = list(result["records"])
    if len(names) != 2:
        return []
    pairs = list(zip(*(result["records"][n] for n in names), strict=False))
    chosen = next(
        (
            i
            for i, (a, b) in enumerate(pairs)
            if abs(a["applied"]["discharge_kw"] - b["applied"]["discharge_kw"]) > 1e-4
        ),
        None,
    )
    if chosen is None:
        return []
    return [
        {
            "controller": n,
            "hour": chosen,
            "component": "battery",
            "label": "First differing battery discharge",
            "discharge_kw": result["records"][n][chosen]["applied"]["discharge_kw"],
            "energy_kwh": result["records"][n][chosen]["state"]["battery_kwh"],
        }
        for n in names
    ]


def report(identifier, root=STORE):
    manifest = read_manifest(identifier, root)
    histories = history(identifier, root)
    if manifest["protocol"]["schema_version"] == "dispatch-lab/study-protocol/3":
        from methane.uncertainty_studies import report as uncertainty_report

        return uncertainty_report(manifest, histories, withdrawal(identifier, root))
    if manifest["protocol"]["schema_version"] == "dispatch-lab/study-protocol/2":
        from methane.field_studies import report as field_report

        value = field_report(manifest, histories, withdrawal(identifier, root))
        if manifest["protocol"].get("resolver") == "repeated-field-computation/1":
            from methane.computation_studies import qualify

            value["computation"] = qualify(value)
            value["finding"] += (
                " Computation repetitions are listed separately from seeds. Inspect their repeatability and solve quality before interpreting policy differences."
            )
        return value
    cases, groups = [], {}
    for case in manifest["cases"]:
        attempts = histories.get(case["case_id"], [])
        entry = attempts[-1] if attempts else {"status": "pending"}
        row = {
            **case,
            "entry": entry,
            "attempts": [
                {k: a.get(k) for k in ("attempt_id", "status", "started_at", "error", "run_id")}
                for a in attempts
            ],
        }
        if entry["status"] == "complete" and not withdrawal(identifier, root):
            a, b = (entry["metrics"][n] for n in comparison_names(manifest["protocol"]))
            delta = {
                "methane_kg": b["methane_kg"] - a["methane_kg"],
                "battery_kwh": b["ending"]["battery_kwh"] - a["ending"]["battery_kwh"],
                "forced_downtime_hours": b["forced_downtime_hours"] - a["forced_downtime_hours"],
            }
            row["delta"] = delta
            groups.setdefault(case["battery_factor"], []).append(delta)
        cases.append(row)
    aggregate = []
    for factor, rows in groups.items():
        aggregate.append(
            {
                "battery_factor": factor,
                "pairs": len(rows),
                "mean": {k: sum(r[k] for r in rows) / len(rows) for k in rows[0]},
                "methane_range_kg": [
                    min(r["methane_kg"] for r in rows),
                    max(r["methane_kg"] for r in rows),
                ],
                "higher_output_pairs": sum(r["methane_kg"] > 1e-5 for r in rows),
                "lower_output_pairs": sum(r["methane_kg"] < -1e-5 for r in rows),
            }
        )
    completed = sum(c["entry"]["status"] == "complete" for c in cases)
    withdrawn = withdrawal(identifier, root)
    status = "withdrawn" if withdrawn else "complete" if completed == len(cases) else "incomplete"
    finding = "No complete paired cases yet. No controller-performance conclusion is available."
    if aggregate:
        finding = " ".join(
            f"Battery ×{g['battery_factor']:g}: across {g['pairs']} completed pairs, the reserve planner produced "
            f"{abs(g['mean']['methane_kg']):.2f} kg {'more' if g['mean']['methane_kg'] >= 0 else 'less'} methane on average "
            f"and ended with {g['mean']['battery_kwh']:+.1f} kWh battery energy relative to the baseline. "
            f"Output differences ranged from {g['methane_range_kg'][0]:+.2f} to {g['methane_range_kg'][1]:+.2f} kg."
            for g in aggregate
        )
    if withdrawn:
        finding = withdrawn["reason"]
    return {
        "schema_version": "dispatch-lab/study-report/1",
        "edition_id": identifier,
        "manifest": manifest,
        "status": status,
        "completed_pairs": completed,
        "total_pairs": len(cases),
        "cases": cases,
        "aggregate": aggregate,
        "finding": finding,
        "interpretation_status": "Generated descriptive findings; no causal narrative review recorded",
        "scope": "Applies to these recorded configurations, source, inputs and compute budgets. A different plant needs a new evaluation.",
        "comparison_definition": "Reserve minus baseline within each case; incomplete cases excluded from means and retained in the case table.",
    }


def publish(identifier, root=STORE):
    return save_publication(report(identifier, root), root)


def publish_interpretation(identifier, report_id, paragraphs, reviewer, root=STORE):
    """Bind an authored interpretation to the exact reported attempts, without rerunning."""
    if not reviewer.strip() or not paragraphs or any(not p.strip() for p in paragraphs):
        raise ValueError("An interpretation needs an author and nonempty passages")
    value = stored_report(identifier, root, report_id)
    value.pop("integrity_sha256")
    value["interpretation"] = {
        "source_report_id": report_id,
        "author": reviewer,
        "paragraphs": paragraphs,
        "scope": "Authored interpretation of these recorded attempts; not empirical validation.",
    }
    value["interpretation_status"] = "Authored interpretation by " + reviewer
    return save_publication(value, root)


def save_publication(value, root=STORE):
    # Summary metrics alone cannot certify that the referenced recordings are
    # still present. Check once at publication, not on each UI progress poll.
    if value["status"] != "withdrawn":
        if withdrawal(value["edition_id"], root):
            raise ValueError("Publish the withdrawn report; this edition is not complete evidence")
        checked = 0
        for case in value["cases"]:
            entry = case.get("entry") or {}
            if entry.get("archive"):
                recorded = archive_for(value["edition_id"], entry, root)
                if recorded.get("study") and any(
                    recorded["study"].get(k) != expected
                    for k, expected in (
                        ("edition_id", value["edition_id"]),
                        ("case_id", case["case_id"]),
                        ("attempt_id", entry["attempt_id"]),
                    )
                ):
                    raise ValueError("Recording belongs to a different study case or attempt")
                checked += 1
            elif entry.get("status") == "complete":
                raise ValueError("A complete study case has no recorded archive")
        value["archive_verification"] = {
            "schema_version": "dispatch-lab/study-archive-verification/1",
            "status": "passed" if checked else "no-recorded-archives",
            "checked": checked,
            "scope": "Sealed recording identity, applicable study context, and referenced audit/service artifact identities at publication. Not empirical validation.",
        }
    reporting_source(value, root, preserve=True)
    value.update(report_id=uuid.uuid4().hex, published_at=now())
    value["integrity_sha256"] = digest(value)
    path = location(value["edition_id"], root) / "reports" / value["report_id"]
    write_once(path.with_suffix(".json"), value)
    from methane.study_presentation import preserve_index

    preserve_index(value, path.with_suffix(".json"))
    path.with_suffix(".md").write_text(markdown(value))
    path.with_suffix(".html").write_text(offline_html(value))
    return value


def markdown(value):
    if "uncertainty" in value:
        from methane.uncertainty_studies import markdown as uncertainty_markdown

        return uncertainty_markdown(value)
    if value["schema_version"] == "dispatch-lab/study-report/2":
        from methane.field_studies import markdown as field_markdown

        return field_markdown(value)
    m = value["manifest"]
    p = m["protocol"]
    lines = [
        f"# {p['title']}",
        "",
        p["question"],
        "",
        "## Finding",
        "",
        value["finding"],
        "",
        f"{value['completed_pairs']}/{value['total_pairs']} complete pairs. {value['interpretation_status']}.",
        "",
        *(
            [
                "## Interpretation",
                "",
                "\n\n".join(value["interpretation"]["paragraphs"]),
                "",
                value["interpretation"]["scope"],
                "",
            ]
            if value.get("interpretation")
            else []
        ),
        "## Method",
        "",
        p["rationale"],
        "",
        p["comparison"],
        "",
        p["policy_tuning"],
        "",
        *[f"- **{k.replace('_', ' ')}:** {v}" for k, v in p["resolution"].items()],
        "",
        f"Tier: {m['tier']}. Protocol revision {p['revision']}. Source: `{m['source_hash']}`.",
        "",
        "## Paired outcomes",
        "",
        "| Case | Status | Methane difference kg | Ending battery difference kWh | Attempts |",
        "|---|---|---:|---:|---:|",
    ]
    for c in value["cases"]:
        d = c.get("delta")
        numbers = f"{d['methane_kg']:+.3f} | {d['battery_kwh']:+.3f}" if d else "— | —"
        lines.append(
            f"| {c['label']} | {c['entry']['status']} | {numbers} | {len(c['attempts'])} |"
        )
    lines += [
        "",
        "## Limits",
        "",
        *[f"- {s}" for s in p["limits"]],
        "",
        value["scope"],
        "",
        "## Reproduce or extend",
        "",
        "The manifest freezes every resolved configuration, policy and weather input. Source and dependency locks are preserved. Recorded playback does not solve again. A numerical rerun can diverge because of time-limited optimization. See the reproduction bundle instructions.",
    ]
    return "\n".join(lines) + "\n"


def offline_html(value, playback_links=False):
    from markdown_it import MarkdownIt

    from methane.study_presentation import metric

    body = MarkdownIt("commonmark", {"html": False}).enable("table").render(markdown(value))
    # The complete immutable publication stays linked, rather than duplicating
    # every service receipt into a single enormous DOM.
    prefix = value["edition_id"] + "/reports/" if playback_links else ""
    if value.get("report_id"):
        body += (
            '<p><a href="'
            + html.escape(prefix + value["report_id"] + ".json", quote=True)
            + '">Complete original publication, calculations and service records (JSON)</a></p>'
        )
    body += "<h2>Selected recorded metrics and case inputs</h2>"
    for c in value["cases"]:
        if playback_links and c["entry"].get("archive"):
            body += f'<p><a href="playback/{c["case_id"]}/playback.html">Open recorded playback: {html.escape(c["label"])}</a></p>'
        entry = c["entry"]
        if entry.get("attempt_id"):
            attempt = f"attempts/{entry['attempt_id']}/case-{c['case_id']}.json"
            link = value["edition_id"] + "/" + attempt if playback_links else "../" + attempt
            body += f'<p><a href="{html.escape(link, quote=True)}">Full original case attempt: {html.escape(c["label"])}</a></p>'
        metrics = {name: metric(m) for name, m in (entry.get("metrics") or {}).items()}
        body += f"<h3>{html.escape(c['label'])}</h3><pre>{html.escape(json.dumps({'metrics': metrics, 'events': entry.get('events'), 'attempts': c['attempts'], 'configuration': c['config'], 'policies': c.get('policies'), 'uncertainty_world': c.get('uncertainty_world')}, ensure_ascii=False, indent=2))}</pre>"
    body = body.replace(
        "<table>",
        '<div class="table-scroll" tabindex="0" aria-label="Scrollable recorded results"><table>',
    ).replace("</table>", "</table></div>")
    return (
        '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Dispatch Lab study</title><style>body{max-width:1000px;margin:40px auto;padding:0 22px;color:#222;font:17px/1.65 Georgia,serif}h1,h2,h3,table{font-family:system-ui,sans-serif}h1{line-height:1.2}table{width:100%;border-collapse:collapse;font-size:13px}td,th{border-bottom:1px solid #ccc;padding:10px;text-align:left}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:12px/1.5 monospace;background:#f4f4f4;padding:18px}h2{margin-top:48px}.table-scroll{overflow-x:auto;margin:24px 0}.table-scroll:focus-visible{outline:2px solid currentColor;outline-offset:3px}code{overflow-wrap:anywhere}</style>'
        + body
        + "</html>"
    )


def list_editions(root=STORE):
    from methane.study_presentation import publications

    rows = []
    worker = active_worker(root)
    for path in Path(root).glob("*/manifest.json"):
        try:
            m = read_manifest(path.parent.name, root)
            published = publications(m["edition_id"], root)
            r = published[0] if published else report(m["edition_id"], root)
            progress_path = path.parent / "progress.json"
            progress = json.loads(progress_path.read_text()) if progress_path.exists() else {}
            status = r["status"]
            if progress.get("status") == "running":
                status = (
                    "running"
                    if worker and worker["edition_id"] == m["edition_id"]
                    else "interrupted"
                )
            if withdrawal(m["edition_id"], root):
                status = "withdrawn"
            rows.append(
                {
                    k: m[k]
                    for k in (
                        "edition_id",
                        "created_at",
                        "tier",
                        "action",
                        "parent_edition_id",
                        "source_hash",
                    )
                }
                | {
                    "title": m["protocol"]["title"],
                    "study_id": m["protocol"]["study_id"],
                    "completed_cases": r.get("completed_cases"),
                    "total_cases": r.get("total_cases"),
                    "completed_pairs": r["completed_pairs"],
                    "total_pairs": r["total_pairs"],
                    "status": status,
                    "summary_scope": "latest-publication" if published else "current-attempts",
                    "report_id": r.get("report_id"),
                }
            )
        except (ValueError, OSError, KeyError) as exc:
            rows.append(
                {"edition_id": path.parent.name, "status": "unavailable", "error": str(exc)}
            )
    return sorted(rows, key=lambda r: r.get("created_at", ""), reverse=True)


def active_worker(root=STORE):
    """The inherited OS lock survives app restarts and releases on worker exit."""
    root = Path(root)
    if not (root / ".execution.lock").exists():
        return None
    with (root / ".execution.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            lease = root / "worker.json"
            return json.loads(lease.read_text()) if lease.exists() else {"edition_id": None}
    return None


def launch(identifier, root=STORE, fresh=False):
    if withdrawal(identifier, root):
        raise ValueError("A withdrawn edition cannot be resumed; use the replacement protocol")
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".execution.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise ValueError("A study is already running in this store") from exc
        worker = _launch(identifier, root, fresh, lock.fileno())
        atomic(root / "worker.json", {"edition_id": identifier, "pid": worker.pid})
        # No explicit unlock: the child retains the inherited open file descriptor.
        return worker


def _launch(identifier, root, fresh, lock_fd):
    m = read_manifest(identifier, root)
    directory = location(identifier, root).resolve()
    capsule = json.loads((directory / "source-capsule.json").read_text())
    if capsule["sha256"] != m["source_capsule_sha256"]:
        raise ValueError("Frozen source identity mismatch")
    source = prepare_source(directory, capsule)
    (directory / "cancel").unlink(missing_ok=True)
    atomic(
        directory / "progress.json",
        {"status": "running", "fraction": 0, "description": "Starting frozen study execution"},
    )
    env = {
        **os.environ,
        "PYTHONPATH": str(source),
        "OMP_NUM_THREADS": "1",
        "OPENBLAS_NUM_THREADS": "1",
        "MKL_NUM_THREADS": "1",
        "VECLIB_MAXIMUM_THREADS": "1",
        "DISPATCH_BATCH_WORKER": "1",
    }
    args = [sys.executable, "-m", "methane.study_worker", str(directory)] + (
        ["--fresh"] if fresh else []
    )
    with (directory / ("worker-" + uuid.uuid4().hex + ".log")).open("w") as log:
        return subprocess.Popen(
            args, cwd=source, env=env, stdout=log, stderr=log, pass_fds=(lock_fd,)
        )


def export(identifier, destination, root=STORE, report_id=None):
    import posixpath

    from methane.bundle import playback
    from methane.evidence import publish_completed, staging
    from methane.offline_model import pages

    directory = location(identifier, root)
    if withdrawal(identifier, root):
        raise ValueError(
            "This study was withdrawn. Its original records remain in the study store."
        )
    value = stored_report(identifier, root, report_id)
    capsule = json.loads((directory / "source-capsule.json").read_text())
    source = decode(capsule)
    with (
        staging(destination) as temporary,
        zipfile.ZipFile(temporary, "w", zipfile.ZIP_DEFLATED) as z,
    ):
        for path in directory.rglob("*"):
            if (
                path.is_file()
                and path.resolve() not in (temporary.resolve(), Path(destination).resolve())
                and "__pycache__" not in path.parts
                and path.suffix != ".log"
                and path.name != "cancel"
            ):
                z.write(path, identifier + "/" + str(path.relative_to(directory)))
        z.writestr("study.html", offline_html(value, playback_links=True))
        z.writestr("study.md", markdown(value))
        z.writestr("model-report-source.json", json.dumps(LOADED_CAPSULE, allow_nan=False))
        for c in value["cases"]:
            if c["entry"].get("archive"):
                result = archive_for(identifier, c["entry"], root)
                z.writestr(f"playback/{c['case_id']}/playback.html", playback(result, source))
                prefix = f"playback/{c['case_id']}"
                archive_href = posixpath.relpath(identifier + "/" + c["entry"]["archive"], prefix)
                for name, data in pages(
                    result,
                    archive_href=archive_href,
                    source_href="../../model-report-source.json",
                    include_source=False,
                ):
                    z.writestr(prefix + "/" + name, data)
        z.writestr(
            "README.txt",
            f"""Dispatch Lab study reproduction bundle

Open study.html for the preserved write-up and metrics, without network access.
Recorded playback for each executed case is in playback/. It never reruns a solver.
Each playback directory also contains model-report.html and linked model/ reading pages.
Their current reading/calculation source is shared in model-report-source.json;
it does not replace the numerical run's original source or explanations.
The original edition (manifest, inputs, attempts, reports and source) is in {identifier}/.
New report revisions can use a separately identified reporting implementation.
Their reporting/ capsules preserve the code that derived those tables; they do
not replace the numerical run's original source. Older reports without this
metadata make no claim to an original reporting-source snapshot.
Check hashes and independent balances with only the Python standard library:
  python -I -S check_study.py .
Restore its recorded dependencies using its source/uv.lock. Offline restoration needs cached packages.
To make a NEW edition with the original protocol, inputs and source:
  cd {identifier}/source
  uv sync --locked --offline --no-dev
  .venv/bin/python -m methane.studies --root ../.. reproduce {identifier}
Time-limited solves and hardware may change numerical decisions; the new edition records differences.
All coefficients are illustrative. Numerical checks are not empirical calibration.
""",
        )
        z.writestr("checker/reference.py", source["methane/reference.py"])
        if "methane/recovery_belief_reference.py" in source:
            z.writestr(
                "checker/recovery_belief_reference.py",
                source["methane/recovery_belief_reference.py"],
            )
        for companion in (
            "recovery_loop_reference.py",
            "autonomy_reference.py",
            "duration_reference.py",
            "performance_reference.py",
        ):
            if "methane/" + companion in source:
                z.writestr("checker/" + companion, source["methane/" + companion])
        z.writestr("check_study.py", LOADED_FILES["methane/study_bundle_check.py"])
        inventory = {
            i.filename: hashlib.sha256(z.read(i.filename)).hexdigest() for i in z.infolist()
        }
        z.writestr(
            "bundle.json",
            json.dumps(
                {
                    "schema_version": "dispatch-lab/study-bundle/1",
                    "edition_id": identifier,
                    "report_id": value.get("report_id"),
                    "files": inventory,
                    "archives": [
                        {
                            "path": identifier + "/" + c["entry"]["archive"],
                            "status": c["entry"]["status"],
                        }
                        for c in value["cases"]
                        if c["entry"].get("archive")
                    ],
                },
                indent=2,
            ),
        )
        z.close()
        return publish_completed(temporary, destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=STORE)
    commands = parser.add_subparsers(dest="command", required=True)
    new = commands.add_parser("create")
    new.add_argument("--tier", choices=("smoke", "reference", "sensitivity"), default="reference")
    new.add_argument("--config", type=Path)
    new.add_argument("--protocol", choices=tuple(PROTOCOLS))
    new.add_argument("--protocol-file", type=Path)
    for name in ("run", "reproduce", "report"):
        sub = commands.add_parser(name)
        sub.add_argument("edition")
        if name == "run":
            sub.add_argument("--fresh", action="store_true")
    args = parser.parse_args()
    if args.command == "create":
        basis = json.loads(args.config.read_text()) if args.config else None
        value = create(
            basis,
            args.tier,
            action="current-plant" if basis else "reference",
            root=args.root,
            protocol_id=args.protocol,
            specification=json.loads(args.protocol_file.read_text())
            if args.protocol_file
            else None,
        )
        print(value["edition_id"], flush=True)
    elif args.command == "report":
        print(json.dumps(publish(args.edition, args.root), ensure_ascii=False))
    else:
        identifier = (
            create(parent=args.edition, action="reproduce", root=args.root)["edition_id"]
            if args.command == "reproduce"
            else args.edition
        )
        print(identifier, flush=True)
        worker = launch(identifier, args.root, getattr(args, "fresh", False))
        raise SystemExit(worker.wait())


if __name__ == "__main__":
    main()
