# What can the plant actually service?

A realism review of field operations in Dispatch Lab · 12 September 2026

**The review is complete. The realism gate remains open.** The existing model is useful for explaining coupled scheduling, observation delays, resource accounting and conditional service decisions. It is not yet a defensible basis for choosing a real robot fleet, estimating European maintenance savings or training policies whose performance is meant to transfer to a plant.

The most consequential gaps are **what a fault physically means, which observations distinguish its causes, and which intervention can actually resolve it**. Many are already labelled as illustrative in the implementation. This review tests the consequences of those labels rather than treating them as calibration.

Four findings change what I would do next:

1. **Constrain repair capabilities before tuning repair durations.** A general electrolyser capacity-loss fault does not identify a replaceable component. A rover reading a contact is an inspection system; it does not acquire a repair capability. Even the human fallback needs a cause-specific procedure.
2. **Make the information problem less ideal.** Hydrogen inventory and downstream flow provide unusually clean evidence in the current fixture. The cleaning controller knows the type and amount of surface contamination directly. These assumptions affect whether autonomous diagnosis is possible.
3. **Choose a complete hardware configuration.** A dedicated row cleaner, portable operated cleaner, and ground inspection rover have different interfaces, docks, service needs and costs. Evidence for one cannot calibrate another.
4. **Establish when recovered capacity has value.** All corrected 48-hour stress comparisons produced 290 kg of methane, despite different service costs and fault durations. The selected constant-power fixtures hit CO₂ limits. This is a useful counterexample to “repairing faster must increase output,” not a conclusion about London, Seville or Copenhagen.

The broader implementation and learned-policy programme remains paused. Production code, current defaults, original illustrations and earlier archives were not changed. The new work consists of research, separate reproducible challenge cases and this scoped review decision.

## 1. What was reviewed

The review covers the existing 1 MW solar / 800 kWh battery / 450 kW electrolyser fixture, hydrogen and CO₂ buffers, and 10 kg/h methanator. It examines the first service system—cleaning, inspection, reset, human intervention and support—and screens all 14 hardware families from the earlier research.

The European reference locations are London, Seville and Copenhagen. I inspected the existing weather cache and refreshed the relevant primary literature, OEM documentation, regulator guidance and company technical material. There are **28 sources**, **14 family assessments** and **31 consequence-ranked assumptions**. “Commercial” below describes an available bounded capability, not demonstrated suitability for this plant.

Source assessment distinguishes a supplier specification, a primary laboratory/deployment study, a testing protocol and an explicitly missing measurement. Product availability establishes neither the fixture’s numerical parameters nor a field reliability distribution. Undated supplier pages are recorded as accessed on this review date; newer announcements are not silently applied to older hardware versions.

The main production source identity is `76a41fc80ebe5e12f52b4a7c26d3b88a13825e065c9d9e5db47e84f83aaaecfd`. [The review context](review-context.json) captures defaults and the full identity. Each experiment also retains its own configuration, weather, source capsule, archive and independent audit. The optional service models are versioned opt-ins; they are not all active in the default application configuration.

## 2. The first complete service system

### Cleaning: choose the array and cleaner together

The current optical model usefully distinguishes loose material, adhered fouling and permanent damage, and accounts for partial treatment before conversion and clipping. Its hardware abstraction remains generic.

Ecoppia’s T4 specification describes cleaning near-horizontal single-axis trackers, up to 400 m² per night and 3 m²/min, with dedicated solar-powered docks and vendor maintenance. Its 160 km/h figure is a **docked resistance specification**, not a permitted cleaning wind speed. These are manufacturer limits, not a site-average duty cycle. [S01]

At the fixture’s assumed 5,000 m², dividing by that nightly coverage gives a **lower bound of 13 T4 units** for a whole-array nightly pass, before geometry and operating margins. This arithmetic is not a fleet design or quote. It shows why a single generic €15,000 cleaner operating at 1,000 m²/h cannot be labelled a T4 implementation. Fixed-tilt arrays need a compatible alternative.

