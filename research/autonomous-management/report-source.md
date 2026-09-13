# Autonomous management of renewable-powered methane plants

The strongest direction for Dispatch Lab is a **hierarchical controller that plans under uncertainty, maintains an estimate of plant health, and executes bounded recovery procedures**. A constrained economic planner should coordinate electricity, gas inventories and reactor heat. Learning should initially improve forecasts, health estimates and the value assigned to future operating opportunities. A separate supervisor should govern starts, stops, diagnostic probes, degraded modes and recovery. Homeostatic reinforcement learning deserves a focused experimental track within this architecture.

This recommendation is an engineering synthesis, not a claim that one published algorithm solves unattended methane production. The literature supports many of the constituent capabilities. Public industrial evidence is strongest for bounded process optimization and control, with local protection and fallback retained. Evidence for prolonged, whole-plant operation through unfamiliar mechanical faults is substantially thinner in the sources reviewed.

The assessment covers publications and official company material available through **10 September 2026**. It distinguishes mathematical results, simulations, equipment experiments, industrial case reports and vendor claims. The accompanying catalogue contains 16 approach families and 42 primary references. Where only an abstract or indexed publisher excerpt was accessible, that limitation is recorded in the bibliography. No new controller experiments were run for this assessment.

## 1. What autonomy should mean here

An autonomous methane plant must repeatedly answer four connected questions: what condition is the plant actually in; what can it safely do; which feasible action best serves its mission; and whether the result justifies continuing, investigating or recovering. Scheduling alone addresses only part of that loop.

For this platform, a useful mission statement is: **produce useful methane over sustained operation, economically and with bounded intervention, while retaining the ability to remain within operating limits and reach an appropriate shutdown or restart state**. Useful production will eventually include gas specification and delivery acceptance. Until those mechanisms exist in the model, the defensible output is simulated methane mass, not certified saleable product.

Autonomy should be specified as a coverage envelope: a set of operating conditions, disturbances, fault classes, available recovery actions and acceptable escalation outcomes. A controller that safely identifies an unrecoverable fault and arranges service can be more autonomous than one that repeatedly attempts an unsafe restart. “No human action under any circumstance” is an unsuitable target for equipment whose physical repair options are limited.

There is a substantial precedent outside process engineering. Model-based spacecraft autonomy combines reasoning about system modes with diagnosis and reconfiguration; NASA's Remote Agent announcement described a bounded Deep Space 1 command experiment in 1999. The transferable idea is an explicit relationship between plans, execution and equipment state. Neither source implies that software can repair arbitrary broken hardware. [@livingstone] [@nasa]

### The starting point in Dispatch Lab

The current source already has coupled electrical and material accounting; battery and gas buffers; a lumped thermal reactor; greedy, methane-MPC and economic-MPC policies; versioned execution and planning components; causal forecast selection; recorded decisions; bounded diagnosis; isolated jobs; and reproducible archives. These are useful foundations for comparing autonomous strategies under identical information.

Several simplifications now become research boundaries. The simulation is hourly. Battery energy, CO₂ inventory and reactor temperature are currently ideal observed state channels. Hydrogen-buffer metrology noise scales with interval throughput rather than tank capacity, making low-flow residuals easier to observe than some real installations would allow. There are two injected fault classes, and the simulator's scheduled capacity recovery is not a repair process. Pressure, product quality, local reactor hotspots, detailed actuator dynamics and essential protection loads are outside the current plant abstraction. These observations come from the local configuration, sensing and simulation source, not external literature.

The next step in realism should therefore be selected by the autonomy question. Studying sensor isolation requires independent measurement channels with plausible errors and delays. Studying unattended restart requires restart prerequisites and failure outcomes. Studying maintenance requires health evolution. Adding a highly detailed illustration or a neural policy cannot compensate for missing mechanisms. Dynamic methanation literature also considers spatial temperature profiles, conversion and product composition during changing hydrogen loads—behaviour that the current lumped thermal fixture does not represent. [@methanation]

## 2. Where the state of the art sits

Three strands are converging. Process control supplies constrained optimization, estimators and supervisory sequencing. Machine learning supplies adaptable models, policies and value estimates. Reliability engineering supplies diagnosis, inspection and maintenance decisions. A process-industry RL review spans control and related operational tasks, illustrating that the field is broader than one end-to-end policy. The learning-MPC literature distinguishes learning the prediction model, tuning the optimization formulation and using MPC to constrain a learned controller. [@processrl] [@hewing]

