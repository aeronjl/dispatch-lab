"""Original-information substitutions retain mechanics and independent ledgers."""

import copy
import json
from dataclasses import asdict, replace

import pytest
from test_cleaning_forecast import fixture as cleaning_fixture
from test_visit_planning import forecast

from methane.config import Config, Scenario
from methane.physics import State
from methane.provenance import LOADED_SOURCE, digest
from methane.sensing import Diagnosis
from methane.service_alternatives_service import describe
from methane.service_economics import ACTIVITY_VERSION, illustrative
from methane.services.alternatives import compare, prepare
from methane.services.coupling import evaluate, identity
from methane.services.inspection_demo import fixture as inspection_fixture
from methane.services.optical import OpticalArray
from methane.services.plant import PlantServices
from methane.services.snapshot import RecordedServices, capture
from methane.simulation import digest as process_digest
from methane.solar_model import default_design


def inspection(*, blocked=False):
    c = inspection_fixture()
    c = replace(
        c,
        field_operations=replace(c.field_operations, initial_soiling_fraction=0),
        service_system=replace(c.service_system, support_model="logistics/1"),
        service_economics=illustrative(c.costs, version=ACTIVITY_VERSION),
    )
    rt = PlantServices(c.field_operations, c.service_system, 7, c.plant.electrolyser_kw)
    d = Diagnosis(225, active_incident=True, incidents=1, informative=True, tracking_residual=0.5)
    rt.prepare(0, d, 750)
    key = next(o["id"] for o in rt.orders if o["kind"] == "inspection")
    if blocked:
        rt.ledger.stock["energy:rover"] = 0
    return c, rt, key, forecast(8), None


def cleaning(*, water=1000, resident=True):
    args, _, _, _ = cleaning_fixture(portable="wet")
    c = Config(
        plant=args["plant"],
        weather=args["weather"],
        field_operations=replace(args["config"], cleaner_enabled=resident),
        service_system=replace(args["options"], portable_water_initial_l=water),
        scenario=Scenario(hours=12, horizon_hours=6, solver_seconds=2),
    )
    c = replace(c, service_economics=illustrative(c.costs, version=ACTIVITY_VERSION))
    optical = OpticalArray(c.plant, c.weather, args["design"], c.field_operations, c.service_system)
    rt = PlantServices(
        c.field_operations, c.service_system, 7, c.plant.electrolyser_kw, optical=optical
    )
    raw = args["forecast"]
    f = {**raw, "pv_kw": [r["dirty"]["output_kw"] for r in optical.convert(raw)]}
    rt.prepare(0, Diagnosis(450), f["pv_kw"][0], environment={"ambient_c": 20})
    key = next(
        o["id"] for o in rt.orders if o["kind"] == ("cleaning" if resident else "portable-cleaning")
    )
    return c, rt, key, f, raw


def source(values):
    c, rt, key, f, raw = values
    state = replace(State.initial(c.plant), temperature_c=300)
    captured = capture(rt)
    evaluated = evaluate(
        rt,
        c.plant,
        state,
        f,
        225 if raw is None else 450,
        c.costs,
        ((key, 0),),
        service_prices=c.service_economics,
        objective="greedy",
        reference_forecast=raw,
    )
    assert evaluated["state"] == "feasible", evaluated["constraints"]
    rt.dispatch_selected(((key, 0),), charge=False)
    inputs = dict(
        schema_version="service-process-planning-inputs/1",
        estimate=asdict(state),
        capacity_kw=225 if raw is None else 450,
        forecast=f,
        reference_forecast=raw,
        objective="greedy",
        terminal_battery_value=0,
        cost_version=process_digest(asdict(c.costs)),
        service_cost_version=digest(c.service_economics),
    )
    result = dict(
        run_id="procedure-teaching",
        config=c.to_dict(),
        provenance=dict(source=dict(content_hash=LOADED_SOURCE["content_hash"])),
        service_planning_catalogues={captured["snapshot"]["catalogue_id"]: captured["catalogue"]},
        records={
            "teaching": [
                dict(
                    hour=0,
                    decision=dict(service_planning_inputs=inputs, plan=evaluated["process_plan"]),
                    field_operations={
                        **copy.deepcopy(rt.interval),
                        "planning_snapshot": captured["snapshot"],
                    },
                )
            ]
        },
    )
    return result, key


