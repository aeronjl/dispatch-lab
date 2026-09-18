# Dispatch Lab · submission film

The submission edition is **2 minutes 48 seconds**, silent, 1920 × 1080 at 30 fps.
It uses short, full-screen title cards in off-white with plain sans-serif type.
Operating scenes retain the app's amber illustrations and Departure Mono; no
editorial captions cover the plant. Earlier short demo editions remain unchanged.

- Movie: `build/submission-video/dispatch-lab-submission.mp4`
- Local player: `build/submission-video/index.html`
- Source/scene ledger: `build/submission-video/manifest.json`
- Verification: `build/submission-video/verification.json`

## Editorial plan

| Time | Section | What the viewer can see |
| --- | --- | --- |
| 0:00–0:20 | Introduction, site and design | Actual app screens: European reference map, Seville selection, illustrated design and battery sizing. These design edits are separate from the following saved operating examples. |
| 0:20–0:46 | Store now. Produce later. | Operating plant; recorded battery plan; cursor moves from charging to later discharge while physical playback stays at the original decision. |
| 0:46–1:00 | Keep the plant working. | Cleaning robot travels to the solar array and works through its recorded mission. |
| 1:00–1:26 | Recognise. Inspect. Adapt. | Inspection rover, requested/applied electrical shortfall and bounded diagnostic evidence. |
| 1:26–1:40 | Coordinate service with production. | Human service arrival and work; the electrolyser is isolated during the shown repair. |
| 1:40–2:03 | Repair is not recovery. | Explicitly separate controlled example: estimated capacity remains derated after the remedy, then rises from 225 to 450 kW through observed confirmations. |
| 2:03–2:25 | Compare decisions fairly. | Three predicted process-policy alternatives share one starting information packet. Costs, output and remaining battery inventory remain visible. |
| 2:25–2:43 | Inspect the model. Trace the result. | Actual battery learning example, efficiency edit and recalculated output; explicit change to This run reveals original operands and source identity. |
| 2:43–2:48 | Build your own experiment. | Repository address and research-simulation boundary. |

The four judging criteria guide selection rather than appearing as marketing
claims in the film. Numerical/source inspection supports technical execution;
production, service and observation-based recovery expose the candidate
architectural contribution; human intervention and explicit assumptions preserve
feasibility boundaries; intermittent energy and faults address the brief.
No first-in-literature novelty, policy superiority or field readiness is claimed.

## Sources and honest cuts

Operating and robot scenes retain the earlier field-motion archive `0edb1cf9141204ab`.
The matched comparison retains its saved original-information packet and three
already calculated predictions. It holds service commitments fixed; it does not
re-optimise robot scheduling. Its source identity and solver termination remain
in the fixture and manifest.

The recovery scene retains release-1 archive `71fd13ba49689ad2`, using
`scheduled-load-tests/5`. A human module replacement precedes the load tests.
The original service deadline miss remains recorded; the later recovery must not
be interpreted as all requirements having passed. Its weather is a controlled
fixture, not a field measurement or a Seville production forecast.

The film cuts between these examples and between recorded hours. Sprite motion
illustrates saved missions, not a navigation or repair-kinematics simulation.
The inspection rover does not perform the human replacement. Recorded actuator
outcomes, sensor observations and estimates retain their own meanings.

Site, Build and Model screenshots come from real application interactions in a
separate local workspace. No live project or existing run is changed. The sizing
edits are not represented as having produced either operating archive. Model
learning edits stay separate from the original result shown in This run.

## Rebuild

Requires the locked Python dependencies, `npm ci`, Playwright Chromium and FFmpeg.
From the repository root:

```sh
node tools/submission-video/capture.cjs
node tools/submission-video/render.cjs --preview
uv run python -m tools.submission-video.verify --preview
node tools/submission-video/render.cjs
uv run python -m tools.submission-video.verify
```

Actual-app screen capture requires the preserved release-1 archive at
`build/release-1/release-example/offline/recorded-run.json.gz`. A fresh clone does
not include that large archive or the generated screen captures; restore those
artifacts to reproduce the exact edition. The compact motion/control fixtures
are committed. `prepare.py` is an explicit extraction tool for that archive,
not an automatic rerun of the experiment:

```sh
uv run python -m tools.submission-video.prepare
```

Ordinary video rendering needs only the saved captures, their manifest and the
committed fixtures. It performs no numerical solve and blocks HTTP requests.
Each encoded second records its scene, playhead, forecast cursor and sprite poses.
Frame capture drives the existing production playback and Control renderers;
film-only styles change framing and emphasis without editing application files.
The MP4, captures and detailed manifests remain local under ignored `build/`.

Verification checks input identities, identical-information policy comparison,
battery/production reconciliation, observed recovery progression, repair isolation,
scene timing, format, frame count, audio absence, fast-start and complete decoding.
Visual review checks title cards, model/context labels, key robot poses, controller
legibility and encoded-frame appearance. This is presentation verification, not a
new scientific study or participant comprehension test.

## Delivered edition

The 168-second MP4 passed the verification above, complete decoding, actual browser
playback and eleven seeks. Encoded title, repair, recovery and policy-comparison
frames were visually reviewed. The 25 targeted Control, field-operation and
playback JavaScript checks passed, along with the new tooling's lint, formatting
and syntax checks. No application code or visual baseline was changed; the full
physics/research suite was not repeated for this presentation-only increment.

`tools/submission-video/delivery.json` preserves the movie hash, verification scope
and browser review. The film is approximately 23 MiB. Nothing has been uploaded
or published. The prior short social editions remain in `build/demo-video/`.
