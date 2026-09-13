# Uncertainty is part of the model contract

Every one of the 407 registered parameter paths across 19 mechanism groups now has an explicit uncertainty status. Optional hardware and support systems remain in the catalogue even when absent from the active plant. This is a coverage contract, not a claim that the parameters are calibrated.

Use **Simulation menu → Studies → Explore uncertainty**. Search the active parameter catalogue, attach explicit support and evidence, select controller knowledge, and preview the resolved worlds. Registered stress tests provide an existing, explicitly uncalibrated starting point. New physical parameters, prices, service assumptions, policy settings and supported model alternatives use the same workflow. Parameter inspection and Model reference pages show the uncertainty status without adding controls to the plant illustration.

## What a parameter means

- **Unquantified:** uncertainty is relevant but adequate support is missing. It remains visible when held fixed.
- **Scenario values or bounds:** plausible or illustrative cases with an authored rationale. Their results have observed ranges, not probabilities or confidence coverage.
- **Explicit probability:** a uniform or triangular law, weighted discrete rows or a joint empirical sample with declared evidence and applicability. Probability is conditional on that choice, not conferred by the software.
- **Selected choice:** design and policy settings are choices. Compare them without calling the choice a calibrated fact.
- **Model choice / fixed convention:** implemented model identities and accounting conventions are explicit. Omitted kinetics, gas quality, pressure physics and robot capabilities cannot be manufactured by adding random parameters.

Sources, ranges and assumptions are kept distinct. Reference defaults do not imply a distribution. The existing hourly physical kernels still enforce balances, operating limits and feasible execution for each realization.

## Worlds, events and computation

The versioned `dispatch-lab/uncertainty/1` specification defines:

1. Persistent world parameters, grouped into dependent blocks. Joint rows are selected intact. Random streams are keyed by block identity, so reordering blocks or adding a different block does not perturb existing draws at the same budget.
2. Inner event seeds. A world is held constant while each event seed supplies the existing weather, sensor and service random mechanisms. Controllers share the world and random channel keys. Usage-dependent work or failure exposure can still differ because the policies act differently.
3. Numerical attempts. A fresh solver run is a new numerical attempt, never another weather sample. Frozen-source study workers, solver budgets, cancellation, resume, integrity checks and immutable publications are reused.

Space-filling scenarios stratify each block and pair block rows reproducibly; they do not assign a probability to outcomes. Factorial designs enumerate the entire declared grid and reject an insufficient world budget. Screening holds all other blocks at their nominal values and changes one dependent block at a time. Probability mode requires explicit distributions; bare bounds and unweighted scenario values are rejected. Between-block independence is an assumption. Correlated factors must be represented jointly.

Actual resolved draws, controller inputs, source identities and event seeds are saved before solving. Seeds alone are insufficient provenance. Configuration violations remain **invalid-input** cases, without clipping or replacement draws. Runtime failures, cancellations and missing weather remain visible and are excluded from complete-case calculations with explicit denominators.

The UI supports ordinary scalar scenario/bounds editing, all observation channels and import/export of complete specifications. Joint rows and probability weights can be authored/imported together. Existing optional systems must be enabled through experiment setup before their parameters are sampled; uncertainty exploration does not enable hardware.

## Controller knowledge

A realization records separate physical and controller configurations. Hidden execution is implemented for battery/thermal/electrolyser/material performance and capacity assumptions, original-versus-actual costs, sensor noise and injected fault assumptions. Planning uses the original controller model; execution uses the physical model. Fault onset, severity and recovery information remain confined to physical execution. Current measured power and observed state may legitimately change a decision.

Initial inventory follows the physical world and is observed. It is therefore not secret perfect state when an observation model is enabled. Raw readings remain recorded; inventory estimates are projected to the controller's declared storage boundaries. The projection is an estimator assumption, not a measurement correction or a calibrated posterior.

**Selected solar conversion and service outcomes now support hidden execution:** reference conversion loss/NOCT/temperature coefficient, detailed-converter efficiency/NOCT, cleaning removal, mission failure and procedure reliability. Fractional service contracts must be enabled. The [observed-performance release](observed-performance.md) adds optional recorded or adaptive solar/cleaning estimates. Service durations, logistics, other weather-model settings and unsupported hidden paths remain rejected; they can still be varied as **disclosed assumption comparisons**. This boundary is visible in the editor and reports; these tests must not be described as robust control with unknown service dynamics. Robot repair capability is unchanged. Unsupported model identities cannot pass configuration validation.

Same-information what-ifs and numerical recomputation retain original controller assumptions. Repricing preserves the physical trace and original dispatch prices, while reporting the explicitly selected accounting prices. Changing dispatch assumptions requires a new run.

