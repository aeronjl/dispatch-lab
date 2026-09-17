# Source-device reference experiments · edition 1

Open **Project → Equipment & evidence → Reference experiments**. This workspace
executes two named models against published reference devices. It is independent
of the project design and of whichever saved run was selected on entry. It does
not assign their fitted coefficients to the AEM electrolyser or generic reactor.

Choose the electrical boundary, signal and model form for the PEM example, or an
inspection time and digitization sensitivity for the reactor. **Run reference
experiment** fits and saves a new immutable result. Changed inputs clear the old
result; invalid input reports the violated domain. Reset restores the fixture.
The graph and numeric text use one Python response. Source mappings, full paired
points, uncertainty and evidence are revealed on demand. Escape restores the
originating workspace and focus. None of this changes the main plant artwork.

A saved experiment records the exact request, observations, mapping, source byte
hashes, fitted parameters, joint sensitivity vectors, predictions, discrepancies,
implementation identity and execution capsule. **Saved reference experiments**
opens original values without recalculating. A changed implementation or dataset
is labelled historical. **Save readable report** includes an editable interpretation;
**Export reference bundle** preserves the result, report and original implementation
capsule using the existing cancellable export workflow.

## CSU PEM power and hydrogen

The [Veatch, Windom & Zdanowicz dataset](https://datadryad.org/dataset/doi:10.5061/dryad.8931zcs64)
and its [author repository snapshot](https://github.com/HydrogenDude/ERCOT_Electrolyzer_Sim_Engine/tree/a534d8a89cf5e662f183d91a9b40b7936387c4a2)
supply one-second signals from a 60 kW-class NEL C-Series PEM system. The adapter
retains the original `hydrogen_flow` and `hydrogen_flow_cs` names. It does not
assume these establish independent calibrated net/gross meters. The experimental
measurements are distinct from the repository's larger simulated dispatch studies.
The source is a recently released dataset; peer-reviewed publication is not
established by this implementation.

`system_power = smps_power + subsystem_power + chiller_power` in AC kW.
`stack_power` is the separate DC stack boundary. Neither is the plant's DC bus.
Power command identifies consecutive segments; it is not substituted for measured
power. Retain positive-command segments lasting at least 900 seconds, omit their
first 120 seconds, then divide each into first and second halves. The first halves
are development; the second halves are evaluation. Their mean observations enter
with equal plateau weights. No residual-based filtering is performed.

The source contains 15,068 synchronized samples and eight retained long plateaus.
Compact records retain original row indices, counts, naive source timestamps,
channel means and excluded-segment reasons. The timestamp file does not specify a
timezone: the adapter does not invent UTC or resample into the hourly plant model.
Hash mismatch, missing/nonfinite channels or nonconsecutive timestamps fail visibly.

Two models use the same development samples:

- `csu-pem-affine/1`: `flow = slope × power + intercept`, ordinary least squares.
- `csu-pem-constant-specific/1`: `flow = slope × power`, least squares through zero.

Both report evaluation bias and RMSE in kg/h. Inspection is limited to the observed
power envelope for the chosen boundary; off, startup and scale-up extrapolation are
rejected. The observed and fitting envelopes are separately retained. Small endpoint
differences between paired development/evaluation power are not a new equipment range.
No negative predictions are clipped to conceal model behaviour.

The default whole-system / `hydrogen_flow` affine fit reproduces the earlier
research relationship: approximately 0.01505746 kg/kWh slope, −0.34851065 kg/h
intercept, and 0.01199274 kg/h evaluation RMSE. These are **same-device, same-day
checks**, with correlated adjacent samples and previously inspected data. They are
not independent equipment validation. Selection rules are inherited from the dated
research protocol; this new implementation is not a claim of blind preregistration.
Short commissioning/startup segments remain excluded, not fitted into a startup law.

## KIT controlled-coolant response

[Sauerschell, Bajohr & Kolb (2022), figure 8](https://publikationen.bibliothek.kit.edu/1000148877/149046930)
describes a slurry bubble-column pilot at 20 bar, with H₂ feed increasing from 20
to 40 m³(STP)/h, CO₂ adjusted at S = 1.05 and coolant inlet held at 310°C. The source
uses a 30-second ramp; this reduced model approximates it by a step at minute five.

Twelve manually selected points from the black temperature curve are retained
with their original pixel coordinates and mapping:

`time_min = (x − 174) × 40 / 365`

`temperature_C = 260 + (358 − y) × 80 / 224`.

The grey conversion curve is not temperature evidence. `kit-slurry-first-order/1`
fits `T = baseline + increment × (1 − exp(−max(t − 5, 0)/tau))`, with time in minutes.
Least-squares bounds are baseline 315–325°C, increment 5–25 K and tau 0.1–50 min;
initial values are 320°C, 14 K and 8 min. The fitted tau is about 9.2994 min and
in-sample RMSE 0.4898 K. All points enter this descriptive fit; held-out validation
is explicitly missing. Inspection stays inside the figure's 0–40 minute interval.
The curve does not predict conversion or identify independent thermal capacity,
coolant transfer, ambient UA or kinetic parameters. It is not a warm-up model for
the project reactor.

## Uncertainty and model choice

The workspace keeps four questions separate:

1. **Measurement:** no calibrated channel uncertainty is inferred. For PEM, an
   editable common flow-offset bound refits the model at both signed offsets;
   results at the query point are reported separately. Zero means no offset
   sensitivity assessment. This scenario omits power-meter uncertainty, noise,
   drift and their correlations unless a future adapter provides evidence for them.
2. **Parameters:** PEM uses eight leave-one-development-plateau-out fits. Slope and
   intercept stay paired. Their prediction envelope describes leverage of these
   samples, not a confidence interval. KIT uses 64 seeded refits with independent
   uniform vertical digitization perturbations (default ±1 K, seed 20260917), or
   just the nominal fit at zero. Full parameter vectors are retained. The envelope
   is the min/max of these scenarios, not an experimental probability interval or
   a rigorous worst-case bound.
3. **Model form:** affine and constant-specific PEM models are compared on identical
   evaluation samples. The reactor has one descriptive approximation; unrepresented
   mechanisms remain unknown. Neither lowest error nor a numerical check silently
   chooses a plant model.
4. **Transfer:** not quantified. Changing technology, capacity, support boundary or
   cooling conditions needs an explicit executable mapping and its own uncertainty.
   Plant defaults and old archives remain unchanged.

No overall trust score or generic pass/fail acceptance tolerance is invented.
Scoped claims distinguish arithmetic/selection checks, descriptive results,
unsupported transfer and missing validation.

## Offline reconstruction and preservation

The compact source records live in `docs/reference-data/`. These are new application
datasets derived from verified original bytes, not edited versions of previous
research results. The old scripts, fits and protocols retain their original meaning.

Run a new numerical edition from the bundled compact observations:

```sh
uv run python -m methane.literature run csu-pem --output build/literature-models/pem.json
uv run python -m methane.literature run kit-slurry --output build/literature-models/kit.json
```

Use `--inputs request.json` for an explicit request shape matching the
chosen adapter. Unsupported fields, nonfinite numbers and out-of-domain queries
are rejected. The CLI performs no network access and never changes project designs.

Reconstruct preprocessing from restored originals:

```sh
uv run python -m methane.literature verify-sources csu-pem --directory research/literature-calibration/raw
uv run python -m methane.literature verify-sources kit-slurry --directory /path/to/restored-kit-sources
```

The KIT directory must contain the named paper PDF, rendered figure and authored
`reactor-digitization.json` listed in its dataset. Hashes are verified before mapping.
A changed source requires a reviewed new dataset edition, not silent acceptance.
The bundled observations suffice to rerun fits offline; reconstructing extraction
requires these separately restored raw inputs. Reports and bundles explicitly list
those omissions. Original raw files remain on disk and are not repackaged as newly
licensed data. Restoring a bundle preserves the original result and source capsule;
executing its original implementation requires restoring that capsule's environment.

## Verification scope

Independent checks cover linear-regression arithmetic, system/stack boundaries,
exact pixel conversion, analytic first-order transitions, development/evaluation
separation, paired sensitivity vectors, finite/domain checks, strict original-byte
identity, missing timestamps, immutable results and offline export/restore.
Browser checks exercise both models, input edits/errors/reset, source detail,
uncertainty, saved results, reports, exports, stale responses and return focus.
Plant/solar screenshot references are unchanged. Software verification is separate
from source-device agreement and from participant usability testing.

Narrative review bindings identify the exact adapter, model, compact data and model
notes. The existing documentation freshness check rejects drift until these
mechanisms, conditions and limitations have been reviewed again. Previously saved
results remain readable under their original identities.
