"""Survey-space layout calculations; drawing does not qualify engineering or routing."""

from typing import Literal

from pydantic import Field
from shapely.geometry import shape
from shapely.ops import transform, unary_union

from methane.siting.contracts import Record
from methane.siting.geometry import FORWARD, geographic


class Feature(Record):
    asset_id: str = Field(min_length=1, max_length=120)
    kind: Literal[
        "pv-area",
        "equipment-pad",
        "support-pad",
        "exclusion",
        "access-route",
        "cable-route",
        "pipe-route",
    ]
    geometry: dict
    evidence_id: str | None = None
    assumption: str = Field(min_length=1, max_length=2000)


def calculate(site, features):
    boundary = geographic(site["geometry"])
    if features and boundary.geom_type == "Point":
        raise ValueError("A site plan needs an explicit parcel boundary")
    metric = transform(FORWARD.transform, boundary)
    rows, occupied = [], []
    ids = set()
    for item in features:
        f = Feature(**item)
        if f.asset_id in ids:
            raise ValueError("Layout asset identities must be unique")
        ids.add(f.asset_id)
        g = shape(f.geometry)
        route = f.kind.endswith("route")
        if (
            not g.is_valid
            or g.is_empty
            or g.has_z
            or g.geom_type not in (("LineString",) if route else ("Polygon", "MultiPolygon"))
        ):
            raise ValueError("Routes require valid lines; areas require valid polygons")
        if not boundary.covers(g):
            raise ValueError("Layout extends outside the declared parcel")
        m = transform(FORWARD.transform, g)
        if not route:
            occupied.append(m)
        rows.append(
            dict(
                **f.model_dump(),
                area_m2=None if route else m.area,
                length_m=m.length if route else None,
            )
        )
    union = unary_union(occupied)
    return dict(
        schema_version="site-layout-calculation/1",
        crs="EPSG:3035",
        features=rows,
        parcel_area_m2=metric.area,
        occupied_union_m2=union.area,
        overlapping_area_m2=sum(p.area for p in occupied) - union.area,
        unallocated_area_m2=metric.difference(union).area,
        scope="Declared survey-space areas and route lengths. No cable losses, pipe pressure, safety separation, rights of access or robot traversal are inferred. Apply quoted distances to an identified service configuration explicitly.",
    )
