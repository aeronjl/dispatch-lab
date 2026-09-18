# P3 · Installable Dispatch Lab for Mac and Windows

Status: P3.1 implementation candidate; local Mac verification, joint platform gate
still open. P3.2–P3.6 are not started. See [runtime delivery](desktop-runtime.md).
Agreed on 18 September 2026.
The user chose Mac and Windows together. This replaces P3's source-install-only
interpretation with an end-user desktop release; P1 remains complete and P2's real
participant walkthrough remains open. Deliver one increment at a time and report
these same IDs, completed gates and remaining work after each increment.

## Product outcome and scope

A user installs Dispatch Lab, opens or creates a project, runs an experiment,
inspects its decisions, connects an agent when desired, and preserves the work.
They need no terminal, Python, Git, Node, Rust or Docker installation. Existing
physics, constraints, evidence boundaries, quiet presentation, Departure Mono and
reviewed illustrations remain intact. This continues to operate simulated plants.

First-release build targets are Apple Silicon macOS and Windows 11 x64. These
architectures are planning defaults, not an assertion that all Mac/Windows devices
are supported. P3.1 records the minimum OS versions and checks native dependencies
and webviews on both targets. Intel Mac, native Windows ARM, Linux installers, a
hosted multi-user service and a container distribution are outside this release.
The existing developer/browser launch remains supported. Share the engine and
storage interfaces so a later container does not require a separate product.

No research comparison matrix is added to the release gate. Use named mechanism
checks, short workflow fixtures and existing long-duration fixtures. Changes to
the runtime or worker layer require relevant numerical regression checks, not a
claim that policies have become better or models more realistic.

## Existing foundations and observed gaps

The project already has versioned inputs/results, content-addressed Sites records,
atomic control commits, checkpoints, worker leases, a stdio MCP bridge, offline
reports, source capsules and scoped agent capabilities. Reuse these contracts.

Inspection for this plan found:

- Data paths mix repository-relative `runs/`, working-directory paths and specific
  environment overrides (`weather.py`, `evidence.py`, `siting/store.py`,
  `control_sessions.py`). Installed application files must become read-only assets.
- Project edits, run forms, investigation drafts and study notes use browser
  `localStorage`. That is not a durable project store and can change with origin.
- Workers launch with `sys.executable -m ...`; some execute a captured source tree
  through `PYTHONPATH`. A frozen executable cannot be treated as ordinary Python.
- `fcntl`, inherited `pass_fds`, process signals and Unix resource limits appear
  in study, project, learning and control code. Windows needs tested equivalents.
- Owner access currently depends on a browser-held capability. Installed-app owner
  access and restored work need an explicit local ownership model.
- Provenance captures source bytes and queries Git. The distributed release needs
  an immutable manifest and retained source capsule without requiring Git.
- CI currently exercises Linux/browser workflows, not installed Mac and Windows
  applications. Those are new verification targets, not existing qualifications.

## Architecture decisions

Use a thin desktop shell around the existing interface and Python engine. Tauri 2
is the leading candidate, subject to the P3.1 compatibility gate. It must preserve
the Gradio transport, SVG animation, maps, keyboard interaction, file downloads and
accessibility. Do not rewrite the scientific engine or replace the UI framework.

Package the Python interpreter/dependencies and all static resources. Compare a
PyInstaller directory bundle with a private, relocatable Python runtime in P3.1.
Select one approach for both platforms after exercising frozen-source execution,
SciPy/HiGHS and geospatial libraries. Keep backend execution behind explicit
launch commands for the service, worker types, replay and MCP bridge; never infer
that the desktop executable supports arbitrary `python -m` arguments.

Separate four storage domains: immutable application/runtime resources; durable
user workspace; bounded disposable caches/logs; and OS-protected credentials.
Local-only backend endpoints use an owned-instance handshake, scoped credentials
and request-origin checks. A port number or localhost address alone is not identity.
Expose no arbitrary shell/filesystem bridge to web content. External references
open in the ordinary browser without desktop privileges.

Keep application version, model/source identity, dependency/runtime identity,
workspace schema version and MCP protocol version distinct. An OS-specific build
is recorded as such; matching inputs do not promise bitwise-identical time-limited
solver outcomes across machines.

## Fixed delivery increments

