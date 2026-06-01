#!/usr/bin/env python3
"""Post-scan finalisation: read clf_v6_ncr_series.csv, update BENCHMARKS.md
with the multi-year v6 canopy series, sanity-check the numbers, re-verify.

Run after `make scan-v6` (or detection/scan/multi_year_scan.py) completes.
"""

from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SERIES_CSV = ROOT / "detection" / "scan" / "clf_v6_ncr_series.csv"
LGU_SERIES = ROOT / "detection" / "scan" / "clf_v6_per_lgu_series.csv"
BENCHMARKS = ROOT / "BENCHMARKS.md"


def read_series() -> list[dict]:
    if not SERIES_CSV.exists():
        print(f"[finalize] missing {SERIES_CSV}", file=sys.stderr)
        return []
    with SERIES_CSV.open() as fh:
        return list(csv.DictReader(fh))


def render_series_section(rows: list[dict]) -> str:
    out = ["## v6 multi-year NCR canopy series\n"]
    out.append(
        "Per-year v6 continuous-density estimates across 2019-2026, "
        "from the Ridge regressor applied to fresh Sentinel-2 RGB embeddings "
        "for each annual epoch.\n"
    )
    out.append("| Year | v6 NCR canopy % | v6 canopy hectares | Total NCR ha |")
    out.append("|---|---|---|---|")
    for r in rows:
        out.append(
            f"| {r['year']} | {float(r['ncr_canopy_pct_v6']):.2f}% | "
            f"{float(r['ncr_canopy_ha_v6']):,.0f} | "
            f"{float(r['ncr_total_ha']):,.0f} |"
        )
    pcts = [float(r["ncr_canopy_pct_v6"]) for r in rows]
    if len(pcts) >= 2:
        delta = pcts[-1] - pcts[0]
        out.append(
            f"\n{rows[0]['year']} -> {rows[-1]['year']} v6 series delta: "
            f"{'+' if delta >= 0 else ''}{delta:.2f} pp."
        )
    return "\n".join(out) + "\n"


def main() -> int:
    rows = read_series()
    if not rows:
        return 1
    block = render_series_section(rows)
    txt = BENCHMARKS.read_text()
    placeholder = re.compile(
        r"Multi-year v6 NCR canopy series \(across all 8 epochs\)[^\n]*",
    )
    if placeholder.search(txt):
        txt = placeholder.sub(f"Multi-year v6 NCR canopy series landed.\n\n{block}", txt)
    else:
        txt += "\n" + block
    BENCHMARKS.write_text(txt)
    print(f"[finalize] BENCHMARKS.md updated with {len(rows)}-year v6 series")
    for r in rows:
        print(
            f"  {r['year']}  {float(r['ncr_canopy_pct_v6']):>6.2f}%   {float(r['ncr_canopy_ha_v6']):,.0f} ha"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