## Observations and diagnosis

An optional versioned additive error model covers electrical power, hydrogen flow and inventory, hydrogen withdrawal, battery energy, CO₂ inventory and reactor temperature. Channel units appear in the editor and records. For channel c and interval t:

`reading(c,t) = existing reading(c,t) + bias(c) + elapsed(t) × drift_rate(c) + noise(c,t)`

Bias and linear drift rate are sampled once per device/channel; noise is independent per reading. Their standard deviations and source are public; their actual sampled values are retrospective truth. The Gaussian and channel-independence assumptions are explicit. Existing multiplicative sensor noise remains active and is not silently replaced. These error budgets are not a full Bayesian state estimator.

Diagnosis uses independently propagated additional error budgets. Persistent inventory bias cancels from successive-reading mass balance; reading noise contributes twice and persistent drift contributes over the elapsed difference. The added budgets combine in quadrature with the existing relative-noise proxy before the discrepancy floor is applied to electrical/balance/flow thresholds. The original throughput-based noise abstraction remains an approximation. Low activity still means insufficient evidence. A standard-library Decimal calculation independently checks this propagation in the bounded diagnosis/recovery audit. Configured limits still supply the baseline threshold.

## Conclusions and evidence priorities

Every report lists paired outcome differences, including methane, costs, contribution, curtailment, starts, downtime, diagnostic outcomes, solver limitations and ending energy/material/thermal inventories. All three controllers run in each complete case. Undefined metrics remain missing; a zero-output unit cost is not invented.

Outer-world means require every inner seed to be complete. Complete-case extrema and denominators remain available even when a world is incomplete. Probability mode also computes conditional finite-sample quantiles; these are not confidence intervals. Screening reports the matched change in controller advantage from each block and flags ranking reversals. This is a measurement-priority screen, not a global Sobol decomposition or a monetary value-of-information calculation. Joint scenario studies are needed to test interactions and decisions under combined uncertainty.

Reports enumerate uncertain active assumptions that were held fixed. Failure frequency, repairability and observation quality remain evidence gaps where no equipment-matched data supports a distribution. A useful finding can be that a conclusion reverses; tests do not require MPC to win.

## Calibration samples and preservation

`docs/uncertainty/supsi-reference-ensemble-v1.json` retains all 80 joint day-bootstrap replicates of Faiman U0, U1 and effective NOCT from the existing literature-calibration dataset. The original research outputs remain unchanged. The new ensemble identifies its source hash, fitting script, split, units, dependence and excluded uncertainty. It quantifies conditional sampling variability at one site/module; it excludes systematic metrology, transfer and model discrepancy. Faiman is not a production model input in this plant. Do not transplant its coefficients into unrelated parameters. Reproducing the fit requires the identified cached research data; replaying saved samples is offline.

New run archives capture an uncertainty snapshot once per run. Legacy archives keep missing original uncertainty explicitly missing. Human-readable catalogue reports show original knowledge boundaries and drawn values; study publications, complete specifications, draw matrices and original controller configurations are preserved in reproduction bundles. Frozen source capsules include these contracts and saved reference samples.

## Validation

`tests/test_uncertainty.py` checks complete catalogue coverage, optional systems, concrete array paths, joint dependence, stream invariance, explicit probability requirements, invalid worlds, observation timing and independent error propagation, hidden-parameter/future-information causality, physics reconciliation, what-if immutability, paired reports, resume, reproduction and exports. Browser checks exercise the editor, preview invalidation, return navigation and narrow screens. Existing physical, study, evidence, cost and documentation checks remain applicable; no new empirical validation is claimed.

The broader basis is the [BIPM GUM uncertainty framework](https://www.bipm.org/documents/20126/194484570/JCGM_GUM-1/74e7aa56-2403-7037-f975-cd6b555b80e6), [NIST guidance on Type B assignments](https://pml.nist.gov/cuu/Uncertainty/typeb.html), and [JRC sensitivity-analysis methods](https://joint-research-centre.ec.europa.eu/sensitivity-analysis-samo/methods_en). These guide the distinctions; they do not validate our parameter choices.

Source review for this increment: the original deterministic physical equations and plant artwork remain unchanged. The added execution/controller split, observation error propagation, schema-3 study resolver, metadata and pricing/replay paths were reviewed together. The comparison fixture `field-computation-v2.json` explicitly records a previously missing inactive nullable assumption in its configuration and policies; its original revision and saved editions are retained. Missing-versus-present-null configuration differences are now reported explicitly. Weather retrieval is frozen per identical weather-input set within an uncertainty edition, including across forecast publication boundaries, and detailed solar conversion is saved before execution so its original inputs can be verified on resume.
