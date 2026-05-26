# Contributing to Leaves.PH

Thanks for considering a contribution. This repo welcomes:

1. **Verified per-LGU corrections** to `data/per_lgu/per_lgu_canopy_2019_2026.csv`. Open an issue with the LGU name, year, your alternative value, and the source.
2. **Per-barangay extensions** (push from 17 LGU polygons to 142 NCR barangays). See `docs/research/prior-work.md` section 5.5 for the verified barangay anchors.
3. **Region extensions** (Cebu, Davao, CDO, Iloilo). See `docs/methodology.md` for the LGU polygon and NDVI-threshold recipe.
4. **Methodology improvements** to the NDVI calibration against Meta canopy height. Open an issue first with the proposed change and a one-paragraph rationale.
5. **Code review and bug fixes** on anything in `pipeline/` or `leaves_ph/`.

## Dev setup

```bash
git clone https://github.com/xmpuspus/leaves-ph
cd leaves-ph
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
pip install pytest

# Authenticate Earth Engine (one-time; see docs/setup-gee.md)
earthengine authenticate

# Verify the deterministic build before changing anything.
make fetch         # pulls Sentinel-2 + Hansen + ESA + Dynamic World composites
make compute       # per-LGU canopy curves 2016-2026
make hash-verify   # asserts the per-LGU CSV sha256 matches the canonical
pytest tests/ -q
```

For the Astro site:

```bash
cd site
pnpm install
pnpm dev            # http://localhost:4321
pnpm typecheck      # must be clean before opening a PR
pnpm build          # production build, must succeed
```

## PR conventions

- Branch naming: `fix/<short-slug>`, `feat/<short-slug>`, `docs/<short-slug>`.
- One logical change per PR.
- If the change affects the per-LGU CSV, re-run `make hash-verify` and update `EXPECTED_HASH` in the Makefile if the hash legitimately moves.
- If the change affects animation frames, re-run `make animate` and frame-extract the GIFs for visual inspection.

## Testing expectations

| Change type | Required tests |
|---|---|
| New helper function | Pure-function test in `tests/test_<module>.py` |
| Bug fix | Regression test that fails on the broken code and passes after the fix |
| Pipeline behavior change | Manual rerun against cached composites + diff against prior CSV |
| Site UI change | `pnpm typecheck` clean and `pnpm build` succeeds; describe browser checks in the PR body |

Never silence a failing test by editing the assertion.

## Code style

- Python: 3.11+, `ruff format`, `ruff check`. No `bare except:` in committed code.
- TypeScript: strict mode, Astro 5, no `any` in new code unless cast at a library boundary.
- Markdown: no em-dashes. Use hyphens with spaces, commas, periods, or parentheses. Match the existing tone in `README.md`.

## Reporting a security issue

Do not open a public issue. Use the [GitHub Security Advisory form](https://github.com/xmpuspus/leaves-ph/security/advisories/new). See `SECURITY.md` for what is in scope.

## Code of conduct

This project follows the [Contributor Covenant 2.1](CODE_OF_CONDUCT.md). Be kind, ask before assuming, no harassment.