SolarCleano F1 represents a different comparison: an operator transports and remotely controls a portable wet/dry machine. Setup, transport, water, battery charging and operator attendance belong inside the service boundary. Its advertised throughput must not be interpreted as unattended throughput. [S02]

**Required boundary:** define the compatible array sections and treatment; distinguish resident hardware from a contracted portable service; preserve weather/access restrictions, partial progress, consumable exhaustion, failed work and retrieval. Cleaning does not repair cracked modules or arbitrary permanent losses.

### Inspection: observations, not a fault label

Commercial ground robots carry useful optical, thermal, acoustic and optional gas payloads. Commissioning routes, selecting viewpoints, connectivity, charging and exception handling remain part of the system. ExRobotics explicitly offers service/support arrangements alongside the robot. [S03]

A primary AutoInspect deployment study provides a useful counterweight to broad autonomy language: one 49-day deployment reported 84 missions and 25 interventions; another 35-day deployment reported 81 missions and 16 interventions. Intervention categories and duration denominators matter. These are specific research deployments, not a current commercial failure-rate estimate. They justify recording remote assistance and site work separately. [S04]

Our mobile inspector currently reads a **prepared contact**. It does not perform realistic thermal localization or infer arbitrary component damage. Two readers observing the same stuck contact do not provide two independent health measurements. Zero/span references can assess the acquisition path while leaving a shared physical failure undetected.

Hydrogen-area access also needs a real equipment/site pairing. ANYmal X advertises an IIB configuration; hydrogen’s IIC classification is a consequential distinction. That marketing specification alone does not establish eligibility at the simulated equipment. Inspection from outside a restricted area may be a viable different design. [S05] [S25]

**Required boundary:** record the physical observable, compatible payload/interface, measurement conditions, uncertainty, availability time and hypotheses it can distinguish. A missing or ambiguous observation must remain ambiguous.

### Recovery: identify the cause and the acceptance test

The persistent-fault lifecycle is a sound improvement: physical faults no longer disappear on a timer unless explicitly modelled as transient. The weakness is the breadth of a generic capacity-loss cause and replacement remedy.

Actual OEM documentation distinguishes resettable conditions from failures requiring cause clearance, checks or manufacturer support. Enapter’s public handbook illustrates these differences, rich equipment telemetry and utility dependencies. It describes AEM equipment; it is useful evidence for **the structure of the problem**, not a parameter source for an unspecified 450 kW electrolyser. [S22]

A remote actuator is an engineered interface. It must have a specified physical effect and feedback; an actuator catalogue is not evidence that our electrolyser can safely clear a particular trip. [S16]

Likewise, an automatic pH/ORP cleaning/calibration station is not a solution for a hydrogen-flow meter. Hydrogen metrology needs a suitable meter and reference method. Facilities such as DNV’s hydrogen calibration service illustrate the specificity of the measurement chain. [S14] [S24]

A credible service sequence is:

**Observed symptom → competing causes → informative inspection → permitted remedy → preparation/isolation → intervention → acceptance test → confirmed return.**

Each arrow can fail or require support. “Procedure completed” and “capacity restored” must remain separate records. The existing versioned recovery/verification machinery gives us a useful foundation for this separation.

### Support: account for the whole operating system

The platform already has useful mechanisms for shifts, travel, return journeys, finite stocks, water, retrieval, charging and some service-hardware failures. Their numerical values remain assumptions. A complete first configuration needs:

- Installed equipment, routes, access adaptations, docks, communications and independent/control power.
- Traction, payload, work, standby, charging and thermal-management energy by operating state.
- Brushes, water, filters, reference standards, compatible spares, shelf life and replenishment.
- Routine servicing, remote assistance, retrieval, supplier response, qualified human work and acceptance testing.
- Support failures and shared constraints: a lost dock, inaccessible route or unavailable crew can disable several tasks together.

