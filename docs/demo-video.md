# Shareable plant demo

For the longer, title-card-led competition walkthrough, see the
[2:48 submission film](submission-video.md). The short social editions below
remain preserved separately.

The current **46-second silent film** shows the plant, controller planning,
robot cleaning and inspection, a human repair visit, and a policy comparison.
It uses the original Departure Mono / amber equipment and robot artwork.
The only editorial text is a short section heading at a time, in a light,
rounded Helvetica Neue / Arial card, visibly separate from the app.

The delivery is `build/demo-video/dispatch-lab-demo-control.mp4`: 1920 × 1080,
30 fps, H.264 / YUV 4:2:0, with a front-loaded MP4 index and no audio track.
`dispatch-lab-demo-control.html` is its local player. `index.html` defaults to
this version; `?edition=minimal` and `?edition=original` still select the earlier
movies. Neither earlier movie is overwritten. Nothing is published to X.

## What changed

The controller gets readable screen space instead of merely switching names.
These scenes use the **production Control view renderer**, with larger,
film-only framing. Numeric statements, diagrams and tables come from saved
Python calculation responses; the film does not implement a second controller.

| Seconds | Scene | Visible mechanism |
| --- | --- | --- |
| 0–3 | Plant simulation | Connected operating plant |
| 3–10 | Planning ahead | Charge now; move along the recorded horizon to later discharge, with a prior-plan comparison |
| 10–16 | Solar cleaning | Recorded robot departure and cleaning poses |
| 16–23 | Fault inspection | Rover travel and bounded inspection |
| 23–28 | Adapting to a fault | Requested versus applied load, capacity-loss estimate and an unconfirmed recovery probe |
| 28–34 | Human repair | Travel, isolation and repair, followed by awaiting verification |
| 34–43 | Comparing control policies | Identical starting information; contrasting predicted battery trajectories, methane, costs and remaining energy |
| 43–46 | Plant simulation | Return to the plant |

Planning holds recorded decision H14 (completed plant boundary H15) while the
forecast cursor moves to H17/H18. It does not advance the physical plant into a
prediction. Adaptation shows recorded decisions H13/H14. The comparison holds
recorded decision H16 from methane MPC and forks its information into three
current-model predictions. It **does not compare three already-diverged plant
histories**. Column and curve highlighting is editorial emphasis.

## Rebuild

Install the locked browser dependencies with `npm ci`, Playwright Chromium and
FFmpeg. From the repository root:

```sh
node tools/demo-video/render.cjs --preview
node tools/demo-video/render.cjs
uv run python tools/demo-video/verify.py
```

Preview rendering writes review frames; full rendering writes the movie, player
and manifest. Both run offline without starting or changing the user's app, and
fail if a browser error or an HTTP request occurs. `--minimal` selects the
previous storyboard, for an explicit rebuild of that older edition.

The storyboard lives in `tools/demo-video/storyboard.json`. Camera framing,
selective detail, type sizing and heading styling are in `film.js` / `film.css`.
No application artwork, calculation or UI file is modified by rendering.
Every captured frame uses the production playback clock and existing component
and field renderers. CSS animation time is set explicitly. Control scenes route
only saved responses through the production read-only display interface, using
a non-operational, film-only context marker; they do not contact a server or
represent live solver execution.

`dispatch-lab-demo-control-manifest.json` records both fixture hashes, archived
run identity, controller information identity, original/current source identities,
solver outcomes, rendering source hashes, browser version and each encoded
second's selected hour, forecast offset and robot poses. The comparison's input
packet and outputs are retained in `tools/demo-video/fixtures/control-view.json.gz`.
The video renderer never re-solves the comparison, so repeated captures use the
same results even if solver timing or the application later changes.

To explicitly prepare a **new** comparison fixture, first restore
`build/field-operations/0edb1cf9141204ab.json.gz`, then run:

```sh
uv run python -m tools.demo-video.prepare_controls
```

That command validates the full archive against the motion excerpt and performs
one bounded three-policy comparison. It replaces the compact fixture, records
its new implementation identity and retains solver termination. Review those
new outputs before rebuilding the film. It is not necessary for ordinary video
reproduction. Use a new storyboard output name to preserve an earlier rendered
edition of the current film.

## What the film establishes

This is an interface and recorded-mechanics demonstration, not a policy
qualification, a profitability claim or evidence of real robot capability.

- The motion excerpt is `tests/fixtures/field-motion.json.gz`, from archived run
  `0edb1cf9141204ab`. Its original values and identities remain unchanged.
- Weather, equipment, service and price assumptions are illustrative. Selected
  scenes jump between hours; the film is not one continuous real-time run.
- Readouts show completed hourly boundaries. Schematic sprite motion illustrates
  recorded work during the following interval, with no added navigation,
  sensing or repair physics. Repair cuts to H19 after travel, when the completed
  readout already reflects electrical isolation.
- The rover inspects the model's module-trip contact. A human performs the
  repair. Neither repair completion nor a planned probe establishes recovery.
- The saved comparison uses the original estimate, forecast, capacity and
  dispatch prices. Recorded service loads/isolation remain fixed. No future
  realised weather, post-decision observation or simulator fault truth enters
  the comparison packet. Greedy is a local-rule rollout; the two MPC curves are
  optimised forecasts. Solver termination remains visible. Ending inventories
  receive no speculative sale credit.
- All three comparison columns share the same starting battery and other
  inputs. More methane can come with higher decision costs and less remaining
  energy. This one illustrative case does not establish a general policy ranking.
- Current presentation code displays archived plans alongside a separately
  identified saved current-model comparison. No old validation is relabelled as
  evidence for the current application.

## Review

Review controller legibility, prediction labels, timeline selection, matched
comparison inputs, robot poses and repair isolation. `verify.py` checks the
saved operands, film ledger, streams, duration, audio absence and complete video
decoding. Its report is saved beside the movie. Preview frames and the manifest
remain available for visual review; neither constitutes numerical qualification
or a comprehension study. No large research queue is needed for this film.

The delivered edition passed those checks and local Chromium playback/seeking.
The two earlier editions also loaded with their original 41-second duration.
The existing control-view, field-scene and playback suites passed all 25 tests;
Python style checks and JavaScript syntax checks passed. The production app was
unchanged, so the full simulation and research suites were not rerun for this
presentation change.
