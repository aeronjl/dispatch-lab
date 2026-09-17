"""Versioned uncertainty contracts, coherent worlds and observation processes.

Bounds are experimental support, not probability. No distribution is inferred
from a reference default or from a literature range. Kernels stay deterministic.
"""

import copy
import itertools
import json
import math
import random
import re

from methane.provenance import digest

VERSION = "dispatch-lab/uncertainty/1"
HIDDEN_PLANT = {
    "roundtrip_efficiency",
    "specific_energy_kwh_per_kg",
    "start_energy_kwh",
    "thermal_capacity_kwh_per_k",
    "heat_loss_kw_per_k",
    "auxiliary_kw",
    "methane_electric_kwh_per_kg",
    "cooling_electric_fraction",
    "heater_max_kw",
    "cooling_max_kw",
    "electrolyser_kw",
    "min_load_fraction",
    "methane_max_kgph",
    "methane_min_kgph",
    "temperature_min_c",
    "temperature_max_c",
    "minimum_run_hours",
    "battery_c_rate",
    "battery_kwh",
    "h2_capacity_kg",
    "co2_capacity_kg",
    "initial_soc",
    "initial_h2_kg",
    "initial_co2_kg",
}
CHANNELS = {
    "power_kw": "kW",
    "hydrogen_flow_kg": "kg/interval",
    "h2_inventory_kg": "kg",
    "h2_outflow_kg": "kg/interval",
    "battery_kwh": "kWh",
    "co2_kg": "kg",
    "temperature_c": "°C",
}
SCOPE = {
    "commissioning": "Work quantities, acceptance challenges, access, support and invoicing use disclosed assumptions. Accepted capacity changes execution only after a receipt; no measured robot construction rate is inferred.",
    "lifecycle-condition": "PV calendar loss and PEM usage growth are reduced literature hypotheses. Observation noise, reporting delay, spare price and replacement outcomes need equipment evidence; model uncertainty is not removed by repeatable seeds.",
    "layout": "Design alternatives; geometry and support compatibility must remain consistent.",
    "thermal": "Persistent plant properties; heat capacity and heat loss may be dependent. A fit under controlled coolant does not identify ambient heat loss.",
    "chemistry": "Implemented ideal stoichiometry is fixed. Real conversion, gas quality and kinetics remain structural gaps, not perturbed molecular weights.",
    "electrolyser": "Persistent performance and startup assumptions. AC-system and DC-stack fits have different boundaries; do not scale either silently.",
    "battery": "Efficiency, usable capacity, power and aging are dependent on equipment, load and age. A constant efficiency sweep tests this abstraction only.",
    "gas-storage": "Capacity and inventory are distinct; pressure heel, leakage and compression are omitted mechanisms, not random inventory losses.",
    "solar": "Section geometry, shared weather and conversion parameters are dependent. Preserve joint fits; site transfer uncertainty is separate from fit uncertainty.",
    "weather": "Saved forecast vintages and temporally coherent weather trajectories. Noise at independent hours cannot represent a cloudy-day forecast error.",
    "sensing": "Per-reading noise, persistent channel bias and elapsed-time drift have different clocks. Public error budgets do not reveal sampled errors.",
    "faults": "Event hazards, onset, severity and repairability are conditional assumptions. Injected scenarios do not estimate field failure frequencies.",
    "cleaning": "Surface/weather exposure, removal effectiveness, wear and mission failure depend on the work and hardware family.",
    "inspection": "Observation quality, latency, access, drift and common causes affect what inspection can establish. Unknown repair capability remains unavailable.",
    "recovery": "Outcome branches and restoration tests are conditional on incident class, isolation and available information; priors are illustrative.",
    "support": "Logistics, weather access, energy, stock and crew availability are coupled. Cost and time uncertainty cannot create missing capabilities.",
    "maintenance": "Lifetime, degradation and consumables depend on usage and calendar exposure. Key event randomness to the work, not controller call order.",
    "economics": "Prices and life/usage allowances are assumptions. Dispatch prices remain frozen separately from retrospective accounting prices.",
    "control": "Policy choices are selected, not physical uncertainty. Compare policies on paired worlds; solver repetitions are a separate numerical layer.",
    "coupling": "Shared resource balances remain constraints for every world. Optional plant interfaces offer disclosed constant or source-scoped conversion/cooling and heat-balance models, pressure compatibility and finite water assumptions. User-selected scenario ranges are not calibrated probability distributions. Hidden interface variations are not supported. Invalid combinations are recorded, never clipped into validity.",
    "experiment": "Boundary, horizon, seed and model choice define an experiment. Scenario frequencies are not empirical event probabilities.",
}


