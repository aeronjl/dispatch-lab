# Autonomous management of renewable-powered methane plants

The strongest direction for Dispatch Lab is a **hierarchical controller that plans under uncertainty, maintains an estimate of plant health, and executes bounded recovery procedures**. A constrained economic planner should coordinate electricity, gas inventories and reactor heat. Learning should initially improve forecasts, health estimates and the value assigned to future operating opportunities. A separate supervisor should govern starts, stops, diagnostic probes, degraded modes and recovery. Homeostatic reinforcement learning deserves a focused experimental track within this architecture.

This recommendation is an engineering synthesis, not a claim that one published algorithm solves unattended methane production. The literature supports many of the constituent capabilities. Public industrial evidence is strongest for bounded process optimization and control, with local protection and fallback retained. Evidence for prolonged, whole-plant operation through unfamiliar mechanical faults is substantially thinner in the sources reviewed.

The assessment covers publications and official company material available through **10 September 2026**. It distinguishes mathematical results, simulations, equipment experiments, industrial case reports and vendor claims. The accompanying catalogue contains 16 approach families and 42 primary references. Where only an abstract or indexed publisher excerpt was accessible, that limitation is recorded in the bibliography. No new controller experiments were run for this assessment.

## 1. What autonomy should mean here

An autonomous methane plant must repeatedly answer four connected questions: what condition is the plant actually in; what can it safely do; which feasible action best serves its mission; and whether the result justifies continuing, investigating or recovering. Scheduling alone addresses only part of that loop.

For this platform, a useful mission statement is: **produce useful methane over sustained operation, economically and with bounded intervention, while retaining the ability to remain within operating limits and reach an appropriate shutdown or restart state**. Useful production will eventually include gas specification and delivery acceptance. Until those mechanisms exist in the model, the defensible output is simulated methane mass, not certified saleable product.

Autonomy should be specified as a coverage envelope: a set of operating conditions, disturbances, fault classes, available recovery actions and acceptable escalation outcomes. A controller that safely identifies an unrecoverable fault and arranges service can be more autonomous than one that repeatedly attempts an unsafe restart. “No human action under any circumstance” is an unsuitable target for equipment whose physical repair options are limited.

There is a substantial precedent outside process engineering. Model-based spacecraft autonomy combines reasoning about system modes with diagnosis and reconfiguration; NASA's Remote Agent announcement described a bounded Deep Space 1 command experiment in 1999. The transferable idea is an explicit relationship between plans, execution and equipment state. Neither source implies that software can repair arbitrary broken hardware. [24: A Model-Based Approach to Reactive Self-Configuring Systems](https://aaai.org/papers/144-aaai96-144-a-model-based-approach-to-reactive-self-configuring-systems/) [25: Computer Program Assumes Spacecraft Command](https://www.jpl.nasa.gov/news/computer-program-assumes-spacecraft-command/)

### The starting point in Dispatch Lab

The current source already has coupled electrical and material accounting; battery and gas buffers; a lumped thermal reactor; greedy, methane-MPC and economic-MPC policies; versioned execution and planning components; causal forecast selection; recorded decisions; bounded diagnosis; isolated jobs; and reproducible archives. These are useful foundations for comparing autonomous strategies under identical information.

Several simplifications now become research boundaries. The simulation is hourly. Battery energy, CO₂ inventory and reactor temperature are currently ideal observed state channels. Hydrogen-buffer metrology noise scales with interval throughput rather than tank capacity, making low-flow residuals easier to observe than some real installations would allow. There are two injected fault classes, and the simulator's scheduled capacity recovery is not a repair process. Pressure, product quality, local reactor hotspots, detailed actuator dynamics and essential protection loads are outside the current plant abstraction. These observations come from the local configuration, sensing and simulation source, not external literature.

