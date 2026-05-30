#!/usr/bin/env python3
"""Leaves.PH release-readiness gate.

Ports solar-map-ph/scripts/verify_v11_release.py to this repo. Must return
N PASS / 0 FAIL before any tag, push, or deploy.
"""

from __future__ import annotations

import csv
import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

BANNED_AI_WORDS = re.compile(
    r"\b("
    r"delve|tapestry|in the realm of|paradigm shift|game-changer|cutting-edge|"
    r"state-of-the-art|forefront|leverage|leverages|leveraged|seamless|seamlessly|"
    r"robust\s+(?:framework|solution|system)"
    r")\b",
    re.IGNORECASE,
)
EM_DASH = "—"

MD_FILES = [
    "README.md",
    "MODEL_CARD.md",
    "BENCHMARKS.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "docs/methodology.md",
    "docs/setup-gee.md",
    "docs/privacy-impact-assessment.md",
    "docs/research/prior-work.md",
]
SITE_GLOBS = (
    "site/src/pages/**/*.astro",
    "site/src/components/**/*.astro",
    "site/src/layouts/**/*.astro",
)


def _all_text_files() -> list[Path]:
    files: list[Path] = []
    for rel in MD_FILES:
        p = ROOT / rel
        if p.exists():
            files.append(p)
    for pattern in SITE_GLOBS:
        files.extend(ROOT.glob(pattern))
    return files


# ---- Gates ---------------------------------------------------------------


def gate_em_dash():
    hits: list[str] = []
    for p in _all_text_files():
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if EM_DASH in line:
                hits.append(f"{p.relative_to(ROOT)}:{lineno}: {line.strip()}")
    return (
        "em-dash sweep",
        not hits,
        f"{len(hits)} hit(s)" if hits else f"clean ({len(_all_text_files())} files)",
    )


def gate_ai_jargon():
    hits: list[str] = []
    for p in _all_text_files():
        for lineno, line in enumerate(p.read_text(encoding="utf-8").splitlines(), start=1):
            if BANNED_AI_WORDS.search(line):
                hits.append(f"{p.relative_to(ROOT)}:{lineno}: {line.strip()[:80]}")
    return (
        "AI-jargon sweep",
        not hits,
        f"{len(hits)} hit(s)" if hits else f"clean ({len(_all_text_files())} files)",
    )


