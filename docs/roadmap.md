# Dispatch Lab completion roadmap

The completion target is a reproducible research platform: select a European site,
configure a plant and support system, compare operation under uncertainty, inspect
its decisions and publish a traceable assessment. This is separate from field
validation, live plant control, safety certification and eventual DePIN deployment.

The September 2026 scope correction makes product usability the release criterion.
Small named checks verify mechanisms and the complete workflow; large policy/site/
season matrices are reusable study templates for users, not a mandatory research
queue. One representative annual case checks long-duration operation. See the
[product acceptance revision](../research/release-2/product-acceptance.md).

## Current finite product roadmap

The modelling tranche is closed for this roadmap. The original releases and
subsequent equipment work below are delivery history, not a repeatedly expanding
sequence. Additional components, literature mappings, data and learned policies
are optional backlog unless explicitly reprioritised.

| ID | Increment | Completion gate | Status |
|---|---|---|---|
| **P1** | Practical agent operation | Operate saved project inputs including utilities; continue committed state; recover interrupted sessions; numerically replay saved requests with differences reported. Retain the six bounded process actions and the reference service executive. | Complete — see the P1 acceptance record below |
| **P2** | Expert UX consolidation | A coherent Site → Build → Operate → Investigate → Compare → Write up workflow, progressive disclosure, reliable context/return navigation, and real participant walkthroughs with misunderstandings recorded and addressed. | Next; not started |
| **P3** | Installation and durability | Fresh installation and guided workflow rehearsal, plus an actual off-machine export/backup/restore drill at an agreed destination. | After P2; storage destination needed for the off-machine drill |

Return after each increment with these same IDs, their status and outstanding gate.
A discovered defect can require correction inside an increment; a useful modelling
idea does not automatically become a new step before P2. Real plant observations
are not a prerequisite for completion of this research-based software platform.
P1's contract is [practical agent operation](agent-control.md).

### P1 acceptance · 18 September 2026

Delivered through **Simulation menu → Agent control**. The [control guide](agent-control.md)
describes project/site-utility inputs, committed state, interruption recovery,
permission renewal, recorded-request replay and portable archives.

Verification covers ten new acceptance cases, including a killed worker after
command acceptance, app-registry loss, site water restrictions, disclosed CO₂
arrivals, carried service state/accounting, corrupt inputs, authority boundaries,
independent-balance corruption detection, cancellation and offline bundles.
The existing controller, continuation and protocol checks also passed.

- Full Python sweep: **1,313 passed; one source-identity mismatch**. README was edited
  after that process captured its source capsule but before an isolated worker
  started. The check correctly refused identical experiment identity across those
  different capsules. Both isolated-worker tests passed in a stationary rerun;
  the original failed sweep is retained, not relabelled as a clean full pass.
- **99 JavaScript tests passed.** **17 distinct browser cases passed**, including
  the actual stdio MCP round trip, recovery, continuation, project selection,
  replay, keyboard/narrow-screen navigation and unchanged plant/solar screenshots.
  Two environment-gated browser cases (new component lineage and extracted offline
  playback) were skipped; the standalone offline bundle checker was exercised in Python.
- Locked dependency installation, lint, formatting, documentation freshness,
  catalogue, taxonomy and generated engineering documentation checks passed.
- Desktop/mobile captures were reviewed. The live app's entry and return were
  rehearsed; this is software verification, not participant feedback or empirical
  plant validation. Numerical replay preserves requests, not external agent inference.

Local test artifacts are under `build/agent-control/`; old evidence is unchanged.
P2 and P3 remain the next increments. No modelling extension is inserted ahead of them.

## Delivery history

## Release 1 — qualified reference autonomy

Acceptance and current work: [release-1.md](release-1.md).
Implemented contract: [reference-autonomy.md](reference-autonomy.md).
Publication: [release report](../research/release-1/report.html).

