"""Independent interface arithmetic, shared dispatch limits and saved design workflow."""

from copy import deepcopy
from dataclasses import replace

import pytest

from methane.audit import PhysicalAuditError, physical
from methane.config import Config, Costs, Plant, Scenario
from methane.costing import allocation, decision_cost, reprice
from methane.dispatch import execute, plan
from methane.engineering import audit_archive
from methane.integration import Integration, forecast
from methane.physics import ACTION_KEYS, State, transition
from methane.reference import economics as independent_costs
from methane.reference import interval as independent_interval
from methane.simulation import run


def plant(**changes):
    return Plant(min_load_fraction=0.01, start_energy_kwh=0, integration=changes)


def action(**changes):
    return {**dict.fromkeys(ACTION_KEYS, 0.0), **changes}


def horizon(p, hours=6):
    return forecast(
        p, dict(pv_kw=[700] * hours, ambient_c=[20] * hours, deliveries_kg=[0] * hours), 0
    )


def test_independent_electricity_heat_water_and_compression_accounting():
    p = plant(
        ac_efficiency=0.8,
        dryer_kw=8,
        heat_fraction=0.2,
        cooler_electric_fraction=0.1,
        h2_buffer_barg=40,
        compressor_kwh_per_kg=2,
        compressor_kgph=10,
    )
    before = State.initial(p)
    a = action(electrolyser_kw=110, heater_kw=20)
    after, row = transition(p, before, a, 400, 20, 0, service_kw=10, water_delivery_l=300)
    r = row["integration"]
    assert row["h2_produced_kg"] == 2
    assert r["ac_kw"] == pytest.approx(110 + 20 + 8 + 2.2 + 4)
    assert row["demand_kw"] == pytest.approx(144.2 / 0.8 + 10)
    assert r["conversion_loss_kwh"] == pytest.approx(36.05)
    assert (r["water_accepted_l"], r["water_rejected_l"], after.water_l) == (250, 50, 482)
    independent = independent_interval(vars(p), vars(before), a, 400, 20, 0, 10, 300)
    assert vars(after) == pytest.approx(independent["state"])
    assert row["curtailed_kwh"] == pytest.approx(independent["curtailed_kwh"])
    assert row["electrical_residual_kwh"] == pytest.approx(0, abs=1e-10)
    corrupt = deepcopy(row)
    corrupt["integration"]["water_consumed_l"] += 1
    assert not all(a["passed"] for a in physical(p, before, corrupt))
    corrupt = deepcopy(row)
    corrupt["integration"]["parameters"]["ac_efficiency"] = 1
    assert not all(a["passed"] for a in physical(p, before, corrupt))


@pytest.mark.parametrize("objective", ["greedy", "methane", "economics"])
def test_planning_execution_respect_water_and_cooler_limits(objective):
    p = plant(
        initial_water_l=20,
        water_delivery_l=0,
        cooler_capacity_kw=10,
        heat_fraction=0.5,
        ac_capacity_kw=80,
        dryer_kw=0,
    )
    state = State.initial(p)
    result = plan(p, state, horizon(p), p.electrolyser_kw, Costs(), objective, seconds=1)
    assert result["actions"]
    assert sum(r["integration"]["water_consumed_l"] for r in result["trajectory"]) <= 20 + 1e-5
    for a, r in zip(result["actions"], result["trajectory"], strict=True):
        assert a["electrolyser_kw"] <= 20 + 1e-5
        assert r["integration"]["ac_kw"] <= 80 + 1e-5
        assert r["state"]["water_l"] >= -1e-5
    _, actual = execute(
        p, state, action(electrolyser_kw=400, heater_kw=60), 700, 20, 0, p.electrolyser_kw, Costs()
    )
    assert actual["applied"]["electrolyser_kw"] <= 20 + 1e-5
    assert actual["requested"]["electrolyser_kw"] == 400
    assert actual["integration"]["ac_kw"] <= 80 + 1e-5


def test_supply_exhaustion_arrivals_and_delivery_before_withdrawal():
    p = plant(initial_water_l=0, water_delivery_l=100, water_every_hours=2, water_delay_hours=1)
    f = horizon(p)
    assert f["water_deliveries_l"] == [0, 0, 0, 100, 0, 100]
    result = plan(p, State.initial(p), f, p.electrolyser_kw, Costs(), "greedy")
    assert all(r["h2_produced_kg"] == 0 for r in result["trajectory"][:3])
    assert result["trajectory"][3]["h2_produced_kg"] > 0
    p = plant(initial_water_l=500, water_delivery_l=100)
    before = State.initial(p)
    after, r = transition(p, before, action(electrolyser_kw=55), 200, 20, 0, water_delivery_l=100)
    assert r["integration"]["water_rejected_l"] == 100
    assert after.water_l == 491
    with pytest.raises(PhysicalAuditError):
        transition(p, replace(before, water_l=0), action(electrolyser_kw=55), 200, 20, 0)


