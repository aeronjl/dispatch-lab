# Matched field-operation studies

Studies now supports separate hardware/configuration arms alongside the existing battery-reserve comparison. Open Simulation menu → Studies, then Run a study to select the question and its declared execution size. The first question is **When can a service system restore production?** Its complete protocol is [field-recovery-v1.json](studies/field-recovery-v1.json). Original battery protocols, editions and publications retain their existing meanings.

## Comparison contract

`dispatch-lab/study-protocol/2` selects the `matched-field-workflow/1` resolver. Each condition, plant variant and seed creates one matched group; every hardware arm has a separate configuration, physical run and archive. The protocol freezes complete controller policies, environmental assumptions, field hardware, finite logistics and service prices. The active-plant basis supplies plant parameters, component implementations, process sensors, solar configuration and production costs. It does not silently replace the protocol's service package. Every difference from the selected basis is saved before execution.

Arm patches may change service configuration, hardware and service economics, but cannot change shared plant, weather, process-fault, sensor-noise or optical-environment inputs. The resolver rejects unknown paths, incomplete policies, duplicate identifiers, unmatched environmental mechanisms and invalid configurations. The saved weather hash must also match within a group before a numerical difference is reported. Conditions and variants remain separate in aggregation.

A physically complete pair may still lack an applicable price. Monetary differences then remain undefined, with available-pair counts for each metric. Incomplete, failed, cancelled and withdrawn cases remain visible and do not become invented zero outcomes. Three-seed means and observed ranges are descriptive, not confidence intervals.

## First reference edition

The 72-hour reference has four packages (diagnosis only, fixed reader/reset, human service and rover-assisted service), four conditions (normal, latched trip, permanent module damage and flow-sensor bias), and seeds 7, 19 and 31. All packages share Greedy process dispatch and the same section-optical environmental-loss model; none cleans in this question. Reader/reset capability is a prepared contact interface, not arbitrary visual diagnosis. The rover cannot mechanically replace a module in this edition.

- Edition: `fa16440b7a984f999dd9659c59ab55aa`.
- Generated report: `0dd5085d58ee46b781c547ca856a254f`.
- [Authored write-up](../runs/studies/fa16440b7a984f999dd9659c59ab55aa/reports/fce9ebd27fcc48b3b4ce2a5c07c81e72.html): `fce9ebd27fcc48b3b4ce2a5c07c81e72`.
- Execution source: `4261f417f459ab14cf847082f6ee4a4df3c0b0e49e501ab8b6fbe288dd9fb261`.
- [Portable study bundle](../build/services/field-studies/reference-study.zip), with all attempts, source, prices, reports, recorded playback and offline model reports.
- Numerical reproduction: `c16556920ad448aeacd1616cddce3ab3`, using the original frozen source and inputs. All 48 cases reproduce the same applied actions and methane totals for all 72 intervals. This equality does not establish identical solver timings or universal numerical determinism.

All 48 original cases completed and passed their independent audits (446,380 scoped checks). The extracted portable bundle also passed its standard-library integrity and independent-archive checks without external dependencies. These checks establish the declared numerical/resource relationships, not calibrated hardware reliability or authenticated field observations.

The fixed reader/reset package improves the modelled latch cases with less allocated cost than the rover package. A reset cannot cure permanent damage; the rover package still needs a human module intervention. Some attempted interventions fail. Successful sensor calibration adds no methane in these cases because the independent balance estimate already supports dispatch. Several physically restored modules remain uncertified: the current local controller has not gathered enough load-test evidence to close their recovery order within 72 hours. Queued work and work awaiting verification remain in the terminal inventory. These findings motivate informative recovery scheduling and terminal-backlog treatment in stage 4; they do not change the agreed hardware scope.

The reference is a comparison of packages, not an isolated causal estimate for a single robot. Fault-active hours are retrospective fault duration, not whole-plant downtime or time to verified recovery. Scheduled maintenance is currently a billing allowance rather than an executed visit; standby electricity remains unmodelled. These are explicit limits for the next implementation. No annual installation-economics claim is made.

## Preserved evidence and transport

The existing immutable edition/attempt/publication engine runs each case in an isolated worker with one numerical thread. Cancellation retains completed attempts, resume reuses verified complete cases, and reproduction creates a new edition with original source and dependency versions. Changed plant parameters create a new edition with visible resolved differences.

Every new field attempt saves a `dispatch-lab/study-service-calculation/1` artifact once per run. It contains the original service cost calculation and is bound to the run, source and service-price identity with an artifact hash. Archive reads check that its three views reconcile with the recorded metrics. Cost inspection reads those saved operands; it does not silently reprice the old run using today's implementation. Missing original calculation steps are explicitly unavailable.

The browser renders the selected Python report, with service totals, committed crew/remote time, visits, plant inventories, service stores and unresolved work. Detailed records appear only on inspection. Report history remains pinned to exact attempts; opening recorded playback and returning preserves the originating publication. Loading another publication removes the previous report's actions until the selected response arrives, preventing actions on stale data.

`methane/studies.py` owns storage/execution/publication; `methane/field_studies.py` owns field resolution and comparison; `methane/study_service.py` owns the capability-scoped UI transport. The current experiment Model essay describes the separate-arm comparison boundary. Deep service essays and planning alternatives remain later work in the full programme.

```sh
.venv/bin/python -m methane.studies create --protocol field-recovery --tier reference
.venv/bin/python -m methane.studies run EDITION_ID
.venv/bin/python -m methane.studies reproduce EDITION_ID
```

An explicitly authored full protocol may be supplied with `create --protocol-file path.json`. Existing editions pin their protocol; reproduction cannot substitute another question. After extracting an export, `python -I -S check_study.py .` uses only the standard library to verify its inventory and archived numerical checks. Numerical reruns require the recorded dependencies, with cached packages for offline installation.

## Remaining programme

The smoke tier is workflow verification, not a research conclusion. The 144-case sensitivity tier is specified but not yet executed. Actual scheduled maintenance, standby demand, the other five independent study questions, additional service policies and later prepared-interface intervention comparisons are still required. Joint planning, all 14 hardware families, service-specific learning/what-if workflows and held-out learned-policy evaluation remain in the [six-stage roadmap](field-operations-roadmap.md).

The exact verification artifacts, performance observations, failed test-harness attempts and source boundaries are recorded in `build/services/field-studies/verification.json`. Tests for this increment exercise multi-arm matching, missing prices, cancellation/resume, frozen reproduction, saved cost operands, legacy battery Studies, publication history, keyboard/narrow-screen access and stale-response handling. Original plant and solar artwork is unchanged.


The separately preserved presentation `97857d393a23450289152fd7075e01f3` retains the original nine interpretation passages with paragraph separation in its offline HTML. It identifies source report `fce9ebd27fcc48b3b4ce2a5c07c81e72`; numerical outcomes, attempt identities and interpretation text are unchanged. The original report and original portable bundle are not rewritten. Current recovery protocol revision 2 explicitly disables the newly available routine-maintenance and standby mechanisms, preserving this study's comparison boundary. Their mechanism examples and limits are documented in [routine services](routine-services.md); broader service-value studies remain to be completed.