The next step in realism should therefore be selected by the autonomy question. Studying sensor isolation requires independent measurement channels with plausible errors and delays. Studying unattended restart requires restart prerequisites and failure outcomes. Studying maintenance requires health evolution. Adding a highly detailed illustration or a neural policy cannot compensate for missing mechanisms. Dynamic methanation literature also considers spatial temperature profiles, conversion and product composition during changing hydrogen loads—behaviour that the current lumped thermal fixture does not represent. [23: Power-to-Gas: Process analysis and control strategies for dynamic catalytic methanation system](https://www.sciencedirect.com/science/article/pii/S0196890424001985)

## 2. Where the state of the art sits

Three strands are converging. Process control supplies constrained optimization, estimators and supervisory sequencing. Machine learning supplies adaptable models, policies and value estimates. Reliability engineering supplies diagnosis, inspection and maintenance decisions. A process-industry RL review spans control and related operational tasks, illustrating that the field is broader than one end-to-end policy. The learning-MPC literature distinguishes learning the prediction model, tuning the optimization formulation and using MPC to constrain a learned controller. [8: Reinforcement Learning in Process Industries: Review and Perspective](https://www.ieee-jas.net/en/article/doi/10.1109/JAS.2024.124227) [1: Learning-Based Model Predictive Control: Toward Safe Learning in Control](https://www.annualreviews.org/content/journals/10.1146/annurev-control-090419-075625)

**Industrial learning control is real, but its operating boundary matters.** Yokogawa and JSR reported 35 consecutive days of reinforcement-learning control in early 2022. The described equipment was a distillation column, with existing protection, monitoring and integration into a distributed control system. This is stronger evidence than simulation, but it does not establish unattended recovery of an entire chemical plant. [33: Yokogawa and JSR Use AI to Autonomously Control a Chemical Plant for 35 Consecutive Days](https://www.yokogawa.com/news/press-releases/2022/2022-03-22/)

**Hybrid planning and learning is especially relevant to renewable fuels.** A 2024 electrolyser study combines site-wide planning with real-time optimization. A 2026 green-ammonia paper uses a Q-function as the terminal cost of stochastic MPC, addressing consequences beyond its immediate horizon. The latter is a simulation study in an adjacent process, not a methane deployment. It is nevertheless a close match to the problem of valuing energy and feedstock left for tomorrow. [6: Combination of Site-Wide and Real-Time Optimization for the Control of Systems of Electrolyzers](https://arxiv.org/abs/2404.06748) [7: Q-learning-based stochastic model predictive control for green ammonia production](https://www.sciencedirect.com/science/article/pii/S0959152426000557)

**Safety results are conditional results.** A predictive safety filter can check a proposed action against a model and backup trajectory. Its guarantee depends on the stated uncertainty, feasibility and computation assumptions. It cannot protect an unmodelled pressure system merely because the battery and thermal equations are verified. Keeping those scopes visible is essential when incorporating such methods into the platform. [2: A predictive safety filter for learning-based control of constrained nonlinear dynamical systems](https://arxiv.org/abs/1812.05506)

### Company landscape: what the public evidence actually establishes

| Organization | Relevant public evidence | Implication and remaining boundary |
|---|---|---|
| Yokogawa / JSR | Joint March 2022 report of 35 days of RL control of a distillation column. | Bounded industrial deployment with protection retained; not whole-plant fault autonomy. [33: Yokogawa and JSR Use AI to Autonomously Control a Chemical Plant for 35 Consecutive Days](https://www.yokogawa.com/news/press-releases/2022/2022-03-22/) |
| Phaidra | June 2024 Merck case describes autonomous cooling setpoints and transfer back to local building-management control. | Useful pattern for learned supervision and fallback; a vendor case, not an independent comparison of general recovery methods. [34: Autonomous AI Control of Mission-Critical Cooling at Merck](https://www.phaidra.ai/blog/autonomous-ai-control-of-mission-critical-cooling-at-merck) |
| Imubit | Named refinery case material describes closed-loop optimization and retraining after feed changes. | Model updating is part of operations, rather than a one-off training event. Public material does not provide a common benchmark against alternatives. [35: 3 Reasons Your Refinery Needs Closed-Loop AI Optimization](https://imubit.com/blog/3-reasons-your-refinery-needs-closed-loop-ai-optimization) |
| Rivan | August 2026 announcement of a deployed 1 MW system entering commissioning. | Direct mission relevance. Commissioning and planned autonomous validation should not be presented as an established long-duration reliability record. [36: Rivan deploys full-scale 1MW system](https://rivan.com/news/rivan-deploys-full-scale-1mw-system/) |
| Terraform Industries | Company timeline reports a March 2024 end-to-end sunlight/air-to-gas demonstration. | Evidence of integrated process ambition; the cited page does not document comprehensive diagnosis or recovery performance. [37: Terraform Industries](https://www.terraformindustries.com/) |
| Siemens gPROMS | Process-modelling and digital-twin offerings include hydrogen applications. | A route to richer engineering models and model exchange; software availability is distinct from validated autonomous operation. [38: gPROMS for sustainability](https://www.siemens.com/en-us/products/gproms/sustainability/) |
| ANYbotics | June 2025 material describes mobile gas-leak inspection. | Physical inspection can become an action available to autonomy. Detection and localization remain separate from repair. [39: Robotic Gas Leak Detection with ANYmal](https://www.anybotics.com/news/robotic-gas-leak-detection-anymal/) |
| Augury | Machine Health offering combines condition monitoring and diagnostic support. | Relevant to pumps, compressors and other monitored machinery; it does not establish catalyst or electrolyser remaining life. [40: Machine Health](https://www.augury.com/machine-health/) |
| Raptor Maps | Remote solar inspection and drone operations. | A potential inspection layer for PV assets. Its thermography guidance makes clear that useful inspection depends on environmental conditions. [41: Raptor Maps](https://raptormaps.com/) [42: Solar PV Inspection Drone Flight Guidelines](https://pages.raptormaps.com/raptor-maps-knowledge-hub/solar-pv-inspection-drone-flight-guidelines) |

The commercial opportunity suggested by this evidence is integration: a plant that can connect an uncertain forecast, a health hypothesis, a changed schedule and a verified recovery action. This is an inference from the coverage of these examples, not proof that no company already offers overlapping capabilities.

## 3. Catalogue of approaches

The methods below solve different parts of the problem and can be composed. “Priority” expresses a recommendation for Dispatch Lab, not a ranking of scientific quality. Maturity in another domain does not validate transfer to methane equipment.

| Approach | Role and strength | Limitation | Evidence | Priority |
|---|---|---|---|---|
| **Rules, state machines and supervisory control** | Reference policy and explicit start, stop, hold, trip and restart sequences. Fast, legible and suitable for preconditioned recovery actions. | Rules proliferate as resources and fault combinations interact; local choices can consume tomorrow's reserves. | Established control architecture; plant-specific sequences still need engineering. [24](https://aaai.org/papers/144-aaai96-144-a-model-based-approach-to-reactive-self-configuring-systems/) [25](https://www.jpl.nasa.gov/news/computer-program-assumes-spacecraft-command/) | Foundation |
| **Mixed-integer economic MPC** | Schedule discrete modes, minimum runs, gas buffers, battery and reactor heat together. Makes resource trade-offs and forecast-dependent commitments explicit. | Model mismatch, finite-horizon effects and solver deadlines; an incumbent is not necessarily optimal. | Established research framework; specific implementations require validation. [3](https://flore.unifi.it/handle/2158/599111) [6](https://arxiv.org/abs/2404.06748) [1](https://www.annualreviews.org/content/journals/10.1146/annurev-control-090419-075625) | Primary planner |
| **Scenario and chance-constrained MPC** | Choose actions against several plausible weather and equipment trajectories. Represents recourse and asymmetric shortage costs. | Scenario quality, temporal correlation and nonanticipativity matter; nominal probability bounds are conditional on assumptions. | Substantial control literature; adjacent renewable-fuels simulation studies. [4](https://escholarship.org/uc/item/1wt3d4vr) [7](https://www.sciencedirect.com/science/article/pii/S0959152426000557) [26](https://www.ecmwf.int/en/research/modelling-and-prediction/quantifying-forecast-uncertainty) | Near term |
| **Robust MPC, viability and predictive safety filters** | Keep a feasible protective or shutdown trajectory available while accepting useful planner actions. Separates performance proposals from constraint enforcement. | A guarantee depends on valid uncertainty bounds, a suitable backup set and timely computation; excessive robustness sacrifices output. | Conditional mathematical results and benchmark demonstrations. [2](https://arxiv.org/abs/1812.05506) [1](https://www.annualreviews.org/content/journals/10.1146/annurev-control-090419-075625) | Foundation |
| **State and health estimation; Kalman filters and MHE** | Infer inventories, temperatures, biases and available capacity from noisy observations. Carries uncertainty and reconciles several measurements with conservation laws. | Unobservable faults cannot be recovered by choosing a more sophisticated estimator; model and sensor errors can be confounded. | Established estimation methods; MHE tooling available. [27](https://www.do-mpc.com/en/latest/) [18](https://www.vehicular.isy.liu.se/Edu/Courses/DocDiagnos/CourseMaterial/sensplace.pdf) | Near term |
| **Structural diagnosis and residual hypothesis banks** | Design independent residuals and determine which faults can be distinguished with available sensors. Connects an alarm to violated physical relationships and additional evidence needed. | Diagnosis is conditional on mode, excitation and the completeness of the fault hypotheses. | Mature model-based diagnosis literature and open tooling. [18](https://www.vehicular.isy.liu.se/Edu/Courses/DocDiagnos/CourseMaterial/sensplace.pdf) [19](https://faultdiagnosistoolbox.github.io/) | Near term |
| **Learned anomaly detection and soft sensors** | Detect unfamiliar patterns or estimate unavailable measurements from operating history. Can capture nonlinear signatures omitted by reduced physics. | Novel operating regimes can look faulty; anomaly scores do not identify causes or establish safe recovery. | Active process-industry research and commercial condition monitoring. [8](https://www.ieee-jas.net/en/article/doi/10.1109/JAS.2024.124227) [40](https://www.augury.com/machine-health/) | Complement to physics |
| **Dual control and active fault diagnosis** | Choose a small perturbation or inspection that improves decisions by revealing health or sensor reliability. Makes the cost of uncertainty and the benefit of information explicit. | Probes consume energy, time and equipment life and may be unsafe or uninformative in the current mode. | Research literature; bounded probes are a tractable implementation subset. [20](https://www.sciencedirect.com/science/article/pii/S2405896318324467) [21](https://pubsonline.informs.org/doi/10.1287/opre.2013.1171) | Near term, bounded |
| **Health-aware control and partially observed maintenance planning** | Jointly plan production, inspection, service and replacement using health uncertainty. Connects present stress with future availability and intervention costs. | Requires equipment-specific degradation and service data; an accounting wear charge is not a remaining-life model. | Operations-research theory, experimental degradation studies and commercial monitoring. [21](https://pubsonline.informs.org/doi/10.1287/opre.2013.1171) [22](https://research-hub.nlr.gov/en/publications/electrolyzer-durability-at-low-catalyst-loading-and-with-dynamic--2/) [40](https://www.augury.com/machine-health/) | After health data |
| **Learning-enhanced MPC** | Learn forecast corrections, residual dynamics or a terminal continuation value around a constrained planner. Improves a bounded part of the controller while retaining interpretable resource constraints. | Learned uncertainty and terminal values can be wrong out of distribution; revalidation remains necessary. | Broad learning-control literature; 2026 green-ammonia simulation example. [1](https://www.annualreviews.org/content/journals/10.1146/annurev-control-090419-075625) [7](https://www.sciencedirect.com/science/article/pii/S0959152426000557) | First learning experiment |
| **Offline and online reinforcement learning** | Learn a sequential policy or value function from simulated or logged transitions. Can represent complex long-term behaviour and make fast deployed decisions. | Exploration, reward errors, dataset coverage and simulator exploitation; offline conservatism is not physical safety. | Industrial deployments on bounded tasks; wider process research remains heterogeneous. [9](https://papers.nips.cc/paper_files/paper/2020/hash/0d2b2061826a5df3221116a5085a6052-Abstract.html) [8](https://www.ieee-jas.net/en/article/doi/10.1109/JAS.2024.124227) [33](https://www.yokogawa.com/news/press-releases/2022/2022-03-22/) [34](https://www.phaidra.ai/blog/autonomous-ai-control-of-mission-critical-cooling-at-merck) | Challenger policy |
| **Homeostatic and allostatic RL** | Represent internal resource needs and learn anticipatory regulation of reserves. A useful hypothesis for balancing coupled energy, feedstock, heat and health states over time. | Fixed setpoints can waste energy; drive reduction can crowd out production; industrial benefit is unestablished by the cited neuroscience studies. | Neuroscience theory and simulations, including 2024–2026 developments. [10](https://elifesciences.org/articles/04811) [11](https://academic.oup.com/pnasnexus/article/3/12/pgae540/7912045) [12](https://arxiv.org/abs/2507.04998) [13](https://pubmed.ncbi.nlm.nih.gov/41513000/) [15](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf) | Focused research track |
| **Active inference** | Jointly reason about preferred states and information-seeking actions using a generative model. Provides a unified language for belief, anticipation and investigation. | Preferences and model likelihoods are design choices; usefulness must be compared with explicit decision-theoretic baselines. | Computational neuroscience simulations; plant application here is a proposal. [14](https://pubmed.ncbi.nlm.nih.gov/35051559/) | Exploratory |
| **Hierarchical and distributed control** | Separate slow production scheduling, faster regulation and equipment protection; coordinate local controllers through shared constraints. Matches different physical time scales and modular component interfaces. | Independent agents can fight over the same bus or learn nonstationary environments unless coordination is explicit. | Electrolyser control research and commercial multi-plant cooling systems. [6](https://arxiv.org/abs/2404.06748) [34](https://www.phaidra.ai/blog/autonomous-ai-control-of-mission-critical-cooling-at-merck) [24](https://aaai.org/papers/144-aaai96-144-a-model-based-approach-to-reactive-self-configuring-systems/) | Architecture |
| **Calibrated ensemble and decision-focused forecasting** | Estimate distributions of available power and train forecasts against consequences of decision errors. Targets the shortages that matter operationally rather than only average forecast accuracy. | Coverage can fail by regime or lead time; marginal calibration does not establish joint trajectory safety. | Weather ensemble practice and statistical/optimization research. [26](https://www.ecmwf.int/en/research/modelling-and-prediction/quantifying-forecast-uncertainty) [17](https://arxiv.org/abs/2106.00170) [16](https://arxiv.org/abs/1710.08005) | Near term |
| **LLM-assisted engineering and operator support** | Retrieve grounded explanations, propose structured experiments and summarize recorded decisions. Makes complex evidence and controller reasoning accessible. | Free-form generation does not establish numerical correctness, diagnosis or actuator safety; use typed tools and independent checks. | Architectural proposal for this platform, not a claimed plant-control result.  | Interface support |

An architecture based on these methods should avoid creating independent equipment agents that all optimize their own utilization. The battery, electrolyser and heater share the same bus; their local requests require plant-wide coordination. Modularity is valuable at the interfaces, while resource feasibility remains a joint property.

## 4. What to optimize—and what must not be traded away

### A hierarchy of obligations

The proposed controller should separate three levels. First are non-negotiable physical and protective conditions. Second are mission commitments, such as an explicitly assumed production obligation or an allowed service interruption. Third is optimization among the remaining alternatives. A finite “safety penalty” in an otherwise economic reward permits a sufficiently large revenue to purchase a violation. That is the wrong semantics for a forbidden operating condition.

The protective envelope should include more than instantaneous limits. Given the current state estimate and specified disturbances, is there enough energy and working equipment to follow a controlled shutdown sequence? Can the system fulfil a minimum-run commitment, or must that commitment be interrupted to respect a more fundamental limit? Is a restart feasible after the action? Maintaining a set of states from which an acceptable future trajectory exists is a useful control concept; the appropriate set must be derived from this plant's model and uncertainty assumptions.

When no safe continuation is available inside the supervisory model, the outcome must be explicit: invoke the appropriate independently implemented protective action, record the loss of supervisory feasibility and escalate. A solver's “infeasible” status is not itself a physical shutdown procedure.

### Proposed decision objective

For economic experiments, maximize expected operating contribution plus the value of future operating opportunities, with an explicit downside-risk term:

```text
maximize  E[ Στ { vτ mτ − cinputs,τ − cwear,τ − cintervention,τ
                  − ccontract-shortfall,τ } + VH(bH, calendarH) ]
          − λ CVaRα(L)

subject to physical balances, admissible modes and actions,
           commitments, uncertainty treatment and recovery constraints.
```

Here, `m` is simulated methane output; `v` is an explicit assumed value per kg; every cost term is in the same monetary unit; `b` is the estimated state and its uncertainty; and `V` is a continuation value. `L` is a separately defined adverse operating loss over the horizon, such as unmet contracted production plus recovery expense. Its definition and any overlap with expected costs must be visible. `λ` is an intentional premium against bad outcomes, not a hidden duplication in the accounting report. CVaR provides a tractable way to price the adverse tail of a modeled distribution; it is not protection against every possible event. [5: Optimization of Conditional Value-at-Risk](https://sites.math.washington.edu/~rtr/papers/rtr179-CVaR1.pdf)

This is a proposed formulation. Economic MPC provides relevant theory, but its published stability conditions do not automatically apply to a nonstationary solar plant with binary modes and time-limited solves. [3: On Average Performance and Stability of Economic Model Predictive Control](https://flore.unifi.it/handle/2158/599111)

Several accounting choices have important behavioural consequences:

- **Fixed ownership allocation stays outside dispatch incentives.** It matters for comparing asset designs and reporting full period cost, but it is not avoided by switching an installed asset off for an hour.
- **Incremental wear appears once.** If a degradation model already prices start-induced damage, a second generic start penalty needs a distinct rationale. A small tie-break discouraging unnecessary switches should be labelled separately.
- **Ending inventory has operational value without assumed sale proceeds.** Hydrogen, CO₂, battery energy and reactor heat may enable later methane production. The continuation value belongs to planning; it must not be booked as inventory revenue in the period cost report.
- **Contract shortfall only exists if a contract is actually modeled.** An invented demand penalty can dominate all other choices and make a controller look impressive at solving an artificial problem.
- **Zero-output unit cost remains undefined.** Optimizing an hourly cost-per-kg ratio encourages unstable choices and confuses periods of preparation with failure. Report ratios over meaningful windows, alongside their numerator and denominator.

Keep a second, explicitly different objective for physical research: maximize methane over the chosen evaluation window, subject to the same operational constraints and an explicit treatment of terminal state. That allows the value of planning to be studied without confusing it with an illustrative methane price. Neither policy should be required to beat the other on its own objective.

### Preserve productive options, rather than maximize reserves

The relevant resource is often a *combination*. Hydrogen without CO₂ cannot make methane. Full gas buffers with a cold reactor and an empty battery may be less useful than smaller inventories with sufficient start-up energy. Keeping a reactor hot through a long outage may destroy more future production than allowing it to cool and restarting later.

The current fixture gives a concrete illustration. At the minimum 3 kg CH₄/h output for a four-hour run, ideal stoichiometry requires **6 kg H₂ and 33 kg CO₂** for the 12 kg methane total. Those are independently calculated material requirements, not a complete start permission: heat, auxiliary electricity, cooling capability and the timing of inflows must also be feasible. At 10 kg CH₄/h, hydrogen use is 5 kg/h, so a full 60 kg buffer supplies at most 12 hours at that rate before accounting for new hydrogen, other constraints or losses absent from the ideal model.

A reserve policy should therefore ask “which future actions remain available?” rather than “is SOC above 30%?” Useful derived quantities include energy needed for the current commitment, the lower-confidence inventory available before the next credible delivery, time until controlled shutdown becomes necessary, and the probability of a feasible restart under the forecast scenarios. These are proposed engineering quantities whose units and assumptions should be inspectable.

Terminal treatment deserves a dedicated experiment. Start with a longer look-ahead or a transparent continuation rollout using a conservative reference policy. Then test a learned terminal value against that reference. A finite-horizon policy that empties every store just before the experiment ends can win an output table while leaving the next shift unable to operate. Conversely, a controller can hoard inventory to inflate its terminal score and never produce. Compare both behaviours across extended windows and report every ending inventory.

Curtailment, equipment utilization and number of starts are diagnostic metrics, not universal primary objectives. Deliberately curtailing a brief solar peak can be sensible when starting consumes scarce energy or accelerates damage. If assumed revenue is below avoidable costs, idling can be the correct economic result; the response is to inspect the assumptions, not secretly reward production until the controller runs.

If decarbonization is part of the mission, add a separate, documented carbon accounting model and test carbon-intensity constraints or a multi-objective frontier. It would require explicit electricity provenance, CO₂ origin, process emissions, methane leakage and product fate. Do not substitute “renewable-powered” for a calculated lifecycle result. Similarly, water availability can become a physical operating constraint before its price becomes economically significant. These are proposed extensions, not quantities the present methane-mass model already verifies.

## 5. Homeostatic RL and related neuroscience ideas

Homeostatic RL links reward to changes in an internal drive function: an action is valuable when it reduces deviation from a physiologically preferred state. Keramati and Gutkin's 2014 formulation connects discounted drive-reduction reward to regulation and anticipatory behaviour. It also exposes why discounting and trajectory treatment matter: an undiscounted difference of consecutive drive values can telescope into an endpoint comparison. This is a computational account of regulation, not evidence of industrial control performance. [10: Homeostatic reinforcement learning for integrating reward collection and physiological stability](https://elifesciences.org/articles/04811)

The idea has continued to develop. A 2024 deep-HRL study models long-term nutritional behaviour. A 2025 perspective relates internal state to motivation and anticipation. A 2026 computational study investigates gradual proactive regulation and shows that coupling several internal variables through shared actions can create destabilizing interactions. Those are useful research signals for a plant in which heating uses the electricity needed to replenish hydrogen; they do not establish a ready-made plant controller. [11: Modeling long-term nutritional behaviors using deep homeostatic reinforcement learning](https://academic.oup.com/pnasnexus/article/3/12/pgae540/7912045) [12: Linking Homeostasis to Reinforcement Learning: Internal State Control of Motivated Behavior](https://arxiv.org/abs/2507.04998) [13: Gradual proactive regulation of body state by reinforcement learning of homeostasis](https://pubmed.ncbi.nlm.nih.gov/41513000/)

Active inference offers a related but different formulation: action and information seeking arise from a generative model and preferred outcomes. A 2022 study explicitly simulates homeostatic, allostatic and goal-directed regulation. Its “free energy” terminology is a statistical construct, not reactor heat or electrical energy. For this project, any claimed advantage should be translated into measurable decisions and compared with ordinary belief-state planning. [14: Simulating homeostatic, allostatic and goal-directed forms of interoceptive control using active inference](https://pubmed.ncbi.nlm.nih.gov/35051559/)

### A plant-specific hypothesis worth testing

The proposed analogue of internal state is the vector of energy, feedstock, thermal readiness, equipment health and uncertainty. **Homeostasis** would regulate these around fixed acceptable bands. **Allostasis**, as used in this engineering proposal, would shift the bands in anticipation of weather, delivery schedules, commitments and likely equipment availability.

For example, a long low-solar forecast could increase the energy reserved for essential services while reducing planned electrolysis. An imminent credible CO₂ delivery could justify filling the hydrogen buffer. A doubtful cooling subsystem could narrow admissible reactor operation even with abundant sunlight. A cold, intentionally stopped plant is a legitimate operating mode: a universal reward for approaching 300°C would be a serious design error.

An interpretable candidate drive function is:

```text
D(b,t) = Σi wi · deficit_i(b, viable_band_i(t))²
```

Each deficit should be dimensionless and uncertainty-aware. The bands depend on mode and forecast, and may overlap only where joint operation is feasible. This separable expression is a useful baseline, not a full measure of viability: it can miss complementarity between resources. A richer candidate could measure the margin to losing a feasible commitment or recovery trajectory. Such a margin must be computed and checked, rather than inferred from a visually appealing “plant health” score.

There are two different experiments to keep separate. One changes the mission objective by directly rewarding low drive. The other uses drive as a **potential-based shaping signal** while retaining the original production/economic objective:

```text
Φ(b,t) = −D(b,t)
rshaped = rmission + β [ γ Φ(bnext,t+1) − Φ(b,t) ]
```

Potential-based shaping has policy-invariance results under its stated MDP and discount assumptions. Applying it with changing targets requires representing the relevant context in the state; finite episodes also need consistent terminal handling. A belief approximation, a truncated simulation or an incorrectly reset potential can invalidate the intended interpretation. [15: Policy Invariance Under Reward Transformations: Theory and Application to Reward Shaping](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf)

The research question is not whether an internally motivated agent can keep a battery charged. It is whether this representation improves sustained production, sample efficiency, adaptation or interpretability compared with a planner or learned policy given exactly the same reserve information. Test fixed-band HRL, forecast-conditioned HRL, MPC with those same bands, and a baseline RL policy with the same observations and hard action constraints. Keep model-learning benefits separate from reward-design benefits.

Useful adversarial cases include a safe cold shutdown, a long night, scarce CO₂, repeated reset opportunities, cheap but damaging cycling, an uncertainty signal that can be manipulated by avoiding measurements, and a fault that makes all reserve targets jointly impossible. These distinguish useful anticipation from hoarding, reward loops and conflicting drives.

## 6. Scheduling intermittent power and adapting to wrong forecasts

### Plan jointly across resources and time scales

The recommended scheduler is initially mixed-integer economic MPC, retaining the existing HiGHS implementation and verified component ports. It should choose equipment modes, electrical allocations, gas use, heater power and cooling together. The first action is implemented; observations then update the next optimization. A faster regulation layer would eventually track its setpoints, while independent local protection handles faster failures.

There should be no universal allocation order such as “electrolysis first, battery second.” Near a constrained restart, another kWh in the battery may be more useful than hydrogen; with adequate thermal reserve and a hydrogen-limited run ahead, the opposite can hold. Explain such choices through matched counterfactual replans. Marginal values from a continuous relaxation may also help, but must be labelled as relaxation results: binary starts and minimum runs can make actual trade-offs discontinuous.

Time scales should be treated as design choices to validate. Hourly decisions suit the current sandbox. A later plant may require a supervisory update every few minutes, faster temperature/flow regulation and much faster electrical protection. An hourly balance cannot demonstrate correct behaviour during a subsecond DC-bus collapse or a local temperature excursion between recorded samples.

For uncertainty, begin with a small set of coherent forecast trajectories: central, overestimate, delayed-ramp and prolonged-shortage cases, then calibrated ensembles. ECMWF ensembles provide a source of meteorological uncertainty, but conversion to site PV and operationally meaningful shortage probabilities requires additional modelling and calibration. Preserve correlation across hours; independent hourly noise can create implausible alternating weather and underestimate sustained shortages. [26: Quantifying forecast uncertainty](https://www.ecmwf.int/en/research/modelling-and-prediction/quantifying-forecast-uncertainty)

In scenario MPC, alternative future plans may branch only after the relevant information would be observed. Their first action must be shared. Otherwise an apparently excellent controller has effectively selected a different present action for each future weather realization. Record scenario weights, branches, availability times and the uncertainty model version alongside the plan. Stochastic MPC supplies several formulations, each with its own assumptions and computational burden. [4: Stochastic Model Predictive Control: An Overview and Perspectives for Future Research](https://escholarship.org/uc/item/1wt3d4vr)

### Adapt the right model when conditions change

Forecast adaptation should separate at least four causes of error: weather forecast bias; local PV conversion error; sensor bias; and changed equipment capability. A solar shortfall should not automatically become an electrolyser capacity fault. A lower methane rate should not automatically trigger retraining of the weather model.

Use lead-time- and regime-dependent residuals, recent forecast calibration, and explicit missing-data states. A rolling bias correction is a useful baseline. More advanced predictors can be evaluated against the decision losses they cause, rather than just RMSE; “predict, then optimize” research formalizes that distinction. Adaptive conformal methods can help track uncertainty coverage under change, but long-run coverage does not guarantee adequate coverage for every night, fault condition or joint trajectory. [16: Smart ‘Predict, then Optimize’](https://arxiv.org/abs/1710.08005) [17: Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170)

A practical proposal is stochastic planning for normal economic choices, with a more conservative recovery envelope for essential loads and irreversible commitments. The uncertainty sets must be distinguishable: an expected-revenue scenario distribution and a protective disturbance bound serve different purposes. Neither should silently expand into a claim of safety under arbitrary weather or faults.

When forecast confidence falls, actions should change in proportion to their consequences. Shorten an unreliable commitment, leave more reserve, prefer a reversible action, or move to a known degraded policy. Record the triggering evidence and the cost of conservatism. The “healthy” planner should not remain nominal merely because its solver found a mathematically feasible trajectory under an outdated forecast.

## 7. Faults: detection, localization, maintenance and recovery

### Begin with distinguishability and measurements

Sensor-based diagnosis should start with a fault-to-measurement structure. Which independent relationship is violated by capacity loss, a biased flow meter, a leak, a stuck valve or a drifting temperature sensor? Which pairs produce the same observable signature? Structural sensor-placement literature and the Fault Diagnosis Toolbox provide concrete machinery for asking these questions before training an anomaly detector. [18: Sensor Placement for Fault Diagnosis](https://www.vehicular.isy.liu.se/Edu/Courses/DocDiagnos/CourseMaterial/sensplace.pdf) [19: Fault Diagnosis Toolbox for Python and Matlab](https://faultdiagnosistoolbox.github.io/)

For the current electrolyser example, compare electrical tracking with hydrogen mass balance. The power residual should use the command actually issued after resource allocation, with timing and mode semantics preserved. Comparing measured power to an infeasible pre-allocation request can classify a cloud-induced shortage as broken equipment. Compare flow-meter hydrogen with independently inferred inventory change plus known outflow, allowing for metrology uncertainty, startup behaviour and transport delay.

These are not automatically independent channels in real equipment. Tank mass inferred from pressure and temperature inherits both sensors' errors and a gas model. Several identical sensors can share calibration drift, power loss or a common communication fault. “Two sensors agree” does not prove that either is correct. The measurement model should express such dependencies and classify unresolved combinations as ambiguous.

An estimator—initially a modest Kalman-style or moving-horizon formulation, depending on the model—can maintain state, slow parameter changes and candidate sensor biases. Do-mpc supplies MHE tooling. Estimation complexity should follow demonstrated observability, not precede it. Learned soft sensors can supplement this evidence, but their training coverage and correlated inputs must remain visible. [27: do-mpc documentation](https://www.do-mpc.com/en/latest/)

### Proposed fault-handling map

| Condition | Evidence to seek | Autonomous response to model | Boundary or recovery test |
|---|---|---|---|
| Electrolyser capacity reduction | Sustained tracking deficit under a feasible command; consistent independent hydrogen production estimate. | Derate the estimated capacity, reschedule hydrogen production and downstream commitments. | A small permitted upward probe must track before capacity is restored. Equipment repair is a separate event/action. |
| Hydrogen-flow sensor bias | Flow channel disagrees with independently reconciled inventory and electrical evidence. | Isolate the channel; use a qualified alternative estimate with greater uncertainty. | Require calibrated agreement before reinstating it; tank and outflow errors can make localization ambiguous. |
| Slow sensor drift | Mode-conditioned residual changes over time, calibration checks, disagreement with a diverse reference. | Increase uncertainty, reject affected measurements or schedule inspection. | Do not adapt the physical model so aggressively that it absorbs the sensor bias. |
| Cooling capacity loss | Actuation feedback and heat-balance evidence; abnormal temperature response at comparable load. | Lower production/heat input or enter a specified cooling/shutdown sequence. | Reaction heat and local hotspots make this a higher-fidelity task than the present single-temperature model supports. |
| CO₂ delivery delay or valve failure | Delivery confirmation, inventory movement and valve/flow feedback. | Replan feedstock commitments; avoid creating unusable excess hydrogen. | Distinguish logistics delay from instrument error or blocked transfer. |
| PV string/converter underperformance | Measured irradiance and temperature, peer/string electrical signatures, inspection where informative. | Revise available generation; route inspection; preserve downstream reserves. | Cloud, shading, soiling and electrical faults require different evidence. |
| Communication or compute failure | Stale timestamps, missed deadlines, command/acknowledgement failure. | Retain bounded local control or execute a pre-agreed safe sequence. | Return only after state reconciliation; blindly replaying an old plan is inappropriate. |
| Leak, persistent failed restart or unisolated critical fault | Independent protective detection or repeated failed postconditions. | Enter the specified protective state and request intervention. | No automatic retry loop merely because the high-level objective rewards uptime. |

This table is a proposed simulation expansion, not equipment-specific operating instructions. Recovery sequences require manufacturer and plant engineering input before use beyond the sandbox.

### Diagnosis under uncertainty and low activity

Use mode-specific residual distributions and a sequential confirmation rule. CUSUM, generalized likelihood ratios, change-point models or a small explicit hypothesis bank are candidates to compare; there is no need to begin with all of them. Preserve “insufficient excitation,” “ambiguous,” and “unknown anomaly” as distinct outcomes. Idle equipment supplies little tracking evidence. Repeated measurements do not eliminate a systematic bias.

Tune detection with missed-fault consequences and false-intervention cost, not accuracy alone. False alarms per operating hour, detection delay after the first informative interval, and time spent uncertain are more interpretable than a single classifier score on an artificially balanced dataset. A threshold of three standard deviations is not by itself a validated false-alarm rate when residuals are serially correlated or non-Gaussian.

### Inspection and active diagnosis are control actions

A small load perturbation can discriminate a capacity limit from a flow-sensor fault. An inspection can resolve a hypothesis that ordinary operation cannot. Active fault diagnosis studies deliberate auxiliary inputs under uncertainty; partially observed maintenance research connects the timing of observations to subsequent decisions. [20: A Survey of Active Fault Diagnosis Methods](https://www.sciencedirect.com/science/article/pii/S2405896318324467) [21: Joint Optimization of Sampling and Control of Partially Observable Failing Systems](https://pubsonline.informs.org/doi/10.1287/opre.2013.1171)

For Dispatch Lab, start with a finite menu of probes. Each should specify its permissible modes, available power, storage headroom, thermal prerequisites, maximum duration, expected discriminating observations and abort conditions. Permit a probe only when its likely operational benefit exceeds its energy, delay and wear cost. Do not award an unlimited information bonus that makes the controller repeatedly interrogate already-understood equipment.

Physical inspection has its own constraints. A mobile robot may obtain an independent gas measurement; a drone may inspect PV thermally. Raptor Maps' particular thermography protocol calls for sufficient irradiance, including a 600 W/m² threshold. That is a provider-specific requirement, not a universal standard, but it illustrates a general planning issue: the moment an inspection is most needed may not be the moment it is informative or possible. [39: Robotic Gas Leak Detection with ANYmal](https://www.anybotics.com/news/robotic-gas-leak-detection-anymal/) [42: Solar PV Inspection Drone Flight Guidelines](https://pages.raptormaps.com/raptor-maps-knowledge-hub/solar-pv-inspection-drone-flight-guidelines)

### Predictive maintenance needs a health model

The current usage and start allowances price assumptions; they do not predict failure. A credible maintenance model needs equipment-specific measurements, loading history, maintenance events, censored lifetimes and uncertainty about failure mechanisms. Remaining useful life should be a conditional distribution or a bounded estimate, with clear dependence on the future operating policy—not a single countdown displayed as fact.

Electrolyser technology matters. Experimental work on PEM electrolyser durability found materially different degradation under different dynamic protocols; renewable-like profiles were less severe than some accelerated square/triangle cycling protocols. This is evidence against a universal “one start equals this much damage” rule, and it does not provide coefficients for alkaline or anion-exchange equipment. [22: Electrolyzer Durability at Low Catalyst Loading and with Dynamic Operation](https://research-hub.nlr.gov/en/publications/electrolyzer-durability-at-low-catalyst-loading-and-with-dynamic--2/)

The recommended progression is a documented synthetic health model for controlled experiments, then calibration against relevant equipment data. Add service actions with duration, cost, crew/spare requirements and uncertain efficacy. A repair can restore only some health variables; replacing a sensor should not rejuvenate the stack. Maintenance planning can then trade a visit during a low-solar interval against the probability and consequence of later failure. The POMDP maintenance literature supplies a framework, not ready-made parameters. [21: Joint Optimization of Sampling and Control of Partially Observable Failing Systems](https://pubsonline.informs.org/doi/10.1287/opre.2013.1171)

### Recovery should be a verifiable sequence

Represent recovery as `suspect → isolate or derate → stabilize → investigate → attempt permitted restoration → verify → return or lock out`. The sequence is an engineering proposal. Every action needs preconditions, expected postconditions, a timeout and a bounded retry policy. A restored communication link, a reset drive and a repaired cooling loop require different evidence.

Report recovery by fault class and available hardware. Software can substitute a sensor, reroute through a modeled redundant component, reduce load, or verify that a repaired subsystem is usable. It cannot replace a failed pump unless the plant actually contains an autonomous replacement mechanism. This distinction makes the future case for modular hardware, redundancy and remote maintenance measurable.

## 8. Controller architecture and available machinery

The recommended architecture is shown below. The arrows represent information and authorized proposals; detailed equipment protection remains local. Each box should retain the versioned interfaces already established in the platform.

```text
Mission + risk limits + original forecasts
                    ↓
Observations → State / health belief → Joint planner
      ↑                ↓                    ↓
      │         Diagnosis / inspection  Action proposal
      │                ↓                    ↓
      │          Recovery executive ← Safety check
      │                ↓
      └── Plant ← Local regulation and protection

Offline models / values → Evaluated candidate registry → Planner / estimator
All decisions and transitions → Versioned evidence record
```

The central interface is a **control context** containing timestamped observations, a state/health belief with uncertainty, eligible forecasts, active commitments, available action capabilities, and versioned objectives. It must not contain injected fault labels, the scheduled time at which a simulator will repair a fault, or future realized weather. A planner returns a proposal with predicted trajectories, assumptions, solver termination and constraint evidence. The executive records what was requested, what was authorized, what was applied and what was observed.

A safety filter can reject or minimally modify a proposal only within its modeled scope. The rejected proposal and the replacement both remain in the record. When safety intervention becomes frequent, the planner is poorly matched to its environment; the filter's success should not conceal that failure. Independent local protection and a feasible fallback remain necessary design elements. [2: A predictive safety filter for learning-based control of constrained nonlinear dynamical systems](https://arxiv.org/abs/1812.05506)

### Tools the autonomous manager could call

| Capability | Input and output | Authority and resource boundary |
|---|---|---|
| Read observations and forecasts | Timestamped, provenance-bearing records and uncertainty. | Read-only; only information available at the decision time. |
| Evaluate a candidate plan | Predicted states, constraints, costs and uncertainty under a named model. | Simulation only; clearly separated from executed actions. |
| Diagnose and request inspection | Hypotheses, evidence gaps and a bounded probe/inspection proposal. | Executive checks prerequisites; no arbitrary actuator exploration. |
| Optimize operation | A typed scheduling problem and a validated incumbent or explicit fallback. | Deadline and compute budget; preserve solver limitations. |
| Fit a model or value function | Frozen dataset, training specification and candidate model artifact. | Isolated worker; cannot consume resources needed by active control. |
| Evaluate and register a candidate | Matched held-out experiments, regressions and source/data identities. | Training does not grant deployment authority; promotion follows a distinct reviewed release process. |
| Plan maintenance | Available service actions, health belief, logistics and expected downtime. | Scheduling capability only; physical work is a separate modeled event. |
| Explain a decision | Recorded operands, active limits, alternatives and uncertainty. | Grounded reporting; explanations must not invent causal importance scores. |

Learning can operate at several levels. **Supervised identification** learns conversion losses, thermal parameters and degradation residuals. **Forecast learning** estimates and calibrates available power distributions. **Value learning** approximates continuation beyond the planning horizon. **Policy learning** proposes actions directly. These should be separate experiments, so a gain from improved forecasts is not incorrectly credited to a new reward or policy architecture.

Begin with offline training in the simulator and shadow evaluation. Offline RL methods such as Conservative Q-Learning address one important problem—overoptimistic values outside logged action support—but do not create evidence for unobserved fault regimes or guarantee physical safety. Real exploration should eventually be restricted to engineered identification and probe actions, rather than unconstrained reinforcement learning on working equipment. [9: Conservative Q-Learning for Offline Reinforcement Learning](https://papers.nips.cc/paper_files/paper/2020/hash/0d2b2061826a5df3221116a5085a6052-Abstract.html)

### Software choices

Keep Python, SciPy/HiGHS and the existing component contracts for scheduling. Add a Gymnasium-compatible environment adapter when training is needed, with strict observation/truth separation and seeded resets. Use the Fault Diagnosis Toolbox for an initial isolability and sensor-placement study. For nonlinear estimation or faster lower-level control, evaluate CasADi with do-mpc or acados in a separate component; these tools do not directly replace mixed-integer scheduling. [30: Gymnasium documentation](https://gymnasium.farama.org/) [19: Fault Diagnosis Toolbox for Python and Matlab](https://faultdiagnosistoolbox.github.io/) [28: CasADi documentation](https://web.casadi.org/docs/) [27: do-mpc documentation](https://www.do-mpc.com/en/latest/) [29: acados documentation](https://docs.acados.org/)

The training environment should support batched rollouts, checkpoints, cancellation, scenario registries and held-out evaluation. Use an independently checked high-fidelity or alternative model for final challenges where possible. A fast simulator used for both training and evaluation can reward exploitation of its own approximations. BOPTEST and safe-control-gym offer useful examples of standardized control comparisons, while their underlying buildings and robotics systems should not be mistaken for methane validation. [31: Building Optimization Testing Framework (BOPTEST)](https://ibpsa.github.io/project1-boptest/index.html) [32: safe-control-gym: A Unified Benchmark Suite for Safe Learning-based Control and Reinforcement Learning in Robotics](https://arxiv.org/abs/2109.06325)

An LLM can be useful around this machinery: searching model documentation, producing structured experiment proposals and explaining recorded outcomes. The recommendation is to keep its outputs as typed requests to checked tools. It should not define a new safety limit, certify a diagnosis or send an unconstrained valve command through prose. This is an architectural choice for the project, not a claim that the cited industrial deployments use LLMs.

## 9. Experiments that would establish progress

The benchmark should measure **sustained mission performance under partial information**, with physical feasibility and reproducibility checked independently. No experiment should require MPC or RL to win. A simple policy may be best in a given weather or feedstock regime.

Existing local reports already show why comparison boundaries matter: some MPC traces preserve more terminal energy and heat, while some greedy traces produce more methane inside the displayed window. The solver comparison also records that mathematically equivalent formulations can produce different time-limited incumbents and diverging trajectories. These are findings from the saved local studies, not general statements about optimal control. Future comparisons need both equal wall-clock budgets and a higher-budget reference to distinguish control ideas from solver artifacts.

| Research question | Matched comparison | Evidence to retain |
|---|---|---|
| Does uncertainty modelling help? | Deterministic MPC versus scenario MPC with identical forecasts and feasible actions. | Shortage severity, missed commitments, conservatism cost, tail performance and calibration. |
| Does health estimation improve decisions? | Identical controllers with diagnosis on/off and with realistic versus ideal sensors. | Detection delay, false alarms, uncertainty, mistaken localization, production and intervention burden. |
| Are probes worth their cost? | Passive diagnosis versus a fixed safe probe policy versus information-aware probe selection. | Energy/wear spent, ambiguity resolved, prevented downtime and unsuccessful probes. |
| Does a terminal value help? | Short horizon, longer-horizon reference, reference-policy rollout, learned continuation value. | Extended-window output, ending states, feasibility and value prediction error. |
| Does homeostatic structure add value? | Fixed-band HRL, forecast-conditioned HRL, MPC with identical bands, and ordinary RL with matched information. | Sample efficiency, sustained output, reserve shortfalls, hoarding, sensitivity and distribution-shift behaviour. |
| Can recovery be autonomous? | Explicit recoverable faults, unavailable recovery hardware, failed resets and repaired components. | Successful verified restoration, lockouts, time to recovery and human actions actually needed. |

Use weather blocks held out by location and time, and equipment parameter families held out from training. Randomly splitting adjacent hours leaks correlated weather and operating history. Retain common random numbers across policies, but do not treat three fixed seeds as strong evidence of generalization. Include unseen combinations: forecast overestimate plus capacity loss; sensor drift plus CO₂ delay; a failed cooling actuator during a warm run; missing weather; stale telemetry; common-cause sensor errors; and prolonged power scarcity.

Metrics should preserve their meanings. Report methane and all ending inventories; allocated period costs separately from decision contribution; starts and forced downtime; health loss under the stated model; time spent in degraded modes; failed restarts; manual interventions; solver deadlines and fallback use. Diagnostic results should include delay after informative evidence, false alarms per operating time, missed faults, isolation accuracy, uncertainty duration and recovery-probe outcomes. Report both central and adverse-tail results rather than an overall “autonomy score.”

Use paired comparisons and uncertainty intervals that respect correlated weather blocks. Preserve incomplete runs, infeasible alternatives and failed training candidates. Zero observed violations in a finite suite are not a proof of zero risk. Formal checking can establish specific properties of a finite supervisor or bounded kernel, while empirical validation concerns agreement with physical equipment. Keep those evidence categories separate.

### Three proposed research increments

**First: uncertainty and operational viability.** Formalize essential loads, stop/restart semantics and terminal-state treatment; add a belief-bearing controller context and coherent forecast scenarios. Compare risk-aware MPC with current policies before introducing a learned policy. The gate is a reproducible case where a present reserve decision changes future recovery or productive capability, and the full balance reconciles.

**Second: diagnosis and recovery as decisions.** Expand sensor realism, enumerate distinguishable faults, and implement a small action library for probing, derating, isolation and verified restoration. The gate is correctly differentiated weather limitation, equipment derating and sensor inconsistency, plus an honest unresolved case and an unrecoverable case.

**Third: learning and homeostatic hypotheses.** Add the training adapter and candidate registry. Compare learned forecast/model corrections, continuation values and bounded policies separately. Test homeostatic and allostatic representations under matched information and constraints. The gate is a documented benefit or a well-supported negative result on held-out conditions, including computation and intervention costs.

## 10. Implications for the product and the physical plant

The simulation UI can make autonomy concrete through a repeated chain: **observed evidence → current belief → threatened commitment or opportunity → chosen action → expected test of success → observed outcome**. A battery inspector could explain the energy reserved for a restart; an electrolyser inspector could show that a channel is isolated and which evidence would restore it. The living Model workspace can expose the exact objective, reserve definition, sensor assumptions and claim boundaries without filling the main illustration with text.

A guided experiment should include both successful adaptation and deliberate refusal to continue. For example: a forecast overestimate threatens a minimum run; the planner changes electrical allocation; a discrepancy creates competing equipment and sensor hypotheses; a permitted probe resolves one case but leaves another uncertain; a derated plan preserves feasible operation; a restoration test either passes or produces a lockout. The score is the sustained physical and economic outcome, not the drama of the animation.

Before selecting physical implementation parameters, the most consequential missing inputs are the actual equipment technology and permissible operating envelope; essential loads and stop/restart sequences; available independent sensors and calibration histories; redundancy and remotely actuated recovery options; degradation and maintenance data; and the commercial definition of useful output and acceptable interruption. These are engineering design inputs. The platform can investigate sensitivity while they remain assumptions, but should not present illustrative values as calibrated requirements.

Future distributed ownership or DePIN machinery can use the same asset identities, evidence records and economic attribution. It should not sit in the fast control path. A signed record can authenticate who reported a reading; it does not establish that the sensor was calibrated or that the physical claim is true. The immediate research value lies in traceable decisions and explicitly bounded autonomy.

## References and evidence scope

Sources below support their associated factual descriptions. Plant-specific objective functions, architecture, fault expansion and research increments are recommendations derived from that evidence, not reproduced results. Company material is identified as such; inaccessible full papers are not treated as fully reviewed. External references require a connection; this report and its catalogue are otherwise self-contained.

<a id="source-hewing"></a>

**1. L. Hewing, K. P. Wabersich, M. Menner and M. N. Zeilinger.** [Learning-Based Model Predictive Control: Toward Safe Learning in Control](https://www.annualreviews.org/content/journals/10.1146/annurev-control-090419-075625). 2020. **Evidence:** Peer-reviewed review. **Access:** Publisher text. **Scope:** Taxonomy of learning within and around MPC; no universal safety guarantee.

<a id="source-safety"></a>

**2. K. P. Wabersich and M. N. Zeilinger.** [A predictive safety filter for learning-based control of constrained nonlinear dynamical systems](https://arxiv.org/abs/1812.05506). 2021; preprint first posted 2018. **Evidence:** Peer-reviewed method; author preprint. **Access:** Author abstract. **Scope:** Conditional predictive safety construction, not a safety certification for a methane plant.

<a id="source-empc"></a>

**3. D. Angeli, R. Amrit and J. B. Rawlings.** [On Average Performance and Stability of Economic Model Predictive Control](https://flore.unifi.it/handle/2158/599111). 2012. **Evidence:** Peer-reviewed control theory. **Access:** Author institutional record and abstract. **Scope:** Economic MPC performance and stability under stated mathematical assumptions.

<a id="source-mesbah"></a>

**4. A. Mesbah.** [Stochastic Model Predictive Control: An Overview and Perspectives for Future Research](https://escholarship.org/uc/item/1wt3d4vr). 2016. **Evidence:** Peer-reviewed review. **Access:** Indexed author-repository abstract; direct page challenged. **Scope:** Uncertainty-aware MPC; different formulations have different guarantees and computational demands.

<a id="source-cvar"></a>

**5. R. T. Rockafellar and S. Uryasev.** [Optimization of Conditional Value-at-Risk](https://sites.math.washington.edu/~rtr/papers/rtr179-CVaR1.pdf). 2000 publication; linked manuscript dated 1999-09-05. **Evidence:** Peer-reviewed optimization method; author manuscript. **Access:** Author-hosted PDF text. **Scope:** Tail-risk optimization technique, originally illustrated in finance; plant objective is an application proposal.

<a id="source-hydrogen"></a>

**6. V. Henkel, L. P. Wagner, F. Gehlhoff and A. Fay.** [Combination of Site-Wide and Real-Time Optimization for the Control of Systems of Electrolyzers](https://arxiv.org/abs/2404.06748). 2024. **Evidence:** Peer-reviewed application; author preprint. **Access:** Author abstract. **Scope:** Hierarchical electrolyser scheduling and real-time control; not evidence of whole-plant unattended recovery.

<a id="source-qsmcp"></a>

**7. H. M. Park, T. H. Oh and J. M. Lee.** [Q-learning-based stochastic model predictive control for green ammonia production](https://www.sciencedirect.com/science/article/pii/S0959152426000557). 2026-04. **Evidence:** Peer-reviewed application study. **Access:** Indexed publisher abstract and highlights; direct full text unavailable. **Scope:** Simulation of ammonia production with a learned terminal Q-function; transfer to methane remains to be tested.

<a id="source-processrl"></a>

**8. O. Dogru et al..** [Reinforcement Learning in Process Industries: Review and Perspective](https://www.ieee-jas.net/en/article/doi/10.1109/JAS.2024.124227). 2024-02. **Evidence:** Peer-reviewed review. **Access:** Publisher abstract and article metadata. **Scope:** Process-industry RL landscape across control and related tasks; individual deployment claims need their own evidence.

<a id="source-cql"></a>

**9. A. Kumar, A. Zhou, G. Tucker and S. Levine.** [Conservative Q-Learning for Offline Reinforcement Learning](https://papers.nips.cc/paper_files/paper/2020/hash/0d2b2061826a5df3221116a5085a6052-Abstract.html). 2020. **Evidence:** Peer-reviewed ML method. **Access:** Conference abstract. **Scope:** Addresses offline value overestimation; does not certify safety or fill missing operating-regime coverage.

<a id="source-homeo14"></a>

**10. M. Keramati and B. Gutkin.** [Homeostatic reinforcement learning for integrating reward collection and physiological stability](https://elifesciences.org/articles/04811). 2014-12-02. **Evidence:** Peer-reviewed computational neuroscience. **Access:** Full publisher text. **Scope:** Drive reduction, reward and physiological regulation; no industrial plant experiment.

<a id="source-homeo24"></a>

**11. N. Yoshida, E. Arikawa, H. Kanazawa and Y. Kuniyoshi.** [Modeling long-term nutritional behaviors using deep homeostatic reinforcement learning](https://academic.oup.com/pnasnexus/article/3/12/pgae540/7912045). 2024. **Evidence:** Peer-reviewed computational neuroscience. **Access:** Publisher text. **Scope:** Long-term nutritional behaviour in simulated agents; not plant control validation.

<a id="source-homeo25"></a>

**12. N. Yoshida, H. Sprekeler and B. Gutkin.** [Linking Homeostasis to Reinforcement Learning: Internal State Control of Motivated Behavior](https://arxiv.org/abs/2507.04998). 2025-07-07 preprint. **Evidence:** Research perspective; author preprint. **Access:** Author abstract. **Scope:** Conceptual synthesis of internal-state-dependent motivation, anticipation and hierarchical behaviour.

<a id="source-homeo26"></a>

**13. Mana Fujiwara and Honda Naoki (as indexed by PubMed).** [Gradual proactive regulation of body state by reinforcement learning of homeostasis](https://pubmed.ncbi.nlm.nih.gov/41513000/). 2026-02; online 2026-01-07. **Evidence:** Peer-reviewed computational neuroscience. **Access:** PubMed abstract. **Scope:** Proactive regulation and interacting internal variables in a computational model; industrial application is untested.

<a id="source-activeinference"></a>

**14. A. Tschantz, L. Barca, D. Maisto, C. L. Buckley, A. K. Seth and G. Pezzulo.** [Simulating homeostatic, allostatic and goal-directed forms of interoceptive control using active inference](https://pubmed.ncbi.nlm.nih.gov/35051559/). 2022. **Evidence:** Peer-reviewed computational neuroscience. **Access:** PubMed abstract. **Scope:** Generative-model simulations of three forms of regulation; not a plant recovery demonstration.

<a id="source-shaping"></a>

**15. A. Y. Ng, D. Harada and S. Russell.** [Policy Invariance Under Reward Transformations: Theory and Application to Reward Shaping](https://ai.stanford.edu/~ang/papers/shaping-icml99.pdf). 1999. **Evidence:** Peer-reviewed RL theory; author manuscript. **Access:** Author-hosted PDF text. **Scope:** Potential-based reward shaping under stated MDP and discount assumptions.

<a id="source-spo"></a>

**16. A. N. Elmachtoub and P. Grigas.** [Smart ‘Predict, then Optimize’](https://arxiv.org/abs/1710.08005). 2022 publication; preprint 2017. **Evidence:** Peer-reviewed optimization/learning method; author preprint. **Access:** Author abstract. **Scope:** Prediction trained around downstream decision loss; application to weather dispatch is a proposal.

<a id="source-aci"></a>

**17. I. Gibbs and E. Candès.** [Adaptive Conformal Inference Under Distribution Shift](https://arxiv.org/abs/2106.00170). 2021. **Evidence:** Peer-reviewed statistical method; author preprint. **Access:** Author abstract. **Scope:** Adaptive long-run coverage; not a conditional or joint physical-safety guarantee.

<a id="source-sensors"></a>

**18. M. Krysander and E. Frisk.** [Sensor Placement for Fault Diagnosis](https://www.vehicular.isy.liu.se/Edu/Courses/DocDiagnos/CourseMaterial/sensplace.pdf). 2008. **Evidence:** Peer-reviewed diagnosis method; author manuscript. **Access:** Indexed author-hosted PDF and author publication record; direct PDF retrieval failed. **Scope:** Structural detectability and isolability; actual signal quality and operating excitation remain relevant.

<a id="source-fdtool"></a>

**19. E. Frisk and contributors.** [Fault Diagnosis Toolbox for Python and Matlab](https://faultdiagnosistoolbox.github.io/). Undated documentation; accessed 2026-09-10. **Evidence:** Primary research software documentation. **Access:** Official documentation. **Scope:** Structural analysis, isolability, sensor placement and residual generation tooling.

<a id="source-activefault"></a>

**20. I. Punčochář and J. Škach.** [A Survey of Active Fault Diagnosis Methods](https://www.sciencedirect.com/science/article/pii/S2405896318324467). 2018. **Evidence:** Peer-reviewed review. **Access:** Indexed publisher abstract; bibliographic authors corroborated by university-hosted reference. **Scope:** Auxiliary-input design for diagnosis under uncertainty; specific probes require plant constraints.

<a id="source-maintenance"></a>

**21. M. J. Kim and V. Makis.** [Joint Optimization of Sampling and Control of Partially Observable Failing Systems](https://pubsonline.informs.org/doi/10.1287/opre.2013.1171). 2013-06-01 online. **Evidence:** Peer-reviewed operations research. **Access:** Publisher abstract. **Scope:** Joint observation/maintenance decisions in a particular partially observed failing-system model.

<a id="source-degradation"></a>

**22. S. M. Alia, S. Stariha and R. L. Borup.** [Electrolyzer Durability at Low Catalyst Loading and with Dynamic Operation](https://research-hub.nlr.gov/en/publications/electrolyzer-durability-at-low-catalyst-loading-and-with-dynamic--2/). 2019. **Evidence:** Peer-reviewed experimental electrochemistry. **Access:** National-laboratory publication abstract. **Scope:** PEM technology and specified catalyst/loading/cycling conditions; coefficients must not be transferred to alkaline equipment.

<a id="source-methanation"></a>

**23. L. Colelli, C. Bassano, N. Verdone, V. Segneri and G. Vilardi.** [Power-to-Gas: Process analysis and control strategies for dynamic catalytic methanation system](https://www.sciencedirect.com/science/article/pii/S0196890424001985). 2024-04-01. **Evidence:** Peer-reviewed process study. **Access:** Indexed publisher abstract/excerpts; direct full text unavailable. **Scope:** Dynamic methanation modelling and thermal control; does not calibrate the current lumped reactor fixture.

<a id="source-livingstone"></a>

**24. B. C. Williams and P. P. Nayak.** [A Model-Based Approach to Reactive Self-Configuring Systems](https://aaai.org/papers/144-aaai96-144-a-model-based-approach-to-reactive-self-configuring-systems/). 1996 (paper year; repository page is newer). **Evidence:** Peer-reviewed model-based autonomy. **Access:** AAAI paper record and author manuscript excerpt. **Scope:** Model-based diagnosis/reconfiguration precedent; predefined physical alternatives bound recovery.

<a id="source-nasa"></a>

**25. NASA Jet Propulsion Laboratory.** [Computer Program Assumes Spacecraft Command](https://www.jpl.nasa.gov/news/computer-program-assumes-spacecraft-command/). 1999-05-17. **Evidence:** Agency mission announcement. **Access:** Official text. **Scope:** Remote Agent taking command for a bounded spacecraft test; announcement is not a final performance report.

<a id="source-ecmwf"></a>

**26. ECMWF.** [Quantifying forecast uncertainty](https://www.ecmwf.int/en/research/modelling-and-prediction/quantifying-forecast-uncertainty). Undated documentation; accessed 2026-09-10. **Evidence:** Official forecasting documentation. **Access:** Official text. **Scope:** Ensemble weather uncertainty; local PV conversion and calibration remain separate tasks.

<a id="source-dompc"></a>

**27. do-mpc contributors.** [do-mpc documentation](https://www.do-mpc.com/en/latest/). Current documentation accessed 2026-09-10. **Evidence:** Primary software documentation. **Access:** Official documentation. **Scope:** Nonlinear/robust MPC and moving-horizon estimation tooling; not a certified controller.

<a id="source-casadi"></a>

**28. CasADi contributors.** [CasADi documentation](https://web.casadi.org/docs/). Current documentation accessed 2026-09-10. **Evidence:** Primary software documentation. **Access:** Official documentation. **Scope:** Symbolic differentiation and optimization interfaces.

<a id="source-acados"></a>

**29. acados contributors.** [acados documentation](https://docs.acados.org/). Current documentation accessed 2026-09-10. **Evidence:** Primary software documentation. **Access:** Official documentation. **Scope:** Fast optimal-control problem solvers; not a direct replacement for a mixed-integer scheduling solver.

<a id="source-gym"></a>

**30. Farama Foundation and contributors.** [Gymnasium documentation](https://gymnasium.farama.org/). Current documentation accessed 2026-09-10. **Evidence:** Primary software documentation. **Access:** Official documentation. **Scope:** Standard environment interfaces and seeding; observation separation is the environment author's responsibility.

<a id="source-boptest"></a>

**31. IBPSA Project 1 contributors.** [Building Optimization Testing Framework (BOPTEST)](https://ibpsa.github.io/project1-boptest/index.html). Project documentation accessed 2026-09-10. **Evidence:** Primary benchmark project. **Access:** Official project documentation. **Scope:** Reproducible building-control benchmarking precedent; its buildings are not methane-plant models.

<a id="source-safegym"></a>

**32. Z. Yuan et al..** [safe-control-gym: A Unified Benchmark Suite for Safe Learning-based Control and Reinforcement Learning in Robotics](https://arxiv.org/abs/2109.06325). 2022 publication; preprint 2021. **Evidence:** Peer-reviewed benchmark; author preprint. **Access:** Author abstract. **Scope:** Robotics benchmark pattern for safety/performance comparisons; not plant validation.

<a id="source-yokogawa"></a>

**33. Yokogawa Electric Corporation and JSR Corporation.** [Yokogawa and JSR Use AI to Autonomously Control a Chemical Plant for 35 Consecutive Days](https://www.yokogawa.com/news/press-releases/2022/2022-03-22/). 2022-03-22. **Evidence:** Joint supplier/customer deployment announcement. **Access:** Official company text. **Scope:** Control of a distillation column with existing protection and monitoring; title is broader than the described test boundary.

<a id="source-phaidra"></a>

**34. Phaidra.** [Autonomous AI Control of Mission-Critical Cooling at Merck](https://www.phaidra.ai/blog/autonomous-ai-control-of-mission-critical-cooling-at-merck). 2024-06-25. **Evidence:** Vendor customer case study. **Access:** Official company text. **Scope:** Cooling setpoint control with local BMS handover; not independently audited general fault repair.

<a id="source-imubit"></a>

**35. Imubit.** [3 Reasons Your Refinery Needs Closed-Loop AI Optimization](https://imubit.com/blog/3-reasons-your-refinery-needs-closed-loop-ai-optimization). Undated page; accessed 2026-09-10. **Evidence:** Vendor customer case material. **Access:** Official company text. **Scope:** Named refinery closed-loop optimization and retraining after feed changes; no cross-vendor benchmark.

<a id="source-rivan"></a>

**36. Harvey Hodd / Rivan.** [Rivan deploys full-scale 1MW system](https://rivan.com/news/rivan-deploys-full-scale-1mw-system/). 2026-08-12. **Evidence:** Company deployment announcement. **Access:** Official company text. **Scope:** Deployment and commissioning; extended autonomous performance remains to be established by the cited announcement.

<a id="source-terraform"></a>

**37. Terraform Industries.** [Terraform Industries](https://www.terraformindustries.com/). Undated company timeline; accessed 2026-09-10. **Evidence:** Company technology/timeline page. **Access:** Official company text. **Scope:** Company-reported sunlight/air-to-gas demonstration in March 2024; no broad fault-recovery benchmark.

<a id="source-gproms"></a>

**38. Siemens.** [gPROMS for sustainability](https://www.siemens.com/en-us/products/gproms/sustainability/). Undated product page; accessed 2026-09-10. **Evidence:** Vendor technical/product page. **Access:** Official company text. **Scope:** Process modelling and digital twins, including hydrogen applications; tool availability is not deployment validation.

<a id="source-anybotics"></a>

**39. ANYbotics.** [Robotic Gas Leak Detection with ANYmal](https://www.anybotics.com/news/robotic-gas-leak-detection-anymal/). 2025-06-17. **Evidence:** Vendor technical announcement. **Access:** Official company text. **Scope:** Mobile gas inspection and detection capability; repair and process control are separate functions.

<a id="source-augury"></a>

**40. Augury.** [Machine Health](https://www.augury.com/machine-health/). Undated product page; accessed 2026-09-10. **Evidence:** Vendor product page. **Access:** Official company text. **Scope:** Machine condition monitoring and diagnostic support; rotating-equipment evidence does not establish catalyst or electrolyser remaining life.

<a id="source-raptor"></a>

**41. Raptor Maps.** [Raptor Maps](https://raptormaps.com/). Undated product page; accessed 2026-09-10. **Evidence:** Vendor product page. **Access:** Official company text. **Scope:** Solar inspection and remote drone operations; capability claims are company supplied.

<a id="source-flight"></a>

**42. Raptor Maps.** [Solar PV Inspection Drone Flight Guidelines](https://pages.raptormaps.com/raptor-maps-knowledge-hub/solar-pv-inspection-drone-flight-guidelines). Undated operational guidance; accessed 2026-09-10. **Evidence:** Vendor inspection protocol. **Access:** Official guidance. **Scope:** Provider-specific thermography conditions, including irradiance; not a universal inspection standard.

### Local platform material reviewed

- `methane/config.py`, `methane/sensing.py` and the execution loop in `methane/simulation.py`: current assumptions, observation boundaries and controller behaviour.
- `docs/evidence-summary.md` and `docs/solver-comparison.md`: previously saved experiment interpretation and solver sensitivity, not newly rerun evidence.
- `docs/living-documentation-research.md`: existing research on explanation and evidence presentation.
- The original project brief and future-company/DePIN notes supplied with the project: scope and motivation, treated as project material rather than scientific evidence.

The report is stored outside the application source-capsule allowlist. Producing this research does not alter the simulation or the evidence identity of an existing run.
