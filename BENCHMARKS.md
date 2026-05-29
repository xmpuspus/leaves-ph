# Benchmarks

In optimization toward a first release.

## Methodology overview

Three stages produce the published numbers and the detection model:

1. **NDVI baseline (published numbers).** Per-pixel rule `NDVI > 0.62` on Sentinel-2 surface reflectance, calibrated to Meta's 1m canopy-height reference. The threshold was chosen by F1-max sweep against Meta v2 canopy heights > 5m with a recall floor of 0.85. This baseline backs the map, the per-LGU series, the per-barangay series, and the headline NCR canopy percentage.

2. **Detection model (in optimization).** CLIP ViT-Large/14 image embeddings per Sentinel-2 RGB tile, with a gradient-boosted regression head (HistGradientBoostingRegressor) onto Meta's 1m canopy fraction (continuous, 0..1). This is the model under active optimization toward a first release.

3. **Held-out evaluation.** 5-fold cross-validation grouped by location (train and test locations disjoint, leakage-free), n = 16,800 tiles across 2019-2026, scored against Meta AI Global Canopy Height v2 (1m, canopy > 5m).

## Best-model benchmark

| Metric | Value |
|---|---|
| R² (held-out location) | 0.87 |
| MAE | 0.069 |

The model is evaluated with location-grouped cross-validation: a location used in training never appears in test, so the R² measures generalization to unseen places, not memorization. The target is Meta v2 canopy fraction (canopy > 5m) per tile.

## NCR area-weighted canopy series

Annual epochs 2019-2026, NDVI baseline pipeline (NDVI > 0.62, calibrated to Meta v2).

| Year | NCR canopy % | Canopy hectares | Notes |
|---|---|---|---|
| 2019 | 8.08 | 6,325 | first full-NCR year of S2 L2A PH coverage |
| 2020 | 9.88 | 7,737 | |
| 2021 | 9.79 | 7,665 | ESA WorldCover v200 cross-check: 13.38% area-weighted |
| 2022 | 9.99 | 7,818 | |
| 2023 | 10.24 | 8,013 | 8-year peak |
| 2024 | 7.76 | 6,076 | |
| 2025 | 9.88 | 7,733 | |
| 2026 | 7.46 | 5,840 | most recent measurement, provisional (imagery Jan-May 2026) |

2018 has only ~24% NCR coverage (S2 L2A PH coverage was thin that early) and is excluded from the published series. Source-image counts per year are recorded in the Sentinel-2 fetch manifest under `data/composites/`.

The 8-year shift from 2019 to 2026 is -0.62 pp. The 2026 value is provisional because the year's imagery only covers January through May.

## Per-LGU 2026 baseline ranking (NDVI)

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

ESA WorldCover v200 numbers run consistently higher than the NDVI mask because ESA class-10 includes mixed shrub-tree pixels while the NDVI 0.62 threshold (calibrated against Meta v2 canopy > 5m) is stricter.

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
