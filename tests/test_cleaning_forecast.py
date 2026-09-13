"""Independent area arithmetic, execution reconciliation and conditional value."""

import copy
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from methane.config import Costs, Plant, Scenario, WeatherConfig
from methane.faults import FaultPolicy, FaultState
from methane.field_operations import FieldOperations
from methane.forecast import IncompleteWeather
from methane.physics import State
from methane.sensing import Diagnosis
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.cleaning_forecast import project
from methane.services.configuration import ServiceSystem
from methane.services.coupling import evaluate
from methane.services.optical import OpticalArray
from methane.services.planning import Commitment
from methane.services.plant import PlantServices
from methane.services.scenario_planning import Branch
from methane.services.supervisor import Candidate, choose, commit
from methane.solar_model import default_design


def fixture(*, clip=None, portable="none", solar_kw=1000):
    p = replace(
        Plant(),
        solar_kw=solar_kw,
        battery_kwh=0,
        heat_loss_kw_per_k=0,
        heater_max_kw=0,
        thermal_capacity_kwh_per_k=10,
        initial_h2_kg=0,
    )
    w = WeatherConfig(loss_fraction=0, temperature_coefficient=0)
    c = FieldOperations(
        enabled=True,
        initial_soiling_fraction=0.1,
        soiling_per_day=0,
        cleaning_removal_fraction=1,
        mission_failure_probability=0,
        rover_enabled=False,
        reset_enabled=False,
        human_fallback=portable != "none",
        cleaner_enabled=portable == "none",
        dock_available=False,
    )
    o = ServiceSystem(
        cleaning_model="section-optical/1",
        inspector="none",
        support_model="logistics/1",
        cleaning_policy="condition",
        initial_adhered_fraction=0.2,
        initial_damage_fraction=0.05,
        portable_cleaner=portable,
        area_m2_per_kw=5,
        cleaning_area_m2ph=solar_kw * 2.5,
        portable_area_m2ph=solar_kw * 2.5,
        crew_response_lead_hours=0,
        crew_travel_hours=0.25,
        portable_setup_hours=0.25,
        portable_water_l_per_m2=0.01,
        outcome_randomness="target-action-request/1",
    )
    design = default_design(p, w)
    for i, s in enumerate(design["sections"]):
        s["capacity_kw"] = solar_kw if i == 0 else 0
    if clip is not None:
        design["converter_kw"] = clip
    optical = OpticalArray(p, w, design, c, o)
    rt = PlantServices(c, o, 7, p.electrolyser_kw, optical=optical)
    clock = datetime(2026, 4, 10, 10, tzinfo=UTC)
    raw = dict(
        decision_hour=0,
        times=[(clock + timedelta(hours=i)).isoformat() for i in range(8)],
        source=dict(
            id="teaching:constant-radiation",
            initialized_at=clock.isoformat(),
            available_at=clock.isoformat(),
        ),
        pv_kw=[solar_kw] * 8,
        ambient_c=[20] * 8,
        source_samples=[dict(irradiance_wm2=1000)] * 8,
        deliveries_kg=[0] * 8,
    )
    converted = [r["dirty"]["output_kw"] for r in optical.convert(raw)]
    forecast = {**raw, "pv_kw": converted}
    rt.prepare(0, Diagnosis(p.electrolyser_kw), converted[0], environment={"ambient_c": 20})
    key = next(q["id"] for q in rt.orders if q["kind"] in ("cleaning", "portable-cleaning"))
    plan, assessment = rt.propose(key)
    assert assessment["feasible"], assessment
    args = dict(
        plant=p,
        weather=w,
        design=design,
        config=c,
        options=o,
        snapshot=optical.surface.snapshot(),
        forecast=raw,
        commitments=(Commitment(plan),),
        brush_remaining_m2=rt.ledger.stock["brush:cleaner"],
    )
    return args, rt, forecast, key


