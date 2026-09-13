# Siting and production forecasting

Build **Sites**, a dedicated workspace that connects geographical evidence to a configured plant, a continuous operating study and an investment case. Its central question is: **which site–plant–service combination remains attractive when weather, operating behaviour and incomplete site evidence are taken seriously?**

This is a researched product and engineering design. It includes a live-tested solar-data example, not an implemented siting feature or a recommendation to acquire any parcel. The first product is the existing solar–battery–electrolysis–methanation plant with supplied CO₂. Europe, including the UK, is the initial geographical scope.

## 1. The experience

The main flow is **Explore → Assess site → Design plant → Run study → Compare → Open simulation**. Add Sites to the existing menu and keep the operating plant quiet and full-screen. Site exploration has its own full-screen map; selecting a candidate reveals a compact drawer. The user can return to the map, the study or the exact operating hour without losing context.

<div id="workflow" class="workflow" aria-label="Proposed workspace flow"></div>

**Explore.** Search an address, enter coordinates, draw an area, import candidate polygons or ask for candidates within a region. Start with a basemap and a few saved candidates. Resource, land, utilities, feedstock and service access are selectable layers, rather than simultaneous overlays. Offer a keyboard-accessible list alongside the map. Colours express a selected quantity or evidence state; they do not combine everything into an opaque suitability score.

**Assess site.** A candidate initially shows usable-area estimate, solar seasonality, unresolved dependencies and an evidence date. Selecting one reveals the source geometry, measurement or inference. An industrial facility is a lead for a CO₂ supply discussion; a power line is network context. Neither silently satisfies a plant requirement. Missing land or network data remains visibly unresolved, even when solar data is excellent.

**Design plant.** Reuse the illustrated plant and component inspectors. Start from the existing reference configuration or a saved design; change solar layout, battery power/energy, electrolysis, buffers, methanation and the service fleet. A site plan adds boundaries, access routes, equipment pads and exclusion areas. These physical positions should inform area, cable/pipe lengths and robot travel only through explicit, identified models. Dragging an icon is not permission to invent a feasible pipe, safety separation or robot capability.

**Run study.** Choose the question before the compute budget: resource potential; expected operation under a specified policy; robustness to uncertainty; or economics of a design. Show a quick resource response, then a background study with progress, cancellation, resume and partial-result status. The year view is a production calendar with selectable difficult periods. Clicking a low-output week opens the existing animation at that time, with the same observations, forecasts, service events and cost assumptions.

**Compare.** Compare both the *same plant at different sites* and *a separately sized plant at each site*. These answer different questions and have separate result groups. A compact frontier shows cost, annual output, land/water requirements and service dependence. A site’s explanation lists why it remains a candidate, which conditions could reverse the result, and the next evidence needed. A generated write-up retains rejected, incomplete and unsuccessful cases.

Keep Departure Mono, amber linework and the existing equipment illustrations. Use progressive disclosure: the selected site or result owns the inspector, while source and financial detail occupy dedicated sheets. Entering Sites pauses playback; Back/Escape restores the originating site, study, component, controller, hour, map extent and keyboard focus. On narrow screens use a map/list switch and a single sheet, not compressed multi-column panels. Reduced-motion mode removes travel/zoom transitions.

## 2. What the first version can actually answer

| Question | Required calculation | Qualification |
|---|---|---|
| How good is the solar resource? | Multi-year irradiance, temperature and panel conversion | Satellite/reanalysis estimates, with source and conversion assumptions |
| What could this plant produce? | Continuous hourly plant operation with realistic initial and terminal states | Conditional on the plant, policy, feedstock and service assumptions |
| What limits it? | Recorded active constraints plus controlled design perturbations | Constraint activity is descriptive; a paired perturbation supports a bounded causal claim |
| What does it cost? | Physical usage plus allocated costs and a separate project cash-flow model | Reference budgets and supplier quotes must remain distinguishable |
| Which locations deserve investigation? | Transparent feasibility filters and robust comparisons | A ranked shortlist within a declared search area and dataset coverage |
| Is this particular parcel deployable? | Site survey, permissions, utility/CO₂/offtake evidence and engineering review | Public maps alone cannot establish this |

