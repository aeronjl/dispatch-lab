# Investigate the release example

Open the local `build/release-1/release-example/offline/playback.html`, or load its
saved archive in the app. The offline example uses saved outputs; live learning
requires the restored application. No editing here changes the completed run.

1. Select MPC · methane and step to boundary 15. Simulator truth says capacity
   has been restored. The controller still has to observe successful tracking;
   the service receipt alone does not justify restoring its estimate.
2. Open Services, then **Trace this service decision**. Follow the recorded
   policy, original state estimate and separate recovery obligation/test appointment.
   The end-of-interval state is not the state used to make that decision.
3. Continue through boundaries 15–25. Five 45 kW increases take the estimate
   from 225 to 450 kW, with two informative intervals at each level. Confirmation
   occurs at boundary 25; the outer post-mission boundary remains 39.
4. Enter Model → Recovery. Switch explicitly to the independent learning example.
   Compare a successful remedy, failed remedy and power shortage. Notice the
   distinction between simulated restoration, observed confirmation and escalation.
5. Enter Inspection and move the clock before/after measurement availability.
   Missing evidence does not mean a healthy component or a zero reading. The
   fixture's retrospective truth is labelled separately.
6. Enter Service costs. Reprice the fixed teaching quantities and compare allocated
   cost, decision economics and expenditure. They are separate views, not three
   totals to add. Return/Escape restores the originating simulation context.
7. In the release report, select an unresolved seasonal case. Inspect its original
   decisions, solver status and terminal resources. A case can pass numerical
   conservation checks while failing to recover or losing production.

This example produces 290.91 kg of methane, exhausting the available CO₂ under
the illustrative chemistry. It is an example of human module substitution and
observed verification, not a demonstration of autonomous robotic replacement.
The original-source numerical recomputation matches all 36 intervals in this
execution. Time-limited optimisation is not guaranteed to reproduce bit for bit
on another runtime or solve.

The comprehension record is an agent-led engineering walkthrough. Actual operator
and participant comprehension studies remain in Release 3.
