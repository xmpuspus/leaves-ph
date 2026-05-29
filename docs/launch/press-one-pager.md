# Leaves.PH press one-pager

For RadarPH, Inquirer, PhilStar, Rappler, ABS-CBN, Earth Journalism Network, Mongabay, or any outlet running the Metro Manila canopy story.

## What

Leaves.PH is an open-source, reproducible measurement series of Metro Manila tree cover. Per-LGU and per-barangay annual values for the 17 LGUs of the National Capital Region (16 cities plus the municipality of Pateros) and 892 OSM admin-level=10 barangay polygons inside NCR. CC-BY-4.0 data, MIT code. Live at https://leaves.ph.

## Headline measurement

NCR area-weighted canopy in 2026 (provisional, imagery Jan-May): **7.46%** under the v0 NDVI pixel rule, **8.40%** under the v9 multi-epoch CLIP+HistGBR head. Both numbers come from public-record Sentinel-2 imagery and a 1m Meta canopy-height reference. Across the published 2019 to 2026 series, regional canopy is flat to slightly declining (−0.62 percentage points under v0; near zero under v9).

## Method

Pull annual Sentinel-2 L2A median composites over the NCR bbox. Mask clouds. Compute NDVI per pixel. Threshold at NDVI > 0.62, tuned against Meta's 1m canopy-height product at the >5m height level. Aggregate per LGU and per barangay against PSA / OSM admin boundaries. On top of the pixel rule, a second-pass CLIP model trained per the [SolarMap.PH](https://github.com/xmpuspus/solar-map-ph) playbook (OSM bootstrap → ESA WorldCover teacher → Meta-oracle active learning → Platt calibration → continuous canopy-fraction regression) confirms and expands the baseline at tile level. Two tracks: the binary classifier reaches 5-fold CV F1 = 0.78 (v3, classification); the deployed canopy-fraction regressor (clf_v9, CLIP + HistGBR) reaches R² = 0.87 on held-out locations (leakage-free GroupKFold). These are different tasks and metrics, not one trajectory.

## Per-LGU highlights (2026, v0 NDVI)

- Quezon City 18.93 percent, anchored by La Mesa watershed, UP Diliman, the Wack Wack greens.
- Mandaluyong 11.19 percent, Makati 8.92 percent, Caloocan 8.80 percent, Marikina 6.87 percent.
- Manila 0.89 percent, Navotas 0.47 percent: reclamation and dense urban core.
- Steepest year-over-year declines: Taguig (−2.76 pp), Malabon (−1.54), Las Pinas (−1.47), Valenzuela (−1.39).

Full per-LGU table and per-barangay top hits at https://leaves.ph and in `BENCHMARKS.md`.

## Adjacent published estimates

Listed for context, not ranked. Each uses a different definition and vintage.

| Source | Year | Method | NCR canopy |
|---|---|---|---|
| Meta v2 (canopy height > 5m) | 2018-2020 | 1m AI canopy-height regression | 7.5% |
| ESA WorldCover v200 (class 10) | 2021 | 10m land-cover classification (esa_tree_pct_2021, per-LGU CSV) | 13.38% |
| DENR FMB (cited in news / EJN) | 2024+ | not specified in public docs found | 6.0% |
| Global Forest Watch dashboard PHL/47 | 2020 baseline | Hansen 30m tree-cover ≥ 30% canopy | 4.0% |
| Earth Journalism Network | 2020 | DENR "open forest" sub-class | 2,071 ha |
| ScienceKonek 2024 map | 2024 | raster + methodology not publicly findable | unknown |

## What this is and is not

This is a reproducible methodology-and-data ship: pipeline, model artefacts, per-LGU and per-barangay CSVs, multi-year density rasters, validation panels, all hash-pinned and CC-BY-4.0. It is not a verdict on any other source, not a permit-compliance tool, and not a per-tree census. Specific allegations of unpermitted clearing require independent investigation.

## Verification welcome

Code, data, methodology, and full benchmarks at https://github.com/xmpuspus/leaves-ph. Reproduce locally with:

```bash
git clone https://github.com/xmpuspus/leaves-ph
cd leaves-ph
earthengine authenticate
make fetch && make compute && make verify
```

`make hash-verify` confirms a bit-exact reproduction of the canonical per-LGU CSV. The 27-check release gate (`make verify`) covers em-dash + AI-jargon hygiene, requirements-pinning, classifier CV F1 / R² floors, Astro typecheck, and per-LGU schema integrity.

## Contact

Open an issue or LGU-correction at https://github.com/xmpuspus/leaves-ph/issues.

Private security advisory (RA 10173 / takedown): https://github.com/xmpuspus/leaves-ph/security/advisories/new. Acknowledged within 5 working days.

Direct: xpuspus@gmail.com.

## Citation

```bibtex
@software{puspus_leaves_ph_2026,
  author = {Puspus, Xavier},
  title  = {{Leaves.PH: an open-source tree-cover measurement series for Metro Manila}},
  year   = {2026},
  url    = {https://github.com/xmpuspus/leaves-ph}
}
```

Versioned Zenodo DOI minted at each tagged release.
