# Uncertainty-aware first service system

Authorized 13 September 2026: implement roadmap steps 1–4, then give an honest
account of remaining work. This is a new bounded programme; the paused full
14-family hardware/degradation programme is not implicitly resumed.

## Completion gates

1. Controlled comparison protocol: immutable inputs, isolated sequential numerical
   attempts, nominal no-op controls, solver termination/gaps, ending inventories,
   and conclusions that separate numerical variability from adaptation effects.
2. Uncertain service execution: cleaning, inspection, bounded recovery, human work
   and supplies retain finite resources, elapsed/progress observations, interrupted
   work, return commitments and post-work verification. Actual durations and future
   support events cannot enter a decision before observation. Public bounds govern
   reservations; a bound is an assumption, not a field guarantee.
3. Recorded beliefs: observation error, evidence age, duration censoring, conditional
   reliability, ambiguous causes and unsupported observations remain explicit.
   Estimates never become calibrated probabilities merely by being updated.
4. Joint planning: declared weather/service outcomes, nonanticipative current
   actions, charging and obligations, terminal reserves, expected/downside objectives,
   conditional information actions and feasible fallbacks. Report unsuccessful cases.

Across all gates: preserve original illustrations, quiet UI, old archives, original
information alternatives, independent numerical checks and offline reports. The
existing constrained planning and inspection mechanisms are reused. No unsupported
repair capability, empirical calibration, real-plant safety or global optimality is
claimed. Detailed implementation decisions and evidence are recorded below.

## Work record

- Inspected the current execution, resource, planning, observation and archive ports.
  Existing scenario MPC already enforces shared decisions and supports expected /
  worst-branch objectives. Existing inspection/recovery machinery remains applicable.
  The first integration gap is private service timing versus public reservations and
  observed execution cursors; solving a future independently would leak information.

Implemented: bounded private phase clocks across the first service system; current-only support events; censored and versioned duration/completion evidence; bounded surface/reference observations; joint finite-outcome work, charging and process planning; original-information snapshots; independent offline checking and reports; explicit Studies controls.

The controlled programme retains every immutable edition, including unsuccessful attempts. The first execution exposed interruption histories that could forget an earlier distinct observation. The scenario validator rejected those branches; no invalid incumbent was applied. History labels now retain the observed job and availability boundary, with a dedicated live optical-controller regression.

Acceptance is reported in `research/uncertainty-autonomy/report.html`, including original programme identifiers, source identities, tests, numerical variability, solver limits and uncompleted work. This design note does not predeclare a policy advantage or field calibration. The complete source is frozen before each qualification; later reporting does not change its decisions.

Remaining model boundaries are documented in [uncertain-service-system.md](uncertain-service-system.md): conservative shared-visit/stranding predictions, finite assumed scenarios, persistent world factors rather than measured job variability, and the paused later hardware/degradation programme.
