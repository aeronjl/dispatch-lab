import copy
import json
import subprocess
import sys
import zipfile
from dataclasses import replace

import pytest

from methane import studies
from methane.config import Config, Plant
from methane.field_studies import matching_inputs
from methane.provenance import digest


def small_protocol():
    spec = studies.protocol("field-recovery")
    spec["conditions"] = spec["conditions"][:1]
    spec["tiers"]["smoke"].update(hours=2, seeds=[7])
    return spec


def test_repeated_identical_inputs_keep_distinct_case_archives_and_publication_gate(tmp_path):
    from methane.evidence import load

    spec = small_protocol()
    spec["arms"] = spec["arms"][:2]
    spec["tiers"]["smoke"]["variants"] = [
        {"id": "repeat-1", "label": "First execution", "patch": {}},
        {"id": "repeat-2", "label": "Second execution", "patch": {}},
    ]
    manifest = studies.create(specification=spec, tier="smoke", root=tmp_path)
    identifier = manifest["edition_id"]
    report = studies.run_edition(identifier, tmp_path)
    assert report["status"] == "complete" and report["completed_cases"] == 4
    assert report["archive_verification"]["checked"] == 4
    cases = report["cases"]
    paths = [studies.location(identifier, tmp_path) / c["entry"]["archive"] for c in cases]
    assert len(set(paths)) == 4
    records = [load(path) for path in paths]
    assert len({r["run_id"] for r in records}) < 4
    assert len({r["integrity_sha256"] for r in records}) == 4
    for c in cases:
        assert (
            studies.archive_for(identifier, c["entry"], tmp_path)["study"]["case_id"]
            == c["case_id"]
        )
    # A valid recording belonging to another case must not make a publication
    # appear complete. The previous immutable publication remains readable.
    original_publications = set((studies.location(identifier, tmp_path) / "reports").glob("*.json"))
    paths[0].write_bytes(paths[1].read_bytes())
    with pytest.raises(ValueError, match="identity mismatch"):
        studies.publish(identifier, tmp_path)
    assert (
        set((studies.location(identifier, tmp_path) / "reports").glob("*.json"))
        == original_publications
    )


def test_support_protocol_matches_physics_separately_from_recovery_permission():
    spec = studies.protocol("field-support")
    assert spec["revision"] == 3
    cases = studies.resolve_cases(spec, spec["reference_config"], "smoke")
    assert {c["config"]["faults"]["hardware_model"] for c in cases} == {"actuator-interlock/1"}
    assert {c["config"]["service_system"]["outcome_randomness"] for c in cases} == {
        "target-action-request/1"
    }
    assert {c["config"]["service_system"]["equipment_recovery_enabled"] for c in cases} == {
        False,
        True,
    }
    groups = {}
    for case in cases:
        groups.setdefault(case["group_id"], set()).add(case["matching_inputs_hash"])
    assert all(len(values) == 1 for values in groups.values())


def test_field_resolution_freezes_separate_arms_and_shared_background():
    spec = studies.protocol("field-recovery")
    basis = Config(plant=replace(Plant(), battery_kwh=1400)).to_dict()
    before = digest([spec, basis])
    cases = studies.resolve_cases(spec, basis, "reference")
    assert len(cases) == len({c["case_id"] for c in cases}) == 48
    groups = {}
    for c in cases:
        assert c["config"] == Config.from_dict(c["config"]).to_dict()
        assert c["config"]["plant"]["battery_kwh"] == 1400
        assert list(c["policies"]) == [c["controller"]]
        assert digest(matching_inputs(c["config"])) == c["matching_inputs_hash"]
        assert any(d["parameter"] == "service_economics" for d in c["changes_from_basis"])
        groups.setdefault(c["group_id"], []).append(c)
    assert len(groups) == 12
    for members in groups.values():
        assert len({c["matching_inputs_hash"] for c in members}) == 1
        assert len({c["arm_id"] for c in members}) == 4
        assert len({digest(c["config"]) for c in members}) == 4
    assert digest([spec, basis]) == before


