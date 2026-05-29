# Leaves.PH Model Card

Updated for the v6 release.

## Intended use

Leaves.PH publishes per-LGU annual canopy values for Metro Manila across the 17 NCR LGUs (16 cities plus the municipality of Pateros), built from canonical public satellite and a SolarMap-pattern CLIP+LR + Ridge head. It is **not** a per-household measurement, **not** a parcel-level land-use tool, and **not** a per-tree census.

## Pipeline overview

1. **Inputs:** Sentinel-2 L2A median composites (annual, cloud-masked via s2cloudless), Hansen GFC v1.13 loss-year band, ESA WorldCover v200 class-10 tree mask, Dynamic World v1 trees probability median per year, Meta Canopy Height v2 tile crop.
2. **v0 NDVI threshold:** tuned at 0.62 by F1-max sweep against Meta v2 height > 5m with recall floor 0.85.
3. **Per-LGU aggregation:** PSA admin boundaries for the 17 NCR LGUs; pixel-level canopy mask summed per polygon. Hash-pinned canonical CSV at `data/per_lgu/per_lgu_canopy_2019_2026.csv`.
4. **v2-v6 SolarMap-pattern head:** per-tile CLIP ViT-Large embeddings + LogisticRegression / Ridge layered on top of the NDVI baseline. Five iterations:
    - v2: OSM bootstrap (5,460 tiles), CV F1 = 0.69
    - v3: + ESA WorldCover 2021 teacher (3,591 tiles), CV F1 = 0.78
    - v4: + Meta v2 active-learning hard-negatives (882 tiles), CV F1 = 0.77 on harder distribution
    - v5: Platt sigmoid calibration over v4, max reliability bin gap = 0.055
    - v6: Ridge regression on Meta v2 >5m canopy fraction (continuous, 0..1), CV MAE = 0.047, R² = 0.71

## Known biases

- Meta Canopy Height v2 source imagery is 80% 2018-2020. The calibration layer is a ~2019 truth.
- Sentinel-2 cloud masking removes many wet-season images in tropical monsoon zones, potentially under-representing canopy during June-September.
- Dynamic World probability values reflect model confidence, not ground truth.
- Hansen GFC v1.13 cannot distinguish plantation harvest from natural forest loss.
- 30m Hansen resolution misses small-scale urban tree-cutting events.
- v6 Ridge regressor exhibits regression-to-the-mean bias at the high end of canopy fraction: true 0.85 predicted 0.55, true 0.97 predicted 0.68. Per-LGU v6 estimates compress toward the regional mean.
- CLIP training imagery was single-year (2024 S2 RGB). The model has not seen 2019/2020/2025/2026 imagery characteristics at training time. Multi-year scan applies the 2024-trained model to other epochs. CLIP embeddings are reasonably stable across S2 epochs but not guaranteed.
- 240m tile window is coarse. The classifier learns neighborhood-level tree-richness, not per-pixel canopy. Sub-tile canopy fraction would need a regression head at finer spatial resolution.

## Reported metrics

| Stage | Source | CV F1 (5-fold stratified) | Notes |
|---|---|---|---|
| v0 NDVI baseline | 10k Meta-truth samples | 0.512 | Per-pixel rule, precision 0.37 / recall 0.85 at t=0.62 |
| v2 CLIP+LR | 5,460 OSM tiles | 0.691 | Bootstrap labels |
| v3 CLIP+LR | 9,051 OSM + ESA | 0.784 | ESA teacher signal |
| v4 CLIP+LR | 9,933 + Meta-oracle mining | 0.772 | Active learning, harder eval distribution |
| v5 Platt | clf_v4 + sigmoid calibration | 0.771 | Reliability-calibrated probabilities |
| v6 Ridge regressor | 21,460 tile Meta-fraction | MAE 0.047 / R² 0.71 | Continuous canopy density |

NCR 2024 cross-check:
- v0 NDVI baseline: 7.78%
- v3 binary tile classifier: 7.36%
- v6 continuous regression: 7.73%

The three layers agree at NCR level within 0.5pp. Per-LGU they diverge because v6 compresses toward the regional mean (Ridge bias-to-mean).

## Sources of truth used in evaluation

- Meta Canopy Height v2 (1m wall-to-wall): calibration + active-learning oracle
- ESA WorldCover v200 2021 (independent 10m cross-check): teacher labels for v3
- 5-fold stratified CV on bootstrap + teacher labels
- Leave-one-LGU-out (LORO) for per-region honesty metrics (`detection/train/clf_v2_metrics.json`)
- Visual validation panels per LGU (`detection/scan/validation_v3/`)

## What this model does NOT do

- Does not allege specific permit violations or unpermitted cutting.
- Does not provide parcel-level or per-tree estimates.
- Does not extrapolate beyond the published series window.
- Is not Platt-calibrated PER-LGU (the v5 calibration is regional, not per-region).

## v7+ (documented next steps)

- Continuous regression with a non-linear head (gradient-boosted regressor) to correct v6's high-end bias-to-mean.
- Per-LGU Platt calibration with a held-out scan sample per region.
- Multi-year training imagery (per-epoch label augmentation).
- Finer tile windows (75-120m) for sub-tile canopy fraction.
- Active learning with human-in-the-loop spot-checks for the highest-disagreement tiles.

## Versioning and provenance

Every artifact ships with a sha256 prefix. `data/per_lgu/per_lgu_canopy_2019_2026.csv` is the deterministic-build canonical (Makefile asserts the hash). Model artefacts at `detection/train/clf_v2-v6.joblib` are deterministic given the same seed and `requirements.txt` pins.

## Author and license

Xavier Puspus. MIT (code) + CC-BY-4.0 (data). See `LICENSE` and `CITATION.cff`.
