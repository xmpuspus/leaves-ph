# Leaves.PH Hardening Plan

Adversarial defensibility audit, 2026-05-29. Five claims adjudicated against the
actual data and code, not against the docs. Evidence files:
`tmp/defensibility-20260529T043825Z/claim-{1..5}.md` plus the raw scripts,
stdout, and CSVs alongside them. Every number below is reproducible from those
scripts with `python3.12`.

Verdict key: **VERIFIED** (claim holds) / **FIXABLE-WITH-WORK** (claim becomes
true after a concrete fix) / **MUST-SOFTEN** (claim as written is not supported
and copy must change now).

---

## Claims that must change (lead with these)

### Claim 1 — "R² 0.87 is leakage-free, 5-fold CV grouped by location, spatially disjoint tiles"
**Verdict: MUST-SOFTEN (the "leakage-free / spatially disjoint" part is false). The fix is FIXABLE-WITH-WORK and is now done.**

Nuance found during the fix: there are *two* 0.87-ish numbers. The shipped
`clf_v9_metrics.json` reports R² 0.879 from a non-grouped shuffled split (leaky).
The site's `MODEL_R2 = 0.87` constant came from a *separate* prior audit
(`tmp/phase1-audit/v9_grouped_cv.py`) that genuinely ran `GroupKFold` by location
on the v9 set and got 0.8667. So "grouped by location" was *true* for the site
figure. What was false is **"leakage-free / spatially disjoint tiles"**:
location-grouping does NOT separate adjacent 240m tiles (two neighbouring tiles at
different locations still split across folds), and it was computed on v9-alone, not
the full union. Under the stricter spatial-block CV that does separate neighbours,
R² drops to 0.83. The model genuinely learns; the overclaim is the "leakage-free /
disjoint tiles" wording, which appears in the docs.

Evidence:
- `detection/train/train_v9_multiepoch.py:64` uses
  `KFold(n_splits=5, shuffle=True, random_state=42)`. Plain **shuffled** KFold.
  Not `GroupKFold`. The `loc` array is loaded from `dataset_v9.npz` but is never
  passed to any splitter (zero grep hits for a group argument).
- Two leakage channels, both confirmed on the data:
  - **Same-location-different-year target leakage.** `build_dataset_v9_multiepoch.py:159`
    copies one Meta snapshot target to all 8 yearly rows of a location
    (`y_targets[k] = tile_meta[loc_i]`). The audit confirmed all 2,100 location
    groups have target std < 1e-9 across their 8 years. Shuffled KFold puts ~7/8
    of each location's identical (embedding≈, target=) rows in train and the rest
    in test.
  - **Adjacent / duplicate-tile leakage.** `dataset_v6` (21,460 tiles, all 2024,
    the full 185×116 grid) and `dataset_v9` (a 2,100-location subset of the same
    grid) share locations and neighbouring 240m tiles; shuffled KFold scatters
    neighbours across folds.
- Honest recomputation with the same estimator (HistGradientBoostingRegressor,
  same hyperparameters), full v6+v9 union (n = 38,260), in
  `detection/train/clf_v9_metrics_honest.json`:

  | Split | MAE | RMSE | R² |
  |---|---|---|---|
  | Published: shuffled KFold (`clf_v9_metrics.json`) | 0.048 | 0.083 | **0.879** |
  | **Honest: GroupKFold by location** | 0.053 | 0.090 | **0.86** |
  | **Honest: 8×8 spatial-block GroupKFold** | 0.056 | 0.097 | **0.84** |
  | **Honest: 5×5 spatial-block GroupKFold** | 0.057 | 0.100 | **0.83** |

  Leakage inflation on the union: −0.02 (location-grouped) to −0.05 (spatial-block,
  which controls adjacent-tile leakage the published number did not). The model is
  not a memorization artifact; the headline drops only from 0.879 to 0.83–0.86.
  v6's full-grid row order maps deterministically to grid cells (185×116 = 21,460 =
  v6 row count), so this union recompute is reproducible from shipped artifacts.