@pytest.mark.parametrize(
    "path,value,reason",
    [
        ("scenario.seed", 99, "shared plant/weather"),
        ("faults.capacity_cause", "resettable-trip", "shared plant/weather"),
        ("faults.hardware_model", "actuator-interlock/1", "shared plant/weather"),
        ("field_operations.enabled", False, "environmental mechanism"),
        ("field_operations.initial_soiling_fraction", 0.01, "shared environmental"),
        ("service_system.initial_damage_fraction", 0.2, "shared environmental"),
        ("service_system.outcome_randomness", "target-action-request/1", "shared environmental"),
        ("service_system.nonexistent", 7, "Unknown study parameter"),
    ],
)
def test_arm_cannot_gain_an_unmatched_environment_or_unknown_defaults(path, value, reason):
    spec = small_protocol()
    spec["arms"][1]["patch"][path] = value
    with pytest.raises(ValueError, match=reason):
        studies.resolve_cases(spec, spec["reference_config"], "smoke")


def test_duplicate_ids_and_partial_policies_are_rejected():
    spec = small_protocol()
    spec["arms"][1]["id"] = spec["arms"][0]["id"]
    with pytest.raises(ValueError, match="Duplicate"):
        studies.resolve_cases(spec, spec["reference_config"], "smoke")
    spec = small_protocol()
    del spec["policies"]["Greedy"]["version"]
    with pytest.raises(ValueError, match="implicit defaults"):
        studies.resolve_cases(spec, spec["reference_config"], "smoke")


def test_field_preview_is_scoped_and_does_not_reuse_the_battery_resolver():
    from methane.study_service import Request, handle, register

    source = {"run_id": "field-preview", "config": Config().to_dict()}
    before = digest(source)
    token = register(source)
    result = handle(
        Request(
            token=token,
            run_id=source["run_id"],
            key="new-question",
            operation="preview",
            protocol_id="field-recovery",
            tier="smoke",
        )
    )
    p = result["preview"]
    assert p["kind"] == "field" and p["cases"] == 16 and p["pairs"] == 12
    assert len(p["arms"]) == 4 and p["batteries"] == []
    assert len(p["resolved_cases"]) == 16
    assert digest(source) == before and result["key"] == "new-question"


