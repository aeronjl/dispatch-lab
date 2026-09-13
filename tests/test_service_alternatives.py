"""Paired predictions retain the original information and economic boundary."""

import copy
import json
from dataclasses import asdict

import pytest
from test_visit_planning import fixture, forecast

from methane.components import assemble
from methane.physics import State
from methane.provenance import LOADED_SOURCE, digest
from methane.services import charge_control, coupling
from methane.services.alternatives import compare, prepare
from methane.services.pricing import recorded_inputs
from methane.services.snapshot import RecordedServices, capture
from methane.simulation import digest as process_digest


def source(*, joint=False, groups=True, start=1, charge=False):
    c, rt, keys = fixture()
    if charge:
        rt.ledger.stock["energy:cleaner"] = 0.5
    captured = capture(rt)
    singles = () if groups else ((keys[0], start),)
    visits = ((keys[:2], start),) if groups else ()
    targets = [charge_control.Target("cleaner", 1, 1, "Original reserve")] if charge else []
    if joint:
        evaluation = charge_control.evaluate(
            rt,
            c.plant,
            State.initial(c.plant),
            forecast(),
            450,
            c.costs,
            targets,
            service_prices=c.service_economics,
            joint_work=True,
            selections=singles,
            visit_groups=visits,
            seconds=2,
            components=assemble(c.plant, c.models),
        )
        assert evaluation["state"] == "feasible", evaluation["constraints"]
        charge_control.accept(rt, evaluation)
        planned = evaluation["process_plan"]
    else:
        evaluated = coupling.evaluate(
            rt,
            c.plant,
            State.initial(c.plant),
            forecast(),
            450,
            c.costs,
            singles,
            visit_groups=visits,
            service_prices=c.service_economics,
            objective="greedy",
        )
        assert evaluated["state"] == "feasible", evaluated["constraints"]
        planned = evaluated["process_plan"]
        rt.dispatch_selected(singles, charge=charge, visit_groups=visits)
    inputs = dict(
        schema_version="service-process-planning-inputs/1",
        estimate=asdict(State.initial(c.plant)),
        capacity_kw=450,
        forecast=forecast(),
        reference_forecast=None,
        objective="methane" if joint else "greedy",
        terminal_battery_value=0,
        cost_version=process_digest(asdict(c.costs)),
        service_cost_version=digest(c.service_economics),
    )
    decision = dict(service_planning_inputs=inputs, plan=planned)
    if joint:
        decision["service_control"] = dict(
            status="selected",
            selected_candidate_id="original",
            fallback_used=False,
            inputs=dict(
                targets=[asdict(t) for t in targets],
                obligations=[],
                service_cost_prefix=recorded_inputs(()),
            ),
            candidates=[dict(candidate_id="original", evaluation=evaluation)],
        )
    field = copy.deepcopy(rt.interval)
    field["planning_snapshot"] = captured["snapshot"]
    result = dict(
        run_id="saved-service-example",
        config=c.to_dict(),
        provenance=dict(source=dict(content_hash=LOADED_SOURCE["content_hash"])),
        service_planning_catalogues={captured["snapshot"]["catalogue_id"]: captured["catalogue"]},
        records={"teaching": [dict(hour=0, decision=decision, field_operations=field)]},
    )
    return result, keys, rt


def request(key, delay=1):
    return dict(kind="postpone", order_id=key, delay_hours=delay)


def test_shared_visit_moves_as_one_and_retains_independent_cost_and_stock_totals():
    result, keys, _ = source()
    before = copy.deepcopy(result)
    packet = json.loads(json.dumps(prepare(result, "teaching", 0)))
    answer = compare(packet, request(keys[1]))
    assert answer["status"] == "complete", answer
    assert answer["changed_order_ids"] == list(keys[:2])
    assert answer["baseline"]["schedule"]["groups"][0][1] == 1
    assert answer["alternative"]["schedule"]["groups"][0][1] == 2
    assert answer["objective"] == "greedy"
    for name in ("baseline", "alternative"):
        s = answer[name]["summary"]
        # One €300 callout, 1.5 crew h at €80, .5 travel h at €20,
        # two €50 maintenance kits. No speculative health benefit.
        assert s["service_decision_eur"] == pytest.approx(530)
        assert s["total_decision_eur"] == pytest.approx(
            s["prediction"]["variable_and_wear_eur"] + 530
        )
        assert s["ending_service_stocks"]["stock:maintenance"] == 6
        assert len(s["unselected_work"]) == 2
    assert result == before
    assert (
        answer["recorded"]["process_prediction"]
        == result["records"]["teaching"][0]["decision"]["plan"]["predicted"]
    )
    assert answer["same_application_source"] and answer["same_service_source"]


