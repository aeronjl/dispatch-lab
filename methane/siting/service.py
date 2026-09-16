"""Sites transport. Browser requests reference saved identities; calculations stay in Python."""

import base64
import json
from datetime import UTC, datetime
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field

from methane.config import Config
from methane.siting import catalogue, geometry, raster, sources
from methane.siting.contracts import DeploymentDesign, Evidence, ScreeningPolicy, SiteCandidate
from methane.siting.store import Store


class Request(BaseModel):
    model_config = ConfigDict(extra="forbid")
    token: str = Field(max_length=100)
    run_id: str = Field(max_length=100)
    key: str = Field(max_length=200)
    operation: str = Field(max_length=60)
    id: str | None = Field(default=None, max_length=64)
    data: dict = Field(default_factory=dict)
    offline: bool = False


def view(store, key):
    site = store.get("site", key)
    evidence = [r for r in store.list("evidence") if r["site_id"] == site["site_id"]]
    now = datetime.now(UTC)
    for item in evidence:
        end = item.get("valid_until")
        item["expired"] = bool(end and datetime.fromisoformat(end.replace("Z", "+00:00")) < now)
    return dict(
        id=key,
        site=site,
        evidence=evidence,
        coordinates=list(reversed(geometry.centre(site["geometry"]))),
        assessments=[r for r in store.list("assessment") if r.get("site_revision") == key],
        designs=[r for r in store.list("design") if r["site_revision"] == key],
        country=catalogue.COUNTRIES.get(
            site["country"],
            {
                "name": site["country"],
                "links": {},
                "protection": "National coverage requires review",
            },
        ),
    )


