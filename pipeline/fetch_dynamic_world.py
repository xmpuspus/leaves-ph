"""Fetch Dynamic World v1 annual median 'trees' probability per year 2016..2026.

For each year, compute median of the `trees` band (class 1) across all
Sentinel-2-derived classifications. Output: single-band float raster at
**30 m** (downsampled from Dynamic World's native 10 m to match Hansen's
30 m grid and share the GEE 50 MB sync-URL limit with Sentinel-2; rationale
in fetch_sentinel2_yearly.py).

Idempotent.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _gee_init import NCR_BBOX, NCR_YEARS, init, ncr_geometry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "composites"
MANIFEST = OUT_DIR / "_fetch_manifest_dw.json"


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Fetch Dynamic World v1 annual median tree probability for NCR"
    )
    parser.add_argument("--years", nargs="+", type=int, default=list(NCR_YEARS))
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init()
    import ee  # noqa: PLC0415
    import geemap  # noqa: PLC0415

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    geom = ncr_geometry()

    manifest: dict[str, dict] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())

    for year in args.years:
        out_path = OUT_DIR / f"dw_trees_{year}.tif"
        if out_path.exists() and not args.force:
            print(f"[fetch_dw] {year}: {out_path.name} already exists; skip")
            continue

        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"
        dw = (
            ee.ImageCollection("GOOGLE/DYNAMICWORLD/V1")
            .filterBounds(geom)
            .filterDate(start, end)
            .select("trees")
        )
        n = dw.size().getInfo()
        if n == 0:
            print(f"[fetch_dw] {year}: NO IMAGES in date window; skip")
            continue

        composite = dw.median().clip(geom).rename("tree_prob")
        print(f"[fetch_dw] {year}: {n} images, exporting -> {out_path.name}")
        geemap.ee_export_image(
            composite,
            filename=str(out_path),
            scale=30,
            region=geom,
            file_per_band=False,
        )

        manifest[str(year)] = {
            "n_source_images": n,
            "scale_m": 30,
            "bbox": list(NCR_BBOX),
            "start": start,
            "end": end,
            "ee_collection": "GOOGLE/DYNAMICWORLD/V1",
            "band": "trees",
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[fetch_dw] DONE. Manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
