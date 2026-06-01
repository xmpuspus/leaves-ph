"""v5 = clf_v4 wrapped in Platt sigmoid calibration.

Uses sklearn CalibratedClassifierCV with method='sigmoid' (Platt scaling) over
5-fold CV on dataset_v4. The resulting estimator outputs reliability-calibrated
probabilities so the threshold sweep maps to interpretable precision/recall.

We also export a per-tile reliability diagram (predicted prob vs empirical
positive rate, binned) to detection/train/clf_v5_reliability.json.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v4.npz"
CLF = ROOT / "detection" / "train" / "clf_v5.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v5_metrics.json"
RELIABILITY = ROOT / "detection" / "train" / "clf_v5_reliability.json"

LR_KW = dict(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)


def prf(pos, neg, t):
    tp = int((pos >= t).sum())
    fp = int((neg >= t).sum())
    fn = int((pos < t).sum())
    tn = int((neg < t).sum())
    p = tp / (tp + fp) if (tp + fp) else None
    r = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * p * r / (p + r)) if (p is not None and r is not None and (p + r) > 0) else None
    return {"t": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r, "f1": f1}


def reliability_bins(probs, labels, n_bins=10):
    bins = np.linspace(0, 1, n_bins + 1)
    out = []
    for i in range(n_bins):
        lo, hi = bins[i], bins[i + 1]
        mask = (probs >= lo) & (probs < hi if i < n_bins - 1 else probs <= hi)
        n = int(mask.sum())
        if n == 0:
            out.append(
                {"bin_lo": float(lo), "bin_hi": float(hi), "n": 0, "mean_pred": None, "empirical_pos": None}
            )
            continue
        out.append(
            {
                "bin_lo": float(lo),
                "bin_hi": float(hi),
                "n": n,
                "mean_pred": float(probs[mask].mean()),
                "empirical_pos": float(labels[mask].mean()),
            }
        )
    return out


def main() -> int:
    if not DS.exists():
        print(f"[v5-platt] missing {DS}", file=sys.stderr)
        return 1
    d = np.load(DS, allow_pickle=True)
    X = d["X"]
    y = d["y"].astype(int)
    print(f"[v5-platt] X={X.shape}  pos={(y == 1).sum()}  neg={(y == 0).sum()}")

    base = LogisticRegression(**LR_KW)
    # CalibratedClassifierCV with cv=5 trains 5 inner LR models, then fits a
    # sigmoid (Platt) calibration on the held-out folds. The final estimator
    # averages predict_proba over the 5 calibrators.
    cal = CalibratedClassifierCV(estimator=base, method="sigmoid", cv=5)
    print("[v5-platt] fitting CalibratedClassifierCV(method=sigmoid, cv=5)")
    cal.fit(X, y)

    # Cross-validated probs for honest evaluation
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_probs = np.zeros(len(y))
    for tr, te in skf.split(X, y):
        c = CalibratedClassifierCV(estimator=LogisticRegression(**LR_KW), method="sigmoid", cv=5).fit(
            X[tr], y[tr]
        )
        cv_probs[te] = c.predict_proba(X[te])[:, 1]
    cv_pos = cv_probs[y == 1]
    cv_neg = cv_probs[y == 0]

    sweep = [prf(cv_pos, cv_neg, round(float(t), 2)) for t in np.arange(0.30, 0.96, 0.05)]
    best = max(sweep, key=lambda s: s["f1"] or 0)
    print(
        f"[v5-platt] post-calibration CV F1-optimal: t={best['t']}  P={best['precision']:.3f}  R={best['recall']:.3f}  F1={best['f1']:.3f}"
    )
    for s in sweep:
        if s["precision"] and s["recall"] and s["f1"]:
            print(f"  t={s['t']:.2f}  P={s['precision']:.3f}  R={s['recall']:.3f}  F1={s['f1']:.3f}")

    rel = reliability_bins(cv_probs, y)
    RELIABILITY.write_text(json.dumps({"n_bins": len(rel), "bins": rel}, indent=2))
    print("[v5-platt] reliability bins (pred bin -> empirical):")
    for r in rel:
        if r["n"] == 0:
            continue
        print(
            f"  [{r['bin_lo']:.1f},{r['bin_hi']:.1f}]  n={r['n']:>5}  mean_pred={r['mean_pred']:.3f}  empirical={r['empirical_pos']:.3f}"
        )

    metrics = {
        "model": "openai/clip-vit-large-patch14 + LR (clf_v4) + Platt sigmoid (clf_v5)",
        "hyperparams": LR_KW,
        "method": "CalibratedClassifierCV(method=sigmoid, cv=5)",
        "n_total": int(len(y)),
        "n_pos": int((y == 1).sum()),
        "n_neg": int((y == 0).sum()),
        "cv5_f1_optimal": best,
        "cv5_sweep": sweep,
    }
    METRICS.write_text(json.dumps(metrics, indent=2, default=str))
    joblib.dump(cal, CLF)
    print(f"[v5-platt] wrote {CLF.name} + {METRICS.name} + {RELIABILITY.name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
