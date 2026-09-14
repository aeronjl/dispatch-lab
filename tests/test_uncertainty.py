import copy
import json
import math
from dataclasses import replace

import pytest

from methane.config import Config, Scenario
from methane.uncertainty import (
    VERSION,
    catalogue,
    leaves,
    measure,
    residual_budgets,
    resolve,
    validate_spec,
)


def basis():
    return Config(scenario=Scenario(hours=6, horizon_hours=6, solver_seconds=0.05)).to_dict()


def block(path="plant.heat_loss_kw_per_k", values=(0.04, 0.16), visibility="hidden"):
    return dict(
        id=path,
        paths=[path],
        kind="values",
        rows=[[v] for v in values],
        visibility=visibility,
        source="Explicit test support; not calibration",
        rationale="Numerical verification",
    )


def specification(blocks=None, **changes):
    return dict(
        schema_version=VERSION,
        seed=24,
        worlds=8,
        inner_seeds=[7, 17],
        design="space-filling",
        blocks=blocks if blocks is not None else [block()],
        rationale="Test scenario support",
        **changes,
    )


def test_complete_catalogue_covers_optional_families_and_scalar_paths():
    from methane.assumptions import reference_configuration

    c = catalogue(reference_configuration())
    assert len(c["parameters"]) == 467
    assert not c["unregistered"]
    assert len(c["groups"]) == 21
    assert all(
        p["representation"] and p["mechanism_scope"] and p["evidence_needed"]
        for p in c["parameters"]
    )
    assert not any(p["representation"] == "known-exact" for p in c["parameters"])
    assert len(catalogue(basis())["parameters"]) == 467
    assert any(not p["active"] for p in catalogue(basis())["parameters"])


def test_joint_rows_and_named_streams_preserve_dependence_and_order():
    joint = block()
    joint.update(
        id="joint",
        paths=["plant.heat_loss_kw_per_k", "plant.thermal_capacity_kwh_per_k"],
        rows=[[0.04, 0.15], [0.16, 0.6]],
    )
    s = specification([joint])
    a = resolve(s, basis())
    assert all(
        w["config"]["plant"]["thermal_capacity_kwh_per_k"]
        == w["config"]["plant"]["heat_loss_kw_per_k"] * 3.75
        for w in a
    )
    s["blocks"].insert(0, block("costs.methane_eur_per_kg", (0.5, 2)))
    b = resolve(s, basis())
    s["blocks"].reverse()
    c = resolve(s, basis())
    assert [w["config"]["plant"] for w in a] == [w["config"]["plant"] for w in b]
    assert b == c
    assert all(w["controller_config"]["plant"]["heat_loss_kw_per_k"] == 0.08 for w in a)


def test_invalid_combinations_retained_no_clipping_or_resampling():
    s = specification([block("plant.h2_capacity_kg", (-1, 60), "hidden")])
    s.update(design="factorial", worlds=2)
    worlds = resolve(s, basis())
    assert [w["status"] for w in worlds] == ["invalid-input", "resolved"]
    assert worlds[0]["config"]["plant"]["h2_capacity_kg"] == -1


def test_discrete_booleans_strings_repeated_assets_and_unknown_capabilities():
    from methane.solar_model import default_design

    c = Config()
    v = c.to_dict()
    v["solar"] = default_design(c.plant, c.weather)
    paths = leaves(v)
    path = next(p for p in paths if p.startswith("solar.sections.0.") and p.endswith(".tilt"))
    s = specification(
        [
            block(path, (10, 40), "disclosed"),
            block("models.battery", ("affine/1", "unknown-hardware/1"), "disclosed"),
        ]
    )
    worlds = resolve(s, v)
    assert any(w["status"] == "invalid-input" for w in worlds)
    assert all(w["config"]["solar"] == w["controller_config"]["solar"] for w in worlds)


@pytest.mark.parametrize("kind", ["bounds", "values"])
def test_ranges_are_not_probabilities(kind):
    b = block()
    b["kind"] = kind
    if kind == "bounds":
        b.update(low=0.01, high=0.1)
    s = specification([b])
    s["design"] = "probability"
    with pytest.raises(ValueError, match="probabilit"):
        validate_spec(s, basis())


def test_explicit_probability_and_hidden_adapter_rejection():
    b = block()
    b["weights"] = [0.2, 0.8]
    s = specification([b])
    s.update(design="probability", worlds=128)
    worlds = resolve(s, basis())
    assert 70 < sum(w["config"]["plant"]["heat_loss_kw_per_k"] == 0.16 for w in worlds) < 125
    bad = specification([block("weather.publication_lag_hours", (4, 8), "hidden")])
    with pytest.raises(ValueError, match="Hidden execution adapter"):
        resolve(bad, basis())