def leaves(value, prefix=""):
    """Concrete paths retain list indices; repeated assets can vary independently."""
    if isinstance(value, dict):
        return {
            p: v for k, x in value.items() for p, v in leaves(x, f"{prefix}.{k}".strip(".")).items()
        }
    if isinstance(value, (list, tuple)):
        return {p: v for i, x in enumerate(value) for p, v in leaves(x, f"{prefix}.{i}").items()}
    return {prefix: value}


def canonical(path):
    return re.sub(r"(?<=\.)\d+(?=\.|$)", "[]", path)


def assign(value, path, item):
    parts = path.split(".")
    current = value
    for part in parts[:-1]:
        current = current[int(part)] if isinstance(current, list) else current[part]
    key = int(parts[-1]) if isinstance(current, list) else parts[-1]
    if (isinstance(current, dict) and key not in current) or isinstance(current[key], (dict, list)):
        raise ValueError("Select an existing scalar parameter: " + path)
    current[key] = copy.deepcopy(item)


def hidden_supported(path):
    from methane.adaptation import SERVICE_PATHS, SOLAR_PATHS
    from methane.services.uncertain_timing import PATHS

    return (
        path in SERVICE_PATHS | SOLAR_PATHS | PATHS
        or path.startswith("plant.")
        and path.split(".", 1)[1] in HIDDEN_PLANT
        or path.startswith("costs.")
        or path == "sensors.noise_fraction"
        or path.startswith("faults.")
        and not path.endswith(("hardware_model", "lifecycle"))
        or path
        in {
            "scenario.capacity_fraction",
            "scenario.flow_bias_fraction",
            "scenario.fault_start_hour",
            "scenario.fault_duration_hours",
        }
    )


def validate_world(world):
    """Execution rejects unsupported mismatches even when called outside the editor."""
    from methane.services.uncertain_timing import PATHS

    actual, nominal = leaves(world["config"]), leaves(world["controller_config"])
    for values in (actual, nominal):
        for path in PATHS:
            values.setdefault(path, 1)
    differences = {p for p in actual.keys() | nominal.keys() if actual.get(p) != nominal.get(p)}
    for path in differences:
        if not hidden_supported(path):
            raise ValueError("Hidden execution adapter is unavailable for " + path)
        declared = next(
            (
                d
                for d in world.get("draws", [])
                if d.get("path") == path and d.get("visibility") == "hidden"
            ),
            None,
        )
        if (
            declared is None
            or declared.get("value") != actual[path]
            or declared.get("nominal") != nominal[path]
        ):
            raise ValueError("Hidden execution mismatch is not bound to its original draw: " + path)
    from methane.adaptation import SERVICE_PATHS, validate

    if differences & SERVICE_PATHS and (
        not world["config"]["field_operations"]["enabled"]
        or world["config"]["service_system"] is None
    ):
        raise ValueError("Hidden service outcomes require enabled fractional service contracts")
    if "adaptation" in world:
        validate(world["adaptation"])
    from methane.services.uncertain_timing import PATHS

    if differences & PATHS and "autonomy" not in world:
        raise ValueError("Hidden duration factors require declared autonomy reservation bounds")
    if "autonomy" not in world and any(actual.get(p, 1) != 1 for p in PATHS):
        raise ValueError("Duration factors require the bounded autonomy execution model")
    if "autonomy" in world:
        from methane.autonomy import validate_world as validate_autonomy_world

        validate_autonomy_world(world)


