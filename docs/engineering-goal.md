# Complete engineering programme

Authorized goal: complete steps 1–6 from the engineering roadmap. Preserve the
quiet full-screen simulation, original SVG and labels, original archive meaning,
and usable intermediate releases. Review findings at each gate; seek guidance
only for material changes in scope, physical assumptions or acceptance criteria.

| Step | Deliverable and acceptance gate | Status |
|---|---|---|
| 1 | Independent physics/economic reference checker; known-answer planning cases; same-information formulation/solver comparison and battery divergence report | Complete |
| 2 | Replaceable electrolyser and H₂ buffer execution/planning; independent tests; metadata docs and recorded lineage | Complete |
| 3 | Reactor planning, CO₂ delivery/storage and solar/weather boundaries; explicit units/time/failures and isolated tests | Complete |
| 4 | Common component/derived/economic lineage; repricing identifies new prices and original dispatch assumptions | Complete |
| 5 | Source/lock/input/result reproduction bundle; clean offline playback/check and explicit recomputation comparison | Complete |
| 6 | Versioned evidence catalogue; documentation/compatibility/performance CI gates and interactive/batch isolation | Complete |

Initial baseline: battery has two equivalent execution/planning implementations,
100 Python tests, 19 JavaScript checks, browser coverage and versioned lineage.
Solar and reactor have partial pure numerical boundaries. The archive auditor
reuses production transitions; source provenance has hashes but not source bytes.
The short-time-limit battery MPC comparison requires controlled analysis before
attributing its different trajectories to any physical-model difference.

Completion means executed evidence for every gate, not merely new interfaces or
documentation. Numerical verification remains distinct from empirical calibration.

Implementation guide: [component-engineering.md](component-engineering.md).
Generated contracts: [components.md](components.md) and [component-catalogue.json](component-catalogue.json).

All six gates completed. Final verification and limitations: [engineering-completion.md](engineering-completion.md).
