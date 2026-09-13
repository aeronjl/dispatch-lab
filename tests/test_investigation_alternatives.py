"""Original-information choices, honest branch totals and immutable source runs."""

import copy
import json
from dataclasses import replace
from decimal import Decimal

import pytest
from test_investigator import prepared

from methane.components import assemble
from methane.physics import State
from methane.provenance import LOADED_SOURCE
from methane.services import investigation_alternatives as alternatives
from methane.services.coupling import identity
from methane.services.investigation_examples import fixture as learning_fixture
from methane.services.investigator import Investigator


@pytest.fixture(scope="module")
def recorded_choice():
    c, rt, diagnosis = prepared()
    policy = replace(
        c.investigation_policy, mode="inspect-first", comparison_seconds=2, risk_weight=0
    )
    chooser = Investigator(policy, c.service_policy)
    forecast = learning_fixture("fixed-reader")["forecast"]
    investigation = chooser.step(
        rt,
        diagnosis,
        c.plant,
        State.initial(c.plant),
        forecast,
        225,
        c.costs,
        c.service_economics,
        components=assemble(c.plant, c.models),
    )
    selection = investigation["episodes"][0]["selection"]
    assert selection["selected"], selection["comparison"]
    original = selection["comparison"]["inputs"]
    # This is an explicitly assembled contract fixture, not a claimed run.
    value = dict(
        run_id="investigation-contract-fixture",
        config=c.to_dict(),
        provenance=dict(source=LOADED_SOURCE),
        records={
            "fixture": [
                dict(
                    hour=0,
                    decision=dict(
                        service_control=dict(investigation=investigation),
                        service_planning_inputs=dict(
                            estimate=original["state"],
                            capacity_kw=original["capacity_kw"],
                            forecast=original["forecast"],
                            reference_forecast=original["reference_forecast"],
                        ),
                    ),
                )
            ]
        },
    )
    return json.loads(json.dumps(value))


def request(packet):
    return dict(
        kind="investigation", selection_id=packet["selection_id"], strategy="direct-intervention"
    )


@pytest.fixture(scope="module")
def calculated(recorded_choice):
    packet = alternatives.prepare(recorded_choice, "fixture", 0)
    return alternatives.compare(packet, request(packet))


def test_every_arm_uses_original_inputs_and_preserves_recorded_choice(recorded_choice, calculated):
    before = copy.deepcopy(recorded_choice)
    packet = alternatives.prepare(recorded_choice, "fixture", 0)
    assert calculated["status"] == "complete", calculated
    assert calculated["baseline"]["strategy"] == "inspect-first"
    assert calculated["alternative"]["strategy"] == "direct-intervention"
    assert calculated["recorded"] == packet["recorded"]
    for key in (
        "state",
        "forecast",
        "capacity_kw",
        "costs",
        "prices",
        "prefix",
        "reference_forecast",
    ):
        assert calculated["comparison"]["inputs"][key] == packet["inputs"][key]
    assert identity(calculated["comparison"]["inputs"]["belief"]) == identity(
        packet["inputs"]["belief"]
    )
    assert recorded_choice == before


def test_expected_costs_and_inventories_reconcile_without_double_charging(calculated):
    for name in ("baseline", "alternative"):
        arm = calculated["comparison"]["strategies"][calculated[name]["strategy"]]
        summary = calculated[name]["summary"]["expected"]
        branches = arm["process"]["branches"]

        def weighted(fn, values=branches):
            return float(sum(Decimal(str(b["probability"])) * Decimal(str(fn(b))) for b in values))

        assert summary["methane_kg"] == pytest.approx(
            weighted(lambda b: b["predicted"]["methane_kg"])
        )
        assert summary["total_decision_eur"] == pytest.approx(
            weighted(lambda b: b["service_decision_eur"] + b["predicted"]["variable_and_wear_eur"])
        )
        for key, value in summary["ending"].items():
            assert value == pytest.approx(weighted(lambda b, k=key: b["predicted"]["ending"][k]))
        assert all("Unverified" in c["ending_diagnostic_state"] for c in arm["cases"])
        assert calculated["service_stock_units"]["stock:cleaning"] == "kit"


def test_later_truth_receipts_and_repricing_cannot_enter_original_packet(recorded_choice):
    baseline = alternatives.prepare(recorded_choice, "fixture", 0)
    changed = copy.deepcopy(recorded_choice)
    changed["records"]["fixture"].append(dict(hour=1, state={"temperature_c": 999}))
    changed["retrospective_truth"] = {"fault": "secret damaged module"}
    changed["repriced_report"] = {"prices": {"methane_value_eur_kg": 999}}
    episode = changed["records"]["fixture"][0]["decision"]["service_control"]["investigation"][
        "episodes"
    ][0]
    episode.update(finding={"secret": True}, recovery_belief={"later": True}, confirmed_at=20)
    assert alternatives.prepare(changed, "fixture", 0) == baseline
    assert "retrospective_truth" not in json.dumps(baseline)
    assert "episodes" not in baseline