def catalogue(config):
    from methane.adaptation import DEFAULT
    from methane.adaptation import SCOPE as PERFORMANCE_SCOPE
    from methane.assumptions import registry
    from methane.autonomy import DEFAULT as AUTONOMY_DEFAULT
    from methane.autonomy import SCOPE as AUTONOMY_SCOPE

    review = registry()
    actual = leaves(config)
    if config.get("service_system") is not None:
        from methane.services.uncertain_timing import PATHS

        for path in PATHS:
            actual.setdefault(path, 1)
    parameters = []
    for p in review["parameters"]:
        category = p["category"]
        representation = "unquantified"
        if category in ("design", "policy"):
            representation = "selected-choice"
        elif category == "implementation":
            representation = (
                "model-choice"
                if p["path"].startswith("models.")
                or p["path"].endswith(
                    (
                        "_model",
                        ".version",
                        ".model",
                        "research.converter",
                        "research.electrolysis_heat",
                        "research.cooler",
                        "research.reactor_heat",
                    )
                )
                else "fixed-convention"
            )
        elif p.get("sensitivity_values"):
            representation = "scenario-values"
        elif category == "scenario":
            representation = "scenario-assumption"
        matches = {path: v for path, v in actual.items() if canonical(path) == p["path"]}
        parameters.append(
            {
                "id": p["id"],
                "path": p["path"],
                "label": p["label"],
                "unit": p["unit"],
                "group": p["group"],
                "category": category,
                "representation": representation,
                "values": matches,
                "active": bool(matches),
                "reference_default": p["reference_default"],
                "suggested_values": p.get("sensitivity_values"),
                "suggestion_scope": p.get(
                    "sensitivity_scope",
                    "No quantitative uncertainty has been established. A user-authored stress test needs its own rationale.",
                ),
                "sources": review["groups"][p["group"]]["sources"],
                "evidence": p["evidence_status"],
                "evidence_needed": review["groups"][p["group"]]["next_data"],
                "mechanism_scope": SCOPE[p["group"]],
                "timing": "World-level parameter; configured event/observation mechanisms retain their own clocks",
                "hidden_supported": hidden_supported(p["path"]),
            }
        )
    known = {p["path"] for p in parameters}
    result = {
        "schema_version": VERSION,
        "registry_edition": review["edition"],
        "adaptation": {"defaults": copy.deepcopy(DEFAULT), "scope": PERFORMANCE_SCOPE},
        "autonomy": {"defaults": copy.deepcopy(AUTONOMY_DEFAULT), "scope": AUTONOMY_SCOPE},
        "parameters": parameters,
        "groups": SCOPE,
        "sources": review["sources"],
        "unregistered": [
            p for p, v in actual.items() if canonical(p) not in known and v is not None
        ],
        "scope": "Every registered parameter has an explicit uncertainty status. Unquantified is not exact. Scenario support is not a probability distribution. Disabled optional mechanisms are not enabled by this catalogue.",
        "knowledge_boundary": "Hidden plant, conversion, sensor and service outcomes use separate execution ports. Opt-in service uncertainty adds private time factors within declared support and current-only support status observations. Other hidden weather-model choices, unimplemented mechanisms and unsupported capabilities remain rejected. Bounds, sensor models and scenario weights are assumptions, not calibration.",
    }
    from methane.duration_population import AUTONOMY_VERSION, default_model

    result["autonomy"]["equipment_job_defaults"] = {
        **copy.deepcopy(AUTONOMY_DEFAULT),
        "version": AUTONOMY_VERSION,
        "duration_model": default_model(),
    }
    result["content_hash"] = digest(result)
    return result


def snapshot(config, world=None):
    result = catalogue(config)
    result.pop("content_hash")
    result["world"] = copy.deepcopy(world)
    result["context"] = (
        "Recorded uncertainty contract; a single trace is one realization, not an ensemble mean."
    )
    result["content_hash"] = digest(result)
    return result


def rng(seed, *keys):
    return random.Random(int(digest([VERSION, seed, *keys]), 16))


