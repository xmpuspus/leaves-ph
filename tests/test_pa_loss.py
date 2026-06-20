"""Protected-area forest-loss product checks (offline, against committed artifacts).

These run without Earth Engine: they assert the published CSV, map GeoJSON, and
summary JSON are internally consistent and within sane bounds, so a bad pipeline
run cannot ship silently.
"""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "protected_areas" / "pa_forest_loss.csv"
GEOJSON_PATH = ROOT / "site" / "public" / "data" / "pa_forest_loss.geojson"
SUMMARY_PATH = ROOT / "site" / "public" / "data" / "pa_forest_loss_summary.json"

# International overlay designations excluded to avoid double-counting (a site
# under more than one designation). The published set must contain none of these.
INTL_OVERLAY = {
    "ASEAN Heritage Park",
    "World Heritage Site (natural or mixed)",
    "Wetland of International Importance (Ramsar Site)",
}

REQUIRED_COLUMNS = {
    "rank",
    "site_id",
    "name",
    "desig",
    "iucn_cat",
    "status",
    "status_yr",
    "rep_area_ha",
    "area_ha",
    "forest2000_ha",
    "loss_ha",
    "pct_of_forest2000",
    "pct_of_pa",
}

pytestmark = pytest.mark.skipif(
    not CSV_PATH.exists(), reason="pa_forest_loss.csv not generated yet (run make compute-pa)"
)


@pytest.fixture(scope="module")
def rows() -> list[dict]:
    with CSV_PATH.open() as f:
        return list(csv.DictReader(f))


@pytest.fixture(scope="module")
def summary() -> dict:
    return json.loads(SUMMARY_PATH.read_text())


@pytest.fixture(scope="module")
def geojson() -> dict:
    return json.loads(GEOJSON_PATH.read_text())


def test_csv_has_required_columns(rows):
    assert rows, "CSV is empty"
    assert REQUIRED_COLUMNS.issubset(set(rows[0].keys()))


def test_national_pa_count_is_reasonable(rows):
    # 266 WDPA PH records minus 15 international overlays == 251 national designations.
    assert 200 <= len(rows) <= 266


def test_no_international_overlay_designations(rows):
    bad = [r["name"] for r in rows if r["desig"] in INTL_OVERLAY]
    assert not bad, f"international overlay designations leaked in: {bad[:3]}"


def test_loss_values_are_nonnegative_and_bounded(rows):
    for r in rows:
        loss = float(r["loss_ha"])
        area = float(r["area_ha"])
        assert loss >= 0
        # loss can never exceed the polygon area
        assert loss <= area + 1.0
        pct = r["pct_of_forest2000"]
        if pct not in ("", None):
            assert 0 <= float(pct) <= 100.0


def test_rows_sorted_worst_first_and_ranked(rows):
    losses = [float(r["loss_ha"]) for r in rows]
    assert losses == sorted(losses, reverse=True), "rows not sorted by loss_ha desc"
    ranks = [int(r["rank"]) for r in rows]
    assert ranks == list(range(1, len(rows) + 1)), "rank column is not 1..N"


def test_summary_matches_csv(rows, summary):
    assert summary["n_protected_areas"] == len(rows)
    assert summary["window_start"] == 2016
    assert summary["window_end"] == 2025
    assert summary["disclaimer"]
    # Headline total is the sum across national-designation records (international
    # overlays already excluded), so it equals the per-PA sum within rounding.
    dedup_sum = sum(float(r["loss_ha"]) for r in rows)
    total = float(summary["total_loss_ha"])
    assert 1_000 < total < 1_000_000
    assert abs(total - dedup_sum) <= max(2.0, dedup_sum * 0.001)


def test_worst_by_ha_is_actually_the_worst(rows, summary):
    top_csv = max(rows, key=lambda r: float(r["loss_ha"]))
    assert summary["worst_by_ha"][0]["name"] == top_csv["name"]


def test_geojson_consistent_with_csv(rows, geojson):
    feats = geojson["features"]
    # one feature per PA; a handful of tiny PAs over-simplify to a non-polygon
    # sliver and carry geometry: null (valid GeoJSON), so the table still lists them.
    assert len(feats) == len(rows)
    csv_ids = {r["site_id"] for r in rows}
    with_polygon = 0
    for f in feats:
        p = f["properties"]
        assert str(p["site_id"]) in csv_ids
        g = f["geometry"]
        if g is not None:
            assert g["type"] in ("Polygon", "MultiPolygon")
            with_polygon += 1
        for key in ("name", "desig", "loss_ha", "pct_of_forest2000"):
            assert key in p
    # the overwhelming majority must render on the map
    assert with_polygon >= len(feats) - 20
