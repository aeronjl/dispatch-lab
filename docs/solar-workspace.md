# Solar array workspace

Select the solar array in plant operation to enter its dedicated circuit view.
The shared-element transition expands the original equipment illustration and
reveals three selectable array sections, their independent ideal MPPT channels,
section isolators and a shared DC converter. Back or Escape returns to the plant;
the clock position is retained. Navigation pauses playback. Reduced-motion
preferences skip the transition and animated flows.

The geometry controls change section nameplate capacity, tilt and azimuth.
Capacity changes the number of schematic rows, not a literal panel count. Tilt
and azimuth change the projected module geometry. Uniform section shading darkens
panel tiles, soiling adds surface deposits, and disconnection opens an isolator.
The condition and conversion tabs progressively expose the other assumptions.

## Model boundary

Power accounting is in `methane/solar.py`; browser code only renders results and
projects the SVG geometry. The model is versioned `dispatch-lab/solar-sections/1`.
Each section has its own capacity, orientation, shading, soiling and connection
state. Thermal NOCT and converter parameters are shared. Per-section output is
calculated after shading, soiling, temperature response and the existing
aggregate electrical loss. That aggregate is retained once; converter efficiency
is a separate optional additional loss, defaulting to 100%. Default identical
sections and the nameplate converter limit reproduce the prior lumped conversion.
The loss budget records negative temperature losses as gains when applicable.

The saved weather includes irradiance on the original tilted plane, not separate
measured direct and diffuse channels. Changed orientations use a deliberately
illustrative 30% diffuse-horizontal fraction, isotropic diffuse projection and an
approximate midpoint solar position, normalized to the reference orientation.
The beam denominator is bounded near sunrise; below the horizon only the diffuse
tilt ratio is applied. This preserves unusual synthetic day lengths. It is an
orientation sensitivity model, not a calibrated irradiance transposition or
geometric shading solver. The UI discloses this assumption. References:

- [Sandia: plane-of-array irradiance](https://pvpmc.sandia.gov/modeling-guide/1-weather-design-inputs/plane-of-array-poa-irradiance/)
- [Sandia: isotropic diffuse model](https://pvpmc.sandia.gov/modeling-guide/1-weather-design-inputs/plane-of-array-poa-irradiance/calculating-poa-irradiance/poa-sky-diffuse/isotropic-sky-diffuse-model/)

Shading and soiling are uniform fractions for each section; no bypass diode,
string mismatch, tracker, wind cooling or fault diagnosis is claimed. MPPT
channels have ideal independent tracking. Panel temperature follows the existing
NOCT-style hourly approximation. All section telemetry is labelled as modelled,
not independently measured.

## Preview, application and provenance

Edits preview the complete saved weather replay. They do not alter the recorded
plant run and are not decision-time predictions. Preview responses carry a run
identifier and a unique request generation; late responses cannot replace a
newer draft. Numerical readouts are withheld while a new design is calculating.

**Run plant with design** creates a new run for all three strategies, using the
same saved reference, original forecast vintages, publication boundaries and
scenario seeds. Both reference and each forecast are converted independently.
Forecasts never derive their solar profile from later realised weather. The
plant capacity equals the sum of section capacities and its existing solar
capital allocation scales accordingly. Additional mounting/converter capital
premiums are not priced in this release, as disclosed in the workspace.

The new run stores the design in `config.solar`, the original weather and
configuration as solar-reference provenance, and detailed hourly conversion
records. Repeated edits always start from the original irradiance; losses are
not compounded through repeated previews. Saved archives round-trip the design.
Legacy synthetic forecasts without irradiance invert the previous monotone PV
conversion; unrecoverable/clipped samples produce an explicit error. New
synthetic forecasts retain irradiance directly.

When changing total solar capacity in experiment setup, saved section capacities
scale proportionally. Other detailed design settings persist into the rerun.
Converter clipping and plant curtailment remain separate accounting quantities.