Correct recovery obligations, qualify saved failures, establish matched repeated
baselines and complete explanations/evidence for the existing plant/service system.
The release gate includes independent accounting, causal information separation,
legacy preservation, browser/offline workflows, performance and an explicitly scoped
comprehension walkthrough. Numerical qualification is not empirical calibration.

## Release 2 — complete deployment and service lifecycle

Preserve the [field programme](field-operations-roadmap.md) and expose its reusable
recipes; do not relaunch optional studies or erase their incomplete records.

1. Complete capability/prerequisite coverage for all fourteen families. Each family
   needs executable mechanisms, qualified boundaries, support, costs, observations,
   failure/recovery examples, illustrations, Model material and a comparison. Keep
   unsupported capabilities unavailable or explicitly speculative.
2. Complete service infrastructure and design comparisons: docks, access, references,
   tools, communications, consumables, remote assistance, crews and common failures.
   Verify restoration on representative artifacts; retain broader terminal-risk
   studies as user-run templates.
3. Model commissioning and progressive plant availability, installation access and
   temporary construction hardware. Tie capacity and expenditure dates to Sites.
4. Add credible degradation, replacement and replenishment mechanisms. Carry condition,
   stocks and backlog through chronology; distinguish simulated ageing from cyclical
   reuse of weather years and financial assumptions.
5. Develop condition-based and preventive maintenance comparisons. Only claim remaining
   useful life where the mechanism and observations support it. Coordinate work,
   isolation, production, charging, visits and failed interventions.
6. Qualify the workflow for site/design/lifecycle comparisons and uncertainty.
   Equipment-specific observations, logistics evidence and quotations remain a
   separate evidence programme; missing inputs stay visible.

Gate: every agreed family has an explicit implemented or evidence-restricted disposition;
a continuous deployment-to-maintenance example reconciles capacities, condition,
resources, costs and unresolved obligations. Unsupported realism is never filled in
with an arbitrary probability simply to complete the catalogue.

## Release 3 — comparative autonomy research platform

1. Provide reproducible training datasets, observation-only environments, training
   protocols, model/version registration and bounded policy deployment interfaces.
2. Start with learned estimators and planning aids, then evaluate scheduling and
   homeostatic approaches against the reference controllers. Preserve hard execution
   bounds, fallback and explicit objectives/reserves.
3. Separate training from held-out weather, equipment and plant configurations. Keep
   numerical repeats, scenario seeds and environmental samples distinct. Provide
   reports for failures, reversals and data/runtime cost, using small integration
   examples to verify the machinery. Users choose the research questions to execute.
4. Finish the unified Sites → design → operation → investigation → comparison →
   write-up workflow and complete service/lifecycle/learning explanations and lineage.
5. Qualify installation, runtime limits, resumption, old archives, offline recovery,
   artifact durability, performance and actual participant comprehension.

Gate: a fresh installation can execute the guided end-to-end demonstration, restore
its published study offline and make a new numerical edition with differences
reported. The agreed capabilities and limitations are understandable and traceable.
No requirement that every robot is useful or every learned policy wins.

## Parallel evidence programme

Prioritise observations that could change a structural conclusion: which device and
fault an action can address; independent sensor/reference quality; thermal response;
weather/soiling conversion; failure/degradation exposure; access, isolation and return;
crew/spares/CO2/water logistics; dated commercial inputs. Existing literature supplies
scoped priors and gaps. New measurements need identity, timing, coverage and uncertainty.
Sensitivity and independent numerical checks cannot substitute for empirical evidence.

## Release 2 implementation and evidence

Implementation contract: [release-2.md](release-2.md). Numerical findings, verified
scope, preservation receipts and the remaining evidence gaps belong to the
[Release-2 publication](../research/release-2/report.html). Six unsupported families
remain explicitly restricted; two construction families use declared assisted work
packages. This distinction is part of the release gate, not a claim of fourteen
calibrated robots.

Release 3 builds observation and estimator datasets over these contracts, retaining
the condition channel's limitations and low-excitation exclusions. It freezes
train/validation/test boundaries and compares fixed, adaptive and fitted estimates.
Registered planning aids and reserve hypotheses are available for matched experiments;
no result here establishes their general superiority. Data acquisition and actual
participant research remain necessary alongside the delivered software.

