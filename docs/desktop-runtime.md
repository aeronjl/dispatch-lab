# P3.1 · Desktop runtime candidate

Status: implementation candidate, with local Apple Silicon checks. **The joint
Mac/Windows gate remains open.** No Windows build or Windows 11 webview check has
been observed yet. The native CI workflow is supplied but has not been pushed or
run. This is an unsigned development app, not a public installable release.

## Architecture

The Tauri shell presents the existing Gradio application in the system webview.
It exposes no general native JavaScript commands. The scientific engine, SVG art,
Departure Mono, quiet simulation and browser/developer entry remain unchanged.
First desktop launch uses the existing recorded browser teaching fixture, retaining
its original provenance, instead of calculating a full default run before opening
Site selection. A new experiment still executes the installed model.

A private standalone CPython 3.12.13 interpreter contains dependencies installed
from `uv.lock`. It is an ordinary interpreter, so captured-source study/training
workers can still execute their original allowlisted modules. Worker entry points
are enumerated; the desktop executable is never treated as `python -m`.

| Candidate | Assessment |
|---|---|
| Private relocatable Python | Built and exercised on Mac, including numerical/geospatial imports, isolated simulation, preview, captured-source training fixture and numerical replay. Selected development approach for both platforms, conditional on Windows checks. |
| PyInstaller directory bundle | Architecture review only; not built or benchmarked. Its frozen executable cannot directly satisfy the existing captured-source `-m` worker contract. Shipping an additional ordinary interpreter would remove much of its benefit here. No comparative size or speed claim is made. |

The current locked NumPy, SciPy, pyproj and rasterio Mac wheels declare **macOS 14
arm64**. The package minimum is therefore 14.0, not Tauri's lower theoretical
minimum. Local execution is on macOS 26.5.2 arm64; macOS 14 itself remains untested.
Windows target remains Windows 11 x64. The workflow's Windows Server 2025 build
host does not qualify Windows 11 interaction. Windows WebView2 presently uses its
download bootstrapper; offline-first installation is still a P3.5 requirement.

## Resources and storage

- Application resources: private Python, native libraries, source, fonts and font
  licence, map renderer and licence, documentation and saved teaching fixtures.
  Source manifests carry original file hashes and revision metadata without Git.
- Desktop workspace: macOS `~/Library/Application Support/org.dispatchlab.desktop/workspace`;
  Windows `%LOCALAPPDATA%/org.dispatchlab.desktop/workspace`.
- Runtime logs: adjacent `logs/`; Gradio temporary files are under workspace
  `cache/gradio`. No automatic evidence cleanup or repository import is introduced.
- Existing per-store environment overrides and developer `runs/` defaults remain
  supported. Bootstrap occurs before stores and provenance are imported.

Immutable source, dependency lock and runtime identities remain distinct. The
runtime inventory includes dependency versions, wheel declarations and supplied
licence metadata. It is not a completed publisher licence audit. Python dependency
licence files remain in their original distributions; Rust dependencies are locked
in `Cargo.lock`. Signing and redistribution review belong to P3.6.

Opening an individual gzip/ZIP recording validates its bounded contents and never
extracts or executes archive code. Multi-case project imports remain in the existing
project workflow; this native picker is not the P3.2 migration facility.

## Ownership, authentication and limits

Leases use POSIX inherited open-file locks or Windows exclusive inherited file
handles. Parent exit must not release a child's lease. Only requested handles are
inherited. Site worker liveness follows the lease and recorded job identity, not
whether a possibly reused PID exists. Session commands and project writes retain
serialized ownership. The native test cases must run on each OS to qualify this.

Worker CPU budgets use OS mechanisms (POSIX resource limits or Windows Job Objects).
A worker-owned watchdog enforces elapsed time and sampled peak-memory limits even
if its UI parent disappears. Windows additionally caps process commit memory;
POSIX's sampled peak RSS is not an equivalent hard address-space guarantee. Existing
interactive and heavy-worker limits remain separate. More complete crash/sleep/
restart behaviour and checkpoint-aware background work remain P3.3.

Each backend chooses a loopback port and has a fresh private owner credential.
The shell verifies a credential-derived instance proof after Gradio startup before
opening a one-use session link. Cookies are HttpOnly and instance-specific. Every
request checks Host and Origin. Gradio's internal startup call receives owner
authentication through an exact-URL, launch-scoped adapter; it is never made public.
A compatibility test launches the real locked Gradio version to check this contract.

