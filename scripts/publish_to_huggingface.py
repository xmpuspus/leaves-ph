#!/usr/bin/env python3
"""Publish Leaves.PH artefacts to HuggingFace as a dataset + model card.

Mirrors solar-map-ph/scripts/publish_to_huggingface.py.

What lands on HuggingFace:
  - README.md dataset card (license, tags, cross-links; generated here)
  - Per-LGU canopy series CSV (canonical)
  - BENCHMARKS.md (with v0/v3 comparison)
  - MODEL_CARD.md
  - detection/train/clf_v3.joblib (calibrated head)
  - detection/train/clf_v3_metrics.json
  - detection/scan/clf_v3_probs_2024.tif (per-pixel probability raster)
  - detection/scan/clf_v3_vs_ndvi_per_lgu_2024_t60.csv (per-LGU comparison)
  - detection/scan/validation_v3/*.png (per-LGU visual validation)

Requires HUGGINGFACE_HUB_TOKEN in env.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ID = "xmpuspus/leaves-ph"
DOI = "10.5281/zenodo.20470306"


def dataset_card(version: str) -> str:
    """Dataset README with HF frontmatter.

    The viewer is disabled on purpose: this repo is a collection of published
    artefacts (CSVs, GeoJSON-adjacent series, model card, validation panels),
    not a single train/validation table, so the auto-detected split viewer has
    nothing coherent to render. Numbers live in the uploaded BENCHMARKS.md and
    MODEL_CARD.md so they are stated in exactly one place.
    """
    return f"""---
license: cc-by-4.0
language:
  - en
pretty_name: "Leaves.PH: Metro Manila tree-canopy series"
tags:
  - remote-sensing
  - urban-canopy
  - sentinel-2
  - metro-manila
  - geospatial
viewer: false
---

# Leaves.PH: Metro Manila tree-canopy series

Open per-LGU and per-barangay annual tree-canopy estimates for the 17 LGUs of
Metro Manila (2019 to 2026), measured from Sentinel-2 imagery with a
human-calibrated classifier. Canopy here is a dense-vegetation proxy, not a
pixel-exact tree census. Read each year as a cross-sectional snapshot, not a
validated change series.

## What is in this repo

- `per_lgu/per_lgu_canopy_2019_2026.csv`, `per_barangay/per_barangay_canopy_2019_2026_model.csv`: the published canopy series.
- `MODEL_CARD.md`, `BENCHMARKS.md`, `RESULTS.md`: accuracy, intended use, known biases, and the 656-label evaluation. All metrics live here.
- `canopy_model/`: the published classifier, its 656 manual gold labels, and the ablation it was chosen from.
- `validation_v3/*.png`: per-LGU visual validation panels.

The CLIP detection artefacts are a separate research track (in optimization) and
are not the source of any published figure.

## Links

- Code and full methodology: https://github.com/xmpuspus/leaves-ph
- Interactive map: https://leaves.ph
- Model repository: https://huggingface.co/xmpuspus/leaves-ph
- DOI: https://doi.org/{DOI}

## License

Data: CC-BY-4.0. Code (in the GitHub repository): MIT. Upstream inputs retain
their own licenses (Copernicus Sentinel-2, Hansen GFC, ESA WorldCover, Google
Dynamic World, Meta Canopy Height, OpenStreetMap, PSA); see the repository
LICENSE for the required attribution string.

## Citation

```
@software{{puspus_leaves_ph_2026,
  title  = {{Leaves.PH: open tree-canopy measurement for Metro Manila}},
  author = {{Puspus, Xavier}},
  year   = {{2026}},
  version = {{{version}}},
  doi    = {{{DOI}}},
  url    = {{https://github.com/xmpuspus/leaves-ph}}
}}
```
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="semver, e.g. 0.6.0")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("HUGGINGFACE_HUB_TOKEN")
    if not token and not args.dry_run:
        print("[hf] FAIL: HUGGINGFACE_HUB_TOKEN missing", file=sys.stderr)
        return 1

    artefacts = [
        # Canonical published series.
        ROOT / "data" / "per_lgu" / "per_lgu_canopy_2019_2026.csv",
        ROOT / "data" / "per_barangay" / "per_barangay_canopy_2019_2026_model.csv",
        ROOT / "BENCHMARKS.md",
        ROOT / "MODEL_CARD.md",
        # Published human-calibrated canopy model (source of every site figure)
        # plus the 656 hand labels and the ablation it was chosen from.
        ROOT / "data" / "canopy_model" / "canopy_clf.joblib",
        ROOT / "data" / "canopy_model" / "canopy_clf_meta.json",
        ROOT / "data" / "canopy_model" / "master_labels.csv",
        ROOT / "data" / "canopy_model" / "master_metadata.csv",
        ROOT / "data" / "canopy_model" / "model_comparison.json",
        ROOT / "data" / "canopy_model" / "rich_feature_result.json",
        ROOT / "data" / "canopy_model" / "RESULTS.md",
        # CLIP detection model (separate research track, kept for completeness).
        ROOT / "detection" / "train" / "clf_v3.joblib",
        ROOT / "detection" / "train" / "clf_v3_metrics.json",
        ROOT / "detection" / "scan" / "clf_v3_probs_2024.tif",
        ROOT / "detection" / "scan" / "clf_v3_vs_ndvi_per_lgu_2024_t60.csv",
        ROOT / "detection" / "scan" / "clf_v3_threshold_sweep_2024.json",
    ]
    panels = sorted((ROOT / "detection" / "scan" / "validation_v3").glob("*.png"))
    artefacts.extend(panels)

    missing = [p for p in artefacts if not p.exists()]
    if missing:
        print(f"[hf] FAIL: {len(missing)} missing artefact(s):", file=sys.stderr)
        for p in missing:
            print(f"    {p.relative_to(ROOT)}", file=sys.stderr)
        return 1

    print(f"[hf] {len(artefacts)} artefacts ready for push to {REPO_ID} @ v{args.version}")
    for p in artefacts[:20]:
        size_kb = p.stat().st_size / 1024
        rel_str = str(p.relative_to(ROOT))
        print(f"  {rel_str:60s}  {size_kb:>8.1f} KB")
    if len(artefacts) > 20:
        print(f"  ... and {len(artefacts) - 20} more (validation panels)")

    if args.dry_run:
        print("[hf] dry-run; not uploading")
        return 0

    try:
        from huggingface_hub import HfApi, create_repo
    except ImportError:
        print("[hf] FAIL: pip install huggingface_hub", file=sys.stderr)
        return 1

    api = HfApi(token=token)
    create_repo(REPO_ID, repo_type="dataset", exist_ok=True, token=token)

    # Dataset card first, so the repo renders with a license + cross-links.
    print("[hf] uploading README.md (dataset card)")
    api.upload_file(
        path_or_fileobj=io.BytesIO(dataset_card(args.version).encode("utf-8")),
        path_in_repo="README.md",
        repo_id=REPO_ID,
        repo_type="dataset",
        token=token,
        commit_message=f"Leaves.PH v{args.version}: dataset card",
    )

    for p in artefacts:
        rel = p.relative_to(ROOT)
        print(f"[hf] uploading {rel}")
        api.upload_file(
            path_or_fileobj=str(p),
            path_in_repo=str(rel),
            repo_id=REPO_ID,
            repo_type="dataset",
            token=token,
            commit_message=f"Leaves.PH v{args.version}: {rel.name}",
        )
    print(f"[hf] DONE: https://huggingface.co/datasets/{REPO_ID}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