The [Release-3 delivery contract](release-3.md) makes the next sequence explicit:
freeze observation datasets and held-out boundaries; qualify estimators; register
bounded deployments; compare scheduling/reserve objectives; complete the user-facing
research workflow and participant work; then qualify fresh installation and recovery.
It is now implemented through the [learning and policy workflow](learning-and-policies.md).
Current qualification, source identities and remaining gates are recorded in the
[Release-3 report](../research/release-3/report.html). Chronological throughput,
storage and export budgets remain separate from interactive latency.

## After the Release 3 implementation

The platform now provides frozen datasets, fixed/adaptive/fitted estimator
comparisons, registered observation-only planning aids, soft reserve objectives,
matched study templates, original calculation traces and portable result editions.
More extensive policy/season/uncertainty studies are available for users to conduct;
they are not an unfinished release research queue.

The remaining external release gates are real participant walkthroughs, resolution
of any material misunderstandings, and a durable off-machine storage/restore
arrangement. The software supplies session capture and integrity-checked exports;
it cannot invent participant responses or a backup destination.

Subsequent engineering should be driven by those users and by evidence that changes
the mechanisms: better observed condition/reference channels, identifiable duration
models, additional reviewed estimator/policy adapters and—when justified—RL or
neuroscience-inspired training. The delivered reserve policy is a transparent
homeostatic planning hypothesis, not an RL-trained agent or field-qualified autonomy.

## Expert workflow roadmap — one increment at a time

The next product work makes the platform useful as an expert's working instrument
while retaining its approachable default view. Each increment returns to the user
with delivered scope, verification, limitations and the remaining sequence. Further
increments are not automatically started.

1. **Expert investigation workflow — implemented.** Select a recorded operating
   period, inspect its constraints and observations, pin evidence, calculate a
   targeted alternative, compare predictions and save an authored account with its
   source context. The [investigation contract](expert-investigation.md) records
   scope and limitations. Actual expert-participant walkthroughs remain outstanding;
   the completed software rehearsal is not a substitute for them.
2. **Shared control interface and MCP — implemented.** Give the UI, reference policies and
   external agents the same versioned observation/action contract. Start with
   bounded simulated-plant sessions: observe, inspect constraints, propose a plan,
   preview it, advance execution and trace the result. Make agent authority,
   allowed actions, budgets, cancellation and fallback visible. Preserve hard
   execution constraints and keep simulator truth outside agent observations.
   Expose recorded reasoning and actions in the existing plant/control views.
   This does not authorise connecting an agent to real plant hardware.
   The initial interface was bounded to hour-zero sessions. The current
   [control contract](agent-control.md) includes P1’s project, checkpoint and
   recorded-request replay extensions; external-agent re-inference remains distinct.
3. **Operating requirements and robust design comparisons — implemented.** Let an expert express
   production commitments, reserve/service requirements and acceptable shortfall,
   then compare site/design choices against them. Reveal bottlenecks, uncertainty,
   infeasibility and trade-offs beside the relevant equipment. Preserve starting
   assumptions and comparison boundaries; avoid a single unexplained ranking.
   The [operating brief contract](operating-requirements.md) defines production
   windows, reserve/service limits, incomplete outcomes, scenario coverage, original
   calculation links and portable assessment editions. Requirements assess outcomes;
   they do not silently change dispatch objectives or establish field feasibility.
4. **Equipment-specific planning for one deployment use case — implemented.** The
   [equipment planning contract](equipment-planning.md) provides a reviewed European
   PV–AEM reference, explicit model bindings and support gaps, immutable design/run
   applicability, commissioning review records and observed-versus-simulated hourly
   comparisons with original interval links and portable reports. The reference
   identifies Trina and Enapter specification editions; other equipment and support
   remain illustrative. No site observations are bundled and no calibration or
   field readiness is inferred. OEM interlocks, AC conversion, external cooling and
   gas conditioning are not added to the execution model by this evidence layer.

