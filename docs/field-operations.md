# Field operations and persistent faults

This is an optional **hourly service simulation**, with illustrative hardware, prices and reliability assumptions. Choose **Field services / repairable damage** or **Field services / resettable trip** in experiment setup. Inspect **Simulation menu → Site services** to follow work orders, batteries, consumables, costs and recorded calculations. Service hardware appears in a separate animated layer; every original equipment path and label is preserved.

## Faults, observations and repair

New configurations default to `faults.lifecycle = persistent`. A fault starts at the configured interval and does not end when `fault_duration_hours` expires. Successful compatible service is required. A transient must be selected explicitly: it represents a temporary disturbance which clears after its configured duration, rather than damage healing itself. Configurations from older archives, without the lifecycle field, resolve to `legacy-timed`; loading does not rewrite them.

| Injected condition | Permitted restoration | What the controller learns |
|---|---|---|
| Equipment capacity damage | Qualified service replaces the affected module | Work completion, followed by tracking probes; no true capacity disclosure |
| Latched module trip | One engineered reset after reading a latched contact, or qualified service | Dry-contact report, command outcome and subsequent load tracking |
| Hydrogen-flow sensor bias | Qualified service calibrates the flow channel | Independent balance residual returns to agreement; reset cannot calibrate it |
| Explicit transient | Configured disturbance duration ends | Only subsequent observations reveal recovery |

A repair effect is recorded after the interval's physical operation and becomes available at the following boundary. It never directly raises a diagnostic capacity estimate or clears a diagnostic isolation. The observer still requires its configured successful informative intervals. Both capacity and flow-channel effects are tracked separately. Fault truth is stored **per controller**, because repair timing depends on the controller's observed operation.

## Field assets and work orders

`FieldOperations` is a versioned configuration. `FieldRuntime.begin()` accepts the hour, diagnostic state and currently available PV, schedules work and reserves dock electricity. It does not accept fault type, actual capacity or scheduled recovery. `FieldRuntime.end()` advances execution. Only declared inspection measurements and service completion reports cross back to the scheduler. `FaultState` owns physical fault effects; a diagnosis is never a repair command.

The assets are `PLANT-01/CLEAN-01`, `PLANT-01/ROVER-01`, `PLANT-01/DOCK-01` and a declared module reset interface. Work orders have their own identifiers, capability, incident, reason, creation/start/completion boundaries, phases, blocked conditions and reports. The manifest saved once per run lists parameters, capabilities, route edges, information boundaries and omitted behaviour. These classes are separate from the process component kernels and controller optimizer.

| Asset/capability | Modelled work | Boundary |
|---|---|---|
| Cleaner | Travel → clean → verify → return; removes a configured fraction of an accumulated loss | Lumped additional **available-DC loss after conversion**, not optical, row geometry, rain, abrasion or electrical-string physics |
| Inspection rover | Travel → read module-trip contact → verify → return | Ideal status contact; cannot identify hidden damage or diagnose every sensor |
| Shared dock | Charges idle, available robots, with a shared power limit and efficiency | Measured solar only; plant-battery charging overnight is not scheduled |
| Reset interface | One attempt per incident with a latched indication | Electrolyser is isolated for the work interval; reset cannot repair equipment damage or sensor bias |
| Human service | Travel/lead time → isolate and replace module/calibrate flow channel → operational verification | One finite service kit per attempt; failed work remains unresolved |

The initial service policy is a documented local rule shared by all process controllers. It inspects confirmed incidents, resets only a latched indication, otherwise requests human service; it cleans at a configured measured-loss threshold. An unavailable inspection route triggers human fallback. Unavailable energy can leave a mission queued, and missing service kits leave human work blocked. Fallback can be disabled explicitly. There is no automatic resupply or invisible recovery of stranded robots.

The route graph contains declared dock-to-array, dock-to-electrolyser and gate-to-electrolyser connections. Travel is aggregated to hourly phases. Mission launch reserves energy for the entire route plus a return reserve. One cleaner and one rover may operate concurrently. Hands-on service and resets impose an ideal electrical isolation on the electrolyser; known scheduled isolation is included in the process planning horizon. This models availability, not lockout/tagout certification, emergency shutdown logic or hazardous-area compliance.

The process optimizer accounts for current dock load and known isolation intervals. Its remaining horizon uses the current loss estimate with linear accumulation. It does **not** anticipate future cleaning benefits, future dock charging or unverified repaired capacity. Service policy is not jointly optimized with production yet. What-if process replans retain their original service assumptions and exclude the fixed service workload from predicted decision costs. Executed run contribution includes actual service costs.