| ID | Deliverable | Completion gate |
|---|---|---|
| P3.1 | Cross-platform runtime and desktop shell | Installed development packages launch UI, numerical workers and MCP executable on both targets without developer tools; native/worker risks resolved or explicitly brought back for a scope decision |
| P3.2 | Durable projects and working context | Edits, notes, settings and saved evidence survive browser-storage loss, application restart and reinstall; legacy import is verified and nondestructive |
| P3.3 | Experiment lifecycle and recovery | Closing, background work, quitting, interruption, sleep and restart have tested meanings; duplicate execution and false completion are prevented |
| P3.4 | Connect an agent | A compatible local MCP client connects through the packaged bridge, receives only granted authority, and can be tested/revoked through the app on both targets |
| P3.5 | Updates, offline work, diagnostics and preservation | Signed update/recovery paths preserve version identity; project backup and cross-platform restore work offline with missing-data/compatibility boundaries explicit |
| P3.6 | Distribution and end-user qualification | Signed installers pass clean-machine workflows on Mac and Windows; real participant review and an actual agreed off-machine restore are recorded |

Both platforms are part of every applicable gate. An unsigned development package
is useful progress in P3.1, not completion of public distribution. A skipped
Windows test does not count as a Mac-and-Windows pass.

### P3.1 · Runtime and shell

Introduce explicit runtime-resource, user-data, cache and temporary paths; preserve
existing command-line/environment overrides for developer/test workflows. Bootstrap
them before imports capture source or construct stores. Bundle fonts, map assets,
documentation, teaching fixtures, source metadata, licences and native libraries.

Provide a cross-platform process/lease layer before broad desktop UI work. Preserve
one-writer ownership and atomic commits across workers, application restarts and
competing app instances. Use real OS locking/ownership, not PID existence alone or
unreliable expiry timestamps. Enforce bounded CPU/wall/memory limits through supported
platform mechanisms and disclose any differing measurement semantics. Test lock
handoff, parent death, child death, PID reuse, cancellation and slot release.

The shell handles readiness, a loading/error view, port collision, single-instance
activation, native file dialogs and opening a supported project/export. Logs must
not leak into the MCP stdout stream. Its backend cannot write into the installation.
Use authenticated discovery so another local listener cannot impersonate the app.

Gate: build on each target; run without system Python/Git; load the plant/solar
views and maps; execute a short simulation, preview, learning worker and source-bound
replay; exercise MCP startup, paths containing spaces/non-ASCII characters, changed
working directory, read-only app resources and backend failure. Record package size,
cold/warm startup time and native dependencies before choosing the final bundler.

### P3.2 · Durable projects and drafts

Use the OS application-data location by default, with a user-visible workspace
location and supported move/import operation. Preserve current append-only numerical
records and reports. Add a transactional index for mutable project heads, drafts,
run forms and navigation context; published editions remain immutable. Use revision
checks to prevent one window from silently overwriting another's newer edits.

Autosave changed design inputs, investigations and report notes with a clear
Saved / Saving / Could not save state within the relevant editor. Invalid unfinished
inputs can be retained as drafts but cannot be dispatched as valid configurations.
Changing storage origin or clearing a webview must not erase acknowledged saves.
Restore project, component, controller, hour and workspace where applicable; never
resume simulation advancement just because the window reopened.

Import the current repository's `runs/` through an inventory and copy/verify step.
Do not delete or reinterpret the original files. Browser drafts require an explicit
export from the existing browser app because a new desktop webview cannot read
another browser's storage. Retain the existing view for that handover. Migration is
idempotent, preserves identities and reports skipped/missing/corrupt records.

Project Home contains recent projects, Open/Import, New project and recoverable
work. It appears at entry or on request, not as more chrome over the simulation.
Workspace settings reveal storage size, backup status and cache management; evidence
and source snapshots are never silently evicted as cache. Uninstall preserves user
data unless the user separately chooses removal.

Gate: restart/reinstall, clear webview storage, conflict two editors, interrupt an
autosave, exhaust disk space, migrate twice, reopen older archives, and verify both
mutable drafts and immutable evidence. Saved status means a durable acknowledged
write, not an optimistic browser message.

### P3.3 · Running, closing and recovering

Use one visible job model across simulation, study, learning, download and export
work. Each adapter declares progress, cancellation boundary, checkpoint support,
runtime limits and recovery compatibility. Do not imply every task can resume at an
arbitrary interval. Preserve completed partitions; retain failed/incomplete cases.

Closing a window while work is active offers Continue in background or Save and
quit, with a rememberable preference. Background operation keeps a visible menu-bar
or tray presence and a way to reopen/pause/quit. Explicit Quit blocks new work,
checkpoints at the next valid boundary, and reports what may be rerun if the user
forces termination. Idle quit leaves no orphan process. No automatic login startup.

