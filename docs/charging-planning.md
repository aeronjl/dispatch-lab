# Robot charging and production planning

Status: callable experimental stage-4 machinery. The default simulation continues to use its recorded local service rule. This port does not yet select inspections, contingent remedies or human visits, and is not the complete autonomous service supervisor.

## What is decided

`service-charge-process-mpc/1` solves the existing plant dispatch equations together with one shared dock and explicit robot energy balances. It chooses a robot and charging power for each hourly slot. Inputs include current inventories, accepted mission consumption, return reserves, conditional connected periods, dock availability and a fixed energy target with an absolute deadline. It supports methane and economic objectives, retaining the existing process costs and operating constraints.

`service-charge-controller-port/1` constructs those inputs from the open service decision and the original eligible forecast. It projects accepted work without a redundant process solve. The numerical result retains plant parameters, estimated state, forecast issue and times, original costs, robot profiles, solver termination and the replayed physical trajectory. Conditional successful mission continuation may free a later charging slot; it is not evidence that the robot has actually returned.

The port evaluates charging for declared targets. It does not invent a future inspection's value or treat an unaccepted task as a commitment. The caller must say why energy is required and preserve its deadline across replans. An overdue target or one beyond the current horizon is reported as an invalid comparison boundary; it is not silently postponed. A missing applicable price or a solve without a validated incumbent remains unresolved.

## Independent balances and timing

For an hourly interval:

`ending robot energy = beginning energy − mission consumption + efficiency × dock electricity`

`beginning robot energy ≥ mission consumption + held return reserve`

Mission consumption is conservatively funded at the beginning of its intersecting hour. Charging is credited at the end. The held reserve is inventory, not another energy consumption. A 10 kWh dock input at 80% efficiency therefore supplies 8 kWh; a subsequent 6 kWh journey leaves 2 kWh of reserve and has lost 2 kWh in charging.

Each robot's energy stays within its declared capacity. A robot committed elsewhere cannot occupy the dock, and one shared charger cannot serve two robots in a single slot. A stronger charger does not remove that occupancy limit. An accepted later departure still allows charging before departure when the current resources and whole-mission bookings permit it. Unearned charging receipts do not fund acceptance of a new mission.

Charging draws from the shared electrical bus and competes with electrolysis, heating, cooling and plant battery charging. The existing active-service rule is preserved: the dock requires available solar power. Plant battery energy alone cannot authorize charging during darkness. Fixed-service peaks are reserved separately from their hourly energy, including overlapping fractional tasks. This remains an hourly scheduling approximation rather than a fast electrical controller.

## A prediction becomes an actual request

`PlantServices.propose_charge` rebuilds a current-hour recipe from the installed dock, current battery headroom, compatibility, occupancy and observed support availability. The proposal does not reserve resources, draw a fault outcome or add energy.

With `actuator-interlock/1`, a private charger failure prevents energy delivery with either recovery policy. The failure becomes visible through the same next-boundary command feedback; subsequent planning treats the observed dock as unavailable. Recovery permission controls possible remedies. Legacy archived `recovery-gated/1` runs retain the older, policy-dependent fault execution and cannot establish a fair charger-recovery comparison.

`dispatch_selected(..., charge=False, charge_requests=...)` rechecks the explicit request. If it no longer fits, it records rejection with the original requested power; it does not silently shrink the request. The registered executive books and executes accepted charging. Only its actual completion receipt replenishes the robot battery. A stale comparison cannot be accepted over another decision.

Only the first hour is accepted from an optimized schedule. Later charges remain conditional predictions. The selection and its original evaluation are retained in the service decision record. Solver time limits and no-incumbent outcomes remain visible; choosing a feasible fallback or escalation is the caller's responsibility.

## Running cost without double-counting

`dock-incremental-cost-table/1` computes the exact additional decision cost for zero through the horizon's active dock hours. It uses the recorded prefix and already committed work, preserving the existing maximum-of-usage-and-parts allowance. With a €1,000 consumed dock part and €600 per active hour, the additional allowance for zero, one, two and three new hours is €0, €0, €200 and €800. Fixed ownership does not enter the comparison. Contracted activity uses its declared service rate; missing rates remain unknown.

The optimizer uses a one-hot active-hour cost table rather than an average per-kWh price that could duplicate a replacement allowance. Dock electricity is already in the plant energy balance. The comparison reports process economics and additional dock cost separately; it excludes unchanged committed service costs and sunk costs and is not an allocated whole-run cost report.

A small explicit numerical tie-break of `1e-5` per charging kWh and reserved slot discourages unnecessary charging. This is a weighted objective, not a proof of strict lexicographic optimality. A validated integer-off slot can contain floating-point residue; any removal is recorded, and the revised trajectory must pass the energy checks again. If a degenerate solution reserves a zero-power slot, it is released and both the solver's reserved count and the actual positive-power count are reported. Releasing it cannot increase the nondecreasing cost table.

## Evidence and remaining work

The independent two-hour thermal fixture has 12 kWh solar per hour, a warm reactor, hydrogen already available and no heater. It can produce 10 kg methane now before cooling below its production band. A robot needs 10 kWh of charging by the second boundary. Postponing that charge retains the 10 kg production opportunity; requiring it immediately leaves too little power for the minimum production load. This verifies one understandable trade-off, not general MPC superiority.

`tests/test_service_charging.py` also covers empty/full storage, exact losses, unavailable dock/robot intervals, a shared charger, no same-hour energy borrowing, fixed-service demand, return reserves, immutable input forecasts, unavailable forecast vintages, missing prices, stale selections, actual receipts and cost reconciliation. Existing service planning, pricing and legacy execution checks continue to apply.

Remaining stage-4 integration includes choosing meaningful targets from work requests, joint mission selection with observation-contingent remedies, online rescheduling and fallback, service what-ifs, run-level policy configuration and paired Studies. Uncertain weather and service outcomes must enter explicit scenarios. This first charging optimizer uses a conditional saved point forecast; it does not claim robust service availability.