def test_pressure_block_trips_minimum_run_and_invalid_compression_is_rejected():
    p = plant(co2_supply_barg=1)
    before = replace(
        State.initial(p), h2_kg=20, temperature_c=300, reactor_on=True, commitment_hours=3
    )
    _, row = execute(p, before, action(methane_kg=5), 700, 20, 0, p.electrolyser_kw, Costs())
    assert row["applied"]["methane_kg"] == 0 and row["forced_trip"]
    assert not row["integration"]["feed_pressure_compatible"]
    for changes in (
        {"h2_buffer_barg": 40},
        {"initial_water_l": 501},
        {"ac_efficiency": 0},
        {"dryer_kw": float("nan")},
        {"unknown": 1},
    ):
        with pytest.raises(ValueError):
            Integration(**changes)


def test_pricing_uses_water_once_and_preserves_unpriced_costs():
    p = plant()
    _, row = transition(p, State.initial(p), action(electrolyser_kw=110), 700, 20, 0)
    c = Costs(water_litres_per_kg=99, water_eur_per_m3=100)
    report = allocation(p, c, [row], with_lineage=True)
    assert report["water_input_m3"] == 0.018
    assert report["components"]["integration"] is None and report["total_eur"] is None
    assert report["known_subtotal_eur"] > 0
    from methane.siting.cashflow import defaults as cash_defaults

    with pytest.raises(ValueError, match="Price additional plant interfaces"):
        cash_defaults(Config(plant=p).to_dict())
    p = replace(p, integration={**p.integration, "installed_eur": 15000, "fixed_eur_per_year": 200})
    cash = cash_defaults(Config(plant=p).to_dict())
    extra = [i for i in cash["items"] if "interface" in i["name"]]
    assert {i["category"]: i["eur"] for i in extra} == {"initial": 15000, "annual": 200}
    priced = allocation(p, c, [row], with_lineage=True)
    reference = independent_costs(vars(p), vars(c), [row])
    assert priced["total_eur"] == pytest.approx(reference["total_eur"])
    assert priced["variable_and_wear_eur"] == pytest.approx(reference["variable_and_wear_eur"])
    assert priced["components"]["integration"] == pytest.approx(1200 / 8760)
    assert decision_cost(p, c, [row])["variable_and_wear_eur"] == pytest.approx(
        report["variable_and_wear_eur"]
    )


def test_run_forecasts_observations_archive_and_repricing():
    c = Config(
        plant=plant(initial_water_l=10, water_delivery_l=30, water_every_hours=4),
        scenario=Scenario(hours=12, horizon_hours=6, solver_seconds=0.1),
    )
    r = run(c, strategies=("Greedy",))
    assert r["status"] == "complete", r.get("errors")
    rows = r["records"]["Greedy"]
    for i, row in enumerate(rows):
        assert row["decision"]["estimate"]["water_l"] == pytest.approx(
            10 if i == 0 else rows[i - 1]["state"]["water_l"]
        )
        assert row["decision"]["forecast"]["water_deliveries_l"][0] == (30 if i in (4, 8) else 0)
        assert row["observations_after"]["water_l"] == row["state"]["water_l"]
    assert audit_archive(r)["passed"]
    before = deepcopy(r)
    reprice(r, replace(c.costs, water_eur_per_m3=10))
    assert r == before
    from methane.reference import audit

    checked = audit(r)
    assert checked["passed"], checked["failures"][:3]


def test_configuration_roundtrip_and_legacy_neutral_boundary():
    old = Config().to_dict()
    assert "integration" not in old["plant"]
    assert Config.from_dict(old).to_dict() == old
    c = Config(plant=plant())
    assert Config.from_dict(c.to_dict()) == c
    assert State.initial(Plant()).water_l == 0


def test_checkpoint_preserves_water_inventory_and_absolute_delivery_clock():
    from methane.siting.checkpoint import Continuation
    from methane.siting.store import digest
    from methane.weather import prepare

    c = Config(
        plant=plant(initial_water_l=10, water_delivery_l=30, water_every_hours=4),
        scenario=Scenario(hours=12, horizon_hours=6, solver_seconds=0.1),
    )
    w = prepare(c)
    binding = digest({"config": c.to_dict(), "weather": w})
    whole = run(c, w, ["Greedy"])
    first = Continuation(12, 5, binding)
    a = run(c, w, ["Greedy"], continuation=first)
    b = run(
        c,
        w,
        ["Greedy"],
        continuation=Continuation(12, 12, binding, checkpoint=deepcopy(first.output)),
    )
    combined = a["records"]["Greedy"] + b["records"]["Greedy"]
    for x, y in zip(combined, whole["records"]["Greedy"], strict=True):
        assert x["state"] == pytest.approx(y["state"])
        assert x["integration"] == y["integration"]
    assert combined[8]["integration"]["water_delivery_l"] == 30


