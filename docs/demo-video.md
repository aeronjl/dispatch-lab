# Shareable plant demo

The 41-second, silent, captioned demo shows plant operation, battery planning,
solar cleaning, fault inspection, a human repair visit and three control policies.
It uses the original Departure Mono / amber plant and robot artwork.

The delivery is `build/demo-video/dispatch-lab-demo.mp4`: 1920 × 1080, 30 fps,
H.264 with a YUV 4:2:0 pixel format and a front-loaded MP4 index. There is no audio
track. The video is a local artifact; rendering it does not publish it anywhere.

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

`build/demo-video/manifest.json` preserves the input fixture hash, archived run
identity, rendering source hashes, storyboard, browser version and a selection
ledger for each encoded second. `encoder.log` and `capture.log` record encoding
and capture diagnostics. Re-rendering intentionally replaces these delivery
files; copy the folder to retain a previous edition.

## What the film establishes

This is a demonstration of the interface and recorded mechanics. Its fixture is
the renderer-only excerpt in `tests/fixtures/field-motion.json.gz`, from archived
run `0edb1cf9141204ab`. It is not a new experiment, a current-model qualification
or evidence of real robot capability. Original record values and source
identities remain unchanged.

- Weather and service assumptions are illustrative. The film labels itself as
  recorded simulation throughout.
- Scenes select different moments; the cleaning scene explicitly returns to an
  earlier part of the same run. The displayed hour and policy identify each view.
- Readouts show the completed hourly boundary. Schematic sprite motion depicts
  work during the following interval. It adds no navigation, sensing or repair
  physics. The repair scene cuts from travel to H19, where the completed readout
  already reflects isolation, avoiding a working technician beside a previous
  interval's running load.
- The rover reads the model's module-trip contact. A human performs the repair.
  The film does not claim that repair completion proves operating recovery.
- The three policy cards use the same H18 boundary and report methane produced
  alongside all ending energy/feedstock inventories. This is an illustrative
  comparison, not a policy ranking or a profitability claim.
- Rebuilding uses the current rendering source with the archived numerical
  trace. It does not relabel old results as evidence for a new physical model.

## Review

Inspect the preview frames, the encoded movie and the selection ledger. Check
robot departure and work poses, capacity-estimate timing, repair isolation,
pending verification, caption legibility and all three H18 comparison cards.
Decode the final video with FFmpeg and inspect its streams with FFprobe. The
existing `tests/field-scene.test.cjs` and `tests/playback.test.cjs` checks exercise
the production motion and playback functions used here. No numerical rerun or
large research queue is needed for this presentation-only artifact.
