# Facebook launch draft

DO NOT POST until leaves.ph, github.com/xmpuspus/leaves-ph, and the Zenodo DOI return 200.

---

When RadarPH (Kieth Earl Rebano) posted "Metro Manila is rapidly becoming a city without trees" on 2026-05-26, the headline cited four different sources for the canopy number. They disagreed by half.

ScienceKonek's 2024 map. DENR's "6 percent / 3,565 hectares". GFW's dashboard at 4.0 percent. Earth Journalism Network's "open forest" 2,071 ha in 2020.

So I built Leaves.PH to settle it.

Fresh 2026 measurement using:
* Sentinel-2 L2A (Copernicus / ESA, free)
* Hansen Global Forest Change v1.13 (UMD GLAD, the global standard)
* ESA WorldCover v200 (independent cross-check)
* Dynamic World v1 (Google / WRI, fuzzy probability)
* Meta Canopy Height v2 (1 m AI canopy height, the calibration truth)

Stacked per-LGU for all 17 NCR cities and Pateros. NDVI threshold tuned against Meta canopy height > 5 m.

Result: NCR canopy 2026 = 7.46 percent.

That validates DENR's cited 6 percent (within methodology variance). It refutes GFW's 4 percent (which materially understates 2026). It matches Meta's independent ground truth (7.5 percent) within 0.04 percentage points.

Per-LGU:
* Quezon City: 18.93 percent (the NE green zone, La Mesa, UP)
* Mandaluyong: 11.19 percent
* Makati: 8.92 percent
* Caloocan: 8.80 percent
* Marikina: 6.87 percent
...
* Manila: 0.89 percent
* Navotas: 0.47 percent (densely built reclamation)

Steepest 2019 to 2026 declines: Taguig -2.76pp, Malabon -1.54pp, Las Pinas -1.47pp, Valenzuela -1.39pp. Makati is the rare gainer at +1.69pp.

The 225 trees felled along Quirino Avenue in May 2026 for the SALEX expressway: they will eventually show in Hansen, but 30 m resolution misses sub-pixel events. The before/after canopy strip is in the demo: docs/demo/salex-timeline.gif.

Everything is open and reproducible:
https://github.com/xmpuspus/leaves-ph
https://leaves.ph

Code MIT. Data CC-BY-4.0. Cite as: Leaves.PH (2026-Q2), https://github.com/xmpuspus/leaves-ph.

---

## Image to attach

Primary: `docs/demo/hero.gif`
Alternative: per-LGU choropleth still or the SALEX before/after side-by-side

## Notes for posting

- Tone is a notch friendlier than LinkedIn (FB audience). Less technical.
- Tag: @ScienceKonek (PH science communication collective), @EarthJournalismNetwork
- Comment-thread responses ready: link to BENCHMARKS reconciliation table, link to methodology, link to the data downloads page
