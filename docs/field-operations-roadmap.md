# Field operations: proposed full roadmap

Status: proposed next programme, 11 September 2026. Based on the [field robotics research](../research/field-robotics/report.html), its [14-class catalogue](../research/field-robotics/catalogue.json), the [implemented service model](field-operations.md) and the [Studies architecture](studies.md). This document does not change simulation behaviour. Hardware feasibility assessments remain those of the dated research; numerical performance and cost assumptions require their own evidence.

**Required realism gate, reviewed 12 September 2026:** the [completed initial review](../research/field-realism-review/report.html) covers the first service system, plant assumptions and all 14 families. The [gate](field-operations-realism.md) remains open for real autonomous-repair, fleet-selection and European ROI claims. Repeatability and implementation completion do not satisfy it. Cause-specific remedies, measurement chains, compatible array/cleaner designs and site/support evidence take priority before expansion or learned-policy investment. The stopped programme is not resumed by this review.

## Outcome

Make field operations a composable part of autonomous plant management. The platform should support a complete chain:

**Observe → assess uncertainty → choose work → allocate hardware and resources → coordinate with production → execute → verify → recover or escalate.**

The research catalogue spans inspection, maintenance, fixed automation, service-friendly equipment design and construction. Each family should enter through the same service contracts, with a physical mechanism and an experiment that makes it useful. Catalogue coverage alone is not a completion criterion for a numerical model.

## Implemented baseline and remaining boundaries

We have persistent faults with explicit transient/legacy alternatives; an optional cleaner, inspection rover, dock, bounded reset and human service; finite robot energy and kits; work phases; physical isolation during intervention; separate repair and diagnostic verification; running costs; recorded outcomes; and animated main-scene hardware. Current examples use illustrative assumptions.

Important remaining limitations:

- Assets and task kinds are built into a single service runtime, rather than independently registered models with capability contracts.
- The shared service policy is a local rule. Process MPC accounts for current dock load and known isolation but does not choose future cleaning, inspection, repair or charging schedules.
- Cleaning removes a lumped available-DC loss after conversion. There is no section coverage, weather-dependent treatment or brush-condition model.
- Rover inspection reads an ideal declared trip contact. Other sensing modalities and their observation errors are not implemented.
- Human service bundles module replacement and flow calibration. Remote assistance, replenishment and stranded-robot retrieval are incomplete.
- Field tasks use whole-hour phases and coarse access flags. The drawn routes do not implement geometry or navigation physics.
- Service-specific Model essays and targeted service what-ifs remain to be built.
- The reusable study storage exists, but its case resolver and policy comparison are still specialised to the battery-reserve protocol. Field presets and validation examples are not yet a published field-operations study programme.

## 1. Establish reusable service contracts

Extract independently testable definitions for **assets, capabilities, service interfaces, work orders, mission records and support resources**. Separate task selection, feasibility checks, execution effects, observations and costing. Migrate existing hardware without changing its versioned physical semantics.

An asset declares its location, mobility, energy source, health, tools/payloads, compatible interfaces, autonomy/assistance mode, ownership basis and maintenance needs. A capability declares the specific action it can attempt, required operating state, duration/resource model, environmental limits and verification procedure. Unsupported combinations remain unavailable with a recorded reason.

Use an access graph with named service points, travel duration/energy, permitted platforms and blocked edges. Add reservations for docks, tools, spares, work areas, crew time and equipment isolation. Distinguish unavailable communications from unavailable power. Compatibility records can include exact hazard/certificate scope or explicitly unknown status; the sandbox does not certify a real installation.

Introduce versioned fractional-hour mission events while retaining hourly plant dispatch. Integrate resource consumption over intersecting hours. Measurements and restored plant capability become eligible at the next plant decision boundary after completion. Specify conservative isolation reservations across those intervals; do not imply emergency-response fidelity.

