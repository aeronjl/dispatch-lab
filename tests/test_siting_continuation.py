"""Compare independent invocation boundaries against one continuous execution."""

import copy
from dataclasses import replace

import pytest

from methane.config import Config, Scenario
from methane.simulation import run
from methane.siting.checkpoint import FIELDS, Continuation, freeze, pack, unpack
from methane.siting.store import digest
from methane.weather import prepare


@pytest.fixture(autouse=True)
def site_worker_profile(monkeypatch):
    # production.launch uses this bounded solver profile. Comparing two fresh
    # multithreaded solves can differ before the checkpoint is even reached.
    # Keep exact physical assertions; isolate the continuation mechanism.
    monkeypatch.setenv("DISPATCH_BATCH_WORKER", "1")


def physical(rows):
    return [
        {
            k: r[k]
            for k in (
                "hour",
                "state",
                "applied",
                "diagnosis_after",
                "co2_delivered_kg",
                "forced_trip",
            )
        }
        for r in rows
    ]


@pytest.mark.parametrize("services", [False, True])
@pytest.mark.parametrize("start", ["2025-01-01", "2025-12-31"])
def test_checkpoint_matches_uninterrupted_runtime(services, start):
    c = Config(
        scenario=Scenario(
            hours=30,
            horizon_hours=6,
            solver_seconds=0.05,
            capacity_fraction=0.5,
            fault_start_hour=10,
        )
    )
    c = replace(c, weather=replace(c.weather, start=start))
    if services:
        from methane.services.configuration import ServiceSystem

        c = replace(
            c,
            field_operations=replace(c.field_operations, enabled=True),
            service_system=ServiceSystem(),
        )
    w = prepare(c)
    whole = run(c, w, ["Greedy"])
    binding = digest({"config": c.to_dict(), "weather": w})
    first = Continuation(30, 13, binding)
    a = run(c, w, ["Greedy"], continuation=first)
    assert first.output["next_hour"] == 13
    second = Continuation(30, 30, binding, checkpoint=copy.deepcopy(first.output))
    b = run(c, w, ["Greedy"], continuation=second)
    assert physical(a["records"]["Greedy"] + b["records"]["Greedy"]) == physical(
        whole["records"]["Greedy"]
    )
    assert b["continuous_period"]["initial_state"] == a["records"]["Greedy"][-1]["state"]
    assert b["records"]["Greedy"][0]["hour"] == 13
    assert b["status"] == "complete"


def test_checkpoint_preserves_aliases_and_rejects_wrong_binding():
    value = {"x": []}
    value["y"] = value["x"]
    restored = unpack(pack(value))
    assert restored["x"] is restored["y"]
    c = Continuation(
        2,
        2,
        "new",
        {
            "schema_version": "dispatch-lab/simulation-checkpoint/1",
            "binding": "old",
            "next_hour": 1,
        },
    )
    with pytest.raises(ValueError, match="binding"):
        c.restore()
    with pytest.raises(ValueError, match="Unsupported"):
        pack(lambda: 1)


def test_coordinated_service_cost_prefix_survives_checkpoint():
    from methane.services.verification_examples import fixture

    c = fixture("successful-procedure")
    c = replace(c, scenario=replace(c.scenario, hours=10, solver_seconds=0.1))
    w = prepare(c)
    binding = digest({"config": c.to_dict(), "weather": w})
    first = Continuation(10, 5, binding)
    a = run(c, w, ["MPC · methane"], continuation=first)
    second = Continuation(10, 10, binding, first.output)
    b = run(c, w, ["MPC · methane"], continuation=second)
    assert len(a["records"]["MPC · methane"]) == 5
    assert len(b["records"]["MPC · methane"]) == 5
    assert len(unpack(second.output["graph"])["service_cost_rows"]) == 10
    assert (
        b["records"]["MPC · methane"][0]["decision"]["service_control"]["inputs"][
            "service_cost_prefix"
        ]["hours"]
        == 5
    )