def test_field_editions_execute_cancel_resume_trace_reproduce_and_export(tmp_path, monkeypatch):
    from methane.study_service import Request, handle, register

    spec = small_protocol()
    # A used asset has an unknown quote: physical results stay complete, monetary
    # differences stay undefined rather than turning into a free robot.
    spec["arms"][-1]["patch"]["service_economics.assets.rover.capital_eur"] = None
    m = studies.create(specification=spec, tier="smoke", root=tmp_path)
    identifier = m["edition_id"]
    directory = studies.location(identifier, tmp_path)
    assert len({c["weather_hash"] for c in m["cases"]}) == 1
    before = (directory / "manifest.json").read_bytes()
    (directory / "cancel").touch()
    cancelled = studies.run_edition(identifier, tmp_path)
    assert cancelled["status"] == "incomplete" and cancelled["completed_cases"] == 0
    assert all(c["entry"]["status"] == "cancelled" for c in cancelled["cases"])
    worker = studies.launch(identifier, tmp_path)
    assert worker.wait(timeout=90) == 0
    report = studies.stored_report(identifier, tmp_path)
    assert report["status"] == "complete", [
        (c["arm_id"], c["entry"].get("error")) for c in report["cases"]
    ]
    assert report["completed_cases"] == 4 and report["completed_pairs"] == 3
    assert all(len(c["attempts"]) == 2 for c in report["cases"])
    for c in report["cases"]:
        r = studies.archive_for(identifier, c["entry"], tmp_path)
        assert r["provenance"]["controller_policies"] == c["policies"]
        assert r["config"] == c["config"]
        assert c["entry"]["independent_audit"]["passed"]
    unknown = next(c for c in report["comparisons"] if c["arm_id"] == "rover-assisted")
    assert unknown["delta"]["total_eur"] is None
    assert unknown["delta"]["methane_kg"] == 0
    aggregate = next(g for g in report["aggregate"] if g["arm_id"] == "rover-assisted")
    assert aggregate["metrics"]["total_eur"]["available_pairs"] == 0
    assert aggregate["metrics"]["methane_kg"]["available_pairs"] == 1
    assert "Undefined" in studies.markdown(report)
    # Reuse does not create fake attempts; numerical reproduction has separate identity.
    assert studies.launch(identifier, tmp_path).wait(timeout=90) == 0
    assert all(len(a) == 2 for a in studies.history(identifier, tmp_path).values())
    reproduced = studies.create(parent=identifier, action="reproduce", root=tmp_path)
    assert (
        reproduced["cases"] == m["cases"]
        and reproduced["source_capsule_sha256"] == m["source_capsule_sha256"]
    )
    assert studies.launch(reproduced["edition_id"], tmp_path).wait(timeout=90) == 0
    rereport = studies.stored_report(reproduced["edition_id"], tmp_path)
    assert all(
        c["entry"]["numerical_comparison"]["Greedy"]["different_intervals"] == 0
        for c in rereport["cases"]
    )
    assert (directory / "manifest.json").read_bytes() == before
    with pytest.raises(ValueError, match="parent's protocol"):
        studies.create(
            parent=identifier, action="reproduce", protocol_id="field-recovery", root=tmp_path
        )
    # Calculation transport binds the chosen case and original price identity.
    monkeypatch.setattr(studies, "STORE", tmp_path)
    monkeypatch.setattr(studies, "report", lambda i: report)
    original_entry, original_archive = studies.entry_for, studies.archive_for
    original_calculation = studies.service_calculation_for
    monkeypatch.setattr(
        studies,
        "service_calculation_for",
        lambda i, e, root=tmp_path: original_calculation(i, e, root),
    )
    monkeypatch.setattr(
        studies,
        "entry_for",
        lambda i, c, attempt_id=None: original_entry(i, c, tmp_path, attempt_id),
    )
    monkeypatch.setattr(studies, "archive_for", lambda i, e: original_archive(i, e, tmp_path))
    token = register({"run_id": "viewer", "config": Config().to_dict()})
    c = report["cases"][-1]
    answer = handle(
        Request(
            token=token,
            run_id="viewer",
            key="trace",
            operation="trace",
            edition_id=identifier,
            case_id=c["case_id"],
            controller="Greedy",
            metric="service_allocated_eur",
        )
    )
    assert "trace" in answer, answer
    assert answer["trace"]["value"] is None
    assert answer["trace"]["original_service_cost_version"]
    assert answer["trace"]["calculation"]["views"]["allocated"]["unpriced"]
    # Reading an old calculation does not call today's service pricing implementation.
    from methane import service_economics

    pricing_function = service_economics.report
    monkeypatch.setattr(
        service_economics,
        "report",
        lambda *a, **k: pytest.fail("Saved trace repriced with current code"),
    )
    assert handle(
        Request(
            token=token,
            run_id="viewer",
            key="old-trace",
            operation="trace",
            edition_id=identifier,
            case_id=c["case_id"],
            controller="Greedy",
            metric="service_expenditure_eur",
        )
    )["trace"]["calculation"]
    monkeypatch.setattr(service_economics, "report", pricing_function)
    reference = c["entry"]["service_calculation"]
    calculated_path = directory / reference["artifact"]
    original_bytes = calculated_path.read_bytes()
    calculated_path.write_bytes(b"changed")
    with pytest.raises(ValueError, match="modified"):
        original_calculation(identifier, c["entry"], tmp_path)
    calculated_path.write_bytes(original_bytes)
    # Restore the real helpers before exporting all original attempts and archives.
    monkeypatch.setattr(studies, "entry_for", original_entry)
    monkeypatch.setattr(studies, "archive_for", original_archive)
    archive = studies.export(identifier, tmp_path / "study.zip", tmp_path)
    restored = tmp_path / "restored"
    with zipfile.ZipFile(archive) as z:
        z.extractall(restored)
    result = subprocess.run(
        [sys.executable, "-I", "-S", str(restored / "check_study.py"), str(restored)],
        capture_output=True,
        text=True,
        check=True,
    )
    checked = json.loads(result.stdout)
    assert checked["integrity_passed"] and checked["complete_archives_passed"]
    assert len(checked["archives"]) == 4


def test_missing_or_unmatched_cases_cannot_enter_a_difference(tmp_path, monkeypatch):
    spec = small_protocol()
    m = studies.create(specification=spec, tier="smoke", root=tmp_path)
    identifier = m["edition_id"]
    # No attempts: no artificial zero outcomes or hardware conclusion.
    report = studies.report(identifier, tmp_path)
    assert report["completed_pairs"] == 0
    assert all(not c["delta"] for c in report["comparisons"])
    modified = copy.deepcopy(m)
    modified["cases"][1]["weather_hash"] = "different-weather"
    from methane.field_studies import report as field_report

    mismatch = field_report(modified, {})
    assert any(c["status"] == "unmatched-inputs" for c in mismatch["comparisons"])
    withdrawn = field_report(m, {}, {"reason": "Withdrawn fixture"})
    assert withdrawn["status"] == "withdrawn" and not withdrawn["aggregate"]
    assert all(not c["delta"] for c in withdrawn["comparisons"])


