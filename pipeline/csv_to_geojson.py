"""Merge per-LGU canopy CSV into the LGU polygon GeoJSON for the Astro site.

Reads:
    data/lgu/ncr_lgu.geojson                            (17 polygons)
    data/per_lgu/per_lgu_canopy_2019_2026.csv           (one row per LGU, year)

Writes:
    site/public/data/per_lgu_canopy.geojson
        Each feature has properties:
            lgu_name: str
            canopy_<year>_ha:  float for year in 2019..2026
            canopy_<year>_pct: float for year in 2019..2026
            canopy_delta_2019_2026_pct: float
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
LGU_GEOJSON = REPO_ROOT / "data" / "lgu" / "ncr_lgu.geojson"
PER_LGU_CSV = REPO_ROOT / "data" / "per_lgu" / "per_lgu_canopy_2019_2026.csv"
OUT_GEOJSON = REPO_ROOT / "site" / "public" / "data" / "per_lgu_canopy.geojson"


def main() -> int:
    parser = argparse.ArgumentParser(description="Merge per-LGU CSV into LGU GeoJSON for the site")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    if not LGU_GEOJSON.exists():
        print(f"[csv_to_geojson] MISSING {LGU_GEOJSON}; run fetch_lgu_polygons.py first", file=sys.stderr)
        return 1
    if not PER_LGU_CSV.exists():
        print(f"[csv_to_geojson] MISSING {PER_LGU_CSV}; run aggregate_lgu.py first", file=sys.stderr)
        return 1
    if OUT_GEOJSON.exists() and not args.force:
        print(f"[csv_to_geojson] {OUT_GEOJSON.name} already exists; skip (use --force)")
        return 0

    OUT_GEOJSON.parent.mkdir(parents=True, exist_ok=True)

    lgu_fc = json.loads(LGU_GEOJSON.read_text())
    by_lgu_year: dict[str, dict[int, dict]] = defaultdict(dict)
    with PER_LGU_CSV.open() as f:
        reader = csv.DictReader(f)
        for row in reader:
            lgu = row["lgu_name"]
            year = int(row["year"])
            by_lgu_year[lgu][year] = {
                "canopy_ha": float(row["canopy_ha"]) if row["canopy_ha"] else None,
                "canopy_pct": float(row["canopy_pct"]) if row["canopy_pct"] else None,
                "total_ha": float(row["total_ha"]) if row["total_ha"] else None,
                "hansen_loss_ha_cumulative": (
                    float(row["hansen_loss_ha_cumulative"]) if row["hansen_loss_ha_cumulative"] else None
                ),
                "esa_tree_pct_2021": (float(row["esa_tree_pct_2021"]) if row["esa_tree_pct_2021"] else None),
            }

    for feature in lgu_fc.get("features", []):
        lgu = feature.get("properties", {}).get("lgu_name")
        if lgu not in by_lgu_year:
            continue
        years = by_lgu_year[lgu]
        for year, stats in years.items():
            feature["properties"][f"canopy_{year}_ha"] = stats["canopy_ha"]
            feature["properties"][f"canopy_{year}_pct"] = stats["canopy_pct"]
        # Hansen cumulative + ESA 2021 are static (year-independent in this product).
        if years:
            sample = next(iter(years.values()))
            feature["properties"]["hansen_loss_ha_cumulative_2024"] = sample["hansen_loss_ha_cumulative"]
            feature["properties"]["esa_tree_pct_2021"] = sample["esa_tree_pct_2021"]
            feature["properties"]["total_ha"] = sample["total_ha"]
        # Delta 2019-2026 (only if both endpoints exist).
        if 2019 in years and 2026 in years:
            v0 = years[2019]["canopy_pct"]
            v1 = years[2026]["canopy_pct"]
            if v0 is not None and v1 is not None:
                feature["properties"]["canopy_delta_2019_2026_pct"] = round(v1 - v0, 2)

    OUT_GEOJSON.write_text(json.dumps(lgu_fc, indent=2))
    print(
        f"[csv_to_geojson] wrote {len(lgu_fc.get('features', []))} features "
        f"-> {OUT_GEOJSON.relative_to(REPO_ROOT)}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
