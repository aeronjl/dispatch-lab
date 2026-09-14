# Release 3: comparative autonomy research platform

Status: not started. Release 2 must finish its source-bound qualification gates
before this programme starts. The [roadmap](roadmap.md) remains the scope authority;
this document makes its sequence and acceptance criteria explicit.

Completion means delivering the machinery users need to train, evaluate and compare
policies. Verify it with small, named acceptance examples. Large training campaigns,
policy/season sweeps and claims of superior control are optional studies run using
the platform; they are not release gates. This supersedes any reading of the gates
below as requiring an exhaustive research programme. Participant work requires real
participants and must remain explicitly outstanding until they take part.

## 1. Observation datasets and frozen evaluation boundaries

Build datasets from recorded decisions, eligible forecasts, actions, service reports,
condition readings, prices and their original identities. Keep retrospective truth
in a separate scoring/label store. Each record identifies availability time, missing
channels, measurement/reference assumptions, plant design, environment and source.

Split whole episodes/sites/weather windows and equipment assumptions before training.
Do not divide adjacent hours from the same episode randomly between training and
held-out evaluation. Hold out plant capacities and support configurations as well
as weather. Distinguish scenario seeds, weather samples and numerical solver repeats.
Register training inputs, labels, transformations, exclusions, costs and random seeds.
Synthetic labels remain synthetic; data volume does not turn them into field evidence.

Gate: changing a future observation, private outcome or forecast publication cannot
change an earlier policy input. A dataset can be reconstructed from its saved sources,
and the held-out registry has no episode overlap with the training registry.

## 2. Estimators before learned scheduling

Start with fixed and simple adaptive baselines for condition, removable soiling and
service duration. Compare a learned estimator only where the observation interface
can identify the quantity. Include low-load ambiguity, shared references, missing
communications, drift and unsuccessful procedures. Evaluate calibration and intervals
alongside point error, detection delay and the operating consequences of the estimate.

Release-2 observations are assumed measurement channels. They do not establish that
an installed sensor can independently identify irreversible degradation, distinguish
a specific cause of a shortfall, or predict remaining useful life. Keep unsupported
inferences unavailable. Begin with bounded hypotheses that can be independently checked.

Gate: a held-out comparison explains when the estimator improves decisions, when it
fails and when the available information cannot distinguish competing states. Report
required observations and compute/data cost; improvement is not required for publication.

## 3. Versioned policy deployment and containment

Add an observation-only policy interface and registered estimator/planning-aid artifacts.
A deployment pins model weights, training dataset/protocol, preprocessing, interfaces,
plant applicability, execution budget and fallback. Loading a new model is an explicit
experiment change, never a silent update to a completed run or interactive playback.

Keep electrical/material/thermal limits and service prerequisites in the execution
kernels. Record proposed actions, any applied restriction, model failures and fallback.
Timeout, unavailable features, out-of-domain inputs and invalid predictions must leave
a feasible, inspectable operating decision. Do not add a real-plant actuation interface.

Gate: model errors and missing observations cannot bypass the existing physical bounds
or grant a restricted hardware capability. Old model artifacts and source environments
remain restorable, with numerical differences reported on a new edition.

## 4. Scheduling and homeostatic reserves

Compare learned planning aids and scheduling policies against Greedy, methane MPC,
economic MPC and the declared maintenance rules. Keep identical starting information
and exposure scenarios. The forecast-window maintenance rule is a heuristic; process
economic MPC does not jointly optimise construction capital or replacement thresholds.
A richer policy must be compared with an appropriate simple alternative.

Use explicit objectives rather than one unexplained reward:

- Hard feasibility: plant limits, isolation, compatible support and finite resources.
- Production and controllable economics: methane and assumed contribution under frozen
  dispatch prices, with starts, usage wear, feedstock, interventions and human effort.
  Fixed ownership allocation remains outside the dispatch incentive.
- Continuation and reserves: energy, feedstock, thermal state, service energy, reference
  availability, spare stock and unfinished work, conditional on mode and uncertainty.
  Ending inventory is reported without invented sale proceeds. Excess hoarding also
  has an opportunity cost.
- Reliability and intervention burden: unconfirmed recovery, failed attempts, downtime,
  constraint-triggered trips, unresolved obligations and human escalation.

A homeostatic policy can treat reserves as needs that depend on the operating mode;
it must not override safety bounds or hide trade-offs behind a universal trust score.
Publish a range of objective/reserve choices and their consequences. Test adverse
forecast errors, correlated support losses, rare conditions and expensive interventions.

Gate: all policies share the same causal interface and execution restrictions. Report
successes, failures, reversals, fallback, sensitivity and where extra complexity adds
no value. Do not require a learned controller to outperform a simpler one.

## 5. User-facing studies and comprehension

Complete Sites → design → operation → investigation → comparison → write-up for
registered policies. Keep original recordings, repricing and new numerical editions
separate. Extend Model with dataset, estimator and policy explanations that state
applicability, observation requirements and uncertainty. Results link to their operands,
source, model and original forecast; provenance is not reconstructed when missing.

Run actual participant walkthroughs: explain a mechanism, identify an assumption,
trace a decision, recognise unconfirmed work and limited evidence, and return to the
originating simulation context. Preserve their words and misunderstandings separately
from automated test outcomes. The Release-2 walkthrough is agent-authored only.

Gate: address material confusion between observations, estimates, predictions and
retrospective truth before calling the research workflow complete.

## 6. Final operational qualification

From a fresh locked installation, execute a guided end-to-end study, interrupt and
resume it, restore its publication offline and produce a new numerical edition with
all differences reported. Qualify old archives, model applicability, unavailable data,
worker cancellation, runtime/memory/disk budgets and durable artifact preservation.
Give numerical, training and export jobs explicit resource/concurrency budgets so
they cannot starve the interactive service. Keep simple interaction targets separate
from numerical study throughput; a fast slider
does not establish that a continuous lifecycle study scales to years.

Gate: a reproducible release demonstrates the complete workflow, including unsuccessful
and incomplete cases. Local commits remain separate from a backup of ignored weather,
source capsules, numerical recordings and portable bundles. Document storage/export
costs and the user's durable storage arrangement rather than silently deleting evidence.

## Parallel evidence work

Review the lumped whole-asset replacement and condition-observation abstractions
before treating a maintenance-policy comparison as a field recommendation. Test
durations are not established feasible ranges. Where the actual service unit is a
module population or a different bounded procedure, change the mechanism and create
a new comparison edition.

Seek equipment-specific capability/isolation evidence, independent condition/reference
observations, thermal response, degradation exposure, service and return durations,
site access, crew/spare/CO2/water logistics and dated quotations. Prefer evidence that
could invalidate a mechanism or reverse a decision. Literature priors, sensitivity
ranges and successful numerical checks cannot replace these observations.

Field validation, gas-quality acceptance, pressure-system design, safety certification,
live plant control and DePIN payments remain outside this software release.
