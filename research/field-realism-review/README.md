# Field operations realism review

Read [the self-contained report](report.html) or [Markdown version](report.md). This is a source/code/conditional-experiment review of the existing fixture, not plant calibration. The wider field-operations programme remains paused.

The authoritative reviewed outputs are `sources.json`, `capabilities.json`, `assumptions.json`, `review-context.json`, `review-decision.json` and `experiments/analysis.json`. Register configuration bindings distinguish optional service-model defaults from the default app's active configuration. Source pages are external links; no network is required to read the report or saved numerical evidence.

## Evidence preservation

- `protocol.json`: original 84-case 48-hour design, frozen before execution.
- `boundary-protocol.json`: every seed-7 arm extended to 240 hours, declared before the extension, after the first suite began.
- `portable-correction.json` and `portable-boundary-correction.json`: transparent correction of the review runner's zero adhered-soil threshold. All 16 affected original cases remain as setup-error evidence; 16 replacements were run. Original output directories were not rewritten.
- `experiments/case-index.csv`: every execution, including use/exclusion reason and its summary path.
- Each suite retains `cases.json`, a protocol, production source identity/capsule, complete per-case inputs, compressed run archive, SHA-256, independent audit, costs, terminal service state and summary. The numerical run IDs are not substituted for archive checksums.
- `experiments/mechanism-checks.json`: independent Decimal thermal grid and chemistry; contact boundaries and observations-only diagnosis challenges. These are not empirical sensor/thermal ranges.
- `experiments/weather-inventory.json`: hashes/variables/requests of the existing 109 cached European responses. Raw originals remain under `runs/weather`; no historical study was resumed.
- `experiments/targeted-tests.txt`: 101 targeted tests passed; no production or UI change was made by this review.
- `integrity.json`: hashes of review outputs and experiment files at delivery. Large numerical evidence stays local, linked from the small report. An audit assertion count is not an empirical sample size.

## Repeating or updating the review

Use the project `.venv/bin/python`. Run from the repository root. The production identity must match the recorded capsule to describe a replay as the same implementation. A change in source, plant, observation channel, allowed remedy or support contract requires a new edition and review decision. Do not overwrite old evidence or reclassify it as calibrated.

To rerun original inputs, choose a **new directory**:

```sh
.venv/bin/python research/field-realism-review/run_experiments.py --protocol research/field-realism-review/protocol.json --directory /tmp/dispatch-realism-repeat-primary
```

The original protocol deliberately reproduces the original threshold mistake. For the corrected portable cases use `portable-correction.json`; use `boundary-protocol.json` and `portable-boundary-correction.json` for the corresponding extension. Each protocol retains its intended subset. `--limit 1` permits a smoke run; creating a `CANCEL` file in that run directory stops before the next case. A run does not use the paused study queue or change app setup. Matching finished cases are reused only after input/archive checks; a different frozen input raises an error.

To regenerate the independent challenges on the current source:

```sh
.venv/bin/python research/field-realism-review/check_mechanisms.py
```

This writes a new current-source check report; copy the review directory first if preserving the delivered edition. The independent reference expectations use Decimal arithmetic and do not call production thermal functions to form their expected values. Diagnosis challenges deliberately use the production observer with declared input observations.

`analyze.py` reconstructs every case group and replaces only the documented portable setup-error arms. `build_report.py` builds both offline report formats using those saved results and the authored text. `build_registers.py` is an authored review record, not a source-retrieval or automatic scientific-review process. Rebuilding it alone does not constitute a fresh review. Run `bind_parameters.py` after register generation to validate all configuration paths.

The full numerical evidence includes unsuccessful interventions and unverified terminal work even though all runs completed computationally. No run here constitutes a real plant/robot trial. The 240-hour extension has only seed 7 and cannot support a reliability estimate.
