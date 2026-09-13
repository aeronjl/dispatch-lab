# Field operations: realism gate

Status: initial review **performed on 12 September 2026; credibility gate remains open**. See the [review report](../research/field-realism-review/report.html), [31-assumption register](../research/field-realism-review/assumptions.json), [14-family matrix](../research/field-realism-review/capabilities.json) and [scoped decision](../research/field-realism-review/review-decision.json). Conditional mechanism comparisons may proceed; real autonomous-repair, fleet-selection and European ROI claims require capability, metrology, site and support evidence. The wider programme remains paused. No production assumptions, capabilities, old archives or artwork were changed.

Repeatability establishes that a result can be reproduced under its recorded assumptions. Independent numerical checks establish particular properties of the implemented mechanism. Neither establishes that the mechanism, assumed work or maintenance problem represents a real installation.

The review used the existing fixture and European sites as requested. It retained 128 numerical executions: 112 comparison cases and 16 transparently superseded portable-cleaning setup cases. Independent audits and 101 targeted tests passed, without establishing empirical realism. The next substantive decision, before implementation resumes, is to bind specific fault causes, observations and permissible remedies, including a credible human local-reset baseline. Each hardware family must subsequently pass a more detailed, version-bound review as it enters stage 5.

## Scope

| Review | Required coverage |
|---|---|
| First complete service system | Cleaning, inspection, bounded recovery, human intervention and shared support: compatible work, restrictions, durations, energy, observation quality, failure mechanisms, docks, tools, communications, operator assistance, spares, references, replenishment and retrieval |
| Plant and site that determine service value | Fault types and frequency, degradation and exposure, production bottlenecks, thermal/material constraints, isolation and return-to-service requirements, environmental conditions, access and logistics |
| Initial feasibility of all 14 families | A specific plausible task and target, evidence for that capability, operating prerequisites, observable effects, support burden, failure boundaries and unresolved evidence gaps; no family passes through a catalogue description alone |

The 14 entries are dedicated row cleaner, portable wet/dry cleaner, ground inspector, aerial inspector, contact crawler, vegetation-management robot, sampling/analyzer station, sensor service station, fixed sensor package, remote actuator/redundant path, maintenance manipulator, replaceable module, solar construction robot and deployable array. Preserve their identifiers from the [dated research catalogue](../research/field-robotics/catalogue.json).

## Review capability before tuning parameters

For every consequential action, identify **the asset, target interface, fault or condition, procedure, prerequisites, permitted effect and verification method**. “Robot repair” is not a sufficiently specific capability. Distinguish an observation, a reset, calibration, replacement and a repair procedure. A successful command or completed work order is not evidence of physical restoration.

Use separate judgements:

- **Capability:** supported within a stated operating envelope; conditional on explicit prerequisites; speculative; unsupported; or unknown.
- **Parameter:** measured or documented for that envelope; transferred from an analogue with a stated justification; defensible range; or evidence gap.
- **Evidence:** which assertion a source supports, its tested conditions and limitations. A source establishing that a product exists does not establish its repair repertoire, field reliability, autonomy or the fixture's numerical values.

Unsupported or unknown capabilities remain unavailable in comparisons presented as credible operational options. Speculative capabilities may appear only in explicitly separate future-capability experiments, with the enabling design change and its costs/support requirements visible. A low success probability must not be used to disguise a capability that has not been established.

An evidence gap may justify an unanswered question or a conditional threshold study. It does not, by being documented, permit an unconditional deployment, autonomy or economic conclusion.

## Assumption and evidence register

Create a versioned register before changing defaults. Each entry must include:

| Field | Purpose |
|---|---|
| Stable assumption ID and exact claim | Identify what is asserted; distinguish a capability claim from a quantitative input |
| Applicable asset, task, fault, interface and model version | Prevent transferring evidence between incompatible systems or silently applying it to old runs |
| Configuration/implementation binding and units | Locate the actual mechanism or value being reviewed, including legacy variants |
| Current assumption and role | State whether it affects feasibility, observations, restoration, scheduling, fault exposure, costs or reported conclusions |
| Source and scope | Citation, date, relevant passage/data, conditions, measurement method, sample/denominator where available, and whether this is independent evidence, supplier documentation or an analogy |
| Range or explicit gap | Explain bounds and their basis; do not present arbitrary scenario limits as confidence intervals |
| Dependencies and exclusions | Identify shared causes, prerequisites, unavailable conditions and omitted behaviour |
| Consequence if wrong | Identify which comparison could reverse or become invalid; prioritise structural capability and information errors |
| Independent checks | Assertion, reference calculation or external comparison, tolerance and result; keep numerical verification separate from empirical validation |
| Review outcome and invalidation | Reviewer/date, applicable identities, permitted use, unresolved question and changes requiring another review |

