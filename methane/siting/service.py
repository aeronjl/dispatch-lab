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
        return geometry.candidates_within(
            d["geometry"], d.get("spacing_m", 5000), d.get("limit", 100)
        )
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
                coverage_geometry = d.get("coverage_geometry", {}).get(product["source_id"])
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
        for key in record.evidence_ids:
            if store.get("evidence", key)["site_id"] != site["site_id"]:
                raise ValueError("Evidence belongs to another site")
        return {"design_id": store.put("design", record), **view(store, record.site_revision)}
    if request.operation == "design":
        return {"design": store.get("design", request.id)}
    raise ValueError("Unknown Sites operation")


def handle(request: Request):
    from methane.study_service import context

    current = context(request.token, request.run_id)
    try:
        answer = perform(request, Store(), current["config"])
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
