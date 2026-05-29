# Benchmarks

## Pipeline overview

| Stage | Layer | Definition |
|---|---|---|
| v0 baseline | NDVI threshold | Per-pixel rule `NDVI > 0.62` on Sentinel-2 surface-reflectance. Threshold chosen by F1-max sweep against the Meta v2 1m canopy-height reference at heights >5m, recall floor 0.85. |
| v2 first head | CLIP ViT-L + LR | OSM-bootstrapped labels (5,460 tiles): `natural=tree`, `landuse=forest`, `leisure=park` as positives; `building`, `highway`, `landuse=industrial` as negatives. CLIP image embeddings; LogisticRegression head (`max_iter=2000, C=1.0, class_weight=balanced, random_state=42`). |
| v3 teacher signal | CLIP ViT-L + LR | dataset_v2 + ESA WorldCover v200 2021 teacher labels (3,591 tiles): class 10 tree-cover as positive; class 50 built-up, 80 water, 30 grassland, 40 cropland as hard negatives. Same hyper-params. |
| v4 active learning | CLIP ViT-L + LR | dataset_v3 + Meta-v2-oracle hard-negative mining (882 tiles): clf_v3 high-confidence NEW that Meta rejects → hard negatives; clf_v3 dropped that Meta confirms → positives; tiles where both clf and NDVI miss but Meta finds canopy → positives. Same hyper-params. |
| v5 Platt | clf_v4 + sigmoid calibration | `CalibratedClassifierCV(method="sigmoid", cv=5)` wraps clf_v4. Output probabilities are reliability-calibrated against the empirical positive rate (5-bin max gap = 0.055). |
| v6 continuous | CLIP ViT-L + Ridge | Continuous canopy-fraction regression (target: Meta v2 >5m fraction per 240m tile, 0..1). Same 21,460-tile scan grid as the classifier. Replaces the binary tile mask with a continuous density estimate for canopy hectares. |
| v7 non-linear | CLIP ViT-L + GBR | HistGradientBoosting regressor on the same dataset_v6 target. Corrects v6's bias-to-mean at high canopy fractions. CV MAE 0.038 (v6 was 0.047), R² 0.781 (v6 was 0.709). |
| v8 per-LGU Platt | clf_v4 + per-LGU sigmoid | 12 of the 17 LGUs get their own Platt sigmoid (n >= 150 labelled samples). 11/12 improved reliability gap over the regional v5. Sparse LGUs (Pateros, San Juan, Navotas, Malabon, Mandaluyong) fall back to regional v5. |
| v9 multi-epoch | CLIP ViT-L + GBR | Multi-year training (2,100 stratified locations × 8 epochs = 16,800 (loc, year) pairs added to dataset_v6). Per-year CV R² in [0.82, 0.91] across all 8 epochs. Overall R² 0.879 (v7 was 0.781). |
| v10 finer windows | CLIP ViT-L + GBR | 4×4 pixel tiles (~120m) instead of v6/v9's 8×8 (240m). 20,000 stratified samples. Sub-tile canopy fraction comes from the finer grid directly rather than averaging over the larger tile. |

## NCR area-weighted canopy series

Annual epochs 2019-2026, v0 NDVI threshold pipeline.

| Year | NCR canopy % | Canopy hectares | Notes |
|---|---|---|---|
| 2019 | 8.08 | 6,325 | first full-NCR year of S2 L2A PH coverage |
| 2020 | 9.88 | 7,737 | |
| 2021 | 9.79 | 7,665 | ESA WorldCover v200 cross-check: 13.38% area-weighted |
| 2022 | 9.99 | 7,818 | |
| 2023 | 10.24 | 8,013 | 8-year peak |
| 2024 | 7.76 | 6,076 | |
| 2025 | 9.88 | 7,733 | |
| 2026 | 7.46 | 5,840 | most recent measurement |

2018 has only ~24% NCR coverage (S2 L2A PH coverage was thin that early) and is excluded from the published series. Source-image counts per year in `data/composites/_fetch_manifest_s2.json`.

## Held-out CV F1 (5-fold stratified)

| Version | Labels | Best CV F1 | Deploy t | Precision | Recall |
|---|---|---|---|---|---|
| v0 NDVI | 10k px (Meta truth) | 0.512 | 0.62 | 0.365 | 0.853 |
| v2 CLIP+LR | 5,460 OSM | 0.691 | 0.50 | 0.695 | 0.687 |
| v3 CLIP+LR | 9,051 OSM + ESA | 0.784 | 0.50 | 0.755 | 0.816 |
| v4 CLIP+LR | 9,933 OSM + ESA + Meta active learning | 0.772 | 0.45 | 0.721 | 0.829 |
| v5 Platt | clf_v4 + sigmoid calibration | 0.771 | 0.35 | 0.697 | 0.863 |

