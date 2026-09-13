# Composable service contracts

This is the stage-1 implementation of the [field operations programme](field-operations-goal.md). It is an executable independent library in `methane/services/`. An opt-in [coupled-plant adapter](service-plant-integration.md) now executes the existing service hardware through these contracts. The running `field-operations/1` examples retain their previous mechanics.

## Interfaces

`Asset`, `Capability`, `Interface` and `WorkOrder` describe the executor, permitted task, target compatibility and requested outcome. `Registry` checks declared resource ports and assembles a `MissionPlan` through either a fixed or a mobile adapter. Models identify their implementation, parameter sources and assumptions. The registry exports these definitions together with the package source identities captured at import.

An immutable `Context` contains timestamped `Reading` records available when the decision is made. It rejects future readings. `Requirement` checks units, quality, age and a named condition; absent, uncertain or stale information does not count as a satisfied prerequisite. Builders have no fault-state argument.

`Access` finds eligible paths through declared directed edges with platform compatibility, observation prerequisites and optional shared access capacity. It models task-level travel time, not locomotion. The mobile adapter reserves outbound travel, work, verification and return. The fixed adapter requires installation at the target service point.

`Ledger` distinguishes stocks from simultaneous capacity. Materials and robot energy are reserved atomically; consumption is a separate event. Workspaces, assets, corridors, crew and power use half-open capacity windows. Overlapping demand is checked in aggregate. Release preserves past occupancy and frees only unused/future resources. Replenishment records offered, accepted and rejected quantities. No units are silently converted.

`Executive` integrates constant stage power over fractional-hour overlaps. Declared decimal durations accumulate with decimal arithmetic. Stage consumables are spent on entering work and remain spent after interruption. A return-energy margin is reserved but is not consumed as fictitious travel. A stranded asset retains its location/progress until another explicit task retrieves it.

Capabilities may also declare `hourly_consumables`: each quantity's amount is a rate per hour in its declared stock unit. The adapter reserves rate × duration and execution consumes rate × elapsed span. An optional effect-port `next_event` hook exposes only a physical integration boundary to the executive; `progress` returns partial-work receipts after a span. Invalid hook responses fail the mission and release unused reservations. The supervisor does not receive those private future event times. [Section cleaning](section-cleaning.md) exercises this interface with partial surface treatment and brush-area stock.

The `EffectPort` is the execution-only boundary that may access the physical world. Its receipt separates named observations and a public task report from retrospective physical effects. Observations cannot become available before the first hourly decision boundary at or after work completion. A malformed receipt invalidates the mission; previously consumed resources are retained and work cannot silently execute twice.

Repair and calibration capabilities must declare post-work acceptance conditions. Finishing motion leaves verification pending. Only fresh, available evidence after the work can satisfy those tests. Inspection evidence can be collected during the work interval and arrive later. A failed test does not restore the controller's estimate.

The executive produces eligible observations, requested plans, applied phase events and resource records. A coupled-plant adapter must separately apply physical effects at their recorded effective boundary, reserve isolation and reconcile service bus energy with plant dispatch. The opt-in `PlantServices` adapter performs that coupling. The standalone library example alone does not claim full-plant conservation or restored production.

## Runnable example

```
.venv/bin/python -m methane.services.example --directory build/services/contracts
```

The identical contact-reading request is executed once by a fixed reader and once by a rover. Illustrative assumptions: fixed work/verification takes 0.5 h at 0.4 kW; rover travel takes 1 h total at 0.6 kW, with the same 0.5 h work/verification at 0.4 kW. The fixed reader uses 0.2 kWh of bus electricity; the rover uses 0.8 kWh of its initial 2 kWh battery. Both obtain an observation eligible at H1. The rover returns at H1.5 and its completed mission is accepted at H2. This is a service execution check, not a hardware economics or plant-performance study.

The command writes human-readable results and JSON with metadata, source identities, starting information, phase snapshots and resource events. It requires only the Python standard library. Training, the browser and a solver are not involved.

## Verification

`tests/test_service_contracts.py` compares energy against independent decimal calculations, checks invariance under integration splitting, and compares capacity admission against an independently accumulated occupancy schedule. It exercises incompatible tools/routes/platforms, missing/stale/uncertain observations, fractional visibility boundaries, failed acceptance, interrupted travel/work, blocked return, consumed materials, finite replenishment, atomic admission, duplicate execution and malformed effect receipts.

These are numerical and contract checks. They do not constitute empirical calibration of hardware, proof of real-world safety or a general formal proof of the implementation.
