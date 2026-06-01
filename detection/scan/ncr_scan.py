"""Scan NCR with a versioned CLIP+LR head, persist probabilities, sweep
thresholds, render per-LGU visual-validation panels.

Framing: EXPANSION OF the NDVI v0 baseline, not replacement.
  - NDVI is the floor
  - clf confirms a subset (shared) and proposes additions (new)
  - Visual validation per LGU lets a human inspect the new tiles

M5 utilisation:
  - CLIP forward in bf16 on MPS, batch 256
  - Pre-stacked uint8 crop tensor before any model call
  - 10-thread pool for per-LGU mask + stats + panel rendering
"""

from __future__ import annotations

import csv
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import joblib
import matplotlib

matplotlib.use("Agg")
import matplotlib.patches as mpatches
import matplotlib.pyplot as plt
import numpy as np
import rasterio
import torch
from rasterio.features import geometry_mask
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parents[2]
RGB_TIF_TPL = ROOT / "data" / "composites" / "s2_rgb_{year}.tif"
NDVI_TIF_TPL = ROOT / "data" / "composites" / "canopy_{year}.tif"
LGU_GEOJSON = ROOT / "data" / "lgu" / "ncr_lgu.geojson"

VERSION = "v3"
CLF_PATH = ROOT / "detection" / "train" / f"clf_{VERSION}.joblib"
OUT_DIR = ROOT / "detection" / "scan"
OUT_VIS_DIR = OUT_DIR / f"validation_{VERSION}"

MODEL_ID = "openai/clip-vit-large-patch14"
WINDOW_PX = 8
TILE_PX = 224
BATCH = 256
YEAR = 2024
N_THREADS = 10
DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")

THRESHOLDS = [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.85, 0.90]
DEFAULT_T = 0.60
ALL_YEARS = list(range(2019, 2027))


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


def embed_all_tiles(crops: np.ndarray) -> np.ndarray:
    t0 = time.time()
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
    k = len(crops)
    embeds = np.zeros((k, 768), dtype=np.float32)
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
    print(f"[scan] embed complete  {time.time() - t0:.1f}s")
    return embeds


def rasterise_tile_mask(mask_lo: np.ndarray, rows_c, cols_c, height: int, width: int) -> np.ndarray:
    out = np.zeros((height, width), dtype=bool)
    half = WINDOW_PX // 2
    for ri in range(mask_lo.shape[0]):
        for ci in range(mask_lo.shape[1]):
            if mask_lo[ri, ci]:
                r0 = rows_c[ri] - half
                c0 = cols_c[ci] - half
                out[r0 : r0 + WINDOW_PX, c0 : c0 + WINDOW_PX] = True
    return out


def lgu_stats(args):
    (name, geom, ndvi_mask, clf_mask, ncr_mask, transform, height, width, pixel_area_m2) = args
    lgu_pix = geometry_mask([geom], out_shape=(height, width), transform=transform, invert=True)
    lgu_pix &= ncr_mask
    n_total = int(lgu_pix.sum())
    if not n_total:
        return None
    n_v0 = int((ndvi_mask & lgu_pix).sum())
    n_clf = int((clf_mask & lgu_pix).sum())
    n_shared = int((ndvi_mask & clf_mask & lgu_pix).sum())
    n_new = int((~ndvi_mask & clf_mask & lgu_pix).sum())
    n_dropped = int((ndvi_mask & ~clf_mask & lgu_pix).sum())
    return {
        "lgu_name": name,
        "total_ha": round(n_total * pixel_area_m2 / 10_000, 1),
        "ndvi_v0_pct": round(100.0 * n_v0 / n_total, 3),
        "clf_pct": round(100.0 * n_clf / n_total, 3),
        "shared_pct": round(100.0 * n_shared / n_total, 3),
        "new_pct": round(100.0 * n_new / n_total, 3),
        "dropped_pct": round(100.0 * n_dropped / n_total, 3),
        "delta_pp_clf_vs_v0": round(100.0 * (n_clf - n_v0) / n_total, 3),
    }


