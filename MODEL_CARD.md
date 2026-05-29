# Leaves.PH Model Card

In optimization toward a first release.

## Intended use

Leaves.PH estimates per-tile canopy density for Metro Manila across the 17 NCR LGUs (16 cities plus the municipality of Pateros), built from canonical public satellite imagery and a CLIP + gradient-boosted regression model. It is **not** a per-household measurement, **not** a parcel-level land-use tool, and **not** a per-tree census.

## Inputs and training data

- Sentinel-2 L2A median composites (annual, cloud-masked via s2cloudless), used as the RGB source for tile embeddings.
- Meta AI Global Canopy Height v2 (1m wall-to-wall, canopy > 5m): the continuous regression target (canopy fraction per tile, 0..1).
- Supporting reference layers used during evaluation and cross-checks: ESA WorldCover v200 (10m class-10 tree mask), Hansen GFC v1.13 (loss-year band), Dynamic World v1 (trees probability).
- Training corpus: 16,800 tiles spanning 2019-2026, stratified across locations and epochs.

## Model architecture

A single model:

- **Embeddings:** CLIP ViT-Large/14 image embeddings computed per tile from Sentinel-2 RGB.
- **Head:** gradient-boosted regression (HistGradientBoostingRegressor) onto Meta's 1m canopy fraction (continuous, 0..1).

The published canopy figures (the map, per-LGU series, per-barangay series, and the headline NCR canopy percentage) come from the NDVI baseline (NDVI > 0.62) calibrated to Meta's 1m reference. The CLIP + gradient-boosted model is the detection model under optimization; the NDVI baseline is what backs the published numbers today.

## Evaluation

Held-out-location accuracy:

| Metric | Value |
|---|---|
| R² (held-out location) | 0.87 |
| MAE | 0.069 |

Protocol: 5-fold cross-validation grouped by location (leakage-free, train and test locations disjoint), n = 16,800 tiles across 2019-2026, evaluated against Meta AI Global Canopy Height v2 (1m, canopy > 5m). Grouping by location means a location seen in training is never scored in test, so the R² reflects generalization to unseen places rather than memorization.

## Known biases and limitations

- The Meta target is a fixed truth: Meta Canopy Height v2 source imagery is roughly 2019-vintage, so the calibration reference is a single point in time. The model estimates canopy fraction against that fixed truth; it is **not** a change-detection model.
- The model estimates canopy fraction per tile, not per tree. It learns neighborhood-level tree richness, not individual crowns.
- Sentinel-2 cloud masking removes many wet-season images in tropical monsoon zones, potentially under-representing canopy during June-September.
- Dynamic World probability values reflect model confidence, not ground truth.
- Hansen GFC v1.13 cannot distinguish plantation harvest from natural forest loss; 30m resolution misses small-scale urban tree-cutting events.
- The tile window is coarse relative to individual trees: sub-tile canopy patches smaller than the tile footprint are below the model's resolution.

## What this model does NOT do

- Does not allege specific permit violations or unpermitted cutting.
- Does not provide parcel-level or per-tree estimates.
- Does not perform change detection (the Meta target is a fixed reference, not a time series).
- Does not extrapolate beyond the published series window.

## Provenance, seeds, and hashes

Every artifact ships with a sha256 prefix. `data/per_lgu/per_lgu_canopy_2019_2026.csv` is the deterministic-build canonical (the Makefile asserts the hash). Model artifacts in `detection/train/` are deterministic given the same seed and the `requirements.txt` pins.

## Author and license

Xavier Puspus. MIT (code) + CC-BY-4.0 (data). See `LICENSE` and `CITATION.cff`.
