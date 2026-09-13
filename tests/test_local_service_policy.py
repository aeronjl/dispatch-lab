"""Explicit local rules: independent cadence, withheld truth and interface access."""

import copy
from dataclasses import replace
from decimal import Decimal

import pytest

from methane.config import Config, Scenario, WeatherConfig
from methane.field_operations import FieldOperations
from methane.reference import audit
from methane.sensing import Diagnosis
from methane.services.configuration import ServiceSystem
from methane.services.contracts import WorkOrder
from methane.services.core import ASSETS
from methane.services.inspection_demo import execute
from methane.services.inspection_demo import fixture as inspection_fixture
from methane.services.plant import PlantServices
from methane.simulation import run
from methane.weather import synthetic


def fixture(**options):
    return Config(
        scenario=Scenario(hours=12, horizon_hours=6, solver_seconds=0.05),
        weather=WeatherConfig(loss_fraction=0, temperature_coefficient=0),
        field_operations=FieldOperations(
            enabled=True,
            rover_enabled=False,
            reset_enabled=False,
            human_fallback=False,
            initial_soiling_fraction=0.1,
            soiling_per_day=0,
            cleaning_removal_fraction=1,
            mission_failure_probability=0,
        ),
        service_system=ServiceSystem(
            **(
                dict(
                    inspector="none",
                    cleaning_model="section-optical/1",
                    cleaning_policy="periodic",
                    cleaning_period_hours=4,
                )
                | options
            ),
        ),
    )


def execute_cleaning(c):
    w = synthetic(c)
    for mapping in (w["truth"], w["template"]):
        for s in mapping.values():
            s.update(irradiance_wm2=1000, pv_kw=1000, ambient_c=20)
    r = run(c, weather=w, strategies=["Greedy"])
    assert r["status"] == "complete", r["failures"]
    return r


def fields(r):
    return [q["field_operations"] for q in r["records"]["Greedy"]]


def check(r):
    a = audit(r)
    assert a["passed"], [x for x in a["checks"] if not x["passed"]][:8]


@pytest.fixture(scope="module")
def periodic():
    return execute_cleaning(fixture())


def test_complete_pass_recurrence_and_no_early_credit(periodic):
    rows = fields(periodic)
    check(periodic)
    events = [e for r in rows for e in r["cleaning_policy_effects"]]
    assert len(events) >= 3
    for e in events:
        assert e["next_due_hour"] == float(Decimal(str(e["completed_at"])) + Decimal(4))
        assert e["effective_at"] >= e["completed_at"]
        earlier = rows[e["effective_at"] - 1]["decision"]["cleaning_policy"]["schedules"]
        assert next(s for s in earlier if s["section"] == e["section"])["completed_passes"] == 0
    assert rows[0]["treated_area_m2"] > 0 and rows[0]["cleaning_policy_effects"] == []
    forged = copy.deepcopy(periodic)
    event = next(r for r in fields(forged) if r["cleaning_policy_effects"])[
        "cleaning_policy_effects"
    ][0]
    event["next_due_hour"] += 1
    assert not audit(forged)["passed"]


@pytest.mark.parametrize("rule", ["off", "condition", "periodic"])
def test_rules_share_optical_mechanics_and_record_original_inputs(rule):
    c = fixture()
    c = replace(c, service_system=replace(c.service_system, cleaning_policy=rule))
    r = execute_cleaning(c)
    check(r)
    rows = fields(r)
    assert (
        rows[0]["surface_before"]
        == fields(execute_cleaning(fixture(cleaning_first_due_hour=20)))[0]["surface_before"]
    )
    orders = rows[-1]["state"]["orders"]
    if rule == "off":
        assert orders == [] and sum(x["treated_area_m2"] for x in rows) == 0
    else:
        assert orders and all(q["cleaning_rule"] == rule for q in orders)


