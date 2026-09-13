"""Source-bound raster sampling, with class/terrain exclusions at native resolution."""

import json
import math
from datetime import UTC, datetime

import numpy as np
import rasterio
from rasterio.features import geometry_mask, shapes
from rasterio.io import MemoryFile
from rasterio.warp import transform_geom
from rasterio.windows import from_bounds

from methane.siting.geometry import geographic
from methane.siting.sources import MissingData, snapshot
from methane.siting.store import atomic, digest, encode


def window_source(store, candidate, family, offline=False):
    """Read only intersecting COG blocks; retain the exact extracted numeric raster."""
    if family not in ("land", "terrain"):
        raise ValueError("Unknown raster family")
    g = geographic(candidate["geometry"], polygon=True)
    west, south, east, north = g.bounds
    if east - west > 0.1 or north - south > 0.1:
        raise ValueError("Raster assessment requires a parcel/regional subset under 0.1° per side")
    step = 3 if family == "land" else 1
    lon, lat = math.floor(west / step) * step, math.floor(south / step) * step
    if east > lon + step or north > lat + step:
        raise MissingData(
            "Parcel crosses a source tile boundary. Import a merged raster extract with its source metadata."
        )
    ns, ew = (
        f"{'N' if lat >= 0 else 'S'}{abs(lat):02d}",
        f"{'E' if lon >= 0 else 'W'}{abs(lon):03d}",
    )
    if family == "land":
        url = f"https://esa-worldcover.s3.eu-central-1.amazonaws.com/v200/2021/map/ESA_WorldCover_10m_2021_v200_{ns}{ew}_Map.tif"
        product, edition = "ESA WorldCover land classes", "2021/v200"
        licence, attribution = (
            "CC BY 4.0",
            "ESA WorldCover project 2021 / Contains modified Copernicus Sentinel data (2021) processed by ESA WorldCover consortium",
        )
    else:
        stem = f"Copernicus_DSM_COG_10_{ns}_00_{ew}_00_DEM"
        url = f"https://copernicus-dem-30m.s3.amazonaws.com/{stem}/{stem}.tif"
        product, edition = "Copernicus GLO-30 surface elevation", "Public COG edition at retrieval"
        licence, attribution = (
            "Copernicus DEM GLO-30 public licence",
            "© DLR e.V. 2010–2014 and © Airbus Defence and Space GmbH 2014–2018 provided under COPERNICUS by the European Union and ESA",
        )
    key = digest(dict(url=url, bounds=list(g.bounds), adapter="native-window/1"))
    cache = store.root / "raster-cache" / (key + ".json")
    if cache.exists():
        result = json.loads(cache.read_bytes())
        source = store.get("source", result["source_id"])
        store.read_raw(source["raw_sha256"])
        return result
    if offline:
        raise MissingData("No saved raster subset for this polygon and product")
    try:
        with rasterio.Env(
            GDAL_DISABLE_READDIR_ON_OPEN="EMPTY_DIR",
            CPL_VSIL_CURL_ALLOWED_EXTENSIONS=".tif",
            GDAL_HTTP_TIMEOUT="40",
            GDAL_HTTP_MAX_RETRY="1",
        ):
            with rasterio.open(url) as ds:
                window = (
                    from_bounds(west, south, east, north, ds.transform)
                    .round_offsets()
                    .round_lengths()
                )
                # One-cell border supports boundary coverage and terrain derivatives.
                window = rasterio.windows.Window(
                    max(0, window.col_off - 1),
                    max(0, window.row_off - 1),
                    window.width + 3,
                    window.height + 3,
                )
                if window.width * window.height > 2_000_000:
                    raise ValueError("Raster subset exceeds two million cells")
                data = ds.read(1, window=window, masked=True)
                profile = ds.profile.copy()
                profile.update(
                    driver="GTiff",
                    width=data.shape[1],
                    height=data.shape[0],
                    count=1,
                    transform=ds.window_transform(window),
                    compress="deflate",
                )
                with MemoryFile() as mem:
                    with mem.open(**profile) as out:
                        out.write(data.filled(ds.nodata or 0), 1)
                    raw = mem.read()
        source_id = snapshot(
            store,
            raw,
            provider="ESA / Copernicus",
            product=product,
            edition=edition,
            retrieved_at=datetime.now(UTC),
            request={
                "url": url,
                "bounds": list(g.bounds),
                "derivation": "native raster window with border, lossless GeoTIFF encoding; raw hash covers the extracted raster, not the remote whole tile",
            },
            attribution=attribution,
            licence=licence,
            redistribution="permitted",
            timing="Static mapped surface at product epoch",
            source_url=url,
            coverage={"bounds": list(g.bounds), "family": family},
            units={"band_1": "class" if family == "land" else "m"},
        )
        result = {"source_id": source_id, "family": family}
        atomic(cache, encode(result))
        return result
    except (OSError, rasterio.errors.RasterioError) as exc:
        raise MissingData(f"Raster subset unavailable: {exc}") from exc


