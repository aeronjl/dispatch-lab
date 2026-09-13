import copy
import hashlib
import json
import math
import subprocess
import sys
from dataclasses import replace

import numpy as np
import pytest

from methane import studies
from methane.config import Config, Costs, Plant, Scenario
from methane.dispatch import plan, prepare_model
from methane.physics import State
from methane.policy import Policy
from methane.provenance import digest


@pytest.fixture
def small_protocol(monkeypatch):
    spec = studies.protocol()
    spec["tiers"]["smoke"].update(hours=2, seeds=[42], battery_factors=[1], solver_seconds=0.05)
    spec["conditions"] = spec["conditions"][:1]
    monkeypatch.setattr(studies, "protocol", lambda: copy.deepcopy(spec))
    return spec


def test_resolved_parameters_have_explicit_scaling_and_no_defaults():
    spec = studies.protocol()
    basis = Config(plant=replace(Plant(), initial_soc=0.5)).to_dict()
    cases = studies.resolve_cases(spec, basis, "reference")
    assert len(cases) == 12
    assert {c["resolved_battery"]["power_kw"] for c in cases} == {400}
    assert {c["resolved_battery"]["capacity_kwh"] for c in cases} == {800, 1600}
    assert {c["resolved_battery"]["initial_kwh"] for c in cases} == {400, 800}
    assert all(c["config"]["scenario"]["capacity_fraction"] == 1 for c in cases)
    missing = copy.deepcopy(basis)
    del missing["plant"]["initial_soc"]
    with pytest.raises(ValueError, match="implicit defaults"):
        studies.resolve_cases(spec, missing, "reference")
    assert spec["reference_config"] == Config().to_dict()


def test_signed_comparison_uses_identities_after_json_sorting(
    tmp_path, small_protocol, monkeypatch
):
    manifest = studies.create(tier="smoke", root=tmp_path)
    # Candidate alphabetically precedes baseline; JSON sorting must not invert the effect.
    original = {
        "MPC · methane": {
            "methane_kg": 40,
            "ending": {"battery_kwh": 10},
            "forced_downtime_hours": 2,
        },
        "MPC · battery reserve": {
            "methane_kg": 35,
            "ending": {"battery_kwh": 90},
            "forced_downtime_hours": 1,
        },
    }
    for metrics in (original, json.loads(json.dumps(original, sort_keys=True))):
        monkeypatch.setattr(
            studies,
            "history",
            lambda *args, metrics=metrics: {
                manifest["cases"][0]["case_id"]: [{"status": "complete", "metrics": metrics}]
            },
        )
        value = studies.report(manifest["edition_id"], tmp_path)
        assert value["cases"][0]["delta"] == {
            "methane_kg": -5,
            "battery_kwh": 80,
            "forced_downtime_hours": -1,
        }
        assert "5.00 kg less methane" in value["finding"]
    studies.write_once(
        studies.location(manifest["edition_id"], tmp_path) / "withdrawal.json",
        {"reason": "Regression fixture"},
    )
    withdrawn = studies.report(manifest["edition_id"], tmp_path)
    assert withdrawn["status"] == "withdrawn" and not withdrawn["aggregate"]
    assert "delta" not in withdrawn["cases"][0]


def test_terminal_policy_changes_only_objective_and_has_independent_optimum():
    p = replace(
        Plant(),
        battery_kwh=100,
        initial_h2_kg=5,
        heat_loss_kw_per_k=0,
        heater_max_kw=0,
        cooling_max_kw=0,
        minimum_run_hours=1,
    )
    state = State.initial(p, 300)
    forecast = dict(pv_kw=[12], ambient_c=[20], deliveries_kg=[0])
    base = prepare_model(p, state, forecast, 0, Costs())
    alternative = prepare_model(p, state, forecast, 0, Costs(), terminal_battery_value=0.01)
    for key in ("lower", "upper", "integer", "rows", "cols", "values", "lo", "hi"):
        assert np.array_equal(getattr(base, key), getattr(alternative, key))
    delta = alternative.objective - base.objective
    assert np.count_nonzero(delta) == 1
    assert delta[base.ids["battery_kwh"][-1]] == -0.01
    # 5 kg H2 enables 10 kg CH4, consuming exactly 12 kWh. At a deliberately
    # high terminal value of 1 kg/kWh, storing 12*sqrt(.9) is worth more than 10 kg.
    plain = plan(p, state, forecast, 0, Costs(), seconds=2)
    reserve = plan(p, state, forecast, 0, Costs(), seconds=2, terminal_battery_value=1)
    assert plain["predicted"]["methane_kg"] == pytest.approx(10)
    assert reserve["predicted"]["methane_kg"] == 0
    assert reserve["predicted"]["ending"]["battery_kwh"] == pytest.approx(12 * math.sqrt(0.9))
    assert reserve["predicted"]["assumed_value_eur"] == 0
    with pytest.raises(ValueError):
        Policy(objective="economics", terminal_battery_value_kg_per_kwh=0.01)


