# Leaves.PH pipeline targets.
# `make all` reproduces the per-LGU canopy CSV + animation frames from cached
# Sentinel-2 + Hansen + ESA + Dynamic World composites (no network).
# `make fetch` re-pulls from Google Earth Engine (requires earthengine auth).

PY := python3
PIPELINE := pipeline
ANIM := animation
DATA := data
SITE_DATA := site/public/data

# Per-LGU output (canonical hash gate target)
PER_LGU_CSV := $(DATA)/per_lgu/per_lgu_canopy_2019_2026.csv
PER_LGU_GEOJSON := $(SITE_DATA)/per_lgu_canopy.geojson

# Animation outputs
HERO_GIF := docs/demo/hero.gif
SALEX_GIF := docs/demo/salex-timeline.gif
LAMESA_GIF := docs/demo/la-mesa-watershed.gif
QUIRINO_GIF := docs/demo/quirino-avenue.gif
CHOROPLETH_GIF := docs/demo/lgu-choropleth.gif

.PHONY: all fetch compute calibrate animate verify hash hash-verify status test clean help \
        train scan release-build release-tag release-zenodo release-hf release release-smoke

help:
	@echo "Leaves.PH pipeline targets:"
	@echo "  make all          Full pipeline: fetch -> compute -> calibrate -> animate -> verify"
	@echo "  make fetch        Pull S2 + Hansen + ESA + Dynamic World + Meta from GEE (network)"
	@echo "  make compute      Per-LGU canopy curves 2016-2026 from cached composites"
	@echo "  make calibrate    Tune NDVI threshold against Meta canopy height v2"
	@echo "  make animate      Generate the 5 hero GIFs (hero, SALEX, La Mesa, Quirino, choropleth)"
	@echo "  make verify       Run scripts/verify_release.py (release gate)"
	@echo "  make hash         Print sha256 of $(PER_LGU_CSV)"
	@echo "  make hash-verify  Assert per-LGU CSV matches the canonical sha256"
	@echo "  make status       Print partial-state inventory (composites/per-LGU/GIFs timestamps)"
	@echo "  make test         Run the pytest suite"
	@echo "  make clean        Remove generated artifacts (keeps composites cache)"
	@echo "  make train        Run v2->v3 SolarMap-pattern training (basic head)"
	@echo "  make train-all    Run v2->v3->v4->v5->v6 full iteration chain (~30 min)"
	@echo "  make scan         Run v6 multi-year scan across all 8 epochs (~80 min)"
	@echo "  make release      Run the 7-step release pipeline (verify, build, tag, mint)"

all: $(PER_LGU_CSV) $(HERO_GIF)
	@echo
	@echo "[make all] DONE."
	@$(MAKE) -s hash-verify

# ----- fetch (network; GEE auth required) -----
fetch:
	$(PY) $(PIPELINE)/fetch_sentinel2_yearly.py
	$(PY) $(PIPELINE)/fetch_hansen.py
	$(PY) $(PIPELINE)/fetch_esa_worldcover.py
	$(PY) $(PIPELINE)/fetch_dynamic_world.py
	$(PY) $(PIPELINE)/fetch_meta_canopy_height.py
	$(PY) $(PIPELINE)/fetch_lgu_polygons.py
	@echo "[make fetch] DONE."

# ----- compute (per-LGU canopy 2016-2026) -----
$(PER_LGU_CSV): $(PIPELINE)/compute_canopy.py $(PIPELINE)/aggregate_lgu.py
	$(PY) $(PIPELINE)/compute_canopy.py
	$(PY) $(PIPELINE)/aggregate_lgu.py

compute: $(PER_LGU_CSV)
	@echo "[make compute] $(PER_LGU_CSV) ready"

$(PER_LGU_GEOJSON): $(PER_LGU_CSV) $(PIPELINE)/csv_to_geojson.py
	$(PY) $(PIPELINE)/csv_to_geojson.py

# ----- calibrate (NDVI threshold against Meta canopy height v2) -----
calibrate:
	$(PY) $(PIPELINE)/calibrate_ndvi_threshold.py

# ----- animate (5 hero GIFs) -----
$(HERO_GIF): $(ANIM)/generate_metro_manila_timeline.py
	$(PY) $(ANIM)/generate_metro_manila_timeline.py

$(SALEX_GIF): $(ANIM)/generate_salex_corridor.py
	$(PY) $(ANIM)/generate_salex_corridor.py

$(LAMESA_GIF): $(ANIM)/generate_la_mesa_watershed.py
	$(PY) $(ANIM)/generate_la_mesa_watershed.py

