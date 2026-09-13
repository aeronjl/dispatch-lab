"""Future findings are guards, never observations usable by current execution."""

import copy

import pytest
from test_visit_planning import fixture, forecast

from methane.config import Costs, Plant
from methane.physics import State
from methane.services.conditional_work import GuardedWork, project, remedy
from methane.services.contracts import Context
from methane.services.investigation_belief import findings, illustrative, update
from methane.services.scenario_planning import Branch, solve


def guarded():
    c, rt, _ = fixture(inspection_model="referenced-contact/1", inspection_noise_v=0)
    b = update(illustrative(), Context(0, ()), rt.options)
    return c, rt, findings(b, "fixed", rt.options, measured_at=0.5)["branches"]


def test_guarded_reset_keeps_missing_observation_and_cannot_be_executed():
    c, rt, branches = guarded()
    before = copy.deepcopy((rt.public(), rt.ledger.events, rt._context))
    prediction = remedy(rt, "reset", requested_at=1, finding=branches[0])
    assert rt._context.latest("trip-contact").value is None
    assert rt._context.latest("trip-contact").quality == "uncertain"
    assert prediction.plan.context == rt._context
    assert any(r.channel == "trip-contact" for r in prediction.plan.capability.requirements)
    projected = project(rt, (prediction,), forecast(), c.service_economics)
    assert projected["context"] == "prediction"
    assert projected["service_pricing"]["status"] == "complete"
    assert projected["forecast"]["electrolyser_isolated"][1]
    assert projected["projection"]["rows"][1]["bus_kwh"] == pytest.approx(
        (rt.options.reset_hours + rt.options.verification_hours) * rt.options.reset_kw
    )
    with pytest.raises(ValueError, match="predictions"):
        rt.executive.submit(prediction.plan)
    assert (rt.public(), rt.ledger.events, rt._context) == before


def test_qualified_response_lead_begins_when_the_conditional_request_becomes_known():
    c, rt, _ = fixture(
        crew_response_lead_hours=2, inspection_model="referenced-contact/1", inspection_noise_v=0
    )
    b = update(illustrative(), Context(0, ()), rt.options)
    finding = findings(b, "fixed", rt.options, measured_at=0.5)["branches"][1]
    work = remedy(rt, "module-replacement", requested_at=1, finding=finding)
    assert work.plan.order.requested_at == 1 and work.plan.starting_at == 3
    r = project(rt, (work,), forecast(12), c.service_economics)
    used = sum(
        q["amount"]
        for row in r["projection"]["rows"]
        for q in row["stock_use"]
        if q["resource"] == "stock:module"
    )
    assert used == 1
    hours = sum(
        q["amount"]
        for row in r["projection"]["rows"]
        for q in row["stock_use"]
        if q["resource"] == "crew-hours"
    )
    # .25 h each way, original hands-on and verification time, no second visit.
    assert hours == pytest.approx(
        0.5 + c.field_operations.human_work_hours + rt.options.verification_hours
    )
    assert r["service_pricing"]["with_additions"]["predicted_quantities"]["human_visits"] == 1


def test_premature_stale_or_open_findings_do_not_permit_a_reset():
    _, rt, branches = guarded()
    for finding, when in ((branches[0], 0), (branches[1], 1), (branches[0], 100)):
        with pytest.raises(ValueError):
            remedy(rt, "reset", requested_at=when, finding=finding)
    with pytest.raises(ValueError, match="guard"):
        remedy(rt, "reset", requested_at=1)
    work = remedy(rt, "reset", requested_at=1, finding=branches[0])
    work.guard["available_at"] = 0
    with pytest.raises(ValueError, match="identity"):
        project(rt, (work,), forecast(), Costs())


def test_conditional_work_respects_existing_stock_isolation_and_horizon():
    c, rt, branches = guarded()
    a = remedy(rt, "module-replacement", requested_at=1, finding=branches[1])
    rt.ledger.stock["stock:module"] = 0
    with pytest.raises(ValueError, match="stock:module"):
        project(rt, (a,), forecast(12), c.service_economics)
    rt.ledger.stock["stock:module"] = 1
    with pytest.raises(ValueError, match="inside this horizon"):
        project(rt, (a,), forecast(1), c.service_economics)
    b = remedy(rt, "reset", requested_at=1, finding=branches[0], request_id="another-procedure")
    with pytest.raises(ValueError):
        project(rt, (a, b), forecast(12), c.service_economics)


