"""Independent candidate money calculations and reconciliation with executed work."""

import copy

import pytest

from methane.config import Costs, Plant, Scenario
from methane.faults import FaultPolicy, FaultState
from methane.field_operations import FieldOperations
from methane.reference import service_accounts
from methane.sensing import Diagnosis
from methane.service_economics import ACTIVITY_VERSION, illustrative, report
from methane.services.adapters import fixed
from methane.services.configuration import ServiceSystem
from methane.services.contracts import Asset, Capability, Context, Interface, Quantity, WorkOrder
from methane.services.core import ASSETS
from methane.services.planning import Commitment
from methane.services.plant import PlantServices
from methane.services.pricing import price


def rates():
    a = illustrative(Costs(), version=ACTIVITY_VERSION)
    for asset in a["assets"].values():
        for key in asset:
            if key not in ("provision", "life_years"):
                asset[key] = 0
    for key in a["rates"]:
        a["rates"][key] = 0
    return a


def simple_plan(hours=2, start=0, kind="observe", consumables=()):
    asset = Asset(ASSETS["cleaner"], "test station", "example/1", "port", "fixed", ("work",), ())
    cap = Capability("work", "test", kind, "procedure/1", hours, 0, consumables=consumables)
    interface = Interface("port", ASSETS["cleaner"], "port", ("test",), ())
    return fixed(
        WorkOrder("candidate", "test", "port", start, "Explicit cost example"),
        asset,
        interface,
        cap,
        Context(start, ()),
    )


def prefix_with_part():
    return [
        dict(
            field_operations=dict(
                hour=0,
                assets=dict(cleaner=True),
                human_visits=0,
                crew_committed_hours=0,
                mission_events=[],
                support_effects=[],
                resource_events=[
                    dict(
                        kind="consume",
                        resource="stock:brush",
                        amount=1,
                        unit="kit",
                        phase="perform",
                    )
                ],
                state=dict(executive=dict(resources=[])),
            )
        )
    ]


def test_candidate_wear_is_incremental_to_the_existing_parts_pool():
    a = rates()
    a["assets"]["cleaner"]["wear_eur_per_hour"] = 10
    prefix = prefix_with_part()
    before = copy.deepcopy(prefix)
    for duration, expected in ((2, 0), (12, 20)):
        quote = price(
            (),
            (Commitment(simple_plan(duration, 1)),),
            a,
            at_hour=1,
            hours=duration,
            installed=["cleaner"],
            prefix=prefix,
        )
        # Existing brush expenditure/consumption allowance is €100.
        # max(100, 2*10)-100=0; max(100, 12*10)-100=20.
        assert quote["incremental_decision_eur"] == expected
        assert quote["incremental_expenditure_eur"] == 0
        assert quote["status"] == "complete"
        assert all(
            isinstance(p, str)
            for paths in quote["with_additions"]["quantity_sources"].values()
            for p in paths
        )
    assert prefix == before


def test_ownership_does_not_enter_candidate_dispatch_cost_and_contract_wear_is_covered():
    a = rates()
    a["assets"]["cleaner"].update(
        capital_eur=100000, replaceable_capital_eur=20000, wear_eur_per_hour=2
    )
    work = Commitment(simple_plan())
    quote = price((), (work,), a, at_hour=0, hours=2, installed=["cleaner"])
    assert quote["incremental_decision_eur"] == 4
    a["assets"]["cleaner"]["capital_eur"] *= 10
    assert (
        price((), (work,), a, at_hour=0, hours=2, installed=["cleaner"])["incremental_decision_eur"]
        == 4
    )
    a["assets"]["cleaner"].update(
        provision="contracted",
        capital_eur=0,
        replaceable_capital_eur=0,
        wear_eur_per_hour=0,
        service_eur_per_active_hour=5,
    )
    quote = price((), (work,), a, at_hour=0, hours=2, installed=["cleaner"])
    assert quote["incremental_decision_eur"] == 10
    assert quote["incremental_expenditure_eur"] == 10


def test_unfinished_return_or_unknown_delivery_disposition_is_not_free():
    a = rates()
    later = price((), (Commitment(simple_plan(3)),), a, at_hour=0, hours=2, installed=["cleaner"])
    assert later["status"] == "conditional" and later["incremental_decision_eur"] is None
    delivery = Commitment(
        simple_plan(1, kind="supply", consumables=(Quantity("upstream:water", 10, "L"),))
    )
    quote = price((), (delivery,), a, at_hour=0, hours=2, installed=["cleaner"])
    assert quote["status"] == "conditional" and quote["incremental_decision_eur"] is None
    assert quote["incremental_expenditure_eur"] == pytest.approx(0.03)
    assert "destination inventory" in quote["conditions"][0]["condition"]


def test_missing_applicable_prices_and_missing_prefix_are_explicit():
    a = rates()
    a["assets"]["cleaner"]["wear_eur_per_hour"] = None
    quote = price((), (Commitment(simple_plan()),), a, at_hour=0, hours=2, installed=["cleaner"])
    assert quote["status"] == "incomplete-prices" and quote["incremental_decision_eur"] is None
    with pytest.raises(ValueError, match="prefix"):
        price((), (), a, at_hour=1, hours=2, installed=["cleaner"])


