"""Convert available forecast information through the recorded section surface."""

import copy
import json
from dataclasses import asdict
from math import isfinite

from methane.forecast import IncompleteWeather
from methane.pv import Parameters, dc_power
from methane.services.surface import Surface
from methane.solar_model import default_design, interval, validate


class OpticalArray:
    def __init__(self, plant, weather, design, config, options):
        self.plant, self.weather = plant, weather
        self.baseline = validate(design or default_design(plant, weather))
        self.surface = Surface(
            [s["capacity_kw"] for s in self.baseline["sections"]], config, options
        )

    def convert(self, forecast):
        rows = []
        for i, (time, sample) in enumerate(
            zip(forecast["times"], forecast["source_samples"], strict=True)
        ):
            if (
                not isinstance(sample.get("irradiance_wm2"), (int, float))
                or not isfinite(sample["irradiance_wm2"])
                or sample["irradiance_wm2"] < 0
            ):
                raise IncompleteWeather(
                    "Section cleaning needs available irradiance; the selected forecast has missing radiation"
                )
            source = {
                **sample,
                "pv_kw": forecast["pv_kw"][i],
                "ambient_c": forecast["ambient_c"][i],
            }
            design = getattr(self, "planning_surface", self.surface).design(self.baseline, i)
            clean = interval(self.baseline, source, time, self.plant, self.weather)
            dirty = interval(design, source, time, self.plant, self.weather)
            rows.append(dict(time=time, sample=source, design=design, clean=clean, dirty=dirty))
        return rows

    def observed_treatments(self):
        if hasattr(self, "planning_surface"):
            if not hasattr(self, "pass_estimates"):
                self.pass_estimates = {}
            rows = []
            for e in self.surface.events:
                key = e["order_id"]
                self.pass_estimates.setdefault(key, getattr(self, "performance_prior", 0.9))
                rows.append(
                    {
                        **{
                            k: copy.deepcopy(e[k])
                            for k in (
                                "order_id",
                                "section",
                                "started_at",
                                "completed_at",
                                "effective_at",
                                "start_m2",
                                "end_m2",
                            )
                        },
                        "efficacy_start": self.pass_estimates[key],
                        "efficacy_end": self.pass_estimates[key],
                        "observation_basis": "Reported covered area; efficacy retains the estimate available at the first observation, never the private treatment coefficient",
                    }
                )
            return rows
        if hasattr(self, "performance_prior"):
            from methane.adaptation import treatment_observations

            return treatment_observations(self.surface.events, self.performance_prior)
        return self.surface.events

    def record(self, row, weather_reference, snapshots):
        p, w = self.plant, self.weather
        source, detail = row["sample"], row["dirty"]
        parameters = asdict(
            Parameters(p.solar_kw, w.loss_fraction, w.noct_c, w.temperature_coefficient)
        )
        parameters.update(
            design_json=json.dumps(row["design"], sort_keys=True),
            latitude=w.latitude,
            longitude=w.longitude,
            tilt=w.tilt,
            azimuth=w.azimuth,
        )
        return dict(
            schema_version="dispatch-lab/component-record/1",
            model_id="dispatch-lab/solar-sections",
            model_version="2",
            implementation_id="sections/2",
            parameters=parameters,
            before={},
            after={},
            inputs=dict(
                time=row["time"],
                irradiance_wm2=source["irradiance_wm2"],
                ambient_c=source["ambient_c"],
                scenario_pv_kw=source["pv_kw"],
                **(
                    {"lifecycle_factor": source["lifecycle_factor"]}
                    if "lifecycle_factor" in source
                    else {}
                ),
            ),
            flows=dict(
                output_kw=detail["output_kw"],
                reference_power_kw=dc_power(source["irradiance_wm2"], source["ambient_c"], p, w),
            ),
            diagnostics=dict(
                detail=copy.deepcopy(detail),
                weather_time=row["time"],
                reference=weather_reference,
                snapshot_ids=snapshots,
                surface_model=self.surface.version,
                surface_before=self.surface.snapshot(),
                baseline_design=copy.deepcopy(self.baseline),
            ),
            audits=copy.deepcopy(detail["audits"]),
        )

    def current_forecast_error(self, forecast, actual_output_kw):
        """Compare DC on the same surface and conversion basis, before observation overwrite."""
        sample = forecast["current_prediction_sample"]
        if (
            not isinstance(sample.get("irradiance_wm2"), (int, float))
            or not isfinite(sample["irradiance_wm2"])
            or sample["irradiance_wm2"] < 0
        ):
            raise IncompleteWeather("Section cleaning forecast has missing radiation")
        predicted = interval(
            getattr(self, "planning_surface", self.surface).design(self.baseline),
            sample,
            forecast["times"][0],
            self.plant,
            self.weather,
        )
        return actual_output_kw - predicted["output_kw"]