def test_selected_single_keeps_other_work_and_fixed_current_charging():
    result, keys, _ = source(groups=False, start=2, charge=True)
    packet = prepare(result, "teaching", 0)
    assert packet["fixed_charges"]
    answer = compare(packet, request(keys[0]))
    assert answer["status"] == "complete", answer
    for k in ("baseline", "alternative"):
        # The fixture dock supplies 1 kWh, of which 0.9 reaches the battery.
        assert answer[k]["summary"]["ending_service_stocks"]["energy:cleaner"] == pytest.approx(1.4)
        assert answer[k]["evaluation"]["demand"]["projection"]["rows"][0]["bus_kwh"] >= 1
        # €300 callout + one crew h at €80 + .5 vehicle h at €20 + €50 kit.
        # The fixture's dock usage rate is zero; ownership stays outside dispatch.
        assert answer[k]["summary"]["service_decision_eur"] == pytest.approx(440)
        assert answer[k]["summary"]["cost_status"] == "complete"


def test_missing_charge_usage_price_retains_physical_prediction_and_incomplete_comparison():
    result, keys, _ = source(groups=False, start=2, charge=True)
    prices = result["config"]["service_economics"]
    prices["assets"]["dock"]["wear_eur_per_hour"] = None
    result["records"]["teaching"][0]["decision"]["service_planning_inputs"][
        "service_cost_version"
    ] = digest(prices)
    answer = compare(prepare(result, "teaching", 0), request(keys[0]))
    assert answer["status"] == "incomplete"
    for k in ("baseline", "alternative"):
        s = answer[k]["summary"]
        assert s["state"] == "feasible" and s["prediction"]
        assert s["cost_status"] == "incomplete"
        assert s["total_decision_eur"] is None and s["service_decision_eur"] is None
    assert answer["differences"]["decision_eur"] is None


def test_current_charge_readonly_port_and_joint_reserve_use_real_drawn_down_stock():
    result, _, rt = source(joint=True, charge=True, start=2)
    assert any(m.plan.order.action.startswith("charge-") for m in rt.executive.missions.values())
    packet = prepare(result, "teaching", 0)
    assert packet["fixed_charges"] == []
    restored = RecordedServices(packet["snapshot"], packet["catalogue"])
    _, assessment = restored.propose_charge("cleaner", 1)
    assert assessment["feasible"]
    answer = compare(
        packet, dict(kind="reserve-energy", robot="cleaner", energy_kwh=1.3, due_hour=1)
    )
    assert answer["status"] == "complete", answer
    alternative = answer["alternative"]["evaluation"]
    first = alternative["charging"]["plan"]["charging"][0]
    assert first["after_kwh"] >= 1.3 - 1e-6
    assert alternative["current_requests"]
    assert answer["baseline"]["targets"][0]["energy_kwh"] == 1
    assert answer["alternative"]["targets"][0]["energy_kwh"] == 1.3

    # The same reserve above the physical one-hour charging limit remains
    # unchanged and infeasible; it is not clamped to a convenient target.
    rejected = compare(
        packet, dict(kind="reserve-energy", robot="cleaner", energy_kwh=2, due_hour=1)
    )
    assert rejected["status"] == "incomplete"
    assert rejected["alternative"]["targets"][0]["energy_kwh"] == 2
    assert rejected["alternative"]["evaluation"]["constraints"]


def test_no_future_rows_fault_truth_repricing_or_random_receipts_enter_packet():
    result, _, _ = source()
    original = prepare(result, "teaching", 0)
    result["records"]["teaching"].append(
        dict(hour=1, future_weather="not eligible", fault_truth="secret")
    )
    result["retrospective_truth"] = ["changed hidden fault"]
    result["weather"] = dict(realized=[0, 9999])
    result["config"]["faults"]["capacity_start_hour"] = 999
    result["cost_report"] = dict(costs=dict(methane_eur_per_kg=100000))
    result["records"]["teaching"][0]["field_operations"]["retrospective_effects"] = ["success"]
    assert prepare(result, "teaching", 0) == original
    assert "stochastic_event" not in json.dumps(original["snapshot"])


