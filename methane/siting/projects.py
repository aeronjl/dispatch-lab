"""A plant project links editable design revisions to immutable operating cases.

This is workflow composition over existing kernels and Sites contracts. It does
not introduce plant physics, grant service capabilities or revise recorded runs.
"""

import fcntl
import uuid
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import Field

from methane.config import Config
from methane.costing import capital
from methane.siting.contracts import DeploymentDesign, Record
from methane.siting.geometry import centre
from methane.siting.store import encode

VERSION = "plant-project/1"
NAMES = dict(
    solar="Solar array",
    battery="Battery",
    electrolyser="Electrolyser",
    hydrogen="Hydrogen buffer",
    co2="CO₂ supply",
    reactor="Methanator",
    services="Site services",
    controls="Management",
    costs="Economics",
    weather="Weather & location",
)
PRIMARY = dict(
    solar=["plant.solar_kw", "weather.tilt", "weather.azimuth"],
    battery=["plant.battery_kwh", "plant.battery_c_rate"],
    electrolyser=["plant.electrolyser_kw", "plant.specific_energy_kwh_per_kg"],
    hydrogen=["plant.h2_capacity_kg", "plant.initial_h2_kg"],
    co2=["plant.co2_capacity_kg", "plant.initial_co2_kg", "plant.co2_delivery_kg"],
    reactor=["plant.methane_max_kgph", "plant.methane_min_kgph"],
    services=[
        "field_operations.enabled",
        "field_operations.dock_kw",
        "field_operations.human_fallback",
    ],
    controls=["scenario.horizon_hours", "sensors.enabled"],
    costs=["costs.methane_eur_per_kg", "costs.co2_eur_per_kg"],
    weather=["weather.start", "scenario.forecast_bias", "scenario.variability"],
)
GROUPS = dict(
    solar=[
        "solar",
        "weather.tilt",
        "weather.azimuth",
        "weather.loss_fraction",
        "weather.noct_c",
        "weather.temperature_coefficient",
        "plant.solar_kw",
    ],
    battery=["plant.battery", "plant.initial_soc", "plant.roundtrip_efficiency", "models.battery"],
    electrolyser=[
        "plant.electrolyser",
        "plant.specific_energy",
        "plant.min_load",
        "plant.start_energy",
        "models.electrolyser",
    ],
    hydrogen=["plant.h2", "plant.initial_h2", "models.hydrogen"],
    co2=["plant.co2", "plant.initial_co2", "models.co2"],
    reactor=[
        "plant.methane",
        "plant.temperature",
        "plant.thermal",
        "plant.heat",
        "plant.cool",
        "plant.auxiliary",
        "plant.minimum_run",
        "models.reactor",
    ],
    services=["field_operations", "service_system", "service_economics", "lifecycle"],
    controls=[
        "scenario",
        "sensors",
        "faults",
        "recovery_policy",
        "service_policy",
        "investigation_policy",
        "randomness",
    ],
    costs=["costs", "service_economics"],
    weather=["weather"],
)
EQUIPMENT = [
    dict(
        id="cleaner",
        name="Array cleaner",
        topic="cleaning",
        group="Site services",
        requires="Dock, DC charging, accessible rows, brush and cleaning stock",
        boundary="Removes modelled surface loss; does not repair damaged panels.",
    ),
    dict(
        id="rover",
        name="Inspection rover",
        topic="inspection",
        group="Site services",
        requires="Dock, access route, communications and a prepared inspection interface",
        boundary="Reads the declared channel; does not diagnose arbitrary equipment faults.",
    ),
    dict(
        id="reset",
        name="Bounded reset actuator",
        topic="recovery",
        group="Site services",
        requires="Communications and an informative trip indication",
        boundary="Attempts the supported reset; successful recovery still requires verification.",
    ),
    dict(
        id="human",
        name="Human service support",
        topic="logistics",
        group="Site services",
        requires="Crew availability, mobilisation time, access and finite service kits",
        boundary="Declared module replacement and calibration tasks; not a general repair oracle.",
    ),
]


class Project(Record):
    schema_version: Literal["plant-project/1"] = VERSION
    project_id: str = Field(pattern=r"^[a-f0-9]{32}$")
    name: str = Field(min_length=1, max_length=160)
    site_revision: str = Field(pattern=r"^[a-f0-9]{64}$")
    config: dict
    baseline: dict
    parent_id: str | None = None
    design_id: str | None = None
    requirements_id: str | None = None
    equipment_basis_id: str | None = None
    created_at: str
    updated_at: str