def test_weather_recovery_and_shared_runtime_continue_without_reset():
    from methane.recovery import RecoveryPolicy
    from methane.services.verification_examples import fixture

    c = fixture("successful-procedure")
    c = replace(
        c,
        scenario=replace(c.scenario, hours=14, solver_seconds=0.1),
        sensors=replace(c.sensors, ambiguity_policy="retain-capacity/1"),
        recovery_policy=replace(
            c.recovery_policy or RecoveryPolicy(), version="scheduled-load-tests/4"
        ),
    )
    w = prepare(c)
    first = Continuation(14, 7, "weather-loop-check")
    a = run(c, w, ["MPC · methane"], continuation=first)
    second = Continuation(14, 14, "weather-loop-check", checkpoint=first.output)
    b = run(c, w, ["MPC · methane"], continuation=second)
    assert a["status"] == b["status"] == "complete"
    assert b["records"]["MPC · methane"][0]["hour"] == 7
    assert (
        unpack(second.output["graph"])["joint_recovery_scheduler"].policy.version
        == "scheduled-load-tests/4"
    )


def test_transaction_image_survives_later_mutation_and_preserves_wire_format():
    from methane.services.contracts import Quantity

    ledger = {"stock": [Quantity("stock:module", 2, "module")]}
    ledger["self"] = ledger
    row = {"nested": ledger}
    scope = dict.fromkeys(FIELDS)
    scope.update(services=ledger, physical_optical=ledger, rows=[row])
    expected = pack({**{k: scope[k] for k in FIELDS}, "previous_row": row})
    cont = Continuation(3, 3, "transaction-test")
    cont.capture(1, scope)
    # A cancelled/failing next interval can mutate several aliased runtime paths.
    ledger["stock"].clear()
    ledger["failed_interval"] = True
    saved = cont.output
    assert saved["graph"] == expected
    restored = unpack(saved["graph"])
    assert restored["services"] is restored["physical_optical"]
    assert restored["services"]["self"] is restored["services"]
    assert restored["previous_row"]["nested"] is restored["services"]
    cont.capture(2, scope)
    assert cont.output["next_hour"] == 2
    assert saved["next_hour"] == 1 and saved["graph"] == expected
    with pytest.raises(ValueError, match="Unsupported checkpoint"):
        freeze(object())
    with pytest.raises(ValueError, match="Nonfinite checkpoint"):
        freeze({"value": float("nan")})


@pytest.mark.parametrize("failure", ["cancel", "physical"])
def test_resumption_after_mid_interval_failure_matches_whole_run(monkeypatch, failure):
    import methane.simulation as simulation
    from methane.audit import PhysicalAuditError
    from methane.cancellation import CancelledOperation
    from methane.lifecycle.fixtures import illustrative

    c = illustrative(Config(), commission=True, aged=True, policy="condition")
    c = replace(c, scenario=replace(c.scenario, hours=20, horizon_hours=6))
    weather = prepare(c)
    whole = run(c, weather, ["Greedy"])
    execute = simulation.execute
    calls = 0

    def interrupt(*args, **kwargs):
        nonlocal calls
        calls += 1
        if calls == 12:
            # Service preparation and lifecycle.begin already changed the runtime.
            if failure == "cancel":
                raise CancelledOperation()
            raise PhysicalAuditError([], {"test": "interrupted after preparation"})
        return execute(*args, **kwargs)

    first = Continuation(20, 20, "mid-interval-failure")
    monkeypatch.setattr(simulation, "execute", interrupt)
    a = run(c, weather, ["Greedy"], continuation=first)
    assert first.output["next_hour"] == 11
    monkeypatch.setattr(simulation, "execute", execute)
    second = Continuation(20, 20, "mid-interval-failure", checkpoint=first.output)
    b = run(c, weather, ["Greedy"], continuation=second)
    combined = a["records"]["Greedy"] + b["records"]["Greedy"]
    assert physical(combined) == physical(whole["records"]["Greedy"])
    for key in ("field_operations", "lifecycle"):
        assert [r.get(key) for r in combined] == [r.get(key) for r in whole["records"]["Greedy"]]
