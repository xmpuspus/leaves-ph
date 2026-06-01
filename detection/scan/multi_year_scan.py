"""Final multi-year scan: predict per-tile canopy with clf_v5 (Platt-calibrated
binary head) and clf_v6 (Ridge continuous canopy-fraction head) across every
epoch in ALL_YEARS.

Per year produces:
  detection/scan/clf_v5_probs_<year>.tif        (binary head probability)
  detection/scan/clf_v6_density_<year>.tif      (continuous canopy fraction 0..1)
  detection/scan/clf_v6_per_lgu_<year>.csv      (per-LGU canopy ha + %)

Final aggregated artefacts:
  detection/scan/clf_v6_ncr_series.csv          (8-year NCR canopy series)
  detection/scan/clf_v6_per_lgu_series.csv      (per-LGU x per-year long format)

Compute strategy:
  - 21,460 tiles per year
  - CLIP forward bf16 on MPS, batch 256
  - Per-tile probability & density predicted; rasterised back to full Hansen grid
  - 10-thread ThreadPoolExecutor for I/O + per-LGU mask + per-year CSV
"""

from __future__ import annotations

import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import joblib
import numpy as np
import rasterio
import torch
from rasterio.features import geometry_mask
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parents[2]
RGB_TIF_TPL = ROOT / "data" / "composites" / "s2_rgb_{year}.tif"
LGU_GEOJSON = ROOT / "data" / "lgu" / "ncr_lgu.geojson"

CLF_V5 = ROOT / "detection" / "train" / "clf_v5.joblib"
CLF_V6 = ROOT / "detection" / "train" / "clf_v6.joblib"
OUT_DIR = ROOT / "detection" / "scan"

ALL_YEARS = list(range(2019, 2027))
MODEL_ID = "openai/clip-vit-large-patch14"
WINDOW_PX = 8
TILE_PX = 224
BATCH = 256
N_THREADS = 10
DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")


def stretch_band(b: np.ndarray) -> np.ndarray:
    valid = b > 0
    if not valid.any():
        return np.zeros_like(b, dtype=np.uint8)
    p2, p98 = np.percentile(b[valid], (2, 98))
    out = np.clip((b.astype(np.float32) - p2) / max(p98 - p2, 1) * 255, 0, 255)
    return out.astype(np.uint8)


def upsample_block(crop: np.ndarray) -> np.ndarray:
    rep = TILE_PX // WINDOW_PX
    return crop.repeat(rep, axis=0).repeat(rep, axis=1)


