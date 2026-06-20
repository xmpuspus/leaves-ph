"""Tree-cover loss inside Philippine protected areas (WDPA x Hansen).

National extension of the per-barangay /accountability lens: instead of one
Metro Manila barangay against the DENR replacement rule, this ranks every
legally protected area in the country by the tree cover lost inside it since
2016.

Writes three artifacts, all generated from the same Earth Engine run so no
number is ever hand-typed:

    data/protected_areas/pa_forest_loss.csv        canonical per-PA table (hash-pinned)
    site/public/data/pa_forest_loss.geojson        per-PA simplified polygons + props (map + table)
    site/public/data/pa_forest_loss_summary.json   national totals + worst-ranked lists (page reads this)

Both inputs are Earth Engine assets, so there are no gated downloads:
    WCMC/WDPA/current/polygons                      filtered ISO3 == PHL
    UMD/hansen/global_forest_change_2025_v1_13      loss, lossyear, treecover2000

Honesty boundary (see the /protected-areas page and MODEL_CARD): Hansen "loss"
is tree-cover loss, i.e. stand replacement. It is NOT a deforestation verdict.
It includes plantation harvest, fire, and typhoon blowdown, and it cannot say
whether any clearing was permitted. The civic framing is "warrants review",
never accusation.

WDPA double-counting: a single physical site can appear under more than one
designation (a Natural Park that is also an ASEAN Heritage Park, a World
Heritage Site, or a Ramsar wetland). UNEP-WCMC warns against summing those
records. We exclude those international overlay designations so each site is
counted once under its national designation. The national headline is the sum
across those national records (deterministic and reproducible); per-PA figures
are exact, and the sum may slightly overcount where two national designations
overlap.

A run caches the Earth Engine results (per-PA loss and simplified geometries) to
a gitignored sidecar so re-runs that only touch the output formatting are fast.
Pass --force to recompute from scratch.

Run (network; personal EE key only, never a work GCP project):
    LEAVES_PH_EE_KEY=$PWD/.ee-key.json PYTHONPATH=. \
        .venv/bin/python pipeline/compute_pa_loss.py
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

HANSEN_ASSET = "UMD/hansen/global_forest_change_2025_v1_13"
WDPA_ASSET = "WCMC/WDPA/current/polygons"
TREECOVER_MIN = 30  # percent canopy in 2000 for a pixel to count as forest
WINDOW_START = 2016  # Hansen lossyear code 16
WINDOW_END = 2025  # latest year in the 2025_v1_13 asset (lossyear code 25)
LOSSYEAR_MIN = WINDOW_START - 2000  # 16
CHUNK = 8  # PAs per synchronous reduceRegions call (the 266-PA union times out)
SIMPLIFY_M = 500  # geometry simplification for the national overview map

# International overlay designations: each sits on top of an existing national
# PA, so summing them double-counts. Excluded from the published set.
INTL_OVERLAY = [
    "ASEAN Heritage Park",
    "World Heritage Site (natural or mixed)",
    "Wetland of International Importance (Ramsar Site)",
]
META_FIELDS = ["SITE_ID", "NAME", "DESIG", "DESIG_ENG", "IUCN_CAT", "STATUS", "STATUS_YR", "REP_AREA"]

OUT_CSV = REPO / "data" / "protected_areas" / "pa_forest_loss.csv"
OUT_GEOJSON = REPO / "site" / "public" / "data" / "pa_forest_loss.geojson"
OUT_SUMMARY = REPO / "site" / "public" / "data" / "pa_forest_loss_summary.json"
CACHE = REPO / "data" / "protected_areas" / ".pa_compute_cache.json"  # gitignored

CSV_FIELDS = [
    "rank",
    "site_id",
    "name",
    "desig",
    "iucn_cat",
    "status",
    "status_yr",
    "rep_area_ha",
    "area_ha",
    "forest2000_ha",
    "loss_ha",
    "pct_of_forest2000",
    "pct_of_pa",
]

DISCLAIMER = (
    "Statistical indicators derived from public-record satellite data. Hansen "
    "tree-cover loss is stand replacement (which includes plantation harvest, "
    "fire, and storm damage), not a finding of illegal or unpermitted clearing. "
    "Patterns may have legitimate explanations and warrant independent review."
)


def _f(v) -> float:
    return float(v) if v is not None else 0.0


def load_cache() -> dict:
    if CACHE.exists():
        try:
            return json.loads(CACHE.read_text())
        except Exception:
            return {}
    return {}


def save_cache(cache: dict) -> None:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    CACHE.write_text(json.dumps(cache))


def build_metrics() -> ee.Image:
    """Three summed bands: tree-cover loss (ha), year-2000 forest (ha), area (ha)."""
    gfc = ee.Image(HANSEN_ASSET)
    px_ha = ee.Image.pixelArea().divide(1e4)
    forest2000 = gfc.select("treecover2000").gte(TREECOVER_MIN)
    lost = gfc.select("loss").And(gfc.select("lossyear").gte(LOSSYEAR_MIN)).And(forest2000)
    return (
        lost.multiply(px_ha)
        .rename("loss_ha")
        .addBands(forest2000.multiply(px_ha).rename("forest2000_ha"))
        .addBands(px_ha.rename("area_ha"))
    )


def per_pa_rows(national: ee.FeatureCollection, metrics: ee.Image, ids: list[str], by_id: dict) -> list[dict]:
    """Sum the three bands inside each PA, batched to dodge the union timeout.

    A three-band image under ee.Reducer.sum() returns each value keyed by its
    band name, side-stepping the single-band 'sum' trap that read every PA as 0.
    """
    rows = []
    for i in range(0, len(ids), CHUNK):
        chunk = ids[i : i + CHUNK]
        sub = national.filter(ee.Filter.inList("SITE_ID", chunk))
        per = metrics.reduceRegions(collection=sub, reducer=ee.Reducer.sum(), scale=30, tileScale=16)
        got = per.select(["SITE_ID", "loss_ha", "forest2000_ha", "area_ha"], retainGeometry=False).getInfo()[
            "features"
        ]
        for f in got:
            p = f["properties"]
            sid = p.get("SITE_ID")
            meta = by_id.get(sid, {})
            loss = _f(p.get("loss_ha"))
            f2000 = _f(p.get("forest2000_ha"))
            area = _f(p.get("area_ha"))
            rows.append(
                {
                    "site_id": sid,
                    "name": meta.get("NAME"),
                    "desig": meta.get("DESIG"),
                    "iucn_cat": meta.get("IUCN_CAT"),
                    "status": meta.get("STATUS"),
                    "status_yr": meta.get("STATUS_YR"),
                    "rep_area_ha": round(_f(meta.get("REP_AREA")) * 100, 1),
                    "area_ha": round(area, 1),
                    "forest2000_ha": round(f2000, 1),
                    "loss_ha": round(loss, 1),
                    "pct_of_forest2000": round(100 * loss / f2000, 2) if f2000 > 0 else None,
                    "pct_of_pa": round(100 * loss / area, 3) if area > 0 else None,
                }
            )
        print(f"  loss ...{min(i + CHUNK, len(ids))}/{len(ids)}")
    # Stable order: worst first, site_id breaks ties so the hash is reproducible.
    rows.sort(key=lambda r: (-r["loss_ha"], str(r["site_id"])))
    for rank, r in enumerate(rows, start=1):
        r["rank"] = rank
    return rows


def rows_from_csv() -> list[dict] | None:
    if not OUT_CSV.exists():
        return None
    with OUT_CSV.open() as f:
        raw = list(csv.DictReader(f))
    rows = []
    for r in raw:
        rows.append(
            {
                "rank": int(r["rank"]),
                "site_id": r["site_id"],
                "name": r["name"],
                "desig": r["desig"],
                "iucn_cat": r["iucn_cat"] or None,
                "status": r["status"] or None,
                "status_yr": r["status_yr"] or None,
                "rep_area_ha": _f(r["rep_area_ha"]),
                "area_ha": _f(r["area_ha"]),
                "forest2000_ha": _f(r["forest2000_ha"]),
                "loss_ha": _f(r["loss_ha"]),
                "pct_of_forest2000": float(r["pct_of_forest2000"]) if r["pct_of_forest2000"] else None,
                "pct_of_pa": float(r["pct_of_pa"]) if r["pct_of_pa"] else None,
            }
        )
    return rows


def fetch_geometries(national: ee.FeatureCollection, ids: list[str]) -> dict[str, dict]:
    """Simplified polygon + server-side centroid per PA, for the overview map."""
    out: dict[str, dict] = {}

    def add_centroid(f):
        c = f.geometry().centroid(maxError=1000).coordinates()
        return f.set("cx", c.get(0), "cy", c.get(1))

    for i in range(0, len(ids), CHUNK):
        chunk = ids[i : i + CHUNK]
        sub = national.filter(ee.Filter.inList("SITE_ID", chunk)).map(
            lambda f: add_centroid(f.simplify(SIMPLIFY_M))
        )
        got = sub.select(["SITE_ID", "cx", "cy"]).getInfo()["features"]
        for f in got:
            p = f["properties"]
            # str key: CSV site_id is a string, EE SITE_ID is an int; align them.
            out[str(p["SITE_ID"])] = {
                "geometry": f.get("geometry"),
                "lon": round(p["cx"], 4) if p.get("cx") is not None else None,
                "lat": round(p["cy"], 4) if p.get("cy") is not None else None,
            }
        print(f"  geom ...{min(i + CHUNK, len(ids))}/{len(ids)}")
    return out


def normalize_geom(g: dict | None) -> dict | None:
    """Keep only polygonal geometry for the map; merge a GeometryCollection's
    polygon parts into a MultiPolygon; drop lines/points (over-simplified slivers)."""
    if not g:
        return None
    t = g.get("type")
    if t in ("Polygon", "MultiPolygon"):
        return g
    if t == "GeometryCollection":
        coords = []
        for sub in g.get("geometries", []):
            st = sub.get("type")
            if st == "Polygon":
                coords.append(sub["coordinates"])
            elif st == "MultiPolygon":
                coords.extend(sub["coordinates"])
        return {"type": "MultiPolygon", "coordinates": coords} if coords else None
    return None


def main() -> int:
    parser = argparse.ArgumentParser(description="Forest loss inside PH protected areas")
    parser.add_argument("--force", action="store_true", help="ignore cache and recompute everything")
    args = parser.parse_args()

    ee_init()
    metrics = build_metrics()

    pas = ee.FeatureCollection(WDPA_ASSET).filter(ee.Filter.eq("ISO3", "PHL"))
    n_total = pas.size().getInfo()
    national = pas.filter(ee.Filter.inList("DESIG", INTL_OVERLAY).Not())
    meta = national.select(META_FIELDS, retainGeometry=False).getInfo()["features"]
    by_id = {f["properties"]["SITE_ID"]: f["properties"] for f in meta}
    ids = list(by_id.keys())
    n_intl = n_total - len(ids)
    print(
        f"WDPA PH records: {n_total} | national designations kept: {len(ids)} | intl overlays excluded: {n_intl}"
    )

    cache = {} if args.force else load_cache()

    # ---- per-PA loss (reuse the canonical CSV if present and not --force) ----
    rows = None if args.force else rows_from_csv()
    if rows is None:
        rows = per_pa_rows(national, metrics, ids, by_id)
        OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
        with OUT_CSV.open("w", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
            w.writeheader()
            for r in rows:
                w.writerow({k: r.get(k) for k in CSV_FIELDS})
    else:
        print(f"  loss: reused {len(rows)} rows from {OUT_CSV.name}")

    dedup_sum = round(sum(r["loss_ha"] for r in rows), 1)
    forest2000 = round(sum(r["forest2000_ha"] for r in rows), 1)

    # National total = sum across national-designation records, with international
    # overlays already excluded so no site is counted twice. This is deterministic
    # and reproducible (unlike a synchronous geometric-dissolve reduce, which times
    # out under EE load). Residual overlap between two national designations may
    # still slightly inflate the sum; per-PA figures are exact regardless.
    headline = dedup_sum
    method = "national-designations-sum"
    n_with_loss = sum(1 for r in rows if r["loss_ha"] > 1)

    # ---- geometries (cached) ----
    geoms = cache.get("geoms")
    if not geoms:
        geoms = fetch_geometries(national, ids)
        cache["geoms"] = geoms
        save_cache(cache)
    else:
        print(f"  geom: reused {len(geoms)} geometries from cache")

    # ---- GeoJSON (map + table) ----
    features = []
    for r in rows:
        gc = geoms.get(str(r["site_id"])) or {}
        geom = normalize_geom(gc.get("geometry"))
        features.append(
            {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "rank": r["rank"],
                    "site_id": r["site_id"],
                    "name": r["name"],
                    "desig": r["desig"],
                    "iucn_cat": r["iucn_cat"],
                    "status_yr": r["status_yr"],
                    "loss_ha": r["loss_ha"],
                    "forest2000_ha": r["forest2000_ha"],
                    "area_ha": r["area_ha"],
                    "rep_area_ha": r["rep_area_ha"],
                    "pct_of_forest2000": r["pct_of_forest2000"],
                    "pct_of_pa": r["pct_of_pa"],
                    "lon": gc.get("lon"),
                    "lat": gc.get("lat"),
                },
            }
        )
    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_GEOJSON.write_text(
        json.dumps({"type": "FeatureCollection", "features": features}, separators=(",", ":"))
    )

    # ---- Summary (the page reads this; no number is hand-typed) ----
    def slim(r):
        return {
            "name": r["name"],
            "desig": r["desig"],
            "loss_ha": round(r["loss_ha"]),
            "pct_of_forest2000": r["pct_of_forest2000"],
            "forest2000_ha": round(r["forest2000_ha"]),
        }

    by_pct = sorted(
        (r for r in rows if r["forest2000_ha"] >= 500 and r["pct_of_forest2000"] is not None),
        key=lambda r: -r["pct_of_forest2000"],
    )
    summary = {
        "hansen_asset": HANSEN_ASSET,
        "wdpa_asset": WDPA_ASSET,
        "window_start": WINDOW_START,
        "window_end": WINDOW_END,
        "treecover_min_pct": TREECOVER_MIN,
        "n_wdpa_records": n_total,
        "n_protected_areas": len(rows),
        "n_intl_overlays_excluded": n_intl,
        "n_with_loss": n_with_loss,
        "total_loss_ha": round(headline),
        "total_loss_method": method,
        "total_loss_dedup_sum_ha": round(dedup_sum),
        "forest2000_ha": round(forest2000),
        "pct_of_pa_forest_lost": round(100 * headline / forest2000, 2) if forest2000 else None,
        "worst_by_ha": [slim(r) for r in rows[:15]],
        "worst_by_pct": [slim(r) for r in by_pct[:12]],
        "disclaimer": DISCLAIMER,
    }
    OUT_SUMMARY.write_text(json.dumps(summary, indent=2))

    n_geom = sum(1 for f in features if f["geometry"])
    print("\n" + "=" * 72)
    print(f"headline national total ({method}): {round(headline):,} ha")
    print(f"  deduplicated per-PA sum: {round(dedup_sum):,} ha across {len(rows)} PAs")
    print(
        f"  {n_with_loss} PAs with > 1 ha loss; {round(100 * headline / forest2000, 2)}% of year-2000 forest"
    )
    print(
        f"  worst: {rows[0]['name']} = {round(rows[0]['loss_ha']):,} ha ({rows[0]['pct_of_forest2000']}% of its forest)"
    )
    print(f"  geojson features: {len(features)} ({n_geom} with polygon geometry)")
    print(
        f"wrote {OUT_CSV.relative_to(REPO)}, {OUT_GEOJSON.relative_to(REPO)}, {OUT_SUMMARY.relative_to(REPO)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
