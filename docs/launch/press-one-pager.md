# Leaves.PH press one-pager

For RadarPH, Inquirer, PhilStar, Rappler, ABS-CBN, Earth Journalism Network, Mongabay, or any outlet running the Metro Manila canopy story.

## What

Leaves.PH is an open-source, reproducible 2026 measurement of Metro Manila's tree cover. Per-LGU (16 NCR cities + Pateros). 8-year time series 2019 to 2026. CC-BY-4.0 data, MIT code.

## Headline finding

NCR canopy 2026 = 7.46 percent.

This sits between the four 2024+ public figures that have been quoted in news coverage:

| Source | Headline | Status |
|---|---|---|
| DENR FMB (cited in news / EJN) | 6 percent / 3,565 ha | Plausible. Our 2026 measurement is +1.46pp above. The original DENR source document is not in public 2024+ reports we could locate. |
| Global Forest Watch dashboard | 4.0 percent / 2.3 kha (2020 baseline) | Understates 2026. Our 2026 measurement is +3.46pp above. Difference of methodology (Hansen 30 m loss-history vs our NDVI canopy mask). |
| Earth Journalism Network 2024 ("open forest") | 2,071 ha in 2020 | Different definition. "Open forest" is a DENR sub-class, not directly comparable. |
| ScienceKonek 2024 map | (referenced by RadarPH) | Map raster + methodology not publicly findable. |
| Meta Canopy Height v2 | 7.5 percent (canopy > 5 m, 2018-2020 imagery) | Independent ground truth. Within 0.04pp of our 2026 number. |

## Per-LGU highlights

- Top canopy: Quezon City 18.93 percent (NE green zone: La Mesa watershed, UP Diliman, Wack Wack).
- Bottom canopy: Manila 0.89 percent, Navotas 0.47 percent (densely built / reclamation).
- Steepest 2019 to 2026 decline: Taguig -2.76pp, Malabon -1.54pp, Las Pinas -1.47pp, Valenzuela -1.39pp.
- Notable gain: Makati +1.69pp.

## Method

Five canonical public canopy datasets stacked over NCR:

1. **Sentinel-2 L2A** (Copernicus / ESA). Annual median composites, cloud-masked with s2cloudless at probability < 40, exported at 30 m to match Hansen's grid.
2. **Hansen Global Forest Change v1.13** (UMD GLAD / Global Forest Watch). Year-2000 baseline + 2001-2025 annual loss + 2000-2012 binary gain.
3. **ESA WorldCover v200** (ESA, 2021 single-epoch). Independent 10 m class-10 tree cross-check.
4. **Dynamic World v1** (Google AI + WRI). Annual median tree-probability 2019 to 2026.
5. **Meta Canopy Height v2** (Meta AI + Land & Carbon Lab). 1 m AI canopy height (source imagery 2018-2020). The calibration truth.

NDVI threshold tuned to 0.62 (F1-maximised against Meta canopy height > 5 m, with recall floor 0.85). Per-LGU aggregation against OSM admin-level=6 polygons.

## What this is not

- Not a per-tree census. 30 m resolution misses sub-pixel events.
- Not legal evidence of unpermitted cutting. We compute the canopy delta from public-domain satellite imagery. Specific allegations require independent investigation.
- Not 2026 ground truth. Meta v2's source imagery is mostly 2018-2020, so our calibration layer is a ~2019 truth.
- Not affiliated with DENR, GFW, ScienceKonek, EJN, or any LGU.

## SALEX / Quirino Avenue

The 225 trees felled along Quirino Avenue in May 2026 for the Southern Access Link Expressway (SALEX) had an Environmental Compliance Certificate from DENR-NCR. Whether the ECC's conditions were met is a separate question and not one Leaves.PH answers.

A before-and-after canopy strip of the SALEX corridor (3.97 km along Quirino Ave + San Marcelino + near Roxas Boulevard) lives at `docs/demo/salex-timeline.gif`. It is descriptive, not legal evidence. Hansen v1.13 at 30 m will probably not register the May 2026 event until a future release.

## Independent verification welcome

Code: https://github.com/xmpuspus/leaves-ph
Site: https://leaves.ph
Data: CC-BY-4.0; downloads at https://leaves.ph/data
Methodology: https://leaves.ph/methodology
Per-LGU CSV: https://github.com/xmpuspus/leaves-ph/blob/main/data/per_lgu/per_lgu_canopy_2019_2026.csv

Reproduce with:
```bash
git clone https://github.com/xmpuspus/leaves-ph
cd leaves-ph
earthengine authenticate
make fetch && make compute && make verify
```

Hash-verified canonical CSV: the sha256 prefix is pinned in the Makefile and asserted in CI. Bit-exact across any environment with the pinned `requirements.txt` versions.

## Contact

Open an issue at https://github.com/xmpuspus/leaves-ph/issues or use the LGU-correction template at https://github.com/xmpuspus/leaves-ph/issues/new?template=lgu_correction.md.

For takedowns or privacy concerns: file a private security advisory at https://github.com/xmpuspus/leaves-ph/security/advisories/new. Acknowledged within 5 working days.

Direct: xpuspus@gmail.com.

## Citation

```
@software{puspus_leaves_ph_2026,
  author = {Puspus, Xavier},
  title  = {{Leaves.PH: open-source tree-cover validation for Metro Manila}},
  year   = {2026},
  url    = {https://github.com/xmpuspus/leaves-ph}
}
```

Versioned Zenodo DOI minted at each tagged release.
