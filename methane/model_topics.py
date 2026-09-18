"""Authored explanations and explicit bindings; facts come from component contracts."""

from methane.learning_lab.topics import topics as learning_topics
from methane.lifecycle.topics import topics as lifecycle_topics
from methane.service_topics import topics as service_topics


def control(key, label, default, lower=0, upper=1, step=0.01, unit="", options=None):
    return dict(
        key=key,
        label=label,
        default=default,
        lower=lower,
        upper=upper,
        step=step,
        unit=unit,
        options=options,
    )


def passage(title, text, controls=(), equation="", terms=()):
    return dict(
        title=title, text=text, controls=list(controls), equation=equation, terms=list(terms)
    )


def topic(title, group, specs, files, purpose, passages, limits, sources=()):
    return dict(
        title=title,
        group=group,
        specs=specs,
        files=files,
        purpose=purpose,
        passages=passages,
        limitations=limits,
        sources=list(sources),
        version="1",
    )


C = control
P = passage
TOPICS = {
    "battery": topic(
        "Keeping energy for later",
        "Physical plant",
        ["battery"],
        ["battery.py"],
        "The battery moves electricity through time. Its inventory is stored energy; the bus sees power flowing into or out of it.",
        [
            P(
                "Energy crosses a boundary",
                "Start with some stored energy and ask the battery to charge for one hour. The bus supplies more energy than reaches storage. Change the round-trip efficiency and watch both sides of the balance respond.",
                [
                    C("energy", "Starting energy", 200, 0, 800, 10, "kWh"),
                    C("charge", "Charging request", 100, 0, 400, 10, "kW"),
                    C("discharge", "Discharging request", 0, 0, 400, 10, "kW"),
                    C("efficiency", "Round-trip efficiency", 0.9, 0.5, 1, 0.01),
                ],
                "E_end = E_start + η × charge × Δt − discharge × Δt / η",
                [
                    ("E_start", "Energy at the beginning of the interval, in kWh."),
                    ("η", "Each direction uses the square root of round-trip efficiency."),
                    ("Δt", "One hour in this teaching fixture."),
                ],
            ),
            P(
                "The limits are part of the model",
                "Charging and discharging are mutually exclusive. A request beyond available energy or storage headroom is infeasible. This isolated component reports the violated condition; the plant dispatch layer is responsible for choosing an achievable action.",
            ),
            P(
                "Two routes to the same balance",
                "Switch between the direct equation and the loss ledger. They describe the same constant-efficiency battery. The 100 kWh round-trip check independently expects 100 times the configured round-trip efficiency back at the bus.",
                [
                    C(
                        "implementation",
                        "Implementation",
                        "affine/1",
                        options=["affine/1", "loss-ledger/1"],
                    )
                ],
            ),
        ],
        "No physical ageing, self-discharge, temperature response or SOC-dependent efficiency. Usage wear is an economic allowance, not capacity fade.",
    ),
    "solar": topic(
        "From sunlight to the DC bus",
        "Physical plant",
        ["solar", "reference_pv"],
        ["solar_model.py", "pv.py"],
        "A section converts incident light into electrical power. The model exposes each approximation on the path to the bus.",
        [
            P(
                "Turn a section toward the light",
                "All three sections share the settings in this example. Orientation changes the projection relative to a saved reference plane; it is a sensitivity calculation using an assumed diffuse fraction, not measured direct and diffuse channels.",
                [
                    C("tilt", "Panel tilt", 30, 0, 90, 1, "°"),
                    C("azimuth", "Azimuth, south = 0", 0, -180, 180, 5, "°"),
                    C("shade", "Uniform shading", 0, 0, 0.9, 0.05),
                ],
                "Section light = reference irradiance × orientation factor",
                [
                    (
                        "orientation factor",
                        "Illustrative 30% diffuse sky, normalized to the reference plane.",
                    )
                ],
            ),
            P(
                "Brightness is only the beginning",
                "Change ambient temperature or the cell-temperature assumption. Warmer cells change output even when the light is unchanged. Uniform shading and soiling act at section level; the drawn tiles are schematic.",
                [
                    C("ambient", "Ambient temperature", 20, -10, 45, 1, "°C"),
                    C("noct", "Nominal cell temperature", 45, 20, 80, 1, "°C"),
                    C("soiling", "Soiling fraction", 0, 0, 0.5, 0.01),
                ],
                "T_cell = T_ambient + (NOCT − 20) × irradiance / 800",
                [
                    (
                        "NOCT",
                        "Illustrative nominal operating cell temperature; not site calibration.",
                    )
                ],
            ),
            P(
                "A converter can become the bottleneck",
                "Reduce the converter capacity to clip generation. Clipping happens before the DC bus. Plant curtailment happens when the plant cannot use available bus power; this isolated example does not dispatch the plant.",
                [C("converter", "Converter capacity", 1000, 100, 1200, 25, "kW")],
            ),
        ],
        "No string I–V curves, bypass diodes, geometric row shading, tracking or measured panel telemetry. This teaching fixture has uniform editable soiling and no service missions. Opt-in section-cleaning plant runs compose recorded loose, adhered and damage transmission before this same conversion kernel; dry brushing changes only treated loose material, while the optional portable wet method also reduces its declared adhered fraction and consumes finite water/operator time. Permanent damage remains unchanged. A static design preview does not replay those service decisions.",
        [
            "https://open-meteo.com/en/docs",
            "https://pvpmc.sandia.gov/modeling-guide/1-weather-design-inputs/plane-of-array-poa-irradiance/",
        ],
    ),
    "electrolyser": topic(
        "Turning electricity into hydrogen",
        "Physical plant",
        ["electrolyser"],
        ["electrolyser.py"],
        "Electrolysis consumes electricity and water. Starting also consumes energy, before productive conversion is counted.",
        [
            P(
                "A productive load has a yield",
                "The six-hour example runs at the requested load for the selected number of hours, then stops. Start and stop the sequence with the interval control. Productive load must be zero or at least 135 kW.",
                [
                    C("load", "Productive load", 275, 0, 450, 5, "kW"),
                    C("sec", "Specific electricity", 55, 40, 80, 1, "kWh/kg"),
                    C("run_hours", "Hours before stopping", 3, 1, 6, 1, "h"),
                ],
                "Hydrogen = productive electricity / specific electricity",
                [
                    ("productive electricity", "Excludes separately accounted startup energy."),
                    ("specific electricity", "Constant conversion assumption, in kWh per kg H₂."),
                ],
            ),
            P(
                "Starting leaves a separate footprint",
                "Compare the first running interval with the next. Startup electricity is counted separately; water consumption is nine kilograms per kilogram of hydrogen. The initial on/off state determines whether the first interval is a start.",
                [C("initial_on", "Initially operating", "no", options=["no", "yes"])],
            ),
            P(
                "Water is an input",
                "The reactor produces water downstream, but this plant assumes no recycling credit. An isolated conversion example has sufficient supplied power; the bus essay shows electrical competition.",
            ),
        ],
        "Constant specific electricity and a fixed start allowance. No pressure, stack temperature, purity or physical degradation model.",
    ),
    "hydrogen": topic(
        "A buffer is a balance over time",
        "Physical plant",
        ["hydrogen"],
        ["storage.py"],
        "Hydrogen storage connects production now with methane demand later. Inflow and outflow can occur during the same hourly interval.",
        [
            P(
                "Follow the kilograms",
                "Choose starting inventory and concurrent inflow and withdrawal. Five kilograms of hydrogen can support ten kilograms of methane if CO₂, electricity and temperature also permit it.",
                [
                    C("inventory", "Starting inventory", 20, 0, 60, 1, "kg"),
                    C("inflow", "Interval inflow", 8, 0, 20, 0.5, "kg"),
                    C("outflow", "Interval withdrawal", 5, 0, 30, 0.5, "kg"),
                ],
                "Inventory_end = inventory_start + inflow − withdrawal",
                [
                    ("withdrawal", "A material request, not a guarantee of methane production."),
                    ("inflow", "Concurrent over the interval; not silently vented."),
                ],
            ),
            P(
                "Storage is finite",
                "If the requested interval would overfill or empty the tank, the example reports an infeasible balance. There is no unrecorded venting to make the numbers work.",
            ),
            P(
                "A second implementation",
                "The direct balance and ledger are equivalent accounting formulations. Their role is to test replacement without changing the meaning of inventory.",
                [
                    C(
                        "implementation",
                        "Implementation",
                        "balance/1",
                        options=["balance/1", "ledger/1"],
                    )
                ],
            ),
        ],
        "This isolated inventory example has no pressure, leakage, compression or gas quality. Optional deployment interfaces add declared regulated pressures and specified compression electricity; they do not simulate vessel pressure or certify gas quality. Hydrogen inventory alone does not establish downstream feasibility.",
    ),
    "co2": topic(
        "Deliveries arrive before withdrawal",
        "Physical plant",
        ["co2"],
        ["storage.py"],
        "Supplied CO₂ is scheduled feedstock. Tank headroom determines how much of a delivery is accepted.",
        [
            P(
                "Make room before the truck arrives",
                "Move a delivery within this six-hour sequence. Each hour accepts feedstock against beginning inventory, then withdraws material. Delaying a delivery can therefore cause an earlier shortage.",
                [
                    C("inventory", "Starting inventory", 100, 0, 1000, 25, "kg"),
                    C("delivery", "Delivery quantity", 300, 0, 1200, 25, "kg"),
                    C("arrival", "Delivery interval", 2, 0, 5, 1, "h"),
                    C("outflow", "Hourly withdrawal", 20, 0, 100, 5, "kg"),
                ],
                "Accepted = min(delivery, capacity − starting inventory)",
                [
                    ("Accepted", "Only this portion enters the buffer."),
                    ("delivery", "Rejected excess remains explicitly recorded."),
                ],
            ),
            P(
                "Feedstock places a ceiling on methane",
                "Every kilogram of methane needs 2.75 kg CO₂ under the rounded stoichiometry. Rejected delivery is not counted as stored material, and a later withdrawal does not retroactively create delivery headroom.",
            ),
        ],
        "Scheduled supplied CO₂, not direct-air capture. No transport emissions, purity, pressure or supply-market dynamics.",
    ),
    "reactor": topic(
        "Keeping the reactor ready",
        "Physical plant",
        ["reactor"],
        ["reactor.py", "physics.py"],
        "A warm reactor carries a useful state into the future. Chemistry releases heat, while its surroundings continually remove it.",
        [
            P(
                "Warm up before producing",
                "Follow twelve hourly intervals. An explicit teaching policy heats until production is thermally feasible, requests the configured methane output, and regulates cooling. Shared electricity and feedstock are supplied for this local thermal example.",
                [
                    C("heater", "Heater request", 60, 0, 60, 5, "kW"),
                    C("ambient", "Ambient temperature", 20, -10, 40, 1, "°C"),
                    C("loss", "Heat-loss coefficient", 0.08, 0.01, 0.2, 0.01, "kW/K"),
                    C("methane", "Methane request", 10, 0, 10, 1, "kg/h"),
                ],
                "C × dT/dt = heater + reaction heat − UA(T − ambient) − cooling",
                [
                    ("C", "Lumped thermal capacity: 0.3 kWh/K."),
                    ("UA", "Heat-loss coefficient, in kW/K."),
                    ("reaction heat", "165 MJ/kmol CH₄ using rounded molecular weights."),
                ],
            ),
            P(
                "A chemical balance is also a heat source",
                "The ideal reaction consumes 0.5 kg H₂ and 2.75 kg CO₂ per kg methane, producing 2.25 kg water. Inspect heating, reaction heat, heat loss and rejected heat separately.",
            ),
            P(
                "Account for cold feed explicitly",
                "This learning sequence retains the original heat coefficient. In Project → Equipment & evidence → Plant interfaces, the optional NIST model separates gross reaction heat from feed heating. Its editable reference temperature and recuperation are frozen for each design. Preview shows their net heat; saved intervals retain the operands. Heat capacity and ambient heat loss remain assumptions, and the controlled-coolant slurry fit is not transferred to this reactor.",
            ),
            P(
                "A commitment meets a physical limit",
                "Cut the supplied feedstock at a chosen interval. The operating-state model records a forced trip if a four-hour commitment cannot continue. Physical feasibility takes precedence.",
                [C("cutoff", "Feedstock supplied until interval", 12, 1, 12, 1, "h")],
            ),
        ],
        "Analytic constant-input intervals; no reaction kinetics, pressure design, gas certification or water recycling.",
        ["https://doi.org/10.1039/D5RE00337G"],
    ),
    "bus": topic(
        "Several machines share one bus",
        "Physical plant",
        ["battery", "electrolyser", "reactor"],
        ["physics.py", "dispatch.py"],
        "Every electrical request competes for the same available power. A feasible plant action must balance the bus and material flows together. Equipment & evidence can enable a separate AC island, external cooling/drying and finite purified-water supplies for deployment studies. This teaching example retains the original abstract DC bus; an enabled deployment records the extra balances beside its original decisions.",
        [
            P(
                "Ask for more than the sun supplies",
                "This six-hour example begins with a warm reactor and stored gas. Adjust solar power and productive demand. The existing execution allocator finds feasible applied actions and records unmet requests.",
                [
                    C("pv", "Available solar", 300, 0, 1000, 25, "kW"),
                    C("load", "Electrolyser request", 275, 0, 450, 5, "kW"),
                    C("reserve", "Starting battery energy", 300, 0, 800, 25, "kWh"),
                ],
                "Solar + discharge = demand + charge + unused solar",
                [
                    (
                        "demand",
                        "Electrolysis, startup, reactor auxiliaries, heating and cooling electricity.",
                    ),
                    ("unused solar", "Explicit energy not harvested."),
                ],
            ),
            P(
                "Inspect conversion and cooling boundaries",
                "Optional plant interfaces add a capacity-limited AC island and finite purified water. Research options in Equipment & evidence expose a published inverter analogue, reference-state electrolysis heat and a dry-cooler envelope that loses capacity in hot weather. Their preview is a learning calculation; saving creates a new design for future runs. These source-scoped equations do not establish an OEM envelope or field calibration. The six-hour teaching sequence here retains the original abstract bus.",
            ),
            P(
                "Today’s reserve becomes tomorrow’s option",
                "Solar disappears halfway through the sequence. Step into the dark intervals and compare the battery, gas inventories and reactor state. Requested actions remain visible beside applied actions.",
            ),
        ],
        "A six-hour teaching request schedule, not an optimized policy. Execution uses a bounded solver and may fall back.",
    ),
    "weather": topic(
        "What could the controller know?",
        "Information and control",
        ["weather"],
        ["forecast.py", "timebase.py"],
        "A forecast has an issue time and an availability time. A historical reference describes another kind of information.",
        [
            P(
                "Move across the publication boundary",
                "These explicitly synthetic saved issues illustrate a six-hour publication lag. The newer issue becomes eligible at 12:00 UTC. Move the decision clock and inspect the issue actually selected.",
                [
                    C("hour", "Decision hour, UTC", 11, 6, 17, 1, "h"),
                    C("lag", "Assumed publication lag", 6, 0, 12, 1, "h"),
                    C("missing", "Remove next required hour", "no", options=["no", "yes"]),
                ],
                "Eligible issue: available_at ≤ decision_time",
                [
                    (
                        "available_at",
                        "Issue initialization plus the declared assumed publication lag.",
                    ),
                    ("decision_time", "UTC boundary, before taking the decision."),
                ],
            ),
            P(
                "An hourly average belongs to an interval",
                "Radiation supplied as a preceding-hour average is associated with the preceding interval during normalization. The plant schedules hourly mean PV. Local labels include timezone offsets; computation uses UTC.",
            ),
            P(
                "Reference is not observation",
                "ERA5 is reanalysis, not a site measurement. The second curve is a synthetic historical reference illustrating that role, not actual ERA5 data. It never enters forecast selection. Forecasts, reanalysis, synthetic scenarios and sensor readings retain different origins. Removing a required sample yields an incomplete-data result, not substituted weather.",
            ),
        ],
        "The editable example contains synthetic issue fixtures, not a live forecast download.",
        [
            "https://open-meteo.com/en/docs/single-runs-api",
            "https://open-meteo.com/en/docs/historical-weather-api",
        ],
    ),
    "diagnosis": topic(
        "An anomaly needs evidence",
        "Information and control",
        [],
        ["sensing.py"],
        "The controller receives noisy observations. The teaching harness knows the injected fault; the diagnostic function does not.",
        [
            P(
                "Compare independent channels",
                "Step through twenty-four intervals. This teaching example explicitly uses a transient disturbance beginning at interval three and clearing at interval eight. New plant faults instead persist until repair unless a transient lifecycle is chosen. Compare requested power, the electrical meter, the flow meter and the independent inventory balance.",
                [
                    C(
                        "fault",
                        "Teaching scenario",
                        "capacity",
                        options=["normal", "capacity", "flow", "low activity", "ambiguous"],
                    ),
                    C("noise", "Sensor noise fraction", 0.02, 0, 0.1, 0.01),
                    C("threshold", "Discrepancy fraction", 0.1, 0.01, 0.5, 0.01),
                    C(
                        "ambiguity_policy",
                        "Response to disagreeing channels",
                        "reduce-capacity/1",
                        options=["reduce-capacity/1", "retain-capacity/1"],
                    ),
                ],
                "Threshold = max(discrepancy fraction, 3 × noise fraction)",
                [
                    (
                        "noise fraction",
                        "Seeded measurement noise; two consecutive informative intervals are required.",
                    ),
                    (
                        "discrepancy fraction",
                        "Relative residual threshold, not a probability of fault.",
                    ),
                ],
            ),
            P(
                "Silence does not mean health",
                "Low activity leaves insufficient evidence. Disagreeing channels can remain ambiguous. A biased flow channel can be isolated while independent balance supplies the usable estimate. The original ambiguity rule reduces the capacity estimate using measured power minus the discrepancy margin, even at a partial load. The experimental retain-capacity rule holds the preceding estimate instead. It does not establish health, restore capacity or identify which channel is wrong. All other thresholds and recovery rules are unchanged. Compare the ambiguous teaching scenario to see this isolated policy difference.",
            ),
            P(
                "Recovery must be earned",
                "The harness requests small upward load probes after derating, while retaining supplied power and tank headroom. Only successful measured tracking restores the estimate. An incident is counted once when confirmed. In new plant runs this is not a repair: explicit service work incurs costs, physical restoration requires a compatible successful action, and the controller still verifies recovery. Older archives retain their alarm-based cost allowance.",
            ),
        ],
        "A bounded diagnostic study: ideal battery/CO₂/temperature sensors, throughput-scaled tank noise and only the stated fault cases. Opt-in service runs also offer fixed and rover contact measurements with internal reference checks, delayed publication, reader drift/dropout and shared-contact failures. Reference checks can isolate a reader; agreement cannot rule out a shared stuck contact. Support runs distinguish a robot's physical retrieval from its later supervised drive-test evidence. The optional service-hardware model adds ideal command feedback, bounded control release, typed module replacement and a separate test for each procedure. A later repair cannot verify an earlier failed release. This teaching fixture does not simulate those service workflows or arbitrary mechanical repair.",
    ),
    "controllers": topic(
        "Planning with the same information",
        "Information and control",
        [],
        ["dispatch.py", "forecast.py", "policy.py"],
        "The objectives differ, but the starting state, forecast, prices and physical constraints are shared.",
        [
            P(
                "Choose how far ahead to look",
                "Calculate three plans from a warm plant with stored hydrogen. The fixture includes a night-time deficit. Change the planning horizon or forecast stress and compare all three policies.",
                [
                    C("horizon", "Forecast horizon", 12, options=[6, 12, 24, 48]),
                    C("bias", "Forecast scaling bias", 0, -0.6, 0.6, 0.1),
                ],
                "Economic objective = assumed methane value − variable inputs − usage wear",
                [
                    ("assumed methane value", "An illustrative value, not contracted revenue."),
                    (
                        "usage wear",
                        "Action-sensitive allowances; fixed ownership does not enter dispatch incentives.",
                    ),
                ],
            ),
            P(
                "A schedule is a prediction",
                "The plan uses only its supplied information. Read methane, thermal trajectory, ending inventories and active operating limits together. More output within the horizon does not imply a better continuing position.",
            ),
            P(
                "Test a value for continuing operation",
                "Related studies compare methane MPC with the same planner given an explicit value for battery energy left at the horizon. That continuation assumption changes one objective coefficient. It is neither methane output nor sale proceeds, and it does not impose a minimum safety reserve. The standard teaching comparison above retains its original three policies.",
            ),
            P(
                "The search can stop before the answer is proved",
                "Each MPC solve keeps the configured 0.5-second limit. Termination, gap and fallback are shown. Equivalent formulations can lead to different feasible schedules under a time limit; MPC is not required to win.",
            ),
            P(
                "Keep future choices conditional",
                "The experimental service scheduler can compare declared work windows under several weather outcomes. It requires the same current action until an observation distinguishes those outcomes. Procedure deadlines, ending plant reserves and service-stock reserves are explicit constraints. A feasible inspection schedule does not establish the value of its unknown finding, and completing a repair does not automatically confirm recovery. The standard teaching comparison retains its existing policies. Ordinary simulation uses the local service rule unless coordinated services is enabled.",
            ),
            P(
                "Revisit a recorded service choice",
                "The Site services comparison uses the selected decision's saved forecast, estimates, dispatch prices and work commitments. It can postpone work, raise an original joint charging target, or choose a saved compatible contact-reading or section-cleaning procedure. Installed equipment is fixed by that original context. A different section cannot lend its treatment duration, and a mobile reader does not earn an assumed useful finding. Travel, resources and any shared return are rechecked. Older recordings without those original choices say that the information is missing. The completed run remains unchanged.",
            ),
            P(
                "Ask whether a finding changes the remedy",
                "Saved investigation examples compare immediate qualified replacement with an inspection followed by a compatible conditional action. A closed prepared contact permits a reset, but can also be a shared stuck contact on damaged equipment. The declared prior and reader noise determine the branch weights; they are not calibrated fault probabilities. An interrupted mobile read produces no contact evidence and leaves the rover awaiting recovery. Energy, stocks, crew lead and test requests remain explicit in each branch. Hidden procedure success cannot change a requested schedule. If a possible continuation cannot be completed, the comparison keeps that gap rather than discarding the branch. The opt-in observed-service investigation policy can now commission its selected present request and choose a later remedy from the actual eligible finding. Only commissioned readers contribute to its contact decision; older policies retain their configured-reader semantics. A static prior becomes inapplicable after intervention. Post-service load tests can justify a bounded qualified follow-up without inventing a new posterior. The episode keeps its original deadline and remains open until observer confirmation or explicit escalation. Investigation version 2 uses the same bounded upward test target as the operating scheduler. After an actual eligible finding, every remaining latent branch must agree on the remedy and test before it becomes a nominated follow-up. Joint recovery version 2 then rechecks that work, its complete return, charging and process demand before accepting an absolute test window. A later accepted window can differ from the original conditional prediction; both are recorded with the original deadline. Repeated actual failed tests can nominate qualified follow-up without renewing the static prior. New planning snapshots preserve eligible procedure and crew-return receipts; older snapshots explicitly lack this evidence. Investigation version 3 optionally carries the original incident hypotheses through observed reset or replacement attempts and actual informative power tests. It records a conditional restoration probability without reading repair-success truth. A separate stuck contact can remain closed after a restored module. Repeated resource-feasible shortfalls remain necessary before its additional impairment-probability gate permits another repair. The declared procedure reliability, point impaired-capacity estimate and static reader hypotheses are illustrative, not calibrated probabilities. Only operating observation checks confirm recovery. Unmodelled interventions or unsupported measurements leave the probability unavailable, and the original deadline remains. At a saved resolved selection, the Site services comparison can revisit inspect-first versus direct intervention using that original snapshot, belief, forecast and prices. Later intervals return to the original choice before calculating. Both strategies are recalculated with current code; original predictions remain separate. Expected inventories and costs average hypothetical branches, while branch-specific thermal paths and unfinished work remain visible. Incomplete branches are never discarded, and the original restoration requirement still governs eligibility. These initial-choice alternatives do not use later recovery observations or revise an ongoing incident belief. Probability calibration remains outside this bounded model.",
            ),
            P(
                "Follow the test after a completed repair",
                "A completed substitution can still leave the plant derated. Opt-in coordinated service version 3 checks actual post-return load requests against electrical readings and the independent hydrogen inventory balance. The original estimated state and current power must support that requested test. Inactivity adds no evidence; ambiguous channels, infeasible tests and supported tracking cannot authorise a repeat. Repeated same-load shortfalls within the declared window can request a separate qualified attempt, retaining the original deadline, finite spares and attempt limit. The retry wait starts when enough evidence first exists; later failed tests do not postpone it. Exhausting the attempt budget leaves an explicit escalation. This bounded rule does not identify the physical cause or claim that a further substitution will help. Only the existing observer confirms recovery.",
            ),
            P(
                "Reserve an operating test",
                "Experiment setup can enable scheduled recovery tests. The controller searches for the earliest feasible sequence of consecutive upward load requests while retaining an explicit ending battery reserve. It checks both tracking and unchanged-delivery hypotheses with the same requested actions. The test can use stored electricity. Actual electrical and inventory observations must confirm the result; a performed reset only permits another test. Failed or inconclusive tests wait before retrying. During these episodes Greedy uses the methane MPC subplanner, so this is a changed recovery-policy package, not unchanged Greedy operation. Recovery version 2 jointly selects work, dock power and process requests for coordinated MPC. An accepted test window constrains subsequent planning until observed progress consumes it or an explicitly recorded interruption releases it. New procedure receipts, failed tracking and missing feasible continuations do not silently move the original deadline. Charging uses the same beginning-inventory, return-reserve, solar-availability and pooled-cost rules as the ordinary dock planner. Both delivery hypotheses share charging and requested process actions until an observation distinguishes them. Recorded service and process alternatives retain the accepted test and original energy deadlines. Greedy retains recovery version 1 and the local service rule; the exact per-controller policies are saved. None of these planning checks calibrate the assumed probability of tracking or establish physical recovery.",
            ),
        ],
        "Predicted single-horizon comparisons, not realized full-run performance. No future fault truth enters the planner. Service task selection defaults to a separate local rule. Opt-in coordinated service version 1 compares bounded single-request start times, current robot charging and production together. Version 2 also offers contiguous shared crew groups from up to eight currently compatible requests; unsearched groups and budget-limited candidates remain recorded. It retains original work/energy deadlines, interrupted-repair attempts and unmet obligations; its service pane shows the recorded candidates and fallbacks. Conditional cleaning uses observed surface/brush state and the eligible forecast, not a future treatment result. Version 1 creates separate new visits. Version 2 reserves each shared itinerary, prices one callout and retains separate job effects and verification. An interrupted early job can prevent later jobs. Neither version optimises contingent remedies or general fleet routing. Optional scheduled recovery anticipates accepted service demand, requests consecutive tests and updates capacity only through actual observations. Its earliest-feasible test priority, branch probabilities, retry interval and ending reserve are declared assumptions; it is not a calibrated value-of-information policy or the complete joint service supervisor. The experimental mission selector does not infer useful findings, future stock deliveries or charging credits. Shared visits use already-known feasible jobs, available stocks and current crew readiness; future restoration or replenishment is not assumed. A candidate can reserve one crew journey. Another separate departure requires an observed return, so an unsupported two-trip projection is explicitly infeasible. This teaching comparison does not optimise their timing or itinerary. The standard learning example retains its original three policies.",
    ),
    "economics": topic(
        "Which costs can this action change?",
        "Economics and experiments",
        [],
        ["costing.py", "service_economics.py"],
        "An ownership allocation answers a different question from a dispatch incentive. Both use the same physical trace. Recorded finite-logistics runs can also retain complete service accounting: period allocation, action-dependent costs and modelled expenditure are distinct views. Their original service prices remain frozen; a repriced report carries its own price identity.",
        [
            P(
                "Reprice the same operation",
                "Change the illustrative prices and asset life. The fixed six-hour trace is never re-dispatched. Its methane, inventory and starts remain unchanged.",
                [
                    C("price", "Methane value", 1, 0, 5, 0.1, "€/kg"),
                    C("co2_price", "CO₂ price", 0.15, 0, 1, 0.05, "€/kg"),
                    C("life", "New-asset ownership life", 20, 5, 40, 1, "years"),
                    C(
                        "output",
                        "Teaching trace",
                        "producing",
                        options=["producing", "zero output"],
                    ),
                ],
                "Contribution = assumed output value − variable inputs and usage wear",
                [
                    (
                        "Contribution",
                        "Excludes fixed ownership allocation and speculative inventory sale value.",
                    ),
                    (
                        "usage wear",
                        "For replaceables, allocation uses the larger of calendar or usage allowance, not their sum.",
                    ),
                ],
            ),
            P(
                "Ownership still belongs in the report",
                "The allocated view includes ownership, standing operation, consumables and interventions. Inspect component allocations and decision costs separately. Fixed ownership cannot steer the original dispatch. In service runs, an executed routine procedure consumes crew time and kits separately from the calendar maintenance allowance, which excludes those recorded costs. Completing routine work does not imply that an injected fault was repaired or that equipment life increased.",
                [
                    C(
                        "reactor_life",
                        "Replaceable reactor operating life",
                        60000,
                        10000,
                        100000,
                        1000,
                        "hours",
                    )
                ],
            ),
            P(
                "No output means no unit cost",
                "A zero-output example still incurs period costs, but cost per kilogram is undefined. Ending inventories are reported physically without assigning speculative sale proceeds.",
            ),
            P(
                "Price activity from its recorded interval",
                "The optional second service-price version derives hardware activity from original mission intervals, including fixed readers and chargers. The first version retains its older activity counters. A prospective service decision prices the difference in the accumulated usage-and-parts pool, so a part already charged is not added again as wear. Missing original intervals, applicable prices or the disposition of a future delivery remain explicit gaps. Candidate pricing version 2 distinguishes routine kit-consuming procedures from deliveries: a routine procedure has no destination stock to accept or reject. Version 3 also prices registered dock activity and input electricity without requiring the disposition of a purchased material. Delivered robot energy remains a separately checked conditional inventory. These changes affect candidate eligibility; saved decisions keep their original pricing implementation. A feasible physical comparison can still have incomplete costs, which remain undefined. The teaching trace above contains no service work.",
            ),
        ],
        "Illustrative prices, linear capital scaling and usage allowances; no financial return, settlement or physical ageing claim. This fixed teaching trace has no field-service missions. Support-enabled runs record remote time, brush replacements, portable tool hire, cleaning water, typed hardware modules and rejected supplies as unpriced quantities until their full procurement and running-cost assumptions are provided; an unpriced quantity is not a zero-cost input. A combined visit incurs one actual departure callout while each job retains its hands-on and material charges. Full committed crew time remains a resource quantity, not an additional travel-labour charge under the current price basis.",
    ),
    "experiments": topic(
        "Read a comparison through to its boundary",
        "Economics and experiments",
        [],
        [
            "costing.py",
            "dispatch.py",
            "studies.py",
            "study_presentation.py",
            "study_service.py",
            "offline_model.py",
            "documentation.py",
            "field_studies.py",
            "computation_studies.py",
            "study_bundle_check.py",
            "evidence.py",
            "bundle.py",
        ],
        "Matched cases share declared background conditions. The tested intervention and reporting boundary determine which consequences are included.",
        [
            P(
                "Move the end of the comparison",
                "Compare two explicitly authored, feasible action schedules with identical starting state, weather and prices. One produces immediately; the other retains feedstock. The labels describe teaching schedules, not Greedy or MPC results.",
                [
                    C("window", "Included intervals", 3, 1, 6, 1, "h"),
                    C(
                        "schedule",
                        "Selected teaching schedule",
                        "produce",
                        options=["produce", "retain"],
                    ),
                ],
                "Period methane = sum of produced methane in included intervals",
                [
                    (
                        "Period methane",
                        "Separate from remaining hydrogen, CO₂ and battery inventories.",
                    )
                ],
            ),
            P(
                "Report the remainder",
                "Inspect all ending inventories and temperature alongside output and allocated cost. This comparison supplies a counterexample to interpreting a short period total in isolation.",
            ),
            P(
                "Playback and recomputation answer different questions",
                "Recorded playback replays saved actions. A numerical rerun executes a solver again and may produce a different feasible schedule. The linked saved comparison retains actual divergence rather than manufacturing exact agreement.",
            ),
            P(
                "Check computation before ranking a policy",
                "The repeated-computation Study executes unchanged seeds at declared process, service and investigation budgets. Repetitions are computation trials, not additional weather samples. Its table separates equality of recorded actions, states and public work histories from process solve quality. It requires all intervals and matching original input identities. Stable sampled repeats do not prove determinism or optimality; a process solve can meet its tolerance while the outer service comparison leaves candidates unsearched. Original gaps, fallbacks, exclusions and ending inventories remain available in each recording. The editable teaching example above retains its fixed schedules.",
            ),
            P(
                "Open details from the original publication",
                "The study workspace first loads selected recorded metrics and inventories. Detailed service histories are retrieved when selected, bound to that publication's original case, attempt and controller. A smaller display is a derived view, not a new simulation or a replacement archive. The index labels counts from the latest publication separately from running or interrupted work. Full original publications and attempts remain linked in offline reports; a missing or changed record produces an error instead of a reconstructed history.",
            ),
            P(
                "Follow a saved calculation offline",
                "New reproduction bundles retain original explanations and saved learning outputs in a model index, with linked interval calculations, parameters and evidence. These reading pages identify their calculation and reporting source separately from the original simulation. Complete service decisions and planning snapshots remain available as recorded data. Opening a page does not run a controller or train a model. Missing original explanations or examples remain missing; current material is not substituted as original evidence.",
            ),
            P(
                "Keep each recording, even when actions match",
                "Two executions can share a physical run identifier while retaining different solver timings, plans or study contexts. The full recording has its own integrity identity. New archives include that identity and never replace a different saved file; Studies also separates case directories. Before publication, the application checks each recording and its referenced audit and service artifacts. Missing or mismatched records cannot support a complete publication. Existing archives keep their original paths and meanings. Repeated exports preserve earlier bytes, returning a distinct filename when their contents change.",
            ),
            P(
                "A hardware comparison needs separate plants",
                "Studies can compare service packages through separate runs with matched weather and fault inputs. A package may change both sensing and repair options, so its overall result does not isolate the value of one robot. Inspect the declared changes, human work, missing prices and unfinished work alongside methane output. Cleaning questions separately record treated area, converter clipping and plant curtailment. Inspection questions count eligible evidence rather than assuming that a working pose reveals a fault. A prepared contact permits a compatible reading; it does not enable robotic module replacement. The editable teaching schedules above remain independent of these saved studies.",
            ),
            P(
                "A revised report need not be a new physical experiment",
                "A finished restoration procedure can still await an informative operating test; counting it does not establish physical success. New study publications preserve the reporting code separately from the original execution code. A corrected table is a new publication over the same recorded attempts, with its derivation available under Protocol and assumptions. Earlier reports remain intact. A missing original explanation or derivation is never replaced with today's documentation under its old identity.",
            ),
            P(
                "Match the event before comparing the outcome",
                "A shared seed does not by itself make two service policies comparable. The optional target/action/request model numbers accepted requests separately for each target and action. Rewording a reason, changing the actor or moving a job does not change that matched random draw. A cancelled accepted job keeps its number; an unaccepted candidate does not use one. Different procedures, conditions or success assumptions can still produce different physical outcomes. The draw is saved only in retrospective truth, never as evidence available to the controller. Existing protocols explicitly retain their original request-text mapping; changing the matching model is a recorded assumption shared across the comparison arms.",
            ),
        ],
        "Teaching schedules explain reporting, not controller rankings. Historical comparison evidence remains tied to its original source and configuration.",
    ),
}

