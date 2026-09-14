# Deployment and condition contracts

`Config.lifecycle` selects `site-lifecycle/1`. Omitting it preserves the old
configuration encoding and execution path. `methane.lifecycle.fixtures.illustrative`
creates an editable example; it is not a vendor specification. The full Release-2
completion gates remain in [release-2.md](release-2.md).

## Commissioning

A work package declares an asset fraction, prerequisite packages, an earliest
mobilisation time, work hours, acceptance attempts and departure. A single declared
project crew performs mobilisation → installation → acceptance → departure. Failed
acceptance goes through rework up to the attempt limit. Failed packages remain
unavailable; dependent work cannot proceed. The configured acceptance challenge is
private execution input. The policy receives completed acceptance receipts.

Crew time is finite within a declared shift. Access and communications are separate
interlocks. Sub-hour remaining work uses only that fraction of a crew hour; the next
phase begins at the next hourly boundary. No unused part of an interval is credited
as another phase. Accepted capacity becomes available at the following boundary.
Temporary construction equipment leaves only after its recorded departure work.

Solar availability and irreversible loss act **before converter clipping**. Battery
availability restricts charging/discharging power; energy already stored remains in
inventory. Electrolyser and reactor power/output limits constrain both planning and
execution. Reactor heat rejection remains available to preserve the existing thermal
boundary; partial reactor availability is an aggregate throughput assumption, not a
parallel-reactor geometry model. Minimum runs yield to physical restrictions.

Work-package machinery is specified by hired hours, external energy, crew time and
installation materials. External energy is recorded and priced separately from the
plant DC bus. Methods describe manual work or a prepared/assisted installation; they
do not establish autonomous robot capability or real safety certification.

## Condition and observation

Two reduced mechanisms are implemented:

| Asset | Mechanical hypothesis | Starting reference | Limits |
|---|---|---|---|
| Solar | Linear calendar loss, capped at 95%; independent of cleaning | 0.5% per 8,766 hours | Broad crystalline-silicon median, not a site calibration; no wear-out distribution |
| PEM electrolyser | Relative voltage growth applied to specific electricity consumption | 4.8 mV per 1,000 operating hours at 1.9 V | Continuous-operation status; uniform system-SEC scaling is an approximation; no load/temperature-specific kinetics |

Calendar exposure advances even during isolation. Operating exposure advances only
when the electrolyser produces, with a separately declared equivalent-hours cost
per start (zero by default). Initial exposure represents used equipment. It is not
manufactured by repeating an observed weather year. The aggregate solar condition
applies uniformly to installed capacity; heterogeneous panel ages are omitted.

The solar reference is Jordan et al., *Compendium of photovoltaic degradation rates*
([2016, DOI 10.1002/pip.2744](https://doi.org/10.1002/pip.2744)). Its reported
crystalline-silicon median spans 0.5–0.6%/year, with considerable variation and
measurement/soiling confounding. This supports a sensitivity hypothesis, not a
universal rate. The PEM reference is the [DOE technical target table](https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis),
specifically its **2022 status**, not the 2026 target. It defines end of life using a
10% performance change; operation beyond that point in a challenge is explicit
extrapolation. Both sources were checked on 14 September 2026.

A declared condition channel produces a fraction with seeded **uniform bounded**
noise, a sampling period, a positive reporting delay and optional dropout.
Communications gate packet receipt. Only eligible readings update the estimate;
old readings retain their measurement time. The channel is a modelling assumption,
not an identified off-the-shelf sensor or an inferred remaining-life oracle.

Current available PV retains the existing ideal contemporaneous power-observation
abstraction. Later forecast intervals use estimated condition and accepted capacity,
held through the horizon. Future acceptance, successful replacement and outage end
times are not credited. All other new lifecycle assumptions are disclosed; hidden
lifecycle parameter variations are rejected until a separate observation contract
exists. Physical condition and replacement outcomes reside in retrospective truth.

## Maintenance, support and costs

Policies are none, periodic, measured-condition threshold, and forecast-window.
The last chooses a complete on-shift work window with low predicted PV, using only
the supplied horizon. It is a transparent heuristic, not a globally optimal joint
maintenance schedule. Construction has priority. Waiting work has an outer deadline;
two consecutive unsuccessful or expired jobs require review. Physical work already
started remains visible until complete, including overnight isolation.

Replacement requires stock, access, crew, communications and a reference at its
start. Consumption and later replenishment are separate events. A successful private
execution outcome resets age; completion does not confirm restoration. A new eligible
post-work reading verifies it, or the verification deadline expires. Replacement
addresses this condition mechanism only. It cannot clear an injected process fault,
permanent surface damage or sensor bias merely because the asset names coincide.

The project crew is **explicitly additional** to the field-service crew. Construction
and condition replacement share it; they cannot run simultaneously. Existing docks,
references, access and communications also receive present common-outage indications.
Supplier stock, site capacity, delayed arrivals and rejected stock remain recorded.

Part prices are required assumptions. The example uses existing illustrative capital
for a whole-array replacement or the replaceable stack share. It supplies no quotation.
Opening stock and purchases enter cash once. Allocated replacement charges the larger
of calendar/use allowance and consumed-part cost. It does not add both. Construction
invoices replace the modelled asset share of the existing installation allowance;
their allocation accrues from the invoice boundary. Site setup and unmodelled
installation shares retain their existing assumptions. Project maintenance resources
are an additional operating expense. Cash, allocated cost and dispatch-dependent
cost remain distinct views.

Cumulative counters are checkpointed. Partitioned allocation is the difference
between those pools at its two boundaries. Repricing preserves physical records and
original dispatch prices. Lifecycle job/part prices remain frozen to their recorded
receipts; changing them for dispatch requires another scenario. Ending inventory has
no assumed liquidation proceeds. Project cash projection rejects repeating a partial
or earlier lifecycle year as if commissioning and ageing happened again. Short studies
have dated expenditure; lifetime profitability requires the requested chronology.

## Verification and preservation

`methane.lifecycle_reference` has no production-module imports. It independently
checks Decimal condition counters, eligible measurement values, work phases,
acceptance, crew limits, capacity, parts, seeded restoration, cash and cumulative
allocation operands. The portable archive checker includes it; continuous Sites
verification carries its state across partitions. Physical balances use the verified
interval-specific electricity-consumption parameter. Numerical verification is not
empirical validation. The finite reactor formal model has not been expanded to prove
the lifecycle executive.

The first implementation checkpoint passed 62 targeted tests, covering the new
mechanisms, independent balances, resumption, existing optical services and economic
regressions. The full Release-2 UI, documentation catalogue, historical comparisons
and release verification remain separate delivery work.