def validate_spec(spec, basis):
    if spec.get("schema_version") != VERSION:
        raise ValueError("Unsupported uncertainty specification")
    allowed = {
        "schema_version",
        "seed",
        "worlds",
        "inner_seeds",
        "design",
        "blocks",
        "measurements",
        "rationale",
        "adaptation",
        "autonomy",
        "support_events",
    }
    if set(spec) - allowed:
        raise ValueError("Unknown uncertainty fields: " + ", ".join(sorted(set(spec) - allowed)))
    for name, limit in (("worlds", 128), ("seed", 2**32 - 1)):
        n = spec.get(name)
        if type(n) is not int or not (1 if name == "worlds" else 0) <= n <= limit:
            raise ValueError(f"{name} must be an integer within the supported limit {limit}")
    seeds = spec.get("inner_seeds")
    if (
        not isinstance(seeds, list)
        or not 1 <= len(seeds) <= 20
        or len(set(seeds)) != len(seeds)
        or any(type(s) is not int or not 0 <= s < 2**32 for s in seeds)
    ):
        raise ValueError("Supply 1–20 distinct nonnegative event seeds")
    if spec.get("design") not in ("space-filling", "probability", "factorial", "screening"):
        raise ValueError("Choose space-filling, factorial, screening or probability sampling")
    if not isinstance(spec.get("rationale"), str) or not spec["rationale"].strip():
        raise ValueError("Record the scope and rationale of this uncertainty experiment")
    if "adaptation" in spec:
        from methane.adaptation import validate

        validate(spec["adaptation"])
    if "autonomy" in spec:
        from methane.autonomy import validate as validate_autonomy

        validate_autonomy(spec["autonomy"])
    if "support_events" in spec:
        from methane.autonomy import validate_support_events

        if "autonomy" not in spec:
            raise ValueError("Private support events require an autonomy observation contract")
        validate_support_events(spec["support_events"])
    blocks = spec.get("blocks", [])
    if not isinstance(blocks, list) or len(blocks) > 512:
        raise ValueError("At most 512 dependent parameter blocks per study")
    if not blocks and not spec.get("measurements") and not spec.get("autonomy"):
        raise ValueError(
            "Select a parameter block or observation model before running an uncertainty study"
        )
    present = leaves(basis)
    if spec.get("autonomy") and basis.get("service_system") is not None:
        from methane.services.uncertain_timing import PATHS

        for path in PATHS:
            present.setdefault(path, 1)
    used, ids = set(), set()
    for b in blocks:
        if set(b) - {
            "id",
            "paths",
            "kind",
            "rows",
            "low",
            "high",
            "mode",
            "weights",
            "visibility",
            "source",
            "rationale",
        }:
            raise ValueError("Unknown parameter-block field")
        if not isinstance(b.get("id"), str) or not b["id"] or b["id"] in ids:
            raise ValueError("Each uncertainty block needs a unique stable identity")
        ids.add(b["id"])
        paths = b.get("paths", [])
        if not isinstance(paths, list) or not paths or len(set(paths)) != len(paths):
            raise ValueError("A block needs distinct concrete parameter paths")
        for path in paths:
            if path not in present or path in used:
                raise ValueError("Missing or multiply sampled parameter: " + path)
            if path in ("scenario.seed", "rng_policy"):
                raise ValueError(
                    "Random streams are controlled by the study, not sampled as parameters"
                )
            if b.get("visibility") == "hidden" and not hidden_supported(path):
                raise ValueError(
                    "Hidden execution adapter unavailable for "
                    + path
                    + "; use an explicitly disclosed comparison"
                )
            used.add(path)
        if (
            b.get("visibility") not in ("hidden", "disclosed")
            or not b.get("rationale")
            or not b.get("source")
        ):
            raise ValueError(
                "Every block needs knowledge visibility, source and rationale; 'user stress assumption' is an explicit evidence gap"
            )
        kind = b.get("kind")
        if kind in ("values", "joint-empirical"):
            rows = b.get("rows")
            if (
                not isinstance(rows, list)
                or not rows
                or len(rows) > 2000
                or any(not isinstance(r, list) or len(r) != len(paths) for r in rows)
            ):
                raise ValueError("Each joint row must supply every member of the block")
            weights = b.get("weights")
            if weights is not None and (
                len(weights) != len(rows)
                or any(
                    type(w) not in (int, float) or not math.isfinite(w) or w <= 0 for w in weights
                )
                or not math.isclose(sum(weights), 1, abs_tol=1e-9)
            ):
                raise ValueError("Explicit joint-row probabilities must be positive and sum to one")
            if spec["design"] == "probability" and kind == "values" and weights is None:
                raise ValueError(
                    "Scenario values have no probabilities. Supply defensible weights or use a scenario design"
                )
        elif kind in ("bounds", "uniform", "triangular"):
            if len(paths) != 1 or type(present[paths[0]]) not in (int, float):
                raise ValueError(
                    "Continuous support requires one numeric parameter; use joint rows for dependencies"
                )
            low, high = b.get("low"), b.get("high")
            if (
                any(type(x) not in (int, float) or not math.isfinite(x) for x in (low, high))
                or low >= high
            ):
                raise ValueError("Finite lower bound must be below upper bound")
            if integer_parameter(basis, paths[0]):
                raise ValueError(
                    "Integer parameters require explicit discrete values; no rounding sampled inputs"
                )
            if kind == "triangular" and (
                type(b.get("mode")) not in (int, float) or not low <= b["mode"] <= high
            ):
                raise ValueError("Triangular mode must lie within support")
            if kind == "bounds" and spec["design"] == "probability":
                raise ValueError("Bounds alone do not define probability")
        else:
            raise ValueError("Unsupported uncertainty representation")
    validate_measurements(spec.get("measurements", {}))
    # Also rejects NaN nested in joint rows, and non-JSON inputs.
    digest(spec)
    value = copy.deepcopy(spec)
    value["blocks"] = sorted(value["blocks"], key=lambda b: b["id"])
    return value


