# Scheduled work and dock control power

`plant-service-contracts/8` adds two opt-in mechanisms to the existing mission executive. Both default to off, preserving the behaviour of older configurations and published studies. They are illustrative scheduling assumptions, not manufacturer maintenance instructions or electrical designs.

## Routine procedure

`routine-service/1` schedules exterior and connector cleaning plus a mechanical check on an installed row cleaner, rover, dock, fixed reader or reset controller. The selected resident assets receive separate due clocks. The first due hour is measured from the simulation origin; subsequent due times are the **actual work completion time plus the configured interval**. A late visit stays overdue until work finishes. The completion is exposed at the next hourly boundary, with its fractional work time retained.

The task needs a contracted crew, a reachable declared interface, one maintenance kit, finite labour allowance and a shift that covers the journey and return. A battery robot must be at its dock. The target is reserved during the procedure, excluding conflicting charging or use. The crew follows the existing recorded travel/work/return phases; optional combined visits share eligible travel while retaining separate tasks and supplies. Finite upstream kits use the existing restock pipeline. Interrupted work retains spent time and supplies, creates no completion credit and remains visible in the backlog.

Completion records only this declared procedure. It **does not** repair injected damage, clear a latch, calibrate a sensor, renew a brush, certify equipment health or imply quantified life extension. Each of those needs its own compatible action and evidence. Degradation and avoided-failure hypotheses remain part of stage 6. With the current fixed injected-fault model, omitting this routine procedure therefore avoids its costs without increasing faults; that is an explicit model boundary, not evidence against real maintenance.

Reference assumptions: first due 720 h; repeat interval 720 h; 1 h of work per target; two opening kits; €50 per kit when new complete service prices are selected. All are editable. Opening inventory is distinct from procurement. Existing price snapshots missing the new material stay unpriced when it is consumed. Routine labour, kit consumption, callout and vehicle time enter their existing cost lines. The calendar maintenance allowance excludes separately recorded labour and materials and must not be interpreted as a second charge for these visits.

## Dock standby

`dock-standby/1` represents constant hourly control-electronics demand upstream of the charger power stage. Its default is 0 kW. A failed charging power stage may therefore continue to draw standby electricity; the control board and the power stage are distinct assumed functions.

At each decision, the board receives its full declared rate only if current measured PV plus safely available plant-battery bus power can supply it. Available battery power is the smaller of the battery power limit and starting energy multiplied by discharge efficiency for the one-hour interval. The service runtime returns the granted load to plant dispatch; only plant execution changes the battery. Electricity is included once in bus balance and service consumption.

An insufficient supply gives a zero grant and records the full unmet standby demand. It does not earn a fractional hour of working controls. New charge tasks and dock function tests require powered controls. Remaining measured PV bounds active service and charging; those discretionary tasks retain their existing solar-only local rule. Standby uses PV first in this priority allocation, leaving only the remaining PV for active services; production competes for the remaining combined plant supply.

The current local supervisor does not anticipate future service loads. It can spend battery energy now and leave the dock unpowered later. This consequence is recorded, not hidden by free charging or retroactive reserve decisions. Stage 4 will compare explicit service reserves and joint scheduling. The hourly mean-power model does not simulate electrical transients, converter protection or subhour battery dispatch.

## Evidence and presentation

The original SVG artwork remains unchanged. Recorded crew phases use the existing service vehicle and technician illustrations. The revealed service inspector shows due clocks, completed procedure counts, standby supplied/unserved electricity, resource events and original cost calculations. Detailed service essays and targeted alternatives remain required later in the programme.

The independent standard-library checker reconstructs procedure timing and recurrence, checks resource accounting, and derives standby grants from original plant parameters, starting battery inventory and measured PV. Tests exercise supplies, interruption, target contention, night power, a failed power stage, persistent damage and causal decision boundaries. These are numerical and software checks of the declared model; they are not empirical evidence of maintenance effectiveness.
