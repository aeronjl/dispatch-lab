"""Post-service load-test evidence, without repair truth or future information.

A tracking shortfall supports another bounded investigation, not a diagnosis of
its cause. Successful operation is still confirmed by the existing observer.
"""

import copy
from dataclasses import asdict
from math import isfinite

from methane.audit import PhysicalAuditError
from methane.components import assemble
from methane.physics import ACTION_KEYS, State, transition
from methane.services.contracts import available_boundary
from methane.services.coupling import identity

VERSION = "post-service-load-evidence/1"
TRACKER_VERSION = "bounded-post-service-followup/1"
RESET_TRACKER_VERSION = "bounded-post-service-followup/2"


def capture(row):
    """An explicit allowlist; never pass a whole simulator row to the verifier."""
    d = row["decision"]
    f = d["forecast"]
    return dict(
        hour=d["hour"],
        available_at=d["hour"] + 1,
        probe=d["probe"],
        capacity_estimate_kw=d["diagnosis"]["capacity_kw"],
        estimate=copy.deepcopy(d["estimate"]),
        request={k: row["requested"][k] for k in ACTION_KEYS},
        current=dict(
            pv_kw=f["pv_kw"][0],
            ambient_c=f["ambient_c"][0],
            delivery_kg=f["deliveries_kg"][0],
            service_kw=f.get("service_kw", [0])[0],
            isolated=f.get("electrolyser_isolated", [False])[0],
            **(
                {"water_delivery_l": f["water_deliveries_l"][0]}
                if "water_deliveries_l" in f
                else {}
            ),
        ),
        prior_inventory_kg=d["observations"]["h2_inventory_kg"],
        observations={
            k: row["observations_after"][k]
            for k in ("power_kw", "h2_inventory_kg", "h2_outflow_kg", "hydrogen_flow_kg")
        },
    )


