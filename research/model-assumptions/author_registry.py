"""Authored September 2026 review edition; rerun only after reviewing changed mechanics.

Classification is frozen into docs/assumption-review.json. Runtime never automatically
approves new fields or changed implementation bindings.
"""

import hashlib
import json
from pathlib import Path

from methane.assumptions import flatten, reference_configuration

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/assumption-review.json"
SOURCES = {}


def source(key, title, url, finding, boundary, access="Read primary documentation on 2026-09-12"):
    SOURCES[key] = dict(
        title=title, url=url, finding=finding, applicability=boundary, access=access
    )


source(
    "doe-pem",
    "DOE technical targets for PEM electrolysis",
    "https://www.energy.gov/cmei/fuels/technical-targets-proton-exchange-membrane-electrolysis",
    "The 2022 status table distinguishes stack electricity (51 kWh/kg) from system electricity (55 kWh/kg); later columns are targets. Performance, lifetime and cost must be considered together.",
    "Technology benchmark, not a matched 450 kW device. No support for the fixture startup energy, minimum load, fixed efficiency curve or European installed cost.",
)
source(
    "sam-pv",
    "SAM / PVWatts model documentation",
    "https://samrepo.nlr.gov/help/pvwatts.html",
    "Version 8 uses NOCT reference temperatures of 45°C for open-rack and 49°C for roof-mount; listed crystalline-silicon power coefficients are −0.37 and −0.35 %/°C. Module and converter models have separate boundaries.",
    "Reference model assumptions, not fitted site values. Dispatch Lab is not a PVWatts implementation; its simple NOCT and fixed diffuse fraction omit several mechanisms.",
)
source(
    "nist-h2",
    "NIST Chemistry WebBook: hydrogen",
    "https://webbook.nist.gov/cgi/cbook.cgi?ID=C1333740&Mask=1",
    "Molecular weight 2.01588; standard elemental reference enthalpy zero.",
    "Reference chemistry only, not an electrolyser conversion or purity guarantee.",
)
source(
    "nist-co2",
    "NIST Chemistry WebBook: carbon dioxide",
    "https://webbook.nist.gov/cgi/cbook.cgi?ID=C124389&Mask=1",
    "Molecular weight 44.0095; Chase gas formation enthalpy −393.52 kJ/mol.",
    "Standard-state gas thermochemistry; pressure, kinetics and process conversion require additional models.",
)
source(
    "nist-ch4",
    "NIST Chemistry WebBook: methane",
    "https://webbook.nist.gov/cgi/cbook.cgi?ID=C74828&Mask=1",
    "Molecular weight 16.0425; Chase gas formation enthalpy −74.87 kJ/mol.",
    "Supports ideal stoichiometric and standard heat comparisons, not reactor thermal capacity or kinetics.",
)
source(
    "nist-water",
    "NIST Chemistry WebBook: water",
    "https://webbook.nist.gov/cgi/cbook.cgi?ID=C7732185&Mask=1",
    "Molecular weight 18.01528; gas formation enthalpy −241.8264 kJ/mol in Chase Shomate coefficients.",
    "Water vapour basis. Do not substitute liquid-water enthalpy without accounting for condensation and recovery.",
)
source(
    "gum",
    "JCGM VIM: calibration",
    "https://jcgm.bipm.org/vim/en/2.39.html",
    "Calibration establishes a measurement relationship with uncertainties under specified conditions; it differs from adjustment and verification.",
    "Terminology and measurement practice. Simulation parameter fitting additionally needs an identifiable model and held-out validation.",
)
source(
    "uncertainty",
    "JCGM VIM: metrological compatibility",
    "https://jcgm.bipm.org/vim/en/2.47.html",
    "Uncertainty of a difference depends on both uncertainties and their covariance.",
    "Independent inventory differences do not inherit a percentage-of-flow uncertainty without an explicit measurement model.",
)
source(
    "forecast",
    "Open-Meteo single model runs",
    "https://open-meteo.com/en/docs/single-runs-api",
    "Archive preserves model initialisation. Hourly solar radiation is a preceding-hour average; GTI specifies tilt and south-zero azimuth.",
    "Initialisation is not publication. The configured six-hour availability lag is our replay assumption, not an observed delivery guarantee.",
)
source(
    "era5",
    "Open-Meteo historical weather",
    "https://open-meteo.com/en/docs/historical-weather-api",
    "ERA5 is a gridded reanalysis; historical datasets combine observations and modelling.",
    "External environmental reference, not site sensor truth or calibrated PV power. Use explicit ERA5 rather than changing best-match products.",
)
source(
    "atb",
    "2024 ATB utility PV plus battery",
    "https://atb.nrel.gov/electricity/2024/utility-scale_pv-plus-battery",
    "Assumes 85% grid-charge and 87% coupled-PV round-trip efficiency for a utility-scale reference design.",
    "Planning assumptions at a different scale and electrical boundary, not evidence that the fixture 90% is measured. Do not transplant US cost estimates.",
    "Official search-index extract; direct page fetch failed (502), 2026-09-12",
)
source(
    "soiling",
    "IEA PVPS: soiling losses",
    "https://iea-pvps.org/key-topics/soiling-losses-impact-on-the-performance-of-photovoltaic-power-plants/",
    "Soiling is spatially heterogeneous and requires local measurement; snow is a separate concern at higher latitudes.",
    "Global annual loss estimates cannot establish a constant European daily deposition rate or a robot cleaning efficacy.",
)
source(
    "pv-validation",
    "Sandia PV performance modelling and validation",
    "https://www.sandia.gov/research/publications/details/pv-performance-modeling-and-stakeholder-engagement-final-technical-report-2024-09-30/",
    "Reports public quality-controlled PV/weather datasets and independent blind model comparisons.",
    "Useful candidate for testing a generic PV model. These observations do not describe our unnamed European array.",
)
source(
    "field-review",
    "Existing field realism review and sources",
    "research/field-realism-review/report.html",
    "Fourteen families reviewed; cause-specific repair, sensor identifiability and support requirements remain open.",
    "Retained historical review, not current-run validation. Relevant current source files were reviewed again for this edition. The 31 prior findings are retained separately.",
)
source(
    "rsc",
    "Monning et al.: three-phase CO₂ methanation kinetics",
    "https://pubs.rsc.org/en/content/articlepdf/2026/re/d5re00337g",
    "Reports ideal Sabatier heat of −165 kJ/mol and studies catalyst wetting, side reactions and deactivation in a three-phase slurry system.",
    "Supports exothermic chemistry and the importance of heat management; does not calibrate the fixture lumped thermal mass, heat loss or production envelope.",
    "Primary abstract and indexed first-page PDF extract read; direct HTML returned 403, 2026-09-12",
)

