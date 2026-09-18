# Investigating recorded operation

Open **Simulation menu → Investigate**, or **Investigate this period**
from a component inspector. The workspace is revealed on request; the normal plant
canvas and reviewed illustrations remain unchanged. Entering pauses playback.

## One question, its evidence and an alternative

1. In **Period**, select an hourly bar or enter a start and end boundary. The end
   is excluded. Methane, unfulfilled requests, curtailment and forced trips are
   calculated in Python from the selected execution records. An unfulfilled request
   means requested minus applied methane, clipped at zero; it is not unmet customer
   demand. Low output alone does not establish a fault. Missing quantities remain
   missing rather than becoming zero.
2. Select equipment and **Inspect decision** to open the existing Control view at
   that decision. Its Evidence view separates information available before the
   decision from observations and diagnosis afterwards. Plan and Delivery retain
   the recorded forecast, constraints, solver status and requested/applied actions.
   Back/Escape returns to the investigation and its focused decision.
3. **Pin evidence** keeps a decision with the investigation. **Try alternative**
   opens an explicit calculation: compare the three dispatch policies, prevent
   battery discharge for one interval, keep electrolysis off for one interval,
   delay a reactor start, or delay the next forecast CO₂ delivery by 24 hours.
   Solver work runs in an isolated, cancellable worker. Completed and incomplete
   prediction results with outputs are saved by the server and linked to the
   investigation; stopped jobs do not publish a replacement result.
4. **Evidence & alternatives** places saved predictions beside the recorded limits
   and pinned decisions. Select equipment to change the displayed trajectory.
   Compare output, decision costs, starts, ending inventories and temperature;
   retain solver limitations when interpreting differences.
5. In **Notes**, record the question, interpretation and next step. **Save
   investigation** creates an immutable edition. Authored interpretations remain
   separate from calculation evidence. **Export write-up** produces self-contained
   HTML; **Export evidence** includes the complete saved calculation packets and
   outputs as JSON. Exports always refer to the last saved edition.

Closing restores the original run view, controller, playback boundary, component
inspector/menu and keyboard focus. Working notes survive close/reload in local
browser storage. Saved investigations appear for the same recording and controller.
Opening an edition allows restoring the previous working draft. Edits made during
a pending save remain unsaved; a delayed edition load cannot replace newer edits.
Range validation, pending/error states, keyboard access, reduced motion and a
narrow layout are part of this workflow.

## Interpretation boundary

The investigation covers the **loaded recording or chronological interval block**.
It does not join several annual blocks into a new recording. The existing project
and study workflow still opens other blocks, revises designs, runs matched full
experiments and exports reproduction bundles.

Alternatives are conditional **process dispatch predictions**. They reuse the
original starting estimate, forecast, available capacity and frozen dispatch
prices. They do not use later realised weather or injected fault truth. Both
reference and restricted dispatch are recalculated using the current implementation;
time-limited solver differences from an old plan remain possible. Saved service
power, isolation and availability commitments are held fixed. They are not new
robot schedules or alternative realised plant histories.

Delaying CO₂ supply can move it outside the saved horizon. No delivery in that
horizon or a reactor already running is explicitly described as an alternative
with no corresponding restriction effect. Turning electrolysis off deliberately
suspends a simple load probe for that interval. Other alternatives retain its
dependable-capacity contract. Decisions containing conditional, multi-interval
recovery tests remain unavailable to this process fork; the recorded recovery
alternatives are the appropriate workflow. No automatic fallback substitutes an
unrestricted solution for an unresolved targeted alternative.

Ending inventories receive no speculative sale credit. Configured methane terminal
allowances and solver statuses remain visible. A binding limit is not a causal
importance score, and a modelled prediction difference does not establish field
performance. No test requires MPC to win.

## Persistence and interfaces

`POST /dispatch/investigation` provides `overview`, `period`, `save`, `load` and
`comparison`. It resolves the server-owned recording capability and validates the
run/controller, interval bounds and referenced evidence. Requests carry a client
generation; stale results and stale errors cannot cross selections. Browser-supplied
numerical results are not accepted as evidence.

The Sites content-addressed store contains three new record kinds:

| Kind | Contents |
| --- | --- |
| `decision-comparison` | Original decision description, worker operands, implementation identities and returned predictions |
| `investigation` | Source identity, selected execution period, authored notes, pinned decisions and complete comparison snapshots |
| `investigation-index` | Small source/controller/title references for listing saved editions |

An investigation uses schema `expert-investigation/1`; comparisons use
`decision-comparison/1`. The original run ID, integrity hash and source identity are
retained where available. A legacy recording without an original integrity hash
gets a local content fingerprint for binding, with missing original provenance
still labelled missing. Saving never rewrites the archive. Source or controller
mismatches and evidence outside the selected period are rejected.

Records live locally under `runs/sites/` (or `DISPATCH_SITES_ROOT`). Browser drafts
are convenience recovery, not a backup. Saved JSON contains the evidence needed to
read the investigation without a job or network; HTML contains the readable account.
Neither is advertised as a complete numerical reproduction bundle. Preserve the
original archive and existing source/environment bundle for reruns. Off-machine
durability remains a separate deployment requirement.

## Verification and walkthrough status

Backend checks in `tests/test_expert_investigations.py` cover independent period
totals, missing data, immutable editions, source ownership, original-information
boundaries, all four real targeted alternatives, incomplete solutions and legacy
provenance. Control transport tests cover actual worker persistence, ownership and
cancellation. Existing Sites/project checks cover the shared store and surrounding
project workflow.

Browser checks in `tests/browser/expert-investigations.spec.cjs` exercise period →
evidence → actual alternative → authored notes → saved edition → export → return.
They also cover invalid ranges, stale replies, edits during pending requests, draft
recovery, keyboard focus and narrow screens. Existing Control view and plant/solar
checks remain applicable; original screenshot baselines are unchanged. Reviewed
workspace captures and a short render timing sample are written to
`build/expert-investigation/` as local review artifacts.

The implementation check used 38 focused Python tests, 95 JavaScript unit tests
and 27 distinct browser cases across investigations, Control view, projects and
the existing platform. Ruff lint/format and documentation binding checks passed.
Three environment-gated browser cases (new component lineage, extracted offline
player and fresh Site entry) were not enabled in this scope. The existing platform
artwork checks passed without baseline changes. A 17-render desktop sample measured
p95 of 1.9 ms; it measures synchronous workspace rendering, not network/solver
latency or sustained batch-load performance.

This is an **agent-conducted workflow rehearsal**, not an expert-participant study.
The rehearsal found and corrected a hidden save footer, lost return navigation via
the hide-controls shortcut, Escape after disabling the Save button, and races around
pending edits. No participant responses
or comprehension outcomes have been collected. A real walkthrough should ask an
intended user to find a difficult period, distinguish a recorded observation from
a prediction, explain one comparison limitation, save their interpretation and
return to the original operation. Record misunderstandings separately from software
test outcomes; use them to revise the interaction before claiming user validation.
