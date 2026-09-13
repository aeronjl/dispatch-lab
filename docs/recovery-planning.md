# Scheduling an operating test

`scheduled-load-tests/1` is an optional recovery policy available in experiment setup beside the diagnostic assumptions. It applies to the production controllers in that experiment. Existing setups and archives keep opportunistic probes unless the new policy is explicitly selected. `dispatch-lab/policy/2` freezes the settings in every relevant decision and the run's provenance.

The objective is to complete the next upward test increment at the earliest feasible time. This is an explicit recovery priority, not an inferred monetary value of information. Within a candidate window the production objective retains its usual methane or economic criterion and the declared expected/worst-case mixture. Greedy uses a methane MPC subplanner during a scheduled-test episode; comparisons must describe that package change.

## Requests and delivered power

The controller requests a load above its current capacity estimate. `service-outcome-tree-mpc/2` separates that command from possible delivered power. The two hypotheses are tracking the test request and delivering only the unchanged estimated capacity. Each branch has a complete electrical, gas and thermal trajectory. The same requested plant actions apply to both branches throughout the horizon; the planner receives no future observation or injected fault identity.

Delivered productive power is the minimum of the request and the declared branch capacity, or zero if that capacity cannot support the minimum stable load. Startup electricity follows actual predicted operation. These are explicit scenario hypotheses, not a reconstruction of simulator truth or a guarantee against a different failure. Actual execution retains its physical feasibility correction and requested-versus-applied record.

Tests must fit in consecutive intervals before the episode deadline. Plant power, hydrogen headroom, thermal limits and accepted minimum-run commitments remain constraints. The ending battery reserve is a fraction of the configured capacity; it is an end-of-horizon requirement, not a minimum at every instant. Accepted service missions contribute their future utility and isolation demands. Unaccepted charging, replenishment, cleaning benefits and successful repairs are not credited.

The reference assumptions are a 12-hour scheduling opportunity, a 24-hour delay after an unsuccessful or inconclusive test, a 10% ending battery reserve, and equally weighted tracking/unchanged-delivery hypotheses with a 0.5 worst-case objective weight. These are editable policy assumptions, not calibrated probabilities. Solver time remains the configured per-solve limit; candidate failures and missing incumbents stay recorded. No feasible test leaves the existing production policy in control. A missed deadline or delayed retry remains explicit.

## Confirmation follows actual observations

The scheduler sees the preceding diagnosis and eligible public procedure receipts. A reported reset or module replacement can reopen a test opportunity whether or not the procedure physically succeeded. Future receipts are ineligible. A successful-repair draw and the actual fault lifecycle are unavailable to this controller.

The opt-in policy requires successive actual requests at the same test load with consistent electrical tracking and an independent hydrogen balance. A skipped test, changed load, shortfall or ambiguous balance breaks the sequence. After a flow channel has been isolated, an otherwise consistent electrical/balance test can still support capacity recovery. The observer updates capacity only after the required number of intervals. Confirmation is within the configured sensor discrepancy tolerance; it is not an exact equipment rating or certification.

Original opportunistic diagnosis/probe semantics remain available for archived policies. What-if calculations on a scheduled decision retain its original observations, forecast, target, deadline, reserve and delivery hypotheses. An alternative may move the test window or leave it unresolved. It does not modify the recorded run or confirm a repair.

## Evidence and remaining work

Checks include shared requests with different delivery, independent hydrogen calculations, actual execution of both branches, a battery-limited night interval, full hydrogen storage, interrupted confirmation, unavailable procedure receipts, failed-test retries, a complete reset/confirmation run, an independent observation-based checker and immutable what-ifs. The checker rejects fabricated early confirmation. This evidence verifies those implemented assumptions; it does not validate the delivery probabilities against a plant.

The `field-recovery-tests` study compares methane MPC with opportunistic probes against methane MPC with this scheduling package, using the same hardware and exogenous inputs. Its reference has normal operation, a latched trip, incompatible module damage and optimistic-forecast stress across three fixed seeds. It reports physical restoration, subsequent confidence, test effort, solver outcomes, methane, costs, backlog and ending inventories. It does not require planning to win.

Joint choice of inspection/repair, conditional follow-up remedies, charging and shared visits, learned diagnosis/duration/value models, broader service alternatives and the remaining hardware families are still required. This policy supplies actual recovery-test scheduling within that larger programme.
