# Repeated computation before policy ranking

The `field-computation` Studies protocol asks whether declared computation budgets change the recorded operation of the same plant. It follows the investigation-continuation examples: independent numerical reruns reversed both paired methane rankings under finite solver limits. Those original recordings and reruns remain preserved. This protocol tests that uncertainty directly before using the rankings to select a service policy.

Open **Simulation menu → Studies → New study** and select **Does the computation budget change the result?** Preview shows the number of distinct cases, unchanged-seed repetitions, and all three calculation budgets. The reference edition executes 36 cases: two fault conditions, two policy packages, three budgets and three repetitions of seed 7. Repetition is a computation trial, not another draw of weather or equipment noise. Runs use the existing sequential, single numerical thread worker. Budgets are interleaved in a declared fixed order within each repetition; individual cases do not get a fresh worker process. A source-restored new edition tests a separate execution.

## What stays fixed and what changes

The two packages retain separate versus joint post-service testing and their original investigation, charging and continuation semantics. They are a package comparison, not a one-factor test of timing. Matched cases share the configured plant, physical fault, environment, observations and exogenous random channels. The constant-DC fixture supplies hourly mean electricity at 75% of the array nameplate and 20°C. It is explicitly a dispatch fixture, not measured weather or a test of solar orientation, clipping or weather uncertainty.

| Budget | Process limit | Service comparison | Investigation comparison |
|---|---:|---:|---:|
| Workflow | 0.15 s | 0.5 s | 0.5 s |
| Process 2 s | 2 s | 0.5 s | 0.5 s |
| Joint 4 s | 2 s | 4 s | 4 s |

These are independent limits. An outer comparison can stop before all candidate schedules have been evaluated even when a process solve reports optimality within tolerance. Raising the process limit while leaving an outer budget small can therefore make less outer work finish. Candidate caps and model assumptions stay declared and unchanged. The highest listed budget is not called a converged or globally optimal reference.

**Repeat on active plant** uses the existing complete-basis resolution rules and saves every change. Increasing solar nameplate scales this explicit DC fixture; it does not calculate a new irradiance-to-power conversion. Capacity and policy changes make a new edition. Existing reports keep their original inputs and attempts. The sensitivity tier additionally uses three seeds, longer windows and a smaller battery; it is a separate evaluation, not an automatic promotion of the short reference finding.

A basis with an explicit solar conversion design or optical section model is incompatible with this constant-DC fixture. Preview explains that boundary and leaves the selected plant untouched. Such a study needs a separately declared weather/conversion protocol; this one never removes the design or silently substitutes another generation model.

## What is checked and preserved

Every executed case seals requested and applied actions, physical state, numerical diagnostic estimates, public work history and original solver/candidate records with its source, weather and numerical-input identities. The report’s compact repeatability packet must equal its archived original at publication, reuse and portable checking. No replan or later weather is used to reconstruct it.

The qualification table groups the same condition, plant variant, seed, policy and budget. It requires every declared repetition and every interval, equal recorded input identities and finite numerical operands. A cancelled, failed, missing, mismatched or shortened run cannot appear stable. Numeric fields are compared separately in their native units using the protocol’s absolute tolerance; the maximum difference is a diagnostic across fields, not a physical norm. Public work-order histories are compared exactly. Numeric equality covers those recorded fields only; it does not mean that every candidate search, log or runtime was identical.

Repeatability and solve quality are separate findings. **Stable in sampled repeats** does not prove determinism, optimality, calibration or reliable policy ranking outside those cases. Methane and allocated-cost ranges preserve variation. Time-limited solves, gaps, fallback use, omitted candidates and ending inventories remain available rather than being removed from averages. Outer comparisons retain their original exclusions. The same distinction applies if all process solves happen to meet their requested tolerance.

## Publication and interpretation

Run, cancel, resume, inspect a case, trace an outcome and download an offline bundle through the existing Studies workflow. A user-facing interpretation is attached to the exact report revision after execution. It should explain observed variation, original solver limitations and terminal conditions, and distinguish computation repeats from environmental evidence. It must retain unsuccessful and incomplete cases. A different publication never silently replaces the original attempts.

The portable checker requires only the Python standard library and checks file integrity, independent physical/accounting balances, and equality between the published computation packet and the sealed original. These checks do not authenticate a third party’s source or establish real-plant performance. Numerical reproduction uses the captured implementation and saved weather to create another edition; it may produce different valid decisions. That difference is a result of this experiment, not a reason to overwrite the recording.

The protocol is defined in [field-computation-v1.json](studies/field-computation-v1.json). The general preservation and execution rules are in [Studies](studies.md). This qualification advances the existing field-operations programme; it does not replace the broader weather, support, terminal-condition, degradation or held-out policy experiments.