The existing agent endpoint still requires its independent narrow simulation
capability. It receives no desktop owner credential. `--mcp` launches the private
stdio bridge without a window or developer commands; missing grants confer no
implicit access. Credential-store integration and **Connect an agent** are P3.4.

External HTTPS links open in the normal browser. The shell supplies recording
selection and download dialogs, single-instance activation, readiness/error views
and native menus. Idle close stops its backend. Active close warns that this
candidate interrupts calculations and retains committed checkpoints; it does not
promise save-and-quit or background continuation. Original browser sessions remain
separate. Browser-held drafts are still origin-dependent until P3.2.

## Build and verify

Build-host tools are needed to build, not to run, the app. From the repository:

```sh
uv sync --locked
npm ci
uv run python desktop/build.py
uv run python desktop/verify.py
npm run desktop:build -- --bundles app   # Mac
npm run desktop:build -- --bundles nsis  # Windows, on a native Windows host
```

`desktop/rust-toolchain.toml` pins Rust. Tauri and its CLI are locked. The Python
preparation retains previous payloads under ignored `build/desktop/history/`.
`--source-only` refreshes source without reinstalling the unchanged private runtime.
Do a full preparation when dependencies/runtime inventory change.

Mac candidate: `desktop/src-tauri/target/release/bundle/macos/Dispatch Lab.app`.
Windows candidate: `desktop/src-tauri/target/release/bundle/nsis/`.
`desktop/verify.py --mcp-executable <installed-executable>` exercises actual SDK
initialization, tool discovery and rejection of an ungranted observation.

The relocation check copies the payload into a path containing spaces and `ü`,
removes developer programs from PATH, changes working directory and denies writes
to resources on POSIX. It executes Greedy and methane MPC, a saved-source learning
worker, a policy-preview worker, one committed control interval and a numerical
recorded-action replay. It then starts the actual Gradio server twice, verifies the
handshake and application configuration and shuts it down through its authenticated
route. Readiness timing excludes native rendering and is not a percentile benchmark.
Windows read-only directory attributes are not claimed as an ACL test.

Raw local receipts live under `build/desktop/`; they bind the source that actually
ran. Later builds must not inherit earlier receipts as their own validation.

## Local verification · 18 September 2026

- The initial full Python sweep reported **1,327 passes and one stale assumption
  review failure**. Weather-cache and provenance bindings were reviewed and updated
  without changing scientific assumptions. The full sweep is retained as a failed
  sweep, not retrospectively relabelled as passing.
- After the review correction and the final worker/close-status refinements,
  **87 focused Python checks passed**, covering actual Gradio startup, native
  process leases, shutdown, source execution, control continuation/replay, studies,
  training, project writes, assumptions, offline reports and MCP.
- **101 JavaScript checks** and **21 browser cases** passed. Three browser cases
  requiring separately supplied component/offline fixtures were skipped. The
  original plant and solar screenshot baselines were unchanged and passed.
- Locked dependency setup, Python lint/formatting, Rust formatting/compilation,
  catalogue/taxonomy/engineering documentation and explanation-freshness checks
  passed. These are software checks, not plant calibration or participant feedback.
- Native Mac review covered the site map, original plant, solar inspection and
  preview/reset, playback, return navigation, separate recording windows, native
  file selection, a downloaded recording ZIP reopened successfully, and idle
  closing with backend termination. A path-entry automation issue was resolved
  using the native enter key; no app change or security bypass was required.

The Mac development bundle is approximately **503 MiB**. One earlier relocated
payload run measured two backend startup samples of **13.36 s and 5.08 s**, while
other regression checks were active. These are readiness samples, not a clean
first-frame benchmark or p95. Latest source-bound runtime and MCP receipts are in
`build/desktop/relocation-report.json` and `build/desktop/mcp-report.json`.

## Remaining qualification

The next P3.1 gate is running the supplied workflow and the interactive checklist
on an actual Windows 11 x64 host, then addressing any failures. Minimum macOS,
clean-machine operation, external links, display scaling,
screen reader behaviour and a full native interaction pass also need qualification.
Automated Chromium checks are useful regression evidence but do not replace those
webview checks. Keep P3.1 open until both target platforms have passed or the user
explicitly revises its gate.

P3.2–P3.6 remain exactly as agreed in [the fixed plan](desktop-release.md): durable
projects; lifecycle/recovery; agent connection; updates/offline/preservation; signed
distribution and real end-user qualification. P2's participant review remains open.
