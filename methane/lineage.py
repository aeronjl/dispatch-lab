"""Recorded evidence graphs. No solver, data fetching, or physical re-execution."""

import copy
from dataclasses import asdict

from methane.battery_trace import pointer_token
from methane.battery_trace import trace as battery_trace
from methane.config import Costs, Plant
from methane.costing import allocation
from methane.provenance import LOADED_SOURCE, digest

FILES = {
    "electrolyser": "methane/electrolyser.py",
    "hydrogen": "methane/storage.py",
    "co2": "methane/storage.py",
    "reactor": "methane/reactor.py",
    "solar": "methane/solar_model.py",
}
OBSERVATIONS = {
    "electrolyser": ("power_kw", "hydrogen_flow_kg"),
    "hydrogen": (
        "h2_inventory_kg",
        "h2_outflow_kg",
        "hydrogen_flow_kg",
        "usable_hydrogen_inflow_kg",
    ),
    "co2": ("co2_kg",),
    "reactor": ("temperature_c", "commitment_hours"),
    "solar": (),
}
FORMULAS = {
    "electrolyser": "H₂ = productive kW × duration / specific energy; bus kW = productive kW + start energy / duration; water = 9 × H₂",
    "hydrogen": "Inventory end = inventory begin + concurrent inflow − outflow; overflow is infeasible",
    "co2": "Accepted = min(delivery, capacity − beginning inventory); rejected = delivery − accepted; end = begin + accepted − outflow",
    "reactor": "C dT/dt = heater + reaction heat − UA(T−ambient) − cooling; analytic constant-input integration; H₂ / CO₂ / water = 0.5 / 2.75 / 2.25 × methane",
}


def unit(key):
    for suffix, value in (
        ("_kwh", "kWh"),
        ("_kw", "kW"),
        ("_kg", "kg"),
        ("_c", "°C"),
        ("_hours", "h"),
        ("_eur", "EUR"),
        ("_fraction", "fraction"),
    ):
        if key.endswith(suffix):
            return value
    return "dimensionless"


def node(key, value, source, parents=(), formula=None, label=None, units=None):
    return dict(
        id=key,
        label=label or key.replace("_", " "),
        value=value,
        unit=units or unit(key),
        source=source,
        parents=list(parents),
        **({"formula": formula} if formula else {}),
    )


def trace(result, controller, hour, component):
    if component == "battery":
        return battery_trace(result, controller, hour)
    row = result["records"][controller][hour]
    base = f"/records/{pointer_token(controller)}/{hour}"
    record = row.get("component_records", {}).get(component)
    identity = dict(
        run_id=result["run_id"],
        controller=controller,
        hour=hour,
        asset_id=result["asset_ids"][component],
    )
    if record is None:
        return {
            **identity,
            "status": "unavailable",
            "note": "This archive has no recorded component execution lineage. A current implementation has not been substituted.",
        }
    path = base + "/component_records/" + component
    nodes = []
    for group in ("parameters", "before", "inputs"):
        for key, value in record[group].items():
            nodes.append(
                node(group + "." + key, value, path + "/" + group + "/" + key, units=unit(key))
            )
    parents = [n["id"] for n in nodes]
    for group in ("after", "flows"):
        for key, value in record[group].items():
            nodes.append(
                node(
                    group + "." + key,
                    value,
                    path + "/" + group + "/" + key,
                    parents,
                    FORMULAS.get(component, "Recorded solar conversion stages"),
                    units=unit(key),
                )
            )
    measured = [
        node(
            "observed." + key,
            row["observations_after"][key],
            base + "/observations_after/" + key,
            units=unit(key),
        )
        for key in OBSERVATIONS[component]
        if key in row["observations_after"]
    ]
    source = result.get("provenance", {}).get("source", {})
    return copy.deepcopy(
        {
            **identity,
            "schema_version": "dispatch-lab/component-lineage/1",
            "status": "recorded",
            "model": {k: record[k] for k in ("model_id", "model_version", "implementation_id")},
            "nodes": nodes,
            "observed_nodes": measured,
            "observation_provenance": {
                "implementation_file": "methane/sensing.py",
                "implementation_sha256": source.get("files", {}).get("methane/sensing.py"),
                "sensor_parameters_path": "/config/sensors",
                "uncertainty_world_path": "/uncertainty/world"
                if result.get("uncertainty")
                else None,
                "controller_assumptions_path": "/controller_config"
                if result.get("controller_config")
                else "/config",
                "seed_path": "/config/scenario/seed",
                "rng_policy": result.get("provenance", {}).get("rng_policy"),
                "retrospective_injection_path": (
                    f"/retrospective_truth_by_controller/{pointer_token(controller)}/{hour}"
                    if result.get("retrospective_truth_by_controller")
                    else f"/retrospective_truth/{hour}"
                ),
            },
            "field_operations_adjustment": copy.deepcopy(row.get("field_operations"))
            if component == "solar"
            else None,
            "record_path": path,
            "decision_path": base + "/decision",
            "record_sha256": digest(record),
            "source_content_hash": source.get("content_hash"),
            "implementation_file": "methane/pv.py"
            if record["model_id"] == "dispatch-lab/reference-pv"
            else FILES[component],
            "implementation_file_sha256": source.get("files", {}).get(
                "methane/pv.py"
                if record["model_id"] == "dispatch-lab/reference-pv"
                else FILES[component]
            ),
            "audits": record.get("audits", []),
            "note": "Observed channels above are separate from retrospective model execution below. Input dependencies identify the model boundary, not causal importance. Hashes detect changes; they do not certify empirical validity.",
        }
    )


