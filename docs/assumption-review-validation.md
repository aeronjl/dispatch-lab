# Assumption evidence review — validation record

Reviewed 12 September 2026. Scope: a platform-wide configuration inventory and consequential mechanism/evidence pass for the illustrative plant and existing European sites. This does not close the empirical calibration gate.

## Delivered

- `docs/assumption-review.json`: 407 canonical parameter paths, seven classifications, 19 authored mechanism groups, primary references, applicability limits, explicit gaps, measurement plans and labelled sensitivity values. Repeated object values remain lists. Optional reference blocks do not become configured equipment.
- `methane/assumptions.py`: read-only registry, current/recorded values, source-bound review status, changed-default and missing-field gates. Unknown runtime paths are reported, not auto-approved.
- Component explorer: Assumptions → mechanism → parameter; source, bounds and evidence are progressively revealed. Current Model essays include the scoped review. Original plant art and labels are unchanged.
- New catalogue snapshots retain the review once per run; offline catalogue exports remain readable. Older catalogue snapshots explicitly lack original review; current interpretation requires a labelled context switch.
- `research/model-assumptions/report.html`: complete user-facing findings, conditional results, all 14 retained hardware-family boundaries, sources and evidence-acquisition priorities. Existing reports/archives were not migrated.

## Executed validation

- 76 tests for assumptions, taxonomy, batteries, components, sensing and offline Model preservation passed.
- 162 additional tests for plant/reference accounting, economics, surface treatment, inspection, hardware/procedures, verification and archive transport passed.
- 8 JavaScript tests passed, including exact preservation of plant SVG elements/labels.
- Browser checks passed for desktop/narrow parameter views, keyboard operation, return focus, nested Model navigation, stale-response rejection, errors, offline report/archived review and original plant/solar screenshot comparisons. The older coupled-service optional test was skipped without its fixture; a new archived-review fixture was tested offline separately.
- New two-hour reproduction: independent dependency-free checker passed 114 assertions, bundle integrity and source capture; artifact under `build/assumptions/offline`, result in `research/model-assumptions/offline-check.json`.
- Backend complete catalogue response p95 6.85 ms across 30 in-process samples. This is not an end-to-end rendering or active-batch performance claim.
- Changed files pass lint/format and documentation freshness. The repository-wide lint run also found pre-existing issues in the earlier `research/field-realism-review` scripts; those historical research files were left untouched.

## Numerical evidence

Initial registered matrix: five joint profiles × three seeds × three strategies = 45 trajectories. A recorded exploratory amendment varies cooling time constants separately: two profiles × three seeds × three strategies = 18 more. All 21 run groups completed and passed the independent archive audit. The two editions have identical bound scientific implementation files; full source identities differ and remain recorded. Three seeds and time-limited optimization do not establish general policy dominance.

The first joint matrix scaled C and UA proportionally; it did not vary C/UA. This limitation prompted the explicit amendment. No original case was replaced. The original initial-matrix helper accidentally read a nonexistent decision-level solver field in its summary; published analysis instead reads the authoritative saved run metrics and retains actual limited-solve/fallback counts. Physical records and original summaries are preserved. The runner was corrected for later editions.

384 thermal helper cases match independent differential-equation integration within 1e-7 K (maximum error approximately 1.08e-10 K). These include deliberately out-of-band inputs and do not prove feasible dispatch. NIST-based reference chemistry quantifies rounded-mass approximations. Low-flow sensor and implicit PV-cap counterexamples are documented, not silently fixed.

All nine cached ten-day European windows loaded offline. Forecast-vs-reanalysis error is explicitly not error against measured generation. Missing wind/rain channels prevent site-specific cleaning-weather conclusions. Eighty-one fixed-trace price combinations preserve physical-trace hashes; they are repricing, not rerun optimization.

## Limits and next gate

No matched equipment/site measurement series exists in the supplied project. No fitted plant parameter or empirical uncertainty interval was invented. The next priority is a coherent equipment boundary and corrected observation model, then reactor/electrolyser calibration with independent validation. Cause-specific repair capability, real service exposure and supplier support remain prerequisites for field-economics claims. The earlier six-stage programme and study queue remain paused.

The existing experiments essay was read against the additive documentation change: teaching schedules, numerical calculations and archive meanings remain unchanged. Only its affected narrative binding/example was refreshed; other reviews were not blindly reapproved.

## Bounded service clocks, 13 September 2026

Reviewed the six added phase-family multipliers as unmeasured equipment assumptions (413 registered parameters). One factor persists through a world; the duration fit is an illustrative belief model, not new measured population evidence. Checked reservation versus actual-consumption semantics, independent phase clocks, grouped censoring, explicit support status and observed-surface boundaries. Existing quantitative evidence claims and reference defaults remain unchanged. Mechanism bindings renewed after this implementation review; probability calibration remains an evidence gap.
