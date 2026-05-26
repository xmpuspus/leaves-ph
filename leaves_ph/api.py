"""Public API stubs. Real implementations land in Phase 3 (per-LGU compute)."""

from __future__ import annotations

from typing import Any


def compute_ndvi(red: Any, nir: Any) -> Any:
    """NDVI = (NIR - RED) / (NIR + RED), masked where the denominator is 0.

    Args:
        red: red-band array (Sentinel-2 B4) as a numpy array or similar.
        nir: NIR-band array (Sentinel-2 B8) of matching shape.

    Returns:
        NDVI array in [-1, 1], NaN where the denominator is 0.

    Note: Phase 3 fills in the real implementation. This stub raises so that
    a missing-phase regression is caught by the smoke test.
    """
    raise NotImplementedError("compute_ndvi is provided in Phase 3.")


def canopy_threshold(ndvi: Any, threshold: float = 0.5) -> Any:
    """Binary canopy mask from an NDVI raster.

    Args:
        ndvi: NDVI raster as a numpy array.
        threshold: NDVI value above which a pixel is treated as canopy.
                   v1.0 default 0.5; calibrated against Meta canopy height v2.

    Returns:
        Boolean array of the same shape, True for canopy pixels.

    Phase 3 implementation tunes the threshold per the calibration report.
    """
    raise NotImplementedError("canopy_threshold is provided in Phase 3.")


def aggregate_lgu(canopy_mask: Any, lgu_polygons: Any) -> dict[str, dict[str, float]]:
    """Per-LGU canopy stats from a binary canopy mask and an LGU polygon set.

    Args:
        canopy_mask: boolean canopy raster from canopy_threshold().
        lgu_polygons: GeoDataFrame with one row per LGU (17 NCR cities + Pateros).

    Returns:
        Mapping LGU name -> {canopy_ha, canopy_pct, total_ha}.
    """
    raise NotImplementedError("aggregate_lgu is provided in Phase 3.")
