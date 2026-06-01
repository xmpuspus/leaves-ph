"""Tier 3 proof-of-concept: fetch Cebu City for 2024 only.

Demonstrates the SolarMap-pattern pipeline generalises beyond NCR. Fetches:
  - S2 L2A RGB composite for 2024 at 30m
  - Meta Canopy Height v2 clip for the Cebu bbox
  - OSM admin-level=8 polygon for Cebu City (city boundary)
  - OSM admin-level=10 polygons for Cebu barangays

Then re-runs the v9 GBR head to predict canopy density for Cebu, aggregates
to LGU + barangay level, writes CSV + GeoJSON.

Outputs (under data/cebu/ to keep separate from NCR):
  data/cebu/s2_rgb_2024.tif
  data/cebu/canopy_height.tif
  data/cebu/cebu_lgu.geojson
  data/cebu/cebu_barangays.geojson
  detection/scan_cebu/clf_v9_density_2024.tif
  detection/scan_cebu/clf_v9_per_barangay_2024.csv
"""

from __future__ import annotations

import json
import sys
import time
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT / "pipeline"))
from _gee_init import init

CEBU_BBOX = (123.84, 10.25, 124.05, 10.45)  # (min_lon, min_lat, max_lon, max_lat)
CEBU_DIR = REPO_ROOT / "data" / "cebu"
SCAN_DIR = REPO_ROOT / "detection" / "scan_cebu"

OVERPASS = "https://overpass-api.de/api/interpreter"


def fetch_s2() -> None:
    out_path = CEBU_DIR / "s2_rgb_2024.tif"
    if out_path.exists():
        print(f"[cebu-s2] {out_path.name} exists; skip")
        return
    init()
    import ee
    import geemap

    geom = ee.Geometry.Rectangle(list(CEBU_BBOX), proj="EPSG:4326", geodesic=False)
    s2 = (
        ee.ImageCollection("COPERNICUS/S2_SR_HARMONIZED")
        .filterBounds(geom)
        .filterDate("2024-01-01", "2025-01-01")
        .filter(ee.Filter.lt("CLOUDY_PIXEL_PERCENTAGE", 80))
    )
    s2_cloud = (
        ee.ImageCollection("COPERNICUS/S2_CLOUD_PROBABILITY")
        .filterBounds(geom)
        .filterDate("2024-01-01", "2025-01-01")
    )
    joined = ee.Join.saveFirst("cloud_prob").apply(
        primary=s2,
        secondary=s2_cloud,
        condition=ee.Filter.equals(leftField="system:index", rightField="system:index"),
    )

    def _mask(img):
        cloud = ee.Image(img.get("cloud_prob")).select("probability")
        return img.updateMask(cloud.lt(40))

    masked = ee.ImageCollection(joined).map(_mask)
    composite = masked.median().select(["B4", "B3", "B2"]).rename(["red", "green", "blue"]).clip(geom)
    n = masked.size().getInfo()
    print(f"[cebu-s2] {n} source images; exporting RGB at 30m")

    CEBU_DIR.mkdir(parents=True, exist_ok=True)
    geemap.ee_export_image(
        composite, filename=str(out_path), scale=30, region=geom, crs="EPSG:4326", file_per_band=False
    )


