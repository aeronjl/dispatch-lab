# Watching a control decision

Open **Simulation menu → Control view**, or **Watch this decision** in a component inspector. The default simulation stays quiet. Closing the view restores the originating menu or component inspector; the playback position and controller remain where the reader left them. The original plant and solar artwork is unchanged.

Select equipment in the diagram or the component selector. The revealed layer has four views:

- **Plan** shows the recorded forecast horizon, the selected component's predicted state or load, and a shared schedule for solar, battery charge/discharge, electrolysis and methane. A dashed previous plan is aligned to the same absolute intervals and timestamps. Missing older points remain absent. The highlighted column is a prediction selection; it never moves the completed run's playhead. Starting inventories, planned deficits, downstream requirements and active limits come from recorded evidence.
- **Delivery** distinguishes the interval's requested and applied actions. Applied actions are execution records, not independent sensor measurements. At playback boundary zero the diagram still shows the initial plant; the view explicitly labels its first recorded interval.
- **Evidence** shows the observations available before the decision, diagnostic state after the interval, load probes, recovery-test status, recorded events, forecast provenance and solver termination. A bound does not establish causal importance, and a requested recovery test does not establish successful repair.
- **Compare** runs Greedy, methane MPC and economic MPC from one recorded starting estimate, forecast, capacity and frozen dispatch prices. All outputs are labelled new, current-model predictions. Ending inventories have no speculative sale credit. A configured methane continuation allowance is identified separately.

The recorded-events selector moves the playhead to a decision and selects its affected component. Play, pause, step and speed continue to use the existing playback clock. Plant states update at completed hourly boundaries; existing robot motion illustrates recorded work between those boundaries. Keyboard and narrow-screen access remain available, and the reveal respects reduced-motion preferences.

## Comparison boundary

This is a comparison of **process dispatch objectives**, with recorded service power, isolation, component availability and deliveries held fixed. It does not optimise three new robot schedules or simulate future sensor observations, repairs or weather errors. Greedy's future curve is a rollout of its local rule on that forecast; it is not a horizon optimiser. Changing objectives is a fresh solve and need not reproduce a recorded time-limited incumbent.

Single-interval load probes retain their requested minimum load and dependable-capacity bound; the generic fallback is disabled for these probes because it would not retain that lower bound. Older probes without this contract are unavailable. Decisions containing a scheduled conditional recovery test retain their recorded visualisation but cannot use the plain three-policy fork: that dispatcher cannot preserve the test's conditional, multi-interval commitments. The interface identifies this boundary and directs the reader to recovery alternatives rather than silently dropping it.

Recorded source identities and current comparison identities are distinct. Missing original provenance is not reconstructed. Repriced report inputs are never accepted by this endpoint. Original runs and exports are not rewritten; comparison results are temporary predictions tied to this selection.

## Implementation and checks

`methane/control_view.py` adapts existing records and dispatch kernels without changing plant execution, optimisation objectives or diagnostic logic. The worker receives only a minimal original-information packet. All three policies receive independent copies of identical forecast operands and the packet identity. This keeps later realised weather, injected fault truth and post-decision observations outside the comparison.

`/dispatch/control-view` uses the existing server-owned run capability, plus run, controller, decision and request generation. Isolated workers have the run's per-solve limit, a separate wall deadline, cancellation before or after a job ID is returned, bounded concurrency and cleanup. Late requests cannot cross selections; cancellation tombstones prevent out-of-order starts from reviving a cancelled generation. Solver time limits, fallbacks, unavailable and incomplete results remain visible.

Python checks cover aligned/missing plans, original information, frozen prices, probes, conditional-recovery rejection, real prediction reconciliation, worker ownership and cancellation. Browser checks cover the four views, event navigation, same-information comparisons, stale responses, cancellation, return focus, mobile layout and reduced motion. Original plant/solar screenshot references are not updated. Reviewed view captures are written to `build/control-view/` as local design artifacts, not empirical evidence about policy quality.

No claim is made that MPC must win or that these illustrative predictions establish field realism.
