"""Repeated seeds are computation trials, with sealed evidence and scoped claims."""

import copy
import hashlib
import json
import zipfile
from dataclasses import replace

import pytest

from methane import studies
from methane.computation_studies import REPORTING, qualify, settings, weather
from methane.config import Config
from methane.provenance import digest


def protocol():
    return studies.protocol("field-computation")


def small():
    spec = protocol()
    spec["conditions"] = spec["conditions"][:1]
    spec["tiers"]["smoke"]["hours"] = 2
    spec["tiers"]["smoke"]["computation"]["budgets"] = spec["tiers"]["smoke"]["computation"][
        "budgets"
    ][:1]
    return spec


def test_distinct_repeats_keep_seeds_and_numerical_inputs_and_apply_only_declared_budgets():
    spec = protocol()
    original = copy.deepcopy(spec)
    cases = studies.resolve_cases(spec, spec["reference_config"], "reference")
    assert len(cases) == len({c["case_id"] for c in cases}) == 36
    groups = {}
    physical = {}
    for c in cases:
        comp = c["computation"]
        groups.setdefault((c["condition"], c["arm_id"], comp["budget"]["id"]), []).append(c)
        physical.setdefault(c["condition"], set()).add(comp["physical_inputs_hash"])
        assert c["seed"] == c["config"]["scenario"]["seed"] == 7
        assert c["config"]["scenario"]["solver_seconds"] == comp["budget"]["process_seconds"]
        p = c["policies"][c["controller"]]
        assert p["service"]["comparison_seconds"] == comp["budget"]["service_seconds"]
        assert p["investigation"]["comparison_seconds"] == comp["budget"]["investigation_seconds"]
    assert all(len(v) == 1 for v in physical.values())
    for members in groups.values():
        assert {c["computation"]["repetition"] for c in members} == {1, 2, 3}
        assert len({digest(c["config"]) for c in members}) == 1
        assert len({c["computation"]["numerical_inputs_hash"] for c in members}) == 1
    assert spec == original


def test_changed_plant_basis_changes_equations_and_keeps_explicit_weather_scope():
    spec = protocol()
    c = Config.from_dict(spec["reference_config"])
    c = replace(c, plant=replace(c.plant, solar_kw=2000, battery_kwh=1600))
    cases = studies.resolve_cases(spec, c.to_dict(), "smoke")
    assert all(r["config"]["plant"]["battery_kwh"] == 1600 for r in cases)
    w = weather(c, spec["weather_fixture"])
    assert {v["pv_kw"] for v in w["truth"].values()} == {1500}
    assert {v["irradiance_wm2"] for v in w["truth"].values()} == {750}
    assert "not site weather" in w["reference"]
    assert studies.complete_config(json.loads(json.dumps(c.to_dict()))) == studies.complete_config(
        c.to_dict()
    )
    incomplete = c.to_dict()
    del incomplete["sensors"]["noise_fraction"]
    with pytest.raises(ValueError, match="implicit defaults"):
        studies.complete_config(incomplete)


@pytest.mark.parametrize("explicit_design", [True, False])
def test_detailed_solar_cannot_silently_change_the_declared_dc_experiment(explicit_design):
    from methane.solar_model import default_design

    spec = protocol()
    c = Config.from_dict(spec["reference_config"])
    if explicit_design:
        c = replace(c, solar=default_design(c.plant, c.weather))
    else:
        c = replace(c, service_system=replace(c.service_system, cleaning_model="section-optical/1"))
    with pytest.raises(ValueError, match="constant-DC"):
        studies.resolve_cases(spec, c.to_dict(), "smoke")
    with pytest.raises(ValueError, match="constant-DC"):
        weather(c, spec["weather_fixture"])


@pytest.mark.parametrize(
    "key,value",
    [
        ("repetitions", 1),
        ("repetitions", True),
        ("repetitions", 2.5),
        ("absolute_tolerance", float("nan")),
        ("absolute_tolerance", 0),
    ],
)
def test_qualification_settings_reject_ambiguous_repetitions_and_tolerances(key, value):
    spec = small()
    spec["tiers"]["smoke"]["computation"][key] = value
    with pytest.raises(ValueError):
        settings(spec, "smoke")