The fix:
1. Re-run training with `GroupKFold` (groups = spatial block, so neighbouring
   tiles and a location's 8 epochs share a fold). v6's row index maps
   deterministically to a grid cell (v6 is the full grid in order), so a
   full-union grouped CV is achievable. ~30 min.
2. Regenerate `clf_v9_metrics.json` with the honest number so the artifact and
   the docs cannot drift.
3. Replace the label in all 7 files (list below) with the honest number and an
   explicit "reproduces Meta, not ground truth" qualifier (see Claim 3).

Files carrying the false label (fix every one):
`MODEL_CARD.md:34`, `BENCHMARKS.md:13` & `:22`, `README.md:18`,
`site/src/pages/methodology.astro:52`, `docs/launch/linkedin-post.md:11,28`,
`docs/launch/press-one-pager.md:15`, `docs/launch/facebook-post.md:21`.

---

### Claim 2 — "The 2019-2026 canopy series is real canopy change"
**Verdict: MUST-SOFTEN. It is a composite-greenness / threshold-crossing artifact, not change.**

Evidence:
- Not a coverage artifact: `_canopy_manifest.json` `nodata_pixels` is 154–1,173
  every year 2019-2026; valid pixels (canopy + non_canopy) are constant at
  ~1.379M. So the sawtooth is pixels crossing the fixed NDVI 0.62 line, not
  missing data.
- Image count only weakly explains it (Pearson r ≈ +0.51); 2024 dipped hard with
  178 source scenes while 2022 peaked on 162.
- Decisive test on the actual `s2_YYYY.tif` rasters: in dip years (2024, 2026)
  the NDVI upper tail shifts left across 0.62 — the 0.62–0.70 band collapses
  (4.40% in 2023 → 3.87% in 2024 → 3.41% in 2026) and the 90th-percentile NDVI
  drops from ~0.705 to 0.644/0.624. A small global greenness drop in each year's
  median composite pushes a large near-threshold mass below the cut.
- Rank-normalizing each year to a common reference percentile flattens the 4.52pp
  sawtooth to ~0.0pp; z-score normalization cuts it ~60%. (Normalized series:
  `tmp/defensibility-20260529T043825Z/claim2_normalized_series.csv`.)

The fix (cheap, executed inline): present a single pooled cross-sectional estimate
(~8–10% area-weighted) with a per-year ±2pp sensitivity band, OR the rank-normalized
flat series. Drop "8-year peak" (BENCHMARKS.md:34) and the "−0.62pp 8-year shift"
trend sentence (BENCHMARKS.md:41). The per-LGU "steepest decliners" language
(index.astro, MapView.astro, launch posts) inherits the same artifact and must be
reframed or dropped. MODEL_CARD already says "not a change-detection model" — good;
the series presentation just needs to match that.

---

### Claim 3 — "R² 0.87 = accuracy"
**Verdict: MUST-SOFTEN the framing. A real non-Meta accuracy number is FIXABLE-WITH-WORK and partially delivered now.**

R² 0.87 measures reproduction of Meta, which is BOTH the NDVI calibration target
AND the held-out scoring target. It is not accuracy against reality.

Evidence (first real non-Meta numbers, ESA WorldCover v200 class-10 and Dynamic
World reprojected to our 30m 2021 grid, clipped to the 17-LGU mask, 904,715 valid
pixels):
- Against ESA WorldCover: **IoU 0.52, F1 0.69, precision 0.81, recall 0.59,
  92.7% pixel agreement** — moderate, not 0.87.
- The two independent references disagree with each other worse (ESA vs DW IoU
  0.22) than ours does with ESA. The products span 4.5× for the same year/place:
  DW 2.97% · Hansen 4.0% · DENR 6.0% · Meta 7.5% · ours 9.79% · ESA 13.36%.
  There is no single satellite truth; our 9.79% sits bracketed inside the envelope.
- The 13.38-vs-9.79 ESA gap is entirely threshold strictness: NDVI ≥ 0.54
  reproduces ESA's 13.36% (sweep in `ndvi_threshold_sweep.csv`); 100% of pixels
  ESA calls tree that we miss have median NDVI 0.508 (just below our Meta-→5m
  cut). ESA's 10m classifier rounds up sparse street trees that our stricter
  threshold drops.

The fix:
- Now: state R² 0.87 (→0.85 honest, Claim 1) as "agreement with Meta, our
  calibration target," and cite the ESA cross-check (IoU 0.52 / F1 0.69) as the
  first independent accuracy number.
- Next (scoped, ~1.5 days): manual high-resolution labeling of a stratified
  ~30-tile / ~300–500-point sample (dense-urban / reclaimed / green-fringe +
  boundary oversample). Spec in `claim-3.md`. This produces the first
  reality-anchored precision/recall/IoU.

---

### Claim 4 — "123,169 new crowns surfaced by the model"
**Verdict: MUST-SOFTEN. Two defects: provenance and precision.**

Evidence:
- **Provenance.** The 123,169 "new" crowns are NOT model detections. They are
  connected components of Meta's 1m canopy-height mask (≥5m, p95 ≥ 8m, no OSM
  tag), produced by `pipeline/extract_tree_crowns.py:105` and tagged by
  `pipeline/tag_tree_crowns_status.py`. Verified directly: 242,810 crowns total,
  new = 123,169 (50.7%), OSM-confirmed = 8,824 (3.6%). The CLIP detection model,
  its deploy threshold, and the >100% over-detection scan artifact play zero role
  in this count.