TOPICS["siting"] = topic(
    "From a location to an operating case",
    "Sites and projects",
    [],
    [
        "siting/geometry.py",
        "siting/environment.py",
        "siting/production.py",
        "siting/checkpoint.py",
        "siting/cashflow.py",
        "siting/comparison.py",
        "siting/layout.py",
        "siting/utilities.py",
    ],
    "Site evidence, continuous operation and investment assumptions answer different questions. A strong resource does not establish a deployable parcel or profitable project.",
    [
        P(
            "Keep spatial evidence at its real resolution",
            "The toy parcel has one hectare. Change the portion excluded by a declared policy and the footprint reserved for equipment. Real Sites assessments union source geometries in EPSG:3035 before subtracting them. Overlapping exclusions count once. Missing land, terrain, national protection or flood coverage remains unresolved. A point is a regional anchor. Route drawings report lengths without inventing pipe, cable or robot performance.",
            [
                C("excluded", "Area excluded by policy", 0.2, 0, 1, 0.05),
                C("footprint", "Equipment footprint", 500, 0, 10000, 100, "m²"),
            ],
            "PV capacity = max(0, area − exclusions − footprint) × density",
            [
                ("area", "Parcel area in square metres"),
                ("density", "Illustrative 0.04 kW/m², not an engineered row layout"),
            ],
        ),
        P(
            "Weather becomes power, then operation",
            "Change the hourly plane-of-array irradiance. The current conversion kernel applies temperature and losses once. PVGIS reference PV output is a separate cross-check, not a second loss applied to this curve. ERA5 is reanalysis. Persistence uses the previous completed day; original ECMWF issues remain unavailable until their publication boundary. A continuous operating case carries inventories, heat, observer beliefs, service work and economic usage across saved partitions. The example below is a resource conversion, with no methane production claim.",
            [
                C("irradiance", "Hourly irradiance", 600, 0, 1200, 50, "W/m²"),
                C("ambient", "Ambient temperature", 20, -20, 45, 1, "°C"),
            ],
        ),
        P(
            "Cash is distinct from allocated cost",
            "The fixed teaching trace assumes 30,000 kg gross methane per year for ten years, €500,000 initial capital and €20,000 annual cash costs. Change acceptance and price while that physical trace stays fixed. The actual Sites ledger uses recorded hourly production and dated cost items. It excludes ownership allocation and usage wear already represented by capital and replacement cash. Missing quotations make complete NPV unavailable. No-build has zero new-project cash flow. Scenario ranges are not probabilities, and numerical repeats do not become weather samples.",
            [
                C("acceptance", "Accepted fraction", 0.8, 0, 1, 0.05),
                C("price", "Accepted methane price", 1, 0, 8, 0.1, "EUR/kg"),
                C("discount", "Real discount rate", 0.07, 0, 0.2, 0.01),
            ],
            "NPV = −capital + Σ(net cash / (1 + rate)^year)",
            [
                ("capital", "Initial cash expenditure"),
                ("net cash", "Receipts less cash costs; no depreciation charge"),
                ("rate", "Consistent real discount rate"),
            ],
        ),
    ],
    "Illustrative teaching geometry and fixed production, independent of any site study. No consent, grid import, gas certification, hydrogen sales, CO2 capture or investment recommendation. Service and fault assumptions retain their original calibration gaps. Supplied water bounds electrolysis separately from equipment-capacity estimates.",
    [
        "https://re.jrc.ec.europa.eu/pvg_tools/en/",
        "https://open-meteo.com/en/docs/historical-weather-api",
        "https://open-meteo.com/en/docs/single-runs-api",
    ],
)


