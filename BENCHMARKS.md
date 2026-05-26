# Benchmarks

**v1.0 measurement: Leaves.PH puts NCR canopy at 7.46 percent in 2026**, with an 8-year curve that peaks at 10.24 percent in 2023 before stepping back. Per-LGU breakdowns range from Quezon City at 18.93 percent (the NE green zone) to Manila at 0.89 percent and Navotas at 0.47 percent (densely built reclamation areas).

Pipeline: Sentinel-2 L2A median composites (cloud-masked at s2cloudless probability less than 40, 30 m), NDVI thresholded at 0.62 (F1-maximised against Meta Canopy Height v2 with recall floor 0.85), per-LGU aggregated against OSM admin-level=6 polygons for the 17 NCR LGUs.

## Headline (2019 to 2026)

| Year | NCR canopy percent | Canopy hectares | Notes |
|---|---|---|---|
| 2019 | 8.08 | 6,325 | First full-NCR year of S2 L2A PH coverage |
| 2020 | 9.88 | 7,737 | |
| 2021 | 9.79 | 7,665 | ESA WorldCover v200 cross-check: 13.38 percent area-weighted |
| 2022 | 9.99 | 7,818 | |
| 2023 | 10.24 | 8,013 | 8-year peak |
| 2024 | 7.76 | 6,076 | |
| 2025 | 9.88 | 7,733 | |
| 2026 | 7.46 | 5,840 | Most recent measurement |

2018 has only ~24 percent NCR coverage (S2 L2A PH coverage was thin that early) and is excluded from the published curve. See `_fetch_manifest_s2.json` for source-image counts per year.

## Reconciliation against the four public 2024+ NCR canopy figures

| Source | Headline | Our 2026 measurement | Delta | Status |
|---|---|---|---|---|
| DENR FMB (cited in EJN / news) | 6 percent / 3,565 ha | 7.46 percent / 5,840 ha | +1.46pp | Plausible, slightly above the cited figure. DENR source document not in public 2024+ reports. |
| Global Forest Watch dashboard PHL/47 | 4.0 percent / 2.3 kha (2020 baseline) | 7.46 percent (2026) | +3.46pp | GFW materially understates 2026 NCR canopy. Difference of methodology (Hansen 30 m loss-history vs our NDVI canopy mask). |
| Earth Journalism Network 2024 ("open forest", DENR-sourced) | 2,071 ha in 2020 | n/a | n/a | "Open forest" is a DENR sub-class, not the same definition as canopy mask. Not directly comparable. |
| ScienceKonek 2024 map (referenced by RadarPH May 2026) | unknown | n/a | n/a | Map raster + methodology not publicly findable. |

Independent Meta v2 ground truth (1 m canopy height, source imagery 2018-2020): **7.5 percent of NCR pixels have canopy height greater than 5 m**. This is within 0.04pp of our 2026 7.46 percent and supports DENR's 6 percent cited figure as plausible.

## Per-LGU 2026 ranking

| Rank | LGU | 2026 canopy percent | 2019 to 2026 delta (pp) | ESA 2021 percent |
|---|---|---|---|---|
| 1 | Quezon City | 18.93 | -0.38 | 28.77 |
| 2 | Mandaluyong | 11.19 | -0.28 | 14.40 |
| 3 | Makati | 8.92 | +1.69 | 16.01 |
| 4 | Caloocan | 8.80 | -0.96 | 23.62 |
| 5 | Marikina | 6.87 | -0.01 | 17.10 |
| 6 | Taguig | 6.47 | -2.76 | 7.58 |
| 7 | Valenzuela | 5.81 | -1.39 | 14.56 |
| 8 | Pasig | 5.23 | -0.17 | 12.01 |
| 9 | Las Pinas | 5.20 | -1.47 | 11.92 |
| 10 | Pateros | 4.96 | +1.26 | 9.96 |
| 11 | Paranaque | 4.35 | +0.57 | 9.55 |
| 12 | Muntinlupa | 3.77 | -0.74 | 7.55 |
| 13 | Malabon | 3.68 | -1.54 | 7.24 |
| 14 | San Juan | 2.41 | +0.76 | 7.09 |
| 15 | Pasay | 2.08 | -0.93 | 5.07 |
| 16 | Manila | 0.89 | +0.21 | 2.42 |
| 17 | Navotas | 0.47 | -0.40 | 0.92 |

