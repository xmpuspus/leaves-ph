"""v4 active-learning iteration: Meta-oracle hard-negative mining.

The SolarMap v3 → v4 cycle eyeballs model false positives in scan tiles and
labels them as hard negatives. Without a human-in-the-loop available
mid-pipeline, this script substitutes Meta Canopy Height v2 (1m AI canopy
height regression) as the oracle:

  - 240m tile with mean Meta canopy height > 5m  -> CONFIRMED canopy
  - 240m tile with mean Meta canopy height < 2m  -> CONFIRMED not-canopy

This is the same teacher SolarMap uses for the calibration layer : we just
extend it into the active-learning loop.

Mining strategy (using saved clf_v3_probs_2024.tif + canopy_2024.tif):

  Category 1: clf_v3 NEW with high confidence (prob > 0.7, ndvi v0 == 0)
    - Meta > 5m -> TP (positive label)
    - Meta < 2m -> FP (negative label, the v4 hard negative)
  Category 2: clf_v3 DROPPED with low confidence (prob < 0.3, ndvi v0 == 1)
    - Meta > 5m -> FN (positive label, NDVI was right after all)
    - Meta < 2m -> TN (negative label, NDVI was wrong; both agree to drop)

Stratified sample per category per LGU. Re-embed via CLIP, concat with
dataset_v3, dump dataset_v4.npz.
"""

from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import torch
from rasterio.features import geometry_mask
from rasterio.warp import Resampling, reproject
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parents[2]
RGB_TIF = ROOT / "data" / "composites" / "s2_rgb_2024.tif"
NDVI_TIF = ROOT / "data" / "composites" / "canopy_2024.tif"
META_TIF = ROOT / "data" / "meta" / "canopy_height_ncr.tif"
PROBS_TIF = ROOT / "detection" / "scan" / "clf_v3_probs_2024.tif"
LGU_GEOJSON = ROOT / "data" / "lgu" / "ncr_lgu.geojson"
DS_V3 = ROOT / "detection" / "train" / "dataset_v3.npz"
DS_V4 = ROOT / "detection" / "train" / "dataset_v4.npz"

WINDOW_PX = 8
TILE_PX = 224
PROB_HIGH = 0.50
PROB_LOW = 0.50
META_FRAC_HIGH = 0.20  # tile has at least 20% Meta >5m pixels  -> canopy
META_FRAC_LOW = 0.03  # tile has at most  3% Meta >5m pixels   -> not canopy
META_HIGHT_PIXEL_M = 5.0
N_PER_CATEGORY_PER_LGU = 100  # bigger budget; v4 needs density
MODEL_ID = "openai/clip-vit-large-patch14"
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


