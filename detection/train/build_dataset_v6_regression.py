"""v6 dataset: per-tile (CLIP embedding -> Meta canopy-fraction) for regression.

Walk the entire 21,460-tile scan grid, embed each with CLIP ViT-Large, compute
the Meta v2 >5m canopy fraction as the regression target. Saved as
dataset_v6.npz with float32 y in [0, 1].

Used by train_v6_regressor.py to produce a continuous canopy-density head
(predicted canopy fraction per 240m tile), the v6 deliverable on top of the
binary clf_v5 classifier.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import rasterio
import torch
from rasterio.warp import Resampling, reproject
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parents[2]
RGB_TIF = ROOT / "data" / "composites" / "s2_rgb_2024.tif"
META_TIF = ROOT / "data" / "meta" / "canopy_height_ncr.tif"
DS_V6 = ROOT / "detection" / "train" / "dataset_v6.npz"

WINDOW_PX = 8
TILE_PX = 224
META_HEIGHT_M = 5.0
MODEL_ID = "openai/clip-vit-large-patch14"
BATCH = 256
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
    if not RGB_TIF.exists() or not META_TIF.exists():
        print("[v6-build] missing inputs", file=sys.stderr)
        return 1
    with rasterio.open(RGB_TIF) as src:
        bands = src.read([1, 2, 3])
        transform = src.transform
        height, width = src.height, src.width
        crs = src.crs
    rgb = np.stack([stretch_band(bands[i]) for i in range(3)], axis=-1)

    with rasterio.open(META_TIF) as src:
        meta_h = src.read(1)
        meta_t = src.transform
        meta_crs = src.crs
    meta_binary = (meta_h.astype(np.float32) >= META_HEIGHT_M).astype(np.float32)
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
    print(f"[v6-build] Meta >5m fraction reprojected, NCR mean {meta_frac.mean():.3f}")

    rows_c = np.arange(WINDOW_PX // 2, height - WINDOW_PX // 2, WINDOW_PX)
    cols_c = np.arange(WINDOW_PX // 2, width - WINDOW_PX // 2, WINDOW_PX)
    half = WINDOW_PX // 2

    # Pre-stack crops + target
    total_tiles = len(rows_c) * len(cols_c)
    crops = np.zeros((total_tiles, TILE_PX, TILE_PX, 3), dtype=np.uint8)
    y_reg = np.zeros(total_tiles, dtype=np.float32)
    k = 0
    for r in rows_c:
        for c in cols_c:
            ndvi_tile = meta_frac[r - half : r + half, c - half : c + half]  # reusing var name
            crop = rgb[r - half : r + half, c - half : c + half, :]
            if crop.shape[:2] != (WINDOW_PX, WINDOW_PX):
                continue
            crops[k] = upsample_block(crop)
            y_reg[k] = float(ndvi_tile.mean())  # per-tile Meta-fraction target
            k += 1
    crops = crops[:k]
    y_reg = y_reg[:k]
    print(
        f"[v6-build] {k} tiles, target mean {y_reg.mean():.3f}, "
        f"target distribution: <0.05={float((y_reg < 0.05).sum()) / k:.2f}, "
        f"[0.05,0.3]={float(((y_reg >= 0.05) & (y_reg < 0.30)).sum()) / k:.2f}, "
        f">=0.30={float((y_reg >= 0.30).sum()) / k:.2f}"
    )

    # Embed via CLIP
    print(f"[v6-build] embedding via CLIP on {DEVICE}, batch={BATCH}")
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
    n = k
    X = np.zeros((n, 768), dtype=np.float32)
    t0 = time.time()
    with torch.no_grad():
        for i in range(0, n, BATCH):
            j = min(i + BATCH, n)
            arr = crops[i:j].astype(np.float32) / 255.0
            t = torch.from_numpy(arr).permute(0, 3, 1, 2).to(DEVICE)
            t = (t - img_mean) / img_std
            if DEVICE in ("mps", "cuda"):
                t = t.to(dtype=torch.bfloat16)
            emb = model.get_image_features(pixel_values=t)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            X[i:j] = emb.float().cpu().numpy()
            if (i // BATCH) % 8 == 0 or j == n:
                print(f"  embed {j}/{n}  ({j / (time.time() - t0):.0f} tiles/s)")

    np.savez_compressed(DS_V6, X=X, y=y_reg)
    print(
        f"[v6-build] wrote {DS_V6.relative_to(ROOT)}  X={X.shape}  y range [{y_reg.min():.3f}, {y_reg.max():.3f}]"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