def test_partial_work_and_empty_supplies_do_not_advance_cadence():
    c = fixture(work_failure_fraction=0.3)
    c = replace(c, field_operations=replace(c.field_operations, mission_failure_probability=1))
    r = execute_cleaning(c)
    check(r)
    assert sum(f["treated_area_m2"] for f in fields(r)) > 0
    assert not any(f["cleaning_policy_effects"] for f in fields(r))
    assert all(
        s["completed_passes"] == 0 for s in fields(r)[-1]["state"]["cleaning_policy"]["schedules"]
    )
    c = fixture()
    c = replace(c, field_operations=replace(c.field_operations, cleaning_kits=0))
    r = execute_cleaning(c)
    check(r)
    order = fields(r)[-1]["state"]["orders"][0]
    assert order["status"] == "queued" and "stock:cleaning" in order["blocked"]


def test_periodic_uses_declared_clock_even_on_clean_surface_and_no_future_fault_truth():
    c = fixture(cleaning_first_due_hour=3)
    c = replace(c, field_operations=replace(c.field_operations, initial_soiling_fraction=0))
    a = execute_cleaning(c)
    b = execute_cleaning(
        replace(c, scenario=replace(c.scenario, fault_start_hour=8, capacity_fraction=0.3))
    )
    assert fields(a)[:8] == fields(b)[:8]
    assert not fields(a)[2]["state"]["orders"]
    assert fields(a)[3]["state"]["orders"][0]["created_hour"] == 3
    check(a)


@pytest.mark.parametrize("mechanism", ["bounded-contact/1", "referenced-contact/1"])
def test_enclosed_contact_selects_human_procedure_without_fake_reader_evidence(mechanism):
    c = inspection_fixture("trip")
    c = replace(
        c,
        service_system=replace(
            c.service_system,
            inspector="mobile",
            inspection_model=mechanism,
            inspection_interface="enclosed-contact",
        ),
    )
    r = execute(c)
    check(r)
    orders = fields(r)[-1]["state"]["orders"]
    assert any(q["kind"] == "module-replacement" for q in orders)
    assert not any(q["kind"] in ("inspection", "inspection-confirm", "reset") for q in orders)
    assert all(
        not any(
            x["channel"].startswith(("contact-", "trip-contact"))
            for x in q["state"]["executive"]["observations"]
        )
        for q in fields(r)
    )


def test_accessible_port_acquires_evidence_and_direct_incompatible_build_is_blocked():
    c = inspection_fixture("trip")
    c = replace(
        c,
        service_system=replace(
            c.service_system, inspector="mobile", inspection_interface="accessible-port"
        ),
    )
    r = execute(c)
    check(r)
    assert any(q["state"]["executive"]["observations"] for q in fields(r))
    o = replace(c.service_system, inspection_interface="enclosed-contact")
    rt = PlantServices(c.field_operations, o, 7, c.plant.electrolyser_kw)
    ctx = rt.context(0, Diagnosis(450))
    face = rt.registry.interfaces["ELY/contact"]
    cap = next(k for k, v in rt.registry.capabilities.items() if v.action == "read-trip-contact")
    with pytest.raises(ValueError, match="contact-port-accessible"):
        rt.registry.build(
            WorkOrder("TEST", "read-trip-contact", face.interface_id, 0, "Declared request"),
            ASSETS["rover"],
            cap,
            ctx,
        )


def test_invalid_rules_and_fractional_input_contracts():
    with pytest.raises(ValueError):
        ServiceSystem(cleaning_policy="periodic")
    with pytest.raises(ValueError):
        fixture(cleaning_period_hours=0)
    with pytest.raises(ValueError):
        ServiceSystem(inspection_interface="magic")
    o = ServiceSystem(cleaning_first_due_hour=2, cleaning_period_hours=8)
    assert isinstance(o.cleaning_first_due_hour, float) and isinstance(
        o.cleaning_period_hours, float
    )


def test_period_outcomes_are_independently_checked_and_missing_is_not_zero(periodic):
    m = periodic["metrics"]["Greedy"]["service_outcomes"]
    assert m["cleaning_treated_m2"] == sum(f["treated_area_m2"] for f in fields(periodic))
    assert m["contact_first_usable_hour"] is None and m["dock_unserved_kwh"] is None
    altered = copy.deepcopy(periodic)
    altered["metrics"]["Greedy"]["service_outcomes"]["cleaning_treated_m2"] += 1
    assert not audit(altered)["passed"]
