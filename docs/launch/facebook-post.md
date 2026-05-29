# Facebook launch draft

DO NOT POST until leaves.ph, github.com/xmpuspus/leaves-ph, and the Zenodo DOI return 200.

---

Posting an open measurement series I built: Leaves.PH.

It maps tree-cover percentage across the 17 LGUs of the National Capital Region for every annual epoch in the published window, from Sentinel-2 surface-reflectance imagery, calibrated against Meta's 1m canopy-height reference.

Inputs are all open, all canonical:
* Sentinel-2 L2A from Copernicus / ESA
* Hansen Global Forest Change v1.13 (UMD GLAD) for the loss layer
* ESA WorldCover v200 for an independent land-cover cross-check
* Dynamic World v1 (Google / WRI) for fuzzy tree probability
* Meta Canopy Height v2 as the 1m calibration reference
* PSA boundaries for the 17 LGUs

NDVI threshold tuned against Meta canopy height > 5m, recall floor 0.85.

A separate detection model is in optimization toward a first release: CLIP ViT-Large/14 embeddings feeding a gradient-boosted regression head, trained the same way SolarMap.PH was built onto Meta's 1m canopy fraction. On held-out locations it reaches R² = 0.87 (MAE 0.069, 5-fold cross-validation grouped by location, n = 16,800 tiles across 2019-2026). The deliverable includes a per-LGU validation gallery so anyone can inspect the model.

Headline measurement for the latest annual epoch: NCR area-weighted canopy = 7.46%, from the NDVI baseline calibrated to Meta's 1m reference.

Per-LGU:
* Quezon City: 18.93% (La Mesa watershed + UP Diliman + Wack Wack)
* Mandaluyong: 11.19%
* Makati: 8.92%
* Caloocan: 8.80%
* Marikina: 6.87%
...
* Manila: 0.89%
* Navotas: 0.47% (reclamation-heavy)

Steepest year-over-year declines across the series sit in Taguig, Malabon, Las Pinas, Valenzuela.

Everything is open and reproducible. From a clean clone, `make hash-verify` reproduces the canonical CSV byte-for-byte:

https://github.com/xmpuspus/leaves-ph
https://leaves.ph

Code MIT. Data CC-BY-4.0.

---

## Image to attach

Primary: `docs/demo/remaining-canopy-satellite.gif`
Alternative: any of the per-LGU validation panels under `detection/scan/validation/`

## Notes for posting

- Neutral standalone framing. No comparison to specific prior published estimates in the lead.
- A methodology cross-reference table on the site lists adjacent published estimates side-by-side with their respective definitions.
- Comment-thread responses ready: /methodology, /validation gallery, /data downloads.