def test_observation_clocks_units_independent_difference():
    channels = {
        "h2_inventory_kg": dict(noise_sd=2, bias_sd=100, drift_sd_per_hour=3, source="Test")
    }
    a, ta = measure({"h2_inventory_kg": 10}, channels, 7, -1)
    b, tb = measure({"h2_inventory_kg": 10}, channels, 7, 0)
    assert ta["h2_inventory_kg"]["bias"] == tb["h2_inventory_kg"]["bias"]
    assert ta["h2_inventory_kg"]["drift_per_hour"] == tb["h2_inventory_kg"]["drift_per_hour"]
    assert ta["h2_inventory_kg"]["noise"] != tb["h2_inventory_kg"]["noise"]
    assert residual_budgets(a, b, 55)["balance_kg"] == pytest.approx(math.sqrt(2 * 4 + 9))
    assert "bias" not in b["measurement_uncertainty"]["h2_inventory_kg"]
    assert measure({"h2_inventory_kg": 10}, channels, 7, 0) == (b, tb)


def test_hidden_truth_cannot_change_first_plan_and_accounting_reconciles():
    from methane.reference import audit
    from methane.simulation import run, what_if

    c = basis()
    s = specification([block(), block("costs.methane_eur_per_kg", (0.5, 2))])
    s.update(design="factorial", worlds=4)
    worlds = resolve(s, c)
    runs = [
        run(Config.from_dict(w["config"]), strategies=["Greedy"], uncertainty=w) for w in worlds
    ]
    assert all(r["status"] == "complete" and audit(r)["passed"] for r in runs)
    actions = [r["records"]["Greedy"][0]["decision"]["plan"]["actions"][0] for r in runs]
    assert all(a == actions[0] for a in actions)
    for r in runs:
        assert r["controller_config"] == c
        assert r["uncertainty"]["world"]["world_id"]
        old = json.dumps(r, sort_keys=True)
        what_if(r, "Greedy", 0, "battery")
        assert json.dumps(r, sort_keys=True) == old


def test_future_fault_parameters_do_not_change_earlier_decisions():
    from methane.simulation import run

    c = basis()
    s = specification(
        [
            block("scenario.capacity_fraction", (0.3, 0.8)),
            block("scenario.fault_start_hour", (10, 20)),
        ]
    )
    s.update(design="factorial", worlds=4)
    runs = [
        run(Config.from_dict(w["config"]), strategies=["Greedy"], uncertainty=w)
        for w in resolve(s, c)
    ]
    assert all(
        [(x["decision"], x["diagnosis_after"]) for x in r["records"]["Greedy"]]
        == [(x["decision"], x["diagnosis_after"]) for x in runs[0]["records"]["Greedy"]]
        for r in runs
    )


def test_study_immutable_worlds_resume_invalid_and_export(tmp_path):
    from methane import studies
    from methane.uncertainty_studies import protocol

    s = specification([block("plant.heat_loss_kw_per_k", (-0.1, 0.08))])
    s.update(design="factorial", worlds=2, inner_seeds=[7])
    spec = protocol(basis(), s)
    m = studies.create(specification=spec, root=tmp_path)
    assert len(m["cases"]) == 2
    studies.run_edition(m["edition_id"], root=tmp_path)
    value = studies.report(m["edition_id"], root=tmp_path)
    assert {c["entry"]["status"] for c in value["cases"]} == {"invalid-input", "complete"}
    assert value["uncertainty"]["summaries"][0]["complete_pairs"] == 1
    assert len(value["uncertainty"]["summaries"]) == 2
    publication = studies.publish(m["edition_id"], root=tmp_path)
    assert "Unsampled assumptions" in studies.markdown(publication)
    before = studies.history(m["edition_id"], tmp_path)
    studies.run_edition(m["edition_id"], root=tmp_path)
    after = studies.history(m["edition_id"], tmp_path)
    complete = next(c for c in value["cases"] if c["entry"]["status"] == "complete")
    assert len(before[complete["case_id"]]) == len(after[complete["case_id"]])
    reproduced = studies.create(parent=m["edition_id"], action="reproduce", root=tmp_path)
    assert reproduced["cases"] == m["cases"]
    destination = studies.export(
        m["edition_id"], tmp_path / "bundle.zip", root=tmp_path, report_id=publication["report_id"]
    )
    assert destination.exists()


def test_additive_observations_reprice_and_numerical_rerun_preserve_assumptions(tmp_path):
    from methane.config import Costs
    from methane.costing import reprice
    from methane.evidence import load
    from methane.reference import audit, observation_limits
    from methane.simulation import run
    from recompute import recompute

    c = basis()
    s = specification([block("costs.methane_eur_per_kg", (0.5,))])
    s.update(design="factorial", worlds=1)
    s["measurements"] = {
        name: dict(noise_sd=0.02, bias_sd=0.03, drift_sd_per_hour=0.001, source="Unit test only")
        for name in (
            "power_kw",
            "hydrogen_flow_kg",
            "h2_inventory_kg",
            "h2_outflow_kg",
            "battery_kwh",
            "co2_kg",
            "temperature_c",
        )
    }
    w = resolve(s, c)[0]
    r = run(Config.from_dict(w["config"]), strategies=["Greedy"], uncertainty=w)
    assert r["status"] == "complete" and audit(r)["passed"]
    row = r["records"]["Greedy"][1]
    obs = row["observations_after"]
    before = row["decision"]["observations"]
    independent = observation_limits(before, obs, c["plant"])
    production = residual_budgets(before, obs, 55)
    assert list(map(float, independent)) == pytest.approx(
        [3 * production[k] for k in ("tracking_kw", "balance_kg", "flow_kg")]
    )
    saved = copy.deepcopy(r)
    report = reprice(r, replace(Costs(), methane_eur_per_kg=3))
    assert report["dispatch_costs"]["methane_eur_per_kg"] == 1
    assert report["costs"]["methane_eur_per_kg"] == 3
    assert r == saved
    repeated = recompute(r, tmp_path / "recomputed.json")
    new = load(repeated["archive"])
    assert new["controller_config"] == r["controller_config"]
    assert new["uncertainty"]["world"] == r["uncertainty"]["world"]
    assert repeated["controllers"]["Greedy"]["different_intervals"] == 0


