"""Observation-only performance adaptation; no fault or execution ports.

These bounded point estimators are illustrative identification rules, not calibrated
posteriors. Their complete operands and initial assumptions are saved per decision.
"""

import copy
import math
from dataclasses import replace

from methane.provenance import digest
from methane.pv import dc_power

VERSION = "observed-performance/1"
SOLAR_PATHS = {
    "weather.loss_fraction",
    "weather.noct_c",
    "weather.temperature_coefficient",
    "solar.efficiency",
    "solar.noct_c",
}
SERVICE_PATHS = {
    "field_operations.cleaning_removal_fraction",
    "field_operations.mission_failure_probability",
    "field_operations.repair_success_probability",
}
DEFAULT = dict(
    version=VERSION,
    mode="adaptive",
    gain=0.35,
    minimum_samples=2,
    minimum_solar_kw=30.0,
    solar_support=[0.1, 2.0],
)
SCOPE = (
    "Illustrative observation-only estimates. Current hourly mean power, irradiance, "
    "ambient temperature and the existing ideal surface monitor are assumed observed. "
    "A solar multiplier does not identify a unique fault or calibrate individual physical "
    "parameters. Observed ranges are not confidence intervals. Completed work is not proof "
    "of successful repair. No future weather or private service outcomes enter the estimator."
)


def validate(value):
    if not isinstance(value, dict) or set(value) != set(DEFAULT):
        raise ValueError("Performance adaptation needs every versioned assumption explicitly")
    if value["version"] != VERSION or value["mode"] not in ("fixed", "adaptive"):
        raise ValueError("Unsupported performance adaptation mode")
    if (
        type(value["minimum_samples"]) is not int
        or not 1 <= value["minimum_samples"] <= 24
        or not isinstance(value["gain"], (int, float))
        or not 0 < value["gain"] <= 1
        or not isinstance(value["minimum_solar_kw"], (int, float))
        or not math.isfinite(value["minimum_solar_kw"])
        or value["minimum_solar_kw"] <= 0
    ):
        raise ValueError("Invalid performance adaptation evidence threshold or gain")
    bounds = value["solar_support"]
    if (
        not isinstance(bounds, list)
        or len(bounds) != 2
        or any(not isinstance(v, (int, float)) or not math.isfinite(v) for v in bounds)
        or not 0 < bounds[0] <= 1 <= bounds[1] <= 10
    ):
        raise ValueError("Declare a finite solar multiplier support containing one")
    return copy.deepcopy(value)


def required(world):
    return bool(
        world
        and (
            world.get("adaptation")
            or world.get("autonomy")
            or any(
                d["visibility"] == "hidden" and d["path"] in SOLAR_PATHS | SERVICE_PATHS
                for d in world["draws"]
            )
        )
    )


def split_weather(weather, actual, controller):
    """Keep execution samples; reconstruct ONLY saved forecast conversion with nominal inputs.

    Raw irradiance and forecast issue boundaries are preserved. Retain explicitly
    injected generation stress independently from conversion model discrepancy.
    """
    from methane.solar_model import interval

    marker = dict(
        version=VERSION, controller=digest(controller.to_dict()), execution=digest(actual.to_dict())
    )
    if weather.get("performance_boundary") == marker:
        return weather
    if weather.get("performance_boundary"):
        raise ValueError("Saved weather has a different original performance boundary")
    out = copy.deepcopy(weather)
    source = weather.get("solar_reference_weather", weather)
    # The source conversion identity is recorded, never inferred from future output.
    from methane.config import Config

    reference = Config.from_dict(weather.get("solar_reference_config", actual.to_dict()))
    for target, original in [
        (out.get("template", {}), source.get("template", {})),
        *[
            (v["data"], s["data"])
            for v, s in zip(out.get("vintages", []), source.get("vintages", []), strict=True)
        ],
    ]:
        for time, row in original.items():
            sample = nominal_sample(row, reference, controller)
            if controller.solar:
                detail = interval(
                    controller.solar, sample, time, controller.plant, controller.weather
                )
                sample.update(pv_kw=detail["output_kw"], solar_detail=detail)
            target[time] = sample
    out["performance_boundary"] = marker
    return out


