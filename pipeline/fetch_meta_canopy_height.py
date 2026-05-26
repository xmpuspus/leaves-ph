"""Fetch Meta Global Canopy Height v2 for NCR from AWS Open Data S3.

Bucket: dataforgood-fb-data
Prefix: forests/v1/alsgedi_global_v6_float/chm/
Naming: per-tile canopy height GeoTIFFs at Bing-style Mercator quadkey
        zoom 9 (9-digit base-4 strings). E.g. NCR is covered by
        132303031, 132303120, 132303033, 132303122.

Tile facts (probed live 2026-05-26):
- CRS:        EPSG:3857 (Web Mercator), NOT 4326
- Datatype:   uint8 (height in meters; 0..255)
- Resolution: ~1.19 m
- Shape:      65536 x 65536 per tile
- Layout:     strip TIFF, single-row strips (not COG, no overviews)

Because the tiles are strip-organized rather than COG-tiled, /vsicurl/ window
reads would still pull most of each tile (every strip overlapping the NCR
row range). It is faster and more memory-safe to download the 4 overlapping
tiles whole (~500 MB each, ~2.3 GB total), mosaic with bounds set to NCR in
EPSG:3857, reproject to EPSG:4326, and delete the temporary files.

Output:
    data/meta/canopy_height_ncr.tif       EPSG:4326, NCR-clipped (~10-50 MB)
    data/meta/_fetch_manifest_meta.json
"""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import math
import shutil
import sys
import tempfile
import time
import urllib.request
from pathlib import Path

from _gee_init import NCR_BBOX

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "meta"
MANIFEST = OUT_DIR / "_fetch_manifest_meta.json"

BUCKET = "dataforgood-fb-data"
PREFIX = "forests/v1/alsgedi_global_v6_float/chm/"
META_ZOOM = 9
TILE_HOST = f"https://{BUCKET}.s3.amazonaws.com/{PREFIX}"


def latlon_to_quadkey(lat: float, lon: float, zoom: int) -> str:
    sin_lat = math.sin(lat * math.pi / 180.0)
    pixel_x = (lon + 180) / 360 * (256 << zoom)
    pixel_y = (0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)) * (256 << zoom)
    tile_x = int(pixel_x / 256)
    tile_y = int(pixel_y / 256)
    qk = ""
    for i in range(zoom, 0, -1):
        digit = 0
        mask = 1 << (i - 1)
        if tile_x & mask:
            digit += 1
        if tile_y & mask:
            digit += 2
        qk += str(digit)
    return qk


def overlapping_quadkeys(bbox: tuple[float, float, float, float], zoom: int = META_ZOOM) -> list[str]:
    """Distinct quadkeys overlapping the bbox. Probe 4 corners + center."""
    min_lon, min_lat, max_lon, max_lat = bbox
    probes = [
        (max_lat, min_lon),
        (max_lat, max_lon),
        (min_lat, min_lon),
        (min_lat, max_lon),
        ((min_lat + max_lat) / 2, (min_lon + max_lon) / 2),
    ]
    seen: dict[str, None] = {}
    for lat, lon in probes:
        seen[latlon_to_quadkey(lat, lon, zoom)] = None
    return list(seen)


