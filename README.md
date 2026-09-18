# Dispatch Lab — autonomous plant experiments

An hourly, local scheduling sandbox for a solar-powered methane plant. Begin with **Site → Build → Operate**: select a location, configure the illustrated equipment, then calculate and watch operation. The simulation remains a quiet full-screen workspace: play, pause, step or change speed; select equipment to inspect **Now → Why → Next → Costs → What if**. Experiment setup is a separate screen.

```sh
uv sync --locked
uv run python app.py
# http://127.0.0.1:7860
```

An unsigned Mac desktop development candidate now bundles its own Python runtime.
The Windows build workflow is supplied but has not yet been qualified. See the
[desktop runtime guide](docs/desktop-runtime.md) and the fixed
[P3.1–P3.6 release plan](docs/desktop-release.md). Durable desktop drafts,
background recovery and integrated agent connection are subsequent increments.

The saved reference 72-hour experiment compares **Greedy**, **MPC · methane** and **MPC · economics**. Setup includes an **Autonomy story / four days** preset, a flow-sensor fault and delayed feedstock. Results include methane, ending hydrogen/CO₂/battery inventories, curtailment, starts, forced trips, diagnosis performance, solver limitations and illustrative costs.

The [plant project guide](docs/plant-projects.md) covers common controls, complete expert settings, saved design revisions, weather retrieval and matched comparisons. From recorded playback, open **Menu → Site · Build · Operate** to return to your project.

**Menu → Agent control** starts a bounded simulated-plant session. Operators and
MCP agents can observe, preview, advance one interval and trace delivery using the
same physical executor. Start from saved project inputs and site utilities, continue
a committed checkpoint, recover an interruption, or replay recorded requests in a
separate numerical edition. Grants are session-specific and revocable. See the
[control guide](docs/agent-control.md) for setup, permissions and current boundaries.

**Sites → Production studies → Learning & policies** adds frozen observation datasets,
held-out estimator comparisons, registered planning aids and homeostatic reserve
experiments. Training, operation, cancellation/resumption, write-ups and portable
exports share the existing study workflow. Start with the
[learning guide](docs/learning-and-policies.md); broader research campaigns are
optional uses of the platform, not a required setup step.

### What the model includes

- Explicit electrical dispatch and ideal Sabatier chemistry, with hydrogen/CO₂ tanks and recorded rejected deliveries.
- Analytically integrated reactor temperature, reaction heat, warm-up, cooling and minimum-run commitments. Physical execution records requested/applied differences and forced shutdowns.
- Receding-horizon mixed-integer planning with a 0.5-second default solver limit, incumbent validation, physical replay validation and a local feasible fallback. Time-limited incumbents are reported, not labelled optimal.
- Bounded sensor diagnosis using electrical tracking and an independent inventory mass balance. Low excitation is uncertain; flow-sensor isolation is distinct from equipment derating. Constrained upward probes test recovery. The controller never receives injected fault type/capacity/recovery timing.
- Saved ECMWF forecasts, individual historical forecast issues and ERA5 reanalysis. UTC interval normalization, explicit PV conversion, provenance and raw response caching. Missing weather is visible and never replaced silently with synthetic data.
- Component cost allocation, separately displayed marginal dispatch proxies, frozen decision assumptions and immutable same-information what-ifs.

All plant and cost defaults are **illustrative**, not an industrial calibration. This is not a live plant controller or a gas-quality model. Stable asset IDs and provenance support future equipment economics; DePIN contracts, tokens, settlement and marketplaces are outside this release.

### Development and research records

Completed, verified increments are committed locally by default; see the
[working agreement](AGENTS.md). The current platform implementation is in
`methane/`, with browser rendering in `assets/` and contracts and modelling
references in `docs/`. [Research records](research/README.md) explain which
protocols, reports and evidence summaries are versioned, and which large artifacts
require a separately preserved local archive. A fresh checkout includes the
automated test fixtures, but does not include every historical experiment run.

### Reproduce and compare