$(QUIRINO_GIF): $(ANIM)/generate_quirino_avenue.py
	$(PY) $(ANIM)/generate_quirino_avenue.py

$(CHOROPLETH_GIF): $(ANIM)/generate_per_lgu_choropleth.py $(PER_LGU_CSV)
	$(PY) $(ANIM)/generate_per_lgu_choropleth.py

animate: $(HERO_GIF) $(SALEX_GIF) $(LAMESA_GIF) $(QUIRINO_GIF) $(CHOROPLETH_GIF)
	@echo "[make animate] all 5 GIFs ready under docs/demo/"

# ----- verify (release gate) -----
verify:
	$(PY) scripts/verify_release.py

# ----- hash (per-LGU CSV is the deterministic-build canonical) -----
# EXPECTED_HASH gets pinned once the per-LGU CSV stabilises.
# Hash gets pinned once the per-LGU CSV stabilises.
EXPECTED_HASH := bcacdbc73b0c06c8

hash:
	@$(PY) -c "import hashlib, os; \
p='$(PER_LGU_CSV)'; \
print(p, 'sha256:', (hashlib.sha256(open(p,'rb').read()).hexdigest()[:16] if os.path.exists(p) else 'missing'))"

hash-verify: $(PER_LGU_CSV)
	@actual=$$($(PY) -c "import hashlib; print(hashlib.sha256(open('$(PER_LGU_CSV)','rb').read()).hexdigest()[:16])"); \
	expected="$(EXPECTED_HASH)"; \
	if [ "$$expected" = "PENDING" ]; then \
	  echo "[hash-verify] SKIP: canonical hash not yet pinned (unpinned-hash)"; \
	elif [ "$$actual" = "$$expected" ]; then \
	  echo "[hash-verify] OK: per_lgu_canopy_2019_2026.csv sha256 = $$actual"; \
	else \
	  echo "[hash-verify] FAIL: per_lgu_canopy_2019_2026.csv sha256 = $$actual (expected $$expected)"; \
	  echo "[hash-verify] Likely cause: dependency version drift. Check requirements.txt pins."; \
	  exit 1; \
	fi

status:
	@echo "Leaves.PH state inventory"
	@echo "  S2 composites        : $$(ls -1 $(DATA)/composites/*.tif 2>/dev/null | wc -l | tr -d ' ') tifs"
	@echo "  Hansen tiles         : $$(ls -1 $(DATA)/hansen/*.tif 2>/dev/null | wc -l | tr -d ' ') tifs"
	@echo "  ESA WC tiles         : $$(ls -1 $(DATA)/esa/*.tif 2>/dev/null | wc -l | tr -d ' ') tifs"
	@echo "  Meta canopy tiles    : $$(ls -1 $(DATA)/meta/*.tif 2>/dev/null | wc -l | tr -d ' ') tifs"
	@echo "  LGU polygons         : $$(test -f $(DATA)/lgu/ncr_lgu.geojson && echo 'present' || echo 'missing')"
	@echo "  per-LGU CSV          : $$(test -f $(PER_LGU_CSV) && stat -f '%Sm' -t '%Y-%m-%dT%H:%MZ' $(PER_LGU_CSV) 2>/dev/null || echo 'missing')"
	@echo "  per-LGU GeoJSON      : $$(test -f $(PER_LGU_GEOJSON) && stat -f '%Sm' -t '%Y-%m-%dT%H:%MZ' $(PER_LGU_GEOJSON) 2>/dev/null || echo 'missing')"
	@echo "  hero GIF             : $$(test -f $(HERO_GIF) && stat -f '%Sm' -t '%Y-%m-%dT%H:%MZ' $(HERO_GIF) 2>/dev/null || echo 'missing')"
	@echo "  SALEX GIF            : $$(test -f $(SALEX_GIF) && stat -f '%Sm' -t '%Y-%m-%dT%H:%MZ' $(SALEX_GIF) 2>/dev/null || echo 'missing')"

test:
	pytest tests/ -q

clean:
	rm -f $(PER_LGU_CSV) $(PER_LGU_GEOJSON)
	rm -f $(HERO_GIF) $(SALEX_GIF) $(LAMESA_GIF) $(QUIRINO_GIF) $(CHOROPLETH_GIF)
	rm -rf $(ANIM)/_scratch/

# ====================================================================
# Release pipeline (mirrors solar-map-ph release targets)
# ====================================================================