def test_incomplete_or_unmatched_repeats_cannot_appear_stable():
    spec = small()
    cases = studies.resolve_cases(spec, spec["reference_config"], "smoke")
    value = dict(manifest=dict(protocol=spec, tier="smoke", source_hash="source"), cases=cases)
    for c in cases:
        c.update(weather_hash="weather", entry=dict(status="pending"))
    result = qualify(value)
    assert all(
        g["repeatability"] == "incomplete" and g["solve_quality"] == "missing"
        for g in result["groups"]
    )
    for c in cases:
        c["entry"] = dict(
            status="complete",
            computation=dict(
                version=REPORTING,
                source="source",
                weather="weather",
                inputs=c["computation"]["numerical_inputs_hash"],
                vectors=[{"applied": 1}, {"applied": 1}],
                work=["work", "work"],
                solvers=[dict(termination="time-limited", gap=0.5)] * 2,
                selections=[dict(not_evaluated_candidates=0, omissions=[])] * 2,
                elapsed_seconds=1,
            ),
        )
        c["outcomes"] = dict(methane_kg=1, total_eur=2)
    result = qualify(value)
    assert all(g["repeatability"] == "stable in sampled repeats" for g in result["groups"])
    assert all(
        g["solve_quality"] == "limited or fallback solves retained" for g in result["groups"]
    )
    cases[-1]["entry"]["computation"]["inputs"] = "different"
    assert any(g["repeatability"] == "unmatched inputs" for g in qualify(value)["groups"])
    cases[-1]["entry"]["computation"]["inputs"] = cases[-1]["computation"]["numerical_inputs_hash"]
    cases[-1]["entry"]["computation"]["vectors"][0]["applied"] = 2
    different = next(
        g
        for g in qualify(value)["groups"]
        if g["repeatability"] == "different recorded trajectories"
    )
    assert (
        different["first_different_interval"] == 0 and different["maximum_numeric_difference"] == 1
    )
    cases[-1]["entry"]["computation"]["vectors"] = [{"applied": float("nan")}] * 2
    assert any(g["repeatability"] == "incomplete" for g in qualify(value)["groups"])
    # Equal, finite prefixes are still not complete repeated executions.
    for c in cases:
        c["entry"]["computation"]["vectors"] = [{"applied": 1}]
    assert all(g["repeatability"] == "incomplete" for g in qualify(value)["groups"])


def test_study_execution_seals_repeatability_evidence_and_preserves_cancel_resume(tmp_path):
    spec = small()
    manifest = studies.create(specification=spec, tier="smoke", root=tmp_path)
    path = studies.location(manifest["edition_id"], tmp_path)
    (path / "cancel").touch()
    cancelled = studies.run_edition(manifest["edition_id"], tmp_path)
    assert all(g["repeatability"] == "incomplete" for g in cancelled["computation"]["groups"])
    (path / "cancel").unlink()
    result = studies.run_edition(manifest["edition_id"], tmp_path)
    assert result["status"] == "complete", result["cases"]
    assert result["archive_verification"]["checked"] == 4
    assert len(result["computation"]["groups"]) == 2
    assert "Computation qualification" in studies.markdown(result)
    case = result["cases"][0]
    recorded = studies.archive_for(manifest["edition_id"], case["entry"], tmp_path)
    assert recorded["study"]["computation"] == case["entry"]["computation"]
    assert case["entry"]["computation"]["inputs"] == case["computation"]["numerical_inputs_hash"]
    corrupt = copy.deepcopy(case["entry"])
    corrupt["computation"]["vectors"][0]["applied.methane_kg"] += 1
    with pytest.raises(ValueError, match="sealed original"):
        studies.archive_for(manifest["edition_id"], corrupt, tmp_path)
    corrupt.pop("computation")
    with pytest.raises(ValueError, match="sealed original"):
        studies.archive_for(manifest["edition_id"], corrupt, tmp_path)
    from methane.study_bundle_check import check

    archive = studies.export(manifest["edition_id"], tmp_path / "bundle.zip", tmp_path)
    restored = tmp_path / "restored"
    with zipfile.ZipFile(archive) as z:
        z.extractall(restored)
    checked = check(restored)
    assert checked["complete_archives_passed"]
    assert all(c["computation_summary"] == "matched" for c in checked["archives"])
    inventory = json.loads((restored / "bundle.json").read_text())
    name = f"{manifest['edition_id']}/reports/{inventory['report_id']}.json"
    path = restored / name
    saved = json.loads(path.read_text())
    saved["cases"][0]["entry"]["computation"]["vectors"][0]["applied.methane_kg"] += 1
    path.write_text(json.dumps(saved))
    # File hashes alone cannot establish the relationship to the original run.
    inventory["files"][name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (restored / "bundle.json").write_text(json.dumps(inventory))
    with pytest.raises(ValueError, match="sealed original"):
        check(restored)
