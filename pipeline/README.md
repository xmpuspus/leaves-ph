# pipeline/

GEE data pull, per-LGU compute, NDVI calibration, and the optional calibrated head.

Each script in this directory is a single-file standalone runnable script
that writes to `data/` under the repo root. Scripts are idempotent: re-running
overwrites the same output deterministically when the cached inputs are unchanged.

| Step | Script | Output |
|---|---|---|
| fetch | `fetch_sentinel2_yearly.py` | `data/composites/s2_ndvi_<year>.tif` for year in 2019..2026 |
| 2 | `fetch_hansen.py` | `data/hansen/{hansen_canopy2000,lossyear,gain}.tif` |
| 2 | `fetch_esa_worldcover.py` | `data/esa/worldcover_2021.tif` |
| 2 | `fetch_dynamic_world.py` | `data/composites/dw_trees_<year>.tif` for year in 2019..2026 |
| 2 | `fetch_meta_canopy_height.py` | `data/meta/canopy_height_ncr.tif` |
| 2 | `fetch_lgu_polygons.py` | `data/lgu/ncr_lgu.geojson` (17 LGUs) |
| 3 | `compute_canopy.py` | `data/composites/canopy_<year>.tif` per year |
| 3 | `calibrate_ndvi_threshold.py` | `data/calibration_report.json` |
| 3 | `aggregate_lgu.py` | `data/per_lgu/per_lgu_canopy_2019_2026.csv` |
| 3 | `csv_to_geojson.py` | `site/public/data/per_lgu_canopy.geojson` |
| 4 (optional) | `train_alphaearth_head.py` | `detection/train/clf_leaves_v1.joblib` |
| 4 (optional) | `apply_head.py` | scored per-LGU CSV |

Stubs land at scaffold-time as `# TODO` placeholders so the
Makefile targets are not broken when running `make help`.
