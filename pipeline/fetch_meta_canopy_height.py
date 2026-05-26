"""Fetch Meta Global Canopy Height v2 tiles overlapping NCR from AWS Open Data.

Bucket: dataforgood-fb-data, prefix: forests/v1/alsgedi_global_v6_float/
Anonymous S3 access (no AWS account required).

Output:
    data/meta/<tile>.tif              per overlapping tile (raw from S3)
    data/meta/canopy_height_ncr.tif   cropped to NCR bbox

Tiles are 3 deg x 3 deg. NCR (14.4N to 14.8N, 120.9E to 121.15E) typically
overlaps a single tile but we compute the overlap explicitly.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
import urllib.error
import urllib.request
from pathlib import Path

from _gee_init import NCR_BBOX

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "meta"
MANIFEST = OUT_DIR / "_fetch_manifest_meta.json"

BUCKET = "dataforgood-fb-data"
PREFIX = "forests/v1/alsgedi_global_v6_float/"
TILE_SIZE_DEG = 3


def overlapping_tiles(bbox: tuple[float, float, float, float]) -> list[tuple[int, int]]:
    """Tile lower-left corners (lat, lon) overlapping the bbox."""
    min_lon, min_lat, max_lon, max_lat = bbox
    lat_min = math.floor(min_lat / TILE_SIZE_DEG) * TILE_SIZE_DEG
    lat_max = math.floor(max_lat / TILE_SIZE_DEG) * TILE_SIZE_DEG
    lon_min = math.floor(min_lon / TILE_SIZE_DEG) * TILE_SIZE_DEG
    lon_max = math.floor(max_lon / TILE_SIZE_DEG) * TILE_SIZE_DEG
    out: list[tuple[int, int]] = []
    for lat in range(lat_min, lat_max + 1, TILE_SIZE_DEG):
        for lon in range(lon_min, lon_max + 1, TILE_SIZE_DEG):
            out.append((lat, lon))
    return out


def tile_url(lat: int, lon: int) -> str:
    lat_str = f"{abs(lat):02d}{'N' if lat >= 0 else 'S'}"
    lon_str = f"{abs(lon):03d}{'E' if lon >= 0 else 'W'}"
    return f"https://{BUCKET}.s3.amazonaws.com/{PREFIX}{lat_str}_{lon_str}.tif"


def fetch_tile(url: str, out_path: Path) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=60) as resp, open(out_path, "wb") as f:
            while True:
                chunk = resp.read(1024 * 1024)
                if not chunk:
                    break
                f.write(chunk)
        return True
    except urllib.error.HTTPError as e:
        print(f"[fetch_meta] HTTP {e.code} for {url}", file=sys.stderr)
        return False
    except urllib.error.URLError as e:
        print(f"[fetch_meta] URL error for {url}: {e.reason}", file=sys.stderr)
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Meta canopy height for NCR")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)

    tiles = overlapping_tiles(NCR_BBOX)
    print(f"[fetch_meta] NCR bbox overlaps {len(tiles)} Meta tile(s): {tiles}")

    fetched: list[str] = []
    for lat, lon in tiles:
        url = tile_url(lat, lon)
        out_path = OUT_DIR / Path(url).name
        if out_path.exists() and not args.force:
            print(f"[fetch_meta] {out_path.name} already exists; skip")
            fetched.append(out_path.name)
            continue
        print(f"[fetch_meta] downloading {url}")
        if fetch_tile(url, out_path):
            print(f"[fetch_meta] saved -> {out_path.name} ({out_path.stat().st_size // 1024} KB)")
            fetched.append(out_path.name)
        else:
            print(
                "[fetch_meta] FAIL: tile naming may differ from this script's guess. "
                "Read the AWS Open Data index file (alsgedi_global_v6_float/) to confirm "
                "the actual tile filename convention.",
                file=sys.stderr,
            )

    merged_path = OUT_DIR / "canopy_height_ncr.tif"
    if len(fetched) == 1:
        try:
            import rasterio  # noqa: PLC0415
            from rasterio.windows import from_bounds, transform as window_transform  # noqa: PLC0415

            src_path = OUT_DIR / fetched[0]
            with rasterio.open(src_path) as src:
                window = from_bounds(*NCR_BBOX, transform=src.transform)
                data = src.read(1, window=window)
                profile = src.profile.copy()
                profile.update(
                    {
                        "height": data.shape[0],
                        "width": data.shape[1],
                        "transform": window_transform(window, src.transform),
                    }
                )
                with rasterio.open(merged_path, "w", **profile) as dst:
                    dst.write(data, 1)
            print(f"[fetch_meta] cropped to NCR -> {merged_path.name}")
        except Exception as e:  # noqa: BLE001
            print(f"[fetch_meta] cropping skipped ({e}); use the per-tile file directly", file=sys.stderr)
    elif len(fetched) > 1:
        print(f"[fetch_meta] {len(fetched)} tiles fetched; mosaic step TBD")

    MANIFEST.write_text(
        json.dumps(
            {
                "bucket": BUCKET,
                "prefix": PREFIX,
                "tiles": fetched,
                "bbox": list(NCR_BBOX),
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"[fetch_meta] DONE. Manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