TOPICS.update(service_topics(C, P, topic))
TOPICS.update(lifecycle_topics(C, P, topic))
TOPICS.update(learning_topics(C, P, topic))

TOPICS["controllers"]["files"] += [
    "control_port.py",
    "control_sessions.py",
    "control_session_worker.py",
    "control_sources.py",
    "control_storage.py",
    "control_replay.py",
    "simulation.py",
]
TOPICS["controllers"]["passages"].append(
    P(
        "A bounded external controller",
        "Agent control starts a separate simulation from frozen recording or saved project inputs, including disclosed site utilities. Committed checkpoints can carry physical state, diagnostic history and service obligations into a continued session; displayed estimates cannot serve as physical starting state. The operator and an explicitly granted MCP agent receive the same observation, estimated state and forecast boundary. A preview predicts a reference-policy action or six explicit process requests without advancing time. One accepted proposal advances one hour through the existing physical executor; requested and applied actions, solver fallback, observations, author and reason are retained. Recovery commitments protect their intervals and the configured service executive keeps responsibility for repairs. Grants can be restricted, paused, revoked or expired. Missing agent commands leave simulated time paused; they never cause an implicit dispatch. Each successful hour atomically saves the runtime, recording and public receipts. Interrupted sessions recover at that boundary with fresh authority and previews; accepted but uncommitted requests are not counted as completed. Numerical replay executes the saved process requests in a new edition and reports changed information and outcomes. It does not ask an external agent to infer again, and its original saved proposal predictions remain labelled. Private checkpoints and retrospective comparisons never cross the MCP observation boundary. Independent process checks treat service loads and initial runtime as recorded boundary conditions; they do not reconstruct a mid-history service mission. This is software scheduling, not real hardware control or proof of controller safety.",
    )
)