def gate_requirements_pinned():
    req = ROOT / "requirements.txt"
    if not req.exists():
        return ("requirements pinned", False, "requirements.txt missing")
    bad = []
    for lineno, raw in enumerate(req.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if any(op in line for op in (">=", "<=", "~=", "^")):
            bad.append(f"{lineno}: {line}")
    return ("requirements pinned", not bad, "loose pins: " + "; ".join(bad[:3]) if bad else "all ==")


def gate_package_version():
    init = ROOT / "leaves_ph" / "__init__.py"
    if not init.exists():
        return ("package version", False, "leaves_ph/__init__.py missing")
    m = re.search(r'__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', init.read_text())
    return ("package version", bool(m), f"v{m.group(1)}" if m else "no __version__")


def gate_site_root_boundary():
    pat = re.compile(r"""(?:from|import)\s+['"](\.\./){3,}|(?:from|import)\s+['"]/Users/""")
    hits: list[str] = []
    for f in ROOT.glob("site/src/**/*.astro"):
        for lineno, line in enumerate(f.read_text().splitlines(), start=1):
            if pat.search(line):
                hits.append(f"{f.relative_to(ROOT)}:{lineno}")
    return ("site/ root boundary", not hits, f"{len(hits)} escape(s)" if hits else "no imports escape site/")


def gate_per_lgu_csv_shape():
    p = ROOT / "data" / "per_lgu" / "per_lgu_canopy_2019_2026.csv"
    if not p.exists():
        return ("per-LGU CSV shape", False, "missing")
    with p.open() as f:
        rows = list(csv.DictReader(f))
    lgus = {r["lgu_name"] for r in rows}
    years = {r["year"] for r in rows}
    expected = 17 * 8
    ok = len(lgus) == 17 and len(years) == 8 and len(rows) == expected
    return ("per-LGU CSV shape", ok, f"{len(rows)} rows / {len(lgus)} LGUs / {len(years)} years")


def gate_geojson_features():
    p = ROOT / "site" / "public" / "data" / "per_lgu_canopy.geojson"
    if not p.exists():
        return ("per-LGU GeoJSON", False, "missing")
    fc = json.loads(p.read_text())
    n = len(fc.get("features", []))
    return ("per-LGU GeoJSON", n == 17, f"{n} features")


def gate_pmtiles_artifact():
    p = ROOT / "site" / "public" / "data" / "tree_crowns_ncr_tagged.pmtiles"
    if not p.exists():
        return ("pmtiles vector pyramid", False, "missing")
    size_mb = p.stat().st_size / 1_000_000
    return ("pmtiles vector pyramid", size_mb >= 5, f"{size_mb:.1f} MB")


def gate_clf_v3():
    clf = ROOT / "detection" / "train" / "clf_v3.joblib"
    metrics = ROOT / "detection" / "train" / "clf_v3_metrics.json"
    if not clf.exists() or not metrics.exists():
        return ("clf_v3 head", False, "missing clf_v3.joblib or metrics")
    m = json.loads(metrics.read_text())
    best_f1 = (m.get("cv5_f1_optimal") or {}).get("f1") or 0
    return ("clf_v3 head", best_f1 >= 0.70, f"CV F1={best_f1:.3f}")


def gate_clf_v4():
    clf = ROOT / "detection" / "train" / "clf_v4.joblib"
    metrics = ROOT / "detection" / "train" / "clf_v4_metrics.json"
    if not clf.exists() or not metrics.exists():
        return ("clf_v4 head (active learning)", False, "missing")
    m = json.loads(metrics.read_text())
    best_f1 = (m.get("cv5_f1_optimal") or {}).get("f1") or 0
    return ("clf_v4 head (active learning)", best_f1 >= 0.70, f"CV F1={best_f1:.3f}")


def gate_clf_v5():
    clf = ROOT / "detection" / "train" / "clf_v5.joblib"
    metrics = ROOT / "detection" / "train" / "clf_v5_metrics.json"
    rel = ROOT / "detection" / "train" / "clf_v5_reliability.json"
    if not all(p.exists() for p in (clf, metrics, rel)):
        return ("clf_v5 head (Platt-calibrated)", False, "missing")
    r = json.loads(rel.read_text())
    # Check reliability: predicted mean should be within 0.10 of empirical in each
    # populated bin (a basic calibration sanity check).
    bins = [b for b in r["bins"] if b["n"] > 0 and b["mean_pred"] is not None]
    if not bins:
        return ("clf_v5 head (Platt-calibrated)", False, "no populated bins")
    worst = max(abs(b["mean_pred"] - b["empirical_pos"]) for b in bins)
    return ("clf_v5 head (Platt-calibrated)", worst < 0.10, f"max bin |pred-empirical| = {worst:.3f}")


def gate_clf_v6():
    clf = ROOT / "detection" / "train" / "clf_v6.joblib"
    metrics = ROOT / "detection" / "train" / "clf_v6_metrics.json"
    if not clf.exists() or not metrics.exists():
        return ("clf_v6 Ridge regressor", False, "missing")
    m = json.loads(metrics.read_text())
    r2 = (m.get("cv5") or {}).get("r2") or 0
    mae = (m.get("cv5") or {}).get("mae") or 1.0
    return ("clf_v6 Ridge regressor", r2 >= 0.50 and mae < 0.10, f"R^2={r2:.3f}  MAE={mae:.3f}")


def gate_clf_v7():
    clf = ROOT / "detection" / "train" / "clf_v7.joblib"
    metrics = ROOT / "detection" / "train" / "clf_v7_metrics.json"
    if not clf.exists() or not metrics.exists():
        return ("clf_v7 GBR regressor", False, "missing")
    m = json.loads(metrics.read_text())
    r2 = (m.get("cv5") or {}).get("r2") or 0
    mae = (m.get("cv5") or {}).get("mae") or 1.0
    return ("clf_v7 GBR regressor", r2 >= 0.70 and mae < 0.06, f"R^2={r2:.3f}  MAE={mae:.3f}")


def gate_clf_v8():
    manifest = ROOT / "detection" / "train" / "clf_v8_per_lgu_manifest.json"
    if not manifest.exists():
        return ("clf_v8 per-LGU Platt", False, "manifest missing")
    m = json.loads(manifest.read_text())
    n_per_lgu = sum(1 for v in m.values() if v.get("strategy") == "platt_per_lgu")
    return ("clf_v8 per-LGU Platt", n_per_lgu >= 8, f"{n_per_lgu}/{len(m)} LGUs got per-LGU calibrator")


def gate_clf_v9():
    clf = ROOT / "detection" / "train" / "clf_v9.joblib"
    metrics = ROOT / "detection" / "train" / "clf_v9_metrics.json"
    if not clf.exists() or not metrics.exists():
        return ("clf_v9 multi-epoch GBR", False, "missing")
    m = json.loads(metrics.read_text())
    r2 = (m.get("cv5") or {}).get("r2") or 0
    per_year = m.get("per_year_cv") or {}
    min_r2 = min((v["r2"] for v in per_year.values()), default=0)
    return (
        "clf_v9 multi-epoch GBR",
        r2 >= 0.80 and min_r2 >= 0.70,
        f"overall R^2={r2:.3f}, min per-year R^2={min_r2:.3f}",
    )


def gate_per_barangay():
    csv_p = ROOT / "data" / "per_barangay" / "per_barangay_canopy_2019_2026.csv"
    gj_p = ROOT / "site" / "public" / "data" / "per_barangay_canopy.geojson"
    if not csv_p.exists() or not gj_p.exists():
        return ("per-barangay aggregation", False, "missing")
    with csv_p.open() as f:
        rows = list(csv.DictReader(f))
    return ("per-barangay aggregation", len(rows) >= 800, f"{len(rows)} barangays")


def gate_validation_panels():
    d = ROOT / "detection" / "scan" / "validation_v3"
    if not d.exists():
        return ("validation panels", False, "validation_v3/ missing")
    pngs = list(d.glob("validation_*_t*.png"))
    return ("validation panels", len(pngs) >= 17, f"{len(pngs)} panels in validation_v3/")


def gate_demo_gifs():
    needed = [
        "site/public/demo/remaining-canopy-satellite.gif",
        "site/public/demo/remaining-canopy-timeline.gif",
    ]
    missing = [n for n in needed if not (ROOT / n).exists()]
    return ("demo GIFs", not missing, "all present" if not missing else f"missing: {missing}")


def gate_series_constants():
    p = ROOT / "site" / "src" / "lib" / "series.ts"
    if not p.exists():
        return ("series constants", False, "site/src/lib/series.ts missing")
    text = p.read_text()
    needed = ["SERIES_START", "SERIES_END", "LATEST_NCR_PCT", "NCR_LGU_COUNT"]
    missing = [c for c in needed if c not in text]
    return ("series constants", not missing, "all present" if not missing else f"missing: {missing}")


def gate_calendar_text_in_masthead():
    p = ROOT / "site" / "src" / "components" / "Header.astro"
    if not p.exists():
        return ("masthead is timeless", False, "Header.astro missing")
    text = p.read_text()
    forbidden = ["MMXXVI", "VOLUME ONE", "ISSUE ZERO", "TUE · MAY"]
    hits = [w for w in forbidden if w in text]
    return ("masthead is timeless", not hits, "clean" if not hits else f"contains {hits}")


def gate_seo_description_length():
    p = ROOT / "site" / "src" / "layouts" / "Base.astro"
    if not p.exists():
        return ("SEO description length", False, "Base.astro missing")
    text = p.read_text()
    m = re.search(r'description\s*=\s*"([^"]+)"', text)
    if not m:
        return ("SEO description length", False, "no description default")
    length = len(m.group(1))
    return ("SEO description length", 50 <= length <= 220, f"{length} chars")


def gate_ncr_canopy_sanity():
    p = ROOT / "data" / "per_lgu" / "per_lgu_canopy_2019_2026.csv"
    if not p.exists():
        return ("NCR canopy bounded", True, "no CSV; SKIP")
    with p.open() as f:
        rows = list(csv.DictReader(f))
    by_year: dict[str, tuple[float, float]] = {}
    for r in rows:
        y = r["year"]
        canopy = float(r.get("canopy_ha", 0) or 0)
        total = float(r.get("total_ha", 0) or 0)
        prev = by_year.get(y, (0.0, 0.0))
        by_year[y] = (prev[0] + canopy, prev[1] + total)
    pcts = {y: 100 * c / t for y, (c, t) in by_year.items() if t}
    sane = all(2.0 < p < 25.0 for p in pcts.values())
    return (
        "NCR canopy bounded",
        sane,
        "years: " + ", ".join(f"{y}={p:.1f}%" for y, p in sorted(pcts.items())),
    )


def gate_clf_v3_scan_probs():
    p = ROOT / "detection" / "scan" / "clf_v3_probs_2024.tif"
    return (
        "clf_v3 scan probs raster",
        p.exists(),
        f"{p.stat().st_size / 1_000_000:.1f} MB" if p.exists() else "missing",
    )


def gate_threshold_sweep_exists():
    p = ROOT / "detection" / "scan" / "clf_v3_threshold_sweep_2024.json"
    if not p.exists():
        return ("threshold sweep file", False, "missing")
    sweep = json.loads(p.read_text())
    n = len(sweep.get("sweep", []))
    return ("threshold sweep file", n >= 5, f"{n} thresholds")


def gate_benchmarks_has_v3():
    p = ROOT / "BENCHMARKS.md"
    if not p.exists():
        return ("BENCHMARKS has v3", False, "missing")
    text = p.read_text()
    needed = ["v3 CLIP+LR", "clf_v3", "shared", "NEW"]
    missing = [w for w in needed if w not in text]
    return ("BENCHMARKS has v3", not missing, "v3 section present" if not missing else f"missing: {missing}")


def gate_site_typecheck():
    site = ROOT / "site"
    if not site.exists():
        return ("Astro typecheck", False, "site/ missing")
    res = subprocess.run(
        ["pnpm", "typecheck"],
        cwd=site,
        capture_output=True,
        text=True,
        timeout=120,
    )
    ok = res.returncode == 0 and "0 errors" in (res.stdout + res.stderr)
    tail = (res.stdout + res.stderr).strip().splitlines()[-3:]
    return ("Astro typecheck", ok, " | ".join(tail))


def gate_no_hardcoded_year_in_user_copy():
    """No literal '2026' anywhere in the public-facing astro components,
    pages, or layouts, except via {SERIES_END}/{LATEST}/etc interpolation."""
    rx = re.compile(r"(?<![\w_])2026(?![\w_])")
    allowed_substrings = [
        "canopy_2026_pct",
        "canopy_delta_2019_2026",
        "/data/",
        "leaves_ph_2026",
        "puspus_leaves_ph_",
        "year   = ",
    ]
    hits: list[str] = []
    for pattern in SITE_GLOBS:
        for f in ROOT.glob(pattern):
            for lineno, line in enumerate(f.read_text().splitlines(), start=1):
                if not rx.search(line):
                    continue
                if any(a in line for a in allowed_substrings):
                    continue
                hits.append(f"{f.relative_to(ROOT)}:{lineno}: {line.strip()[:80]}")
    return (
        "no hardcoded year in user copy",
        not hits,
        "clean" if not hits else f"{len(hits)} hit(s): " + " | ".join(hits[:2]),
    )


def main() -> int:
    gates = [
        gate_em_dash,
        gate_ai_jargon,
        gate_requirements_pinned,
        gate_package_version,
        gate_site_root_boundary,
        gate_per_lgu_csv_shape,
        gate_geojson_features,
        gate_pmtiles_artifact,
        gate_clf_v3,
        gate_clf_v4,
        gate_clf_v5,
        gate_clf_v6,
        gate_clf_v7,
        gate_clf_v8,
        gate_clf_v9,
        gate_per_barangay,
        gate_validation_panels,
        gate_demo_gifs,
        gate_series_constants,
        gate_calendar_text_in_masthead,
        gate_seo_description_length,
        gate_ncr_canopy_sanity,
        gate_clf_v3_scan_probs,
        gate_threshold_sweep_exists,
        gate_benchmarks_has_v3,
        gate_site_typecheck,
        gate_no_hardcoded_year_in_user_copy,
    ]
    n_pass = n_fail = 0
    for g in gates:
        try:
            name, ok, detail = g()
        except Exception as e:
            name, ok, detail = (g.__name__, False, f"raised {type(e).__name__}: {e}")
        marker = "[PASS]" if ok else "[FAIL]"
        print(f"{marker} {name}: {detail}")
        if ok:
            n_pass += 1
        else:
            n_fail += 1
    print()
    print(f"{n_pass} PASS / {n_fail} FAIL of {len(gates)} gates")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
