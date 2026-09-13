# Recovery and finite support logistics

`ServiceSystem.support_model = "logistics/1"` opts into `plant-service-contracts/3`. Older runs retain their original runtime, fields and source. This is an illustrative hourly scheduling model with fractional mission phases, not a navigation or mechanical-repair simulation.

## Retrieval and observed return to work

A mobile mission abort records its last point, phase and progress. Its hardware remains stranded and its unfinished work remains failed. The supervisor sees that telemetry; it does not receive a future failure or recovery schedule. An enabled crew can undertake a compatible retrieval with five declared phases: outbound travel, preparation, transport to the dock, unloading and return to base. The default response lead is two hours before dispatch; outbound/return crew travel takes one hour each, and preparation, towing and unloading each take half an hour. Those timings are assumptions, separately editable in advanced setup.

Unloading produces a physical location receipt at the next hourly decision boundary. It does not establish health. A separate quarter-hour supervised drive test uses 0.2 kW of robot energy, a remote operator reservation and 0.25 hours of finite remote allowance. Its seeded usable pass/fail observation becomes available at the following decision boundary. Only a new passing reading measured after the return permits ordinary work. Charging is permitted at the dock before acceptance; it does not substitute for acceptance. Failed tests, missing communications and exhausted remote time leave the robot unavailable. A failed test is retained without automatic repeated attempts in this version.

For the reference example, an H1 retrieval request dispatches at H3, unloads at H5.5 and is eligible at H6. A test at H6–6.25 supplies evidence at H7. The original cleaning mission remains failed, with its already treated area and consumed resources intact. Retrieval addresses a mission abort; arbitrary mechanical damage requires another compatible repair model. The probability of a passing drive test is an assumption, not an empirical reliability claim.

## Finite crews, operators and supplies

The repeating crew calendar uses elapsed hours from the simulation origin, not inferred local business hours. Defaults are a 12-hour shift in a 24-hour period, 12 crew hours and one remote hour per period. A whole crew mission, including its return, must fit inside a shift. Every actual travel, work and return interval consumes crew allowance. Remote tests reserve the single operator and consume their actual duration. At each positive period boundary the ledger records offered, accepted and rejected allowance; unused allowance does not accumulate beyond capacity. A busy or stranded crew cannot start a duplicate visit.

Typed on-site cleaning, module, calibration and brush stocks have explicit capacities. Each has its own finite upstream stock. An exhausted store can request a fixed delivery lot, with declared lead, travel and handling. The upstream quantity includes reserved goods in transit until the delivery completes. At the next plant boundary the ledger records the quantity accepted and any rejected excess. Reserved stock cannot be reused; an incomplete visit retains its used labour and unmet demand. This aggregate pipeline does not simulate cargo handling or individual warehouse custody. A full lot must be available upstream; the example does not silently reduce a requested lot.

A dock brush change consumes one brush spare and explicitly discards the remaining old usable-area allowance. The new allowance is replenished only after the work completes. Installed brush life, spare inventory and actual treated area remain distinct; replacement cannot generate negative reported brush wear. Full replenishment and partial cleaning remain separate events.

## Accounting, drawing and evidence

Every dispatch stores its original request, current eligibility information, complete mission stages and model identities. The support ledger records consumed crew/remote hours, typed supply flows, rejected deliveries and discarded brush allowance. Existing visit and hands-on labour rates still apply. Remote time, installed brushes and rejected supply quantities are marked **unpriced** until stage 3 supplies their complete procurement and running-cost basis. These examples must not be interpreted as complete hardware economics or annual installation value.

The original plant drawing is untouched. A service van follows a schematic ground route, a technician prepares the recorded stranded location, and a flatbed carries the existing robot illustration back to the dock. A loading pause and transport pose are illustrative interpolation of declared phases. They do not claim winch, reach, force, slope or route-clearance calculations. Drive tests do not animate brushing or scanning. Reduced motion uses recorded boundary poses. Returned hardware can become visually docked while still unavailable to the controller.

The independent standard-library reference reconstructs crew calendars and response lead, mission interval duration, labour consumption, allowance timing, retrieval/effect boundaries, immutable test readings and return-to-work eligibility. It checks supply receipts against upstream consumption and brush replacement against spare/discard records. Stock bounds, accepted/rejected quantities, electrical conservation and optical effects have separate checks. Forged return flags, early effects, backdated drive readings and altered labour counters are tested. Passing these checks establishes consistency of the declared model, not real-world validity of assumed service success.

Run `.venv/bin/python -m methane.services.support_demo` for saved mechanism examples, playback and reproduction bundles. The report keeps failed recovery, remaining stock and outstanding work visible. These cases are not substitutes for the generalised Studies publications planned in stage 3.

## Remaining scope

Visit bundling, richer remote assistance, explicit failed docks and support hardware, equipment-specific mechanical repairs, wet cleaning, richer sensing and complete costs remain required programme work. No arbitrary repair capability is inferred from this retrieval adapter. All assumptions and operations remain subject to the compatibility and information boundaries in [service contracts](service-contracts.md) and [plant integration](service-plant-integration.md).