def integer_parameter(basis, path):
    """Read declared dataclass types; a float assumption may have an integer default."""
    from dataclasses import is_dataclass
    from typing import get_type_hints

    from methane.config import Config

    current = Config.from_dict(basis)
    parts = path.split(".")
    for part in parts[:-1]:
        current = (
            getattr(current, part)
            if is_dataclass(current)
            else current[int(part)]
            if isinstance(current, (list, tuple))
            else current[part]
        )
    return is_dataclass(current) and get_type_hints(type(current)).get(parts[-1]) is int


def block_value(block, u):
    kind = block["kind"]
    if kind in ("values", "joint-empirical"):
        rows = block["rows"]
        weights = block.get("weights") or [1 / len(rows)] * len(rows)
        cumulative = 0
        for row, weight in zip(rows, weights, strict=True):
            cumulative += weight
            if u < cumulative:
                return copy.deepcopy(row)
        return copy.deepcopy(rows[-1])
    low, high = block["low"], block["high"]
    if kind == "triangular":
        f = (block["mode"] - low) / (high - low)
        x = (
            low + math.sqrt(u * (high - low) * (block["mode"] - low))
            if u < f
            else high - math.sqrt((1 - u) * (high - low) * (high - block["mode"]))
        )
    else:
        x = low + u * (high - low)
    return [x]


