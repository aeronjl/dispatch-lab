"""Small, immutable modelling contracts. No UI, I/O, or dispatch allocation."""

from dataclasses import asdict, dataclass, replace
from math import isfinite


@dataclass(frozen=True)
class Parameter:
    key: str
    label: str
    unit: str
    default: float
    lower: float
    upper: float
    source: str = "Illustrative assumption; not calibrated"

    def validate(self, value):
        if isinstance(value, bool) or not isinstance(value, (float, int)):
            raise ValueError(f"{self.label} must be numeric ({self.unit}).")
        if not isfinite(value) or not self.lower <= value <= self.upper:
            raise ValueError(f"{self.label} must be {self.lower}–{self.upper} {self.unit}.")
        return float(value)


@dataclass(frozen=True)
class ComponentSpec:
    model_id: str
    version: str
    parameters: tuple[Parameter, ...]
    inputs: tuple[str, ...]
    outputs: tuple[str, ...]
    assumptions: tuple[str, ...]
    references: tuple[str, ...]
    time_semantics: str
    validation: str = "Illustrative model; numerical verification is not plant calibration"
    execution_interface: str = ""
    planning_interface: str = ""
    verification: tuple[str, ...] = ()

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True)
class ComponentResult:
    state: object
    flows: tuple[tuple[str, float], ...]
    diagnostics: tuple[tuple[str, object], ...] = ()
    audits: tuple = ()


SOLAR = ComponentSpec(
    "dispatch-lab/solar-sections",
    "2",
    (
        Parameter("capacity_kw", "Section capacity", "kWp", 1000 / 3, 0, 10000),
        Parameter("tilt", "Panel tilt", "degrees", 30, 0, 90),
        Parameter("azimuth", "Azimuth (south = 0)", "degrees", 0, -180, 180),
        Parameter("shade", "Uniform shading", "fraction", 0, 0, 1),
        Parameter("soiling", "Soiling", "fraction", 0, 0, 1),
        Parameter("converter_kw", "Converter limit", "kW", 1000, 0, 30000),
        Parameter("efficiency", "Converter efficiency", "fraction", 1, 0.5, 1),
        Parameter("noct_c", "Nominal operating cell temperature", "°C", 45, 20, 80),
    ),
    (
        "reference-plane irradiance: W/m²",
        "ambient: °C",
        "UTC interval start",
        "section design",
        "reference geometry",
        "scenario power adjustment",
    ),
    (
        "DC output: kW",
        "section outputs: kW",
        "cell temperature: °C",
        "explicit losses/clipping: kW",
    ),
    (
        "30% isotropic diffuse sky; archived reference plane normalisation",
        "Uniform section shading; independent ideal MPPT",
        "Panel tiles are schematic; no string I–V or bypass-diode model",
        "Hourly mean radiation; geometry evaluated at interval midpoint",
    ),
    ("https://open-meteo.com/en/docs",),
    "One-hour mean power; 0° azimuth south, −90° east, +90° west",
)

REACTOR = ComponentSpec(
    "dispatch-lab/lumped-reactor",
    "1",
    (
        Parameter("thermal_capacity_kwh_per_k", "Thermal capacity", "kWh/K", 0.3, 0.000001, 10000),
        Parameter("heat_loss_kw_per_k", "Heat-loss coefficient", "kW/K", 0.08, 0, 10000),
        Parameter("temperature_min_c", "Production minimum", "°C", 250, -49, 1499),
        Parameter("temperature_max_c", "Production maximum", "°C", 400, -49, 1499),
        Parameter("heater_max_kw", "Maximum heating", "kW", 60, 0, 100000),
        Parameter("cooling_max_kw", "Maximum heat rejection", "kW", 40, 0, 100000),
        Parameter("minimum_run_hours", "Minimum production run", "h", 4, 1, 240),
    ),
    (
        "initial temperature: °C",
        "ambient: °C",
        "heater/cooling: kW",
        "methane in interval: kg",
        "duration: h",
    ),
    (
        "ending temperature: °C",
        "reaction heat: kWh",
        "heat loss: kWh",
        "operating mode",
        "commitment: h",
    ),
    (
        "C dT/dt = heater + reaction heat − UA(T−ambient) − cooling",
        "Constant inputs within each interval; ideal Sabatier stoichiometry",
        "H₂=2, CO₂=44, CH₄=16, H₂O=18 kg/kmol; reaction heat 165 MJ/kmol",
        "No pressure, kinetics, gas-quality or water-recycling model",
    ),
    ("https://doi.org/10.1039/D5RE00337G",),
    "Thermal helper accepts positive durations; dispatch and commitments use one-hour intervals",
)

