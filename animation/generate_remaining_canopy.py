"""ScienceKonek-style "Remaining Tree Cover" time-animated GIF.

For each year 2019..2026:
1. Per-pixel canopy density at 30 m, derived from Hansen v1.13:
     density(year) = canopy2000(pixel) if lossyear == 0 OR lossyear > (year - 2000)
                     else 0
   (i.e. start with year-2000 canopy and subtract pixels Hansen recorded as
    lost on or before the year of interest.)
2. Render the density layer as an olive-green gradient (0 to 100 percent)
3. Place over an editorial beige basemap with LGU outlines
4. Stamp a magazine-style title, the year, and source attribution
5. Stitch yearly frames into a GIF

Output:
    docs/demo/remaining-canopy-timeline.gif

If S2 RGB composites (data/composites/s2_rgb_<year>.tif) exist, a second
GIF with the real Sentinel-2 satellite basemap is also generated:
    docs/demo/remaining-canopy-satellite.gif
"""

from __future__ import annotations

import io
import json
import subprocess
import sys
from pathlib import Path

import imageio.v2 as imageio
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import rasterio
from matplotlib.colors import LinearSegmentedColormap
from rasterio.features import geometry_mask
from rasterio.transform import from_bounds
from rasterio.warp import Resampling, reproject

REPO_ROOT = Path(__file__).resolve().parent.parent
HANSEN_DIR = REPO_ROOT / "data" / "hansen"
COMP_DIR = REPO_ROOT / "data" / "composites"
LGU_GEOJSON = REPO_ROOT / "data" / "lgu" / "ncr_lgu.geojson"
OUT_DIR = REPO_ROOT / "docs" / "demo"
OUT_GIF = OUT_DIR / "remaining-canopy-timeline.gif"
OUT_GIF_SAT = OUT_DIR / "remaining-canopy-satellite.gif"

YEARS = list(range(2019, 2027))
NCR_BBOX = (120.9, 14.4, 121.15, 14.8)

# ScienceKonek olive-green gradient (transparent at 0, dark olive at 100)
SK_CMAP = LinearSegmentedColormap.from_list(
    "tree_density",
    [
        (1.0, 1.0, 1.0, 0.0),  # 0%  - fully transparent
        (0.85, 0.86, 0.55, 0.6),  # 25% - light olive
        (0.62, 0.66, 0.30, 0.85),  # 50% - mid olive
        (0.36, 0.44, 0.14, 0.92),  # 75% - dark olive
        (0.18, 0.27, 0.10, 0.96),  # 100% - very dark olive
    ],
    N=256,
)


def load_hansen() -> tuple[np.ndarray, np.ndarray, dict]:
    """Returns (canopy2000_uint8_pct, lossyear_uint8_code, src_meta)."""
    with rasterio.open(HANSEN_DIR / "hansen_canopy2000.tif") as src:
        tc = src.read(1)
        meta = {
            "transform": src.transform,
            "crs": src.crs,
            "width": src.width,
            "height": src.height,
            "bounds": (src.bounds.left, src.bounds.bottom, src.bounds.right, src.bounds.top),
        }
    with rasterio.open(HANSEN_DIR / "lossyear.tif") as src:
        ly = src.read(1)
    return tc, ly, meta