v4 CV F1 is fractionally lower than v3's because the v4 evaluation includes hard cases (clf-NEW-that-Meta-rejects, etc.) that v3 never saw at training time. The point of v4 is that the model has been corrected on those hard cases. Per-source-prefix CV mean probability in clf_v4_metrics.json shows: v4_a_meta_confirms_new mean_p=0.81 (correctly endorses confirmed expansions), v4_b_meta_rejects_new mean_p=0.65 (pulled down on the false-positive direction), v4_c_meta_rejects_shared mean_p=0.70 (pulled down), v4_f_meta_only_positive mean_p=0.52 (Meta-only positives lifted from low).

v5 Platt calibration sigmoid produces reliability bins that match the empirical positive rate within 0.055:

| Predicted bin | n | mean predicted | empirical positive rate |
|---|---|---|---|
| [0.0, 0.1] | 1,470 | 0.059 | 0.005 |
| [0.4, 0.5] | 683   | 0.447 | 0.432 |
| [0.5, 0.6] | 718   | 0.551 | 0.570 |
| [0.7, 0.8] | 929   | 0.751 | 0.746 |
| [0.9, 1.0] | 818   | 0.935 | 0.971 |

Full reliability table: `detection/train/clf_v5_reliability.json`.

## Regression head progression (continuous canopy fraction)

5-fold cross-validated metrics, target = Meta v2 >5m canopy fraction per tile (0..1):

| Version | Model | Dataset | Window | n | MAE | RMSE | R² |
|---|---|---|---|---|---|---|---|
| v6 | Ridge | dataset_v6 (2024 imagery only) | 240m | 21,460 | 0.047 | 0.083 | 0.709 |
| v7 | HistGradientBoosting | dataset_v6 (2024 imagery only) | 240m | 21,460 | 0.038 | 0.072 | 0.781 |
| v9 | HistGradientBoosting | dataset_v6 + dataset_v9 multi-epoch | 240m | 38,260 | 0.048 | 0.083 | 0.879 |
| v10 | HistGradientBoosting | dataset_v10 stratified | 120m | 20,000 | 0.082 | 0.125 | 0.783 |

v10 vs v9 (same model, finer window): R² drops from 0.879 to 0.783, MAE roughly doubles. **Finer windows do not pay off at S2 30m native resolution.** A 4×4-pixel = 120m window upsampled to 224×224 for CLIP carries less information than an 8×8 = 240m window, and the regression target (Meta-fraction over 16 ESA pixels) is noisier than over 64 pixels. v9 stays the deployed regressor. If a future revision upgrades the input to S2 10m or PlanetScope 3m, the finer-window hypothesis is worth re-testing.

v7 vs v6 (same data, different model): GBR cuts MAE 19% and lifts R² from 0.71 to 0.78. High-end bin [0.9, 1.0] true 0.97 → v6 predicted 0.68 (off 0.29) vs v7 predicted 0.85 (off 0.12). The Ridge bias-to-mean is substantially corrected.

v9 vs v7 (multi-epoch training): R² jumps to 0.879. Per-year CV R²:

| Year | n | CV MAE | CV R² |
|---|---|---|---|
| 2019 | 2,100 | 0.0547 | 0.908 |
| 2020 | 2,100 | 0.0573 | 0.898 |
| 2021 | 2,100 | 0.0597 | 0.889 |
| 2022 | 2,100 | 0.0638 | 0.876 |
| 2023 | 2,100 | 0.0589 | 0.893 |
| 2024 | 23,560 | 0.0386 | 0.842 |
| 2025 | 2,100 | 0.0696 | 0.857 |
| 2026 | 2,100 | 0.0793 | 0.819 |

The multi-year training closes the per-epoch generalisation gap: 2019-2023 R² lands in [0.88, 0.91], 2025-2026 R² lands in [0.82, 0.86]. v9 is the deployed head for any future multi-year scan.

## v6 continuous regression (legacy details)

5-fold cross-validated metrics on dataset_v6 (21,460 tiles, target = Meta v2 >5m canopy fraction per tile, 0..1):

| Metric | Value |
|---|---|
| MAE | 0.047 |
| RMSE | 0.083 |
| R² | 0.709 |

