# Shared control and MCP

Open **Simulation menu → Agent control**. Choose a reference policy and a bounded
session (1–72 simulated hours, 1–120 minutes of wall time; two active sessions per
app). The loaded recording supplies frozen plant, weather, sensor, policy and
uncertainty inputs. A **new simulation starts at hour zero** with the current
implementation. Nothing mutates the source recording. Continued histories and
site-utility-constrained recordings are explicitly unsupported in this increment.

## Operator workflow

1. Start the session and read the observation. The plant drawing shows the last
   decision's estimated inventories and temperature, together with last delivered
   process flows. It is not a view of private physical state. Services continue in
   the existing executive; their full animations are in recorded playback.
2. Preview the reference policy or enter the six explicit hourly process requests.
   Reference previews retain the configured horizon. Explicit requests have a
   one-hour feasibility prediction; the interface reports requested and predicted
   applied values separately. Changing inputs invalidates the preview.
3. Add a reason and advance one hour. Read the receipt before the next action.
   No agent command means no advance. There is no implicit timeout policy action.
4. The **Connection** view creates a session-specific capability with observe,
   preview or advance permission. It shows a ready-to-copy stdio MCP configuration.
   The **Trace** view records operator/agent attribution, reasons, requested and
   applied commands, solver status, forced trips and balance checks.
5. Pause blocks new actions; resume requires a fresh proposal. Revocation blocks
   that agent immediately at the API boundary. An already accepted interval may
   finish. Stop or expiry ends the bounded session and preserves completed work.
   Closing the workspace preserves session access in this browser and restores
   the original playhead, selected component and focus; it does not revoke access.
6. Open the completed or partial recording in ordinary playback, Control view,
   inspectors and archive/export workflows. This explicitly replaces the displayed
   recording. Its provenance identifies an external-control session and source run.

This is a local, single-user app capability system, not a multi-tenant deployment
or safety-certified access-control system. Do not expose the app publicly. A local
MCP bridge is not an OS sandbox for the client that launches it. Only grant a client
you intend to receive the declared plant, prices, observations and forecasts.

## Contract and implementation

`dispatch-control/1` in `methane/control_port.py` adapts the existing causal learning
data port. It includes a decision revision, UTC time, observations, estimate,
diagnostic state, declared plant and component models, frozen prices, forecast,
reference plan, constraint evidence, source identity and information hash. Forecast
PV[0] retains the existing contemporaneous hourly-mean abstraction; future forecast
values are predictions. Hidden execution parameters, fault schedules, scheduled
repair outcomes, future realised weather and retrospective truth are not exposed.

Actions are six finite nonnegative requests: electrolyser power, battery charge,
battery discharge, heating, heat rejection and methane mass for the hourly interval.
Unknown fields, incompatible simultaneous battery requests and declared equipment
limit violations are rejected. Shared resource constraints can project a request to
a smaller feasible action; that projection and unmet request remain explicit.
Probes and scheduled recovery tests accept the reference plan only. Service and
recovery commitments, physical diagnosis, shared power and physical balance checks
continue in `simulation.py` and the existing kernels.

The simulation worker waits immediately after constructing each decision. Both
operator and agent previews/commands use the same server and physical executor.
Each proposal binds the original information, authority generation and revision.
Advance atomically accepts at most one command per revision. Retrying the same
request/proposal returns its acceptance; conflicting or stale requests are rejected.
Do not change request IDs after an uncertain response: observe the receipt first.
Preview jobs have two execution slots and a 1,000-proposal session limit. The physical
executor retains its 0.5-second solver limit, incumbent validation and safe-off
fallback. These are bounded numerical mechanisms, not guarantees of field safety.

The private worker process has an independent wall deadline, so a lost browser or
MCP connection cannot leave a simulation running indefinitely. The app detects dead
workers and labels them interrupted. Sessions cannot resume across an application
restart; completed intervals remain readable with the owner capability. Changed
source under a running app is rejected when a worker starts. Restart to use it.

