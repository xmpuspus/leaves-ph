# Leaves.PH

Tree cover for Metro Manila, measured from satellite imagery. Annual per-LGU values from 2019 to 2026 for the 17 LGUs of the National Capital Region (16 cities plus the municipality of Pateros). Inputs, method, and outputs are open and reproducible from a clean clone.

[![License: MIT (code) / CC-BY-4.0 (data)](https://img.shields.io/badge/license-MIT%20%2F%20CC--BY--4.0-blue.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](https://www.python.org/downloads/)
[![Status](https://img.shields.io/badge/status-alpha-orange.svg)](README.md)

![Sentinel-2 RGB basemap with canopy density overlay 2019 to 2026](docs/demo/remaining-canopy-satellite.gif)

Live site: [leaves.ph](https://leaves.ph).

## What it measures

For each year, what fraction of each LGU's area is covered by tree canopy taller than 5 m. Two layers stack on top of each other:

1. **NDVI baseline (v0).** Per Sentinel-2 pixel: is the spectral signature green enough to be canopy? A single threshold (NDVI > 0.62) decides yes/no, calibrated against Meta v2's 1m canopy-height reference at heights above 5m.
2. **CLIP + Ridge head (v6 to v9).** A second pass that looks at each 240m tile via CLIP image embeddings and predicts canopy fraction in [0, 1] with a regression head. Trained the same way [SolarMap.PH](https://github.com/xmpuspus/solar-map-ph) was built. Both layers are published; per-LGU canopy hectares can be computed from either.

Headline number: NCR area-weighted canopy = **7.46%** in 2026 (v0 NDVI), **8.40%** (v9 CLIP+HistGBR). 2026 is provisional (imagery Jan-May). The two layers agree at NCR level; per-LGU they diverge in expected ways (the regression head compresses toward the mean).

| LGU | 2026 canopy % (v0 NDVI) | 2019 → 2026 Δ (pp) |
|---|---|---|
| Quezon City | 18.93 | −0.38 |
| Mandaluyong | 11.19 | −0.28 |
| Makati | 8.92 | +1.69 |
| Caloocan | 8.80 | −0.96 |
| Marikina | 6.87 | −0.01 |
| ... | ... | ... |
| Manila | 0.89 | +0.21 |
| Navotas | 0.47 | −0.40 |

Full series, per-LGU table, model progression, and adjacent published estimates: [`BENCHMARKS.md`](BENCHMARKS.md).

## What you can do with it

- Read the per-LGU canopy series for all 17 NCR LGUs at [`data/per_lgu/per_lgu_canopy_2019_2026.csv`](data/per_lgu/per_lgu_canopy_2019_2026.csv). The CSV is hash-pinned; `make hash-verify` confirms a clean reproduction.
- Browse the interactive map at [leaves.ph/map](https://leaves.ph/map). It carries an OSM/satellite basemap, a 1m Meta canopy raster overlay, 242k individual tree-crown polygons coloured by source (OSM-confirmed / tall canopy / candidate), and a year slider.
- Inspect any model-detected tree: click a crown polygon and the popup shows an Esri aerial of that exact location plus the polygon's metadata (status, area, p50/p95 height).
- Re-run the pipeline on a different city. The Cebu City proof in `pipeline/fetch_cebu_proof.py` shows the same pipeline run end-to-end against a different bbox, with no NCR-specific retraining.

## What it is not

- Not a competing global forest model. Uses Hansen GFC, ESA WorldCover, Dynamic World, and Meta Canopy Height verbatim and stacks them.
- Not a per-tree census. A 30m Sentinel-2 pixel can contain a few small trees or none; the per-crown polygons in `tree_crowns_ncr_tagged.pmtiles` are derived from a 5m-tall canopy mask, not from individual tree detections.
- Not a permit-compliance tool. The pipeline computes canopy fractions from public-record satellite imagery. Specific allegations of unpermitted cutting require independent investigation.
- Not a measurement of every tree. Sub-pixel canopy (street trees in a building shadow, hedges, recently-planted seedlings) sits below the model's resolution floor.

## Adjacent published estimates

Listed for methodology context, not as a ranking. Definitions differ across sources (canopy fraction vs closed-canopy area, % vs hectares, single-epoch vs multi-year baseline).

| Source | Year | Method | NCR canopy |
|---|---|---|---|
| Meta v2 (canopy height > 5m) | 2018-2020 | 1m AI canopy-height regression | 7.5% |
| ESA WorldCover v200 (class 10) | 2021 | 10m land-cover classification | 13.38% |
| DENR FMB (cited in news / EJN) | 2024+ | not specified in public docs found | 6.0% |
| Global Forest Watch dashboard PHL/47 | 2020 baseline | Hansen 30m tree-cover ≥ 30% canopy | 4.0% |
| Earth Journalism Network | 2020 | DENR "open forest" sub-class | 2,071 ha |
| ScienceKonek 2024 map | 2024 | raster + methodology not publicly findable | unknown |

## Reproduce locally

Requires Python 3.11+, ~2 GB of disk for cached composites, and one-time Google Earth Engine + AWS-Open-Data authentication.

```bash
git clone https://github.com/xmpuspus/leaves-ph
cd leaves-ph
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
earthengine authenticate     # one-time browser flow

make fetch                   # pull S2 + Hansen + ESA + Dynamic World + Meta (~30 min, network)
make compute                 # per-LGU canopy series 2019-2026 from cached composites
make calibrate               # tune the NDVI threshold against Meta canopy height
make train                   # CLIP+LR v2 → v3 → v4 → v5 → v6 (optional, ~30 min on M-series GPU)
make scan                    # multi-year v9 density rasters + per-LGU + per-barangay CSVs
make verify                  # 27-check release gate (must return all PASS)
make hash                    # sha256 prefix of the canonical per-LGU CSV
```

If the GEE pull is skipped, `make compute` reads cached composites from `data/composites/`. The 17 LGU canopy curves drop into `data/per_lgu/per_lgu_canopy_2019_2026.csv` and the static site reads from `site/public/data/per_lgu_canopy.geojson`.

## Methodology

Full version: [`docs/methodology.md`](docs/methodology.md). [`MODEL_CARD.md`](MODEL_CARD.md) documents intended use, known biases, and the v0 → v9 model progression. [`BENCHMARKS.md`](BENCHMARKS.md) carries every CV F1, MAE, R², per-bin residual, per-LGU table, and multi-year scan result.

Short version: pull annual Sentinel-2 L2A median composites over the NCR bbox, mask clouds with s2cloudless, compute NDVI, threshold at a value calibrated against Meta v2. On top of that, train a CLIP+LR head per the SolarMap pattern (OSM bootstrap → ESA WorldCover teacher → Meta-oracle active learning → Platt calibration → continuous canopy-fraction regression). Aggregate per LGU and per barangay from PSA / OSM admin boundaries.

## Data products

Published under `site/public/data/` and `data/per_lgu/` (CC-BY-4.0):

| File | Schema | Notes |
|---|---|---|
| `data/per_lgu/per_lgu_canopy_2019_2026.csv` | (lgu_name, year, canopy_ha, canopy_pct, total_ha) | 17 × 8 = 136 rows; hash-pinned |
| `site/public/data/per_lgu_canopy.geojson` | one feature per LGU; props = canopy_<year>_pct + canopy_<year>_ha | derived from the CSV |
| `data/per_barangay/per_barangay_canopy_2019_2026.csv` | (barangay, lgu_name, canopy_pct_v6_<year> × 8, canopy_ha × 8) | 892 OSM admin-level=10 polygons inside NCR |
| `data/per_barangay/per_barangay_canopy_2019_2026_v9.csv` | same schema; v9 multi-epoch GBR predictions | 892 barangays |
| `site/public/data/tree_crowns_ncr_tagged.pmtiles` | 242,810 crown polygons; status ∈ {confirmed, new, candidate} | the map's vector layer |
| `detection/scan/clf_v9_density_<year>.tif` | continuous canopy density 0..1 per pixel | one per year 2019-2026 |
| `detection/scan/clf_v9_ncr_series.csv` | (year, ncr_canopy_pct_v9, ncr_canopy_ha_v9, ncr_total_ha) | the 8-year v9 series |
| `detection/scan/validation_v3/*.png` | per-LGU visual validation panels | 17 panels showing v0 vs v3 |

## Roadmap

- Per-barangay extension shipped at 892 OSM polygons; mapping them onto the PSA barangay roster is the next data-engineering step.
- Cebu City proof shipped (`pipeline/fetch_cebu_proof.py`, `detection/scan/scan_cebu.py`). Davao, Iloilo, Cagayan de Oro are the next regional rollouts.
- S2 10m chunked exports for a precision lift (v11 proof on a QC subset shows R² 0.36 → 0.53 over the same 240m physical window).
- GEDI L2A monthly RH98 spot truth for per-epoch calibration (currently the NDVI threshold is calibrated to a single ~2019 Meta-derived truth and applied uniformly).

## License and attribution

Code: MIT (see [`LICENSE`](LICENSE)). Data products: CC-BY-4.0.

Attribution when redistributing the data: *Leaves.PH (2026), Sentinel-2 2019-2026 (2026 provisional), https://github.com/xmpuspus/leaves-ph*.

Required upstream attribution line:
*Imagery contains modified Copernicus Sentinel data 2019-2026 processed by ESA. Tree-cover-loss layer: Hansen et al. 2013 via Global Forest Watch. Land cover: ESA WorldCover v200 (CC-BY-4.0) and Google Dynamic World v1. Canopy height: Meta AI / Land & Carbon Lab Global Canopy Height v2 (CC-BY-4.0). Administrative boundaries: OpenStreetMap contributors and Philippine Statistics Authority.*

## Citation

```bibtex
@software{puspus_leaves_ph_2026,
  author = {Puspus, Xavier},
  title  = {{Leaves.PH: an open-source tree-cover measurement series for Metro Manila}},
  year   = {2026},
  url    = {https://github.com/xmpuspus/leaves-ph}
}
```

[`CITATION.cff`](CITATION.cff) is the machine-readable form. A versioned Zenodo DOI is minted at each tagged release.

## Public-record disclaimer

All inputs are public-record satellite imagery and public administrative boundaries. The pipeline computes per-LGU and per-barangay canopy fractions from canonical global datasets. Specific allegations of unpermitted tree cutting, if any, require independent investigation and corroboration. Vegetation visible from public-domain satellites is not personal data under Republic Act 10173.

## Contact and corrections

LGU value corrections, missing barangays, methodological questions: open a GitHub issue at https://github.com/xmpuspus/leaves-ph/issues.

If you believe a published artefact identifies a specific private individual or violates RA 10173, file a private advisory at https://github.com/xmpuspus/leaves-ph/security/advisories/new. Acknowledged within 5 working days.
