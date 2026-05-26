# Security Policy

## Reporting a vulnerability

Open a private security advisory via the GitHub Security tab:
https://github.com/xmpuspus/leaves-ph/security/advisories/new

Do not open a public issue. Acknowledged within 5 working days.

## In scope

- Code execution via crafted inputs to any script in `pipeline/`, `animation/`, or `detection/`.
- Cross-site scripting on `leaves.ph` or any deployed preview.
- CSP bypass on the site.
- Path traversal in the composite-cache lookup paths.
- Supply-chain issues against the pinned dependencies in `requirements.txt`.

## Out of scope

- Vulnerabilities in third-party services we call (Google Earth Engine, Copernicus, AWS Open Data, OpenStreetMap). Report to the upstream operator.
- Social engineering, phishing, physical attacks.

## Known-safe-by-design surfaces

- The site runs entirely client-side. No backend session, no user authentication, no PII collected.
- Earth Engine credentials run locally with a service-account key. The key never enters Vercel, never enters git history. `.gitignore` blocks the common naming patterns; `.dockerignore` blocks the same.

## joblib / pickle deserialization

If a calibrated-head classifier is shipped, `pipeline/recalibrate.py` accepts a `--clf` argument that is passed directly to `joblib.load`. `joblib.load` is built on Python's pickle module, which executes arbitrary code during deserialization.

**Only run `joblib.load` against classifier files you trust.** Any shipped `clf_leaves_v*.joblib` is verifiable via `make hash-verify`. If you fork the repo and someone sends you a classifier file, verify its sha256 against a known-good source before invoking any `make` target that loads it.

## Data publication boundaries

The published per-LGU canopy CSV and the per-LGU choropleth GeoJSON contain administrative-boundary aggregates only. No personal data, no per-building information, no household-level inference. Vegetation is not personal data under RA 10173.

If you observe a feature in any published artifact that you believe identifies a private individual, open an advisory immediately.
