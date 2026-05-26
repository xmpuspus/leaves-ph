"""Fetch Hansen Global Forest Change v1.12 layers cropped to the NCR bbox.

Exports three bands as separate GeoTIFFs:
    data/hansen/treecover2000.tif   year-2000 percent canopy
    data/hansen/lossyear.tif         year of forest loss (1-24 = 2001-2024)
    data/hansen/gain.tif             binary forest gain 2000-2012

Idempotent.

Default GEE asset: UMD/hansen/global_forest_change_2024_v1_12.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _gee_init import NCR_BBOX, init, ncr_geometry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "hansen"
MANIFEST = OUT_DIR / "_fetch_manifest_hansen.json"
DEFAULT_ASSET = "UMD/hansen/global_forest_change_2024_v1_12"
BANDS = ("treecover2000", "lossyear", "gain")


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Hansen GFC for NCR")
    parser.add_argument("--asset", default=DEFAULT_ASSET)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    init()
    import ee  # noqa: PLC0415
    import geemap  # noqa: PLC0415

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    geom = ncr_geometry()

    gfc = ee.Image(args.asset).clip(geom)

    for band in BANDS:
        out_path = OUT_DIR / f"{band}.tif"
        if out_path.exists() and not args.force:
            print(f"[fetch_hansen] {band}: {out_path.name} already exists; skip")
            continue
        print(f"[fetch_hansen] exporting {band} -> {out_path.name}")
        geemap.ee_export_image(
            gfc.select(band),
            filename=str(out_path),
            scale=30,
            region=geom,
            file_per_band=False,
        )

    MANIFEST.write_text(
        json.dumps(
            {"asset": args.asset, "bbox": list(NCR_BBOX), "bands": list(BANDS)},
            indent=2,
            sort_keys=True,
        )
    )
    print(f"[fetch_hansen] DONE. Manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
