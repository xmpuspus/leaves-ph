"""Fetch Sentinel-2 RGB (B4 + B3 + B2) yearly median composites for NCR.

Separate from fetch_sentinel2_yearly.py (which fetches red + nir for NDVI).
This script pulls red + green + blue at 30 m so we have true-color basemap
imagery for the GhostWatch-style animation (real satellite imagery, time-
varying year by year).

Output:
    data/composites/s2_rgb_<year>.tif   for year in 2019..2026

Color scaling: Sentinel-2 SR values are 0..10000 (scaled reflectance).
For visualisation we stretch p2-p98 per band, normalize to 0..255 uint8.
This is done at render time, not at fetch time, so the raw reflectance
values stay archived.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _gee_init import NCR_BBOX, NCR_YEARS, init, ncr_geometry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "composites"
MANIFEST = OUT_DIR / "_fetch_manifest_s2_rgb.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Sentinel-2 RGB yearly composites for NCR")
    parser.add_argument("--years", nargs="+", type=int, default=list(NCR_YEARS))
    parser.add_argument("--force", action="store_true")
    parser.add_argument(
        "--cloud-prob", type=int, default=30, help="s2cloudless cutoff (stricter than NDVI fetch)"
    )
    args = parser.parse_args()

    init()
    import ee
    import geemap

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    geom = ncr_geometry()

    manifest: dict[str, dict] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())

    for year in args.years:
        out_path = OUT_DIR / f"s2_rgb_{year}.tif"
        if out_path.exists() and not args.force:
            print(f"[fetch_s2_rgb] {year}: {out_path.name} already exists; skip")
            continue

        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"

        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 60))
        )
        s2_cloud_prob = (
            ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY").filterBounds(geom).filterDate(start, end)
        )
        joined = ee.Join.saveFirst("cloud_prob").apply(
            primary=s2,
            secondary=s2_cloud_prob,
            condition=ee.Filter.equals(leftField="system:index", rightField="system:index"),
        )

        def _mask(img, cutoff=args.cloud_prob):
            cloud = ee.Image(img.get("cloud_prob")).select("probability")
            return img.updateMask(cloud.lt(cutoff))

        masked = ee.ImageCollection(joined).map(_mask)
        composite = masked.median().select(["B4", "B3", "B2"]).rename(["red", "green", "blue"]).clip(geom)

        n_images = masked.size().getInfo()
        print(f"[fetch_s2_rgb] {year}: {n_images} source images; exporting {out_path.name}")
        geemap.ee_export_image(
            composite,
            filename=str(out_path),
            scale=30,
            region=geom,
            file_per_band=False,
        )

        manifest[str(year)] = {
            "n_source_images": n_images,
            "cloud_prob_cutoff": args.cloud_prob,
            "scale_m": 30,
            "bbox": list(NCR_BBOX),
            "start": start,
            "end": end,
            "ee_collection": "COPERNICUS/S2_SR_HARMONIZED",
            "bands": ["B4", "B3", "B2"],
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[fetch_s2_rgb] DONE  manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