On abnormal termination or reboot, discover committed work and offer recovery from
the actual last committed boundary. Already accepted but uncommitted requests remain
distinct from completed actions. Never repeat an agent action merely because its
response was lost. Workers remain bound to the runtime with which they started.

Sleep is not productive runtime: report suspension/interruption honestly and keep
wall-time grant expiry effective after wake. Do not silently renew agent permissions.
Offer keeping the machine awake only as an explicit experiment option if supported.
Resuming/recovering agent sessions requires renewed authority as in P1. Closing an
inspection view alone retains P1's existing semantics and does not revoke a grant.

Gate: window close/reopen, deliberate quit, app crash, worker crash, OS restart,
sleep/wake, full disk during commit, cancellation races, concurrent launches and
lost response retries. Verify conservation/receipt integrity and original runtime
binding, not just whether a progress indicator reappears.

### P3.4 · Connect an agent

Keep the entry under Operate → Agent control → Connect an agent. The flow selects
a saved simulation/session, shows its starting information, sets hour/wall budgets,
and grants Observe, Preview or Advance. Default to Observe. Describe Advance as
changing that simulation, with service execution still owned by the reference
executive. This release does not broaden the five-tool/six-action control contract.

Ship a stable local stdio bridge with the app. Generated connection configuration
uses its installed path and an opaque connection identity, without requiring `uv`
or placing raw grant tokens into copied configuration. Store credentials in the
OS credential store with user-only local descriptors; retain hashed authorization
records. Logs, diagnostics, project exports and ordinary backups exclude credentials.
Make local owner recovery independent of fragile browser storage, but do not give
agents an owner credential or a way to grant themselves access.

Provide Copy connection settings and guided setup for a tested local MCP client.
Only offer automated client installation when its documented interface supports it
and the user elects that action. Do not silently rewrite client configuration. The
baseline is standard stdio; specific client support is named only after its actual
round trip passes on both platforms.

Test connection performs an observation-only handshake. Distinguish Configured,
Waiting for client, Connected, Paused, Expired and Revoked using actual contact
evidence, not copied settings. Reveal permissions, remaining budget, last request,
receipts and a Revoke control. Private runtime state stays outside MCP observations.
Reconnecting to a relaunched backend validates connection/session/runtime identity;
it never silently changes projects, grants or authority generations.

Gate: connect an actual client; observe/preview/advance within grants; reject wrong
scope/session/stale proposals; test expiry, revocation, relocation/update, app crash,
lost replies and reconnect. Check that read-only handshake advances no time and no
secret enters clipboard configuration, logs, diagnostic bundles or shared reports.

### P3.5 · Updates, offline operation and preservation

Offer user-controlled update checks and signed installable updates. Downloading an
update does not replace the runtime under an active worker. Before applying, show
active work, quiesce safely, take a consistent workspace snapshot and record schema
compatibility. Interrupted install/migration must retain the previous usable state.
Reject corrupt/unsigned update metadata or payloads. Keep the previous approved
runtime for rollback; rollback restores a compatible snapshot or fails clearly,
rather than opening a newer incompatible store with old code.

Preserve immutable model/source capsules and runtime manifests without requiring
Git. Older archives remain readable. Exact continuation/recomputation requires a
matching trusted installed runtime; report incompatibility when it is unavailable.
Running with the current model creates a new edition with differences. Never execute
arbitrary code from an imported archive automatically or disguise a substituted
implementation as original. Runtime cleanup must disclose affected resumable work.

Offline operation supports bundled learning examples, cached-data calculations,
recorded playback, documentation, agent control with a local client and reports.
External agents may themselves require a network. First install must carry or provide
an offline installer for required runtime/webview components. New weather, maps or
site evidence remain explicit network dependencies. A missing tile/data hour is not
replaced by synthetic information; expose cached coverage and missing resources.

Add workspace backup and project export with different scopes. A full backup covers
durable drafts, indexes, complete referenced evidence, raw data, checkpoints and
required manifests. A shareable project/report export lets the owner review inclusion
of private runtime/retrospective state and excludes credentials. Generate consistent
snapshots at committed boundaries, with checksums, sizes and an inventory. Show which
uncommitted work is excluded. Use existing content identities to avoid duplicate data.

Offer manual backup and optional local scheduled backups while the app is running,
with chosen destination/retention and visible last verified result. Never overwrite
the last good backup on failure. A same-disk snapshot is labelled local recovery,
not off-machine protection; a successful write is separate from a tested restoration.
Do not require cloud accounts or implement multi-writer folder synchronisation.

