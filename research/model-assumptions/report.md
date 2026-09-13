# Assumptions and evidence review — 12 September 2026

The platform-wide review is complete; empirical calibration remains open because there are no matched plant/service observations. All 407 reference parameter paths and 19 consequential mechanism groups are classified, including optional contracts. Existing physics defaults, repair capabilities, old archives and the paused programme queue are unchanged.

The most consequential gaps are reactor heat/operating assumptions, the electrolyser system boundary, unrealistic inventory metrology at low flow, implicit reference-PV clipping, omitted storage/compression loads and cause-specific repair capability. Literature benchmarks do not close these gaps.

The initial conditional study executed 45 controller trajectories (five joint profiles, three seeds, three strategies). An explicitly exploratory amendment adds 18 trajectories with slower/faster cooling. Outcomes, independent audits and all limitations are retained in the full report. Methane MPC/Greedy mean-output rankings reverse across profiles. 384 thermal cases passed independent integration checks. Nine European ten-day windows replayed offline; their cached data does not contain cleaning wind/rain channels. Fixed-trace repricing preserves recorded actions.

[Read the full report](report.html), [all trajectories](trajectories.csv), [parameter and mechanism registry](../../docs/assumption-review.json), [protocol](protocol.json), [review/source decision](review-decision.json).

In the app: Explore component → Assumptions → mechanism → parameter. Older runs require the labelled Current catalogue context. Current Model essays also include the scoped parameter review. New run catalogues capture the review once and reproduction exports retain it.

Next: choose a coherent reference equipment package; repair the observation model; acquire/fit reactor and electrolyser data with held-out validation. Keep capabilities without a named device/procedure explicitly conditional.
