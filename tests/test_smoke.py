"""Smoke tests: package imports cleanly, version string is sane, API stubs raise.

These tests must pass at every commit, including the v0.1.0 scaffold.
"""

import re

import pytest


def test_version_is_pep440():
    """__version__ should follow PEP 440 (e.g. '0.1.0', '1.2.3rc1')."""
    from leaves_ph import __version__

    assert re.match(r"^\d+\.\d+\.\d+(?:[abc]\d+|rc\d+)?$", __version__), (
        f"version {__version__!r} does not look like a PEP 440 release"
    )


def test_version_at_least_0_1_0():
    from leaves_ph import __version__

    major, minor, patch = (int(x) for x in __version__.split(".")[:3])
    assert (major, minor, patch) >= (0, 1, 0)


def test_public_api_imports():
    """Public API must be importable from the top-level package."""
    from leaves_ph import aggregate_lgu, canopy_threshold, compute_ndvi

    assert callable(compute_ndvi)
    assert callable(canopy_threshold)
    assert callable(aggregate_lgu)


def test_api_stubs_raise_until_phase_3():
    """Phase 3 fills these in. Until then, calling them must raise so a missing
    Phase 3 cannot silently pass CI as a no-op."""
    from leaves_ph import aggregate_lgu, canopy_threshold, compute_ndvi

    with pytest.raises(NotImplementedError):
        compute_ndvi(None, None)
    with pytest.raises(NotImplementedError):
        canopy_threshold(None)
    with pytest.raises(NotImplementedError):
        aggregate_lgu(None, None)
