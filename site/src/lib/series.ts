export const SERIES_START = 2019;
export const SERIES_END = 2026;

export const SERIES_YEARS: number[] = Array.from(
  { length: SERIES_END - SERIES_START + 1 },
  (_, i) => SERIES_START + i,
);

export const SERIES_RANGE = `${SERIES_START}–${SERIES_END}`;
export const SERIES_EPOCH_COUNT = SERIES_YEARS.length;
export const LATEST = SERIES_END;

// Published headline = the human-calibrated canopy model (see below), 2026.
export const LATEST_NCR_PCT = 8.82;
export const LATEST_NCR_CANOPY_HA = 5_857;
export const LATEST_NCR_TOTAL_HA = 66_407;
export const NCR_LGU_COUNT = 17;
export const NCR_BARANGAY_COUNT = 892;

export const DELTA_START_TO_LATEST_PP = 0.01;

// PUBLISHED canopy source = a human-calibrated classifier (gradient-boosted) over 10
// per-pixel features: NDVI, Dynamic-World tree-prob, Meta 1 m canopy height, ESA-tree,
// and the raw Sentinel-2 spectral bands (red/nir/green/blue + GNDVI). Trained on 656
// manually labeled high-resolution pixels (active learning + a 500-pixel random round).
// Against those human labels it scores F1 0.78 / IoU 0.64, vs the old NDVI>0.62
// baseline's F1 0.68 / IoU 0.52. It drives the map, the per-LGU and per-barangay
// series, and the headline number. Per-year area-weighted from
// site/public/data/per_lgu_canopy.geojson; the threshold is calibrated so 2021 matches
// the 10.1% human-truth canopy. SERIES_NCR_NDVI is the old NDVI-threshold baseline,
// kept only for the comparison chart: it swings ~2.8 pp year to year (an imagery/
// threshold-crossing artifact); the calibrated model holds a steady ~9-10% snapshot.
// 2026 is provisional (imagery Jan-May only).
export const SERIES_NCR_PUBLISHED: number[] = [8.81, 9.74, 10.11, 10.00, 10.02, 9.15, 9.99, 8.82];
export const SERIES_NCR_NDVI: number[] = [8.08, 9.88, 9.79, 9.99, 10.24, 7.76, 9.88, 7.46];

// Accuracy of the published model vs manual high-resolution gold labels (n = 656,
// region-grouped out-of-fold CV, post-stratified population weighting). A 500-pixel
// random round tightened the precision 95% CI to ~0.61-0.76. Feature experiments:
// adding the raw S2 spectral bands lifted F1 0.75->0.78 (precision +0.10, rejecting
// grass); a CLIP ViT-L/14 embedding did NOT help (0.73) and was dropped.
export const CANOPY_MODEL_F1 = 0.78;
export const CANOPY_MODEL_IOU = 0.64;
export const CANOPY_MODEL_PRECISION = 0.77;
export const CANOPY_MODEL_RECALL = 0.79;
export const BASELINE_NDVI_F1 = 0.68;
export const BASELINE_NDVI_IOU = 0.52;
export const GOLD_LABEL_N = 656;

// Separate research track: a CLIP ViT-L/14 + gradient-boosted regression head that
// predicts Meta's 1 m canopy fraction (R2 below = location-grouped 5-fold CV vs Meta,
// the calibration target, not ground truth; spatial-block grouping gives 0.83). Used
// in the capabilities demo and per-LGU validation panels; not the published source.
// Source: detection/train/clf_v9_metrics.json (cv5 = 0.858; cv5_spatialblock_5x5 = 0.826).
export const MODEL_R2 = 0.86;
export const MODEL_MAE = 0.053;
export const MODEL_REFERENCE = "Meta AI Global Canopy Height v2 (1 m, canopy > 5 m)";