def assess(plant, sensors, packet, *, components=None):
    """Reconcile an actual interval and check that its requested test was feasible.

    Resource feasibility uses the recorded estimate, current metered PV and
    registered production kernels at nameplate capacity. It does not use actual
    delivered actions, fault capacity, later weather or an intervention outcome.
    The current-hour mean-PV abstraction and sensor assumptions still apply.
    """
    p = copy.deepcopy(packet)
    if (
        type(p["hour"]) is not int
        or p["hour"] < 0
        or p["available_at"] != p["hour"] + 1
        or type(p["available_at"]) is not int
        or type(p["probe"]) is not bool
        or type(p["current"]["isolated"]) is not bool
        or plant.dt_hours != 1
    ):
        raise ValueError("Load evidence needs one complete hourly observation interval")
    values = (
        p["capacity_estimate_kw"],
        p["prior_inventory_kg"],
        *p["observations"].values(),
        *p["request"].values(),
        *(v for k, v in p["current"].items() if k != "isolated"),
    )
    if any(
        isinstance(v, bool) or not isinstance(v, (int, float)) or not isfinite(v) for v in values
    ):
        raise ValueError("Load evidence operands must be finite numbers")
    components = components or assemble(plant)
    threshold = max(sensors.discrepancy_fraction, 3 * sensors.noise_fraction)
    requested = p["request"]["electrolyser_kw"]
    measured = p["observations"]["power_kw"]
    expected = measured / plant.specific_energy_kwh_per_kg
    balance = (
        p["observations"]["h2_inventory_kg"]
        - p["prior_inventory_kg"]
        + p["observations"]["h2_outflow_kg"]
    )
    scale = max(expected, plant.min_kw / plant.specific_energy_kwh_per_kg)
    tracking = (requested - measured) / max(requested, 1)
    balance_error = balance - expected
    checked = dict(status="not checked", conditions=[])
    if not sensors.enabled or not p["probe"] or requested < plant.min_kw - 1e-5:
        outcome, reason = "insufficient evidence", "No enabled informative load-test request"
    elif requested <= p["capacity_estimate_kw"] + 1e-5:
        outcome, reason = (
            "insufficient evidence",
            "Request did not test above the previous estimate",
        )
    elif p["current"]["isolated"]:
        outcome, reason = "inconclusive", "The recorded service schedule isolated the electrolyser"
    else:
        try:
            transition(
                plant,
                State(**p["estimate"]),
                p["request"],
                p["current"]["pv_kw"],
                p["current"]["ambient_c"],
                p["current"]["delivery_kg"],
                capacity=plant.electrolyser_kw,
                service_kw=p["current"]["service_kw"],
                water_delivery_l=p["current"].get("water_delivery_l", 0),
                components=components,
            )
            checked["status"] = "feasible at recorded estimate"
        except PhysicalAuditError as exc:
            checked.update(
                status="infeasible at recorded estimate",
                conditions=[a for a in exc.audits if not a["passed"]],
            )
        except ValueError as exc:
            checked.update(status="infeasible at recorded estimate", conditions=[str(exc)])
        if checked["status"] != "feasible at recorded estimate":
            outcome, reason = "inconclusive", "Known resource or operating limits prevent this test"
        elif abs(balance_error) > threshold * scale or measured < 0 or balance < -threshold * scale:
            outcome, reason = "ambiguous", "Electrical and independent inventory channels disagree"
        elif tracking < -threshold:
            outcome, reason = (
                "ambiguous",
                "Measured power exceeds the request beyond the declared tolerance",
            )
        elif tracking > threshold:
            outcome, reason = (
                "tracking shortfall",
                "The resource-feasible test did not track; its physical cause is not established",
            )
        else:
            outcome, reason = (
                "tracking supported",
                "Tracking is supported only at this tested load; observer confirmation is separate",
            )
    result = dict(
        implementation_id=VERSION,
        inputs=dict(
            packet=p,
            plant=plant.to_dict(),
            sensors=asdict(sensors),
            component_models=components.identities(),
            component_parameters={
                name: asdict(getattr(components, name).parameters)
                for name in components.identities()
            },
        ),
        outcome=outcome,
        reason=reason,
        operands=dict(
            requested_kw=requested,
            measured_kw=measured,
            tracking_fraction=tracking,
            expected_hydrogen_kg=expected,
            balance_hydrogen_kg=balance,
            balance_error_kg=balance_error,
            balance_tolerance_kg=threshold * scale,
            discrepancy_threshold=threshold,
        ),
        resource_check=checked,
        scope="Measured tracking and independent inventory balance under the recorded hourly model. No hidden capacity or repair-success receipt. This evidence does not localise a cause or establish full recovery.",
    )
    result["evidence_id"] = identity(result)
    return result


def validate(result):
    if result.get("implementation_id") != VERSION or identity(
        {k: v for k, v in result.items() if k != "evidence_id"}
    ) != result.get("evidence_id"):
        raise ValueError("Post-service evidence integrity or version mismatch")


