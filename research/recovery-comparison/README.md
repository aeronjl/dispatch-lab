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

The separate 240-hour clock-observation exercise uses Greedy operation and new
seeds/episodes, not evaluation outcomes. A predeclared H120 cut separates training
from future new jobs. Finite candidate job-width models are chosen on training
evidence; held-out jobs assess prediction. These are simulator observations that
verify the calibration workflow. They cannot establish field-calibrated uncertainty.

The null comparison reports exact trace identity and per-operand maximum spreads.
Finite-time optimisation differences, fallbacks, incomplete recovery, rejected work,
ending inventories, allocated costs and decision economics must remain visible.
An adaptive arm is not required to win.
