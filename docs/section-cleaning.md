# Section cleaning and optical conversion

This is a stage-2 checkpoint of the [field operations programme](field-operations-goal.md). Select `plant-service-contracts/1` execution and `section-optical/1` cleaning in advanced setup. The resulting runtime records identify `plant-service-contracts/2`, `array-surface/1` and `section-dry-brush/1`. The configuration's execution selector remains the generic contracts adapter; the recorded model identity distinguishes its optical mechanism. Existing `field-operations/1` and `lumped-dc/1` runs retain their post-conversion loss proxy.

## What changes physically

Every installed solar section has an area inventory. The reference area is capacity multiplied by the editable 5 m²/kW assumption. Contiguous patches carry three separate optical-loss fractions: removable material, adhered material and permanent damage. Initial values, area, brush life, treatment rate and weather limits are illustrative assumptions, not fitted measurements.

For patch area A, transmission is `(1 − removable) × (1 − adhered) × (1 − damage)`. Section transmission is the area-weighted mean, composed with any separate soiling already declared in the solar design. It enters the existing solar kernel before converter clipping. That kernel uses a lumped section temperature; there is no added cell-string, bypass-diode or within-panel temperature model. Drawing three surface bands does not imply three electrical strings.

Dry brushing removes only the removable fraction in the area actually traversed. Adhered material and permanent damage persist. Efficacy for one pass is frozen at dispatch into work as `configured removal × remaining brush area / original brush life`. Brush stock is then consumed at the area treatment rate during each actual work span. This is an explicit wear proxy, not a calibrated bristle model. Efficacy changes between passes; freezing it within a pass makes the result independent of hourly integration splits.

The underlying treatment function can integrate a linearly varying efficacy over a patch, retaining its area mean. Repeated overlapping treatments of such a varying patch would lose subpatch detail. The current plant adapter therefore uses constant efficacy within each pass. Boundary tests cover that implemented case.

The executive reserves enough brush, battery and a cleaning kit for the planned pass and return. A kit is consumed on entering work. Brush and power are consumed only for elapsed work. An interrupted mission retains already treated area, used resources and its last recorded location. It does not receive a full-pass completion credit. Retrieval is a subsequent task; this checkpoint leaves the stranded asset unavailable.

Physical changes become available at the next hourly plant boundary. For example, travel from H0 to H0.5 and brushing from H0.5 to H1 treat 500 m² at 1,000 m²/h. H0 power uses the original surface; H1 uses the partially cleaned surface. Surface accumulation is applied after treatment at each boundary, capped at the existing 30% loose-loss assumption. No future cleaning benefit enters a process forecast in this local service-policy version.

## Conditions and information

Per-section capabilities require declared row access, current wind and current rain within editable limits. The `assumed` option supplies clearly labelled fixture conditions. The `weather` option requires those channels in the saved current weather sample; missing, invalid or unavailable readings block the task. Weather restrictions are eligibility conditions, not automatic rain cleaning. There is no unlabelled substitution of forecast or synthetic conditions.

The cleaning supervisor currently receives an **ideal section surface monitor**. Loose/adhered/damaged fractions are assumed directly observable; these are not camera inferences. It chooses the section whose loose loss exceeds the threshold most. Inspection payload uncertainty and estimated soiling belong to later work. Injected mission failure and its time stay behind the execution boundary.

Future conversion uses only the forecast vintage eligible at the decision time, its recorded radiation and the current surface estimate plus accumulation. Current measured mean-PV and ambient values replace only the current interval. Missing radiation produces an incomplete input error. Forecast error is compared on the same surface/converter basis; the underlying source-reference DC error is retained separately. Altering future realised weather cannot alter an earlier dispatch decision.

## Reading the result

The main scene adds a surface overlay and a section-specific schematic sweep while retaining every original plant path and label. Dust responds to recorded loose/adhered patches. The service inspector reveals treated area, brush stock, remaining fouling, mission phases and ledger events. The solar detail view shows the recorded section design and conversion result. An edited design preview is labelled separately and does not rewrite the completed surface trace.

Recovered optical transmission is not automatically recovered DC: the converter may already be clipping. Recovered DC is not automatically used energy: bus demand and storage may be limiting. Used energy is not automatically methane: feedstock and reactor constraints may bind. Reports therefore retain clipping, curtailment, service electricity, methane and ending inventories separately.

## Evidence and reproduction

`tests/test_surface_services.py` checks independent area arithmetic, partial work, preserved adhered fouling/damage, brush and battery use, no-effect conditions, converter clipping, missing input, zero capacity, orientation/temperature and future-information separation. The dependency-free `methane/reference.py` independently reconstructs patch treatment, brush efficacy, converter output and clipping from recorded operands. Mutation tests ensure forged effects fail that audit. These numerical checks do not establish field performance or hardware reliability.

```
.venv/bin/python -m methane.services.cleaning_demo --directory build/services/cleaning
```

This writes four deterministic cases, saved runs, offline playback, human-readable results and reproduction bundles. All use a deliberately constant irradiance/ambient fixture to isolate the mechanism. It is not a seasonal weather study. The interrupted case retains incomplete work and a stranded cleaner in its report.

## Remaining scope

This checkpoint does not complete stage 2. Portable/wet cleaning, water, brush replacement, explicit retrieval, replenishment, crew/remote availability, support failures and richer sensing still need integration. Snow and adhered material are not removed by this dry brush; permanent damage requires a compatible physical repair. Detailed running costs and Studies publications are stage 3. Brush wear is quantified here but still covered by the existing unseparated cleaner-wear allowance; it has no additional replacement charge in this checkpoint. Do not use these short mechanism examples to price an installation or claim that robotic cleaning pays back.

The subsequent opt-in [support logistics checkpoint](service-support.md) adds finite crew/remote allowance, retrieval with separate drive-test acceptance, typed supply delivery and brush replacement. The saved section-cleaning examples retain their original scope and source; their results are not rewritten by this extension.
