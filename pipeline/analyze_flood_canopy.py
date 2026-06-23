"""Controlled analysis of observed flood inundation vs tree canopy per barangay.

Reads the hash-pinned per-barangay table from compute_flood_canopy.py and asks
the question an LGU actually cares about: at the barangay scale, is less canopy
associated with more flooding once you account for the things that really drive
floods (low-lying ground, how built-up the area is, distance to water)?

The honest answer the data gives is counterintuitive and is exactly why this
ships as a co-occurrence screen, never a causal claim:

  - The RAW canopy/flood correlation is POSITIVE (greener barangays appear to
    flood more). That is the opposite of the "less canopy -> more flooding"
    hypothesis, and it is largely a radar artifact: Sentinel-1 under-detects
    flooding inside dense built-up cores (building double-bounce), so open,
    greener barangays are simply where the radar can SEE standing water.
  - Once built-up fraction and elevation are controlled, canopy's independent
    association collapses toward zero. The dominant barangay-scale signals are
    built-up fraction (mostly detection bias plus drainage) and low-lying
    topography, not tree cover.

So: trees are not the barangay-scale flood lever. The street-scale runoff
benefit of canopy is real but small here; urban forestry and drainage are
complements, not substitutes. We surface barangays that are both flood-exposed
and tree-poor as a prioritization screen, with no causal claim attached.

Outputs (the page reads these; no number is hand-typed):
    site/public/data/flood_canopy_barangay.geojson   polygons + per-barangay props + bivariate class
    site/public/data/flood_canopy_summary.json       regression table, distributions, top lists, disclaimer

Run (offline; reads the committed CSV):
    PYTHONPATH=. .venv/bin/python pipeline/analyze_flood_canopy.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import statsmodels.api as sm
from statsmodels.stats.outliers_influence import variance_inflation_factor

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

CSV = REPO / "data" / "flood" / "flood_canopy_barangay.csv"
SRC_GEOJSON = REPO / "site" / "public" / "data" / "per_barangay_canopy.geojson"
OUT_GEOJSON = REPO / "site" / "public" / "data" / "flood_canopy_barangay.geojson"
OUT_SUMMARY = REPO / "site" / "public" / "data" / "flood_canopy_summary.json"

# Predictor of interest + confounders. Both elevation and HAND describe height;
# we lead with HAND (height above nearest drainage, the hydrology-direct one) and
# keep elevation in the full model, reporting VIF so collinearity is visible.
PREDICTOR = "canopy_pct_2025"
CONFOUNDERS = ["hand_m", "elev_m", "builtup_prob", "dist_water_m"]
FLAG_THRESHOLD_PCT = 0.5  # barangay flagged as "observed inundation" if flood_pct >= this

EVENT = "July 2025 southwest-monsoon flood (Sentinel-1 acquisition 2025-07-23)"
DISCLAIMER = (
    "Statistical indicators derived from public satellite data. Observed inundation "
    "is a Sentinel-1 radar lower bound that under-detects flooding in dense built-up "
    "areas; this is an observed co-occurrence screen, not a causal model. Patterns "
    "may have legitimate explanations and warrant independent review."
)


def _z(s: pd.Series) -> pd.Series:
    return (s - s.mean()) / s.std(ddof=0)


def fit_ols(df: pd.DataFrame, y: str, xs: list[str]) -> dict:
    X = sm.add_constant(df[xs])
    m = sm.OLS(df[y], X).fit(cov_type="HC3")  # heteroskedasticity-robust SEs
    return {
        "r2": round(float(m.rsquared), 4),
        "n": int(m.nobs),
        "coef": {k: round(float(v), 4) for k, v in m.params.items()},
        "p": {k: round(float(v), 4) for k, v in m.pvalues.items()},
        "ci": {k: [round(float(a), 4), round(float(b), 4)] for k, (a, b) in m.conf_int().iterrows()},
    }


def fit_logit(df: pd.DataFrame, y: str, xs: list[str]) -> dict:
    X = sm.add_constant(df[xs])
    m = sm.Logit(df[y], X).fit(disp=0)
    return {
        "pseudo_r2": round(float(m.prsquared), 4),
        "n": int(m.nobs),
        "coef": {k: round(float(v), 4) for k, v in m.params.items()},
        "odds_ratio": {k: round(float(np.exp(v)), 4) for k, v in m.params.items()},
        "p": {k: round(float(v), 4) for k, v in m.pvalues.items()},
    }


def vif_table(df: pd.DataFrame, xs: list[str]) -> dict:
    X = sm.add_constant(df[xs]).to_numpy()
    return {xs[i - 1]: round(float(variance_inflation_factor(X, i)), 2) for i in range(1, len(xs) + 1)}


def morans_i(df: pd.DataFrame, resid: np.ndarray) -> dict | None:
    """Moran's I of OLS residuals over KNN-8 barangay centroids."""
    try:
        from esda.moran import Moran
        from libpysal.weights import KNN
    except Exception as e:  # pragma: no cover
        return {"error": f"spatial libs unavailable: {e}"}
    coords = df[["cx", "cy"]].to_numpy()
    w = KNN.from_array(coords, k=8)
    w.transform = "r"
    np.random.seed(0)  # deterministic permutation p-value across re-runs
    mi = Moran(resid, w, permutations=999)
    return {"I": round(float(mi.I), 4), "p_sim": round(float(mi.p_sim), 4), "k": 8}


