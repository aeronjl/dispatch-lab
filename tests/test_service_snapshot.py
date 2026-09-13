"""Original-information planning transport, without a simulator effect port."""

import copy
import json

import pytest
from test_visit_planning import fixture, forecast, repair_fixture

from methane.faults import FaultState
from methane.physics import State
from methane.sensing import Diagnosis
from methane.services import charge_control, coupling
from methane.services.snapshot import RecordedServices, capture


def frozen(runtime):
    packet = json.loads(json.dumps(capture(runtime)))
    return RecordedServices(packet["snapshot"], packet["catalogue"]), packet


def project(rt, c, selections=(), groups=()):
    result = coupling.evaluate(
        rt,
        c.plant,
        State.initial(c.plant),
        forecast(),
        450,
        c.costs,
        selections,
        visit_groups=groups,
        service_prices=c.service_economics,
        project_only=True,
    )
    result.pop("decision_key")
    return result


def test_snapshot_roundtrip_reconciles_single_and_shared_projections_without_mutation():
    c, rt, keys = fixture()
    before = copy.deepcopy((rt.public(), rt.orders, rt.ledger.events))
    restored, packet = frozen(rt)
    assert project(rt, c, ((keys[0], 1),)) == project(restored, c, ((keys[0], 1),))
    assert project(rt, c, groups=((keys[:2], 1),)) == project(restored, c, groups=((keys[:2], 1),))
    assert packet == json.loads(json.dumps(capture(rt)))
    assert (rt.public(), rt.orders, rt.ledger.events) == before
    assert restored.source_matches
    assert not hasattr(restored, "_effects") and not hasattr(restored, "dispatch_selected")
    with pytest.raises(ValueError, match="cannot execute"):
        restored.executive.advance(1, restored._context)
    assert restored.executive.at_hour == 0


def test_saved_observations_cannot_be_replaced_by_later_execution_or_private_draws():
    c, rt, d = repair_fixture()
    restored, packet = frozen(rt)
    before = copy.deepcopy(packet)
    keys = tuple(o["id"] for o in rt.orders)
    original = project(restored, c, groups=((keys, 0),))
    rt.dispatch_selected((), charge=False, visit_groups=((keys, 0),))
    faults = FaultState(c.plant, c.scenario, c.faults)
    for hour in range(6):
        if hour:
            rt.prepare(hour, d, 750)
            rt.dispatch_selected((), charge=False)
        rt.end(hour, faults, d)
    assert project(restored, c, groups=((keys, 0),)) == original
    assert packet == before
    # Only named observations/cursors and recipes cross the boundary; the
    # live effect port cannot be reached or restored from the transport.
    assert "random_events" not in json.dumps(packet)
    assert "retrospective_effects" not in json.dumps(packet)


def test_active_shared_commitment_preserves_current_cursors_and_remaining_costs():
    c, rt, keys = fixture(maintenance_work_hours=2)
    rt.dispatch_selected((), charge=False, visit_groups=((keys[:2], 0),))
    faults = FaultState(c.plant, c.scenario, c.faults)
    first = rt.end(0, faults, Diagnosis(450))
    rt.prepare(1, Diagnosis(450), 750)
    restored, _ = frozen(rt)
    assert rt.planned_demands(6) == restored.planned_demands(6)
    assert rt.isolation_horizon(6) == restored.isolation_horizon(6)
    assert rt.ledger.available("stock:maintenance") == restored.ledger.available(
        "stock:maintenance"
    )
    for k, m in rt.executive.missions.items():
        assert (m.stage_index, m.entered, m.status) == (
            restored.executive.missions[k].stage_index,
            restored.executive.missions[k].entered,
            restored.executive.missions[k].status,
        )
    assert first["human_visits"] == 1


def test_frozen_joint_charging_and_production_preserve_the_original_plan():
    c, rt, keys = fixture()
    restored, _ = frozen(rt)
    results = []
    for instance in (rt, restored):
        result = charge_control.evaluate(
            instance,
            c.plant,
            State.initial(c.plant),
            forecast(),
            450,
            c.costs,
            [charge_control.Target("cleaner", 1, 6, "Declared teaching reserve")],
            joint_work=True,
            visit_groups=((keys[:2], 1),),
            service_prices=c.service_economics,
            seconds=2,
        )
        assert result["state"] == "feasible", result["constraints"]
        results.append(result)
    assert results[0]["process_plan"]["actions"] == results[1]["process_plan"]["actions"]
    assert results[0]["mission_pricing"] == results[1]["mission_pricing"]
    assert results[0]["current_requests"] == results[1]["current_requests"]
    assert not rt.executive.missions