Report methane produced at the model boundary separately from gas delivered and accepted by a customer. Show gross hydrogen production, hydrogen consumed by methanation, and remaining hydrogen independently. A hydrogen-sales option requires a real export branch, delivery conditions and cost model; it cannot sell the same hydrogen that became methane. The current system consumes supplied CO₂. It does not capture atmospheric CO₂, certify methane quality or establish net carbon removal. “Captured CO₂” therefore stays unavailable until a capture component is implemented and reviewed.

Off-grid solar remains the first executable operating mode. Grid proximity, indicative capacity and quotes can enter site assessment immediately. A grid-assisted plant becomes executable only after adding an import/export interface, connection limits, conversion losses, tariff timing and metered accounting to both planning and execution. A nearby substation must not enable electricity imports by changing a site label.

## 3. Evidence from existing tools

Fraunhofer ISE’s HYSCOPE approach combines geography, facility size, operation and transport. That is the useful pattern here: identify a viable supply chain and operating system, rather than optimise irradiance alone. REopt illustrates a connected techno-economic and resilience workflow, but its US-oriented defaults and equipment scope are not a substitute for this plant. [[fraunhofer]] [[reopt]]

Use atlite’s explicit land-availability and renewable-time-series patterns for regional processing, while retaining Dispatch Lab’s component kernels, controller information boundaries and service model. Renewables.ninja supplies a useful independent renewable-modelling reference; its commercial-data conditions need separate consideration. [[atlite]] [[ninja]]

PV uncertainty literature supports separating year-to-year resource variation from uncertainty in measurements, conversion and reliability. That transfers well to the existing uncertainty contracts. It does not justify copying a generic PV uncertainty percentage onto methane output: reactor thresholds, gas storage and recovery decisions make that transformation nonlinear. [[pv-uncertainty]]

## 4. European data acquisition plan

Use a **public regional baseline plus country-specific adapters and uploaded site evidence**. Each field has a value, units, spatial/temporal support, source edition, retrieval date, derivation, uncertainty status and applicability. A dataset can be available for screening while remaining inadequate for a parcel decision.

<div id="data-catalogue" aria-label="Proposed data connectors"></div>

**Solar and historical weather.** Pin PVGIS 5.3/SARAH3 for the first resource adapter; its live-tested responses cover 2005–2023. The current JRC site also offers PVGIS 6 for testing, so migration should be a new, compared adapter edition. Use PVGIS reference PV estimates as a cross-check, and irradiance plus meteorology as inputs to the existing conversion kernel. Applying both PVGIS system losses and the plant’s losses to the same power trace would double-count them. [[pvgis]] [[pvgis-api]]

Use explicit ERA5 or ERA5-Land products for long continuous meteorological histories, and evaluate CAMS radiation as an additional satellite-informed source. Preserve product provenance when combining fields; PVGIS meteorological inputs themselves use reanalysis, so the resulting estimates are not statistically independent just because they have different provider names. ERA5 and ERA5-Land are model reconstructions, not measurements at the proposed array. [[era5]] [[era5-land]] [[cams]]

**Forecasts.** Keep the existing saved ECMWF single-run interface and publication-lag convention. The long historical resource record and the original forecast archive have different coverage: ECMWF IFS single runs begin in March 2024 in the documented service. Earlier resource years can support chronological yield tests with an explicitly specified persistence/climatology or synthetic error model, but cannot be called archived-forecast backtests. Validate a recent complete year, such as 2025, separately wherever all required forecast vintages are available. [[weather-runs]] [[weather-history]]