**Industrial learning control is real, but its operating boundary matters.** Yokogawa and JSR reported 35 consecutive days of reinforcement-learning control in early 2022. The described equipment was a distillation column, with existing protection, monitoring and integration into a distributed control system. This is stronger evidence than simulation, but it does not establish unattended recovery of an entire chemical plant. [@yokogawa]

**Hybrid planning and learning is especially relevant to renewable fuels.** A 2024 electrolyser study combines site-wide planning with real-time optimization. A 2026 green-ammonia paper uses a Q-function as the terminal cost of stochastic MPC, addressing consequences beyond its immediate horizon. The latter is a simulation study in an adjacent process, not a methane deployment. It is nevertheless a close match to the problem of valuing energy and feedstock left for tomorrow. [@hydrogen] [@qsmcp]

**Safety results are conditional results.** A predictive safety filter can check a proposed action against a model and backup trajectory. Its guarantee depends on the stated uncertainty, feasibility and computation assumptions. It cannot protect an unmodelled pressure system merely because the battery and thermal equations are verified. Keeping those scopes visible is essential when incorporating such methods into the platform. [@safety]

### Company landscape: what the public evidence actually establishes

| Organization | Relevant public evidence | Implication and remaining boundary |
|---|---|---|
| Yokogawa / JSR | Joint March 2022 report of 35 days of RL control of a distillation column. | Bounded industrial deployment with protection retained; not whole-plant fault autonomy. [@yokogawa] |
| Phaidra | June 2024 Merck case describes autonomous cooling setpoints and transfer back to local building-management control. | Useful pattern for learned supervision and fallback; a vendor case, not an independent comparison of general recovery methods. [@phaidra] |
| Imubit | Named refinery case material describes closed-loop optimization and retraining after feed changes. | Model updating is part of operations, rather than a one-off training event. Public material does not provide a common benchmark against alternatives. [@imubit] |
| Rivan | August 2026 announcement of a deployed 1 MW system entering commissioning. | Direct mission relevance. Commissioning and planned autonomous validation should not be presented as an established long-duration reliability record. [@rivan] |
| Terraform Industries | Company timeline reports a March 2024 end-to-end sunlight/air-to-gas demonstration. | Evidence of integrated process ambition; the cited page does not document comprehensive diagnosis or recovery performance. [@terraform] |
| Siemens gPROMS | Process-modelling and digital-twin offerings include hydrogen applications. | A route to richer engineering models and model exchange; software availability is distinct from validated autonomous operation. [@gproms] |
| ANYbotics | June 2025 material describes mobile gas-leak inspection. | Physical inspection can become an action available to autonomy. Detection and localization remain separate from repair. [@anybotics] |
| Augury | Machine Health offering combines condition monitoring and diagnostic support. | Relevant to pumps, compressors and other monitored machinery; it does not establish catalyst or electrolyser remaining life. [@augury] |
| Raptor Maps | Remote solar inspection and drone operations. | A potential inspection layer for PV assets. Its thermography guidance makes clear that useful inspection depends on environmental conditions. [@raptor] [@flight] |

The commercial opportunity suggested by this evidence is integration: a plant that can connect an uncertain forecast, a health hypothesis, a changed schedule and a verified recovery action. This is an inference from the coverage of these examples, not proof that no company already offers overlapping capabilities.

## 3. Catalogue of approaches

The methods below solve different parts of the problem and can be composed. “Priority” expresses a recommendation for Dispatch Lab, not a ranking of scientific quality. Maturity in another domain does not validate transfer to methane equipment.

{{APPROACH_TABLE}}

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

Here, `m` is simulated methane output; `v` is an explicit assumed value per kg; every cost term is in the same monetary unit; `b` is the estimated state and its uncertainty; and `V` is a continuation value. `L` is a separately defined adverse operating loss over the horizon, such as unmet contracted production plus recovery expense. Its definition and any overlap with expected costs must be visible. `λ` is an intentional premium against bad outcomes, not a hidden duplication in the accounting report. CVaR provides a tractable way to price the adverse tail of a modeled distribution; it is not protection against every possible event. [@cvar]

