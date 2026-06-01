"""Tier 3 proof: scan Cebu City with the v9 multi-epoch GBR head.

Cebu uses the same 240m tile window, same CLIP+GBR pipeline. The only
differences from the NCR scanner: input paths + LGU/barangay geojsons.

Output:
  detection/scan_cebu/clf_v9_density_2024.tif
  detection/scan_cebu/clf_v9_per_lgu_2024.csv
  detection/scan_cebu/clf_v9_per_barangay_2024.csv
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
RGB_TIF = ROOT / "data" / "cebu" / "s2_rgb_2024.tif"
LGU_GEOJSON = ROOT / "data" / "cebu" / "cebu_lgu.geojson"
BARANGAY_GEOJSON = ROOT / "data" / "cebu" / "cebu_barangays.geojson"
CLF_V9 = ROOT / "detection" / "train" / "clf_v9.joblib"
OUT_DIR = ROOT / "detection" / "scan_cebu"

MODEL_ID = "openai/clip-vit-large-patch14"
WINDOW_PX = 8
TILE_PX = 224
BATCH = 256
N_THREADS = 10
DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")


def stretch_band(b):
    valid = b > 0
    if not valid.any():
        return np.zeros_like(b, dtype=np.uint8)
    p2, p98 = np.percentile(b[valid], (2, 98))
    return np.clip((b.astype(np.float32) - p2) / max(p98 - p2, 1) * 255, 0, 255).astype(np.uint8)


def upsample_block(crop):
    rep = TILE_PX // WINDOW_PX
    return crop.repeat(rep, axis=0).repeat(rep, axis=1)


def main() -> int:
    for p in (RGB_TIF, LGU_GEOJSON, CLF_V9):
        if not p.exists():
            print(f"missing {p}", file=sys.stderr)
            return 1
    print(f"[cebu-scan] device={DEVICE} batch={BATCH}")

    with rasterio.open(RGB_TIF) as src:
        bands = src.read([1, 2, 3])
        transform = src.transform
        height, width = src.height, src.width
        crs = src.crs
        bounds = src.bounds
    rgb = np.stack([stretch_band(bands[i]) for i in range(3)], axis=-1)
    print(f"[cebu-scan] composite {height}x{width}")

    # Tile grid
    rows_c = np.arange(WINDOW_PX // 2, height - WINDOW_PX // 2, WINDOW_PX)
    cols_c = np.arange(WINDOW_PX // 2, width - WINDOW_PX // 2, WINDOW_PX)
    half = WINDOW_PX // 2
    nr, nc = len(rows_c), len(cols_c)
    total = nr * nc

    crops = np.zeros((total, TILE_PX, TILE_PX, 3), dtype=np.uint8)
    idx_to_rc = []
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
    print(f"[cebu-scan] {k} tiles ({crops.nbytes / 1e9:.2f} GB)")

    # CLIP embed
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
            if (i // BATCH) % 8 == 0 or j == k:
                print(f"  embed {j}/{k}  ({j / (time.time() - t0):.0f} tiles/s)")

    reg_v9 = joblib.load(CLF_V9)
    density_flat = np.clip(reg_v9.predict(embeds), 0, 1)
    density_grid = np.zeros((nr, nc), dtype=np.float32)
    for idx, (ri, ci) in enumerate(idx_to_rc):
        density_grid[ri, ci] = density_flat[idx]
    density_full = np.zeros((height, width), dtype=np.float32)
    for ri in range(nr):
        for ci in range(nc):
            r0 = rows_c[ri] - half
            c0 = cols_c[ci] - half
            density_full[r0 : r0 + WINDOW_PX, c0 : c0 + WINDOW_PX] = density_grid[ri, ci]

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    out_path = OUT_DIR / "clf_v9_density_2024.tif"
    with rasterio.open(
        out_path,
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
        dst.write(density_full, 1)
    print(f"[cebu-scan] wrote {out_path.name}")

    # Per-LGU stats
    fc_lgu = json.loads(LGU_GEOJSON.read_text())
    fc_brgy = json.loads(BARANGAY_GEOJSON.read_text()) if BARANGAY_GEOJSON.exists() else {"features": []}
    lat_centre = (bounds.bottom + bounds.top) / 2
    pix_area_m2 = abs(transform.a) * abs(transform.e) * 111_320 * 111_320 * np.cos(np.radians(lat_centre))

    def stats(args):
        name, geom = args
        mask = geometry_mask([geom], out_shape=(height, width), transform=transform, invert=True)
        n_total = int(mask.sum())
        if not n_total:
            return None
        den = density_full[mask]
        return {
            "name": name,
            "total_ha": round(n_total * pix_area_m2 / 10_000, 1),
            "canopy_pct_v9": round(float(den.mean()) * 100, 3),
            "canopy_ha_v9": round(float(den.sum()) * pix_area_m2 / 10_000, 1),
        }

    print(f"\n[cebu-scan] per-LGU (n={len(fc_lgu['features'])}):")
    lgu_rows = []
    for f in fc_lgu["features"]:
        name = f["properties"].get("name") or f["properties"].get("lgu_name") or "unknown"
        r = stats((name, f["geometry"]))
        if r:
            lgu_rows.append(r)
            print(
                f"  {name:25s}  total_ha={r['total_ha']:>8.0f}  canopy={r['canopy_pct_v9']:>6.2f}%  ({r['canopy_ha_v9']:,.0f} ha)"
            )

    if lgu_rows:
        out_csv = OUT_DIR / "clf_v9_per_lgu_2024.csv"
        with out_csv.open("w") as fh:
            w = csv.DictWriter(fh, fieldnames=list(lgu_rows[0].keys()))
            w.writeheader()
            for r in lgu_rows:
                w.writerow(r)
        print(f"[cebu-scan] wrote {out_csv.name}")

    if fc_brgy["features"]:
        print(f"\n[cebu-scan] per-barangay (n={len(fc_brgy['features'])}):")
        arg_list = [(f["properties"].get("name", "?"), f["geometry"]) for f in fc_brgy["features"]]
        with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
            brgy_rows = [r for r in ex.map(stats, arg_list) if r is not None]
        brgy_rows.sort(key=lambda r: -r["canopy_pct_v9"])
        out_csv = OUT_DIR / "clf_v9_per_barangay_2024.csv"
        with out_csv.open("w") as fh:
            w = csv.DictWriter(fh, fieldnames=list(brgy_rows[0].keys()))
            w.writeheader()
            for r in brgy_rows:
                w.writerow(r)
        print(f"[cebu-scan] wrote {out_csv.name} ({len(brgy_rows)} barangays)")
        print("[cebu-scan] top 5 barangays:")
        for r in brgy_rows[:5]:
            print(f"  {r['name']:30s}  {r['canopy_pct_v9']:>6.2f}%  ({r['canopy_ha_v9']:,.0f} ha)")

    # NCR-comparable summary
    total_canopy_ha = sum(r["canopy_ha_v9"] for r in lgu_rows)
    total_area_ha = sum(r["total_ha"] for r in lgu_rows)
    if total_area_ha:
        print("\n[cebu-scan] CEBU CITY 2024 (v9):")
        print(
            f"  area-weighted canopy = {100 * total_canopy_ha / total_area_ha:.2f}% "
            f"({total_canopy_ha:,.0f} ha of {total_area_ha:,.0f})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
