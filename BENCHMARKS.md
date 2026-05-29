# Benchmarks

In optimization toward a first release.

## Methodology overview

Three stages produce the published numbers and the detection model:

1. **NDVI baseline (published numbers).** Per-pixel rule `NDVI > 0.62` on Sentinel-2 surface reflectance, calibrated to Meta's 1m canopy-height reference. The threshold was chosen by F1-max sweep against Meta v2 canopy heights > 5m with a recall floor of 0.85. This baseline backs the map, the per-LGU series, the per-barangay series, and the headline NCR canopy percentage.

2. **Detection model (in optimization).** CLIP ViT-Large/14 image embeddings per Sentinel-2 RGB tile, with a gradient-boosted regression head (HistGradientBoostingRegressor) onto Meta's 1m canopy fraction (continuous, 0..1). This is the model under active optimization toward a first release.

3. **Held-out evaluation.** 5-fold cross-validation grouped by location, n = 16,800 tiles across 2019-2026, scored against Meta AI Global Canopy Height v2 (1m, canopy > 5m).

## Best-model benchmark

Full v6+v9 union (n = 38,260), same estimator and hyperparameters as the shipped model. Numbers reproducible from `detection/train/clf_v9_metrics_honest.json`:

| Split | MAE | RMSE | R² |
|---|---|---|---|
| Location-grouped CV (a location's tiles all in one fold) | 0.053 | 0.090 | 0.86 |
| 8×8 spatial-block CV (neighbouring tiles in one fold) | 0.056 | 0.097 | 0.84 |
| 5×5 spatial-block CV (coarser blocks) | 0.057 | 0.100 | 0.83 |
| (superseded) non-grouped shuffled split | 0.048 | 0.083 | 0.879 |

The honest headline is **R² 0.83–0.86 under grouped cross-validation** (0.86 location-grouped, 0.83 under coarse 5×5 spatial blocks where neighbouring 240m tiles and a location's 8 yearly epochs share a fold). `clf_v9_metrics.json` now reports these grouped numbers directly: headline `cv5` is location-grouped (R² 0.858), with `cv5_spatialblock_5x5` (0.826), `cv5_spatialblock_8x8` (0.836), and the old non-grouped shuffled split kept as `cv5_shuffled_superseded` (0.879). The shuffled split ([train_v9_multiepoch.py](detection/train/train_v9_multiepoch.py)) leaked adjacent tiles and repeated-location epochs across folds; it is superseded. Leakage inflation on the union is −0.02 (location) to −0.05 (spatial-block).

**This R² measures reproduction of Meta v2 canopy fraction (the calibration target), not accuracy against independent ground truth.** Independent check: against ESA WorldCover v200 (separate 10m product, 2021) the NDVI baseline agrees on 93% of pixels (IoU 0.52, F1 0.69). Independent satellite products span 3% (Dynamic World) to 13% (ESA) for the same NCR/year — our estimate is bracketed inside that envelope. See "Adjacent published estimates" below.

### Published canopy model vs NDVI baseline — accuracy against manual high-resolution labels

The published canopy product is no longer the bare NDVI > 0.62 rule. It is a **human-calibrated classifier** (gradient-boosted over NDVI, Dynamic-World tree probability, Meta v2 1m canopy height, and the ESA tree class) trained on **656 manually labeled high-resolution pixels**. Labels were drawn by active learning (round 1 stratified-random over 6 disjoint regions of the 17-LGU 2021 grid, rounds 2–4 oversampling the NDVI decision boundary [0.55, 0.66] and grass-vs-tree confusion zones) plus a **500-pixel uniform-random round** that tightened the confidence intervals. Each 30m target cell was marked on a 0.5–1m Esri World Imagery chip and labeled canopy = ≥25% woody tree canopy.

Scored against those labels under **region-grouped out-of-fold CV with post-stratified (NDVI-band × ESA-tree) population weighting** — unbiased despite the active-learning sampling — the model beats the baseline on every metric:

| Classifier (vs human labels, n=656) | Precision | Recall | F1 | IoU |
|---|---|---|---|---|
| **Published human-calibrated model (10 feat)** | **0.77** | **0.79** | **0.78** | **0.64** |
| NDVI > 0.62 baseline (comparison) | 0.69 | 0.67 | 0.68 | 0.52 |
| Meta height ≥ 5m (CLIP-model ceiling) | 0.96 | 0.46 | — | 0.45 |

The model's 10 features are NDVI, Dynamic-World tree prob, Meta 1m height, ESA-tree, and the raw Sentinel-2 spectral bands (red/nir/green/blue + GNDVI). It recovers diluted urban-fringe canopy the fixed threshold missed and uses the green/blue bands to reject high-NDVI grass/scrub the threshold over-called (precision 0.67 → 0.77); F1 +0.10, IoU +0.12 over the baseline. The NDVI baseline's own accuracy converged at F1 0.68 / IoU 0.52 (precision 95% CI 0.61–0.76 at n=656; implied canopy 10.1% vs its published 9.79%). **Feature ablation (region-grouped OOF, post-stratified):** the four base features score F1 0.75; adding the raw spectral bands lifts it to **0.78** (the win); ESA-neighbourhood fractions and NDVI texture give small gains; throwing all 21 features in overfits (0.74). **CLIP did not help, honestly reported:** the CLIP detection density as a scalar (F1 0.77, no gain) and a full CLIP ViT-L/14 embedding PCA-reduced (F1 0.73, a slight loss — the 240m S2 crop is too coarse for CLIP texture, and 656 samples overfit 768 dims). A learning curve on the 656 labels shows F1 plateaued by n≈300, so more labels tighten CIs but do not raise F1 — the feature set, not label count, is the ceiling. Single labeler — defensible, not definitive. Method, chips, scripts, per-round + ablation results: `tmp/labeling-20260529T073613Z/` (`RESULTS.md`, `master_labels.csv`, `model_comparison.json`, `rich_feature_result.json`, `clip_feature_result.json`, `learning_curve.json`).

## NCR area-weighted canopy — annual cross-sectional snapshots (not a change series)

Published series = the human-calibrated canopy model (above). The old NDVI baseline is shown alongside for comparison: the model **removes the threshold-crossing sawtooth** that plagued the NDVI series.

| Year | Published model % | NDVI baseline % | Notes |
|---|---|---|---|
| 2019 | 8.81 | 8.08 | first full-NCR year of S2 L2A PH coverage |
| 2020 | 9.74 | 9.88 | |
| 2021 | 10.11 | 9.79 | calibrated to 10.1% human-truth; ESA cross-check 13.38% |
| 2022 | 10.00 | 9.99 | |
| 2023 | 10.02 | 10.24 | |
| 2024 | 9.15 | 7.76 | baseline dips hard (greenness artifact); model holds |
| 2025 | 9.99 | 9.88 | |
| 2026 | 8.82 | 7.46 | provisional (imagery Jan-May 2026, 104 vs ~190 source scenes) |

**Read these as a per-year cross-sectional snapshot, not a trend.** The published model holds a steady **9–10% band** (swing 1.3 pp across 8 years; the threshold is calibrated so 2021 matches the 10.1% human-truth canopy). The NDVI baseline swung 2.78 pp, a **threshold-crossing artifact**: a small shift in each year's median-composite greenness moved a large near-threshold NDVI mass across the fixed 0.62 cut (in the dip years 2024/2026 the 90th-percentile NDVI fell from ~0.705 to ~0.63). The model's multi-feature decision (DW + Meta + ESA, not greenness alone) is far less sensitive to that, which is why its series is stable. Do not read any single year as a peak or decline. 2018 is excluded (~24% NCR coverage). The greenness-normalized baseline series is in `tmp/defensibility-20260529T043825Z/claim2_*.csv`; the model-vs-baseline per-year series is in `data/canopy_model/ncr_series_model_vs_ndvi.csv`.

## Per-LGU 2026 ranking (published model)

| Rank | LGU | 2026 canopy % | 2019→2026 Δ (pp) |
|---|---|---|---|
| 1 | Quezon City | 22.10 | -0.22 |
| 2 | Caloocan | 14.36 | -1.42 |
| 3 | Makati | 12.22 | +1.77 |
| 4 | Mandaluyong | 10.36 | +0.73 |
| 5 | Marikina | 7.96 | -0.32 |
| 6 | Pateros | 7.40 | +1.73 |
| 7 | Las Pinas | 7.12 | -0.20 |
| 8 | Pasig | 6.63 | +0.53 |
| 9 | Paranaque | 6.26 | +0.93 |
| 10 | Muntinlupa | 5.06 | -0.15 |
| 11 | Taguig | 4.80 | +0.60 |
| 12 | Valenzuela | 4.46 | -0.68 |
| 13 | San Juan | 4.45 | +0.24 |
| 14 | Pasay | 2.97 | -0.07 |
| 15 | Malabon | 2.53 | -0.20 |
| 16 | Manila | 1.37 | +0.23 |
| 17 | Navotas | 0.30 | -0.24 |

The "2019→2026 Δ" column is the difference of two cross-sectional snapshots, not measured canopy change. Quezon City carries the largest absolute share (La Mesa / Diliman / Wack Wack); the largest snapshot differences sit in Caloocan, Valenzuela, and Marikina. For reference, against ESA WorldCover v200 (2021) the underlying NDVI mask agrees on 93% of pixels (IoU 0.52); ESA runs higher (13.38%) because its tree class includes mixed shrub-tree pixels.

## Adjacent published estimates

| Source | Year | Method | NCR canopy |
|---|---|---|---|
| Meta v2 (canopy height > 5m) | 2018-20 | 1m AI canopy-height regression | 7.5% |
| ESA WorldCover v200 (class 10) | 2021 | 10m land cover classification | 13.38% |
| DENR FMB (cited in news / EJN) | 2024+ | not specified in public docs found | 6.0% |
| Global Forest Watch dashboard PHL/47 | 2020 baseline | Hansen 30m tree-cover ≥ 30% canopy | 4.0% |
| Earth Journalism Network | 2020 | DENR "open forest" sub-class | 2,071 ha |
| ScienceKonek 2024 map | 2024 | raster + methodology not publicly findable | unknown |

Definitions differ across sources (canopy fraction vs closed-canopy area, % vs hectares, single-epoch vs multi-year baseline). Listed for methodology context, not as a ranking.

## Hansen GFC cumulative tree-cover loss, NCR 2001-2025

| LGU | Hansen cumulative loss (ha) |
|---|---|
| Taguig | 77.6 |
| Quezon City | 30.5 |
| Caloocan | 19.6 |
| Las Pinas | 15.9 |
| Valenzuela | 15.8 |
| Navotas | 8.5 |
| Pasig | 6.7 |
| Muntinlupa | 3.7 |
| Paranaque | 3.1 |
| Marikina | 2.6 |
| Manila | 1.6 |
| Pasay | 1.5 |
| Malabon | 0.7 |
| Makati | 0.6 |
| Others | 0.0 |
| Total NCR | ~188 |

Hansen 30m misses sub-pixel clearings. Localized events appear in the global Hansen product only at the next release cadence.

## Per-barangay aggregation (892 OSM admin-level=10 polygons)

`data/per_barangay/per_barangay_canopy_2019_2026.csv` aggregates the canopy density rasters to OSM admin-level=10 polygons whose centroid falls inside one of the 17 NCR LGUs. 892 barangays are covered (OSM admin-level=10 is more granular than PSA's 142 canonical barangays; many barangays are subdivided in OSM).

Top per-barangay 2026 canopy fraction (provisional):

| Barangay | LGU | total ha | 2026 canopy % |
|---|---|---|---|
| Forbes Park | Makati | 253 | 20.05% |
| Post Proper Southside | Taguig | 11 | 19.59% |
| Pansol | Quezon City | 172 | 18.98% |
| Urdaneta | Makati | 75 | 18.26% |
| UP Campus | Quezon City | 465 | 18.19% |
| Dasmariñas | Makati | 192 | 14.81% |
| Matandang Balara | Quezon City | 533 | 14.05% |
| Bagong Silangan | Quezon City | 408 | 13.96% |

The top hits are the well-known canopy-rich enclaves: Forbes Park (Makati gated forest), Post Proper Southside (BGC parks), UP Campus (Diliman), and La Mesa-adjacent QC barangays. Bottom barangays are the small dense urban polygons in Manila and Pasay that round to 0% canopy.

GeoJSON for site overlay: `site/public/data/per_barangay_canopy.geojson`.

## Files

| Artifact | Description |
|---|---|
| `data/calibration_report.json` | NDVI sweep against Meta v2 truth |
| `data/per_lgu/per_lgu_canopy_2019_2026.csv` | 17-LGU canopy series (hash-pinned canonical) |
| `data/per_barangay/per_barangay_canopy_2019_2026.csv` | 892-barangay canopy series |
| `detection/train/` | CLIP embeddings and the gradient-boosted regression head |
| `detection/scan/` | per-pixel canopy density rasters and NCR/LGU series |
| `site/public/data/per_barangay_canopy.geojson` | per-barangay GeoJSON for the site overlay |

## Known limitations

- The tile window inherits a granularity floor: sub-tile canopy patches smaller than the tile footprint are below the model's resolution.
- The detection model is evaluated against Meta v2 (a fixed ~2019 reference), so it estimates canopy fraction, not change over time.
- The published series are NDVI-baseline numbers calibrated to Meta; the CLIP + gradient-boosted model is still under optimization and does not yet back the published figures.
- 2026 is provisional: the year's Sentinel-2 imagery only spans January through May.

## Reproducibility

```bash
pip install -r requirements.txt
make fetch              # GEE + AWS; ~30 min
make calibrate          # NDVI threshold tuned against Meta v2
make compute            # per-year canopy mask, per-LGU CSV
python3 detection/bootstrap/fetch_osm_tree_labels.py
python3 detection/buildings/fetch_tiles.py
python3 detection/scan/ncr_scan.py
make verify             # release gate
make hash               # sha256 of per_lgu_canopy_2019_2026.csv
```
