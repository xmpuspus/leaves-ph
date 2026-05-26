# Leaves.PH

Open-source tree-cover validation for Metro Manila. Validates the four 2024+ NCR canopy figures in public circulation (DENR FMB "6 percent / 3,565 ha", GFW "2.3 kha / 4.0 percent", EJN "open forest 2,071 ha 2020", ScienceKonek 2024 map) against fresh 2026 Sentinel-2, Hansen Global Forest Change, ESA WorldCover, Dynamic World, and Meta Canopy Height data, broken down per LGU for the 17 NCR LGUs (16 cities plus the municipality of Pateros).

[![License: MIT (code) / CC-BY-4.0 (data)](https://img.shields.io/badge/license-MIT%20%2F%20CC--BY--4.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](README.md)

![NCR canopy 2019 to 2026](docs/demo/hero.gif)

## Headline

**NCR canopy 2026 = 7.46 percent.** Validates DENR's cited 6 percent (we measure +1.46pp above). Refutes GFW's 4.0 percent dashboard figure (+3.46pp above ours). Within 0.04pp of Meta's independent v2 ground-truth (canopy height greater than 5 m, 2018-2020 epoch). ScienceKonek 2024 map not publicly findable; EJN "open forest" 2,071 ha is a different definition.

Per-LGU 2026: Quezon City 18.93% (top), Mandaluyong 11.19%, Makati 8.92%, Caloocan 8.80%, ..., Manila 0.89%, Navotas 0.47% (bottom). 2019 to 2026 deltas range from +1.69pp (Makati) to -2.76pp (Taguig).

Full curve, reconciliation table, per-LGU rankings, Hansen cumulative loss per LGU: see [`BENCHMARKS.md`](BENCHMARKS.md).

## Demo

- [`docs/demo/hero.gif`](docs/demo/hero.gif) - NCR-wide 2019 to 2026 canopy timeline, OSM basemap + Sentinel-2 NDVI overlay.
- [`docs/demo/lgu-choropleth.gif`](docs/demo/lgu-choropleth.gif) - per-LGU choropleth animation, shaded by canopy %.
- [`docs/demo/la-mesa-watershed.gif`](docs/demo/la-mesa-watershed.gif) - NE NCR green zone (QC + Marikina), 24-28 percent canopy.
- [`docs/demo/salex-timeline.gif`](docs/demo/salex-timeline.gif) - Quirino Avenue / SALEX corridor (where 225 trees were felled May 2026).
- [`docs/demo/quirino-avenue.gif`](docs/demo/quirino-avenue.gif) - Quirino Avenue close-up, the strip Inquirer / PhilStar coverage centred on.

## What this is

- A reproducible pipeline that pulls Sentinel-2 L2A, Hansen GFC v1.13, ESA WorldCover v200, Dynamic World v1, and Meta Canopy Height v2 for the NCR bounding box and computes a per-LGU annual canopy curve from 2019 to 2026.
- An honest reconciliation of the four official 2024+ NCR canopy figures that disagree with each other (see "First finding" below).
- A SALEX corridor before-and-after timelapse covering the 225 trees felled along Quirino Avenue in May 2026.
- An interactive Astro + MapLibre site at https://leaves.ph.

## What this is not

- Not a competing global forest model. We use Hansen, ESA WorldCover, Dynamic World, and Meta verbatim and stack them.
- Not a per-household measurement. Publishes per-LGU only (17 polygons: 16 NCR cities + Pateros). Per-barangay (142 polygons) is on the roadmap.
- Not 2026 ground truth. Meta Canopy Height v2 is mostly sourced from 2018 to 2020 imagery, so our calibration layer is a ~2019 truth, not a 2026 truth. The methodology footnote documents this.
- Not an investigative tool. Vegetation loss flagged here may have a permit, an ECC, or a legitimate reason. We compute the canopy delta; we do not allege wrongdoing.

## The four public 2024+ NCR canopy figures disagree

| Source | Headline | Date | Reproducibility |
|---|---|---|---|
| DENR FMB (cited in news) | 6 percent / 3,565 ha total tree cover | 2024+ | source document not in public 2024+ reports |
| Global Forest Watch dashboard | 2.3 kha natural forest / 4.0 percent of land area | 2020 baseline | https://www.globalforestwatch.org/dashboards/country/PHL/47/ |
| Earth Journalism Network 2024 (DENR-sourced) | "Open forest" 2,790 ha to 2,071 ha 2020 | Oct 2024 | https://earthjournalism.net/stories/blazing-heat-of-2024-ignites-filipinos-need-for-trees-and-green-spaces |
| ScienceKonek 2024 map | (referenced by RadarPH, May 2026) | 2024 | map artifact not publicly findable; possibly Facebook-only |

DENR and GFW disagree by roughly 50 percent for the same area. Leaves.PH publishes a fifth, fully reproducible 2026 number from canonical Sentinel-2 + Hansen + Dynamic World, and explains where each prior figure agrees and disagrees with the new measurement.

## Quickstart

```bash
git clone https://github.com/xmpuspus/leaves-ph
cd leaves-ph
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# One-time Google Earth Engine auth (browser flow)
earthengine authenticate

# Reproduce the full pipeline (requires ~30 min of GEE quota for the first run)
make fetch         # pull S2 + Hansen + ESA + Dynamic World + Meta composites
make compute       # per-LGU canopy curves 2019-2026
make calibrate     # NDVI threshold tuned against Meta canopy height v2
make animate       # generate the 5 hero GIFs
make verify        # release gate (must return N PASS / 0 FAIL)
```

If `make fetch` is skipped, `make compute` runs against the cached composites under `data/`. The 17 LGU canopy curves drop into `data/per_lgu/per_lgu_canopy_2019_2026.csv` and the Astro site reads from `site/public/data/per_lgu_canopy.geojson`.

## Methodology

Full methodology in `docs/methodology.md`. One-paragraph version:

For each year 2019 to 2026, we pull a median Sentinel-2 L2A composite over the NCR bbox (longitude 120.9 to 121.15, latitude 14.4 to 14.8), mask clouds with s2cloudless, compute NDVI per pixel, and threshold at a value tuned against Meta Canopy Height v2 (target: greater than 90 percent agreement with Meta pixels above 5 m). We cross-check the 2021 result against ESA WorldCover class 10 and ground long-term loss context against Hansen GFC v1.13 `lossyear`. Per-LGU statistics come from PSA / OSM administrative polygons via `pipeline/aggregate_lgu.py`. The full prior-work and tool survey is in `docs/research/prior-work.md`.

## Data products published

All under `site/public/data/` (CC-BY-4.0):

| File | Schema | Cadence |
|---|---|---|
| `per_lgu_canopy.geojson` | one polygon per LGU; properties = canopy_ha + canopy_pct per year | annual 2019-2026 |
| `per_lgu_canopy_timeseries.json` | one row per (LGU, year) | annual 2019-2026 |
| `hansen_loss_ncr.geojson` | Hansen `lossyear` raster cropped to NCR, polygonized | one-shot snapshot |
| `salex_corridor.geojson` | SALEX route polygon + 225-tree-fell zone | one-shot snapshot |

## Reproducibility

```bash
docker build -t leaves-ph:latest .
docker run leaves-ph:latest make hash
```

`make hash` prints the sha256 prefix of `data/per_lgu/per_lgu_canopy_2019_2026.csv`. The canonical hash is pinned in the Makefile (`EXPECTED_HASH`) and asserted in CI. If your build produces a different hash, your pinned dependencies have drifted; reinstall from `requirements.txt`.

Until the canonical hash is pinned, `EXPECTED_HASH=PENDING` and `make hash-verify` is a SKIP, not a FAIL.

## Roadmap

- Per-barangay extension (142 NCR barangays).
- Cebu / Davao / CDO regional rollout (same pipeline, different LGU polygon set).
- TESSERA backfill comparison once full PH historical tiles are available.
- AlphaEarth Foundations + sklearn calibrated head as a comparison artifact.

## License and attribution

Code: MIT (see `LICENSE`).
Data products under `site/public/data/` and `data/per_lgu/`: CC-BY-4.0.

Attribution required when redistributing the data: "Leaves.PH (YYYY-Q-N), https://github.com/xmpuspus/leaves-ph".

Upstream sources cited in `LICENSE`. The mandatory attribution line on the site map:
"Imagery contains modified Copernicus Sentinel data 2019-2026 processed by ESA. Tree-cover-loss layer: Hansen et al. 2013 via Global Forest Watch. Land cover: ESA WorldCover v200 (CC-BY-4.0) and Google Dynamic World v1. Canopy height: Meta AI / Land & Carbon Lab Global Canopy Height v2 (CC-BY-4.0). Administrative boundaries: OpenStreetMap contributors and Philippine Statistics Authority."

## Citation

```bibtex
@software{puspus_leaves_ph_2026,
  author = {Puspus, Xavier},
  title = {{Leaves.PH: open-source tree-cover validation for Metro Manila}},
  year = {2026},
  url = {https://github.com/xmpuspus/leaves-ph}
}
```

See `CITATION.cff` for the machine-readable form. Zenodo DOI added at first tagged release.

## Public-record disclaimer

All inputs are public-record satellite imagery and administrative boundaries. This tool computes per-LGU canopy statistics from canonical global datasets. Specific allegations of unpermitted tree cutting, if any, require independent investigation and corroboration. Vegetation visible from public-domain satellites is not personal data under Republic Act 10173.

## Contact and takedown

Issues, false-positive reports, LGU corrections: open a GitHub issue at https://github.com/xmpuspus/leaves-ph/issues.

If you believe a published artifact identifies a specific private individual or violates RA 10173, file a private advisory at https://github.com/xmpuspus/leaves-ph/security/advisories/new. Acknowledged within 5 working days.
