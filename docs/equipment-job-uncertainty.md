# Equipment effects and job variation

Service autonomy version 2 is opt-in in Studies → uncertainty → Service duration
model, or through a saved uncertainty specification. Version 1 retains its
piecewise-uniform population fit. Existing archives are not migrated.

Version 2 models a duration as nominal recipe time × persistent equipment factor
× job multiplier. The persistent factor belongs to a declared finite grid. Each
equipment/clock group has its own posterior. The current illustrative execution
fixture uses the configured group factor for each installed asset in that group;
it does not pretend that a measured distribution of equipment has been supplied.
Within an accepted job, the same multiplier applies to correlated phases in one
group, including outward and return travel. New jobs draw independent bounded
uniform multipliers. The accepted target/action/request index and event seed
identify each draw. Candidate evaluation and rejected requests consume no draws.

Full product support must fit the public resource reservation bounds. Hidden
persistent values outside the declared grid are rejected. The controller sees
elapsed/completed phase clocks, equipment identities and declared assumptions,
never the realised multiplier or persistent factor. Those operands are stored
only as retrospective truth. An independent standard-library checker regenerates
the draws and checks resulting energy, time and posterior arithmetic.

Completed and censored phases of one job/group contribute one likelihood.
Repeated censoring packets replace earlier packets. A completed outward journey
informs the same job's return clock; an unfinished job conditions remaining time
without counting its survival evidence twice. New-job predictions marginalise a
fresh job multiplier. Out-of-support evidence is visible and prevents an adaptive
model-based candidate from claiming feasibility. The existing feasible fallback
remains available. A finite grid is a modelling approximation, not a certified
uncertainty bound or proof of equipment reliability.

## Observation-based model selection

`python -m methane.duration_calibration protocol.json new-result.json` evaluates
declared candidate models against a versioned observation dataset. The protocol
contains `dataset`, `candidates`, `cutoff` and `bounds`. Datasets identify their
source as `field-observation` or `simulated-observation`, reference the original
artifact, and retain equipment/job/phase IDs, nominal and elapsed hours,
start/completion/availability times and censoring. Names must be globally unique
within the dataset; prefix them with run/site/equipment identities when joining
separate records.

Candidate selection uses marginal training evidence with a persistent factor
integrated once per equipment/group. Only packets available at the cutoff enter
fitting. Later, newly started jobs are held out: their predictive densities or
survival probabilities, 90% predictive intervals, coverage and support failures
are reported separately. Later phases of a training job cannot become an
independent held-out trial. Existing result files cannot be overwritten.

Few repeated jobs, a misspecified nominal recipe, selective dispatch and
unobserved environmental covariates can make equipment and job variability hard
to distinguish. The report flags groups with fewer than three training jobs;
this is a screening flag, not an identifiability theorem. No matched field clock
dataset has been supplied. Simulated observation experiments qualify the fitting
workflow; they do not calibrate the real service system.

## The null comparison

A nominal-only model requires all time factors and forecast multipliers to be
one, no mission interruption probability and no additional terminal constraint.
All modes reuse the validated nominal candidate, including any separately
declared recovery outcome tree. There is no redundant second time-limited solve
over duplicate duration branches. This removes a confound; it does not guarantee
bitwise repeatability between separate time-limited solver invocations. Historical
“no-op” studies that retained mission-failure uncertainty keep their original
meaning and are not relabelled as uncertainty-free.
