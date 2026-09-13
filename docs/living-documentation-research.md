# Living documentation: research and design exploration

Research date: 10 September 2026. Status: proposal for discussion; no application
changes made. The purpose is to make the platform's component mechanics, modelling
choices and recorded evidence understandable while preserving quiet plant operation.

## What the existing work tells us

The review covered the available earlier task responses, the solar exploration,
component contracts and catalogue, component-engineering guide, engineering
completion record, original comparative experiment findings, and the current UI.
Some earlier research/planning turns were empty in task retrieval; this note does
not claim to have recovered their complete source lists.

The relevant local material is:

- [Component contracts](../methane/contracts.py) and [generated reference](components.md).
- [Component engineering](component-engineering.md) and [completion evidence](engineering-completion.md).
- [Solar workspace rationale](solar-workspace.md).
- [Earlier experiment findings](evidence-summary.md) and [controlled solver comparison](solver-comparison.md).

We already have versioned parameters, assumptions, execution/planning boundaries,
observations, component transitions, cost operands, checks and recoverable run
bundles. The user-facing gap is interpretation and navigation. Raw traces answer a
developer's question but require users to reconstruct the story themselves.

The experiments also supply useful teaching examples: stored hydrogen can coexist
with inadequate electrical/thermal reserves; ending inventories change how a
period's methane output should be interpreted; equivalent model formulations can
produce different time-limited solver schedules. These are examples with particular
configurations and source versions, not universal findings about current controllers.

There is a concrete documentation-drift example: the handwritten solar-workspace
page identifies solar-sections/1, while the current contract identifies version 2.
Generating reference tables alone cannot keep explanatory narratives current.

## Research findings and their application

