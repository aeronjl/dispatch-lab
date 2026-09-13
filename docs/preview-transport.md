# Immutable playback transport

Live Gradio HTML receives its large playback and economics props as JSON strings.
The browser decodes them once per prop update. Numerical APIs, archives and
offline playback keep their structured format; the renderer accepts both forms.
No model calculation, plant artwork or label changed.

Chromium CPU/trace inspection identified Gradio's loading-state update walking
the full reactive playback props through Svelte snapshots and structured clones.
The immutable scalar avoids that repeated deep traversal. The local Python solar
preview for the 72-hour fixture took about 12 ms; it was not the dominant cold
browser cost. Profiling used an isolated Playwright CDP session because the
configured DevTools browser profile was already occupied.

Recorded local macOS/Chromium checks, 30 inputs each:

| Fixture | Preview p95 | Render p95 | First sample |
| --- | ---: | ---: | ---: |
| 72-hour demo, no batch | 126.0 ms | 1.1 ms | 170.7 ms |
| 240-hour fixture, active batch | 112.8 ms | 2.7 ms | 1,566.3 ms |

The existing p95 gates (200 ms interaction, 10 ms rendering) pass. A separate
cold trace after the change took 427.7 ms, followed by roughly 88–108 ms samples.
The long first active-batch sample is retained: the p95 result does **not** mean
every first interaction meets 200 ms. Further cold-start work should isolate
server/worker initialisation and first-request serialisation. This evidence is
local and fixture-specific, not a universal hardware performance guarantee.

Compact measurements live in `research/recovery-comparison/preview-*.json`.
Original plant and solar screenshot baselines passed unchanged, together with
keyboard, narrow-screen, playback/cost, lazy-inspection and uncertainty controls.