Per-target-bin residuals (`detection/train/clf_v6_residuals_by_bin.json`) show clean predictions in [0, 0.3] but bias-toward-mean at the high end: tiles with true fraction 0.85 are predicted at 0.55, tiles with true fraction 0.97 are predicted at 0.68. The v6 regressor is a Ridge linear head; a non-linear (gradient-boosted) regressor would correct the high-end bias at the cost of a non-deterministic artefact. Future v7.

### v6 NCR canopy (2024 cross-validated)

| Layer | NCR canopy (2024) | Canopy hectares |
|---|---|---|
| v0 NDVI baseline | 7.78% | 6,094 |
| v3 binary tile classifier (t=0.60) | 7.36% | 5,765 |
| v6 continuous regression (CV) | 7.73% | 6,096 |

The v6 continuous head lands within 0.05pp of the v0 NDVI baseline at NCR level, a useful cross-check that the regression target (Meta v2 >5m fraction) is consistent with the NDVI threshold (NDVI > 0.62, calibrated against Meta >5m). Per-LGU the v6 estimates compress toward the regional mean (the Ridge bias-to-mean noted above): QC v6 = 16.9% vs v0 NDVI 19.5%, Manila v6 = 1.99% vs v0 0.69%.

Per-LGU v6 2024 cross-validated:

| LGU | v6 canopy % | v6 canopy ha |
|---|---|---|
| Quezon City | 16.93 | 2,725 |
| Marikina | 10.42 | 238 |
| Makati | 9.27 | 168 |
| Caloocan | 8.77 | 467 |
| Pasig | 8.31 | 256 |
| Pateros | 7.24 | 13 |
| San Juan | 7.14 | 42 |
| Las Pinas | 7.06 | 257 |
| Mandaluyong | 7.04 | 80 |
| Paranaque | 6.41 | 385 |
| Valenzuela | 6.23 | 293 |
| Malabon | 5.86 | 97 |
| Taguig | 5.60 | 447 |
| Muntinlupa | 3.96 | 264 |
| Pasay | 3.44 | 117 |
| Manila | 1.99 | 211 |
| Navotas | 0.98 | 36 |

Multi-year v6 NCR canopy series landed.

## v6 multi-year NCR canopy series

Per-year v6 continuous-density estimates across 2019-2026, from the Ridge regressor applied to fresh Sentinel-2 RGB embeddings for each annual epoch.

| Year | v6 NCR canopy % | v6 canopy hectares | Total NCR ha |
|---|---|---|---|
| 2019 | 7.06% | 5,562 | 78,811 |
| 2020 | 8.00% | 6,306 | 78,811 |
| 2021 | 7.18% | 5,659 | 78,811 |
| 2022 | 6.98% | 5,500 | 78,811 |
| 2023 | 7.68% | 6,054 | 78,811 |
| 2024 | 7.76% | 6,117 | 78,811 |
| 2025 | 7.67% | 6,047 | 78,811 |
| 2026 | 7.37% | 5,804 | 78,811 |

2019 -> 2026 v6 series delta: +0.31 pp.


v3 metrics file: `detection/train/clf_v3_metrics.json`. Per-source CV probabilities in the same file (sanity check that ESA-water tiles score ~0.10 mean probability while ESA-tree tiles score ~0.88).

## NCR 2024 scan: v0 baseline vs v3 confirmation/expansion

Scan at the 240m tile grid (8×8 Sentinel-2 pixels), v3 deploy threshold t=0.60.

| Layer | % of NCR area | hectares |
|---|---|---|
| v0 NDVI baseline | 7.78% | 6,094 |
| v3 confirmed (shared with v0) | 4.54% | 3,556 |
| v3 NEW (added on top of v0) | 2.82% | 2,209 |
| v3 dropped (v0 hits the model rejects) | 3.25% | 2,547 |
| v3 total | 7.36% | 5,765 |

v3 is not a strict superset of v0. It confirms ~58% of the v0 baseline, removes 42% as suspected NDVI false positives (e.g. grass / sparse vegetation that crosses 0.62 NDVI), and proposes 2.82pp NEW canopy that the per-pixel NDVI rule missed (urban tree clusters, mixed-class neighborhoods with real tree presence inside the 240m tile).

Full sweep across thresholds 0.30 to 0.90 in `detection/scan/clf_v3_threshold_sweep_2024.json`.

## Per-LGU v0 vs v3 (2024, t=0.60)

LGUs where v3 expands the v0 baseline (Δ > 0):