def test_policy_is_recorded_and_retained_in_what_if(monkeypatch):
    from methane import simulation
    from methane.simulation import run, what_if

    policies = {"reserve": Policy(terminal_battery_value_kg_per_kwh=0.01).to_dict()}
    result = run(
        Config(scenario=Scenario(hours=2, horizon_hours=6, solver_seconds=0.05)),
        strategies=list(policies),
        policies=policies,
    )
    assert result["provenance"]["controller_policies"] == policies
    assert result["records"]["reserve"][0]["decision"]["controller_policy"] == policies["reserve"]
    original = digest(result)
    calls = []
    original_plan = simulation.plan

    def capture(*args, **kwargs):
        calls.append(kwargs)
        return original_plan(*args, **kwargs)

    monkeypatch.setattr(simulation, "plan", capture)
    alternative = what_if(result, "reserve", 0, "battery")
    assert calls and calls[0]["terminal_battery_value"] == 0.01
    assert (
        alternative["cost_version"] == result["records"]["reserve"][0]["decision"]["cost_version"]
    )
    assert digest(result) == original


def test_study_context_is_scoped_and_preview_does_not_change_inputs():
    from fastapi import HTTPException

    from methane.study_service import Request, handle, register

    original = {"run_id": "context-a", "config": Config().to_dict()}
    token = register(original)
    before = digest(original)
    response = handle(
        Request(
            token=token,
            run_id="context-a",
            key="selection-3",
            operation="preview",
            basis="current-plant",
            tier="reference",
        )
    )
    assert response["key"] == "selection-3"
    assert response["preview"]["pairs"] == 12
    assert response["preview"]["batteries"][1]["power_kw"] == 400
    assert digest(original) == before
    with pytest.raises(HTTPException) as error:
        handle(Request(token=token, run_id="context-b", key="wrong-run"))
    assert error.value.status_code == 410
    legacy = copy.deepcopy(original)
    del legacy["config"]["models"]
    del legacy["config"]["rng_policy"]
    legacy_response = handle(
        Request(
            token=register(legacy),
            run_id="context-a",
            key="legacy",
            operation="preview",
            basis="current-plant",
            tier="reference",
        )
    )
    resolution = legacy_response["preview"]["basis_origin"]
    assert resolution["original_config_hash"] == digest(legacy["config"])
    assert {d["parameter"] for d in resolution["resolved_legacy_fields"]} == {
        "models",
        "rng_policy",
    }


def test_source_inputs_editions_and_reports_are_preserved(tmp_path, small_protocol):
    first = studies.create(tier="smoke", root=tmp_path)
    identifier = first["edition_id"]
    folder = studies.location(identifier, tmp_path)
    before = (folder / "manifest.json").read_bytes()
    worker = studies.launch(identifier, tmp_path)
    assert studies.active_worker(tmp_path)["edition_id"] == identifier
    with pytest.raises(ValueError, match="already running"):
        studies.launch(identifier, tmp_path)
    assert worker.wait(timeout=60) == 0, list(folder.glob("*.log"))
    assert studies.active_worker(tmp_path) is None
    report = studies.stored_report(identifier, tmp_path)
    assert report["completed_pairs"] == report["total_pairs"] == 1
    entry = studies.entry_for(identifier, first["cases"][0]["case_id"], tmp_path)
    record = studies.archive_for(identifier, entry, tmp_path)
    assert record["provenance"]["controller_policies"] == small_protocol["policies"]
    assert (
        hashlib.sha256((folder / entry["independent_audit"]["artifact"]).read_bytes()).hexdigest()
        == entry["independent_audit"]["artifact_sha256"]
    )
    original_report = (folder / "reports" / (report["report_id"] + ".json")).read_bytes()
    reviewed = studies.publish_interpretation(
        identifier,
        report["report_id"],
        ["Two hours do not evaluate a full solar cycle."],
        "Automated integration fixture",
        tmp_path,
    )
    assert reviewed["interpretation"]["source_report_id"] == report["report_id"]
    assert reviewed["cases"] == report["cases"]
    assert "Two hours do not evaluate" in studies.markdown(reviewed)
    # Resume reuses a complete verified attempt; fresh trial records another attempt.
    assert studies.launch(identifier, tmp_path).wait(timeout=60) == 0
    assert len(studies.history(identifier, tmp_path)[entry["case_id"]]) == 1
    assert studies.launch(identifier, tmp_path, fresh=True).wait(timeout=60) == 0
    assert len(studies.history(identifier, tmp_path)[entry["case_id"]]) == 2
    assert studies.entry_for(identifier, entry["case_id"], tmp_path, entry["attempt_id"]) == entry
    assert (folder / "reports" / (report["report_id"] + ".json")).read_bytes() == original_report
    assert (folder / "manifest.json").read_bytes() == before
    assert (
        studies.stored_report(identifier, tmp_path, report["report_id"])["cases"][0]["entry"][
            "attempt_id"
        ]
        == entry["attempt_id"]
    )
    second = studies.create(parent=identifier, action="reproduce", root=tmp_path)
    assert second["edition_id"] != identifier
    assert second["cases"] == first["cases"]
    assert second["source_capsule_sha256"] == first["source_capsule_sha256"]
    assert studies.launch(second["edition_id"], tmp_path).wait(timeout=60) == 0
    rerun = studies.entry_for(second["edition_id"], entry["case_id"], tmp_path)
    assert "numerical_comparison" in rerun


