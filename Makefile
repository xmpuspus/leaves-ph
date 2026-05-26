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

.PHONY: all fetch compute calibrate animate verify hash hash-verify status test clean help

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
# EXPECTED_HASH is updated in tandem with the canonical CSV in CHANGELOG.md.
# v0.1.0: hash is empty (no CSV exists yet); first real value set at v0.9 freeze.
EXPECTED_HASH := PENDING_PHASE_3

hash:
	@$(PY) -c "import hashlib, os; \
p='$(PER_LGU_CSV)'; \
print(p, 'sha256:', (hashlib.sha256(open(p,'rb').read()).hexdigest()[:16] if os.path.exists(p) else 'missing'))"

hash-verify: $(PER_LGU_CSV)
	@actual=$$($(PY) -c "import hashlib; print(hashlib.sha256(open('$(PER_LGU_CSV)','rb').read()).hexdigest()[:16])"); \
	expected="$(EXPECTED_HASH)"; \
	if [ "$$expected" = "PENDING_PHASE_3" ]; then \
	  echo "[hash-verify] SKIP: canonical hash not yet pinned (pre-Phase 3)"; \
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
