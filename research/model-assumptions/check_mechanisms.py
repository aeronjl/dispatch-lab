"""Independent calculations and a read-only audit of cached European weather."""

import hashlib
import json
import math
from itertools import product
from pathlib import Path

import numpy as np
from scipy.integrate import solve_ivp

from methane.config import Config, Plant, Scenario, Sensors, WeatherConfig
from methane.forecast import choose_vintage
from methane.physics import CO2_PER_CH4, H2_PER_CH4, WATER_PER_CH4, State
from methane.provenance import LOADED_SOURCE, digest
from methane.pv import Parameters, convert
from methane.reactor import REACTION_KWH_PER_KG, ThermalInput, step
from methane.sensing import observe
from methane.timebase import utc
from methane.weather import CACHE, IncompleteWeather, prepare

HERE = Path(__file__).resolve().parent


def checks():
    rows = []
    for c, ua, start, ambient, heater, methane, cooling in product(
        [0.15, 0.3, 0.6], [0, 0.04, 0.08, 0.16], [20, 300], [-5, 20], [0, 60], [0, 10], [0, 40]
    ):
        p = Plant(thermal_capacity_kwh_per_k=c, heat_loss_kw_per_k=ua)
        # Independently integrate the differential equation; no production coefficients.
        q = heater + methane * 165000 / 16 / 3600 - cooling
        expected = float(
            solve_ivp(
                lambda t, y, q=q, ua=ua, ambient=ambient, c=c: [(q - ua * (y[0] - ambient)) / c],
                (0, 1),
                [start],
                method="DOP853",
                rtol=1e-11,
                atol=1e-11,
            ).y[0, -1]
        )
        actual = step(p, ThermalInput(start, ambient, heater, methane, cooling)).state.temperature_c
        rows.append(
            dict(
                C=c,
                UA=ua,
                initial=start,
                ambient=ambient,
                heater=heater,
                methane=methane,
                cooling=cooling,
                error_K=abs(expected - actual),
                passed=abs(expected - actual) < 1e-7,
            )
        )
    mw = dict(h2=2.01588, co2=44.0095, ch4=16.0425, water=18.01528)
    reference = dict(
        h2=4 * mw["h2"] / mw["ch4"], co2=mw["co2"] / mw["ch4"], water=2 * mw["water"] / mw["ch4"]
    )
    modeled = dict(h2=H2_PER_CH4, co2=CO2_PER_CH4, water=WATER_PER_CH4)
    chemistry = {
        k: dict(
            modeled_kg_per_kg=modelled,
            reference_kg_per_kg=reference[k],
            relative_difference_percent=100 * (modelled / reference[k] - 1),
        )
        for k, modelled in modeled.items()
    }
    # Chase Shomate formation constants at 298.15 K, gas water. Standard-state only.
    reference_heat = -(-74.87310 + 2 * (-241.8264) - (-393.5224)) / (mw["ch4"] / 1000) / 3600
    chemistry["reaction_heat"] = dict(
        modeled_kwh_per_kg=REACTION_KWH_PER_KG, reference_kwh_per_kg=reference_heat
    )
    solar = []
    for irradiance, ambient in product([400, 800, 1000, 1200], [-10, 20, 35]):
        p = Parameters(1000, 0.14, 45, -0.004)
        temp = ambient + (45 - 20) * irradiance / 800
        uncapped = 1000 * irradiance / 1000 * 0.86 * (1 - 0.004 * (temp - 25))
        actual = convert(p, irradiance, ambient)
        solar.append(
            dict(
                irradiance_wm2=irradiance,
                ambient_c=ambient,
                uncapped_reference_kw=uncapped,
                applied_kw=actual,
                implicit_cap_loss_kw=max(0, uncapped - actual),
            )
        )
    sensor = []
    p = Plant()
    state = State(400, 30, 500, 300)
    for flow in [0, 0.1, 1, 5]:
        row = dict(
            h2_produced_kg=flow,
            h2_consumed_kg=0,
            applied={"electrolyser_kw": flow * 55},
            state=vars(state),
        )
        samples = [
            observe(p, Sensors(), None, row, seed, 0, rng_policy="named-channels/1")[
                "h2_inventory_kg"
            ]
            for seed in range(200)
        ]
        sensor.append(
            dict(
                flow_kgph=flow,
                modeled_inventory_sigma_kg=flow * 0.02,
                observed_sample_sigma_kg=float(np.std(samples)),
                all_exact=all(x == 30 for x in samples),
            )
        )
    uncertainty = [
        dict(
            flow_kgph=flow,
            inventory_sigma_kg=sigma,
            correlation=rho,
            difference_sigma_kg=math.sqrt(2 * sigma * sigma * (1 - rho)),
            relative_sigma=math.sqrt(2 * sigma * sigma * (1 - rho)) / flow,
        )
        for flow, sigma, rho in product([0.1, 1, 5], [0.02, 0.1, 0.5], [0, 0.9])
    ]
    result = dict(
        source=LOADED_SOURCE,
        thermal=dict(
            count=len(rows),
            passed=all(r["passed"] for r in rows),
            maximum_error_K=max(r["error_K"] for r in rows),
            cases=rows,
            scope="Pure thermal helper, including deliberately out-of-band temperatures; not feasible production dispatch or real-reactor validation.",
        ),
        chemistry=chemistry,
        solar_cap_cases=solar,
        sensor_cases=sensor,
        inventory_uncertainty_examples=uncertainty,
        uncertainty_scope="Hypothetical uncertainty budgets, not specifications of a real meter; no change to diagnosis implementation.",
    )
    (HERE / "mechanism-checks.json").write_text(json.dumps(result, indent=2))
    print(
        "Thermal:",
        len(rows),
        "cases;",
        result["thermal"]["passed"],
        "max",
        result["thermal"]["maximum_error_K"],
        flush=True,
    )


