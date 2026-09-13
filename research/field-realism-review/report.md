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

Ecoppia’s T4 specification describes cleaning near-horizontal single-axis trackers, up to 400 m² per night and 3 m²/min, with dedicated solar-powered docks and vendor maintenance. Its 160 km/h figure is a **docked resistance specification**, not a permitted cleaning wind speed. These are manufacturer limits, not a site-average duty cycle. [Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf)

At the fixture’s assumed 5,000 m², dividing by that nightly coverage gives a **lower bound of 13 T4 units** for a whole-array nightly pass, before geometry and operating margins. This arithmetic is not a fleet design or quote. It shows why a single generic €15,000 cleaner operating at 1,000 m²/h cannot be labelled a T4 implementation. Fixed-tilt arrays need a compatible alternative.

SolarCleano F1 represents a different comparison: an operator transports and remotely controls a portable wet/dry machine. Setup, transport, water, battery charging and operator attendance belong inside the service boundary. Its advertised throughput must not be interpreted as unattended throughput. [SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1)

**Required boundary:** define the compatible array sections and treatment; distinguish resident hardware from a contracted portable service; preserve weather/access restrictions, partial progress, consumable exhaustion, failed work and retrieval. Cleaning does not repair cracked modules or arbitrary permanent losses.

### Inspection: observations, not a fault label