**Land and hazards.** CLCplus Backbone supplies 10 m land cover; GLO-30 supplies 30 m surface elevations. Calculate usable fractions, slope distributions and terrain-horizon effects at their real resolution. Do not imply that a smooth zoomed map is more precise than those inputs. Natura 2000 and national designations inform a configurable avoidance policy and investigation flags. Absence of a protected-area overlap is not a planning consent. National data must fill jurisdictional gaps; England’s MAGIC layers are not a complete UK assessment. [[clc]] [[dem]] [[natura]] [[england]]

JRC flood maps are regional modelled river-flood evidence and explicitly not official flood-hazard maps; small catchments, surface-water and coastal hazards need additional local products. Seasonal EEA WEI+ and WRI Aqueduct help prioritise water investigations. Neither establishes a water connection, licensed abstraction volume, purity or treatment requirement. [[flood]] [[wei]] [[aqueduct]]

**Utilities, feedstock and market access.** Import industrial-facility locations as potential supply/demand leads. Keep emission totals distinct from recoverable, purified, contracted CO₂. Add a structured supply offer: composition evidence, sustainable origin if relevant, quantity schedule, outages, price basis, compression/purification responsibility and delivery distance. Road distance and mapped access are planning inputs, not proof that a heavy delivery vehicle can enter the parcel. [[industrial]]

DSO publications are more useful than a continental transmission map for actual electricity access, but published headroom remains indicative. Model import and export independently. Record voltage, firm versus interruptible service, maximum power, reinforcement/connection cost, delivery date and quote validity when an operator supplies them. UKPN is a practical first country adapter; Spain and Denmark need their own chosen DSO agreements and datasets. ENTSOG is useful background for gas infrastructure, but its map carries an indicative-use disclaimer; do not assume an unrestricted commercial map layer or a local injection right. [[ukpn]] [[entsog]]

ENTSO-E supplies bidding-zone market data through authenticated access. Preserve native settlement intervals and publication timestamps; wholesale energy prices are only one part of a site tariff. GB needs an explicit source choice: Elexon settlement/system-price data is not a day-ahead purchase contract. Spanish e·sios is another national adapter. Tariffs still need network charges, capacity charges, taxes, retail/PPA terms and curtailment conditions. [[entsoe]] [[entsoe-api]] [[elexon]] [[esios]]

**Costs and measurements.** Retain current illustrative costs as a labelled reference. Import dated technology benchmarks, such as the Danish Energy Agency catalogue, only with technology, reference scale, price year and uncertainty; current material includes an August 2026 update. A 100 MW industrial benchmark is not a supplier quote for a 450 kW package. Supplier quotations, land rent, water/CO₂ agreements and maintenance invoices take priority when they match the proposed equipment. [[costs]]

Make field-data import a first-class interface: station/plant ID, location/elevation, sensor type, calibration, measured plane, units, time support, quality flags, availability and licence. DWD radiation observations offer a useful verification path for German sites. The Met Office DataHub land-observation API is recent data, with a documented 48-hour window; it cannot fill a long historical calibration requirement by itself. [[dwd]] [[metoffice]]

## 5. A real-data example, with a deliberately narrow claim

The following are live-retrieved **PVGIS reference PV yields**, using the three existing city reference coordinates. They are regional resource anchors, not screened parcels. All use 1 kWp crystalline silicon, fixed 30° south-facing free-standing panels, a 14% input system-loss assumption and the provider’s terrain horizon. Values below come directly from the saved responses; no methane, land availability or payback has been calculated.

<div id="resource-example" aria-label="Saved PVGIS resource example"></div>

The implication is a question for plant simulation: how much of a stronger solar resource survives converter limits, electrolyser turndown, reactor warm-up, buffer constraints and the cost of sustaining operation? The response is not obtained by multiplying annual solar energy by a single methane efficiency. Copenhagen and London also illustrate why a similar annual reference PV yield need not mean a similar winter operating pattern.

The [saved requests and numerical outputs](retrieval-20260913/resource-samples.json) preserve the database, years, coordinates, assumptions and raw hashes. The [retrieval script](fetch-resource-samples.py) is a small feasibility probe. Other proposed data connectors have had their documentation reviewed but have not been implemented or live-tested in this design.

