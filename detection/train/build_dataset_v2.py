"""Step 1 of the SolarMap-style CLIP+LR head.

Walk detection/scan/tiles/<lgu>/<src>_<idx>_y{0,1}.jpg, embed each with
openai/clip-vit-large-patch14 (768-dim), stack into X, parse y and src
from filenames, dump to detection/train/dataset_v2.npz.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import numpy as np
import torch
from PIL import Image
from transformers import CLIPModel, CLIPProcessor

ROOT = Path(__file__).resolve().parents[2]
TILES_DIR = ROOT / "detection" / "scan" / "tiles"
OUT_NPZ = ROOT / "detection" / "train" / "dataset_v2.npz"

MODEL_ID = "openai/clip-vit-large-patch14"
BATCH = 64
DEVICE = "mps" if torch.backends.mps.is_available() else ("cuda" if torch.cuda.is_available() else "cpu")
FNAME_RE = re.compile(r"^(?P<src>[a-z]+)_(?P<idx>\d+)_y(?P<y>[01])\.jpg$")


def list_tiles() -> list[tuple[Path, str, int, str]]:
    rows: list[tuple[Path, str, int, str]] = []
    for lgu_dir in sorted(TILES_DIR.iterdir()):
        if not lgu_dir.is_dir():
            continue
        lgu = lgu_dir.name
        for p in sorted(lgu_dir.iterdir()):
            m = FNAME_RE.match(p.name)
            if not m:
                continue
            rows.append((p, m.group("src"), int(m.group("y")), lgu))
    return rows


def main() -> int:
    tiles = list_tiles()
    if not tiles:
        print("[v2-build] no tiles found", file=sys.stderr)
        return 1
    print(f"[v2-build] {len(tiles)} tiles  device={DEVICE}")

    processor = CLIPProcessor.from_pretrained(MODEL_ID, use_fast=True)
    model = CLIPModel.from_pretrained(MODEL_ID).to(DEVICE).eval()

    feats: list[np.ndarray] = []
    ys: list[int] = []
    srcs: list[str] = []
    lgus: list[str] = []
    paths: list[str] = []
    n = 0
    with torch.no_grad():
        for i in range(0, len(tiles), BATCH):
            chunk = tiles[i : i + BATCH]
            imgs = [Image.open(p).convert("RGB") for (p, _, _, _) in chunk]
            inputs = processor(images=imgs, return_tensors="pt")
            inputs = {k: v.to(DEVICE) for k, v in inputs.items()}
            emb = model.get_image_features(**inputs)
            emb = emb / emb.norm(dim=-1, keepdim=True)
            feats.append(emb.cpu().float().numpy())
            ys.extend([t[2] for t in chunk])
            srcs.extend([t[1] for t in chunk])
            lgus.extend([t[3] for t in chunk])
            paths.extend([str(t[0].relative_to(ROOT)) for t in chunk])
            n += len(chunk)
            if n % (BATCH * 4) == 0 or n == len(tiles):
                print(f"  embedded {n}/{len(tiles)}")
    X = np.concatenate(feats, axis=0)
    y = np.array(ys, dtype=np.int8)
    src = np.array(srcs)
    lgu = np.array(lgus)
    path = np.array(paths)
    OUT_NPZ.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(OUT_NPZ, X=X, y=y, src=src, lgu=lgu, path=path)
    print(
        f"[v2-build] wrote {OUT_NPZ.relative_to(ROOT)}  X={X.shape}  pos={(y == 1).sum()}  neg={(y == 0).sum()}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
