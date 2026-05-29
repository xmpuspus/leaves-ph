# LinkedIn launch draft

DO NOT POST until leaves.ph, github.com/xmpuspus/leaves-ph, the Zenodo DOI, and the HuggingFace dataset all return 200.

---

## Version A: research-tone series lead

Leaves.PH is an open, reproducible measurement series of Metro Manila tree cover. Per-LGU annual values across the 17 NCR LGUs, computed from Sentinel-2 surface-reflectance imagery and calibrated against the Meta v2 1m canopy-height reference. NDVI threshold tuned to 0.62 (F1-maximised against canopy height > 5m, recall floor 0.85).

A separate detection model is in optimization toward a first release: CLIP ViT-Large/14 embeddings feeding a gradient-boosted regression head onto Meta's 1m canopy fraction. On held-out locations it reaches R² = 0.87 (MAE 0.069, 5-fold cross-validation grouped by location, n = 16,800 tiles across 2019-2026). The deliverable includes a per-LGU validation gallery so anyone can inspect the model's tiles.

Headline measurement for the latest annual epoch: NCR area-weighted canopy = 7.46%. Quezon City carries the largest absolute share (La Mesa watershed, UP Diliman, Wack Wack). Steepest year-over-year declines across the series: Taguig, Malabon, Las Pinas, Valenzuela.

Everything is open and reproducible. From a clean clone, `make hash-verify` reproduces the canonical CSV byte-for-byte.

https://github.com/xmpuspus/leaves-ph
https://leaves.ph

MIT + CC-BY-4.0.

---

## Version B: technical lead

Open-source pipeline: Sentinel-2 L2A median composites (cloud-masked at s2cloudless probability < 40, 30m exports), Hansen Global Forest Change v1.13 for loss history, ESA WorldCover v200 for an independent cross-check, Dynamic World v1 for fuzzy tree probability, Meta Canopy Height v2 (1m, 2018-2020 source imagery) as the calibration reference. Per-LGU aggregation against PSA admin boundaries for the 17 NCR LGUs.

A CLIP ViT-Large/14 + gradient-boosted regression head, trained the same way SolarMap.PH was, is in optimization toward a first release. It predicts canopy fraction in [0, 1] from Meta's 1m canopy fraction and reaches R² = 0.87 (MAE 0.069) on held-out locations, 5-fold cross-validation grouped by location, n = 16,800 tiles across 2019-2026. Per-LGU visual validation panels make the model inspectable.

Headline measurement: NCR area-weighted canopy = 7.46% in the latest annual epoch, from the NDVI baseline calibrated to Meta's 1m reference.

Per-LGU rankings, detection-model accuracy, Hansen cumulative loss, ESA cross-check in BENCHMARKS.md. Per-LGU validation gallery at /validation. Demo animations at docs/demo/.

https://github.com/xmpuspus/leaves-ph
https://leaves.ph

MIT + CC-BY-4.0. Reproducible from `make fetch && make compute && make train && make scan && make verify`.

---

## Version C: civic-tech lead

A reproducible tree-cover measurement series for Metro Manila, built in the same pattern as my earlier SolarMap.PH project.

Two layers in the deliverable:
- Per-pixel NDVI baseline calibrated against Meta's 1m canopy-height reference (the published figures)
- A detection model in optimization toward a first release: per-tile CLIP + gradient-boosted regression onto Meta's 1m canopy fraction, R² = 0.87 on held-out locations

Inputs are all canonical public satellite. Outputs are hash-pinned CSVs and a per-LGU validation gallery you can inspect tile-by-tile.

Headline measurement: NCR area-weighted canopy = 7.46% in the latest annual epoch. Quezon City carries the largest absolute share. Steepest year-over-year declines sit in the construction-heavy southern and northern fringes.

Code, data, methodology, validation gallery:
https://github.com/xmpuspus/leaves-ph
https://leaves.ph

MIT (code) + CC-BY-4.0 (data). Same playbook as SolarMap.PH: canonical public satellite, a CLIP + gradient-boosted detection head, per-LGU honest evaluation.

---

## Image to attach

Primary: `docs/demo/remaining-canopy-satellite.gif` (Sentinel-2 RGB basemap + canopy density overlay)
Alternative: any per-LGU validation panel from `detection/scan/validation/`

## Notes for posting

- Hashtags: #LeavesPH #MetroManila #CivicTech #OpenData #RemoteSensing
- Best time to post: weekday morning Manila time (UTC+8)
- Cross-post to FB (use `facebook-post.md` draft)
- Neutral standalone framing. The site lists adjacent published estimates side-by-side with their definitions in a methodology cross-reference table; the launch post does not antagonise.
