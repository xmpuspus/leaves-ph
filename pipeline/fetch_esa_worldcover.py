"""Fetch ESA WorldCover v200 (2021) cropped to NCR. Single-year cross-check.

Output:
    data/esa/worldcover_2021.tif       full 11-class raster
    data/esa/worldcover_trees_2021.tif binary mask (class 10 = trees)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _gee_init import NCR_BBOX, init, ncr_geometry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "esa"
MANIFEST = OUT_DIR / "_fetch_manifest_esa.json"
TREE_CLASS = 10


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch ESA WorldCover v200 (2021) for NCR")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init()
    import ee
    import geemap

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    geom = ncr_geometry()

    wc = ee.ImageCollection("ESA/WorldCover/v200").first().clip(geom)

    full_path = OUT_DIR / "worldcover_2021.tif"
    trees_path = OUT_DIR / "worldcover_trees_2021.tif"

    if not full_path.exists() or args.force:
        print(f"[fetch_esa] exporting full WorldCover -> {full_path.name}")
        geemap.ee_export_image(wc, filename=str(full_path), scale=10, region=geom, file_per_band=False)
    else:
        print(f"[fetch_esa] {full_path.name} already exists; skip")

    if not trees_path.exists() or args.force:
        trees_mask = wc.eq(TREE_CLASS).rename("trees")
        print(f"[fetch_esa] exporting binary tree mask -> {trees_path.name}")
        geemap.ee_export_image(
            trees_mask, filename=str(trees_path), scale=10, region=geom, file_per_band=False
        )
    else:
        print(f"[fetch_esa] {trees_path.name} already exists; skip")

    MANIFEST.write_text(
        json.dumps(
            {
                "asset": "ESA/WorldCover/v200",
                "year": 2021,
                "bbox": list(NCR_BBOX),
                "tree_class": TREE_CLASS,
            },
            indent=2,
            sort_keys=True,
        )
    )
    print(f"[fetch_esa] DONE. Manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
