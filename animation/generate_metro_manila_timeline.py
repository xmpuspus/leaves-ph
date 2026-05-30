"""NCR-wide canopy timeline animation 2019 to 2026.

Stitches an OSM basemap, overlays the per-year canopy raster (green where
NDVI >= 0.62), renders one frame per year, writes a GIF.

Output:
    docs/demo/hero.gif
"""

from __future__ import annotations

import io
import sys
from pathlib import Path

import imageio.v2 as imageio
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from rasterio.features import geometry_mask

sys.path.insert(0, str(Path(__file__).parent))
from _basemap import basemap_for_bbox, desaturate

REPO_ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = REPO_ROOT / "data" / "composites"
LGU_GEOJSON = REPO_ROOT / "data" / "lgu" / "ncr_lgu.geojson"
CSV_PATH = REPO_ROOT / "data" / "per_lgu" / "per_lgu_canopy_2019_2026.csv"
OUT_DIR = REPO_ROOT / "docs" / "demo"
OUT_GIF = OUT_DIR / "hero.gif"

NCR_BBOX = (120.88, 14.39, 121.16, 14.82)
YEARS = list(range(2019, 2027))
ZOOM = 11


def ncr_pct_by_year() -> dict[int, float]:
    """Area-weighted NCR canopy percent per year, from the per-LGU CSV.

    This matches BENCHMARKS.md (the canonical numbers published on the site)
    rather than the raster-pixel ratio (which would include ocean / non-LGU
    pixels and read higher).
    """
    import csv

    by_year_canopy: dict[int, float] = {}
    by_year_total: dict[int, float] = {}
    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            year = int(row["year"])
            by_year_canopy[year] = by_year_canopy.get(year, 0.0) + float(row["canopy_ha"])
            by_year_total[year] = by_year_total.get(year, 0.0) + float(row["total_ha"])
    return {y: 100.0 * by_year_canopy[y] / by_year_total[y] for y in by_year_canopy if by_year_total[y]}


def load_canopy(year: int) -> tuple[np.ndarray, tuple[float, float, float, float]]:
    path = COMP_DIR / f"canopy_{year}.tif"
    with rasterio.open(path) as src:
        a = src.read(1)
        b = src.bounds
    return a, (b.left, b.bottom, b.right, b.top)


def load_lgu_mask(canopy_bbox, shape: tuple[int, int]) -> np.ndarray:
    """Boolean mask True where the pixel is INSIDE one of the 17 NCR LGUs."""
    import json

    from rasterio.transform import from_bounds

    fc = json.loads(LGU_GEOJSON.read_text())
    geoms = [f["geometry"] for f in fc["features"]]
    transform = from_bounds(*canopy_bbox, shape[1], shape[0])
    return geometry_mask(geoms, out_shape=shape, transform=transform, invert=True)


def render(
    basemap: np.ndarray,
    base_bbox,
    canopy: np.ndarray,
    canopy_bbox,
    lgu_mask: np.ndarray,
    year: int,
    ncr_pct: float,
) -> np.ndarray:
    # Mask out pixels outside any LGU polygon (ocean, non-NCR land).
    canopy = canopy.copy()
    canopy[~lgu_mask] = 255  # treat as nodata
    fig, ax = plt.subplots(figsize=(9, 9.5), dpi=110)
    fig.patch.set_facecolor("#fbfaf6")
    ax.set_facecolor("#fbfaf6")

    desat = desaturate(basemap, 0.55)
    # matplotlib extent for imshow is (left, right, bottom, top). When the
    # data array is row-major top-to-bottom (origin="upper"), the bottom/top
    # in extent control where the rows MAP TO, not the array order.
    ax.imshow(
        desat,
        extent=(base_bbox[0], base_bbox[2], base_bbox[1], base_bbox[3]),
        origin="upper",
        interpolation="bilinear",
        zorder=1,
    )

    # Canopy overlay as masked array so transparent pixels really pass through.
    overlay = np.ma.masked_array(
        (canopy == 1).astype(np.uint8),
        mask=(canopy != 1),
    )
    cmap = plt.matplotlib.colors.ListedColormap(["#2d5a3d"])
    ax.imshow(
        overlay,
        extent=(canopy_bbox[0], canopy_bbox[2], canopy_bbox[1], canopy_bbox[3]),
        origin="upper",
        interpolation="nearest",
        cmap=cmap,
        alpha=0.82,
        zorder=2,
    )

    ax.set_xlim(NCR_BBOX[0], NCR_BBOX[2])
    ax.set_ylim(NCR_BBOX[1], NCR_BBOX[3])
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    ax.text(
        NCR_BBOX[0] + 0.005,
        NCR_BBOX[3] - 0.005,
        f"{year}",
        fontsize=44,
        weight="bold",
        color="#0b1220",
        family="monospace",
        ha="left",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", fc=(1, 1, 1, 0.85), ec="none"),
    )
    ax.text(
        NCR_BBOX[0] + 0.005,
        NCR_BBOX[3] - 0.035,
        f"NCR canopy: {ncr_pct:.2f}%",
        fontsize=14,
        color="#0b1220",
        family="monospace",
        ha="left",
        va="top",
        bbox=dict(boxstyle="round,pad=0.3", fc=(1, 1, 1, 0.85), ec="none"),
    )

    ax.text(
        NCR_BBOX[2] - 0.005,
        NCR_BBOX[1] + 0.005,
        "Leaves.PH  ·  Sentinel-2 NDVI >= 0.62  ·  basemap (c) OpenStreetMap contributors",
        fontsize=7,
        color="#0b1220",
        family="monospace",
        ha="right",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.25", fc=(1, 1, 1, 0.85), ec="none"),
    )
    ax.text(
        NCR_BBOX[0] + 0.005,
        NCR_BBOX[1] + 0.005,
        "https://leaves.ph",
        fontsize=7,
        color="#0b1220",
        family="monospace",
        ha="left",
        va="bottom",
        bbox=dict(boxstyle="round,pad=0.25", fc=(1, 1, 1, 0.85), ec="none"),
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
    buf.seek(0)
    img = imageio.imread(buf)
    plt.close(fig)
    if img.shape[-1] == 4:
        img = img[..., :3]
    return img


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print(f"[hero] fetching OSM basemap for NCR at zoom {ZOOM}")
    basemap, base_bbox = basemap_for_bbox(NCR_BBOX, ZOOM)
    print(f"[hero] basemap shape {basemap.shape}, snapped bbox {base_bbox}")

    pct_by_year = ncr_pct_by_year()
    # Load the LGU mask once (same shape for all canopy rasters).
    canopy0, canopy_bbox = load_canopy(YEARS[0])
    lgu_mask = load_lgu_mask(canopy_bbox, canopy0.shape)
    print(f"[hero] LGU mask: {lgu_mask.sum():,} pixels inside, {(~lgu_mask).sum():,} outside")
    frames = []
    for year in YEARS:
        canopy, canopy_bbox = load_canopy(year)
        pct = pct_by_year.get(year, 0.0)
        print(f"[hero] {year}: canopy {pct:.2f}% (area-weighted), rendering frame")
        frames.append(render(basemap, base_bbox, canopy, canopy_bbox, lgu_mask, year, pct))
    frames.extend([frames[-1]] * 4)
    print(f"[hero] writing {OUT_GIF.relative_to(REPO_ROOT)} ({len(frames)} frames)")
    imageio.mimsave(str(OUT_GIF), frames, duration=0.9, loop=0)
    print(f"[hero] DONE  {OUT_GIF.stat().st_size / 1_000_000:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