def test_declared_float_with_integer_default_can_have_continuous_support():
    b = block("costs.methane_eur_per_kg")
    b.update(kind="uniform", low=0.5, high=2)
    b.pop("rows")
    s = specification([b])
    s["design"] = "probability"
    assert all(w["status"] == "resolved" for w in resolve(s, basis()))
    b = block("scenario.hours", visibility="disclosed")
    b.update(kind="bounds", low=5, high=10)
    b.pop("rows")
    with pytest.raises(ValueError, match="Integer"):
        resolve(specification([b]), basis())


def test_support_and_service_inputs_use_same_resolved_workflow():
    from methane import studies
    from methane.reference import audit
    from methane.simulation import run
    from methane.uncertainty_studies import protocol, resolve_cases

    c = copy.deepcopy(studies.protocol("field-coordination")["reference_config"])
    c["scenario"].update(hours=3, horizon_hours=6, solver_seconds=0.05)
    s = specification(
        [
            block("service_system.travel_hours", (0.25, 0.75), "disclosed"),
            block("field_operations.mission_failure_probability", (0, 0.2), "disclosed"),
        ]
    )
    s.update(design="factorial", worlds=4, inner_seeds=[7])
    spec = protocol(c, s)
    cases = resolve_cases(spec, c, "reference")
    assert len(cases) == 4 and all(not c["input_error"] for c in cases)
    for case in cases:
        world = case["uncertainty_world"]
        assert world["controller_config"] == world["config"]
        result = run(
            Config.from_dict(case["config"]),
            strategies=["Greedy"],
            policies={"Greedy": case["policies"]["Greedy"]},
            uncertainty=world,
        )
        assert result["status"] == "complete" and audit(result)["passed"]


def test_world_means_never_count_missing_inner_seeds_as_zero():
    from methane.uncertainty_studies import protocol, report, resolve_cases

    s = specification()
    s.update(design="factorial", worlds=2)
    p = protocol(basis(), s)
    cases = resolve_cases(p, basis(), "reference")
    manifest = dict(protocol=p, cases=cases, basis=basis(), edition_id="test")
    metrics = {
        name: dict(
            methane_kg=i,
            ending=dict(battery_kwh=0, h2_kg=0, co2_kg=0, temperature_c=20),
            forced_downtime_hours=0,
        )
        for i, name in enumerate(p["policies"])
    }
    value = report(manifest, {cases[0]["case_id"]: [{"status": "complete", "metrics": metrics}]})
    summary = value["uncertainty"]["summaries"][0]
    assert summary["complete_pairs"] == 1 and summary["complete_worlds"] == 0
    assert summary["metrics"]["methane_kg"]["world_means"]["mean"] is None
    assert "sample_quantiles" not in summary["metrics"]["methane_kg"]["paired_cases"]


def test_weather_is_frozen_once_and_detailed_solar_is_archivable(tmp_path, monkeypatch):
    from methane import studies, weather
    from methane.solar_model import default_design
    from methane.uncertainty_studies import protocol

    c = Config.from_dict(basis())
    v = c.to_dict()
    v["solar"] = default_design(c.plant, c.weather)
    s = specification()
    s.update(design="factorial", worlds=2, inner_seeds=[7])
    calls = []
    original = weather.prepare

    def prepared(c, *args, **kwargs):
        calls.append(c)
        return original(c, *args, **kwargs)

    monkeypatch.setattr(weather, "prepare", prepared)
    m = studies.create(specification=protocol(v, s), root=tmp_path)
    assert len(calls) == 1
    studies.run_edition(m["edition_id"], root=tmp_path)
    r = studies.report(m["edition_id"], root=tmp_path)
    assert r["completed_pairs"] == 2
    for case in r["cases"]:
        saved = studies.archive_for(m["edition_id"], case["entry"], tmp_path)
        assert saved["provenance"]["weather_content_hash"] == case["weather_hash"]


def test_missing_nullable_parameters_are_explicit_differences():
    from methane.studies import differences

    assert differences({}, dict(value=None)) == [
        dict(parameter="value", before=None, after=None, before_present=False, after_present=True)
    ]
