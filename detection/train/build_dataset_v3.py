"""Step 1 of v3 iteration: extend dataset_v2 with ESA WorldCover teacher labels.

Mirrors SolarMap detection/train/build_dataset_v3.py (label cleanup + hard negs).

Sampling strategy:
  - At each candidate tile centre on the S2-RGB grid, look up the ESA-class
    distribution in the corresponding 8x8-S2-pixel window (~24x24 ESA pixels).
  - Keep tiles where >= 0.80 of pixels belong to one majority class.
  - Stratified sample per class:
      class 10 (tree cover)     -> label 1            n_tree
      class 50 (built-up)       -> label 0 (hard neg) n_built
      class 80 (water)          -> label 0 (hard neg) n_water
      class 30 (grassland)      -> label 0 (hard neg) n_grass
      class 40 (cropland)       -> label 0 (hard neg) n_crop

Crop S2-RGB tiles centred on each kept point, embed with the same
CLIP ViT-Large-patch14 used for dataset_v2, then merge with the existing
dataset_v2.npz embeddings + labels into dataset_v3.npz.

This is automatic (ESA is the teacher), no manual review.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
import torch
from rasterio.warp import Resampling, reproject
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parents[2]
RGB_TIF = ROOT / "data" / "composites" / "s2_rgb_2024.tif"
ESA_TIF = ROOT / "data" / "esa" / "worldcover_2021.tif"
LGU_GEOJSON = ROOT / "data" / "lgu" / "ncr_lgu.geojson"
DS_V2 = ROOT / "detection" / "train" / "dataset_v2.npz"
DS_V3 = ROOT / "detection" / "train" / "dataset_v3.npz"

WINDOW_PX = 8
TILE_PX = 224
PURITY = 0.80
N_PER_CLASS = {
    10: 1500,  # trees (label 1)
    50: 1500,  # built-up (label 0)
    80: 800,  # water (label 0)
    30: 500,  # grassland (label 0)
    40: 300,  # cropland (label 0)
}
MODEL_ID = "openai/clip-vit-large-patch14"
BATCH = 256
N_THREADS = 10
SEED = 42
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
    if not DS_V2.exists():
        print(f"[v3-build] missing {DS_V2}", file=sys.stderr)
        return 1
    rng = np.random.default_rng(SEED)

    print("[v3-build] loading S2 RGB + ESA WorldCover")
    with rasterio.open(RGB_TIF) as src:
        bands = src.read([1, 2, 3])
        rgb_transform = src.transform
        rgb_height, rgb_width = src.height, src.width
        rgb_crs = src.crs
    rgb = np.stack([stretch_band(bands[i]) for i in range(3)], axis=-1)

    # Reproject ESA onto the S2 RGB grid (so 1 S2 pixel maps to 1 ESA pixel)
    with rasterio.open(ESA_TIF) as src:
        esa_src = src.read(1)
        esa_t = src.transform
        esa_crs = src.crs
    esa_aligned = np.zeros((rgb_height, rgb_width), dtype=np.uint8)
    reproject(
        source=esa_src,
        destination=esa_aligned,
        src_transform=esa_t,
        src_crs=esa_crs,
        dst_transform=rgb_transform,
        dst_crs=rgb_crs,
        resampling=Resampling.mode,
    )
    print(f"[v3-build] ESA aligned to S2 grid {esa_aligned.shape}")

    # Tile-grid candidates (same spacing as scan)
    rows_c = np.arange(WINDOW_PX // 2, rgb_height - WINDOW_PX // 2, WINDOW_PX)
    cols_c = np.arange(WINDOW_PX // 2, rgb_width - WINDOW_PX // 2, WINDOW_PX)
    half = WINDOW_PX // 2

    # For every tile, compute the majority ESA class + its purity
    print(f"[v3-build] scoring {len(rows_c) * len(cols_c)} candidate tiles")
    candidates: dict[int, list[tuple[int, int, float]]] = {c: [] for c in N_PER_CLASS}
    for r in rows_c:
        for c in cols_c:
            window = esa_aligned[r - half : r + half, c - half : c + half]
            if window.size == 0:
                continue
            vals, counts = np.unique(window, return_counts=True)
            top = counts.argmax()
            cls = int(vals[top])
            purity = float(counts[top]) / window.size
            if cls in candidates and purity >= PURITY:
                candidates[cls].append((int(r), int(c), purity))

    # Stratified sample N per class
    print("[v3-build] candidate pool per class:")
    sampled: list[tuple[int, int, int]] = []  # (r, c, label)
    for cls, want in N_PER_CLASS.items():
        pool = candidates[cls]
        print(f"  class {cls:>3} -> pool {len(pool):>6}, want {want}")
        if not pool:
            continue
        idx = rng.choice(len(pool), size=min(want, len(pool)), replace=False)
        label = 1 if cls == 10 else 0
        for i in idx:
            r, c, _ = pool[i]
            sampled.append((r, c, label))
    rng.shuffle(sampled)
    print(f"[v3-build] sampled {len(sampled)} new tiles")

    # Crop tiles (10-thread)
    print(f"[v3-build] cropping (x{N_THREADS})")

    def crop_one(args):
        r, c, lab = args
        cr = rgb[r - half : r + half, c - half : c + half, :]
        if cr.shape[:2] != (WINDOW_PX, WINDOW_PX):
            return None
        return upsample_block(cr), lab

    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        results = [r for r in ex.map(crop_one, sampled) if r is not None]
    new_crops = np.stack([r[0] for r in results], axis=0)
    new_labels = np.array([r[1] for r in results], dtype=np.int8)
    new_src = np.array([f"esa_class_{lab}" for lab in new_labels])
    print(
        f"[v3-build] new tile array {new_crops.shape}  pos={int((new_labels == 1).sum())} neg={int((new_labels == 0).sum())}"
    )

    # Embed
    print(f"[v3-build] embedding via CLIP on {DEVICE}, batch={BATCH}")
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
            if (i // BATCH) % 4 == 0 or j == n:
                print(f"  embed {j}/{n}  ({j / (time.time() - t0):.0f} tiles/s)")

    # Merge with dataset_v2
    print("[v3-build] merging with dataset_v2")
    d2 = np.load(DS_V2, allow_pickle=True)
    X = np.concatenate([d2["X"], new_X], axis=0)
    y = np.concatenate([d2["y"].astype(int), new_labels.astype(int)], axis=0)
    src = np.concatenate([d2["src"].astype(str), new_src], axis=0)
    lgu = np.concatenate([d2["lgu"].astype(str), np.array(["scan"] * n)], axis=0)
    path = np.concatenate([d2["path"].astype(str), np.array(["esa_teacher"] * n)], axis=0)
    np.savez_compressed(DS_V3, X=X, y=y, src=src, lgu=lgu, path=path)
    print(f"[v3-build] wrote {DS_V3.relative_to(ROOT)}")
    print(f"  total: X={X.shape}  pos={int((y == 1).sum())}  neg={int((y == 0).sum())}")
    print("  by src: " + ", ".join(f"{s}={(src == s).sum()}" for s in sorted(set(src))))
    return 0


if __name__ == "__main__":
    sys.exit(main())