def embed_tiles(crops: np.ndarray, model, processor, img_mean, img_std) -> np.ndarray:
    k = len(crops)
    embeds = np.zeros((k, 768), dtype=np.float32)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, k, BATCH):
            j = min(i + BATCH, k)
            arr = crops[i:j].astype(np.float32) / 255.0
            t = torch.from_numpy(arr).permute(0, 3, 1, 2).to(DEVICE)
            t = (t - img_mean) / img_std
            if DEVICE in ("mps", "cuda"):
                t = t.to(dtype=torch.bfloat16)
            emb = model.get_image_features(pixel_values=t)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            embeds[i:j] = emb.float().cpu().numpy()
            if (i // BATCH) % 16 == 0 or j == k:
                print(f"      embed {j}/{k}  ({j / (time.time() - t0):.0f} tiles/s)")
    return embeds


def rasterise(
    tile_vals: np.ndarray, rows_c, cols_c, height: int, width: int, fill: float = 0.0, dtype=np.float32
) -> np.ndarray:
    out = np.full((height, width), fill, dtype=dtype)
    half = WINDOW_PX // 2
    for ri in range(tile_vals.shape[0]):
        for ci in range(tile_vals.shape[1]):
            r0 = rows_c[ri] - half
            c0 = cols_c[ci] - half
            out[r0 : r0 + WINDOW_PX, c0 : c0 + WINDOW_PX] = tile_vals[ri, ci]
    return out


def lgu_density_stats(args):
    name, geom, density_raster, ncr_mask, transform, height, width, pixel_area_m2 = args
    lgu_pix = geometry_mask([geom], out_shape=(height, width), transform=transform, invert=True)
    lgu_pix &= ncr_mask
    n_total = int(lgu_pix.sum())
    if not n_total:
        return None
    density_in_lgu = density_raster[lgu_pix]
    canopy_pct = float(density_in_lgu.mean()) * 100.0
    canopy_ha = float(density_in_lgu.sum()) * pixel_area_m2 / 10_000.0
    total_ha = float(n_total) * pixel_area_m2 / 10_000.0
    return {
        "lgu_name": name,
        "total_ha": round(total_ha, 1),
        "canopy_ha_v6": round(canopy_ha, 1),
        "canopy_pct_v6": round(canopy_pct, 3),
    }


def scan_year(year: int, model, processor, img_mean, img_std, clf_v5, reg_v6, lgu_features, ncr_mask) -> dict:
    rgb_path = Path(str(RGB_TIF_TPL).format(year=year))
    if not rgb_path.exists():
        print(f"[multi-scan] missing {rgb_path}, skip", file=sys.stderr)
        return {}
    print(f"\n[multi-scan] === year {year} ===")
    with rasterio.open(rgb_path) as src:
        bands = src.read([1, 2, 3])
        transform = src.transform
        height, width = src.height, src.width
        crs = src.crs
        bounds = src.bounds
    rgb = np.stack([stretch_band(bands[i]) for i in range(3)], axis=-1)

    rows_c = np.arange(WINDOW_PX // 2, height - WINDOW_PX // 2, WINDOW_PX)
    cols_c = np.arange(WINDOW_PX // 2, width - WINDOW_PX // 2, WINDOW_PX)
    nr, nc = len(rows_c), len(cols_c)
    total_tiles = nr * nc

    t0 = time.time()
    crops = np.zeros((total_tiles, TILE_PX, TILE_PX, 3), dtype=np.uint8)
    idx_to_rc: list[tuple[int, int]] = []
    half = WINDOW_PX // 2
    k = 0
    for ri, r in enumerate(rows_c):
        for ci, c in enumerate(cols_c):
            crop = rgb[r - half : r + half, c - half : c + half, :]
            if crop.shape[:2] != (WINDOW_PX, WINDOW_PX):
                continue
            crops[k] = upsample_block(crop)
            idx_to_rc.append((ri, ci))
            k += 1
    crops = crops[:k]
    print(f"  pre-stacked {k} crops ({crops.nbytes / 1e9:.2f} GB) {time.time() - t0:.1f}s")

    embeds = embed_tiles(crops, model, processor, img_mean, img_std)

    # v5 calibrated probability
    probs_flat = clf_v5.predict_proba(embeds)[:, 1]
    # v6 continuous canopy fraction
    density_flat = np.clip(reg_v6.predict(embeds), 0.0, 1.0)

    probs_grid = np.zeros((nr, nc), dtype=np.float32)
    density_grid = np.zeros((nr, nc), dtype=np.float32)
    for idx, (ri, ci) in enumerate(idx_to_rc):
        probs_grid[ri, ci] = probs_flat[idx]
        density_grid[ri, ci] = density_flat[idx]

    probs_full = rasterise(probs_grid, rows_c, cols_c, height, width, dtype=np.float32)
    density_full = rasterise(density_grid, rows_c, cols_c, height, width, dtype=np.float32)

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for arr, name in [(probs_full, f"clf_v5_probs_{year}.tif"), (density_full, f"clf_v6_density_{year}.tif")]:
        with rasterio.open(
            OUT_DIR / name,
            "w",
            driver="GTiff",
            height=height,
            width=width,
            count=1,
            dtype=rasterio.float32,
            crs=crs,
            transform=transform,
            compress="deflate",
        ) as dst:
            dst.write(arr, 1)
    print(f"  wrote clf_v5_probs_{year}.tif + clf_v6_density_{year}.tif")

    lat_centre = (bounds.bottom + bounds.top) / 2
    pixel_area_m2 = abs(transform.a) * abs(transform.e) * 111_320 * 111_320 * np.cos(np.radians(lat_centre))
    # Mask density to NCR before per-LGU stats
    density_in_ncr = np.where(ncr_mask, density_full, 0.0).astype(np.float32)

    arg_list = [
        (
            f["properties"]["lgu_name"],
            f["geometry"],
            density_in_ncr,
            ncr_mask,
            transform,
            height,
            width,
            pixel_area_m2,
        )
        for f in lgu_features
    ]
    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        rows = [r for r in ex.map(lgu_density_stats, arg_list) if r is not None]
    rows.sort(key=lambda r: -r["canopy_pct_v6"])
    out_csv = OUT_DIR / f"clf_v6_per_lgu_{year}.csv"
    with out_csv.open("w") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) + ["year"])
        w.writeheader()
        for r in rows:
            r["year"] = year
            w.writerow(r)
    print(f"  wrote {out_csv.name}")

    # NCR-wide
    total_pix = ncr_mask.sum()
    ncr_canopy_ha = float(density_in_ncr.sum()) * pixel_area_m2 / 10_000.0
    ncr_total_ha = float(total_pix) * pixel_area_m2 / 10_000.0
    ncr_pct = 100.0 * ncr_canopy_ha / ncr_total_ha if ncr_total_ha else 0.0
    print(f"  NCR {year}: clf_v6 canopy = {ncr_pct:.2f}% ({ncr_canopy_ha:,.0f} ha of {ncr_total_ha:,.0f})")

    return {
        "year": year,
        "ncr_canopy_pct_v6": round(ncr_pct, 3),
        "ncr_canopy_ha_v6": round(ncr_canopy_ha, 1),
        "ncr_total_ha": round(ncr_total_ha, 1),
        "per_lgu": rows,
    }


def main() -> int:
    if not CLF_V5.exists() or not CLF_V6.exists():
        print("[multi-scan] FAIL: clf_v5 or clf_v6 missing", file=sys.stderr)
        return 1
    print(f"[multi-scan] device={DEVICE} batch={BATCH} threads={N_THREADS}")

    print("[multi-scan] loading CLIP + models")
    processor = CLIPProcessor.from_pretrained(MODEL_ID, use_fast=True)
    model = CLIPModel.from_pretrained(MODEL_ID).to(DEVICE).eval()
    if DEVICE in ("mps", "cuda"):
        model = model.to(dtype=torch.bfloat16)
    img_mean = torch.tensor(processor.image_processor.image_mean, dtype=torch.float32, device=DEVICE).view(
        1, 3, 1, 1
    )
    img_std = torch.tensor(processor.image_processor.image_std, dtype=torch.float32, device=DEVICE).view(
        1, 3, 1, 1
    )
    clf_v5 = joblib.load(CLF_V5)
    reg_v6 = joblib.load(CLF_V6)

    fc = json.loads(LGU_GEOJSON.read_text())
    # NCR mask is shared across years (PSA boundaries stable)
    with rasterio.open(Path(str(RGB_TIF_TPL).format(year=ALL_YEARS[0]))) as src:
        transform = src.transform
        height, width = src.height, src.width
    ncr_mask = geometry_mask(
        [f["geometry"] for f in fc["features"]], out_shape=(height, width), transform=transform, invert=True
    )

    series: list[dict] = []
    for year in ALL_YEARS:
        res = scan_year(year, model, processor, img_mean, img_std, clf_v5, reg_v6, fc["features"], ncr_mask)
        if res:
            series.append(res)

    # Aggregated NCR canopy series
    series_csv = OUT_DIR / "clf_v6_ncr_series.csv"
    with series_csv.open("w") as fh:
        w = csv.writer(fh)
        w.writerow(["year", "ncr_canopy_pct_v6", "ncr_canopy_ha_v6", "ncr_total_ha"])
        for s in series:
            w.writerow([s["year"], s["ncr_canopy_pct_v6"], s["ncr_canopy_ha_v6"], s["ncr_total_ha"]])
    print(f"\n[multi-scan] wrote {series_csv.name}")

    # Long-format per-LGU series
    long_csv = OUT_DIR / "clf_v6_per_lgu_series.csv"
    with long_csv.open("w") as fh:
        w = csv.DictWriter(fh, fieldnames=["lgu_name", "year", "canopy_ha_v6", "canopy_pct_v6", "total_ha"])
        w.writeheader()
        for s in series:
            for r in s["per_lgu"]:
                w.writerow(
                    {
                        "lgu_name": r["lgu_name"],
                        "year": s["year"],
                        "canopy_ha_v6": r["canopy_ha_v6"],
                        "canopy_pct_v6": r["canopy_pct_v6"],
                        "total_ha": r["total_ha"],
                    }
                )
    print(f"[multi-scan] wrote {long_csv.name}")
    print("\n[multi-scan] === NCR series ===")
    for s in series:
        print(f"  {s['year']}  clf_v6 = {s['ncr_canopy_pct_v6']:>6.2f}%   {s['ncr_canopy_ha_v6']:,.0f} ha")
    return 0


if __name__ == "__main__":
    sys.exit(main())