def fetch_meta_canopy() -> None:
    """Fetch Meta Canopy Height v2 from S3 for the Cebu quadkeys.

    Mirrors pipeline/fetch_meta_canopy_height.py but for Cebu bbox.
    """
    import math

    import boto3
    import rasterio
    from botocore import UNSIGNED
    from botocore.config import Config
    from rasterio.merge import merge
    from rasterio.warp import Resampling, calculate_default_transform, reproject

    out_path = CEBU_DIR / "canopy_height.tif"
    if out_path.exists():
        print(f"[cebu-meta] {out_path.name} exists; skip")
        return

    def lonlat_to_quadkey(lon, lat, zoom):
        sin_lat = math.sin(lat * math.pi / 180.0)
        x = (lon + 180.0) / 360.0
        y = 0.5 - math.log((1 + sin_lat) / (1 - sin_lat)) / (4 * math.pi)
        n = 2**zoom
        tx = int(x * n)
        ty = int(y * n)
        quadkey = ""
        for i in range(zoom, 0, -1):
            digit = 0
            mask = 1 << (i - 1)
            if (tx & mask) != 0:
                digit += 1
            if (ty & mask) != 0:
                digit += 2
            quadkey += str(digit)
        return quadkey

    # Cebu bbox corners -> zoom-9 quadkeys
    zoom = 9
    lon_min, lat_min, lon_max, lat_max = CEBU_BBOX
    qks = set()
    for lon in (lon_min, lon_max):
        for lat in (lat_min, lat_max):
            qks.add(lonlat_to_quadkey(lon, lat, zoom))
    print(f"[cebu-meta] needs zoom-{zoom} quadkeys: {sorted(qks)}")

    CEBU_DIR.mkdir(parents=True, exist_ok=True)
    s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    tmp_files = []
    for qk in sorted(qks):
        key = f"forests/v1/alsgedi_global_v6_float/chm/{qk}.tif"
        local = CEBU_DIR / f"meta_{qk}.tif"
        if not local.exists():
            try:
                print(f"  downloading s3://dataforgood-fb-data/{key}")
                s3.download_file("dataforgood-fb-data", key, str(local))
            except Exception as e:
                print(f"  WARN: failed {qk}: {e}")
                continue
        tmp_files.append(local)
    if not tmp_files:
        print("[cebu-meta] no quadkeys downloaded")
        return

    # Mosaic + reproject to EPSG:4326
    srcs = [rasterio.open(p) for p in tmp_files]
    mosaic, transform = merge(srcs)
    src0 = srcs[0]
    src_crs = src0.crs
    dst_crs = "EPSG:4326"
    height_src, width_src = mosaic.shape[-2:]
    dst_transform, dst_w, dst_h = calculate_default_transform(
        src_crs,
        dst_crs,
        width_src,
        height_src,
        left=transform[2],
        bottom=transform[5] + transform[4] * height_src,
        right=transform[2] + transform[0] * width_src,
        top=transform[5],
    )
    dst = np.zeros((dst_h, dst_w), dtype="float32")
    reproject(
        source=mosaic[0].astype("float32"),
        destination=dst,
        src_transform=transform,
        src_crs=src_crs,
        dst_transform=dst_transform,
        dst_crs=dst_crs,
        resampling=Resampling.average,
    )
    with rasterio.open(
        out_path,
        "w",
        driver="GTiff",
        height=dst_h,
        width=dst_w,
        count=1,
        dtype="uint8",
        crs=dst_crs,
        transform=dst_transform,
        compress="deflate",
    ) as dst_f:
        dst_f.write(np.clip(dst, 0, 255).astype("uint8"), 1)
    for s in srcs:
        s.close()
    for p in tmp_files:
        p.unlink()
    print(f"[cebu-meta] wrote {out_path.name} {dst_h}x{dst_w}")


def fetch_cebu_admin() -> None:
    """OSM admin-level=8 (city) + admin-level=10 (barangays) inside Cebu bbox."""
    import osm2geojson

    out_lgu = CEBU_DIR / "cebu_lgu.geojson"
    out_brgy = CEBU_DIR / "cebu_barangays.geojson"
    if out_lgu.exists() and out_brgy.exists():
        print("[cebu-osm] both exist; skip")
        return

    bbox_str = f"{CEBU_BBOX[1]},{CEBU_BBOX[0]},{CEBU_BBOX[3]},{CEBU_BBOX[2]}"
    queries = {
        "lgu": f"""[out:json][timeout:240];
(
  relation["admin_level"="6"]["boundary"="administrative"]({bbox_str});
  relation["admin_level"="8"]["boundary"="administrative"]({bbox_str});
);
out geom;
""",
        "brgy": f"""[out:json][timeout:240];
(
  relation["admin_level"="10"]["boundary"="administrative"]({bbox_str});
);
out geom;
""",
    }
    for tag, q in queries.items():
        out = out_lgu if tag == "lgu" else out_brgy
        if out.exists():
            continue
        print(f"[cebu-osm] fetching {tag}")
        req = urllib.request.Request(
            OVERPASS, data=q.encode("utf-8"), headers={"User-Agent": "leaves.ph/1.0"}
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(req, timeout=240) as r:
                    data = json.loads(r.read().decode("utf-8"))
                break
            except Exception as e:
                print(f"  retry {attempt + 1}: {e}")
                time.sleep(15)
        else:
            print("  FAILED")
            continue
        fc = osm2geojson.json2geojson(data)
        feats = []
        for f in fc.get("features", []):
            props = f.get("properties") or {}
            tags = props.get("tags") or {}
            name = tags.get("name") or props.get("name") or ""
            if not name:
                continue
            keep = {
                "name": name,
                "admin_level": tags.get("admin_level"),
                "lgu_hint": tags.get("is_in:city") or tags.get("is_in") or "",
            }
            if tag == "lgu":
                keep["lgu_name"] = name
            else:
                keep["barangay_name"] = name
                keep["lgu_hint"] = tags.get("is_in:city", "")
            feats.append({"type": "Feature", "geometry": f["geometry"], "properties": keep})
        CEBU_DIR.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps({"type": "FeatureCollection", "features": feats}))
        print(f"  wrote {out.name} ({len(feats)} features)")


def main() -> int:
    global np
    import numpy as np_mod

    np = np_mod
    fetch_s2()
    fetch_meta_canopy()
    fetch_cebu_admin()
    print("\n[cebu] fetch complete. Next: run scan_cebu.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
