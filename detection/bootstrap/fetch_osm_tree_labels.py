"""Bootstrap label-point fetcher for the CLIP+LR tree-cover classifier.

Mirrors detection/bootstrap/fetch_osm_solar.py from solar-map-ph: pulls
labelled point coordinates from OpenStreetMap inside the 17 NCR LGUs, splits
into positive (canopy-bearing) and negative (built / paved) classes, snaps
each point to a stable LGU name, writes JSONL.

Positives  (label=1):
  natural=tree                  individual trees (point)
  landuse=forest                forest polygon (sample interior centroid)
  leisure=park                  park polygon  (sample interior centroid)

Negatives  (label=0):
  building=*                    building polygon (interior centroid)
  highway in {motorway,trunk,primary,secondary}  road centerlines (sampled)
  landuse in {industrial,commercial,retail}     industrial polygons

Output: detection/bootstrap/osm_tree_labels.jsonl
        {lat, lon, label, src, lgu_name}

Target: ~3,000 positive + ~3,000 negative points, stratified roughly evenly
across the 17 NCR LGUs.
"""

from __future__ import annotations

import json
import random
import sys
import time
import urllib.request
from pathlib import Path

from shapely.geometry import Point, shape

ROOT = Path(__file__).resolve().parents[2]
LGU_GEOJSON = ROOT / "data" / "lgu" / "ncr_lgu.geojson"
OUT_JSONL = ROOT / "detection" / "bootstrap" / "osm_tree_labels.jsonl"

OVERPASS = "https://overpass-api.de/api/interpreter"
NCR_BBOX = (14.40, 120.90, 14.80, 121.15)  # (s, w, n, e)

POS_QUERIES = {
    "tree": '(node["natural"="tree"]({bbox}););',
    "forest": '(way["landuse"="forest"]({bbox});relation["landuse"="forest"]({bbox}););',
    "park": '(way["leisure"="park"]({bbox});relation["leisure"="park"]({bbox}););',
}

NEG_QUERIES = {
    "building": '(way["building"]({bbox}););',
    "road": '(way["highway"~"motorway|trunk|primary|secondary"]({bbox}););',
    "industrial": '(way["landuse"~"industrial|commercial|retail"]({bbox});relation["landuse"~"industrial|commercial|retail"]({bbox}););',
}

# Per-class sample caps. Trees are point-rich; we cap to keep balance.
POS_CAPS = {"tree": 1800, "forest": 700, "park": 500}
NEG_CAPS = {"building": 1800, "road": 700, "industrial": 500}


def overpass(query_body: str) -> dict:
    bbox_str = f"{NCR_BBOX[0]},{NCR_BBOX[1]},{NCR_BBOX[2]},{NCR_BBOX[3]}"
    query = f"[out:json][timeout:120];{query_body.format(bbox=bbox_str)}out center;"
    print(f"  overpass: {len(query)} chars")
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


def element_points(elements: list) -> list[tuple[float, float]]:
    out: list[tuple[float, float]] = []
    for el in elements:
        if el.get("type") == "node":
            out.append((el["lat"], el["lon"]))
        elif "center" in el:
            out.append((el["center"]["lat"], el["center"]["lon"]))
    return out


def load_lgu_polygons() -> list[tuple[str, shape]]:
    fc = json.loads(LGU_GEOJSON.read_text())
    return [(f["properties"]["lgu_name"], shape(f["geometry"])) for f in fc["features"]]


def snap_to_lgu(lat: float, lon: float, lgus) -> str | None:
    p = Point(lon, lat)
    for name, poly in lgus:
        if poly.contains(p):
            return name
    return None


def fetch_class(queries: dict, caps: dict, label: int, lgus) -> list[dict]:
    rng = random.Random(4242 + label)
    rows: list[dict] = []
    for src, q in queries.items():
        print(f"  -> {src}")
        data = overpass(q)
        pts = element_points(data.get("elements", []))
        rng.shuffle(pts)
        kept = 0
        for lat, lon in pts:
            lgu = snap_to_lgu(lat, lon, lgus)
            if not lgu:
                continue
            rows.append({"lat": lat, "lon": lon, "label": label, "src": src, "lgu_name": lgu})
            kept += 1
            if kept >= caps.get(src, 1_000):
                break
        print(f"    kept {kept} (of {len(pts)} returned)")
    return rows


def main() -> int:
    print("[bootstrap] loading NCR LGU polygons")
    lgus = load_lgu_polygons()
    print(f"[bootstrap] {len(lgus)} LGUs loaded")

    print("[bootstrap] fetching POSITIVES")
    pos = fetch_class(POS_QUERIES, POS_CAPS, label=1, lgus=lgus)
    print(f"[bootstrap] positives: {len(pos)}")

    print("[bootstrap] fetching NEGATIVES")
    neg = fetch_class(NEG_QUERIES, NEG_CAPS, label=0, lgus=lgus)
    print(f"[bootstrap] negatives: {len(neg)}")

    OUT_JSONL.parent.mkdir(parents=True, exist_ok=True)
    rows = pos + neg
    random.Random(42).shuffle(rows)
    with OUT_JSONL.open("w") as fh:
        for r in rows:
            fh.write(json.dumps(r) + "\n")
    print(f"[bootstrap] wrote {OUT_JSONL.relative_to(ROOT)} ({len(rows)} rows)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
