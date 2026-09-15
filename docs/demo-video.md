# Shareable plant demo

The 41-second, silent demo shows plant operation, battery planning,
solar cleaning, fault inspection, a human repair visit and three control policies.
It uses the original Departure Mono / amber plant and robot artwork. The only
added text is one short section heading at a time, in a light, rounded card with
Helvetica Neue / Arial typography. This editorial overlay is visibly separate
from the app. The artwork occupies the remaining screen; added titles, prose,
branding, progress indicators and comparison cards have been removed.

The delivery is `build/demo-video/dispatch-lab-demo-minimal.mp4`: 1920 × 1080, 30 fps,
H.264 with a YUV 4:2:0 pixel format and a front-loaded MP4 index. There is no audio
track. The first caption-heavy movie remains at `dispatch-lab-demo.mp4`. The local
preview page opens the minimal version; rendering does not publish it anywhere.

## Rebuild

Install the locked browser dependencies with `npm ci` and install Playwright's
Chromium. FFmpeg must be available on the path. From the repository root:

```sh
node tools/demo-video/render.cjs --preview
node tools/demo-video/render.cjs
```

The first command writes review frames. The second renders the complete movie.
Both run offline, without starting or changing the user's application, and fail
if the capture produces a browser error or attempts an HTTP request.

The editable storyboard is `tools/demo-video/storyboard.json`. Camera movements,
captions and typography live beside it in `film.js` and `film.css`; they are a
presentation layer, not changes to the application or simulation. Each frame
advances the production playback clock to its recorded hour. The existing plant
renderer supplies readouts and the existing field renderer supplies mission
poses. CSS animation time is set explicitly for deterministic capture.

`build/demo-video/dispatch-lab-demo-minimal-manifest.json` preserves the input fixture hash, archived run
identity, rendering source hashes, storyboard, browser version and a selection
ledger for each encoded second. `encoder.log` and `capture.log` record encoding
and capture diagnostics. Re-rendering intentionally replaces these delivery
files for the configured storyboard output name. A different output name
preserves the previous movie, poster and manifest.

## What the film establishes

This is a demonstration of the interface and recorded mechanics. Its fixture is
the renderer-only excerpt in `tests/fixtures/field-motion.json.gz`, from archived
run `0edb1cf9141204ab`. It is not a new experiment, a current-model qualification
or evidence of real robot capability. Original record values and source
identities remain unchanged.

- Weather and service assumptions are illustrative. The opening and closing
  headings identify the plant as a simulation.
- Scenes select different moments; cleaning returns to an earlier part of the
  same run. Exact hours and policies are retained in the manifest selection
  ledger. They are not added as persistent on-screen captions.
- Readouts show the completed hourly boundary. Schematic sprite motion depicts
  work during the following interval. It adds no navigation, sensing or repair
  physics. The repair scene cuts from travel to H19, where the completed readout
  already reflects isolation, avoiding a working technician beside a previous
  interval's running load.
- The rover reads the model's module-trip contact. A human performs the repair.
  The film does not claim that repair completion proves operating recovery.
- The policy section switches the original plant scene between Greedy, methane
  MPC and economic MPC at the same H18 boundary. Its single heading identifies
  the selected policy. Readouts remain the app's own recorded values. These
  selected views do not establish a ranking or a profitability claim.
- Rebuilding uses the current rendering source with the archived numerical
  trace. It does not relabel old results as evidence for a new physical model.

## Review

Inspect the preview frames, the encoded movie and the selection ledger. Check
robot departure and work poses, capacity-estimate timing, repair isolation,
pending verification, heading legibility and all three H18 policy views.
Decode the final video with FFmpeg and inspect its streams with FFprobe. The
existing `tests/field-scene.test.cjs` and `tests/playback.test.cjs` checks exercise
the production motion and playback functions used here. No numerical rerun or
large research queue is needed for this presentation-only artifact.
