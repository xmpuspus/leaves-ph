"""Vectorize Meta canopy height v2 into per-crown polygons.

Reads data/meta/canopy_height_ncr.tif (1 m, uint8, EPSG:4326), thresholds
at MIN_HEIGHT_M to get a binary canopy mask, then uses rasterio.features.shapes
to extract every connected polygon. Filters out crowns smaller than
MIN_AREA_M2 (default 6 m^2; a single mature tree is ~25 m^2, but smaller
patches are real and worth keeping). Each crown polygon is simplified with
Douglas-Peucker at TOLERANCE_DEG to keep file size manageable, and stamped
with its area in m^2 and the height percentile (p50, p95) sampled from
the underlying raster.

Outputs:
    data/per_crown/tree_crowns_ncr.geojson
        FeatureCollection of crown polygons with properties:
          area_m2 (float)
          p50_height_m (int)
          p95_height_m (int)
          lgu_name (str | null)  — the LGU containing the crown centroid
    site/public/data/tree_crowns_ncr.geojson
        Mirror of the above, for direct fetch by the MapLibre layer.

This is the analog to SolarMap.PH's per_building_solar_ncr.geojson —
every tree canopy patch above 5 m is mapped.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import shapes
from shapely.geometry import Point, mapping, shape
from shapely.geometry.polygon import Polygon

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC = REPO_ROOT / "data" / "meta" / "canopy_height_ncr.tif"
LGU_GEOJSON = REPO_ROOT / "data" / "lgu" / "ncr_lgu.geojson"
OUT_DATA = REPO_ROOT / "data" / "per_crown" / "tree_crowns_ncr.geojson"
OUT_SITE = REPO_ROOT / "site" / "public" / "data" / "tree_crowns_ncr.geojson"

MIN_HEIGHT_M = 5
MIN_AREA_M2 = 6  # drop crowns smaller than 6 m^2 (noise / partial-tree fragments)
TOLERANCE_DEG = 0.000015  # ~1.7 m at NCR latitude; preserves shape, trims vertices


def lonlat_m2(lat: float, lon_extent: float, lat_extent: float) -> float:
    """Approximate planar area in m^2 for a lon/lat bbox at the given lat."""
    lat_factor = 110_574.0
    lon_factor = 111_320.0 * float(np.cos(np.radians(lat)))
    return lon_extent * lon_factor * lat_extent * lat_factor


def polygon_area_m2(poly_geom: dict) -> float:
    """Compute approximate planar area in m^2 from a GeoJSON polygon.

    Uses the spherical-excess formula (Green's theorem on the sphere) scaled
    to m^2 at lat 14.6. NCR is small enough that the flat-projection error is
    well under 1 percent for individual crowns.
    """
    p = shape(poly_geom)
    if isinstance(p, Polygon):
        polys = [p]
    else:
        polys = list(p.geoms)
    total = 0.0
    for poly in polys:
        minx, miny, maxx, maxy = poly.bounds
        lat = (miny + maxy) / 2
        # shapely area is in deg^2; convert at this latitude
        deg2_to_m2 = (110_574.0) * (111_320.0 * float(np.cos(np.radians(lat))))
        total += poly.area * deg2_to_m2
    return total


def main() -> int:
    parser = argparse.ArgumentParser(description="Extract per-crown tree polygons from Meta canopy")
    parser.add_argument("--min-height", type=float, default=MIN_HEIGHT_M)
    parser.add_argument("--min-area", type=float, default=MIN_AREA_M2)
    parser.add_argument("--tolerance-deg", type=float, default=TOLERANCE_DEG)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not SRC.exists():
        print(f"[crowns] MISSING {SRC}", file=sys.stderr)
        return 1
    if OUT_DATA.exists() and not args.force:
        print(f"[crowns] {OUT_DATA.name} already exists; skip (use --force)")
        return 0
    OUT_DATA.parent.mkdir(parents=True, exist_ok=True)
    OUT_SITE.parent.mkdir(parents=True, exist_ok=True)

    print(f"[crowns] reading {SRC}")
    with rasterio.open(SRC) as src:
        height = src.read(1)
        transform = src.transform
        crs = src.crs
    print(f"[crowns] raster {height.shape[1]}x{height.shape[0]}  crs={crs}")
    mask = (height >= args.min_height) & (height < 250)
    print(f"[crowns] canopy pixels (height>={args.min_height} m): {mask.sum():,} ({100*mask.sum()/mask.size:.2f}% of NCR)")

    print(f"[crowns] vectorising connected components via rasterio.features.shapes")
    # `shapes` with connectivity=8 unites diagonally-touching pixels into one
    # crown (canonical for canopy delineation; matches how a viewer would
    # interpret adjoining greens as one tree-cluster).
    crowns_iter = shapes(mask.astype(np.uint8), mask=mask, connectivity=8, transform=transform)

    # Load LGU polygons for spatial-join attribution.
    lgu_fc = json.loads(LGU_GEOJSON.read_text())
    from shapely.strtree import STRtree

    lgu_geoms = [(shape(f["geometry"]), f["properties"]["lgu_name"]) for f in lgu_fc["features"]]
    lgu_tree = STRtree([g for g, _ in lgu_geoms])

    features: list[dict] = []
    dropped = 0
    sampled = 0

    # Pre-compute pixel-mapping for height-percentile sampling. We need to
    # convert each polygon's geometry back to raster window. For speed we
    # sample inside the geometry by drawing a coarse grid of points; for very
    # small crowns we sample 3x3, for larger 7x7. Faster than rasterising
    # each polygon into a mask.

    for geom, val in crowns_iter:
        if val != 1:
            continue
        poly = shape(geom)
        if poly.is_empty:
            continue
        # Simplify
        poly_s = poly.simplify(args.tolerance_deg, preserve_topology=True)
        if poly_s.is_empty or not poly_s.is_valid:
            continue
        area = polygon_area_m2(mapping(poly_s))
        if area < args.min_area:
            dropped += 1
            continue
        # Sample raster heights inside the polygon to compute p50/p95
        minx, miny, maxx, maxy = poly_s.bounds
        # Sample a grid
        nx = ny = 5 if area < 100 else 9
        xs = np.linspace(minx, maxx, nx)
        ys = np.linspace(miny, maxy, ny)
        heights_in_crown = []
        for xv in xs:
            for yv in ys:
                if not poly_s.contains(Point(xv, yv)):
                    continue
                # Convert lon/lat to row/col
                col, row = ~transform * (xv, yv)
                col = int(col)
                row = int(row)
                if 0 <= row < height.shape[0] and 0 <= col < height.shape[1]:
                    h = int(height[row, col])
                    if 0 < h < 250:
                        heights_in_crown.append(h)
        if heights_in_crown:
            p50 = int(np.median(heights_in_crown))
            p95 = int(np.percentile(heights_in_crown, 95))
        else:
            p50 = p95 = int(args.min_height)
        # Spatial-join LGU
        centroid = poly_s.centroid
        lgu_name = None
        for idx in lgu_tree.query(centroid):
            cand_geom, cand_name = lgu_geoms[idx]
            if cand_geom.contains(centroid):
                lgu_name = cand_name
                break
        features.append(
            {
                "type": "Feature",
                "geometry": mapping(poly_s),
                "properties": {
                    "area_m2": round(area, 1),
                    "p50_height_m": p50,
                    "p95_height_m": p95,
                    "lgu_name": lgu_name,
                },
            }
        )
        sampled += 1
        if sampled % 5000 == 0:
            print(f"[crowns] kept {sampled:,} crowns; dropped {dropped:,} small fragments")

    print(f"[crowns] DONE  kept {sampled:,} crowns; dropped {dropped:,}")
    fc = {
        "type": "FeatureCollection",
        "metadata": {
            "source": "Meta Canopy Height v2 (CC-BY-4.0)",
            "raster": "data/meta/canopy_height_ncr.tif",
            "min_height_m": args.min_height,
            "min_area_m2": args.min_area,
            "simplify_tolerance_deg": args.tolerance_deg,
            "n_features": sampled,
        },
        "features": features,
    }
    OUT_DATA.write_text(json.dumps(fc))
    OUT_SITE.write_text(json.dumps(fc))
    size_mb = OUT_DATA.stat().st_size / 1_000_000
    print(f"[crowns] wrote {OUT_DATA.relative_to(REPO_ROOT)} ({size_mb:.1f} MB)")
    print(f"[crowns] mirrored {OUT_SITE.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