class Followup:
    """Bounded repeated-test evidence for completed, unverified substitutions.

    Inactivity adds no evidence. A successful, ambiguous or infeasible probe
    clears the qualifying shortfalls. Only same-load tests within the declared
    window combine; a later physical intervention starts a new attempt.
    """

    def __init__(self, required_tests, maximum_age_hours, *, include_resets=False):
        if type(required_tests) is not int or not 1 <= required_tests <= 8:
            raise ValueError("Require one to eight observed failed tests")
        if type(maximum_age_hours) is not int or not 1 <= maximum_age_hours <= 168:
            raise ValueError("Evidence window must be one to 168 hours")
        self.required_tests = required_tests
        if type(include_resets) is not bool:
            raise ValueError("Reset verification choice must be Boolean")
        self.include_resets = include_resets
        self.maximum_age_hours = maximum_age_hours
        self.attempts = {}
        self.seen = {}
        self.last_hour = -1

    def advance(self, hour, orders, evidence=None):
        if type(hour) is not int or hour < self.last_hour:
            raise ValueError("Verification cannot move backwards in time")
        if evidence is not None:
            validate(evidence)
            packet = evidence["inputs"]["packet"]
            if packet["available_at"] != hour:
                raise ValueError("Use only the test becoming available at this decision")
            old = self.seen.get(packet["hour"])
            if old is not None and old != evidence["evidence_id"]:
                raise ValueError("Conflicting evidence for an already observed interval")
        else:
            packet, old = None, None
        relevant = [o for o in orders if o["kind"] in ("reset", "module-replacement")]
        if any(
            o.get("completed_hour") is not None and available_boundary(o["completed_hour"]) > hour
            for o in relevant
        ):
            raise ValueError("A future completion cannot support a follow-up")
        self.last_hour = hour
        for order in relevant:
            if (order["kind"] != "module-replacement" and not self.include_resets) or order.get(
                "completed_hour"
            ) is None:
                continue
            completed = available_boundary(order["completed_hour"])
            entry = self.attempts.setdefault(
                order["id"],
                dict(
                    order_id=order["id"],
                    completed_at=completed,
                    tests=[],
                    qualifying=[],
                    status="awaiting verification",
                ),
            )
            successors = [
                o["id"]
                for o in relevant
                if o.get("retry_of") == order["id"] or o.get("followup_of") == order["id"]
            ]
            if successors:
                entry.update(status="superseded by separate attempt", successors=successors)
                continue
            if order["status"] == "verified":
                entry.update(status="observer confirmed", confirmed_at=order["verified_at_hour"])
                continue
            if order["status"] != "awaiting verification":
                continue
            # Do not attribute a later intervention's tests to this earlier work.
            later_work = any(
                o["id"] != order["id"]
                and o.get("incident") == order.get("incident")
                and o["created_hour"] >= order["created_hour"]
                and o["status"] != "queued"
                for o in relevant
            )
            eligible = (
                packet is not None
                and old is None
                and packet["hour"] >= completed
                and not later_work
            )
            entry["qualifying"] = [
                q for q in entry["qualifying"] if hour - q["available_at"] <= self.maximum_age_hours
            ]
            if eligible:
                test = dict(
                    evidence_id=evidence["evidence_id"],
                    hour=packet["hour"],
                    available_at=packet["available_at"],
                    requested_kw=packet["request"]["electrolyser_kw"],
                    outcome=evidence["outcome"],
                )
                entry["tests"].append(test)
                if test["outcome"] == "tracking shortfall":
                    entry["qualifying"] = [
                        q
                        for q in entry["qualifying"]
                        if abs(q["requested_kw"] - test["requested_kw"]) <= 1e-5
                    ]
                    entry["qualifying"].append(test)
                elif packet["probe"] and test["outcome"] != "insufficient evidence":
                    entry["qualifying"] = []
            entry["status"] = (
                "follow-up supported"
                if len(entry["qualifying"]) >= self.required_tests
                else "awaiting verification"
            )
            if entry["status"] == "follow-up supported":
                entry.setdefault("supported_at", hour)
            else:
                entry.pop("supported_at", None)
            entry["reason"] = (
                "Repeated resource-feasible load tests still fall short; another compatible attempt is permitted, not guaranteed useful"
                if entry["status"] == "follow-up supported"
                else "Completed work remains unverified; qualifying repeated tests are missing"
            )
        if packet is not None:
            self.seen[packet["hour"]] = evidence["evidence_id"]
        result = dict(
            implementation_id=RESET_TRACKER_VERSION if self.include_resets else TRACKER_VERSION,
            at_hour=hour,
            required_tests=self.required_tests,
            maximum_age_hours=self.maximum_age_hours,
            attempts=copy.deepcopy(list(self.attempts.values())),
            previous_test=copy.deepcopy(evidence),
        )
        result["assessment_id"] = identity(result)
        return result