This is a proposed formulation. Economic MPC provides relevant theory, but its published stability conditions do not automatically apply to a nonstationary solar plant with binary modes and time-limited solves. [@empc]

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

Homeostatic RL links reward to changes in an internal drive function: an action is valuable when it reduces deviation from a physiologically preferred state. Keramati and Gutkin's 2014 formulation connects discounted drive-reduction reward to regulation and anticipatory behaviour. It also exposes why discounting and trajectory treatment matter: an undiscounted difference of consecutive drive values can telescope into an endpoint comparison. This is a computational account of regulation, not evidence of industrial control performance. [@homeo14]

The idea has continued to develop. A 2024 deep-HRL study models long-term nutritional behaviour. A 2025 perspective relates internal state to motivation and anticipation. A 2026 computational study investigates gradual proactive regulation and shows that coupling several internal variables through shared actions can create destabilizing interactions. Those are useful research signals for a plant in which heating uses the electricity needed to replenish hydrogen; they do not establish a ready-made plant controller. [@homeo24] [@homeo25] [@homeo26]

Active inference offers a related but different formulation: action and information seeking arise from a generative model and preferred outcomes. A 2022 study explicitly simulates homeostatic, allostatic and goal-directed regulation. Its “free energy” terminology is a statistical construct, not reactor heat or electrical energy. For this project, any claimed advantage should be translated into measurable decisions and compared with ordinary belief-state planning. [@activeinference]

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

Potential-based shaping has policy-invariance results under its stated MDP and discount assumptions. Applying it with changing targets requires representing the relevant context in the state; finite episodes also need consistent terminal handling. A belief approximation, a truncated simulation or an incorrectly reset potential can invalidate the intended interpretation. [@shaping]

The research question is not whether an internally motivated agent can keep a battery charged. It is whether this representation improves sustained production, sample efficiency, adaptation or interpretability compared with a planner or learned policy given exactly the same reserve information. Test fixed-band HRL, forecast-conditioned HRL, MPC with those same bands, and a baseline RL policy with the same observations and hard action constraints. Keep model-learning benefits separate from reward-design benefits.

Useful adversarial cases include a safe cold shutdown, a long night, scarce CO₂, repeated reset opportunities, cheap but damaging cycling, an uncertainty signal that can be manipulated by avoiding measurements, and a fault that makes all reserve targets jointly impossible. These distinguish useful anticipation from hoarding, reward loops and conflicting drives.

## 6. Scheduling intermittent power and adapting to wrong forecasts

### Plan jointly across resources and time scales

The recommended scheduler is initially mixed-integer economic MPC, retaining the existing HiGHS implementation and verified component ports. It should choose equipment modes, electrical allocations, gas use, heater power and cooling together. The first action is implemented; observations then update the next optimization. A faster regulation layer would eventually track its setpoints, while independent local protection handles faster failures.

There should be no universal allocation order such as “electrolysis first, battery second.” Near a constrained restart, another kWh in the battery may be more useful than hydrogen; with adequate thermal reserve and a hydrogen-limited run ahead, the opposite can hold. Explain such choices through matched counterfactual replans. Marginal values from a continuous relaxation may also help, but must be labelled as relaxation results: binary starts and minimum runs can make actual trade-offs discontinuous.

Time scales should be treated as design choices to validate. Hourly decisions suit the current sandbox. A later plant may require a supervisory update every few minutes, faster temperature/flow regulation and much faster electrical protection. An hourly balance cannot demonstrate correct behaviour during a subsecond DC-bus collapse or a local temperature excursion between recorded samples.

For uncertainty, begin with a small set of coherent forecast trajectories: central, overestimate, delayed-ramp and prolonged-shortage cases, then calibrated ensembles. ECMWF ensembles provide a source of meteorological uncertainty, but conversion to site PV and operationally meaningful shortage probabilities requires additional modelling and calibration. Preserve correlation across hours; independent hourly noise can create implausible alternating weather and underestimate sustained shortages. [@ecmwf]

In scenario MPC, alternative future plans may branch only after the relevant information would be observed. Their first action must be shared. Otherwise an apparently excellent controller has effectively selected a different present action for each future weather realization. Record scenario weights, branches, availability times and the uncertainty model version alongside the plan. Stochastic MPC supplies several formulations, each with its own assumptions and computational burden. [@mesbah]

