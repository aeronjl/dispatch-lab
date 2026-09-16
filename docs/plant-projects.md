# Plant projects

A project connects a location, editable plant design and frozen operating cases.
Its Site, Build and Operate views expose the existing simulation in stages. They
retain the full model; they do not define a separate simplified physics model.

## Using the workspace

1. **Site:** choose a saved European regional anchor or search for another place.
   The compact resource card distinguishes saved PVGIS reference yield from plant
   production. Open **Land, supplies & evidence** for coordinates, parcel geometry,
   screening layers, supply contracts, original sources and saved site designs.
   Return to Site and choose **Build here**. A regional point does not establish
   land availability. Existing projects can be resumed from the name in the header.
2. **Build:** select the actual illustrated equipment. Common controls appear first;
   **More settings** reveals the component's other parameters. **All project
   settings** is searchable, and **Complete configuration** supports optional
   structures. Invalid drafts remain visible while the diagram retains its last
   valid state. **Save changes** creates a revision; **Discard unsaved changes**
   returns to the saved design. Drafts are retained locally on close/reload.
   The Costs overlay shows assumed process equipment capital, not a project quote.
3. **Operate:** choose a compatible saved environment, retrieve historical weather,
   or explicitly select the synthetic learning example. Retrieval saves its inputs
   before calculation starts. Objective, period and source remain visible before
   freezing the run. Longer studies and full comparison tools are available from
   this screen. Calculation has its own progress, cancellation and resumption;
   **Watch interval block** opens recorded playback with the original trace.
4. From a recorded component, choose **Revise this design** (solar provides
   **Revise plant project**). Edit and save, then return to Operate. The comparison
   recalculates both designs using the original information. **Report, traces &
   export** opens the existing calendar, editable write-up and reproduction tools.
5. From recorded playback, **Investigate operation** opens the
   [investigation workspace](expert-investigation.md). Select a period, pin decision
   evidence, calculate a targeted alternative and save an interpretation. Closing
   restores the original operating context. These conditional predictions do not
   replace the full matched design experiment in Operate.

Site services includes the installed packages and their support resources. Add
cleaning, inspection, bounded reset or human support from **Equipment & support**.
The full catalogue is still available, and commissioning/maintenance examples can
be activated explicitly. Changing package selection does not silently erase shared
support assumptions. All configured parameters remain in the full configuration.

**How it is modelled** opens the living documentation in the Current model context.
The project draft is distinct from its learning examples and from This run traces.
The complete standalone simulation setup, learning tools, templates, economics and
source investigations remain under Project tools. Site design revisions made in
those tools can be chosen as the starting design of a new project; they do not
silently overwrite an existing project.

Escape dismisses the current inspector before leaving the project. Closing restores
the originating simulation/controller/hour and focus. Controls are keyboard
accessible; narrow screens use a full-width inspector and a scrollable circuit.
Reduced-motion preferences suppress transitions. A fresh normal app starts at Site;
opening an explicit archive starts at recorded playback. The latter retains its
original five visible controls, with projects revealed through the menu.

## Records and boundaries

`plant-project/1` records are content addressed in the Sites store. Each project
has a stable identity, immutable configuration revisions, an initial baseline,
and a site revision. Saving uses a cross-process lock and rejects a stale parent.
Neither editing nor repricing changes completed operating cases.

A run creates a deployment design and a chronological study through the existing
Sites execution interface. The study records the project identity and revision.
A matched design comparison recalculates both original and revised designs using
the original environment, controller, explicit policy and seed. Other changes to
the design are preserved; this is not automatically a single-factor experiment.
Existing source capsules, continuation checkpoints, solver reporting and original
period playback remain authoritative.

Weather must be selected explicitly. Historical retrieval retains source snapshots
and original forecast issues or an explicitly chosen persistence assumption. The
short synthetic option saves a labelled teaching fixture and causal previous-day
persistence forecasts. It is not a site production estimate. Missing real weather
does not invoke a synthetic fallback. Orientation changes require compatible
irradiance; capacity changes can reuse the saved irradiance conversion.

The equipment palette only enables existing bounded service packages. Their
support assumptions and limitations are shown before installation. The catalogue
continues to include the wider hardware taxonomy without granting unsupported
repair capabilities. Optional lifecycle examples are explicitly illustrative.

Parameter metadata enumerates all present scalar configuration fields, including
nested optional systems and list entries. Common component controls are authored
subsets; full configuration remains available for optional structures. Python
validates drafts and returns display capacities and equipment costs. Browser code
does not calculate physical dispatch or economic allocations.

## Verification

`tests/test_plant_projects.py` checks immutable revisions, conflicting saves,
site binding, parameter coverage, restricted equipment packages, explicit weather,
matched input reuse and a short execution/playback cycle. These are workflow and
correctness checks, not evidence of field realism or controller superiority.

Browser checks in `tests/browser/projects.spec.cjs` exercise common/deep settings,
invalid drafts, retained revisions, package prerequisites, source selection,
calculation/playback, matched alternatives, keyboard return, mobile access,
missing weather and stale responses. The original plant/solar screenshot baselines
are retained. Screenshots of the new views are reviewed as new artifacts rather
than substituted for the original illustrations.

## Operating briefs

Operate and Project tools expose [Operating requirements](operating-requirements.md).
Save production, reserve and service limits for future project runs, then compare
saved designs against the same brief without changing their physical traces.
Requirement revisions are preserved separately from physical configuration.
