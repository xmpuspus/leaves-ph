# Manual high-resolution labeling: reality-anchored accuracy (Claim 3 gold truth)

Done 2026-05-29. The first accuracy number for Leaves.PH measured against
**human visual labels on high-resolution imagery**, not against another satellite
product. Replaces "agreement with ESA WorldCover" as the headline accuracy.

## What was done

- **Sample.** 42 30m pixels inside the 17-LGU mask, drawn (seed 42) across **6
  disjoint strata** that partition the 904,715 valid pixels, so the sample is
  population-weightable (Horvitz-Thompson) and both predicted classes are present:

  | Stratum | Definition | Pop pixels | Pop % | Sampled |
  |---|---|---|---|---|
  | D clear-canopy | NDVI > 0.65 | 77,845 | 8.6% | 10 |
  | C boundary | NDVI in [0.55, 0.65] | 37,953 | 4.2% | 10 |
  | A dense-urban | ESA built-up & NDVI < 0.55 | 475,429 | 52.6% | 6 |
  | B reclaimed | ESA bare & NDVI < 0.55 | 6,209 | 0.7% | 6 |
  | E green-fringe | ESA tree & NDVI < 0.55 | 32,660 | 3.6% | 6 |
  | F other-low | other ESA & NDVI < 0.55 | 274,619 | 30.4% | 4 |

- **Reference imagery.** Esri World Imagery (~0.5–1m, no-auth ArcGIS export) per
  chip, bbox = target 30m cell ± 3.5 cells (~210m), with a red box drawn on the
  **exact** 30m target cell. Sentinel-2 RGB crop (`s2_rgb_2021.tif`) as a second
  view. Ambiguous cells re-inspected at 2.3× and 3.4× zoom.
- **Labeling.** Each chip labeled by Claude via visual inspection (read the
  annotated chip, decide "is ≥25% of the marked 30m cell woody **tree** canopy?").
  Labels + one-line reasons in `my_labels.csv`; chips in `chips/`, zooms in `zoom/`,
  ultra-zooms in `uz/`, contact sheet `contact_sheet.png`.

## Headline result: NDVI > 0.62 mask vs manual labels

Confusion (n=42): **TP 10, FP 3, FN 5, TN 24.**

| Metric | Pooled (stratified sample) | Population-weighted (H-T) |
|---|---|---|
| Precision | 0.77 (95% CI 0.50–0.92) | **0.78** (95% CI 0.54–1.0) |
| Recall | 0.67 (95% CI 0.42–0.85) | **0.73** (95% CI 0.61–0.88) |
| F1 | 0.71 | **0.76** |
| IoU | 0.56 | **0.61** |
| Accuracy | 0.81 | 0.95 |

- **Implied true canopy fraction = 10.5%**, against the mask's 9.86%, the
  reality-anchored canopy area lands within ~0.7pp of the published 9.79% estimate.
- Dropping the 5 cells Claude flagged ambiguous (n=37): precision 0.86, recall 0.83,
  IoU 0.73 (population-weighted precision 0.86, recall 0.83).

### Where the errors live (matches the prior ESA-gap analysis)

- **3 false positives, all high-NDVI non-tree vegetation:** riparian scrub on a
  gravel bar (#0), a dense grass/low-veg slope (#6), a dry-grass field with a green
  edge (#12). Exactly the "we over-call dense grass/scrub" failure the threshold
  analysis predicted.
- **5 false negatives, all real canopy the strict 0.62 cut or 30m mixing misses:**
  a tall-canopy cell at NDVI 0.619 just under the cut (#13, Meta 11m), and four
  ESA-tree green-fringe cells (#32/33/35/37) where sub-5m or sparse street/yard trees
  dilute the 30m NDVI below threshold.
- Per-stratum: dense-urban (A), reclaimed (B) and water/other (F) are 100% correctly
  negative; all recall loss is concentrated in the green-fringe (E) stratum.

## Detection-model ceiling: Meta height ≥ 5m vs manual labels

The detection model (CLIP + gradient-boosted regression) is trained to **reproduce
Meta's 1m canopy fraction**, so the Meta target is its accuracy ceiling. Meta height
≥ 5m as a classifier vs the same manual labels:

| Metric | Pooled | Population-weighted |
|---|---|---|
| Precision | 1.00 (95% CI 0.68–1.0) | 1.00 |
| Recall | 0.53 (95% CI 0.30–0.75) | 0.59 (95% CI 0.34–0.81) |
| F1 / IoU | 0.70 / 0.53 | 0.74 / 0.59 |

Meta never false-positives in this sample (every Meta ≥ 5m cell is real canopy by
eye) but recovers only ~59% of canopy and implies just 6.2% canopy vs the 10.5%
truth, it misses sub-5m and sparse urban trees. The NDVI mask trades some precision
(0.78 vs 1.00) for much higher recall (0.73 vs 0.59); the two are complementary, and
the model, reproducing Meta at R² 0.83–0.86, inherits Meta's high-precision /
moderate-recall profile.

## Honest caveats

- n=42 manual labels → wide CIs; this is a defensible first reality-anchored number,
  not a definitive accuracy. Single labeler (Claude), no second-rater κ.
- "Canopy" = ≥25% of the 30m cell is woody tree canopy by eye on ~0.6m imagery dated
  near (not exactly) 2021; canopy moves slowly so ±1–2yr basemap drift is minor.
- Population-weighting leans on small per-stratum n (A=6, F=4 carry large weights);
  those strata are unambiguous (roofs / bare / water), so their TN weight is stable,
  but the weighted recall depends on the 6 green-fringe chips.

## Files

`sample_metadata.csv` · `my_labels.csv` · `accuracy_results.json` ·
`strata_pop.json` · `contact_sheet.png` · `chips/` `zoom/` `uz/` `s2crops/` ·
scripts `sample_chips.py` `build_composites.py` `zoom.py` `uz.py` `uz2.py`
`compute_accuracy.py` `build_contact_sheet.py`.