def render_lgu_panel(args):
    (
        name,
        geom,
        ndvi_mask,
        clf_mask,
        _ncr_mask,
        rgb,
        transform,
        height,
        width,
        _pixel_area_m2,
        year,
        threshold,
        out_dir,
        stats,
        version,
    ) = args
    lgu_pix = geometry_mask([geom], out_shape=(height, width), transform=transform, invert=True)
    rows, cols = np.where(lgu_pix)
    if rows.size == 0:
        return None
    pad = 8
    r0 = max(rows.min() - pad, 0)
    r1 = min(rows.max() + pad, height)
    c0 = max(cols.min() - pad, 0)
    c1 = min(cols.max() + pad, width)
    rgb_lg = rgb[r0:r1, c0:c1, :]
    nd_lg = ndvi_mask[r0:r1, c0:c1] & lgu_pix[r0:r1, c0:c1]
    cl_lg = clf_mask[r0:r1, c0:c1] & lgu_pix[r0:r1, c0:c1]
    shared = nd_lg & cl_lg
    new = ~nd_lg & cl_lg

    fig, axes = plt.subplots(1, 4, figsize=(18, 5.5), dpi=120)
    for ax in axes:
        ax.set_xticks([])
        ax.set_yticks([])
        for s in ax.spines.values():
            s.set_visible(False)
    fig.patch.set_facecolor("#f7f3e9")

    axes[0].imshow(rgb_lg)
    axes[0].set_title("S-2 RGB", fontsize=10, family="serif")

    axes[1].imshow(rgb_lg)
    overlay = np.zeros((*nd_lg.shape, 4), dtype=np.float32)
    overlay[nd_lg] = (0.95, 0.55, 0.20, 0.6)
    axes[1].imshow(overlay)
    axes[1].set_title(f"NDVI v0 baseline ({stats['ndvi_v0_pct']:.2f}%)", fontsize=10, family="serif")

    axes[2].imshow(rgb_lg)
    overlay2 = np.zeros((*cl_lg.shape, 4), dtype=np.float32)
    overlay2[shared] = (0.12, 0.40, 0.20, 0.7)
    overlay2[new] = (0.96, 0.85, 0.20, 0.8)
    axes[2].imshow(overlay2)
    axes[2].set_title(
        f"clf_{version} @ t={threshold} ({stats['clf_pct']:.2f}%)  +{stats['new_pct']:.2f}pp",
        fontsize=10,
        family="serif",
    )

    axes[3].axis("off")
    axes[3].set_facecolor("#f7f3e9")
    text = (
        f"{name.upper()}\n\n"
        f"AREA           {stats['total_ha']:>10,.0f} ha\n"
        f"NDVI v0        {stats['ndvi_v0_pct']:>10.2f} %\n"
        f"clf_{version}         {stats['clf_pct']:>10.2f} %\n"
        f"shared         {stats['shared_pct']:>10.2f} %\n"
        f"new (added)    {stats['new_pct']:>10.2f} %\n"
        f"dropped        {stats['dropped_pct']:>10.2f} %\n"
        f"delta vs v0    {stats['delta_pp_clf_vs_v0']:>+10.2f} pp\n\n"
        f"Threshold      {threshold:>10.2f}\n"
        f"Year           {year:>10}\n"
    )
    axes[3].text(0.0, 0.95, text, fontsize=11, family="monospace", color="#1a1a1a", va="top", ha="left")
    handles = [
        mpatches.Patch(color="#f28a33", label="NDVI v0 baseline"),
        mpatches.Patch(color="#1f6634", label=f"clf_{version} shared (confirmed)"),
        mpatches.Patch(color="#f6d933", label=f"clf_{version} NEW (added by model)"),
    ]
    axes[3].legend(handles=handles, loc="lower left", frameon=False, fontsize=9, prop={"family": "monospace"})
    fig.suptitle(
        f"Leaves.PH validation · {name} · {year} · clf_{version} t={threshold}",
        fontsize=13,
        family="serif",
        color="#1f3d2b",
        y=1.02,
    )
    safe = name.replace(" ", "_").replace("/", "_")
    out_path = out_dir / f"validation_{safe}_t{int(threshold * 100):02d}.png"
    fig.savefig(out_path, bbox_inches="tight", facecolor=fig.get_facecolor())
    plt.close(fig)
    return out_path


