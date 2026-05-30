"""Capabilities demo: KNOWN vs PREDICTED canopy across NCR locations + time.

One looping GIF that shows, for three under-sampled Metro Manila locations,
the same scene three ways:

    1. SENTINEL-2 RGB        real annual imagery (the model input)
    2. KNOWN (reference)     Meta 1m canopy > 5m + OSM-confirmed crowns,
                             a single fixed-epoch (~2019) reference
    3. PREDICTED (model)     the Leaves.PH detection model's annual canopy
                             estimate, calibrated to reproduce the Meta reference
                             (R2 0.83-0.86 grouped CV vs Meta, not ground truth)

The year ticks 2019 -> 2026 inside each location, then the scene cuts to the
next location. Sentinel-2 and the model prediction refresh every year; the
reference (Meta + OSM) is a single epoch and stays put. That contrast is the
point: the model gives you canopy everywhere, every year; the reference does
not.

The Sentinel-2 basemap uses ONE contrast stretch per location (pooled across
all years), so the basemap brightness stays put and only real canopy change
moves frame to frame.

All inputs are local rasters/vectors. No Earth Engine call at render time.
Frame timing (per-year pace + scene-boundary holds) is set with gifsicle in
the optimisation step; imageio does not reliably persist per-frame delays.

Output:
    docs/demo/known-vs-predicted.gif
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
from matplotlib.colors import LinearSegmentedColormap
from rasterio.windows import Window
from rasterio.windows import bounds as win_bounds
from rasterio.windows import from_bounds as win_from_bounds

REPO_ROOT = Path(__file__).resolve().parent.parent
COMP_DIR = REPO_ROOT / "data" / "composites"
SCAN_DIR = REPO_ROOT / "detection" / "scan"
META_TIF = REPO_ROOT / "data" / "meta" / "canopy_height_ncr.tif"
CROWN_GEOJSON = REPO_ROOT / "data" / "per_crown" / "tree_crowns_ncr_tagged.geojson"
CROWN_CACHE = Path("/tmp/crown_centroids.npz")
OUT_DIR = REPO_ROOT / "docs" / "demo"
OUT_GIF = OUT_DIR / "known-vs-predicted.gif"

YEARS = list(range(2019, 2027))

# Three locations other canopy products under-sample. bbox = (min_lon, min_lat,
# max_lon, max_lat). Two are dense-urban / reclaimed (model >> known); one is a
# real green fringe (model ~= known, which shows the model is accurate where
# canopy genuinely exists, not just optimistic everywhere).
AOIS = [
    {
        "name": "Tondo, Manila",
        "sub": "Dense informal coastal settlement",
        "bbox": (120.955, 14.600, 120.985, 14.625),
    },
    {
        "name": "Pasay  Manila-Bay reclamation",
        "sub": "Reclaimed coastal land, mostly post-2019",
        "bbox": (120.975, 14.525, 121.005, 14.550),
    },
    {
        "name": "La Mesa watershed edge",
        "sub": "Quezon City peri-urban green fringe",
        "bbox": (121.060, 14.720, 121.100, 14.760),
    },
]

# Model density heatmap: transparent at 0 -> saturated green at high canopy.
MODEL_CMAP = LinearSegmentedColormap.from_list(
    "model_density",
    [
        (0.20, 0.55, 0.30, 0.00),  # 0.0  fully transparent
        (0.20, 0.60, 0.32, 0.55),  # low
        (0.13, 0.52, 0.26, 0.80),  # mid
        (0.05, 0.34, 0.16, 0.95),  # high
    ],
    N=256,
)
META_FILL = (0.71, 0.58, 0.16, 0.78)  # olive-gold for the known reference
CONFIRMED_DOT = "#13c4d8"  # OSM-confirmed crowns (cyan)
NEW_DOT = "#ff8a3d"  # Meta-derived tall-canopy crowns absent from OSM (orange)

INK = "#0b1220"
GREEN = "#1f3d2b"
MUTE = "#5a5446"
PAPER = "#fbfaf6"

FIG_W, FIG_H = 13.2, 7.0
PANEL_TOP, PANEL_BOTTOM = 0.775, 0.150


def load_crown_centroids() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """(lon, lat, status) centroid arrays for all tagged crowns.

    Reads the compact npz cache if present (built once from the 139 MB
    geojson); otherwise builds it from the geojson and caches it.
    """
    if CROWN_CACHE.exists():
        z = np.load(CROWN_CACHE, allow_pickle=True)
        return z["lon"], z["lat"], z["status"]
    import json

    fc = json.loads(CROWN_GEOJSON.read_text())
    feats = fc["features"]
    lon = np.empty(len(feats))
    lat = np.empty(len(feats))
    status = np.empty(len(feats), dtype="U10")
    for i, f in enumerate(feats):
        ring = np.asarray(f["geometry"]["coordinates"][0])
        lon[i] = ring[:, 0].mean()
        lat[i] = ring[:, 1].mean()
        status[i] = f["properties"].get("status") or "none"
    np.savez(CROWN_CACHE, lon=lon, lat=lat, status=status)
    return lon, lat, status


def crop_shared_grid(path: Path, bbox, bands=(1,)) -> tuple[np.ndarray, tuple]:
    """Window-read a band (or bands) of a raster on the shared NCR grid.

    Returns (array, actual_bbox). For a single band, array is (H, W); for
    multiple bands, array is (H, W, n).
    """
    with rasterio.open(path) as src:
        win = win_from_bounds(*bbox, src.transform)
        win = win.round_offsets().round_lengths()
        data = src.read(list(bands), window=win)
        actual = win_bounds(win, src.transform)
    arr = data[0] if len(bands) == 1 else np.transpose(data, (1, 2, 0))
    return arr, actual


def read_meta_window(bbox, max_px: int = 700) -> tuple[np.ndarray, tuple]:
    """Decimated window read of the Meta 1m canopy-height raster for bbox.

    Returns (height_array_uint8, actual_bbox). 255 is nodata.
    """
    with rasterio.open(META_TIF) as src:
        win = win_from_bounds(*bbox, src.transform)
        win = Window(
            int(win.col_off),
            int(win.row_off),
            max(1, int(win.width)),
            max(1, int(win.height)),
        )
        scale = max(1, int(max(win.width, win.height) / max_px))
        out_h = max(1, int(win.height // scale))
        out_w = max(1, int(win.width // scale))
        data = src.read(
            1,
            window=win,
            out_shape=(out_h, out_w),
            resampling=rasterio.enums.Resampling.nearest,
        )
        actual = win_bounds(win, src.transform)
    return data, actual


def fixed_stretch_for_aoi(rgb_by_year: dict[int, np.ndarray]) -> tuple[np.ndarray, np.ndarray]:
    """Pool every year's pixels per band and return (p2[3], p98[3]).

    A single stretch shared across years keeps the basemap brightness stable so
    only real canopy change moves frame to frame (no exposure flicker).
    """
    p2 = np.zeros(3)
    p98 = np.zeros(3)
    for b in range(3):
        pooled = np.concatenate([rgb[..., b].ravel() for rgb in rgb_by_year.values()])
        pooled = pooled[pooled > 0]
        if pooled.size:
            p2[b], p98[b] = np.percentile(pooled, (2, 98))
        else:
            p2[b], p98[b] = 0.0, 1.0
    return p2, p98


def apply_stretch(rgb: np.ndarray, p2: np.ndarray, p98: np.ndarray) -> np.ndarray:
    out = np.zeros(rgb.shape, dtype=np.uint8)
    for b in range(3):
        band = rgb[..., b].astype(np.float32)
        out[..., b] = np.clip((band - p2[b]) / max(p98[b] - p2[b], 1e-6) * 255, 0, 255)
    return out


def desaturate(rgb: np.ndarray, factor: float = 0.72) -> np.ndarray:
    gray = rgb.mean(axis=-1, keepdims=True)
    return (rgb * (1 - factor) + gray * factor).astype(np.uint8)


def _panel_base(ax, bbox):
    ax.set_xlim(bbox[0], bbox[2])
    ax.set_ylim(bbox[1], bbox[3])
    ax.set_xticks([])
    ax.set_yticks([])
    ax.set_aspect("equal")
    for spine in ax.spines.values():
        spine.set_edgecolor("#cdc7b8")
        spine.set_linewidth(1.0)


def _panel_caption(fig, ax, num, title, sub):
    """Caption placed in the dedicated band ABOVE the panels (fig coords)."""
    pos = ax.get_position()
    cx = (pos.x0 + pos.x1) / 2
    fig.text(
        cx,
        0.838,
        f"{num}  {title}",
        ha="center",
        va="bottom",
        fontsize=12.5,
        weight="bold",
        color=INK,
        family="monospace",
    )
    fig.text(cx, 0.812, sub, ha="center", va="bottom", fontsize=8.2, color=MUTE, family="monospace")


def render_frame(aoi, year, rgb_stretch, rgb_bbox, density, dens_bbox, meta, meta_bbox, crowns) -> np.ndarray:
    bbox = aoi["bbox"]
    conf_lon, conf_lat, new_lon, new_lat, n_conf, n_new = crowns

    meta_valid = meta != 255
    meta_pct = float(((meta > 5) & meta_valid).sum()) / max(meta_valid.sum(), 1) * 100
    pred_pct = float(density.mean()) * 100

    fig = plt.figure(figsize=(FIG_W, FIG_H), dpi=110)
    fig.patch.set_facecolor(PAPER)
    gs = fig.add_gridspec(
        1,
        3,
        left=0.012,
        right=0.988,
        top=PANEL_TOP,
        bottom=PANEL_BOTTOM,
        wspace=0.045,
    )
    ax1, ax2, ax3 = (fig.add_subplot(gs[0, i]) for i in range(3))

    # Panel 1 - Sentinel-2 RGB input
    ax1.imshow(
        rgb_stretch,
        extent=(rgb_bbox[0], rgb_bbox[2], rgb_bbox[1], rgb_bbox[3]),
        origin="upper",
        interpolation="bilinear",
        zorder=1,
    )
    _panel_base(ax1, bbox)

    # Panel 2 - KNOWN reference (Meta > 5m + OSM-confirmed crowns)
    ax2.imshow(
        desaturate(rgb_stretch),
        extent=(rgb_bbox[0], rgb_bbox[2], rgb_bbox[1], rgb_bbox[3]),
        origin="upper",
        interpolation="bilinear",
        zorder=1,
    )
    meta_mask = np.ma.masked_array((meta > 5).astype(np.uint8), mask=~(meta > 5))
    ax2.imshow(
        meta_mask,
        extent=(meta_bbox[0], meta_bbox[2], meta_bbox[1], meta_bbox[3]),
        origin="upper",
        interpolation="nearest",
        cmap=matplotlib.colors.ListedColormap([META_FILL]),
        zorder=2,
    )
    if n_conf:
        ax2.scatter(conf_lon, conf_lat, s=9, c=CONFIRMED_DOT, edgecolors="none", alpha=0.95, zorder=3)
    _panel_base(ax2, bbox)

    # Panel 3 - PREDICTED model density (+ Meta-derived crowns absent from OSM)
    ax3.imshow(
        desaturate(rgb_stretch),
        extent=(rgb_bbox[0], rgb_bbox[2], rgb_bbox[1], rgb_bbox[3]),
        origin="upper",
        interpolation="bilinear",
        zorder=1,
    )
    ax3.imshow(
        density,
        extent=(dens_bbox[0], dens_bbox[2], dens_bbox[1], dens_bbox[3]),
        origin="upper",
        interpolation="bilinear",
        cmap=MODEL_CMAP,
        vmin=0.0,
        vmax=0.6,
        zorder=2,
    )
    if n_new:
        ax3.scatter(new_lon, new_lat, s=5, c=NEW_DOT, edgecolors="none", alpha=0.85, zorder=3)
    _panel_base(ax3, bbox)

    # Panel captions (own band, no collision with the title row)
    _panel_caption(fig, ax1, "1", "SENTINEL-2 RGB", "real annual imagery / model input")
    _panel_caption(fig, ax2, "2", "KNOWN  reference", "Meta 1m >5m + OSM crowns / single epoch")
    _panel_caption(fig, ax3, "3", "PREDICTED  model", "annual estimate / calibrated to reproduce Meta")

    # ---- Title row (full-width band at the very top) ----
    # Left: brand + demo name.
    fig.text(
        0.012,
        0.965,
        "LEAVES.PH",
        fontsize=17,
        weight="bold",
        color=GREEN,
        family="serif",
        ha="left",
        va="top",
    )
    fig.text(
        0.012,
        0.918,
        "KNOWN vs PREDICTED CANOPY",
        fontsize=10.5,
        color=GREEN,
        family="serif",
        ha="left",
        va="top",
    )
    # Center: the animating element (big year) + model credential.
    fig.text(
        0.50,
        0.972,
        f"{year}",
        fontsize=27,
        weight="bold",
        color=INK,
        family="monospace",
        ha="center",
        va="top",
    )
    fig.text(
        0.50,
        0.912,
        "detection model in optimization  -  held-out R2 0.87 vs Meta 1m",
        fontsize=8,
        color=MUTE,
        family="monospace",
        ha="center",
        va="top",
    )
    # Right: location.
    fig.text(
        0.988,
        0.965,
        f"{aoi['name']}",
        fontsize=14,
        weight="bold",
        color=INK,
        family="monospace",
        ha="right",
        va="top",
    )
    fig.text(
        0.988, 0.918, f"{aoi['sub']}", fontsize=8.5, color=MUTE, family="monospace", ha="right", va="top"
    )

    # ---- Footer: the delta story ----
    fig.patches.append(
        plt.Rectangle(
            (0.012, 0.040),
            0.976,
            0.078,
            transform=fig.transFigure,
            facecolor="#f1ede1",
            edgecolor="#d8d2c2",
            linewidth=1.0,
            zorder=0,
        )
    )
    fig.text(
        0.024,
        0.092,
        f"MODEL canopy in view  {pred_pct:4.1f}%",
        fontsize=12.5,
        weight="bold",
        color="#13402a",
        family="monospace",
        ha="left",
        va="center",
    )
    fig.text(
        0.024,
        0.060,
        f"reference (Meta >5m)  {meta_pct:4.1f}%",
        fontsize=10.5,
        color="#7a6a2a",
        family="monospace",
        ha="left",
        va="center",
    )
    fig.text(
        0.40,
        0.092,
        f"OSM-confirmed crowns   {n_conf:,}",
        fontsize=11,
        color="#0e7d8c",
        family="monospace",
        ha="left",
        va="center",
    )
    fig.text(
        0.40,
        0.060,
        f"tall canopy, no OSM tag  {n_new:,}",
        fontsize=11,
        color="#c25a1c",
        family="monospace",
        ha="left",
        va="center",
    )
    fig.text(
        0.988,
        0.092,
        "Same place, three views.",
        fontsize=10.5,
        style="italic",
        color=INK,
        family="serif",
        ha="right",
        va="center",
    )
    fig.text(
        0.988,
        0.061,
        "Crowns are Meta-derived; OSM records only a fraction.",
        fontsize=9,
        color=MUTE,
        family="serif",
        ha="right",
        va="center",
    )
    fig.text(
        0.012,
        0.014,
        "Estimates from public satellite data (Sentinel-2, Meta v2, OSM). "
        "CLIP detection model, in optimization; published canopy % uses the human-calibrated model.",
        fontsize=6.6,
        color="#8a8270",
        family="monospace",
        ha="left",
        va="bottom",
    )
    fig.text(
        0.988,
        0.014,
        "https://leaves.ph",
        fontsize=7,
        color="#8a8270",
        family="monospace",
        ha="right",
        va="bottom",
    )

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), dpi=100)
    buf.seek(0)
    img = imageio.imread(buf)
    plt.close(fig)
    if img.shape[-1] == 4:
        img = img[..., :3]
    return img


def crowns_in_bbox(lon, lat, status, bbox):
    inb = (lon >= bbox[0]) & (lon <= bbox[2]) & (lat >= bbox[1]) & (lat <= bbox[3])
    conf = inb & (status == "confirmed")
    new = inb & (status == "new")
    return (lon[conf], lat[conf], lon[new], lat[new], int(conf.sum()), int(new.sum()))


def main() -> int:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    print("[kvp] loading crown centroids")
    clon, clat, cstat = load_crown_centroids()

    frames: list[np.ndarray] = []
    for aoi in AOIS:
        bbox = aoi["bbox"]
        print(f"[kvp] scene: {aoi['name']}  bbox={bbox}")
        meta, meta_bbox = read_meta_window(bbox)
        crowns = crowns_in_bbox(clon, clat, cstat, bbox)

        # Load every year's RGB once, derive ONE shared stretch for the AOI.
        rgb_by_year: dict[int, np.ndarray] = {}
        rgb_bbox = None
        for year in YEARS:
            rgb, rgb_bbox = crop_shared_grid(COMP_DIR / f"s2_rgb_{year}.tif", bbox, bands=(1, 2, 3))
            rgb_by_year[year] = rgb
        p2, p98 = fixed_stretch_for_aoi(rgb_by_year)

        for year in YEARS:
            rgb_s = apply_stretch(rgb_by_year[year], p2, p98)
            density, dens_bbox = crop_shared_grid(SCAN_DIR / f"clf_v9_density_{year}.tif", bbox)
            print(f"[kvp]   {year}: model {density.mean() * 100:4.1f}%  rgb {rgb_s.shape[:2]}")
            frames.append(
                render_frame(
                    aoi,
                    year,
                    rgb_s,
                    rgb_bbox,
                    density,
                    dens_bbox,
                    meta,
                    meta_bbox,
                    crowns,
                )
            )

    print(f"[kvp] writing {OUT_GIF.relative_to(REPO_ROOT)}  ({len(frames)} frames)")
    imageio.mimsave(str(OUT_GIF), frames, loop=0)
    print(f"[kvp] DONE (pre-timing/opt)  {OUT_GIF.stat().st_size / 1_000_000:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
