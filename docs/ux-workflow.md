# P2 · Expert workflow consolidation

The simulation stays a quiet, full-screen instrument. Its menu reveals work in six
tasks: **Site → Build → Operate → Investigate → Compare → Write up**. These are
entry points, not a wizard: an expert can return to any stage without executing the
previous stages again. Site feasibility, an editable project, recorded operation
and a predicted alternative remain different contexts.

## Navigation and information design

The previous menu exposed eleven workspaces beside run information and equipment
shortcuts. Similar names obscured different meanings of “compare”; specialist
tools competed with the ordinary project journey. The first level now presents
six tasks and the current recording's controller/hour. Playback, events, service
operation and retrospective truth are separate reveals. **All tools** searches
the existing specialist surfaces by purpose, including weather, sources, learning,
costs and archives. Searching neither executes a study nor changes a configuration.

| Task | First action | Further detail |
|---|---|---|
| Site | Choose a location or resume its project | Coordinates, land, supply contracts and source evidence |
| Build | Inspect equipment on the editable diagram | All parameters, equipment basis, uncertainty and requirements |
| Operate | Choose recorded playback, project calculation, decision inspection or bounded agent operation | Weather admission, management, costs, long studies and solver controls |
| Investigate | Select a recorded period and decision | Interval rows, original observations, active limits, traces and pinned evidence |
| Compare | Choose a decision, site/design results, or a policy/uncertainty experiment | Identical-information predictions, ending stocks, comparison boundaries and provenance |
| Write up | Continue an operating investigation or choose a study | Authored findings, saved report editions, traceable exports and reproduction bundles |

The menu's Build and Operate routes resume the saved project, not a speculative
reconstruction of the currently displayed recording. Revising a recording's design
still uses its explicit **Revise this design** workflow. Without a saved project,
Build and Operate explain that a site must be selected first. A synthetic example
continues to be labelled as such; choosing a site does not make its weather real.

The original plant and solar SVGs and their labels are unchanged. Playback retains
its step, play/pause and speed controls. The new menu pauses playback so that the
recording does not move underneath a user's navigation. No persistent six-stage
header is added over the plant.

## Working context and progressive disclosure

- Project weather, date, duration, forecast-information, offline and controller
  choices survive stage changes and a browser reload. Designs still pass Python
  validation before saving or execution. A new project does not inherit the previous
  project's run draft. Browser drafts are convenience storage, not an archive.
- Nested Model/catalogue/site tools identify their return destination. Return and
  Escape restore the originating controls. Component, controller and playhead
  restoration continue to use the original recording context. Model and Sites
  retain the originating control's semantic address so progress updates can replace
  its DOM node without breaking keyboard return.
- Completed project cases offer Watch, Investigate and Write up. For multiple
  recorded blocks, one selector chooses the actual saved interval block; the page
  does not grow three buttons for every week of an annual study. Opening a block
  loads its admitted recording, then enters the requested view. Navigation intent
  is kept out of the numerical archive.
- Investigation, comparison of alternatives and write-up share one draft. Detailed
  hourly rows are disclosed only when requested. Exporting a saved edition remains
  possible while editing, with an explicit warning that newer edits are not included.
  Reopening preserves the saved edition link and the newer working notes.
- Study lists disclose templates, prior reports and environments separately.
  The Write up entry offers existing study results and saved editions directly.
  Optional cash-flow identifiers remain available in a separate disclosure.
- Study write-up fields are retained in this browser by report type, source and
  original publication identity. A content fingerprint binds publication to the
  results reviewed when opening the editor. If results advance, publication rejects
  the stale basis; the user can reopen, review the current results and retain their
  notes. Revising an existing publication keeps its original frozen numerical record.
- Offline playback keeps reading, component inspection and source explanations.
  Calculation/editing routes are unavailable with an explicit restoration message.

The six paths reuse the existing Python calculations and immutable result stores.
There is no new physical model, dispatch objective, policy study or inferred evidence.

## Acceptance and limitations

`tests/browser/workflow.spec.cjs` exercises tool discovery, saved run-form choices,
nested return, saved versus unsaved write-up exports, comparison semantics, and a
complete Site → Build → Operate → Investigate → Compare → Write up rehearsal.
The last test executes a short synthetic Greedy case, calculates an original-information
alternative, saves an investigation, then publishes a study report. This verifies
the product path; it is not a new scientific comparison.

`tests/test_siting_workflow.py` checks that publishing against changed results is
rejected, while revising a prior publication retains its original evidence.
Existing browser checks cover keyboard/reduced-motion/narrow layouts, stale replies,
cancel/resume, model controls, source context and portable reading. Plant and solar
screenshot references remain unchanged. The study header reference is intentionally
reviewed for its more specific return label.

During the agent rehearsal, clicking descriptive text in a menu card exposed an
incorrect focus return to a non-interactive child. The return now targets its
containing button. Separately, the run form's lost choices, disconnected report
entry, and unguarded changing report basis were addressed. These are engineering
observations, not participant quotations. Failed test attempts remain under
`build/ux/`; the roadmap records the final verification scope.

**P2's participant gate remains open until real people take part and material
misunderstandings are addressed.** No amount of automated navigation establishes
expert comprehension. [The walkthrough](ux-walkthrough.md) is ready to conduct.
P3 is still installation and off-machine durability; no modelling work is inserted
between these increments.
