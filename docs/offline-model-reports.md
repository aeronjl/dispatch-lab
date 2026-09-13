# Offline Model reading

New reproduction bundles open `model-report.html` as a small reading index. Original essays, assumptions, limitations and evidence summaries remain there. Each topic's original parameter defaults, interface contracts and detailed evidence open on linked pages. Recorded intervals link to separate calculation pages and service records. Local fonts and styles require no network access.

This is a reading representation, not a numerical rerun. The exporter invokes the existing calculation/lineage adapters against the saved recording. It never starts the planner, trains a policy or regenerates teaching examples. An archive without original explanations or saved teaching outputs explicitly says they are missing. Later examples or evidence are never inserted as if they existed when the run was made.

## Information boundaries

- Original dispatch and service-price identities remain frozen. Accumulated cost and experiment calculations state their interval boundary. Undefined unit costs remain undefined.
- Controller and weather pages show the prediction and information saved at the decision boundary. Diagnostic pages distinguish channels acquired during the interval from estimates before and after it. Physical execution calculations and applied service effects are retrospective.
- Each page distinguishes the original execution identity from the implementation used to derive this report. The original documentation snapshot retains its own identity. Reading a current derivation does not grant current evidence to an older model.
- Complete JSON calculations preserve operands, units, transformations, source identities and context. Readable lineage pages follow the same operands. Long values are split without truncation; large tables continue across labelled pages.
- Readable controller trajectories show applied actions and ending states. Their full prediction records remain in linked data. The service reading pages show accounting, work state and events; large original decision searches and planning snapshots remain in the complete service JSON. Summary pages do not replace those records.

## Preservation

The `dispatch-lab/offline-model-pages/1` manifest records the input hash, original recording seal where available, execution and documentation identities, current renderer identity and hashes of emitted files. Hashes establish integrity, not authenticity or empirical validity. The outer reproduction manifest also covers the page manifest.

A single-run bundle includes `model-report-source.json`. A study bundle shares that capsule once at its root and links it from each case's report. Original executable source remains separately preserved for numerical reproduction. The standard-library bundle checker verifies the new reading files alongside the original recordings and numerical checks.

New files are streamed into the archive. Existing runs, publications, source capsules and earlier exports are preserved. The legacy monolithic `documentation.offline_report` function remains available to callers of that interface; new reproduction and service-example exports use `offline_model.pages`/`write`. Main simulation and solar illustrations are unchanged.

External scientific references remain links and require connectivity when followed. Saved reading and playback work offline. Live exploration, alternative calculations and numerical reruns require the restored application and its dependencies. The explicit Recorded playback link opens the saved simulation; ordinary browser Back retains browser-managed navigation state. The export does not imply a new simulation has been run.

## Checks

Tests compare all topic calculations with the existing recorded-calculation interface, verify independent battery arithmetic, immutable source inputs, original missing-data semantics, complete service records, escaped long values, relative links and shared renderer capsules. Portable export tests execute the dependency-free checker. Actual-size browser checks cover offline font loading, readable page bounds, original evidence, desktop/narrow layout, keyboard table access and navigation. Measurements are scoped to their fixture and source; one opening or export measurement is not a p95 or an active-batch latency claim.
