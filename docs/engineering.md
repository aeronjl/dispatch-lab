# Engineering foundations

The intended use is comparative plant/controller experiments under explicit
assumptions. No component has been calibrated to a Rivan plant. The generated
[component reference](components.md) describes solar, reactor and battery contracts.
The [battery example](battery.md) completes execution/planning replacement and
displayed-result lineage across the plant.

## Running checks

Install the locked Python environment with `uv sync --locked`. Browser checks use
`npm ci` and `npx playwright install chromium`. Run:

```sh
uv run pytest -q --junitxml=build/engineering/pytest.xml
node --test tests/*.test.cjs
uv run python -m methane.mutations
uv run python -m methane.engineering docs --check
uv run python -m methane.engineering docs --junit build/engineering/pytest.xml
uv run python -m methane.engineering component reactor
uv run python -m methane.engineering component solar
uv run python -m methane.engineering component battery
uv run python -m methane.engineering audit runs/methane-v2/RUN_ID.json.gz
uv run python -m methane.engineering benchmark
npm run test:browser
uv run python -m methane.release_check
uv run python -m methane.release_check --audit
```

For formal verification, install Java 17 and download TLC 1.7.4 from the official
TLA+ release. The runner verifies the jar checksum before executing:

```sh
uv run python -m methane.engineering formal --java /path/to/java --jar /path/to/tla2tools.jar
```

See [formal assumptions](../formal/README.md). The finite abstraction covers
minimum runs 1–4; larger configured commitments are not covered by this model
checking report. Thermal accuracy is independently tested against numerical
integration, analytical examples and subdivision equivalence.

## Component and execution boundaries

Frozen component specifications describe parameters, dimensions, data needs,
time semantics and references. Solar and reactor numerical functions have no
network/browser/filesystem access. Plant orchestration continues to allocate
shared electricity/feedstock and enforce coupled MILP constraints.

The reactor accepts interval methane **mass**, not a mass rate. Its thermal helper
supports positive durations; the plant scheduler rejects non-hourly intervals.
`expm1` and a small-argument series improve thermal arithmetic near zero heat
loss without changing the intended model.

Physical audits run regardless of Python optimisation flags. Tolerances are
1e-5 absolute in the declared unit plus 1e-8 times the relevant magnitude.
Invalid physical traces preserve their prefix and failing context. Forecast
rollouts retain audit summaries; actual intervals retain named audit records.
Solver termination and fallback are separate; a missing incumbent is never
silently described as proof of infeasibility.

## Archives and reproducibility

New runs use methane schema 3. Field meanings and hourly CSV units are preserved.
Schema 2 reads do not mutate or upgrade the source. Missing provenance is explicitly
unavailable. The existing hydrogen reader remains separate.

Manifests identify executable source content captured at process initialisation,
the dependency lock, runtime environment, solver settings, named sensor-stream
policy, frozen configuration and weather payloads. Restart the server after code
changes so its loaded implementation matches the new source. Weather generation
retains its existing seeded policy; sensor channels use independent stable names.
Configurations loaded without a random policy retain `legacy/1`.

An experiment ID identifies frozen inputs/environment; run IDs also distinguish
applied action traces. The archive hash detects payload changes, but is not a
signature or attestation of physical operation. The archive audit command
recomputes state/flow accounting rather than trusting recorded residuals.

Playback is exact recorded replay. Recalculation with time-limited mixed-integer
solves can select different feasible incumbents, particularly across machines.
Compare differences and objective gaps; do not assert that every controller
always wins or that reruns must be bitwise identical.

## Interactive performance and presentation

The browser receives compact decision records and obtains trajectories through
`inspect_decision` only when needed. Hourly tables render only on data/selection
changes; CSS animation remains independent. A read-only `/dispatch/preview-solar`
route on Gradio's FastAPI app avoids reconstructing the large HTML component on
each slider change. Random capability tokens address at most 16 frozen preview
contexts. Expired contexts report an error; they never switch to other data.
Gradio's existing preview callback remains available. Both paths call the same
Python component and preserve request-generation checks.

Recorded solar decision/cost details and calculation lineage are fetched when
their disclosure is opened. Opening the diagram alone does not enqueue that
hidden work. The preview route serialises JSON-native operands directly and
exposes separate calculation and serialization durations in `Server-Timing`.
Measurements retain the first edit separately; plant rendering and solar preview
rendering each have their own timing series, so the plant-only timing cannot
stand in for a preview redraw. The September autonomy qualification report records
the 72-hour and 240-hour fixtures and the active-batch measurements separately.

Solar caching covers individual sections and full intervals; cache values are
immutable and callers receive separate results. Full plant changes still
propagate through dispatch. Batch and interactive queues are separate, and
cancellation is checked before each solve, including fallback horizons.

Browser performance artifacts separate input-to-display time from render work.
Set `DISPATCH_PERFORMANCE_GATE=1` to enforce the 200 ms preview gate on the
reference machine. PNG baselines were captured from the pre-refactor app on
Apple Silicon macOS with pinned Chromium; Linux CI runs functional browser
checks and explicitly skips those platform-specific PNG comparisons. Snapshot
updates require an intentional visual review, never automatic acceptance.

Generated reports under `build/engineering` include test counts derived from
JUnit, mutation outcomes, formal output, standalone reactor plots and timings.
They identify the build/fixture they describe and do not imply empirical plant
validation.

For the heavier reference-machine interaction gate, run
`DISPATCH_BROWSER_HOURS=240 DISPATCH_BATCH_ACTIVE=1 DISPATCH_PERFORMANCE_GATE=1 npm run test:browser -- --grep 'preview latency'`.
This starts a separate local test app, executes a real batch while measuring
previews, and requests cancellation afterwards. The release matrix uses cached
weather offline; missing historical snapshots are reported as incomplete.
See [verification results](engineering-results.md).

### Chronological checkpoint cost

Sites retains an independent transaction image after every completed hour, including
shared service ledgers and optical state. Portable graph encoding and integrity
hashing happen when that image is exported at the partition/cancellation boundary.
A failed following interval cannot mutate the saved image. The allowlisted,
non-executable checkpoint format remains readable without migration. The Release-2
compatibility experiment resumes the same saved boundary with each source and
compares physical, observation, service and lifecycle records; it does not relabel
the old annual study as a result of the new implementation.

### Whole-case reporting

Long Sites cases now decode each committed summary partition once. The report view
uses the existing finite-service cost projection, adds the descriptive outcome
operands and retains the complete final service state. Scalar totals, allocation,
calendar and products reuse that view instead of repeatedly decoding historical
decision trees. Full hourly recordings remain unchanged. Legacy records outside
that finite-pricing contract retain their original reporting objects.

`tests/test_siting_summary.py` checks exact equality of every summary field against
full operands, including costs, terminal work and condition, and rejects missing
hours. Cancellation is checked between partitions; resumption can finish reporting
without resimulating committed hours. Reporting progress is separate from simulated
hours and from export work. The first annual acceptance derivation is recorded in
`research/release-2/annual-reconciliation.json`, with its reporting source separate
from the original execution source.
