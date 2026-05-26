"""Per-LGU canopy aggregation: produce the canonical per-LGU CSV.

For each LGU (17 polygons from data/lgu/ncr_lgu.geojson) and each year
2019..2026, mask the binary canopy raster with the LGU polygon, sum the
canopy pixels, and compute hectares + percent of LGU area. Also pull
Hansen cumulative loss and ESA WorldCover 2021 tree percent for the same
polygons.

Output:
    data/per_lgu/per_lgu_canopy_2019_2026.csv
        columns: lgu_name, year, canopy_ha, canopy_pct, total_ha,
                 hansen_loss_ha_cumulative, esa_tree_pct_2021
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.features import geometry_mask

REPO_ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = REPO_ROOT / "data" / "composites"
HANSEN_DIR = REPO_ROOT / "data" / "hansen"
ESA_DIR = REPO_ROOT / "data" / "esa"
LGU_GEOJSON = REPO_ROOT / "data" / "lgu" / "ncr_lgu.geojson"
OUT_DIR = REPO_ROOT / "data" / "per_lgu"
OUT_CSV = OUT_DIR / "per_lgu_canopy_2019_2026.csv"

YEARS = list(range(2019, 2027))


def pixel_area_ha(transform) -> float:
    """Approximate pixel area in hectares for a rasterio Affine transform
    in EPSG:4326. At NCR latitude ~14.6, 1 deg longitude ~= 107.7 km, 1 deg
    latitude ~= 110.6 km. Pixel = transform.a x transform.e degrees."""
    lat_factor = 110.574  # km per degree latitude
    lon_factor = 111.320 * np.cos(np.radians(14.6))
    width_km = abs(transform.a) * lon_factor
    height_km = abs(transform.e) * lat_factor
    return width_km * height_km * 100.0  # km^2 to hectares (1 km^2 = 100 ha)


def aggregate_one_year(canopy_path: Path, lgus: gpd.GeoDataFrame) -> dict[str, dict]:
    """Return {lgu_name: {canopy_ha, total_ha}} for the given year's canopy raster."""
    out: dict[str, dict] = {}
    with rasterio.open(canopy_path) as src:
        canopy = src.read(1)
        transform = src.transform
        nodata = src.nodata if src.nodata is not None else 255
        height, width = canopy.shape
    pa_ha = pixel_area_ha(transform)
    for _, row in lgus.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        mask = geometry_mask(
            [geom.__geo_interface__],
            out_shape=(height, width),
            transform=transform,
            invert=True,
        )
        in_poly = canopy[mask]
        valid = in_poly != nodata
        canopy_pixels = int(np.sum((in_poly == 1) & valid))
        total_valid_pixels = int(np.sum(valid))
        out[row["lgu_name"]] = {
            "canopy_ha": round(canopy_pixels * pa_ha, 2),
            "total_ha": round(total_valid_pixels * pa_ha, 2),
        }
    return out


def hansen_loss_cumulative(lgus: gpd.GeoDataFrame, through_year: int) -> dict[str, float]:
    """Sum Hansen loss-year pixels through `through_year` (e.g. through 2024 = code 24)."""
    loss_path = HANSEN_DIR / "lossyear.tif"
    if not loss_path.exists():
        return {row["lgu_name"]: float("nan") for _, row in lgus.iterrows()}
    out: dict[str, float] = {}
    with rasterio.open(loss_path) as src:
        loss = src.read(1)
        transform = src.transform
        h, w = loss.shape
    pa_ha = pixel_area_ha(transform)
    threshold_code = max(0, through_year - 2000)  # 2025 -> code 25 (Hansen v1.13)
    for _, row in lgus.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        mask = geometry_mask(
            [geom.__geo_interface__], out_shape=(h, w), transform=transform, invert=True
        )
        in_poly = loss[mask]
        cumulative_pixels = int(np.sum((in_poly > 0) & (in_poly <= threshold_code)))
        out[row["lgu_name"]] = round(cumulative_pixels * pa_ha, 2)
    return out