def analyse(store, source_id, geometry, family, policy):
    source = store.get("source", source_id)
    raw = store.read_raw(source["raw_sha256"])
    geographic(geometry, polygon=True)
    with MemoryFile(raw) as mem, mem.open() as ds:
        if ds.crs is None or ds.count != 1 or ds.width * ds.height > 2_000_000:
            raise ValueError("Raster needs one band, an explicit CRS and at most two million cells")
        polygon = transform_geom("EPSG:4326", ds.crs, geometry)
        inside = geometry_mask([polygon], (ds.height, ds.width), ds.transform, invert=True)
        data = ds.read(1, masked=True)
        valid = inside & ~np.ma.getmaskarray(data) & np.isfinite(data.data)
        if not inside.any() or valid.sum() != inside.sum():
            raise MissingData("No cells or missing raster cells in the parcel")
        # Ensure the full parcel is covered, not just the part intersecting this tile.
        from shapely.geometry import box, shape

        if not box(*ds.bounds).covers(shape(polygon)):
            raise MissingData("Raster does not cover the full polygon")
        if family == "land":
            classes, counts = np.unique(data.data[valid], return_counts=True)
            values = {str(int(k)): int(v) for k, v in zip(classes, counts, strict=True)}
            excluded = valid & np.isin(data.data, policy.excluded_land_classes)
            summary = {
                "class_cell_counts": values,
                "classification": "Input product classes, not zoning",
                "native_pixel_size": list(ds.res),
            }
        elif family == "terrain":
            # Reproject elevation to a metre grid before calculating finite differences.
            from rasterio.warp import Resampling, calculate_default_transform, reproject

            affine, width, height = calculate_default_transform(
                ds.crs, "EPSG:3035", ds.width, ds.height, *ds.bounds, resolution=30
            )
            elevation = np.full((height, width), np.nan, dtype="float64")
            reproject(
                data.filled(np.nan).astype(float),
                elevation,
                src_transform=ds.transform,
                src_crs=ds.crs,
                dst_transform=affine,
                dst_crs="EPSG:3035",
                src_nodata=np.nan,
                dst_nodata=np.nan,
                resampling=Resampling.bilinear,
            )
            if min(elevation.shape) < 3:
                raise MissingData("Terrain subset needs at least three cells per axis")
            dy, dx = np.gradient(elevation, abs(affine.e), abs(affine.a))
            slope = np.degrees(np.arctan(np.hypot(dx, dy)))
            mask = geometry_mask(
                [transform_geom("EPSG:4326", "EPSG:3035", geometry)],
                slope.shape,
                affine,
                invert=True,
            )
            if not mask.any() or not np.isfinite(slope[mask]).all():
                raise MissingData("Slope is undefined at missing or edge cells")
            summary = {
                "minimum_elevation_m": float(data.data[valid].min()),
                "maximum_elevation_m": float(data.data[valid].max()),
                "median_slope_degrees": float(np.median(slope[mask])),
                "maximum_slope_degrees": float(slope[mask].max()),
                "method": "GLO-30 surface elevations → EPSG:3035 30 m bilinear grid → centred finite differences; not a ground survey",
            }
            excluded = mask & (slope > policy.maximum_slope_degrees)
            exclusion_transform, exclusion_crs = affine, "EPSG:3035"
        else:
            raise ValueError("Unknown raster assessment family")
        if family == "land":
            exclusion_transform, exclusion_crs = ds.transform, ds.crs
        polygons = [
            transform_geom(exclusion_crs, "EPSG:4326", g)
            for g, v in shapes(
                excluded.astype("uint8"), mask=excluded, transform=exclusion_transform
            )
            if v == 1
        ]
    return {
        "source_id": source_id,
        "family": family,
        "summary": summary,
        "exclusions": [
            {
                "geometry": p,
                "source_id": source_id,
                "reason": f"{family} threshold in selected screening policy",
            }
            for p in polygons
        ],
        "scope": "Raster cell coverage and threshold screen; source resolution limits parcel precision",
    }