Do not infer a constant energy load from a maximum-input rating, or a per-mission failure probability from a duration of unattended operation. Do not count a contracted service as owning an additional robot while also charging a contract price that includes it. The current cost separation is useful; actual contract inclusions remain unverified.

## 3. Plant assumptions that determine service value

### The maintenance problem can dominate the robot

A scheduled 50% capacity loss is a challenge scenario, not evidence about fault frequency. A power-stage fault, pump failure, stack ageing, contamination and sensor drift can have different physical effects, observations, restoration paths and consequences. The present scalar derating leaves conversion efficiency unchanged and supplies no cause-specific hazard or degradation process.

DOE’s PEM table gives 55 kWh/kg as a system-level status guidepost; target values are not observed performance. JRC testing protocols explicitly distinguish reference conditions, dynamic loading, cold starts and standby transitions. These support a measured operating envelope, not the current constant efficiency, 40 kWh start or failure rate for every technology. [S20] [S27]

Balance-of-plant loads and limitations matter: water preparation, gas processing, pressure, purge/venting, cooling and power electronics can change both production and the service problem. They are not all resolved by the hourly plant abstraction. [S21]

### Three calculations expose the dominant constraints

| Independent calculation | Fixture result | Implication |
|---|---:|---|
| 300 kg CO₂/day ÷ 2.75 kg CO₂/kg CH₄ | 109.09 kg CH₄/day | Long-run supply ceiling before other losses; 45.45% of reactor nameplate |
| Initial 500 kg CO₂ ÷ 2.75 | 181.82 kg CH₄ | Starting stock can support early production that is not sustainable from deliveries |
| 60 kg H₂ ÷ 0.5 kg H₂/kg CH₄ | 120 kg CH₄ | Storage can hide a temporary upstream shortfall |
| 225 kW derated electrolysis ÷ 55 × 2 | 8.18 kg CH₄/h equivalent | With constant ample power, even the damaged electrolyser exceeds average feedstock-supported demand |
| C/UA = 0.3/0.08 | 3.75 h | Assumed thermal retention timescale, not a measured reactor value |
| Analytic 20→250°C warm-up at 60 kW | 1.373 h | Hourly start eligibility is coarser; auxiliaries and operating limits still apply |

The rounded Sabatier reaction gives 0.5 kg H₂ and 2.75 kg CO₂ per kg CH₄, and 2.8646 kWh/kg reaction heat. The cited methanation paper supports the reaction/heat-management rationale. Its three-phase kinetics experiment does not calibrate our lumped thermal capacity, heat-loss coefficient or operating band. [S28]

Independent calculations across **864 thermal combinations** agree with the production helper to within 1e-9°C (largest observed error about 1.14e-13°C). Some helper inputs intentionally lie outside feasible dispatch limits. This checks the analytic equation; it does not establish realistic start time, internal hot spots, reaction kinetics or pressure-system behaviour.

### The observation model is a structural assumption

The current hydrogen inventory error scales with **that interval’s hydrogen production**. It therefore becomes exactly zero when electrolysis is off. Downstream H₂ withdrawal is exact. Battery energy, CO₂ inventory and reactor temperature are also ideal observations in this bounded diagnosis model.

Real metrology specifications can combine reading-dependent error, full-scale error and temperature dependence. A Bronkhorst hydrogen-meter specification makes that distinction explicit; it is not proposed as the correct flow/pressure-range meter for this plant. Accuracy limits also are not the standard deviation of independent Gaussian noise. [S23]

In a six-interval challenge with a true 5 kg/h inflow/outflow, the production diagnosis function isolates a 30% biased flow channel when the independent balance is ideal. Add a declared 0.6 kg/h inventory-reading drift and the same flow bias remains ambiguous. These deliberately chosen amplitudes are **counterexamples, not measured sensor ranges**. They show that fault identifiability depends on the balance measurement model. Outflow error and cancellation/common-error cases are retained alongside them in [the mechanism checks](experiments/mechanism-checks.json).

