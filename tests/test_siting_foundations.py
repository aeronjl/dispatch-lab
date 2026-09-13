from datetime import UTC, datetime

import numpy as np
import pytest
from rasterio.io import MemoryFile
from rasterio.transform import from_origin
from shapely.geometry import box, mapping
from shapely.ops import transform

from methane.siting.catalogue import bootstrap, heads
from methane.siting.contracts import Evidence, ScreeningPolicy, SiteCandidate
from methane.siting.geometry import FORWARD, INVERSE, assess, candidates_within
from methane.siting.raster import analyse
from methane.siting.sources import MissingData, snapshot, solar_resource
from methane.siting.store import Store


def parcel():
    x, y = FORWARD.transform(0, 51)
    return mapping(transform(INVERSE.transform, box(x, y, x + 100, y + 100)))


def candidate():
    return SiteCandidate(
        site_id="test",
        name="Test parcel",
        country="GB",
        geometry=parcel(),
        origin="Independent geometry fixture",
    )


def test_equal_area_and_duplicate_exclusions():
    c = candidate().model_dump()
    x, y = FORWARD.transform(0, 51)
    exclusion = dict(
        geometry=mapping(transform(INVERSE.transform, box(x, y, x + 50, y + 100))),
        source_id="a" * 64,
        reason="Test policy",
    )
    r = assess(
        c,
        ScreeningPolicy(equipment_footprint_m2=0),
        [exclusion, exclusion],
        coverage=["land", "terrain", "protection", "flood"],
    )
    assert r["total_area_m2"] == pytest.approx(10000, abs=0.1)
    assert r["excluded_area_m2"] == pytest.approx(5000, abs=0.1)
    assert r["usable_area_m2"] == pytest.approx(5000, abs=0.1)
    assert r["coarse_pv_capacity_kw"] == pytest.approx(200, abs=0.01)
    assert r["status"] == "screened under policy"
    assert "land rights" in r["unresolved"]


def test_missing_layers_and_points_are_not_clearance():
    c = candidate().model_dump()
    assert assess(c, ScreeningPolicy())["status"] == "needs investigation"
    c["geometry"] = {"type": "Point", "coordinates": [0, 51]}
    r = assess(c, ScreeningPolicy(), coverage=["land", "terrain", "protection", "flood"])
    assert r["total_area_m2"] is r["coarse_pv_capacity_kw"] is None
    assert "parcel geometry" in r["unresolved"]


def test_no_silent_geometry_repair_or_unsupported_coordinates():
    for g in (
        {"type": "Point", "coordinates": [0, 0]},
        {"type": "Polygon", "coordinates": [[[0, 51], [1, 52], [1, 51], [0, 52], [0, 51]]]},
        {"type": "Point", "coordinates": [0, 51, 5]},
    ):
        with pytest.raises(ValueError):
            SiteCandidate(site_id="a", name="a", country="GB", geometry=g, origin="fixture")


def test_content_addressing_and_immutable_editions(tmp_path):
    s = Store(tmp_path)
    c = candidate()
    first = s.put("site", c)
    assert first == s.put("site", c)
    second = s.put("site", c.model_copy(update={"parent_id": first, "name": "Revised"}))
    assert s.get("site", first)["name"] == "Test parcel"
    assert [r["id"] for r in heads(s)] == [second]
    s.path("site", first).write_text("{}")
    with pytest.raises(ValueError, match="integrity"):
        s.get("site", first)
    with pytest.raises(ValueError):
        s.get("site", "../../config")


def test_evidence_needs_identified_source_and_uncertainty():
    with pytest.raises(ValueError, match="saved source"):
        Evidence(
            site_id="test",
            subject="water",
            status="reported",
            assertion="Connection offered",
            supplied_by="Supplier",
            uncertainty="Offer expires",
        )
    assert (
        Evidence(
            site_id="test",
            subject="water",
            status="assumed",
            assertion="Illustrative supply",
            supplied_by="Analyst",
            uncertainty="No offer",
        ).source_id
        is None
    )


def test_offline_real_reference_and_missing_request(tmp_path):
    s = Store(tmp_path)
    rows = bootstrap(s)
    assert len(rows) == 3
    assert rows[0]["resource"]["annual"]["E_y"] == 1010.28
    assert all(r["geometry"]["type"] == "Point" for r in rows)
    assert bootstrap(s) == rows
    with pytest.raises(MissingData):
        solar_resource(s, 52, 0, offline=True)


def test_raster_classes_and_missing_coverage(tmp_path):
    s = Store(tmp_path)
    data = np.array(
        [[10, 10, 20, 20], [10, 10, 20, 20], [30, 30, 40, 40], [30, 30, 40, 40]], dtype="uint8"
    )
    with MemoryFile() as mem:
        with mem.open(
            driver="GTiff",
            width=4,
            height=4,
            count=1,
            dtype="uint8",
            crs="EPSG:4326",
            transform=from_origin(0, 51.004, 0.001, 0.001),
            nodata=0,
        ) as ds:
            ds.write(data, 1)
        raw = mem.read()
    key = snapshot(
        s,
        raw,
        provider="Independent fixture",
        product="Class grid",
        edition="1",
        retrieved_at=datetime.now(UTC),
        request={},
        attribution="Test fixture",
        licence="Test",
        timing="Static",
        source_url="fixture:class-grid",
    )
    r = analyse(
        s,
        key,
        mapping(box(0.00001, 51.00001, 0.00399, 51.00399)),
        "land",
        ScreeningPolicy(excluded_land_classes=[10]),
    )
    assert r["summary"]["class_cell_counts"] == {"10": 4, "20": 4, "30": 4, "40": 4}
    assert len(r["exclusions"]) == 1
    with pytest.raises(MissingData, match="full polygon"):
        analyse(s, key, mapping(box(-0.001, 51, 0.003, 51.004)), "land", ScreeningPolicy())


def test_search_is_bounded_not_ranked():
    r = candidates_within(mapping(box(0, 51, 0.1, 51.1)), spacing_m=1000, limit=3)
    assert len(r["points"]) == 3 and r["truncated"]
    assert "no suitability ranking" in r["ordering"]
    with pytest.raises(ValueError):
        candidates_within(mapping(box(-20, 35, 40, 70)), spacing_m=100, limit=500)


def test_api_design_and_source_boundaries(tmp_path):
    from methane.config import Config
    from methane.siting.service import Request, perform

    store = Store(tmp_path)
    config = Config().to_dict()

    def call(operation, data=None, key=None):
        return perform(
            Request(
                token="local-test",
                run_id="run",
                key="selection",
                operation=operation,
                id=key,
                data=data or {},
            ),
            store,
            config,
        )

    index = call("index")
    anchor = index["references"][0]
    view = call("view", key=anchor["id"])
    assert view["coordinates"] == [-0.1278, 51.5074]
    design = dict(site_revision=anchor["id"], name="Matched reference", config=config)
    saved = call("save-design", design)
    assert store.get("design", saved["design_id"])["config"] == config
    revised = {**config, "weather": {**config["weather"], "latitude": 52}}
    with pytest.raises(ValueError, match="coordinates"):
        call("save-design", {**design, "config": revised})
    with pytest.raises(ValueError, match="Invalid saved"):
        call("source", key="../source")
    with pytest.raises(ValueError, match="Unknown"):
        call("unsupported")