- The live map (`MapView.astro`: "tall canopy ≥ 8m, Meta-derived") and the README
  (`README.md:38,45,99`: "connected components of Meta's 1m canopy-height mask …
  not from individual tree detections") are **already honest**. The only false
  copy is the demo GIF footer: `animation/generate_known_vs_predicted.py:297`
  ("model-surfaced crowns") and the line-94 comment.
- **Precision.** A 40-crown sample stratified across the 17 LGUs (seed 4242):
  the Meta-height proxy "validates" 100% but is circular (every new crown is
  Meta ≥ 8m by definition). Independent corroboration — a Sentinel-2 NDVI ≥ 0.62
  OR Dynamic-World tree-prob ≥ 0.20 signal at the centroid — is **12.5% (5/40),
  Wilson 95% CI [5.5%, 26.1%]**. This is a lower bound on corroboration (the 30m
  S2 grid drowns ~16–100 m² crowns in mixed road/roof pixels), not an upper bound
  on false positives.

The fix (cheap, executed inline): fix the GIF footer. Replace "model-surfaced
crowns N" with "Meta-derived crowns OSM doesn't record." Everywhere the project
discusses crowns, say "Meta-derived canopy-crown polygons; 'new' = absent from
OSM, not verified as a tree."

---

## Claim that is already true (keep, with a label fix)

### Claim 5 — "NDVI > 0.62 = tree cover"
**Verdict: VERIFIED conflation. The "tree cover" label must soften; the measurement is sound as a vegetation proxy.**

Evidence:
- Pixel computation (`canopy_2021.tif` vs Meta height, reprojected to the mask
  grid, clipped to the 17 LGUs, 88,597 fired pixels): **55.2% of NDVI-fired area
  sits on Meta height < 5m** — dense low vegetation, not tree canopy by the
  project's own > 5m definition. Pixel precision 44.8%; median Meta height under a
  "tree cover" pixel is 4.14m; 27.5% of fired pixels are on ground Meta reads as
  < 1m.
- Reconciles with `data/calibration_report.json`: precision@0.62 = 0.3653 →
  implied conflation 63.5%. The ~8pt gap is the calibration's full-bbox random
  sample (incl. bay water) vs the audit's clip to actual LGU land. Both land in
  the 55–64% range. The conflation is designed-in: an F1-optimal threshold chosen
  at ~0.37 precision to hold recall ≥ 0.85.
- Per-LGU: Quezon City is the only place the mask is mostly right (68.6%
  precision — real La Mesa / Diliman canopy) and it dominates the pixel count,
  dragging the NCR average up. The other 16 LGUs run 60–91% conflation, worst in
  reclaimed/coastal Malabon (90.8%), Valenzuela (89.7%), Taguig (86.5%). Concrete
  example: the Villamor / Manila Golf belt fires NDVI on 64% of the window at 4.4m
  mean height — golf turf labeled as tree cover.

The fix (cheap, executed inline): relabel. The honest term is "dense vegetation
cover (NDVI > 0.62 proxy, calibrated to tree canopy > 5m; ~45% of flagged area is
verified > 5m tree canopy, the rest is grass / turf / scrub)." Keep the project
name Leaves.PH, but never present the NDVI layer as bare "tree cover" without
the precision caveat.

---

## Corrected copy block (drop-in for the canonical docs, site, and GIF)

**Model / accuracy line** (replaces every "R² 0.87 … grouped by location, leakage-free"):

> The detection model (CLIP ViT-Large/14 embeddings + gradient-boosted regression
> onto Meta's 1m canopy fraction) reaches **R² 0.83–0.86 under grouped 5-fold
> cross-validation** (0.86 location-grouped, 0.83 under coarse spatial blocks that
> also separate adjacent tiles; MAE 0.053, n = 38,260). This measures how well it
> **reproduces Meta's 1m canopy fraction, its calibration target, not accuracy
> against independent ground truth.** Against ESA WorldCover v200, a fully
> independent product, the underlying NDVI mask agrees on 93% of pixels (IoU 0.52,
> F1 0.69). A shipped 0.879 figure used a non-grouped shuffled split and is
> superseded.

**Canopy figure / series line** (replaces "8-year peak", "−0.62pp", "steepest decliners as change"):

> Metro Manila canopy is estimated at roughly **8–10% area-weighted** (NDVI ≥ 0.62
> on annual Sentinel-2 median composites, calibrated to Meta v2). The 2019-2026
> values are a **per-year cross-sectional snapshot, not a change series**:
> year-to-year swings of ~2pp are driven by greenness shifts in each year's median
> composite crossing the fixed NDVI threshold, not by canopy gain or loss
> (rank-normalizing for composite greenness removes the swing almost entirely).
> 2026 is provisional (Jan–May imagery, 104 vs ~190 source scenes).

**Canopy label** (replaces bare "tree cover"):

> Dense vegetation cover (NDVI > 0.62 proxy, calibrated to Meta tree canopy > 5m;
> about half of flagged area is verified > 5m tree canopy, the rest is dense low
> vegetation — grass, turf, scrub). Not a pure tree-canopy measure.

**Crowns line** (replaces "model-surfaced crowns"):

> 242,810 Meta-derived canopy-crown polygons (connected components of Meta's 1m
> canopy-height mask, not model detections). 8,824 (3.6%) are OSM-corroborated;
> 123,169 (50.7%) are tall canopy (p95 ≥ 8m) that OSM does not yet record. "New"
> means absent from OSM, not verified as an individual tree.

**GIF footer** (replaces `generate_known_vs_predicted.py:297`):

> "Meta-derived crowns OSM doesn't record  {n_new:,}"  (was "model-surfaced crowns")

---

## Effort summary

| # | Claim | Verdict | Fix | Effort |
|---|---|---|---|---|
| 1 | "leakage-free / disjoint tiles" label | MUST-SOFTEN | Honest GroupKFold computed (`clf_v9_metrics_honest.json`); 0.87→0.83–0.86; fixed 9 files | Done |
| 2 | Series = change | MUST-SOFTEN | Cross-sectional reframe + normalized series | Copy (done inline) |
| 3 | R² = accuracy | MUST-SOFTEN / FIXABLE | ESA cross-check now; manual label next | ~1.5 days for gold truth |
| 4 | 123,169 model crowns | MUST-SOFTEN | Fix GIF footer; crowns wording | Trivial (done inline) |
| 5 | NDVI = tree cover | VERIFIED conflation | Relabel "dense vegetation proxy" | Copy (done inline) |

**Executed inline this session (verified, 40/40 e2e pass after changes):**
- Claim 1: honest full-union GroupKFold computed → `detection/train/clf_v9_metrics_honest.json`
  (0.879 shuffled → 0.86 location-grouped → 0.83 spatial-block). R² and the
  "leakage-free / disjoint" wording corrected in `MODEL_CARD.md`, `BENCHMARKS.md`,
  `README.md`, `site/src/lib/series.ts` (`MODEL_R2` 0.87→0.86), `site/src/pages/index.astro`
  (hero + caption), `methodology.astro`, `validation.astro`, and the 3 `docs/launch/*`
  posts. e2e tests T01/T23 updated to the new values.
- Claim 2: BENCHMARKS series reframed as cross-sectional + threshold-crossing caveat,
  "8-year peak" / "−0.62pp" trend language removed; per-LGU "decliner" language
  reframed as snapshot differences in `index.astro`, `MapView.astro`, and launch
  posts. Normalized series in `tmp/.../claim2_normalized_series.csv`.
- Claim 3: ESA non-Meta accuracy (IoU 0.52 / F1 0.69, 93% agreement) added to
  `MODEL_CARD.md`, `BENCHMARKS.md`, `README.md`, `methodology.astro`.
- Claim 4: GIF footer + comments fixed (`generate_known_vs_predicted.py`): "model-surfaced
  crowns" → "tall canopy, no OSM tag"; "the model finds canopy the reference leaves
  blank" removed; the `validation.astro` provenance drift (model "trained on labelled
  tiles / OSM+ESA teacher") corrected to "regression onto Meta's 1m canopy fraction".
- Claim 5: "tree cover" relabeled to "dense vegetation (NDVI proxy), ~half verified
  >5m canopy" in `index.astro`, `README.md`.

**Scoped next steps — DONE 2026-05-29 (follow-up session):**
- (a) **Manual high-resolution labeling — DONE.** 42 30m pixels across 6 disjoint
  strata (seed 42), labeled by visual inspection of ~0.5-1m Esri World Imagery. NDVI>0.62
  mask vs human labels: **precision 0.78, recall 0.73, IoU 0.61, F1 0.76** (population-
  weighted; pooled 0.77/0.67/0.56/0.71); implied true canopy 10.5% vs published 9.79%.
  Meta>=5m (model ceiling): precision 1.00, recall 0.59. Errors symmetric (FP = high-NDVI
  grass/scrub; FN = sub-5m / sparse street trees). Artifacts + RESULTS.md in
  `tmp/labeling-20260529T073613Z/`. MODEL_CARD.md + BENCHMARKS.md updated with CI + n.
- (b) **`clf_v9_metrics.json` regenerated — DONE.** `train_v9_multiepoch.py` now runs
  GroupKFold (location-grouped headline cv5 = 0.858, + spatialblock_5x5 0.826 / 8x8 0.836,
  + shuffled 0.879 kept as `cv5_shuffled_superseded`). Model joblib byte-stable
  (deterministic; guarded refit). Release gate passes (R² 0.858, min per-year 0.806).
- (c) **Brand-level "tree cover" caveat — DONE.** Dense-vegetation-proxy caveat added to
  `Footer.astro`, `Base.astro` meta description, and the `CanopyTrend` chart title
  (project name kept). Site rebuilt, 40/40 e2e pass.
- Also: re-timed the README/site hero GIFs (`remaining-canopy-satellite/-timeline.gif`)
  and the capabilities GIF (`known-vs-predicted.gif`); imageio `duration=1.0` was 1ms
  (max speed) — now gifsicle-timed 1.0s/year + 2.5s end-hold, generator fixed.
- (d) `site/tmp/phase5/matrix.md` is regenerated fresh on every e2e run (now 40/40); no
  stale R² 0.87 remains in a live test.