def request(packet, key):
    choice = packet["snapshot"]["procedure_choices"][key][0]
    return dict(kind="procedure", order_id=key, procedure_id=choice["procedure_id"])


def test_fixed_reader_to_rover_retains_current_evidence_and_independent_energy():
    result, key = source(inspection())
    packet = json.loads(json.dumps(prepare(result, "teaching", 0)))
    before = copy.deepcopy((result, packet))
    answer = compare(packet, request(packet, key))
    assert answer["status"] == "complete", answer
    assert answer["alternative"]["schedule"]["singles"] == packet["original_schedule"]["singles"]
    base = answer["baseline"]["evaluation"]["demand"]["proposals"][0]["plan"]
    other = answer["alternative"]["evaluation"]["demand"]["proposals"][0]["plan"]
    assert base["asset"]["archetype"] == "fixed-sensor"
    assert other["asset"]["archetype"] == "ground-inspector"
    assert other["context"] == base["context"]
    assert other["order"] == base["order"]
    assert "trip-contact:mobile" in [r["channel"] for r in other["capability"]["acceptance"]]
    c = result["config"]["field_operations"]
    # Both .5 h journeys use mission power; contact work + verification use reader power.
    expected = (
        2 * result["config"]["service_system"]["travel_hours"] * c["mission_power_kw"]
        + (c["inspection_hours"] + result["config"]["service_system"]["verification_hours"])
        * result["config"]["service_system"]["reader_kw"]
    )
    stock = answer["alternative"]["summary"]["ending_service_stocks"]
    assert stock["energy:rover"] == pytest.approx(c["rover_battery_kwh"] - expected)
    assert (
        answer["baseline"]["summary"]["ending_service_stocks"]["energy:rover"]
        == c["rover_battery_kwh"]
    )
    assert "No finding or recovery" in answer["note"]
    assert (result, packet) == before


def test_resident_to_wet_portable_retains_distinct_treatment_water_and_crew_cost():
    result, key = source(cleaning())
    packet = prepare(result, "teaching", 0)
    answer = compare(packet, request(packet, key))
    assert answer["status"] == "complete", answer
    a, b = (answer[k]["summary"] for k in ("baseline", "alternative"))
    o = result["config"]["service_system"]
    assert a["ending_service_stocks"]["stock:water"] == 1000
    # 5000 m² at .01 L/m² plus the configured setup rinse; no verification pumping.
    assert b["ending_service_stocks"]["stock:water"] == pytest.approx(
        1000 - 50 - o["portable_rinse_l"]
    )
    assert b["ending_service_stocks"]["brush:cleaner"] == 50000
    assert a["ending_service_stocks"]["brush:cleaner"] == 45000
    assert b["service_decision_eur"] > a["service_decision_eur"]
    # Conditional conversion uses different adhered-fouling removal, not a bonus appended to output.
    af = answer["baseline"]["evaluation"]["demand"]["forecast"]["pv_kw"]
    bf = answer["alternative"]["evaluation"]["demand"]["forecast"]["pv_kw"]
    assert af[0] == bf[0] == pytest.approx(684)
    assert af[-1] == pytest.approx(1000 * 0.8 * 0.95)
    assert bf[-1] == pytest.approx(
        1000
        * (1 - 0.1 * (1 - o["portable_loose_removal"]))
        * (1 - 0.2 * (1 - o["portable_adhered_removal"]))
        * 0.95
    )


