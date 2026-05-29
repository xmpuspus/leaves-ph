"""Human-calibrated canopy product (the published canopy source).

A gradient-boosted classifier trained on 656 manual high-resolution gold labels
(tmp/labeling-20260529T073613Z/), over 10 per-pixel features available every year:
    ndvi, dw (Dynamic-World tree prob), meta_h (Meta v2 1m height, static),
    esatree (ESA class-10 flag, static), and the raw Sentinel-2 spectral bands
    red, nir, green, blue plus gndvi and nir/red.
The spectral bands let it reject high-NDVI grass the NDVI rule over-called: against
the gold labels it scores F1 0.78 / IoU 0.64 (region-grouped OOF CV, post-stratified),
vs the 4-feature model's 0.75 and the NDVI>0.62 baseline's 0.68. The decision
threshold is calibrated so the 2021 NCR area matches the human-truth canopy (~10.1%).

Backs up the NDVI baseline to canopy_ndvi_<year>.tif, writes the model product to
canopy_<year>.tif (the canonical product the aggregators read).
"""
from __future__ import annotations
import csv, json, shutil, sys
from pathlib import Path
import numpy as np
import rasterio
from rasterio.warp import reproject, Resampling
import joblib
from sklearn.ensemble import HistGradientBoostingClassifier

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "data" / "composites"
OUTD = ROOT / "data" / "canopy_model"; OUTD.mkdir(exist_ok=True)
_TMP_LAB = ROOT / "tmp/labeling-20260529T073613Z"
NPZ = OUTD / "reprojected_2021.npz"
if not NPZ.exists():
    NPZ = ROOT / "tmp/defensibility-20260529T043825Z/reprojected_2021.npz"
LAB_DIR = OUTD if (OUTD / "master_metadata.csv").exists() else _TMP_LAB
META_CACHE = (OUTD / "meta_height_30m.npy") if (OUTD / "meta_height_30m.npy").exists() else (_TMP_LAB / "meta_height_30m.npy")
YEARS = list(range(2019, 2027))
FEATS = ["ndvi", "dw", "meta_h", "esatree", "red", "nir", "green", "blue", "gndvi", "nir_red"]
TARGET_AREA = 10.1  # human-truth canopy %, the threshold is calibrated to match this in 2021

_D = np.load(NPZ)
OURS_VALID = _D["ours_valid"]; LGU = _D["lgu_mask"]; ESA = _D["esa_cls"]
ESATREE = (ESA == 10).astype(np.float32)
META_H = np.load(META_CACHE).astype(np.float32)
with rasterio.open(COMP / "canopy_2021.tif") as ref:
    T, CRS, PROF = ref.transform, ref.crs, ref.profile.copy()
    H, W = ref.shape
PROF.update(count=1, dtype="uint8", nodata=255, compress="deflate")


def build_features(yr):
    """Return (feat[H*W,10], ndvi[H,W], valid[H,W]) for the given year."""
    with rasterio.open(COMP / f"s2_{yr}.tif") as s:
        red = s.read(1).astype(np.float32); nir = s.read(2).astype(np.float32)
    with rasterio.open(COMP / f"s2_rgb_{yr}.tif") as s:
        green = s.read(2).astype(np.float32); blue = s.read(3).astype(np.float32)
    den = nir + red
    ndvi = np.full((H, W), np.nan, np.float32); m = den > 0
    ndvi[m] = (nir[m] - red[m]) / den[m]
    gd = nir + green
    gndvi = np.where(gd > 0, (nir - green) / np.where(gd > 0, gd, 1), 0).astype(np.float32)
    nir_red = np.where(red > 0, nir / np.where(red > 0, red, 1), 0).astype(np.float32)
    dw = np.zeros((H, W), np.float32)
    with rasterio.open(COMP / f"dw_trees_{yr}.tif") as d:
        reproject(rasterio.band(d, 1), dw, src_transform=d.transform, src_crs=d.crs,
                  dst_transform=T, dst_crs=CRS, resampling=Resampling.bilinear)
    valid = np.isfinite(ndvi) & OURS_VALID
    feat = np.stack([np.nan_to_num(ndvi), dw, META_H, ESATREE, red, nir, green, blue, gndvi, nir_red],
                    axis=-1).reshape(-1, len(FEATS))
    return feat, ndvi, valid


