export const SERIES_START = 2019;
export const SERIES_END = 2026;

export const SERIES_YEARS: number[] = Array.from(
  { length: SERIES_END - SERIES_START + 1 },
  (_, i) => SERIES_START + i,
);

export const SERIES_RANGE = `${SERIES_START}–${SERIES_END}`;
export const SERIES_EPOCH_COUNT = SERIES_YEARS.length;
export const LATEST = SERIES_END;

export const LATEST_NCR_PCT = 7.46;
export const LATEST_NCR_CANOPY_HA = 4_954;
export const LATEST_NCR_TOTAL_HA = 66_407;
export const NCR_LGU_COUNT = 17;
export const NCR_BARANGAY_COUNT = 892;

export const DELTA_START_TO_LATEST_PP = -0.62;

// Per-year NCR area-weighted canopy %, 2019..2026.
// v0 = NDVI pixel rule (the displayed series); area-weighted from
//   site/public/data/per_lgu_canopy.geojson (canopy_<year>_ha / total_ha).
//   2026 = 7.46% and Δ2019->2026 = -0.62 pp both reconcile with the scalars above.
// SERIES_NCR_V9 = the detection model's canopy-density series; source
//   detection/scan/clf_v9_ncr_series.csv.
// The v0 pixel rule swings year to year with imagery (cloud masks, sun angle,
// seasonal phenology); the detection model recovers a steadier signal. 2026 is provisional
// (imagery Jan-May only).
export const SERIES_NCR_V0: number[] = [8.08, 9.88, 9.79, 9.99, 10.24, 7.76, 9.88, 7.46];
export const SERIES_NCR_V9: number[] = [8.42, 9.30, 8.52, 8.46, 8.93, 8.54, 9.07, 8.40];

// Current detection model (CLIP ViT-L/14 + gradient-boosted regression to Meta's
// 1 m canopy fraction). In optimization toward a first release. Accuracy is the
// leakage-free held-out-location score (5-fold GroupKFold by location), n=16,800,
// from tmp/phase1-audit/v9_grouped_cv_result.json.
export const MODEL_R2 = 0.87;
export const MODEL_MAE = 0.069;
export const MODEL_REFERENCE = "Meta AI Global Canopy Height v2 (1 m, canopy > 5 m)";
