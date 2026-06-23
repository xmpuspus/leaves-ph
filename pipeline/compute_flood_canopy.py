"""Observed flood inundation x tree canopy, per Metro Manila barangay.

Pairs the per-barangay canopy series with how much of each barangay actually
went under water in the most severe recent Metro Manila flood that has clean
radar coverage: the July 2025 southwest-monsoon flood (Wipha / Co-may enhanced
habagat; Metro Manila placed under a state of calamity on 22 July 2025). A
Sentinel-1 descending acquisition on 2025-07-23 sits right on the flood peak.

Why we measure inundation ourselves instead of using an official hazard layer:
the DOST GeoRiskPH / HazardHunter and Project NOAH flood layers are auth-gated
(`499 Token Required`) or SPA-only with no addressable data URLs. Rather than
ship a broken scraped layer, we compute observed inundation on the personal EE
key. The official-hazard overlay is tracked as a README roadmap item.

Why July 2025 and not the bigger July 2024 Carina (Gaemi) flood: verified that
Carina's flood window (24-30 Jul 2024) has ZERO Sentinel-1 descending
acquisitions over NCR (single-satellite S1A revisit missed the peak). You cannot
measure a flood the radar never saw.

Outputs:
    data/flood/flood_canopy_barangay.csv   per-barangay table (hash-pinned)

`analyze_flood_canopy.py` turns this CSV into the controlled regression summary
and the site geojson. No published number is hand-typed.

Honesty boundaries (carried into the /flood-risk page copy):
  - SAR under-detects flooding inside dense urban cores (building double-bounce
    masks the smooth-water signal). The inundation signal is cleanest in open,
    low-rise, and floodplain barangays. Built-up fraction is a regression
    control partly because it also absorbs this detection bias.
  - This is an observed co-occurrence screen, not a causal model. Flooding at the
    barangay scale is driven mostly by elevation/drainage, how built-up the
    ground is, and rainfall; canopy is a secondary factor. The controlled
    regression (analyze step) reports canopy's association after those controls.

Run (network; personal EE key only, never a work GCP project):
    LEAVES_PH_EE_KEY=$PWD/.ee-key.json PYTHONPATH=. \
        .venv/bin/python pipeline/compute_flood_canopy.py
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

import ee

from pipeline._gee_init import init as ee_init

# ---- data sources (all Earth Engine assets; no gated downloads) -------------
S1_ASSET = "COPERNICUS/S1_GRD"  # bands already terrain-corrected sigma0 in dB
MERIT_ASSET = "MERIT/Hydro/v1_0_1"  # hnd = height above nearest drainage, elv = elevation
DW_ASSET = "GOOGLE/DYNAMICWORLD/V1"  # built = built-up probability 0..1
GSW_ASSET = "JRC/GSW1_4/GlobalSurfaceWater"  # occurrence = % of time water 1984-2021

# ---- event windows (verified to contain clean descending S1 acquisitions) ---
FLOOD_START, FLOOD_END = "2025-07-22", "2025-07-25"  # peak; one acq on 2025-07-23
REF_START, REF_END = "2025-05-01", "2025-06-25"  # pre-monsoon dry reference, 5 acqs
DW_START, DW_END = "2024-01-01", "2025-12-31"  # built-up averaged for stability

# ---- SAR change-detection thresholds (documented; fixed, not Otsu, for a
#      reproducible hash-stable product) ---------------------------------------
SMOOTH_M = 30  # focal-median speckle filter radius (m)
DIFF_DB = -3.0  # VH must drop > 3 dB vs the dry reference to flag new water
ABS_DB = -17.0  # and be dark (< -17 dB) in absolute terms (smooth open water)
PERM_WATER_OCC = 40  # GSW occurrence >= this is permanent water, excluded
WATER_OCC = 25  # GSW occurrence >= this counts as "water" for distance-to-water
SLOPE_DEG = 5.0  # slopes steeper than this cannot pool floodwater, excluded
DIST_NEIGHBORHOOD_PX = 256  # fastDistanceTransform search radius (px); ~7.7 km at 30 m

CHUNK = 60  # barangays per synchronous reduceRegions call
SCALE = 30  # reduceRegions sampling scale (m)

SRC_GEOJSON = REPO / "site" / "public" / "data" / "per_barangay_canopy.geojson"
OUT_CSV = REPO / "data" / "flood" / "flood_canopy_barangay.csv"
CACHE = REPO / "data" / "flood" / ".flood_compute_cache.json"  # gitignored

CANOPY_YEARS = list(range(2019, 2027))

CSV_FIELDS = [
    "barangay_name",
    "lgu_name",
    "total_ha",
    "canopy_pct_2025",
    "canopy_pct_2019",
    "canopy_trend_pct_per_yr",
    "flood_frac",
    "flood_pct",
    "hand_m",
    "elev_m",
    "builtup_prob",
    "dist_water_m",
]


def _num(v):
    return float(v) if v is not None else None


def load_barangays() -> list[dict]:
    gj = json.loads(SRC_GEOJSON.read_text())
    out = []
    for i, feat in enumerate(gj["features"]):
        p = feat["properties"]
        vals = {y: p.get(f"canopy_pct_v6_{y}") for y in CANOPY_YEARS}
        out.append(
            {
                "bidx": i,
                "geometry": feat["geometry"],
                "barangay_name": p.get("barangay_name"),
                "lgu_name": p.get("lgu_name"),
                "total_ha": _num(p.get("total_ha")),
                "canopy_pct_2025": _num(vals.get(2025)),
                "canopy_pct_2019": _num(vals.get(2019)),
                "canopy_trend_pct_per_yr": _trend(vals),
            }
        )
    return out


def _trend(vals: dict) -> float | None:
    """OLS slope of canopy % vs year over the available series (%/yr)."""
    pts = [(y, v) for y, v in vals.items() if v is not None]
    n = len(pts)
    if n < 2:
        return None
    mx = sum(y for y, _ in pts) / n
    my = sum(v for _, v in pts) / n
    num = sum((y - mx) * (v - my) for y, v in pts)
    den = sum((y - mx) ** 2 for y, _ in pts)
    return round(num / den, 4) if den else None


def build_metric_image() -> ee.Image:
    """One multi-band image: flood fraction + the four confounders.

    A multi-band image under reduceRegions(mean) returns each value keyed by its
    band name, side-stepping the single-band reducer-key trap.
    """
    merit = ee.Image(MERIT_ASSET)
    gsw = ee.Image(GSW_ASSET).select("occurrence").unmask(0)

    s1 = (
        ee.ImageCollection(S1_ASSET)
        .filter(ee.Filter.eq("instrumentMode", "IW"))
        .filter(ee.Filter.listContains("transmitterReceiverPolarisation", "VH"))
        .filter(ee.Filter.eq("orbitProperties_pass", "DESCENDING"))
        .select("VH")
    )
    pre = s1.filterDate(REF_START, REF_END).median().focal_median(SMOOTH_M, "circle", "meters")
    flo = s1.filterDate(FLOOD_START, FLOOD_END).median().focal_median(SMOOTH_M, "circle", "meters")
    diff = flo.subtract(pre)

    not_perm = gsw.lt(PERM_WATER_OCC)
    not_steep = ee.Terrain.slope(merit.select("elv")).lt(SLOPE_DEG)
    flood = diff.lt(DIFF_DB).And(flo.lt(ABS_DB)).And(not_perm).And(not_steep)
    flood_frac = flood.unmask(0).rename("flood_frac")

    # fastDistanceTransform avoids the 512-px kernel limit that a euclidean
    # distance kernel hits at an 8 km radius. Output is squared distance in
    # pixels of the request projection; sqrt then scale by the pixel side (m).
    water = gsw.gte(WATER_OCC)
    dist = (
        water.fastDistanceTransform(DIST_NEIGHBORHOOD_PX)
        .sqrt()
        .multiply(ee.Image.pixelArea().sqrt())
        .rename("dist_water_m")
    )
    builtup = (
        ee.ImageCollection(DW_ASSET)
        .filterDate(DW_START, DW_END)
        .select("built")
        .mean()
        .rename("builtup_prob")
    )
    return (
        flood_frac.addBands(merit.select("hnd").rename("hand_m"))
        .addBands(merit.select("elv").rename("elev_m"))
        .addBands(builtup)
        .addBands(dist)
    )


def reduce_barangays(metric: ee.Image, brgys: list[dict]) -> dict[int, dict]:
    bands = ["flood_frac", "hand_m", "elev_m", "builtup_prob", "dist_water_m"]
    out: dict[int, dict] = {}
    for i in range(0, len(brgys), CHUNK):
        chunk = brgys[i : i + CHUNK]
        fc = ee.FeatureCollection(
            [
                ee.Feature(
                    ee.Geometry(b["geometry"], proj="EPSG:4326", geodesic=False),
                    {"bidx": b["bidx"]},
                )
                for b in chunk
            ]
        )
        per = metric.reduceRegions(collection=fc, reducer=ee.Reducer.mean(), scale=SCALE, tileScale=8)
        got = per.select(["bidx"] + bands, retainGeometry=False).getInfo()["features"]
        for f in got:
            p = f["properties"]
            out[int(p["bidx"])] = {k: _num(p.get(k)) for k in bands}
        print(f"  reduce ...{min(i + CHUNK, len(brgys))}/{len(brgys)}")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="Observed flood inundation x canopy per NCR barangay")
    ap.add_argument("--force", action="store_true", help="ignore cache and re-run Earth Engine")
    ap.add_argument("--sanity", action="store_true", help="print NCR-wide diagnostics and exit")
    args = ap.parse_args()

    ee_init()
    brgys = load_barangays()
    print(f"barangays: {len(brgys)}")
    metric = build_metric_image()

    if args.sanity:
        ncr = ee.Geometry.Rectangle([120.9, 14.4, 121.15, 14.8], proj="EPSG:4326", geodesic=False)
        px_ha = ee.Image.pixelArea().divide(1e4)
        flooded_ha = (
            metric.select("flood_frac")
            .multiply(px_ha)
            .reduceRegion(ee.Reducer.sum(), ncr, SCALE, maxPixels=1e10, tileScale=8)
            .get("flood_frac")
            .getInfo()
        )
        print(f"NCR-wide flooded area (2025-07-23 vs ref): {flooded_ha:,.0f} ha")
        return 0

    cache = {} if args.force else (json.loads(CACHE.read_text()) if CACHE.exists() else {})
    metrics = cache.get("metrics")
    if not metrics:
        raw = reduce_barangays(metric, brgys)
        metrics = {str(k): v for k, v in raw.items()}
        CACHE.parent.mkdir(parents=True, exist_ok=True)
        CACHE.write_text(json.dumps({"metrics": metrics}))
    else:
        print(f"  reduce: reused {len(metrics)} barangay metrics from cache")
        metrics = {int(k): v for k, v in metrics.items()}
    metrics = {int(k): v for k, v in metrics.items()}

    rows = []
    for b in brgys:
        m = metrics.get(b["bidx"], {})
        ff = m.get("flood_frac")
        rows.append(
            {
                "barangay_name": b["barangay_name"],
                "lgu_name": b["lgu_name"],
                "total_ha": b["total_ha"],
                "canopy_pct_2025": b["canopy_pct_2025"],
                "canopy_pct_2019": b["canopy_pct_2019"],
                "canopy_trend_pct_per_yr": b["canopy_trend_pct_per_yr"],
                "flood_frac": round(ff, 5) if ff is not None else None,
                "flood_pct": round(100 * ff, 3) if ff is not None else None,
                "hand_m": round(m["hand_m"], 2) if m.get("hand_m") is not None else None,
                "elev_m": round(m["elev_m"], 2) if m.get("elev_m") is not None else None,
                "builtup_prob": round(m["builtup_prob"], 4) if m.get("builtup_prob") is not None else None,
                "dist_water_m": round(m["dist_water_m"], 1) if m.get("dist_water_m") is not None else None,
            }
        )
    rows.sort(key=lambda r: (-(r["flood_pct"] or -1), r["barangay_name"] or ""))

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k) for k in CSV_FIELDS})

    n_flooded = sum(1 for r in rows if (r["flood_pct"] or 0) > 0.5)
    fps = [r["flood_pct"] for r in rows if r["flood_pct"] is not None]
    print("\n" + "=" * 64)
    print(f"wrote {OUT_CSV.relative_to(REPO)} ({len(rows)} barangays)")
    print(f"  flood_pct: min={min(fps):.2f} max={max(fps):.2f} mean={sum(fps) / len(fps):.2f}")
    print(f"  barangays > 0.5% inundated: {n_flooded}")
    print(f"  worst: {rows[0]['barangay_name']} ({rows[0]['lgu_name']}) {rows[0]['flood_pct']}%")
    return 0


if __name__ == "__main__":
    sys.exit(main())