@pytest.mark.parametrize(
    "change", ["prices", "snapshot", "missing", "context", "recovery", "probe"]
)
def test_missing_original_or_inconsistent_information_is_explicit(change):
    result, _, _ = source()
    d = result["records"]["teaching"][0]
    if change == "prices":
        result["config"]["costs"]["methane_eur_per_kg"] = 99
    elif change == "snapshot":
        d["field_operations"]["planning_snapshot"]["resources"]["stock"]["energy:cleaner"] = 999
    elif change == "missing":
        del d["decision"]["service_planning_inputs"]
    elif change == "context":
        d["decision"]["service_planning_inputs"]["forecast"]["decision_hour"] = 1
    elif change == "probe":
        d["decision"]["probe"] = True
    else:
        d["decision"]["recovery_planning"] = dict(status="scheduled")
    with pytest.raises(ValueError):
        prepare(result, "teaching", 0)


def test_delay_past_horizon_retains_baseline_and_explicit_infeasible_alternative():
    result, keys, _ = source()
    answer = compare(prepare(result, "teaching", 0), request(keys[0], 24))
    assert answer["status"] == "incomplete"
    assert answer["baseline"]["summary"]["prediction"] is not None
    assert answer["alternative"]["summary"]["prediction"] is None
    assert answer["alternative"]["evaluation"]["constraints"]
    assert answer["alternative"]["schedule"]["groups"][0][1] == 25
    assert answer["differences"] is None


@pytest.mark.parametrize("bad", [0, -1, True, float("nan")])
def test_invalid_delays_not_silently_normalized(bad):
    result, keys, _ = source()
    with pytest.raises(ValueError):
        compare(prepare(result, "teaching", 0), request(keys[0], bad))


def test_cannot_postpone_unselected_work_or_relax_prior_energy_commitment():
    result, keys, _ = source()
    packet = prepare(result, "teaching", 0)
    with pytest.raises(ValueError, match="not newly selected"):
        compare(packet, request(keys[-1]))
    with pytest.raises(ValueError, match="not a cleaning"):
        compare(packet, {**request(keys[0]), "kind": "defer-cleaning"})
    result, _, _ = source(joint=True, charge=True, start=2)
    packet = prepare(result, "teaching", 0)
    with pytest.raises(ValueError, match="keeps its deadline"):
        compare(packet, dict(kind="reserve-energy", robot="cleaner", energy_kwh=0.5, due_hour=1))
    with pytest.raises(ValueError, match="keeps its deadline"):
        compare(packet, dict(kind="reserve-energy", robot="cleaner", energy_kwh=2, due_hour=2))


def test_changed_model_is_labelled_and_sealed_packet_cannot_be_repriced():
    result, keys, _ = source()
    result["provenance"]["source"]["content_hash"] = "historical implementation"
    packet = prepare(result, "teaching", 0)
    answer = compare(packet, request(keys[0]))
    assert not answer["same_application_source"]
    packet["costs"]["methane_eur_per_kg"] = 99
    with pytest.raises(ValueError, match="integrity mismatch"):
        compare(packet, request(keys[0]))


def test_deadline_history_distinguishes_observed_satisfaction_and_conditional_continuation():
    from methane.services.alternatives import deadline_evidence

    obligations = [
        dict(id="past", current_order_id="a", status="verified", satisfied_at=4, due_hour=5),
        dict(id="late", current_order_id="b", status="completed", satisfied_at=6, due_hour=5),
        dict(id="working", current_order_id="c", status="active", due_hour=8),
        dict(id="waiting", current_order_id="d", status="queued", due_hour=8),
    ]
    evidence = deadline_evidence(obligations, {"c": 7})
    assert evidence[0]["met"] and evidence[0]["observed_satisfied_at"] == 4
    assert evidence[0]["predicted_completion_at"] is None
    assert not evidence[1]["met"] and evidence[1]["observed_satisfied_at"] == 6
    assert evidence[2]["met"] and evidence[2]["observed_satisfied_at"] is None
    assert evidence[2]["predicted_completion_at"] == 7
    assert "verification remains unknown" in evidence[2]["basis"]
    assert not evidence[3]["met"] and evidence[3]["basis"] == "Completion not established"
