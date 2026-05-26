"""Shared helpers for animation overlays.

Renders an OSM Carto-light basemap into a numpy array for an arbitrary bbox.
Downloads OSM raster tiles, stitches them, crops to the requested AOI.

Tile attribution required: "(c) OpenStreetMap contributors" included by the
caller in the figure caption.
"""

from __future__ import annotations

import math
import urllib.request
from pathlib import Path
from typing import Tuple

import numpy as np
from PIL import Image

TILE_HOST = "https://a.tile.openstreetmap.org"
CACHE = Path("/tmp/leaves-ph-tiles")
CACHE.mkdir(exist_ok=True)
USER_AGENT = "leaves-ph/0.1.0 (https://github.com/xmpuspus/leaves-ph)"


def lonlat_to_tile(lon: float, lat: float, zoom: int) -> Tuple[float, float]:
    lat_rad = math.radians(lat)
    n = 2 ** zoom
    x = (lon + 180) / 360 * n
    y = (1 - math.log(math.tan(lat_rad) + 1 / math.cos(lat_rad)) / math.pi) / 2 * n
    return x, y


def tile_to_lonlat(x: float, y: float, zoom: int) -> Tuple[float, float]:
    n = 2 ** zoom
    lon = x / n * 360 - 180
    lat_rad = math.atan(math.sinh(math.pi * (1 - 2 * y / n)))
    return lon, math.degrees(lat_rad)


def fetch_tile(z: int, x: int, y: int) -> Image.Image:
    cached = CACHE / f"{z}_{x}_{y}.png"
    if cached.exists():
        return Image.open(cached).convert("RGB")
    url = f"{TILE_HOST}/{z}/{x}/{y}.png"
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=30) as r, open(cached, "wb") as f:
        f.write(r.read())
    return Image.open(cached).convert("RGB")


def basemap_for_bbox(bbox: Tuple[float, float, float, float], zoom: int) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Returns (image, actual_bbox).

    bbox is (min_lon, min_lat, max_lon, max_lat). Output image covers at
    LEAST that bbox; actual_bbox is the snapped bbox.
    """
    min_lon, min_lat, max_lon, max_lat = bbox
    x1, y1 = lonlat_to_tile(min_lon, max_lat, zoom)
    x2, y2 = lonlat_to_tile(max_lon, min_lat, zoom)
    tx1, ty1 = int(math.floor(x1)), int(math.floor(y1))
    tx2, ty2 = int(math.ceil(x2)), int(math.ceil(y2))

    cols = tx2 - tx1
    rows = ty2 - ty1
    if cols <= 0 or rows <= 0:
        raise ValueError(f"Empty tile range for bbox={bbox} zoom={zoom}")

    canvas = Image.new("RGB", (cols * 256, rows * 256), (255, 255, 255))
    for j in range(rows):
        for i in range(cols):
            tile = fetch_tile(zoom, tx1 + i, ty1 + j)
            canvas.paste(tile, (i * 256, j * 256))

    actual_min_lon, actual_max_lat = tile_to_lonlat(tx1, ty1, zoom)
    actual_max_lon, actual_min_lat = tile_to_lonlat(tx2, ty2, zoom)
    return np.array(canvas), (actual_min_lon, actual_min_lat, actual_max_lon, actual_max_lat)


def desaturate(arr: np.ndarray, factor: float = 0.5) -> np.ndarray:
    """Push the basemap toward gray so the overlay reads more clearly."""
    gray = arr.mean(axis=-1, keepdims=True)
    return (arr * (1 - factor) + gray * factor).astype(np.uint8)
