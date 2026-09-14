# What the checkpoint comparisons establish

These are numerical compatibility checks across two saved implementation identities.
They do not establish equipment calibration, field capability or a universal runtime.
The original receipts and as-executed scripts remain unchanged.

1. **The 24-hour continuation and timing check** (`checkpoint-comparison.json`) starts
   each implementation from the same saved checkpoint. It compares eleven selected
   field groups: hour, requested/applied actions, ending state, post-interval observations
   and diagnosis, lifecycle, complete field-operations data, CO₂ delivered/rejected,
   and forced-trip status. It also checks three shared-reference identities. The measured
   elapsed times apply to that experiment. This receipt does not compare every row key.
2. **The original-state comparison** (`source-comparison.json`, version 2) reads full
   period records and compares those same eleven groups for all 72 seasonal cases and
   the saved 1,337-hour annual prefix. Its first summary-only draft and correction are
   retained separately. Reading a full record does not itself check every field in it.
3. **The whole-record extension** (`complete-record-comparison.json`) compares every
   interval-record field and controller-specific retrospective truth for those same
   cases and boundaries. That includes original decisions and forecasts, curtailment,
   heat, water, component records, audit results and intervention accounting. Only
   `record.execution_solver.seconds` is excluded from equality; every pair of excluded
   wall-clock measurements is retained. Complete case inputs must also be identical.
   Its own completion and outcome flags determine whether this stronger check passed.

The report's completion gates require the intended programme and source identities,
not merely a passing boolean from another receipt. Offline preservation also requires
matching edition, source and bundle digest, all declared comparison counts and a passed
integrity/standalone check. `report-contract-check.json` exercises those predicates
with altered in-memory receipts; it never changes an experiment or an archive.

No check asserts equality of source provenance or archive bytes across implementations.
These are Greedy cases. They do not establish deterministic time-limited MPC decisions
or agreement after the saved original annual prefix.