def resolve(spec, basis):
    """Freeze the draw matrix. Invalid combinations remain visible case records."""
    from methane.config import Config

    basis = json.loads(json.dumps(basis, allow_nan=False))
    if spec.get("autonomy") and basis.get("service_system") is not None:
        from methane.services.uncertain_timing import PATHS

        for path in PATHS:
            basis["service_system"].setdefault(path.split(".")[1], 1)
    spec = validate_spec(spec, basis)
    blocks = sorted(spec["blocks"], key=lambda b: b["id"])
    design, n = spec["design"], spec["worlds"]
    uniforms = {}
    for b in blocks:
        generator = rng(spec["seed"], b["id"])
        # Separate per-block streams: ordering/adding blocks cannot perturb existing draws.
        values = (
            [(i + 0.5) / n for i in range(n)]
            if design == "space-filling"
            else [generator.random() for _ in range(n)]
        )
        if design == "space-filling":
            generator.shuffle(values)
        uniforms[b["id"]] = values
    selections = []
    if not blocks:
        selections = [{}]
    elif design == "factorial":
        if any(b["kind"] not in ("values", "joint-empirical") for b in blocks):
            raise ValueError("Factorial designs require explicit joint rows")
        count = math.prod(len(b["rows"]) for b in blocks)
        if count > n:
            raise ValueError(
                f"The complete factorial requires {count} worlds; increase the budget or use space-filling"
            )
        selections = [
            dict(zip((b["id"] for b in blocks), rows, strict=True))
            for rows in itertools.product(*(b["rows"] for b in blocks))
        ]
    elif design == "screening":
        selections = [{}]
        for b in blocks:
            rows = b.get("rows") or [[b["low"]], [b["high"]]]
            selections += [{b["id"]: row} for row in rows]
        if len(selections) > n:
            raise ValueError(f"Matched one-block screening needs {len(selections)} worlds")
    else:
        selections = [
            {b["id"]: block_value(b, uniforms[b["id"]][i]) for b in blocks} for i in range(n)
        ]
    worlds = []
    for i, chosen in enumerate(selections):
        actual, controller, draws = copy.deepcopy(basis), copy.deepcopy(basis), []
        for b in blocks:
            if b["id"] not in chosen:
                continue
            for path, value in zip(b["paths"], chosen[b["id"]], strict=True):
                assign(actual, path, value)
                if b["visibility"] == "disclosed":
                    assign(controller, path, value)
                draws.append(
                    {
                        "block": b["id"],
                        "path": path,
                        "value": value,
                        "nominal": leaves(basis)[path],
                        "visibility": b["visibility"],
                        "source": b["source"],
                    }
                )
        error = None
        try:
            from methane.adaptation import SERVICE_PATHS

            if any(d["visibility"] == "hidden" and d["path"] in SERVICE_PATHS for d in draws):
                if not actual["field_operations"]["enabled"] or actual["service_system"] is None:
                    raise ValueError(
                        "Hidden service outcomes require enabled fractional service contracts"
                    )
            for v in (actual, controller):
                resolved = json.loads(json.dumps(Config.from_dict(v).to_dict(), allow_nan=False))
                comparison = copy.deepcopy(v)
                if spec.get("autonomy") and comparison.get("service_system") is not None:
                    from methane.services.uncertain_timing import PATHS

                    keys = [p.split(".")[1] for p in PATHS]
                    if all(comparison["service_system"].get(k, 1) == 1 for k in keys):
                        for k in keys:
                            comparison["service_system"].pop(k, None)
                if resolved != comparison:
                    raise ValueError(
                        "Resolved configuration changes supplied values or introduces implicit defaults"
                    )
                v.clear()
                v.update(resolved)
        except (TypeError, ValueError, KeyError) as exc:
            error = str(exc)
        world = {
            "schema_version": VERSION,
            "specification_hash": digest(spec),
            "index": i,
            "draws": draws,
            "config": actual,
            "controller_config": controller,
            "measurements": spec.get("measurements", {}),
            **({"adaptation": copy.deepcopy(spec["adaptation"])} if "adaptation" in spec else {}),
            **(
                {
                    "autonomy": copy.deepcopy(spec["autonomy"]),
                    "support_events": copy.deepcopy(spec.get("support_events", [])),
                }
                if "autonomy" in spec
                else {}
            ),
            "status": "invalid-input" if error else "resolved",
            "error": error,
        }
        if not error:
            try:
                validate_world(world)
            except (TypeError, ValueError, KeyError) as exc:
                world.update(status="invalid-input", error=str(exc))
        world["world_id"] = digest(world)[:24]
        worlds.append(world)
    return worlds


def validate_measurements(channels):
    if not isinstance(channels, dict) or set(channels) - set(CHANNELS):
        raise ValueError("Unknown observation channel")
    for channel, c in channels.items():
        if set(c) != {"noise_sd", "bias_sd", "drift_sd_per_hour", "source"} or not c["source"]:
            raise ValueError(
                "Observation model needs noise, persistent bias, drift and source: " + channel
            )
        if any(
            type(c[k]) not in (int, float) or not math.isfinite(c[k]) or c[k] < 0
            for k in ("noise_sd", "bias_sd", "drift_sd_per_hour")
        ):
            raise ValueError("Observation uncertainty scales must be finite and nonnegative")


