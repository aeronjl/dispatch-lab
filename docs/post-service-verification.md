# A repair still needs an operating test

## Coordinated verification episodes

New version-3 results report distinct post-mission windows opened, windows
expired, observer-confirmed windows and escalation intervals separately. Repeated
snapshots of one receipt-defined window count once. Escalation can occur before
any completed mission, so its interval count is not a count of failed repairs.
The legacy `recovery_deadline_misses` metric is undefined for these new version-3
results; it counted the earlier scheduler's `deadline-missed` state. Earlier
archives retain their original reported values. Dated research reports can add
explicitly identified derivations from their saved episode histories.

Recovery `scheduled-load-tests/3` is the opt-in completion of the bounded loop.
It uses the existing joint electricity, dock charging and test-window solver. A
whole-mission return and eligible receipt open a separate test window of
`maximum_wait_hours`. The original diagnosis and service deadlines stay recorded;
late repair does not retroactively satisfy either. A queued or active remedy
precedes verification rather than competing for its own test power.

Shortfalls and inconclusive tests consume the current window without imposing
the version-2 24-hour delay between individual observations. Distinct same-load
shortfalls must reach the sensor confirmation count before the loop waits for
the existing finite repair-follow-up rule. Inconclusive or ambiguous tests do
not justify another repair. No observed recovery by the verification deadline
leaves an explicit escalation, with no automatic rolling deadline. A separate
completed remedy may open a new recorded window. Ordinary service attempt limits
and retry delays remain in force; physical capacity still changes only through
the existing execution mechanism and observer.

The standard-library archive checker separately verifies receipt availability,
whole-return timing, window arithmetic, distinct evidence and immutable original
boundaries. These checks do not establish an industrially appropriate
deadline, empirical repair success, or real-plant safety. Versions 1 and 2 retain
their prior behaviour for older configurations and archives.

The opt-in `coordinated-services/3` policy extends the existing shared-visit controller with measured follow-up for completed, unverified electrolyser module substitutions. It is a usable part of stage 4; it does not complete the investigation supervisor or the six-stage field programme.

## Observed evidence and timing

`post-service-load-evidence/1` receives an explicit allowlist from the preceding interval: the actual requested actions, recorded starting estimate, current hourly PV/ambient/feedstock/service inputs, the probe flag and capacity estimate, and electrical/hydrogen observations. It never receives delivered simulator actions, fault capacity, repair-success truth or later weather. A result becomes eligible at the interval's ending hourly boundary.

The verifier recomputes the independent hydrogen inflow from successive tank readings and measured outflow. It compares that with measured power divided by the configured specific electricity consumption. The discrepancy threshold is the larger of the configured fraction or three noise standard deviations, as in the existing observer. A biased flow meter is retained as an operand but cannot defeat the independent inventory comparison. These are the existing bounded sensor assumptions, not a claim of arbitrary fault isolation.

Only an enabled probe above the previous capacity estimate can add shortfall evidence. The complete requested action must also be feasible under the recorded starting estimate, current power and registered production kernels at nameplate capacity. This check includes power, storage, gas and thermal limits. A blocked or resource-infeasible test is inconclusive. Disagreement between electrical and inventory channels is ambiguous. Supported tracking is evidence only at the tested load; it does not itself update capacity or certify the preceding repair.

The `bounded-post-service-followup/1` tracker only attributes tests that start at or after the hourly boundary following the **whole mission's completion**, including return. Fractional return at H4.25 makes H5 the earliest eligible interval start. Another intervention begins a separate attempt; its subsequent tests cannot be credited to the earlier procedure.

## A finite follow-up rule

The configured sensor confirmation count determines the required number of distinct shortfall tests. They must request the same load and lie within the service policy's original maximum-wait duration, used here as an explicitly declared evidence window. Intervening inactivity does not count as healthy operation or add evidence. An ambiguous, resource-infeasible or successfully tracking probe clears the qualifying shortfall sequence. Different test loads do not combine.

Once enough evidence first exists, the controller starts its configured retry delay. Further failed tests do not move that start time. After the delay it may create a distinct qualified substitution request, with fresh prerequisites, current evidence and a new crew-response lead. The old receipt stays unverified. A `followup_of` link and the evidence assessment identify why the new request exists. The original obligation deadline and total repair-attempt limit remain unchanged. An exhausted budget leaves an explicit unresolved escalation.

This rule does **not** conclude that the module caused the residual or that another replacement will work. It is a bounded investigative option. Repeated unsuccessful substitution can spend labour and parts without recovering methane production. A cause-aware investigation policy, condition transitions after service and value-of-information selection are still required by the roadmap.

## Interface and preservation

Select service scheduling version 3 in advanced experiment setup, alongside scheduled recovery tests, enabled sensors, complete service prices, finite logistics and shared visits. Versions 1 and 2 retain their original behaviour. The new policy is frozen in each run; it does not change an existing archive.

The revealed Site services pane adds a **Post-service load tests** disclosure. It shows the original interval, requested/measured power, independent balance, resource check, qualifying evidence and unresolved attempts. The full operand record and model identities remain available there. The main plant illustration and its labels are unchanged. Model → Controllers explains the rule and its limits.

Each interval assessment has an integrity identifier; each follow-up assessment retains the test references and original completion boundary. Integrity hashes detect changes, not authorship or scientific truth. Economic repricing reads the unchanged physical trace. A later observer confirmation may support current operation after another intervention; the follow-up history preserves the previous failed tests and their separate attempt.

## Reproducible operating examples

Run `.venv/bin/python -m methane.services.verification_examples` to save four 40-hour cases under a source-identified directory. The failed-procedure case and its version-2 baseline differ only in service-policy version. A successful-procedure sensitivity changes the declared procedure reliability from zero to one; a power-shortage sensitivity removes generation from H14. Every run retains its configuration, original forecast snapshots, actual observations, missions, costs, ending stores, incomplete recovery and solver limitations.

The HTML write-up links to recorded playback, the original Model report, full outcomes and a reproduction bundle. Another execution must use a new `--directory`; an existing output directory is refused before running any case so its links cannot accidentally point to an earlier output. The bundle includes captured source, an offline independent accounting checker and the numerical-rerun entry point. Recorded playback is immutable; a finite-time numerical rerun may differ and is recorded separately. These are workflow examples, not an annual installation-economics study or a claim that the new controller always improves performance.

Validation covers independent residual calculations, rejected tests at resource limits, bias/ambiguity, stale and duplicate evidence, return boundaries, failed and successful actual procedures, finite attempts, retained deadlines, no truth access, repricing, and disclosed UI evidence. These checks do not establish empirical reliability or complete model verification.
