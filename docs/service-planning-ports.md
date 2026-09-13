# Service commitments before production dispatch

This is an internal stage-4 checkpoint, not the complete autonomous service supervisor. The simulation still uses its existing local service rule by default. The opt-in [run-level coordinator](service-coordination.md) now uses these interfaces to evaluate known service schedules, current charging and production before accepting work. The complete programme still requires contingent remedies, joint visits and broader failure/risk comparisons.

## A decision has an explicit boundary

`PlantServices.prepare` processes current observations, post-work verification, supply interruptions and queued work requests. It does not accept a new mission. A caller can then use `propose` repeatedly to build an immutable mission from a registered recipe and assess current eligibility and resources. This neither consumes a random-event request number nor reserves stock.

`dispatch_selected` accepts work-order identifiers and proposed start times. It rebuilds the registered recipe and rechecks current power, stock, compatibility and occupancy. It cannot accept an externally modified mission with omitted travel, tools or energy. Acceptance is sequential: an accepted job remains an explicit commitment if a later choice fails. Rejections stay queued with their reasons. `dispatch_local` retains the existing ordered policy and visit bundling; the compatibility `begin` method calls preparation and local dispatch.

The decision must be completed before execution. Execution happens once, and the next decision must follow completion. Actual fault effects and stochastic outcomes remain in the private execution port after dispatch. A candidate therefore cannot learn whether a repair will work by evaluating it.

## Energy, power and material are different quantities

`service-demand-projection/1` projects remaining stages from each live mission's observed cursor. It intersects fractional stages with half-open hourly intervals using decimal boundary arithmetic.

- **Bus energy, kWh:** integrated tool/charger load plus the declared continuation of the currently granted standby load.
- **Bus peak, kW:** the sum of simultaneously active stages. Separate jobs' independent peaks are not simply added when they occur at different times.
- **Robot energy, kWh:** consumption by battery resource. Return margins remain held inventory and are not treated as consumed energy.
- **Supplies:** one-time stage-entry consumption is distinct from hourly consumption. An already-entered stage does not consume its opening materials again.
- **Isolation:** an hourly production restriction whenever an isolation reservation intersects that interval.
- **Terminal obligations:** actual remaining work duration, waiting until departure, time until completion, return duration and battery consumption after the horizon. Waiting is not labelled as work.

A quarter-hour task drawing 4 kW uses 1 kWh. It still requires 4 kW while running. A task ending exactly as another starts does not overlap it. Those two facts are independently checked, alongside reconciliation with the execution ledger.

The projection assumes successful continuation. It creates no future deliveries, charging credits, repair success, cleaning benefit or observation outcome. Changed conditions still cause interruptions in execution. Current readiness requirements are conservative: a currently unavailable robot is not promised to a later job on the assumption that another job will repair it first.

## A conditional production calculation

`service-process-demand-coupling/1` checks proposed mission recipes jointly against the current resource ledger, then passes their hourly utility and isolation trajectory into the production planner. It separately checks fixed-service peaks against forecast solar supply. The existing active-service solar-only rule remains in force; plant battery energy cannot silently authorize a tool that the execution model would interrupt.

Inputs include the original estimated plant state, capacity estimate, prices, decision hour and saved forecast identity/publication time. Forecast times must be consecutive UTC hours, and the issue must have been available at the decision time. Missing timing is not reconstructed. Current forecast power must agree with the prepared service decision. The result retains an input identity and service-decision identity for later transport and selection checks.

By default, every proposed new job must finish, including its return, within the comparison horizon. A caller can explicitly relax that requirement; the result marks the assumption and reports the unfinished obligation. Previously accepted work can extend beyond the horizon and remains visible. No terminal resale revenue is assigned.

The result distinguishes:

- **Infeasible:** a declared requirement, resource, completion boundary or forecast tool-power limit is violated.
- **Unresolved:** the production solve produced no validated incumbent, or its physical trajectory failed verification. A solver time limit is not proof of infeasibility. No unverified zero-action schedule is accepted as a solution.
- **Feasible:** these declared demands and the validated process trajectory can coexist under the supplied forecast and continuation assumptions.