Existing research, including its [source inventory](../research/field-robotics/sources.json), is a starting point for locating evidence. It is not a completed contemporary review. Retrieve the relevant primary material, evaluate its applicability to the specific plant/task and preserve the supporting evidence before changing the register's review status. Do not infer quantitative support from a source title, search snippet or manufacturer category.

For observation claims, include what the sensor physically observes, the hypotheses it can distinguish under informative operation, delay, detection limits, error structure, drift/dropout and common-mode dependencies. Preserve uncertainty when those relationships are unestablished. Simulated fault truth must remain outside the controller's information.

For repair and support claims, include preparation, isolation, access, tool/reference compatibility, actual intervention, acceptance tests, return travel and replenishment. Distinguish autonomous execution from remote supervision and site attendance. Review the support hardware's own failure and maintenance needs.

For plant claims, separate illustrative fault injections from evidence about event frequency or lifetime. Review the fault-to-production mapping as well as the probability of the fault. A severity or bottleneck assumption can dominate service value even if the robot assumptions are credible. Hourly dispatch and schematic routes do not establish emergency-response, pressure-system or navigation fidelity.

## Sensitivity and independent checks

First screen structural alternatives: whether a task is possible, which observations are informative, which isolation is required, and whether recovery needs a human or prepared interface. Then vary numerical inputs within evidence-backed bounds. Where bounds are unavailable, report break-even thresholds and the missing evidence; do not call the sampled region a plausible range without justification.

Use joint scenarios when inputs share causes or prerequisites. Examples to investigate include weather that both changes production and prevents access, or an intervention whose duration changes with the fault and required isolation. Preserve matched exogenous inputs; for degradation-driven failures, match the underlying exposure/randomness assumptions while allowing policies to change failure timing.

The study plan must be fixed before reading the ranking. Retain no-intervention, human-service and relevant fixed-automation baselines under the same maintenance problem. Report production, ending inventories, unresolved work, human visits and remote time, service/resource expenditure and allocated costs. Include service failure and incomplete execution. Check longer windows and end obligations so postponing work cannot manufacture apparent savings.

Independent checks must cover applicable physical/resource balances, service timing, compatibility, observation availability, isolation and recovery conditions, and economic reconciliation. A separate implementation of the same unsupported premise can verify arithmetic but cannot validate the premise.

Publish which conclusions remain unchanged within the supported envelope, which reverse, the reversal thresholds, and which cannot be answered. Stability of a ranking is not itself mandatory: a defensible finding may be that the preferred option depends on site or hardware design. Separate numerical noise/solver limitations from sensitivity to assumptions.

## Acceptance and release decision

The gate produces four reviewable artifacts:

1. A capability/condition/support matrix covering the first service system and all 14 families, with explicit unavailable and speculative entries.
2. A consequence-ranked register linking hardware, observation and plant assumptions to sources, justified ranges or gaps.
3. Independently checked, reproducible sensitivity studies and a user-facing interpretation of robust, reversed and unresolved conclusions.
4. A scoped decision stating which model configurations and claims may proceed, which require changed boundaries, and which remain blocked by evidence gaps.

“Realistic enough to proceed” requires all four for the proposed next use. It applies to stated configurations and questions, not the whole platform. A family with unresolved capability prerequisites cannot pass because unrelated components were verified. No overall realism or trust score combines these judgements.

If evidence changes the available action set, observation model, necessary plant design or main comparison, stop for user guidance before further implementation. Updating a supported duration within its range is a routine parameter revision; discovering that an assumed procedure is unavailable is a change in the problem being compared.

Preserve existing archives and their original claims. Corrections create new configurations, source versions and study editions. Prior results can remain reproducible yet lose applicability; record that distinction without rewriting their historical evidence. More detail, more tests and more repeated runs do not satisfy this gate by themselves.