BATTERY = ComponentSpec(
    "dispatch-lab/dc-battery",
    "1",
    (
        Parameter("battery_kwh", "Usable energy capacity", "kWh", 800, 0, 1e9),
        Parameter("battery_c_rate", "Power / energy ratio", "1/h", 0.5, 1e-9, 1e3),
        Parameter("roundtrip_efficiency", "Round-trip efficiency", "fraction", 0.9, 1e-9, 1),
        Parameter("initial_soc", "Initial state of charge", "fraction", 0, 0, 1),
    ),
    ("initial stored energy: kWh", "DC-bus charge/discharge: kW", "duration: h"),
    ("ending energy: kWh", "charge/discharge loss: kWh", "SOC: %", "named physical audits"),
    (
        "eta_charge = eta_discharge = sqrt(roundtrip_efficiency)",
        "E_end = E_begin + eta × charge × duration − discharge × duration / eta",
        "Power limit = usable capacity × C-rate; charge and discharge are mutually exclusive",
        "Constant interval power; no self-discharge, temperature, degradation or SOC-dependent efficiency",
        "Zero capacity represents an absent battery; its displayed SOC is zero by convention",
        "Execution accounts for feasible applied actions; plant dispatch owns clipping, bus allocation and curtailment",
        "Usage-related wear is an economic allowance, not a physical capacity-fade model",
    ),
    (),
    "Positive-duration constant-power intervals; plant scheduling remains hourly. State is at interval end.",
    execution_interface="Battery.step(BatteryState(energy_kwh), BatteryInput(charge_kw, discharge_kw, duration_hours)) -> ComponentResult",
    planning_interface="Battery.planning(BatteryState, tuple[duration_hours, ...]) -> PlanningBlock(bounds, rows); local ports: energy, charge, discharge, charging (binary)",
    verification=(
        "tests/test_battery.py: hand-calculated round trip, Decimal reference, subdivision, empty/full/absent battery, invalid actions",
        "tests/test_battery.py: independent standalone MILP consumer, plan/execution conformance, exclusive directions",
        "tests/test_battery.py: implementation swap across all controllers, what-if, fallback, archive audit and display lineage",
        "tests/test_engineering.py::test_pre_refactor_physical_fixture: preserved physical trace",
    ),
)

