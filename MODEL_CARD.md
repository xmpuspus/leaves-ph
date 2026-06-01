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

The published canopy figures (the map, per-LGU series, per-barangay series, and the headline NCR canopy percentage) come from the **human-calibrated classifier** described under Evaluation (10 features including Sentinel-2 spectral bands, trained on 656 manual high-resolution labels). The CLIP + gradient-boosted regression model below is a separate detection track under optimization; the NDVI > 0.62 rule is retained only as a comparison baseline.

## Evaluation

Held-out agreement with the Meta reference:

| Metric | Value |
|---|---|
| R² (location-grouped CV vs Meta) | 0.86 |
| R² (5×5 spatial-block CV vs Meta) | 0.83 |
| MAE | 0.053 |

Protocol: 5-fold cross-validation grouped by location, full v6+v9 union (n = 38,260), scored against Meta AI Global Canopy Height v2 (1m, canopy > 5m). Under strict grouping, a location's tiles (and its 8 yearly epochs) all held in one fold so neighbours and repeated places never straddle train/test, R² is 0.86 (location-grouped) to 0.83 (coarse 5×5 spatial blocks). An earlier published 0.879 used a non-grouped shuffled split that leaked adjacent tiles and repeated-location epochs; it is superseded. Honest numbers: `detection/train/clf_v9_metrics_honest.json`.

**What this number is and is not.** R² measures how well the model **reproduces Meta's 1m canopy fraction, which is its calibration target**, it is *not* accuracy against independent ground truth. For an independent check, the NDVI baseline was compared to ESA WorldCover v200 (a separate 10m land-cover product): 93% pixel agreement, IoU 0.52, F1 0.69 for 2021. Independent satellite products span 3% (Dynamic World) to 13% (ESA) for the same NCR/year; our estimate sits bracketed inside that envelope.

**Published canopy source = a human-calibrated model (replaces the NDVI baseline).** The published per-pixel canopy product is a gradient-boosted classifier over NDVI, Dynamic-World tree probability, Meta v2 1m canopy height, and the ESA tree class, trained on **656 manually labeled high-resolution pixels** (active-learning plus a 500-pixel uniform-random round). Its 10 features are NDVI, Dynamic-World tree probability, Meta 1m height, ESA-tree, and the raw Sentinel-2 spectral bands (red/nir/green/blue + GNDVI). Scored against those human labels under region-grouped out-of-fold CV with post-stratified population weighting, it reaches **precision 0.77, recall 0.79, F1 0.78, IoU 0.64**, beating the old NDVI > 0.62 baseline (F1 0.68, IoU 0.52; precision 95% CI 0.61–0.76) by +0.10 F1 / +0.12 IoU. The spectral bands let it reject high-NDVI grass/scrub the threshold over-called (precision 0.67→0.77) and it recovers diluted urban-fringe canopy; it removes the year-to-year sawtooth (NDVI swung 2.8pp; model holds a 9–10% band, threshold calibrated to the 10.1% human-truth). The spectral bands lifted F1 from 0.75 (four-feature) to 0.78; a CLIP ViT-L/14 embedding was tested and did not help, so it was dropped. The NDVI baseline is retained only for comparison. The Meta ≥5m target (the CLIP regression model's ceiling) scores precision 0.96 / recall 0.46 on the same labels. Method, gold labels, scripts, and the per-round build: `data/canopy_model/` (`RESULTS.md`, `master_labels.csv`, `model_comparison.json`); deployed product `pipeline/compute_canopy_model.py` + `data/canopy_model/`.

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
