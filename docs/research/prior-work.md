# Prior Work and Tool Survey for Leaves.PH v1.0

Written 2026-05-26 as Phase 0 of Leaves.PH. Synthesizes findings from four parallel research dispatches:

- canonical baselines (Hansen GFC, ESA WorldCover, Dynamic World)
- frozen-encoder embedding stacks (AlphaEarth Foundations, TESSERA)
- canopy-height truth layers (Meta 2023/v2, GEDI L2A, ICESat-2 ATL08)
- PH-specific evidence (ScienceKonek 2024, DENR FMB, SALEX, GFW PH dashboard, academic + civic prior work)

Raw per-agent reports are in `/tmp/leaves-prior-work-{canonical,embeddings,canopy-height,ph}.md` (not committed).

## 1. Headline finding

The canonical global tree-cover stack for 2016 to 2026 already exists at 10 m. Hansen GFC v1.12 carries the loss history back to 2001, ESA WorldCover v200 freezes a 2021 cross-check, Dynamic World v1 gives a near-real-time annual probability for 2015 to today, and Meta v2 plus GEDI L2A give a 1 m to 25 m height truth layer for NDVI calibration. None of these are PH-specific, none publish a per-LGU breakdown for Metro Manila, and the four public 2024+ NCR figures in circulation (DENR FMB "6 percent / 3,565 ha", GFW "2.3 kha at 4.0 percent of land area", EJN "open forest 2,790 ha to 2,071 ha 2020", ScienceKonek 2024) disagree with each other.

Leaves.PH v1.0 is the **2026 update layer + per-LGU breakdown + reconciliation between those four figures**, using all four canonical sources stacked, validated against Meta canopy height, and held out by entire LGU. Not a new global model.

## 2. Dataset matrix

| Source | Resolution | Cadence | License | GEE asset | Best as |
|---|---|---|---|---|---|
| Hansen GFC v1.12 | 30 m | annual loss 2001-2024 | Public domain | `UMD/hansen/global_forest_change_2024_v1_12` | long-term loss history |
| ESA WorldCover v200 | 10 m | 2021 single epoch | CC-BY-4.0 | `ESA/WorldCover/v200` | 2021 cross-check |
| Dynamic World v1 | 10 m | ~5 day (Sentinel-2) | CC-BY-4.0 | `GOOGLE/DYNAMICWORLD/V1` | annual per-LGU curve 2016-2026 |
| Sentinel-2 L2A | 10 m | ~5 day | Copernicus (open) | `COPERNICUS/S2_SR_HARMONIZED` | RGB + NDVI for animations |
| AlphaEarth Foundations V1 | 10 m | annual 2017-2025 | CC-BY-4.0 | `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL` | optional calibrated head, multi-year time series |
| TESSERA | 10 m | 2024 now, 2017-2024 rolling | CC0 + MIT | `geotessera` pip | optional canopy-task head, 2024 only |
| Meta Canopy Height v2 | 1 m | source 2009-2020, 80 percent 2018-2020 | CC-BY-4.0 | AWS `s3://dataforgood-fb-data/forests/v1/alsgedi_global_v6_float/` | wall-to-wall height truth for NDVI calibration |
| GEDI L2A monthly | 25 m | 2019-present, sparse | NASA public domain | `LARSE/GEDI/GEDI02_A_002_MONTHLY` | spot-truth (200-400 points) |
| ICESat-2 ATL08 | 20 m segments | sparse, cloud-penetrant | NASA public domain | NSIDC + GEE | defer; redundant for dense urban NCR |

## 3. Pinned stack for v1.0

Decision: use Hansen GFC + ESA WorldCover + Dynamic World as the **input baseline triad**, Meta v2 + GEDI L2A as the **calibration layer**, and Sentinel-2 L2A for the **RGB animation frames**. AlphaEarth is **conditional** for an optional Phase 4 head.

### 3.1 Baseline triad (mandatory)

1. **Hansen GFC v1.12** for 2001-2024 loss history and `treecover2000` year-2000 baseline. Crops to NCR bbox in one GEE call; ~30 m loss tiles per year.
2. **Dynamic World v1** for the annual canopy curve 2016 to 2026. Median of the `trees` probability band per year per LGU is the headline series. Avoids Hansen's plantation-harvest false positive and captures regrowth that Hansen ignores.
3. **ESA WorldCover v200** for an independent 2021 binary tree mask. Used as the calibration cross-check, not as a trend layer.

This triad covers loss, presence, and probability across three sensors. Three-way consensus on a pixel = high confidence. One-way disagreement = flag for the methodology footnote.

### 3.2 Calibration layer (mandatory)