def nominal_sample(sample, source_config, target_config):
    if sample.get("irradiance_wm2") is None:
        raise ValueError("Performance separation requires recorded irradiance; no reconstruction")
    old = dc_power(
        sample["irradiance_wm2"], sample["ambient_c"], source_config.plant, source_config.weather
    )
    stress = sample["pv_kw"] / old if old > 1e-8 else 1.0
    new = dc_power(
        sample["irradiance_wm2"], sample["ambient_c"], target_config.plant, target_config.weather
    )
    return {**copy.deepcopy(sample), "pv_kw": new * stress}


def current_nominal(sample, time, config):
    """No actual conversion parameters: ideal contemporaneous weather measurement only."""
    power = dc_power(sample["irradiance_wm2"], sample["ambient_c"], config.plant, config.weather)
    if config.solar:
        from methane.solar_model import interval

        return interval(
            config.solar, {**sample, "pv_kw": power}, time, config.plant, config.weather
        )["output_kw"]
    return power


class Observer:
    def __init__(self, options, field):
        self.options = validate(options)
        self.field = field
        self.solar = 1.0
        self.cleaning = field.cleaning_removal_fraction
        self.samples = {"solar": [], "cleaning": []}
        self.seen_hour = -1
        self.seen_service = -1
        self.solar_record = None
        self.service_record = None

    def solar_observation(self, hour, expected_kw, measured_kw):
        if hour <= self.seen_hour:
            raise ValueError("Solar observations must advance the decision clock")
        self.seen_hour = hour
        before = self.solar
        status = "insufficient evidence"
        ratio = None
        if expected_kw >= self.options["minimum_solar_kw"]:
            ratio = measured_kw / expected_kw
            lo, hi = self.options["solar_support"]
            if not math.isfinite(ratio) or not lo <= ratio <= hi:
                status = "outside model support"
            else:
                self.samples["solar"].append(ratio)
                status = "collecting evidence"
                if len(self.samples["solar"]) >= self.options["minimum_samples"]:
                    status = "estimated"
                    if self.options["mode"] == "adaptive":
                        self.solar += self.options["gain"] * (ratio - self.solar)
        self.solar_record = dict(
            hour=hour,
            expected_kw=expected_kw,
            measured_kw=measured_kw,
            residual_kw=measured_kw - expected_kw,
            ratio=ratio,
            before=before,
            after=self.solar,
            status=status,
            informative_intervals=len(self.samples["solar"]),
            observed_range=[min(self.samples["solar"]), max(self.samples["solar"])]
            if self.samples["solar"]
            else None,
            interpretation="Effective conversion multiplier conditional on observed weather; "
            "weather measurement error and conversion faults are not identified separately",
        )
        return copy.deepcopy(self.solar_record)

    def service_observation(self, hour, packet):
        """Only an explicit observation packet, not a runtime or physical effects record."""
        if hour <= self.seen_service:
            raise ValueError("Service observations must advance the clock")
        self.seen_service = hour
        if set(packet) != {"before", "after", "accumulation", "passes", "basis"}:
            raise ValueError("Only declared surface observation operands are accepted")
        before = self.cleaning
        status, value = "insufficient evidence", None
        if packet["passes"] > 0 and packet["before"] > 1e-8:
            remaining = (packet["after"] - packet["accumulation"]) / packet["before"]
            if 0 <= remaining <= 1:
                value = 1 - remaining ** (1 / packet["passes"])
                self.samples["cleaning"].append(value)
                status = "estimated"
                if self.options["mode"] == "adaptive":
                    self.cleaning += self.options["gain"] * (value - self.cleaning)
            else:
                status = "outside model support"
        self.service_record = dict(
            hour=hour,
            available_at=hour + 1,
            inputs=copy.deepcopy(packet),
            before=before,
            after=self.cleaning,
            estimated_removal=value,
            status=status,
            informative_updates=len(self.samples["cleaning"]),
            interpretation="Removal inferred from declared ideal surface observations and recorded coverage. "
            "An ineffective pass does not identify its mechanical cause.",
        )
        return copy.deepcopy(self.service_record)

    def field_estimate(self):
        return replace(self.field, cleaning_removal_fraction=self.cleaning)

    def forecast(self, forecast, limit_kw=float("inf")):
        result = copy.deepcopy(forecast)
        result["nominal_pv_kw"] = list(forecast["pv_kw"])
        result["pv_kw"] = [
            v if i == 0 else min(limit_kw, max(0, v * self.solar))
            for i, v in enumerate(forecast["pv_kw"])
        ]
        result["performance_multiplier"] = self.solar
        return result

    def record(self):
        return dict(
            version=VERSION,
            options=copy.deepcopy(self.options),
            solar=copy.deepcopy(self.solar_record),
            services=copy.deepcopy(self.service_record),
            scope=SCOPE,
        )