### Adapt the right model when conditions change

Forecast adaptation should separate at least four causes of error: weather forecast bias; local PV conversion error; sensor bias; and changed equipment capability. A solar shortfall should not automatically become an electrolyser capacity fault. A lower methane rate should not automatically trigger retraining of the weather model.

Use lead-time- and regime-dependent residuals, recent forecast calibration, and explicit missing-data states. A rolling bias correction is a useful baseline. More advanced predictors can be evaluated against the decision losses they cause, rather than just RMSE; “predict, then optimize” research formalizes that distinction. Adaptive conformal methods can help track uncertainty coverage under change, but long-run coverage does not guarantee adequate coverage for every night, fault condition or joint trajectory. [@spo] [@aci]

A practical proposal is stochastic planning for normal economic choices, with a more conservative recovery envelope for essential loads and irreversible commitments. The uncertainty sets must be distinguishable: an expected-revenue scenario distribution and a protective disturbance bound serve different purposes. Neither should silently expand into a claim of safety under arbitrary weather or faults.

When forecast confidence falls, actions should change in proportion to their consequences. Shorten an unreliable commitment, leave more reserve, prefer a reversible action, or move to a known degraded policy. Record the triggering evidence and the cost of conservatism. The “healthy” planner should not remain nominal merely because its solver found a mathematically feasible trajectory under an outdated forecast.

## 7. Faults: detection, localization, maintenance and recovery

### Begin with distinguishability and measurements

Sensor-based diagnosis should start with a fault-to-measurement structure. Which independent relationship is violated by capacity loss, a biased flow meter, a leak, a stuck valve or a drifting temperature sensor? Which pairs produce the same observable signature? Structural sensor-placement literature and the Fault Diagnosis Toolbox provide concrete machinery for asking these questions before training an anomaly detector. [@sensors] [@fdtool]

For the current electrolyser example, compare electrical tracking with hydrogen mass balance. The power residual should use the command actually issued after resource allocation, with timing and mode semantics preserved. Comparing measured power to an infeasible pre-allocation request can classify a cloud-induced shortage as broken equipment. Compare flow-meter hydrogen with independently inferred inventory change plus known outflow, allowing for metrology uncertainty, startup behaviour and transport delay.

These are not automatically independent channels in real equipment. Tank mass inferred from pressure and temperature inherits both sensors' errors and a gas model. Several identical sensors can share calibration drift, power loss or a common communication fault. “Two sensors agree” does not prove that either is correct. The measurement model should express such dependencies and classify unresolved combinations as ambiguous.

An estimator—initially a modest Kalman-style or moving-horizon formulation, depending on the model—can maintain state, slow parameter changes and candidate sensor biases. Do-mpc supplies MHE tooling. Estimation complexity should follow demonstrated observability, not precede it. Learned soft sensors can supplement this evidence, but their training coverage and correlated inputs must remain visible. [@dompc]

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

A small load perturbation can discriminate a capacity limit from a flow-sensor fault. An inspection can resolve a hypothesis that ordinary operation cannot. Active fault diagnosis studies deliberate auxiliary inputs under uncertainty; partially observed maintenance research connects the timing of observations to subsequent decisions. [@activefault] [@maintenance]

For Dispatch Lab, start with a finite menu of probes. Each should specify its permissible modes, available power, storage headroom, thermal prerequisites, maximum duration, expected discriminating observations and abort conditions. Permit a probe only when its likely operational benefit exceeds its energy, delay and wear cost. Do not award an unlimited information bonus that makes the controller repeatedly interrogate already-understood equipment.

Physical inspection has its own constraints. A mobile robot may obtain an independent gas measurement; a drone may inspect PV thermally. Raptor Maps' particular thermography protocol calls for sufficient irradiance, including a 600 W/m² threshold. That is a provider-specific requirement, not a universal standard, but it illustrates a general planning issue: the moment an inspection is most needed may not be the moment it is informative or possible. [@anybotics] [@flight]

### Predictive maintenance needs a health model

The current usage and start allowances price assumptions; they do not predict failure. A credible maintenance model needs equipment-specific measurements, loading history, maintenance events, censored lifetimes and uncertainty about failure mechanisms. Remaining useful life should be a conditional distribution or a bounded estimate, with clear dependence on the future operating policy—not a single countdown displayed as fact.

