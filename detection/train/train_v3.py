"""Step 2 of v3 iteration: train clf_v3 on the merged dataset_v3.npz."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v3.npz"
CLF = ROOT / "detection" / "train" / "clf_v3.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v3_metrics.json"

LR_KW = dict(max_iter=2000, C=1.0, class_weight="balanced", random_state=42)


def prf(pos: np.ndarray, neg: np.ndarray, t: float) -> dict:
    tp = int((pos >= t).sum())
    fp = int((neg >= t).sum())
    fn = int((pos < t).sum())
    tn = int((neg < t).sum())
    p = tp / (tp + fp) if (tp + fp) else None
    r = tp / (tp + fn) if (tp + fn) else None
    f1 = (2 * p * r / (p + r)) if (p is not None and r is not None and (p + r) > 0) else None
    return {"t": t, "tp": tp, "fp": fp, "fn": fn, "tn": tn, "precision": p, "recall": r, "f1": f1}


def main() -> int:
    if not DS.exists():
        print(f"[v3-train] missing {DS}", file=sys.stderr)
        return 1
    d = np.load(DS, allow_pickle=True)
    X = d["X"]
    y = d["y"].astype(int)
    src = d["src"].astype(str)
    print(f"[v3-train] X={X.shape}  pos={(y == 1).sum()}  neg={(y == 0).sum()}")

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_probs = np.zeros(len(y))
    for fold, (tr, te) in enumerate(skf.split(X, y)):
        clf = LogisticRegression(**LR_KW).fit(X[tr], y[tr])
        cv_probs[te] = clf.predict_proba(X[te])[:, 1]
    cv_pos = cv_probs[y == 1]
    cv_neg = cv_probs[y == 0]

    sweep = [prf(cv_pos, cv_neg, round(float(t), 2)) for t in np.arange(0.30, 0.96, 0.05)]
    best = max(sweep, key=lambda s: s["f1"] or 0)
    print(
        f"[v3-train] CV F1-optimal: t={best['t']}  "
        f"P={best['precision']:.3f}  R={best['recall']:.3f}  F1={best['f1']:.3f}"
    )
    for s in sweep:
        if s["precision"] and s["recall"] and s["f1"]:
            print(f"  t={s['t']:.2f}  P={s['precision']:.3f}  R={s['recall']:.3f}  F1={s['f1']:.3f}")

    clf_full = LogisticRegression(**LR_KW).fit(X, y)

    # Per-src honest metrics (helps see if the ESA teacher labels help or hurt)
    by_src = {}
    for s in sorted(set(src)):
        ix = src == s
        if not ix.any():
            continue
        sp = cv_probs[ix]
        sy = y[ix]
        by_src[s] = {
            "n": int(ix.sum()),
            "pos_share": float((sy == 1).mean()),
            "mean_prob": float(sp.mean()),
            "above_0.5": float((sp >= 0.5).mean()),
            "above_0.85": float((sp >= 0.85).mean()),
        }

    metrics = {
        "model": "openai/clip-vit-large-patch14 + LogisticRegression (clf_v3)",
        "hyperparams": LR_KW,
        "n_total": int(len(y)),
        "n_pos": int((y == 1).sum()),
        "n_neg": int((y == 0).sum()),
        "cv5_f1_optimal": best,
        "cv5_sweep": sweep,
        "per_src_cv": by_src,
    }
    METRICS.write_text(json.dumps(metrics, indent=2, default=str))
    joblib.dump(clf_full, CLF)
    print(f"[v3-train] wrote {CLF.name} + {METRICS.name}")
    print("[v3-train] per-src mean CV probability (sanity check):")
    for s, m in by_src.items():
        print(
            f"  {s:>20s}  n={m['n']:>5}  pos_share={m['pos_share']:.2f}  mean_p={m['mean_prob']:.3f}  >=.5={m['above_0.5']:.2f}  >=.85={m['above_0.85']:.2f}"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
