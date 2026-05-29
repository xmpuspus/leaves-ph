# Leaves.PH press one-pager

For RadarPH, Inquirer, PhilStar, Rappler, ABS-CBN, Earth Journalism Network, Mongabay, or any outlet running the Metro Manila canopy story.

## What

Leaves.PH is an open-source, reproducible measurement series of Metro Manila tree cover. Per-LGU and per-barangay annual values for the 17 LGUs of the National Capital Region (16 cities plus the municipality of Pateros) and 892 OSM admin-level=10 barangay polygons inside NCR. CC-BY-4.0 data, MIT code. Live at https://leaves.ph.

## Headline measurement

NCR area-weighted canopy is **~8–10%** (pooled cross-sectional estimate under the published NDVI pixel rule, calibrated to a 1m Meta canopy-height reference from public-record Sentinel-2 imagery; 2026 reads 7.46% but is provisional, imagery Jan-May). The 2019 to 2026 values are per-year cross-sectional snapshots, not a change series: year-to-year swings of ~2 pp are composite-greenness threshold-crossing noise, not measured canopy gain or loss.

## Method

Pull annual Sentinel-2 L2A median composites over the NCR bbox. Mask clouds. Compute NDVI per pixel. Threshold at NDVI > 0.62, tuned against Meta's 1m canopy-height product at the >5m height level. Aggregate per LGU and per barangay against PSA / OSM admin boundaries. The published per-LGU and per-barangay series come from this baseline. Separately, a detection model is in optimization toward a first release: CLIP ViT-Large/14 embeddings feeding a gradient-boosted regression head, trained per the [SolarMap.PH](https://github.com/xmpuspus/solar-map-ph) playbook onto Meta's 1m canopy fraction. On held-out locations it reaches R² 0.83–0.86 under grouped 5-fold cross-validation (0.86 location-grouped, 0.83 spatial-block, n = 38,260 tiles) — agreement with Meta, its calibration target, not accuracy against independent ground truth. It is not yet the source of any published figure.

## Per-LGU highlights (2026, NDVI baseline)

- Quezon City 18.93 percent, anchored by La Mesa watershed, UP Diliman, the Wack Wack greens.
- Mandaluyong 11.19 percent, Makati 8.92 percent, Caloocan 8.80 percent, Marikina 6.87 percent.
- Manila 0.89 percent, Navotas 0.47 percent: reclamation and dense urban core.
- Largest 2019-to-2026 snapshot differences: Taguig (−2.76 pp), Malabon (−1.54), Las Pinas (−1.47), Valenzuela (−1.39). These are differences of two cross-sectional snapshots, not measured canopy loss (they inherit the composite-greenness threshold-crossing artifact).

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

`make hash-verify` confirms a bit-exact reproduction of the canonical per-LGU CSV. The 27-check release gate (`make verify`) covers em-dash + AI-jargon hygiene, requirements-pinning, the detection model's held-out R² floor, Astro typecheck, and per-LGU schema integrity.

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