def test_cancellation_and_failed_inputs_remain_visible(tmp_path, small_protocol):
    manifest = studies.create(tier="smoke", root=tmp_path)
    folder = studies.location(manifest["edition_id"], tmp_path)
    (folder / "cancel").touch()
    cancelled = studies.run_edition(manifest["edition_id"], tmp_path)
    assert cancelled["completed_pairs"] == 0
    assert cancelled["cases"][0]["entry"]["status"] == "cancelled"
    assert "delta" not in cancelled["cases"][0]
    (folder / "cancel").unlink()
    weather = folder / "inputs" / (manifest["cases"][0]["weather_hash"] + ".json")
    weather.write_text("{}")
    failed = studies.run_edition(manifest["edition_id"], tmp_path)
    assert failed["cases"][0]["entry"]["status"] == "failed"
    assert failed["aggregate"] == []
    assert len(failed["cases"][0]["attempts"]) == 2


def test_portable_study_checks_without_packages(tmp_path, small_protocol):
    from methane.bundle import unpack

    manifest = studies.create(tier="smoke", root=tmp_path / "store")
    identifier = manifest["edition_id"]
    assert studies.launch(identifier, tmp_path / "store").wait(timeout=60) == 0
    bundle = studies.export(identifier, tmp_path / "study.zip", tmp_path / "store")
    root = unpack(bundle, tmp_path / "unpacked")
    completed = subprocess.run(
        [sys.executable, "-I", "-S", str(root / "check_study.py"), str(root)],
        text=True,
        capture_output=True,
        check=True,
    )
    result = json.loads(completed.stdout)
    assert result["integrity_passed"] and result["complete_archives_passed"]
    assert list((root / "playback").glob("*/model-report.html"))
    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE

    assert json.loads((root / "model-report-source.json").read_text()) == LOADED_CAPSULE
    for metadata in (root / "playback").glob("*/model/manifest.json"):
        pages = json.loads(metadata.read_text())
        assert pages["renderer_source"] == LOADED_SOURCE["content_hash"]
        assert (metadata.parent.parent / pages["source_href"]).resolve() == (
            root / "model-report-source.json"
        )
        assert (metadata.parent.parent / pages["archive_href"]).is_file()
        assert pages["original_recording_integrity"]
    assert 'href="playback/' in (root / "study.html").read_text()
    (root / "study.md").write_text("modified")
    tampered = subprocess.run(
        [sys.executable, "-I", "-S", str(root / "check_study.py"), str(root)],
        text=True,
        capture_output=True,
    )
    assert tampered.returncode != 0
    assert "Modified bundle member: study.md" in tampered.stderr


def test_manifest_and_frozen_source_tampering_is_rejected(tmp_path, small_protocol):
    manifest = studies.create(tier="smoke", root=tmp_path)
    folder = studies.location(manifest["edition_id"], tmp_path)
    (folder / "source/methane/policy.py").write_text('raise RuntimeError("changed")')
    with pytest.raises(ValueError, match="modified"):
        studies.launch(manifest["edition_id"], tmp_path)
    value = json.loads((folder / "manifest.json").read_text())
    value["cases"][0]["config"]["plant"]["battery_kwh"] = 1
    (folder / "manifest.json").write_text(json.dumps(value))
    with pytest.raises(ValueError, match="integrity"):
        studies.read_manifest(manifest["edition_id"], tmp_path)
