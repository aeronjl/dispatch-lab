"""Performance knowledge boundaries, independent recurrences and real execution."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.adaptation import DEFAULT, Observer, split_weather, validate
from methane.config import Config, Scenario
from methane.field_operations import FieldOperations
from methane.pv import dc_power
from methane.reference import audit
from methane.services.configuration import ServiceSystem
from methane.simulation import run
from methane.uncertainty import VERSION, resolve
from methane.weather import synthetic


def fixture(optical=False, hours=12):
    return Config(
        scenario=Scenario(hours=hours, horizon_hours=6, solver_seconds=0.05),
        field_operations=FieldOperations(
            enabled=True,
            initial_soiling_fraction=0.15,
            soiling_per_day=0,
            mission_failure_probability=0,
            rover_enabled=False,
            reset_enabled=False,
            human_fallback=False,
        ),
        service_system=ServiceSystem(
            inspector="none", cleaning_model="section-optical/1" if optical else "lumped-dc/1"
        ),
    )


def specification(mode="adaptive", **changes):
    paths = [("weather.loss_fraction", 0.35), ("field_operations.cleaning_removal_fraction", 0.2)]
    return dict(
        schema_version=VERSION,
        seed=1,
        worlds=1,
        inner_seeds=[7],
        design="factorial",
        rationale="Explicit numerical test, not field calibration",
        adaptation={**DEFAULT, "mode": mode},
        blocks=[
            dict(
                id=p,
                paths=[p],
                kind="values",
                rows=[[v]],
                visibility="hidden",
                source="Test assumption",
                rationale="Test",
            )
            for p, v in paths
        ],
        **changes,
    )


def execute(c, mode="adaptive", weather=None):
    world = resolve(specification(mode), c.to_dict())[0]
    actual = Config.from_dict(world["config"])
    if weather is None:
        weather = synthetic(actual)
        for mapping in [weather["truth"], weather["template"]]:
            for sample in mapping.values():
                sample.update(
                    irradiance_wm2=700,
                    ambient_c=20,
                    pv_kw=dc_power(700, 20, actual.plant, actual.weather),
                )
    result = run(actual, weather=weather, strategies=["Greedy"], uncertainty=world)
    assert result["status"] == "complete", result.get("failures")
    return result


def test_observer_recurrence_matches_decimal_and_low_activity_is_not_health():
    o = Observer(DEFAULT, FieldOperations())
    assert o.solar_observation(0, 0, 0)["status"] == "insufficient evidence"
    o.solar_observation(1, 100, 60)
    r = o.solar_observation(2, 100, 60)
    assert r["after"] == float(Decimal(1) + Decimal(".35") * (Decimal(".6") - 1))
    previous = o.solar
    assert o.solar_observation(3, 100, 400)["status"] == "outside model support"
    assert o.solar == previous
    with pytest.raises(ValueError, match="advance"):
        o.solar_observation(3, 100, 60)
    with pytest.raises(ValueError, match="operands"):
        o.service_observation(0, {"successful_repair": True})
    with pytest.raises(ValueError):
        validate({**DEFAULT, "minimum_samples": False})


@pytest.mark.parametrize("optical", [False, True])
def test_real_execution_separates_conversion_and_cleaning_and_reconciles(optical):
    r = execute(fixture(optical))
    rows = r["records"]["Greedy"]
    assert rows[0]["decision"]["performance_estimates"]["solar"]["after"] == 1
    assert rows[-1]["decision"]["performance_estimates"]["solar"]["after"] < 0.8
    assert (
        rows[0]["field_operations"]["planning_snapshot"]["config"]["cleaning_removal_fraction"]
        == 0.9
    )
    assert rows[-1]["field_operations"]["performance_update"]["after"] < 0.5
    assert (
        rows[-1]["field_operations"]["planning_snapshot"]["config"]["cleaning_removal_fraction"]
        < 0.5
    )
    assert r["config"]["field_operations"]["cleaning_removal_fraction"] == 0.2
    assert (
        r["provenance"]["controller_config"]["field_operations"]["cleaning_removal_fraction"] == 0.9
    )
    a = audit(r)
    assert a["passed"], [x for x in a["checks"] if not x["passed"]][:5]
    assert any(x["id"].startswith("performance.") for x in a["checks"])
    tampered = copy.deepcopy(r)
    tampered["records"]["Greedy"][2]["decision"]["performance_estimates"]["solar"]["after"] += 0.1
    assert not audit(tampered)["passed"]


def test_fixed_ablation_records_same_observations_without_updating_parameters():
    r = execute(fixture(), "fixed")
    assert all(
        x["decision"]["performance_estimates"]["solar"]["after"] == 1
        for x in r["records"]["Greedy"]
    )
    assert all(
        x["field_operations"]["performance_update"]["after"] == 0.9 for x in r["records"]["Greedy"]
    )
    assert audit(r)["passed"]


def test_later_weather_cannot_change_earlier_estimates_actions_or_diagnoses():
    c = fixture(hours=6)
    world = resolve(specification(), c.to_dict())[0]
    actual = Config.from_dict(world["config"])
    w = synthetic(actual)
    for sample in w["truth"].values():
        sample.update(
            irradiance_wm2=700, ambient_c=20, pv_kw=dc_power(700, 20, actual.plant, actual.weather)
        )
    changed = copy.deepcopy(w)
    for t in changed["times"][3:]:
        changed["truth"][t]["pv_kw"] *= 0.3
        changed["truth"][t]["irradiance_wm2"] *= 0.3
    a, b = execute(c, weather=w), execute(c, weather=changed)
    for x, y in zip(a["records"]["Greedy"][:3], b["records"]["Greedy"][:3], strict=True):
        assert x["decision"] == y["decision"]
        assert x["diagnosis_after"] == y["diagnosis_after"]


def test_hidden_service_probability_never_enters_first_planning_snapshot():
    c = fixture(hours=6)
    results = []
    for value in [0, 1]:
        s = specification()
        s["blocks"] = [
            dict(
                id="repair",
                paths=["field_operations.repair_success_probability"],
                kind="values",
                rows=[[value]],
                visibility="hidden",
                source="test",
                rationale="test",
            )
        ]
        world = resolve(s, c.to_dict())[0]
        r = run(Config.from_dict(world["config"]), strategies=["Greedy"], uncertainty=world)
        results.append(r["records"]["Greedy"][0]["decision"])
    assert results[0] == results[1]


def test_unknown_duration_and_legacy_hidden_services_still_rejected():
    s = specification()
    s["blocks"][0].update(paths=["service_system.travel_hours"], rows=[[2]])
    with pytest.raises(ValueError, match="hidden|Hidden"):
        resolve(s, fixture().to_dict())
    assert resolve(specification(), Config().to_dict())[0]["status"] == "invalid-input"


def test_saved_forecasts_use_original_conversion_and_keep_issue_availability():
    c = fixture()
    a = replace(c, weather=replace(c.weather, loss_fraction=0.35))
    w = synthetic(a)
    s = split_weather(w, a, c)
    assert s["truth"] == w["truth"]
    assert s["times"] == w["times"]
    for v in s["template"].values():
        assert v["pv_kw"] == pytest.approx(
            dc_power(v["irradiance_wm2"], v["ambient_c"], c.plant, c.weather)
        )
    assert split_weather(s, a, c) == s
    with pytest.raises(ValueError, match="different"):
        split_weather(s, c, a)


def test_same_information_replan_and_numerical_replay_retain_original_models():
    from methane.simulation import what_if

    r = execute(fixture(hours=6))
    original = copy.deepcopy(r)
    alt = what_if(r, "Greedy", 3, "battery")
    assert alt["label"] == "PREDICTION / SAME INFORMATION"
    assert alt["forecast_source"] == r["records"]["Greedy"][3]["decision"]["forecast"]["source"]
    assert r == original
    world = r["provenance"]["uncertainty_world"]
    replay = run(
        Config.from_dict(r["config"]),
        weather=r["weather"],
        strategies=["Greedy"],
        uncertainty=world,
    )
    assert [x["decision"] for x in replay["records"]["Greedy"]] == [
        x["decision"] for x in r["records"]["Greedy"]
    ]


def test_hidden_mission_failure_changes_execution_not_initial_selection():
    c = fixture(hours=6)
    decisions, failures = [], []
    for chance in [0, 1]:
        spec = specification()
        spec["blocks"] = [
            dict(
                id="mission",
                paths=["field_operations.mission_failure_probability"],
                kind="values",
                rows=[[chance]],
                visibility="hidden",
                source="test",
                rationale="test",
            )
        ]
        world = resolve(spec, c.to_dict())[0]
        actual = Config.from_dict(world["config"])
        weather = synthetic(actual)
        for mapping in (weather["truth"], weather["template"]):
            for sample in mapping.values():
                sample.update(
                    irradiance_wm2=700,
                    ambient_c=20,
                    pv_kw=dc_power(700, 20, actual.plant, actual.weather),
                )
        r = run(actual, weather=weather, strategies=["Greedy"], uncertainty=world)
        assert r["status"] == "complete"
        decisions.append(r["records"]["Greedy"][0]["decision"])
        failures.append(
            any(
                o["status"] in ("stranded", "failed")
                for o in r["records"]["Greedy"][-1]["field_operations"]["state"]["orders"]
            )
        )
        assert audit(r)["passed"]
    assert decisions[0] == decisions[1]
    assert failures == [False, True]


def test_direct_execution_cannot_bypass_unsupported_hidden_adapter_rejection():
    c = fixture(hours=2)
    world = resolve(specification(), c.to_dict())[0]
    world["config"]["service_system"]["travel_hours"] = 2
    with pytest.raises(ValueError, match="Hidden execution adapter"):
        run(Config.from_dict(world["config"]), uncertainty=world)


def test_forecast_vintage_availability_is_unchanged_by_conversion_separation():
    from datetime import timedelta

    from methane.timebase import stamp, utc
    from methane.weather import forecast_at

    c = fixture(hours=6)
    a = replace(c, weather=replace(c.weather, loss_fraction=0.35))
    w = synthetic(a)
    w["mode"] = "historical"
    start = utc(w["times"][0])
    w["vintages"] = [
        dict(
            id=str(i),
            initialized_at=stamp(start + timedelta(hours=i)),
            available_at=stamp(start + timedelta(hours=i)),
            source="saved test issue",
            data=copy.deepcopy(w["template"]),
        )
        for i in (0, 3)
    ]
    separated = split_weather(w, a, c)
    assert [forecast_at(separated, c, h)["source"]["id"] for h in range(6)] == ["0"] * 3 + ["3"] * 3
    assert [v["available_at"] for v in separated["vintages"]] == [
        v["available_at"] for v in w["vintages"]
    ]


def test_solar_adaptation_preserves_legacy_services_without_claiming_service_learning():
    c = replace(fixture(hours=3), service_system=None)
    spec = specification()
    spec["blocks"] = spec["blocks"][:1]
    world = resolve(spec, c.to_dict())[0]
    r = run(Config.from_dict(world["config"]), strategies=["Greedy"], uncertainty=world)
    assert r["status"] == "complete"
    assert all(
        "performance_update" not in row["field_operations"] for row in r["records"]["Greedy"]
    )
    assert audit(r)["passed"]


def test_execution_rejects_unrecorded_hidden_mismatch():
    world = resolve(specification(), fixture(hours=2).to_dict())[0]
    world["draws"] = []
    with pytest.raises(ValueError, match="original draw"):
        run(Config.from_dict(world["config"]), uncertainty=world)