GROUPS = {}


def group(
    key,
    title,
    topics,
    mechanism,
    boundary,
    next_data,
    files,
    sources=(),
    checks=(),
    priority=1,
    status="Evidence gap",
):
    files = [*files, "methane/uncertainty.py"]
    if key in ("solar", "weather", "cleaning", "control", "coupling", "experiment", "recovery"):
        files += ["methane/adaptation.py", "methane/performance_reference.py"]
        checks = [*checks, "tests/test_adaptation.py"]
    checks = [*checks, "tests/test_uncertainty.py"]
    GROUPS[key] = dict(
        id=key,
        title=title,
        topics=topics.split(),
        mechanism=mechanism,
        boundary=boundary,
        next_data=next_data,
        sources=list(sources),
        checks=list(checks),
        priority=priority,
        evidence_status=status,
        bindings={p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in files},
    )


base = ["methane/config.py", "plant.py", "methane/contracts.py"]
group(
    "layout",
    "Capacities and initial conditions",
    "solar battery hydrogen co2 electrolyser reactor experiments",
    "Installed capacities and starting inventories define the test plant. They are choices, not population estimates.",
    "The fixture is not a named, coherent equipment package. Changing capacity alone does not resize vessels, converters, pumps, access or thermal mass.",
    "Choose a bill of materials and electrical/material boundaries; record working versus nominal capacity and starting-state measurements.",
    base,
    checks=["tests/test_boundaries.py"],
    status="Design choice",
)
group(
    "thermal",
    "Reactor heat and operating envelope",
    "reactor",
    "One perfectly mixed temperature; constant inputs per hour; analytic heating, reaction heat, ambient heat loss and cooling. Production requires beginning and ending temperatures in band.",
    "C=0.3 kWh/K and UA=0.08 kW/K are unmeasured. No spatial hot spots, catalyst kinetics, feed sensible heat, pressure, conversion efficiency, condensation or purge. The 4-hour commitment is a scheduling assumption.",
    "Obtain reactor geometry/material masses, insulation and catalyst specifications; log heater power, ambient and multiple temperatures through controlled warm-up, soak and cool-down, then separate load-step validation.",
    base + ["methane/reactor.py", "methane/physics.py"],
    ["nist-ch4", "nist-co2", "nist-water", "rsc"],
    ["tests/test_components.py", "tests/test_methane.py"],
    0,
)
group(
    "chemistry",
    "Stoichiometry and product boundary",
    "reactor electrolyser hydrogen co2",
    "Ideal CO₂ + 4H₂ → CH₄ + 2H₂O. Rounded molecular weights 44, 2, 16 and 18; reaction heat 165 MJ/kmol. Electrolysis consumes 9 kg reaction water/kg hydrogen.",
    "Conservation of the reduced chemistry can be verified. Complete conversion, pure feed and no gas-quality acceptance remain assumptions. Product water vapour heat basis is not liquid-water heat recovery.",
    "Specify feed composition, conversion and recycle/purge boundaries; measure gas composition and water before extending product or heating claims.",
    ["methane/physics.py", "methane/reactor.py", "methane/electrolyser.py"],
    ["nist-h2", "nist-co2", "nist-ch4", "nist-water"],
    ["tests/test_components.py"],
    0,
    "Physical relationship with approximations",
)
group(
    "electrolyser",
    "Electrolyser system performance",
    "electrolyser diagnosis",
    "A constant 55 kWh/kg converts productive bus electricity to hydrogen. Startup consumes 40 kWh in the same interval, without a separate warm-up delay. Minimum load is 30%.",
    "55 matches a DOE 2022 system benchmark numerically, not a particular plant calibration. A DC-bus input needs an explicit rectifier/balance-of-plant boundary. Startup, standby, turndown, pressure and load-dependent efficiency are not established.",
    "One matched supplier curve with system boundary, pressure, purity and temperature; startup/standby traces and degradation history, then validate at held-out loads.",
    base + ["methane/electrolyser.py"],
    ["doe-pem"],
    ["tests/test_components.py", "tests/test_startup.py"],
    0,
)
group(
    "battery",
    "Battery losses and power limits",
    "battery",
    "Charging and discharging use symmetric square-root efficiencies; constant power and usable energy constraints. Two execution implementations share this contract.",
    "90% round-trip efficiency is an assumption at the model bus. No standby loss, thermal response, state-dependent efficiency, physical fade or ageing feedback. Wear cost is not a capacity model.",
    "Matched DC-to-DC tests across SOC, power and temperature; idle consumption and usable-capacity data. Fit separate charge/discharge losses if identifiable.",
    base + ["methane/battery.py"],
    ["atb"],
    ["tests/test_battery.py"],
    1,
)
group(
    "gas-storage",
    "Gas buffers and deliveries",
    "hydrogen co2",
    "Ideal mass inventories with capacity bounds. CO₂ delivery is accepted before withdrawal; concurrent hydrogen inflow/outflow follows the execution contract. Excess delivery is rejected explicitly.",
    "No pressure, temperature, compressor consumption, usable heel, leakage, boil-off, delivery purity or unloading equipment. Supply quantities and timing are scenarios, not contracted logistics.",
    "Specify storage technology and operating pressure/temperature, usable mass, compression/drying power, supplier delivery constraints and metering.",
    base + ["methane/storage.py"],
    ["nist-h2", "nist-co2"],
    ["tests/test_components.py", "tests/test_boundaries.py"],
    0,
)
group(
    "solar",
    "PV conversion and clipping",
    "solar weather",
    "Hourly tilted irradiance drives a simple NOCT temperature relation and linear power coefficient. Reference PV caps at nameplate. Detailed sections use fixed 30% diffuse contribution, uniform shade and a separate converter.",
    "Nameplate is a reference rating, not by itself a physical output ceiling. Sections have no string mismatch, diode, wind or snow model. Generic losses, section soiling and service soiling need non-overlapping definitions.",
    "Select module, mounting, converter and loss ledger together. Obtain measured POA irradiance, cell/ambient temperature, wind and unclipped DC power; validate on different seasons.",
    base + ["methane/pv.py", "methane/solar_model.py"],
    ["sam-pv", "pv-validation", "soiling"],
    ["tests/test_solar.py"],
    0,
)
group(
    "weather",
    "Weather provenance and forecast availability",
    "weather experiments",
    "Saved ECMWF runs are selected by availability; GTI at t+1 applies to [t,t+1), temperature is sampled at t. UTC is numerical time; local offsets are presentation.",
    "ERA5 is reanalysis, not measured site weather. Six-hour publication lag, forecast bias and synthetic variability are assumptions. Existing weather archive lacks the site output needed to calibrate PV conversion.",
    "Measure site irradiance/temperature and log actual forecast arrival; estimate errors by season, lead time and correlated weather regimes. Keep calibration windows separate from evaluation.",
    base + ["methane/weather.py", "methane/forecast.py", "methane/timebase.py"],
    ["forecast", "era5"],
    ["tests/test_methane.py", "tests/test_components.py"],
    0,
    "External reference with explicit assumptions",
)
group(
    "sensing",
    "Measurement uncertainty and diagnosis",
    "diagnosis electrolyser hydrogen",
    "Power and flow get seeded multiplicative noise. Tank noise scales with current production; battery, CO₂, temperature and hydrogen withdrawal are exact. Diagnosis compares tracking and mass-balance residuals.",
    "Tank noise becomes zero at zero production. Differencing inventory measurements needs an uncertainty/covariance budget; two samples and a 10%/3σ threshold do not establish a field false-alarm rate.",
    "Identify meters and independent reference channels; collect zero/span, drift, bias, covariance and time-synchronisation data over low and high flows. Validate diagnosis with blind held-out faults.",
    base + ["methane/sensing.py"],
    ["gum", "uncertainty"],
    ["tests/test_sensing_policy.py", "tests/test_methane.py"],
    0,
)
group(
    "faults",
    "Fault lifecycle and incidence",
    "diagnosis services experiments",
    "Scheduled disturbances have declared causes; persistent faults remain until a compatible accepted intervention. Transient timing is explicit.",
    "Fault schedules and categorical causes are test scenarios, not estimated incidence, MTBF or a complete failure-mode analysis. A contact cannot uniquely diagnose all equipment faults.",
    "Cause-coded fleet/site logs with exposure hours, censored healthy intervals, downtime and repair outcomes. Preserve common-cause failures and seasonal effects.",
    base + ["methane/faults.py", "methane/field_operations.py"],
    ["field-review"],
    ["tests/test_field_operations.py", "tests/test_hardware_physics.py"],
    0,
)
group(
    "cleaning",
    "Cleaning physics and environmental limits",
    "solar services",
    "Optional lumped-DC or section-surface cleaning; finite coverage, brush condition, water, power and work time.",
    "Uniform deposition, ideal soiling knowledge, efficacy and brush life are assumptions. Weather is often assumed rather than site data. Global annual soiling cannot calibrate 0.5 percentage points/day. Cleaning cannot remove module damage.",
    "Paired clean/reference strings, local deposition/rain history, surface compatibility, before/after cleaning tests, abrasion and access records. Commission one complete cleaner/support configuration.",
    [
        "methane/field_operations.py",
        "methane/services/configuration.py",
        "methane/services/surface.py",
        "methane/solar_model.py",
    ],
    ["soiling", "field-review"],
    ["tests/test_surface_services.py", "tests/test_portable_cleaning.py"],
    0,
)
group(
    "inspection",
    "Inspection channels and references",
    "diagnosis services",
    "Fixed/mobile readers observe a prepared contact; optional zero/span references can separate certain reader errors from common contact faults.",
    "Prepared test points and a common contact are not guaranteed OEM features. Thresholds, read errors and references are uncalibrated. Reference checks on contacts do not calibrate a hydrogen flow meter.",
    "Obtain electrical interface and fault truth table, safe access and reference specifications. Blind inject reader faults and common-contact failures, including uninformative states.",
    ["methane/services/configuration.py", "methane/services/inspection.py", "methane/faults.py"],
    ["gum", "uncertainty", "field-review"],
    ["tests/test_inspection_sensing.py"],
    0,
)
group(
    "recovery",
    "Recovery and intervention capability",
    "services diagnosis",
    "Reset, calibration, module replacement and operating probes are distinct modeled activities; physical outcome is followed by operating verification.",
    "Generic module replacement and erasing a flow bias lack a named replaceable part, reference instrument, procedure and cause-clearance test. Remote release addresses only declared control holds. All capability conclusions are conditional.",
    "Bind each action to a specific device, fault cause, interface, isolation procedure, tool, trained actor and verification result. Unsupported repair families remain concepts.",
    [
        "methane/faults.py",
        "methane/field_operations.py",
        "methane/services/procedures.py",
        "methane/recovery.py",
    ],
    ["field-review", "gum"],
    ["tests/test_service_procedures.py", "tests/test_post_service_verification.py"],
    0,
)
group(
    "support",
    "Support system and access",
    "services",
    "Finite work time, shifts, inventory, transport, charging and returns can constrain service. Optional models declare which resources exist.",
    "Route traversal and interlocks are ideal abstractions; no obstacles, terrain, hazardous-area qualification or physical isolation dynamics. Durations, travel and supplier capacity are illustrative.",
    "Site layout and access survey, regional callout terms, task time/energy observations, stores policy, staffed support and communications availability. Do not combine incompatible hardware claims.",
    [
        "methane/field_operations.py",
        "methane/services/configuration.py",
        "methane/services/core.py",
        "methane/services/support.py",
    ],
    ["field-review"],
    [
        "tests/test_service_support.py",
        "tests/test_service_contracts.py",
        "tests/test_service_charging.py",
    ],
    0,
)
group(
    "maintenance",
    "Reliability and routine maintenance",
    "services economics",
    "Routine work, replaceable stock and duty-related wear can be accounted for; hardware failures have explicit recovery paths.",
    "Fixed intervals, success probabilities and calendar lives are assumptions. Preventive maintenance is not a measured hazard reduction or a physical degradation model.",
    "Exposure-based failure histories and maintenance manuals for the selected equipment; separate scheduled maintenance, breakdown repair and capacity ageing.",
    [
        "methane/services/configuration.py",
        "methane/services/maintenance.py",
        "methane/service_economics.py",
    ],
    ["field-review"],
    ["tests/test_routine_services.py"],
    0,
)
group(
    "economics",
    "Prices, allocations and decision economics",
    "economics experiments services",
    "Allocated ownership and max(calendar, usage) replacement allowances are separate from action-dependent inputs and wear. Repricing cannot change recorded actions.",
    "EUR defaults have no quotations, price year, location-specific tariffs or matched equipment scope. Purchased water is 12 L/kg H₂ versus 9 kg/kg reaction consumption; the additional treatment/handling allowance is not an independently tracked water process. Linear capacity scaling and wear proxies are scenario assumptions. No annual ROI can be inferred from short injected-fault windows.",
    "Matched installed quotes, utility/water/CO₂ contracts, service invoices and replacement records; explicit VAT, currency date, utilisation and equipment boundaries.",
    base + ["economics.py", "methane/costing.py", "methane/service_economics.py"],
    ["doe-pem", "atb", "field-review"],
    ["tests/test_economics.py", "tests/test_service_economics.py"],
    0,
)
group(
    "control",
    "Objectives and planning approximations",
    "controllers services diagnosis",
    "Greedy, methane MPC and economic MPC operate on declared horizons and information. Service policies use finite candidate sets and subjective recovery/inspection beliefs.",
    "Weights, priors, probe size, retries and risk budgets are policy choices. Optimality is bounded by information, terminal inventory treatment, candidate coverage and solver termination; model mismatch is separate.",
    "Choose service/production objectives and acceptable uncertainty; evaluate with frozen matched information, terminal inventories and held-out stress cases. Do not infer event probabilities from illustrative belief priors.",
    base
    + [
        "methane/policy.py",
        "methane/dispatch.py",
        "methane/recovery.py",
        "methane/services/controller.py",
        "methane/services/investigator.py",
    ],
    ["field-review"],
    ["tests/test_service_planning.py", "tests/test_investigation_planning.py"],
    1,
    "Policy choice and bounded approximation",
)
group(
    "coupling",
    "Plant electrical and temporal boundary",
    "bus experiments controllers",
    "Hourly average DC electricity is allocated jointly to electrolysis, storage, reactor heat/cooling and services. Requested and applied actions and unused electricity are separate.",
    "No voltage, frequency, ramp, protection or sub-hour ride-through model. One-hour energy sufficiency does not demonstrate real-time physical feasibility.",
    "Define DC conversion topology, auxiliary loads and fast interlocks; use sub-hour traces to test any claim about plant continuity.",
    base + ["methane/physics.py", "methane/dispatch.py"],
    checks=["tests/test_reference.py", "tests/test_boundaries.py"],
    priority=0,
    status="Conservation within reduced boundary",
)
group(
    "experiment",
    "Reproducibility and comparison settings",
    "experiments controllers weather",
    "Named seeds and saved forecasts preserve inputs. Simulation duration, solver limits, model identifiers and archive context define comparison scope.",
    "Repeatability does not establish realism; time-limited optimization need not reproduce identical numerical decisions. Model versions and source identities must accompany claims.",
    "Separate scenario design, calibration data and blind evaluation. Compare inventories, failures, solver limitations and service obligations at the same boundary.",
    base + ["methane/simulation.py", "methane/provenance.py", "methane/forecast.py"],
    checks=["tests/test_engineering.py", "tests/test_studies.py"],
    status="Experiment design",
)