```sh
uv run pytest -q
node --test tests/*.test.cjs
uv run ruff check .
uv run ruff format --check .
uv run python -m methane.evidence --suite synthetic
uv run python -m methane.evidence --suite ablation
uv run python -m methane.evidence --suite thermal
uv run python -m methane.evidence --suite historical
# Once weather is cached:
uv run python -m methane.evidence --suite historical --offline
# Replay an exported archive using its exact saved weather:
uv run python -m methane.evidence --replay runs/methane-v2/RUN_ID.zip
```

Batch controls also live under the expandable evidence area. Cancellation records unfinished cases; completed cases are reused. Synthetic evidence covers six scenarios × seeds 7/19/42. Historical evidence covers London, Seville and Copenhagen, each starting on 10 January, 10 April and 10 July 2026, for ten days. Solver time limits can produce different incumbents on different machines; raw inputs, chosen actions and predictions are archived for inspection.

Artifacts are under `runs/methane-v2/`; raw weather caches are under `runs/weather/` (both ignored by Git). ZIP exports contain versioned JSON, an explicit methane CSV, cost reports and source weather. The saved-run loader accepts v0.2 JSON.gz files and restores their setup. Legacy hydrogen archives retain their original meaning and remain supported by the original modules and `uv run python app.py --legacy --port 7862`.

- [Model assumptions and information boundaries](docs/methane-model.md)
- [Solar workspace, design previews and modelling assumptions](docs/solar-workspace.md)
- [Guided demonstration](docs/guided-demo.md)
- [Implementation and validation record](docs/v0.2-delivery.md)
- [Completed evidence and findings](docs/evidence-summary.md)

---

The [expert workflow](docs/ux-workflow.md) connects Site, Build, Operate, Investigate, Compare and Write up. Open the simulation menu to choose a task; specialist tools are searchable under **All tools**. The plant view stays quiet.

## Preserved v0.1 hydrogen model documentation

# Dispatch lab

A local Python playground for solar–battery–electrolyser scheduling. Compare a
greedy operating rule with a receding-horizon mixed-integer controller (MPC),
using the same synthetic weather, initial inventory and equipment limits.

The **Plant simulation** screen integrates operation and optional component cost
labels. Select equipment to inspect its operating constraints, allocated cost,
wear and trade-offs at the current hour. Deeper cost reports include controller
comparisons, sensitivity tests and battery sizing.
Every cost default is an illustrative EUR assumption. Cost edits do not change
the physical schedule or either controller's objective.

## Run locally

