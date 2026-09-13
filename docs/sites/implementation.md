# Sites: evidence, operation and project cash flow

Open **Sites** in the simulation menu. Map and list selection share a saved site
identity. **How Sites is modelled** opens a learning essay with independently
editable area, resource and cash examples. Returning restores the Sites context.
The plant artwork and labels are preserved.

## A complete workflow

1. Search a European place, enter coordinates, draw a polygon or generate a bounded
   regional grid. Points are reference locations; they are never treated as parcels.
2. Inspect PVGIS seasonality. Screen a polygon with WorldCover land classes, GLO-30
   slopes and Natura polygons. Select exclusions explicitly. Import national
   designations, flood layers, quotes and measurements with units, coverage,
   timestamps, attribution and redistribution permission. Source bytes are immutable.
3. Save a plant design. Capacity inputs use the existing physical Config. Full
   configuration exposes component, fault, sensor, service-fleet, support and cost
   assumptions. Optional layout features report metric areas and route lengths;
   they do not infer feasible engineering. The site supply contract bounds water
   throughput and supplies a known CO2 delivery calendar. Only off-grid electricity
   is executable. A network lead remains evidence until a grid interface is qualified.
4. Under **Studies**, save an environment, then freeze cases with controller, period
   role, seed and numerical repetition. ERA5 is reanalysis. Archived ECMWF issues
   use their publication lag; previous-day persistence is an explicitly different
   information assumption. Missing data stops acquisition visibly. Measured CSV
   import requires hourly UTC support, units and preceding-day coverage. Optional
   DC-scale calibration fits only the declared training period and reports held-out
   error without editing a design.
5. Start the study. One frozen numerical worker executes bounded partitions. Cancel
   and resume retain the last committed interval. A case carries physical, diagnostic,
   fault, service and usage states across hours and years. Only independent cases
   start from their configured initial state. Select a saved period to open its
   original plant recording; use the menu to return to that study.
6. Reprice a finished physical case with a separate cash scenario. Specify acceptance,
   offtake capacity, price year, discount convention and dated items. Missing costs
   leave full NPV and unit cost unavailable. The displayed known-price ledger is a
   subtotal. Short samples require an explicit annual-repetition assumption. Whole
   observed years repeat cyclically over project life; this is not an ageing model.
7. Declare a finite sizing universe, budget and service designs. Compare equal-plant
   signatures separately from resized designs. Roles and temporal overlaps remain
   visible. Unweighted ranges are not probability bands. Supported probabilities
   must belong to one design/controller/duration and cannot count numerical repeats
   as fresh weather draws. No-build has zero new-project NPV. Only strict, matched
   reversals across environments are labelled as paired reversals.
8. Freeze a write-up. Its edition includes unsuccessful and incomplete cases. Export
   an HTML report and reproduction ZIP. Restore offline with
   `python -m methane.siting.reporting restore BUNDLE.zip --root NEW_STORE`.
   All members and conflicts are checked before writes. Restricted inputs, detailed
   forecasts and checkpoints are omitted rather than redistributed indirectly.

## Execution and accounting contracts

`site-yield-study/1` binds source capsule, original Config, environment, utilities,
uncertainty world and explicit case identity. `site-period-entry/1` is the append-only
transaction joining a period and its next checkpoint. A failed interval does not
advance the checkpoint. The full original archive is rehydrated and integrity-checked
for playback; thin numerical projections accelerate aggregation. Final allocation
runs once over the whole case. Do not add week-level replacement allowances to
estimate annual costs. A separate cumulative service-cost prefix preserves shared
procurement and usage across partitions and repriced interval reports.

The legacy scenario duration remains its short-run fixture setting. New
`continuous_period.total_hours` and study case hours are authoritative for long
chronology; global interval indices are retained. UI indices are local to the
selected saved period. This does not alter old archive meanings.

Checkpoints encode an explicit allowlist of runtime classes and aliases, not pickle.
Random channels use absolute interval indices and the original seed. Observers never
receive injected fault types, private capacities or future repair outcomes.
Off-grid water supply is a separate planning/execution bound, not an observer fault.
Recovery version 4 opens a fixed forecast-aware verification deadline within the
original finite maximum wait. Unlocated windows preserve the hard cap, and later
forecasts cannot roll it forward. Only observed tracking confirms recovery.

Project cash includes capital and replacement payments, not capital plus ownership
allocation or duplicate wear. Gross hydrogen, consumed hydrogen, supplied/accepted/
rejected CO2 and terminal stocks remain separate. Acceptance is an explicit scenario;
there is no hydrogen export, DAC, methane certification or subsidy premium inferred.

## Data qualifications

The vendored Natural Earth map is a coarse public-domain basemap. It is not parcel
geometry. Live adapters cover PVGIS 5.3, ERA5, archived ECMWF forecasts, WorldCover
2021 COG windows, GLO-30 and regional Natura extracts. Native raster resolution and
class units are retained; display colours never become quantitative data. A window
crossing a source tile boundary requires a merged, identified import.

Country packs cover investigation routes for GB, Spain, Denmark, Germany, France,
Netherlands, Italy and Portugal. National flood, water, grid, land-rights, road-access
and commercial supply information enters through the structured source/evidence
interface. Country links are not automatically fetched, calibrated or approved
connection data. The source catalogue labels proposed/manual/authenticated routes.
External accounts, private quotes and real site measurements have not been invented.

The reference plant remains illustrative. Annual numerical conservation does not
calibrate thermal dynamics, fault incidence, repair capability, weather conversion,
land availability or accepted product value. Grid import/export, fuel-export branches,
capture and new physical families remain separately reviewed extensions.

Forecast gust maxima are normalized from the following timestamp into their
preceding operating interval; ERA5 gust values retain the indicated-hour sample
convention. This distinction is documented separately by the provider's
[forecast](https://open-meteo.com/en/docs) and
[historical](https://open-meteo.com/en/docs/historical-weather-api) variable tables.
Initial null forecast accumulations are not fabricated as zero.
