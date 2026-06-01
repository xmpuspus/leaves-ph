"""Crop a square tile from data/composites/s2_rgb_<year>.tif centred on every
labelled (lat, lon) in detection/bootstrap/osm_tree_labels.jsonl.

The S2 RGB composite is at ~30 m/pixel, EPSG:4326. We sample an
8x8-pixel window (~240 m on a side, the scan-grid spacing the SolarMap
playbook uses) and resize to 224x224 for CLIP ViT-Large-patch14.

Output: detection/scan/tiles/<lgu_name>/<src>_<idx>.jpg
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import rasterio
from PIL import Image

ROOT = Path(__file__).resolve().parents[2]
LABELS_JSONL = ROOT / "detection" / "bootstrap" / "osm_tree_labels.jsonl"
RGB_TIF = ROOT / "data" / "composites" / "s2_rgb_2024.tif"
TILES_DIR = ROOT / "detection" / "scan" / "tiles"

WINDOW_PX = 8  # 8 x 30 m = 240 m on a side
TILE_PX = 224  # CLIP-native resolution


def stretch_band(b: np.ndarray) -> np.ndarray:
    valid = b > 0
    if not valid.any():
        return np.zeros_like(b, dtype=np.uint8)
    p2, p98 = np.percentile(b[valid], (2, 98))
    out = np.clip((b.astype(np.float32) - p2) / max(p98 - p2, 1) * 255, 0, 255)
    return out.astype(np.uint8)


def main() -> int:
    if not RGB_TIF.exists():
        print(f"[tiles] missing {RGB_TIF}", file=sys.stderr)
        return 1
    labels = [json.loads(line) for line in LABELS_JSONL.open()]
    print(f"[tiles] {len(labels)} labels to crop")
    with rasterio.open(RGB_TIF) as src:
        bands = src.read([1, 2, 3])  # 3 x H x W (red, green, blue)
        transform = src.transform
        height, width = src.height, src.width
        left, _bottom, _right, top = src.bounds
    # Per-band p2-p98 stretch once for the whole composite (consistent across tiles)
    rgb_stretched = np.stack([stretch_band(bands[i]) for i in range(3)], axis=-1)
    print(f"[tiles] composite stretched ({height}x{width})")

    TILES_DIR.mkdir(parents=True, exist_ok=True)
    by_src_idx: dict[str, int] = {}
    skipped = 0
    written = 0
    for lab in labels:
        lat, lon = lab["lat"], lab["lon"]
        # Convert (lat, lon) -> (row, col) via affine
        col = int((lon - left) / (transform.a))
        row = int((lat - top) / (transform.e))  # e is negative
        half = WINDOW_PX // 2
        r0, r1 = row - half, row + half
        c0, c1 = col - half, col + half
        if r0 < 0 or c0 < 0 or r1 > height or c1 > width:
            skipped += 1
            continue
        crop = rgb_stretched[r0:r1, c0:c1, :]
        if crop.shape[:2] != (WINDOW_PX, WINDOW_PX):
            skipped += 1
            continue
        # Upsample to 224x224 (NEAREST keeps the pixel grid recognisable to CLIP)
        img = Image.fromarray(crop, mode="RGB").resize((TILE_PX, TILE_PX), Image.NEAREST)
        lgu_dir = TILES_DIR / lab["lgu_name"].replace(" ", "_")
        lgu_dir.mkdir(parents=True, exist_ok=True)
        src_key = lab["src"]
        idx = by_src_idx.get(src_key, 0)
        by_src_idx[src_key] = idx + 1
        out_path = lgu_dir / f"{src_key}_{idx:05d}_y{lab['label']}.jpg"
        img.save(out_path, quality=88)
        written += 1
    print(f"[tiles] wrote {written} tiles, skipped {skipped} (out of bounds)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