def test_missing_original_and_later_selection_request_are_explicit(recorded_choice):
    changed = copy.deepcopy(recorded_choice)
    changed["records"]["fixture"].append(
        {**copy.deepcopy(changed["records"]["fixture"][0]), "hour": 1}
    )
    description = alternatives.describe(changed, "fixture", 1)
    assert description["origin_hour"] == 0 and "selection_id" not in description
    with pytest.raises(ValueError, match="Return to original"):
        alternatives.prepare(changed, "fixture", 1)
    changed["records"]["fixture"][0]["decision"]["service_control"] = {}
    assert "No original" in alternatives.describe(changed, "fixture", 0)["unavailable"]


@pytest.mark.parametrize("change", ["price", "state", "identity", "policy"])
def test_inconsistent_original_records_are_rejected(recorded_choice, change):
    changed = copy.deepcopy(recorded_choice)
    row = changed["records"]["fixture"][0]
    if change == "price":
        changed["config"]["costs"]["methane_eur_kg"] = 999
    elif change == "state":
        row["decision"]["service_planning_inputs"]["estimate"]["battery_kwh"] = 999
    elif change == "identity":
        row["decision"]["service_control"]["investigation"]["episodes"][0]["selection"][
            "selection_id"
        ] = "changed"
    else:
        row["decision"]["service_control"]["investigation"]["policy"]["risk_weight"] = 1
    with pytest.raises(ValueError):
        alternatives.prepare(changed, "fixture", 0)


def test_unknown_and_stale_alternatives_and_changed_packets_are_rejected(recorded_choice):
    packet = alternatives.prepare(recorded_choice, "fixture", 0)
    for extra in (
        {"strategy": "camera"},
        {"strategy": "inspect-first"},
        {"selection_id": "later"},
        {"prices": {}},
    ):
        with pytest.raises(ValueError):
            alternatives.validate_request(packet, {**request(packet), **extra})
    packet["seconds"] += 1
    with pytest.raises(ValueError, match="integrity"):
        alternatives.compare(packet, request(packet))


def test_incomplete_branches_are_not_renormalized_and_requirement_remains_visible(calculated):
    arm = copy.deepcopy(calculated["comparison"]["strategies"]["inspect-first"])
    arm.update(status="incomplete", conditions=["Crew unavailable in one possible branch"])
    summary = alternatives.summary(arm, 1)
    assert summary["expected"] is None and summary["restoration_probability"] is None
    assert not summary["eligible"]
    arm["status"] = "feasible"
    arm["process"]["branches"].pop()
    with pytest.raises(ValueError, match="probability mass"):
        alternatives.summary(arm, 1)
    genuine = calculated["comparison"]["strategies"]["inspect-first"]
    assert not alternatives.summary(genuine, 1)["eligible"]


def test_real_transport_worker_isolated_and_same_generation_cannot_change_choices(recorded_choice):
    import time

    from fastapi import HTTPException

    from methane import service_alternatives_service as service
    from methane.model_service import register

    service.cleanup()
    values = dict(
        token=register(recorded_choice),
        run_id=recorded_choice["run_id"],
        key="investigation-1",
        controller="fixture",
        hour=0,
    )

    def call(op, **extra):
        return service.handle(service.Request(**values, operation=op, **extra))

    try:
        description = call("describe")
        assert description["status"] == "available"
        assert description["investigation"]["selected_strategy"] == "inspect-first"
        packet = alternatives.prepare(recorded_choice, "fixture", 0)
        job = call("start", alternative=request(packet))["job_id"]
        with pytest.raises(HTTPException) as exc:
            call("poll", job_id=job, alternative={**request(packet), "strategy": "other"})
        assert exc.value.status_code == 409
        end = time.monotonic() + 25
        while time.monotonic() < end:
            result = call("poll", job_id=job)
            if result["status"] != "running":
                break
            time.sleep(0.05)
        assert result["status"] == "complete", result
        assert result["kind"] == "investigation"
        assert result["key"] == values["key"]
        text = (service.Path(service._jobs[job]["directory"].name) / "input.json").read_text()
        assert '"records"' not in text and '"retrospective_truth"' not in text
    finally:
        service.cleanup()