def perform(request, store, current_config):
    d = request.data
    if request.operation.startswith("requirements-"):
        from methane.learning_lab import jobs as assessment_jobs
        from methane.siting import requirements

        if request.operation == "requirements-save":
            return requirements.save(store, d)
        if request.operation == "requirements-index":
            return dict(
                briefs=store.list("requirements"),
                assessments=[
                    {k: r[k] for k in ("id", "title", "requirements_id", "study_ids")}
                    for r in store.list("operating-assessment")
                ],
            )
        if request.operation == "requirements-assess":
            return assessment_jobs.launch(store, "requirements", requirements.freeze(store, **d))
        if request.operation == "requirements-result":
            return dict(id=request.id, **store.get("operating-assessment", request.id))
    if request.operation.startswith("project-"):
        from methane.siting.projects import perform as project_operation

        return project_operation(store, request.operation, request.id, d)
    if request.operation.startswith("lab-"):
        from methane.learning_lab.service import perform as learning_operation

        return learning_operation(store, request.operation, request.id, d)
    if request.operation == "index":
        reference = catalogue.bootstrap(store)
        return dict(
            sites=catalogue.heads(store),
            references=reference,
            catalogue=catalogue.catalogue(),
            config=current_config,
        )
    if request.operation == "search":
        return sources.search(store, d["query"], request.offline)
    if request.operation == "view":
        return view(store, request.id)
    if request.operation == "save-site":
        candidate = SiteCandidate(**d)
        if (
            candidate.parent_id
            and store.get("site", candidate.parent_id)["site_id"] != candidate.site_id
        ):
            raise ValueError("Parent revision belongs to another site")
        return view(store, store.put("site", candidate))
    if request.operation == "discover":
        result = geometry.candidates_within(
            d["geometry"], d.get("spacing_m", 5000), d.get("limit", 100)
        )
        value = {"schema_version": "site-discovery/1", "region": d["geometry"], **result}
        return {"id": store.put("discovery", value), **value}
    if request.operation == "source":
        return {"source": store.get("source", request.id)}
    if request.operation == "import-source":
        raw = base64.b64decode(d["base64"], validate=True)
        source_id = sources.snapshot(store, raw, **d["metadata"])
        return {"source_id": source_id}
    if request.operation == "save-evidence":
        record = Evidence(**d)
        site = store.get("site", request.id)
        if site["site_id"] != record.site_id:
            raise ValueError("Evidence belongs to a different site")
        if record.source_id:
            store.get("source", record.source_id)
        store.put("evidence", record)
        return view(store, request.id)
    if request.operation == "resource":
        site = store.get("site", request.id)
        lat, lon = geometry.centre(site["geometry"])
        result = sources.solar_resource(
            store,
            lat,
            lon,
            d.get("tilt", 30),
            d.get("azimuth", 0),
            d.get("loss_percent", 14),
            request.offline,
        )
        store.put(
            "evidence",
            Evidence(
                site_id=site["site_id"],
                subject="solar",
                status="modelled",
                assertion="PVGIS reference PV resource",
                source_id=result["source_id"],
                value=result,
                unit="kWh/kWp/year",
                supplied_by="PVGIS adapter",
                uncertainty="Resource and conversion estimates; not site measurements or methane output",
            ),
        )
        return {"resource": result, **view(store, request.id)}
    if request.operation == "layers":
        site = store.get("site", request.id)
        policy = ScreeningPolicy(**d.get("policy", {}))
        products = []
        errors = []
        for family in d.get("families", ["land", "terrain", "protection"]):
            try:
                if family in ("land", "terrain"):
                    source = raster.window_source(store, site, family, request.offline)
                    result = raster.analyse(
                        store, source["source_id"], site["geometry"], family, policy
                    )
                elif family == "protection":
                    collection = sources.protected_areas(
                        store,
                        geometry.geographic(site["geometry"]).bounds,
                        site["country"],
                        request.offline,
                    )
                    result = {
                        "family": family,
                        "source_ids": collection["source_ids"],
                        "exclusions": [
                            dict(
                                geometry=f["geometry"],
                                source_id=collection["source_ids"][0],
                                reason="Natura avoidance policy",
                            )
                            for f in collection["features"]
                        ],
                        "summary": {
                            "features": len(collection["features"]),
                            "scope": collection["scope"],
                        },
                    }
                else:
                    raise ValueError("Unknown automatic layer; use source-bound import")
                products.append(result)
            except (ValueError, OSError) as exc:
                errors.append({"family": family, "status": "incomplete", "reason": str(exc)})
        return {
            "products": products,
            "incomplete": errors,
            "site_revision": request.id,
            "policy": policy.model_dump(),
        }
    if request.operation == "assess":
        site = store.get("site", request.id)
        policy = ScreeningPolicy(**d.get("policy", {}))
        exclusions = []
        coverage = []
        for product in d.get("products", []):
            family = product["family"]
            if family in ("land", "terrain"):
                result = raster.analyse(
                    store, product["source_id"], site["geometry"], family, policy
                )
                exclusions.extend(result["exclusions"])
                coverage.append(family)
            else:
                source = store.get("source", product["source_id"])
                collection = json.loads(store.read_raw(source["raw_sha256"]))
                if collection.get("type") != "FeatureCollection":
                    raise ValueError("Vector layer requires source-bound GeoJSON")
                coverage_geometry = d.get("coverage_geometry", {}).get(
                    product["source_id"], source["coverage"].get("geometry")
                )
                if source["product"] == "Natura 2000 spatial extract":
                    from shapely.geometry import box, mapping

                    coverage_geometry = mapping(box(*source["coverage"]["bounds"]))
                    if source["coverage"]["country"] != site["country"]:
                        raise ValueError("Protection extract belongs to another country")
                if not coverage_geometry or not geometry.geographic(
                    coverage_geometry, polygon=True
                ).covers(geometry.geographic(site["geometry"])):
                    raise ValueError(
                        "Imported vector layer needs a declared coverage polygon containing the site"
                    )
                for f in collection["features"]:
                    exclusions.append(
                        dict(
                            geometry=f["geometry"],
                            source_id=product["source_id"],
                            reason=product.get("reason", "Protection avoidance policy"),
                        )
                    )
                coverage.append(family)
        result = geometry.assess(site, policy, exclusions, coverage)
        result = catalogue.assessment_identity(site, result)
        key = store.put("assessment", result)
        return {"assessment_id": key, "assessment": result, **view(store, request.id)}
    if request.operation in ("lifecycle-preset", "lifecycle-check"):
        from dataclasses import replace

        from methane.lifecycle.fixtures import illustrative

        data = dict(d["config"])
        if request.operation == "lifecycle-preset":
            data.pop("lifecycle", None)
        config = Config.from_dict(data)
        if request.operation == "lifecycle-preset":
            if d["preset"] not in ("commissioning", "maintenance", "none"):
                raise ValueError("Unknown lifecycle fixture")
            config = (
                replace(config, lifecycle=None)
                if d["preset"] == "none"
                else illustrative(config, commission=d["preset"] == "commissioning")
            )
        life = config.lifecycle
        return dict(
            config=config.to_dict(),
            summary="Lifecycle disabled in this draft"
            if life is None
            else f"Validated draft: {len(life['packages'])} work packages, {len(life['conditions'])} condition mechanisms, {life['crew_hours_per_day']:g} project-crew hours per day. Explicit assumptions; save the design to use them in a new study.",
        )
    if request.operation == "save-design":
        record = DeploymentDesign(**d)
        site = store.get("site", record.site_revision)
        lat, lon = geometry.centre(site["geometry"])
        config = Config.from_dict(record.config)
        if abs(config.weather.latitude - lat) > 1e-6 or abs(config.weather.longitude - lon) > 1e-6:
            raise ValueError("Plant weather coordinates must match the saved site")
        if (
            record.assessment_id
            and store.get("assessment", record.assessment_id)["site_revision"]
            != record.site_revision
        ):
            raise ValueError("Assessment belongs to another site revision")
        for key in [*record.evidence_ids, *(record.utilities or {}).get("evidence_ids", [])]:
            if store.get("evidence", key)["site_id"] != site["site_id"]:
                raise ValueError("Evidence belongs to another site")
        from methane.siting.layout import calculate

        layout = calculate(site, record.layout)
        for feature in record.layout:
            if (
                feature.get("evidence_id")
                and store.get("evidence", feature["evidence_id"])["site_id"] != site["site_id"]
            ):
                raise ValueError("Layout evidence belongs to another site")
        return {
            "design_id": store.put("design", record),
            "layout": layout,
            **view(store, record.site_revision),
        }
    if request.operation == "design":
        from methane.siting.layout import calculate

        design = store.get("design", request.id)
        return {
            "design": design,
            "layout": calculate(store.get("site", design["site_revision"]), design["layout"]),
        }
    from methane.siting import (
        cashflow,
        comparison,
        environment,
        jobs,
        production,
        reporting,
        workflow,
    )

    if request.operation == "studies-index":
        return dict(
            designs=store.list("design"),
            environments=store.list("environment"),
            studies=[
                {"id": s["id"], "name": s["name"], "state": production.state(store, s["id"])}
                for s in store.list("study")
            ],
            recommendations=store.list("recommendation"),
            publications=[
                dict(
                    id=p["id"],
                    kind=p["kind"],
                    source_id=p["source_id"],
                    title=p.get("title")
                    or p["record"].get("manifest", {}).get("name")
                    or p["record"].get("title", "Recorded report"),
                )
                for p in store.list("publication")
            ],
            templates=store.list("template"),
            deployments=[
                {k: v.get(k) for k in ("id", "name", "mode")} for v in store.list("deployment")
            ],
        )
    if request.operation == "prepare-environment":
        return jobs.launch(store, request.token, d, request.offline)
    if request.operation == "data-job":
        return jobs.poll(request.token, request.id, d.get("cancel", False))
    if request.operation == "import-environment":
        return environment.import_measurements(store, **d)
    if request.operation == "calibrate":
        return environment.calibration(store, request.id, d["training_end"])
    if request.operation == "create-study":
        return production.create(store, **d)
    if request.operation == "repeat-study":
        from methane.learning_lab.editions import repeat

        return repeat(store, request.id)
    if request.operation == "study":
        value = production.inspect(store, request.id)
        value["runtime_estimate"] = workflow.runtime_estimate(value)
        return value
    if request.operation == "estimate-study":
        return workflow.runtime_estimate(
            production.inspect(store, request.id), d.get("seconds_per_hour")
        )
    if request.operation == "save-template":
        return workflow.save_template(store, request.id, **d)
    if request.operation == "report-draft":
        return reporting.draft(store, d["kind"], request.id, d.get("publication_id"))
    if request.operation == "start-study":
        return production.launch(store, request.id)
    if request.operation == "cancel-study":
        return production.cancel(store, request.id)
    if request.operation == "cash-defaults":
        return dict(assumptions=cashflow.defaults(store.get("design", request.id)["config"]))
    if request.operation == "cash-report":
        return cashflow.report(store, request.id, d["case_id"], d["assumptions"])
    if request.operation == "search-designs":
        return comparison.search(store, **d)
    if request.operation == "recommend":
        return comparison.recommend(store, **d)
    if request.operation == "publish":
        return reporting.publish(
            store,
            d["kind"],
            request.id,
            writeup=d.get("writeup"),
            previous_publication_id=d.get("previous_publication_id"),
        )
    if request.operation == "export":
        return reporting.bundle(store, request.id)
    raise ValueError("Unknown Sites operation")


