# Field robotics and remote maintenance for Dispatch Lab

The next useful extension is a **field-operations layer**: equipment that gathers evidence, maintains the plant, restores particular capabilities and reduces the work requiring a person on site. Mobile robots are one member of this class. Fixed analyzers, self-cleaning instruments, remote actuators, charging docks, spare parts and human service crews belong in the same operational picture.

This changes the autonomy problem. The controller must decide when to produce, when to learn more about a suspected problem, when to intervene, and how to preserve the resources needed to do so. A maintenance action consumes time and resources, can fail, and needs evidence of success. A robot also becomes another asset that can require maintenance.

**Recommendation:** define this layer before the next expanded controller experiments. Implement a deliberately small first example around solar cleaning, an inspection rover and one engineered recovery action. Preserve the completed battery study as evidence about its original plant boundary. Continue solver checks on that frozen boundary; evaluate field operations through new, explicitly different study editions.

## 1. Current capability and emerging designs

Commercial capability is strongest in repeatable inspection, cleaning, sensing and purpose-built actuation. Capability falls off as tasks require irregular manipulation, unknown fault repair, new tools, or work in an unprepared environment. “Autonomous” needs to be resolved into the actual workflow: who commissions the route, starts the mission, supervises exceptions, replaces consumables and retrieves a failed robot?

The catalogue distinguishes commercial products and deployments from prototypes, research demonstrations and proposed simulation abstractions. Manufacturer availability and performance claims are identified as such. A product description is not an independent estimate of uptime, maintenance burden or lifecycle cost.

