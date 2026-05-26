"""SALEX corridor canopy timeline (Quirino Ave, the 225-tree May 2026 felling).

The Southern Access Link Expressway clears 3.97 km along Quirino Avenue,
San Marcelino, and connects Skyway to Roxas Boulevard.

Output:
    docs/demo/salex-timeline.gif
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from _zoomed import REPO_ROOT, make_timeline  # noqa: E402

# Quirino Avenue corridor: roughly from Manila City Hall area south-west to
# the San Marcelino / Roxas Blvd intersection.
TARGET_BBOX = (120.978, 14.575, 121.000, 14.605)
ZOOM = 15
LABEL = "SALEX corridor (Quirino Ave)"
SUB_LABEL = "225 trees felled May 2026; 50+yr narra confirmed"
YEARS = list(range(2019, 2027))
OUT = REPO_ROOT / "docs" / "demo" / "salex-timeline.gif"


def main() -> int:
    return make_timeline(OUT, TARGET_BBOX, ZOOM, LABEL, SUB_LABEL, YEARS, fig_size=(9, 9))


if __name__ == "__main__":
    sys.exit(main())
