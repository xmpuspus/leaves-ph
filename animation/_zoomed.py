"""Shared zoomed-bbox canopy timeline renderer.

Used by generate_la_mesa_watershed.py, generate_salex_corridor.py,
generate_quirino_avenue.py. Same NDVI-overlay-on-OSM-basemap pattern as
generate_metro_manila_timeline.py, parameterised by bbox + zoom + label.
"""

from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import imageio.v2 as imageio
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import rasterio  # noqa: E402
from rasterio.features import geometry_mask  # noqa: E402
from rasterio.transform import from_bounds  # noqa: E402

sys.path.insert(0, str(Path(__file__).parent))
from _basemap import basemap_for_bbox, desaturate  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = REPO_ROOT / "data" / "composites"
LGU_GEOJSON = REPO_ROOT / "data" / "lgu" / "ncr_lgu.geojson"
CSV_PATH = REPO_ROOT / "data" / "per_lgu" / "per_lgu_canopy_2019_2026.csv"


def load_canopy(year: int) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    path = COMP_DIR / f"canopy_{year}.tif"
    with rasterio.open(path) as src:
        return src.read(1), (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top)


def load_lgu_mask(canopy_bbox, shape: tuple[int, int]) -> np.ndarray:
    fc = json.loads(LGU_GEOJSON.read_text())
    geoms = [f["geometry"] for f in fc["features"]]
    transform = from_bounds(*canopy_bbox, shape[1], shape[0])
    return geometry_mask(geoms, out_shape=shape, transform=transform, invert=True)


def crop_canopy_to_bbox(canopy: np.ndarray, canopy_bbox, target_bbox) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    """Crop a canopy raster to target_bbox (subset of canopy_bbox).

    Returns (cropped_array, actual_cropped_bbox).
    """
    h, w = canopy.shape
    src_min_lon, src_min_lat, src_max_lon, src_max_lat = canopy_bbox
    tgt_min_lon, tgt_min_lat, tgt_max_lon, tgt_max_lat = target_bbox

    px_x = (tgt_min_lon - src_min_lon) / (src_max_lon - src_min_lon) * w
    px_x2 = (tgt_max_lon - src_min_lon) / (src_max_lon - src_min_lon) * w
    # rasterio rasters use row=0 at top (max lat), so y inverts
    px_y = (src_max_lat - tgt_max_lat) / (src_max_lat - src_min_lat) * h
    px_y2 = (src_max_lat - tgt_min_lat) / (src_max_lat - src_min_lat) * h

    x0, x1 = int(max(0, np.floor(px_x))), int(min(w, np.ceil(px_x2)))
    y0, y1 = int(max(0, np.floor(px_y))), int(min(h, np.ceil(px_y2)))
    if x1 <= x0 or y1 <= y0:
        return canopy, canopy_bbox

    cropped = canopy[y0:y1, x0:x1]
    # actual bbox from pixel coords
    actual_min_lon = src_min_lon + x0 / w * (src_max_lon - src_min_lon)
    actual_max_lon = src_min_lon + x1 / w * (src_max_lon - src_min_lon)
    actual_max_lat = src_max_lat - y0 / h * (src_max_lat - src_min_lat)
    actual_min_lat = src_max_lat - y1 / h * (src_max_lat - src_min_lat)
    return cropped, (actual_min_lon, actual_min_lat, actual_max_lon, actual_max_lat)


def canopy_pct_in_bbox(canopy: np.ndarray, canopy_bbox, lgu_mask: np.ndarray, target_bbox) -> float:
    """Canopy percent within the target_bbox crop, over LGU-masked pixels."""
    cropped, _ = crop_canopy_to_bbox(canopy, canopy_bbox, target_bbox)
    cropped_mask, _ = crop_canopy_to_bbox(lgu_mask.astype(np.uint8), canopy_bbox, target_bbox)
    cropped_mask = cropped_mask.astype(bool)
    valid = cropped_mask & (cropped != 255)
    if not valid.any():
        return 0.0
    return float((cropped == 1)[valid].sum()) / float(valid.sum()) * 100