def derived(result, controller, end_hour):
    rows = result["records"][controller][:end_hour]
    root = "/records/" + pointer_token(controller)
    nodes = []
    for field, path in (
        ("methane_kg", "applied/methane_kg"),
        ("curtailed_kwh", "curtailed_kwh"),
        ("h2_produced_kg", "h2_produced_kg"),
    ):
        ids = []
        for i, row in enumerate(rows):
            value = row["applied"]["methane_kg"] if field == "methane_kg" else row[field]
            key = f"{field}.{i}"
            ids.append(key)
            nodes.append(node(key, value, f"{root}/{i}/{path}", units=unit(field)))
        nodes.append(
            node(
                "cumulative_" + field,
                sum(n["value"] for n in nodes if n["id"] in ids),
                "derived:/" + field,
                ids,
                "Sum of recorded interval totals",
                units=unit(field),
            )
        )
    methane = sum(r["applied"]["methane_kg"] for r in rows)
    nodes.extend(
        (
            node("elapsed_hours", len(rows), "derived:/elapsed_hours"),
            node(
                "rated_methane_kgph",
                result["config"]["plant"]["methane_max_kgph"],
                "/config/plant/methane_max_kgph",
                units="kg/h",
            ),
            node(
                "utilisation",
                methane / (len(rows) * result["config"]["plant"]["methane_max_kgph"])
                if rows
                else None,
                "derived:/utilisation",
                ("cumulative_methane_kg", "elapsed_hours", "rated_methane_kgph"),
                "Produced methane / (elapsed hours × rated output)",
                units="fraction",
            ),
        )
    )
    return dict(
        schema_version="dispatch-lab/derived-lineage/1",
        run_id=result["run_id"],
        controller=controller,
        end_hour=end_hour,
        nodes=nodes,
    )


_SAVED = object()


def economic(result, controller, end_hour, costs=None, *, service_economics=_SAVED):
    prices = costs or Costs(**result["config"]["costs"])
    if service_economics is _SAVED:
        service_economics = result["config"].get("service_economics")
    report = allocation(
        Plant(**result["config"]["plant"]),
        prices,
        result["records"][controller][:end_hour],
        with_lineage=True,
        service_economics=service_economics,
    )
    original = digest(result.get("controller_config", result["config"])["costs"])
    return dict(
        schema_version="dispatch-lab/economic-lineage/1",
        run_id=result["run_id"],
        controller=controller,
        end_hour=end_hour,
        row_source=f"/records/{pointer_token(controller)}",
        interval_slice=[0, end_hour],
        report_price_version=digest(asdict(prices)),
        dispatch_price_version=original,
        report_service_price_version=digest(service_economics)
        if service_economics is not None
        else None,
        dispatch_service_price_version=digest(result["config"]["service_economics"])
        if result["config"].get("service_economics") is not None
        else None,
        service_economics=service_economics,
        prices=asdict(prices),
        source_file="methane/costing.py",
        source_file_sha256=LOADED_SOURCE["files"].get("methane/costing.py"),
        report_source_content_hash=LOADED_SOURCE["content_hash"],
        dispatch_source_content_hash=result.get("provenance", {})
        .get("source", {})
        .get("content_hash"),
        report=report,
        note="Report prices apply to this fixed physical trace. Recorded decisions retain their original cost version. Allocation and operating contribution are separate views; ending inventories have no sale credit.",
    )