## 6. From regional search to a credible site shortlist

Start with a declared search area and a land-use/development strategy. Useful discovery modes are: near a plausible CO₂ supplier; near an identified gas customer; within a service-base travel range; or within a specified country/region. This makes co-location and support logistics part of candidate generation. The highest-irradiance cell is only one kind of candidate.

Use coarse regional cells to reduce the search space, then obtain actual polygons for shortlisted areas. Retain candidate IDs through geometry changes, with explicit versions. Perform area calculations in an appropriate metric/equal-area CRS, not latitude/longitude degrees or uncorrected display-map pixels. Store the original geometry and CRS, intersections, buffers, cell coverage and the resolution of every input.

For each candidate calculate: total area; excluded-by-policy area without double-counting overlapping exclusions; remaining contiguous area; a layout-constrained PV capacity range; equipment/support footprint; access alternatives; and unresolved feasibility conditions. A simple watts-per-square-metre estimate may be used for coarse screening, visibly labelled, then replaced by row geometry, spacing, maintenance corridors, slope and setbacks. Technical or safety separations require sourced design requirements rather than arbitrary visual spacing.

Use separate states: **candidate**, **screened under policy**, **needs investigation**, **excluded by selected policy**, and **site-specific evidence supplied**. Data absence never becomes “clear”. A policy exclusion is not automatically a statement that development is legally prohibited. Store who supplied or reviewed decisive parcel/utility evidence and when it expires.

Country packs define datasets, coverage, authoritative local sources, connection organisations and rule references. They share one contract, so adding countries does not hard-code national assumptions into plant physics. Start the first regional tests around our London, Seville and Copenhagen anchors, then select candidate polygons through the declared rules. The anchor points themselves receive no deployability status.

Size designs with a bounded outer search around the existing dispatch controller: first an explicit catalogue/grid of feasible solar, battery, electrolyser, buffer, reactor and service configurations; then screened chronological evaluations; finally full-year and held-out confirmation of the shortlist. Record rejected configurations and each search budget. The existing mixed-integer dispatch optimiser is not automatically a joint land-layout and capital-design optimiser. A surrogate may later propose candidates, but final recommendations require the physical simulator and uncertainty checks. Report the best designs *among those examined*, not a globally optimal European site.

## 7. Production forecasting that respects chronology

The repository currently validates **1–240-hour simulations**. A multi-year assessment therefore needs a new long-run execution path, not a larger dropdown alone. Extract a checkpointable simulation session that keeps physical execution state separate from controller information. A checkpoint includes gas and battery inventories, thermal state, minimum-run commitments, installed damage, accumulated usage, diagnostic beliefs, pending probes, service positions/jobs/resources/orders, absolute event time and random-stream identity.

Stream results into bounded partitions while retaining a continuous state and forecast horizon across partition boundaries. Save a thin annual/monthly summary for exploration; retrieve detailed intervals for playback on demand. A selected week must open its original checkpoint and recorded interval trace, not rerun from empty tanks. New result manifests bind all partitions, the model version and the weather/environment bundle. Old archives retain their meaning and remain readable.

Run three explicitly labelled assessment modes:

1. **Resource assessment:** multi-year solar/climate summaries and reference PV output. No autonomous-controller claim.
2. **Design assessment:** chronological plant operation under identified controllers and information assumptions, including explicit commissioning/steady-operation boundaries. An ideal-information comparison can diagnose opportunity but is not a feasible weather forecast. A finite-time solver incumbent is not a certified upper bound.
3. **Autonomous-operation assessment:** original available forecast vintages, noisy observations, persistent faults, service and recovery. Controller validity, fault assumptions and numerical limitations accompany the results.

Use long weather records for climate variability and the shorter forecast-vintage period for information-realistic backtests. If long-record forecast errors are generated, fit them only on a separate training period, preserve temporal/seasonal dependence and publication lead time, and label the transfer to other years/sites as an assumption. Do not let realised future radiation appear in the controller’s inputs.