Install [uv](https://docs.astral.sh/uv/getting-started/installation/), then:

```sh
git clone git@github.com:aeronjl/dispatch-lab.git
cd dispatch-lab
uv sync --locked
uv run python app.py
```

Open http://127.0.0.1:7860. The server binds to loopback only, with sharing and
Gradio analytics disabled. Once dependencies are installed, simulation requires
no weather API, account or network connection. `Ctrl-C` stops the server.

Python 3.12 is required. `uv.lock` pins the environment. Downloaded runs are in
`runs/` and contain a JSON record and CSV time series. They can be deleted.
Cost and sizing downloads include the exact cost inputs, accounting method,
sensitivity ranges and complete physical traces for sizing candidates.

## Playback console

The **Plant simulation** screen opens on a full-width animated plant. Press **Play**,
step backward/forward, reset, or scrub to any hour. Speeds range from **0.25× to
8×**; **1× means one simulated hour per real second**. Speed changes preserve the
current position. Stepping and scrubbing pause playback; the end stops
automatically and offers Replay. Focus the console to use Space (play/pause),
arrow keys (step), R/Home (reset) or End (finish). Native buttons and the timeline
also support keyboard navigation.

The console replays a completed run locally in the browser. Both controllers
advance together, with traces revealed only through the selected hour. The MPC
still makes causal hourly decisions using the original forecast and physics.
The clock does not introduce sub-hour physics, fetch live plant data or change
controller decisions. Power readouts describe the last completed hourly interval;
battery and cumulative hydrogen are the state at its end. Hour zero shows the
initial inventory. Switch **Forecast MPC / Greedy** to inspect either controller.

**Experiment setup** is a separate screen. Capacity comes first; operating limits,
costs and lifetimes expand beneath the relevant component. Weather, forecast and
fault settings form a second group; shared site and production costs form a third.
**Run experiment** applies physical settings, returns to the simulation and resets
to hour zero, paused. Until then the previous run remains visible with an unapplied
settings notice. Cost edits recalculate immediately and preserve the playhead.
Leaving the simulation or hiding the browser tab pauses playback.

**Costs on/off** toggles financial labels. Component inspectors show values only
through the selected hour, using the same allocation function as full-run analysis.
At hour zero, allocated cost is zero and €/kg is undefined. An incident budget
appears only after the fault's first interval. Calendar and usage capital estimates
are alternatives: the larger is allocated once. Solar curtailment, storage losses
and start-up energy reduce output, with no duplicate electricity charge.

**Live comparison** reveals traces and numeric telemetry. **Run analysis** and
**Cost analysis** below the simulation contain whole-run reports and exports;
these are explicitly distinguished from playhead values. The battery inspector
links directly to the sizing study. Components support keyboard selection
(Enter/Space), and Escape closes the inspector.

The interface uses the locally bundled [Departure Mono](https://departuremono.com/)
font by Helena Zhang and an amber instrument-panel style inspired by its specimen
site. The font's SIL Open Font License is included in `assets/fonts/OFL.txt`.

### Animated plant diagram

The amber component illustrations follow the selected controller and hour:
solar panel brightness follows generation, the battery rack fills with stored
energy, the charge/discharge connection reverses, stack plates respond to
productive load and available capacity, and hydrogen markers appear during
production. Unused solar branches off before the DC bus; power labels separate
available solar from the portion actually used. Start-up energy remains part
of electrical demand, while hydrogen follows productive power only.

Moving markers show direction; marker thickness and cadence respond to relative
throughput. Animations freeze on pause and respect reduced-motion preferences.
They illustrate hourly states, not additional physical dynamics. A plain-language
caption explains the same flows. On narrow screens, pan the diagram horizontally;
numeric telemetry and the caption remain available without panning.

## What to try

Start with “Broken clouds”, then remove the battery. Raise start-up energy,
increase forecast bias, or inject a capacity fault. Change one assumption at a
time and keep the weather seed fixed for paired comparisons. Repeat over seeds
before making claims about a controller. Ten-day runs are available, but start
with three days to make individual decisions visible.

## Model boundary

This is an hourly control experiment, **not a calibrated Rivan digital twin**.
Output is hydrogen, with illustrative 55 kWh/kg productive electricity, an
adjustable electrical start-up overhead, and minimum operating load. There are
no gas or thermal dynamics, price signals, grid connection, physical ageing,
water limits, compressors or methane production. All defaults are assumptions.

The battery has finite capacity, power and charging/discharging losses. Energy
is explicitly conserved. The DC-bus identity for each step is:

```text
PV energy = productive electricity + start-up electricity + curtailment
            + battery losses + change in stored energy
```

The MPC sees the current observed PV and capacity plus a synthetic forecast.
It does not see future realised weather or fault timing. Current-hour average
PV is treated as measured, an explicit hourly abstraction. There is no fault
diagnosis; the available equipment capacity is assumed observable immediately.

The objective is forecast hydrogen output, with a tiny battery-throughput
tie-break. End-of-horizon battery energy has zero salvage value. Reported final
inventories must be considered alongside production differences. A 0.5-second
solver time limit and 0.1% objective gap keep interaction quick; feasible
time-limited solutions and fallback counts are reported. The initial battery
is identical for both strategies. The greedy baseline can use the battery.

## Structure

- `plant.py`: physical state and one-step energy accounting.
- `controllers.py`: greedy rule and MILP planning, using SciPy/HiGHS.
- `experiment.py`: synthetic weather, causal forecasts, faults and paired runs.
- `app.py`: Gradio controls, Plotly charts, comparison and downloads.
- `playback.py`, `assets/playback.*`: browser clock, timeline, instruments and hourly traces.
- `assets/plant-scene.*`, `assets/plant-motion.css`: connected illustrations and measured flows.
- `ui_theme.py`, `assets/*.css`: shared Departure Mono typography and instrument palette.
- `economics.py`: period and hourly cost allocation, capital, sensitivity and paired sizing.
- `assets/plant-inspector.js`: contextual operation, cost labels and component trade-offs.
- `economics_ui.py`: cost controls, comparisons, charts and reproducible exports.
- `tests/`: analytical energy checks, operating limits, causality and fallback.

There is one canonical physical model shared by both controllers. Research code
does not depend on Gradio, so policies and experiments can also run from scripts
or notebooks.

## Validate

```sh
uv run pytest -q
uv run ruff check .
uv run ruff format --check .
node --test tests/playback.test.cjs
```

The browser clock tests use Node.js 20+ with no npm dependencies. Node is not
required to run the app. They cover speed, pause/resume, seeking, boundaries,
new runs, and hourly telemetry accounting.

The tests include a hand-solvable scheduling problem with a 180 kWh optimum,
battery round-trip efficiency, start-up overhead, fault limits, zero-energy
behaviour, forecast causality and identical pre-fault decisions. They validate
internal consistency, not accuracy against real equipment.

## Cost accounting

Upfront investment and period capital allocation are separate views, not amounts
to add together. Fixed capital allocation is cost / assumed years × hours / 8,760.
For replaceable battery cells and stacks, we charge the larger of calendar and
usage-based allocation once. Usage is an explicit proxy for consumption of an
assumed cycle/operating life; it does not simulate ageing, replacements or payment
timing. Installation and site costs are separate from hardware. The stack is a
share of electrolyser cost, not an additional purchase.

Cash operating budget comprises prorated standing costs, water/consumables and
one repair/visit budget if an injected capacity fault starts during the run.
Owned solar has no second electricity purchase charge; curtailed electricity,
losses and start energy affect output rather than creating duplicate invoices.

Period €/kg is undefined with zero output. Annual figures are only the calendar
capital plus standing-cost budget; annual hydrogen output is not inferred from
the short weather sample. No financing, taxes, subsidies or revenue are modelled.
Opening and closing battery inventories are shown without a monetary valuation.
The sizing comparison starts every candidate empty, holds weather/other equipment
fixed, and scales battery power with energy capacity at the selected C-rate.

Cost sensitivities stress one input from 50% to 150% of its current value, except
extra wear per start (0 to at least 10 equivalent hours). These are scenario
ranges, not confidence intervals. Cost and sizing exports record these choices.

## Implementation references

- [SciPy `milp`](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
- [HiGHS](https://highs.dev/)
- [Gradio Blocks](https://www.gradio.app/guides/blocks-and-event-listeners)
- [Plotly subplots](https://plotly.com/python/subplots/)

## Engineering foundations

See [engineering checks and architecture](docs/engineering.md), the generated [component reference](docs/components.md), and [reactor verification assumptions](formal/README.md). New methane runs use schema 3 with audits and provenance; saved schema 2 runs remain readable.

### Component engineering

[Execution/planning boundaries, lineage, offline bundles and CI gates](docs/component-engineering.md)
describes the complete engineering workflow. [Generated component catalogue](docs/component-catalogue.json)
is checked for freshness alongside the human-readable [component reference](docs/components.md).

### Field operations

New injected faults persist until compatible successful service; timed transients are explicit. The optional cleaner, inspection rover, DC dock, bounded reset and human fallback are available through the field-services setup presets and **Simulation menu → Site services**. See [mechanics, boundaries and accounting](docs/field-operations.md). Existing archives preserve their timed-fault semantics.

Component exploration and the complete site taxonomy are described in [the taxonomy guide](docs/site-taxonomy.md). New runs preserve original catalogue snapshots; older runs explicitly distinguish current interpretation from missing original metadata.


## Sites and production studies

Open **Sites** from the simulation menu to save European site evidence, configure a
plant, run continuous chronological studies, inspect original periods and compare
project cash scenarios. Reference examples for London, Seville and Copenhagen are
available in the local saved store. The [Sites workflow](docs/sites/implementation.md)
and [qualification record](research/siting-implementation/README.md) distinguish
implemented data adapters, required site evidence and model boundaries. Grid-assisted
operation, CO2 capture and certified product export remain separate extensions.
