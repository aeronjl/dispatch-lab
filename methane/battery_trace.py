"""Recorded battery lineage, resolved in Python without rerunning a model or solver."""

import copy

from methane.provenance import digest


def pointer_token(value):
    return str(value).replace("~", "~0").replace("/", "~1")


def trace(result, controller, hour):
    """`hour` is the zero-based decision interval, not the displayed end-hour."""
    row = result["records"][controller][hour]
    record = row.get("battery_record")
    identity = {
        "run_id": result["run_id"],
        "controller": controller,
        "hour": hour,
        "asset_id": result["asset_ids"]["battery"],
    }
    if record is None:
        return {
            **identity,
            "status": "unavailable",
            "note": "This archive predates battery component records. Its original model version and input lineage are unavailable; no current model has been substituted.",
        }
    base = f"/records/{pointer_token(controller)}/{hour}"
    prior = f"/records/{pointer_token(controller)}/{hour - 1}/state/battery_kwh"
    config = "/config/plant"
    parameters = record["parameters"]
    capacity = parameters["capacity_kwh"]
    energy = record["after"]["energy_kwh"]
    # Match the existing renderer's bounded ratio and nonnegative display convention.
    displayed_energy = max(0, energy)
    soc = min(1, max(0, energy / capacity)) * 100 if capacity > 0 else 0
    nodes = [
        {
            "id": "capacity",
            "label": "Usable capacity",
            "value": capacity,
            "unit": "kWh",
            "source": config + "/battery_kwh",
            "parents": [],
        },
        {
            "id": "c_rate",
            "label": "Power / energy ratio",
            "value": parameters["c_rate"],
            "unit": "1/h",
            "source": config + "/battery_c_rate",
            "parents": [],
        },
        {
            "id": "roundtrip",
            "label": "Round-trip efficiency",
            "value": parameters["roundtrip_efficiency"],
            "unit": "fraction",
            "source": config + "/roundtrip_efficiency",
            "parents": [],
        },
        {
            "id": "begin",
            "label": "Beginning stored energy",
            "value": record["before"]["energy_kwh"],
            "unit": "kWh",
            "source": prior if hour else config + "/initial_soc × " + config + "/battery_kwh",
            "parents": [],
        },
        {
            "id": "charge",
            "label": "Applied charging",
            "value": record["inputs"]["charge_kw"],
            "unit": "kW",
            "source": base + "/applied/charge_kw",
            "parents": [],
        },
        {
            "id": "discharge",
            "label": "Applied discharge",
            "value": record["inputs"]["discharge_kw"],
            "unit": "kW",
            "source": base + "/applied/discharge_kw",
            "parents": [],
        },
        {
            "id": "duration",
            "label": "Interval duration",
            "value": record["inputs"]["duration_hours"],
            "unit": "h",
            "source": config + "/dt_hours",
            "parents": [],
        },
        {
            "id": "end",
            "label": "Ending stored energy",
            "value": energy,
            "unit": "kWh",
            "source": base + "/state/battery_kwh",
            "parents": ["begin", "charge", "discharge", "duration", "roundtrip"],
            "formula": "E_end = E_begin + sqrt(efficiency) × charge × duration − discharge × duration / sqrt(efficiency)",
        },
        {
            "id": "loss",
            "label": "Interval losses",
            "value": record["flows"]["loss_kwh"],
            "unit": "kWh",
            "source": base + "/battery_loss_kwh",
            "parents": ["charge", "discharge", "duration", "roundtrip"],
            "formula": "Loss = (1 − eta) × charge × duration + (1/eta − 1) × discharge × duration",
        },
        {
            "id": "display_energy",
            "label": "Displayed energy (before rounding)",
            "value": displayed_energy,
            "unit": "kWh",
            "source": "SVG battery label / inspector stored energy",
            "parents": ["end"],
            "formula": "max(0, E_end); SVG rounds to whole kWh, inspector to 0.1 kWh",
        },
        {
            "id": "display_soc",
            "label": "Displayed SOC (before rounding)",
            "value": soc,
            "unit": "%",
            "source": "SVG battery SOC label and cell fill",
            "parents": ["end", "capacity"],
            "formula": "100 × clamp(E_end / capacity, 0, 1); zero for absent battery; label rounds to whole %",
        },
    ]
    source = result.get("provenance", {}).get("source", {})
    return copy.deepcopy(
        {
            **identity,
            "schema_version": "dispatch-lab/battery-lineage/1",
            "status": "recorded",
            "model": {k: record[k] for k in ("model_id", "model_version", "implementation_id")},
            "source_content_hash": source.get("content_hash"),
            "implementation_file": "methane/battery.py",
            "implementation_file_sha256": source.get("files", {}).get("methane/battery.py"),
            "record_sha256": digest(record),
            "record_path": base + "/battery_record",
            "decision_path": base + "/decision",
            "requested": {k: row["requested"][k] for k in ("charge_kw", "discharge_kw")},
            "nodes": nodes,
            "audits": record["audits"],
            "note": "Recorded execution evidence. Requested actions originate in this decision's frozen forecast, estimate and policy; plant execution may restrict them. A content hash detects changes; it is not a signature or plant calibration.",
        }
    )
