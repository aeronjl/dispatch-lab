# Computation stability before controller rankings

The saved-source reproduction of the scheduled-recovery reference changed applied actions in 23 of 24 cases. Per-case methane differences ranged from −40.4761 to +36.1703 kg; the forecast-overestimate comparison changed sign. All independent audits passed. The corrected rule-based support reference reproduced all 42 applied-action traces and methane totals. Source editions, inputs, outputs and qualifications are preserved in the Studies publications; these are separate claims from empirical validity or bitwise archive equality.

The immediate investigation sits inside the field-operations programme. It does not replace the six-stage scope. Hardware expansion and confident comparative claims should wait for an understood computation envelope.

1. Capture the first differing decisions from both executions, including estimated state, forecast, model matrices, objective, solver settings, native termination, primal/dual values and candidate ordering. Compare the model inputs before attributing differences to the optimizer.
2. Repeat those exact decisions in isolated processes with fixed thread settings and reported CPU competition. Keep the scientific problem fixed. Separate the process solver, recovery candidate enumeration and service supervisor's total wall-clock budget. A faster cost projection can change how many candidates fit that budget.
3. Compare existing short time limits with larger limits and a bounded node-work policy. SciPy exposes node and time limits separately and reports node counts, incumbent values and bounds. Its native status 1 covers iteration or time termination, so adding a node limit also requires honest termination labels. [SciPy MILP reference](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.milp.html)
4. Keep a wall-clock watchdog for responsiveness and cancellation, but report its intervention separately from a scientific work limit. Test node limits; do not assume they guarantee equal trajectories across versions or architectures. Preserve the exact bundled solver and environment. Check the supported options against that installed build before using upstream options. [HiGHS options](https://ergo-code.github.io/HiGHS/dev/options/definitions/)
5. Compare equivalent feasible solutions without confusing equal objective values with equal actions. Stable objective tie-breaking must be explicit, versioned and bounded so it cannot silently displace the primary objective. First-action variability, optimality gaps and downstream production differences are different measurements.
6. Run repeat complete trajectories and matched policy pairs on a small declared case set, including normal operation, repair, forecast stress and failed support. Publish every execution, computation budget, failure and fallback. Report variability within a policy alongside differences between policies. Then choose the default evidence-run configuration on measured stability and runtime; keep faster interactive settings visibly distinct if necessary.

The existing `methane/solver_study.py` provides a starting point for same-information formulation comparisons. Extend its scope rather than creating a second unconnected reporting system. Existing preserved runs are never silently recomputed, and a new computation policy requires a new study edition.

This is a prospective investigation, not an implemented deterministic solver guarantee. No single repeat or arbitrary zero-tolerance action-equality test establishes a generally reproducible MPC experiment.


## First checked investigation

The [80-trial report](../build/engineering/computation-stability/report.md) finds exact schedule repetition within every fixed-problem/budget group. Four original-source problems reconstruct equal matrices and objectives across their paired archives. Two short-budget problems have large objective gaps which narrow at longer limits without changing incumbents. Every converged problem processes only one node; no trial binds its node limit. These findings do not establish a deterministic computation policy or stable whole trajectories. Production defaults remain unchanged.

The next protocol is saved in `build/engineering/computation-stability/trajectory-protocol.json`. It holds seed 7 and each complete physical configuration fixed, using three repetitions of each of two recovery policies across four conditions. Separate 72-hour editions use per-solve limits of 0.15 s and 2 s (24 cases each), with 12-hour horizons. Repetitions are execution labels, not additional stochastic samples. Their complete configuration/policy identities were checked equal before creation. The recovery planner's per-candidate budget is distinguished from a total decision deadline. The first editions were later withdrawn for the recording collision below; verified replacement results follow.

The solver adapter is a fresh-process interface. A full-suite test exposed an invalid test which called the one-thread solver inside a process with an already initialized native thread scheduler; the solver correctly returned an error instead of an incumbent. The corrected independent-optimum test uses the actual isolated worker. This reinforces the process boundary and does not invalidate the 80 isolated trials. The failed test output is retained under `first-test-attempt/`.


## Archive-preservation finding

The first two full-trajectory editions are **withdrawn**, after 10/24 and 16/24 case references failed recording-identity checks. Identical physical run IDs shared a filename and overwrote distinct recording metadata within an attempt. Their automatic summaries remain historical observations, not complete reproducible evidence. The 80 isolated matrix trials are unaffected. A 33-edition/1,574-reference scan found no other conflicting-path editions, without certifying every artifact or reconstructing unindexed standalone history.

The [preservation write-up](../build/engineering/archive-preservation/report.md) records the cause, scope and correction. New writers preserve recordings and exports, and publication now checks recording identities. Replacement editions must use a new captured source and pass the publication gate. No original archive or publication is rewritten, and missing records are not reconstructed.

## Verified full-trajectory repeats

All 48 replacement recordings passed publication checks. At 0.15 seconds, four of eight policy/condition groups vary materially; the largest within-policy methane range is 33.3929 kg. A normal-operation apparent advantage occurs with no recovery tests, so it cannot be assigned to a recovery intervention. At two seconds every tested group repeats requested and applied actions within 0.0001 across three executions. The scheduled-policy methane difference is 0 kg in normal operation, +4.3582 kg after the latched trip, −74.9653 kg under permanent damage and −7.1030 kg with forecast overestimate. One seed and three numerical repeats do not establish a general ranking or cross-platform determinism.

Reviewed append-only interpretations are `5fdbbccba2b2497ea09cd3e1407ad388` (0.15 seconds) and `9065c54db7a448eea30fb0cc1e739aeb` (two seconds). They explicitly clarify that the earlier bug overwrote recordings, while the replacement process preserved surviving originals and withdrawals. The full comparison is `build/engineering/archive-preservation/replacement-comparison.json`.

The next priority is the [ambiguous-capacity ablation](ambiguous-capacity.md). A measured partial-load discrepancy can reduce the working estimate below minimum load, interacting with the recovery retry period. This observation motivates a controlled rule comparison; it does not establish that holding capacity always helps or explain the entire between-policy production difference. Production defaults remain unchanged.