Version 1 of this port reported process decision economics separately. `service-process-demand-coupling/2` also accepts complete service prices and a declared outcome tree. Neither version infers restored capacity or the informational value of an inspection. The complete supervisor still needs conditional service benefits and follow-up actions, charging, rescheduling/fallback integration, broader original-information alternatives and paired Studies. The opt-in [recovery scheduler](recovery-planning.md) now handles actual consecutive operating tests. No global-optimality claim follows from this decomposition.

## Priced alternatives and shared decisions

`service-decision-pricing/1` prices the incremental cost of adding recipes to the original recorded prefix and remaining commitments. It shares the recorded ledger's arithmetic, including the maximum-of-usage-and-parts allowance. Fixed ownership, service electricity already on the plant bus, and lost methane already in the physical trajectory are not charged again. Missing prices, supply acceptance and unfinished costs remain explicit conditions. Optional activity-based price version 2 includes fixed-hardware intervals; older price versions retain their original meaning.

`service-outcome-tree-mpc/1` assembles one production model per declared branch. It adds equalities requiring identical actions while branches have the same observation history. Histories cannot merge after diverging. Current observations and capacity estimates must agree; an estimated capacity change needs a declared later observation. Every branch preserves the original forecast issue and hourly time window. Branch probability and timing are assumptions with identifiers, not empirical calibration or simulator fault truth.

Version 2 adds explicit requested load and possible delivered load for recovery tests. All hypotheses share the current capacity estimate and original forecast; their declared delivery limits can differ without granting the controller knowledge of which one is true. A shared request can therefore produce different hydrogen and electricity flows in the branches. These optional hypotheses have their own recorded identities. Branches without them retain the original action model.

The objective mixes expected and worst-branch process objective with an explicit risk weight from zero to one. It retains the process objective's cost/start tie-breaks and adds the candidate's incremental service cost once. Plant terminal minima are hard constraints in every branch. A missing or invalid incumbent remains unresolved. A separate solve for each future is not a valid comparison if it chooses different present actions using tomorrow's information.

An independently calculable two-hour fixture demonstrates the distinction. A 12 kWh battery faces either 12 kW or no solar next hour, while a mandatory next-hour bus load needs 12 kWh. A warm reactor could use the battery now to produce 10 kg methane, but without heating it cools below its production band. Shared decisions retain the battery and produce zero methane. Separate clairvoyant solves incorrectly suggest an expected 5 kg. This checks the information constraint, not the accuracy of weather probabilities.

## Bounded schedule selection

`service-schedule-supervisor/1` enumerates supplied order/start combinations and evaluates registered recipes using the same initial information, prices and outcome branches. Optional requests include deferral. Required procedures have explicit completion deadlines within the comparison window; completion includes return and does not claim useful evidence or verified recovery. Ending service-stock floors deduct forecast consumption without invented replenishment or charging. Existing reservations still enforce return-energy requirements.

The result records every rejected, unresolved, feasible or unattempted candidate. It chooses the best validated incumbent under the declared objective, with stable identifier tie-breaking. Per-solve limits and a total comparison budget are separate. Cancellation leaves live work unaccepted. Committing a selected result rechecks the current decision identity and registered recipes, then records the comparison alongside the actual selection. It does not silently call a fallback if no schedule is feasible.

The checked five-hour inspection example selects hour 2 when an hour-1 cloud outcome would interrupt earlier work. At €8 per active hour the 2.25-hour procedure costs €18. If the inspection is optional and no informative finding has been modelled, deferral wins in the zero-production example. This is appropriate: scheduling costs alone do not establish inspection value.