## Illustrated work phases

The main plant scene includes an inspection rover with an articulated sensor head, a tracked cleaner and brush, a shared charging dock, a service van with a walking technician and tools, and the fixed reset actuator. Click or keyboard-select hardware to open Site services; Escape returns focus to it. The service drawer also has **Find** controls for narrow screens.

One playback clock drives both completed hourly states and continuous illustrative poses. Speed changes preserve partial progress; pause freezes motion; seeking reconstructs the selected boundary from recorded work orders. During an interval, motion uses only its beginning-of-interval work state. Outcomes and verification appear at completed boundaries, never early. Reduced motion shows static boundary poses. Controller changes switch to that controller's work history.

These are schematic access routes, a drawn panel access ramp and illustrative walking, scanning, brushing and tool poses, not a navigation, dexterity or repair-kinematics simulation. The scanner depicts the rover reading the declared module contact; it does not add a thermal inspection channel. The cleaner does not repaint individual panels as physically clean: only the model's lumped loss changes. Failed robots remain at the worksite. Human service vehicles remain parked after work because departure/retrieval is not modelled; stowed tools do not mean operating recovery has been verified.

The layer is absent in runs without field records. New reproduction bundles capture the renderer; old bundles retain their original renderer. Viewing an old field run with the current app can add this visualization without changing its archived source or numerical results.

## Accounting and reproducibility

Robot batteries begin full as explicit initial inventories, independently of the plant battery. Disabled robots have no stored energy. Every interval reconciles:

`ending robot energy = starting energy + dock input − charging loss − mission use`

`plant PV + plant battery discharge = process demand + dock demand + plant battery charge + curtailment`

The additional available-DC loss is recorded separately from the underlying solar conversion and converter clipping. The solar design workspace continues to show that base conversion, with a labelled service adjustment and the actual plant availability. It does not attribute the service proxy to individual strings or panels.

Ownership excludes replaceable parts; replaceables use the larger of calendar and usage allowances, charged once. Running costs include observed mission usage, cleaning kits, actual human visits, labour and service kits. Standing service maintenance excludes those recorded visit/labour/kit costs. Dock electricity is a physical bus load, not a second fictitious electricity purchase. Repricing changes cost reports without changing the trace. In the new `recorded-work/1` convention, a diagnosis alone incurs no assumed repair or visit. Historical `legacy-alarm-allowance/1` rows retain their old allowance.

Mission failure and repair success have separate seeded channels keyed by task kind and incident/sequence. Failure probabilities are **assumptions**, not measured manufacturer reliability. A failed cleaning mission still consumes the kit and energy used; it does not remove loss. Failed repairs consume actual service resources but do not restore faulted equipment. A stranded robot remains unavailable and its need for human follow-up is reported; this increment does not simulate retrieval logistics.

Archives preserve the configuration, field manifest, work orders, per-interval quantities, service effects, source capsule and price identity. The offline report includes field mechanics and records, and recorded playback exposes Site services. Tests cover persistent/transient boundaries, compatible resets, failed repairs, service isolation, delayed inspection information, energy accounting, missing resources and costs. The independent decimal checker verifies arithmetic, compatible repair boundaries and costs; it treats diagnosis flags and repair success outcomes as recorded inputs, not independent empirical proof of robot performance.

## Evidence and next experiments

Start with matched **no service / human-only / robot-assisted** cases using the provided presets. All of these keep the field layer enabled so they share the same soiling physics; the no-intervention preset disables capabilities, not environmental loss. Disabling the entire field layer is a compatibility option, not a matched no-service comparison. Then then vary service delay, fault type, initial soiling, charging access, mission failure, repair success and kit stock. Preserve plant parameters, weather and sensor seeds. Report methane and all ending inventories alongside dock energy, actual visits, kits used, unresolved/blocked work and allocated and variable costs. Do not interpret one successful illustrative run as proof of savings. These presets are runnable demonstrations; they do not replace or rewrite existing study editions.

The prior research remains the source for hardware feasibility: [field robotics report](../research/field-robotics/report.html). Its primary sources include [ExRobotics inspection systems](https://www.exrobotics.com/our-products), [Ecoppia cleaning systems](https://www.ecoppia.com/) and [Rotork engineered actuators](https://www.rotork.com/en/products/electric-intelligent-actuators/iq3-pro). These establish categories of capability, not the fixture's numerical performance or cost assumptions.
