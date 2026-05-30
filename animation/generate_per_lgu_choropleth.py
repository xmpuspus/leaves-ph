"""Per-LGU canopy choropleth animation 2019 to 2026.

Reads data/lgu/ncr_lgu.geojson + data/per_lgu/per_lgu_canopy_2019_2026.csv,
renders one frame per year colored by canopy_pct, stitches into a GIF.

Output:
    docs/demo/lgu-choropleth.gif
"""

from __future__ import annotations

import csv
import io
import json
import sys
from pathlib import Path

import imageio.v2 as imageio
import matplotlib

matplotlib.use("Agg")  # headless backend; the macOS FigureCanvasMac dropped tostring_rgb
import matplotlib.pyplot as plt
import numpy as np

REPO_ROOT = Path(__file__).resolve().parent.parent
LGU_PATH = REPO_ROOT / "data" / "lgu" / "ncr_lgu.geojson"
CSV_PATH = REPO_ROOT / "data" / "per_lgu" / "per_lgu_canopy_2019_2026.csv"
OUT_DIR = REPO_ROOT / "docs" / "demo"
OUT_GIF = OUT_DIR / "lgu-choropleth.gif"

YEARS = list(range(2019, 2027))
MAX_PCT = 25.0  # color saturates above this


def load_per_lgu() -> tuple[dict[str, dict[int, float]], dict[int, float]]:
    """Returns (per_lgu_pct, ncr_area_weighted_pct_by_year)."""
    per_lgu: dict[str, dict[int, float]] = {}
    by_year_canopy_ha: dict[int, float] = {}
    by_year_total_ha: dict[int, float] = {}
    with CSV_PATH.open() as f:
        for row in csv.DictReader(f):
            lgu = row["lgu_name"]
            year = int(row["year"])
            pct = float(row["canopy_pct"])
            ha = float(row["canopy_ha"])
            tot = float(row["total_ha"])
            per_lgu.setdefault(lgu, {})[year] = pct
            by_year_canopy_ha[year] = by_year_canopy_ha.get(year, 0.0) + ha
            by_year_total_ha[year] = by_year_total_ha.get(year, 0.0) + tot
    ncr = {
        y: (100.0 * by_year_canopy_ha[y] / by_year_total_ha[y]) if by_year_total_ha[y] else 0.0
        for y in by_year_canopy_ha
    }
    return per_lgu, ncr


def load_lgus() -> list[dict]:
    fc = json.loads(LGU_PATH.read_text())
    return fc["features"]


def color_for_pct(pct: float | None, cmap) -> tuple[float, float, float, float]:
    if pct is None:
        return (0.9, 0.9, 0.9, 1.0)
    t = max(0.0, min(1.0, pct / MAX_PCT))
    return cmap(0.15 + t * 0.85)


def plot_feature(ax, feature, color):
    geom = feature["geometry"]
    if geom["type"] == "Polygon":
        polys = [geom["coordinates"]]
    elif geom["type"] == "MultiPolygon":
        polys = geom["coordinates"]
    else:
        return
    for poly in polys:
        outer = np.array(poly[0])
        ax.fill(outer[:, 0], outer[:, 1], color=color, edgecolor="#22324a", linewidth=0.4)