Begin annual validation with one continuous year, then multiple full years and deliberately adverse sequences. Use actual calendar intervals, including leap days; keep operational timestamps in UTC and display local offsets. Define initial inventory and warm-up treatment explicitly. For independent annual climate cases, document each reset and starting state; for lifetime trajectories, carry damage, service and ageing across year boundaries. A sampled historical year is not an independent new equipment population.

Representative days/weeks can accelerate screening only after comparison with full chronology. Storage and maintenance dependencies crossing representative periods need explicit state treatment; seasonal-storage literature shows why period linking matters. The final shortlist is checked on complete chronological years and difficult multi-day periods. [[aggregation]]

### Solar and environmental adapters

Give every weather value an interval/support type: instantaneous sample, interval mean or accumulation. PVGIS satellite timestamps can have location-dependent minute offsets, while reanalysis conventions differ; Open-Meteo reports some radiation values over the preceding hour. The normaliser must implement each documented product convention and retain any approximation to the plant’s hourly mean abstraction. Do not silently floor timestamps or shift all products by one hour. [[pvgis-manual]] [[weather-history]]

Choose one conversion path: horizontal radiation through solar-position/transposition and local shading, or an already tilted product with those operations accounted for. Keep atmospheric resource, horizon/near shading, temperature losses, conversion losses, converter clipping and plant curtailment separate. Future orientation changes must recalculate a compatible resource conversion. A fixed-tilt power trace cannot be reused unchanged for an alternative tilt.

Temperature can drive existing reactor/PV mechanics. Humidity, precipitation, snow and wind/gusts can inform context and qualified operating restrictions. An uploaded wind record must not automatically invent a storm-failure probability, and a rain event must not automatically clean the panels. Site-specific soiling, corrosion, storm damage and repair incidence need their own reviewed transfer models or explicit scenarios. Water availability similarly becomes an operational resource limit only through a real utility model; rainfall alone is not usable process water.

## 8. Objectives, economics and uncertainty

Optimise the **site, plant and service design together**, but expose the decision objective. For initial screening use feasibility filters and a Pareto comparison. For a specified production obligation, minimise discounted project cost subject to delivery/reliability constraints. For an investment comparison, maximise project value under declared prices and risk treatment. A “no build” alternative belongs in the comparison. Maximising utilisation alone can favour undersizing; minimising unit cost alone can ignore total volume or demand.

Keep the current allocated operating-period costs and decision incentives. Add a separate cash-flow model built from physical quantities and explicit payment assumptions. It must not sum a depreciation/ownership allowance into a ledger that already pays the full initial capital. Likewise choose replacement cash expenditures or an economic wear allowance for the relevant view, without charging both for the same consumption.

The new project ledger includes equipment and installation; land acquisition or lease; development and surveys; connection/reinforcement; water and CO₂ treatment/delivery; product handling/export; service depots, consumables and labour; planned replacements; insurance and standing costs; decommissioning; and separately stated residual value. Costs carry currency, price year, tax treatment, quote date, scale and validity. Use a declared real discount rate with real cash flows, or nominal rate with inflation, consistently.

For a pre-tax, unlevered screening case:

`NPV = −initial capital + Σ[(product receipts − cash operating costs − replacement/development cash costs) / (1 + r)^year] + discounted residual value`

`Levelised product cost = discounted attributable cash costs / discounted accepted product quantity`

The numerator definition states whether credits, decommissioning and residual value are included. Zero accepted output leaves unit cost undefined. Revenue uses a separate offtake scenario until delivery and acceptance are modelled. Do not multiply gross hydrogen and methane by sale prices and count both. Original dispatch prices remain frozen; repricing the cash-flow report is allowed, but an economically different dispatch requires a new operating run.

Replace the ambiguous “time to profitability” headline with **annual operating cash margin**, **simple payback**, **discounted payback** and **NPV over a stated project life**. Payback may be “not reached within the study horizon”. If a later replacement reverses cumulative cash flow, show that reversal and distinguish first crossing from sustained recovery. IRR is optional and explicitly unavailable when absent or ambiguous; it is not the default ranker. Add financing, tax and subsidies only as separate, dated scenarios.

