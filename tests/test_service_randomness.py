"""Matched service events: independent fractions, accepted requests and private outcomes."""

import copy
import hashlib
import math
from dataclasses import replace
from types import SimpleNamespace

import pytest

from methane.config import Config
from methane.reference import audit, service_variate
from methane.services.configuration import ServiceSystem
from methane.services.hardware_demo import fixture as hardware_fixture
from methane.services.plant import IntervalEffects, PlantServices
from methane.services.randomness import LEGACY, VERSION, Event, Events, uniform
from methane.services.visits_demo import execute
from methane.services.visits_demo import fixture as visit_fixture


def plan(order_id="A", target="PLANT-01/ELY-01", action="module-replacement", **details):
    return SimpleNamespace(
        order=SimpleNamespace(order_id=order_id, action=action, reason=details.get("reason", "a")),
        interface=SimpleNamespace(target_asset_id=target),
        **{key: value for key, value in details.items() if key != "reason"},
    )


@pytest.mark.parametrize("ordinal,numerator", [(1, 8984797099206352), (2, 1514810012951362)])
def test_documented_sha256_vectors_and_independent_reconstruction(ordinal, numerator):
    # Independently tabulated first 53 bits of SHA-256 over the documented JSON array.
    event = Event("PLANT-01/ELY-01", "module-replacement", ordinal)
    expected = numerator / 9007199254740992
    assert uniform(7, event, "repair") == expected
    assert service_variate(7, event.to_dict(), "repair") == expected
    assert 0 <= expected < 1


@pytest.mark.parametrize("seed", [-1, True, 1.5, "7"])
def test_invalid_seeds_rejected(seed):
    with pytest.raises(ValueError, match="seed"):
        Events(seed)
    with pytest.raises(ValueError, match="seed"):
        uniform(seed, Event("asset", "repair", 1), "repair")


@pytest.mark.parametrize("number", [0, -1, True, 1.5])
def test_request_numbers_are_positive_integers(number):
    with pytest.raises(ValueError, match="request"):
        Event("asset", "repair", number)


def test_draws_ignore_editorial_text_actor_schedule_and_unrelated_work():
    a, b = Events(7), Events(7)
    p = plan(reason="Replace after inconsistent tracking", starting_at=2, actor="human")
    q = plan("different-order-id", reason="A rewritten explanation", starting_at=90, actor="robot")
    a.register("A", p.interface.target_asset_id, p.order.action)
    b.register("unrelated", "another-target", "module-replacement")
    b.register("another-action", p.interface.target_asset_id, "inspection")
    b.register(q.order.order_id, q.interface.target_asset_id, q.order.action)
    # Another channel can be evaluated first without moving the repair stream.
    b.draw(q, "mission-failure", 90)
    assert a.draw(p, "repair", 2) == b.draw(q, "repair", 90)
    assert a.identity("A") == b.identity(q.order.order_id)
    assert b.draw(q, "mission-failure", 91) != b.draw(q, "repair", 91)
    assert b.count == 2
    returned = b.retrospective()
    returned[0]["event"]["request"] = 99
    assert b.retrospective()[0]["event"]["request"] == 1


def test_acceptance_is_idempotent_but_cancelled_requests_keep_their_ordinal():
    bank = Events(7)
    event = bank.register("cancelled", "asset", "repair")
    assert bank.register("cancelled", "asset", "repair") is event
    # A cancelled accepted request need never draw. A replacement is still request 2.
    assert bank.count == 0
    assert bank.register("replacement", "asset", "repair").request == 2
    assert bank.register("other", "other-asset", "repair").request == 1
    with pytest.raises(ValueError, match="cannot change"):
        bank.register("cancelled", "asset", "inspection")
    assert bank.identity("not-accepted") is None
    with pytest.raises(ValueError, match="before drawing"):
        bank.draw(plan(), "repair", 0)
    with pytest.raises(ValueError, match="does not match"):
        bank.draw(plan("cancelled", target="wrong"), "repair", 0)
    with pytest.raises(ValueError):
        bank.draw(plan("cancelled", target="asset", action="repair"), "repair", -1)


def test_legacy_default_and_exact_original_mapping_remain_available():
    config = Config(service_system=ServiceSystem()).to_dict()
    config["service_system"].pop("outcome_randomness")
    restored = Config.from_dict(config)
    assert restored.service_system.outcome_randomness == LEGACY
    p = plan(reason="old text / incident 3 / occurrence 2")
    effect = IntervalEffects(restored.field_operations, restored.service_system, 7)
    key = "7/module-replacement/old text / incident 3 / occurrence 2/repair"
    expected = int.from_bytes(hashlib.sha256(key.encode()).digest()[:8], "big") / 2**64
    assert effect.random_events is None and effect.draw(p, "repair") == expected
    with pytest.raises(ValueError, match="random"):
        ServiceSystem(outcome_randomness="unreviewed")