def measure(observation, channels, seed, hour):
    """No clipping: uncertain readings may exceed physical limits. Units are channel units.

    Bias and linear drift rate are sampled once per channel/device, white noise
    per interval. This is an explicit Gaussian error assumption, not calibration.
    """
    value = copy.deepcopy(observation)
    budgets, truth = {}, {}
    for channel, c in channels.items():
        bias = rng(seed, channel, "bias").gauss(0, c["bias_sd"])
        drift = rng(seed, channel, "drift").gauss(0, c["drift_sd_per_hour"])
        noise = rng(seed, channel, "reading", hour).gauss(0, c["noise_sd"])
        elapsed = max(0, hour + 1)
        value[channel] += bias + elapsed * drift + noise
        budgets[channel] = {
            "noise_sd": c["noise_sd"],
            "bias_sd": c["bias_sd"],
            "drift_sd_per_hour": c["drift_sd_per_hour"],
            "elapsed_hours": elapsed,
            "unit": CHANNELS[channel],
        }
        truth[channel] = {"bias": bias, "drift_per_hour": drift, "noise": noise}
    if channels:
        value["measurement_uncertainty"] = budgets
    return value, truth


def residual_budgets(before, after, specific_energy):
    """Independent channel error propagation. Persistent inventory bias cancels.

    Returns standard uncertainties of tracking, balance-minus-power, and
    flow-minus-balance in native units, not posterior state certainty.
    """
    prior, now = before.get("measurement_uncertainty", {}), after.get("measurement_uncertainty", {})

    def variance(name):
        c = now.get(name, {})
        return (
            c.get("noise_sd", 0) ** 2
            + c.get("bias_sd", 0) ** 2
            + (c.get("elapsed_hours", 0) * c.get("drift_sd_per_hour", 0)) ** 2
        )

    tank, old = now.get("h2_inventory_kg", {}), prior.get("h2_inventory_kg", {})
    inventory_delta = (
        tank.get("noise_sd", 0) ** 2
        + old.get("noise_sd", 0) ** 2
        + (
            (tank.get("elapsed_hours", 0) - old.get("elapsed_hours", 0))
            * tank.get("drift_sd_per_hour", 0)
        )
        ** 2
    )
    balance = inventory_delta + variance("h2_outflow_kg")
    power = variance("power_kw")
    return {
        "tracking_kw": math.sqrt(power),
        "balance_kg": math.sqrt(balance + power / specific_energy**2),
        "flow_kg": math.sqrt(balance + variance("hydrogen_flow_kg")),
    }


def report_html(record):
    """Readable original contract for offline archives; never substitutes current metadata."""
    import html

    esc = html.escape
    if not record:
        return "<section><h2>Uncertainty</h2><p>No original uncertainty contract was recorded. This absence does not imply exact parameters.</p></section>"
    world = record.get("world")
    text = (
        "<section id='uncertainty'><h2>Uncertainty and controller information</h2><p>"
        + esc(record["scope"])
        + "</p>"
    )
    text += "<p>" + esc(record["knowledge_boundary"]) + "</p>"
    if world:
        text += (
            "<p>World "
            + esc(world["world_id"])
            + "; specification "
            + esc(world["specification_hash"])
            + ". Physical values below are retrospective truth. Hidden values were withheld from the controller.</p>"
        )
        text += "<table><thead><tr><th>Parameter</th><th>Physical value</th><th>Controller assumption</th><th>Evidence</th></tr></thead><tbody>"
        for d in world["draws"]:
            text += (
                "<tr>"
                + "".join(
                    "<td>" + esc(str(v)) + "</td>"
                    for v in (
                        d["path"],
                        d["value"],
                        d["nominal"] if d["visibility"] == "hidden" else d["value"],
                        d["source"],
                    )
                )
                + "</tr>"
            )
        text += "</tbody></table>"
        if world.get("measurements"):
            text += (
                "<h3>Observation error assumptions</h3><p>Additive Gaussian reading noise, persistent device bias and persistent linear drift rate, in the channel's units. These are assumptions, not calibrated posterior uncertainties.</p><pre>"
                + esc(str(world["measurements"]))
                + "</pre>"
            )
    else:
        text += "<p>This run uses one fixed configuration. No uncertainty ensemble was executed; unknown parameters remain unknown.</p>"
    return text + "</section>"
