# Combined crew visits

`crew-visit/1` groups compatible jobs into one declared itinerary. It is opt-in through `visit_bundling_enabled` with `logistics/1`; the plant runtime reports `plant-service-contracts/6`. Existing configurations default to separate visits, and older archives retain their original source and behaviour.

Each member remains a single-effect `MissionPlan`: its original request evidence, capability, interface, materials, physical result and acceptance test are preserved. A `VisitPlan` adds the shared crew, ordered members and return journey. It does not turn several interventions into a generic repair. Supply delivery can complete while a module replacement remains unverified; arriving home does not certify the jobs.

## Routing and resources

The first job includes the outbound journey. Later jobs use the declared access graph between service points, and the final job includes the return home. Default on-site transfers take 0.25 hours per declared edge; these are illustrative travel times, not distances or a navigation model. The dock connects to the electrolyser and solar service point. A retrieval's reported field-to-dock corridor is assumed traversable in reverse by the same recovery crew. No new failure location is inferred.

Every job retains its work, preparation, verification and internal recovery-transfer stages. The complete itinerary must be continuous, fit one crew shift and meet every job's return deadline. A portable tool accompanies the same crew for the entire visit; its work phases still consume the configured power, water and materials. Its illustration appears at the worksite and it travels inside the service vehicle. Van volume, lifting, road traffic and emergency response are not simulated.

Crew, accompanying tools, all current stocks and each work area's time window are reserved atomically before departure. Failure to reserve a later job leaves no partially dispatched visit. Stock consumption is recorded separately as work proceeds. Every actual travel, preparation, work, verification and return hour consumes the finite crew allowance once. The outer visit reservation prevents the same crew or accompanying tool being assigned elsewhere between jobs.

The local rule selects currently feasible queued jobs in request order, up to the configured limit (initially four). It does not predict future diagnoses or wait for an unknown job. A flow-channel fault discovered after capacity repair must become a later request. The common decision context, original request evidence and chosen itinerary are saved separately from subsequent physical outcomes.

All required consumables must already be reservable at departure. A delivery in the same itinerary is not credited as stock for another job before it physically arrives. For example, an empty module store can block replacement even if a replenishment is planned. Conditional replanning after delivery and optimal visit sequencing belong to the coordinated supervisor stage; no speculative future stock is granted here.

## Interruption and acceptance

Requirements are checked again against available observations as execution advances. If the crew or an upcoming member loses a prerequisite, the visit stops at the crew's current recorded location. Unstarted jobs are blocked and their unused reservations released. Already consumed labour, water, materials and partial cleaning remain consumed. The crew and its tool do not teleport back to the gate; compatible assistance is a subsequent procedure.

Completed effects remain separate from observed recovery. Every repair/calibration member keeps its original post-work test. A failed attempt can leave a job awaiting operating evidence even after the crew has returned. A trip to a service point does not establish successful physical repair, and the supervisor never receives private repair-success operands.

## Accounting, evidence and interface

One actual departure creates one callout. The existing price basis charges that callout and the recorded hands-on work/materials; full committed crew time is also reported as a resource quantity. It is not charged a second time as travel labour. Complete travel, installation, procurement and contracted-service economics remain the stage-3 ledger, so these examples do not establish annual hardware value.

The independent standard-library checker reconstructs itinerary continuity, configured travel/work times, complete crew shifts, atomic stock and accompanying-resource reservations, stage execution order, interruptions, actual callouts and return receipts. It checks displayed planned jobs against their records and rejects forged summaries. These checks verify the declared scheduling model; they do not validate real service durations or repair reliability.

In the revealed service inspector, shared visits show their planned jobs and return time alongside actual status. Each original job remains in the work-order list. During playback the vehicle follows the member active at the fractional playhead, including an on-site transfer within an hour. The original plant artwork and labels are untouched. A future scheduled member cannot take over the crew's pose prematurely, and a cancelled future member cannot hide a stranded crew.

Eight reproducible 32-hour mechanism cases are generated by `python -m methane.services.visits_demo`. The supply pair shares the same inputs with bundling enabled/disabled. Other cases exercise known delivery-plus-repair work, unsuccessful repair, portable treatment with a later delivery, partial interruption, a short shift and an empty upstream pipeline. Results retain ending plant/service inventories, unfinished jobs and acceptance still pending. These are workflow fixtures; the full published Studies programme remains outstanding.
