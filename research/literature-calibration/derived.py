"""Source-based calculations and explicit hypothetical designs; no plant mutation."""

import json
import math
from pathlib import Path

from analyse import density_z

HERE = Path(__file__).resolve().parent

# NIST WebBook / Chase (1998), gas-phase Shomate coefficients.
# H2O's fitted range starts at 500 K. Formation enthalpy at 298.15 K is
# read independently; we never extrapolate its polynomial down to 298 K.
SHOMATE = {
    "ch4": [-0.703029, 108.4773, -42.52157, 5.862788, 0.678565, -76.84376, -74.87310],
    "co2": [24.99735, 55.18696, -33.69137, 7.948387, -0.136638, -403.6075, -393.5224],
    "h2": [33.066178, -11.363417, 11.432816, -2.772874, -0.158558, -9.980797, 0],
    "water": [30.09200, 6.832514, 6.793435, -2.534480, 0.082139, -250.8810, -241.8264],
}
MW = {"ch4": 16.0425, "co2": 44.0095, "h2": 2.01588, "water": 18.01528}


def enthalpy(species, temperature_k):
    """kJ/mol relative to elemental 298.15 K reference; limited shared domain."""
    if not 500 <= temperature_k <= 1000:
        raise ValueError("Outside the common Shomate coefficient range")
    a, b, c, d, e, f, _ = SHOMATE[species]
    t = temperature_k / 1000
    return a * t + b * t**2 / 2 + c * t**3 / 3 + d * t**4 / 4 - e / t + f


def density(pressure_bar, temperature_k=293.15):
    return (
        pressure_bar
        * 1e5
        * 0.00201588
        / (density_z(pressure_bar / 10, temperature_k) * 8.314472 * temperature_k)
    )


def calculate():
    ratios = {
        "h2_kg_per_kg_ch4": 4 * MW["h2"] / MW["ch4"],
        "co2_kg_per_kg_ch4": MW["co2"] / MW["ch4"],
        "water_kg_per_kg_ch4": 2 * MW["water"] / MW["ch4"],
        "electrolysis_water_kg_per_kg_h2": MW["water"] / MW["h2"],
    }
    # Tabulated molecular weights carry rounding; do not force exact equality.
    closure = (
        ratios["h2_kg_per_kg_ch4"] + ratios["co2_kg_per_kg_ch4"] - 1 - ratios["water_kg_per_kg_ch4"]
    )
    assert abs(closure) < 1e-5
    delta_h_298 = SHOMATE["ch4"][-1] + 2 * SHOMATE["water"][-1] - SHOMATE["co2"][-1]
    thermal = []
    for tc in [250, 300, 320, 350, 400]:
        h = {s: enthalpy(s, tc + 273.15) for s in SHOMATE}
        dh = h["ch4"] + 2 * h["water"] - h["co2"] - 4 * h["h2"]
        sensible = (h["co2"] - SHOMATE["co2"][-1]) + 4 * (h["h2"] - SHOMATE["h2"][-1])
        thermal.append(
            dict(
                temperature_c=tc,
                reaction_release_kwh_per_kg_ch4=-dh / (3.6 * MW["ch4"]),
                cold_feed_heating_kwh_per_kg_ch4=sensible / (3.6 * MW["ch4"]),
                net_release_after_feed_heating_kwh_per_kg_ch4=(-dh - sensible) / (3.6 * MW["ch4"]),
            )
        )
    storage = []
    for upper in [30, 100, 200, 350]:
        v = 60 / density(upper)
        storage.append(
            dict(
                max_pressure_bar_absolute=upper,
                min_pressure_bar_absolute=20,
                temperature_c=20,
                nominal_mass_kg=60,
                volume_m3=v,
                heel_kg=v * density(20),
                usable_mass_kg=v * (density(upper) - density(20)),
                volume_for_60kg_usable_m3=60 / (density(upper) - density(20)),
            )
        )
    # Hypothetical 40 bar full scale / 0.25%-span pressure instrument.
    v = 60 / density(30)
    pressure_effect = max(abs(v * density(30 + dp) - 60) for dp in [-0.1, 0.1])
    temperature_effect = max(abs(v * density(30, 293.15 + dt) - 60) for dt in [-1, 1])
    sample = {
        "well_mixed_volume_cm3": 100,
        "actual_flow_cm3_per_min": 100,
        "time_to_95_percent_replacement_min": -math.log(0.05),
    }
    area = 5000  # Existing geometry assumption, not a Serbot specification.
    cleaning = dict(
        area_m2=area,
        rate_m2_per_h=670,
        productive_hours=area / 670,
        robot_electricity_kwh=0.8 * area / 670,
        water_litres_range=[0.5 * 60 * area / 670, 3 * 60 * area / 670],
        water_litres_per_m2_range=[0.5 * 60 / 670, 3 * 60 / 670],
        excluded="Travel, setup, row transfers, compressor, lift, pumping and water treatment. Vendor average-rate claim, not a measured site guarantee.",
    )
    row = dict(
        assumed_area_m2=area,
        vendor_speed_m2_per_h=3 * 60,
        vendor_max_nightly_area_m2=400,
        minimum_units_for_single_night=math.ceil(area / 400),
        scope="Ecoppia T4 tracker-specific reference. Geometry may require more units; speed and nightly area are different constraints.",
    )
    return dict(
        schema_version="dispatch-lab/literature-derived/1",
        chemistry=dict(
            molecular_weights_g_per_mol=MW,
            ratios=ratios,
            mass_rounding_residual_kg_per_kg_ch4=closure,
            standard_reaction_kj_per_mol=delta_h_298,
            standard_reaction_kwh_per_kg_ch4=-delta_h_298 / (3.6 * MW["ch4"]),
            thermal=thermal,
            co2_300kg_day_ch4_steady_supply_ceiling_kg_per_day=300 / ratios["co2_kg_per_kg_ch4"],
            scope="Ideal complete conversion, gas water, no pressure/equilibrium/kinetics correction or heat recovery credit.",
        ),
        gas_storage=storage,
        metrology=dict(
            pressure_example_bound_kg=pressure_effect,
            temperature_example_bound_kg=temperature_effect,
            scope="Separate one-at-a-time error examples, not combined uncertainty or Gaussian noise. Assumed 40 bar span, ±0.25% span, ±1 K, and fixed reference volume.",
        ),
        sampling=sample,
        portable_cleaning=cleaning,
        row_cleaning=row,
        inspection=dict(
            b1_actions_successful=673,
            b1_actions_attempted=730,
            b1_action_fraction=673 / 730,
            b1_mtbi_hours=78,
            jet_mtbi_hours=140,
            scope="Published deployment summaries, not fitted per-mission hardware failure hazards. Interventions were clustered; MTBI includes calendar exposure.",
        ),
    )


if __name__ == "__main__":
    (HERE / "analysis" / "derived.json").write_text(
        json.dumps(calculate(), indent=2, allow_nan=False) + "\n"
    )
