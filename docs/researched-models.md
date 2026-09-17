# Researched conversion and thermal models · edition 1

These **optional execution models** are available in Project → Equipment & evidence
→ Plant interfaces → Explore researched conversion and thermal models. Preview
uses the supplied design without saving it. Save creates a new design revision;
new experiments use it in planning and execution. Original runs remain unchanged.
All options and transfer parameters are disclosed to controllers. Hidden variation
of these interfaces is rejected. The uncertainty workspace can compare disclosed
model choices and parameter scenarios, without assigning unsupported probabilities.

## Conversion

`pvwatts-analogue/1` uses the part-load relation from [Dobos, NREL/TP-6A20-62641
(2014), §12, equation 10](https://docs.nlr.gov/docs/fy14osti/62641.pdf).
With z = Pdc/(Pac,rated/eta,nom),

`Pac / Pac,rated = (-0.0162 z² + 0.9858 z − 0.0059) / 0.9637`.

Invert the increasing branch at AC fractions 0.02, 0.05, 0.10, 0.20, 0.30,
0.50, 0.75 and 1.00. Interpolate **DC demand**, not efficiencies, between adjacent
points. The MILP uses a single selected segment, not a convex relaxation across
nonadjacent points. Execution uses the same segments. Off draws zero; positive
operation below 2% is outside this implementation's envelope. Demand never clips
silently to the AC rating. No standby allowance is included.

The publication concerns PV inverters. Applying its normalized curve to the
process AC island is an explicit **technology analogue**, not a selected converter
or grid-forming qualification. Voltage, frequency, switching transients, reactive
power and black start are omitted. Nominal efficiency and rating remain design
inputs. `converter_loss_scale` multiplies the difference between DC input and AC
output; 1 reproduces the source-derived knots. Its alternatives are user scenarios,
not a fitted distribution. Approximation error between knots is checked separately
from source applicability. The constant-efficiency option remains available.

## Electrolysis heat and ambient cooling

[NIST liquid-water formation enthalpy](https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Mask=2)
(285.830 kJ/mol magnitude, CODATA review) and
[hydrogen molecular weight](https://webbook.nist.gov/cgi/cbook.cgi?ID=C1333740&Mask=1)
(2.01588 g/mol) give 39.386 kWh/kg approximately for liquid-water decomposition at
25°C. This is a reference-state energy requirement, not electrical efficiency.

`productive excess heat = base productive electricity − hydrogen × 39.386...`

`cooler heat = productive excess heat × external_heat_share`

The base electricity includes internal utilities in the equipment reference.
Their heat paths are not identified: `external_heat_share` is an explicit transfer
assumption (default 1, a conservative assignment of all reference-state excess to
external cooling). The rest is outside that liquid cooler's boundary, not extra
recoverable energy. Startup electricity remains an energy allowance; its heating,
retention and cooldown are not identified. Dryer and converter losses are not
added to the electrolyser liquid loop. This steady balance omits sensible gas/water
enthalpy and storage of heat. Specific electricity below the decomposition
enthalpy is rejected because an external heat source is absent from this model.

`available cooler heat = min(rated heat, UAeff × max(0, Thot,eff − Tambient))`.

This is an effective steady dry-cooler envelope derived from heat transfer. It is
not a chiller and cannot cool against a reversed temperature gradient. Default
UAeff = 6.4 kW/K and Thot,eff = 45°C reproduce the existing 160 kW rating at 20°C;
these are **design assumptions**, not an OEM performance map. Thot,eff represents
an effective exchanger temperature, not the published 55°C electrolyte condition.
Fan/pump electricity remains the configured heat fraction; no fan-speed curve or
wet-bulb effect is asserted. Both controller forecasts and realised ambient values
use this envelope, so a warmer-than-forecast hour can reduce the applied load.

## Methanation heat and feed conditioning

`nist-cold-feed/1` computes ideal reaction enthalpy and feed sensible heat using
[NIST methane](https://webbook.nist.gov/cgi/cbook.cgi?ID=C74828&Mask=1),
[CO₂](https://webbook.nist.gov/cgi/cbook.cgi?ID=C124389&Mask=1),
[H₂](https://webbook.nist.gov/cgi/cbook.cgi?ID=C1333740&Mask=1) and
[water-vapour](https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Mask=1)
gas Shomate coefficients, Chase (1998); common domain 500–1000 K.

`gross reaction heat = −[H(CH₄) + 2H(H₂O) − H(CO₂) − 4H(H₂)]`.

`feed duty = H(CO₂,Tref) − H(CO₂,298.15) + 4H(H₂,Tref)`.

`product sensible heat = H(CH₄,Tref) − H(CH₄,298.15) + 2[H(H₂O,Tref) − H(H₂O,298.15)]`.

`recovered = effectiveness × min(feed duty, product sensible heat)`.

`feed heat = feed duty − recovered`.

Coefficients are frozen at an editable reference temperature (default 300°C)
inside the production band. This preserves the existing analytic, linear hourly
thermal transition. The reactor evolves dynamically using **net** heat after feed
heating; it does not continuously recompute chemistry at its evolving temperature.
Actual reactor temperature, gross reaction heat, feed heating and net heat are
recorded separately. Reaction heat remains gross heat in existing columns.

The plant's rounded 16 kg/kmol methane extent is retained, preserving its existing
0.5/2.75/2.25 mass ratios and exact rounded mass balance. This differs by about
0.27% from the earlier literature calculation using 16.0425; neither old evidence
nor old columns are rewritten. Formation enthalpy at 298.15 K comes from the
reference constants, not extrapolation of water's 500 K polynomial. Water remains
vapour in the reactor; no condensation credit. `feed_recovery_fraction` is an
assumed sensible-recuperator effectiveness, not free additional electricity or
saleable heat. Recovery cannot exceed the smaller stream duty. At 300°C the
exhaust supplies at most 0.535 of the 0.759 kWh/kg feed duty, so even effectiveness
1 leaves about 0.225 kWh/kg to supply. This is an ideal heat-budget upper bound;
finite exchanger area, pinch and approach temperatures can reduce real recovery.

This is an ideal complete-conversion thermal option, not kinetics, gas quality or
catalyst validation. The existing heat capacity, ambient heat loss, production
limits and minimum run still need uncertainty analysis. The KIT slurry response
fit remains a distinct controlled-coolant experiment: its time constant cannot
identify this reactor's ambient UA or thermal mass. The CSU PEM flow fit is also
not applied to the AEM reference equipment.

## Evidence and uncertainty

Source equations and constants are frozen in `methane/researched_models.py` in
each run's source capsule, alongside the selected parameters and model identity.
There is no network dependency at execution or preview. Source URLs remain links.
Archived integration/1 configurations omit the optional research block; decoding
does not add research assumptions. Current explanations remain explicitly current.

- Numerical verification: independent Decimal/bisection calculations, source
  knots, cold-feed heat, analytic temperature evolution, conservation and segment
  membership. Planner/executor tests include ambient forecast error, unavailable
  cooling and minimum converter load.
- Parameter uncertainty: disclosed choices for nominal conversion and thermal
  coefficients; no measured parameter confidence interval is claimed.
- Transfer uncertainty: converter loss scale, cooler UA/hot temperature, heat
  allocation and recuperation. Suggested scenarios are not statistical bounds.
- Structural uncertainty: constant versus research models; the omitted coolant
  state, voltage dynamics and chemistry kinetics remain explicit limitations.
- Empirical validation: **not established** for this proposed plant. No held-out
  plant data is invented. Public empirical device profiles remain separate until
  their technology, measurement boundary and scaling can be represented faithfully.

Tests are software acceptance checks, not a research programme or a claim that
MPC must win. Existing source-device study results retain their original identities.
