# Privacy Impact Assessment

## Summary

Leaves.PH publishes administrative-level aggregates (per-LGU annual canopy statistics) derived from public-domain satellite imagery. Vegetation is not personal data under Republic Act 10173 (Data Privacy Act of 2012). No personal data is processed, stored, or published.

This PIA is short by design. Compare to SolarMap.PH which processes rooftop imagery at sub-building resolution and required a more thorough RA 10173 analysis. Leaves.PH is structurally different.

## Data sources

| Source | Type | Personal data? |
|---|---|---|
| Sentinel-2 L2A imagery | satellite optical | No. 10 m resolution; cannot identify individuals. |
| Hansen GFC v1.12 | derived raster, 30 m | No. Aggregate forest-loss classification. |
| ESA WorldCover v200 | derived raster, 10 m | No. Aggregate land-cover classification. |
| Dynamic World v1 | derived raster, 10 m | No. Aggregate per-pixel probability. |
| Meta Canopy Height v2 | derived raster, 1 m | No. Tree height only; no identifying features. |
| GEDI L2A | sparse lidar footprints | No. Forest structure metrics. |
| AlphaEarth Foundations V1 (optional) | learned embeddings, 10 m | No. Abstract numeric vectors. |
| PSA / OSM LGU polygons | administrative boundaries | No. Public boundaries. |

## Outputs

| Output | Granularity | Personal data risk |
|---|---|---|
| `data/per_lgu/per_lgu_canopy_2016_2026.csv` | per-LGU (17 polygons) per year | None. Administrative aggregates. |
| `site/public/data/per_lgu_canopy.geojson` | per-LGU choropleth | None. Same aggregates. |
| `docs/demo/*.gif` | satellite imagery overlays | None. 10 m resolution; no individuals identifiable. |
| `docs/demo/salex-timeline.gif` | 3.97 km road corridor | None. Trees only, no individuals. Tree-cut zone is already public via DENR-NCR statements and news coverage. |

## What we deliberately do not publish

- Per-building canopy attribution (single trees attached to specific private parcels).
- Backyard inventories.
- Photographs of identifiable people.
- Anything below 10 m granularity.

## Risk register

| Risk | Likelihood | Severity | Mitigation |
|---|---|---|---|
| Misinterpretation of "no canopy" as "no tree cutting permit" | Medium | Low | Public-record disclaimer in README, on site, in every BENCHMARKS row. |
| Spotlighting a specific private parcel via the salex-timeline GIF | Low | Low | Animation is at 10 m + 3.97 km corridor scale, not parcel-level. |
| Defamation suit on flagged 2016-2026 canopy decline | Low | Low | Project does not allege wrongdoing. The number is the number. |

## Contact

Privacy concerns: open a GitHub Security Advisory at https://github.com/xmpuspus/leaves-ph/security/advisories/new. Acknowledged within 5 working days.

## RA 10173 self-designated DPO

For v1.0, the project author (Xavier Puspus) is the self-designated Data Protection Officer. Given the project does not process personal data, formal National Privacy Commission registration is deferred.
