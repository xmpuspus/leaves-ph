# LinkedIn launch draft

DO NOT POST until leaves.ph, github.com/xmpuspus/leaves-ph, the Zenodo DOI, and the HuggingFace dataset all return 200.

---

## Version A: 2026 finding lead

I used the techniques from SolarMap.PH and applied them to Metro Manila's tree cover. Three weeks of fresh 2026 Sentinel-2 + Hansen GFC v1.13 + ESA WorldCover + Dynamic World + Meta Canopy Height v2, stacked per-LGU for the 17 NCR LGUs.

The headline numbers in public circulation disagree by half. Global Forest Watch's dashboard puts Metro Manila at 4.0 percent canopy. DENR's cited figure (in EJN's Oct 2024 piece and in news coverage) is 6 percent. ScienceKonek published a 2024 map that nobody can find a copy of.

Leaves.PH (2026 measurement, Sentinel-2 NDVI tuned against Meta canopy height v2 with recall floor 0.85): NCR canopy = 7.46 percent.

This validates DENR's 6 percent claim within methodology variance. It refutes GFW's 4 percent. It matches Meta's independent v2 ground-truth (7.5 percent at canopy height > 5 m for the 2018-2020 imagery epoch) within 0.04 percentage points.

Per-LGU the story is real but uneven. Quezon City holds 18.93 percent (the NE green zone: La Mesa watershed, UP Diliman, Wack Wack). Manila is at 0.89 percent. Navotas at 0.47 percent. The steepest decliners 2019 to 2026 are Taguig (-2.76pp), Malabon (-1.54pp), Las Pinas (-1.47pp), Valenzuela (-1.39pp). Makati is up +1.69pp.

The 225 trees felled along Quirino Avenue in May 2026 for the SALEX expressway will not show in the global Hansen v1.13 product until a future release (30 m resolution misses sub-pixel events). They will eventually.

Code, data, methodology, GIFs, per-LGU CSV, reconciliation table: https://github.com/xmpuspus/leaves-ph
Interactive map with year slider 2019 to 2026: https://leaves.ph

MIT for code, CC-BY-4.0 for data. Every input is canonical public satellite. Reproducible from `make fetch && make compute && make verify`.

---

## Version B: technical lead

Five canonical canopy datasets stacked over Metro Manila for 2019 to 2026. Sentinel-2 L2A median composites (cloud-masked at s2cloudless probability < 40, 30 m); Hansen Global Forest Change v1.13 for loss history; ESA WorldCover v200 (2021) as the independent cross-check; Dynamic World v1 for fuzzy probability; Meta Canopy Height v2 (1 m, 2018-2020 source imagery) as the calibration truth. Per-LGU aggregation against OSM admin-level=6 polygons for the 17 NCR LGUs.

NDVI threshold tuned to 0.62 (F1-maximised against Meta canopy height > 5 m, with a recall floor of 0.85).

Result: NCR canopy 2026 = 7.46 percent. 8-year curve peaks at 10.24 percent in 2023, then declines.

The reconciliation table is what makes this useful: GFW's 4.0 percent (Hansen-derived, 2020 baseline) is 3.46pp below our 2026 measurement. DENR's cited 6 percent is 1.46pp below. Meta's independent height truth at > 5 m is within 0.04pp of our number. The published 2024+ narratives were anchored to figures more conservative than what the satellite data shows.

Per-LGU rankings + Hansen cumulative loss + ESA cross-check in BENCHMARKS.md. Hero animation + 4 hotspot GIFs in docs/demo/.

https://github.com/xmpuspus/leaves-ph
https://leaves.ph

MIT + CC-BY-4.0. Reproducible from `make fetch && make compute && make verify`.

---

## Version C: civic-tech lead

When the news cited "Metro Manila is rapidly becoming a city without trees" in May 2026, four different sources had been quoted for the headline canopy number, and the four disagreed by half.

I built Leaves.PH to publish a fifth, fully reproducible 2026 measurement, per-LGU, with the methodology committed.

NCR canopy 2026 = 7.46 percent.

DENR's cited 6 percent is plausible (we measure +1.46pp above). GFW's dashboard 4.0 percent understates 2026 by 3.46pp. ScienceKonek's 2024 map is not findable. Meta's independent v2 ground truth at canopy > 5 m is within 0.04pp of our number.

Quezon City holds 18.93 percent (the NE green zone). Manila is at 0.89 percent. Navotas at 0.47 percent. The steepest 2019 to 2026 declines: Taguig -2.76pp, Malabon -1.54pp, Las Pinas -1.47pp.

The full curve, per-LGU table, Hansen cumulative loss column, ESA 2021 cross-check, 5 hero animations including the SALEX corridor before-and-after, and the reproducible pipeline:

https://github.com/xmpuspus/leaves-ph
https://leaves.ph

MIT (code) + CC-BY-4.0 (data). Same playbook as SolarMap.PH: canonical public satellite, per-LGU disjoint holdout, hash-verified build.

---

## Image to attach

Primary: `docs/demo/hero.gif` (NCR-wide 2019 to 2026 timeline)
Alternative: `docs/demo/lgu-choropleth.gif` (cleaner for a still scroll)

## Notes for posting

- Hashtags: #LeavesPH #MetroManila #CivicTech #OpenData #RemoteSensing
- Tag: ScienceKonek (so they can update their 2024 map if it's still around), DENR, GFW
- Best time to post: weekday morning Manila time (UTC+8)
- Cross-post to FB (use `facebook-post.md` draft)
