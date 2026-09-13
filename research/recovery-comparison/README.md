# Recovery qualification programme

This programme follows the recovery-loop, comparison, uncertainty and speed work
authorised on 13 September 2026. It does not resume the paused hardware-family
programme. Authored findings and compact outputs are committed; original Studies,
raw weather, source capsules, archives and full independent checks stay under
`runs/` with their recorded hashes.

```sh
.venv/bin/python -m methane.recovery_comparison create --pilot
.venv/bin/python -m methane.recovery_comparison run research/recovery-comparison/PROGRAMME
.venv/bin/python -m methane.recovery_comparison create
.venv/bin/python -m methane.recovery_comparison run research/recovery-comparison/PROGRAMME
.venv/bin/python -m methane.recovery_comparison calibrate research/recovery-comparison/PROGRAMME
```

Use `--basis saved-config.json` at creation for changed plant parameters. Creation
freezes source, configurations, original weather and policies in immutable Studies.
Run from that source version. Reuse saved completed cases by rerunning `run`.
Create a `cancel` file in the programme directory to request cancellation; remove
that control file before resuming. Reports get a fresh revision on every invocation
of `report`. Nothing reassigns earlier evidence to a changed implementation.

The complete protocol has seven synthetic conditions, three event seeds, three
service-uncertainty modes, two numerical null repetitions and nine seasonal
European windows. Process objective and physical inputs match across policy arms.
Seasonal cases use 48 hours from each original cached ten-day envelope, preserving
raw references and forecast availability. They are short operational exposures,
not seasonal yield or annual service-cost estimates. Missing inputs stay incomplete.

The service-exposure fixture starts with empty battery and hydrogen stores. Its
persistent fault leaves 112.5 kW capacity, below the 135 kW electrolyser minimum.
Crew response lead is zero, travel is 0.25 hours, and availability is 24 hours;
robot batteries are 10 kWh and three module kits are initially available. These
shared assumptions create a controlled service challenge. They are neither an
empirical distribution of fault severity nor measured European-site logistics.

The separate 240-hour clock-observation exercise uses Greedy operation and new
seeds/episodes, not evaluation outcomes. A predeclared H120 cut separates training
from future new jobs. Finite candidate job-width models are chosen on training
evidence; held-out jobs assess prediction. These are simulator observations that
verify the calibration workflow. They cannot establish field-calibrated uncertainty.

The null comparison reports exact trace identity and per-operand maximum spreads.
Finite-time optimisation differences, fallbacks, incomplete recovery, rejected work,
ending inventories, allocated costs and decision economics must remain visible.
An adaptive arm is not required to win.

## Release editions and report

`programme-index.json` records every edition, including the original independently
failed cleaning case and protocols prepared but never executed. The release
source is `9e045c22f82542cef2334a8e8a4999611f57c9edfe1fbf2b8595de90eb82499b`.
The main programme is `c03f2ebfebde491ea7ce927701f35bf2`. Its 24-hour
verification-window sensitivity is `07c1a191609d4cf89ff694d2a33e67bb`.
The recovery wait setting applies to both initial tests and post-mission windows;
this sensitivity does not isolate the latter alone. Service deadlines stay fixed.
A separate normal-service computation repeat is
`621aec1013f54ddf867731447170cd24`. This is not another set of independent seeds.

`execute-release.py MAIN_ID WINDOW_ID` runs the two programmes and the separate
clock calibration sequentially, without competing optimisers. It writes an
exclusive `release-result.json` containing the original report paths. Then run
the normal-service repeat with the same `run` command above. Solver time limits
remain part of the experiment: matching seeds do not guarantee identical
non-null finite-time incumbents.

For each original programme JSON report, `summarise.py REPORT.json` creates a
new, exclusive `REPORT-summary.json`. It retains every status, source identity,
physical/weather match and ending inventory. `report_metrics.py` derives distinct
post-mission windows from the original recorded episode histories. It does not
reinterpret the legacy `recovery_deadline_misses` column: that column counts the
earlier scheduler's `deadline-missed` status, while v3 emits an explicit
`escalation-required` state. Expired windows, escalation intervals and observer
confirmation therefore have separate, versioned report counts. Check this
aggregation with `check-report-metrics.py`.

`window-trace.py MAIN_SUMMARY WINDOW_SUMMARY` extracts the fixed-mode, seed-7
paired timeline from sealed archives; selection was declared before sensitivity
outcomes. `writeup.py MAIN_SUMMARY WINDOW_SUMMARY REPEAT_SUMMARY CALIBRATION_RESULT`
combines the saved numbers and `interpretation.html` into `report.html`. The
human-readable write-up is generated from recorded outputs, without new solves.
This authored release renderer is bound to the three declared programme IDs.
Changed plant parameters use new generic Study reports and a separately reviewed
interpretation; the old fixture description is never silently reused for them.
Original Study reports remain linked locally. Raw JSON reports, calibration
packets and source capsules require their preserved local archives; compact
summaries and authored interpretation remain readable from Git.

All clock fitting uses simulated observations in this release. Real phase-clock,
failure and repair-effect observations have not been supplied. The fitting
interface accepts labelled field observations; its existence is not evidence that
the illustrative distributions describe real equipment. In particular, this
programme does not calibrate repair success probabilities, fault incidence,
weather-error tails, fleet correlation or human logistics.

## Audit correction and final validation

The 153-case matrix, nine deadline cases and nine numerical repeats all completed
and passed their original independent audits on the frozen numerical source.
They are 171 executions, not 171 independent environmental replications.

One separate calibration record originally failed only an exact Boolean stock
boundary check: decimal replay of rounded brush-disposal operands reached
−1.2539e−11 m². Checker version 2 reports the real overrun in resource units and
uses its unchanged declared tolerance. It leaves the physical trace untouched.
`qualify-calibration.py` preserves the original failed audit and two-run fit,
then qualifies all three observation records for a new fit using the same
candidate models and H120 cutoff. The result binds each new audit artifact.
The new fit has 172 held-out job/group outcomes: 142 of 168 completed outcomes
inside its 90% prediction interval, four censored and ten sparse groups.

The corrected reporting/checker source is
`783a978c022c6af6edc056439fdfa0a169671441b4d8d74e48e024b7538c5010`.
Its 1,011-test regression and topic evidence are separate from the numerical
source's 1,005-test record. Neither retroactively rebinds the original simulations.
`validation/` retains both source stamps and test results. The application browser
suite passed 87 cases with 18 fixture-dependent skips; all 73 renderer tests passed.
The report itself has a separate offline, narrow-screen and keyboard check.

`repeat-counterexample.py` extracts the post-hoc risk-aware seed-7 failure from
the sealed repeat record. It identifies an ambiguous H15 capacity update, not the
first optimisation divergence or an isolated causal effect of risk preferences.
`inventory.py` records local artifact hashes after completion; it is not a backup.