| LGU | NDVI v0 | clf_v3 | Δ (pp) | NEW (pp) | dropped (pp) |
|---|---|---|---|---|---|
| Taguig | 8.24% | 10.22% | +1.98 | 4.62 | 2.63 |
| Mandaluyong | 10.59% | 12.11% | +1.51 | 4.64 | 3.12 |
| Makati | 7.89% | 8.61% | +0.71 | 4.54 | 3.82 |
| Malabon | 5.28% | 5.60% | +0.32 | 4.16 | 3.84 |
| Navotas | 0.39% | 0.45% | +0.06 | 0.34 | 0.28 |

LGUs where v3 trims more than it adds (Δ < 0):

| LGU | NDVI v0 | clf_v3 | Δ (pp) | NEW (pp) | dropped (pp) |
|---|---|---|---|---|---|
| Pateros | 4.68% | 0.84% | −3.84 | 0.80 | 4.64 |
| Caloocan | 8.79% | 5.79% | −3.00 | 3.02 | 6.02 |
| San Juan | 2.31% | 0.21% | −2.10 | 0.20 | 2.29 |
| Pasig | 5.60% | 3.84% | −1.76 | 2.45 | 4.22 |
| Las Pinas | 4.58% | 3.26% | −1.32 | 2.01 | 3.32 |

Full table: `detection/scan/clf_v3_vs_ndvi_per_lgu_2024_t60.csv`. Visual validation panels per LGU: `detection/scan/validation_v3/*.png`.

## Per-LGU 2026 baseline ranking (v0 NDVI)

| Rank | LGU | 2026 canopy % | 2019→2026 Δ (pp) | ESA 2021 % |
|---|---|---|---|---|
| 1 | Quezon City | 18.93 | −0.38 | 28.77 |
| 2 | Mandaluyong | 11.19 | −0.28 | 14.40 |
| 3 | Makati | 8.92 | +1.69 | 16.01 |
| 4 | Caloocan | 8.80 | −0.96 | 23.62 |
| 5 | Marikina | 6.87 | −0.01 | 17.10 |
| 6 | Taguig | 6.47 | −2.76 | 7.58 |
| 7 | Valenzuela | 5.81 | −1.39 | 14.56 |
| 8 | Pasig | 5.23 | −0.17 | 12.01 |
| 9 | Las Pinas | 5.20 | −1.47 | 11.92 |
| 10 | Pateros | 4.96 | +1.26 | 9.96 |
| 11 | Paranaque | 4.35 | +0.57 | 9.55 |
| 12 | Muntinlupa | 3.77 | −0.74 | 7.55 |
| 13 | Malabon | 3.68 | −1.54 | 7.24 |
| 14 | San Juan | 2.41 | +0.76 | 7.09 |
| 15 | Pasay | 2.08 | −0.93 | 5.07 |
| 16 | Manila | 0.89 | +0.21 | 2.42 |
| 17 | Navotas | 0.47 | −0.40 | 0.92 |

ESA WorldCover v200 numbers run consistently higher than the NDVI mask because ESA class-10 includes mixed shrub-tree pixels while the NDVI 0.62 threshold (calibrated against Meta v2 canopy >5m) is stricter.

## Adjacent published estimates

| Source | Year | Method | NCR canopy |
|---|---|---|---|
| Meta v2 (canopy height > 5m) | 2018-20 | 1m AI canopy-height regression | 7.5% |
| ESA WorldCover v200 (class 10) | 2021 | 10m land cover classification | 13.38% |
| DENR FMB (cited in news / EJN) | 2024+ | not specified in public docs found | 6.0% |
| Global Forest Watch dashboard PHL/47 | 2020 baseline | Hansen 30m tree-cover ≥ 30% canopy | 4.0% |
| Earth Journalism Network | 2020 | DENR "open forest" sub-class | 2,071 ha |
| ScienceKonek 2024 map | 2024 | raster + methodology not publicly findable | unknown |

Definitions differ across sources (canopy fraction vs closed-canopy area, % vs hectares, single-epoch vs multi-year baseline). Listed for methodology context.

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

Hansen 30m misses sub-pixel clearings. Localised events appear in the global Hansen product only at the next release cadence.

## Per-barangay aggregation (892 OSM admin-level=10 polygons)

