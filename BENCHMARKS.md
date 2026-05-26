# Benchmarks

Status: placeholder. Real numbers land at v0.9 freeze. The structure mirrors `solar-map-ph/BENCHMARKS.md`.

## Headline (v1.0 target)

| Slice | Metric | Value |
|---|---|---|
| All-NCR 2026 canopy | percent of land area | TBD |
| All-NCR 2026 canopy | total ha | TBD |
| Per-LGU MAE vs Meta calibration | mean absolute error | TBD |
| Per-LGU MAE vs Meta calibration | worst LGU | TBD |
| 2021 cross-check vs ESA WorldCover | per-LGU correlation | TBD |
| GEDI spot-truth (300 pts) | percent agreement | TBD |

## Reconciliation against published 2024+ NCR figures

| Source | Their headline | Our 2026 measurement | Delta | Status |
|---|---|---|---|---|
| DENR FMB (cited in EJN/news) | 6 percent / 3,565 ha | TBD | TBD | source document not in public 2024+ reports |
| Global Forest Watch dashboard | 2.3 kha (4.0 percent) | TBD | TBD | reproduced from GFW dashboard PHL/47 |
| EJN 2024 "open forest" | 2,071 ha (2020) | TBD | TBD | DENR open-forest sub-category, different definition |
| ScienceKonek 2024 map | (artifact not publicly findable) | TBD | n/a | possibly Facebook-only |

## Verified per-LGU anchors (from EJN October 2024 / Google EIE)

| Anchor | EJN 2024 figure | Our 2026 measurement | Delta |
|---|---|---|---|
| Muntinlupa per-capita tree cover | 14.4 sq m / capita | TBD | TBD |
| Quezon City per-capita tree cover | 12.5 sq m / capita | TBD | TBD |
| Quezon City canopy (Google EIE) | 33 percent | TBD | TBD |
| Escopa IV (QC barangay) | 1.48 percent (lowest of 142 MM barangays) | v1.1 (per-barangay) | n/a |

## La Mesa watershed regrowth (Estoque 2018)

| Period | Estoque 2018 | Our measurement |
|---|---|---|
| 1988-2002 | net loss 259 ha | n/a (pre-Sentinel-2) |
| 2002-2016 | net gain 557 ha | TBD |
| 2016-2026 | not measured | TBD (this is our delta) |

## What we have not measured (yet)

- **Per-barangay breakdown for all 142 NCR barangays.** v1.1 scope. Polygons exist on OSM but require name reconciliation (lesson from SolarMap v1.1 LGU-OSM-relation mismatches).
- **TESSERA backfill comparison.** TESSERA reports 8.88 m RMSE on Borneo canopy vs AlphaEarth ~16 m. Once full PH historical TESSERA tiles ship (post-2024), we will re-run the optional Phase 4 head against TESSERA and pick the winner.
- **Per-canopy-class (primary forest vs plantation vs urban tree)** breakdown. Hansen + ESA + Dynamic World do not distinguish these cleanly.
- **2027+ SALEX impact.** Hansen at 30 m may not capture the 225-tree SALEX corridor until the 2027 v1.13+ refresh.

## Reproducing these numbers

```bash
pip install -r requirements.txt
make fetch          # GEE auth required; ~30 min
make compute        # deterministic from cached composites
make verify         # release gate
make hash           # print sha256 of per_lgu_canopy_2016_2026.csv
```

If your numbers differ, run `make hash-verify` first to confirm you have the canonical CSV.
