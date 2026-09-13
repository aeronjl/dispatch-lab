"""Country-specific evidence routes alongside shared, explicitly identified products."""

import json
from pathlib import Path

from methane.siting.contracts import SiteCandidate, SourceSnapshot
from methane.siting.sources import resource_view
from methane.siting.store import digest, encode

DOCS = Path(__file__).resolve().parents[2] / "docs" / "sites"
COUNTRIES = {
    "GB": {
        "name": "United Kingdom",
        "timezone": "Europe/London",
        "protection": "National layers required; England MAGIC does not cover Scotland, Wales or Northern Ireland",
        "links": {
            "England environmental evidence": "https://magic.defra.gov.uk/",
            "Scottish natural heritage": "https://sitelink.nature.scot/",
            "Welsh environmental evidence": "https://datamap.gov.wales/",
            "Northern Ireland environment": "https://www.daera-ni.gov.uk/topics/land-and-landscapes/protected-areas",
            "UKPN network evidence": "https://dso.ukpowernetworks.co.uk/dso-data",
            "GB electricity data": "https://developer.data.elexon.co.uk/",
        },
    },
    "ES": {
        "name": "Spain",
        "timezone": "Europe/Madrid",
        "protection": "Natura 2000 plus national and regional designations",
        "links": {
            "National spatial data": "https://centrodedescargas.cnig.es/",
            "Cadastre": "https://www.sedecatastro.gob.es/",
            "Electricity data": "https://api.esios.ree.es/",
        },
    },
    "DK": {
        "name": "Denmark",
        "timezone": "Europe/Copenhagen",
        "protection": "Natura 2000 plus Danish designations",
        "links": {
            "Environmental evidence": "https://arealinformation.miljoeportal.dk/",
            "Energy data": "https://www.energidataservice.dk/",
            "Technology costs": "https://ens.dk/en/analyses-and-statistics/technology-data-renewable-fuels",
        },
    },
    "DE": {
        "name": "Germany",
        "timezone": "Europe/Berlin",
        "protection": "Natura 2000 plus federal and state designations",
        "links": {
            "Measured weather": "https://opendata.dwd.de/climate_environment/CDC/",
            "Geodata": "https://www.geoportal.de/",
        },
    },
    "FR": {
        "name": "France",
        "timezone": "Europe/Paris",
        "protection": "Natura 2000 plus national and local designations",
        "links": {
            "Spatial evidence": "https://geoservices.ign.fr/",
            "National open data": "https://www.data.gouv.fr/",
        },
    },
    "NL": {
        "name": "Netherlands",
        "timezone": "Europe/Amsterdam",
        "protection": "Natura 2000 plus Dutch designations",
        "links": {"National geodata": "https://www.pdok.nl/"},
    },
    "IT": {
        "name": "Italy",
        "timezone": "Europe/Rome",
        "protection": "Natura 2000 plus national and regional designations",
        "links": {"National geodata": "https://geodati.gov.it/"},
    },
    "PT": {
        "name": "Portugal",
        "timezone": "Europe/Lisbon",
        "protection": "Natura 2000 plus national designations",
        "links": {"National geodata": "https://snig.dgterritorio.gov.pt/"},
    },
}


def catalogue():
    return dict(
        version="site-data-catalogue/1",
        families=json.loads((DOCS / "data-catalogue.json").read_text()),
        countries=COUNTRIES,
        adapters={
            "solar": "PVGIS 5.3 reference PV",
            "weather": "ERA5 historical / original ECMWF vintages",
            "land": "ESA WorldCover 2021/v200 native class raster",
            "terrain": "Copernicus GLO-30 native raster",
            "protection": "Natura 2000 regional features; national imports",
            "imports": "Source-bound GeoJSON / single-band GeoTIFF / CSV measurements / evidence and quotes",
        },
        clarification="Country links are investigation routes, not verified parcel evidence or live DSO connections. CLCplus is supported through source-bound raster import; ESA WorldCover is a separate explicitly selected public adapter, never an unlabelled substitute.",
    )


def bootstrap(store):
    """Seed regional points and pinned reference PV, never fabricate deployable polygons."""
    countries = {"London": "GB", "Seville": "ES", "Copenhagen": "DK"}
    result = []
    for row in json.loads((DOCS / "reference-resources.json").read_text()):
        response, request = row["response"], row["request"]
        place = response["inputs"]["location"]
        country = countries[row["name"]]
        candidate = SiteCandidate(
            site_id="reference-" + row["name"].lower(),
            name=row["name"] + " regional anchor",
            country=country,
            timezone=COUNTRIES[country]["timezone"],
            geometry={"type": "Point", "coordinates": [place["longitude"], place["latitude"]]},
            origin="Existing regional weather fixture; city coordinates are not candidate development land",
        )
        site_id = store.put("site", candidate)
        source = SourceSnapshot(
            provider="European Commission JRC",
            product="PVGIS 5.3 PVcalc",
            edition="5.3/SARAH3",
            retrieved_at=request["retrieved_at"],
            request=request["params"],
            raw_sha256=store.raw(encode(response)),
            attribution="European Commission Joint Research Centre / PVGIS",
            licence="European Commission reuse policy; cite PVGIS",
            redistribution="permitted",
            timing="Monthly/annual reference PV output; original retrieval 13 September 2026; JSON canonically encoded for this fixture",
            source_url=request["request_url"],
            units={"E_y": "kWh/kWp/year", "E_m": "kWh/kWp/month"},
        )
        source_id = store.put("source", source)
        result.append(
            {
                "id": site_id,
                **candidate.model_dump(mode="json"),
                "resource": resource_view(source_id, response),
            }
        )
    return result


def heads(store):
    rows = store.list("site")
    parents = {r.get("parent_id") for r in rows}
    return [r for r in rows if r["id"] not in parents]


def assessment_identity(candidate, value):
    return {**value, "site_revision": digest(candidate)}