Renewable-fuel eligibility and product acceptance affect saleable output and achievable prices. EU rules include additionality and temporal/geographic criteria. A renewable-looking resource trace does not certify compliant hydrogen or methane. Store applicable rule versions and evidence gaps; leave price premiums and subsidies disabled unless their eligibility assumptions are supplied. UK and other European jurisdictions require their own treatment. [[rfnbo]]

### Uncertainty as a decision input

Reuse the existing distinction between unquantified uncertainty, bounded scenarios and supported probability. Nest **site/design choice → persistent equipment world → weather sequence and operating events → numerical repetition**. Preserve correlations between temperature, radiation and adverse service conditions, and between weather and electricity prices when those are modelled jointly. Do not independently shuffle hours or invent cross-site independence for a portfolio.

For probability-supported ensembles, report the median and clearly defined exceedance output, with sample count, horizon and included uncertainty. P90 energy is the level exceeded with 90% probability; it is not the 90th percentile of output and not a guarantee. With unweighted scenarios show ranges and ranking reversals instead. A typical meteorological year is assembled from representative months, and cannot by itself establish a P90 methane claim. [[pv-uncertainty]] [[pvgis-manual]]

Show which uncertainties were held fixed and which evidence gaps prevent an investment interpretation. Ask how conclusions change under plausible CO₂ cost, export price, grid availability, logistics, soiling and repair assumptions. Prioritise evidence by sensitivity and decision reversals. Call it a measurement-priority analysis until a proper prior/posterior and acquisition-cost model supports a monetary value-of-information calculation.

## 9. Integration architecture

Retain Python, Gradio, SciPy/HiGHS, the existing plant kernels and SVG renderer. Add a modular `methane/siting/` layer for geospatial and project concerns. Use MapLibre GL JS for the map; package a pinned library and approved tiles locally where permitted. GIS ingestion and calculations run in Python workers. Regional raster/vector preprocessing is distinct from numerical dispatch. [[maplibre]]

| Contract | Responsibility | Reuse and boundary |
|---|---|---|
| `SiteCandidate` | Stable identity, point/polygon, jurisdiction, CRS, candidate origin | Links to site/environment taxonomy; an assessed location is not an installed plant |
| `SourceSnapshot` | Raw bytes/hash, request, edition, licence, coverage, timestamps, units | Extend weather/provenance conventions; access credentials stay outside artifacts |
| `SiteAssessment` | Evidence-backed constraints, area, infrastructure leads and gaps | Pure GIS transforms and versioned screening rules; no plant execution |
| `DeploymentDesign` | Component configuration, layout, utilities, fleet and cost assumptions | Produces the existing validated Config plus new typed site interfaces |
| `EnvironmentBundle` | Physical time series and separately available forecast vintages | Explicit radiation normalisation, source relationships and missing-data policy |
| `SimulationCheckpoint` | Continuous physical and controller state at a global interval boundary | Execution resumes without resets or truth leakage |
| `YieldStudy` | Matched sites/designs/worlds/years/policies/budgets and saved attempts | Extend immutable Studies, cancellation, source capsules and publications |
| `ProjectCashflow` | Dated economic scenario over recorded physical outputs | Distinct from allocation and dispatch prices; changed prices do not rewrite actions |
| `RecommendationSet` | Search universe, exclusions, trade-offs, rank robustness and caveats | Derived, reproducible analysis; not an unexplained “best location” label |

Separate endpoints load a site, retrieve evidence, assess geometry, preview design, launch a study, poll/cancel, inspect a period and reprice a report. Use server-owned IDs rather than accepting an arbitrary completed run from the browser. Responses carry candidate, geometry version, design, study/publication and request generation; changing selection prevents a late response replacing the current screen.

