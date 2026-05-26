"""Per-year per-pixel canopy mask from cached Sentinel-2 composites.

Reads `data/composites/s2_<year>.tif` (4-band: red, nir, green, blue), computes
NDVI = (nir - red) / (nir + red), thresholds at the calibrated cutoff (see
`pipeline/calibrate_ndvi_threshold.py`), and writes a single-band uint8 raster.

Output:
    data/composites/canopy_<year>.tif   for year in 2016..2026
    data/composites/_canopy_manifest.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio

REPO_ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = REPO_ROOT / "data" / "composites"
MANIFEST = COMP_DIR / "_canopy_manifest.json"
DEFAULT_THRESHOLD = 0.50  # tuned at Phase 3 calibration step; this is the fallback


def compute_ndvi(red: np.ndarray, nir: np.ndarray) -> np.ndarray:
    red = red.astype(np.float32)
    nir = nir.astype(np.float32)
    denom = nir + red
    out = np.full_like(denom, np.nan, dtype=np.float32)
    valid = denom > 0
    out[valid] = (nir[valid] - red[valid]) / denom[valid]
    return out


def canopy_mask_for_year(in_path: Path, threshold: float) -> tuple[np.ndarray, dict]:
    with rasterio.open(in_path) as src:
        red = src.read(1)
        nir = src.read(2)
        profile = src.profile.copy()
    ndvi = compute_ndvi(red, nir)
    canopy = (ndvi >= threshold).astype(np.uint8)
    canopy[np.isnan(ndvi)] = 255  # nodata sentinel
    profile.update(
        {"count": 1, "dtype": "uint8", "nodata": 255, "compress": "deflate", "predictor": 2}
    )
    return canopy, profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Compute per-year canopy mask from S2 composites")
    parser.add_argument("--years", nargs="+", type=int, default=list(range(2019, 2027)))
    parser.add_argument("--threshold", type=float, default=None,
                        help="NDVI threshold; default reads from data/calibration_report.json or falls back to 0.50")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    threshold = args.threshold
    if threshold is None:
        cal_path = REPO_ROOT / "data" / "calibration_report.json"
        if cal_path.exists():
            cal = json.loads(cal_path.read_text())
            threshold = float(cal.get("best_threshold", DEFAULT_THRESHOLD))
            print(f"[compute_canopy] using calibrated threshold {threshold:.3f} from {cal_path.name}")
        else:
            threshold = DEFAULT_THRESHOLD
            print(
                f"[compute_canopy] no calibration report; falling back to {threshold:.3f}. "
                "Run `python3 pipeline/calibrate_ndvi_threshold.py` first for tuned threshold."
            )

    manifest: dict[str, dict] = {}
    if MANIFEST.exists():
        manifest = json.loads(MANIFEST.read_text())

    for year in args.years:
        in_path = COMP_DIR / f"s2_{year}.tif"
        out_path = COMP_DIR / f"canopy_{year}.tif"
        if not in_path.exists():
            print(f"[compute_canopy] {year}: MISSING {in_path.name} (run `make fetch` first); skip")
            continue
        if out_path.exists() and not args.force:
            print(f"[compute_canopy] {year}: {out_path.name} already exists; skip")
            continue
        print(f"[compute_canopy] {year}: ndvi >= {threshold:.3f} -> {out_path.name}")
        canopy, profile = canopy_mask_for_year(in_path, threshold)
        with rasterio.open(out_path, "w", **profile) as dst:
            dst.write(canopy, 1)
        manifest[str(year)] = {
            "input": in_path.name,
            "output": out_path.name,
            "ndvi_threshold": threshold,
            "canopy_pixels": int((canopy == 1).sum()),
            "non_canopy_pixels": int((canopy == 0).sum()),
            "nodata_pixels": int((canopy == 255).sum()),
        }

    MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True))
    print(f"[compute_canopy] DONE. Manifest at {MANIFEST.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