**Gate:** a fixed device and a mobile asset can fulfil the same compatible work request through different execution adapters. Tests cover resource contention, interruptions, missing prerequisites, observation timing and immutable legacy replay. No controller receives hidden fault cause or successful-repair truth as an estimate.

## 2. Complete the first service system's physical and recovery detail

### Cleaning

Add section-level removable soiling, covered area, imperfect treatment, partial progress, residual fouling and distinct permanent damage. Associate cleaner capability with array geometry and declared access. Track brush condition, cleaning materials and water when applicable. Introduce rain/wind restrictions only with recorded data or labelled synthetic assumptions; missing weather is explicitly unknown.

Move the richer optical-soiling mechanism into the irradiance/conversion chain before clipping under a new model version. Preserve the existing post-conversion proxy in old runs. Distinguish recovered irradiance, recovered available electricity, curtailed electricity and actual methane benefit. Permanent damage, snow and adhered fouling need compatible actions, not automatic removal by every brush.

### Inspection and sensing

Start with bounded fault hypotheses and observations whose relation to those hypotheses is explicit. Add measurement error, unreadable targets, delay, stale readings, sensor drift/dropout and common-mode errors. Compare process sensors, a fixed independent channel and rover-acquired evidence. A camera does not reveal arbitrary hidden health. Store the observation method and its conditions for informative evidence.

### Repair and support

Separate reset, module replacement, instrument calibration and robot retrieval. Each gets compatible interfaces, prerequisites, resources, possible interruption/failure and a post-service test. Calibration needs an appropriate reference and procedure. Physical restoration and the observer's confidence update remain separate.

Add finite remote assistance, human availability, travel/lead time, visit bundling, spare replenishment and stranded-asset recovery. Human departure and robot return become recorded events when modelled. Include failed docks and disabled service hardware: the maintenance system also needs maintenance.

**Gate:** demonstrate useful recovery, unsuccessful service, an inconclusive observation, blocked access, exhausted stock and stranded-robot retrieval. Every visible effect reconciles with the mission and resource ledgers.

## 3. Establish complete economics and baseline experiments

Extend the current cost ledger with installation/mapping, access modifications, payloads, dock standby demand, software/communications, remote labour, scheduled maintenance, callouts, replenishment and retrieval. Distinguish purchased equipment from contracted/shared service. Keep illustrative inputs and quote-required fields visible.

Maintain three related views: allocated period cost, action-dependent decision economics and actual expenditure/events. Reconcile replaceable-part wear and replacement treatment; avoid duplicate ownership/subscription charges. Production losses already appear in the physical trace and must not also be subtracted as the same lost output. Report remote human time separately from site visits. Visits shared with feedstock or spare delivery are only partially avoidable.

Generalise study protocols to select named scenario resolvers, service policies, hardware configurations and comparison arms. Preserve the existing battery protocols and publications. Start with human-only, no-intervention and robot-assisted systems under the same environmental-loss mechanism, then add fixed automation as a baseline when its observation/action model exists.

Publish these first questions independently:

| Study | Comparison and purpose |
|---|---|
| Cleaning value | No cleaning, periodic cleaning, condition-based cleaning and human-operated cleaning; expose clipping, curtailment and feedstock bottlenecks |
| Information value | Existing sensors, added fixed sensing and rover observations; distinguish earlier evidence from physical repair |
| Verified recovery | Diagnosis only, compatible reset, human repair and later robot-compatible intervention; retain failed attempts and incomplete recovery |
| Support dependence | Blocked route, weak charging, failed dock, unavailable communications, depleted references/spares and unavailable crew |
| Installation economics | Resident equipment, shared/contracted service and on-call human visits across plant sizes and travel distances |
| Service-friendly design | Conventional versus prepared interface with the same task, robot and fault assumptions |

Initially publish short fault-recovery and workflow studies. Annual installation economics waits for adequate seasonal weather, degradation, logistics and simulation duration.

