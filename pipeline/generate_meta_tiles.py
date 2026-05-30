"""Generate XYZ raster tile pyramid from Meta canopy height v2 for the map.

Output is a per-zoom directory of 256x256 PNG tiles under
site/public/tiles/meta/{z}/{x}/{y}.png. Each tile contains a transparent
PNG where pixels with canopy height >= MIN_HEIGHT_M are painted
forest-green (#2d5a3d) at the specified alpha, transparent elsewhere.

This is the granular layer that gives the map "actual tree cover" detail
instead of just the LGU polygon choropleth.

Zoom range default 11..14 (around 6000 tiles, ~30-60 MB on disk).
Higher zooms are not generated to keep the site bundle reasonable.
"""

from __future__ import annotations

import argparse
import math
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image
from rasterio.warp import Resampling, reproject

REPO_ROOT = Path(__file__).resolve().parent.parent
SRC_PATH = REPO_ROOT / "data" / "meta" / "canopy_height_ncr.tif"
OUT_DIR = REPO_ROOT / "site" / "public" / "tiles" / "meta"

TILE_SIZE = 256
MIN_HEIGHT_M = 5  # any pixel with Meta canopy >= 5 m counts as tree cover
RGBA_GREEN = (45, 90, 61, 220)  # #2d5a3d at ~86% alpha


def tile_to_lonlat(x: int, y: int, z: int) -> tuple[float, float]:
    n = 2**z
    lon = x / n * 360 - 180
    lat = math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * y / n))))
    return lon, lat


def tile_bounds_lonlat(x: int, y: int, z: int) -> tuple[float, float, float, float]:
    """Bounds of XYZ tile in lon/lat (min_lon, min_lat, max_lon, max_lat)."""
    min_lon, max_lat = tile_to_lonlat(x, y, z)
    max_lon, min_lat = tile_to_lonlat(x + 1, y + 1, z)
    return min_lon, min_lat, max_lon, max_lat


def lonlat_to_tile(lon: float, lat: float, z: int) -> tuple[int, int]:
    n = 2**z
    x = int((lon + 180.0) / 360.0 * n)
    lat_rad = math.radians(lat)
    y = int((1.0 - math.asinh(math.tan(lat_rad)) / math.pi) / 2.0 * n)
    return x, y


def tiles_for_bbox(bbox, z: int) -> list[tuple[int, int]]:
    min_lon, min_lat, max_lon, max_lat = bbox
    x0, y0 = lonlat_to_tile(min_lon, max_lat, z)
    x1, y1 = lonlat_to_tile(max_lon, min_lat, z)
    return [(x, y) for x in range(min(x0, x1), max(x0, x1) + 1) for y in range(min(y0, y1), max(y0, y1) + 1)]


def render_tile(
    src_data: np.ndarray,
    src_transform,
    src_crs,
    z: int,
    x: int,
    y: int,
    out_path: Path,
) -> None:
    """Reproject a tile-sized window from EPSG:4326 source onto Web Mercator XYZ tile.

    The source raster is already EPSG:4326 (Meta v2). The XYZ tile is Web
    Mercator (EPSG:3857) at TILE_SIZE px. rasterio.warp.reproject handles
    the transform; we then threshold canopy >= MIN_HEIGHT_M and write a
    transparent PNG with the green pixels.
    """
    min_lon, min_lat, max_lon, max_lat = tile_bounds_lonlat(x, y, z)
    # Compute the destination affine in Web Mercator pixel space.
    # rasterio.warp.reproject can go EPSG:4326 -> EPSG:3857 with an explicit
    # destination transform sized to TILE_SIZE x TILE_SIZE.
    from rasterio.transform import from_bounds
    from rasterio.warp import transform_bounds

    dst_bounds_3857 = transform_bounds(
        "EPSG:4326", "EPSG:3857", min_lon, min_lat, max_lon, max_lat, densify_pts=21
    )
    dst_transform = from_bounds(*dst_bounds_3857, TILE_SIZE, TILE_SIZE)
    dst = np.zeros((TILE_SIZE, TILE_SIZE), dtype=src_data.dtype)
    reproject(
        source=src_data,
        destination=dst,
        src_transform=src_transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs="EPSG:3857",
        resampling=Resampling.average,
    )
    # Threshold: canopy >= MIN_HEIGHT_M
    mask = (dst >= MIN_HEIGHT_M) & (dst < 250)
    if not mask.any():
        # No canopy in this tile; skip writing entirely.
        return
    rgba = np.zeros((TILE_SIZE, TILE_SIZE, 4), dtype=np.uint8)
    rgba[mask] = RGBA_GREEN
    out_path.parent.mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgba, mode="RGBA").save(str(out_path), optimize=True)


def worker(args):
    z, x, y, out_dir, src_path = args
    with rasterio.open(src_path) as src:
        a = src.read(1)
        t = src.transform
        crs = src.crs
    out_path = out_dir / str(z) / str(x) / f"{y}.png"
    if out_path.exists():
        return False  # skipped
    render_tile(a, t, crs, z, x, y, out_path)
    return out_path.exists()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate XYZ tile pyramid from Meta canopy height for NCR")
    parser.add_argument("--zoom-min", type=int, default=11)
    parser.add_argument("--zoom-max", type=int, default=14)
    parser.add_argument("--processes", type=int, default=4)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not SRC_PATH.exists():
        print(f"[meta-tiles] MISSING {SRC_PATH}", file=sys.stderr)
        return 1

    with rasterio.open(SRC_PATH) as src:
        bbox = (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)
    print(f"[meta-tiles] source bbox: {bbox}")

    if args.force:
        import shutil

        if OUT_DIR.exists():
            shutil.rmtree(OUT_DIR)
            print(f"[meta-tiles] cleared {OUT_DIR}")

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    all_tasks: list[tuple] = []
    for z in range(args.zoom_min, args.zoom_max + 1):
        for x, y in tiles_for_bbox(bbox, z):
            all_tasks.append((z, x, y, OUT_DIR, str(SRC_PATH)))
    print(f"[meta-tiles] {len(all_tasks)} tile candidates across z={args.zoom_min}..{args.zoom_max}")

    written = 0
    skipped = 0
    with ProcessPoolExecutor(max_workers=args.processes) as ex:
        futures = {ex.submit(worker, t): t for t in all_tasks}
        for i, fut in enumerate(as_completed(futures)):
            if fut.result():
                written += 1
            else:
                skipped += 1
            if (i + 1) % 200 == 0:
                print(
                    f"[meta-tiles] progress: {i + 1}/{len(all_tasks)}  written={written} skipped/empty={skipped}"
                )

    # Disk usage report
    total_bytes = sum(p.stat().st_size for p in OUT_DIR.rglob("*.png"))
    print(f"[meta-tiles] DONE  {written} tiles written  ({total_bytes / 1_000_000:.1f} MB on disk)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