def density_for_year(tc: np.ndarray, ly: np.ndarray, year: int) -> np.ndarray:
    """Per-pixel canopy density (0..100) for the given year.

    Combines two signals:
    1. **Spatial gradient**: a 3x3 mean filter on our calibrated NDVI canopy
       mask for the year, scaled to 0..100. This produces a density-percent
       per 90 m neighborhood (visually similar to the Hansen year-2000 canopy band but
       refreshed every year, so the time-animation shows real flux).
    2. **Hansen subtraction**: any pixel Hansen records as lost on or before
       the year is forced to 0 (matches the ScienceKonek source data).

    The result reads "trees are going away" through time because our NDVI
    mask is per-year (Hansen alone at 30m barely changes in NCR over 8 years).
    """
    threshold_code = year - 2000
    canopy_path = COMP_DIR / f"canopy_{year}.tif"
    if canopy_path.exists():
        with rasterio.open(canopy_path) as src:
            our = src.read(1)
        # Resample our canopy mask onto the Hansen grid if shapes differ.
        if our.shape != tc.shape:
            from rasterio.transform import from_bounds as _fb
            from rasterio.warp import Resampling as _R
            from rasterio.warp import reproject as _rep

            with rasterio.open(canopy_path) as src:
                src_t = src.transform
                src_crs = src.crs
            dst = np.zeros(tc.shape, dtype=np.uint8)
            _rep(
                source=our,
                destination=dst,
                src_transform=src_t,
                src_crs=src_crs,
                dst_transform=_fb(
                    120.9,
                    14.399897556473057,
                    121.15022770141589,
                    14.800097015548303,
                    tc.shape[1],
                    tc.shape[0],
                ),
                dst_crs="EPSG:4326",
                resampling=_R.nearest,
            )
            our = dst
        # 3x3 mean filter -> density 0..100
        from scipy.ndimage import uniform_filter

        mask01 = (our == 1).astype(np.float32)
        density = uniform_filter(mask01, size=3, mode="constant", cval=0) * 100
    else:
        # Fallback: pure Hansen-derived if NDVI canopy missing
        density = tc.astype(np.float32)

    # Hansen-loss subtraction
    lost = (ly > 0) & (ly <= threshold_code)
    density[lost] = 0
    return density


def load_lgu_mask(canopy_bbox, shape) -> np.ndarray:
    fc = json.loads(LGU_GEOJSON.read_text())
    geoms = [f["geometry"] for f in fc["features"]]
    transform = from_bounds(*canopy_bbox, shape[1], shape[0])
    return geometry_mask(geoms, out_shape=shape, transform=transform, invert=True)


def lgu_outlines_xy(canopy_bbox, shape) -> list[tuple[np.ndarray, np.ndarray]]:
    """Per-LGU outer-ring (x, y) arrays for plotting outlines."""
    fc = json.loads(LGU_GEOJSON.read_text())
    out = []
    for f in fc["features"]:
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        for poly in polys:
            outer = np.array(poly[0])
            out.append((outer[:, 0], outer[:, 1]))
    return out