Restore validates archive paths, integrity, schema/source support and size limits
before activation. Restore into a new workspace by default; preserve the existing
one, detect duplicates and report missing artifacts. Restored agent sessions have
no active credentials/grants: the new local owner must explicitly recover and grant.
Historical numerical continuation may remain platform/runtime-specific even when
project interchange and playback work across Mac and Windows.

Diagnostics provide a readable failure, relevant action and exportable technical
details. Redact tokens, personal paths and sensitive inputs by default, with a
preview before export. No automatic sending, telemetry or remote support access.

Gate: offline cold launch and core workflow; missing weather; update while jobs
run; tampered package; interrupted migration; rollback; verified backup during work;
corrupt/partial archive; Mac-to-Windows and Windows-to-Mac project restore; lost
credentials; and diagnostic redaction. Cross-platform numerical repeats report
differences honestly. No exact-solver-identity claim follows from containerisation
or packaging alone.

### P3.6 · Release qualification and handover

Build signed/notarized Mac distribution and signed Windows installer, with checksums,
release notes, dependency/licence inventory and a supported OS/architecture matrix.
Use native build/test hosts; preserve source-bound test results for each artifact.
Signatures for updates and OS publisher signing are separate credentials and checks.
Do not promise that Windows signing eliminates all reputation prompts.

On clean Mac and Windows installations with no development tools: install; create
a project; retrieve a real site/weather input; deliberately go offline; run a short
cached-data case; investigate; compare; write a report; connect an agent; interrupt
and recover; update; export; uninstall/reinstall without losing user data; restore.
Keep an explicitly synthetic offline-first fixture as a separate reproducible check.
Retest actual native webviews, file associations/dialogs, keyboard/screen-reader
paths, display scaling, reduced motion, maps and unchanged plant/solar appearance.
Browser tests alone do not qualify the desktop shell.

Retain existing interaction targets where applicable: p95 200 ms for simple
input-to-result and 10 ms rendering, including a representative active batch.
Measure desktop cold/warm start and recovery times, report hardware and percentiles,
and set reasonable startup budgets from P3.1 before final qualification. Long jobs
must retain progress/cancellation rather than meet an interactive calculation budget.

Conduct real participant walkthroughs on both platforms, recording misunderstandings
separately from automated results; incorporate P2's prepared six-task protocol so it
is not duplicated as another research programme. Resolve material confusion before
closing P2/P3. Perform an actual off-machine backup/restore at an agreed destination,
recording original/restored hashes, readable results, differences and any missing
runtime. Merely making a ZIP in another local folder does not satisfy this gate.

## External decisions and stopping points

Proceed with reversible implementation and unsigned development builds without
waiting for public release credentials. The following are explicit dependencies,
to resolve when concrete artifacts are ready:

- Access to native Mac/Windows build and clean test environments. Local Mac success
  does not establish Windows support; remote CI execution needs the user's existing
  authorised hosting setup or an agreed destination.
- Publisher identity and Apple/Windows signing/notarization credentials, separately
  protected update-signing keys, and a distribution/update endpoint. Do not purchase,
  publish, upload source or alter accounts as an assumed part of a local build.
- An off-machine backup destination and authorisation for the selected contents.
- Participants for the final walkthrough; do not invent their answers.

Review after P3.1 before expanding shell work. Return for guidance if native-library
support, source-bound worker execution or Windows lease semantics require changing
the product contract; if a supported OS cannot pass; or if signing/distribution
requires a materially different hosting/cost arrangement. Otherwise continue the
agreed increment and return with the fixed roadmap. Useful new modelling ideas and
additional deployment formats remain backlog, not new prerequisites.

## Technical references consulted for this plan

- [Tauri external binaries](https://v2.tauri.app/develop/sidecar/): bundled Python
  services and architecture-specific executable packaging.
- [PyInstaller runtime/process caveats](https://pyinstaller.org/en/stable/common-issues-and-pitfalls.html):
  embedded-interpreter subprocesses and multiprocessing need explicit handling.
- [macOS distribution signing](https://v2.tauri.app/distribute/sign/macos/) and
  [Windows distribution signing](https://v2.tauri.app/distribute/sign/windows/):
  platform release credentials and verification.
- [Tauri updater](https://v2.tauri.app/plugin/updater/): signed update artifacts and
  platform packaging. Our workspace/runtime migration policy remains application work.

These references establish packaging capabilities, not that our application already
works in them. The gates above require tests against actual built artifacts.