def surface_observation(record, runtime):
    """Make a measurement packet from declared surface monitors and accepted work.

    No physical treatment receipt, sampled efficacy, random variate or repair truth
    is read. Optical removal uses the measured patch change over reported coverage.
    Brush allowance and coverage rates remain disclosed assumptions.
    """
    c = runtime.config
    if runtime.optical and getattr(runtime, "autonomy", None):
        exposure, removed, exposure_error, removal_error = 0.0, 0.0, 0.0, 0.0
        # Area is a declared work-encoder observation; surface operands come
        # exclusively from bounded monitor readings, not the effect coefficient.
        for event in record.get("surface_events", []):
            section = event["section"]
            if event.get("method", "dry-brush") != "dry-brush":
                continue
            for old in record["observed_surface_before"][section]:
                for new in record["observed_surface_after"][section]:
                    area = max(
                        0,
                        min(event["end_m2"], old["end_m2"], new["end_m2"])
                        - max(event["start_m2"], old["start_m2"], new["start_m2"]),
                    )
                    brush = (
                        record["brush_before_m2"] + event["start_m2"]
                    ) / runtime.options.brush_life_m2
                    exposure += area * old["removable"] * brush
                    removed += area * (old["removable"] + c.soiling_per_day / 24 - new["removable"])
                    exposure_error += area * brush * runtime.autonomy["surface_absolute_error"]
                    removal_error += 2 * area * runtime.autonomy["surface_absolute_error"]
        return dict(
            before=exposure,
            after=exposure - removed,
            accumulation=0.0,
            passes=1 if exposure > 1e-8 else 0,
            measurement_bounds=dict(
                exposure=[max(0, exposure - exposure_error), exposure + exposure_error],
                removed=[removed - removal_error, removed + removal_error],
            ),
            basis="Bounded removable-surface readings and reported covered area. Effective removal includes brush condition; correlated partial readings are not independent trials.",
        )
    packet = dict(
        before=record["soiling_before"],
        after=record["soiling_after"],
        accumulation=c.soiling_per_day / 24,
        passes=record["cleanings_completed"],
        basis="Existing ideal lumped surface monitor; no sensor calibration claimed",
    )
    if not runtime.optical:
        return packet
    from methane.services.adapters import schedule

    exposure, removed = 0.0, 0.0
    for event in record["mission_events"]:
        if event["kind"] != "interval" or event["phase"] != "perform":
            continue
        mission = runtime.executive.missions[event["order_id"]]
        plan = mission.plan
        if plan.order.action != "clean-section":
            continue  # Other cleaning methods need their own observation equation.
        section = plan.interface.target_asset_id
        start = next(a for a, _, stage in schedule(plan) if stage.effect)
        rate = runtime.options.cleaning_area_m2ph
        a, b = (event["start"] - start) * rate, (event["end"] - start) * rate
        brush_at_start = record["brush_before_m2"] + max(0, record["hour"] - start) * rate
        brush_factor = brush_at_start / runtime.options.brush_life_m2
        for old in record["surface_before"][section]:
            for new in record["surface_after"][section]:
                area = max(
                    0,
                    min(b, old["end_m2"], new["end_m2"]) - max(a, old["start_m2"], new["start_m2"]),
                )
                if new["removable"] >= 0.3 or area == 0:
                    continue  # Saturation destroys the inverse observation equation.
                exposure += area * old["removable"] * brush_factor
                removed += area * (old["removable"] + c.soiling_per_day / 24 - new["removable"])
    return dict(
        before=exposure,
        after=exposure - removed,
        accumulation=0.0,
        passes=1 if exposure > 1e-8 else 0,
        basis="Existing ideal patch monitor, recorded covered area and brush allowance; "
        "saturated patches and portable treatments excluded",
    )


