"""Leaves.PH: validate Metro Manila tree cover against public canopy datasets.

Public API surface (stable from v1.0):

    from leaves_ph import __version__
    from leaves_ph import compute_ndvi              # S2 SR band math -> NDVI
    from leaves_ph import canopy_threshold          # NDVI threshold tuned to Meta canopy height
    from leaves_ph import aggregate_lgu             # per-LGU stats from a raster + polygons

Everything else is internal and may change between versions.
"""

from __future__ import annotations

__version__ = "0.2.0"

from .api import (
    aggregate_lgu,
    canopy_threshold,
    compute_ndvi,
)

__all__ = [
    "__version__",
    "aggregate_lgu",
    "canopy_threshold",
    "compute_ndvi",
]