Electrolyser technology matters. Experimental work on PEM electrolyser durability found materially different degradation under different dynamic protocols; renewable-like profiles were less severe than some accelerated square/triangle cycling protocols. This is evidence against a universal “one start equals this much damage” rule, and it does not provide coefficients for alkaline or anion-exchange equipment. [@degradation]

The recommended progression is a documented synthetic health model for controlled experiments, then calibration against relevant equipment data. Add service actions with duration, cost, crew/spare requirements and uncertain efficacy. A repair can restore only some health variables; replacing a sensor should not rejuvenate the stack. Maintenance planning can then trade a visit during a low-solar interval against the probability and consequence of later failure. The POMDP maintenance literature supplies a framework, not ready-made parameters. [@maintenance]

### Recovery should be a verifiable sequence

Represent recovery as `suspect → isolate or derate → stabilize → investigate → attempt permitted restoration → verify → return or lock out`. The sequence is an engineering proposal. Every action needs preconditions, expected postconditions, a timeout and a bounded retry policy. A restored communication link, a reset drive and a repaired cooling loop require different evidence.

Report recovery by fault class and available hardware. Software can substitute a sensor, reroute through a modeled redundant component, reduce load, or verify that a repaired subsystem is usable. It cannot replace a failed pump unless the plant actually contains an autonomous replacement mechanism. This distinction makes the future case for modular hardware, redundancy and remote maintenance measurable.

## 8. Controller architecture and available machinery

The recommended architecture is shown below. The arrows represent information and authorized proposals; detailed equipment protection remains local. Each box should retain the versioned interfaces already established in the platform.

{{ARCHITECTURE}}

The central interface is a **control context** containing timestamped observations, a state/health belief with uncertainty, eligible forecasts, active commitments, available action capabilities, and versioned objectives. It must not contain injected fault labels, the scheduled time at which a simulator will repair a fault, or future realized weather. A planner returns a proposal with predicted trajectories, assumptions, solver termination and constraint evidence. The executive records what was requested, what was authorized, what was applied and what was observed.

A safety filter can reject or minimally modify a proposal only within its modeled scope. The rejected proposal and the replacement both remain in the record. When safety intervention becomes frequent, the planner is poorly matched to its environment; the filter's success should not conceal that failure. Independent local protection and a feasible fallback remain necessary design elements. [@safety]

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

Begin with offline training in the simulator and shadow evaluation. Offline RL methods such as Conservative Q-Learning address one important problem—overoptimistic values outside logged action support—but do not create evidence for unobserved fault regimes or guarantee physical safety. Real exploration should eventually be restricted to engineered identification and probe actions, rather than unconstrained reinforcement learning on working equipment. [@cql]

### Software choices

Keep Python, SciPy/HiGHS and the existing component contracts for scheduling. Add a Gymnasium-compatible environment adapter when training is needed, with strict observation/truth separation and seeded resets. Use the Fault Diagnosis Toolbox for an initial isolability and sensor-placement study. For nonlinear estimation or faster lower-level control, evaluate CasADi with do-mpc or acados in a separate component; these tools do not directly replace mixed-integer scheduling. [@gym] [@fdtool] [@casadi] [@dompc] [@acados]

The training environment should support batched rollouts, checkpoints, cancellation, scenario registries and held-out evaluation. Use an independently checked high-fidelity or alternative model for final challenges where possible. A fast simulator used for both training and evaluation can reward exploitation of its own approximations. BOPTEST and safe-control-gym offer useful examples of standardized control comparisons, while their underlying buildings and robotics systems should not be mistaken for methane validation. [@boptest] [@safegym]

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

{{REFERENCES}}

### Local platform material reviewed

- `methane/config.py`, `methane/sensing.py` and the execution loop in `methane/simulation.py`: current assumptions, observation boundaries and controller behaviour.
- `docs/evidence-summary.md` and `docs/solver-comparison.md`: previously saved experiment interpretation and solver sensitivity, not newly rerun evidence.
- `docs/living-documentation-research.md`: existing research on explanation and evidence presentation.
- The original project brief and future-company/DePIN notes supplied with the project: scope and motivation, treated as project material rather than scientific evidence.

The report is stored outside the application source-capsule allowlist. Producing this research does not alter the simulation or the evidence identity of an existing run.