def test_design_trace_offline_bundle_and_missing_original_context(tmp_path):
    from methane.siting import equipment, production, projects, reporting
    from methane.siting.catalogue import bootstrap
    from methane.siting.store import Store

    store = Store(tmp_path / "store")
    site = next(s for s in bootstrap(store) if s["country"] == "ES")
    p = projects.create(store, site["id"])
    original = deepcopy(p["project"])
    updated = equipment.save_integration(store, original["id"], Integration().model_dump())
    assert store.get("project", original["id"]) == {k: v for k, v in original.items() if k != "id"}
    assert equipment.context(store, project_id=updated["project"]["id"])["integration"]["enabled"]
    s = projects.run_project(
        store, updated["project"]["id"], synthetic=True, hours=4, controller="Greedy"
    )
    sid = s["study_id"]
    c = store.get("study", sid)["cases"][0]
    assert "not been recorded" in equipment.integration_trace(store, sid, c["case_id"], 0)["status"]
    production.execute(store, sid)
    t = equipment.integration_trace(store, sid, c["case_id"], 0)
    assert t["status"] == "Recorded execution" and t["record"]["version"] == "plant-integration/1"
    assert t["record"]["ending_water_l"] == 250
    detached = equipment.save_integration(store, updated["project"]["id"], None)
    assert not equipment.context(store, project_id=detached["project"]["id"])["integration"][
        "enabled"
    ]
    assert equipment.context(store, study_id=sid, case_id=c["case_id"])["integration"]["enabled"]
    pub = reporting.publish(store, "study", sid)
    bundle = reporting.bundle(store, pub["publication_id"])["path"]
    restored = Store(tmp_path / "restored")
    reporting.restore(bundle, restored)
    assert equipment.integration_trace(restored, sid, c["case_id"], 0) == t


def test_disclosed_uncertainty_inventory_and_hidden_rejection():
    from methane.uncertainty import catalogue, validate_world

    c = Config(plant=plant()).to_dict()
    view = catalogue(c)
    assert not view["unregistered"]
    entries = [r for r in view["parameters"] if r["path"].startswith("plant.integration.")]
    assert len(entries) == len(Integration.model_fields)
    assert all(r["active"] and not r["hidden_supported"] for r in entries)
    changed = deepcopy(c)
    changed["plant"]["integration"]["heat_fraction"] = 0.4
    with pytest.raises(ValueError, match="Hidden execution adapter"):
        validate_world(dict(config=changed, controller_config=c, draws=[]))


def test_solver_failure_falls_back_with_water_receipt_and_no_invented_power(monkeypatch):
    from methane.dispatch import Model

    monkeypatch.setattr(
        Model,
        "solve",
        lambda self, seconds: (None, {"status": "time-limit", "seconds": seconds, "gap": None}),
    )
    p = plant(initial_water_l=0)
    state, row = execute(
        p,
        State.initial(p),
        action(electrolyser_kw=300),
        300,
        20,
        0,
        p.electrolyser_kw,
        Costs(),
        water_delivery_l=100,
    )
    assert row["execution_solver"]["status"] == "time-limit"
    assert row["execution_solver"]["fallback_action"] == "safe-off"
    assert row["execution_solver"]["fallback_used"]
    assert state.water_l == 100
    assert row["h2_produced_kg"] == 0 and row["demand_kw"] == 0
    assert all(a["passed"] for a in row["audits"])


def test_interface_constraints_survive_lifecycle_and_coordinated_service_planning():
    from methane.lifecycle.fixtures import illustrative
    from methane.services.verification_examples import fixture

    c = fixture("successful-procedure")
    c = replace(
        c,
        plant=replace(
            c.plant, integration=Integration(initial_water_l=10, water_every_hours=2).model_dump()
        ),
        scenario=replace(c.scenario, hours=6, solver_seconds=0.1),
    )
    for config in (
        c,
        illustrative(Config(scenario=Scenario(hours=6, horizon_hours=6, solver_seconds=0.1))),
    ):
        config = replace(
            config,
            plant=replace(config.plant, integration=Integration(water_every_hours=2).model_dump()),
        )
        r = run(config, strategies=("MPC · methane",))
        assert r["status"] == "complete", r.get("errors")
        for row in r["records"]["MPC · methane"]:
            assert all(a["passed"] for a in row["audits"])
            assert row["decision"]["forecast"]["water_deliveries_l"][0] == (
                300 if row["hour"] in (2, 4) else 0
            )