def main() -> int:
    for pth in (RGB_TIF, NDVI_TIF, META_TIF, PROBS_TIF, DS_V3):
        if not pth.exists():
            print(f"[v4-build] missing {pth}", file=sys.stderr)
            return 1

    rng = np.random.default_rng(4242)

    print("[v4-build] loading rasters")
    with rasterio.open(RGB_TIF) as src:
        bands = src.read([1, 2, 3])
        transform = src.transform
        height, width = src.height, src.width
        crs = src.crs
    rgb = np.stack([stretch_band(bands[i]) for i in range(3)], axis=-1)

    with rasterio.open(NDVI_TIF) as src:
        ndvi_mask = src.read(1).astype(bool)
    with rasterio.open(PROBS_TIF) as src:
        probs_full = src.read(1)

    # Reproject Meta canopy height >5m BINARY mask onto the S2/Hansen grid using
    # FRACTION-OF-PIXELS semantics. We do this by first computing the >5m binary
    # at native Meta resolution, then averaging on reproject (gives the fraction
    # of >5m pixels per S2 pixel and, by extension, per 240m tile).
    with rasterio.open(META_TIF) as src:
        meta_h = src.read(1)
        meta_t = src.transform
        meta_crs = src.crs
    meta_binary = (meta_h.astype(np.float32) >= META_HIGHT_PIXEL_M).astype(np.float32)
    meta_frac = np.zeros((height, width), dtype=np.float32)
    reproject(
        source=meta_binary,
        destination=meta_frac,
        src_transform=meta_t,
        src_crs=meta_crs,
        dst_transform=transform,
        dst_crs=crs,
        resampling=Resampling.average,
    )
    meta_aligned = meta_frac  # 0..1, fraction of Meta >5m pixels at each S2 pixel
    print(
        f"[v4-build] Meta >5m fraction aligned, mean {meta_aligned.mean():.3f}, max {meta_aligned.max():.3f}"
    )

    # Tile centres
    rows_c = np.arange(WINDOW_PX // 2, height - WINDOW_PX // 2, WINDOW_PX)
    cols_c = np.arange(WINDOW_PX // 2, width - WINDOW_PX // 2, WINDOW_PX)
    half = WINDOW_PX // 2

    fc = json.loads(LGU_GEOJSON.read_text())

    # Pre-compute per-tile summary stats
    print(f"[v4-build] scoring {len(rows_c) * len(cols_c)} candidate tiles")
    candidates_by_lgu_cat: dict[str, dict[str, list[tuple[int, int]]]] = {}
    for f in fc["features"]:
        name = f["properties"]["lgu_name"].replace(" ", "_")
        candidates_by_lgu_cat[name] = {
            # A: clf says yes, NDVI says no, Meta says yes  -> POSITIVE (model adds, Meta confirms)
            "a_meta_confirms_new": [],
            # B: clf says yes, NDVI says no, Meta says no   -> NEGATIVE (model FP)
            "b_meta_rejects_new": [],
            # C: clf says yes, NDVI says yes, Meta says no  -> NEGATIVE (NDVI FP, clf agrees but Meta disagrees)
            "c_meta_rejects_shared": [],
            # D: clf says no, NDVI says yes, Meta says yes  -> POSITIVE (model FN)
            "d_meta_confirms_dropped": [],
            # E: clf says no, NDVI says yes, Meta says no   -> NEGATIVE (NDVI FP confirmed)
            "e_meta_rejects_dropped": [],
            # F: clf says no, NDVI says no, Meta says yes   -> POSITIVE (both missed; Meta finds)
            "f_meta_only_positive": [],
        }
    # Build per-LGU pixel masks
    lgu_pix_by_name = {}
    for f in fc["features"]:
        name = f["properties"]["lgu_name"].replace(" ", "_")
        lgu_pix_by_name[name] = geometry_mask(
            [f["geometry"]], out_shape=(height, width), transform=transform, invert=True
        )

    for r in rows_c:
        for c in cols_c:
            ndvi_tile = ndvi_mask[r - half : r + half, c - half : c + half]
            prob_tile = probs_full[r - half : r + half, c - half : c + half]
            meta_tile = meta_aligned[r - half : r + half, c - half : c + half]
            if ndvi_tile.size != WINDOW_PX * WINDOW_PX:
                continue
            mean_ndvi = float(ndvi_tile.mean())
            mean_prob = float(prob_tile.mean())
            mean_meta_frac = float(meta_tile.mean())  # avg fraction of Meta >5m in this tile
            # Find which LGU
            lgu_name = None
            for name, lgu_pix in lgu_pix_by_name.items():
                if lgu_pix[r, c]:
                    lgu_name = name
                    break
            if lgu_name is None:
                continue
            cats = candidates_by_lgu_cat[lgu_name]
            clf_yes = mean_prob >= 0.5
            ndvi_yes = mean_ndvi >= 0.5
            meta_yes = mean_meta_frac >= META_FRAC_HIGH
            meta_no = mean_meta_frac < META_FRAC_LOW
            key = (int(r), int(c))
            if clf_yes and not ndvi_yes:
                if meta_yes:
                    cats["a_meta_confirms_new"].append(key)
                elif meta_no:
                    cats["b_meta_rejects_new"].append(key)
            elif clf_yes and ndvi_yes:
                if meta_no:
                    cats["c_meta_rejects_shared"].append(key)
            elif not clf_yes and ndvi_yes:
                if meta_yes:
                    cats["d_meta_confirms_dropped"].append(key)
                elif meta_no:
                    cats["e_meta_rejects_dropped"].append(key)
            elif not clf_yes and not ndvi_yes:
                if meta_yes:
                    cats["f_meta_only_positive"].append(key)

    # Stratified sample per LGU per category
    print(f"[v4-build] sampling up to {N_PER_CATEGORY_PER_LGU} per (LGU, category)")
    sampled: list[tuple[int, int, int, str, str]] = []  # (r, c, label, src, lgu)
    pool_summary = {}
    POS_CATS = {"a_meta_confirms_new", "d_meta_confirms_dropped", "f_meta_only_positive"}
    for lgu_name, cats in candidates_by_lgu_cat.items():
        for cat, pool in cats.items():
            label = 1 if cat in POS_CATS else 0
            src_tag = f"v4_{cat}_{lgu_name}"
            n_want = min(N_PER_CATEGORY_PER_LGU, len(pool))
            pool_summary.setdefault(cat, 0)
            pool_summary[cat] += len(pool)
            if n_want == 0:
                continue
            idx = rng.choice(len(pool), size=n_want, replace=False)
            for i in idx:
                r, c = pool[i]
                sampled.append((r, c, label, src_tag, lgu_name))
    print("[v4-build] candidate pool by category:")
    for cat, n in sorted(pool_summary.items()):
        print(f"  {cat:>10s}  {n:>6}")
    print(f"[v4-build] sampled {len(sampled)} tiles total")

    # Crop tiles (10-thread)
    def crop_one(args):
        r, c, lab, sg, lgu = args
        cr = rgb[r - half : r + half, c - half : c + half, :]
        if cr.shape[:2] != (WINDOW_PX, WINDOW_PX):
            return None
        return upsample_block(cr), lab, sg, lgu

    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        results = [r for r in ex.map(crop_one, sampled) if r is not None]
    if not results:
        print("[v4-build] no tiles sampled; v3 already covers the space", file=sys.stderr)
        return 0
    new_crops = np.stack([r[0] for r in results], axis=0)
    new_labels = np.array([r[1] for r in results], dtype=np.int8)
    new_srcs = np.array([r[2] for r in results])
    new_lgus = np.array([r[3] for r in results])
    print(
        f"[v4-build] cropped {len(results)} tiles  pos={int((new_labels == 1).sum())} neg={int((new_labels == 0).sum())}"
    )

    # Embed
    print(f"[v4-build] embedding via CLIP on {DEVICE}, batch={BATCH}")
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
    n = len(new_crops)
    new_X = np.zeros((n, 768), dtype=np.float32)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, n, BATCH):
            j = min(i + BATCH, n)
            arr = new_crops[i:j].astype(np.float32) / 255.0
            t = torch.from_numpy(arr).permute(0, 3, 1, 2).to(DEVICE)
            t = (t - img_mean) / img_std
            if DEVICE in ("mps", "cuda"):
                t = t.to(dtype=torch.bfloat16)
            emb = model.get_image_features(pixel_values=t)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            new_X[i:j] = emb.float().cpu().numpy()
            print(f"  embed {j}/{n}  ({j / (time.time() - t0):.0f} tiles/s)")

    # Merge with dataset_v3
    d3 = np.load(DS_V3, allow_pickle=True)
    X = np.concatenate([d3["X"], new_X], axis=0)
    y = np.concatenate([d3["y"].astype(int), new_labels.astype(int)], axis=0)
    src = np.concatenate([d3["src"].astype(str), new_srcs], axis=0)
    lgu = np.concatenate([d3["lgu"].astype(str), new_lgus], axis=0)
    path = np.concatenate([d3["path"].astype(str), np.array(["meta_oracle"] * n)], axis=0)
    np.savez_compressed(DS_V4, X=X, y=y, src=src, lgu=lgu, path=path)
    print(f"[v4-build] wrote {DS_V4.relative_to(ROOT)}")
    print(f"  total: X={X.shape}  pos={int((y == 1).sum())}  neg={int((y == 0).sum())}")
    new_categories = {s: int((new_srcs == s).sum()) for s in sorted(set(new_srcs))}
    by_cat = {}
    for s, n in new_categories.items():
        cat = s.split("_")[1] + "_" + s.split("_")[2]
        by_cat[cat] = by_cat.get(cat, 0) + n
    print("[v4-build] new labels by category: " + ", ".join(f"{k}={v}" for k, v in by_cat.items()))
    return 0


if __name__ == "__main__":
    sys.exit(main())