**Gate:** new field protocols run, cancel, resume, reproduce and publish through Studies. Reports retain exact editions/attempts, all input changes, failed/incomplete cases, unresolved backlog and ending plant/service inventories. Baselines may outperform robots.

## 4. Add planning for maintenance and production together

Keep the current rule as a baseline. Add a service supervisor that proposes feasible mission schedules using current estimates, eligible weather forecasts and possible observation outcomes. Exchange predicted charging/utility demands, equipment downtime, resource reservations and observation arrival times with process MPC. Validate the combined schedule in execution. Record solver limits, blocked tasks and fallbacks; decomposition is not a claim of global optimality.

Operational choices include cleaning now versus after rain, inspecting before reserving a technician, charging before a low-power period, timing replacement during low-value production, combining visits, retaining recovery resources and choosing a permitted degraded mode.

Use physical limits, compatible actions, return-energy requirements and accepted operational commitments as constraints. Offer sustained methane production and operating contribution as explicit objectives. Evaluate service failure and uncertain weather through scenarios/risk sensitivity rather than hiding everything in a single reward weight. Report visits, remote minutes, downtime and adverse outcomes separately. A site-independence requirement can be a declared constraint with an explicit infeasible outcome and escalation policy.

Terminal conditions must include plant energy/feedstock/thermal state, robot energy, usable spares/references, health uncertainty and outstanding work. A controller must not appear economical or autonomous by postponing every expensive task beyond the study window. Compare extended rollouts and terminal assumptions; do not assign speculative resale revenue to inventories.

Inspection value depends on whether credible findings would change subsequent actions. Evaluate those branches from the current belief, never from the injected fault identity. A first version may use a small enumerated set of outcomes instead of a general POMDP solver.

**Gate:** paired studies identify where service planning helps, where it loses and why, using the same available information and compatible actions. Forecast errors and support failures trigger explainable rescheduling or escalation.

## 5. Expand the hardware catalogue through mechanism-specific modules

The following covers all 14 research classes. Existing implementations are reduced archetypes, not calibrated replicas of the example manufacturers.

| Hardware class | Place in the programme | Required modelling depth |
|---|---|---|
| Dedicated solar-row cleaner | Expand current core | Section coverage, geometry, partial cleaning, brush condition, weather and return/dock resources |
| Portable wet/dry cleaner | Early comparison baseline | Operator presence, setup/transfer labour, water, coverage and travel |
| Mobile ground inspector | Expand current core | Payload-specific evidence, access, uncertainty, failed reads and remote help |
| Docked aerial inspector | Next inspection family | Coverage versus revisit time, wind/rain eligibility, flight reserve, dock support and delayed observations |
| Contact inspection crawler | Conditional integrity study | Reachable surfaces and thickness observations linked to an explicit corrosion/erosion model |
| Vegetation-management robot | Site-operations study | Growth, shading/access effects, terrain, treatment coverage and seasonal maintenance |
| Sampling and analyzer station | Fixed-hardware study | Sample/transport/purge delay, utilities, contamination, analyzer uncertainty and reference stocks |
| Automatic sensor service station | Early fixed-automation comparison | Compatible sensor/reference, cleaning/calibration procedure, channel downtime and verified return |
| Rugged fixed sensor package | Early inspection baseline | Coverage, independent/common-mode errors, drift, dropout, energy and servicing |
| Remote actuator / redundant service path | Expand bounded recovery | Position/command feedback, stuck states, motive power and a specific permitted plant effect |
| Mobile maintenance manipulator | Explicit future-capability study | Tool/reach/torque compatibility, staged operations, supervision, failures and verification |
| Robot-compatible replaceable module | Paired plant-design study | Prepared interfaces, isolation, spares, insertion/removal and acceptance tests |
| Solar construction robot | Separate commissioning programme | Mobilisation, crew/machinery, installation progress, defects and commissioned-capacity timing |
| Pre-integrated deployable solar array | Separate plant-design comparison | Transport, crew/equipment, deployment time, footprint and operational access/cleaning compatibility |

