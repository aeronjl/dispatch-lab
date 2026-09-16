# Plant interfaces

The optional `plant.integration` contract connects the reference equipment to an
hourly AC island, external conditioning and finite purified-water supply. Open
**Project → Equipment & evidence → Plant interfaces**, inspect the assumptions and
save a design revision. It is disabled in existing configurations. Enabling it is
an explicit design change; attaching the equipment evidence alone does not enable it.

The original plant illustration and labels are unchanged. For a saved study, the
same tab shows original parameters and a recorded hourly calculation, with a link
back to the original controller decision. No current calculation is substituted
for missing historical records. Edits and saved studies keep separate identities.

## Electrical and thermal boundary

Solar and battery power remain on the DC bus. Electrolysis (including its startup
allowance), reactor electric demand, dryer, external cooler and optional hydrogen
compressor share an AC output limit. DC demand is total AC demand divided by a
constant converter efficiency. Field services remain DC loads. Thus battery
conversion loss, process AC conversion loss and solar converter clipping are
separate; energy is counted once at each boundary.

The electrolyser base load already includes internal utilities. The added dryer
fixture is four times the approximately 3 kW optional dryer increment in Enapter
**AEMFlex120-DTS-COM02_rev08**, page 2. The alternative chiller increment is not
added as well. The four skids are treated as an aggregate: the configured dryer
load is applied whenever aggregate electrolysis is on. Neither this load rule nor
the aggregate turndown is a measured multi-skid staging curve.

External electrolyser heat duty = productive electrolyser power × declared heat
fraction. Rejected heat must fit within the external cooler capacity; its electric
load is heat duty × declared electric fraction. The default 25% heat fraction,
160 kW capacity and 5% electric fraction are **unquantified assumptions**. They do
not follow from the published nominal electricity alone. The model has no ambient
cooler curve, coolant temperature/storage or startup heat duty. Reactor cooling
remains a separate existing heat-balance mechanism, with its own electric load.

The converter's 600 kW and 96% defaults are also assumptions. This is an hourly
energy and capacity model, not an AC power-flow, grid-forming, protection or
ride-through qualification.

## Pressure and conditioning

Declared regulated hydrogen supply and buffer pressures determine whether an
explicit compressor is required. A higher buffer pressure without positive
compression energy and throughput is rejected. If configured, every kilogram
produced passes through compression, consuming the specified kWh/kg under its
throughput limit. Regulation to a lower pressure consumes no electricity in this
abstraction and receives no expansion-energy credit.

Hydrogen buffer and CO₂ supply pressures must both meet the assumed reactor feed
pressure; otherwise methane production is blocked, with a forced trip if a run
commitment must be interrupted. These are compatibility checks, **not** a relation
between tank mass and pressure, vessel sizing or a transient compressor model.
There is no CO₂ compressor adapter: a low CO₂ supply blocks production. The
manufacturer's “up to 31 barg” hydrogen figure is a maximum, not a guaranteed
operating pressure. The default 30/30/5/6 barg interface values need engineering
confirmation. Gas composition, drying performance and catalyst acceptance are not
certified or simulated by adding a dryer load.

## Finite water and chronology

A separate purified-water inventory starts at the declared stock. At each hourly
boundary, the scheduled delivery is accepted up to **beginning** tank headroom;
excess is recorded as rejected, then electrolysis withdraws water. Production and
planning cannot consume unavailable water. All rejected water, consumption and
ending stock are recorded. Existing site water-throughput limits can additionally
bound consumption; they are a withdrawal limit and do not refill this tank.

Nominal 19.4 L/h divided by 2.16 kg/h is approximately 8.98 L/kg in the rounded
Flex120 datasheet. This fixture uses 9 L/kg, matching the simulator's ideal water
stoichiometry and its 1 kg/L approximation. Extra treatment/feed losses can be
entered by increasing that value. There is no water recycling credit, treated-water
quality state, purification skid or pump-power model. Tank level is explicitly an
exact observed channel in this version; no unsupported sensor-fault model is implied.
Robot cleaning water and CO₂ inventories retain their existing, separate ledgers.

Water delivery timing is disclosed to controllers, uses absolute elapsed simulation
hours and survives partition checkpoints. Replans receive the original inventory
estimate and saved arrival schedule. Disclosed uncertainty blocks can vary every
scalar integration assumption, including dependent combinations. No probability
distribution is inferred. Hidden interface variations remain unsupported.

## Costs, evidence and preservation

The configured water-use rate replaces the older total-water allowance for these
runs, in both marginal dispatch costs and allocated costs. It is charged once on
consumption; rejected deliveries receive no assumed purchase/waste-disposal charge.
Those commercial terms require a separate logistics cash assumption.

Additional **installed** interface capital and annual standing maintenance are
blank by default. Total allocated cost and unit cost remain undefined until both
are supplied. A known subtotal remains available. Installed cost is allocated over
its ownership life without another installation markup or usage-wear charge. It is
excluded from dispatch incentives. The existing off-grid energy balance captures
the opportunity cost of auxiliary electricity; there is no duplicate electricity
purchase charge. Creating a cash scenario requires these missing prices and adds
separate interface initial/annual line items. Repricing a run leaves decisions intact.

The source edition and file digest are retained in `equipment-reference.json` and
saved equipment bases. The manufacturer document was checked again on 16 September
2026; it supplies nominal internal loads, optional conditioning increments, water
and electrical/pressure requirements. It does **not** supply the new cooler,
converter, logistics, compressor or price assumptions. These are registered as
explicitly uncalibrated, with user-authored sensitivity support. No old research
result is relabelled as verification of this implementation.

Primary source: [Enapter Flex120 rev08, page 2](https://handbook.enapter.com/electrolyser/aem-flex120/downloads/Enapter_Datasheet_AEM-Flex-120_EN.pdf).
The local, hashed source copy is recorded by the [equipment review](../research/equipment-planning/downloads.json).

Named checks in `tests/test_plant_integration.py` cover independent electricity,
water and heat calculations; all three controller objectives; clipping an
infeasible request; pressure-forced interruption; empty/full tanks; delivery timing;
original information; repricing and independent cost reconciliation. Saved-study
checks exercise checkpoint/resume, traces, legacy records and offline preservation.
Browser checks exercise enabling, invalid input, recorded tracing, narrow screens
and navigation. Passing these checks establishes software consistency, not field
feasibility. Public performance maps, experimental thermal data and researched cost
ranges are the next modelling inputs. Site commissioning or quotations could
strengthen validation later but are not prerequisites for this software project.

## Verification receipt · 16 September 2026

The new interface and worker checks passed on settled source: 16 tests covering
`test_plant_integration.py` and `test_jobs.py`, followed by all 14 solver-study
checks. The wider Python run completed with 1,243 passes and two source-identity
failures: files were still being edited after its parent process captured its
source identity. Both affected tests passed in those fresh-process repeats. This
is not reported as an uninterrupted all-green full-suite run.

All 98 JavaScript checks passed. Six selected browser checks passed, covering the
equipment workflow, stale responses, interface configuration/tracing, keyboard
inspection, narrow-screen access and unchanged plant/solar screenshot baselines.
The interface desktop, narrow-screen and recorded-calculation captures were visually
reviewed. No screenshot baseline was updated. Ruff lint/format checks, documentation
freshness, the 489-path assumption inventory, generated engineering documentation,
component catalogue and taxonomy checks passed.

These are software acceptance results. No new site measurements, calibrated cooler
curve, participant walkthrough, live-hardware qualification or broad research
comparison is claimed. Saved research artifacts and prior result editions remain
unchanged.