# Explicit per-field assignments for physical inputs. Other blocks are reviewed below
# as complete policy, scenario or commercial contract families.
plant_groups = {}


def assign(g, names):
    for name in names.split():
        plant_groups[name] = g


assign(
    "layout",
    "solar_kw battery_kwh electrolyser_kw initial_soc h2_capacity_kg initial_h2_kg co2_capacity_kg initial_co2_kg",
)
assign("battery", "battery_c_rate roundtrip_efficiency")
assign("electrolyser", "min_load_fraction start_energy_kwh specific_energy_kwh_per_kg")
assign("gas-storage", "co2_delivery_kg co2_delivery_every_hours")
assign("coupling", "dt_hours")
assign(
    "thermal",
    "methane_max_kgph methane_min_kgph temperature_min_c temperature_max_c thermal_capacity_kwh_per_k heat_loss_kw_per_k heater_max_kw cooling_max_kw auxiliary_kw methane_electric_kwh_per_kg cooling_electric_fraction minimum_run_hours",
)

CATEGORIES = {
    "design": "Chosen capacity, geometry or initial condition; requires a matched design, not statistical calibration.",
    "equipment": "Equipment performance assumption; needs matched specifications or measurements.",
    "scenario": "Test condition or injected disturbance; not an occurrence-rate estimate.",
    "policy": "Controller or operational policy choice; evaluate consequences rather than label calibrated.",
    "economic": "Commercial or accounting assumption; requires dated, scoped prices and wear evidence.",
    "reference": "External data/source convention; source and applicability matter.",
    "implementation": "Numerical/model selection or metadata; verified by software contracts.",
}