def heads(store):
    records = store.list("project")
    parents = {r["parent_id"] for r in records if r.get("parent_id")}
    return sorted(
        (r for r in records if r["id"] not in parents), key=lambda r: r["updated_at"], reverse=True
    )


def validate_config(store, site_id, value):
    c = Config.from_dict(value)
    site = store.get("site", site_id)
    lat, lon = centre(site["geometry"])
    if (
        abs(c.weather.latitude - lat) > 1e-6
        or abs(c.weather.longitude - lon) > 1e-6
        or c.weather.timezone != site["timezone"]
    ):
        raise ValueError(
            "Project weather location must match its site. Choose another site to change location."
        )
    return c


def create(store, site_id, name=None, design_id=None):
    site = store.get("site", site_id)
    lat, lon = centre(site["geometry"])
    c = Config()
    c = replace(
        c,
        weather=replace(c.weather, latitude=lat, longitude=lon, timezone=site["timezone"]),
        sensors=replace(c.sensors, ambiguity_policy="retain-capacity/1"),
    )
    if design_id:
        design = store.get("design", design_id)
        if design["site_revision"] != site_id:
            raise ValueError("Design belongs to another site")
        c = Config.from_dict(design["config"])
    now = datetime.now(UTC).isoformat()
    p = Project(
        project_id=uuid.uuid4().hex,
        name=name or "Plant at " + site["name"],
        site_revision=site_id,
        config=c.to_dict(),
        baseline=c.to_dict(),
        design_id=design_id,
        equipment_basis_id=design.get("equipment_basis_id") if design_id else None,
        created_at=now,
        updated_at=now,
    )
    key = store.put("project", p)
    return read(store, key)


