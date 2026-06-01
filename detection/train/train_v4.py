"""Train clf_v4 on dataset_v4.npz (v3 + Meta-oracle hard-negatives + missed-positives)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import StratifiedKFold

ROOT = Path(__file__).resolve().parents[2]
DS = ROOT / "detection" / "train" / "dataset_v4.npz"
CLF = ROOT / "detection" / "train" / "clf_v4.joblib"
METRICS = ROOT / "detection" / "train" / "clf_v4_metrics.json"

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


def main() -> int:
    if not DS.exists():
        print(f"[v4-train] missing {DS}", file=sys.stderr)
        return 1
    d = np.load(DS, allow_pickle=True)
    X = d["X"]
    y = d["y"].astype(int)
    src = d["src"].astype(str)
    print(f"[v4-train] X={X.shape}  pos={(y == 1).sum()}  neg={(y == 0).sum()}")

    skf = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)
    cv_probs = np.zeros(len(y))
    for tr, te in skf.split(X, y):
        clf = LogisticRegression(**LR_KW).fit(X[tr], y[tr])
        cv_probs[te] = clf.predict_proba(X[te])[:, 1]
    cv_pos = cv_probs[y == 1]
    cv_neg = cv_probs[y == 0]

    sweep = [prf(cv_pos, cv_neg, round(float(t), 2)) for t in np.arange(0.30, 0.96, 0.05)]
    best = max(sweep, key=lambda s: s["f1"] or 0)
    print(
        f"[v4-train] CV F1-optimal: t={best['t']}  P={best['precision']:.3f}  R={best['recall']:.3f}  F1={best['f1']:.3f}"
    )
    for s in sweep:
        if s["precision"] and s["recall"] and s["f1"]:
            print(f"  t={s['t']:.2f}  P={s['precision']:.3f}  R={s['recall']:.3f}  F1={s['f1']:.3f}")

    clf_full = LogisticRegression(**LR_KW).fit(X, y)

    by_src = {}
    for s in sorted(set(src)):
        ix = src == s
        if not ix.any():
            continue
        sp = cv_probs[ix]
        sy = y[ix]
        # Aggregate by src prefix (everything before LGU suffix)
        prefix = s.split("_")[0] + "_" + s.split("_")[1] + "_" + s.split("_")[2] if s.startswith("v4_") else s
        by_src[prefix] = by_src.get(prefix, {"n": 0, "p_sum": 0.0, "pos": 0})
        rec = by_src[prefix]
        rec["n"] += int(ix.sum())
        rec["p_sum"] += float(sp.sum())
        rec["pos"] += int((sy == 1).sum())
    for k, v in by_src.items():
        v["mean_prob"] = v["p_sum"] / max(v["n"], 1)
        v["pos_share"] = v["pos"] / max(v["n"], 1)
        del v["p_sum"]

    metrics = {
        "model": "openai/clip-vit-large-patch14 + LogisticRegression (clf_v4)",
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
    print(f"[v4-train] wrote {CLF.name} + {METRICS.name}")
    print("[v4-train] per-src-prefix CV (mean prob / pos share):")
    for k, v in sorted(by_src.items()):
        print(f"  {k:<32s} n={v['n']:>5}  mean_p={v['mean_prob']:.3f}  pos_share={v['pos_share']:.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
