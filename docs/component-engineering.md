# Component engineering and reproducibility

The plant assembler connects local component ports. A component owns its conversion,
inventory or heat equations; the plant owns the shared electrical bus, dispatch
priorities and the distinction between estimated and physical inputs.

## Working on a component

- Execution takes an immutable parameter object, beginning state and explicit interval
  inputs. It returns state, flows, diagnostics and named checks. An infeasible action
  raises an audit failure instead of silently clipping or venting.
- Planning returns immutable bounds and linear rows in local ports. Ports carry units;
  the plant adapter rejects incompatible bindings. The component imports no SciPy,
  Gradio, weather transport or plant controller.
- Electrolysis has `specific-energy/1` and `yield-ledger/1` implementations. Hydrogen
  and CO₂ storage have `balance/1` and `ledger/1`. Battery retains its two implementations.
  These are equivalent formulations used to exercise replacement, not claims of
  distinct calibrated technologies. Reactor planning uses its analytic thermal model.
- Register assumptions, units, execution/planning interfaces and verification references
  in `methane/contracts.py`. Generate the human reference and machine catalogue with
  `python -m methane.engineering docs` and `python -m methane.catalogue generate`.
- Verify with an independent consumer of the planning rows and a hand-calculated or
  independently integrated execution case. `tests/test_components.py` and
  `tests/test_boundaries.py` demonstrate both. Add a version when model meaning changes.

Hydrogen flows concurrently over the interval. CO₂ arrives before withdrawal;
full-tank overflow is explicitly rejected. Reactor commitments use whole hourly
intervals. The thermal helper and battery/electrolyser kernels accept their documented
positive durations; this does not change the plant's hourly scheduling abstraction.

The solar kernel is separated from preview/archive adapters and provider transport.
The saved-forecast provider receives only a current observation and forecast issues.
It cannot read later realised weather. Missing data fails visibly; UTC availability
and preceding-hour radiation conventions remain explicit.

## Evidence and lineage

Actual intervals retain full component records with parameters, beginning state,
applied inputs, ending state, flows, audits and implementation identity. Decision
records retain the estimate, forecast issue, requested plan, cost version and component
selections. Forecast replay records the estimated capacity, not simulator fault truth.

Inspect **Now → Trace this result** to reveal component evidence. Observed channels
are separated from retrospective execution and linked to the sensor source, noise
configuration and named random-stream policy. Solar's existing **Model and evidence**
disclosure contains its recorded generation trace. No labels or geometry in the plant
illustration were changed.

**Costs → Trace costs and totals** reveals allocation operands, price versions,
calendar/usage allowances and source interval collections. A sum refers to a precise
recorded column and interval range instead of copying hundreds of identical leaf
entries. Fixed ownership does not enter dispatch incentives. Repricing creates a
new report price identity while preserving original dispatch prices and actions.
Cumulative methane, curtailment and utilisation have separate physical lineage.

The stdlib-only `methane/reference.py` checker independently recalculates chemistry,
battery balance, analytic heat balance, operating bounds and allocated/decision
costs. It does not import production physics or costing. The production archive
checker additionally reconciles component record contents against their recorded
implementation. Neither checker establishes plant calibration or sensor accuracy.

## Recorded playback and numerical recomputation

New processes capture allowlisted source, assets, tests, docs and dependency files
before dispatch. New runs embed a compressed source capsule alongside environment,
configuration and weather provenance. Older archives with only source hashes are
explicitly reported as lacking recoverable source.

Use **Analysis → Run report → Prepare reproduction bundle**, or:

```sh
python -m methane.bundle runs/methane-v2/RUN.json.gz --out reproduction.zip
```

After extraction, open `playback.html` without a server or internet connection. It
uses recorded actions and plans; numerical replanning requires the restored app.
Verify file hashes and independent balances with no installed packages:

```sh
python -I -S check_bundle.py . --out offline-check.json
```

Restore the original Python version recorded in `bundle.json` and the locked runtime
packages. Offline installation requires that interpreter and packages to be cached;
missing packages stop the restore. Development test dependencies are optional:

```sh
uv sync --project source --locked --offline --no-dev --python ORIGINAL_PYTHON_VERSION
source/.venv/bin/python source/recompute.py recorded-run.json.gz recomputation.json
```

A recomputation writes a new archive and a comparison, never overwrites the recorded
run, and reports both environments. Time-limited MILP solving may select different
feasible schedules even with the same source and input information. The comparison
reports divergence instead of pretending to reproduce the decisions bit for bit.

## Continuous gates and latency

CI stamps the source before validation, checks generated documentation/catalogue
freshness, tests components and legacy readers, runs deliberate mutations and TLC's
bounded reactor abstraction, restores a bundle offline, and checks browser behaviour.
The source-bound evidence catalogue exposes absent or failed checks.

Batch cases execute sequentially in separate low-priority processes with one HiGHS
thread and capped numerical-library threads. Progress and cancellation cross an
explicit file boundary. Interactive previews and recorded inspection stay in the
app process. A worker failure is recorded as failed evidence rather than a successful
empty run. This is local process isolation, not a distributed job scheduler.

Backend budgets are p95: 2 s initial playback preparation for a 240-hour run, 100 ms
cached solar preview, 20 ms component lineage and 100 ms economic lineage. Browser
checks separately gate 200 ms changed-design input-to-preview, including debounce,
and 10 ms render work while a real comparative batch is active. Those are measured
budgets for the representative fixture, not a promise of instantaneous optimization.