Docks, tools, communications, reference stocks, spare parts and human crews are shared support resources in addition to this catalogue. A hardware module becomes complete when its relevant mechanism, constraints, cost basis, observations, tests, illustration, documentation and comparative experiment are delivered. A decorative icon or an unsupported generic repair probability does not establish capability.

Commissioning has its own boundary: machinery can leave, construction expenditures have distinct timing and useful plant capacity enters service progressively. Do not retain temporary construction machinery as permanent operating assets by default.

## 6. Add degradation, predictive maintenance and learned policies

Expand from fixed injected-fault challenges to explicit usage/environment-dependent degradation only where a physical hypothesis exists. Distinguish prediction of a condition from knowing remaining life. Test maintenance rules against independent calculations and held-out conditions before treating learned predictions as useful.

Provide reproducible training adapters over the same observation/action contracts. Start with bounded estimates such as soiling forecasts, mission duration, diagnostic uncertainty or continuation value. Compare learned service policies and homeostatic/reserve approaches against rules and service-aware MPC. Preserve training data/seed, model version, hyperparameters and evaluation boundaries; use held-out plant sizes, weather and fault regimes. Training remains outside interactive playback and a published evaluation never silently retrains its policy.

Homeostatic targets represent the capability to keep operating and recover: sufficient joint plant/robot energy, appropriate spares/references, usable observation channels and manageable backlog. Targets depend on operating mode and expected need. Rewarding permanently full batteries or stock can produce hoarding and inactivity, so evaluate production and human work alongside reserve measures.

For fixed-fault studies, match exogenous injections. For degradation studies, match underlying random streams/exposure thresholds while allowing policies to alter failure timing through different usage. Separate evidence about recovery from evidence about prevented failures.

**Gate:** held-out comparisons report learning failures, uncertainty calibration where applicable, data demands, runtime and fallback use. No requirement that a learned controller outperform a simpler method.

## UI, assurance and publication throughout

- Keep the simulation visually quiet. Extend the illustrated hardware through recorded position, task phase and declared working poses; preserve the existing equipment artwork.
- Give each service asset progressive Now / Why / Next / Costs / What-if inspection. Reveal investigation questions, actual returned evidence, compatible actions, missing resources and recovery tests.
- Add targeted alternatives such as defer cleaning, inspect before repair, choose human service, reserve dock energy or postpone an intervention. Replan using the original information and assumptions, with explicit prediction labels and stale-response protection.
- Extend Model with field assets, service interfaces, observation uncertainty, recovery and running-cost essays. Parameter edits in learning examples remain separate from experiment setup.
- Trace report → case → mission → observation/action → physical effect/resource ledger → implementation and source. Narrative interpretation stays distinct from recorded outcomes and automated checks.
- Check physical/resource conservation, compatible effects, isolation, task contention, causal information availability, failed recovery, economic reconciliation and archive compatibility. Preserve original plant/solar screenshots; review each new hardware illustration and reduced-motion behaviour.
- Publish a human-readable write-up for each study: question, method, assumptions, comparison, results, unsuccessful/incomplete cases, limitations and implications. Changed plant parameters produce a new edition with visible differences, not a replacement of earlier evidence.

## Recommended next implementation package

Begin with reusable service contracts and the gaps in the current end-to-end example, while generalising study resolution in parallel within the implementation workflow. Prioritise explicit task-specific service/verification, resource reservations, bounded sensing uncertainty, meaningful cleaning coverage and the human/support logistics needed for fair accounting. Then publish the first matched service studies before expanding to the drone and more speculative manipulation families.

Review after those studies: they may favour fixed sensing, a service-friendly plant interface or occasional human visits over additional resident robotics. Subsequent hardware priority should follow those findings and the user's design goals.
