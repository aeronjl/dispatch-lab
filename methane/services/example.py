"""Executable service-contract example; no plant dispatch or vendor calibration claims.

Run: python -m methane.services.example --directory build/services/contracts
The same contact-reading work order is fulfilled by a fixed reader and a rover.
"""

import argparse
import json
from pathlib import Path

from methane.services import SOURCE_IDENTITY
from methane.services.access import Access, Edge
from methane.services.contracts import (
    Asset,
    Capability,
    Context,
    Interface,
    Reading,
    Requirement,
    Source,
    WorkOrder,
    available_boundary,
)
from methane.services.executive import Executive, Receipt
from methane.services.registry import Registry
from methane.services.resources import Ledger, Resource


def reference_system():
    assumption = Source(
        "service-contract-fixture/1",
        "assumption",
        "docs/service-contracts.md",
        "Illustrative geometry and energy rates for independent execution checks; not hardware performance",
    )
    capability = Capability(
        "read-trip",
        "read-trip-contact",
        "observe",
        "ideal-contact-reader/1",
        work_hours=0.25,
        verify_hours=0.25,
        work_kw=0.4,
        acceptance=(Requirement("trip-contact", "available", True, "boolean", 3),),
        sources=(assumption,),
    )
    interface = Interface(
        "ELY/contact", "ELY", "electrolyser", (capability.action,), ("contact-reader",)
    )
    assets = (
        Asset(
            "FIXED",
            "fixed-sensor",
            "reference-fixed-reader/1",
            "electrolyser",
            "fixed",
            (capability.capability_id,),
            ("contact-reader",),
            sources=(assumption,),
        ),
        Asset(
            "ROVER",
            "ground-inspector",
            "reference-rover/1",
            "dock",
            "wheeled",
            (capability.capability_id,),
            ("contact-reader",),
            "ROVER/energy",
            0.2,
            0.6,
            sources=(assumption,),
        ),
    )
    resources = (
        Resource("ROVER/energy", "kWh", "stock", 2, 2),
        Resource("asset:ROVER", "slot", "capacity", 1),
        Resource("asset:FIXED", "slot", "capacity", 1),
        Resource("plant:service-power", "kW", "capacity", 1),
    )
    access = Access(
        (
            Edge("to-electrolyser", "dock", "electrolyser", 0.5, ("wheeled",)),
            Edge("to-dock", "electrolyser", "dock", 0.5, ("wheeled",)),
        )
    )
    return Registry(assets, (interface,), (capability,), resources, access)


class ContactFixture:
    def perform(self, plan, completed_at):
        return Receipt(
            "Read declared trip contact; no repair performed",
            (
                Reading(
                    "trip-contact",
                    True,
                    "boolean",
                    completed_at,
                    available_boundary(completed_at),
                    "fixture-contact/1",
                ),
            ),
        )


def run_example():
    system = reference_system()
    order = WorkOrder(
        "INSPECT-1", "read-trip-contact", "ELY/contact", 0, "Investigate an observed anomaly"
    )
    cases = []
    for asset in system.assets:
        executor = Executive(Ledger(system.resources.values()), ContactFixture())
        plan = system.build(order, asset, "read-trip", Context(0, ()))
        executor.submit(plan)
        intervals = []
        for end in (0.25, 0.5, 0.75, 1, 1.5, 2):
            executor.advance(end, Context(executor.at_hour, ()))
            executor.reconcile_verification(Context(end, ()))
            intervals.append(executor.public())
        cases.append(
            dict(
                asset=asset,
                requested=plan.to_dict(),
                intervals=intervals,
                applied=executor.public(),
                resource_events=executor.ledger.events,
            )
        )
    return dict(
        schema_version="service-contract-example/1",
        scope="Independent service executive example, not a coupled plant study or empirical hardware validation",
        source=dict(SOURCE_IDENTITY),
        definitions=system.manifest(),
        cases=cases,
    )


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", type=Path, default=Path("build/services/contracts"))
    args = parser.parse_args()
    result = run_example()
    args.directory.mkdir(parents=True, exist_ok=True)
    (args.directory / "example.json").write_text(json.dumps(result, indent=2, allow_nan=False))
    lines = [
        "# Same service request, two execution models",
        "",
        result["scope"],
        "",
        "| Executor | Mission ends h | Observation available h | Robot energy kWh | Bus energy kWh | Verified h |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for case in result["cases"]:
        row = case["applied"]["orders"][0]
        observation = case["applied"]["observations"][0]
        lines.append(
            f"| {case['asset']} | {row['completed_at']} | {observation['available_at']} | {row['battery_kwh']:.2f} | {row['bus_kwh']:.2f} | {row['verified_at']} |"
        )
    lines += [
        "",
        "Independent expectations: fixed reader draws 0.4 kW × 0.5 h = 0.2 kWh from the bus. Rover uses 0.6 kW × 1 h travel + 0.4 kW × 0.5 h work/verification = 0.8 kWh from its battery; 1.2 kWh remains. Inspection creates evidence and never repairs the plant.",
        "",
        "Exact descriptors, original decision contexts, phase events, source identities and resource records: [example.json](example.json).",
    ]
    (args.directory / "example.md").write_text("\n".join(lines) + "\n")
    print(args.directory / "example.md")


if __name__ == "__main__":
    main()
