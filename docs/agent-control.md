# Practical agent operation · P1

Open **Simulation menu → Operate → Agent control**. A local operator and an explicitly
granted MCP agent share the same observation → preview → advance → receipt loop.
This operates a simulation, with six bounded hourly process requests. Repairs,
service scheduling and protected recovery tests remain with the reference executive.
No real plant connection or hardware authority is provided.

## Choose the starting information

- **This recording’s starting inputs** freezes the saved configuration, weather,
  policy and uncertainty. It starts at the original input boundary, not the current
  playback hour. New control recordings also offer their saved ending checkpoint.
- **Saved plant project** freezes a saved design revision, its site utilities and
  a compatible saved weather environment. An explicitly labelled synthetic example
  is also available. Unsaved design edits are not adopted.
- **Saved operating case / checkpoint** uses an immutable Sites case, including
  its original controller, utilities, weather and uncertainty. The owner chooses
  hour zero or a committed partition boundary. Displayed estimates are never
  promoted to physical starting state. Resource-only cases cannot operate a plant.

A new session authorises 1–72 simulated hours and 1–120 minutes of wall time, within
its frozen weather window. Two worker slots bound interactive sessions and numerical
replays together. A completed session can continue for another authorised window;
there is no automatic extension. Archived checkpoints require matching executable
source. Older recordings without portable runtime remain readable; select their
saved study when available, rather than inventing the missing state.

## Operate, interrupt and recover

1. Observe estimated inventories, the current forecast, declared equipment and
   supply limits, reference plan and constraint evidence. The illustration shows
   estimates and the last delivered process flows. Recorded playback retains full
   service animation and explicitly retrospective truth.
2. Preview the reference policy or request electrolyser power, battery charge,
   battery discharge, heating, heat rejection and methane production. All inputs
   are finite and nonnegative. Equipment-limit violations, incompatible battery
   requests and isolated loads are rejected. Shared resource shortages are visibly
   projected to feasible applied actions. Site water limits and finite water stocks
   constrain both prediction and execution. Recovery commitments require the
   reference proposal.
3. Supply a reason and advance one hour. Proposals bind the original information,
   decision revision and authority generation. Acceptance is idempotent for the same
   request/proposal; competing requests are rejected. After an uncertain response,
   observe the receipt before retrying with the same IDs.
4. The **Connection** view grants observe, preview or advance authority. Grants,
   revocation, pause and expiry remain visible. Closing the view does not stop a
   granted agent. Pause blocks new acceptance; already accepted work may finish.
5. Every successful hour atomically commits its private execution checkpoint,
   sealed recording and public receipts together. The checkpoint includes storage,
   thermal state, faults, diagnostic history, service commitments, lifecycle state
   and accounting history. A loose command file is not evidence of a completed hour.
6. **Recover checkpoint** restarts an interrupted, expired or stopped session from
   that committed boundary. Accepted but uncommitted commands are retained separately
   and require a fresh preview. **Continue session** extends a completed session
   within the saved weather window. Both renew the wall budget, invalidate old
   proposals and revoke agent access. The owner must generate a new connection.

Inherited operating-system leases prevent duplicate workers, including after loss
of the app’s process registry. A surviving worker remains observable; a dead worker
can be recovered. Frozen input hashes and source bindings are checked before restart.
The owner capability is retained by this browser. Losing both browser storage and
that capability does not grant access to another session. Private session files live
in `runs/control-sessions/`; they are not an off-machine backup.

## Recorded-request replay and preservation

**Replay recorded requests** takes a snapshot of the completed prefix and starts an
isolated worker. It re-executes the original six process requests from the original
starting checkpoint and frozen inputs. It never calls an external agent to reason
again, and never substitutes fresh reference-policy process requests. Services still
run their configured executive; time-limited planning can produce differences.

Progress and cancellation are visible. A replay is a new immutable edition and can
be opened in ordinary playback. Its comparison records source/environment identities,
changed observation/estimate/forecast fields, requested versus applied outcomes,
physical-state differences, methane difference and incomplete execution. Original
proposal predictions are explicitly labelled as saved predictions, not recomputed
forecasts. The source session and completed recording remain unchanged.

Owner exports include the frozen replay inputs and private starting/ending runtime.
These are never MCP observations. `recompute.py` uses the same recorded-request replay
adapter for new control archives; older archives without the required inputs remain
explicitly unsupported for numerical replay. Recorded playback works offline for
both. Source bundles retain the matching implementation and dependency lock.

The independent control-period checker recalculates process energy, gas, thermal and
water balances, action limits, chronological coverage, disclosed supplies and forecast
availability. It treats starting runtime, actual capacity and service power as recorded
boundary conditions. It does not independently reconstruct a mid-history service
mission, observer or lifecycle state, or establish empirical plant validity. Those
mechanisms retain their separate tests; a replay comparison exposes differences
without turning them into an overall trust score.

## MCP contract

`dispatch-control/2` retains the existing tool/action scope:

| Tool | Effect |
|---|---|
| `observe` | Permitted observations, estimates, supply constraints, plan and receipts |
| `preview_reference(revision)` | Preview the configured reference policy |
| `preview_actions(revision, actions)` | Predict one interval with six explicit requests |
| `advance(revision, proposal_id, request_id, reason)` | Accept one simulated interval |
| `trace` | Completed command receipts and observed outcomes |

Run `uv run python -m methane.mcp_server` with `DISPATCH_CONTROL_URL`,
`DISPATCH_CONTROL_SESSION` and `DISPATCH_AGENT_TOKEN`. The UI supplies the configuration.
The bridge uses the locked official Python MCP SDK, loopback HTTP only, no environment
proxies and no redirects. It cannot select projects, browse archives, read private
checkpoints, recover/extend sessions, replay retrospectively or grant itself authority.
Replay comparisons are owner-only because they contain retrospective physical deltas.

Tokens are stored as hashes and never enter archives. Reasons are escaped untrusted
text; attribution identifies a capability, not cryptographic proof of a person/model
or access to private reasoning. This is a local single-user capability system, not a
multi-tenant service or safety-certified control system. Never expose it publicly.

## Completion boundary

P1 makes configured projects and persisted simulation state available through the
existing bounded MCP interface. It does not add service-control tools, arbitrary
uncommitted-hour forks, live hardware control, new learned policies or new plant
models. P2 consolidates expert navigation and uses real participant feedback; P3
qualifies fresh installation and off-machine restoration. See [the finite roadmap](roadmap.md).
