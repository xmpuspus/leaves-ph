"""Tune the NDVI threshold against Meta Canopy Height v2 ground truth.

Strategy (per docs/methodology.md section 4):
1. Sample N random pixels from the NCR bbox (N=10000 default).
2. For each pixel: read NDVI (computed from a single reference year's S2
   composite) and Meta canopy height.
3. Treat Meta height > 5 m as positive ground truth.
4. Sweep NDVI threshold from 0.40 to 0.70 in 0.01 steps.
5. Pick the threshold that maximises F1 against Meta truth, subject to
   recall >= 0.85.

The reference year for calibration is 2020 by default (Meta source imagery is
mostly 2018-2020, so calibration against 2020 NDVI is the cleanest match).

Output:
    data/calibration_report.json with best_threshold, F1, precision, recall.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from rasterio.warp import Resampling, reproject

REPO_ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = REPO_ROOT / "data" / "composites"
META_PATH = REPO_ROOT / "data" / "meta" / "canopy_height_ncr.tif"
OUT_PATH = REPO_ROOT / "data" / "calibration_report.json"

DEFAULT_YEAR = 2020
DEFAULT_HEIGHT_THRESHOLD = 5.0  # meters: positive truth = canopy > 5 m
DEFAULT_N_SAMPLES = 10000
DEFAULT_THRESHOLD_GRID = np.arange(0.40, 0.71, 0.01)
DEFAULT_RECALL_FLOOR = 0.85


def load_ndvi(year: int) -> tuple[np.ndarray, dict]:
    """Compute NDVI from the cached S2 composite for the given year."""
    s2_path = COMP_DIR / f"s2_{year}.tif"
    if not s2_path.exists():
        raise FileNotFoundError(
            f"Missing {s2_path}. Run `python3 pipeline/fetch_sentinel2_yearly.py --years {year}` first."
        )
    with rasterio.open(s2_path) as src:
        red = src.read(1).astype(np.float32)
        nir = src.read(2).astype(np.float32)
        profile = src.profile.copy()
    denom = nir + red
    ndvi = np.full_like(denom, np.nan, dtype=np.float32)
    valid = denom > 0
    ndvi[valid] = (nir[valid] - red[valid]) / denom[valid]
    return ndvi, profile


def load_meta_aligned(target_profile: dict) -> np.ndarray:
    """Resample Meta canopy height to match the NDVI raster's grid (nearest)."""
    if not META_PATH.exists():
        raise FileNotFoundError(
            f"Missing {META_PATH}. Run `python3 pipeline/fetch_meta_canopy_height.py` first."
        )
    with rasterio.open(META_PATH) as meta_src:
        out = np.full((target_profile["height"], target_profile["width"]), np.nan, dtype=np.float32)
        reproject(
            source=rasterio.band(meta_src, 1),
            destination=out,
            src_transform=meta_src.transform,
            src_crs=meta_src.crs,
            dst_transform=target_profile["transform"],
            dst_crs=target_profile["crs"],
            resampling=Resampling.average,  # average reduces 1m -> 10m honestly
        )
    return out


def sweep_thresholds(
    ndvi: np.ndarray,
    height: np.ndarray,
    grid: np.ndarray,
    height_threshold: float,
    recall_floor: float,
) -> dict:
    """Return the best threshold + F1/precision/recall + the full sweep table."""
    truth = height > height_threshold
    # Mask invalid / nodata pixels
    valid = np.isfinite(ndvi) & np.isfinite(height) & (height >= 0)
    truth = truth[valid]
    ndvi_v = ndvi[valid]

    sweep_rows = []
    best_f1 = -1.0
    best_row = None
    for t in grid:
        pred = ndvi_v >= float(t)
        tp = int(np.sum(pred & truth))
        fp = int(np.sum(pred & ~truth))
        fn = int(np.sum(~pred & truth))
        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
        row = {
            "threshold": round(float(t), 3),
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
        }
        sweep_rows.append(row)
        if recall >= recall_floor and f1 > best_f1:
            best_f1 = f1
            best_row = row

    if best_row is None:
        # No threshold met the recall floor; pick max-F1 unconstrained and flag.
        best_row = max(sweep_rows, key=lambda r: r["f1"])
        best_row["recall_floor_met"] = False
    else:
        best_row["recall_floor_met"] = True
    return {"best": best_row, "sweep": sweep_rows}


def main() -> int:
    parser = argparse.ArgumentParser(description="Tune NDVI threshold vs Meta canopy height truth")
    parser.add_argument("--year", type=int, default=DEFAULT_YEAR,
                        help=f"reference year for NDVI (default {DEFAULT_YEAR})")
    parser.add_argument("--height-threshold", type=float, default=DEFAULT_HEIGHT_THRESHOLD)
    parser.add_argument("--n-samples", type=int, default=DEFAULT_N_SAMPLES,
                        help="random sample size for the sweep (0 = use all valid pixels)")
    parser.add_argument("--recall-floor", type=float, default=DEFAULT_RECALL_FLOOR)
    parser.add_argument("--seed", type=int, default=4242)
    args = parser.parse_args()

    ndvi, profile = load_ndvi(args.year)
    height = load_meta_aligned(profile)

    if args.n_samples > 0:
        rng = np.random.default_rng(args.seed)
        flat_ndvi = ndvi.flatten()
        flat_h = height.flatten()
        valid_idx = np.flatnonzero(np.isfinite(flat_ndvi) & np.isfinite(flat_h) & (flat_h >= 0))
        n_take = min(args.n_samples, valid_idx.size)
        chosen = rng.choice(valid_idx, size=n_take, replace=False)
        ndvi_sample = flat_ndvi[chosen]
        h_sample = flat_h[chosen]
    else:
        ndvi_sample = ndvi
        h_sample = height

    result = sweep_thresholds(
        ndvi_sample, h_sample, DEFAULT_THRESHOLD_GRID, args.height_threshold, args.recall_floor
    )
    best = result["best"]
    report = {
        "reference_year": args.year,
        "height_threshold_m": args.height_threshold,
        "recall_floor": args.recall_floor,
        "n_samples": args.n_samples,
        "seed": args.seed,
        "best_threshold": best["threshold"],
        "best_f1": best["f1"],
        "best_precision": best["precision"],
        "best_recall": best["recall"],
        "best_recall_floor_met": best["recall_floor_met"],
        "sweep": result["sweep"],
    }
    OUT_PATH.write_text(json.dumps(report, indent=2, sort_keys=True))
    print(
        f"[calibrate] best threshold = {best['threshold']:.3f}  "
        f"F1 = {best['f1']:.3f}  precision = {best['precision']:.3f}  recall = {best['recall']:.3f}"
    )
    if not best["recall_floor_met"]:
        print(
            f"[calibrate] WARNING: recall floor {args.recall_floor} not met; "
            "consider raising threshold or relaxing floor."
        )
    print(f"[calibrate] DONE. Report at {OUT_PATH.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