## MCP tools

The stdio bridge is `uv run python -m methane.mcp_server`, using the locked official
Python SDK. The interface follows the [official server documentation](https://modelcontextprotocol.io/docs/develop/build-server)
and [Python SDK](https://github.com/modelcontextprotocol/python-sdk).

| Tool | Effect |
|---|---|
| `observe` | Current permitted observation, authority, reference plan and receipts |
| `preview_reference(revision)` | Saved reference-policy proposal; no time advances |
| `preview_actions(revision, actions)` | One-interval predicted feasibility projection |
| `advance(revision, proposal_id, request_id, reason)` | One accepted simulated interval |
| `trace` | Completed command receipts and observed outcomes |

Environment: `DISPATCH_CONTROL_URL` (local HTTP app origin),
`DISPATCH_CONTROL_SESSION`, `DISPATCH_AGENT_TOKEN`. The bridge only connects to
loopback HTTP, disables environment proxies and refuses redirects. It cannot create
sessions, browse archives, change plant configuration, read arbitrary files or
change its own permission. The owner grant is distinct from the agent grant;
server metadata stores their hashes. Tokens never enter simulation archives.
Reasons are untrusted text, escaped in the UI. Attribution means the capability
used, not cryptographic proof of a particular model, human or reasoning process.

## Preservation and reproducibility

Private session data is saved in `runs/control-sessions/`. Each completed interval
creates an atomic current recording and a separate public receipt. Original public
decision information and action attribution are captured inside the normal run
archive. The recording is sealed with the worker's current source/environment and
the frozen source-run identity. Exported source capsules and model documentation
remain available. Existing archives and column meanings are unchanged.

Recorded playback and independent numerical balance checks work offline. Numerical
external-agent reruns are **not implemented**: standard rerun commands reject these
archives instead of silently substituting the reference policy. A future replay
adapter must specify whether it replays recorded requests or re-evaluates an agent,
preserve the external agent's model/configuration and report changed information.
The current trace records submitted reasons, not an external agent's private chain
of thought or unrecorded tool use.

## Verification and remaining scope

Automated coverage exercises the actual isolated worker, reference passthrough,
independent balance checks, valid and invalid explicit requests, information
separation, repeated/stale commands, permissions, revocation, pause, expiry and stop.
Protocol checks start the real stdio MCP server. Browser checks perform a real MCP
observe → preview → advance round trip and verify the result in the UI and recording;
they also cover keyboard return, narrow screens, input invalidation and escaped text.
Original plant and solar screenshot baselines are retained.

This increment was checked with 81 focused Python cases, all 95 JavaScript unit
tests and 23 distinct browser cases across the new control workspace, existing
Control view, investigations and platform. Lint, formatting, locked dependency
installation and documentation freshness passed. Two environment-gated browser
cases (new component lineage and extracted offline playback) were not enabled;
the Python bundle/offline-report checks were included. Reviewed captures are local
artifacts in `build/agent-control/`. No new throughput or field-performance claim
is made from these checks.

The workflow rehearsal caught and corrected an oversized cloned illustration
intercepting controls, a globally hidden footer, and an MCP response that lacked
structured output. The investigation keyboard check now waits for its asynchronous
draft validation to enable Save before testing the focus cycle. Review of the new
controller passage and the unchanged maintenance/learning narratives preceded the
documentation binding refresh; teaching examples were regenerated under this source.

This is an implementation rehearsal, not an expert-participant evaluation or evidence
that a language-model controller is beneficial. Autonomous service scheduling through
MCP, arbitrary checkpoint forks, utility-constrained site sessions, reconnectable
worker continuation, multi-step proposal execution and agent numerical replay remain
explicit extension boundaries. A real user walkthrough and a durable off-machine
storage/restore arrangement remain outstanding across the product roadmap.
