"""Tag each tree-crown polygon as confirmed / new / candidate.

SolarMap.PH pattern adapted to canopy:
  - confirmed:    crown centroid is within OSM_RADIUS_M of any OSM
                  natural=tree point, OR inside an OSM landuse=forest /
                  leisure=park polygon.
  - candidate:    crown polygon has Meta p95 height < 4 m, low confidence
                  it's actually a tree (could be tall shrub).
  - new:          model finds it as canopy AND it's > 4 m tall AND no OSM
                  tag corroborates. These are the "model expansions."

Output: site/public/data/tree_crowns_ncr_tagged.geojson + .pmtiles
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import osm2geojson
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

ROOT = Path(__file__).resolve().parents[1]
CROWN_IN = ROOT / "site" / "public" / "data" / "tree_crowns_ncr.geojson"
OSM_LABELS = ROOT / "detection" / "bootstrap" / "osm_tree_labels.jsonl"
OSM_AREAS_CACHE = ROOT / "data" / "lgu" / "ncr_osm_canopy_areas.geojson"
CROWN_OUT = ROOT / "site" / "public" / "data" / "tree_crowns_ncr_tagged.geojson"
PMTILES_OUT = ROOT / "site" / "public" / "data" / "tree_crowns_ncr_tagged.pmtiles"

OSM_POINT_RADIUS_M = 30  # 30 m halo around OSM tree points
TALL_TREE_M = 8.0  # p95 >= 8 m -> high-confidence tree; below -> "candidate" tier
NCR_BBOX = (14.40, 120.90, 14.80, 121.15)
OVERPASS = "https://overpass-api.de/api/interpreter"
N_THREADS = 10


def fetch_osm_areas() -> list:
    if OSM_AREAS_CACHE.exists():
        print(f"[tag-crowns] using cached {OSM_AREAS_CACHE.name}")
        return json.loads(OSM_AREAS_CACHE.read_text()).get("features", [])
    bbox_str = ",".join(str(x) for x in NCR_BBOX)
    q = f"""[out:json][timeout:240];
(
  way["landuse"="forest"]({bbox_str});
  relation["landuse"="forest"]({bbox_str});
  way["leisure"="park"]({bbox_str});
  relation["leisure"="park"]({bbox_str});
  way["natural"="wood"]({bbox_str});
  relation["natural"="wood"]({bbox_str});
);
out geom;
"""
    print("[tag-crowns] fetching OSM canopy areas (forest+park+wood) via Overpass")
    req = urllib.request.Request(OVERPASS, data=q.encode("utf-8"), headers={"User-Agent": "leaves.ph/1.0"})
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=240) as r:
                data = json.loads(r.read().decode("utf-8"))
            break
        except Exception as e:
            print(f"  retry {attempt + 1}: {e}")
            time.sleep(15)
    else:
        raise RuntimeError("overpass failed")
    fc = osm2geojson.json2geojson(data)
    OSM_AREAS_CACHE.parent.mkdir(parents=True, exist_ok=True)
    OSM_AREAS_CACHE.write_text(json.dumps(fc))
    return fc.get("features", [])


def load_tree_points() -> list[tuple[float, float]]:
    pts = []
    for line in OSM_LABELS.open():
        row = json.loads(line)
        if row.get("label") == 1 and row.get("src") == "tree":
            pts.append((row["lat"], row["lon"]))
    return pts


def main() -> int:
    if not CROWN_IN.exists():
        print(f"missing {CROWN_IN}", file=sys.stderr)
        return 1

    print(f"[tag-crowns] loading {CROWN_IN.name}")
    fc = json.loads(CROWN_IN.read_text())
    crowns = fc["features"]
    print(f"[tag-crowns] {len(crowns)} crown polygons")

    # Build OSM corroboration layer
    print("[tag-crowns] loading OSM tree points + canopy areas")
    tree_points = load_tree_points()
    print(f"  {len(tree_points)} OSM tree points")
    osm_area_feats = fetch_osm_areas()
    print(f"  {len(osm_area_feats)} OSM canopy areas (forest/park/wood)")

    # Convert OSM tree points to geometries with a 30m buffer
    # 1 degree ~ 111,320 m at the equator; 30 m ~ 0.00027 deg
    point_buffer_deg = OSM_POINT_RADIUS_M / 111_320
    print(f"  buffering OSM tree points by {OSM_POINT_RADIUS_M}m ({point_buffer_deg:.5f} deg)")

    tree_buffer_geoms = [Point(lon, lat).buffer(point_buffer_deg) for (lat, lon) in tree_points]
    area_geoms = []
    for f in osm_area_feats:
        try:
            g = shape(f["geometry"])
            if not g.is_empty:
                area_geoms.append(g)
        except Exception:
            continue

    all_osm_geoms = tree_buffer_geoms + area_geoms
    if not all_osm_geoms:
        print("[tag-crowns] no OSM corroboration data; all crowns will be 'new'")
        tree = None
    else:
        print(f"[tag-crowns] building STRtree on {len(all_osm_geoms)} OSM geometries")
        tree = STRtree(all_osm_geoms)

    # Tag each crown
    print(f"[tag-crowns] tagging {len(crowns)} crowns (parallel x{N_THREADS})")

    def tag_one(feat):
        props = feat.get("properties") or {}
        try:
            g = shape(feat["geometry"])
            centroid = g.centroid
        except Exception:
            props["status"] = "candidate"
            return feat
        p95 = float(props.get("p95_height_m") or 0.0)
        # Check OSM corroboration first (OSM-tagged is always "confirmed")
        is_osm = False
        if tree is not None:
            hits = tree.query(centroid)
            for idx in hits:
                if all_osm_geoms[idx].contains(centroid) or all_osm_geoms[idx].intersects(g):
                    is_osm = True
                    break
        if is_osm:
            props["status"] = "confirmed"
        elif p95 >= TALL_TREE_M:
            props["status"] = "new"  # model-identified, tall (>= 8m p95)
        else:
            props["status"] = "candidate"  # model-identified, short (5-8m p95)
        return feat

    with ThreadPoolExecutor(max_workers=N_THREADS) as ex:
        tagged = list(ex.map(tag_one, crowns))

    # Stats
    from collections import Counter

    counts = Counter(f["properties"]["status"] for f in tagged)
    print("[tag-crowns] tag distribution:")
    for k, n in counts.most_common():
        print(f"  {k:>10s}  {n:>7,}  ({100 * n / len(tagged):.1f}%)")

    out_fc = {"type": "FeatureCollection", "features": tagged}
    print(f"[tag-crowns] writing {CROWN_OUT.name}")
    CROWN_OUT.write_text(json.dumps(out_fc))
    print(f"  size: {CROWN_OUT.stat().st_size / 1_000_000:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
