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
out geom;
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


def osm_relation_to_geojson(rel: dict, lgu_name: str, full_response: dict) -> dict | None:
    """Assemble an OSM admin relation into a proper (Multi)Polygon GeoJSON
    Feature.

    OSM admin boundaries are stored as relations whose member ways form the
    outer (and sometimes inner) ring of the polygon when chained end-to-end.
    Each individual way is just a segment of the boundary, NOT a complete ring,
    so naive per-way conversion produces useless fragments (rasterio rejects
    them as 3-point line strings).

    We delegate the standard MultiPolygon assembly algorithm to the
    `osm2geojson` library, which implements the OSM-standard ring chaining.
    """
    try:
        import osm2geojson
    except ImportError as e:
        raise RuntimeError(
            "osm2geojson is required (pip install osm2geojson). "
            "It handles OSM relation -> MultiPolygon assembly correctly."
        ) from e

    # osm2geojson works on a full Overpass JSON response. We feed it the full
    # response and pull out the one relation we care about by OSM id.
    target_id = rel["id"]
    fc = osm2geojson.json2geojson(full_response)
    for feature in fc.get("features", []):
        props = feature.get("properties") or {}
        # osm2geojson nests OSM tags under properties.tags and the id under
        # properties.id (with type prefix). Match by OSM id either way.
        if props.get("id") == target_id or props.get("id") == f"relation/{target_id}":
            geom = feature.get("geometry")
            if geom is None:
                continue
            return {
                "type": "Feature",
                "geometry": geom,
                "properties": {
                    "lgu_name": lgu_name,
                    "osm_id": target_id,
                    "osm_admin_level": rel.get("tags", {}).get("admin_level"),
                    "osm_name": rel.get("tags", {}).get("name"),
                },
            }
    return None


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
        feature = osm_relation_to_geojson(rel, lgu, resp)
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
        print(
            "[fetch_lgu] WARNING: matched count != canonical count; investigate before running the compute step"
        )
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