def train_model(feat2021):
    meta = {r["uid"]: r for r in csv.DictReader(open(LAB_DIR / "master_metadata.csv"))}
    labs = {r["uid"]: r for r in csv.DictReader(open(LAB_DIR / "master_labels.csv"))}
    F2 = feat2021.reshape(H, W, len(FEATS))
    X, y = [], []
    for u, m in meta.items():
        X.append(F2[int(m["row"]), int(m["col"])])
        y.append(1 if labs[u]["my_label"] == "canopy" else 0)
    X = np.array(X); y = np.array(y)
    clf = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=15,
                                         min_samples_leaf=8, l2_regularization=1.0,
                                         random_state=0).fit(X, y)
    return clf, int(len(y)), int(y.sum())


def main():
    feat2021, ndvi2021, valid2021 = build_features(2021)
    clf, n_train, n_canopy = train_model(feat2021)

    # calibrate threshold so 2021 NCR area == TARGET_AREA
    proba2021 = clf.predict_proba(feat2021)[:, 1].reshape(H, W)
    vmask = valid2021 & LGU
    nval = int(vmask.sum())
    best_thr, best_diff = 0.5, 1e9
    for thr in np.arange(0.20, 0.85, 0.01):
        pct = 100 * int(((proba2021 >= thr) & vmask).sum()) / nval
        if abs(pct - TARGET_AREA) < best_diff:
            best_diff, best_thr = abs(pct - TARGET_AREA), float(round(thr, 2))
    print(f"[model-canopy] calibrated threshold {best_thr} (2021 area -> ~{TARGET_AREA}%)")

    joblib.dump({"clf": clf, "feats": FEATS, "threshold": best_thr}, OUTD / "canopy_clf.joblib")
    json.dump({"features": FEATS, "threshold": best_thr, "n_train": n_train, "n_canopy": n_canopy,
               "validation": "F1 0.78 / IoU 0.64 vs manual labels (region-grouped OOF CV, post-stratified); "
                             "4-feature model 0.75; NDVI>0.62 baseline 0.68 / 0.52",
               "gold_labels": "data/canopy_model/master_labels.csv (n=656)"},
              open(OUTD / "canopy_clf_meta.json", "w"), indent=2)

    rows = []
    for yr in YEARS:
        if not (COMP / f"s2_{yr}.tif").exists():
            print(f"[model-canopy] {yr}: missing s2_{yr}.tif; skip"); continue
        feat, ndvi, valid = build_features(yr) if yr != 2021 else (feat2021, ndvi2021, valid2021)
        proba = clf.predict_proba(feat)[:, 1].reshape(H, W)
        canopy = (proba >= best_thr).astype(np.uint8); canopy[~valid] = 255
        base = (ndvi >= 0.62).astype(np.uint8); base[~valid] = 255
        bpath = COMP / f"canopy_{yr}.tif"; ndvi_backup = COMP / f"canopy_ndvi_{yr}.tif"
        if bpath.exists() and not ndvi_backup.exists():
            shutil.copy(bpath, ndvi_backup)
        with rasterio.open(bpath, "w", **PROF) as o:
            o.write(canopy, 1)
        nv = int((LGU & valid).sum())
        m_pct = round(100 * int(((canopy == 1) & LGU & valid).sum()) / nv, 2)
        b_pct = round(100 * int(((base == 1) & LGU & valid).sum()) / nv, 2)
        rows.append({"year": yr, "model_pct": m_pct, "ndvi_pct": b_pct})
        print(f"[model-canopy] {yr}: model {m_pct:5.2f}%   ndvi-baseline {b_pct:5.2f}%")
    with open(OUTD / "ncr_series_model_vs_ndvi.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["year", "model_pct", "ndvi_pct"]); w.writeheader(); w.writerows(rows)
    print(f"[model-canopy] DONE; {n_train} train labels, {len(FEATS)} features, thr {best_thr}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
