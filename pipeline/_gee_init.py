"""Shared GEE init helper for Leaves.PH pipeline scripts.

Tries auth sources in order:

    1. Service account key at LEAVES_PH_EE_KEY (env var pointing to a JSON file).
    2. Service account key at <repo>/.ee-key.json (gitignored).
    3. Interactive credentials at ~/.config/earthengine/credentials.

Raises a clear error if none work. Re-import-safe: ee is only initialised once.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

import ee

REPO_ROOT = Path(__file__).resolve().parent.parent
NCR_BBOX = (120.9, 14.4, 121.15, 14.8)  # (min_lon, min_lat, max_lon, max_lat)
NCR_YEARS = tuple(range(2016, 2027))  # 2016..2026 inclusive, 11 years

_initialised = False


def init() -> None:
    """Initialise Earth Engine. Idempotent."""
    global _initialised
    if _initialised:
        return

    # Source 1: env-var-pointed service account key.
    env_key = os.environ.get("LEAVES_PH_EE_KEY")
    if env_key and Path(env_key).exists():
        _init_service_account(env_key)
        _initialised = True
        return

    # Source 2: repo-local service account key (.gitignored).
    repo_key = REPO_ROOT / ".ee-key.json"
    if repo_key.exists():
        _init_service_account(str(repo_key))
        _initialised = True
        return

    # Source 3: interactive credentials.
    interactive = Path.home() / ".config" / "earthengine" / "credentials"
    if interactive.exists():
        ee.Initialize()
        _initialised = True
        return

    raise RuntimeError(
        "Earth Engine not authenticated. Run `earthengine authenticate` for interactive "
        "auth, or place a service-account JSON at .ee-key.json (see docs/setup-gee.md)."
    )


def _init_service_account(key_path: str) -> None:
    with open(key_path) as f:
        key = json.load(f)
    credentials = ee.ServiceAccountCredentials(key["client_email"], key_path)
    ee.Initialize(credentials)


def ncr_geometry() -> "ee.Geometry":
    """NCR bounding box as an ee.Geometry.Rectangle."""
    init()
    return ee.Geometry.Rectangle(list(NCR_BBOX), proj="EPSG:4326", geodesic=False)
