# Fractional services in the coupled plant

`plant-service-contracts/1` is an opt-in successor to the unchanged whole-hour field runtime. Select **Fractional service contracts** in the existing experiment setup, enable field operations, then choose a mobile or fixed contact reader. Exact configurations use `Config.service_system: ServiceSystem`; absent/null retains the legacy runtime. Existing archives are not migrated or overwritten.

The `services/core.py` registry assembles the existing cleaner, rover, dock, reset actuator and contracted crew, plus a fixed contact reader. Assets declare capabilities, tools, service points, energy ports and explicit assumptions. The same inspection capability runs through the fixed or mobile adapter. The catalogue does not assert compatibility with hazardous installations; certificates, locomotion and emergency response remain outside this hourly sandbox.

`services/plant.py` contains the local work-selection adapter and a private interval-effect port. The policy has access to diagnosis, the ideal lumped-loss monitor, observed contact reports and declared support availability. It has no access to injected fault cause, true capacity, repair-success outcomes or future recovery dates. Reading failures and Boolean contact errors use separate reproducible channels. A contact report is not a fault-type oracle. An unavailable read cannot authorize a reset.

## Execution and information boundaries

1. At H, dispatch uses observations available at H. Work orders keep the evidence from their original request; a later dispatch has its own current context. Compatibility, current prerequisites, finite materials, asset occupancy, travel corridors and energy are checked before reservation.
2. Known work schedules reserve equipment isolation for every intersecting hourly plant interval. The configured interlock is ideal and conservative. Fractional reservations cannot imply partially restored production within an already-dispatched hour.
3. Service phases integrate electricity over their exact overlap with [H, H+1). The current solar supply bounds simultaneous fixed-service rates. Lost supply interrupts a fixed task before dispatch. Applied service electricity, unfulfilled requests and unused reservations are separate records; the plant receives actual applied service demand.
4. The private effect port collects procedure outcomes during service execution but changes plant faults only after the plant finishes [H, H+1). A work completion at H+0.25 first changes capability at H+1. Its contact reports are available no sooner than that boundary. Reset changes only a compatible latched trip; module replacement changes only capacity; calibration changes only the flow channel.
5. Tracking evidence from an interval starting before the work ended cannot verify its repair. Subsequent informative operating probes must support restoration. Motion can finish and return before the operating test passes. Work completion never directly restores an observer estimate.

The remaining local-rule limitations are explicit: no anticipation of future cleaning benefit in process MPC, no joint maintenance optimisation, and no automatic retrieval or replenishment. Failed mobile missions retain an assistance-required state. A technician uses a separate visit for replacement or calibration; visit bundling is subsequent work.

## Utilities, inventory and cost

The dock is a fixed supply capability. Charging reserves the target robot and shared charger for the interval, consumes bus electricity, then posts the accepted battery energy at the boundary. It never grants future battery energy when work is selected. Return reserve is held but not consumed as fictitious travel. Kits are consumed at work entry even when the procedure later fails. Mission returns are recorded and keep the asset occupied until complete.

The configured legacy cleaning proxy still multiplies available DC after base solar conversion. It is not section coverage or a pre-clipping optical model. This is an intentional retained boundary for this integration checkpoint; the next stage supplies that distinct mechanism.

Existing owned-asset and usage accounting is retained. The new fixed reader (€3,000), reset actuator (€1,500) and calibration kit (€100) defaults are explicitly illustrative, editable assumptions. A fixed reader does not also incur ownership for a disabled rover. Contracted-crew callout covers travel/mobilisation; hands-on and verification time receive the existing hourly labour allowance. This is not yet the complete installation/subscription/support/expenditure ledger promised by stage 3. No duplicate electricity purchase is added: service load already participates in physical dispatch.

## Reproducible example and checks

```
.venv/bin/python -m methane.services.demo
.venv/bin/python -m pytest tests/test_service_plant.py tests/test_service_contracts.py tests/test_field_operations.py tests/test_bundle.py
```

The example saves mobile/fixed runs, original source and assumptions, offline animated playback and independent audits in `build/services/coupled`. It uses constant available power and zero observation/repair randomness to make timings inspectable; it is not a published hardware economics comparison. Separate tests exercise nonzero error probabilities through forced unreadable outcomes, missing prerequisites, power interruption, exhausted/held resources and causal isolation from simulator truth.

Independent checks include decimal energy arithmetic, bus/material/thermal reconciliation in the full plant, component-specific restoration, post-work verification, immutable repricing and old-archive behaviour. Tests do not constitute empirical hardware calibration or a complete formal correctness proof. The existing plant SVG is preserved byte for byte; fractional overlays render recorded stage schedules and reveal results only at the appropriate completed boundary.

Narrative review, 11 September 2026: the existing twelve Model essays retain their original teaching fixtures and equations. The diagnostic essay already distinguishes transient teaching disturbances from persistent plant faults. The new service timing, task-specific effects, charging and price assumptions are reviewed here; the package identities are bound into documentation freshness. Dedicated interactive service essays remain an explicit later deliverable, not a completed catalogue entry.

Narrative review, 12 September 2026: the optional candidate-cleaning forecast now reuses the surface and solar kernels, with treatment effective after each interval and observed efficacy retained for an ongoing pass. Its output is conditional prediction, separate from execution, plant curtailment and methane benefit. The twelve existing teaching fixtures do not change, and their static solar controls still do not replay service decisions. The [planning-port explanation](service-planning-ports.md#conditional-cleaning-benefit) records this scope and its independently checked examples. No new empirical, full-controller or future-hardware claim is added by refreshing the implementation bindings.