Reuse the taxonomy’s existing asset IDs within a deployment namespace. Its site/environment and external-services domains can describe supplier, customer, utility and service-base dependencies. A shared stock remains one inventory, not a duplicate in the map and plant. Model essays explain the resource conversion, feasibility rules and cash-flow mechanics; Trace calculation follows a production or cost figure to its operands and source edition.

Use immutable raw snapshots, typed normalised columnar partitions and a lightweight spatial index. GeoPackage/GeoParquet and tiled rasters fit the local project; a managed spatial database is a scaling option, not a first-release requirement. Cache keys include geometry, data editions, transformation versions, model identities, plant configuration, information policy, prices, uncertainty draws and solver settings. Map changes reuse data tiles; price-only changes reuse physical traces; plant changes create new runs.

The existing solar preview should stay isolated from long-running work. Target p95 ≤200 ms for cached selection/simple previews, measure cold first use separately, and keep expensive geography/network requests and annual optimisation asynchronous. Use progressively refined results with explicit fidelity labels. Do not promise instantaneous yearly MPC or send full annual archives through Gradio reactive props. Start with a bounded worker pool and avoid oversubscribing HiGHS across cases.

### Data access and preservation

PVGIS integration belongs server-side because its API does not permit browser AJAX access. Open-Meteo evaluation access and commercial deployment access have different terms; historical and other advanced commercial APIs require an appropriate plan. Record expected data-service and compute costs separately from plant operating costs. Never auto-subscribe or contact a supplier as part of screening. [[pvgis-api]] [[weather-terms]]

Map renderer, data and tile hosting are separate dependencies. Do not bulk-download public OpenStreetMap tiles for offline use. A licensed/self-hosted regional tile bundle can support offline parcel work; Natural Earth is suitable for a lightweight offline overview. Snapshot only data with adequate redistribution rights. Where a source cannot be bundled, retain its identifier and hash, describe the missing prerequisite, and avoid claiming the bundle is completely reproducible offline. [[osm-tiles]] [[natural-earth]]

OpenStreetMap road extracts have ODbL attribution and database obligations. Geocoding, routing and tile services need their own access choices; open map data does not grant unlimited hosted API use. Keep manual coordinates and polygon upload available when online search is unavailable. [[osm-data]]

A study bundle contains the candidate geometry, transformations and constraints; permitted raw inputs; normalised weather and forecast vintages; design and service assumptions; source capsule; checkpoints and result partitions; cost scenario; independent checks; and the authored conclusion. Data updates produce a new assessment edition and an impact diff. They never silently revise a published location ranking.

## 10. Qualification and experiments

| Gate | Required evidence |
|---|---|
| Geospatial correctness | Known polygon areas, CRS conversion, holes/overlaps, shared boundaries, disjoint usable areas, resolution mismatch and missing coverage |
| Weather/solar | Source-unit checks, exact interval mapping, SARAH minute offsets, accumulated-radiation conversion, DST/leap-year handling, missing hours and versioned PVGIS/kernel reconciliation |
| Chronological execution | Chunked vs monolithic short-run parity; no repeated deliveries/starts at boundaries; uninterrupted thermal, inventory, wear, sensor, fault and job state; resume after interruption |
| Information integrity | Future realised weather cannot alter earlier actions; forecasts unavailable before their declared boundary; original prices and true faults stay separated |
| Output accounting | Gross/net/sold product separation, accepted/rejected CO₂, water and energy conservation, terminal inventories and no duplicate storage/throughput credits |
| Economics | Independent discounted-cash-flow examples, zero-output cases, no double capital/wear charge, replacement-induced payback reversal and repricing immutability |
| Comparisons | Same-design and resized-design groups, held-out years, incomplete-case denominators, solver budgets/repeats, declared screening search universe and no required winner |
| Interface/performance | Map/list keyboard flow, full context return, narrow screens, stale results, offline sources, cold and warm latency, animation preservation and bounded memory for a full year |

