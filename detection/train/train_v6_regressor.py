"""Train the v6 continuous canopy-fraction regressor.

Target: per-tile Meta v2 >5m canopy fraction in [0, 1].
Features: CLIP ViT-Large-patch14 embeddings (768d).
Model: Ridge regression. Same C/penalty discipline as the LR classifier.

Outputs:
  detection/train/clf_v6.joblib                 (Ridge regressor)
  detection/train/clf_v6_metrics.json           (MAE, RMSE, R^2 5-fold CV)
  detection/train/clf_v6_residuals_by_bin.json  (residual analysis per target bin)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import Ridge
from sklearn.model_selection import KFold

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v6.npz"
CLF = ROOT / "detection" / "train" / "clf_v6.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v6_metrics.json"
RESIDUALS = ROOT / "detection" / "train" / "clf_v6_residuals_by_bin.json"


def main() -> int:
    if not DS.exists():
        print(f"[v6-train] missing {DS}", file=sys.stderr)
        return 1
    d = np.load(DS, allow_pickle=True)
    X = d["X"]
    y = d["y"].astype(np.float32)
    print(f"[v6-train] X={X.shape}  y range [{y.min():.3f}, {y.max():.3f}], mean {y.mean():.3f}")

    # 5-fold CV
    kf = KFold(n_splits=5, shuffle=True, random_state=42)
    cv_pred = np.zeros_like(y)
    for tr, te in kf.split(X):
        reg = Ridge(alpha=1.0, random_state=42).fit(X[tr], y[tr])
        cv_pred[te] = reg.predict(X[te])
    cv_pred = np.clip(cv_pred, 0.0, 1.0)

    mae = float(np.abs(cv_pred - y).mean())
    rmse = float(np.sqrt(((cv_pred - y) ** 2).mean()))
    ss_res = float(((y - cv_pred) ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else None
    print(f"[v6-train] 5-fold CV: MAE={mae:.4f}  RMSE={rmse:.4f}  R^2={r2:.3f}")

    # Per-bin residual analysis
    bin_edges = np.linspace(0, 1, 11)
    bins = []
    for i in range(10):
        lo, hi = bin_edges[i], bin_edges[i + 1]
        mask = (y >= lo) & (y < hi if i < 9 else y <= hi)
        if mask.sum() == 0:
            continue
        bins.append(
            {
                "target_bin": [float(lo), float(hi)],
                "n": int(mask.sum()),
                "target_mean": float(y[mask].mean()),
                "predicted_mean": float(cv_pred[mask].mean()),
                "mae": float(np.abs(cv_pred[mask] - y[mask]).mean()),
            }
        )
    RESIDUALS.write_text(json.dumps(bins, indent=2))
    print("[v6-train] per-bin (target_lo, target_hi, n, target_mean, predicted_mean, MAE):")
    for b in bins:
        print(
            f"  [{b['target_bin'][0]:.1f},{b['target_bin'][1]:.1f}]  n={b['n']:>5}  "
            f"true={b['target_mean']:.3f}  pred={b['predicted_mean']:.3f}  MAE={b['mae']:.3f}"
        )

    # Train final on all data
    reg_full = Ridge(alpha=1.0, random_state=42).fit(X, y)
    joblib.dump(reg_full, CLF)

    metrics = {
        "model": "CLIP ViT-Large + Ridge regression (clf_v6)",
        "target": "Meta v2 >5m canopy fraction per 240m tile (0..1)",
        "n": int(len(y)),
        "cv5": {"mae": mae, "rmse": rmse, "r2": r2},
        "alpha": 1.0,
    }
    METRICS.write_text(json.dumps(metrics, indent=2))
    print(f"[v6-train] wrote {CLF.name} + {METRICS.name} + {RESIDUALS.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