def render_frame(
    basemap, base_bbox, canopy, canopy_bbox, lgu_mask,
    target_bbox, year: int, label: str, sub_label: str, pct: float, fig_size=(9, 8),
):
    fig, ax = plt.subplots(figsize=fig_size, dpi=110)
    fig.patch.set_facecolor("#fbfaf6")
    ax.set_facecolor("#fbfaf6")

    desat = desaturate(basemap, 0.55)
    ax.imshow(
        desat,
        extent=(base_bbox[0], base_bbox[2], base_bbox[1], base_bbox[3]),
        origin="upper", interpolation="bilinear", zorder=1,
    )

    # Apply LGU mask
    canopy = canopy.copy()
    canopy[~lgu_mask] = 255
    overlay = np.ma.masked_array((canopy == 1).astype(np.uint8), mask=(canopy != 1))
    cmap = plt.matplotlib.colors.ListedColormap(["#2d5a3d"])
    ax.imshow(
        overlay,
        extent=(canopy_bbox[0], canopy_bbox[2], canopy_bbox[1], canopy_bbox[3]),
        origin="upper", interpolation="nearest", cmap=cmap, alpha=0.82, zorder=2,
    )

    ax.set_xlim(target_bbox[0], target_bbox[2])
    ax.set_ylim(target_bbox[1], target_bbox[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Headline
    span_x = target_bbox[2] - target_bbox[0]
    span_y = target_bbox[3] - target_bbox[1]
    ax.text(target_bbox[0] + 0.02 * span_x, target_bbox[3] - 0.03 * span_y, f"{year}",
            fontsize=42, weight="bold", color="#0b1220", family="monospace",
            ha="left", va="top",
            bbox=dict(boxstyle="round,pad=0.3", fc=(1, 1, 1, 0.88), ec="none"))
    ax.text(target_bbox[0] + 0.02 * span_x, target_bbox[3] - 0.12 * span_y,
            f"{label}\n{sub_label}\nCanopy in view: {pct:.2f}%",
            fontsize=11, color="#0b1220", family="monospace", ha="left", va="top",
            bbox=dict(boxstyle="round,pad=0.3", fc=(1, 1, 1, 0.88), ec="none"))

    ax.text(target_bbox[2] - 0.02 * span_x, target_bbox[1] + 0.02 * span_y,
            "Leaves.PH  ·  S-2 NDVI >= 0.62  ·  basemap (c) OSM contributors",
            fontsize=7, color="#0b1220", family="monospace", ha="right", va="bottom",
            bbox=dict(boxstyle="round,pad=0.25", fc=(1, 1, 1, 0.85), ec="none"))
    ax.text(target_bbox[0] + 0.02 * span_x, target_bbox[1] + 0.02 * span_y,
            "https://leaves.ph",
            fontsize=7, color="#0b1220", family="monospace", ha="left", va="bottom",
            bbox=dict(boxstyle="round,pad=0.25", fc=(1, 1, 1, 0.85), ec="none"))

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
    buf.seek(0)
    img = imageio.imread(buf)
    plt.close(fig)
    if img.shape[-1] == 4:
        img = img[..., :3]
    return img


def make_timeline(out_path: Path, target_bbox, zoom: int, label: str, sub_label: str, years: list[int], fig_size=(9, 8)) -> int:
    """Generate a zoomed canopy timeline GIF for the given bbox + label."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    print(f"[zoomed] fetching OSM basemap for {target_bbox} at zoom {zoom}")
    basemap, base_bbox = basemap_for_bbox(target_bbox, zoom)
    print(f"[zoomed] basemap shape {basemap.shape}, snapped bbox {base_bbox}")

    # LGU mask uses the FULL canopy raster shape (we crop later).
    canopy0, canopy_bbox = load_canopy(years[0])
    lgu_mask_full = load_lgu_mask(canopy_bbox, canopy0.shape)

    frames = []
    for year in years:
        canopy, _ = load_canopy(year)
        pct = canopy_pct_in_bbox(canopy, canopy_bbox, lgu_mask_full, target_bbox)
        print(f"[zoomed] {year}: canopy_in_bbox {pct:.2f}%, rendering frame")
        frames.append(
            render_frame(
                basemap, base_bbox, canopy, canopy_bbox, lgu_mask_full,
                target_bbox, year, label, sub_label, pct, fig_size=fig_size,
            )
        )
    frames.extend([frames[-1]] * 4)
    print(f"[zoomed] writing {out_path} ({len(frames)} frames)")
    imageio.mimsave(str(out_path), frames, duration=0.9, loop=0)
    print(f"[zoomed] DONE  {out_path.stat().st_size / 1_000_000:.1f} MB")
    return 0
