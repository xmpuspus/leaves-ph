"""Per-barangay canopy from the human-calibrated model product (canopy_<year>.tif,
binary 0/1, 255 nodata). Mirrors aggregate_barangay.py but reads the published model
masks instead of the CLIP density. Keys: canopy_pct_model_<year>, canopy_ha_model_<year>.

Outputs:
  data/per_barangay/per_barangay_canopy_2019_2026_model.csv
  site/public/data/per_barangay_canopy_model.geojson
"""

from __future__ import annotations

import csv
import json
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
import rasterio
from rasterio.features import geometry_mask
from shapely.geometry import shape

ROOT = Path(__file__).resolve().parents[1]
COMP = ROOT / "data" / "composites"
BARANGAY_GEOJSON = ROOT / "data" / "lgu" / "ncr_barangays.geojson"
LGU_GEOJSON = ROOT / "data" / "lgu" / "ncr_lgu.geojson"
OUT_CSV = ROOT / "data" / "per_barangay" / "per_barangay_canopy_2019_2026_model.csv"
OUT_GEOJSON = ROOT / "site" / "public" / "data" / "per_barangay_canopy_model.geojson"
YEARS = list(range(2019, 2027))
N_THREADS = 8


def filter_ncr(barangay_fc, lgu_polys):
    out = []
    for f in barangay_fc["features"]:
        try:
            pt = shape(f["geometry"]).representative_point()
        except Exception:
            continue
        for lgu_name, poly in lgu_polys:
            if poly.contains(pt):
                f.setdefault("properties", {})["lgu_name"] = lgu_name
                out.append(f)
                break
    return out


def stats(args):
    name, lgu_name, geom, rasters, transform, H, W, pix_area_m2 = args
    try:
        mask = ~geometry_mask([geom], out_shape=(H, W), transform=transform, invert=False)
    except Exception:
        return None
    if not mask.any():
        return None
    row = {"barangay_name": name, "lgu_name": lgu_name}
    total_valid = None
    for year, arr in rasters.items():
        cell = arr[mask]
        valid = cell != 255
        nv = int(valid.sum())
        if nv == 0:
            row[f"canopy_pct_model_{year}"] = 0.0
            row[f"canopy_ha_model_{year}"] = 0.0
            continue
        frac = float((cell[valid] == 1).mean())
        row[f"canopy_pct_model_{year}"] = round(frac * 100, 3)
        row[f"canopy_ha_model_{year}"] = round(float((cell[valid] == 1).sum()) * pix_area_m2 / 10_000, 1)
        total_valid = nv
    row["total_ha"] = round((total_valid or 0) * pix_area_m2 / 10_000, 1)
    return row


def main() -> int:
    barangay_fc = json.loads(BARANGAY_GEOJSON.read_text())
    lgu_fc = json.loads(LGU_GEOJSON.read_text())
    lgu_polys = [(f["properties"]["lgu_name"], shape(f["geometry"])) for f in lgu_fc["features"]]
    ncr = filter_ncr(barangay_fc, lgu_polys)
    print(f"[barangay-model] {len(ncr)} barangays inside NCR")

    with rasterio.open(COMP / f"canopy_{YEARS[0]}.tif") as src:
        transform, H, W, bounds = src.transform, src.height, src.width, src.bounds
    rasters = {}
    for y in YEARS:
        p = COMP / f"canopy_{y}.tif"
        if p.exists():
            with rasterio.open(p) as src:
                rasters[y] = src.read(1)
    lat_c = (bounds.bottom + bounds.top) / 2
    pix_area = abs(transform.a) * abs(transform.e) * 111_320 * 111_320 * np.cos(np.radians(lat_c))

    args = [
        (
            f["properties"].get("barangay_name", f["properties"].get("name", "?")),
            f["properties"].get("lgu_name", "?"),
            f["geometry"],
            rasters,
            transform,
            H,
            W,
            pix_area,
        )
        for f in ncr
    ]
    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        rows = [r for r in ex.map(stats, args) if r is not None]
    rows.sort(key=lambda r: (r["lgu_name"], r["barangay_name"]))

    headers = (
        ["barangay_name", "lgu_name", "total_ha"]
        + [f"canopy_pct_model_{y}" for y in YEARS]
        + [f"canopy_ha_model_{y}" for y in YEARS]
    )
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with OUT_CSV.open("w") as fh:
        w = csv.DictWriter(fh, fieldnames=headers)
        w.writeheader()
        w.writerows(rows)
    print(f"[barangay-model] wrote {OUT_CSV.relative_to(ROOT)} ({len(rows)} barangays)")

    by = {(r["barangay_name"], r["lgu_name"]): r for r in rows}
    feats = []
    for f in ncr:
        key = (
            f["properties"].get("barangay_name", f["properties"].get("name", "?")),
            f["properties"].get("lgu_name", "?"),
        )
        if key in by:
            feats.append({"type": "Feature", "geometry": f["geometry"], "properties": dict(by[key])})
    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
    print(f"[barangay-model] wrote {OUT_GEOJSON.relative_to(ROOT)} ({len(feats)} features)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
