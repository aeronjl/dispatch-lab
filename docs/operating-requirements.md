# Operating requirements and design comparisons

Open **Site · Build · Operate → Operate → Operating requirements**, or use
**Project tools → Operating requirements** while building. The plant illustration,
labels and default simulation remain unchanged.

A brief defines what an expert wants a design to achieve. Save it for the project,
then calculate operation as usual. Every new project study freezes the brief's
identity alongside its design, weather, controller and source version. Revision
never changes earlier runs. Remove a brief from future runs without deleting it.
Existing studies can also be assessed against a different brief, explicitly labelled
as retrospective. **These are outcome requirements, not new dispatch constraints
or promises of delivered product.** Reference policies keep their stated objectives.

## Accounting contract

`operating-requirements/1` defines optional limits; blank means not assessed, whereas
zero is an explicit limit. The author records a name and rationale.

- **Production:** methane mass per fixed 1–168-hour window, with an allowed shortfall
  per window. Windows begin at the declared assessment hour (default zero, including
  startup). The final partial window and its allowance are prorated. Overproduction
  elsewhere cannot offset a shortfall. Every window remains visible. The headline
  check uses the lowest absolute margin against target minus allowance.
- **Reserves:** minimum battery energy, hydrogen and CO₂ at every boundary, including
  the assessment start. Values are retrospective physical state, not observations
  available to a controller. An explicitly excluded startup does not erase its cost.
- **Continuity/service:** maximum forced-trip intervals, unserved dock energy and
  hours of observer-based recovery escalation, accumulated over assessed hours.
  Forced trips are the execution flag, not all time without production. Escalation
  is not a diagnosis of permanent failure. Missing channels remain unassessed;
  absence of incidents cannot demonstrate recovery capability.

Pass/fail comparisons allow `1e-7` in the stated unit for floating-point accounting.
A case with unavailable declared intervals is **incomplete**. A complete case with
any breached requirement is **unmet**; otherwise missing operands make it
**unassessed**, and only complete available checks produce **met**. Resource-only
studies are unassessed for operation. No missing evidence is replaced with zero.
Configured nameplate/capacity ceilings identify requirements that are impossible
within that model regardless of dispatch. Clearing those necessary bounds does
not establish coupled feasibility.

## Comparing designs under uncertainty

Choose one or more saved studies in **Compare**. The assessment includes all their
cases and freezes only the partitions committed at that moment. It does not run a
solver, fill unfinished cases later or mutate the study. To include subsequent
progress, create another assessment edition.

Groups retain design, controller, policy, source identity and comparison role.
The declared exposure universe is the union of selected calendar/reference/
forecast-information, seed, repetition and explicit uncertainty-world cells.
Coordinates and weather snapshot identities remain case-level inputs for site
comparisons. Calendar coverage does **not** prove identical weather information
across sites or snapshot revisions. Distinct uncertain worlds are conservatively
kept distinct; no matching of latent draws across designs is inferred. Missing
cells, incomplete cases and unreviewed search exclusions prevent an “all selected
requirements met” label.

Cost, methane and production-shortfall minima/maxima are unweighted ranges across
the selected cases. Counts remain visible. They are not confidence intervals,
annual extrapolations, a calibrated probability of success or an overall ranking.
Costs retain the original decision assumptions and whole-case allocation; ending
inventories are separate and receive no hypothetical liquidation value. Search
exclusions remain in the record. Users select additional uncertainty, seasonal and
numerical-repetition studies through existing experiment tools; this increment does
not run a research matrix automatically.

Each check shows its operands, margin and relevant equipment. **Inspect** opens the
original partition at the recorded hour/component. Original decision constraints
and predicted bindings supply context, explicitly distinct from retrospective
physical outcomes. They are not causal importance scores. Use the existing
investigation/alternative workflow to test a proposed explanation or design change.

## Preservation and execution

The Python adapter uses recorded application values; browser code only renders.
Assessment runs in the existing frozen-source worker with progress, cancellation,
a 120-second wall budget and the shared heavy-worker lease. Admission limits are
24 studies, 192 cases and 100,000 recorded intervals. An active heavy study may
occupy that lease; the UI surfaces the resource conflict rather than queueing
unbounded work. Closing the workspace does not cancel a job. Its saved result is
available from the assessment list; returning in the same view resumes polling.
Cancellation or a time limit does not produce a successful assessment.

`operating-assessment/1` stores the brief, case/source/config/weather identities,
committed period references, checks, windows, comparison coverage and assessment
implementation/source capsule. Numerical repetitions/templates carry the frozen
brief forward. Older archives need no migration.

**Write up & export** saves an authored HTML edition with readable checks and its
complete calculation record. The reproduction bundle includes both the brief and
assessment, original studies and permitted source/period data, plus the assessment
source capsule. Existing redistribution restrictions and integrity checks still
apply. A restored report is readable offline without changing the source evidence.

## Verification boundary

Independent arithmetic examples cover shortfall, prorating, boundary reserves,
startup exclusions, service totals, first crossings, invalid inputs and incomplete
information. Integration checks cover frozen pre-completion snapshots, revisions,
actual execution, component replay links and offline bundle restoration. Browser
checks exercise save → run → assess → inspect, authored reports, export, error
states, narrow screens and return focus. Original project and plant/solar checks
remain authoritative; screenshot baselines are not updated.

These checks establish software accounting and workflow behavior, not field
calibration, equipment capability or expert comprehension. A participant walkthrough
and equipment-specific evidence remain separate work.

### Increment verification — 16 September 2026

- 67 Python checks passed: requirements, projects, Sites execution/reporting and
  learning-workflow regressions. One existing Rasterio deprecation warning.
- 96 JavaScript checks passed.
- 19 browser checks passed across requirements, project and platform workflows,
  including the unchanged reviewed plant and solar PNG references and project
  preview performance gate. Three explicit fixture-gated checks were skipped:
  newer-archive cost lineage, the platform offline playback fixture and first-entry
  project mode. The new assessment bundle's offline restoration was checked in Python.
- Ruff, formatting and generated-component documentation freshness passed.
- Desktop and narrow-screen assessment screenshots were visually reviewed in
  `build/requirements-comparison.png` and `build/requirements-mobile.png`.

This is scoped increment verification, not a rerun of every historical acceptance
study or an expert-participant walkthrough. No screenshot baseline was changed.
