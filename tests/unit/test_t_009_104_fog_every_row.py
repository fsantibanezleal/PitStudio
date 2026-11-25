# ruff: noqa: E501
"""T-009-104: every row writes the same fog settings, density 0 when there is no dust, so no row inherits fog state.

Requirements: FR-009-58 (supersedes `fog_settings(0.0)` of the exposure-fog tests, which switched the fog off).

Evidence for the requirement: in the gate history probe of 2026-11-23 (report sdg-finish-2026-11-23) the first structured
row of a process after unstructured rows rendered a black sky (sky pixel mean 0.5 against 171 to 199 in the other order)
and the first frame of the class contact run had a black corner: the first activation of the fog changed the frame.
A fog that is enabled on every row with density 0 never toggles.

Expected (`pitstudio_isaac.sdg.render_settings`):
- `fog_settings(sigma)` returns the same set of keys for every sigma >= 0, with `/rtx/fog/enabled` True and
  `/rtx/fog/fogDistanceDensity == sigma` (0.0 for no dust);
- `render_settings(row)` of an unstructured row (no dust) and of a structured row without dust carry that fog block;
- `transmittance_of` of a no-dust row is exactly 1 at every distance.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import render_settings  # noqa: E402


def _row(arm: str, sigma: float = 0.5) -> dict:
    dr = {
        "sun_elevation_deg": 40.0,
        "sun_azimuth_deg": 120.0,
        "dust_extinction_per_km": sigma,
        "light_intensity_factor": 1.0,
        "colour_temperature_k": 5600.0,
        "texture_ids": ["a"],
    }
    return {"arm": arm, "dr": dr}


@pytest.mark.req("FR-009-58")
@pytest.mark.parametrize("sigma", [0.0, 1e-4, 0.5, 3.0, 12.0])
def test_the_fog_block_has_the_same_keys_for_every_extinction_and_is_always_enabled(sigma: float) -> None:
    s = render_settings.fog_settings(sigma)
    assert set(s) == set(render_settings.fog_settings(0.5))
    assert s["/rtx/fog/enabled"] is True
    assert s["/rtx/fog/fogDistanceDensity"] == sigma
    assert s["/rtx/fog/fogHeightDensity"] == 0.0  # the height fog stays off


@pytest.mark.req("FR-009-58")
def test_a_negative_extinction_is_still_refused() -> None:
    with pytest.raises(ValueError, match="negative"):
        render_settings.fog_settings(-0.1)


@pytest.mark.req("FR-009-58")
@pytest.mark.parametrize("distance", [1.0, 100.0, 1000.0, 1e5])
def test_no_dust_means_a_transmittance_of_exactly_one(distance: float) -> None:
    assert render_settings.transmittance_of(render_settings.fog_settings(0.0), distance) == 1.0
    assert render_settings.transmittance_of(render_settings.fog_settings(2.0), distance) == pytest.approx(
        math.exp(-2.0 * distance / 1000.0)
    )


@pytest.mark.req("FR-009-58")
def test_every_row_of_either_arm_writes_the_whole_fog_block() -> None:
    block = set(render_settings.fog_settings(0.5))
    rows = [_row("structured", 0.0), _row("structured", 0.7), _row("unstructured")]
    for row in rows:
        s = render_settings.render_settings(row)
        assert block <= set(s), row["arm"]
        assert s["/rtx/fog/enabled"] is True
    assert render_settings.render_settings(_row("unstructured"))["/rtx/fog/fogDistanceDensity"] == 0.0
    assert render_settings.render_settings(_row("structured", 0.7))["/rtx/fog/fogDistanceDensity"] == 0.7


@pytest.mark.req("FR-009-58")
def test_two_consecutive_rows_differ_only_in_values_never_in_the_keys_they_set() -> None:
    keys = [
        set(render_settings.render_settings(_row(a, s)))
        for a, s in (("structured", 0.0), ("unstructured", 0.0), ("structured", 2.0))
    ]
    assert keys[0] == keys[1] == keys[2]