def centroid(geom: dict) -> tuple[float, float]:
    """Area-free centroid = mean of all exterior-ring vertices (good enough for KNN)."""
    pts = []

    def walk(coords, depth):
        if depth == 0:
            pts.append(coords)
        else:
            for c in coords:
                walk(c, depth - 1)

    t = geom["type"]
    if t == "Polygon":
        walk(geom["coordinates"][0], 1)
    elif t == "MultiPolygon":
        for poly in geom["coordinates"]:
            walk(poly[0], 1)
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    return sum(xs) / len(xs), sum(ys) / len(ys)


def tercile_bins(s: pd.Series, labels=(0, 1, 2)) -> pd.Series:
    try:
        return pd.qcut(s, 3, labels=labels).astype(int)
    except ValueError:  # too many ties; fall back to rank-based split
        return pd.cut(s.rank(method="first"), 3, labels=labels).astype(int)


def main() -> int:
    df = pd.read_csv(CSV).dropna(subset=[PREDICTOR, "flood_pct"] + CONFOUNDERS).reset_index(drop=True)
    n = len(df)

    # centroids (for spatial weights) joined from the source geojson by name+lgu
    gj = json.loads(SRC_GEOJSON.read_text())
    cent = {}
    for feat in gj["features"]:
        p = feat["properties"]
        cx, cy = centroid(feat["geometry"])
        cent[(p["barangay_name"], p["lgu_name"])] = (round(cx, 6), round(cy, 6))
    df["cx"] = df.apply(lambda r: cent.get((r["barangay_name"], r["lgu_name"]), (np.nan, np.nan))[0], axis=1)
    df["cy"] = df.apply(lambda r: cent.get((r["barangay_name"], r["lgu_name"]), (np.nan, np.nan))[1], axis=1)

    # standardized design so coefficients are comparable betas
    zpred = f"z_{PREDICTOR}"
    zconf = [f"z_{c}" for c in CONFOUNDERS]
    df[zpred] = _z(df[PREDICTOR])
    for c in CONFOUNDERS:
        df[f"z_{c}"] = _z(df[c])

    df["flagged"] = (df["flood_pct"] >= FLAG_THRESHOLD_PCT).astype(int)

    # --- continuous outcome: flood_pct (right-censored at 0; HC3-robust OLS) ---
    ols_bi = fit_ols(df, "flood_pct", [zpred])
    ols_full = fit_ols(df, "flood_pct", [zpred] + zconf)

    # --- binary outcome: observed inundation yes/no (robust to zero-inflation) ---
    logit_bi = fit_logit(df, "flagged", [zpred])
    logit_full = fit_logit(df, "flagged", [zpred] + zconf)

    # collinearity + spatial autocorrelation of residuals
    vif = vif_table(df, [zpred] + zconf)
    Xfull = sm.add_constant(df[[zpred] + zconf])
    resid = (df["flood_pct"] - sm.OLS(df["flood_pct"], Xfull).fit().predict(Xfull)).to_numpy()
    spatial = morans_i(df, resid) if df[["cx", "cy"]].notna().all().all() else None

    # shrinkage of the canopy beta from bivariate -> controlled (the story)
    beta_bi = ols_bi["coef"][zpred]
    beta_full = ols_full["coef"][zpred]

    # --- bivariate class for the map: flood exposure tercile x canopy tercile ---
    df["flood_class"] = (df["flood_pct"] >= FLAG_THRESHOLD_PCT).astype(int)  # 0 none, 1 observed
    df["canopy_tercile"] = tercile_bins(df[PREDICTOR])  # 0 low, 1 mid, 2 high
    # priority = observed inundation AND lowest-canopy tercile
    df["priority"] = ((df["flood_class"] == 1) & (df["canopy_tercile"] == 0)).astype(int)

    # --- merged geojson (polygons from source, props from analysis) -----------
    keyrow = {(r["barangay_name"], r["lgu_name"]): r for _, r in df.iterrows()}
    features = []
    for feat in gj["features"]:
        p = feat["properties"]
        r = keyrow.get((p["barangay_name"], p["lgu_name"]))
        if r is None:
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": feat["geometry"],
                "properties": {
                    "barangay_name": r["barangay_name"],
                    "lgu_name": r["lgu_name"],
                    "total_ha": round(float(r["total_ha"]), 1),
                    "canopy_pct": round(float(r["canopy_pct_2025"]), 2),
                    "canopy_trend": round(float(r["canopy_trend_pct_per_yr"]), 3),
                    "flood_pct": round(float(r["flood_pct"]), 3),
                    "hand_m": round(float(r["hand_m"]), 1),
                    "builtup_prob": round(float(r["builtup_prob"]), 3),
                    "dist_water_m": round(float(r["dist_water_m"]), 0),
                    "flood_class": int(r["flood_class"]),
                    "canopy_tercile": int(r["canopy_tercile"]),
                    "priority": int(r["priority"]),
                },
            }
        )
    OUT_GEOJSON.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    )

    top_flood = df.sort_values("flood_pct", ascending=False).head(15)
    priority = df[df["priority"] == 1].sort_values("flood_pct", ascending=False)

    def slim_flood(r):
        return {
            "barangay": r["barangay_name"],
            "lgu": r["lgu_name"],
            "flood_pct": round(float(r["flood_pct"]), 2),
            "canopy_pct": round(float(r["canopy_pct_2025"]), 1),
            "hand_m": round(float(r["hand_m"]), 1),
        }

    summary = {
        "event": EVENT,
        "n_barangays": n,
        "n_observed_inundation": int(df["flagged"].sum()),
        "flag_threshold_pct": FLAG_THRESHOLD_PCT,
        "flood_pct_max": round(float(df["flood_pct"].max()), 2),
        "flood_pct_mean": round(float(df["flood_pct"].mean()), 3),
        "n_priority": int(df["priority"].sum()),
        "raw_canopy_flood_pearson_r": round(float(df["canopy_pct_2025"].corr(df["flood_pct"])), 3),
        "regression": {
            "outcome_note": "flood_pct is right-censored at 0; OLS uses HC3-robust SEs; logit models observed-inundation yes/no.",
            "predictors_standardized": True,
            "ols_bivariate": ols_bi,
            "ols_controlled": ols_full,
            "logit_bivariate": logit_bi,
            "logit_controlled": logit_full,
            "canopy_beta_bivariate": beta_bi,
            "canopy_beta_controlled": beta_full,
            "vif": vif,
            "spatial_residual_moran": spatial,
        },
        "top_flood_exposed": [slim_flood(r) for _, r in top_flood.iterrows()],
        "priority_barangays": [slim_flood(r) for _, r in priority.iterrows()][:15],
        "sources": {
            "flood": "Sentinel-1 SAR (COPERNICUS/S1_GRD) change detection",
            "canopy": "Leaves.PH human-calibrated Sentinel-2 classifier",
            "confounders": "MERIT Hydro (HAND, elevation), Dynamic World (built-up), JRC Global Surface Water (distance to water)",
        },
        "disclaimer": DISCLAIMER,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))

    print("=" * 64)
    print(
        f"n barangays: {n} | observed inundation: {summary['n_observed_inundation']} | priority: {summary['n_priority']}"
    )
    print(f"raw canopy~flood Pearson r: {summary['raw_canopy_flood_pearson_r']:+.3f}")
    print(
        f"canopy beta (std): bivariate {beta_bi:+.4f} (p={ols_bi['p'][zpred]})  ->  controlled {beta_full:+.4f} (p={ols_full['p'][zpred]})"
    )
    print("full-model standardized betas:")
    for k in [zpred] + zconf:
        print(f"  {k:18s} beta={ols_full['coef'][k]:+.4f}  p={ols_full['p'][k]}")
    print(f"R2: bivariate {ols_bi['r2']} -> controlled {ols_full['r2']}")
    print(f"VIF: {vif}")
    print(f"Moran's I (resid): {spatial}")
    print(
        f"logit canopy odds ratio: bivariate {logit_bi['odds_ratio'][zpred]} -> controlled {logit_full['odds_ratio'][zpred]}"
    )
    print(f"wrote {OUT_GEOJSON.relative_to(REPO)}, {OUT_SUMMARY.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
