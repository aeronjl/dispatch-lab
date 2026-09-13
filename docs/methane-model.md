# Model and information boundaries

## Physical fixture

The hourly DC plant uses 1,000 kW solar, an 800 kWh battery (0.5C, 90% round-trip efficiency), a 450 kW electrolyser (30% minimum load, 40 kWh/start, 55 kWh/kg H₂), a 60 kg H₂ buffer initially empty, and a 1,000 kg supplied-CO₂ buffer initially holding 500 kg. Deliveries of 300 kg arrive at interval starts every 24 hours; excess above tank capacity is rejected and recorded. No implicit venting, export or water recycling occurs.

Ideal reaction: CO₂ + 4 H₂ → CH₄ + 2 H₂O. Rounded molecular weights are 44, 2, 16 and 18 kg/kmol, giving 0.5 kg H₂ and 2.75 kg CO₂ consumed per kg methane, with 2.25 kg reaction water. Electrolysis stoichiometric water is 9 kg/kg H₂; the default purchased/process-water allowance is 12 litres/kg H₂ and is recorded separately in the economics. No recycling credit is taken.

Reaction heat is approximated as 165 MJ/kmol methane (2.8646 kWh/kg); this neglects temperature-dependent enthalpy, conversion efficiency, pressure and reaction kinetics. [Primary methanation reference](https://doi.org/10.1039/D5RE00337G).

For constant interval inputs, `a = exp(-UA/C)` and `b = (1-a)/UA`, with the zero-loss limit `b=1/C`. The temperature transition is `T_next = a*T + (1-a)*T_ambient + b*(heater + reaction_heat − cooling)`. Heat loss is also evaluated from the analytic temperature integral so thermal conservation is checked independently of the residual. With constant inputs temperature is monotonic within an interval; requiring both endpoints in the 250–400°C band bounds the entire production interval.

Default thermal capacity is 0.3 kWh/K, loss coefficient 0.08 kW/K, heating 60 kW and heat rejection 40 kW. Cooling electricity is 10% of rejected heat. Methane output is 3–10 kg/h, with 2 kW running auxiliaries plus 1 kWh/kg. Minimum run is four hours. A future start near the horizon end carries a visible ending commitment; subsequent replans carry actual commitments. Resource failure can override a commitment and is recorded as a forced trip.

The planner and executor share sparse constraints. The executor can reduce requested actions under physical limits but cannot silently add battery charging or electricity consumption. Its preference retains methane first, then electrolysis/heating, with surplus recorded as curtailment. Hydrogen production and consumption are uniform within each hourly interval; CO₂ deliveries occur before consumption. Pressure, compression energy beyond configured auxiliary proxies, plant standby hardware, gas acceptance and downstream methane storage are outside the boundary.

## Objectives and evidence

Greedy uses only current conditions to prioritise methane, heat to Tmin+5°C, hydrogen and surplus battery charging. Its displayed future trajectory is a rollout of that same local rule using the available forecast. MPC maximises either horizon methane (with small cost/start tie-breaks) or assumed methane value less consumption and usage-wear proxies. No terminal sale value is assigned to inventory. Prediction horizons extend past the evaluation window to avoid forcing an artificial plant stop at the report boundary.

Every decision retains prior observations, estimated state, diagnosis, forecast issue and availability, its trajectory, bound evidence, dispatch requests, objective/cost versions and solver status. Starts, forecast changes, anomalies, confirmed diagnoses, probes, trips and recovery events are navigable. Template explanations describe recorded bounds and trajectories; they are not causal importance rankings.

The delayed-supply experiment shifts the delivery schedule by 24 hours. What-ifs restrict first-interval battery discharge, electrolysis or reactor start, or shift only the next forecast CO₂ delivery by 24 hours. They reconstruct the original estimate and forecast and preserve original decision costs. A deferred delivery outside the horizon is labelled. Unavailable feasible incumbents are displayed, with no substitute claimed as an optimised alternative. A probe decision retains its probe requirement unless the alternative explicitly turns electrolysis off. Requests and responses are keyed to run, strategy, interval and alternative.

## Diagnosis

Electrical productive power, H₂ flow and independently metered H₂ inventory are separate observations. Noise draws are keyed to seed/hour/channel, shared across policies. Default multiplicative noise is 2%; inventory noise is scaled to interval production rather than tank capacity. This makes the low-flow mass balance observable and is an explicit metrology idealisation. Battery, CO₂ inventory, reactor temperature, downstream flow and equipment mode channels are ideal in this bounded study.

The controller already has an independent tank inventory measurement; dispatch state therefore does not rely on integrating the flow meter. Flow isolation switches the usable upstream-flow telemetry to the inventory balance. Its diagnosis-disabled ablation can legitimately leave physical dispatch unchanged, while capacity diagnosis can change dispatch. This avoids introducing an artificial dependence on a redundant faulty channel.

The tracking residual compares electrical request with measured delivery. Flow residual compares the flow meter with successive inventory measurements plus metered downstream consumption. The threshold is max(10%, 3×noise fraction). Two consecutive informative requests confirm anomalies. The independent balance must agree with electricity before classifying a flow-channel bias or a tracking shortfall. Conflicting channels produce uncertainty and conservative capacity. A low request is insufficient evidence; it does not establish health.

Derated equipment is probed upward by 10% of nameplate where current solar, hydrogen headroom and a feasible thermal plan permit. Two successful informative probes are needed for each increase. Greedy probes retain its local priority rule; methane MPC and economic MPC retain their own objectives. First-interval methane cannot spend the extra hydrogen from an unconfirmed capacity increase. Recovery can remain incomplete at the experiment end; no truth-based recovery shortcut exists. A four-day autonomy preset gives more daylight opportunities than the initial three-day evidence cases. Confirmed incidents trigger one intervention allowance until supported recovery ends the incident. Disabling diagnosis retains the nameplate assumption and excludes diagnostic interventions.

## Weather

Sources: [Open-Meteo individual ECMWF forecast runs](https://open-meteo.com/en/docs/single-runs-api) and [ERA5 historical reference](https://open-meteo.com/en/docs/historical-weather-api). Attribution and raw responses are included in each export. ERA5 is reanalysis, not a site observation. The saved current forecast is a scenario baseline; seeded stress creates its simulated reference.

Historical replay saves daily 00 UTC initialisations, not a stitched forecast history. The latest saved issue whose assumed availability is at or before the decision is selected. Publication lag defaults to six hours and is editable; it is an assumption, not a claim about an exact historical publication timestamp. The UI/export records this daily sampling cadence. Provider interpolation can turn native multi-hour forecast intervals into hourly values.

Radiation at t+1 is the preceding-hour mean for [t,t+1). Ambient temperature and humidity at t provide interval context. Missing fields, absent units, null radiation and nonconsecutive times exclude the interval; missing required horizons stop the weather run with an incomplete-data result. Synthetic scenarios are never substituted implicitly.

PV DC power = nameplate × GTI/1000 × (1−loss) × max(0, 1+temperature_coefficient×(panel_temperature−25)), capped at nameplate. Panel temperature = ambient + (NOCT−20)×GTI/800. Defaults: tilt 30°, azimuth 0° (south), loss 14%, NOCT 45°C, coefficient −0.004/K. Humidity is context only. UTC governs scheduling; local display includes the offset across DST transitions. Current-hour mean PV is treated as measured, an hourly scheduling abstraction rather than a subhourly forecast claim.

## Economic meaning

All EUR values are editable assumptions. Methanator €200k at 10 kg/h, H₂ storage €60k at 60 kg and CO₂ storage €40k at 1,000 kg scale linearly with their configured capacity. Default life is 20 years. Reactor replaceable share is 20%, with 60,000 operating hours and two equivalent hours per start. CO₂ costs €0.15/kg consumed, assumed methane value €1/kg. Existing solar, battery, electrolyser, site, water and intervention assumptions are retained.

Allocated period cost charges fixed ownership plus **max(calendar, usage)** once for battery cells, electrolyser stack and replaceable reactor allowance. Fixed allocation is excluded from dispatch incentives. Decision economics uses water, consumables, consumed CO₂ and usage-wear proxies. Assumed operating contribution is methane value minus these proxies; it is not revenue after gas certification, investment return or total project profit. Do not add the two views together. CO₂ purchases and rejected deliveries are tracked physically, but consumption accounting does not pretend to be a cash-flow statement. Ending inventories have no speculative sale credit.

Repricing preserves the physical trace and frozen dispatch costs. An exported repriced cost report sits alongside the original decision cost snapshot. Stable asset identifiers provide attribution, not ownership claims or settlement rights.