def handle(request: Request):
    from methane.study_service import context

    current = context(request.token, request.run_id)
    try:
        answer = perform(request, Store(), current["config"])
        bundle_ready = (
            request.operation == "lab-job"
            and answer.get("result_kind") == "bundle"
            and answer.get("status") == "complete"
        )
        if request.operation in ("publish", "export") or bundle_ready:
            from urllib.parse import urlencode

            key = (
                answer["result"]["publication_id"]
                if bundle_ready
                else answer.get("publication_id", request.id)
            )
            answer["download_url"] = (
                "/dispatch/site-download/"
                + key
                + "?"
                + urlencode(
                    dict(
                        token=request.token,
                        run_id=request.run_id,
                        format="html" if request.operation == "publish" else "zip",
                    )
                )
            )
        return {"key": request.key, **answer}
    except (ValueError, KeyError, TypeError, OSError) as exc:
        return {"key": request.key, "error": str(exc)}


def static(filename: str):
    root = Path(__file__).resolve().parents[2] / "assets"
    if filename == "basemap.json":
        return FileResponse(root / "sites-basemap.json", media_type="application/json")
    if filename not in (
        "maplibre-gl.mjs",
        "maplibre-gl-shared.mjs",
        "maplibre-gl-worker.mjs",
        "maplibre-gl.css",
    ):
        raise HTTPException(404, "Unknown Sites asset")
    return FileResponse(
        root / "vendor" / "maplibre" / filename,
        media_type="text/css" if filename.endswith(".css") else "text/javascript",
    )


def download(publication_id: str, token: str, run_id: str, format: str = "html"):
    from methane.siting.store import identifier
    from methane.study_service import context

    context(token, run_id)
    store = Store()
    store.get("publication", publication_id)
    if format not in ("html", "zip"):
        raise HTTPException(400, "Unknown report format")
    path = (
        store.root
        / ("reports" if format == "html" else "exports")
        / (identifier(publication_id) + "." + format)
    )
    if not path.exists():
        raise HTTPException(404, "Generate this publication/export first")
    return FileResponse(
        path,
        media_type="text/html" if format == "html" else "application/zip",
        filename="dispatch-sites-" + publication_id[:12] + "." + format,
        content_disposition_type="inline" if format == "html" else "attachment",
    )