def classify(path, value):
    parts = path.split(".")
    block = parts[0]
    name = parts[-1]
    if block == "plant":
        g = plant_groups[name]
        return (
            g,
            "design"
            if g == "layout"
            else "implementation"
            if name == "dt_hours"
            else "scenario"
            if name.startswith("co2_delivery")
            else "equipment",
        )
    if block in ("costs", "service_economics"):
        return "economics", "economic" if isinstance(value, (int, float)) and not isinstance(
            value, bool
        ) else "implementation"
    if block == "sensors":
        return "sensing", "equipment" if name == "noise_fraction" else "policy"
    if block == "scenario":
        return (
            ("control", "policy")
            if name == "horizon_hours"
            else ("experiment", "implementation")
            if name in ("hours", "seed", "solver_seconds")
            else ("faults", "scenario")
            if name
            in (
                "fault_start_hour",
                "fault_duration_hours",
                "capacity_fraction",
                "flow_bias_fraction",
            )
            else ("weather", "scenario")
        )
    if block == "weather":
        if name in ("noct_c", "temperature_coefficient", "loss_fraction"):
            return "solar", "equipment"
        if name in ("tilt", "azimuth"):
            return "solar", "design"
        return "weather", "implementation" if name in (
            "mode",
            "offline",
        ) else "policy" if name == "publication_lag_hours" else "scenario"
    if block == "solar":
        return (
            "solar",
            "implementation"
            if name == "version"
            else "scenario"
            if name == "online"
            else "design"
            if name in ("tilt", "azimuth", "capacity_kw", "converter_kw")
            else "equipment",
        )
    if block == "faults":
        return "faults", "implementation" if name == "hardware_model" else "scenario"
    if block in ("recovery_policy", "service_policy", "investigation_policy"):
        return "control", "implementation" if name in ("version", "source") else "policy"
    if block == "rng_policy" or block == "models":
        return "experiment", "implementation"
    if block in ("field_operations", "service_system"):
        g = "support"
        if any(
            s in name
            for s in (
                "clean",
                "soil",
                "brush",
                "adhered",
                "damage_fraction",
                "area_m2",
                "wind",
                "rain",
                "portable",
                "environment",
            )
        ):
            g = "cleaning"
        if any(s in name for s in ("inspection", "reader", "contact", "calibration_reference")):
            g = "inspection"
        if any(
            s in name
            for s in (
                "reset",
                "repair",
                "release",
                "hardware_replacement",
                "remote_assistance",
                "equipment_recovery",
            )
        ):
            g = "recovery"
        if any(
            s in name for s in ("maintenance", "success_probability", "mission_failure_probability")
        ):
            g = "maintenance"
        category = "equipment"
        if isinstance(value, bool):
            category = "design"
        if isinstance(value, str):
            category = "implementation"
        if any(
            s in name for s in ("initial", "spares", "kits", "capacity", "battery_kwh", "dock_kw")
        ):
            category = "design"
        if any(
            s in name
            for s in (
                "threshold",
                "reserve",
                "policy",
                "period",
                "first_due",
                "max_jobs",
                "max_age",
                "wait_hours",
                "shift",
                "hours_per_period",
                "maintenance_interval",
            )
        ):
            category = "policy"
        if name.startswith("assumed_"):
            category = "scenario"
        return g, category
    raise ValueError(path)