def scan(year: int) -> None:
    rgb_path = Path(str(RGB_TIF_TPL).format(year=year))
    ndvi_path = Path(str(NDVI_TIF_TPL).format(year=year))
    for pth in (rgb_path, ndvi_path):
        if not pth.exists():
            print(f"[scan] missing {pth}", file=sys.stderr)
            sys.exit(1)
    print(f"[scan] version={VERSION}  year={year}  device={DEVICE}  threads={N_THREADS}")

    with rasterio.open(rgb_path) as src:
        bands = src.read([1, 2, 3])
        transform = src.transform
        height, width = src.height, src.width
        crs = src.crs
        bounds = src.bounds
    with rasterio.open(ndvi_path) as src:
        ndvi_mask_full = src.read(1).astype(bool)
    rgb = np.stack([stretch_band(bands[i]) for i in range(3)], axis=-1)
    print(f"[scan] composite {height}x{width}")

    fc = json.loads(LGU_GEOJSON.read_text())
    geoms_all = [f["geometry"] for f in fc["features"]]
    ncr_mask = geometry_mask(geoms_all, out_shape=(height, width), transform=transform, invert=True)
    n_ncr = int(ncr_mask.sum())
    print(f"[scan] NCR union mask: {n_ncr:,} pixels inside")

    rows_c = np.arange(WINDOW_PX // 2, height - WINDOW_PX // 2, WINDOW_PX)
    cols_c = np.arange(WINDOW_PX // 2, width - WINDOW_PX // 2, WINDOW_PX)
    nr, nc = len(rows_c), len(cols_c)
    total_tiles = nr * nc
    print(f"[scan] tile grid {nr}x{nc} = {total_tiles} tiles")

    # Pre-stack crops
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
    print(f"[scan] pre-stacked {k} crops ({crops.nbytes / 1e9:.2f} GB) {time.time() - t0:.1f}s")

    embeds = embed_all_tiles(crops)
    clf = joblib.load(CLF_PATH)
    probs_flat = clf.predict_proba(embeds)[:, 1]
    probs_grid = np.zeros((nr, nc), dtype=np.float32)
    for idx, (ri, ci) in enumerate(idx_to_rc):
        probs_grid[ri, ci] = probs_flat[idx]

    # Persist probabilities as a GeoTIFF
    probs_full = np.zeros((height, width), dtype=np.float32)
    for ri in range(nr):
        for ci in range(nc):
            r0 = rows_c[ri] - half
            c0 = cols_c[ci] - half
            probs_full[r0 : r0 + WINDOW_PX, c0 : c0 + WINDOW_PX] = probs_grid[ri, ci]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    prob_path = OUT_DIR / f"clf_{VERSION}_probs_{year}.tif"
    with rasterio.open(
        prob_path,
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
        dst.write(probs_full, 1)
    print(f"[scan] wrote {prob_path.name}")

    print("\n[scan] === threshold sweep (NCR-clipped) ===")
    print(f"  {'t':>5}  {'clf':>7}  {'shared':>7}  {'NEW':>7}  {'dropped':>7}")
    sweep = []
    ndvi_in_ncr = ndvi_mask_full & ncr_mask
    n_ndvi = int(ndvi_in_ncr.sum())
    for t in THRESHOLDS:
        mask_lo = (probs_grid >= t).astype(np.uint8)
        clf_mask = rasterise_tile_mask(mask_lo, rows_c, cols_c, height, width)
        clf_in_ncr = clf_mask & ncr_mask
        shared = clf_in_ncr & ndvi_in_ncr
        new = clf_in_ncr & ~ndvi_in_ncr
        dropped = ndvi_in_ncr & ~clf_in_ncr
        row = {
            "threshold": t,
            "ndvi_v0_pct": round(100 * n_ndvi / n_ncr, 3),
            "clf_pct": round(100 * clf_in_ncr.sum() / n_ncr, 3),
            "shared_pct": round(100 * shared.sum() / n_ncr, 3),
            "new_pct": round(100 * new.sum() / n_ncr, 3),
            "dropped_pct": round(100 * dropped.sum() / n_ncr, 3),
        }
        sweep.append(row)
        print(
            f"  {t:>5.2f}  {row['clf_pct']:>7.2f}  {row['shared_pct']:>7.2f}  "
            f"{row['new_pct']:>7.2f}  {row['dropped_pct']:>7.2f}"
        )
    (OUT_DIR / f"clf_{VERSION}_threshold_sweep_{year}.json").write_text(
        json.dumps(
            {
                "year": year,
                "version": VERSION,
                "ndvi_v0_ncr_pct": round(100 * n_ndvi / n_ncr, 3),
                "sweep": sweep,
            },
            indent=2,
        )
    )

    pick_t = DEFAULT_T
    print(f"\n[scan] rendering panels at default t={pick_t}")
    mask_lo = (probs_grid >= pick_t).astype(np.uint8)
    clf_mask = rasterise_tile_mask(mask_lo, rows_c, cols_c, height, width)
    lat_centre = (bounds.bottom + bounds.top) / 2
    pixel_area_m2 = abs(transform.a) * abs(transform.e) * 111_320 * 111_320 * np.cos(np.radians(lat_centre))

    print(f"[scan] per-LGU stats (parallel x{N_THREADS})")
    arg_list = [
        (
            f["properties"]["lgu_name"],
            f["geometry"],
            ndvi_mask_full,
            clf_mask,
            ncr_mask,
            transform,
            height,
            width,
            pixel_area_m2,
        )
        for f in fc["features"]
    ]
    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        rows = [r for r in ex.map(lgu_stats, arg_list) if r is not None]
    rows.sort(key=lambda r: -r["clf_pct"])
    out_csv = OUT_DIR / f"clf_{VERSION}_vs_ndvi_per_lgu_{year}_t{int(pick_t * 100):02d}.csv"
    with out_csv.open("w") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)
    print(f"[scan] wrote {out_csv.name}")

    OUT_VIS_DIR.mkdir(parents=True, exist_ok=True)
    stats_by_lgu = {r["lgu_name"]: r for r in rows}
    panel_args = []
    for f in fc["features"]:
        name = f["properties"]["lgu_name"]
        if name not in stats_by_lgu:
            continue
        panel_args.append(
            (
                name,
                f["geometry"],
                ndvi_mask_full,
                clf_mask,
                ncr_mask,
                rgb,
                transform,
                height,
                width,
                pixel_area_m2,
                year,
                pick_t,
                OUT_VIS_DIR,
                stats_by_lgu[name],
                VERSION,
            )
        )
    print(f"[scan] rendering {len(panel_args)} per-LGU panels (parallel x{N_THREADS})")
    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        out_paths = list(ex.map(render_lgu_panel, panel_args))
    print(f"[scan] wrote {len([p for p in out_paths if p])} panels to {OUT_VIS_DIR.relative_to(ROOT)}/")

    ncr_v0 = round(100 * (ndvi_mask_full & ncr_mask).sum() / n_ncr, 3)
    ncr_clf = round(100 * (clf_mask & ncr_mask).sum() / n_ncr, 3)
    ncr_shared = round(100 * (ndvi_mask_full & clf_mask & ncr_mask).sum() / n_ncr, 3)
    ncr_new = round(100 * (~ndvi_mask_full & clf_mask & ncr_mask).sum() / n_ncr, 3)
    ncr_dropped = round(100 * (ndvi_mask_full & ~clf_mask & ncr_mask).sum() / n_ncr, 3)
    print(f"\n[scan] === NCR {year} @ t={pick_t}  (clf_{VERSION}) ===")
    print(f"  baseline (NDVI v0)    {ncr_v0:>6.2f}%")
    print(f"  clf_{VERSION} (CLIP+LR)    {ncr_clf:>6.2f}%")
    print(f"  shared (confirmed)    {ncr_shared:>6.2f}%")
    print(f"  NEW (added by clf)    {ncr_new:>6.2f}%")
    print(f"  dropped (trimmed)     {ncr_dropped:>6.2f}%")


if __name__ == "__main__":
    import argparse

    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int, default=None)
    ap.add_argument("--all-years", action="store_true", help="Scan every epoch in ALL_YEARS sequentially")
    a = ap.parse_args()
    if a.all_years:
        for y in ALL_YEARS:
            print(f"\n========== year={y} ==========")
            scan(y)
    else:
        scan(a.year or YEAR)