This standalone selector remains callable experimental machinery. The separate opt-in run-level controller now combines single-request scheduling and charging; neither is a complete autonomous repair controller. It does not create contingent remedy choices, automatically bundle new visits, cancel accepted work or infer repair success. A separate [joint charging port](charging-planning.md) now optimizes the dock and plant against declared energy targets, with actual receipt and cost reconciliation. The run-level controller integrates that port with single-request mission selection. Multi-job and observation-contingent selection remain required. An observed reset can clear a physical trip before sufficient consecutive informative load probes have confirmed recovery. The separate opt-in recovery policy now schedules those tests and retains original-information alternatives; integrating the rest of the service decisions remains required stage-4 work.

## Conditional cleaning benefit

`conditional-section-treatment/1` supplies the missing physical consequence for a cleaning candidate. It takes the current, explicitly ideal surface observation; eligible raw radiation/reference-PV samples; registered plans and their observed stage cursors; current brush allowance; and earlier recorded treatment events. There is no simulator fault state or future procedure result in this interface.

For each hourly interval it first calculates available DC using the current patches, then applies the intersecting planned coverage and the hourly loose-soiling accumulation. Treatment changes the next decision interval, preserving execution's timing. Dry passes retain the brush efficacy fixed at their first progress; a partly executed pass requires that original observed efficacy. The predictor consumes the remaining brush allowance and gives no credit for a future brush replacement. Portable wet treatment uses its distinct loose/adhered removal; permanent damage is unchanged. The same section temperature, conversion and clipping kernels calculate power in execution and prediction.

`service-process-demand-coupling/3` opts into this calculation through `reference_forecast`; calls without it retain version 2 behaviour. The supplied raw forecast must reproduce the original untreated DC forecast and preserve its issue, availability, time window and ambient inputs. The resource projection separately checks energy, water, work areas, isolation and fixed-tool peak power. With outcome branches, each branch needs its own matching raw reference in `outcome_references`; all present observations remain common. Response identities bind both original reference inputs and candidate-specific treatment calculations.

`service-schedule-supervisor/2` uses those physical changes when comparing declared schedules. A small eight-hour test starts with a warm reactor, no plant battery, constant radiation and a 300 kW array. With an illustrative €100/kg methane value to make the comparison unambiguous, additional un-clipped generation pays for the cleaning procedure. With a 200 kW converter, the entire gain is clipped and deferral wins. This is an intentionally constructed scheduling check, not a proposed operating price or a representative plant result. Earlier tests also show that extra sunlight cannot help a cold/energy-starved subsystem cross a start threshold without enough power; no test requires cleaning or MPC always to win.

The forecast explicitly assumes uninterrupted continuation. It does not assign calibrated mission-success probabilities, forecast wind/rain eligibility from absent data, make a failed robot return, repair hardware, or count restored DC as methane. The opt-in run-level coordinator adds fixed obligations, bounded interrupted-repair retries and joint charging. Observation-contingent remedies, interruption scenarios and their costs, and new joint visits remain required. Existing experiments and all twelve learning fixtures retain their original interpretation; this callable calculation does not replace their recorded controller.

## Checked example and compatibility

The fixed reader requires 0.2 kW for two hours of work and a quarter-hour verification. In the saved test forecast, solar drops from 1 kW to 0.1 kW during the second interval. Starting immediately violates the future tool-power limit. Starting at hour 2 completes at 4.25 h, with predicted service energy `[0, 0, 0.2, 0.2, 0.05]` kWh. The execution ledger reproduces that demand and completion time. This demonstrates feasible timing, not a general methane gain or a guarantee against forecast error.

The tests also cover material-entry semantics, unspent return reserve, missing publication data, unavailable future forecasts, conflicting tasks that are individually feasible, solver limits, stale selections and repeated read-only candidate queries. Six existing fixed/mobile/cleaning/reset/logistics/bundled workflows were run against a frozen earlier source and the refactored runtime. Their 72 complete service records and fault states match exactly. Evidence is retained in `build/services/planning/local-compatibility-check.json`; the result applies to those fixtures, not every possible run.