def test_independent_transmission_and_next_interval_timing():
    args, rt, _, _ = fixture()
    before = copy.deepcopy((rt.public(), rt.ledger.stock, args))
    result = project(**args)
    # Half an hour travel, then 1250/5000 m² in the first hour. Unit brush
    # condition removes all loose loss on 1/4 of the section. Other loss remains.
    transmission = (Decimal(1) - Decimal(".1") * Decimal(".75")) * Decimal(".8") * Decimal(".95")
    assert result["rows"][0]["predicted"]["output_kw"] == pytest.approx(684)
    assert result["rows"][1]["predicted"]["output_kw"] == pytest.approx(float(1000 * transmission))
    assert result["rows"][0]["available_dc_change_kw"] == 0
    assert result["ending_brush_m2"] == 45000
    assert result["ending_surface"]["PV-01"][0]["adhered"] == 0.2
    assert result["ending_surface"]["PV-01"][0]["damaged"] == 0.05
    assert (rt.public(), rt.ledger.stock, args) == before


@pytest.mark.parametrize("portable", ["none", "wet"])
def test_prediction_reconciles_with_execution_and_replanning_from_observed_pass(portable):
    args, rt, forecast, key = fixture(portable=portable)
    expected = project(**args)
    fault = FaultState(args["plant"], Scenario(fault_start_hour=1000), FaultPolicy())
    diagnosis = Diagnosis(args["plant"].electrolyser_kw)
    seen = []
    for hour in range(8):
        raw = copy.deepcopy(args["forecast"])
        raw["decision_hour"] = hour
        for name in ("times", "pv_kw", "ambient_c", "source_samples", "deliveries_kg"):
            raw[name] = raw[name][hour:]
        actual_pv = rt.optical.convert(raw)[0]["dirty"]["output_kw"]
        assert actual_pv == pytest.approx(expected["rows"][hour]["predicted"]["output_kw"])
        if hour:
            rt.prepare(hour, diagnosis, actual_pv, environment={"ambient_c": 20})
        if hour == 1:
            active = tuple(
                Commitment(m.plan, m.stage_index, m.entered)
                for m in rt.executive.missions.values()
                if m.status in ("active", "scheduled")
            )
            later = {
                **args,
                "snapshot": rt.optical.surface.snapshot(),
                "forecast": raw,
                "commitments": active,
                "brush_remaining_m2": rt.ledger.stock["brush:cleaner"],
                "observed_treatments": seen,
            }
            replay = project(**later)
            assert [r["predicted"]["output_kw"] for r in replay["rows"]] == pytest.approx(
                [r["predicted"]["output_kw"] for r in expected["rows"]][1:]
            )
            with pytest.raises(ValueError, match="original observed efficacy"):
                project(**{**later, "observed_treatments": ()})
        rt.dispatch_selected(((key, 0),) if hour == 0 else (), charge=False)
        rt.execute_interval(hour, fault)
        row = rt.end(hour, fault, diagnosis)
        seen += row["surface_events"]
        assert row["surface_after"] == expected["rows"][hour]["after"]
        assert row["brush_after_m2"] == pytest.approx(expected["rows"][hour]["brush_after_m2"])


def test_clipping_can_absorb_all_of_the_optical_gain():
    args, _, _, _ = fixture(clip=600)
    result = project(**args)
    assert all(r["available_dc_change_kw"] == 0 for r in result["rows"])
    assert (
        result["rows"][-1]["predicted"]["clipped_kw"]
        > result["rows"][-1]["no_further_cleaning"]["clipped_kw"]
    )
    assert "curtail" not in result["rows"][-1]["predicted"]


def test_absent_evidence_and_inputs_are_not_silently_filled():
    args, _, _, _ = fixture()
    bad = copy.deepcopy(args)
    bad["forecast"]["source_samples"][0]["irradiance_wm2"] = None
    with pytest.raises(IncompleteWeather):
        project(**bad)
    with pytest.raises(ValueError, match="brush allowance"):
        project(**{**args, "brush_remaining_m2": 10})
    event = dict(order_id="unrelated", completed_at=1, effective_at=1)
    with pytest.raises(ValueError, match="unavailable"):
        project(**{**args, "observed_treatments": [event]})
    bad = copy.deepcopy(args)
    bad["snapshot"]["PV-01"][0]["end_m2"] -= 1
    with pytest.raises(ValueError, match="partition"):
        project(**bad)
    with pytest.raises(ValueError, match="twice"):
        project(**{**args, "commitments": args["commitments"] * 2})