def render_frame(
    density: np.ndarray,
    lgu_mask: np.ndarray,
    lgu_outlines: list[tuple[np.ndarray, np.ndarray]],
    bounds,
    year: int,
    pct: float,
    title: str = "REMAINING TREE COVER",
    subtitle: str = "OF METRO MANILA",
    satellite_rgb: np.ndarray | None = None,
) -> np.ndarray:
    fig, ax = plt.subplots(figsize=(10, 11), dpi=110)
    fig.patch.set_facecolor("#f7f3e9")
    ax.set_facecolor("#f7f3e9")

    if satellite_rgb is not None:
        # Sentinel-2 RGB basemap: scale to uint8 with p2-p98 stretch per band
        rgb = satellite_rgb.astype(np.float32)
        for b in range(3):
            band = rgb[..., b]
            p2, p98 = np.percentile(band[band > 0], (2, 98)) if (band > 0).any() else (0, 1)
            rgb[..., b] = np.clip((band - p2) / max(p98 - p2, 1) * 255, 0, 255)
        ax.imshow(
            rgb.astype(np.uint8),
            extent=(bounds[0], bounds[2], bounds[1], bounds[3]),
            origin="upper",
            zorder=1,
        )
    else:
        # Editorial pale paper inside the LGU polygons (ScienceKonek style)
        paper = np.zeros((density.shape[0], density.shape[1], 4), dtype=np.float32)
        paper[lgu_mask] = (0.91, 0.88, 0.78, 1.0)  # paper-tint
        paper[~lgu_mask] = (0.97, 0.95, 0.91, 0.0)  # transparent outside
        ax.imshow(
            paper,
            extent=(bounds[0], bounds[2], bounds[1], bounds[3]),
            origin="upper",
            interpolation="nearest",
            zorder=1,
        )

    # Tree-cover density overlay
    masked_density = np.where(lgu_mask, density, np.nan)
    ax.imshow(
        masked_density,
        extent=(bounds[0], bounds[2], bounds[1], bounds[3]),
        origin="upper",
        cmap=SK_CMAP,
        vmin=0,
        vmax=100,
        zorder=2,
        interpolation="nearest",
    )

    # LGU outlines
    for xs, ys in lgu_outlines:
        ax.plot(xs, ys, color="#3a3a3a", linewidth=0.5, alpha=0.7, zorder=3)

    # Frame coordinate system: satellite/density rasters occupy lat 14.4-14.8.
    # Title block sits ABOVE that strip (lat 14.83-14.96), legend + attribution
    # BELOW it (lat 14.30-14.39). Map area is never written over.
    ax.set_xlim(120.86, 121.18)
    ax.set_ylim(14.30, 14.96)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    TXT_Z = 15

    # ---- Editorial title block (ABOVE the map strip) ----
    ax.text(
        120.87,
        14.945,
        title,
        fontsize=26,
        weight="bold",
        color="#1f3d2b",
        family="serif",
        ha="left",
        va="top",
        zorder=TXT_Z,
    )
    ax.text(
        120.87,
        14.905,
        subtitle,
        fontsize=14,
        color="#1f3d2b",
        family="serif",
        ha="left",
        va="top",
        zorder=TXT_Z,
    )
    ax.text(
        120.87,
        14.875,
        f"YEAR  {year}",
        fontsize=12,
        color="#5a4f3a",
        family="monospace",
        ha="left",
        va="top",
        zorder=TXT_Z,
    )
    ax.text(
        121.17,
        14.945,
        "NCR  CANOPY",
        fontsize=9,
        color="#5a4f3a",
        family="monospace",
        ha="right",
        va="top",
        zorder=TXT_Z,
    )
    ax.text(
        121.17,
        14.915,
        f"{pct:.2f}%",
        fontsize=22,
        color="#1f3d2b",
        family="serif",
        weight="bold",
        ha="right",
        va="top",
        zorder=TXT_Z,
    )
    ax.text(
        121.17,
        14.875,
        "Hansen v1.13 + Sentinel-2 NDVI",
        fontsize=7,
        color="#5a4f3a",
        family="monospace",
        ha="right",
        va="top",
        zorder=TXT_Z,
    )

    # ---- Color legend (BELOW the map strip) ----
    legend_x0, legend_y0 = 120.87, 14.355
    legend_w, legend_h = 0.10, 0.010
    ax.text(
        legend_x0,
        legend_y0 + legend_h + 0.012,
        "TREE COVER  %",
        fontsize=8,
        color="#1a1a1a",
        family="monospace",
        ha="left",
        va="bottom",
        weight="bold",
        zorder=TXT_Z,
    )
    grad = np.linspace(0, 100, 256).reshape(1, -1)
    ax.imshow(
        grad,
        extent=(legend_x0, legend_x0 + legend_w, legend_y0, legend_y0 + legend_h),
        cmap=SK_CMAP,
        vmin=0,
        vmax=100,
        aspect="auto",
        zorder=TXT_Z - 1,
    )
    for v, label in [(0, "0"), (50, "50"), (100, "100")]:
        ax.text(
            legend_x0 + (v / 100) * legend_w,
            legend_y0 - 0.006,
            label,
            fontsize=7,
            color="#5a4f3a",
            family="monospace",
            ha="center",
            va="top",
            zorder=TXT_Z,
        )

    # ---- Attribution (very bottom) ----
    ax.text(
        121.17,
        14.315,
        "LEAVES.PH",
        fontsize=8,
        color="#1a1a1a",
        family="monospace",
        ha="right",
        va="bottom",
        weight="bold",
        zorder=TXT_Z,
    )
    ax.text(
        120.87,
        14.315,
        "BASEMAP: Sentinel-2 RGB (ESA Copernicus).  DATA: Hansen GFC v1.13, Meta v2 calibration, PSA boundaries.",
        fontsize=6.5,
        color="#5a4f3a",
        family="monospace",
        ha="left",
        va="bottom",
        zorder=TXT_Z,
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
    buf.seek(0)
    img = imageio.imread(buf)
    plt.close(fig)
    if img.shape[-1] == 4:
        img = img[..., :3]
    return img


def ncr_pct_from_density(density: np.ndarray, lgu_mask: np.ndarray) -> float:
    valid = lgu_mask & (density >= 0) & (density <= 100)
    if not valid.any():
        return 0.0
    # Weighted-average density (treat 0-100 as percent canopy in pixel)
    return float(density[valid].mean())


def reproject_rgb_to_hansen_grid(year: int, hansen_meta: dict) -> np.ndarray | None:
    """Reproject S2 RGB for `year` onto the Hansen grid (so it overlays correctly)."""
    src_path = COMP_DIR / f"s2_rgb_{year}.tif"
    if not src_path.exists():
        return None
    with rasterio.open(src_path) as src:
        rgb = src.read([1, 2, 3])  # 3 x H x W
        src_transform = src.transform
        src_crs = src.crs
    dst = np.zeros((3, hansen_meta["height"], hansen_meta["width"]), dtype=np.float32)
    for b in range(3):
        reproject(
            source=rgb[b],
            destination=dst[b],
            src_transform=src_transform,
            src_crs=src_crs,
            dst_transform=hansen_meta["transform"],
            dst_crs=hansen_meta["crs"],
            resampling=Resampling.bilinear,
        )
    # Reorder to H x W x 3
    return np.transpose(dst, (1, 2, 0))


def _retime_gif(path: Path, year_cs: int = 100, end_cs: int = 250) -> None:
    """Set per-frame GIF delays with gifsicle (imageio does not persist them).

    Year frames hold for `year_cs` centiseconds, the final frame for `end_cs`
    so the loop has a clear pause. No-op if gifsicle is unavailable.
    """
    with imageio.get_reader(str(path)) as r:
        n = r.get_length()
    if n is None or n < 2:
        return
    try:
        subprocess.run(
            [
                "gifsicle",
                "-O3",
                str(path),
                f"-d{year_cs}",
                f"#0-{n - 2}",
                f"-d{end_cs}",
                f"#{n - 1}",
                "-o",
                str(path),
            ],
            check=True,
            capture_output=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"[remaining] gifsicle retime skipped ({e}); frames keep default delay")


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[remaining] loading Hansen year-2000 canopy + lossyear")
    tc, ly, meta = load_hansen()
    bounds = meta["bounds"]
    print(f"[remaining] hansen grid {meta['width']}x{meta['height']}  bounds={bounds}")

    lgu_mask = load_lgu_mask(bounds, tc.shape)
    print(f"[remaining] LGU mask: {lgu_mask.sum():,} pixels inside")
    outlines = lgu_outlines_xy(bounds, tc.shape)

    # ---- Variant A: editorial paper basemap ----
    print("[remaining] rendering EDITORIAL paper variant")
    frames = []
    for year in YEARS:
        density = density_for_year(tc, ly, year)
        pct = ncr_pct_from_density(density, lgu_mask)
        print(f"  {year}: NCR mean density {pct:.2f}%")
        frames.append(render_frame(density, lgu_mask, outlines, bounds, year, pct))
    imageio.mimsave(str(OUT_GIF), frames, loop=0)
    _retime_gif(OUT_GIF)  # imageio loses per-frame delays; gifsicle sets them reliably
    print(f"[remaining] wrote {OUT_GIF.name}  ({OUT_GIF.stat().st_size / 1_000_000:.1f} MB)")

    # ---- Variant B: Sentinel-2 satellite basemap (if RGB composites exist) ----
    rgb_2026 = COMP_DIR / "s2_rgb_2026.tif"
    if rgb_2026.exists():
        print("[remaining] rendering SATELLITE basemap variant")
        sat_frames = []
        for year in YEARS:
            density = density_for_year(tc, ly, year)
            pct = ncr_pct_from_density(density, lgu_mask)
            rgb = reproject_rgb_to_hansen_grid(year, meta)
            if rgb is None:
                print(f"  {year}: missing s2_rgb; skipping satellite variant")
                return 0
            sat_frames.append(render_frame(density, lgu_mask, outlines, bounds, year, pct, satellite_rgb=rgb))
        imageio.mimsave(str(OUT_GIF_SAT), sat_frames, loop=0)
        _retime_gif(OUT_GIF_SAT)
        print(f"[remaining] wrote {OUT_GIF_SAT.name}  ({OUT_GIF_SAT.stat().st_size / 1_000_000:.1f} MB)")
    else:
        print("[remaining] s2_rgb composites not present; skipping satellite variant")
        print("[remaining]   run `python3 pipeline/fetch_sentinel2_rgb.py` to enable it")
    return 0


if __name__ == "__main__":
    sys.exit(main())
