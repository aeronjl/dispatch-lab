# Repeatable studies

Open **Simulation menu → Studies** to read a comparison, inspect a case, trace its methane or battery result, and open its recorded playback. **Return to study** restores the originating report revision. Battery, controller, weather and experiment essays in Model also link to Studies. Opening either workspace pauses playback.

The first protocol asks **What is tomorrow’s battery energy worth?** It compares methane MPC with the same optimization given a terminal battery value of 0.01 kg CH₄-equivalent per kWh. This is an illustrative continuation assumption, not produced methane, revenue or a hard reserve requirement. Both controllers use the same starting information, weather and observation noise channels. Physical execution and fallback remain unchanged.

## Protocol, edition, attempt and publication

- A **protocol** is an authored, versioned question with fixed policies, scenario matrix, scaling rules, metrics and limits. The complete reference fixture lives in `docs/studies/battery-reserves-v4.json` (revisions 2 and 3 are retained unchanged). Changing the research question or tuning the policy requires a new protocol revision.
- An **edition** freezes the protocol, all resolved configurations, saved weather, source capsule, dependency versions and lock. Changing plant parameters creates a new edition; a complete configuration never inherits later application defaults.
- An **attempt** records an execution, including incomplete, cancelled, invalid or failed cases. A resume reuses only a verified complete result; a fresh trial records another execution. Each archive has an independent balance-check artifact. Time-limited solvers can produce different valid decisions with identical numerical inputs.
- A **publication** is an immutable report revision referencing exact attempts. Its generated numerical findings and explicitly authored method remain distinct from a causal interpretation. Earlier reports and attempts are retained when a study resumes.

An author can attach an interpretation through `publish_interpretation(edition_id, report_id, paragraphs, reviewer)`. This creates a new publication bound to the selected report’s exact attempts, leaving its numerical findings intact. The UI and portable report show the attribution and scope. A subsequent fresh trial or resume does not automatically inherit that interpretation.

The reference edition contains twelve matched cases: normal and overestimated forecasts, three fixed seeds, two battery capacities and 72 hours per controller trace. Smoke is a workflow check; sensitivity widens the battery range. Battery capacity scales while absolute charge/discharge power stays fixed; starting SOC fraction stays fixed. Gas starting inventories, reactor assumptions and delivery quantities stay absolute. Ending battery, gas and temperature are reported separately from methane production.

**Repeat on active plant** takes the saved plant, costs, sensor settings and implementation choices from the active run. The protocol supplies its synthetic weather, scenario horizon, seeds and solver budget. Preview shows resolved capacities and power before execution; the report exposes every input and difference. It does not edit experiment setup.

Older archives can omit implementation identifiers or the random-number policy. The preview labels fields supplied by the existing compatibility loader. The edition retains those additions, the original configuration hash and the originating run identifier; it does not rewrite the old archive.

**Reproduce this edition** creates a new edition from the original source capsule and weather bytes, even after this app changes. Dependency versions must match; otherwise execution visibly fails with restoration instructions. A numerical comparison records changed actions and output; recorded playback simply renders the saved values. Source hashes establish content identity, not authenticity or empirical calibration.

## Execution and preservation

The controller policy interface is `methane/policy.py`. Teaching and normal dispatch retain their existing policies. Study terminal values are recorded per decision, preserved in what-if replanning and numerical reproduction, and excluded from physical output and economic cost reports.

`methane/studies.py` owns resolution, persistence, execution, publication and export. `methane/study_service.py` exposes capability-scoped operations. The browser renders Python-calculated results and uses request generations to reject superseded responses. Reports selected from history stay pinned while a later attempt runs. Source playback links carry the original attempt and publication identities.

A subprocess executes the frozen source, using one numerical thread and reduced scheduling priority. An inherited operating-system lock permits one study worker per store and releases after a crash. Cancellation retains the completed prefix and labels remaining cases. The worker can outlive an app restart; progress remains visible. A frozen study may resume with its original implementation, so improvements to the current study engine do not silently rewrite its execution semantics.

The default store is `runs/studies/`; `DISPATCH_STUDY_STORE` selects an isolated store for integration tests. Manifests, reports and case entries are integrity checked. Progress and the worker lease are operational files, not immutable evidence. A reproduction bundle includes all attempts and publications, exact source and locks, readable HTML/Markdown, offline playback and model reports. It includes no external dependency on a tracking service.

The [repeated computation protocol](computation-qualification.md) declares repeated executions of unchanged seeds at separate process, service and investigation budgets. Its qualification table keeps numerical repeatability separate from solver termination and preserves the original evidence. Repetitions are never counted as additional environmental samples.

## Command line

```sh
.venv/bin/python -m methane.studies create --tier reference
.venv/bin/python -m methane.studies run EDITION_ID
.venv/bin/python -m methane.studies run EDITION_ID --fresh
.venv/bin/python -m methane.studies reproduce EDITION_ID
```

Use `create --config complete-config.json` for another plant basis, or `--root PATH` before the subcommand for a separate store. Download a bundle through Studies. After extraction, `python -I -S check_study.py .` checks integrity and independent numerical balances using only the standard library. Follow its README to restore locked dependencies and create a new numerical reproduction. Offline installation requires cached packages.

Large publications use [small display projections and on-demand original service records](study-presentation.md). Published figures and ending inventories are copied from the saved report; selecting a detailed record checks its original case, attempt and publication. Full original files remain linked in offline reports.

## Scope of the first finding

Report complete and incomplete cases, paired differences, raw production and ending inventories. No test requires the reserve policy to win. Three seeds describe the fixed sample; they do not establish population confidence or real-plant safety. The first protocol tests one terminal-value mechanism under forecast error. It does not implement robust MPC, a viability guarantee, learned policies, or new fault recovery. Longer windows, terminal-state sensitivity and solver-budget sensitivity are necessary before treating a finite-window advantage as an operational recommendation.

Revision 1 was withdrawn after discovering that sorted JSON keys reversed the signed comparison. Its physical traces and original publications remain retained with a withdrawal notice. Revision 2 identifies baseline and candidate explicitly; a regression test permutes dictionary order and checks the differences against named operands.