def download_tile(qk: str, out_path: Path) -> tuple[str, int, float]:
    """Download one Meta tile from S3 anonymous. Returns (qk, bytes, seconds)."""
    url = f"{TILE_HOST}{qk}.tif"
    t0 = time.time()
    with urllib.request.urlopen(url, timeout=120) as resp, open(out_path, "wb") as f:
        total = 0
        while True:
            chunk = resp.read(2 * 1024 * 1024)
            if not chunk:
                break
            f.write(chunk)
            total += len(chunk)
    return qk, total, time.time() - t0


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Meta canopy height for NCR")
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--keep-tiles",
        action="store_true",
        help="Keep the downloaded full tiles (default: delete after mosaic)",
    )
    parser.add_argument(
        "--max-parallel", type=int, default=4, help="Parallel tile downloads (default 4)"
    )
    args = parser.parse_args()

    import numpy as np  # noqa: PLC0415
    import rasterio  # noqa: PLC0415
    from rasterio.merge import merge  # noqa: PLC0415
    from rasterio.warp import Resampling, calculate_default_transform, reproject  # noqa: PLC0415
    from rasterio.warp import transform_bounds  # noqa: PLC0415

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    merged_path = OUT_DIR / "canopy_height_ncr.tif"
    if merged_path.exists() and not args.force:
        print(f"[fetch_meta] {merged_path.name} already exists; skip (use --force)")
        return 0

    quadkeys = overlapping_quadkeys(NCR_BBOX, META_ZOOM)
    print(f"[fetch_meta] NCR overlaps {len(quadkeys)} zoom-9 Meta tile(s): {quadkeys}")
    print(f"[fetch_meta] downloading {len(quadkeys)} tile(s) in parallel (up to ~600 MB each)")

    tile_dir = Path(tempfile.mkdtemp(prefix="meta-tiles-", dir=str(OUT_DIR)))
    tile_paths: dict[str, Path] = {qk: tile_dir / f"{qk}.tif" for qk in quadkeys}
    downloaded: list[dict] = []

    try:
        with concurrent.futures.ThreadPoolExecutor(max_workers=args.max_parallel) as ex:
            futures = {ex.submit(download_tile, qk, p): qk for qk, p in tile_paths.items()}
            for f in concurrent.futures.as_completed(futures):
                qk = futures[f]
                try:
                    qk_done, total_bytes, secs = f.result()
                    mb = total_bytes / 1_000_000
                    rate = mb / max(secs, 0.001)
                    print(f"[fetch_meta]   tile {qk_done}: {mb:.0f} MB in {secs:.1f}s ({rate:.1f} MB/s)")
                    downloaded.append(
                        {"quadkey": qk_done, "size_mb": round(mb, 1), "download_s": round(secs, 1)}
                    )
                except Exception as e:  # noqa: BLE001
                    print(f"[fetch_meta]   tile {qk}: FAILED {e}", file=sys.stderr)

        if not downloaded:
            print("[fetch_meta] FAIL: no tiles downloaded", file=sys.stderr)
            return 1

        # Open all downloaded tiles, mosaic in EPSG:3857 with bounds = NCR
        # converted to Web Mercator.
        srcs = [rasterio.open(tile_paths[d["quadkey"]]) for d in downloaded]
        src_crs = srcs[0].crs
        ncr_3857 = transform_bounds("EPSG:4326", src_crs, *NCR_BBOX, densify_pts=21)
        print(f"[fetch_meta] mosaicking {len(srcs)} tile(s) in EPSG:3857 over bounds {ncr_3857}")
        try:
            mosaic, mosaic_transform = merge(srcs, bounds=ncr_3857)
            mosaic_profile = srcs[0].profile.copy()
            mosaic_profile.update(
                {
                    "height": mosaic.shape[1],
                    "width": mosaic.shape[2],
                    "transform": mosaic_transform,
                    "crs": src_crs,
                }
            )
            print(
                f"[fetch_meta]   mosaic shape {mosaic.shape[2]}x{mosaic.shape[1]} "
                f"{mosaic_profile['dtype']} (~{mosaic.nbytes // 1_000_000} MB in RAM)"
            )
        finally:
            for s in srcs:
                s.close()

        # Reproject NCR mosaic 3857 -> 4326 to match the other layers.
        dst_transform, dst_w, dst_h = calculate_default_transform(
            src_crs,
            "EPSG:4326",
            mosaic.shape[2],
            mosaic.shape[1],
            *rasterio.transform.array_bounds(mosaic.shape[1], mosaic.shape[2], mosaic_transform),
        )
        dst = np.zeros((dst_h, dst_w), dtype=mosaic_profile["dtype"])
        reproject(
            source=mosaic[0],
            destination=dst,
            src_transform=mosaic_transform,
            src_crs=src_crs,
            dst_transform=dst_transform,
            dst_crs="EPSG:4326",
            resampling=Resampling.average,
        )
        out_profile = {
            "driver": "GTiff",
            "height": dst_h,
            "width": dst_w,
            "count": 1,
            "dtype": str(dst.dtype),
            "crs": "EPSG:4326",
            "transform": dst_transform,
            "compress": "deflate",
            "predictor": 2,
            "nodata": 255,
        }
        with rasterio.open(merged_path, "w", **out_profile) as out:
            out.write(dst, 1)
        size_mb = merged_path.stat().st_size / 1_000_000
        print(
            f"[fetch_meta] wrote {merged_path.name}  {dst_w}x{dst_h} {dst.dtype} "
            f"EPSG:4326 ({size_mb:.1f} MB)"
        )
    finally:
        if not args.keep_tiles:
            shutil.rmtree(tile_dir, ignore_errors=True)
            print(f"[fetch_meta] cleaned up temp tile dir {tile_dir.name}")
        else:
            print(f"[fetch_meta] kept temp tiles at {tile_dir}")

    MANIFEST.write_text(
        json.dumps(
            {
                "bucket": BUCKET,
                "prefix": PREFIX,
                "zoom": META_ZOOM,
                "bbox": list(NCR_BBOX),
                "tiles": downloaded,
                "mosaic": merged_path.name,
                "mosaic_size_mb": round(size_mb, 1),
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"[fetch_meta] DONE. Manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
