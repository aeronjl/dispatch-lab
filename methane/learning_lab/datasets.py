"""An explicit causal data port; outcome labels never enter policy packets."""

import copy
from datetime import datetime

from methane.siting.store import digest, encode

VERSION = "observation-dataset/1"
PORT = "policy-observation/1"
OBSERVATIONS = (
    "battery_kwh",
    "h2_inventory_kg",
    "co2_kg",
    "temperature_c",
    "power_kw",
    "hydrogen_flow_kg",
    "h2_outflow_kg",
    "electrolyser_on",
    "reactor_on",
    "commitment_hours",
)
FORECAST = (
    "pv_kw",
    "ambient_c",
    "deliveries_kg",
    "service_kw",
    "source",
    "times",
    "component_availability",
    "electrolyser_isolated",
    "reactor_isolated",
)


def packet(decision, *, time, prices, plant, prior_service=None):
    """Select rather than blacklist. Completed-interval service data arrives H+1.

    No runtime, physical configuration, fault schedule, result state or planned
    trajectory crosses this port. Forecast future values are predictions only.
    """
    hour = decision["hour"]
    f = decision.get("forecast", {})
    source = f.get("source", {})
    for key in ("available_at", "availability_time", "assumed_available_at"):
        if source.get(key) and datetime.fromisoformat(
            source[key].replace("Z", "+00:00")
        ) > datetime.fromisoformat(time.replace("Z", "+00:00")):
            raise ValueError("Forecast was not available at this decision")
    observations = {k: decision.get("observations", {}).get(k) for k in OBSERVATIONS}
    conditions = {}
    for asset, value in decision.get("lifecycle", {}).get("condition", {}).items():
        m = value.get("measurement")
        if m and m.get("available_at", hour) <= hour:
            conditions[asset] = {
                k: m.get(k)
                for k in ("value", "measured_at", "available_at", "source", "noise_bound", "epoch")
            }
    clocks = []
    for r in (prior_service or {}).get("duration_observations", []):
        if r["available_at"] <= hour:
            clocks.append(
                {
                    k: r[k]
                    for k in (
                        "id",
                        "order_id",
                        "asset_id",
                        "group",
                        "started_at",
                        "available_at",
                        "elapsed_hours",
                        "nominal_hours",
                        "completed_at",
                        "censored",
                    )
                }
            )
    solar = decision.get("performance_estimates", {}).get("solar") or {}
    value = dict(
        version=PORT,
        hour=hour,
        time=time,
        observations=observations,
        estimate={
            k: decision.get("estimate", {}).get(k)
            for k in (
                "battery_kwh",
                "h2_kg",
                "co2_kg",
                "temperature_c",
                "reactor_on",
                "electrolyser_on",
                "commitment_hours",
            )
        },
        diagnosis={
            k: decision.get("diagnosis", {}).get(k)
            for k in (
                "capacity_kw",
                "status",
                "flow_isolated",
                "uncertain",
            )
        },
        forecast={k: copy.deepcopy(f[k]) for k in FORECAST if k in f},
        condition=conditions,
        duration_observations=clocks,
        solar_measurement={
            k: solar.get(k) for k in ("ratio", "status", "expected_kw", "measured_kw")
        },
        soiling={
            k: decision.get("field_operations", {}).get(k)
            for k in ("soiling_estimate", "soiling_sensor")
        },
        support={
            k: copy.deepcopy(decision.get("field_operations", {}).get(k))
            for k in ("robots", "service_kits", "cleaning_kits", "calibration_kits", "orders")
        },
        plant=copy.deepcopy(plant),
        prices=copy.deepcopy(prices),
        missing=[k for k, v in observations.items() if v is None],
        timing="Decision H; meters cover preceding interval; PV[0] is the existing contemporaneous hourly-mean abstraction. Forecast PV[1:] is prediction, not realised weather.",
    )
    digest(value)
    return value