4. **Meta Canopy Height v2** for the wall-to-wall 1 m height truth used to calibrate the NDVI threshold. Caveats baked into the methodology: Meta's source imagery is mostly 2018-2020, so its truth layer is **a ~2019 epoch**, not a year-by-year truth. We document this honestly; we do not call Meta a 2026 ground truth.
5. **GEDI L2A monthly** RH98 for ~300 spot-truth points across NCR. Independent lidar, weak in tall-multi-layer canopy but adequate for the predominantly low-canopy urban Metro Manila context. Confirms that the NDVI threshold tuned against Meta also predicts GEDI height > 5 m.

### 3.3 Animation frames (mandatory)

6. **Sentinel-2 L2A median composites** per year 2016-2026, s2cloudless-masked, true-color RGB for hero GIF and per-hotspot GIFs (SALEX corridor, Quirino Avenue, La Mesa watershed, per-LGU choropleth).

### 3.4 Optional Phase 4 head (conditional)

7. **AlphaEarth Foundations V1** as the frozen encoder if Phase 3's NDVI threshold + Hansen + Dynamic World is not sharp enough to validate a per-LGU breakdown at LGU granularity. AlphaEarth picked over TESSERA for v1.0 because **2017-2025 historical coverage is mandatory for a 10-year trend** and TESSERA's pre-2024 backfill is still rolling out. TESSERA is on the v1.1 candidate list (higher canopy-task accuracy: 8.88 m RMSE Borneo vs AlphaEarth ~16 m per the TESSERA paper; revisit once full PH historical TESSERA tiles ship).

**Why AlphaEarth and not TESSERA right now:**
- AlphaEarth ships every year 2017-2025 from day one. TESSERA ships 2024 and rolls the rest.
- AlphaEarth is on GEE natively; no extra pip wheel, no separate registry.
- AlphaEarth tile is ~307 MB/year compressed COG vs TESSERA's ~1.62 GB/year quantized int8. Ten-year NCR cache: ~3 GB AlphaEarth vs ~16 GB TESSERA.
- AlphaEarth's lower canopy-task accuracy is acceptable when Hansen + Dynamic World + Meta height are doing the heavy validation lifting. The embedding head is a tiebreaker, not the spine.

If Phase 3 is sufficient on its own (NDVI threshold + Hansen + DW gives a clean per-LGU curve that agrees with Meta calibration within 5 percent), **Phase 4 is skipped** for v1.0. AlphaEarth gets added in v1.1.

## 4. Technical-novelty position

Leaves.PH v1.0 is not a competing global forest model. It is a **single-region, multi-source, fresh-2026, per-LGU reconciliation** layer on top of canonical sources. The novelty is:

- **Recency:** 2026 measurements, not 2020-2022 figures recycled by news outlets.
- **Granularity:** per-LGU and (where possible) per-barangay for all 17 NCR cities, including the canonical underrepresented LGUs (Manila, Caloocan, Navotas) and overrepresented LGUs (QC, Marikina, La Mesa watershed).
- **Validation:** explicit reconciliation of the four public NCR figures that currently disagree (DENR FMB 6 percent, GFW 4.0 percent, EJN open-forest 2,071 ha 2020, ScienceKonek 2024).
- **Reproducibility:** every input layer is canonical, every threshold is committed, every per-LGU number lands in a CSV + Zenodo DOI.

Civic thesis (the net-metering-gap analog from SolarMap.PH): the published headline understates the urgency. Two-step audit framing: **(a) which of the four canonical 2024+ NCR figures is correct in 2026, and (b) what does the 2016-2026 per-LGU delta show**.

## 5. PH evidence base: what we found, what is missing

Agent 4 (PH-specific) was the most consequential dispatch. Headline result: the figures cited in the 2026-05-26 RadarPH post **are not all publicly traceable to a 2024+ DENR document** as of today. This is itself the project's first finding.

### 5.1 ScienceKonek 2024 map