units = {
    "initial_soc": "fraction",
    "roundtrip_efficiency": "fraction",
    "dt_hours": "h",
    "thermal_capacity_kwh_per_k": "kWh/K",
    "heat_loss_kw_per_k": "kW/K",
    "temperature_coefficient": "1/K",
    "battery_c_rate": "1/h",
    "latitude": "degrees north",
    "longitude": "degrees east",
    "azimuth": "degrees; south=0",
    "tilt": "degrees",
    "efficiency": "fraction",
    "shade": "fraction",
    "soiling": "fraction",
    "initial_damage_fraction": "fraction",
    "brush_initial_condition": "fraction",
    "specific_energy_kwh_per_kg": "kWh/kg H₂",
    "methane_electric_kwh_per_kg": "kWh/kg CH₄",
}


def unit(path, value):
    name = path.split(".")[-1]
    if name in units:
        return units[name]
    if isinstance(value, (str, bool)) or value is None:
        return "configuration"
    for token, u in [
        ("eur_per_active_hour", "EUR/h"),
        ("eur_per_travel_hour", "EUR/h"),
        ("eur_per_year", "EUR/year"),
        ("eur_per_incident", "EUR/incident"),
        ("eur_per_hour", "EUR/h"),
        ("eur_per_kwh", "EUR/kWh"),
        ("eur_per_kw", "EUR/kW"),
        ("eur_per_kg", "EUR/kg"),
        ("eur_per_m3", "EUR/m³"),
        ("eur_per_unit", "EUR/declared unit"),
        ("kwh_per_kg", "kWh/kg"),
        ("m2_per_kw", "m²/kW"),
        ("water_l_per_m2", "L/m²"),
        ("m2ph", "m²/h"),
        ("mmph", "mm/h"),
        ("vph", "V/h"),
        ("kgph", "kg/h"),
        ("mps", "m/s"),
        ("kwh", "kWh"),
        ("kw", "kW"),
        ("kg", "kg"),
        ("hours", "h"),
        ("hour", "h"),
        ("seconds", "s"),
        ("years", "years"),
        ("eur", "EUR"),
        ("m2", "m²"),
    ]:
        if name.endswith(token):
            return u
    if name.endswith("_c"):
        return "°C"
    if name.endswith("_v"):
        return "V"
    if name.endswith("_l"):
        return "L"
    if (
        "fraction" in name
        or "probability" in name
        or name
        in ("risk_weight", "probability", "portable_loose_removal", "portable_adhered_removal")
    ):
        return "fraction"
    if name == "soiling_per_day":
        return "fraction/day"
    if name == "water_litres_per_kg":
        return "L/kg H₂"
    return "count or declared dimensionless value"


