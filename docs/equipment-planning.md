# Equipment-specific planning

This increment attaches an identified equipment basis to a plant design and its
future runs. Open **Project → Build → select equipment → Equipment & evidence**,
or use Project tools. A completed run also exposes **Equipment basis**. The plant
illustrations and playback view are unchanged.

## First reference and scope

The European PV–AEM candidate uses 1,667 Trina TSM-NEG19RC.20 modules in the 600 W
bin (1,000.2 kWp), four Enapter AEM Flex 120 skids from the **rev08** datasheet,
and the existing illustrative battery, gas stores and methanator. Seville is the
acceptance example; the same candidate can be attached to the supported European
regional anchors. It is not a claim about an installed plant, identified parcel,
procurement availability or equipment compatibility.

[The versioned reference](equipment-reference.json) identifies the specification
edition, source URL, retrieval time, original PDF hash, scoped facts, conversions,
model bindings and missing evidence. The two manufacturer originals remain in
`research/equipment-planning/raw/`; offline operation uses the authored reference,
not a live webpage. PDFs are reference-only and omitted from shared bundles.

The nominal Enapter power/flow pair implies 112 / 2.16 = 51.85185 kWh/kg, while the
same datasheet separately reports 51.3 kWh/kg. The candidate uses the nominal pair
for an internally consistent aggregate hourly approximation and retains this
discrepancy explicitly. Published flow turndown is approximated as power turndown;
this is not an identified part-load curve or a multi-skid scheduling model.

The reference uses base-configuration specifications. Real AC conversion,
external cooling, water treatment, gas conditioning and pressure interfaces need
an engineered design. The abstract DC bus does not establish compatibility.
Start energy, temperature dependence, service durations, intervention success,
prices and all unchanged parameters retain their existing assumptions. Minimum
and maximum ambient operating temperatures cannot be inferred from a specification
point. Trina's module temperature rating is not an ambient rating. No bifacial
gain is credited by the reference mapping.

Only simulated human escalation is enabled in its basic field-operations package.
The reference supplies no robot capability approval or human service contract.
Additional optional service/lifecycle mechanisms are preserved and explicitly
flagged for separate review. Enapter EL4.1 service instructions are not transferred
to Flex120 as an approved repair method.

## Versioning and applicability

Applying the reviewed changes creates an immutable project revision and equipment
basis. It changes only the displayed bindings. A design carries the basis identity;
a new study captures its applicability and the commissioning reviews available at
creation. Changes to selected parameters, site or execution source appear as
review-required. Matching parameters is a consistency check, not validation.

The checks assess model applicability. They do not add OEM operating interlocks,
pressure models or support-power calculations to the executor. Experiments with
unresolved equipment gaps remain possible and visibly qualified. Requirements
comparisons retain each case's equipment status, without promoting it to feasibility.

Old runs without the basis report missing original explanations. They are not
upgraded with today's reference. Current commissioning history for the exact design
can include later reviews; the UI labels that distinction. Original run snapshots
never absorb later acceptance records.

## Commissioning evidence

Six gates cover site rights/access, utilities/interfaces, equipment acceptance,
thermal/process behaviour, service support and measurements. A record requires an
identified reviewer, original evidence excerpt or acceptance record, rationale and
outcome. Outcomes are **accepted by reviewer**, **failed** or **incomplete**; absence
is **not reviewed**. Records bind to the exact design and executable Python source
identity. A changed implementation marks previous reviews stale. The source binding
is deliberately conservative and covers the execution application, not only one
kernel. A changed design starts a new review scope. No overall readiness score or
certification is calculated. Uploaded assertions are not independently authenticated.

## Observations and retrospective comparison

The import form accepts up to 744 hourly rows over a maximum 744-hour window:

```csv
timestamp,value,quality
2025-07-10T00:00:00Z,12.0,valid
2025-07-10T01:00:00Z,,missing
2025-07-10T02:00:00Z,13.0,suspect
```

Channels are hourly mean applied electrolyser power (kW), hydrogen produced (kg),
methane produced (kg), and battery energy (kWh). Timestamps denote interval starts;
battery readings are for the end of that interval. Explicit offsets normalize to
UTC. Duplicate times, ambiguous times, non-finite numbers, unknown units/channels,
contradictory quality flags and out-of-window data fail visibly. There is no
resampling, interpolation or silent unit conversion. Absent rows remain missing.

The dataset identifies installed assets/serials, origin, supplier, method, source
reference, absolute measurement uncertainty and sharing rights. Uncertainty is a
supplied bound in the channel unit, not an inferred distribution. Synthetic test
data stays synthetic. The built-in software tests supply no field observations.

Comparisons require the exact recorded design identity and use committed original
simulation partitions. Only valid paired hours enter bias and RMSE. Missing,
suspect and unavailable hours remain in the table and coverage denominator. Residual
is simulated minus observed. Each simulated operand links to its original interval,
controller and equipment. Partial simulations produce immutable incomplete editions;
later progress requires a new comparison. Simulation source and comparison source
are both retained, with the comparison source capsule in exports.

This is retrospective shadow analysis: the app does not connect to a plant, control
hardware, estimate a causal controller benefit, fit parameters or certify a model.
Weather, actions, initial states and measurement boundaries must be reviewed before
attributing a difference to equipment. A new calibrated model would need its own
reviewed adapter and held-out evaluation.

## Preservation and product boundaries

Reports preserve source identities, evidence, differences and an editable authored
account. Shareable observation reports and bundles require declared redistribution
permission. Reference-only observations remain usable for local comparisons; they
cannot be published as shareable reports. Frozen commissioning artifacts available
when the run was created accompany that run's reproduction bundle. Later reviews
are not retrospectively substituted. Manufacturer PDF links/hashes remain available
without redistributing their originals.

The numerical suite covers independent nominal-power arithmetic, residuals, storage
interval semantics, partition boundaries, UTC/DST, missing data, version invalidation,
exact design matching, immutable runs and offline export/restore. Browser checks
cover review-before-apply, evidence recording, observations, reports, trace navigation,
stale responses, keyboard return and narrow screens. These checks establish software
behaviour, not field realism or an expert-participant usability outcome.

## Optional physical integration

The separate [plant-interface contract](plant-interfaces.md) is now available in
Equipment & evidence. Enabling it creates a design revision with explicit AC
conversion, external loads, regulated-pressure compatibility and finite purified
water. The evidence reference alone still does not enable these assumptions or
establish OEM interlocks. Original saved cases retain their original boundaries.
