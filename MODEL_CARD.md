# Leaves.PH Model Card

Status: numbers fill in once the pipeline runs against your local data.

## Intended use

Leaves.PH publishes a per-LGU canopy curve for Metro Manila (16 cities plus the municipality of Pateros, 17 LGUs total), 2019 to 2026, computed from a stack of canonical public canopy datasets. It is **not** a per-household measurement, not a parcel-level land-use tool, and not a per-tree census.

## Pipeline overview

1. **Inputs:** Sentinel-2 L2A median composites (annual, cloud-masked via s2cloudless), Hansen GFC v1.13 loss-year band, ESA WorldCover v200 class-10 tree mask, Dynamic World v1 `trees` probability median per year, Meta Canopy Height v2 tile crop.
2. **NDVI threshold:** tuned per-year against Meta canopy height v2 (target: greater than 90 percent pixel-level agreement with Meta height greater than 5 m).
3. **Per-LGU aggregation:** PSA / OSM administrative polygons for the 17 NCR LGUs (16 cities + Pateros); pixel-level canopy mask summed per polygon.
4. **(Optional)** AlphaEarth Foundations Satellite Embedding V1 + sklearn logistic head, 5-fold per-LGU-group CV, Platt sigmoid calibration. Shipped only if its per-LGU MAE is materially lower than the pure NDVI threshold .

## Known biases

- Meta Canopy Height v2 source imagery is 80 percent 2018-2020. Our calibration layer is a ~2019 truth.
- Sentinel-2 cloud masking removes many wet-season images in tropical monsoon zones, potentially under-representing canopy during June to September.
- Dynamic World probability values reflect model confidence, not ground truth.
- Hansen GFC v1.13 cannot distinguish plantation harvest from natural forest loss.
- 30 m Hansen resolution misses small-scale urban tree-cutting events.

## Reported metrics

Skeleton:

| Metric | Per-LGU MAE | All-NCR error vs GFW dashboard | All-NCR error vs DENR 6 percent claim |
|---|---|---|---|
| NDVI threshold baseline | TBD | TBD | TBD |
| AlphaEarth + sklearn head (if shipped) | TBD | TBD | TBD |

## Sources of truth used in evaluation

- Meta Canopy Height v2 (1 m wall-to-wall, calibration layer)
- GEDI L2A monthly RH98 (sparse spot-truth at ~300 points)
- ESA WorldCover v200 2021 (independent 10 m cross-check)
- EJN October 2024 anchors: Muntinlupa 14.4 sq m/capita, Quezon City 12.5 sq m/capita + 33 percent canopy (Google Environmental Insights Explorer), Escopa IV (QC) 1.48 percent
- Estoque et al. 2018 La Mesa watershed: -259 ha 1988-2002, +557 ha 2002-2016

## Versioning and provenance

Every artifact ships with a sha256 prefix. `data/per_lgu/per_lgu_canopy_2019_2026.csv` is the deterministic-build canonical. The Makefile asserts the hash. Dependency drift breaks the hash and CI fails.

## Author and license

Xavier Puspus. MIT (code) + CC-BY-4.0 (data). See `LICENSE` and `CITATION.cff`.