def weather_review():
    sites = [
        ("London", 51.5074, -0.1278, "Europe/London"),
        ("Seville", 37.3891, -5.9845, "Europe/Madrid"),
        ("Copenhagen", 55.6761, 12.5683, "Europe/Copenhagen"),
    ]
    results = []
    for site, lat, lon, tz in sites:
        for month in [1, 4, 7]:
            cfg = Config(
                scenario=Scenario(hours=240, horizon_hours=24),
                weather=WeatherConfig(
                    mode="historical",
                    latitude=lat,
                    longitude=lon,
                    timezone=tz,
                    start=f"2026-{month:02}-10",
                    offline=True,
                ),
            )
            item = dict(
                site=site,
                start=cfg.weather.start,
                reference="ERA5 reanalysis; not site measurements",
                hours=240,
            )
            try:
                weather = prepare(cfg)
                errors = {str(k): [] for k in [0, 6, 12, 23]}
                from datetime import timedelta

                from methane.timebase import stamp

                for time in weather["times"]:
                    vintage = choose_vintage(weather["vintages"], utc(time))
                    for lead in [0, 6, 12, 23]:
                        target = stamp(utc(time) + timedelta(hours=lead))
                        if target in weather["truth"] and target in vintage["data"]:
                            errors[str(lead)].append(
                                vintage["data"][target]["pv_kw"] - weather["truth"][target]["pv_kw"]
                            )
                stats = {
                    k: dict(
                        n=len(v),
                        bias_kw=float(np.mean(v)) if v else None,
                        rmse_kw=float(np.sqrt(np.mean(np.square(v)))) if v else None,
                    )
                    for k, v in errors.items()
                }
                item.update(
                    status="complete",
                    weather_hash=digest(weather),
                    snapshots=[s["id"] for s in weather["snapshots"]],
                    forecast_vs_reanalysis=stats,
                    reference_dc_kwh=sum(weather["truth"][t]["pv_kw"] for t in weather["times"]),
                    missing_service_weather=any(
                        not all(
                            x in s["raw"].get("hourly", {})
                            for x in ("wind_speed_10m", "precipitation")
                        )
                        for s in weather["snapshots"]
                    ),
                )
            except IncompleteWeather as exc:
                item.update(status="incomplete", reason=str(exc))
            results.append(item)
            print("Weather:", site, month, item["status"], flush=True)
    inventory = []
    for path in sorted(CACHE.glob("*.json")):
        raw = path.read_bytes()
        obj = json.loads(raw)
        inventory.append(
            dict(
                path=str(path.relative_to(HERE.parents[1])),
                sha256=hashlib.sha256(raw).hexdigest(),
                request=obj.get("request"),
                retrieved_at=obj.get("retrieved_at"),
                variables=list(obj.get("raw", {}).get("hourly", {})),
            )
        )
    (HERE / "weather-review.json").write_text(
        json.dumps(
            dict(
                source=LOADED_SOURCE["content_hash"],
                windows=results,
                cache_inventory=inventory,
                scope="Daily 00 UTC saved forecast issues, assumed six-hour publication lag. All hours, including night, contribute. Forecast and reanalysis share modelling dependencies; errors are not errors against measured generation. No fitting or online requests.",
            ),
            indent=2,
        )
    )


if __name__ == "__main__":
    checks()
    weather_review()