The right next question is not “what noise percentage should every sensor have?” It is “which physically separate measurements can distinguish these causes, at what load, with what uncertainty?”

## 4. What the experiments establish

### Design and preservation

The [primary protocol](protocol.json) froze 84 complete inputs before execution: cleaning and recovery arms across three seeds. Cleaning has **2 power levels × 2 loose-soil levels × 3 arms × 3 seeds = 36 cases**; recovery has **4 conditions × 4 arms × 3 seeds = 48 cases**.

All use Greedy, the same hourly plant, named target/action randomness, initial battery SOC 50%, no continuing soil deposition, 20°C ambient and declared constant input. Cleaning power is 300 or 1,000 kW; recovery power is 650 kW with one half-capacity incident at hour 6. These are deliberately conditional challenges, **not synthetic approximations labelled as European weather**. Two-percent sensor noise, generic success probabilities and ideal surface observations remain explicit limitations.

The review setup mistakenly set the portable adhered-soil trigger to zero. Because eligibility uses “greater than or equal,” this caused repeated work even with no adhered soil. All affected cases are preserved as configuration-error evidence. The [documented amendment](portable-correction.json) reran every affected arm with a positive 0.02 adhered trigger and the existing 0.04 loose trigger. No production code was changed and no losing result was silently dropped.

The window check extended every seed-7 configuration to 240 hours; its [protocol](boundary-protocol.json) was declared after the first suite started and before extension execution. The same portable correction was applied. This is a boundary check using one seed, not an additional independent reliability sample.

**128 executions were retained: 112 comparison cases and 16 superseded setup-error cases.** All completed numerically and passed their independent audits. Unsuccessful interventions and unverified work remain in those completed runs. The 101 targeted tests also passed. The 1,970,488 audit assertions are repeated interval checks, not that many independent proofs of realism.

### Recovered sunlight is not necessarily extra product

{{CLEANING_TABLE}}

Values are means over seeds 7, 19 and 31, at 1,000 kW unsoiled input and 10% initial loose loss, after the setup correction. Cost numbers use the frozen illustrative assumptions. All three arms produce **290 kg methane**. The resident cleaner restores about **3,764 kWh** of DC availability over 48 hours, but it does not increase methane because other constraints bind. The 300 kW cases also reach 290 kg; ending H₂ differs and is retained, without speculative resale credit.

At 1% soil, neither corrected cleaning policy calls for cleaning. The resident hardware still incurs ownership/support allocation; the portable service incurs only its configured standing allocation. At 10% soil, the portable arm is a different operated treatment and logistics bundle, including multiple visits. Its cost must not be used as an isolated estimate of the value of “autonomy.”

### Reset availability changes the preferred service path

{{RECOVERY_TABLE}}

Fault duration is retrospective simulator truth; it is not what the controller knows. All these arms again produce 290 kg. Fixed-assisted recovery clears the **declared resettable trip** in four fault-active hours in each seed, with no visit; mobile-assisted recovery takes five. Remove the reset or change the cause to physical damage and the assisted options need the same human remedy as the baseline. Under those assumptions, human-only service is cheaper and, on successful seeds, earlier than waiting for inspection before replacement.

This is a **conditional ranking reversal among intervention options**: fixed assistance is attractive when a valid remote reset avoids a visit; its advantage disappears when that remedy is unavailable. It does not establish that a real crew should replace a module to clear a resettable trip. Our human-only rule does exactly that, making it an over-expensive baseline for some real procedures. A qualified human local reset must be a separate action before making a deployment claim.

No-service remains a legitimate physical baseline and leaves the fault unresolved. Its lower cost for damage in these cases is not a recommendation to tolerate a real failure. The review fixture supplies neither a real operating obligation nor a calibrated risk consequence for remaining damaged.

### Ending the experiment changes the question

