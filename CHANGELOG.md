# Changelog

All notable changes to Leaves.PH are tracked here.
The format is loosely based on Keep a Changelog 1.1.0; the project does not
follow strict semantic versioning before v1.0.0.

## [Unreleased]

## [0.2.0] - 2026-05-26

Phase 2 data layer code-complete. Six GEE / S3 / Overpass fetch scripts ready
for Xavier to kick off via `make fetch`. No data pulled yet (requires GEE auth
confirm + ~30 min quota).

### Added
- `pipeline/_gee_init.py`: shared GEE auth helper. Tries env-pointed service key, repo-local `.ee-key.json`, then interactive credentials. Exports `NCR_BBOX`, `NCR_YEARS`, `ncr_geometry()`.
- `pipeline/fetch_sentinel2_yearly.py`: annual S2 L2A median composites 2016-2026, s2cloudless-masked at probability < 40, exports 4-band GeoTIFFs at 10 m. Idempotent.
- `pipeline/fetch_hansen.py`: Hansen GFC v1.12 `treecover2000`, `lossyear`, `gain` bands cropped to NCR. Idempotent.
- `pipeline/fetch_esa_worldcover.py`: ESA WorldCover v200 (2021) full raster + binary tree-class mask.
- `pipeline/fetch_dynamic_world.py`: Dynamic World v1 annual median `trees` probability 2016-2026 at 10 m.
- `pipeline/fetch_meta_canopy_height.py`: Meta Canopy Height v2 tile fetch from AWS Open Data S3 (anonymous), with rasterio cropping to NCR bbox.
- `pipeline/fetch_lgu_polygons.py`: NCR LGU boundaries from OSM via Overpass, with admin_level=5/6 matching against `OSM_NAME_VARIANTS` for the 17 canonical LGUs (includes Las Pinas / Las Piñas + Paranaque / Parañaque accent variants). Returns non-zero exit if fewer than 17 match (early warning for OSM name drift).

### Total Phase 2 LoC
- 7 scripts, 823 lines of real implementation (no stubs remain in pipeline/).

## [0.1.0] - 2026-05-26

Scaffold landed. No data pulled yet. Build runs `make hash` only.

### Added
- `docs/research/prior-work.md` (Phase 0): dataset matrix for Hansen GFC v1.12, ESA WorldCover v200, Dynamic World v1, Meta Canopy Height v2, GEDI L2A, AlphaEarth Foundations V1, TESSERA; PH-specific evidence audit; 5 academic papers; 8 civic / news pieces.
- Python package `leaves_ph/` with `__version__ = "0.1.0"`, public API stubs (`compute_ndvi`, `canopy_threshold`, `aggregate_lgu`), `py.typed` marker.
- Hatchling-based `pyproject.toml` with dynamic version from `leaves_ph/__init__.py`.
- Pinned `requirements.txt` (numpy 1.26.4, scikit-learn 1.7.2, rasterio 1.4.3, geopandas 1.0.1, pillow 11.3.0).
- Dual-license `LICENSE`: MIT (code), CC-BY-4.0 (data), with upstream-source attribution block.
- `Makefile` with targets `fetch`, `compute`, `calibrate`, `animate`, `verify`, `hash`, `hash-verify`, `status`, `test`, `clean`.
- `Dockerfile` (python:3.12-slim-bookworm + GDAL/GEOS/PROJ system deps).
- `CITATION.cff`, `CODE_OF_CONDUCT.md`, `CONTRIBUTING.md`, `SECURITY.md`.
- `MODEL_CARD.md` and `BENCHMARKS.md` placeholders with the v1.0 target schema.
- Directory skeleton: `leaves_ph/`, `pipeline/`, `detection/train/`, `animation/`, `site/`, `scripts/`, `tests/`, `data/{composites,hansen,esa,meta,alphaearth,lgu,per_lgu}/`, `docs/{research,screenshots,demo,figures,launch}/`, `.github/{workflows,ISSUE_TEMPLATE}/`.

### Decisions locked (2026-05-26)
- v1.0 granularity: per-LGU only (17 NCR LGUs = 16 cities + Pateros). Per-barangay (142 polygons) deferred to v1.1. Note: original spec said "17 cities + Pateros = 18"; corrected to the PSA-canonical count (16 cities + 1 municipality = 17 LGUs total).
- Phase 4 (AlphaEarth + sklearn head): trained as a comparison artifact; published only if its per-LGU MAE is materially lower than the pure NDVI baseline.
- DENR-NCR / DPWH outreach: post-launch, not pre-launch. v1.0 publishes the documentation gap honestly.
- Frozen-encoder choice for the optional head: AlphaEarth Foundations V1 over TESSERA (AlphaEarth ships 2017-2025 day one; TESSERA backfill still rolling out; revisit at v1.1).

[Unreleased]: https://github.com/xmpuspus/leaves-ph/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/xmpuspus/leaves-ph/releases/tag/v0.1.0