def test_candidate_builds_and_blocked_dispatch_do_not_allocate_event_numbers():
    from test_service_plant import diagnosed, fault, fixture

    c, o = fixture("fixed", outcome_randomness=VERSION, communications_available=False)
    rt = PlantServices(c, o, 7, 450)
    f, d = fault("resettable-trip"), diagnosed()
    rt.begin(0, d, 650)
    rt.end(0, f, d)
    rt.begin(1, d, 650)
    queued = next(q for q in rt.orders if q["kind"] == "reset")
    assert queued["status"] == "queued" and "communications" in queued["blocked"]
    assert rt._effects.random_events.identity(queued["id"]) is None
    rt.end(1, f, d)
    rt.begin(2, d, 650)
    # The read and its fractional verification phase have both completed.
    inspected = next(q for q in rt.orders if q["kind"] == "inspection")
    for _ in range(3):
        rt._build(inspected)
    assert rt._effects.random_events.identity(inspected["id"])["request"] == 1
    assert len(rt._effects.random_events._events) == 1
    candidate = rt._build(inspected)
    with pytest.raises(ValueError, match="private execution"):
        rt._effects.draw(candidate, "repair")


def matched(config):
    return replace(
        config, service_system=replace(config.service_system, outcome_randomness=VERSION)
    )


@pytest.fixture(scope="module")
def cases():
    retrieval = hardware_fixture("control-hold")
    retrieval = replace(
        retrieval,
        field_operations=replace(retrieval.field_operations, mission_failure_probability=1),
        service_system=replace(retrieval.service_system, equipment_recovery_enabled=False),
    )
    probabilistic = visit_fixture("interventions")
    probabilistic = replace(
        probabilistic,
        field_operations=replace(probabilistic.field_operations, repair_success_probability=0.5),
    )
    return {
        "crew": execute(matched(visit_fixture("interventions"))),
        "replacement": execute(matched(hardware_fixture("drive-power-loss"))),
        "failed": execute(matched(hardware_fixture("failed-replacement"))),
        "portable": execute(matched(hardware_fixture("portable-abort"))),
        "retrieval": execute(matched(retrieval)),
        "probabilistic": execute(matched(probabilistic)),
    }


@pytest.mark.parametrize(
    "name", ["crew", "replacement", "failed", "portable", "retrieval", "probabilistic"]
)
def test_full_workflows_use_private_matched_draws_and_independent_checks(name, cases):
    result = cases[name]
    assert result["status"] == "complete", result["failures"]
    report = audit(result)
    assert report["passed"], (
        report["failures"] or [q for q in report["checks"] if not q["passed"]][:8]
    )
    draws = []
    for row, truth in zip(
        result["records"]["Greedy"],
        result["retrospective_truth_by_controller"]["Greedy"],
        strict=True,
    ):
        service = row["field_operations"]
        assert service["version"] == "plant-service-contracts/11"
        assert "random_draws" not in service
        assert "uniform" not in str(service["decision"])
        assert "uniform" not in str(row["observations_after"])
        draws.extend(truth["service_randomness"])
    assert draws
    channels = {d["channel"] for d in draws}
    assert ({"repair"} if name in ("crew", "probabilistic") else {"mission-failure"}) <= channels
    if name in ("replacement", "failed"):
        assert "hardware-procedure" in channels
    if name == "retrieval":
        assert "drive-test" in channels


@pytest.mark.parametrize("corruption", ["variate", "ordinal", "missing", "repeated", "threshold"])
def test_reference_rejects_tampered_randomness_or_realised_procedure(corruption, cases):
    result = copy.deepcopy(cases["crew"])
    rows = result["retrospective_truth_by_controller"]["Greedy"]
    row = next(q for q in rows if any(d["channel"] == "repair" for d in q["service_randomness"]))
    draws = row["service_randomness"]
    draw = next(d for d in draws if d["channel"] == "repair")
    if corruption == "variate":
        draw["uniform"] = math.nextafter(draw["uniform"], 1)
    elif corruption == "ordinal":
        draw["event"]["request"] += 1
    elif corruption == "missing":
        draws.remove(draw)
    elif corruption == "repeated":
        draws.append(copy.deepcopy(draw))
    else:
        effect = next(e for e in row["service_effects"] if "procedure_passed" in e)
        effect["procedure_passed"] = not effect["procedure_passed"]
    report = audit(result)
    assert not report["passed"]
    assert any(
        not q["passed"] and q["check"].startswith("service_random.") for q in report["checks"]
    )


def test_hidden_future_faults_cannot_change_earlier_service_choices_or_event_identities():
    from test_service_plant import diagnosed, fault, fixture

    c, o = fixture("fixed", outcome_randomness=VERSION)
    a, b = [PlantServices(c, o, 7, 450) for _ in range(2)]
    d = diagnosed()
    a.begin(0, d, 650)
    b.begin(0, d, 650)
    assert a.interval["decision"] == b.interval["decision"]
    original = fault()
    changed = fault()
    changed.scenario = replace(changed.scenario, fault_start_hour=100, capacity_fraction=0.1)
    a.end(0, original, d)
    b.end(0, changed, d)
    assert a.public() == b.public()