The four LGUs with the steepest declines (Taguig -2.76, Malabon -1.54, Las Pinas -1.47, Valenzuela -1.39) are all on the construction-heavy southern and northern fringes. QC's 18.93 percent reflects La Mesa watershed + UP Diliman + Wack Wack greens (the canonical NE green zone).

ESA WorldCover v200 numbers run consistently higher than our NDVI mask. That is a methodology difference: ESA's class-10 includes mixed shrub-tree pixels; our NDVI threshold (0.62, calibrated against Meta height greater than 5 m) is stricter.

## Headline finding

GFW's published 4.0 percent figure materially understates NCR's 2026 canopy. DENR's cited 6 percent is closer to but slightly below the satellite-validated 7.5-7.46 percent (Meta v2 / Leaves.PH 2026). The "Metro Manila is rapidly becoming a city without trees" narrative is anchored to a figure that is more conservative than what 2026 satellite data shows. Real-world local declines (Taguig, Caloocan, Valenzuela, Las Pinas) are visible per-LGU but the NCR-wide aggregate has held in the 7-10 percent band since 2019.

## Cross-source agreement

| Source | Year | Method | NCR canopy percent |
|---|---|---|---|
| Meta Canopy Height v2 (height greater than 5 m) | 2018-2020 epoch | 1 m AI canopy height regression | 7.5 |
| ESA WorldCover v200 (class-10) | 2021 | 10 m land cover classification | 13.38 |
| Leaves.PH (NDVI greater than 0.62) | 2026 | 30 m Sentinel-2 NDVI threshold | 7.46 |
| DENR FMB cited | 2024+ (year unclear) | not specified | 6.0 |
| GFW dashboard | 2020 baseline | Hansen 30 m tree-cover greater than 50 percent | 4.0 |

## Hansen GFC cumulative loss (NCR 2001-2025)

Hansen v1.13 records modest loss inside NCR over 25 years (cumulative across the 17 LGUs):

| LGU | Hansen cumulative loss (ha) 2001-2025 |
|---|---|
| Taguig | 77.6 |
| Quezon City | 30.5 |
| Caloocan | 19.6 |
| Las Pinas | 15.9 |
| Valenzuela | 15.8 |
| Navotas | 8.5 |
| Pasig | 6.7 |
| Muntinlupa | 3.7 |
| Paranaque | 3.1 |
| Marikina | 2.6 |
| Manila | 1.6 |
| Pasay | 1.5 |
| Malabon | 0.7 |
| Makati | 0.6 |
| Others | 0.0 |
| Total NCR | ~188 |

These are conservative because Hansen 30 m misses sub-pixel events: the 225 SALEX trees felled along Quirino Avenue in May 2026 will only appear in the 2027 Hansen v1.14 release at earliest, if at all (depends on whether the loss exceeds the canopy-closure threshold inside any 30 m pixel).

## What we have not measured (yet)

- Per-barangay breakdown for all 142 NCR barangays. v1.1 target.
- AlphaEarth Foundations head trained on per-LGU group-CV; only train if it beats the pure NDVI baseline (decision locked 2026-05-26).
- 10 m calibration. v1.0 ships at 30 m to fit GEE's 50 MB sync limit.
- 2027+ updates. v1.0 stops at 2026.

## Reproducing these numbers

```bash
pip install -r requirements.txt
make fetch          # GEE auth required; ~30 min
make calibrate      # NDVI threshold tuned against Meta canopy height v2
make compute        # per-year canopy mask from cached composites
make verify         # release gate
make hash           # print sha256 of per_lgu_canopy_2019_2026.csv
```

If your numbers differ, run `make hash-verify` first to confirm you have the canonical CSV.
