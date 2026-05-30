"""La Mesa watershed + Marikina canopy timeline (NE NCR green zone).

Output:
    docs/demo/la-mesa-watershed.gif
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _zoomed import REPO_ROOT, make_timeline

# La Mesa watershed + Marikina + UP Diliman: the NE green zone (largely QC).
TARGET_BBOX = (121.03, 14.66, 121.13, 14.78)
ZOOM = 13
LABEL = "La Mesa watershed + Marikina"
SUB_LABEL = "NE NCR green zone (QC + Marikina)"
YEARS = list(range(2019, 2027))
OUT = REPO_ROOT / "docs" / "demo" / "la-mesa-watershed.gif"


def main() -> int:
    return make_timeline(OUT, TARGET_BBOX, ZOOM, LABEL, SUB_LABEL, YEARS)


if __name__ == "__main__":
    sys.exit(main())
