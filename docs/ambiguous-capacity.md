# When measurements disagree

The optional `sensors.ambiguity_policy = "retain-capacity/1"` changes one response in the existing observer. When an informative request produces disagreement between the independent hydrogen inventory balance and the electrical estimate of hydrogen flow, it keeps the preceding capacity estimate and reports ambiguity. It does not establish health, identify the faulty channel, confirm a new incident, or restore capacity. Future operating requests still pass through the plant's physical feasibility checks.

The original `reduce-capacity/1` rule remains the default. Its serialized omission preserves existing complete configurations and study protocols. It reduces capacity to the lesser of the preceding estimate and measured power multiplied by one minus the discrepancy threshold. The new rule is selectable in advanced experiment setup and in the separate diagnosis learning example. Completed recordings, their original explanations and numerical-rerun inputs retain their original policy.

## Why compare these rules?

In the verified two-second computation study, a scheduled-recovery case requests and delivers 135 kW at hour 19. Its electrical meter reads 137.6666 kW. The inferred hydrogen flows are 2.2050 kg from inventory balance and 2.5030 kg from electricity. Their disagreement exceeds the configured threshold. The original rule therefore reduces the capacity estimate from 218.2811 to 123.9000 kW, below the 135 kW minimum load. The scheduler is awaiting a later recovery probe; the process cannot run ordinarily at that estimate. This explains an observed idle interval, not the entire difference in whole-run methane between recovery policies.

The trace is preserved in `build/engineering/archive-preservation/ambiguous-capacity-trace.json`, from edition `963a96023b9249dab282657de7c384db`, case `b3d32e83d443a2b52c35b60d`. Interpretation `9065c54db7a448eea30fb0cc1e739aeb` distinguishes this observation from a causal whole-run claim. The earlier archive collision and its withdrawals remain separate, explicitly documented findings.

## Deliberately narrow ablation

Neither noise draws nor sensor equations change. The fractional discrepancy threshold, throughput-scaled inventory noise, informative-load threshold, consecutive confirmation counts, flow-channel isolation, recovery tests and recovery scheduler remain identical. The observer still receives only declared parameters, preceding diagnosis, current/prior observations and the actual requested test context. Simulator fault type, true capacity and future restoration time are not inputs.

The comparison does not improve uncertainty calibration or independently distinguish every resource-limited request from a physical capacity fault. In particular, the original tracking counter can accumulate during ambiguous intervals; this ablation retains that behavior. Separately changing counter semantics, propagating noise through successive inventory readings, treating sensor saturation or conditioning diagnosis on independently observed resource limits requires another declared comparison. Holding an estimate can also retain an overestimate. The experiment must retain failed tests, corrected execution and unresolved work rather than assume this choice always helps.

## Prospective experiment

Use the already declared 72-hour recovery fixture, 12-hour horizon, two-second per-solve limit, two recovery policies and four conditions: normal operation, latched trip, permanent module damage and forecast overestimate. The primary comparison uses three numerical repeats with physical seed 7. Create separate old-rule and hold-rule editions from the same captured implementation. Exact configuration differences must be limited to the ambiguity policy, with identical exogenous seeds, forecast snapshots, policies, hardware and prices. Compare each observer within a recovery policy, then compare recovery policies within each observer. Repeats measure computation variability, not additional weather or reliability samples.

Report methane, costs, starts, curtailment, ending plant/service inventories, requests versus applied load, recovery tests, unresolved work and diagnostics. Count informative ambiguous intervals, newly lowered estimates below minimum load, time held below that minimum and electrical tracking shortfalls. A later multi-seed sensitivity is required before promoting a default. No improvement or general solver determinism is required.

## Verification scope

Independent decimal arithmetic checks the minimum-load counterexample. Other tests preserve clear capacity/flow-fault confirmation, successful recovery, disabled diagnosis and low excitation; an input mutation check establishes that the observer does not alter source operands. Learning examples use fixture `dispatch-lab/learning/diagnosis/2`, preserving version-1 examples in old archives.

The dependency-free archive checker now verifies a necessary invariant for the hold rule: an informative interval whose balance disagrees beyond the numerical margin retains capacity, reports ambiguity and creates no new confirmed incident. It is not a full independent reconstruction of the observer or empirical validation of fault diagnosis. The scheduled-recovery checker still verifies its separate consecutive-evidence contract. Fabricated capacity reductions, healthy classifications and incident increments are rejected in the test fixture.

## Completed primary comparison

The primary 48-case comparison is complete on checked source `9f0e5d1cef46ea9477579a5b0f885ebb9fe06b0ebe1a6ec14e0b9666d3b434d8`. All recording identities pass publication checks and each policy/condition group repeats its actions within tolerance. The hold rule adds 71.5884 kg methane in the scheduled module-damage case, avoiding 19 decision intervals below minimum estimated load. The other seven groups have identical requested/applied actions across observer choices. Allocated cost rises €78.09 and assumed contribution falls €17.01 in the affected case; two more informative tracking shortfalls occur. The physical fault and unfinished work remain.

Reviewed reports are `b9e434a3c6724ac49249b5af1beae78a` (original rule, edition `3ce3986125ba4c01b0d282ea87875a71`) and `43e9ed2253db470fa180cb94d8dcb721` (hold rule, edition `4294142325fb42fc9848968e8591cba5`). The [comparison write-up](../build/engineering/ambiguity-policy/report.md) links their full records and reproducible derivations. This one-seed experiment supports a bounded causal account, not a general default change or empirical diagnosis claim.
