# Completed engineering programme

All six requested increments are implemented and their acceptance gates executed.
The original plant/solar artwork and quiet full-screen interaction remain intact.

Source under validation: `9131923b6104f2e40388b7ca4d810f8bc069bfbc0ac471411ec995b380060cb8`.
Final example: `305743ed90180597`; 24 hours, all three controllers, original default
physical assumptions. The app at port 7860 serves this example.

| Gate | Executed evidence |
|---|---|
| Independent checker and formulation comparison | Stdlib Decimal/reference equations, independent costs, analytical planning bound; [controlled battery comparison](solver-comparison.md) |
| Electrolyser and hydrogen example | Pure execution/planning, two equivalent implementations, standalone MILP consumers, generated metadata and recorded lineage |
| Remaining boundaries | Reactor planning, CO₂ delivery/storage, solar numerical kernel and saved-forecast provider; units, invalid inputs and causality checks |
| Derived and economic traceability | Recorded component/sensor sources, cumulative metrics, cost operands, original dispatch vs current report price/code identities |
| Offline reproduction | Source/lock/assets/config/weather/result bundle; isolated stdlib checker; clean locked runtime restore and explicit numerical comparison |
| Continuous evidence and speed | Generated catalogue/docs checks, compatibility tests, mutation/TLC/browser gates, isolated single-thread batch workers, 240-hour latency budgets |

Validation: **140 Python tests**, **19 JavaScript checks**, **10 general/legacy browser
checks plus 3 recorded-lineage/offline checks** (the battery case overlaps), all six
deliberate mutations detected, and all four finite reactor models verified by TLC.
Audit checks also pass with Python’s `-O` optimisation enabled. Original SVG screenshots
pass their pixel comparisons. Generated docs and catalogue, lint and formatting pass.

The offline checker evaluated **3302 independent checks**. The clean
recomputation used the same source, Python `3.12.14`
and locked numerical dependencies and passed the independent reference again.
Greedy and economic MPC reproduced their actions in this example. Methane MPC
changed five later intervals and its total by −1.501 kg. This is reported, not
hidden: time-limited solving is not promised to reproduce identical decisions.

For the 240-hour fixture, changed-design preview under an active comparative batch
measured **160.5 ms p95**, including debounce; rendering measured
**3.9 ms p95**. Budgets are 200 ms and 10 ms. Backend economic
lineage measured **0.75 ms p95**, after removing
redundant per-interval ledger entries. All backend budgets pass.

Machine-readable evidence is in `build/engineering/current/evidence-catalogue.json`,
including artifact hashes and the validated source identity. The bundle is
`build/engineering/current/reproduction.zip`; its extracted offline player is
`build/engineering/current/restored/playback.html`. CI runs these workflows and
retains incomplete/failed artifacts. CI has been configured; these reported results
were executed locally, not claimed as a remote CI run.

Limits remain explicit: numerical and bounded formal verification are not empirical
calibration or a proof of the complete plant. Legacy archives without captured source
cannot recover that source. Offline runtime restoration needs cached packages and a
matching interpreter. Recorded playback is immutable; numerical alternatives require
the restored application. Detailed kinetics, physical degradation and real plant
control remain outside this engineering increment.

See [the engineering guide](component-engineering.md) for extension and reproduction commands.