**Organize around different reader needs.** Diátaxis separates explanation,
reference, tutorials and task-oriented guides. This suggests distinct routes for
understanding a mechanism, looking up a parameter, following a worked example and
reproducing a result. Those routes need not become four permanent tabs. [Diátaxis](https://diataxis.fr/)

**Keep deeper material discoverable.** Nielsen Norman Group describes secondary
screens as a way to reveal advanced features on request, with clear labels and
simple navigation. It also cautions against deep disclosure hierarchies. Applied
here: one separate Model workspace, a short topic navigation, direct links from
results, and no stack of nested accordions. [Progressive disclosure](https://www.nngroup.com/articles/progressive-disclosure/)

**Let readers question an explanation.** Bret Victor's explorable explanations
combine authored explanation, interactive examples and contextual sources. The
useful feature is the relationship between an argument and an experiment, rather
than animation by itself. Our examples should ask a precise question and expose
the consequences of changing an assumption. [Explorable Explanations](https://worrydream.com/ExplorableExplanations/)

**Document the case for using a model.** TRACE connects model purpose, formulation,
development, testing and analysis. Its later notebook work emphasizes retaining
the modelling process as it evolves. We can adapt this to an engineering model
without claiming ecological-model certification: keep the reasons for an
approximation, the evidence examined, and the decisions made about its scope.
[TRACE framework](https://doi.org/10.1016/j.ecolmodel.2014.01.018),
[TRACE modelling notebooks](https://doi.org/10.1016/j.envsoft.2020.104932)

**Credibility depends on the intended use and evidence dimensions.** NASA-STD-7009B
separates intended/permissible use and verification/validation, and calls for
records of model capability and results assessments. This supports a claim-specific
evidence view instead of one overall trust score. This is inspiration for our
design, not a claim of compliance with the standard. [NASA-STD-7009B](https://standards.nasa.gov/sites/default/files/standards/NASA/B/1/NASA-STD-7009B-Final-3-5-2024.pdf)

**Make model composition inspectable.** pvlib's ModelChain exposes choices for
irradiance, temperature, conversion and losses; OpenMDAO generates model diagrams
and other reports during model execution. These are useful precedents for a
component's visible transformation chain and automatically assembled reference.
They do not imply that we currently implement pvlib's physical models or should
replace our architecture. [pvlib ModelChain](https://pvlib-python.readthedocs.io/en/stable/user_guide/modeling_topics/modelchain.html),
[OpenMDAO reports](https://openmdao.org/newdocs/versions/latest/features/reports/reports_system.html)

**Preserve the relationships behind a result.** W3C PROV distinguishes entities,
activities and responsibility; RO-Crate describes packaging research data and its
context. Our UI can translate those relationships into readable source-to-result
steps, while the exported report retains machine-readable identities. Adopting
a full interchange standard can be a later interoperability choice. [PROV primer](https://www.w3.org/TR/prov-primer/),
[RO-Crate introduction](https://www.researchobject.org/ro-crate/specification/1.2/introduction.html)

These sources establish useful principles and precedents, not proof that a
particular proposed Dispatch Lab layout will work. The layout needs user testing.

## Proposed workspace

Use **Model** as the short menu label; think of the destination as a living model
atlas. It is a separate full-screen stage. Entering from an inspector uses
**How it is modelled**; entering from a value uses **Trace calculation**. Both
arrive at the same workspace with different initial selections.

Retain the equipment illustration as the spatial anchor. Selecting a mechanism
reveals one explanation, equation or evidence item alongside it. Use the existing
amber instrument language and original artwork. Keep prose in a readable narrow
column. The plant scene receives no additional permanent labels or documentation.

Navigation preserves run, controller, hour and component. Back/Escape returns to
that context. Browser history, keyboard focus and reduced-motion behavior should
work. On narrow screens, the selected explanation takes the available width and
the component remains reachable through a short breadcrumb.

The main catalogue includes three groups:

1. Physical plant: solar, electrical bus, battery, electrolysis, buffers, reactor.
2. Information and control: weather, forecast availability, sensors, estimates,
   diagnosis, objectives and solver/fallback behavior.
3. Economics and experiments: dispatch incentives, allocated costs, scenario
   assumptions, comparison methods and reproduction.

This prevents the illustrated equipment from hiding the less visible models
that often explain a decision. Display one relevant dependency neighborhood at
a time; reserve the complete connection graph for explicit inspection.

## Questions each component should answer

| Reader question | Proposed presentation |
| --- | --- |
| What does it do here? | A short purpose statement, component illustration and its connections |
| How is it calculated? | Input → transformation → output chain; selectable terms, units and interval timing |
| What have we assumed? | Run value, default, origin, rationale, applicability and omitted mechanisms |
| Where did this value come from? | Recorded operands and transformations, with measurement/estimate/prediction/truth distinctions |
| What evidence supports it? | Named claim, method, result, tested domain, applicable source version and limitations |
| What changes if I alter it? | A focused example with baseline, changed input and visible consequences |

These are content requirements, not six mandatory panels shown together.

For solar, begin with the actual implemented pipeline: saved reference-plane
irradiance and time → section geometry adjustment → condition and temperature
response → electrical conversion and clipping → DC bus. Selecting the geometry
step should expose the illustrative diffuse-light assumption and normalization.
The diagram must not suggest that string I–V behavior, bypass diodes or geometric
row shading exist in the current model. Provider documentation is evidence of
the input source, not evidence that our approximation has been calibrated.

For battery, connect the illustration to starting energy, bus-side charge or
discharge, conversion losses and ending energy. An efficiency control changes a
small example, a balance equation and an energy-flow graphic together. The run's
recorded value remains separately selectable. A hand-calculated round-trip case
provides independent expected values beside the component's computed values.

## Make assumptions actionable

For a parameter, distinguish a configured value from its generic default and
from an empirically supported range. Software-accepted bounds are not a validated
operating envelope. Suggested fields are:

- value and unit; origin such as illustrative, source-derived or user-specified;
- reason for the choice and the precise claim supported by a citation;
- relevant limitations and which outputs consume the parameter;
- a linked sensitivity experiment, if one has actually been run.

For example, battery usage wear is an economic allowance, not simulated physical
capacity fade. Weather reanalysis is a historical reference, not a site sensor.
Parameter uncertainty without an established distribution should say so; a
slider range must not be presented as a confidence interval.

## Separate model explanation, run evidence and exploration

A persistent, compact context indicator inside this workspace distinguishes:

- **This run:** original model, inputs, forecast issue and decision assumptions.
- **Current model:** the current catalogue and evidence for its source version.
- **Example / draft:** an explicitly changed case with its own inputs.

Changing a teaching example never rewrites a completed run. A local calculation
can be immediate; full plant consequences require a new preview or run. A
decision-time alternative must retain the original information boundary. Solar
design replay using all saved weather remains explicitly retrospective.

The reader should also be able to switch between a component's execution model
and what the planner assumed. Differences due to estimates, faults, forecast error
or a time-limited incumbent deserve their own explanation.

## Evidence as claims with scope

Useful evidence statements include:

- Battery energy balance agrees with an independent calculation in the linked cases.
- Reactor temperature agrees with analytical and independent integration checks.
- A finite operating-state abstraction satisfies the checked commitment properties.
- A particular empirical validation dataset is unavailable.
- A run completed with a feasible time-limited solution; optimality was not established.

Each item should disclose the applicable component/source/configuration, method,
tolerance or coverage, execution time, outcome and artifact. A passed historical
test for another source version must not become a passed check for this one.
Missing, failed and stale evidence remain visible in the relevant evidence view.

Use test counts only as secondary detail. A single green badge or percentage
would conceal differences between numerical verification, formal abstraction,
data quality, empirical validation and suitability for a particular decision.

## What makes it living

Generate parameter definitions, units, defaults, component interfaces, recorded
values, source identities and check outcomes from existing structured records.
Author the teaching explanations and reasons for approximations, then bind them
to model/assumption identifiers and reviewed versions. A change to an affected
contract flags the associated narrative for review. Do not reconstruct scientific
rationale by guessing from code.

Link equations to the tested implementation and independent reference cases;
do not introduce a second JavaScript physics implementation for the documentation.
Use saved results and cached small Python calculations for fast exploration.

Include a human-readable snapshot of relevant model explanations, assumptions
and evidence in reproduction exports. Old runs continue to explain the model
they actually used; newer documentation is available as an explicit comparison.

## A useful first prototype to discuss

Build the interaction around the battery, using the existing complete component
example, and use solar to test deeper mechanism navigation. Begin with purpose,
one explorable balance, linked assumptions and one evidence claim. Connect that
page to a real archived battery result and return to the same simulation hour.
This exercises learning and audit workflows before extending the visual language.

Evaluate it with concrete comprehension tasks:

1. Explain why bus-side battery output differs from the reduction in stored energy.
2. Identify which quantity was assumed and which was observed or calculated.
3. Find the original weather/input/model behind a selected result.
4. Explain what an independent passing check establishes and what remains unvalidated.
5. Change an example without accidentally changing the recorded run.
6. Return to the original component and playhead without losing context.

Observe task completion, incorrect interpretations and navigation difficulty.
The remaining product choice is whether learning or formal review should be the
default entry experience. The recommendation is explanation first, with direct
result links entering evidence immediately.