@pytest.mark.parametrize(
    "identifier",
    ["field-cleaning", "field-information", "field-support", "field-provision", "field-interface"],
)
def test_all_field_questions_freeze_valid_matched_cases_at_every_tier(identifier):
    s = studies.protocol(identifier)
    from methane.services.optical import OpticalArray
    from methane.services.plant import PlantServices
    from methane.solar_model import default_design

    c = Config()
    design = default_design(c.plant, c.weather)
    design["sections"][0]["tilt"] = 17
    basis = replace(c, solar=design).to_dict()
    for tier in ("smoke", "reference", "sensitivity"):
        cases = studies.resolve_cases(s, basis, tier)
        groups = {}
        for case in cases:
            assert case["config"] == Config.from_dict(case["config"]).to_dict()
            c = Config.from_dict(case["config"])
            optical = OpticalArray(
                c.plant, c.weather, c.solar, c.field_operations, c.service_system
            )
            runtime = PlantServices(
                c.field_operations,
                c.service_system,
                c.scenario.seed,
                c.plant.electrolyser_kw,
                optical,
            )
            assert runtime.manifest()["asset_ids"] is not None
            groups.setdefault(case["group_id"], []).append(case)
        for members in groups.values():
            assert len({m["matching_inputs_hash"] for m in members}) == 1
            assert len(members) == len(s["arms"])
        assert all(case["config"]["solar"]["sections"][0]["tilt"] == 17 for case in cases)


def test_solar_transforms_preserve_geometry_and_expose_converter_assumption():
    from methane.field_studies import solar_design
    from methane.solar_model import default_design

    c = Config().to_dict()
    c["solar"] = default_design(Config().plant, Config().weather)
    c["solar"]["sections"][0]["tilt"] = 47
    solar_design(c, dict(capacity_factor=0.5, converter_fraction=0.4))
    assert c["plant"]["solar_kw"] == 500
    assert sum(s["capacity_kw"] for s in c["solar"]["sections"]) == 500
    assert c["solar"]["converter_kw"] == 200 and c["solar"]["sections"][0]["tilt"] == 47
    with pytest.raises(ValueError):
        solar_design(c, dict(converter_fraction=float("nan")))
    with pytest.raises(ValueError):
        solar_design(c, dict(converter_fraction=0.5, unknown=True))
    s = small_protocol()
    s["report_metrics"] = ["imaginary-value"]
    with pytest.raises(ValueError, match="supported outcome"):
        studies.resolve_cases(s, s["reference_config"], "smoke")


def test_question_report_preserves_undefined_and_defines_metric_scope():
    from methane.field_studies import markdown, report, values

    s = studies.protocol("field-cleaning")
    s["conditions"] = s["conditions"][:1]
    cases = studies.resolve_cases(s, s["reference_config"], "smoke")
    histories = {}
    for c in cases:
        c["weather_hash"] = "same"
        m = dict(
            methane_kg=5,
            total_eur=None,
            service_work={"orders": []},
            service_outcomes={"cleaning_treated_m2": 100},
        )
        histories[c["case_id"]] = [dict(status="complete", metrics={"Greedy": m})]
    r = report(
        dict(protocol=s, cases=cases, edition_id="example", tier="smoke", source_hash="fixture"),
        histories,
    )
    q = next(q for q in r["question_outcomes"] if q["metric"] == "converter_clipped_kwh")
    assert q["mean"] is None and q["available_pairs"] == 0
    assert "Question-specific outcomes" in markdown(r)
    old = {
        "service_work": {
            "orders": [dict(kind="cleaning", status="completed", verified_at_hour=None)]
        }
    }
    assert values(old)["completed_unverified_orders"] == 1
    old["service_outcomes"] = {"implementation_id": "field-period-outcomes/1"}
    assert values(old)["completed_unverified_orders"] == 0


def test_portable_arm_without_crew_is_rejected_before_saving_an_edition():
    s = studies.protocol("field-cleaning")
    s["arms"][-1]["patch"]["field_operations.human_fallback"] = False
    with pytest.raises(ValueError, match="enabled contracted crew"):
        studies.resolve_cases(s, s["reference_config"], "smoke")