def test_snapshot_integrity_and_unavailable_context_are_not_invented():
    _, rt, keys = fixture(crew_available=False)
    _, packet = frozen(rt)
    stored = RecordedServices(packet["snapshot"], packet["catalogue"])
    with pytest.raises(ValueError):
        stored.propose(keys[0])
    for field in ("snapshot", "catalogue"):
        changed = copy.deepcopy(packet)
        if field == "snapshot":
            changed["snapshot"]["at_hour"] = 3
        else:
            changed["catalogue"]["resources"][0]["capacity"] = 999
        with pytest.raises(ValueError, match="mismatch|match"):
            RecordedServices(changed["snapshot"], changed["catalogue"])
    with pytest.raises(ValueError, match="Unsupported or missing"):
        RecordedServices({}, packet["catalogue"])


def test_snapshot_records_model_change_without_claiming_original_execution():
    from methane.services.coupling import identity

    _, rt, _ = fixture()
    packet = capture(rt)
    packet["snapshot"]["service_source"]["planning.py"] = "changed-original-source"
    packet["snapshot"]["snapshot_id"] = identity(
        {k: v for k, v in packet["snapshot"].items() if k != "snapshot_id"}
    )
    restored = RecordedServices(packet["snapshot"], packet["catalogue"])
    assert restored.source_matches is False


@pytest.mark.parametrize("portable", ["none", "wet"])
def test_optical_treatment_projection_uses_only_captured_surface_and_original_raw_forecast(
    portable,
):
    from test_cleaning_forecast import fixture as cleaning_fixture

    from methane.config import Costs
    from methane.service_economics import ACTIVITY_VERSION, illustrative

    args, rt, fc, key = cleaning_fixture(portable=portable)
    restored, packet = frozen(rt)
    predictions = []
    for instance in (rt, restored):
        r = coupling.evaluate(
            instance,
            args["plant"],
            State.initial(args["plant"]),
            fc,
            450,
            Costs(),
            ((key, 0),),
            service_prices=illustrative(Costs(), version=ACTIVITY_VERSION),
            reference_forecast=args["forecast"],
            project_only=True,
        )
        r.pop("decision_key")
        predictions.append(r)
    assert predictions[0]["state"] == "projected", predictions[0]["constraints"]
    assert predictions[0] == predictions[1]
    assert restored.optical.surface.snapshot() == packet["snapshot"]["optical"]["surface"]


def test_new_run_records_preselection_inputs_and_deduplicates_catalogues(tmp_path):
    from dataclasses import replace

    from methane.evidence import load, save
    from methane.provenance import verify
    from methane.simulation import run
    from methane.ui import playback_value

    c, _, _ = fixture()
    c = replace(c, scenario=replace(c.scenario, hours=4))
    result = run(c, strategies=["Greedy"])
    assert result["status"] == "complete", result["failures"]
    assert len(result["service_planning_catalogues"]) == 1
    for row in result["records"]["Greedy"]:
        field = row["field_operations"]
        snapshot = field["planning_snapshot"]
        assert snapshot["at_hour"] == row["hour"]
        current = {p["order"]["order_id"] for p in field["new_missions"]}
        before = {p["plan"]["order"]["order_id"] for p in snapshot["missions"]}
        assert not (current & before)
        restored = RecordedServices(
            snapshot, result["service_planning_catalogues"][snapshot["catalogue_id"]]
        )
        assert restored.executive.at_hour == row["hour"]
        inputs = row["decision"]["service_planning_inputs"]
        assert inputs["forecast"]["decision_hour"] == row["hour"]
        assert "service_kw" not in inputs["forecast"]
        assert inputs["estimate"] == row["decision"]["estimate"]
    archived = load(save(result, tmp_path))
    from methane.services.alternatives import prepare

    packet = prepare(archived, "Greedy", 0)
    assert (
        packet["snapshot"]
        == archived["records"]["Greedy"][0]["field_operations"]["planning_snapshot"]
    )
    assert (
        packet["inputs"]["forecast"]
        == result["records"]["Greedy"][0]["decision"]["service_planning_inputs"]["forecast"]
    )
    assert archived["service_planning_catalogues"] == json.loads(
        json.dumps(result["service_planning_catalogues"])
    )
    view = playback_value(result, register_contexts=False)
    assert "service_planning_catalogues" not in view
    for row in view["records"]["Greedy"]:
        assert "planning_snapshot" not in row["field_operations"]
        assert "service_planning_inputs" not in row["decision"]
        assert row["field_operations"]["planning_context"]["at_hour"] == row["hour"]
    verify(result)
