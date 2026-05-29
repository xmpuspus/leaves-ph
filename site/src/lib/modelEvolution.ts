// Model-evolution record. Every number traces to a committed metrics JSON in
// detection/train/. Two tracks, because the task changed at v6:
//   - Classification (v2..v5): binary tree / not-tree per tile, scored by 5-fold CV F1.
//   - Regression  (v6..v9):   canopy fraction 0..1 per tile vs Meta's 1 m reference,
//                             scored by 5-fold CV R-squared.
// F1 and R-squared are different metrics on different tasks. They are NOT one curve.
// The deployed model is clf_v9; its headline number is the leakage-free held-out-
// location R-squared (5-fold GroupKFold by location), not the optimistic random-CV R.

export type Track = "classification" | "regression";

export interface ModelVersion {
  version: string;
  arch: string;
  task: string;
  track: Track;
  metricLabel: string; // "F1" or "R²"
  metric: number; // primary metric value (0..1)
  n: number; // training tiles
  note: string;
  source: string; // committed file
  deployed?: boolean;
}

export const MODEL_EVOLUTION: ModelVersion[] = [
  {
    version: "v2",
    arch: "CLIP ViT-L/14 + Logistic Regression",
    task: "binary tree / not-tree",
    track: "classification",
    metricLabel: "F1",
    metric: 0.691,
    n: 5460,
    note: "OSM-bootstrapped labels only.",
    source: "clf_v2_metrics.json",
  },
  {
    version: "v3",
    arch: "+ ESA WorldCover teacher",
    task: "binary tree / not-tree",
    track: "classification",
    metricLabel: "F1",
    metric: 0.784,
    n: 9051,
    note: "Adding the ESA teacher lifted F1 by 9.3 points.",
    source: "clf_v3_metrics.json",
  },
  {
    version: "v4",
    arch: "+ Meta-oracle active learning",
    task: "binary tree / not-tree",
    track: "classification",
    metricLabel: "F1",
    metric: 0.772,
    n: 9933,
    note: "Harder mined distribution; six-category active learning.",
    source: "clf_v4_metrics.json",
  },
  {
    version: "v5",
    arch: "+ Platt calibration",
    task: "binary, probability-calibrated",
    track: "classification",
    metricLabel: "F1",
    metric: 0.771,
    n: 9933,
    note: "Reliability-calibrated; max bin gap 0.055.",
    source: "clf_v5_metrics.json",
  },
  {
    version: "v6",
    arch: "CLIP ViT-L/14 + Ridge",
    task: "canopy fraction 0..1",
    track: "regression",
    metricLabel: "R²",
    metric: 0.709,
    n: 21460,
    note: "Task pivot: continuous canopy density vs Meta's 1 m reference.",
    source: "clf_v6_metrics.json",
  },
  {
    version: "v7",
    arch: "+ gradient boosting (HistGBR)",
    task: "canopy fraction 0..1",
    track: "regression",
    metricLabel: "R²",
    metric: 0.781,
    n: 21460,
    note: "MAE 0.038 on the single-epoch set.",
    source: "clf_v7_metrics.json",
  },
  {
    version: "v9",
    arch: "+ multi-epoch training (2019–2026)",
    task: "canopy fraction 0..1",
    track: "regression",
    metricLabel: "R²",
    metric: 0.867,
    n: 16800,
    note: "Held-out-location R² 0.87 (leakage-free GroupKFold). Deployed.",
    source: "clf_v9_metrics.json + held-out re-eval",
    deployed: true,
  },
];

// Headline, leakage-free. See tmp/phase1-audit/v9_grouped_cv_result.json.
export const HEADLINE_R2 = 0.87;
export const HEADLINE_R2_EXACT = 0.8667;
export const HEADLINE_MAE = 0.069;
export const HEADLINE_N = 16800;
export const HEADLINE_REFERENCE =
  "Meta AI / Land & Carbon Lab Global Canopy Height v2 (1 m, canopy > 5 m)";

// Classifier gain that is fair to quote as one number (same task, same metric).
export const F1_V2 = 0.691;
export const F1_V3 = 0.784;

// Resolution probes (different tile sizes; shown as context, not on the main track).
export const RESOLUTION_PROBES = [
  { version: "v10", scale: "120 m tiles", r2: 0.783, n: 20000, source: "clf_v10_metrics.json" },
  { version: "v11", scale: "10 m Sentinel-2 tiles", r2: 0.526, n: 729, source: "clf_v11_metrics.json" },
];