def esa_tree_pct_2021(lgus: gpd.GeoDataFrame) -> dict[str, float]:
    """ESA WorldCover binary tree mask: every polygon pixel counts toward the
    denominator (0 = not-tree is valid, NOT nodata). We deliberately ignore
    src.nodata here because rasterio defaults it to 0 for binary masks, which
    collapses the non-tree class into nodata and makes every LGU read 100%.
    """
    esa_path = ESA_DIR / "worldcover_trees_2021.tif"
    if not esa_path.exists():
        return {row["lgu_name"]: float("nan") for _, row in lgus.iterrows()}
    out: dict[str, float] = {}
    with rasterio.open(esa_path) as src:
        trees = src.read(1)
        transform = src.transform
        h, w = trees.shape
    for _, row in lgus.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        mask = geometry_mask([geom.__geo_interface__], out_shape=(h, w), transform=transform, invert=True)
        in_poly = trees[mask]
        n_tree = int(np.sum(in_poly == 1))
        n_total = int(in_poly.size)
        out[row["lgu_name"]] = round(100.0 * n_tree / n_total, 2) if n_total > 0 else float("nan")
    return out


def main() -> int:
    parser = argparse.ArgumentParser(description="Per-LGU canopy aggregation 2016-2026")
    parser.add_argument("--years", nargs="+", type=int, default=YEARS)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_CSV.exists() and not args.force:
        print(f"[aggregate_lgu] {OUT_CSV.name} already exists; skip (use --force to rebuild)")
        return 0

    if not LGU_GEOJSON.exists():
        print(f"[aggregate_lgu] MISSING {LGU_GEOJSON}. Run fetch_lgu_polygons.py first.", file=sys.stderr)
        return 1

    lgus = gpd.read_file(LGU_GEOJSON)
    if "lgu_name" not in lgus.columns:
        print("[aggregate_lgu] LGU GeoJSON has no `lgu_name` property", file=sys.stderr)
        return 1
    print(f"[aggregate_lgu] {len(lgus)} LGUs loaded from {LGU_GEOJSON.name}")

    # Compute static columns (Hansen cumulative loss + ESA 2021 tree %).
    esa_pct = esa_tree_pct_2021(lgus)

    rows: list[dict] = []
    for year in args.years:
        canopy_path = COMP_DIR / f"canopy_{year}.tif"
        if not canopy_path.exists():
            print(f"[aggregate_lgu] {year}: MISSING {canopy_path.name}; skip")
            continue
        per_lgu = aggregate_one_year(canopy_path, lgus)
        hansen = hansen_loss_cumulative(lgus, through_year=min(year, 2025))
        for lgu_name, stats in per_lgu.items():
            canopy_ha = stats["canopy_ha"]
            total_ha = stats["total_ha"]
            canopy_pct = round(100.0 * canopy_ha / total_ha, 2) if total_ha > 0 else 0.0
            rows.append(
                {
                    "lgu_name": lgu_name,
                    "year": year,
                    "canopy_ha": canopy_ha,
                    "canopy_pct": canopy_pct,
                    "total_ha": total_ha,
                    "hansen_loss_ha_cumulative": hansen.get(lgu_name, ""),
                    "esa_tree_pct_2021": esa_pct.get(lgu_name, ""),
                }
            )
        print(f"[aggregate_lgu] {year}: {len(per_lgu)} LGUs aggregated")

    if not rows:
        print("[aggregate_lgu] FAIL: no rows produced; check that data/composites/canopy_*.tif exists", file=sys.stderr)
        return 1

    rows.sort(key=lambda r: (r["lgu_name"], r["year"]))
    with OUT_CSV.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"[aggregate_lgu] wrote {len(rows)} rows -> {OUT_CSV.relative_to(REPO_ROOT)}")
    # Manifest with per-LGU per-year canopy summary for the methodology footnote.
    summary = {}
    for r in rows:
        summary.setdefault(r["lgu_name"], {})[r["year"]] = r["canopy_pct"]
    (OUT_DIR / "_aggregate_manifest.json").write_text(json.dumps(summary, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
