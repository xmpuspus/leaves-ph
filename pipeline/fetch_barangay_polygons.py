"""Fetch admin-level=10 (barangay) polygons for the 17 NCR LGUs from OSM.

Uses the same Overpass pattern as fetch_lgu_polygons.py but at admin-level=10.
NCR has 142 barangays in the PSA canonical inventory; OSM coverage varies.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

import osm2geojson

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "lgu" / "ncr_barangays.geojson"
OVERPASS = "https://overpass-api.de/api/interpreter"

# bbox covers all NCR + small buffer
S, W, N, E = 14.40, 120.90, 14.80, 121.15


def overpass(query: str) -> dict:
    req = urllib.request.Request(
        OVERPASS, data=query.encode("utf-8"), headers={"User-Agent": "leaves.ph/1.0"}
    )
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=180) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as e:
            print(f"  overpass retry {attempt + 1}: {e}")
            time.sleep(15)
    raise RuntimeError("overpass failed 3x")


def main() -> int:
    bbox_str = f"{S},{W},{N},{E}"
    q = f"""[out:json][timeout:240];
(
  relation["admin_level"="10"]["boundary"="administrative"]({bbox_str});
);
out geom;
"""
    print("[barangay] fetching admin-level=10 in NCR bbox")
    data = overpass(q)
    elements = data.get("elements", [])
    print(f"[barangay] overpass returned {len(elements)} elements")

    fc = osm2geojson.json2geojson(data)
    feats = fc.get("features", [])
    cleaned = []
    for f in feats:
        props = f.get("properties", {}) or {}
        tags = props.get("tags", {}) or {}
        if tags.get("admin_level") != "10":
            continue
        name = tags.get("name") or tags.get("official_name") or props.get("name") or ""
        if not name:
            continue
        cleaned.append(
            {
                "type": "Feature",
                "geometry": f["geometry"],
                "properties": {
                    "barangay_name": name,
                    "lgu_hint": tags.get("is_in:city") or tags.get("is_in") or "",
                    "osm_id": props.get("id"),
                },
            }
        )
    out_fc = {"type": "FeatureCollection", "features": cleaned}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out_fc, indent=2))
    print(f"[barangay] wrote {OUT.relative_to(ROOT)} with {len(cleaned)} barangays")
    return 0


if __name__ == "__main__":
    sys.exit(main())
