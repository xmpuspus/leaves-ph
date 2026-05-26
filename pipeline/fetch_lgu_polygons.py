"""Fetch NCR LGU polygons (17 LGUs: 16 cities + Pateros) from OSM via Overpass.

NCR LGU admin_level in OSM is typically 5 (city) or 6 (municipality / district).
We pull all admin_level 5+6 relations within the NCR area filter and match
them against the canonical NCR_LGUS list using OSM_NAME_VARIANTS.

Output:
    data/lgu/ncr_lgu.geojson           FeatureCollection with `lgu_name` property
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
OUT_DIR = REPO_ROOT / "data" / "lgu"
OUT_PATH = OUT_DIR / "ncr_lgu.geojson"
MANIFEST = OUT_DIR / "_fetch_manifest_lgu.json"

NCR_LGUS = (
    "Manila",
    "Quezon City",
    "Caloocan",
    "Las Pinas",
    "Makati",
    "Malabon",
    "Mandaluyong",
    "Marikina",
    "Muntinlupa",
    "Navotas",
    "Paranaque",
    "Pasay",
    "Pasig",
    "San Juan",
    "Taguig",
    "Valenzuela",
    "Pateros",
)

OSM_NAME_VARIANTS = {
    "Manila": ["City of Manila", "Manila"],
    "Quezon City": ["Quezon City"],
    "Caloocan": ["Caloocan", "Caloocan City", "City of Caloocan"],
    "Las Pinas": ["Las Pinas", "Las Pinas City", "Las Piñas", "Las Piñas City"],
    "Makati": ["Makati", "Makati City", "City of Makati"],
    "Malabon": ["Malabon", "Malabon City"],
    "Mandaluyong": ["Mandaluyong", "Mandaluyong City"],
    "Marikina": ["Marikina", "Marikina City"],
    "Muntinlupa": ["Muntinlupa", "Muntinlupa City"],
    "Navotas": ["Navotas", "Navotas City"],
    "Paranaque": ["Paranaque", "Paranaque City", "Parañaque", "Parañaque City"],
    "Pasay": ["Pasay", "Pasay City"],
    "Pasig": ["Pasig", "Pasig City"],
    "San Juan": ["San Juan", "San Juan City"],
    "Taguig": ["Taguig", "Taguig City"],
    "Valenzuela": ["Valenzuela", "Valenzuela City"],
    "Pateros": ["Pateros"],
}

OVERPASS_URL = "https://overpass-api.de/api/interpreter"
OVERPASS_QUERY = """
[out:json][timeout:120];
area["ISO3166-2"="PH-00"]->.ncr;
(
  relation["admin_level"="5"](area.ncr);
  relation["admin_level"="6"](area.ncr);
);
out tags geom;
"""


def fetch_overpass(query: str = OVERPASS_QUERY) -> dict:
    data = ("data=" + query).encode("utf-8")
    req = urllib.request.Request(
        OVERPASS_URL,
        data=data,
        headers={"User-Agent": "leaves-ph/0.1.0 (https://github.com/xmpuspus/leaves-ph)"},
    )
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.loads(resp.read().decode("utf-8"))


def osm_relation_to_geojson(rel: dict, lgu_name: str) -> dict | None:
    outer: list[list[tuple[float, float]]] = []
    inner: list[list[tuple[float, float]]] = []
    for member in rel.get("members", []):
        if member.get("type") != "way":
            continue
        role = member.get("role", "outer")
        geom = member.get("geometry") or []
        ring = [(node["lon"], node["lat"]) for node in geom]
        if not ring:
            continue
        if role == "outer":
            outer.append(ring)
        elif role == "inner":
            inner.append(ring)
    if not outer:
        return None

    def _close(r):
        return r if r and r[0] == r[-1] else r + [r[0]]

    outer = [_close(r) for r in outer]
    inner = [_close(r) for r in inner]
    if len(outer) == 1 and not inner:
        coords = [[list(pt) for pt in outer[0]]]
        gtype = "Polygon"
    else:
        polys = [[[list(pt) for pt in r]] for r in outer]
        if inner and polys:
            polys[0].extend([[list(pt) for pt in r] for r in inner])
        coords = polys
        gtype = "MultiPolygon"

    return {
        "type": "Feature",
        "geometry": {"type": gtype, "coordinates": coords},
        "properties": {
            "lgu_name": lgu_name,
            "osm_id": rel.get("id"),
            "osm_admin_level": rel.get("tags", {}).get("admin_level"),
            "osm_name": rel.get("tags", {}).get("name"),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Fetch NCR LGU polygons from OSM")
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if OUT_PATH.exists() and not args.force:
        print(f"[fetch_lgu] {OUT_PATH.name} already exists; skip (use --force to re-fetch)")
        return 0

    print(f"[fetch_lgu] querying Overpass: {OVERPASS_URL}")
    resp = fetch_overpass()
    elements = resp.get("elements", [])
    print(f"[fetch_lgu] Overpass returned {len(elements)} elements")

    by_canonical: dict[str, dict] = {}
    for rel in elements:
        if rel.get("type") != "relation":
            continue
        name = rel.get("tags", {}).get("name", "")
        for canonical, variants in OSM_NAME_VARIANTS.items():
            if name in variants:
                existing = by_canonical.get(canonical)
                if existing is None or (
                    rel.get("tags", {}).get("admin_level") == "5"
                    and existing.get("tags", {}).get("admin_level") != "5"
                ):
                    by_canonical[canonical] = rel
                break

    print(f"[fetch_lgu] matched {len(by_canonical)} / {len(NCR_LGUS)} LGUs by OSM name")
    missing = [lgu for lgu in NCR_LGUS if lgu not in by_canonical]
    if missing:
        print(f"[fetch_lgu] MISSING: {missing}")

    features = []
    for lgu in NCR_LGUS:
        rel = by_canonical.get(lgu)
        if rel is None:
            continue
        feature = osm_relation_to_geojson(rel, lgu)
        if feature is not None:
            features.append(feature)

    fc = {"type": "FeatureCollection", "features": features}
    OUT_PATH.write_text(json.dumps(fc, indent=2))
    print(f"[fetch_lgu] wrote {len(features)} features -> {OUT_PATH.relative_to(REPO_ROOT)}")

    MANIFEST.write_text(
        json.dumps(
            {
                "source": "Overpass API (OSM)",
                "url": OVERPASS_URL,
                "lgu_count_canonical": len(NCR_LGUS),
                "lgu_count_matched": len(features),
                "missing": missing,
            },
            indent=2,
            sort_keys=True,
        )
    )
    if len(features) != len(NCR_LGUS):
        print("[fetch_lgu] WARNING: matched count != canonical count; investigate before Phase 3")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
