# Engineering foundations: verification record

Verification performed on 10 September 2026, Apple Silicon macOS 26.5.2,
Python 3.12 and the locked Python/Chromium dependencies. Detailed machine-readable
artifacts are local under `build/engineering`; this document records their scope.

## Delivered

Solar and reactor components now have frozen contracts, parameter metadata,
isolated numerical entry points and generated reference documentation. Actual
plant intervals retain named conservation and operating-limit audits. Failed
traces retain their completed prefix and failure evidence. Solver termination,
incumbent validation and fallback are explicitly reported.

New schema-3 archives include source/dependency/input identity, weather payload
hashes, named sensor random streams and integrity checks. Existing schema-2
archives keep their original interpretation. The standalone archive checker
reconstructs balances, verifies exogenous inputs and rejects missing intervals.

Component inspectors expose model and audit evidence. Plans load on inspection;
unchanged playback frames no longer rebuild tables. Solar preview uses cached
Python calculations and a small read-only transport with stale-response checks.
The original plant and solar SVG artwork passes its visual regression comparison.

## Checks and measurements

- All **85 Python tests** pass. They cover analytical fixtures, independent ODE integration,
  generated sequences, thermal subdivision, archive integrity, invalid traces,
  diagnosis, causality, weather and economic accounting.
- All 18 JavaScript unit tests pass.
- All six browser tests pass on the restarted app, including keyboard access,
  narrow screens, playback, controller switching, costs, lazy inspection and
  out-of-order preview responses.
- A separate browser check passes on a 240-hour run while a real comparative
  batch is active: **124 ms p95 input-to-preview**, **1.7 ms p95 render work**.
  The preview timing includes the 75 ms debounce. Gates are 200 ms and 10 ms.
- The original Gradio component-update preview path measured approximately
  933 ms p95 before the transport fix; the small transport measured approximately
  100 ms p95 in the idle fixture. This is an interaction improvement, not a claim
  of faster MILP solving.
- Five independent mutations are detected: stoichiometry, battery loss,
  heat-flow sign, minimum-run off-by-one and forecast look-ahead.
- TLC exhaustively checks four finite reactor models for minimum runs 1–4,
  reaching 128, 160, 192 and 224 distinct states respectively.
- Five 72-hour, three-controller backend runs complete; median duration is
  **61.6 seconds**. A full-run pre-refactor timing baseline was not captured, so
  this establishes a baseline rather than a quantified solver speedup.

The release matrix completed **51 cases / 153 controller traces**: 18 synthetic
cases, 18 diagnosis-disabled ablations, six thermal sensitivities and nine
historical windows. All 51 saved archives pass **901,720 independent checks**. Two failed
first attempts are preserved. Its report
and saved archive references are in `build/engineering/release-matrix.md` and
`.json`; the final checker has a separate source identity in `release-audits.json`.
Archive generation and the final independent checker may have different source
hashes because checks were strengthened while the long-running suite executed.

## Numerical edge case found during the release matrix

The London winter case exposed a candidate starting approximately 0.00014°C
below the production band; Copenhagen spring exposed a forecast power deficit
of approximately 0.000029 kWh. The audits rejected both, but a handler still caught the
former assertion exception instead of `PhysicalAuditError`. The handler now
records rejected-candidate evidence and enters the existing feasible fallback.
Two regression tests cover the planning and local-rule paths. Both failed archives
are retained as previous attempts in the release report; affected cases are
rerun with the correction.

A separate contention measurement reached 272 ms p95 with four external release
simulation processes and regression checks competing with the app batch. This
result is preserved in `browser-performance-240h-batch-contention.json`.
The 200 ms gate is a defined reference workload, not a guarantee under arbitrary
CPU contention.

## Limits of the evidence

These checks establish numerical invariants, explicit failure handling and a
bounded state-machine result. They do not prove real-plant fidelity, continuous
system safety, solver optimality or universal controller superiority. Inputs
remain illustrative and uncalibrated. Time-limited MILP recomputation can choose
different feasible actions; recorded playback is the exact replay mechanism.

PNG references are platform-specific and run on the reference macOS environment.
Linux CI explicitly skips those PNG comparisons and runs functional browser
checks. Hardware latency gates are opt-in; functional tests and numerical audits
are enforced in CI. See [engineering commands and architecture](engineering.md)
and the generated [component reference](components.md).