@pytest.mark.parametrize(
    "kind,status,completed,verified,expected",
    [
        ("reset", "awaiting verification", 13.5, None, 1),
        ("module-replacement", "awaiting verification", 27.0, None, 1),
        ("flow-calibration", "completed", 0.0, None, 1),
        ("hardware-replacement", "completed", 12.0, None, 1),
        ("reset", "awaiting verification", None, None, 0),
        ("reset", "verified", 13.5, 15, 0),
        ("reset", "completed", 13.5, 15, 0),
        ("module-replacement", "active", None, None, 0),
        ("module-replacement", "failed", 13.5, None, 0),
        ("module-replacement", "cancelled", 13.5, None, 0),
        ("inspection", "awaiting verification", 13.5, None, 0),
        ("cleaning", "completed", 13.5, None, 0),
        ("routine-service", "completed", 13.5, None, 0),
    ],
)
def test_ended_procedures_awaiting_acceptance_are_not_hidden(
    kind, status, completed, verified, expected
):
    from methane.field_studies import values

    # Public telemetry from a fractional mission; no physical repair outcome is supplied.
    m = {
        "service_outcomes": {"implementation_id": "field-period-outcomes/1"},
        "service_work": {
            "orders": [
                dict(
                    kind=kind,
                    status=status,
                    completed_hour=completed,
                    verified_at_hour=verified,
                )
            ]
        },
    }
    before = copy.deepcopy(m)
    assert values(m)["completed_unverified_orders"] == expected
    assert m == before


def test_report_derivation_preserves_its_source_and_original_publications(tmp_path):
    from methane.field_studies import markdown
    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE
    from methane.source_capsule import decode

    m = studies.create(specification=small_protocol(), tier="smoke", root=tmp_path)
    original_execution = m["source_hash"]
    first = studies.publish(m["edition_id"], tmp_path)
    saved = studies.location(m["edition_id"], tmp_path) / "reports" / (first["report_id"] + ".json")
    original_bytes = saved.read_bytes()
    source = studies.reporting_source(first, tmp_path)
    assert json.loads(source.read_text())["sha256"] == LOADED_CAPSULE["sha256"]
    assert decode(json.loads(source.read_text()))["methane/field_studies.py"]
    assert first["reporting"]["source_hash"] == LOADED_SOURCE["content_hash"]
    assert "Numerical execution retains the source above" in markdown(first)
    authored = studies.publish_interpretation(
        m["edition_id"],
        first["report_id"],
        ["Pending trials; no outcome claimed."],
        "Test",
        tmp_path,
    )
    assert authored["manifest"]["source_hash"] == original_execution
    assert authored["reporting"] == first["reporting"]
    assert saved.read_bytes() == original_bytes
    assert len(list(source.parent.glob("*.json"))) == 1
    # An absent original derivation must not be reconstructed from today's source.
    retained = source.read_bytes()
    source.unlink()
    with pytest.raises(ValueError, match="Original reporting source is unavailable"):
        studies.stored_report(m["edition_id"], tmp_path, first["report_id"])
    source.write_bytes(retained)
    corrupt = json.loads(retained)
    corrupt["payload"] = corrupt["payload"][:-8]
    source.write_text(json.dumps(corrupt))
    with pytest.raises(ValueError, match="capsule hash mismatch"):
        studies.stored_report(m["edition_id"], tmp_path, first["report_id"])


def test_portable_reference_arm_executes_and_audits_same_boundary_supply_abort():
    from methane.reference import audit
    from methane.simulation import run

    s = studies.protocol("field-cleaning")
    case = next(
        c
        for c in studies.resolve_cases(s, s["reference_config"], "smoke")
        if c["arm_id"] == "portable"
    )
    r = run(Config.from_dict(case["config"]), strategies=["Greedy"], policies=case["policies"])
    assert r["status"] == "complete", r["failures"]
    checked = audit(r)
    assert checked["passed"], (
        [c for c in checked["checks"] if not c["passed"]],
        checked["failures"],
    )
    rows = r["records"]["Greedy"]
    # This fixed synthetic example reaches the site at H3, then observes too
    # little solar for the tool; packing starts after the current interruption.
    row = next(
        x
        for x in rows
        if any(p["order"]["action"] == "pack-return" for p in x["field_operations"]["new_missions"])
    )
    modified = copy.deepcopy(r)
    f = modified["records"]["Greedy"][row["hour"]]["field_operations"]
    event = next(e for e in f["mission_events"] if e["kind"] == "interrupted")
    event["at_hour"] += 0.1
    assert not audit(modified)["passed"]