def test_changed_future_weather_does_not_change_earlier_treatment_predictions():
    args, _, _, _ = fixture()
    first = project(**args)
    changed = copy.deepcopy(args)
    changed["forecast"]["pv_kw"][5:] = [0] * 3
    second = project(**changed)
    assert first["rows"][:5] == second["rows"][:5]
    assert first["input_id"] != second["input_id"]


def test_reference_publication_must_precede_the_decision_and_inputs_remain_finite():
    args, _, _, _ = fixture()
    wrong = copy.deepcopy(args)
    wrong["forecast"]["source"]["available_at"] = wrong["forecast"]["times"][1]
    with pytest.raises(ValueError, match="eligible"):
        project(**wrong)
    wrong = copy.deepcopy(args)
    wrong["forecast"]["pv_kw"][2] = float("nan")
    with pytest.raises(IncompleteWeather):
        project(**wrong)


def test_private_execution_outcomes_cannot_change_a_candidate_prediction():
    args, rt, forecast, key = fixture()
    kwargs = dict(
        runtime=rt,
        plant=args["plant"],
        state=State.initial(args["plant"]),
        forecast=forecast,
        capacity_kw=450,
        costs=Costs(),
        selections=((key, 0),),
        reference_forecast=args["forecast"],
        project_only=True,
    )
    first = evaluate(**kwargs)
    rt._effects.pass_efficacy[key] = 0.01
    rt._effects.pending.append(("module-replacement", 5, True, "private-only"))
    second = evaluate(**kwargs)
    assert first == second


def test_coupled_candidate_records_treatment_and_rejects_a_different_reference():
    args, rt, forecast, key = fixture(solar_kw=100)
    kwargs = dict(
        runtime=rt,
        plant=args["plant"],
        state=replace(State.initial(args["plant"]), temperature_c=300),
        forecast=forecast,
        capacity_kw=450,
        costs=Costs(),
        selections=((key, 0),),
        objective="greedy",
        seconds=1,
        reference_forecast=args["forecast"],
    )
    result = evaluate(**kwargs)
    assert result["state"] == "feasible", result["constraints"]
    assert result["forecast"]["pv_kw"][0] == forecast["pv_kw"][0]
    assert result["forecast"]["pv_kw"][-1] > forecast["pv_kw"][-1]
    assert result["cleaning_prediction"]["context"] == "prediction"
    wrong = copy.deepcopy(args["forecast"])
    wrong["pv_kw"][1] *= 2
    with pytest.raises(ValueError, match="reproduce"):
        evaluate(**{**kwargs, "reference_forecast": wrong})


@pytest.mark.parametrize("clip,selected", [(None, "clean"), (200, "defer")])
def test_supervisor_values_useful_generation_but_does_not_pay_for_clipped_gain(clip, selected):
    args, rt, forecast, key = fixture(clip=clip, solar_kw=300)
    prices = illustrative(Costs(), version=ACTIVITY_VERSION)
    costs = replace(Costs(), methane_eur_per_kg=100)
    branch = Branch.create("reference", 1, forecast, ("same",) * 8, source="teaching:continuation")
    result = choose(
        rt,
        args["plant"],
        replace(State.initial(args["plant"]), temperature_c=300),
        forecast,
        450,
        costs,
        [Candidate("defer", ()), Candidate("clean", ((key, 0),))],
        [branch],
        prices,
        objective="economics",
        seconds_per_candidate=3,
        reference_forecast=args["forecast"],
        outcome_references={"reference": args["forecast"]},
    )
    assert result["status"] == "selected", result
    assert result["selected_candidate_id"] == selected
    assert not rt.executive.missions
    commit(rt, result)
    assert (key in rt.executive.missions) == (selected == "clean")