At 240 hours, every corrected seed-7 configuration produces **1,163.64 kg CH₄**, exactly the ideal mass ceiling from 500 kg opening CO₂ plus nine 300 kg deliveries. Ending CO₂ is zero within floating-point tolerance. Battery energy is 800 kWh; ending H₂ is about 57.72–60 kg. The feedstock ceiling persists in this extension; the conclusion is bounded to these constant-power cases.

In seed 7, the assumed human replacement attempt is unsuccessful: the capacity fault remains active for all 234 post-onset hours of the extended window, with work awaiting verification. Extending the window does not convert procedure completion into recovery. Other seeds in the 48-hour suite have successful replacements. Three seeds are insufficient to infer an empirical success probability.

A next comparison must report terminal equipment condition, unverified/blocked work, return travel, stock/refill obligations and stored energy/material as well as methane. The [case index](experiments/case-index.csv), [analysis](experiments/analysis.json) and linked case summaries retain these values. No terminal sale proceeds were invented.

### Price thresholds rather than invented European cost ranges

For a fixed matched trace, the methane-price threshold is:

`break-even price = extra action-dependent cost / extra methane`

This is meaningful only when extra methane is positive. Here, additional methane is zero in every matched intervention comparison. There is **no finite positive-output methane price threshold** that makes those interventions pay through extra methane in this window. Some interventions change wear/start costs or avoid a human visit; those are separate measured model consequences. Fixed-trace repricing does not alter dispatch.

For annual hardware selection the relevant conditional relation is:

`required avoided visits/year = extra annual ownership and support / net value per avoided visit`

Neither a site-specific numerator nor a defensible incident/avoided-visit denominator is established. We should publish the threshold once hardware scope and service quotes exist, not turn injected faults into an annual rate. Methane value, response times, success probabilities and capital costs here remain illustrative.

## 5. European applicability and missing data

The existing cache contains **109 weather responses** for the three selected coordinates: 100 archived forecast responses and nine historical-reference responses covering the planned January, April and July windows. The [cache inventory](experiments/weather-inventory.json) records hashes, retrieval metadata, requested variables and coverage. This review did not relabel them as site measurements or rerun the earlier historical study.

They retain tilted irradiance, ambient temperature and humidity. **None contains precipitation or wind.** They therefore support parts of the solar/thermal replay but cannot establish cleaner/drone operating windows, rainfall wash-off, storm-related access or weather-correlated service failures. The current fixed service-weather assumptions must not be presented as derived from those cached European forecasts.

The IEA PVPS soiling report describes location-dependent mechanisms and measurement uncertainty. It does not establish the fixture’s 0.5-percentage-point daily accumulation for these sites. A global annual loss estimate is not a local daily deposition rate. [S26]

The next site evidence should cover local soiling/reference measurements, precipitation and wind, array geometry, surrounding vegetation/dust exposure, access restrictions, utility availability and realistic supplier/crew logistics. For drones, London also needs a UK-specific operating basis; EU/EASA guidance is not a substitute. [S09] [S10]

A useful experiment can remain simple: measured or defensibly bounded loss, compatible treatment and service windows, with unavailable days and support obligations. More detailed robot animation or random failures would not fill these gaps.

## 6. All 14 hardware families

The table is a feasibility screen, not a procurement recommendation. Each row links to the primary evidence and states which capability is unavailable or conditional. A general service-object architecture can represent all these families; it must not grant them identical repair powers.

{{FAMILY_TABLE}}

Near-term expansion is most credible in compatible cleaning, fixed sensing, commissioned inspection and purpose-built actuation. Broader manipulation should remain a separate research/design scenario: Taurob labels Operator a prototype, while the Robot Factors work demonstrates prepared laboratory interfaces rather than qualified gas-system replacement. [S06] [S07]

The remaining families also change the plant boundary. A sample selector needs an analyzer and conditioning chain; a wall-thickness crawler needs a degradation mechanism; mowing needs vegetation/access effects. Construction systems belong in installation/commissioning economics, not daily service uptime. None should be added merely as another asset with a duration and success probability.