- ScienceKonek is a PH science-communication collective with an active Facebook page (https://www.facebook.com/sciencekonek/).
- The "2024 map" is referenced by Earth Journalism Network's October 2024 piece "Blazing Heat of 2024 Ignites Filipinos' Need for Trees and Green Spaces" but **the underlying map raster, methodology, and reproducibility artifacts are not publicly findable** (no GitHub, no PDF report, no data DOI).
- Validation hook: scrape ScienceKonek's Facebook posts for the original 2024 publication image and methodology caption; if it is a Facebook-only artifact, treat as commentary in `BENCHMARKS.md`, not as a primary dataset.

### 5.2 DENR FMB "6 percent / 3,565 ha / -89 ha"

- The DENR FMB Forest Cover NCR page exists (https://forestry.denr.gov.ph/index.php/forest-cover-ncr) but the specific 3,565 ha figure is not in the publicly-rendered 2024+ reports.
- "Open forest" series 2,790 ha to 2,000 ha to 2,071 ha (2020) is documented in EJN's 2024 piece and consistent with DENR's Heritage Book 2023, but **"open forest" is a sub-category of total tree cover, not the same number as Hansen-style canopy**.
- GFW reports "Metropolitan Manila had 2.3 kha natural forest in 2020, extending over 4.0 percent of land area" via the GFW PHL/47 dashboard. 4.0 percent of NCR area (~63,360 ha) is 2,534 ha. 6 percent would be 3,802 ha. **The two official figures disagree by ~50 percent.** This disagreement is the project's first headline result.
- "-89 ha 2001-2022 loss for Metro Manila" is not in GFW's dashboard at MM granularity. Philippines-wide Hansen loss for 2001-2022 is ~1.42 million ha. NCR-scaled-by-land-area gives ~710 ha; NCR-scaled-by-canopy-share gives ~89 ha. The -89 ha figure is plausible at scale but unverified at source.

### 5.3 SALEX (Southern Access Link Expressway)

- 225 of ~600 approved trees felled as of 2026-05-20. Verified by DENR-NCR.
- 50+ year-old narra confirmed. Verified by DENR-NCR.
- Project alignment: 3.97 km along Quirino Avenue, San Marcelino Street, near Roxas Boulevard. Contractor San Miguel Corp. 50,700 replacement seedlings required by law.
- Validation hook: cross-reference the 225 felled-tree locations against Leaves.PH's pre-May 2026 Sentinel-2 baseline; the GIF for the SALEX corridor must show the canopy strip pre-cut and the cleared strip post-cut.

### 5.4 Global Forest Watch PHL dashboard

- National 2001-2024 cumulative loss: 1,524,278 ha (8.2 percent of year-2000 tree cover).
- MM-specific 2001-2022 loss not exposed at dashboard granularity. Will need GFW API query for the NCR ADM1 sub-polygon.
- Hotspots (national context, not NCR): Palawan 163,000 ha, Agusan del Sur 116,000 ha, Quezon Province 44,200 ha.

### 5.5 Verified per-LGU and per-barangay anchors

These three numbers are the strongest anchor points for v1.0 validation. All three appear in EJN's October 2024 piece citing UP Diliman / DENR / Google Environmental Insights Explorer:

- **Muntinlupa**: 14.4 sq m / capita (highest in MM).
- **Quezon City**: 12.5 sq m / capita; 33 percent tree canopy per Google EIE.
- **Escopa IV (QC barangay)**: 1.48 percent tree cover (lowest in MM, out of 142 barangays).

If Leaves.PH's 2026 numbers for these three locations diverge sharply from the 2024 EJN anchors, that itself is a publishable finding.

### 5.6 La Mesa watershed: the regrowth countercurrent

Easy to miss in the headline-decline narrative. Estoque et al. 2018 (Forest Ecology and Management, vol. 430) documents:
- 1988-2002: net forest loss 259 ha
- 2002-2016: net forest gain 557 ha (reforestation efforts)

UPLB's later spatio-temporal analysis adds:
- 2003-2010: -8.76 percent
- 2010-2015: +1.29 percent
- 2015-2020: +2.08 percent

Leaves.PH must show this NE-quadrant recovery alongside the MM-wide decline. A monotone "all of NCR is losing trees" narrative would be wrong.

## 6. Academic prior work

1. **Estoque RC, Murayama Y, Lasco RD, et al. (2018).** "Changes in the landscape pattern of the La Mesa Watershed: The last ecological frontier of Metro Manila, Philippines." *Forest Ecology and Management* 430, 280-290. https://www.sciencedirect.com/science/article/abs/pii/S0378112718307503
2. **UP Diliman Department of Geodetic Engineering (2025-2026).** "Multitemporal analysis of green spaces in Manila City using Sentinel-2 L2A and canopy/building-height datasets, 2018-2024." *ISPRS Annals* X-5-W4. https://isprs-annals.copernicus.org/articles/X-5-W4-2025/237/2026/isprs-annals-X-5-W4-2025-237-2026.pdf
3. **Comiso JC et al. (2022).** "Simulation of Metro Manila urban heat island using WRF coupled with urban canopy models." *MDPI Atmosphere* 13(10), 1658. https://www.mdpi.com/2073-4433/13/10/1658
4. **UP OUVR Repository (2023).** "Managing Momentum: A Spatio-Temporal Analysis of Land Use Land Cover Changes in La Mesa Watershed." https://repository.upou.edu.ph/items/ab2d7a91-7d60-4253-a3ab-b0c25a8c9fa9
5. **UPLB Ecosystems and Development Journal.** "The effect of urban sprawl on forest carbon stocks in La Mesa Watershed Reservation, Metro Manila." https://ovcre.uplb.edu.ph/journals-uplb/index.php/EDJ/article/view/1303
6. **FAO AGRIS (PH2000100469).** Quezon City urban forestry program assessment. https://agris.fao.org/agris-search/search.do?recordID=PH2000100469
7. **"ASTER-based study of night-time urban heat island, Metro Manila."** Academia.edu archive. https://www.academia.edu/506496/ASTER_based_study_of_the_night_time_urban_heat_island_effect_in_Metro_Manila

## 7. Civic / news pieces

1. **Earth Journalism Network, October 2024.** "Blazing Heat of 2024 Ignites Filipinos' Need for Trees and Green Spaces." https://earthjournalism.net/stories/blazing-heat-of-2024-ignites-filipinos-need-for-trees-and-green-spaces
2. **Inquirer Opinion, May 2026.** "The massacre of Quirino Avenue trees." https://opinion.inquirer.net/191897/the-massacre-of-quirino-avenue-trees
3. **PhilStar, 2026-05-25.** "Quirino Avenue mass tree-cutting slammed as 'ecological violence'." https://www.philstar.com/headlines/climate-and-environment/2026/05/25/2530430/quirino-avenue-mass-tree-cutting-slammed-ecological-violence
4. **Inquirer News, 2026.** "DENR defends mass cutting of trees in Manila for road project." https://newsinfo.inquirer.net/2231926/denr-defends-mass-cutting-of-trees-in-manila-for-road-project
5. **Context.ph, 2026-05-20.** "DENR: Tree cutting in Manila is legal, with environmental offsets." https://context.ph/2026/05/20/denr-tree-cutting-in-manila-is-legal-with-environmental-offsets/
6. **GMA News, 2026.** "Manila residents sad over 200 trees felled along Quirino Highway." https://www.gmanetwork.com/news/topstories/metro/988396/manila-residents-trees-quirino-highway-expressway/story/
7. **Tribune, 2026-05-22.** "Stop SMC's mass slaughter of trees." https://tribune.net.ph/2026/05/22/stop-smcs-mass-slaughter-of-trees
8. **Philippine News Agency.** "DENR: Quirino Avenue tree cutting underwent review." https://www.pna.gov.ph/articles/1275435

## 8. Open gaps and Phase 1+ blockers

These are the items we cannot resolve from public web sources alone. Phase 1 starts without them but the launch artifacts (Phase 9) need them resolved or honestly documented as gaps.

| Gap | Status | Resolution path | Blocking? |
|---|---|---|---|
| ScienceKonek 2024 map artifact | not located | scrape FB page, treat as commentary if not reproducible | No (treat as commentary) |
| DENR FMB 3,565 ha / 6 percent source document | not in public 2024+ reports | request from DENR-NCR; check Heritage Book 2023 PDF | No (publish our own number, cite DENR figure as "DENR FMB cited in EJN 2024") |
| DENR FMB -89 ha 2001-2022 source | not in GFW dashboard at MM granularity | query GFW Pro API for MM ADM1 polygon | No (compute our own from Hansen v1.12 directly) |
| SALEX ECC + species inventory | not public | request from DENR-NCR / DPWH | No (cite news sources, cross-reference satellite) |
| Per-barangay tree cover baseline (all 142 MM barangays) | none exists publicly | compute from Dynamic World + OSM barangay polygons | **Yes (this IS the v1.0 deliverable)** |
| Google EIE QC 33 percent canopy methodology | not documented | EIE API or scrape; treat as commentary | No |
| TESSERA pre-2024 PH historical coverage | rolling out | wait for backfill; v1.1 candidate | No (use AlphaEarth) |

## 9. References and sources

Full URLs are inline above. Raw per-agent reports (not committed) at `/tmp/leaves-prior-work-{canonical,embeddings,canopy-height,ph}.md`.

GEE asset paths confirmed live as of 2026-05-26:
- `UMD/hansen/global_forest_change_2024_v1_12` (latest available 2024; v1.13 expected late 2026)
- `ESA/WorldCover/v200`
- `GOOGLE/DYNAMICWORLD/V1`
- `COPERNICUS/S2_SR_HARMONIZED`
- `GOOGLE/SATELLITE_EMBEDDING/V1/ANNUAL`
- `LARSE/GEDI/GEDI02_A_002_MONTHLY`

Meta v2 download path: `s3://dataforgood-fb-data/forests/v1/alsgedi_global_v6_float/` (anonymous S3, no AWS account required).

End of Phase 0 prior-work review.