# ----- CLIP+LR + Ridge heads (SolarMap pattern, v2 -> v6) -----
train: train-v3
	@echo "[make train] clf_v3 ready (basic SolarMap-pattern head)"

train-v3:
	$(PY) detection/bootstrap/fetch_osm_tree_labels.py
	$(PY) detection/buildings/fetch_tiles.py
	$(PY) detection/train/build_dataset_v2.py
	$(PY) detection/train/train_v2.py
	$(PY) detection/train/build_dataset_v3.py
	$(PY) detection/train/train_v3.py

train-v4: train-v3 scan-v3
	$(PY) detection/train/build_dataset_v4.py
	$(PY) detection/train/train_v4.py

train-v5: train-v4
	$(PY) detection/train/train_v5_platt.py

train-v6:
	$(PY) detection/train/build_dataset_v6_regression.py
	$(PY) detection/train/train_v6_regressor.py

train-all: train-v3 scan-v3 train-v4 train-v5 train-v6
	@echo "[make train-all] v2 -> v6 chain complete"

scan: scan-v6 finalize-v6
	@echo "[make scan] multi-year v5+v6 outputs ready + BENCHMARKS updated"

finalize-v6:
	$(PY) scripts/finalize_v6_series.py

scan-v3:
	$(PY) detection/scan/ncr_scan.py
	@echo "[make scan-v3] detection/scan/validation_v3/ + clf_v3_probs_2024.tif ready"

scan-v6:
	$(PY) detection/scan/multi_year_scan.py
	@echo "[make scan-v6] detection/scan/clf_v6_density_<year>.tif + clf_v6_ncr_series.csv ready"

# ----- 7-step release playbook -----
# 1. verify (release gate)
# 2. hash-verify (canonical CSV deterministic)
# 3. release-build (Astro static)
# 4. release-tag (git tag, push)
# 5. release-zenodo (DOI mint; manual; prints upload steps)
# 6. release-hf (publish to HuggingFace)
# 7. release-smoke (post-deploy fingerprint)

VERSION := $(shell $(PY) -c "import re,pathlib; m=re.search(r'__version__\s*=\s*[\"\\']([\\d.]+)', pathlib.Path('leaves_ph/__init__.py').read_text()); print(m.group(1) if m else 'unknown')")

release-build:
	@echo "[release-build] version=$(VERSION)"
	cd site && pnpm install --frozen-lockfile && pnpm build
	@echo "[release-build] site/dist/ ready"

release-tag:
	@if [ -z "$$(git status --porcelain)" ]; then \
	  git tag -a v$(VERSION) -m "Leaves.PH v$(VERSION)" 2>&1 || echo "[release-tag] tag v$(VERSION) exists; skipping"; \
	  echo "[release-tag] To push: git push origin v$(VERSION)"; \
	else \
	  echo "[release-tag] FAIL: working tree dirty. Commit before tagging."; exit 1; \
	fi

release-zenodo:
	@echo "[release-zenodo] DOI mint is manual; follow:"
	@echo "  1. Zip data/per_lgu/, BENCHMARKS.md, MODEL_CARD.md, detection/train/clf_v3.joblib"
	@echo "  2. Upload to https://zenodo.org/deposit"
	@echo "  3. Tag the deposit v$(VERSION); update CITATION.cff with the DOI after mint"

release-hf:
	@if [ -z "$$HUGGINGFACE_HUB_TOKEN" ]; then \
	  echo "[release-hf] FAIL: HUGGINGFACE_HUB_TOKEN not set"; exit 1; \
	fi
	$(PY) scripts/publish_to_huggingface.py --version $(VERSION)

release-smoke:
	@$(PY) -c "import urllib.request; \
url='https://leaves.ph'; \
print(f'[smoke] fetching {url}'); \
r=urllib.request.urlopen(url, timeout=30); \
b=r.read().decode('utf-8','replace'); \
ok='Leaves.PH' in b and 'NDVI' in b; \
print('[smoke] HTTP', r.getcode()); \
print('[smoke] title check:', 'Leaves.PH' in b); \
print('[smoke] method check (NDVI):', 'NDVI' in b); \
import sys; sys.exit(0 if ok else 1)"

release: verify hash-verify release-build release-tag release-zenodo
	@echo
	@echo "[release] v$(VERSION) reached step 5/7."
	@echo "  Step 6 (release-hf) requires HUGGINGFACE_HUB_TOKEN"
	@echo "  Step 7 (release-smoke) runs after the deploy is live"
	@echo "  Push tag: git push origin v$(VERSION)"
