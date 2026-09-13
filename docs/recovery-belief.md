# Uncertainty after attempted repairs

The opt-in `observed-service-investigation/3` policy carries an incident belief through actual work and subsequent observations. It extends version 2's bounded follow-through. It does not replace the operating observer, make the plant's true fault state available to the controller, or establish calibrated failure probabilities.

## What the controller receives

`observed-recovery-belief/1` receives the incident's declared hypotheses, the capacity estimate when the incident opened, configured measurement assumptions, and observed work descriptors. Each work descriptor contains only an order identifier, action and actual work-completion time. It has no successful-repair field. Work completion becomes eligible at the next hourly decision boundary and can precede the crew's return. The separate joint scheduler still waits for the complete work/return prerequisite before authorising a load test.

Referenced fixed/mobile contact packets retain their signal, zero and span operands, measurement time, availability time and reader identity. A complete packet is admitted only within the original evidence-age limit. Its later age does not erase already acquired evidence. Re-reading the same packet does not multiply the evidence, and modifying its original operands or publication time is rejected. A delayed packet conditions the earlier physical state, then propagates through already observed procedures. Previously recorded decisions remain unchanged.

The power channel comes from the existing post-service evidence adapter's explicit observation allowlist. Only an informative load test that was resource-feasible under its recorded estimate contributes a power likelihood. Insufficient activity, known isolation and insufficient resources add no health evidence. Independent inventory-balance checks remain separate; this filter does not pretend that power and inventory form a calibrated joint sensor model.

## Declared mechanics and assumptions

The registered incident hypotheses are a resettable latch, equipment damage, and equipment damage with a separate stuck contact. Each may include static fixed/mobile reader offsets or dropout. The filter adds unrestored/restored states to each hypothesis.

- A reset moves only the resettable-latch probability toward restored operation, using the configured compatible-procedure reliability.
- A module replacement can move any remaining impaired state toward restored operation. An already restored module stays restored within this incident model.
- Replacing the module does not repair a separate stuck contact or faulty reader. A closed contact after replacement can therefore coexist with evidence of successful operation.
- Informative power follows the existing nonnegative multiplicative Gaussian measurement model. Predicted delivered power is the smaller of requested power and the state's declared capacity, with the existing minimum-load boundary. The impaired capacity is a point estimate frozen when the observed incident opened.

Assumption identifiers are `assumption:illustrative-contact-investigation/1` for the default incident prior, the saved inspection-model identity for reader thresholds/noise, and the original run's field-operations configuration for procedure reliability. These are illustrative hypotheses, not learned incident frequencies. Additional failure, degradation and time-varying reader drift within the same incident epoch are outside this model.

Contact likelihoods use the declared finite midpoint quadrature over the reader's bounded noise, with its point count recorded. Power uses a probability mass at clipped zero and a density in 1/kW for positive noisy readings. These different likelihood measures are explicitly labelled. With noiseless measurements the supported values are point masses. No invented variance or probability floor is added.

Calculations retain logarithmic probabilities. A displayed probability can round or underflow to zero while its internal support remains possible; later contradictory evidence can restore its weight. Explicitly impossible states remain distinct. An observation outside all declared support leaves the posterior unavailable. An observed intervention without its original descriptor also leaves it unavailable. Neither case silently renews the prior.

## What the belief may change

After the existing repeated, resource-feasible tracking shortfalls support further work, version 3 additionally compares the conditional impairment probability with an editable threshold, initially 0.5. This can permit or defer another compatible qualified intervention. An unavailable posterior requires escalation. The original deadline and attempt limits remain in force. An actually interrupted mission retains its existing bounded retry path.

The probability cannot upgrade the operating capacity estimate, authorise an incompatible remedy, ignore shared resources or confirm recovery. Consecutive actual electrical and independent balance observations still determine operating confirmation. A historical follow-up decision retains its hour, preceding order and original belief identity; the UI labels that historical context rather than presenting its older probability as the current belief.

Advanced experiment setup reveals the new policy and threshold. The existing version-2 default is unchanged. The Site services inspector shows a compact probability and assumption summary; complete operands and event histories remain in the original decision record. Main plant and solar artwork is unchanged.

## Verification and preservation

`methane/recovery_belief_reference.py` is a standalone standard-library checker. It independently reconstructs contact classification/quadrature, Gaussian likelihoods, procedure transitions and Bayes arithmetic. When checking a run, it also binds the saved operands to original public work events, reader packets, operating observations and frozen policy assumptions. Admitted load tests are checked against the separate hourly physical reference. New portable bundles include this checker; older numerical source and archives retain their original identities.

Independent examples include exact rational Bayes updates, a stuck contact across module replacement, Gaussian tail probabilities and recovery of an underflowed display probability. Integration checks cover an actual reset, failed operating evidence, qualified replacement, separate eventual observer confirmation, future-weather separation and tampered original operands. Passed arithmetic checks establish consistency under the declared model. They do not establish probability calibration, safe real-plant operation or a superior service policy.

This is a usable addition to the coordinated-planning stage. Calibrated uncertainty, richer incident dynamics, investigation-strategy alternatives, full service learning essays and comparative policy evidence remain separate work in the six-stage programme.