def test_scenario_commands_can_differ_only_after_the_recorded_information_boundary():
    p = Plant()
    f = forecast(3)
    branches = tuple(
        Branch.create(
            k,
            0.5,
            f,
            ("same", k, k),
            source="assumption:conditional-test",
            delivery_capacity_kw=[225, 450, 450],
        )
        for k in ("closed", "open")
    )
    bounds = dict(
        closed=dict(minimum=[0, 300, 0], maximum=[225, 450, 450]),
        open=dict(minimum=[0, 0, 0], maximum=[225, 225, 225]),
    )
    r = solve(
        p, State.initial(p), branches, 225, Costs(), seconds=2, branch_requested_bounds=bounds
    )
    assert r["status"] == "feasible", r["solver"]
    assert r["implementation_id"] == "service-outcome-tree-mpc/3"
    a, b = r["branches"]
    assert a["requested_actions"][0] == pytest.approx(b["requested_actions"][0])
    assert a["requested_actions"][1]["electrolyser_kw"] >= 300 - 1e-5
    assert b["requested_actions"][1]["electrolyser_kw"] <= 225 + 1e-5
    premature = copy.deepcopy(bounds)
    premature["closed"]["maximum"][0] = 450
    with pytest.raises(ValueError, match="before their observation"):
        solve(p, State.initial(p), branches, 225, Costs(), branch_requested_bounds=premature)
    with pytest.raises(ValueError, match="contradict shared commitments"):
        solve(
            p,
            State.initial(p),
            branches,
            225,
            Costs(),
            requested_maximum=[225] * 3,
            branch_requested_bounds=bounds,
        )


def test_separate_future_crew_departures_need_an_observed_return_even_with_enough_stock():
    c, rt, _ = guarded()
    rt.ledger.stock["stock:module"] = 2
    a = remedy(rt, "module-replacement", requested_at=1, request_id="first")
    b = remedy(rt, "module-replacement", requested_at=8, request_id="second")
    with pytest.raises(ValueError, match="One crew journey"):
        project(rt, (a, b), forecast(24), c.service_economics)


def test_conditional_projection_keeps_accepted_cleaning_and_requires_its_original_radiation():
    from test_cleaning_forecast import fixture as optical_fixture

    from methane.service_economics import ACTIVITY_VERSION, illustrative

    args, rt, f, key = optical_fixture()
    plan, _ = rt.propose(key)
    rt.executive.submit(plan)
    prices = illustrative(Costs(), version=ACTIVITY_VERSION)
    with pytest.raises(ValueError, match="original radiation"):
        project(rt, (), f, prices)
    r = project(rt, (), f, prices, reference_forecast=args["forecast"])
    assert r["forecast"]["pv_kw"][0] == pytest.approx(684)
    assert r["forecast"]["pv_kw"][1] == pytest.approx(703)
    assert r["forecast"]["pv_kw"][-1] == pytest.approx(760)
    assert len(r["treatment"]["predicted_treatments"]) > 0
    bad = copy.deepcopy(args["forecast"])
    bad["source"]["id"] = "different-issue"
    with pytest.raises(ValueError, match="same eligible forecast"):
        project(rt, (), f, prices, reference_forecast=bad)


@pytest.mark.parametrize("failed", [False, True])
def test_mobile_read_outcome_projection_matches_actual_energy_cost_and_stranding(failed):
    from test_investigation_planning import fixture as investigation_fixture

    from methane.faults import FaultState
    from methane.sensing import Diagnosis
    from methane.service_economics import report
    from methane.services.adapters import schedule

    c, rt = investigation_fixture(mission_failure=int(failed))
    key = next(q["id"] for q in rt.orders if q["kind"] == "inspection-confirm")
    plan, _ = rt.propose(key)
    stop = next(b for _, b, s in schedule(plan) if s.effect)
    work = GuardedWork(plan, None, 0, None, stop if failed else None)
    predicted = project(rt, (work,), forecast(4), c.service_economics)
    if failed:
        with pytest.raises(ValueError, match="predictions"):
            rt.executive.submit(work.demand_plan())
    initial = rt.ledger.stock["energy:rover"]
    faults = FaultState(c.plant, c.scenario, c.faults)
    diagnosis = Diagnosis(
        225, active_incident=True, incidents=1, informative=True, tracking_residual=0.5
    )
    rows = []
    for hour in range(4):
        if hour:
            rt.prepare(hour, diagnosis, 750)
        rt.dispatch_selected(((key, 0),) if hour == 0 else (), charge=False)
        rows.append({"field_operations": copy.deepcopy(rt.end(hour, faults, diagnosis))})
    # Route .5 h at 1 kW, contact read .5 h at .25 kW. Interrupted
    # execution stops before the .25 h verification and .5 h return.
    expected = sum(s.duration_hours * s.battery_kw for s in work.demand_plan().stages)
    assert initial - rt.ledger.stock["energy:rover"] == pytest.approx(expected)
    assert sum(
        sum(row["robot_use_kwh"].values()) for row in predicted["projection"]["rows"]
    ) == pytest.approx(expected)
    assert sum(r["field_operations"]["robot_use_kwh"] for r in rows) == pytest.approx(expected)
    priced = report(rows, c.service_economics, detailed=False)
    assert priced["views"]["decision"]["total_eur"] == pytest.approx(
        predicted["service_pricing"]["with_additions"]["decision"]["total_eur"]
    )
    assert rt.executive.missions[key].status == ("stranded" if failed else "completed")
    assert bool([s for r in rows for s in r["field_operations"]["inspection_samples"]]) != failed