def render_year(features, per_lgu, ncr, year, cmap) -> np.ndarray:
    fig, ax = plt.subplots(figsize=(7.5, 9), dpi=100)
    fig.patch.set_facecolor("#fbfaf6")
    ax.set_facecolor("#fbfaf6")

    for feat in features:
        lgu = feat["properties"]["lgu_name"]
        pct = per_lgu.get(lgu, {}).get(year)
        color = color_for_pct(pct, cmap)
        plot_feature(ax, feat, color)

    # Centroids + labels for the big LGUs
    label_lgus = {
        "Quezon City",
        "Manila",
        "Caloocan",
        "Taguig",
        "Pasig",
        "Marikina",
        "Muntinlupa",
        "Las Pinas",
    }
    for feat in features:
        lgu = feat["properties"]["lgu_name"]
        if lgu not in label_lgus:
            continue
        geom = feat["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        # use largest outer ring as the label anchor
        biggest = max((np.array(p[0]) for p in polys), key=lambda r: r.shape[0])
        cx, cy = biggest.mean(axis=0)
        ax.text(
            cx,
            cy,
            lgu,
            ha="center",
            va="center",
            fontsize=7,
            color="#0b1220",
            bbox=dict(boxstyle="round,pad=0.2", fc=(1, 1, 1, 0.7), ec="none"),
        )

    ax.set_xlim(120.88, 121.18)
    ax.set_ylim(14.38, 14.82)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    for spine in ax.spines.values():
        spine.set_visible(False)

    # Year + area-weighted NCR headline
    ncr_pct = ncr.get(year, 0.0)
    ax.text(
        120.89,
        14.815,
        f"{year}",
        fontsize=42,
        weight="bold",
        color="#0b1220",
        family="monospace",
        ha="left",
        va="top",
    )
    ax.text(
        120.89,
        14.785,
        f"NCR canopy: {ncr_pct:.2f}% (area-weighted across 17 LGUs)",
        fontsize=10,
        color="#445170",
        family="monospace",
        ha="left",
        va="top",
    )
    ax.text(
        120.89,
        14.40,
        "Leaves.PH  ·  Sentinel-2 NDVI >= 0.62  ·  CC-BY-4.0",
        fontsize=7,
        color="#8e98ac",
        family="monospace",
        ha="left",
        va="bottom",
    )
    ax.text(
        121.17,
        14.40,
        "https://leaves.ph",
        fontsize=7,
        color="#8e98ac",
        family="monospace",
        ha="right",
        va="bottom",
    )

    # Color legend strip
    ax2 = fig.add_axes([0.13, 0.07, 0.4, 0.015])
    grad = np.linspace(0, 1, 256)
    grad_colors = [cmap(0.15 + 0.85 * t) for t in grad]
    ax2.imshow(np.array(grad_colors)[np.newaxis, :, :3], aspect="auto", extent=[0, MAX_PCT, 0, 1])
    ax2.set_yticks([])
    ax2.set_xticks([0, 5, 10, 15, 20, 25])
    ax2.set_xticklabels(["0%", "5", "10", "15", "20", "25%+"], fontsize=7, color="#445170")
    ax2.tick_params(axis="x", length=2, pad=2)
    for spine in ax2.spines.values():
        spine.set_visible(False)
    fig.text(0.13, 0.105, "canopy %", fontsize=7, color="#445170", family="monospace")

    buf = io.BytesIO()
    fig.savefig(buf, format="png", facecolor=fig.get_facecolor(), bbox_inches="tight", dpi=100)
    buf.seek(0)
    img = imageio.imread(buf)
    plt.close(fig)
    # Drop alpha if present
    if img.shape[-1] == 4:
        img = img[..., :3]
    return img


def main() -> int:
    if not LGU_PATH.exists():
        print(f"[choropleth] MISSING {LGU_PATH}", file=sys.stderr)
        return 1
    if not CSV_PATH.exists():
        print(f"[choropleth] MISSING {CSV_PATH}", file=sys.stderr)
        return 1
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    features = load_lgus()
    per_lgu, ncr = load_per_lgu()
    print(f"[choropleth] {len(features)} LGUs, {len(YEARS)} years")

    cmap = plt.get_cmap("YlGn")
    frames = []
    for year in YEARS:
        print(f"[choropleth] rendering {year}  (NCR={ncr.get(year, 0):.2f}%)")
        frames.append(render_year(features, per_lgu, ncr, year, cmap))
    # hold last frame
    frames.extend([frames[-1]] * 3)
    print(f"[choropleth] writing {OUT_GIF.relative_to(REPO_ROOT)} ({len(frames)} frames)")
    imageio.mimsave(str(OUT_GIF), frames, duration=0.9, loop=0)
    size_mb = OUT_GIF.stat().st_size / 1_000_000
    print(f"[choropleth] DONE  {size_mb:.1f} MB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
