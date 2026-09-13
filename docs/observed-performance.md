# Observed performance: bounded autonomy release

Version `observed-performance/1`, 13 September 2026. This release implements the agreed next example, not the remainder of the paused six-stage hardware programme.

## What changes

In **Studies → Explore uncertainty**, selected conversion and service outcome parameters can keep their original controller assumptions while physical execution uses the sampled values. Choose **Record estimates without adapting** or **Adapt solar and cleaning estimates** under Learning from observations. The latter changes later forecasts and service planning from observations. Turning it off retains the original path unless hidden conversion/service draws require the separated fixed-model adapter.

Supported hidden paths are `weather.loss_fraction`, `weather.noct_c`, `weather.temperature_coefficient`, `solar.efficiency`, `solar.noct_c`, and `field_operations.cleaning_removal_fraction`, `field_operations.mission_failure_probability`, `field_operations.repair_success_probability`. Existing hidden plant, sensor, cost and fault paths remain available. Selected service outcomes require enabled fractional contracts. The same validation applies to direct numerical execution, not only the editor.

**Durations, support logistics, weather publication assumptions, section geometry and unsupported capabilities remain disclosed or rejected.** This example uses ineffective or interrupted service, rather than introducing a private overrun schedule that a planner could accidentally see. The thermal, electrical, material, resource and cost kernels are unchanged.

## Information and observation contracts

Execution retains actual conversion parameters and private effect-port probabilities. Forecast issue dates, availability boundaries and raw irradiance remain saved. Only eligible forecasts are transformed using the original controller's conversion parameters. Current hourly mean power, irradiance and ambient temperature are assumed observed under the existing hourly abstraction. Weather forecast error and conversion mismatch therefore have separate inputs, although imperfect real weather sensors would make their causes ambiguous.

Optical cleaning uses the existing explicitly ideal patch monitor. The planner sees measured surface state and ongoing-pass efficacy derived from its declared pre/post monitor readings; it no longer copies the private efficacy parameter. Every estimate names this ideal sensing assumption. An equipment-matched measurement chain is still required for calibration. No new robot repair capability or sensor modality is implied.

Service work completion is not successful-repair truth. The existing operating observer and post-service verification still establish recovery. Private mission/procedure outcomes are not passed to the performance estimator. Duration, reliability and incident-frequency learning are deferred; hidden probabilities test the existing controller's response to observed failure, not calibrated probability adaptation.

## Estimator mechanics and limits

The solar rule divides observed available generation by nominal conversion under contemporaneous observed irradiance and temperature. Starting at 1, after two informative intervals it applies `estimate += 0.35 × (observed_ratio − estimate)`. The default informative threshold is 30 kW nominal generation; supported ratios are 0.1–2. These are illustrative editable identification assumptions, not fitted confidence limits. Out-of-support readings remain visible and do not reset or clip the estimate. Low generation means insufficient evidence. Fixed mode records the same evidence but leaves the persistent model unchanged. Future generation uses the recorded multiplier; current observed generation is never replaced by a prediction. The synthetic forecast's current-weather correction is applied separately, avoiding a double correction for conversion error.

For lumped cleaning, the observed pre/post surface loss, known accumulation and completed passes give `removal = 1 − ((after − accumulation)/before)^(1/passes)`. For section cleaning, integrate observed removed optical loss over reported treated area, divided by pre-treatment loose loss and the disclosed brush allowance factor. Saturated patches and portable treatments are excluded from this inverse estimate. A qualifying reading updates expected removal with the same gain. Partial readings from the same pass are correlated updates, not independent trials. Actual effects continue to use the original private execution parameters throughout the run.

These are bounded point-estimate adaptations, not Bayesian posteriors, unique diagnoses, probabilistic forecasts, robust MPC or safe real-plant controllers. Reported observed ranges have no confidence interpretation. A biased irradiance/surface sensor can mislead the estimator. Out-of-support events identify a model gap; a new automated escalation policy is not implied.

## Interaction, recording and reproduction

Solar calculation details and other components' Why views show the original expected/measured generation and multiplier change. The service inspector shows measured removal, revised expectation and its availability hour. The event strip links estimate revisions and unsupported solar observations. Main illustrations and labels are unchanged.

Every decision saves original estimator assumptions, operands, evidence status and before/after values. Service updates become available at the next decision boundary. Original dispatch prices stay frozen; what-ifs retain the selected original forecast and state. Studies keep draws, configuration, source, solver budgets, seeds and failures. New bundles include `performance-estimates.html` and an independent standard-library Decimal recurrence/timing checker. Neither opening the report nor recorded playback requires a network.

Validation covers independent arithmetic, physical conservation, hidden outcome separation, future-information causality, fixed/adaptive ablation, invalid adapter requests, original-information replanning, archive replay and interface operation. A benchmark is a workflow demonstration under disclosed assumptions, not a field-calibrated hardware ranking or a claim that adaptation always helps.