ELECTROLYSER = ComponentSpec(
    "dispatch-lab/electrolyser",
    "1",
    (
        Parameter("capacity_kw", "Nameplate productive load", "kW", 450, 1e-6, 100000),
        Parameter("minimum_fraction", "Minimum productive load", "fraction", 0.3, 1e-9, 1),
        Parameter(
            "specific_energy_kwh_per_kg",
            "Specific electricity consumption",
            "kWh/kg H₂",
            55,
            1e-9,
            10000,
        ),
        Parameter("start_energy_kwh", "Startup energy", "kWh/start", 40, 0, 100000),
    ),
    ("previous on/off state", "productive load: kW", "available capacity: kW", "duration: h"),
    (
        "ending on/off state",
        "hydrogen: kg",
        "water consumed: kg",
        "total bus demand: kW",
        "start count",
    ),
    (
        "H₂ = productive kW × duration / specific energy",
        "Water consumed = 9 kg/kg H₂; startup consumes energy but produces no hydrogen",
        "Constant efficiency and hard turndown; no stack temperature or pressure",
        "Available capacity is an explicit input: estimate during planning, physical capacity during execution; no injected fault labels",
    ),
    (),
    "Positive-duration constant-power intervals; startup is an interval energy, bus demand is mean power.",
    execution_interface="Electrolyser.step(State(on), Inputs(productive_kw, available_kw, duration_hours)) -> ComponentResult",
    planning_interface="Electrolyser.planning(State, available_kw, durations) -> PlanningBlock; local power/electricity kW, hydrogen kg, on/start boolean",
    verification=(
        "tests/test_components.py: independent conversion/start calculations, standalone planning replay, implementation swap and failure limits",
    ),
)
HYDROGEN = ComponentSpec(
    "dispatch-lab/hydrogen-buffer",
    "1",
    (Parameter("capacity_kg", "Hydrogen capacity", "kg", 60, 1e-9, 1e9),),
    ("initial inventory: kg", "interval inflow/outflow: kg"),
    ("ending inventory: kg", "accepted inflow: kg", "rejected inflow: kg"),
    (
        "Uniform concurrent flow within the hour; inflow may feed production in the same interval",
        "No venting; infeasible overflow/exhaustion raises a named physical audit",
        "No pressure or leakage model",
    ),
    (),
    "Interval mass, not mass rate; state at interval end.",
    execution_interface="Storage(Parameters(capacity_kg, 'hydrogen')).step(State, Inputs) -> ComponentResult",
    planning_interface="Storage.planning(State, intervals) -> PlanningBlock; inventory/inflow/outflow kg",
    verification=(
        "tests/test_components.py: independent ledgers, zero inventory, simultaneous flow, no silent venting, standalone planning and replacement",
    ),
)
CO2 = replace(
    HYDROGEN,
    model_id="dispatch-lab/co2-buffer",
    parameters=(Parameter("capacity_kg", "CO₂ capacity", "kg", 1000, 1e-9, 1e9),),
    assumptions=(
        "Delivery occurs at interval start before withdrawal; excess is explicitly rejected",
        "No pressure or leakage model; delivered feedstock is supplied CO₂",
    ),
    execution_interface="Storage(Parameters(capacity_kg, 'co2')).step(State, Inputs) -> ComponentResult",
    planning_interface="Storage.planning(State, intervals, deliveries_kg) -> PlanningBlock; inventory/outflow/accepted/rejected kg, full boolean",
    verification=(
        "tests/test_components.py: full-tank delivery rejection before withdrawal, delivery accounting, isolated planning and execution",
    ),
)
REACTOR = replace(
    REACTOR,
    parameters=REACTOR.parameters
    + (
        Parameter("methane_min_kgph", "Minimum methane production", "kg/h", 3, 1e-9, 100000),
        Parameter("methane_max_kgph", "Maximum methane production", "kg/h", 10, 1e-9, 100000),
        Parameter("auxiliary_kw", "Running auxiliary demand", "kW", 2, 0, 100000),
        Parameter(
            "methane_electric_kwh_per_kg", "Production electricity", "kWh/kg CH₄", 1, 0, 10000
        ),
        Parameter(
            "cooling_electric_fraction",
            "Cooling electricity / rejected heat",
            "fraction",
            0.1,
            0,
            100,
        ),
    ),
    execution_interface="Reactor.execute(ReactorState, ThermalInput, requested_running) -> ComponentResult; thermal and discrete state together",
    planning_interface="Reactor.planning(ReactorState, ambient_c, durations, enforce_commitment) -> PlanningBlock; thermal/gas/electrical ports with units",
    verification=(
        "tests/test_components.py: standalone thermal/gas planning, commitment carry, cold-start rejection, forced trip",
        "tests/test_engineering.py: independent ODE, subdivision and TLC discrete-state conformance",
    ),
)
WEATHER = ComponentSpec(
    "dispatch-lab/saved-forecast",
    "1",
    (),
    (
        "current PV: kW",
        "current ambient: °C",
        "UTC decision start",
        "saved issues and availability times",
        "horizon: whole hours",
    ),
    (
        "hourly predicted PV: kW",
        "ambient: °C",
        "issue/availability provenance",
        "current forecast residual: kW",
    ),
    (
        "Forecast boundary has no future realised weather input",
        "Availability at or before decision time; latest initialized issue wins",
        "Archive radiation stamped t+1 is the mean for [t,t+1); temperature sampled at t",
        "Missing intervals/units/nonfinite samples raise IncompleteWeather; no synthetic substitution",
        "Reanalysis is a historical reference, not a site measurement",
    ),
    (
        "https://open-meteo.com/en/docs/single-runs-api",
        "https://open-meteo.com/en/docs/historical-weather-api",
    ),
    "UTC one-hour intervals; provider issues and local display times retain offsets",
    execution_interface="SavedForecastProvider.horizon(ForecastRequest) -> detached horizon; provider JSON is frozen and network-free",
    planning_interface="Exogenous pv_kw/ambient_c sequences feed component planning; CO₂ delivery is a separate DeliverySchedule",
    verification=(
        "tests/test_boundaries.py: isolated forecast causality and missing inputs, pure solar conversion and dependency boundaries",
        "tests/test_methane.py: normalization, null radiation, forecast availability and DST",
    ),
)
SOLAR = replace(
    SOLAR,
    execution_interface="solar_model.component_step(SolarInput(design_json, sample_json, UTC time, ArrayCapacity, SolarContext)) -> ComponentResult",
    planning_interface="Same pure converter transforms every saved issue independently; output is an exogenous hourly DC-bus power limit",
    verification=(
        "tests/test_solar.py: design replay and altered geometry, no source mutation",
        "tests/test_engineering.py: independent solar calculations, bounded immutable caching",
        "tests/test_boundaries.py: standalone inputs, invalid data and I/O dependency firewall",
    ),
)
REFERENCE_PV = ComponentSpec(
    "dispatch-lab/reference-pv",
    "1",
    (),
    (
        "reference-plane hourly irradiance: W/m²",
        "ambient: °C",
        "nameplate: kW",
        "loss/NOCT/temperature coefficient",
    ),
    ("DC generation: kW",),
    (
        "Cell temperature = ambient + (NOCT−20) × irradiance / 800",
        "DC = min(nameplate, max(0,nameplate × irradiance/1000 × (1−loss) × max(0,1+coefficient×(cell−25))))",
        "Saved stress may adjust generation explicitly after conversion",
    ),
    (),
    "One-hour mean power; no subhour cloud transients",
    execution_interface="pv.convert(Parameters, irradiance_wm2, ambient_c) -> float kW",
    planning_interface="Exogenous generation input",
    verification=("tests/test_boundaries.py: independent known-answer baseline",),
)
SPECS = {
    "solar": SOLAR,
    "weather": WEATHER,
    "reference_pv": REFERENCE_PV,
    "reactor": REACTOR,
    "battery": BATTERY,
    "electrolyser": ELECTROLYSER,
    "hydrogen": HYDROGEN,
    "co2": CO2,
}
