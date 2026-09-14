# Learning and experimental policies

Open **Sites → Production studies → Learning & policies**. The main simulation
and its drawings remain the starting view. Nothing is trained or dispatched by
opening this workspace.

## A complete short workflow

1. Run independent site/design episodes. In **Select observation episodes**, assign
   complete episodes to training, validation and test, then freeze the dataset.
   Overlapping site/weather windows cannot cross these boundaries. Optional axes
   require different sites, designs or equipment configurations as well. Scenario
   seeds and numerical repetitions remain separately recorded.
2. Inspect the saved packets and reconstruct the dataset from its original committed
   partitions. The export adapter has its own source capsule, separate from the
   original simulation source. Retrospective outcome labels use a separate raw object.
   Hidden physical parameter variations never replace the controller's known inputs.
3. Select a target and a declared ridge penalty. The isolated worker fits a small
   four-feature model using training means/scales. Fixed and adaptive baselines are
   evaluated on the same boundaries. Validation calibrates empirical absolute-error
   bands; test observations do not choose weights or widen applicability.
4. Read errors, coverage and unavailable cases together. Low solar excitation,
   absent channels, repeated stale condition readings and censored service clocks
   remain explicit. Use **Write up this evaluation** to author a report edition.
5. Register a named policy. **Record predictions only** leaves decisions unchanged.
   **Revise the first future PV prediction** changes forecast interval 1 only;
   contemporaneous interval 0 remains fixed. **Optimise reserve needs** adds soft
   battery, gas and thermal shortfall preferences to MPC. A model is optional for
   this last mode. Invalid, unsupported, out-of-domain or late inference keeps the
   original policy. Weights and training-source applicability are pinned.
6. Build a matched study/template. It includes Greedy, methane MPC and economic MPC,
   followed by the chosen experimental policies under both MPC objectives. Review
   its saved design/environment/seed before starting. It is a recipe, not a result.
7. Run, cancel and resume through the normal Sites study screen. Open a recorded
   interval and use **Model → Controllers → Trace this run** for the original
   registered policy input, feature operands, prediction, restriction and solver.
   Case totals expose policy fallbacks separately from production and actual cost.
8. Publish a write-up and build a reproduction ZIP. **New numerical repetition**
   creates a new study using the current application and the original frozen policy.
   **Compare with original edition** reports all differences in the declared physical,
   requested/applied and observation/diagnosis fields, plus missing hours and input
   changes. It does not compare solver search logs, elapsed timings or every audit
   operand. The complete original recordings remain available for those fields.

For a quick interface demonstration, **Try a constructed dataset** creates 72
fixed-seed observations across three separate fixture episodes. These are authored
meter signals, not results from an operating plant. For a mechanism lesson, Model
contains Observation datasets, Estimators and Experimental policies. Lesson edits
never modify an experiment.

## What the first learned models can establish

Targets are the next observed PV, solar/PEM condition or removable-surface channel,
and completed service phase duration relative to its nominal recipe. Condition and
soiling channels remain declared measurement assumptions; forecasting their next
readout does not independently identify irreversible degradation, fault cause or
remaining useful life. Duration regression pools completed normalised phase clocks;
it is not a survival estimator and cannot correct censoring bias. The existing
`methane.duration_calibration` path retains its persistent-equipment/job variation
and censored-clock likelihood for that different question.

The fitted estimator is deliberately inspectable ridge regression. There is no
neural-network, RL or general executable-plugin deployment in this release. The
observation and artifact contracts provide a boundary for subsequent algorithms;
an external algorithm must implement a reviewed adapter rather than gain direct
access to a simulator runtime. Field controllers and actuation are outside scope.

Operational PV deployment is limited to the recorded training feature and plant
capacity ranges. An unseen held-out plant can therefore legitimately fall back;
absence of applicability is an experimental result, not permission to extrapolate.
The scalar PV aid is currently unsupported in optical service planning, which
recomputes section forecasts. That combination explicitly falls back and reports
the reason. Homeostatic preferences continue through that planning interface.

## Objective and uncertainty boundaries

Reserve shortfalls saturate at zero once the target is met. Hot/committed reactors
have larger thermal and feedstock needs; recorded service demand adds battery need.
Shortage weights use the selected objective's units: methane equivalents or EUR.
They are preferences, not physical obligations, expenses or inventory sales.
Ownership allocation never becomes a dispatch reward. Compare production, actual
variable costs, starts/wear, trips, unresolved work, human interventions and ending
inventories. A mean predicted reserve penalty is not a sum of cash expenditures.

Robot energy reserves, finite spares/references, isolation and unfinished missions
remain with the existing service executive and explicitly selected maintenance
policy. The process reserve objective does not jointly purchase spares or optimise
construction capital. Compare these support choices as separate frozen designs.

Keep weather samples, random seeds, solver repetitions and policy choices distinct.
The broader adverse-forecast, support-loss, intervention-price and reserve-weight
studies are user-run template variations; no learned policy is required to win.
Empirical error bands and scenario ranges are not calibrated event probabilities.

## Resource and preservation contract

Heavy Sites numerical, dataset, training and export work share one OS-backed worker
lease per store. Solver calls consistently use one HiGHS thread, including the
legacy controller. Numerical/learning workers constrain BLAS threads to one.
Training/data jobs default to a 120-second wall budget; explicit jobs may request
1–600 seconds. CPU and wall limits remain active if the UI process exits. Cancellation
leaves original inputs and finished artifacts on disk; a retry is a new job edition.
The UI waits for worker exit before offering a completed result as released capacity.

Datasets accept at most 100,000 observations or 128 MiB of policy packets. Training
uses four features, with a 100,000-row admission cap. Each worker records maximum
RSS and elapsed time; these are measurements, not a hard address-space limit.
New jobs require at least 512 MiB free disk. Exports default to an 8 GiB uncompressed
input budget (explicit API bounds 1 MiB–64 GiB) and conservatively check available
disk against input size. ZIP members stream from saved files. Cancelled export
temporaries retain unique names; no ignored evidence is deleted. An existing ZIP
is reused only for the same inventory; a changed inventory needs a new publication.

Bundles include registered weights, protocols, datasets, permitted raw observations,
separate labels, source capsules and original study dependencies. Restricted or
missing inputs produce an explicit incomplete reproduction inventory. Offline HTML
remains readable. Restoring a bundle validates its members before writing anything;
it never executes downloaded source. Re-fitting needs the original locked source.

Local commits and ZIPs on this machine are not a durable backup. No off-machine
destination has been configured. Copy the complete required bundle/data inventory
to a user-selected durable store, then verify hashes and perform a restore there.

## Participant comprehension

The workspace provides a six-question session record for a mechanism, assumption,
decision trace, unconfirmed work, evidence boundary and context return. Preserve
participant words separately from facilitator interpretation. Mark agent rehearsals
as rehearsals. Material misunderstandings stay unresolved until a resolution is
recorded in a new immutable session. Automated browser checks do not satisfy this
participant gate. No actual participant sessions have been conducted by this task.
