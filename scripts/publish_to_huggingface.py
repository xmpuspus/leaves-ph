#!/usr/bin/env python3
"""Publish Leaves.PH artefacts to HuggingFace as a dataset + model card.

Mirrors solar-map-ph/scripts/publish_to_huggingface.py.

What lands on HuggingFace:
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
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPO_ID = "xmpuspus/leaves-ph"


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