Across these increments, protect original evidence, responsive interaction,
keyboard/narrow-screen access, and reversible context-preserving navigation. Real
participant feedback and an off-machine storage/restore arrangement remain explicit
external gates. Broad research matrices remain user-run templates, not the product's
completion criterion.

### Historical modelling follow-ons (now closed or optional backlog)

The following records earlier work and proposals. The finite P1–P3 table above
is now authoritative; these proposals do not insert new release gates.

1. **Deployment integration model — implemented, evidence still bounded.** Optional
   [plant interfaces](plant-interfaces.md) connect AC conversion, external cooler/dryer
   and specified H₂ compression loads, declared feed-pressure compatibility and
   finite purified-water stocks to planning and execution. Design revisions, recorded
   calculations, cost incompleteness and disclosed uncertainty are accessible through
   Equipment & evidence. The reduced model does not establish actual cooling duty,
   gas/water quality, pressure dynamics or installation feasibility. Public
   specifications, experimental datasets and engineering derivations are the next
   modelling inputs; private OEM or site records are not a prerequisite.
2. **Research-grounded component models — first usable increment delivered.**
   [Researched conversion and thermal options](researched-models.md) now run in
   both planning and execution: a source-scoped part-load converter analogue,
   reference-state electrolysis heat, ambient-limited dry cooling, and NIST
   reaction heat with explicit cold-feed heating. Preview, design revisions,
   recorded operands, independent calculations and disclosed uncertainty choices
   are integrated. These equations do not establish field calibration.

   **Reference-device adapters are now delivered:** [Reference experiments](literature-models.md)
   executes the CSU PEM power/flow and KIT controlled-coolant response models from
   versioned, hash-identified data mappings. It exposes model forms, paired-parameter
   sensitivity, scoped evaluation, saved results and offline reports. These remain
   source-device experiments: startup, scale-up and plant transfer are not inferred.

   **Optional backlog:** explicit plant-compatible component options and transfer scenarios. Public
   evidence remains the primary modelling basis. Review the literature-derived
   reference profiles, then promote justified mechanisms into named, executable
   component options with explicit source conditions and applicability. Prioritise
   power/conversion boundaries, cooling and process dynamics. Reproduce measured
   behaviour of the published reference equipment before assessing transfer to the
   chosen plant; different technologies must not silently share fitted coefficients.
   Separate measurement, parameter, transfer and model-form uncertainty. Use
   engineering derivations and disclosed scenario ranges where observations are
   unavailable, retaining correlations and structural alternatives. Small held-out
   checks and sensitivity cases should justify each change; broad studies remain
   user-run templates. Completion means a useful, traceable research model with
   honest uncertainty, not qualification of an unobserved physical installation.

   The [qualification workflow](equipment-qualification.md) now freezes review
   criteria and development/evaluation windows, assesses exact recorded designs,
   exposes measurement boundaries and discrepancy traces, and preserves reports
   offline. Its exact-design observation importer is an optional site-comparison
   facility; it is not an adapter for arbitrary literature datasets. The separate reference
   workspace now supplies two named data mappings; additional devices need their
   own mappings and boundary reviews. The CSU PEM and KIT controlled-coolant fits remain scoped to those experiments;
   their coefficients have not been assigned to the AEM or generic reactor.
   Actual plant measurements can strengthen validation later, but are not expected
   or a completion gate for this software project.
3. **Rehearse the expert workflow with real participants.** Observe site selection,
   design changes, requirement assessment, evidence inspection, an alternative and
   a written account; simplify navigation where users misunderstand context.
4. **Practical agent operation.** This is now the fixed P1 increment above,
   documented in [agent-control.md](agent-control.md). Recorded-request replay is
   distinct from asking an external agent to infer again.
5. **Arrange durable storage and restore.** Local content-addressed records and
   bundles are delivered; off-machine retention, access and recovery require a chosen
   destination and a real restore drill. Local commits are not that backup.
