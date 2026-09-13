"""Metric Europe screening. Geometry predicates never establish development rights."""

import math

from pyproj import Transformer
from shapely.geometry import mapping, shape
from shapely.ops import transform, unary_union

FORWARD = Transformer.from_crs("EPSG:4326", "EPSG:3035", always_xy=True)
INVERSE = Transformer.from_crs("EPSG:3035", "EPSG:4326", always_xy=True)


def geographic(value, polygon=False):
    g = shape(value)
    if g.is_empty or not g.is_valid or g.has_z:
        raise ValueError(
            "Supply valid nonempty two-dimensional geometry; it is not repaired silently"
        )
    if g.geom_type not in (
        ("Polygon", "MultiPolygon") if polygon else ("Point", "Polygon", "MultiPolygon")
    ):
        raise ValueError("Site geometry must be a point or polygon")
    west, south, east, north = g.bounds
    if not all(math.isfinite(v) for v in g.bounds) or not (
        -25 <= west <= east <= 45 and 34 <= south <= north <= 72
    ):
        raise ValueError("Site geometry lies outside the declared European coverage")
    return g


def centre(value):
    g = geographic(value)
    if g.geom_type == "Point":
        return g.y, g.x
    c = transform(INVERSE.transform, transform(FORWARD.transform, g).representative_point())
    return c.y, c.x


def assess(candidate, policy, exclusions=(), coverage=(), evidence=()):
    """Union exclusions before subtraction; unknown layer coverage is not clearance."""
    g = geographic(candidate["geometry"])
    point = g.geom_type == "Point"
    metric = transform(FORWARD.transform, g)
    clipped, intersection_records = [], []
    for layer in exclusions:
        if not layer.get("source_id") or not layer.get("reason"):
            raise ValueError("Each exclusion requires a source and declared policy reason")
        other = transform(FORWARD.transform, geographic(layer["geometry"], polygon=True))
        if policy.setback_m:
            other = other.buffer(policy.setback_m)
        overlap = metric.intersection(other)
        if not overlap.is_empty:
            clipped.append(overlap)
        intersection_records.append(
            {
                "source_id": layer["source_id"],
                "reason": layer["reason"],
                "intersects": not overlap.is_empty,
                "area_m2": overlap.area if not point else None,
            }
        )
    excluded = unary_union(clipped)
    remaining = metric.difference(excluded)
    pieces = list(remaining.geoms) if remaining.geom_type == "MultiPolygon" else [remaining]
    missing = [k for k in ("land", "terrain", "protection", "flood") if k not in coverage]
    usable = None if point else remaining.area
    capacity = (
        None if point else max(0, usable - policy.equipment_footprint_m2) * policy.pv_kw_per_m2
    )
    state = (
        "excluded by selected policy"
        if not point and remaining.is_empty
        else "needs investigation"
        if missing or point
        else "screened under policy"
    )
    return dict(
        schema_version="site-assessment/1",
        site_id=candidate["site_id"],
        status=state,
        calculation_crs="EPSG:3035",
        policy=policy.model_dump(),
        source_coverage=list(coverage),
        total_area_m2=None if point else metric.area,
        excluded_area_m2=None if point else excluded.area,
        usable_area_m2=usable,
        largest_contiguous_area_m2=None if point else max((p.area for p in pieces), default=0),
        coarse_pv_capacity_kw=capacity,
        usable_geometry=None if point else mapping(transform(INVERSE.transform, remaining)),
        intersections=intersection_records,
        evidence_ids=list(evidence),
        unresolved=missing
        + (["parcel geometry"] if point else [])
        + [
            "land rights",
            "planning permission",
            "utility/CO2/offtake agreements",
            "surveyed access",
        ],
        scope="Area remaining under supplied policy layers. Unknown coverage stays unresolved; capacity is an illustrative area screen, not an engineered layout or permission.",
    )


def candidates_within(geometry, spacing_m=5000, limit=100):
    g = transform(FORWARD.transform, geographic(geometry, polygon=True))
    if not 100 <= spacing_m <= 100000 or not 1 <= limit <= 500:
        raise ValueError("Candidate search requires 100–100000 m spacing and 1–500 results")
    from shapely.geometry import Point

    x0, y0, x1, y1 = g.bounds
    if (x1 - x0) * (y1 - y0) / spacing_m**2 > 100000:
        raise ValueError("Search is too broad for this spacing; coarsen the regional grid")
    points = []
    x = x0 + spacing_m / 2
    while x < x1 and len(points) < limit:
        y = y0 + spacing_m / 2
        while y < y1 and len(points) < limit:
            p = Point(x, y)
            if g.covers(p):
                points.append(mapping(transform(INVERSE.transform, p)))
            y += spacing_m
        x += spacing_m
    return {
        "points": points,
        "spacing_m": spacing_m,
        "limit": limit,
        "truncated": len(points) == limit,
        "ordering": "EPSG:3035 west to east, south to north; no suitability ranking",
    }