@pytest.mark.parametrize(
    "values,condition",
    [
        (lambda: cleaning(water=0), "stock:water"),
        (lambda: inspection(blocked=True), "energy:rover"),
    ],
)
def test_depleted_resources_remain_infeasible_without_replacing_the_baseline(values, condition):
    result, key = source(values())
    packet = prepare(result, "teaching", 0)
    answer = compare(packet, request(packet, key))
    assert answer["status"] == "incomplete"
    assert answer["baseline"]["summary"]["prediction"] is not None
    assert answer["alternative"]["summary"]["prediction"] is None
    assert condition in json.dumps(answer["alternative"]["evaluation"]["constraints"])
    assert answer["differences"] is None


def test_missing_installed_tool_and_legacy_snapshot_do_not_invent_original_choices():
    _, rt, key, _, _ = cleaning(resident=False)
    captured = capture(rt)
    assert not captured["snapshot"]["procedure_choices"].get(key)
    result, key = source(inspection())
    s = result["records"]["teaching"][0]["field_operations"]["planning_snapshot"]
    original = s.pop("procedure_choices")[key][0]["procedure_id"]
    s["schema_version"] = "service-planning-snapshot/1"
    s["snapshot_id"] = identity({k: v for k, v in s.items() if k != "snapshot_id"})
    packet = prepare(result, "teaching", 0)
    assert not describe(packet)["procedures_recorded"]
    assert all(not o["procedures"] for o in describe(packet)["orders"])
    with pytest.raises(ValueError, match="were not saved"):
        compare(packet, dict(kind="procedure", order_id=key, procedure_id=original))
    # Existing postponement remains supported without migrating the archive.
    assert (
        compare(packet, dict(kind="postpone", order_id=key, delay_hours=1))["status"] == "complete"
    )


def test_no_arbitrary_procedure_or_changed_target_and_fingerprint_tracks_substitution():
    result, key = source(inspection())
    packet = prepare(result, "teaching", 0)
    r = request(packet, key)
    with pytest.raises(ValueError, match="installed compatible"):
        compare(packet, {**r, "procedure_id": "invented robot repair"})
    rt = RecordedServices(packet["snapshot"], packet["catalogue"])
    before = rt.public()
    rt.choose_procedure(key, r["procedure_id"])
    assert rt.public() != before
    assert rt.executive.missions == {} and not rt.ledger.events
    corrupt = copy.deepcopy(packet["snapshot"])
    corrupt["procedure_choices"][key][0]["plan"]["interface"]["target_asset_id"] = "another plant"
    corrupt["snapshot_id"] = identity({k: v for k, v in corrupt.items() if k != "snapshot_id"})
    rt = RecordedServices(corrupt, packet["catalogue"])
    with pytest.raises(ValueError, match="original request"):
        rt.choose_procedure(key, r["procedure_id"])


def test_unequal_sections_cannot_borrow_another_sections_duration_or_reoffer_original_tool():
    c, _, _, _, raw = cleaning()
    design = default_design(c.plant, c.weather)
    for section, capacity in zip(design["sections"], (100, 300, 600), strict=True):
        section["capacity_kw"] = capacity
    optical = OpticalArray(c.plant, c.weather, design, c.field_operations, c.service_system)
    rt = PlantServices(c.field_operations, c.service_system, 7, 450, optical=optical)
    pv = optical.convert(raw)[0]["dirty"]["output_kw"]
    rt.prepare(0, Diagnosis(450), pv, environment={"ambient_c": 20})
    s = capture(rt)["snapshot"]
    for order, choices in s["procedure_choices"].items():
        original = s["recipes"][order]["plan"]
        assert len(choices) == 1
        other = choices[0]["plan"]
        assert other["asset"]["asset_id"] != original["asset"]["asset_id"]
        target = original["interface"]["target_asset_id"]
        assert other["interface"]["target_asset_id"] == target
        assert other["capability"]["capability_id"].endswith("/" + target)
        rate = (
            c.service_system.portable_area_m2ph
            if other["order"]["action"] == "portable-clean-section"
            else c.service_system.cleaning_area_m2ph
        )
        assert other["capability"]["work_hours"] == pytest.approx(
            optical.surface.section(target)["area_m2"] / rate
        )