## 7. Decision and recommended next scope

| Proposed use | Review decision | Required boundary |
|---|---|---|
| Explain hourly coupling, accounting, persistent faults and observation timing | Proceed, conditional | Keep current assumptions and versions visible; use the independent checks |
| Compare declared prepared-interface service mechanisms | Proceed as teaching/threshold cases | No real robot, site-rate or annual-saving claim |
| Claim realistic autonomous diagnosis and repair for this plant | Gate open | Cause-specific capability and metrology contracts are missing |
| Select a real fleet or report European maintenance ROI | Gate open | Compatible hardware, site exposure, support scope and prices are missing |
| Invest heavily in learned policies intended to generalize to equipment changes | Defer | Fix the action/observation problem first; otherwise training optimizes unsupported premises |
| Add all remaining families as realistic operational options | Defer by family | Complete each family’s feasibility gate and required plant mechanism |

**My recommended first credible configuration is fixed sensing plus one explicitly engineered remote-recovery task, a cause-specific human fallback, and a compatible cleaning comparison.** Keep a mobile inspector only where it can provide useful information unavailable from fixed telemetry or access a distinct inspection task. This does not remove the robotic direction: it identifies where mobility can earn its complexity.

I would next prepare a small cause-and-procedure catalogue, with four records for each candidate: physical effect; observable evidence; permitted recovery; successful-return criteria. Include an unresolved/unknown cause. Distinguish a control latch from physical component damage and from a measurement fault. Add a human local-reset action so the baseline is credible.

Then replace ideal inventory/surface knowledge with explicitly modelled observation chains; bind the cleaner to an array layout and support system; and obtain or expose gaps in site service-window and cost evidence. Re-run the same studies as new editions, carrying forward every old result with its original scope. Only then compare increasingly sophisticated planners or learned policies against the corrected problem.

This recommendation changes the admissible action set and what the controller knows. It is the appropriate point for your guidance before further implementation. **I have not made those production changes or resumed the paused programme.**

## 8. Assumption register

Priority 0 means the assumption can make an action impossible or a diagnosis unidentifiable. Priority 1 can change the service value or ranking; priority 2 limits interpretation or later extension. These priorities are consequences, not a numerical trust score.

The [structured register](assumptions.json) includes stable IDs, configuration bindings/defaults, source identity, evidence gaps, consequences and review invalidation rules. An explicit gap is a reason to constrain a claim, not permission to assume any convenient value.

{{ASSUMPTIONS}}

## 9. Evidence, reproduction and limits

The independent checker reconstructs balances, service-resource accounting, timing/compatibility and cost arithmetic under declared inputs. It does not independently validate every observer decision or calibrate mission success. Targeted tests cover surface treatment and clipping, unavailable access/weather, measurement references and timing, support and hardware failures, economic accounting and deliberate audit mutations.

The new observation challenges invoke diagnosis only with declared observations; they do not pass an injected fault type to it. The thermal reference calculation uses high-precision Decimal exponentials independently of the production helper. Passing both calculations supports the equation, not the chosen thermal constants. No new empirical plant trial was conducted.

The report is self-contained for offline reading. Sources remain external links; the numerical evidence is local. [Reproduction instructions](README.md) explain the frozen inputs, amendments, scripts and archive hashes. Reruns should create new output directories and preserve the original source identity; a changed implementation is a new experiment edition, not an overwrite.

Access limits were recorded rather than concealed: the NREL 2009 wind-to-hydrogen PDF could not be retrieved from the attempted endpoint, and an initially attempted RSC publisher route was unavailable. The methanation paper was subsequently read through the author’s KIT repository. No inaccessible source was used to invent a numerical parameter.

This is a source/code/numerical review, not an independent equipment qualification or an empirical reliability study. The evidence is enough to identify the changes that matter before further investment. It does not establish a calibrated envelope for all 31 assumptions.

## 10. Sources

{{SOURCES}}
