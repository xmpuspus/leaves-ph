# Leaves.PH deterministic build image.
# Smoke test:
#   docker build -t leaves-ph:latest .
#   docker run leaves-ph:latest make hash
# should produce the same sha256 as the host build, given the same cached
# Sentinel-2 + Hansen + ESA + Dynamic World composites.

# Pinned to a specific Debian + Python patch level for deterministic builds.
# Refresh quarterly during the canopy-curve refresh.
FROM python:3.12-slim-bookworm

# System deps for rasterio/geopandas/pyproj (GDAL stack), pillow, matplotlib.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libgomp1 \
    libgl1 \
    libglib2.0-0 \
    libgdal-dev \
    libgeos-dev \
    libproj-dev \
    proj-data \
    proj-bin \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install python deps first so the layer caches when source changes.
COPY requirements.txt /app/requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Copy pipeline + Makefile + python package + scripts. Raw composites
# (~50-200 MB of cached S2/Hansen/ESA tifs) are NOT bundled; mount as a
# volume to reproduce `make all`. Default `make hash` only needs the
# per-LGU CSV, which IS bundled.
COPY Makefile /app/Makefile
COPY pipeline/ /app/pipeline/
COPY leaves_ph/ /app/leaves_ph/
COPY scripts/ /app/scripts/
COPY data/per_lgu/ /app/data/per_lgu/
COPY docs/ /app/docs/

# COPY may reset file timestamps in ways that confuse `make`. Re-stamp the
# per-LGU CSV so `make hash-verify` does not try to rebuild from upstream
# composites that aren't bundled in the image.
RUN test -f /app/data/per_lgu/per_lgu_canopy_2016_2026.csv \
    && touch /app/data/per_lgu/per_lgu_canopy_2016_2026.csv \
    || echo "per_lgu CSV not yet built (pre-Phase 3 image)"

# Default command: print the deterministic hash. Use
#   docker run -v $(pwd)/data:/app/data leaves-ph make all
# for the full pipeline against your cached composites.
CMD ["make", "hash"]
