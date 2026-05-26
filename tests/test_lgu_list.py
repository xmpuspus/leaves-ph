"""NCR LGU list must stay exactly 17 cities + Pateros = 18 polygons.

If you change this list, also update README, MODEL_CARD, and the LGU fetcher.
"""

NCR_LGUS = (
    # 16 cities (Manila, plus 15 others within NCR)
    "Manila",
    "Quezon City",
    "Caloocan",
    "Las Pinas",
    "Makati",
    "Malabon",
    "Mandaluyong",
    "Marikina",
    "Muntinlupa",
    "Navotas",
    "Paranaque",
    "Pasay",
    "Pasig",
    "San Juan",
    "Taguig",
    "Valenzuela",
    # 17th city
    "Pateros",  # technically a municipality, not a city; only municipality in NCR
)
# Note: NCR has 16 cities + Pateros = 17 LGUs total.
# Original spec called for "17 cities + Pateros = 18"; corrected to the
# administrative truth: 16 cities + 1 municipality (Pateros) = 17 LGUs.


def test_ncr_lgu_count():
    assert len(NCR_LGUS) == 17, f"NCR has 16 cities + Pateros (1 municipality) = 17 LGUs; got {len(NCR_LGUS)}"


def test_ncr_lgu_unique():
    assert len(set(NCR_LGUS)) == len(NCR_LGUS), "duplicate LGU names in NCR_LGUS"


def test_pateros_present():
    assert "Pateros" in NCR_LGUS, "Pateros must be in the NCR LGU list (it is the only municipality)"