| Hardware class | Evidence and examples | Mechanics to represent | Limits and proposed scope |
|---|---|---|---|
| **Dedicated solar-row cleaner** | Commercial, geometry-specific. Ecoppia E4/H4/T4. [1: Robotic solar panel cleaning services](https://www.ecoppia.com/) [2: T4 autonomous robotic cleaning solution](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) | Dry brushing with docking; some systems use their own solar supply. Soiling removal per section, finite coverage, brush condition, docking and weather limits. | Track/bridge layout; no automatic cross-row compatibility; consumables and servicing remain. **Scope:** First implementation. |
| **Portable wet/dry cleaner** | Commercial, operator-assisted. SolarCleano F1. [3: SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1) | Battery-powered cleaner transported and operated by a person. Water, setup/movement labour, energy, coverage and cleaning effectiveness. | Remote control does not eliminate the operator or deployment visit. **Scope:** Comparison baseline. |
| **Mobile ground inspector** | Commercial, commissioned routes. ANYmal X; ExR-2.5; Spot. [4: ANYmal X — Ex-proof inspection robot](https://www.anybotics.com/robotics/anymal-x/) [5: ExR-2.5 products, software and services](https://www.exrobotics.com/our-products) [6: Automated inspections made simple](https://bostondynamics.com/blog/automated-inspections-made-simple/) | Visual, thermal, acoustic and optional gas sensing on taught inspection rounds. Travel graph, payload, observation quality, delay, charge, failed missions and assistance. | Mobility, gas-group rating and payload compatibility differ; a reading is not a repair. **Scope:** First implementation. |
| **Docked aerial inspector** | Commercial, operation-dependent. DJI Dock 3 / Matrice 4TD. [15: DJI Dock 3 specifications](https://enterprise.dji.com/dock-3/specs) [30: Specific Category — Civil Drones](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones) [31: GM1 Article 3: Categories of UAS Operations](https://regulatorylibrary.caa.co.uk/2019-947/Content/AMC-GM/GM1%20Article%203%20Categories%20of.htm) | Repeatable visual/thermal survey with automatic dock charging. Survey coverage, wind/rain restrictions, flight reserve, dock power and delayed observations. | Weather, airspace/authorization and dock dependence; no generic gas identification. **Scope:** Second implementation. |
| **Contact inspection crawler** | Commercial specialist inspection. Gecko Robotics RUG. [8: Reinforcement Learning for RUG](https://www.geckorobotics.com/resources/blog/reinforcement-learning-for-rug) | Ultrasonic measurement of surface/material thickness. Inspection method, reachable surfaces and measurement uncertainty. | Deployment and contact preparation may require people; requires a corresponding degradation model. **Scope:** Later, if integrity mechanics added. |
| **Vegetation-management robot** | Commercial deployments reported. Renu Robotics Renubot. [9: Renu Robotics: autonomous vegetation management](https://renurobotics.com/about-us/) | Mapped autonomous mowing with recharge pod and remote monitoring. Seasonal growth, access obstruction, service hours, energy and human support. | Terrain, obstacles and robot maintenance; economics differ with site and climate. **Scope:** Later site-operations example. |
| **Sampling and analyzer station** | Commercial engineered subsystem. Swagelok calibration/switching modules. [10: Calibration and switching modules](https://products.swagelok.com/en/all-products/analytical-instrumentation/analytical-subsystems-press/calibrating-switching-modules/c/502?clp=true) | Condition and route process or reference samples to an analyzer. Purge/transport delay, sample use, contamination, analyzer status and reference inventory. | Requires an analyzer, utilities and compatible process interfaces; not gas-quality certification. **Scope:** Initial architecture; later mechanism. |
| **Automatic sensor service station** | Commercial for specified sensors. Endress+Hauser CDC90. [11: Cleaning and calibration system Liquiline Control CDC90](https://www.endress.com/en/field-instruments-overview/liquid-analysis-product-overview/pH-sensor-automatic-cleaning-calibration-cdc90) | Retract, clean, validate and calibrate compatible pH/ORP sensors. Calibration age, reference/cleaner stocks, temporary unavailability and verified return. | Not a generic cure for a hydrogen flow meter; electrode and reagent replacement remain. **Scope:** First fixed-hardware comparison. |
| **Rugged fixed sensor package** | Commercial, technology-specific. Emerson corrosion/erosion sensing. [12: Corrosion and erosion monitoring](https://www.emerson.com/en/measurement-instrumentation/catalog/corrosion-and-erosion-monitoring) | Permanent ultrasonic, acoustic or intrusive measurements. Independent channels, battery life, drift, dropout and common-mode error. | Sensor coverage and calibration are bounded; no automatic remaining-life ground truth. **Scope:** First inspection baseline. |
| **Remote actuator / redundant service path** | Commercial with engineered integration. Rotork IQ3 Pro and shutdown options. [13: IQ3 Pro intelligent electric actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro) [14: Power generation: actuator solutions](https://www.rotork.com/uploads/news/2950/rotork-v3pdf.pdf) | Commanded actuation with position/torque feedback; optional stored-energy shutdown. Actuation power, stuck states, position uncertainty and service-path prerequisites. | Indication backup is not actuator motive power; valve action must have a modeled physical effect. **Scope:** First bounded-recovery example. |
| **Mobile maintenance manipulator** | Prototype / constrained demonstrations. Taurob Operator. [16: Taurob Operator](https://www.taurob.com/operator/) | Valve manipulation, tooling and material handling. Tool/reach/torque compatibility, multi-stage tasks, failure, verification and remote assistance. | Manufacturer page explicitly says prototype; no universal consumable-replacement capability. **Scope:** Explicit future-capability fixture. |
| **Robot-compatible replaceable module** | Research demonstration / design option. Melenbrink–Teeple–Werfel modular hardware. [17: A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf) | Single-axis guided insertion, combined latching and compliant mechanical interfaces. Service-port compatibility, spare stock, isolation, swap and post-service check. | Space-habitat lab hardware is evidence for a design principle, not pressure-system qualification. **Scope:** Explicit future-capability fixture. |
| **Solar construction robot** | Commercial deployments reported; evolving versions. AES/Maximo; Terabase Terafab. [18: Maximo Completes 100 MW of Robotic Solar Installation](https://www.nasdaq.com/press-release/maximo-completes-100-mw-robotic-solar-installation-2026-03-25) [19: Next-generation Terafab completes field testing, ready for deployment](https://www.terabase.energy/resources/terabase-energys-next-generation-terafab-completes-field-testing-ready-for-deployment) | Mechanized panel handling, assembly and installation alongside construction crews. Build-phase labour, rented equipment, mobilization, capacity commissioning and defects. | Not a daily O&M robot; module installation is only part of project completion. **Scope:** Separate commissioning scenario. |
| **Pre-integrated deployable solar array** | Commercial, crew-assisted. 5B Maverick. [20: 5B Maverick](https://5b.co/en/5b-maverick) | Transportable pre-wired solar blocks unfolded with a small crew and machinery. Transport, installation time/cost, footprint and compatible cleaning/access geometry. | A design alternative rather than an autonomous robot; crew and telehandler still required. **Scope:** Separate design comparison. |

### Inspection and cleaning that can be represented now

Ecoppia reports more than 5 GW of robotic cleaning deployments. Its designs demonstrate that a cleaner can be persistent site infrastructure. Geometry is consequential: the T4 datasheet describes tracker cleaning near horizontal stow, dedicated bridges and up to 400 m² daily coverage. That specification must not become a generic robot cleaning an arbitrary fixed-tilt array. SolarCleano's F1 provides a useful contrasting model: a portable wet/dry cleaner with an operator and transport/setup work. [1: Robotic solar panel cleaning services](https://www.ecoppia.com/) [2: T4 autonomous robotic cleaning solution](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf) [3: SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1)

ANYmal X, ExR-2.5 and Spot support inspection with different combinations of mobility and sensing. ExRobotics describes optional optical, thermal, acoustic and gas payloads, autonomous docking and missions lasting two to six hours depending on travel. Its advertised six months without physical human intervention is a design claim, not a published measured fleet mean. [4: ANYmal X — Ex-proof inspection robot](https://www.anybotics.com/robotics/anymal-x/) [5: ExR-2.5 products, software and services](https://www.exrobotics.com/our-products) [6: Automated inspections made simple](https://bostondynamics.com/blog/automated-inspections-made-simple/)

The AutoInspect research is especially useful because it records the assistance behind deployment duration. Its 35-day JET deployment included 81 missions and 16 interventions; the longest period without a serious or fatal intervention was 15 days. Its graph-based mission architecture also offers a practical abstraction for this simulator. These are results from that research system, not failure-rate defaults for commercial robots. [7: AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2)

A docked drone adds broad visual and thermal coverage. DJI's Dock 3 illustrates why the dock must be a separate asset: the published maximum input is 800 W, its backup battery does not support aircraft charging or air conditioning during an outage, and a 27-minute charge specification applies to 15–95% charge at 25°C. Neither maximum dock power nor ideal charge time is a measured average mission cost. [15: DJI Dock 3 specifications](https://enterprise.dji.com/dock-3/specs)

Contact inspection and grounds maintenance are additional concrete classes. Gecko describes robot-carried ultrasonic measurements for material-thickness inference. Renu reports deployed electric mowing robots with charging pods and remote Mission Control. These need distinct plant effects: measured wall condition and vegetation/access state, respectively. They should enter only when those mechanisms matter to an experiment. [8: Reinforcement Learning for RUG](https://www.geckorobotics.com/resources/blog/reinforcement-learning-for-rug) [9: Renu Robotics: autonomous vegetation management](https://renurobotics.com/about-us/)

### Fixed hardware can eliminate an entire task

Swagelok's sampling modules route and condition process or calibration streams for an analyzer. Endress+Hauser's CDC90 automates cleaning and calibration for compatible pH/ORP sensors. Emerson offers permanent corrosion/erosion monitoring. These are different answers to a site visit: bring the sample to an instrument, automate instrument servicing, or measure continuously. [10: Calibration and switching modules](https://products.swagelok.com/en/all-products/analytical-instrumentation/analytical-subsystems-press/calibrating-switching-modules/c/502?clp=true) [11: Cleaning and calibration system Liquiline Control CDC90](https://www.endress.com/en/field-instruments-overview/liquid-analysis-product-overview/pH-sensor-automatic-cleaning-calibration-cdc90) [12: Corrosion and erosion monitoring](https://www.emerson.com/en/measurement-instrumentation/catalog/corrosion-and-erosion-monitoring)

Remote actuation is similarly important. Rotork's IQ3 Pro reports torque, position and other diagnostic information. However, keeping position indication alive during power loss is different from having energy to move a valve. Dedicated shutdown-battery or spring-based products address that separate function. Our simulated equipment must distinguish those capabilities. [13: IQ3 Pro intelligent electric actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro) [14: Power generation: actuator solutions](https://www.rotork.com/uploads/news/2950/rotork-v3pdf.pdf)

These examples support **service capability** as the general abstraction. They do not imply that a pH calibration system can calibrate the existing hydrogen-flow sensor, or that a motorized valve can reverse irreversible electrolyser degradation.

### Manipulation and replacement: plausible, bounded, less mature

Taurob's Operator is a particularly relevant design, but its product page explicitly labels it a prototype. It describes valve manipulation, customized tools and substantial arm torque. This supports an exploratory fixture for specific tool-compatible tasks; it does not establish an off-the-shelf robot that changes arbitrary filters or repairs an entire methane skid unattended. [16: Taurob Operator](https://www.taurob.com/operator/)

The strongest design lesson comes from Melenbrink, Teeple and Werfel's “robot factors” work. They redesigned power and water-filter modules so one robot arm with a standard gripper could replace them. Combining actions, guiding insertion and adding compliance reduced manipulation demands. Those laboratory demonstrations suggest that **the plant's service interfaces are design variables alongside the robot**. They do not establish qualification for pressurized gas service. [17: A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf)

Learning could make these tasks more adaptable. The July 2026 Gemini Robotics On-Device 2 model card describes locally executed manipulation models, trusted-tester distribution and limitations on unfamiliar tasks; its safety discussion excludes mobile/whole-body risks from the scope of primarily standing bi-arm evaluations. That is evidence of an emerging enabling technology, not a basis for assuming reliable autonomous field repair. [27: Gemini Robotics On-Device 2 model card](https://deepmind.google/models/model-cards/gemini-robotics-on-device-2/)

For the next few years, the defensible scenario is broader libraries of constrained tasks on prepared equipment, with remote assistance for exceptions. Routine replacement of a standardized cartridge is a better hypothesis than universal mechanical dexterity. Dates and success rates for that transition remain uncertain. “Present hardware,” “prepared-site prototype” and “future capability assumption” should be separate selectable configurations.

### Deployment is a different part of the lifecycle

Maximo's March 2026 company release reports 100 MW installed at Bellefield and describes its role alongside skilled crews. Terabase's March 2026 announcement reports five first-generation project deployments and completed testing of its second-generation field-factory system. These are substantive construction capabilities; they do not mean an unattended plant can construct itself. [18: Maximo Completes 100 MW of Robotic Solar Installation](https://www.nasdaq.com/press-release/maximo-completes-100-mw-robotic-solar-installation-2026-03-25) [19: Next-generation Terafab completes field testing, ready for deployment](https://www.terabase.energy/resources/terabase-energys-next-generation-terafab-completes-field-testing-ready-for-deployment)

5B's pre-integrated Maverick blocks offer another approach: simplify the solar array's deployment and reduce tasks on site. The advertised workflow still includes a crew and telehandler. Represent that as an alternative plant design with transport, labour, footprint and commissioning consequences. Construction machinery can leave after commissioning rather than silently becoming a permanent O&M expense. [20: 5B Maverick](https://5b.co/en/5b-maverick)

## 2. The abstraction: assets, capabilities, work and evidence

A single new `Robot` class with energy and repair probability would miss most of the interesting decisions. Use composition through a small collection of explicit records. The following is a proposed contract, not an implemented interface.

| Record | Essential contents | Why it exists |
|---|---|---|
| **Field asset** | Stable asset ID; platform and model versions; mobility; location; modes; battery or utility connection; health; service requirements; ownership/service contract | Represents a rover, cleaner, fixed station or dock without forcing them into identical mechanics |
| **Capability** | Action and target-interface IDs; tool/payload; measurable quantities; reach/access limits; duration/energy model; weather and operating restrictions; autonomy/assistance mode | Describes exactly which work an asset can attempt |
| **Work order** | Target, reason, evidence available when requested, priority/deadline, prerequisites, reserved resources, task stages and acceptance test | Separates a desired outcome from the machine assigned to achieve it |
| **Service interface** | Compatible tools/connectors; reachable pose or named service point; required shutdown/isolation state; permitted actions and verification | Lets plant design make maintenance easier or impossible |
| **Mission record** | Requested and applied stages, timestamps, observations, resource use, interruptions, assistance and verified outcome | Makes every service claim and charge traceable |
| **Support resource** | Docks/charging slots, tools, spares, references, cleaning materials, communications and available crew hours | Makes autonomy depend on finite infrastructure |

A human service crew can execute a work order through the same task/result interface, with travel, labour and availability. A fixed actuator may perform an action immediately at its installed location. A rover may first need to travel and acquire a usable observation. This shared description permits meaningful comparison without pretending these executors are interchangeable.

Separate four types of effect: **inspection produces evidence; cleaning changes a physical loss; repair changes a specified failure mechanism; deployment changes commissioned capacity**. Each effect needs its own kernel, units, limits and evidence. Inspecting an asset never directly sets its true health to “healthy.”

```text
Current observations + eligible forecasts + mission requirements
                              ↓
             Plant and service-state estimates
                              ↓
   Service scheduler ↔ Plant dispatch planner
          ↓                 ↓
   Work orders        Electricity / operating commitments
          ↓                 ↓
   Task executive ← Prerequisites and resource checks
          ↓
   Robot / fixed station / human crew → Physical effects
          ↓                                  ↓
   Timestamped observations ← Acceptance test / plant

Docks, tools, spares, references and access constrain each task.
Every attempted task → Resource ledger + human work + evidence.
```

A mission might pass through `queued → preparing → travelling → performing → verifying → returning → complete`. It can also become `blocked`, `aborted`, `failed`, `awaiting remote help`, or `awaiting site visit`. Completion of motion is not proof that the plant is restored. An inconclusive check remains inconclusive.

## 3. Physical detail that changes decisions

### Solar cleaning

Introduce a section-level removable-soiling state, separately from fixed optical losses, permanent degradation, shading and electrical faults. A minimal declared model can accumulate soiling between rain/cleaning events, reduce it by an imperfect cleaning action and retain a persistent damage term. The present PV conversion can consume the resulting transmission factor before converter clipping. Avoid counting soiling again inside an existing aggregate loss allowance.

IEA PVPS explicitly notes that clipping and curtailment can conceal or reduce the value of recovered solar energy. Its global soiling statistics should not be used as a constant loss in London, Seville or Copenhagen. Local rainfall, dust, pollen, biological fouling and seasonal conditions need either sourced data or visible scenario assumptions. [21: Understanding, Measuring, and Mitigating Soiling Losses in PV Power Systems](https://iea-pvps.org/wp-content/uploads/2025/09/Fact-Sheet-Task-1316-Soiling.pdf)

Cleaning should use covered area and actual work duration, not give an entire array an instantaneous reset. Preserve residual dirt, missed rows, interrupted work, brush wear and any water consumption. Dry dust, adhered fouling and snow are distinct regimes; a dry brush should not be a universal remedy.

More frequent cleaning can also damage some surfaces. An 18-month Doha experiment found substantial differences between module types in abrasion associated with dry robotic brushing. This supports a sensitivity test with explicit module/cleaner pairing, not an assumed universal deterioration rate. [22: Abrasion of PV Antireflective Coatings by Robot Cleaning](https://doi.org/10.1109/JPHOTOV.2024.3414192)

The controller should value cleaning through the resulting plant trajectory. Additional available PV may become methane, charge storage, enable a restart, or be curtailed. The existing battery study's fixed CO₂ ceiling is a concrete example of why recovering kWh does not automatically recover saleable production.

### Inspection and sensor servicing

Every measurement needs a sensing method and observation model: what it measures, its error, conditions for a useful reading, and when the controller receives it. Poor light, reflections, an obscured target, sensor drift or an interrupted mission can make it unavailable or misleading. A new measurement can share errors with an existing instrument; independent packaging does not guarantee independent evidence.

A normal thermal camera should not reveal arbitrary internal component state. Conventional optical gas imaging is spectrally selective and does not directly image hydrogen. A methane-capable camera cannot be relabelled a hydrogen detector. Use a suitable gas-specific payload or another declared observation method, and keep its detection limits explicit. [28: Understanding Cooled vs Uncooled Optical Gas Imaging](https://www.flir.com/en-gb/discover/instruments/gas-detection/understanding-cooled-vs-uncooled-optical-gas-imaging/)

Calibration requires a compatible reference and an actual procedure. The reference can be depleted, expired or contaminated. During calibration the channel may be unavailable. Record as-found error and the post-service check. The existing flow-sensor-bias example would need a specified flow reference or independent measurement path; importing a pH calibration product would not provide that mechanism.

Sampling introduces transit, purging, analysis and communication delay. Record sampled material and its fate—returned, consumed, captured as waste or explicitly released. No sampling model should silently create or discard hydrogen or CO₂. An analyzer result is an observation; adding it does not confer product-quality certification.

### Recovery and degradation

For each fault, define which actions could affect its cause. A latched controller trip may permit a bounded reset. A fouled service element may permit a documented cleaning/replacement sequence. A failed power module might require a spare and a prepared interface. Irreversible stack damage cannot be repaired by a restart command.

Represent degradation as an explicit state with a declared evolution and effect on performance. Inspection estimates that state; it does not observe perfect remaining useful life. Until calibrated degradation data exists, predictive-maintenance results are sensitivity experiments under stated synthetic mechanisms.

The same discipline applies to the robots: battery ageing, brush/tool wear, failed docking, obstructed routes, localization loss, contaminated optics, actuator jams and communications loss can produce service work. A robot requiring physical retrieval counts as a site visit. Bounded retries prevent endless “recovery” loops.

## 4. Site geometry, weather and time

Use a lightweight **access graph** with named inspection points, work areas, docks and connecting paths. Each edge can have travel time, energy, surface/slope class, permitted platforms and current obstruction. Tool reach and service-port compatibility determine whether an intervention is possible. This supports meaningful differences between a flat-site wheeled rover, a stair-capable platform, a row cleaner and a drone without simulating locomotion dynamics.

Separate this graph from the existing process-flow diagram. A pipe connection is not necessarily a traversable route. Layout changes should affect access and maintenance, while the circuit illustration continues to explain material and electricity flows.

Hazard compatibility is a concrete attribute, not a generic “industrial robot” flag. ANYmal X currently advertises Zone 1 IIB; hydrogen is associated with gas group IIC. That label alone therefore cannot justify entry into a hydrogen-classified area. Store the exact platform/payload certificate scope, zone/group/temperature requirements and source version, or mark compatibility unverified. The simulator is not performing a real site-classification assessment. [4: ANYmal X — Ex-proof inspection robot](https://www.anybotics.com/robotics/anymal-x/) [29: Working Safely with Hydrogen](https://h2tools.org/sites/default/files/2025-03/0700-006-EU_MSA-White-Paper_Working-Safely-with%20Hydrogen_EN.pdf)

A drone mission also has an operation-specific permission envelope. EASA guidance places BVLOS outside the Open category, with authorization, applicable standard-scenario declaration or relevant LUC privileges determining the route. UK CAA requirements must be represented separately for UK locations. The simulation can use a declared mission-eligibility input rather than attempting an automated legal decision. [30: Specific Category — Civil Drones](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones) [31: GM1 Article 3: Categories of UAS Operations](https://regulatorylibrary.caa.co.uk/2019-947/Content/AMC-GM/GM1%20Article%203%20Categories%20of.htm)

Weather affects both plant need and the ability to intervene. Wind may stop a survey when storm damage makes it valuable; wet ground can block travel; cold can reduce battery availability; rain may make cleaning unnecessary. Preserve these correlations. Expand saved weather inputs to include relevant wind/gust and precipitation fields before using them. Existing archives lacking them must show incomplete applicability, or use an explicitly labelled synthetic scenario—not an inferred “real” weather history.

Keep hourly plant scheduling initially. Represent field tasks as timed events with fractional-hour durations and integrate their electrical/consumable demand over each hour. In the first implementation, task observations and restored plant capacity become eligible at the next hourly decision boundary after completion. This avoids future-information leakage and optimistic within-hour restoration. It also means the model cannot evaluate second-by-second emergency response; that requires a later, explicitly different execution resolution.

## 5. Running costs and economic attribution

The economic unit is a complete service system: robot, payload, docking infrastructure, site preparation, software, support, consumables and remaining human work. Public manufacturer pages reviewed here generally do not provide a complete, comparable installed price and annual service breakdown. Preserve quote-required fields and use visibly illustrative sensitivity inputs rather than invented market averages.

| Cost category | What the simulator should record | Accounting boundary |
|---|---|---|
| Ownership or subscription | Platform, payload, dock, charging converter, installation, access modifications, mapping/commissioning | Choose purchase allocation or the contracted service basis; do not charge both for the same equipment |
| Standing operation | Software, communications, monitoring retainers, scheduled inspection/calibration and dock standby/climate control | Fixed commitments remain outside marginal dispatch incentives |
| Mission resources | Charger input, utility demand, cleaning water, purge/reference gases, sample disposal and other consumables | Physical quantities follow the actual task and the supply boundary |
| Usage-related wear | Robot battery, brushes, tyres/tracks, tools and actuators | Use a consistent allowance or explicit replacement treatment; reconcile the two instead of adding duplicate charges |
| Human work | Remote setup/supervision, interventions, callouts, travel, on-site labour, training and robot retrieval | Report remote minutes and visits separately; telemetry review is not zero labour |
| Logistics and spares | Deliveries, stock replenishment, storage, lead time, tools and unavailable service slots | A robot cannot replace a part that is not present |
| Production consequences | Shutdown, derating, task-related unavailability and delayed restart | Already reflected in the production trace; avoid also subtracting the same lost output as a second cost |

Retain distinct economic views. **Allocated period cost** distributes ownership and applicable allowances. **Action-dependent economics** guides task selection using consumables, wear and other avoidable costs. A separate expenditure ledger can show actual purchases, subscriptions and service events. Repricing changes the report; new decision prices require a new run.

Robot charging belongs in the electrical balance, with losses. If a cleaner has its own solar panel, model that external generation and battery explicitly. It is not free electricity from outside the account. For site-supplied charging, the opportunity cost of using power can be computed by replanning; it should not be added on top of the same forgone methane in a comparison of total contribution.

Scale matters. One sub-kW dock load may have little dispatch impact beside this plant's 1,000 kW solar array. The economically decisive effects may instead be delayed evidence, technician travel, standby systems and avoided downtime. The simulation should be allowed to show that a resident robot is uneconomic for a small, accessible site.

For purchase decisions, compare lifecycle contribution and human-work burden over matched scenarios. For an installed robot, compare the value of a specific mission against its avoidable costs. A useful break-even expression is:

`required avoided visits = (incremental annual service-system cost − other net annual benefit) / cost per genuinely avoided visit`

This is a comparison aid with explicit user inputs, not a robot price estimate. Visits bundled with feedstock deliveries or another repair are not independently avoidable. A reduction in routine inspections does not eliminate CO₂ delivery, spare replenishment, periodic checks or emergency callouts.

## 6. What the controller should optimise

A field-operations planner adds two kinds of choice: **information acquisition** and **physical intervention**. Inspection can be valuable even when it changes no physical state, because the result changes the best subsequent action. Maintenance can be valuable even when it temporarily reduces output, because it preserves later capability.

POMDP and Bayesian inspection-planning literature explicitly treats uncertainty about deterioration and inspection outcomes. The Andriotis/Papakonstantinou work adds resource and risk constraints; Morato and colleagues connect Bayesian deterioration models to inspection and maintenance decisions. These provide relevant formulations, but their numerical results are not evidence that a particular algorithm will outperform our plant controller. [23: Deep reinforcement learning driven inspection and maintenance planning under incomplete information and constraints](https://arxiv.org/abs/2007.01380) [24: Optimal Inspection and Maintenance Planning for Deteriorating Structural Components through Dynamic Bayesian Networks and Markov Decision Processes](https://arxiv.org/abs/2009.04547)

Initially, use a small mission scheduler around the existing planner. It proposes tasks, reserves robot/dock/tool capacity and returns predicted electrical demand, observation arrival times and equipment unavailability. The dispatch planner tests the plant consequences. A task executive checks prerequisites and applies permitted stages. If these schedules cannot be reconciled, record a blocked task or a fallback; do not claim this decomposition is globally optimal.

Open-RMF provides an implementation precedent for fleet task allocation with integrated charging. We can borrow those interface ideas while retaining Python and the existing architecture. A ROS installation, photorealistic simulator or robot foundation model is not needed to investigate task-level plant management. [26: Open-RMF demonstrations: task dispatching](https://github.com/open-rmf/rmf_demos/blob/main/README.md)

The proposed objective remains sustained useful production or operating contribution, subject to physical limits and declared operational commitments. Add mission costs, intervention risk and continuation value for service capability. Keep site visits, remote human time, downtime and adverse outcomes visible as separate metrics. If independence from human visits is a mission requirement, make its target explicit and examine the trade-off; do not hide it inside an arbitrary “autonomy score.”

A practical initial inspection policy can ask whether plausible findings would change the chosen action. If all credible outcomes imply waiting safely for a technician, an immediate inspection may have limited operational value. If one result permits production and another requires isolation, the information could be valuable. The score must use the controller's current belief and predicted observations, not the hidden fault identity.

Learning can later improve soiling forecasts, task-duration estimates, diagnosis or continuation values. A published cleaning-scheduling study compares PPO and SAC in an Abu Dhabi simulation case, but its claimed savings should not be transferred to European weather or a feedstock-constrained methane plant. Use it as a candidate approach, with held-out tests. [25: Reinforcement learning-based dynamic cleaning scheduling framework for solar energy system](https://arxiv.org/abs/2603.07518)

Homeostatic ideas become more interesting in this extended system: keeping energy to inspect and recover, retaining usable calibration references, and avoiding simultaneous exhaustion of plant and robot reserves. These are joint, mode-dependent opportunities. Rewarding high robot battery charge or spare inventory by itself could produce inactivity and hoarding. Compare any learned reserve representation against MPC using the same information and service capabilities.

## 7. Changes required in the present model

The current code contains useful foundations—component contracts, separated observations, decision records, cost lineage and preserved Studies editions. It also has boundaries that matter directly to this proposal:

- `methane/simulation.py` constructs capacity loss and flow bias from a scheduled start and duration. At the end of that interval the injected condition disappears. That is useful for a transient-fault benchmark, but cannot serve as the recovery mechanism in a repair experiment.
- `methane/costing.py` allocates an assumed repair and visit charge for a confirmed incident. It does not yet represent a technician arriving, work being performed or the failure persisting when service is unavailable.
- `methane/config.py` has no field-asset, mission, access-graph or spare-stock contract. Its current scenario length is limited to 240 hours.
- The solar model exposes section-level conversion and losses, but does not provide a dynamic service-dependent soiling state. Existing weather archives are not automatically adequate for all mission weather restrictions.

Introduce a new versioned field-operations configuration with **disabled** as the compatibility default. For enabled runs, separate incident detection, service request, mobilization, work, verification and restored capability. Repairable faults persist until the declared causal transition occurs; naturally transient faults retain an explicit exogenous recovery model. Diagnosis-disabled runs still incur actual physical failures and service requirements.

Replace the incident-based cost shortcut only in the new accounting version. Preserve it in old archives and clearly identify its assumptions. Check the scope of standing O&M allowances before adding itemized service charges. Capture the service catalogue, capability assumptions, exact prices and model identities once per run alongside existing documentation snapshots.

Keep hidden fault causes in simulator truth. Controllers receive observations and beliefs; task eligibility can depend on measured/estimated conditions, while execution still enforces physical limits. A post-repair test may fail, requiring derating or escalation. A generic capacity-loss event without a cause must not acquire an invented thermal signature or a guaranteed robotic fix.

## 8. A first coherent demonstration

The first implementation should contain a small but complete chain, with all numeric parameters marked as assumptions until supported by hardware/site data:

**Solar cleaner:** a fixed-tilt-compatible archetype with a dock, per-section coverage, removable soiling, energy/brush consumption, weather restrictions and a blocked/failed mission case. Compare scheduled and condition-dependent cleaning with a human-operated baseline.

**Inspection rover:** one mapped route and a small set of declared observations. Start with a visible actuator-position indication or an additional independent instrument channel whose relation to a fault is explicitly modelled. Do not use an omniscient “inspect fault” action. Include an unreadable result, a route obstruction and a request for remote assistance.

**One prepared recovery interface:** a low-complexity service action such as switching to a pre-installed redundant auxiliary path, or a bounded reset of a specifically modelled latched trip. Give it prerequisite states, nonzero duration, possible failure and a post-action tracking test. Arbitrary pressure-system manipulation and catalyst/stack replacement remain outside this first example.

**Human service fallback:** a finite response time and resource cost, including cases in which neither the installed hardware nor the available spare can solve the issue. The robot may also need retrieval or servicing.

A guided sequence could begin with suspected solar underperformance ahead of a forecast shortfall. The controller decides whether to inspect, clean or wait for predicted rain. A separate equipment anomaly later presents competing hypotheses. The rover obtains partial evidence; the supervisor attempts the compatible recovery action, verifies its effect and either restores operation or calls for service. A second replay can make the inspection inconclusive or the recovery fail. These are proposed fixtures, not outcomes already demonstrated.

## 9. Experiments and evidence after the extension

Retain the solver and scoring-boundary studies, with field operations fixed or disabled, so we can still isolate numerical effects. Then introduce a separate series of studies whose questions explicitly include the service system.

| Question | Matched alternatives | Necessary outputs |
|---|---|---|
| When is cleaning worthwhile? | Human cleaning, fixed schedule, condition-dependent robot schedule, waiting for rain | Methane/contribution, usable recovered energy, curtailment, water, wear, labour and ending soiling |
| Is mobile inspection worth installing? | Existing sensing, added fixed sensors, rover, drone where eligible | Detection/isolation performance, decision changes, remote time, visits and complete system cost |
| Does intervention change recovery? | Diagnosis only, remote actuator, compatible robot action, human service | Verified restoration, unsuccessful attempts, downtime and resources consumed |
| How much does service-friendly design help? | Same task on a conventional interface and a prepared interface | Extra installation cost, task feasibility/duration, assistance and residual human work |
| What happens when support fails? | Power shortage, failed dock, exhausted reference/spare, blocked access, lost communications | Deferred work, uncertainty duration, stranded assets, retrieval and fallback outcomes |
| When do resident assets pay? | Purchased system, contracted/shared service and on-call human crew | Utilization, mobilization, response time, allocated cost and actual service expenditure |

Distinguish short injected-fault challenges from annual economics. A three-day stress case cannot establish annual maintenance savings. Longer seasonal simulations require extending the present ten-day limit and supplying validated weather/degradation or explicit scenario distributions. Construction studies need their own commissioning boundary, labour schedule and capacity-availability trace.

For matched policies, retain common weather, latent scenario draws and initial resources. Inspection timing and use-dependent degradation can legitimately change observations and failures. Use named random streams by asset/mechanism and a documented exposure-based hazard construction when wear drives failure; do not force identical failure times if actions alter physical exposure. Predeclare whether a study tests recovery from a fixed injected fault or changes to failure incidence.

Count human work consistently: initial commissioning, routine remote attention, remote corrective intervention, planned site visit, unplanned site visit and robot retrieval. Report unresolved service backlog at the end. A policy should not look independent simply because it defers every difficult task beyond the scoring window.

Evidence gates include electrical/material/resource conservation; no simultaneous incompatible tasks; no observation before it becomes available; no repair without a compatible effect; acceptance tests before restoration; no double-counted service cost; and no hidden truth in decisions. Keep uncertain, failed and incomplete outcomes. The service-layer-disabled configuration should retain the old physical trace for a matched numerical execution environment.

## 10. Presentation and implementation order

Preserve the main plant illustration and its labels. An optional **Site services** layer can reveal the dock, active worker and selected route. Equipment appears active because of a recorded mission; movement in the drawing is an interpolation of that record, not a hidden numerical model. Keep additional text inside inspectors.

Selecting the cleaner shows what it is treating, remaining work, energy, effectiveness and why the task was scheduled. Selecting the rover shows the question it is investigating, its payload and the evidence it has actually returned. Selecting a service point reveals compatible actions, prerequisites, missing resources and the test required for restoration. Costs remain toggleable and link to recorded task quantities.

Extend the Model workspace with living explanations of field assets, inspection uncertainty, service interfaces and robot economics. A learned or hypothetical capability should carry that label beside its parameters. Studies should link to the relevant mission and then to the calculation or assumption behind a result. A screenshot or simulated thermal overlay must not masquerade as real sensor evidence.

The recommended delivery sequence is:

1. **Service contracts and accounting:** define work orders, capabilities, fault/action compatibility, human work, resources, lifecycle boundaries and archive versions. Record explicit unknowns and the source-backed/assumed status of each parameter.
2. **Complete first operating example:** cleaner, rover, dock, human fallback and one prepared recovery action; introduce only the physical mechanisms needed for those tasks. Add explanations and reconcile costs and balances.
3. **Reproducible service studies:** cleaning value, information value, verified recovery and support-system failure, followed by longer-horizon economics once its data and time resolution are adequate.
4. **Optional hardware families:** docked drone, sampling station, vegetation maintenance and prepared consumable replacement. Add deployment machinery under a separate construction experiment.

This order establishes which maintenance actions actually exist before asking a more capable controller to choose between them. It also leaves room to test whether modest fixed automation, a different service interface or a human visit is the better design for a particular plant.

## 11. Source records and scope

Assessment current to 10 September 2026. Sources were selected for implemented mechanisms, current product descriptions, physical demonstrations and explicit operating constraints. Commercial savings, availability and deployment quantities remain attributed manufacturer claims. Research methods demonstrated in structural maintenance, laboratories or other climates are not empirical validation of this plant.

Complete installed prices, service contracts, platform-specific failure distributions, local soiling data and compatible plant-service procedures remain unresolved inputs. Current documentation takes precedence over older brochures where versions conflict. For example, Maximo's dated March 2026 milestone is used rather than smaller figures on older product pages. No robot capability, repair outcome or price has been added to the running simulator by this report.

<a id="source-ecoppia"></a>

**1. Ecoppia.** [Robotic solar panel cleaning services](https://www.ecoppia.com/). Undated; current page. **Evidence:** Manufacturer deployment claims. **Access:** Public product/company page. **Scope:** Reports more than 5 GW of deployments; no independent fleet availability or cost audit.

<a id="source-t4"></a>

**2. Ecoppia.** [T4 autonomous robotic cleaning solution](https://www.ecoppia.com/warehouse/temp/ecoppia/T4_Datasheet.pdf). Undated datasheet. **Evidence:** Manufacturer technical specification. **Access:** PDF text. **Scope:** Tracker-specific geometry, coverage and stow requirements; not transferable to fixed-tilt rows.

<a id="source-solarcleano"></a>

**3. SolarCleano.** [SolarCleano F1](https://www.solarcleano.com/products/remote-solarcleano-f1). Undated; current page. **Evidence:** Manufacturer technical specification. **Access:** Public product page. **Scope:** Portable wet/dry cleaner requiring an operator; distinguishes remote control from unattended operation.

<a id="source-anymal"></a>

**4. ANYbotics.** [ANYmal X — Ex-proof inspection robot](https://www.anybotics.com/robotics/anymal-x/). Undated; current page refers to 2026 specifications. **Evidence:** Manufacturer technical specification. **Access:** Public product page. **Scope:** Inspection payloads and advertised Zone 1 IIB rating; not evidence of hydrogen-area suitability for a particular configuration.

<a id="source-exr"></a>

**5. ExRobotics.** [ExR-2.5 products, software and services](https://www.exrobotics.com/our-products). Undated; current page. **Evidence:** Manufacturer technical and service claims. **Access:** Public product page. **Scope:** Modular inspection, autonomous charging, optional payloads, mission durations and service models; advertised unattended intervals are design claims.

<a id="source-spot"></a>

**6. Boston Dynamics.** [Automated inspections made simple](https://bostondynamics.com/blog/automated-inspections-made-simple/). Undated; current page. **Evidence:** Manufacturer workflow description. **Access:** Public article. **Scope:** Teach-in, repeatable missions, payloads and integration with maintenance systems.

<a id="source-autoinspect"></a>

**7. M. Staniaszek et al..** [AutoInspect: Towards Long-Term Autonomous Industrial Inspection](https://arxiv.org/html/2404.12785v2). 22 April 2024, arXiv v2. **Evidence:** Research deployment report. **Access:** Full author manuscript. **Scope:** 49-day and 35-day deployments; mission-level architecture and recorded interventions. Not zero-touch operation for those entire periods.

<a id="source-gecko"></a>

**8. L. Roberto / Gecko Robotics.** [Reinforcement Learning for RUG](https://www.geckorobotics.com/resources/blog/reinforcement-learning-for-rug). 2 June 2025. **Evidence:** Manufacturer technical article. **Access:** Public article. **Scope:** Contact ultrasonic inspection and thickness inference; does not establish unattended deployment or automatic repair.

<a id="source-renu"></a>

**9. Renu Robotics.** [Renu Robotics: autonomous vegetation management](https://renurobotics.com/about-us/). Undated; current page. **Evidence:** Manufacturer deployment and operating claims. **Access:** Public company page. **Scope:** Electric mower, recharge pod and remote Mission Control; not independent savings evidence.

<a id="source-sampling"></a>

**10. Swagelok.** [Calibration and switching modules](https://products.swagelok.com/en/all-products/analytical-instrumentation/analytical-subsystems-press/calibrating-switching-modules/c/502?clp=true). Undated; current page. **Evidence:** Manufacturer technical specification. **Access:** Public product page. **Scope:** Sample conditioning and selection of process/calibration streams; the module is not itself a complete analyzer.

<a id="source-cdc90"></a>

**11. Endress+Hauser.** [Cleaning and calibration system Liquiline Control CDC90](https://www.endress.com/en/field-instruments-overview/liquid-analysis-product-overview/pH-sensor-automatic-cleaning-calibration-cdc90). Undated; current product page. **Evidence:** Manufacturer technical specification. **Access:** Public product page. **Scope:** Automatic pH/ORP cleaning and calibration; not a hydrogen-flow-meter calibration method.

<a id="source-emerson"></a>

**12. Emerson.** [Corrosion and erosion monitoring](https://www.emerson.com/en/measurement-instrumentation/catalog/corrosion-and-erosion-monitoring). Undated; current page. **Evidence:** Manufacturer technical description. **Access:** Public product catalogue. **Scope:** Permanently installed ultrasonic, acoustic and intrusive monitoring options; no plant-specific calibration.

<a id="source-rotork"></a>

**13. Rotork.** [IQ3 Pro intelligent electric actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro). Undated; current page. **Evidence:** Manufacturer technical specification. **Access:** Public product page. **Scope:** Remote actuation and diagnostic torque/position data; retained indication on power loss is distinct from actuation power.

<a id="source-shutdown"></a>

**14. Rotork.** [Power generation: actuator solutions](https://www.rotork.com/uploads/news/2950/rotork-v3pdf.pdf). Undated application document. **Evidence:** Manufacturer application note. **Access:** PDF text. **Scope:** Dedicated shutdown battery or mechanical spring designs for specified failsafe applications.

<a id="source-dock"></a>

**15. DJI.** [DJI Dock 3 specifications](https://enterprise.dji.com/dock-3/specs). Undated; current product specification. **Evidence:** Manufacturer technical specification. **Access:** Public specification text. **Scope:** Dock power, aircraft battery, conditional charge time, landing wind and backup-power exclusions. Maximum ratings are not average consumption.

<a id="source-taurob"></a>

**16. Taurob.** [Taurob Operator](https://www.taurob.com/operator/). Undated; current page. **Evidence:** Manufacturer prototype description. **Access:** Public product page explicitly labelled PROTOTYPE. **Scope:** Valve manipulation and tool handling; broad capability language does not establish routine unattended maintenance availability.

<a id="source-robotfactors"></a>

**17. N. Melenbrink, C. Teeple and J. Werfel.** [A Robot Factors Approach to Designing Modular Hardware](https://www.eecs.harvard.edu/~jkwerfel/iros22melenbrink.pdf). 2022, IROS author manuscript. **Evidence:** Robotics research with physical demonstrations. **Access:** Full author PDF. **Scope:** Robot-friendly power and water-filter modules; laboratory space-habitat examples, not certified industrial gas service.

<a id="source-maximo"></a>

**18. Maximo / AES.** [Maximo Completes 100 MW of Robotic Solar Installation](https://www.nasdaq.com/press-release/maximo-completes-100-mw-robotic-solar-installation-2026-03-25). 25 March 2026. **Evidence:** Company press release distributed by PRNewswire, hosted by Nasdaq. **Access:** Full press release. **Scope:** Company-reported 100 MW installation at Bellefield; construction crews remain part of the system.

<a id="source-terabase"></a>

**19. Terabase Energy.** [Next-generation Terafab completes field testing, ready for deployment](https://www.terabase.energy/resources/terabase-energys-next-generation-terafab-completes-field-testing-ready-for-deployment). 19 March 2026. **Evidence:** Company announcement. **Access:** Public announcement. **Scope:** First generation on five projects; V2 field testing complete and ready for shipment as of announcement, not evidence of every planned deployment.

<a id="source-maverick"></a>

**20. 5B.** [5B Maverick](https://5b.co/en/5b-maverick). Undated; current product page. **Evidence:** Manufacturer design and deployment claims. **Access:** Public product page. **Scope:** Prefabricated, pre-wired folding PV blocks deployed with a crew and telehandler; not an autonomous robot.

<a id="source-pvps"></a>

**21. IEA PVPS Tasks 13 and 16.** [Understanding, Measuring, and Mitigating Soiling Losses in PV Power Systems](https://iea-pvps.org/wp-content/uploads/2025/09/Fact-Sheet-Task-1316-Soiling.pdf). September 2025. **Evidence:** Research-programme technical synthesis. **Access:** PDF text. **Scope:** Site-specific soiling, clipping, curtailment and storage interactions; global figures are not European-site defaults.

<a id="source-abrasion"></a>

**22. B. W. Figgis et al..** [Abrasion of PV Antireflective Coatings by Robot Cleaning](https://doi.org/10.1109/JPHOTOV.2024.3414192). 21 June 2024; IEEE Journal of Photovoltaics 14(5), 824–829. **Evidence:** Peer-reviewed physical field experiment. **Access:** Indexed publisher abstract and introduction; full paper not reviewed. **Scope:** 18-month Doha test shows module-dependent abrasion effects. No universal wear coefficient follows.

<a id="source-pomdp"></a>

**23. C. P. Andriotis and K. G. Papakonstantinou.** [Deep reinforcement learning driven inspection and maintenance planning under incomplete information and constraints](https://arxiv.org/abs/2007.01380). 2 July 2020, author preprint. **Evidence:** Research method. **Access:** Author abstract. **Scope:** Constrained POMDP and DRL formulation for inspection/maintenance; no validation for this plant.

<a id="source-dbn"></a>

**24. P. G. Morato et al..** [Optimal Inspection and Maintenance Planning for Deteriorating Structural Components through Dynamic Bayesian Networks and Markov Decision Processes](https://arxiv.org/abs/2009.04547). 28 November 2021, arXiv v2. **Evidence:** Research method and numerical experiments. **Access:** Author abstract. **Scope:** Belief-state inspection and maintenance for structural deterioration; transfer to plant scheduling is a proposal.

<a id="source-cleanrl"></a>

**25. H. An.** [Reinforcement learning-based dynamic cleaning scheduling framework for solar energy system](https://arxiv.org/abs/2603.07518). 2025 journal article; author manuscript posted 8 March 2026. **Evidence:** Published simulation study, according to author record. **Access:** Author abstract and publication metadata. **Scope:** PPO/SAC cleaning scheduling in an Abu Dhabi case; not European field validation or whole-plant optimization.

<a id="source-rmf"></a>

**26. Open-RMF contributors.** [Open-RMF demonstrations: task dispatching](https://github.com/open-rmf/rmf_demos/blob/main/README.md). Living repository; accessed 10 September 2026. **Evidence:** Official open-source implementation documentation. **Access:** Repository README. **Scope:** Fleet task allocation and integrated charging; an architectural reference, not a mandated dependency.

<a id="source-gemini"></a>

**27. Google DeepMind.** [Gemini Robotics On-Device 2 model card](https://deepmind.google/models/model-cards/gemini-robotics-on-device-2/). 30 July 2026. **Evidence:** Developer model card. **Access:** Public model card. **Scope:** Trusted-tester distribution, manipulation benchmarks and explicit generalization/mobile-platform limitations; not industrial field qualification.

<a id="source-flir"></a>

**28. FLIR.** [Understanding Cooled vs Uncooled Optical Gas Imaging](https://www.flir.com/en-gb/discover/instruments/gas-detection/understanding-cooled-vs-uncooled-optical-gas-imaging/). Undated; current article. **Evidence:** Instrument manufacturer technical explanation. **Access:** Public article. **Scope:** Spectrally selective OGI; hydrogen cannot be directly imaged by the described conventional OGI method. The article incorrectly groups these gases as noble; that wording is not adopted.

<a id="source-hydrogen"></a>

**29. MSA Safety, hosted by H2tools.** [Working Safely with Hydrogen](https://h2tools.org/sites/default/files/2025-03/0700-006-EU_MSA-White-Paper_Working-Safely-with%20Hydrogen_EN.pdf). Document available March 2025; publication date not independently established. **Evidence:** Manufacturer technical white paper. **Access:** Indexed PDF text. **Scope:** Hydrogen gas-group IIC distinction; not a site classification or certificate assessment.

<a id="source-easa"></a>

**30. European Union Aviation Safety Agency.** [Specific Category — Civil Drones](https://www.easa.europa.eu/en/domains/drones-air-mobility/operating-drone/specific-category-civil-drones). Living guidance; accessed 10 September 2026. **Evidence:** Aviation authority guidance. **Access:** Public guidance. **Scope:** BVLOS and applicable authorization/declaration routes in EASA states; not a permission for a particular mission.

<a id="source-caa"></a>

**31. UK Civil Aviation Authority.** [GM1 Article 3: Categories of UAS Operations](https://regulatorylibrary.caa.co.uk/2019-947/Content/AMC-GM/GM1%20Article%203%20Categories%20of.htm). Living regulatory library; accessed 10 September 2026. **Evidence:** Aviation authority guidance. **Access:** Public regulatory text. **Scope:** UK BVLOS lies outside Open category; separate UK scope from EASA rules.

## 12. Local platform material

The local assessment is based on [configuration](../../methane/config.py), [simulation execution](../../methane/simulation.py), [sensing](../../methane/sensing.py), [cost allocation](../../methane/costing.py), [solar conversion](../../methane/solar.py), [Studies documentation](../../docs/studies.md), and the [earlier autonomy research](../autonomous-management/report.html).

The [completed battery study](../../runs/studies/d3631a7f3a124e5a9526cd986ff5971f/reports/4c562340cdb0422eb970b45bf4f629bb.html) remains evidence for its original configuration. Local code links describe the inspected checkout; the accompanying verification record includes content hashes so later changes need not be mistaken for the code reviewed here.
