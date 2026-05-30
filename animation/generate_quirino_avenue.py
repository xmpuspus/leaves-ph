"""Quirino Avenue tight close-up (Manila City Hall to Roxas Boulevard segment).

Output:
    docs/demo/quirino-avenue.gif
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _zoomed import REPO_ROOT, make_timeline

# Tight zoom on the most-photographed Quirino Avenue stretch.
TARGET_BBOX = (120.985, 14.585, 120.998, 14.602)
ZOOM = 16
LABEL = "Quirino Avenue close-up"
SUB_LABEL = "The strip the Inquirer / PhilStar coverage centred on"
YEARS = list(range(2019, 2027))
OUT = REPO_ROOT / "docs" / "demo" / "quirino-avenue.gif"


def main() -> int:
    return make_timeline(OUT, TARGET_BBOX, ZOOM, LABEL, SUB_LABEL, YEARS, fig_size=(9, 11))


if __name__ == "__main__":
    sys.exit(main())
