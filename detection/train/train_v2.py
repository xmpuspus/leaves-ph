"""Step 2 of the SolarMap-style CLIP+LR head.

Train clf_v2 deterministically from detection/train/dataset_v2.npz with the
exact hyper-params SolarMap clf_v5 uses (so the artefact hash is stable
across runs):

    LogisticRegression(max_iter=2000, C=1.0,
                       class_weight="balanced", random_state=42)

Outputs:
    detection/train/clf_v2.joblib
    detection/train/clf_v2_metrics.json   (precision / recall / F1 at t=0.85
                                           plus LGU-stratified LORO)
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v2.npz"
CLF = ROOT / "detection" / "train" / "clf_v2.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v2_metrics.json"

DEPLOY_T = 0.50  # F1-optimal on 5-fold CV; t=0.85 was over-conservative
# for the tile-level "is this neighborhood tree-rich" task.
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
        print(f"[v2-train] missing {DS}; run build_dataset_v2.py first", file=sys.stderr)
        return 1
    d = np.load(DS, allow_pickle=True)
    X = d["X"]
    y = d["y"].astype(int)
    lgu = d["lgu"].astype(str)
    src = d["src"].astype(str)
    print(f"[v2-train] X={X.shape}  pos={(y == 1).sum()}  neg={(y == 0).sum()}")

    # Stratified 5-fold CV (overall honesty metric)
    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_probs = np.zeros(len(y))
    for fold, (tr, te) in enumerate(skf.split(X, y)):
        clf = LogisticRegression(**LR_KW).fit(X[tr], y[tr])
        cv_probs[te] = clf.predict_proba(X[te])[:, 1]
    cv_pos = cv_probs[y == 1]
    cv_neg = cv_probs[y == 0]
    cv_at_85 = prf(cv_pos, cv_neg, DEPLOY_T)
    print(
        f"[v2-train] 5-fold CV @ t={DEPLOY_T}: "
        f"P={cv_at_85['precision']:.3f}  R={cv_at_85['recall']:.3f}  F1={cv_at_85['f1']:.3f}"
    )

    # Leave-one-LGU-out: train on 16, score on 1, per-LGU honesty
    loro: dict[str, dict] = {}
    for held in sorted(set(lgu)):
        tr = lgu != held
        te = lgu == held
        if te.sum() < 5 or len(set(y[tr])) < 2:
            continue
        clf_l = LogisticRegression(**LR_KW).fit(X[tr], y[tr])
        probs = clf_l.predict_proba(X[te])[:, 1]
        pos_p = probs[y[te] == 1]
        neg_p = probs[y[te] == 0]
        loro[held] = {
            "n_pos": int((y[te] == 1).sum()),
            "n_neg": int((y[te] == 0).sum()),
            **prf(pos_p, neg_p, DEPLOY_T),
        }

    # Final classifier trained on ALL labelled data (deployed artefact)
    clf = LogisticRegression(**LR_KW).fit(X, y)
    in_probs = clf.predict_proba(X)[:, 1]
    in_at_85 = prf(in_probs[y == 1], in_probs[y == 0], DEPLOY_T)

    # Threshold sweep for the metrics file
    sweep = []
    for t in np.arange(0.50, 0.96, 0.05):
        sweep.append({"threshold": round(float(t), 2), **prf(cv_pos, cv_neg, float(t))})

    metrics = {
        "model": "openai/clip-vit-large-patch14 + LogisticRegression",
        "hyperparams": LR_KW,
        "deploy_threshold": DEPLOY_T,
        "n_total": int(len(y)),
        "n_pos": int((y == 1).sum()),
        "n_neg": int((y == 0).sum()),
        "cv5_at_deploy": cv_at_85,
        "in_sample_at_deploy": in_at_85,
        "loro_per_lgu": loro,
        "cv5_sweep": sweep,
        "src_provenance": {s: int((src == s).sum()) for s in sorted(set(src))},
    }
    METRICS.write_text(json.dumps(metrics, indent=2))
    joblib.dump(clf, CLF)
    print(f"[v2-train] wrote {CLF.name} + {METRICS.name}")
    print(f"[v2-train] LORO summary (P / R / F1 at t={DEPLOY_T}):")
    for lgu_n, m in sorted(loro.items(), key=lambda kv: -(kv[1]["f1"] or 0)):
        if m["f1"] is None:
            continue
        print(
            f"  {lgu_n:25s}  P={m['precision']:.3f}  R={m['recall']:.3f}  F1={m['f1']:.3f}  "
            f"(n_pos={m['n_pos']} n_neg={m['n_neg']})"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