First assess the three existing regional anchors with pinned resource inputs, then use explicit land/supply/access rules to select a small number of candidate polygons. Keep three complementary comparison sets: identical reference plants across locations; candidate-specific plant sizing under the same budget and information; and the same design with alternative service/logistics choices. Use climate years held out from sizing and forecast-error fitting.

Keep the existing recovery counterexample as a regression and an operational qualification boundary. The recent programme showed 171 independently checked executions, yet a same-condition numerical repeat lost 115.55 kg of methane after an ambiguous capacity estimate locked out a healthy electrolyser. Those are valid recorded model outcomes, not grounds for presenting an autonomous annual yield as established. The [original report](../recovery-comparison/report.html) and [hourly counterexample](../recovery-comparison/repeat-counterexample.json) remain the evidence.

Fix and test that lockout while developing Sites and the data/chronology layer. Compare finite, weather-aware initial diagnosis and post-repair verification windows before qualifying autonomous annual forecasts. Separate initial test deadlines from commissioning deadlines, and account for power, gas headroom, daylight and meaningful load-test depth. Keep bounded escalation. Siting can advance now, but its autonomous-yield claims depend on that work.

A clear acceptance story is: choose a polygon; inspect why it remains a candidate; set up the reference plant and a service option; run a chronological year; identify a low-output period; enter the original plant playback; trace the bottleneck; change one design assumption; compare a new study; and export a self-contained write-up with all unresolved evidence visible.

## 11. Delivery sequence

**A — Sites and evidence.** Deliver the quiet map/list workspace, candidate polygons, source contracts, PVGIS resource adapter, first land/terrain/protection layers, evidence uploads and handoff to the existing short simulation. Gate: a saved candidate can be reproduced offline within its licensed data scope; missing feasibility data stays unresolved. This is already a useful product before annual economics is available.

**B — Continuous production.** Deliver checkpointed annual execution, multi-year weather ingestion, separate resource/design/autonomy modes, calendar-to-playback navigation and independent continuation checks. Resolve the known ambiguity/recovery issue for the qualified autonomous mode. Gate: full-year runs conserve balances across every partition and support honest forecast-information labels. Measure runtime before committing to a large search budget.

**C — Deployment economics and site services.** Add project cash flow, site-specific CO₂/water/offtake inputs, service-base/route/fleet requirements and missing-cost reporting. Implement utilities needed by the chosen operating mode; grid-assisted execution requires its new bus interface and tariffs. Gate: independent financial examples reconcile with physical usage, cash and wear are not duplicated, and a quote change creates a new economic scenario.

**D — Design search and robust shortlist.** Add bounded co-design search, transparent exclusions, Pareto views, multi-year held-out evaluation, uncertainty and numerical repeats, and generated recommendation write-ups. Gate: the report can explain a ranking reversal, a rejected site, an unresolved candidate and a no-build outcome without manufacturing confidence.

**E — Coverage and validated extensions.** Add country packs, supplier/DSO connections and measured calibration datasets according to actual candidate needs. Product-export, capture, future-climate or expanded fleet models enter through their own reviewed contracts. The first four stages deliver the complete methane siting workflow; this stage expands geographical and physical scope without silently changing existing meanings.

The first implementation slice should therefore combine **site selection with traceable real resource data and a continuous-run foundation**. The map provides the new user journey; chronology and economics make its conclusions useful. A blanket European “profitability heatmap” should wait until those dependencies and evidence boundaries are in place.

## 12. References and design status

The primary-source register below was reviewed on 13 September 2026. Only the three PVGIS reference requests were tested live. Other connectors are proposed on the basis of their documentation, with access, coverage and transformation acceptance still required. This design does not select a deployable parcel, calculate annual methane yield or supply a profitability estimate.

Repository inspection used the current component, forecast, study, taxonomy, uncertainty, costing and recovery interfaces. The [integration inventory](integration-inventory.json) records their identities and concrete extension points. The [source register](sources.json), [authored design](design.md) and [report checks](validation.json) accompany this report.

<div id="references"></div>
