"""Bounded public-data retrieval and immutable evidence import. No arbitrary URL proxy."""

import json
from datetime import UTC, datetime
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from methane.siting.contracts import SourceSnapshot
from methane.siting.store import atomic, digest, encode

PVGIS = "https://re.jrc.ec.europa.eu/api/v5_3/PVcalc"
NATURA = "https://bio.discomap.eea.europa.eu/arcgis/rest/services/ProtectedSites/Natura2000Sites/MapServer/0/query"
ENDPOINTS = {
    PVGIS,
    NATURA,
    "https://geocoding-api.open-meteo.com/v1/search",
    "https://archive-api.open-meteo.com/v1/archive",
    "https://single-runs-api.open-meteo.com/v1/forecast",
}


class MissingData(ValueError):
    pass


def snapshot(store, raw, **metadata):
    if len(raw) > 50_000_000:
        raise ValueError("Source exceeds the 50 MB import limit; use a regional/time subset")
    value = SourceSnapshot(raw_sha256=store.raw(raw), **metadata)
    return store.put("source", value)


def fetch(store, endpoint, params, metadata, offline=False):
    if endpoint not in ENDPOINTS:
        raise ValueError("Unknown public-data adapter endpoint")
    url = endpoint + "?" + urlencode(params)
    key = digest(dict(url=url, adapter=metadata["product"], edition=metadata["edition"]))
    path = store.root / "request-cache" / (key + ".json")
    if path.exists():
        source_id = json.loads(path.read_bytes())["source_id"]
        source = store.get("source", source_id)
        return source_id, json.loads(store.read_raw(source["raw_sha256"]))
    if offline:
        raise MissingData("No saved response for this location, product and request")
    try:
        with urlopen(
            Request(url, headers={"User-Agent": "DispatchLab-Sites/1"}), timeout=40
        ) as response:
            raw = response.read(50_000_001)
        data = json.loads(raw)
        if isinstance(data, dict) and data.get("error"):
            raise ValueError(str(data.get("reason", data["error"])))
        source_id = snapshot(
            store, raw, **metadata, retrieved_at=datetime.now(UTC), request=params, source_url=url
        )
        atomic(path, encode({"source_id": source_id}))
        return source_id, data
    except (OSError, ValueError) as exc:
        # Preserve failed requests without presenting them as empty datasets.
        atomic(
            store.root / "retrieval-failures" / (key + ".json"),
            encode(dict(url=url, at=datetime.now(UTC).isoformat(), error=str(exc))),
        )
        raise MissingData(f"Incomplete {metadata['product']} retrieval: {exc}") from exc


def solar_resource(store, latitude, longitude, tilt=30, azimuth=0, loss_percent=14, offline=False):
    if not 34 <= latitude <= 72 or not -25 <= longitude <= 45:
        raise ValueError("Location outside European coverage")
    if not 0 <= tilt <= 90 or not -180 <= azimuth <= 180 or not 0 <= loss_percent < 100:
        raise ValueError("Invalid reference PV orientation or losses")
    params = dict(
        lat=latitude,
        lon=longitude,
        peakpower=1,
        loss=loss_percent,
        angle=tilt,
        aspect=azimuth,
        pvtechchoice="crystSi",
        mountingplace="free",
        usehorizon=1,
        raddatabase="PVGIS-SARAH3",
        outputformat="json",
    )
    # Pinned reference fixtures use original request ordering/number formatting.
    # Reuse only a parameter-equivalent response, never a nearby location.
    if offline:
        for source in store.list("source"):
            if source["product"] == "PVGIS 5.3 PVcalc" and source["request"] == params:
                return resource_view(source["id"], json.loads(store.read_raw(source["raw_sha256"])))
    source_id, data = fetch(
        store,
        PVGIS,
        params,
        dict(
            provider="European Commission JRC",
            product="PVGIS 5.3 PVcalc",
            edition="5.3/SARAH3",
            attribution="European Commission Joint Research Centre / PVGIS",
            licence="European Commission reuse policy; cite PVGIS",
            redistribution="permitted",
            timing="Monthly and annual mean reference PV output; not hourly plant DC",
            units={"E_y": "kWh/kWp/year", "E_m": "kWh/kWp/month"},
        ),
        offline,
    )
    return resource_view(source_id, data)