Commercial ground robots carry useful optical, thermal, acoustic and optional gas payloads. Commissioning routes, selecting viewpoints, connectivity, charging and exception handling remain part of the system. ExRobotics explicitly offers service/support arrangements alongside the robot. [ExRobotics products and services](https://www.exrobotics.com/our-products)

A primary AutoInspect deployment study provides a useful counterweight to broad autonomy language: one 49-day deployment reported 84 missions and 25 interventions; another 35-day deployment reported 81 missions and 16 interventions. Intervention categories and duration denominators matter. These are specific research deployments, not a current commercial failure-rate estimate. They justify recording remote assistance and site work separately. [AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2)

Our mobile inspector currently reads a **prepared contact**. It does not perform realistic thermal localization or infer arbitrary component damage. Two readers observing the same stuck contact do not provide two independent health measurements. Zero/span references can assess the acquisition path while leaving a shared physical failure undetected.

Hydrogen-area access also needs a real equipment/site pairing. ANYmal X advertises an IIB configuration; hydrogen’s IIC classification is a consequential distinction. That marketing specification alone does not establish eligibility at the simulated equipment. Inspection from outside a restricted area may be a viable different design. [ANYmal X](https://www.anybotics.com/robotics/anymal-x/) [Ignition and flow stopping considerations for hydrogen networks](https://hysafe.info/uploads/papers/2023/114.pdf)

**Required boundary:** record the physical observable, compatible payload/interface, measurement conditions, uncertainty, availability time and hypotheses it can distinguish. A missing or ambiguous observation must remain ambiguous.

### Recovery: identify the cause and the acceptance test

The persistent-fault lifecycle is a sound improvement: physical faults no longer disappear on a timer unless explicitly modelled as transient. The weakness is the breadth of a generic capacity-loss cause and replacement remedy.

Actual OEM documentation distinguishes resettable conditions from failures requiring cause clearance, checks or manufacturer support. Enapter’s public handbook illustrates these differences, rich equipment telemetry and utility dependencies. It describes AEM equipment; it is useful evidence for **the structure of the problem**, not a parameter source for an unspecified 450 kW electrolyser. [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/)

A remote actuator is an engineered interface. It must have a specified physical effect and feedback; an actuator catalogue is not evidence that our electrolyser can safely clear a particular trip. [Rotork IQ3 Pro intelligent actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro)

Likewise, an automatic pH/ORP cleaning/calibration station is not a solution for a hydrogen-flow meter. Hydrogen metrology needs a suitable meter and reference method. Facilities such as DNV’s hydrogen calibration service illustrate the specificity of the measurement chain. [Endress+Hauser Liquiline Control CDC90](https://www.endress.com/en/field-instruments-overview/liquid-analysis-product-overview/pH-sensor-automatic-cleaning-calibration-cdc90) [DNV hydrogen and renewable flow calibration](https://www.dnv.com/energy/services/laboratories-test-facilities/technology-centre-groningen-the-netherlands/hydrogen-and-renewable-flow-calibration/)

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

DOE’s PEM table gives 55 kWh/kg as a system-level status guidepost; target values are not observed performance. JRC testing protocols explicitly distinguish reference conditions, dynamic loading, cold starts and standby transitions. These support a measured operating envelope, not the current constant efficiency, 40 kWh start or failure rate for every technology. [DOE technical targets for PEM electrolysis](https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis) [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf)

Balance-of-plant loads and limitations matter: water preparation, gas processing, pressure, purge/venting, cooling and power electronics can change both production and the service problem. They are not all resolved by the hourly plant abstraction. [Hydrogen Shot Water Electrolysis Technology Assessment](https://www.energy.gov/sites/default/files/2024-12/hydrogen-shot-water-electrolysis-technology-assessment.pdf)

### Three calculations expose the dominant constraints

| Independent calculation | Fixture result | Implication |
|---|---:|---|
| 300 kg CO₂/day ÷ 2.75 kg CO₂/kg CH₄ | 109.09 kg CH₄/day | Long-run supply ceiling before other losses; 45.45% of reactor nameplate |
| Initial 500 kg CO₂ ÷ 2.75 | 181.82 kg CH₄ | Starting stock can support early production that is not sustainable from deliveries |
| 60 kg H₂ ÷ 0.5 kg H₂/kg CH₄ | 120 kg CH₄ | Storage can hide a temporary upstream shortfall |
| 225 kW derated electrolysis ÷ 55 × 2 | 8.18 kg CH₄/h equivalent | With constant ample power, even the damaged electrolyser exceeds average feedstock-supported demand |
| C/UA = 0.3/0.08 | 3.75 h | Assumed thermal retention timescale, not a measured reactor value |
| Analytic 20→250°C warm-up at 60 kW | 1.373 h | Hourly start eligibility is coarser; auxiliaries and operating limits still apply |

The rounded Sabatier reaction gives 0.5 kg H₂ and 2.75 kg CO₂ per kg CH₄, and 2.8646 kWh/kg reaction heat. The cited methanation paper supports the reaction/heat-management rationale. Its three-phase kinetics experiment does not calibrate our lumped thermal capacity, heat-loss coefficient or operating band. [Determination of reaction kinetics in three phase CO₂ methanation](https://publikationen.bibliothek.kit.edu/1000188810/171087110)

Independent calculations across **864 thermal combinations** agree with the production helper to within 1e-9°C (largest observed error about 1.14e-13°C). Some helper inputs intentionally lie outside feasible dispatch limits. This checks the analytic equation; it does not establish realistic start time, internal hot spots, reaction kinetics or pressure-system behaviour.

### The observation model is a structural assumption

The current hydrogen inventory error scales with **that interval’s hydrogen production**. It therefore becomes exactly zero when electrolysis is off. Downstream H₂ withdrawal is exact. Battery energy, CO₂ inventory and reactor temperature are also ideal observations in this bounded diagnosis model.

Real metrology specifications can combine reading-dependent error, full-scale error and temperature dependence. A Bronkhorst hydrogen-meter specification makes that distinction explicit; it is not proposed as the correct flow/pressure-range meter for this plant. Accuracy limits also are not the standard deviation of independent Gaussian noise. [Bronkhorst MV-191-H2 datasheet](https://products.bronkhorst.com/media/lbmdbkcf/3276-mv-191-h2-en-datasheet.pdf)

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


| Arm | Available DC kWh | Service allocation € | Plant + service allocation € | Operating contribution € | Visits |
| --- | --- | --- | --- | --- | --- |
| no-cleaning | 43,200.00 | 0.00 | 730.04 | 65.65 | 0.00 |
| condition-cleaner | 46,964.40 | 55.54 | 785.58 | 46.27 | 0.00 |
| portable-wet | 46,358.80 | 2,465.86 | 3,195.90 | -2,399.87 | 3.33 |



Values are means over seeds 7, 19 and 31, at 1,000 kW unsoiled input and 10% initial loose loss, after the setup correction. Cost numbers use the frozen illustrative assumptions. All three arms produce **290 kg methane**. The resident cleaner restores about **3,764 kWh** of DC availability over 48 hours, but it does not increase methane because other constraints bind. The 300 kW cases also reach 290 kg; ending H₂ differs and is retained, without speculative resale credit.

At 1% soil, neither corrected cleaning policy calls for cleaning. The resident hardware still incurs ownership/support allocation; the portable service incurs only its configured standing allocation. At 10% soil, the portable arm is a different operated treatment and logistics bundle, including multiple visits. Its cost must not be used as an isolated estimate of the value of “autonomy.”

### Reset availability changes the preferred service path


| Condition | Arm | Fault hours mean (range) | Visits | Service allocation € | Total allocation € |
| --- | --- | --- | --- | --- | --- |
| resettable-trip | no-service | 42.0 (42–42) | 0.00 | 0.00 | 757.28 |
| resettable-trip | human-only | 18.7 (7–42) | 1.00 | 1,180.00 | 1,920.52 |
| resettable-trip | fixed-assisted | 4.0 (4–4) | 0.00 | 4.11 | 738.35 |
| resettable-trip | mobile-assisted | 5.0 (5–5) | 0.00 | 84.45 | 821.48 |
| equipment-damage | no-service | 42.0 (42–42) | 0.00 | 0.00 | 757.28 |
| equipment-damage | human-only | 18.7 (7–42) | 1.00 | 1,180.00 | 1,920.52 |
| equipment-damage | fixed-assisted | 19.3 (8–42) | 1.00 | 1,184.11 | 1,924.63 |
| equipment-damage | mobile-assisted | 20.0 (9–42) | 1.00 | 1,264.45 | 2,004.97 |
| reset-unavailable | no-service | 42.0 (42–42) | 0.00 | 0.00 | 757.28 |
| reset-unavailable | human-only | 18.7 (7–42) | 1.00 | 1,180.00 | 1,920.52 |
| reset-unavailable | fixed-assisted | 19.3 (8–42) | 1.00 | 1,182.74 | 1,923.26 |
| reset-unavailable | mobile-assisted | 20.0 (9–42) | 1.00 | 1,263.08 | 2,003.60 |
| crew-unavailable | no-service | 42.0 (42–42) | 0.00 | 0.00 | 757.28 |
| crew-unavailable | human-only | 42.0 (42–42) | 0.00 | 0.00 | 757.28 |
| crew-unavailable | fixed-assisted | 4.0 (4–4) | 0.00 | 4.11 | 738.35 |
| crew-unavailable | mobile-assisted | 5.0 (5–5) | 0.00 | 84.45 | 821.48 |



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

The IEA PVPS soiling report describes location-dependent mechanisms and measurement uncertainty. It does not establish the fixture’s 0.5-percentage-point daily accumulation for these sites. A global annual loss estimate is not a local daily deposition rate. [Soiling losses — impact on photovoltaic power plants](https://iea-pvps.org/wp-content/uploads/2023/01/IEA-PVPS-T13-21-2022-EXEC-SUMM-Soiling-Losses-PV-Plants.pdf)

The next site evidence should cover local soiling/reference measurements, precipitation and wind, array geometry, surrounding vegetation/dust exposure, access restrictions, utility availability and realistic supplier/crew logistics. For drones, London also needs a UK-specific operating basis; EU/EASA guidance is not a substitute. [EASA Specific Category — Civil Drones](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones) [UK CAA categories of UAS operations](https://regulatorylibrary.caa.co.uk/2019-947/Content/AMC-GM/GM1%20Article%203%20Categories%20of.htm)

A useful experiment can remain simple: measured or defensibly bounded loss, compatible treatment and service windows, with unavailable days and support obligations. More detailed robot animation or random failures would not fill these gaps.

## 6. All 14 hardware families

The table is a feasibility screen, not a procurement recommendation. Each row links to the primary evidence and states which capability is unavailable or conditional. A general service-object architecture can represent all these families; it must not grant them identical repair powers.


| Family / maturity | Supported task and boundary | Required support / current model |
| --- | --- | --- |
| **F01 · Dedicated solar-row cleaner**<br>Conditional commercial | Dry removal of compatible loose deposits on prepared rows.<br>**Unavailable:** One generic robot serving arbitrary array geometry; removal of permanent damage.<br>[Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) [Soiling losses — impact on photovoltaic power plants](https://iea-pvps.org/wp-content/uploads/2023/01/IEA-PVPS-T13-21-2022-EXEC-SUMM-Soiling-Losses-PV-Plants.pdf) | Named cleaner/module/tracker combination; parking, bridges, clearances, approved operating weather.<br>Per-row docks, communications, brushes, inspection, retrieval and vendor maintenance.<br>**Model:** Section optical treatment exists; generic 1,000 m²/h and bus-fed charger are not T4 parameters. |
| **F02 · Portable wet/dry cleaner**<br>Commercial, human operated | Person-deployed and supervised compatible cleaning.<br>**Unavailable:** Unattended deployment or operation inferred from remote control.<br>[SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1) | Access, lifting/transport, module limits, water method, operator availability.<br>Travel, setup, water/refill, battery charging, consumables, return journey.<br>**Model:** Portable wet service/logistics implemented as illustrative bundle. |
| **F03 · Mobile ground inspector**<br>Conditional commercial | Commissioned visual/thermal/acoustic/gas observations with appropriate payload.<br>**Unavailable:** Repair, unqualified hydrogen-area access, or universal fault localization.<br>[ExRobotics products and services](https://www.exrobotics.com/our-products) [AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2) [ANYmal X](https://www.anybotics.com/robotics/anymal-x/) [Ignition and flow stopping considerations for hydrogen networks](https://hysafe.info/uploads/papers/2023/114.pdf) | Route, lighting, terrain, stairs, reachable view/port and gas-group/payload certificate.<br>Dock, mapping, connectivity, remote assistance, retrieval, batteries and vendor service.<br>**Model:** Mobile prepared-contact reader exists; not a realistic visual/thermal inspection model. |
| **F04 · Docked aerial inspector**<br>Conditional commercial | Permitted repeatable visual/thermal survey.<br>**Unavailable:** General manipulation, concealed-fault diagnosis or permission implied by autonomy.<br>[DJI Dock 3 specifications](https://enterprise.dji.com/dock-3/specs) [EASA Specific Category — Civil Drones](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones) [UK CAA categories of UAS operations](https://regulatorylibrary.caa.co.uk/2019-947/Content/AMC-GM/GM1%20Article%203%20Categories%20of.htm) | Flight authorization, site airspace, landing margin, weather and inspection conditions.<br>Dock mains/backup, internet, aircraft maintenance, remote pilot responsibilities and retrieval.<br>**Model:** Catalogue concept; no complete flight/payload mechanism reviewed. |
| **F05 · Contact inspection crawler**<br>Specialist commercial | Compatible contact/ultrasonic material measurements.<br>**Unavailable:** Repair or automatic launch on every process surface.<br>[Reinforcement Learning for RUG](https://www.geckorobotics.com/resources/blog/reinforcement-learning-for-rug) | Reachable material, coupling/contact, geometry and a thickness/degradation hypothesis.<br>Preparation, qualified interpretation, deployment/retrieval, sensor maintenance.<br>**Model:** No corresponding wall-integrity process in current plant. |
| **F06 · Vegetation-management robot**<br>Conditional commercial | Mapped vegetation cutting on suitable ground.<br>**Unavailable:** Universal terrain operation or value without vegetation/access mechanics.<br>[Renu Robotics autonomous vegetation management](https://renurobotics.com/about-us/) | Terrain/obstacles, exclusion rules, growth and shading/access effects.<br>Charging pod, Mission Control, blade service, weather and recovery.<br>**Model:** Future site-operations mechanism. |
| **F07 · Sampling and analyzer station**<br>Commercial engineered subsystem | Switch and condition compatible process/reference samples.<br>**Unavailable:** Complete chemical diagnosis or certification from a selector alone.<br>[Swagelok calibration and switching modules](https://products.swagelok.com/en/all-products/analytical-instrumentation/analytical-subsystems-press/calibrating-switching-modules/c/502?clp=true) | Analyzer, gas compatibility, flow/pressure conditioning, transport/purge delays.<br>Reference gases, filters, utilities, calibration, purge/sample accounting.<br>**Model:** No complete analyzer/sample-chain model. |
| **F08 · Automatic sensor service station**<br>Commercial for named sensors | Clean/calibrate a compatible pH/ORP sensor using the specified station.<br>**Unavailable:** Generic autonomous hydrogen-flow calibration.<br>[Endress+Hauser Liquiline Control CDC90](https://www.endress.com/en/field-instruments-overview/liquid-analysis-product-overview/pH-sensor-automatic-cleaning-calibration-cdc90) [DNV hydrogen and renewable flow calibration](https://www.dnv.com/energy/services/laboratories-test-facilities/technology-centre-groningen-the-netherlands/hydrogen-and-renewable-flow-calibration/) | Matching sensor, references, retractable assembly and permitted environment.<br>Reagents, reference replacement, waste, pneumatics and technician service.<br>**Model:** Generic calibration remedy lacks identified H2 metrology procedure. |
| **F09 · Rugged fixed sensor package**<br>Conditional commercial | Named electrical/process/material measurements with bounded error.<br>**Unavailable:** Perfect inventory, exact loose/adhered fractions or generic remaining-life truth.<br>[Emerson corrosion and erosion monitoring](https://www.emerson.com/en/measurement-instrumentation/catalog/corrosion-and-erosion-monitoring) [Bronkhorst MV-191-H2 datasheet](https://products.bronkhorst.com/media/lbmdbkcf/3276-mv-191-h2-en-datasheet.pdf) [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf) | Measurement model, range, placement, references and channel independence.<br>Calibration, drift checks, protection, power/comms and replacement.<br>**Model:** Fixed contact/reference acquisition exists; other ideal plant observations remain. |
| **F10 · Remote actuator / redundant service path**<br>Conditional engineered capability | Command and verify a specified permitted action after cause clearance.<br>**Unavailable:** Reset repairing physical damage; bypass of unresolved trips.<br>[Rotork IQ3 Pro intelligent actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro) [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/) | OEM semantics, permissives, position/process feedback, power and communication.<br>Actuator maintenance, stored-energy provision where required, testing and fallback.<br>**Model:** Latched trip reset exists; only an illustrative engineered interface. |
| **F11 · Mobile maintenance manipulator**<br>Prototype / speculative for this plant | Separate prepared-site research tasks.<br>**Unavailable:** Credible default autonomous electrolyser repair or consumable exchange.<br>[Taurob Operator](https://www.taurob.com/operator/) | Reach, tool, torque, connectors, isolation and acceptance specification.<br>Tooling, fixtures, remote supervision, parts and recovery.<br>**Model:** Future capability; do not substitute rover inspection for manipulation. |
| **F12 · Robot-compatible replaceable module**<br>Design principle demonstrated in laboratory | Explicitly speculative purpose-designed module scenario.<br>**Unavailable:** Qualified hydrogen module replacement inferred from a water-filter lab demo.<br>[A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf) [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/) | Guides/connectors, depressurization/isolation, lifting, seals and proof tests.<br>Spare compatibility, handling, waste, tools and trained fallback.<br>**Model:** Current human module replacement is generic; robotic replacement not established. |
| **F13 · Solar construction robot**<br>Company-reported commercial deployments | Construction-phase installation assistance on compatible designs.<br>**Unavailable:** Ongoing maintenance autonomy or whole-site commissioning from panel placement alone.<br>[Maximo completes 100 MW of robotic solar installation](https://www.nasdaq.com/press-release/maximo-completes-100-mw-robotic-solar-installation-2026-03-25) [Next-generation Terafab completes field testing](https://www.terabase.energy/resources/terabase-energys-next-generation-terafab-completes-field-testing-ready-for-deployment) | Foundation/tracker readiness, logistics, quality acceptance and crew workflow.<br>Mobilization, transport, rented equipment, operators and commissioning.<br>**Model:** Separate build-phase scenario; not daily service comparison. |
| **F14 · Pre-integrated deployable solar array**<br>Commercial, crew assisted | Alternative array/deployment design.<br>**Unavailable:** An autonomous maintenance robot.<br>[5B Maverick](https://5b.co/en/5b-maverick) | Ground preparation, access, footprint, wind design and compatible cleaning.<br>Transport, crew, telehandler, electrical commissioning and O&M access.<br>**Model:** Separate plant-design alternative. |



Near-term expansion is most credible in compatible cleaning, fixed sensing, commissioned inspection and purpose-built actuation. Broader manipulation should remain a separate research/design scenario: Taurob labels Operator a prototype, while the Robot Factors work demonstrates prepared laboratory interfaces rather than qualified gas-system replacement. [Taurob Operator](https://www.taurob.com/operator/) [A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf)

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

### A01 · A generic module replacement restores capacity damage

**Priority 0 · Feasibility/restoration.** Current assumption: equipment-damage → nominal capacity after successful module-replacement.

**Evidence or gap:** No component-specific cause or compatible replacement procedure identified. [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/) [A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf)

**Consequence:** Remedy may not exist; a faster repair simulation cannot answer its value. **Required:** Specify pump/power-stage/stack cause separately, named remedy, prerequisites and acceptance; unresolved causes require human escalation.

**Check:** Numerical checks do not establish empirical validity. Binding: `faults.capacity_cause` = equipment-damage.

### A02 · A trip may be cleared by a remote reset

**Priority 0 · Action availability.** Current assumption: Latched resettable-trip; reset duration 0.25 h.

**Evidence or gap:** Cause-clearance and actual OEM interface unbound. [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/) [Rotork IQ3 Pro intelligent actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro)

**Consequence:** A nominal reset could mask a persistent unsafe/process condition. **Required:** Model cause clearance, reset eligibility, command feedback and successful process tracking separately.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.reset_enabled` = True; `service_system.reset_hours` = 0.25.

### A03 · Flow bias is removable by a generic calibration task

**Priority 0 · Metrology/remedy.** Current assumption: Successful calibration clears injected bias.

**Evidence or gap:** No named H2 meter, reference path or on-site procedure. pH/ORP station is incompatible evidence. [Endress+Hauser Liquiline Control CDC90](https://www.endress.com/en/field-instruments-overview/liquid-analysis-product-overview/pH-sensor-automatic-cleaning-calibration-cdc90) [DNV hydrogen and renewable flow calibration](https://www.dnv.com/energy/services/laboratories-test-facilities/technology-centre-groningen-the-netherlands/hydrogen-and-renewable-flow-calibration/) [Bronkhorst MV-191-H2 datasheet](https://products.bronkhorst.com/media/lbmdbkcf/3276-mv-191-h2-en-datasheet.pdf)

**Consequence:** Invalid repair option distorts downtime and robot value. **Required:** Choose a specific meter and permitted verification/replacement/calibration workflow; otherwise leave fault unresolved.

**Check:** Numerical checks do not establish empirical validity. Binding: `scenario.flow_bias_fraction` = 0.

### A04 · Inventory provides independent high-quality H2 balance

**Priority 0 · Observability.** Current assumption: Noise SD = hourly H2 production × 0.02; exact when production = 0.

**Evidence or gap:** No pressure/temperature/volume metrology or measured error covariance. [Bronkhorst MV-191-H2 datasheet](https://products.bronkhorst.com/media/lbmdbkcf/3276-mv-191-h2-en-datasheet.pdf) [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf)

**Consequence:** Current diagnosis may lose identifiability with range errors or drift. **Required:** Replace with declared measurement chain; propagate difference-of-reading and outflow uncertainty.

**Check:** Eight observation stress sequences show isolation lost under unmodelled drift.. Binding: `sensors.noise_fraction` = 0.02.

### A05 · Downstream outflow and other states are known exactly

**Priority 0 · Observability.** Current assumption: Exact H2 outflow, battery energy, CO2 and reactor temperature.

**Evidence or gap:** Ideal sensors; no independent errors or common cause. [Bronkhorst MV-191-H2 datasheet](https://products.bronkhorst.com/media/lbmdbkcf/3276-mv-191-h2-en-datasheet.pdf) [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf)

**Consequence:** Mass-balance fault localization receives unrealistic information. **Required:** Identify separate channels and errors; keep retrospective truth separate.

**Check:** Numerical checks do not establish empirical validity. Binding: `sensors.noise_fraction` = 0.02.

### A06 · Soil types are distinguishable without an inspection task

**Priority 0 · Observability.** Current assumption: Exact section loose/adhered/damaged fractions exposed.

**Evidence or gap:** No optical/soiling station inference model. [Soiling losses — impact on photovoltaic power plants](https://iea-pvps.org/wp-content/uploads/2023/01/IEA-PVPS-T13-21-2022-EXEC-SUMM-Soiling-Losses-PV-Plants.pdf)

**Consequence:** Condition cleaning has perfect information; treatment choice overstates autonomy. **Required:** Use irradiance/reference-cell or inspection evidence with ambiguity; ideal monitor remains teaching-only.

**Check:** Numerical checks do not establish empirical validity. Binding: `service_system.cleaning_model` = lumped-dc/1.

### A07 · Mobile and fixed readers provide independent fault evidence

**Priority 0 · Information independence.** Current assumption: Two readers can share one trip contact; zero/span references.

**Evidence or gap:** References check acquisition, not the physical contact or equipment. [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/)

**Consequence:** Agreeing readers cannot exclude a shared stuck contact. **Required:** Represent sensor-to-hypothesis graph and common causes; require independent process evidence.

**Check:** Shared-contact equivalence and seven voltage boundary cases checked.. Binding: `service_system.inspection_model` = bounded-contact/1; `faults.contact_stuck` = none; `service_system.inspection_zero_limit_v` = 2.0; `service_system.inspection_span_tolerance_fraction` = 0.1.

### A08 · The cleaner works on the chosen array layout

**Priority 0 · Feasibility/fleet size.** Current assumption: Generic row access; area 5 m²/kW; 1,000 m²/h.

**Evidence or gap:** No installed cleaner/array pairing. T4 up to 400 m²/night on near-flat trackers is not this fixture. [Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) [SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1)

**Consequence:** Single asset can become a distributed fleet with altered cost and downtime. **Required:** Bind task to geometry and measured cycle; separate dedicated-row and portable products.

**Check:** Numerical checks do not establish empirical validity. Binding: `service_system.cleaning_area_m2ph` = 1000; `service_system.area_m2_per_kw` = 5; `service_system.row_accessible` = True.

### A09 · Inspection robot may approach the hydrogen equipment

**Priority 0 · Access.** Current assumption: Accessible port; no gas-zone or payload certification model.

**Evidence or gap:** Advertised IIB does not establish IIC H2 eligibility. Site zone unspecified. [ANYmal X](https://www.anybotics.com/robotics/anymal-x/) [Ignition and flow stopping considerations for hydrogen networks](https://hysafe.info/uploads/papers/2023/114.pdf)

**Consequence:** An assumed inspection action can be unavailable. **Required:** Keep path outside restricted area or require matching certificate/site classification; do not infer approval.

**Check:** Numerical checks do not establish empirical validity. Binding: `service_system.inspection_interface` = legacy-prepared.

### A10 · Human replacement reliably clears all capacity-loss causes

**Priority 0 · Fallback capability.** Current assumption: Human fallback; 2 h work; success 0.95.

**Evidence or gap:** No cause-specific parts, isolation, test and expert qualification. [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/)

**Consequence:** Human baseline is also optimistic, affecting relative and absolute rankings. **Required:** Specify complete procedure, unreachable/irreparable cases and escalation; do not use a generic repair probability.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.human_work_hours` = 2; `field_operations.repair_success_probability` = 0.95.

### A11 · Field availability can be inferred from saved European weather

**Priority 1 · Joint exposure.** Current assumption: Default fixed 3 m/s and 0 mm/h; cached snapshots lack wind/rain.

**Evidence or gap:** No site service-window evidence or precipitation-driven soil removal. [Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) [DJI Dock 3 specifications](https://enterprise.dji.com/dock-3/specs) [Soiling losses — impact on photovoltaic power plants](https://iea-pvps.org/wp-content/uploads/2023/01/IEA-PVPS-T13-21-2022-EXEC-SUMM-Soiling-Losses-PV-Plants.pdf)

**Consequence:** Weather can simultaneously create need and prevent work. **Required:** Add provenance-preserving wind/precipitation data and joint access scenarios; missing data must remain unavailable.

**Check:** Numerical checks do not establish empirical validity. Binding: `service_system.environment_source` = assumed; `service_system.assumed_wind_mps` = 3; `service_system.assumed_rain_mmph` = 0.

### A12 · European soiling accumulates at the fixture rate

**Priority 1 · Service demand.** Current assumption: 0.005 fraction/day; no rain wash-off.

**Evidence or gap:** Explicit gap: 0.5 percentage point/day is not a site rate or confidence bound. [Soiling losses — impact on photovoltaic power plants](https://iea-pvps.org/wp-content/uploads/2023/01/IEA-PVPS-T13-21-2022-EXEC-SUMM-Soiling-Losses-PV-Plants.pdf)

**Consequence:** Cleaning benefit can be manufactured by unsupported deposition. **Required:** Site/season monitoring; rain/dew/adhered effects; threshold studies until then.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.soiling_per_day` = 0.005.

### A13 · Treatments remove a fixed fraction and wear predictably

**Priority 1 · Restoration/wear.** Current assumption: Loose removal .9; brush life 50,000 m²; wet adhered .7.

**Evidence or gap:** No module/deposit/brush field calibration; permanent damage is separately retained. [Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) [SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1) [Soiling losses — impact on photovoltaic power plants](https://iea-pvps.org/wp-content/uploads/2023/01/IEA-PVPS-T13-21-2022-EXEC-SUMM-Soiling-Losses-PV-Plants.pdf)

**Consequence:** Repeated work may be ineffective or damage coatings. **Required:** Pair-specific efficacy/wear evidence; never use dust-removal claim for bonded deposits.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.cleaning_removal_fraction` = 0.9; `service_system.brush_life_m2` = 50000; `service_system.portable_adhered_removal` = 0.7.

### A14 · Robot mission failure is an independent fixed probability

**Priority 1 · Reliability.** Current assumption: 0.05 per mission; matched target/action stream option.

**Evidence or gap:** No duration/exposure/cause-specific hazard fit or denominator. [AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2) [ExRobotics products and services](https://www.exrobotics.com/our-products)

**Consequence:** Longer or repeated missions change failure exposure artificially. **Required:** Log distance/time/weather/interventions; separate repeatable failure causes and common support outages.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.mission_failure_probability` = 0.05; `service_system.outcome_randomness` = legacy-reason/1.

### A15 · Robot/dock energy resembles the installed product

**Priority 1 · Energy/support.** Current assumption: 2 kWh packs; .2 kW mission; 1 kW dock; default zero standby, review .05 kW.

**Evidence or gap:** No measured duty/load curve. T4 own PV, drone dock max 800 W are different boundaries. [Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) [ExRobotics products and services](https://www.exrobotics.com/our-products) [DJI Dock 3 specifications](https://enterprise.dji.com/dock-3/specs)

**Consequence:** Shared plant energy and autonomy margins change. **Required:** Separate traction/payload/standby/thermal/dock loads and independent supply; no max-to-average transfer.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.mission_power_kw` = 0.2; `field_operations.dock_kw` = 1; `service_system.dock_standby_kw` = 0.0.

### A16 · Mission durations cover the whole service cycle

**Priority 1 · Timing.** Current assumption: 2 h clean, 1 h inspect; .5 h travel, .25 h verification.

**Evidence or gap:** No route length, commissioning, view quality, setup or test procedure calibration. [Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) [SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1) [AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2)

**Consequence:** Apparent intervention-free performance omits human work. **Required:** Measured full-cycle durations with remote and site effort separated.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.cleaning_hours` = 2; `field_operations.inspection_hours` = 1; `service_system.travel_hours` = 0.5; `service_system.verification_hours` = 0.25.

### A17 · Human/remote support will be available on request

**Priority 1 · Support.** Current assumption: Optional logistics/1; example 2 h response, 1 h travel; finite shifts/stocks.

**Evidence or gap:** No European supplier SLA, shared fleet contention or adverse-weather response data. [ExRobotics products and services](https://www.exrobotics.com/our-products) [AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2)

**Consequence:** Robot failures can create prolonged stranded assets. **Required:** Contract/crew scope and distributions; count return journeys, retrieval, maintenance and unserved work.

**Check:** Numerical checks do not establish empirical validity. Binding: `service_system.support_model` = none; `service_system.crew_response_lead_hours` = 2; `service_system.crew_travel_hours` = 1.

### A18 · Spares, brushes and water are compatible and replenishable

**Priority 1 · Support/consumables.** Current assumption: 12 cleaning kits, 2 service kits; default 1,000 L portable tank; review 4,000 L.

**Evidence or gap:** Generic kits; no exact part/reference shelf life or supplier stock evidence. [SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1) [A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf) [DNV hydrogen and renewable flow calibration](https://www.dnv.com/energy/services/laboratories-test-facilities/technology-centre-groningen-the-netherlands/hydrogen-and-renewable-flow-calibration/)

**Consequence:** Tasks become impossible when compatibility or water fails. **Required:** Part IDs, storage conditions, supply delay, water quality/waste and replenishment limits.

**Check:** Numerical checks do not establish empirical validity. Binding: `field_operations.cleaning_kits` = 12; `field_operations.service_kits` = 2; `service_system.portable_water_capacity_l` = 1000.

### A19 · Injected fault timing represents maintenance demand

**Priority 1 · Exposure.** Current assumption: One scheduled fault, persistent unless repaired or explicitly transient.

**Evidence or gap:** No event frequency, competing failure modes, degradation or environmental hazard fit. [Hydrogen Shot Water Electrolysis Technology Assessment](https://www.energy.gov/sites/default/files/2024-12/hydrogen-shot-water-electrolysis-technology-assessment.pdf) [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf)

**Consequence:** A 48 h injected event cannot justify annual robot savings. **Required:** Treat as challenge; obtain service logs or present break-even incidents/year without claiming incidence.

**Check:** Numerical checks do not establish empirical validity. Binding: `scenario.fault_start_hour` = 34; `faults.lifecycle` = persistent.

### A20 · Capacity loss reduces all electrolysis capability proportionally

**Priority 1 · Fault consequence.** Current assumption: Scalar available kW; unchanged conversion efficiency.

**Evidence or gap:** Pump fault, stack ageing, contamination and sensor fault have different effects. [DOE technical targets for PEM electrolysis](https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis) [Hydrogen Shot Water Electrolysis Technology Assessment](https://www.energy.gov/sites/default/files/2024-12/hydrogen-shot-water-electrolysis-technology-assessment.pdf) [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/)

**Consequence:** Same derating can understate complete shutdown or efficiency loss. **Required:** Create cause→physics→observations→allowed remedies contract.

**Check:** Numerical checks do not establish empirical validity. Binding: `scenario.capacity_fraction` = 1.

### A21 · Electrolysis has constant efficiency and simple starts

**Priority 1 · Production/start value.** Current assumption: 55 kWh/kg; 30% minimum; 40 kWh/start.

**Evidence or gap:** 55 is a PEM status guidepost; load, temperature, cold/standby/purge curves uncalibrated. [DOE technical targets for PEM electrolysis](https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis) [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf)

**Consequence:** Recovered electricity may yield a different amount or incur downtime. **Required:** Use system-level measured load/start maps; distinguish stack vs balance-of-plant.

**Check:** Numerical checks do not establish empirical validity. Binding: `plant.specific_energy_kwh_per_kg` = 55; `plant.min_load_fraction` = 0.3; `plant.start_energy_kwh` = 40.

### A22 · Missing auxiliaries cannot change service value

**Priority 1 · Plant boundary.** Current assumption: No pressure dynamics, purge/vent losses, compression, water treatment or detailed cooling circuit.

**Evidence or gap:** Utilities unspecified. An hourly balanced sandbox is not a complete process energy audit. [Hydrogen Shot Water Electrolysis Technology Assessment](https://www.energy.gov/sites/default/files/2024-12/hydrogen-shot-water-electrolysis-technology-assessment.pdf) [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/)

**Consequence:** Important failures or start costs may be absent entirely. **Required:** Declare pressure/purity/utility interfaces; add only consequential auxiliary loads and failure modes.

**Check:** Numerical checks do not establish empirical validity. Binding: `plant.auxiliary_kw` = 2; `plant.cooling_electric_fraction` = 0.1.

### A23 · The reactor thermal response is representative

**Priority 1 · Delayed response.** Current assumption: 0.3 kWh/K; .08 kW/K; 60/40 kW; 250–400°C; 4 h run.

**Evidence or gap:** Reaction exotherm supported; C, UA, band and commitments are illustrative. [Determination of reaction kinetics in three phase CO₂ methanation](https://publikationen.bibliothek.kit.edu/1000188810/171087110)

**Consequence:** Warm-up, heat retention and capacity-repair value can change direction. **Required:** Obtain design/step-response envelope; continue analytic sensitivity as conditional evidence.

**Check:** 864 Decimal exponential cases reconcile within 1e-9°C; no empirical validation.. Binding: `plant.thermal_capacity_kwh_per_k` = 0.3; `plant.heat_loss_kw_per_k` = 0.08; `plant.heater_max_kw` = 60; `plant.cooling_max_kw` = 40; `plant.minimum_run_hours` = 4.

### A24 · CO2 supply and initial stocks permit useful extra production

**Priority 1 · Bottleneck/terminal effect.** Current assumption: 300 kg/day; 500 kg initial CO2; H2 empty.

**Evidence or gap:** Supply contract and delivered gas condition unspecified. 

**Consequence:** Repairs/cleaning may restore capacity with no methane gain because feedstock binds. **Required:** Publish cumulative inputs/ending inventories and constrained shadow value.

**Check:** Independent supply bound 109.09 kg CH4/day; initial stock supports 181.82 kg.. Binding: `plant.co2_delivery_kg` = 300; `plant.co2_delivery_every_hours` = 24; `plant.initial_co2_kg` = 500; `plant.initial_h2_kg` = 0.

### A25 · Sabatier mass and heat arithmetic are appropriate

**Priority 1 · Numerical mechanism.** Current assumption: MW H2/CO2/CH4/H2O=2/44/16/18; 165 MJ/kmol.

**Evidence or gap:** Ideal conversion; no kinetic/selectivity/gas-quality certification. [Determination of reaction kinetics in three phase CO₂ methanation](https://publikationen.bibliothek.kit.edu/1000188810/171087110)

**Consequence:** Exact arithmetic cannot validate full reactor design. **Required:** Retain ideal chemistry label; separate produced methane from accepted product.

**Check:** Independent mass equality and 2.864583 kWh/kg checked.. Binding: methane/physics.py ratios; reactor.py REACTION_KWH_PER_KG.

### A26 · Short matched windows identify economic service value

**Priority 1 · Interpretation.** Current assumption: 48 h core, 240 h extension; no terminal sales.

**Evidence or gap:** No annual site utilization/fault process. 

**Consequence:** Postponed work or consumed initial stock can manufacture apparent savings. **Required:** Retain all terminal states/unresolved obligations and extend every matched arm; no annualization.

**Check:** Numerical checks do not establish empirical validity. Binding: `scenario.hours` = 72; `plant.initial_soc` = 0.0.

### A27 · Service prices are representative European costs

**Priority 1 · Economics.** Current assumption: Cleaner €15k, rover €80k, dock €5k; 8-year life; human €80/h; other activity assumptions.

**Evidence or gap:** No supplier quote or local labor/insurance/transport contract. [ExRobotics products and services](https://www.exrobotics.com/our-products)

**Consequence:** Ownership/contract preference can reverse. **Required:** Use fixed-trace break-even thresholds; report cash expenditure, allocation and decision cost separately.

**Check:** Numerical checks do not establish empirical validity. Binding: `costs.cleaner_eur` = 15000; `costs.rover_eur` = 80000; `costs.dock_eur` = 5000; `costs.field_asset_years` = 8; `costs.human_service_eur_per_hour` = 80.

### A28 · Costs account for wear without duplicate ownership charges

**Priority 1 · Accounting.** Current assumption: Replaceable capital separated; max(calendar,usage,parts) allocation; expenditure separate.

**Evidence or gap:** Arithmetic convention, not actual invoices; contract inclusions need review. 

**Consequence:** Double counting or omitted inclusions biases ranking. **Required:** Preserve accounting reconciliation and explicit price/version boundaries.

**Check:** Independent per-run audit and targeted economic tests.. Binding: `costs.field_replaceable_share` = 0.2.

### A29 · Robotic actuator completion proves restored operation

**Priority 2 · Recovery acceptance.** Current assumption: Versioned contact/process evidence and optional scheduled tests.

**Evidence or gap:** Actual test load/duration/acceptance depend on cause and instrumentation. [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/) [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf)

**Consequence:** False restoration or insufficient power delays confirmation. **Required:** Keep physical restoration, service receipt and observation confirmation timestamps distinct.

**Check:** Numerical checks do not establish empirical validity. Binding: `service_system.verification_hours` = 0.25.

### A30 · Schematic routes and hourly dispatch establish field response

**Priority 2 · Resolution.** Current assumption: Hourly plant plus fractional service events; illustrated paths.

**Evidence or gap:** No geometric navigation, emergency controls or pressure-system dynamics. 

**Consequence:** Animation can imply capabilities beyond the calculation. **Required:** Keep illustrations as task explanation; emergency/safety and navigation behavior outside validated scope.

**Check:** Numerical checks do not establish empirical validity. Binding: `plant.dt_hours` = 1.0.

### A31 · Other hardware families are ready to add as interchangeable robots

**Priority 2 · Architecture.** Current assumption: Uneven commercial maturity; most absent as full mechanisms.

**Evidence or gap:** Each needs its own task/effect/sensor/support contract. [Taurob Operator](https://www.taurob.com/operator/) [A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf) [Swagelok calibration and switching modules](https://products.swagelok.com/en/all-products/analytical-instrumentation/analytical-subsystems-press/calibrating-switching-modules/c/502?clp=true) [Maximo completes 100 MW of robotic solar installation](https://www.nasdaq.com/press-release/maximo-completes-100-mw-robotic-solar-installation-2026-03-25) [5B Maverick](https://5b.co/en/5b-maverick)

**Consequence:** A common class label can conceal unavailable mechanics. **Required:** Expand only after family-specific feasibility gate, not generic success rate.

**Check:** Numerical checks do not establish empirical validity. Binding: F04–F14 capability entries.


## 9. Evidence, reproduction and limits

The independent checker reconstructs balances, service-resource accounting, timing/compatibility and cost arithmetic under declared inputs. It does not independently validate every observer decision or calibrate mission success. Targeted tests cover surface treatment and clipping, unavailable access/weather, measurement references and timing, support and hardware failures, economic accounting and deliberate audit mutations.

The new observation challenges invoke diagnosis only with declared observations; they do not pass an injected fault type to it. The thermal reference calculation uses high-precision Decimal exponentials independently of the production helper. Passing both calculations supports the equation, not the chosen thermal constants. No new empirical plant trial was conducted.

The report is self-contained for offline reading. Sources remain external links; the numerical evidence is local. [Reproduction instructions](README.md) explain the frozen inputs, amendments, scripts and archive hashes. Reruns should create new output directories and preserve the original source identity; a changed implementation is a new experiment edition, not an overwrite.

Access limits were recorded rather than concealed: the NREL 2009 wind-to-hydrogen PDF could not be retrieved from the attempted endpoint, and an initially attempted RSC publisher route was unavailable. The methanation paper was subsequently read through the author’s KIT repository. No inaccessible source was used to invent a numerical parameter.

This is a source/code/numerical review, not an independent equipment qualification or an empirical reliability study. The evidence is enough to identify the changes that matter before further investment. It does not establish a calibrated envelope for all 31 assumptions.

## 10. Sources

<a id="source-s01"></a>

**S01 · [Ecoppia T4 datasheet](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf)** — Manufacturer specification; Undated; file label 020321. Accessed 2026-09-12. PDF pp. 2–4 inspected. Single-axis tracker geometry; up to 400 m² nightly, 3 m²/min; own PV dock; vendor maintenance. Product claims, not an independent reliability or cost estimate.

<a id="source-s02"></a>

**S02 · [SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1)** — Manufacturer specification; Undated current page. Accessed 2026-09-12. Primary page inspected. Portable remote-controlled wet/dry cleaning with one operator, setup and access limitations. Its stated daily MW coverage is not an autonomous service rate.

<a id="source-s03"></a>

**S03 · [ExRobotics products and services](https://www.exrobotics.com/our-products)** — Manufacturer/service description; Undated current page. Accessed 2026-09-12. Primary page inspected. Inspection payloads, commissioned routes, charging, connectivity and service provision. Endurance and unattended-period claims lack an exposed fleet denominator.

<a id="source-s04"></a>

**S04 · [AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2)** — Primary deployment research; 22 April 2024, v2. Accessed 2026-09-12. Full HTML, deployment tables inspected. Two deployments report mission success and minor/serious/fatal interventions. Calendar deployment time differs from active operation and intervention-free duration.

<a id="source-s05"></a>

**S05 · [ANYmal X](https://www.anybotics.com/robotics/anymal-x/)** — Manufacturer specification; Undated current page. Accessed 2026-09-12. Primary page inspected. Advertised Zone 1 IIB and inspection capabilities. This does not establish IIC hydrogen-area eligibility for the proposed payload and configuration.

<a id="source-s06"></a>

**S06 · [Taurob Operator](https://www.taurob.com/operator/)** — Manufacturer prototype; Undated current page. Accessed 2026-09-12. Primary page inspected. Explicitly a prototype. Constrained manipulation is a design prospect, not evidence of autonomous hydrogen-system replacement.

<a id="source-s07"></a>

**S07 · [A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf)** — Primary laboratory research; IROS 2022. Accessed 2026-09-12. Full author PDF inspected. Prepared mechanical/electrical and water-filter interfaces; redesign enables constrained manipulation. Laboratory tasks are not qualified hydrogen repairs.

<a id="source-s08"></a>

**S08 · [DJI Dock 3 specifications](https://enterprise.dji.com/dock-3/specs)** — Manufacturer specification; Undated current page. Accessed 2026-09-12. Primary page inspected. Dock max input 800 W and 12 m/s landing/operation wind specification. Backup power excludes aircraft charging and some thermal loads; maximum draw is not standby demand.

<a id="source-s09"></a>

**S09 · [EASA Specific Category — Civil Drones](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones)** — Regulator guidance; Current page accessed on review date. Accessed 2026-09-12. Primary page inspected. BVLOS operation is an example within the specific category; site and mission authorization remain separate from dock automation. EU scope.

<a id="source-s10"></a>

**S10 · [UK CAA categories of UAS operations](https://regulatorylibrary.caa.co.uk/2019-947/Content/AMC-GM/GM1%20Article%203%20Categories%20of.htm)** — Regulator guidance; Current page accessed on review date. Accessed 2026-09-12. Primary page inspected. UK operation has its own applicable authorization framework; European product availability is not permission for a London mission.

<a id="source-s11"></a>

**S11 · [Reinforcement Learning for RUG](https://www.geckorobotics.com/resources/blog/reinforcement-learning-for-rug)** — Manufacturer technical account; 2 June 2025. Accessed 2026-09-12. Primary page inspected. Specialist contact/ultrasonic inspection. Requires accessible material and a corresponding integrity model; no generic repair capability.

<a id="source-s12"></a>

**S12 · [Renu Robotics autonomous vegetation management](https://renurobotics.com/about-us/)** — Manufacturer/service account; Undated current page. Accessed 2026-09-12. Primary page inspected. Renubot, recharge infrastructure and Mission Control remote monitoring form a service system. Does not remove all human maintenance.

<a id="source-s13"></a>

**S13 · [Swagelok calibration and switching modules](https://products.swagelok.com/en/all-products/analytical-instrumentation/analytical-subsystems-press/calibrating-switching-modules/c/502?clp=true)** — Manufacturer subsystem specification; Undated current page. Accessed 2026-09-12. Primary page inspected. Conditioned sample/reference routing with pneumatic actuation. Not a complete analyzer or a hydrogen-flow calibration procedure.

<a id="source-s14"></a>

**S14 · [Endress+Hauser Liquiline Control CDC90](https://www.endress.com/en/field-instruments-overview/liquid-analysis-product-overview/pH-sensor-automatic-cleaning-calibration-cdc90)** — Manufacturer specification; Undated current page. Accessed 2026-09-12. Primary page inspected. Automatic pH/ORP cleaning/calibration with compatible assemblies and utilities, non-Ex applications. Not a hydrogen flow meter remedy.

<a id="source-s15"></a>

**S15 · [Emerson corrosion and erosion monitoring](https://www.emerson.com/en/measurement-instrumentation/catalog/corrosion-and-erosion-monitoring)** — Manufacturer technology catalogue; Undated current page. Accessed 2026-09-12. Primary page inspected. Technology-specific ultrasonic, acoustic and intrusive observations. A sensor family does not confer general fault observability or remaining-life truth.

<a id="source-s16"></a>

**S16 · [Rotork IQ3 Pro intelligent actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro)** — Manufacturer specification; Undated current page. Accessed 2026-09-12. Primary page inspected. Purpose-built actuation and feedback. Cause-specific reset/interlock semantics require an engineered equipment interface; this product is not evidence for the simulated electrolyser reset.

<a id="source-s17"></a>

**S17 · [Maximo completes 100 MW of robotic solar installation](https://www.nasdaq.com/press-release/maximo-completes-100-mw-robotic-solar-installation-2026-03-25)** — Company press release hosted by Nasdaq; 25 March 2026. Accessed 2026-09-12. Primary page inspected. Company-reported installation deployment. Construction task scope and site crews remain; not independent O&M autonomy evidence.

<a id="source-s18"></a>

**S18 · [Next-generation Terafab completes field testing](https://www.terabase.energy/resources/terabase-energys-next-generation-terafab-completes-field-testing-ready-for-deployment)** — Manufacturer announcement; 19 March 2026. Accessed 2026-09-12. Primary page inspected. Version-specific field-test/deployment announcement; planned availability is not a completed fleet deployment.

<a id="source-s19"></a>

**S19 · [5B Maverick](https://5b.co/en/5b-maverick)** — Manufacturer specification; Undated current page. Accessed 2026-09-12. Primary page inspected. Pre-wired deployable PV blocks use people and a telehandler. A site design alternative, not autonomous daily maintenance.

<a id="source-s20"></a>

**S20 · [DOE technical targets for PEM electrolysis](https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis)** — Government status/target table; 2022 status and 2026 targets displayed. Accessed 2026-09-12. Primary page inspected. System 55 kWh/kg is a status guidepost; target 51 kWh/kg is aspirational. Continuous-life values do not determine intermittent-duty fault rates.

<a id="source-s21"></a>

**S21 · [Hydrogen Shot Water Electrolysis Technology Assessment](https://www.energy.gov/sites/default/files/2024-12/hydrogen-shot-water-electrolysis-technology-assessment.pdf)** — Government technical assessment; December 2024. Accessed 2026-09-12. Relevant PDF sections inspected. Stack and balance-of-plant scope, dynamic durability and development needs. No equipment-specific repair hazard or duration for this fixture.

<a id="source-s22"></a>

**S22 · [Enapter EL 4.1 handbook](https://handbook.enapter.com/electrolyser/el41/)** — OEM operating documentation; Current online handbook. Accessed 2026-09-12. Primary page inspected. AEM equipment illustrates cause-specific faults, reset conditions, service escalation, utilities, telemetry and venting. Structural analogy only; do not transfer AEM numerical values to an unspecified 450 kW plant.

<a id="source-s23"></a>

**S23 · [Bronkhorst MV-191-H2 datasheet](https://products.bronkhorst.com/media/lbmdbkcf/3276-mv-191-h2-en-datasheet.pdf)** — Manufacturer metrology specification; Modification printed 01-12-2025. Accessed 2026-09-12. PDF specification inspected. Range-dependent reading/full-scale accuracy and temperature effects differ from 2% independent Gaussian noise. Flow/pressure scope is not a proposed plant meter selection.

<a id="source-s24"></a>

**S24 · [DNV hydrogen and renewable flow calibration](https://www.dnv.com/energy/services/laboratories-test-facilities/technology-centre-groningen-the-netherlands/hydrogen-and-renewable-flow-calibration/)** — Calibration facility description; Undated current page. Accessed 2026-09-12. Primary page inspected. Hydrogen-specific reference facilities and operating ranges. Blend calibration uncertainties cannot be transferred to pure-H2 or arbitrary on-site calibration.

<a id="source-s25"></a>

**S25 · [Ignition and flow stopping considerations for hydrogen networks](https://hysafe.info/uploads/papers/2023/114.pdf)** — Primary HSE-authored technical paper; 2023. Accessed 2026-09-12. Relevant PDF passage inspected. Hydrogen gas-group IIC distinction; paper network/pressure scope differs from this plant. Used only to flag equipment certification compatibility.

<a id="source-s26"></a>

**S26 · [Soiling losses — impact on photovoltaic power plants](https://iea-pvps.org/wp-content/uploads/2023/01/IEA-PVPS-T13-21-2022-EXEC-SUMM-Soiling-Losses-PV-Plants.pdf)** — IEA PVPS technical report executive summary; 2022 report; January 2023 file. Accessed 2026-09-12. Three-page executive summary inspected. Site-dependent soiling and measurement uncertainty. Global loss estimates are not London, Seville or Copenhagen daily deposition rates.

<a id="source-s27"></a>

**S27 · [EU harmonised protocols for testing low temperature water electrolysers](https://publications.jrc.ec.europa.eu/repository/bitstream/JRC122565/jrc122565_ltwe_harmonisation_online_identifier_4.pdf)** — JRC technical testing protocol; 2021. Accessed 2026-09-12. PDF contents and relevant testing sections inspected. Reference conditions and measurement requirements; dynamic loading, cold starts and standby transitions require specified tests. Not field failure-rate data.

<a id="source-s28"></a>

**S28 · [Determination of reaction kinetics in three phase CO₂ methanation](https://publikationen.bibliothek.kit.edu/1000188810/171087110)** — Peer-reviewed primary research, author repository; Online December 2025; journal issue March 2026. Accessed 2026-09-12. Author-hosted publisher PDF inspected; DOI 10.1039/D5RE00337G. Reaction enthalpy and heat-management rationale supported; the liquid/catalyst experiment does not calibrate the fixture thermal capacity, heat loss or operating band.
