# Autonomous operation across sites

Authorised 13 September 2026. This bounded qualification programme follows the
Sites release. It does not resume the paused 14-family hardware expansion.

The programme first reads the original 72-hour Seville comparison, then freezes
new, matched experiments in Sites. It separates controller packages from changes
to process objectives, numerical budgets, observer ambiguity and recovery windows.
Seasonal cases are continuous seven-day exposures using the saved 2025 European
ERA5 inputs and causal previous-day forecasts. They are design scenarios, not
archived-forecast autonomy, independent unseen years or annual repair reliability.

All groups and sensitivity values are declared before execution. Repetitions are
numerical repeats, event seeds are conditional simulator replications, and neither
is a new weather sample. Unsupported repairs remain unavailable. No physical
calibration or probability of real-world success follows from simulator samples.

## Intended outputs

- Original counterexample timeline with dispatch, forecasts, diagnosis, work,
  solver termination, heat and inventories; no retrospective causal scores.
- Matched package/objective, horizon/budget, ambiguity/deadline, failed service,
  sensor-bias and seasonal comparisons. Preserve invalid/incomplete attempts.
- Sensitivity-based evidence priorities and specific observation/quote requirements.
- Scoped checks and immutable user-facing write-ups linked to original playback.
- Separate cold/warm/contended preview measurements and verified speed changes.

The original source, raw inputs, checkpoints and numerical records remain under
`runs/sites`. Git retains the protocol, interpretation and compact result editions.
Opening the report is offline; reproducing numerical results requires the saved
source capsule and input bytes. Changed plant parameters create a new programme
with `--basis`, never overwrite earlier cases.

## Reproduction commands

```sh
.venv/bin/python -m methane.autonomy_qualification prepare
.venv/bin/python -m methane.autonomy_qualification run research/autonomy-qualification/PROGRAMME
.venv/bin/python -m methane.autonomy_qualification report research/autonomy-qualification/PROGRAMME
```

`prepare --basis CONFIG.json` starts from a different saved plant. The named
horizon/budget and scenario challenges are explicit overrides; every changed
parameter path is retained. Coordinates must match the original Seville input;
seasonal arms explicitly use their own saved anchor weather. A `cancel` file in
the programme directory cancels the active bounded worker and prevents later
groups from starting. Remove it and run again to resume committed checkpoints.

The release protocol has 105 cases: 12 original-package/horizon/budget, six common
local-service objective comparisons, 33 recovery ablations, 36 support/thermal/
forecast sensitivities, and 18 seven-day seasonal cases. The same 2025 data has
already been used in platform qualification, so these are not unseen-year tests.
Each group has its own frozen source capsule and remains visible in Sites.

Explicit per-case policies use site-yield-study/2. The controller label must match
the policy objective. Older studies retain version 1 and their original default
policy resolution. This allows the common-local-service comparison without
changing Greedy into a coordinated-service controller or changing old runs.
