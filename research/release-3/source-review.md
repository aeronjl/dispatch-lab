# Release 3 source review

14 September 2026. The control, coupling and experiment assumption-review bindings
are updated for the new source. Other mechanism bindings and empirical claims are
unchanged. Existing archives keep their original reviews.

- The policy contract adds a version-5, data-only registered deployment. Its input
  port selects contemporaneously available observations, estimates, prices and
  forecasts; it does not accept a physical runtime or injected fault schedule.
- The physical execution model is unchanged. A saturating reserve deficit changes
  the planning objective using nonnegative slack, so preferences cannot create a
  physical requirement under resource exhaustion. The execution solve does not
  apply these preference penalties.
- Learned PV inference may change forecast interval 1 only. It cannot change the
  contemporaneous mean-PV abstraction, increase a hardware capability or certify
  that a fault was repaired. Invalid/inapplicable inference retains the original
  policy. Optical service reforecasting rejects this scalar adapter explicitly.
- Known controller configuration is used when exporting hidden-uncertainty cases;
  the actual physical configuration remains separately identified as experiment
  metadata. Dataset adapter source and simulation source are both preserved.
- All current controller solver calls use one HiGHS thread. This corrects a
  reproduced legacy/current global-scheduler mismatch and bounds CPU concurrency.
  It is a new numerical source assumption, not a relabelling of old comparisons.
- Condition/surface readout prediction and completed-clock regression do not create
  new sensor identifiability or equipment calibration. Reserve weights, ridge penalty
  and model applicability are explicit policy/protocol choices. They are not
  calibrated equipment constants.

Verification receipts and the final source identity are recorded separately in the
release report. A reviewed explanation is not a passing numerical or field result.