def treatment_observations(events, prior):
    """Derive ongoing-pass evidence from ideal pre/post surface measurements.

    The planner needs a pass estimate for already-started work. It never receives
    the private sampled efficacy field. Zero removable material supplies no evidence.
    """
    result, inferred = [], {}
    for event in events:
        key = event["order_id"]
        if key not in inferred:

            def material(snapshot, event=event):
                return sum(
                    max(
                        0, min(p["end_m2"], event["end_m2"]) - max(p["start_m2"], event["start_m2"])
                    )
                    * p["removable"]
                    for p in snapshot["patches"]
                )

            before, after = material(event["before"]), material(event["after"])
            inferred[key] = 1 - after / before if before > 1e-8 else prior
        result.append(
            {
                **{
                    k: copy.deepcopy(event[k])
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
                "efficacy_start": inferred[key],
                "efficacy_end": inferred[key],
                "observation_basis": "Inferred from existing ideal pre/post surface monitors; no repair truth",
            }
        )
    return result


def metrics(rows):
    estimates = [r["decision"]["performance_estimates"] for r in rows]
    errors = [
        abs(a["decision"]["forecast"]["pv_kw"][1] - b["pv_kw"])
        for a, b in zip(rows, rows[1:], strict=False)
        if len(a["decision"]["forecast"]["pv_kw"]) > 1
    ]
    last = estimates[-1] if estimates else None
    return dict(
        one_step_pv_mae_kw=sum(errors) / len(errors) if errors else None,
        ending_solar_multiplier=last["solar"]["after"] if last else None,
        solar_outside_support_hours=sum(
            e["solar"]["status"] == "outside model support" for e in estimates
        ),
        scope="One-step forecast versus next observed available power; includes weather and service changes. Not an isolated conversion-calibration score.",
    )


def report_html(result):
    """Offline reading of original recorded updates; no live recalculation or network."""
    import html

    esc = html.escape
    body = '<!doctype html><meta charset="utf-8"><title>Recorded performance estimates</title>'
    body += "<style>body{background:#222;color:#ffa12b;font:15px monospace;max-width:1100px;margin:3em auto;padding:1em}table{border-collapse:collapse;width:100%}td,th{padding:.6em;border-bottom:1px solid #66502f;text-align:left}p{line-height:1.7}a{color:inherit}</style>"
    body += "<h1>What the controller expected and learned</h1><p>" + esc(SCOPE) + "</p>"
    body += (
        "<p>Run "
        + esc(result["run_id"])
        + ". Values below were recorded during execution; physical draws remain explicitly retrospective in the uncertainty report.</p>"
    )
    for name, rows in result["records"].items():
        body += (
            "<h2>"
            + esc(name)
            + "</h2><table><tr><th>Decision hour</th><th>Expected / observed solar · kW</th><th>Multiplier before → after</th><th>Evidence</th><th>Cleaning estimate for this decision</th></tr>"
        )
        for row in rows:
            record = row["decision"].get("performance_estimates")
            if not record:
                continue
            s, field = record["solar"], record.get("services")
            cells = [
                str(row["hour"]),
                f"{s['expected_kw']:.3f} / {s['measured_kw']:.3f}",
                f"{s['before']:.4f} → {s['after']:.4f}",
                s["status"],
                f"{field['after']:.4f}; available H{field['available_at']}"
                if field
                else "Original assumption",
            ]
            body += "<tr>" + "".join("<td>" + esc(c) + "</td>" for c in cells) + "</tr>"
        body += "</table>"
    return body
