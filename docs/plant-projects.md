# Plant projects

A project connects a location, editable plant design and frozen operating cases.
Its Site, Build and Operate views expose the existing simulation in stages. They
retain the full model; they do not define a separate simplified physics model.

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