for key, item in TOPICS.items():
    item["id"] = key
    item["fixture_id"] = "dispatch-lab/learning/" + key + "/1"
    item["assumptions"] = [dict(id=key + "/scope/1", text=item["limitations"])]
    item["explicit_calculation"] = key in (
        "controllers",
        "estimators",
        "policies",
        "bus",
        "recovery",
        "charging",
        "maintenance",
    )

# New editable observer choice; archives retain their saved version-1 examples.
TOPICS["diagnosis"]["version"] = "2"
TOPICS["diagnosis"]["fixture_id"] = "dispatch-lab/learning/diagnosis/2"

TOPICS["controllers"]["passages"].append(
    P(
        "Return, test and escalate",
        "Recovery version 3 waits for the whole repair mission, including return, before opening a separate bounded verification window. The original diagnosis and service deadlines remain recorded, including misses. Joint planning allocates load-test and dock power from the same electrical balance. A resource-blocked test is inconclusive and consumes time within that window; it does not justify another repair. Repeated same-load measured shortfalls stop further probes and allow the existing finite service follow-up rule to consider a separate remedy. A missed verification deadline requires explicit escalation. A later completed remedy opens its own recorded window. Only actual observer confirmation supports restored operation. Earlier recovery policies retain their original retry semantics, and these policy windows are illustrative scheduling choices, not certified maintenance limits.",
    )
)
TOPICS["controllers"]["passages"].append(
    P(
        "Equipment uncertainty and individual jobs",
        "Service autonomy version 2 separates a persistent equipment factor from a fresh bounded multiplier for each accepted job. Completed and unfinished phase clocks update equipment-specific estimates without revealing private execution factors. Correlated phases of one job count once. A return journey can use that same job's observed travel factor; a future job retains fresh variability. An observation outside declared support makes the model inapplicable rather than silently widening its bounds. Studies can select this clock model explicitly. Observation calibration has a predeclared time holdout and records field versus simulated sources. No matched field duration dataset has yet calibrated these illustrative distributions.",
    )
)
TOPICS["controllers"]["passages"].append(
    P(
        "Plan with uncertain service time",
        "The opt-in autonomy model keeps physical phase clocks private within explicit resource-reservation bounds. Completed phase boundaries and right-censored elapsed work update a finite duration model; completion is distinct from verified recovery. Fixed, adaptive and risk-aware modes share the original assumptions. Risk-aware candidates combine declared weather regimes and shared duration quantiles with process dispatch, robot charging, recovery-test windows and terminal reserves. Current actions agree across all outcomes; future differences require an eligible observation. Bounds, weights and dependence are assumptions, not calibration. Shared visits and stranded-robot charging use conservative envelopes, and unresolved candidates retain their reason and feasible fallback. The first service system supports explicit current-only support outages; it does not predict an unavailable future timetable or optimise an entire contingent retrieval fleet.",
    )
)
TOPICS["experiments"]["passages"].append(
    P(
        "Separate learning effects from numerical variation",
        "The uncertain-service qualification programme saves matched fixed, adaptive and risk-aware editions and repeats their numerical execution without changing seeds. A no-op condition collapses duration support and observation error. Inspect matching physical and source identities, within-arm trace variation, solver limitations, ending inventories and unfinished work before comparing production or cost. A short stable sample is not evidence of realism, annual performance or optimality. The frozen programme can be repeated with a new plant basis without replacing its earlier editions.",
    )
)

TOPICS["controllers"]["passages"].append(
    P(
        "Weather-aware verification windows",
        "Opt-in recovery version 4 sets a finite deadline when the verification episode opens. It uses the currently eligible forecast, estimated inventories and operating limits to find a feasible load-test window. Later forecast changes cannot roll that deadline forward. If no feasible window is found within the bounded search, the original maximum wait remains. A missed deadline escalates; only actual observation tracking restores estimated capacity. This is an illustrative supervisory policy, not evidence that a repair succeeded.",
    )
)

TOPICS["controllers"]["passages"].append(
    P(
        "Separate appointments from recovery",
        "Recovery version 5 keeps the finite outer diagnosis or post-mission obligation intact. The joint planner chooses individual appointments within it; each successful measured increment reduces the remaining tests. Resource interruptions, failed tracking, later forecasts and numerical limitations never silently extend the deadline. A separate completed remedy opens a separately recorded verification episode. The recovery essay executes this mechanism.",
    )
)
