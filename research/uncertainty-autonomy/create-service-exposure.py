"""Create matched, immutable service-exposure editions after the no-work finding.

Run from the project root with:
PYTHONPATH=. .venv/bin/python research/uncertainty-autonomy/create-service-exposure.py
Then use methane.autonomy_studies run/report on the printed programme directory.
The manifest captures every resolved input; this script is the authored design.
"""

import copy
import json
from dataclasses import replace
from uuid import uuid4

from methane.autonomy import DEFAULT
from methane.autonomy_studies import ARMS, ROOT, fixture
from methane.faults import FaultPolicy
from methane.recovery import JOINT_VERSION, RecoveryPolicy
from methane.services.controller import VERIFICATION_VERSION
from methane.studies import create
from methane.uncertainty import VERSION
from methane.uncertainty_studies import protocol

c = fixture()
c = replace(
    c,
    scenario=replace(
        c.scenario,
        hours=36,
        horizon_hours=12,
        fault_start_hour=2,
        capacity_fraction=0.25,
        solver_seconds=2,
    ),
    field_operations=replace(
        c.field_operations,
        cleaner_enabled=False,
        rover_battery_kwh=10,
        human_lead_hours=1,
        service_kits=3,
        repair_success_probability=0.8,
    ),
    service_system=replace(
        c.service_system,
        crew_response_lead_hours=0,
        crew_travel_hours=0.25,
        visit_bundling_enabled=True,
    ),
    service_policy=replace(
        c.service_policy, version=VERIFICATION_VERSION, maximum_wait_hours=12, comparison_seconds=6
    ),
    recovery_policy=RecoveryPolicy(version=JOINT_VERSION, maximum_wait_hours=12),
    faults=FaultPolicy(capacity_cause="equipment-damage"),
)
cases = ("service-repair", "service-outage")
value = dict(
    version="uncertain-services-qualification/1",
    basis=c.to_dict(),
    cases=list(cases),
    seeds=[7],
    repetitions=2,
    tolerance=1e-6,
    entries=[],
    scope="Declared 36-hour persistent-damage service-exposure fixture. Optional cleaning is disabled to isolate inspection, repair and verification. Timings are persistent world factors (1.5), not sampled population durations. Two computation repeats share one event seed. This is a workflow qualification, not a repair-value or annual reliability estimate.",
    rationale="The initial 12-hour economic programme could leave optional cleaning unexecuted. This follow-up introduces required observed fault work, retains ordinary costs, and lengthens the decision horizon to fit reserved service and return. No policy outcome or superiority is required.",
    authored_design="../create-service-exposure.py",
)
directory = ROOT / uuid4().hex
directory.mkdir(parents=True)
for repeat in (1, 2):
    for case in cases:
        for arm in ARMS:
            u = dict(
                schema_version=VERSION,
                seed=20260913,
                worlds=1,
                inner_seeds=[7],
                design="factorial",
                rationale=value["rationale"],
                autonomy={**copy.deepcopy(DEFAULT), "mode": arm},
                blocks=[
                    dict(
                        id="private-service-clock",
                        paths=[
                            "service_system." + group + "_time_factor"
                            for group in DEFAULT["duration_bounds"]
                        ],
                        kind="values",
                        rows=[[1.5] * 6],
                        visibility="hidden",
                        source="Declared bounded challenge; not field calibration",
                        rationale="Same persistent actual clocks and observation seeds across policy arms",
                    )
                ],
            )
            if case == "service-outage":
                u["support_events"] = [
                    dict(
                        channel="communications",
                        start=12,
                        end=18,
                        available=False,
                        source="Declared six-hour communications interruption",
                    )
                ]
            spec = protocol(c.to_dict(), u)
            spec.update(
                title="Service exposure · " + case + " · " + arm,
                question="Does the complete uncertain service workflow execute and remain auditable under persistent damage and a support interruption?",
                comparison=value["scope"],
                policies={"MPC · economics": {"objective": "economics"}},
                baseline_controller="MPC · economics",
                candidate_controller="MPC · economics",
            )
            edition = create(basis=c.to_dict(), specification=spec)
            value["entries"].append(
                dict(
                    condition=case, arm=arm, seed=7, repeat=repeat, edition_id=edition["edition_id"]
                )
            )
            (directory / "programme.json").write_text(json.dumps(value, indent=2) + "\n")
print(directory)