def revise(store, key, config, name=None, **changes):
    if set(changes) - {"requirements_id", "equipment_basis_id"}:
        raise ValueError("Unknown project revision field")
    if changes.get("requirements_id"):
        from methane.siting.requirements import Brief

        Brief(**store.get("requirements", changes["requirements_id"]))
    if changes.get("equipment_basis_id"):
        basis = store.get("equipment-basis", changes["equipment_basis_id"])
        if basis["site_revision"] != store.get("project", key)["site_revision"]:
            raise ValueError("Equipment basis belongs to another site")
    store.root.mkdir(parents=True, exist_ok=True)
    with (store.root / "project-write.lock").open("a+") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        previous = store.get("project", key)
        current = next(r for r in heads(store) if r["project_id"] == previous["project_id"])
        if current["id"] != key:
            raise ValueError(
                "This project changed in another view. Reload the project before saving; your draft has not been applied."
            )
        c = validate_config(store, previous["site_revision"], config)
        value = c.to_dict()
        if (
            value == previous["config"]
            and (name is None or name == previous["name"])
            and all(previous.get(k) == v for k, v in changes.items())
        ):
            return read(store, key)
        record = Project(
            **{
                **previous,
                **changes,
                "config": value,
                "name": name or previous["name"],
                "parent_id": key,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        return read(store, store.put("project", record))


def fields(value, path=""):
    """All present scalar parameters, including nested optional mechanisms."""
    rows = []
    if isinstance(value, dict):
        for k, v in value.items():
            rows.extend(fields(v, f"{path}.{k}".strip(".")))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            rows.extend(fields(v, f"{path}.{i}"))
    elif value is not None:
        key = path.split(".")[-1]
        label = {
            "plant.solar_kw": "Installed capacity",
            "sensors.enabled": "Sensor diagnosis enabled",
            "field_operations.enabled": "Site services enabled",
            "field_operations.dock_kw": "Shared charging power",
            "field_operations.human_fallback": "Human service fallback",
            "costs.methane_eur_per_kg": "Assumed methane value",
            "costs.co2_eur_per_kg": "CO₂ price",
            "plant.battery_kwh": "Energy capacity",
            "plant.battery_c_rate": "Charge and discharge rate",
            "plant.electrolyser_kw": "Rated power",
            "plant.specific_energy_kwh_per_kg": "Electricity per kg of hydrogen",
            "plant.h2_capacity_kg": "Storage capacity",
            "plant.co2_capacity_kg": "Storage capacity",
            "plant.initial_h2_kg": "Starting hydrogen",
            "plant.initial_co2_kg": "Starting CO₂",
            "plant.co2_delivery_kg": "Scheduled delivery",
            "plant.methane_max_kgph": "Maximum production",
            "plant.methane_min_kgph": "Minimum stable production",
            "plant.roundtrip_efficiency": "Round-trip efficiency",
            "plant.initial_soc": "Starting state of charge",
            "weather.tilt": "Panel tilt",
            "weather.azimuth": "Azimuth from south",
            "scenario.horizon_hours": "Planning horizon",
        }.get(path, key.replace("_", " "))
        unit = next(
            (
                u
                for suffix, u in (
                    ("eur_per_kwh", "EUR/kWh"),
                    ("eur_per_kw", "EUR/kW"),
                    ("eur_per_kg", "EUR/kg"),
                    ("eur_per_m3", "EUR/m³"),
                    ("eur_per_year", "EUR/year"),
                    ("eur_per_hour", "EUR/h"),
                    ("kwh_per_k", "kWh/K"),
                    ("kw_per_k", "kW/K"),
                    ("kwh_per_kg", "kWh/kg"),
                    ("kgph", "kg/h"),
                    ("kwh", "kWh"),
                    ("kw", "kW"),
                    ("hours", "h"),
                    ("_kg", "kg"),
                    ("_c", "°C"),
                    ("fraction", "fraction"),
                    ("eur", "EUR"),
                )
                if key.endswith(suffix)
            ),
            "",
        )
        rows.append(
            dict(
                path=path,
                label=label,
                unit={
                    "plant.battery_c_rate": "1/h",
                    "weather.tilt": "degrees",
                    "weather.azimuth": "degrees",
                }.get(path, unit),
                value=value,
                kind="boolean"
                if isinstance(value, bool)
                else "number"
                if isinstance(value, (int, float))
                else "text",
                integer=type(value) is int,
                groups=[
                    g
                    for g, prefixes in GROUPS.items()
                    if any(path == p or path.startswith(p) for p in prefixes)
                ],
            )
        )
    return rows


def preview(config, baseline=None):
    c = Config.from_dict(config)
    normalized = c.to_dict()
    original = {r["path"]: r["value"] for r in fields(baseline or Config().to_dict())}
    metadata = fields(normalized)
    for row in metadata:
        row["modified"] = row["path"] in original and row["value"] != original[row["path"]]
        row["default"] = original.get(row["path"])
        row["editable"] = row["path"] not in (
            "weather.latitude",
            "weather.longitude",
            "weather.timezone",
        )
    p = c.plant
    cap = capital(p, c.costs)
    cap["battery"] = cap.pop("battery_cells") + cap.pop("battery_power")
    installed = []
    f = c.field_operations
    if f.enabled:
        installed = [
            r
            for r, flag in (
                ("cleaner", f.cleaner_enabled),
                ("rover", f.rover_enabled),
                ("reset", f.reset_enabled),
                ("human", f.human_fallback),
            )
            if flag
        ]
    notes = ["Illustrative operating and economic assumptions; no plant calibration."]
    if f.enabled:
        notes.append(
            "Service access, communications, measurement channels and success rates remain declared assumptions. Inspect Site services."
        )
    if p.integration is not None:
        notes.append(
            "Plant interfaces enabled: conversion, external cooling/drying, pressure compatibility and finite purified water. Inspect Equipment & evidence → Plant interfaces; unpriced extras leave total cost incomplete."
        )
    if c.lifecycle:
        notes.append(
            "Commissioning and maintenance are enabled; nominal installed capacity may not be available at the start."
        )
    return dict(
        config=normalized,
        fields=metadata,
        primary=PRIMARY,
        names=NAMES,
        capital=cap,
        capital_scope="Nominal process equipment capital at current assumptions; excludes site, installation, service equipment and separately priced plant interfaces. Not a quotation or profitability estimate.",
        installed=installed,
        equipment=EQUIPMENT,
        notes=notes,
        visual=dict(
            battery_fraction=p.initial_soc,
            h2_fraction=p.initial_h2_kg / p.h2_capacity_kg if p.h2_capacity_kg else 0,
            co2_fraction=p.initial_co2_kg / p.co2_capacity_kg if p.co2_capacity_kg else 0,
            solar=f"{p.solar_kw:g} kW",
            solar_value=f"{p.solar_kw:g}",
            electrolyser_value=f"{p.electrolyser_kw:g}",
            initial_soc_value=f"{p.initial_soc * 100:g}",
            battery=f"{p.battery_kwh:g} kWh",
            electrolyser=f"{p.electrolyser_kw:g} kW",
            hydrogen=f"{p.h2_capacity_kg:g} kg",
            co2=f"{p.co2_capacity_kg:g} kg",
            reactor=f"{p.methane_max_kgph:g} kg/h",
            battery_power=f"{p.battery_kw:g} kW",
            initial_battery=f"{p.initial_soc * 100:g}% initial SOC",
        ),
    )


def equipment(config, kind, enabled):
    if kind not in {r["id"] for r in EQUIPMENT} or type(enabled) is not bool:
        raise ValueError("Choose a supported equipment package and a boolean selection")
    from methane.services.configuration import ServiceSystem

    c = Config.from_dict(config)
    f = c.field_operations
    if not f.enabled and enabled:
        f = replace(
            f,
            enabled=True,
            cleaner_enabled=False,
            rover_enabled=False,
            reset_enabled=False,
            human_fallback=False,
        )
    field = dict(
        cleaner="cleaner_enabled",
        rover="rover_enabled",
        reset="reset_enabled",
        human="human_fallback",
    )[kind]
    f = replace(f, **{field: enabled})
    c = replace(
        c,
        field_operations=f,
        service_system=c.service_system or (ServiceSystem() if enabled else None),
    )
    return c.to_dict()


def design(store, key):
    project = store.get("project", key)
    c = validate_config(store, project["site_revision"], project["config"])
    previous = store.get("design", project["design_id"]) if project.get("design_id") else {}
    record = DeploymentDesign(
        **{
            **previous,
            "name": project["name"],
            "site_revision": project["site_revision"],
            "config": c.to_dict(),
            "parent_id": project.get("design_id"),
            "equipment_basis_id": project.get("equipment_basis_id"),
        }
    )
    return store.put("design", record)


def read(store, key):
    from methane.siting import production

    p = store.get("project", key)
    environments = []
    for env in store.list("environment"):
        if env["site_revision"] != p["site_revision"]:
            continue
        base = env["conversion"]["weather"]
        compatible = all(
            p["config"]["weather"][k] == base[k]
            for k in ("latitude", "longitude", "tilt", "azimuth")
        )
        environments.append(
            {k: env[k] for k in ("id", "start", "end", "hours", "information", "reference")}
            | dict(compatible=compatible)
        )
    studies = []
    for s in store.list("study"):
        if (s.get("search") or {}).get("project_id") == p["project_id"]:
            studies.append(
                dict(
                    id=s["id"],
                    name=s["name"],
                    state=production.state(store, s["id"]),
                    project_revision=s["search"]["project_revision"],
                )
            )
    return dict(
        project={"id": key, **p},
        requirements=store.get("requirements", p["requirements_id"])
        if p.get("requirements_id")
        else None,
        site=store.get("site", p["site_revision"]),
        preview=preview(p["config"], p["baseline"]),
        environments=environments,
        studies=studies,
    )


def synthetic_environment(store, design_id, start, hours):
    from methane.siting.environment import CONVENTION, exact_times
    from methane.siting.sources import snapshot
    from methane.timebase import stamp, utc
    from methane.weather import synthetic

    if type(hours) is not int or not 1 <= hours <= 168:
        raise ValueError(
            "The short synthetic example supports 1–168 hours; use saved chronological data for longer studies"
        )
    d = store.get("design", design_id)
    c = Config.from_dict(d["config"])
    first = utc(start)
    if first.minute or first.second or first.microsecond:
        raise ValueError("Start must be an exact UTC hour")
    c = replace(
        c,
        scenario=replace(c.scenario, hours=hours + 24),
        weather=replace(c.weather, mode="synthetic", start=stamp(first - timedelta(days=1))),
    )
    w = synthetic(c)
    sid = snapshot(
        store,
        encode(w),
        provider="Dispatch Lab",
        product="Explicit project teaching weather",
        edition="project-synthetic/1",
        retrieved_at=datetime.now(UTC),
        request=dict(seed=c.scenario.seed, start=start, hours=hours),
        attribution="Dispatch Lab synthetic fixture",
        licence="Project teaching fixture",
        redistribution="permitted",
        timing=CONVENTION,
        source_url="fixture:project-synthetic/1",
    )
    env = dict(
        schema_version="site-environment/1",
        design_id=design_id,
        site_revision=d["site_revision"],
        start=stamp(first),
        end=stamp(first + timedelta(hours=hours)),
        hours=hours,
        information="persistence/1",
        reference="Explicit synthetic teaching weather; not historical conditions or a site resource estimate",
        timezone=c.weather.timezone,
        conversion=dict(
            weather=c.to_dict()["weather"], solar_kw=c.plant.solar_kw, section_design=c.solar
        ),
        source_ids=[sid],
        normalized_sha256=store.raw(encode(dict(truth=w["truth"], vintages=[]))),
        convention=CONVENTION,
        publication_lag_hours=0,
        assumptions=[
            "Synthetic hourly weather; location does not turn this fixture into site observations",
            "Previous complete synthetic day repeated at each decision boundary",
        ],
    )
    exact_times(env["start"], env["end"])
    return store.put("environment", env)


def run_project(
    store,
    key,
    *,
    environment_id=None,
    synthetic=False,
    start="2025-07-10T00:00:00Z",
    hours=72,
    controller="MPC · methane",
    baseline_study_id=None,
):
    from methane.siting import production

    p = store.get("project", key)
    did = design(store, key)
    if synthetic:
        if environment_id:
            raise ValueError("Select either a saved environment or explicit synthetic weather")
        environment_id = synthetic_environment(store, did, start, hours)
    if not environment_id:
        raise ValueError("Choose or retrieve weather before starting a run")
    env = store.get("environment", environment_id)
    if env["site_revision"] != p["site_revision"]:
        raise ValueError("Weather belongs to another site")
    c = Config.from_dict(p["config"])
    if any(
        c.to_dict()["weather"][k] != env["conversion"]["weather"][k]
        for k in ("latitude", "longitude", "tilt", "azimuth")
    ):
        raise ValueError(
            "Weather orientation/location is incompatible. Retrieve a new snapshot before running."
        )
    # The worker performs full hourly admission; do not block the interactive server
    # by decoding decades of weather at this boundary.
    cases = [dict(design_id=did, environment_id=environment_id, controller=controller)]
    if baseline_study_id:
        baseline = store.get("study", baseline_study_id)
        if (baseline.get("search") or {}).get("project_id") != p["project_id"]:
            raise ValueError("Comparison run belongs to another project")
        original = baseline["cases"][0]
        if original["environment_id"] != environment_id:
            raise ValueError("A matched design comparison requires the original weather snapshot")
        cases = [
            dict(
                design_id=original["design_id"],
                environment_id=environment_id,
                controller=original["controller"],
                policy=original.get("policy"),
                seed=original["config"]["scenario"]["seed"],
                label="Original design / new calculation",
            ),
            dict(
                design_id=did,
                environment_id=environment_id,
                controller=original["controller"],
                policy=original.get("policy"),
                seed=original["config"]["scenario"]["seed"],
                label="Revised design / new calculation",
            ),
        ]
    study = production.create(
        store,
        name=p["name"] + (" / design comparison" if baseline_study_id else " / operation"),
        cases=cases,
        partition_hours=24,
        requirements_id=p.get("requirements_id"),
        purpose="Plant project operation under the explicitly selected weather and management assumptions",
        search=dict(
            kind=VERSION,
            project_id=p["project_id"],
            project_revision=key,
            baseline_study_id=baseline_study_id,
        ),
    )
    return dict(study_id=study["id"], design_id=did, environment_id=environment_id)


def perform(store, operation, key, data):
    if operation == "project-index":
        return dict(
            projects=[
                {k: p[k] for k in ("id", "project_id", "name", "site_revision", "updated_at")}
                for p in heads(store)
            ]
        )
    if operation == "project-create":
        return create(store, **data)
    if operation == "project-get":
        return read(store, key)
    if operation == "project-from-study":
        study = store.get("study", key)
        project_id = (study.get("search") or {}).get("project_id")
        found = next((p for p in heads(store) if p["project_id"] == project_id), None)
        if found:
            return read(store, found["id"])
        case = study["cases"][0]
        d = store.get("design", case["design_id"])
        return create(store, d["site_revision"], design_id=case["design_id"])
    if operation == "project-save":
        return revise(store, key, **data)
    if operation == "project-preview":
        return preview(**data)
    if operation == "project-equipment":
        return dict(config=equipment(**data))
    if operation == "project-design":
        return dict(design_id=design(store, key))
    if operation == "project-run":
        return run_project(store, key, **data)
    raise ValueError("Unknown plant project operation")