def freeze(store, selections, *, name, holdout_axes=()):
    """Pin committed partition identities before any fitting. Never split hours."""
    from methane.siting.production import entries, read_blob

    if not name.strip() or not 3 <= len(selections) <= 96:
        raise ValueError("Name the dataset and select 3–96 complete episodes")
    if set(holdout_axes) - {"site", "design", "equipment"}:
        raise ValueError("Unknown holdout axis")
    episodes, samples, labels = [], [], []
    observation_bytes = 0
    seen = set()
    for selection in selections:
        study = store.get("study", selection["study_id"])
        case = next(c for c in study["cases"] if c["case_id"] == selection["case_id"])
        split = selection["split"]
        if split not in ("train", "validation", "test"):
            raise ValueError("Use train, validation or test")
        origin = (selection["study_id"], selection["case_id"])
        if origin in seen:
            raise ValueError("An episode may appear in only one split")
        seen.add(origin)
        env = store.get("environment", case["environment_id"])
        entry = entries(store, *origin)
        if not entry or entry[-1]["next_hour"] != case["hours"]:
            raise ValueError(
                "Incomplete episode: retain it as an incomplete study, not training data"
            )
        config = case["config"]
        controller_config = (case.get("uncertainty") or {}).get("controller_config", config)
        episode = dict(
            id=digest(origin),
            study_id=origin[0],
            case_id=origin[1],
            split=split,
            site=env["site_revision"],
            design=case["design_id"],
            equipment=digest(
                {
                    k: config.get(k)
                    for k in ("plant", "field_operations", "service_system", "lifecycle")
                }
            ),
            environment=case["environment_id"],
            start=env["start"],
            end=env["end"],
            seed=config["scenario"]["seed"],
            repetition=case["repetition"],
            source=study["source"]["content_hash"],
            source_capsule_sha256=study["source_capsule_sha256"],
            partitions=[e["period_sha256"] for e in entry],
            measurement_assumptions=config.get("sensors", {}),
            reference=env["reference"],
            config=config,
            controller_config=controller_config,
        )
        episodes.append(episode)
        prior, expected = None, 0
        for key in episode["partitions"]:
            result = read_blob(store, key)["value"]
            truth = {
                r["hour"]: r
                for r in result.get("retrospective_truth_by_controller", {}).get(
                    case["controller"], []
                )
            }
            for row in result["records"][case["controller"]]:
                d = row["decision"]
                if d["hour"] != expected:
                    raise ValueError("Episode has missing or duplicated decision hours")
                expected += 1
                p = copy.deepcopy(d.get("experimental_policy", {}).get("input")) or packet(
                    d,
                    time=row["time"],
                    prices=controller_config["costs"],
                    plant=d.get("operating_plant", controller_config["plant"]),
                    prior_service=prior,
                )
                observation_bytes += len(encode(p))
                if len(samples) >= 100000 or observation_bytes > 128 * 1024**2:
                    raise ValueError(
                        "Dataset budget exceeded: 100,000 observations or 128 MiB of policy packets; declare fewer complete episodes"
                    )
                sid = digest([episode["id"], d["hour"]])
                samples.append(
                    dict(
                        id=sid,
                        episode=episode["id"],
                        split=split,
                        packet=p,
                        packet_id=digest(p),
                        recorded_action=row["requested"],
                        applied_action=row["applied"],
                        partition=key,
                    )
                )
                labels.append(
                    dict(
                        id=sid,
                        basis="Retrospective simulated outcomes; scoring only",
                        truth=copy.deepcopy(truth.get(d["hour"])),
                        methane_kg=row["applied"]["methane_kg"],
                    )
                )
                prior = row.get("field_operations")
    validate_splits(episodes, holdout_axes)
    return save(store, name, episodes, samples, labels, holdout_axes)


def validate_splits(episodes, axes=()):
    if {e["split"] for e in episodes} != {"train", "validation", "test"}:
        raise ValueError("Freeze separate train, validation and test episodes before fitting")
    for i, a in enumerate(episodes):
        for b in episodes[i + 1 :]:
            if a["split"] == b["split"]:
                continue
            overlap = a["site"] == b["site"] and a["start"] < b["end"] and b["start"] < a["end"]
            if overlap or a["id"] == b["id"] or any(a[k] == b[k] for k in axes):
                raise ValueError(
                    "Leakage across splits: shared episode, overlapping site/weather window or held-out axis"
                )


def save(store, name, episodes, samples, labels, axes=()):
    from methane.provenance import LOADED_CAPSULE, LOADED_SOURCE

    observations = store.raw(encode(samples))
    scoring = store.raw(encode(labels))
    value = dict(
        version=VERSION,
        name=name,
        port=PORT,
        episodes=episodes,
        observations_sha256=observations,
        labels_sha256=scoring,
        holdout_axes=list(axes),
        sample_count=len(samples),
        adapter_source=LOADED_SOURCE["content_hash"],
        capsule_raw_sha256=store.raw(encode(LOADED_CAPSULE)),
        scope="Episode-disjoint simulated observation dataset. Labels are separate scoring artifacts, never policy inputs. Seeds and numerical repeats are not independent weather samples.",
    )
    return dict(id=store.put("dataset", value), **value)


def reconstruct(store, dataset_id):
    original = store.get("dataset", dataset_id)
    result = freeze(
        store,
        [{k: e[k] for k in ("study_id", "case_id", "split")} for e in original["episodes"]],
        name=original["name"],
        holdout_axes=original["holdout_axes"],
    )
    if result["id"] != dataset_id:
        raise ValueError("Dataset reconstruction differs; original has not been overwritten")
    return dict(status="identical", dataset_id=dataset_id)