def executed_reader():
    cfg = FieldOperations(
        enabled=True,
        cleaner_enabled=False,
        human_fallback=False,
        reset_enabled=False,
        dock_available=False,
        mission_failure_probability=0,
    )
    options = ServiceSystem(
        inspector="fixed",
        support_model="logistics/1",
        contact_unreadable_probability=0,
        contact_error_probability=0,
    )
    rt = PlantServices(cfg, options, 7, 450)
    d = Diagnosis(
        225,
        active_incident=True,
        incidents=1,
        informative=True,
        status="capacity loss",
        tracking_residual=0.5,
    )
    faults = FaultState(
        Plant(),
        Scenario(fault_start_hour=0, capacity_fraction=0.5),
        FaultPolicy(capacity_cause="equipment-damage"),
    )
    rt.prepare(0, d, 650)
    candidate, _ = rt.propose(rt.orders[0]["id"])
    a = rates()
    a["assets"]["fixed_reader"]["wear_eur_per_hour"] = 8
    quote = price(
        (),
        (Commitment(candidate),),
        a,
        at_hour=0,
        hours=2,
        installed=[k for k, v in rt.interval["assets"].items() if v],
    )
    rt.dispatch_selected(((candidate.order.order_id, 0),), charge=False)
    rows = [dict(field_operations=rt.end(0, faults, d))]
    rt.prepare(1, d, 650)
    rt.dispatch_selected((), charge=False)
    rows.append(dict(field_operations=rt.end(1, faults, d)))
    return a, quote, rows


def test_fixed_hardware_usage_prices_match_original_interval_events_and_independent_arithmetic():
    a, quote, rows = executed_reader()
    actual = report(rows, a)
    independent = service_accounts(a, rows)
    # 1 h reading + .25 h verification, at €8 / active h = €10.
    assert quote["incremental_decision_eur"] == actual["views"]["decision"]["total_eur"] == 10
    assert float(independent["decision"]) == 10
    assert actual["quantities"]["fixed_reader_hours"] == 1.25
    assert actual["schema_version"] == ACTIVITY_VERSION
    legacy = copy.deepcopy(a)
    legacy["schema_version"] = "dispatch-lab/service-economics/1"
    assert report(rows, legacy)["views"]["decision"]["total_eur"] == 0
    assert all(isinstance(p, str) for p in actual["quantity_sources"]["fixed_reader_hours"])
    assert "fixed_reader_hours" not in rows[0]["field_operations"]


def test_activity_prices_do_not_invent_missing_events_and_reject_double_counting():
    a, _, rows = executed_reader()
    changed = copy.deepcopy(rows)
    changed[0]["field_operations"]["mission_events"] *= 2
    with pytest.raises(ValueError, match="overlapping"):
        report(changed, a)
    del changed[0]["field_operations"]["mission_events"]
    with pytest.raises(ValueError, match="original mission"):
        report(changed, a)


def test_recorded_cost_input_projection_preserves_operands_and_original_paths():
    from test_service_charging import control, runtime, service_prices

    from methane.config import Plant, Scenario
    from methane.faults import FaultPolicy, FaultState
    from methane.service_economics import quantities, report
    from methane.services.charge_control import accept
    from methane.services.pricing import recorded_inputs

    rt, diagnosis = runtime()
    rt.prepare(0, diagnosis, 10)
    plan = control(rt)
    accept(rt, plan)
    row = rt.end(0, FaultState(Plant(), Scenario(), FaultPolicy()), diagnosis)
    rows = [dict(field_operations=row, decision=dict(irrelevant="x" * 1_000_000))]
    for activity in (True, False):
        projection = recorded_inputs(rows, activity=activity)
        assert projection["hours"] == 1
        assert quantities(rows, activity=activity) == quantities(
            projection["rows"], activity=activity
        )
        assert "decision" not in projection["rows"][0]
        assert "decision" not in projection["rows"][0]["field_operations"]
        assert report(rows, service_prices(), detailed=False) == report(
            projection["rows"], service_prices(), detailed=False
        )
        before = projection["prefix_id"]
        rows[0]["decision"]["irrelevant"] = "different unrelated text"
        assert recorded_inputs(rows, activity=activity)["prefix_id"] == before
    rows[0]["field_operations"]["charge_input_kwh"] += 0.01
    assert recorded_inputs(rows)["prefix_id"] != before


def test_cost_projection_fails_closed_if_a_future_dependency_is_omitted(monkeypatch):
    from methane.services.pricing import recorded_inputs

    monkeypatch.setattr(
        "methane.services.pricing.quantities", lambda rows, **_: rows[0].get("new_operand")
    )
    with pytest.raises(ValueError, match="does not preserve"):
        recorded_inputs([dict(new_operand=5)])
