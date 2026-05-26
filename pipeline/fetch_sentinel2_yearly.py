"""Fetch Sentinel-2 L2A median composites for each year 2016..2026 over NCR.

Each composite is cloud-masked with s2cloudless (probability < 40) and saved
as a 4-band GeoTIFF (red, nir, green, blue) at **30 m** resolution (matching Hansen GFC's native grid; canopy aggregation
shares the same pixel size across both sources). NDVI is computed downstream
by pipeline/compute_canopy.py.

Scale = 30 m is the current default to fit inside GEE's 50 MB synchronous URL
limit (NCR at 10 m needs ~190 MB / 4 bands / float32; at 30 m it is ~11 MB).
Per-LGU canopy aggregation is unaffected at this scale: B4/B8 are reported
at 10 m natively, but the canopy threshold is computed on NDVI averages
within polygons that are tens to hundreds of km^2. Future builds may move to 10 m
chunked exports if needed.

Idempotent: existing s2_<year>.tif files are skipped unless --force is passed.

Output:
    data/composites/s2_<year>.tif   for year in 2016..2026
    data/composites/_fetch_manifest_s2.json  (input image counts + asset versions)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from _gee_init import NCR_BBOX, NCR_YEARS, init, ncr_geometry

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "composites"
MANIFEST = OUT_DIR / "_fetch_manifest_s2.json"


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch Sentinel-2 L2A yearly composites for NCR")
    parser.add_argument("--years", nargs="+", type=int, default=list(NCR_YEARS))
    parser.add_argument("--force", action="store_true", help="Re-download even if files exist")
    parser.add_argument(
        "--cloud-prob", type=int, default=40, help="s2cloudless probability cutoff (0-100; default 40)"
    )
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
        out_path = OUT_DIR / f"s2_{year}.tif"
        if out_path.exists() and not args.force:
            print(f"[fetch_s2] {year}: {out_path.name} already exists; skip (use --force to re-fetch)")
            continue

        start = f"{year}-01-01"
        end = f"{year + 1}-01-01"

        s2 = (
            ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
            .filterBounds(geom)
            .filterDate(start, end)
            .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
        )
        s2_cloud_prob = (
            ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY")
            .filterBounds(geom)
            .filterDate(start, end)
        )

        joined = ee.Join.saveFirst("cloud_prob").apply(
            primary=s2,
            secondary=s2_cloud_prob,
            condition=ee.Filter.equals(leftField="system:index", rightField="system:index"),
        )

        def _mask(img, cutoff=args.cloud_prob):
            cloud = ee.Image(img.get("cloud_prob")).select("probability")
            mask = cloud.lt(cutoff)
            return img.updateMask(mask)

        masked = ee.ImageCollection(joined).map(_mask)
        # Only red (B4) + nir (B8) for NDVI math. RGB-display bands (B3, B2)
        # are out of scope here; animation fetches them separately
        # against the same composites if needed.
        composite = masked.median().select(["B4", "B8"]).rename(["red", "nir"])
        composite = composite.clip(geom)

        n_images = masked.size().getInfo()
        print(f"[fetch_s2] {year}: {n_images} source images after cloud mask; exporting to {out_path.name}")

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
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[fetch_s2] DONE. Manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