def resource_view(source_id, data):
    try:
        monthly, annual = data["outputs"]["monthly"]["fixed"], data["outputs"]["totals"]["fixed"]
        if [r["month"] for r in monthly] != list(range(1, 13)) or abs(
            sum(r["E_m"] for r in monthly) - annual["E_y"]
        ) > 0.2:
            raise ValueError("Monthly/annual PVGIS output does not reconcile")
        return dict(
            source_id=source_id,
            inputs=data["inputs"],
            annual=annual,
            monthly=monthly,
            winter_share=sum(r["E_m"] for r in monthly if r["month"] in (12, 1, 2)) / annual["E_y"]
            if annual["E_y"]
            else None,
            scope="Provider reference PV output, not Dispatch Lab DC or methane production; city points are not assessed parcels",
        )
    except (KeyError, TypeError) as exc:
        raise MissingData("PVGIS response lacks the expected reference-output fields") from exc


def search(store, query, offline=False):
    if not 2 <= len(query.strip()) <= 200:
        raise ValueError("Search requires 2–200 characters")
    source, data = fetch(
        store,
        "https://geocoding-api.open-meteo.com/v1/search",
        dict(name=query.strip(), count=10, language="en", format="json"),
        dict(
            provider="Open-Meteo / GeoNames",
            product="Location search",
            edition="v1",
            attribution="Open-Meteo.com / GeoNames",
            licence="CC BY 4.0; public API non-commercial use terms",
            redistribution="permitted",
            timing="Location names at retrieval",
        ),
        offline,
    )
    return {
        "source_id": source,
        "results": [
            r
            for r in data.get("results", [])
            if 34 <= r["latitude"] <= 72 and -25 <= r["longitude"] <= 45
        ],
    }


def protected_areas(store, bounds, country, offline=False):
    if country == "GB":
        raise MissingData(
            "Natura 2000 does not establish current UK coverage. Import the relevant national protection layer."
        )
    west, south, east, north = bounds
    if (
        east - west > 1
        or north - south > 1
        or not (-25 <= west <= east <= 45 and 34 <= south <= north <= 72)
    ):
        raise ValueError("Request a European regional extract no larger than 1° × 1°")
    features, sources, offset = [], [], 0
    while True:
        source, data = fetch(
            store,
            NATURA,
            dict(
                f="geojson",
                where="1=1",
                geometry=f"{west},{south},{east},{north}",
                geometryType="esriGeometryEnvelope",
                inSR=4326,
                outSR=4326,
                spatialRel="esriSpatialRelIntersects",
                outFields="*",
                returnGeometry="true",
                resultOffset=offset,
                resultRecordCount=200,
            ),
            dict(
                provider="European Environment Agency",
                product="Natura 2000 spatial extract",
                edition="Service edition at retrieval; freeze raw response",
                attribution="EEA / Natura 2000 country submissions",
                licence="EEA standard reuse policy; attribution required; sensitive features may be omitted",
                redistribution="permitted",
                timing="Designation inventory at retrieval",
                coverage={"bounds": list(bounds), "country": country},
            ),
            offline,
        )
        batch = data.get("features")
        if batch is None:
            raise MissingData("Natura response has no feature collection")
        sources.append(source)
        features.extend(batch)
        if not data.get("exceededTransferLimit") and len(batch) < 200:
            break
        offset += len(batch)
        if not batch or offset >= 10000:
            raise MissingData("Protection extract is truncated; use a smaller area")
    return dict(
        type="FeatureCollection",
        features=features,
        source_ids=sources,
        coverage={"family": "protection", "bounds": list(bounds), "country": country},
        scope="Network inventory, not planning permission; national protection layers may add restrictions",
    )