`data/per_barangay/per_barangay_canopy_2019_2026.csv` aggregates the v6 multi-year density rasters to OSM admin-level=10 polygons whose centroid falls inside one of the 17 NCR LGUs. 892 barangays covered (OSM admin-level=10 is more granular than PSA's 142 canonical barangays; many barangays are subdivided in OSM).

Top per-barangay 2026 canopy fraction:

| Barangay | LGU | total ha | v6 2026 |
|---|---|---|---|
| Forbes Park | Makati | 253 | 20.05% |
| Post Proper Southside | Taguig | 11 | 19.59% |
| Pansol | Quezon City | 172 | 18.98% |
| Urdaneta | Makati | 75 | 18.26% |
| UP Campus | Quezon City | 465 | 18.19% |
| Dasmariñas | Makati | 192 | 14.81% |
| Matandang Balara | Quezon City | 533 | 14.05% |
| Bagong Silangan | Quezon City | 408 | 13.96% |

The top hits are the well-known canopy-rich enclaves: Forbes Park (Makati gated forest), Post Proper Southside (BGC parks), UP Campus (Diliman), La Mesa-adjacent QC barangays. Bottom barangays are the small dense urban polygons in Manila and Pasay (Barangay 567, 568, 154, 82, 84) which round to 0% canopy.

GeoJSON for site overlay: `site/public/data/per_barangay_canopy.geojson`.

## Files

| Artifact | Description |
|---|---|
| `data/calibration_report.json` | NDVI v0 sweep against Meta v2 truth |
| `data/per_barangay/per_barangay_canopy_2019_2026.csv` | 892-barangay canopy series |
| `detection/train/dataset_v2.npz` | OSM bootstrap embeddings (5460 × 768) |
| `detection/train/dataset_v3.npz` | OSM + ESA teacher embeddings (9051 × 768) |
| `detection/train/dataset_v4.npz` | + Meta-oracle active learning (9933 × 768) |
| `detection/train/dataset_v6.npz` | 21,460 tile Meta-fraction regression targets |
| `detection/train/dataset_v9.npz` | 16,800 multi-epoch (loc, year) pairs |
| `detection/train/dataset_v10.npz` | 20,000 stratified 4×4 (120m) tiles |
| `detection/train/clf_v2..v10.joblib` | logistic / Platt / Ridge / GBR heads |
| `detection/train/clf_v8_per_lgu/*.joblib` | 12 per-LGU Platt sigmoids |
| `detection/scan/clf_v6_density_<year>.tif` | per-pixel canopy fraction raster, 8 years |
| `detection/scan/clf_v6_ncr_series.csv` | 8-year NCR canopy series |
| `detection/scan/clf_v6_per_lgu_series.csv` | 17-LGU × 8-year long format |
| `detection/scan/validation_v3/*.png` | per-LGU visual validation panels |

## Known limitations

- v3 labels are automatic (ESA WorldCover at 10m). A v4 with manual hard-negative spot-checks from scan false positives would lift precision further. SolarMap v4-v5 iteration applies.
- 240m tile spacing inherits a granularity floor; sub-tile canopy patches smaller than ~200m are below the model's resolution.
- v3 probabilities are not Platt-calibrated against the scan-distribution prior. Threshold sweep in `detection/scan/clf_v3_threshold_sweep_2024.json` shows the rank-ordering is clean even if the absolute probabilities aren't reliability-calibrated.
- Only the 2024 epoch was scanned for clf_v3 in this release. Multi-year v3 scan is queued.

## Reproducibility

```bash
pip install -r requirements.txt
make fetch              # GEE + AWS; ~30 min
make calibrate          # NDVI threshold tuned against Meta v2
make compute            # per-year canopy mask, per-LGU CSV
python3 detection/bootstrap/fetch_osm_tree_labels.py
python3 detection/buildings/fetch_tiles.py
python3 detection/train/build_dataset_v2.py
python3 detection/train/train_v2.py
python3 detection/train/build_dataset_v3.py
python3 detection/train/train_v3.py
python3 detection/scan/ncr_scan.py        # writes detection/scan/validation_v3/
make verify             # release gate
make hash               # sha256 of per_lgu_canopy_2019_2026.csv
```

## v9 multi-year NCR canopy series (deployed production)

v9 = multi-epoch GBR head (R²=0.879, per-year CV R² in [0.82, 0.91]). Per-year scans across 2019-2026 with 21,460 240m tiles each.

| Year | v9 NCR canopy % | v9 canopy ha | v6 % (legacy) |
|---|---|---|---|
| 2019 | 8.42% | 6,634 | 7.057% |
| 2020 | 9.30% | 7,328 | 8.001% |
| 2021 | 8.52% | 6,712 | 7.18% |
| 2022 | 8.46% | 6,666 | 6.978% |
| 2023 | 8.93% | 7,038 | 7.682% |
| 2024 | 8.54% | 6,727 | 7.761% |
| 2025 | 9.07% | 7,150 | 7.673% |
| 2026 | 8.40% | 6,617 | 7.365% |