ranges = {
    "plant.roundtrip_efficiency": (
        [0.85, 0.90, 0.95],
        "Exploratory DC-bus efficiency stress. ATB values use different boundaries; not a confidence interval.",
    ),
    "plant.specific_energy_kwh_per_kg": (
        [50, 55, 65],
        "Exploratory system-consumption stress around DOE context; not three measured devices.",
    ),
    "plant.thermal_capacity_kwh_per_k": (
        [0.15, 0.3, 0.6],
        "Exploratory half/double thermal inertia; no measured range.",
    ),
    "plant.heat_loss_kw_per_k": (
        [0.04, 0.08, 0.16],
        "Exploratory half/double heat loss; no measured range.",
    ),
    "plant.start_energy_kwh": (
        [20, 40, 80],
        "Exploratory half/double startup overhead; no measured range.",
    ),
    "sensors.noise_fraction": (
        [0.01, 0.02, 0.05],
        "Exploratory scale only; does not repair the inventory metrology model.",
    ),
    "weather.noct_c": (
        [45, 49],
        "Two SAM mounting reference assumptions; not a fitted interval for this array.",
    ),
    "weather.temperature_coefficient": (
        [-0.0047, -0.004, -0.0035],
        "Exploratory coefficient values spanning old/reference module assumptions; choose a single matched module in a real design.",
    ),
    "costs.methane_eur_per_kg": ([0.5, 1, 2], "Decision-price stress, not a market forecast."),
    "costs.co2_eur_per_kg": (
        [0.05, 0.15, 0.30],
        "Delivered-feedstock price stress; no supplier quotation.",
    ),
}
params = []
for path, value in flatten(reference_configuration()).items():
    g, category = classify(path, value)
    item = dict(
        id="parameter:" + path,
        path=path,
        label=path.split(".")[-1].replace("_", " "),
        group=g,
        category=category,
        unit=unit(path, value),
        reference_default=value,
        evidence_status="Chosen input"
        if category in ("design", "scenario", "policy")
        else "Software convention"
        if category == "implementation"
        else "Unmeasured assumption",
        applicable_range=None,
        range_note="Validation bounds only constrain accepted input; they are not evidence of plausible equipment performance.",
    )
    if path == "plant.specific_energy_kwh_per_kg":
        item.update(
            evidence_status="Literature benchmark; unmatched equipment",
            range_note="55 kWh/kg coincides with DOE 2022 system status. No matched plant data or uncertainty interval.",
        )
    if path in ranges:
        item["sensitivity_values"], item["sensitivity_scope"] = ranges[path]
    params.append(item)
prior = json.loads((ROOT / "research/field-realism-review/assumptions.json").read_text())
review = dict(
    schema_version="dispatch-lab/assumption-review/1",
    edition="2026-09-13 / 3",
    scope="Evidence and assumption classification for the illustrative fixture. No plant-specific fitted parameters, no new capability grants, no silently changed defaults. Conditional experiments are not empirical calibration.",
    categories=CATEGORIES,
    sources=SOURCES,
    groups=GROUPS,
    parameters=params,
    prior_field_findings=prior,
    reference_configuration_note="Optional blocks and example arrays are inventoried but not enabled. [] represents repeated objects. Values absent from a run remain unavailable. Within enabled blocks, variant-specific parameters may still be inactive.",
    calibration_gate="Open: no matched plant or service measurement series is supplied. Existing numerical, reference and historical-weather evidence has narrower scope.",
)
OUT.write_text(json.dumps(review, indent=2, ensure_ascii=False) + "\n")
print(len(params), "parameter paths;", len(GROUPS), "mechanism groups")
