#!/usr/bin/env python3
"""Leaves.PH release-readiness gate. Stub for v0.1.0; full gate lands at Phase 7.

Mirrors `solar-map-ph/scripts/verify_v11_release.py`. Must return
N PASS / 0 FAIL before any tag, push, or deploy.

Checks (full set at Phase 7):
- per_lgu_canopy_2016_2026.csv parses and matches schema
- 17 LGUs present in the CSV; no extra or missing
- classifier hash matches canonical (only if Phase 4 ran)
- requirements.txt fully pinned (no >=, ^, ~)
- site/src/data/per_lgu_canopy.json mirrors data/per_lgu/per_lgu_canopy_2016_2026.csv
- README hero counter matches actual aggregated canopy_ha
- Zero em-dashes in README, MODEL_CARD, BENCHMARKS, CHANGELOG, docs/research/, site/src/
- Zero AI-jargon hits from the no-ai-jargon ban list

v0.1.0 checks only what exists.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent

BANNED_AI_WORDS = re.compile(
    r"(delve|tapestry|in the realm of|paradigm shift|game-changer|cutting-edge|state-of-the-art|forefront)",
    re.IGNORECASE,
)
EM_DASH = "—"

MD_FILES = [
    "README.md",
    "MODEL_CARD.md",
    "BENCHMARKS.md",
    "CHANGELOG.md",
    "CONTRIBUTING.md",
    "SECURITY.md",
    "CODE_OF_CONDUCT.md",
    "docs/research/prior-work.md",
]


def gate_em_dash() -> tuple[str, bool, str]:
    hits: list[str] = []
    for rel in MD_FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if EM_DASH in line:
                hits.append(f"{rel}:{lineno}: {line.strip()}")
    if hits:
        return ("em-dash sweep", False, f"{len(hits)} em-dash hit(s):\n  " + "\n  ".join(hits[:10]))
    return ("em-dash sweep", True, "no em-dashes")


def gate_ai_jargon() -> tuple[str, bool, str]:
    hits: list[str] = []
    for rel in MD_FILES:
        p = ROOT / rel
        if not p.exists():
            continue
        text = p.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), start=1):
            if BANNED_AI_WORDS.search(line):
                hits.append(f"{rel}:{lineno}: {line.strip()}")
    if hits:
        return ("AI-jargon sweep", False, f"{len(hits)} AI-jargon hit(s):\n  " + "\n  ".join(hits[:10]))
    return ("AI-jargon sweep", True, "no AI-jargon hits")


def gate_requirements_pinned() -> tuple[str, bool, str]:
    req = ROOT / "requirements.txt"
    if not req.exists():
        return ("requirements pinned", False, "requirements.txt missing")
    bad: list[str] = []
    for lineno, raw in enumerate(req.read_text().splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if any(op in line for op in (">=", "<=", "~=", "^")):
            bad.append(f"requirements.txt:{lineno}: {line}")
    if bad:
        return ("requirements pinned", False, "loose pins:\n  " + "\n  ".join(bad))
    return ("requirements pinned", True, "all pins are ==")


def gate_package_version() -> tuple[str, bool, str]:
    init = ROOT / "leaves_ph" / "__init__.py"
    if not init.exists():
        return ("package version", False, "leaves_ph/__init__.py missing")
    text = init.read_text()
    m = re.search(r'__version__\s*=\s*["\'](\d+\.\d+\.\d+)["\']', text)
    if not m:
        return ("package version", False, "could not find __version__ in leaves_ph/__init__.py")
    return ("package version", True, f"__version__ = {m.group(1)}")


def gate_per_lgu_csv_optional() -> tuple[str, bool, str]:
    """Phase 3+ artifact. v0.1.0 SKIP."""
    p = ROOT / "data" / "per_lgu" / "per_lgu_canopy_2016_2026.csv"
    if not p.exists():
        return ("per-LGU CSV (Phase 3+)", True, "not yet built (pre-Phase 3); SKIP")
    import csv

    with p.open() as f:
        rows = list(csv.DictReader(f))
    lgu_set = {r["lgu_name"] for r in rows}
    if len(lgu_set) != 17:
        return ("per-LGU CSV (Phase 3+)", False, f"expected 17 LGUs, got {len(lgu_set)}: {sorted(lgu_set)}")
    return ("per-LGU CSV (Phase 3+)", True, f"17 LGUs, {len(rows)} rows")


def main() -> int:
    gates = [
        gate_em_dash,
        gate_ai_jargon,
        gate_requirements_pinned,
        gate_package_version,
        gate_per_lgu_csv_optional,
    ]
    n_pass = 0
    n_fail = 0
    for gate in gates:
        name, ok, detail = gate()
        marker = "[PASS]" if ok else "[FAIL]"
        print(f"{marker} {name}: {detail}")
        if ok:
            n_pass += 1
        else:
            n_fail += 1
    print()
    print(f"{n_pass} PASS / {n_fail} FAIL")
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
