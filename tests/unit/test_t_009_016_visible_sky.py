# ruff: noqa: PT018
"""T-009-016 (sdg-gate): the visible sky of the SDG renderer is a constant colour, the dome stays the fill light.

Requirements: FR-009-02, FR-009-05, FR-009-08.

Probes of 2026-11-23 on Isaac Sim 6.1 (queue jobs 88a to 88e, report sdg-gate-2026-11-23):
- the dome seen by camera rays saturated the sky: 86.4 percent of the sky pixels were at 255 in the pit views of the
  gate sample (`/rtx/background/source/type` default `domeLight`);
- `/rtx/background/source/type = color` shows the constant colour `/rtx/background/source/color` and leaves the dome as
  the fill light: the terrain pixels of the same row differed by at most 0.21 levels between the dome and the colour
  variants (0.07 between two renders of the dome variant), so the fill is unchanged;
- the colour does not follow the film ISO (sky 232 at ISO 25 and at ISO 0.4) but goes through the tonemapper like the
  scene radiance, so the colour that displays the same luminance as sunlit ground is ISO times the ground radiance;
- the sunlit ground radiance (p90 of the terrain pixels, ISO 1 units) is about 1.03 times the light factor in the
  unstructured arm (p10 0.77, p90 1.37) and about 0.8 in the structured arm (p10 0.37, p90 1.31).

Oracles: the setting names of the installed schema, the Rec. 709 luminance of the colour by hand, the frame-row
independence.
"""

from __future__ import annotations

import copy
import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import render_settings, scene_render  # noqa: E402
from test_t_009_016_exposure_fog import _u_dr  # noqa: E402
from test_t_009_016_shard_driver import _row  # noqa: E402

REC709 = (0.2126, 0.7152, 0.0722)
TYPE = "/rtx/background/source/type"
COLOUR = "/rtx/background/source/color"


def _unstructured(factor: float) -> dict:
    return _row("pit-u-00000", arm="unstructured") | {"dr": _u_dr(factor)}


def _luminance(rgb: list[float]) -> float:
    return sum(w * c for w, c in zip(REC709, rgb, strict=True))


@pytest.mark.req("FR-009-02")
@pytest.mark.parametrize("row", [_row(), _unstructured(1.0)])
def test_the_sky_is_a_constant_colour_so_the_dome_is_not_seen_by_camera_rays(row: dict) -> None:
    s = render_settings.sky_settings(row)
    assert s[TYPE] == "color"  # installed schema: allowedTokens domeLight, backplate, color (generatedSchema.usda)
    assert len(s[COLOUR]) == 3 and all(c > 0.0 and math.isfinite(c) for c in s[COLOUR])
    assert set(s) == {TYPE, COLOUR}


@pytest.mark.req("FR-009-02")
def test_the_render_settings_of_a_row_carry_the_sky_and_never_the_dome_as_background() -> None:
    for row in (_row(), _unstructured(2.0)):
        s = render_settings.render_settings(row)
        assert s[TYPE] == "color"
        assert s[COLOUR] == render_settings.sky_settings(row)[COLOUR]


@pytest.mark.req("FR-009-08")
@pytest.mark.parametrize("factor", [0.1, 1.0, 10.0])
def test_the_sky_shows_the_luminance_of_sunlit_ground_times_the_ratio(factor: float) -> None:
    row = _unstructured(factor)
    colour = render_settings.sky_settings(row)[COLOUR]
    ground = render_settings.UNSTRUCTURED_GROUND_RADIANCE * factor
    expected = render_settings.SKY_LUMINANCE_RATIO * render_settings.FILM_ISO["unstructured"] * ground
    assert _luminance(colour) == pytest.approx(expected, rel=1e-9)


@pytest.mark.req("FR-009-08")
def test_the_structured_sky_does_not_depend_on_the_light_factor_and_the_ratio_is_physical() -> None:
    colour = render_settings.sky_settings(_row())[COLOUR]
    expected = (
        render_settings.SKY_LUMINANCE_RATIO
        * render_settings.FILM_ISO["structured"]
        * render_settings.STRUCTURED_GROUND_RADIANCE
    )
    assert _luminance(colour) == pytest.approx(expected, rel=1e-9)
    # sky to sunlit ground luminance 3 to 5 kcd/m2 over 5 kcd/m2: 0.6 to 1.6 (Orders of magnitude, luminance)
    assert 0.6 <= render_settings.SKY_LUMINANCE_RATIO <= 1.6
    assert colour[2] > colour[1] > colour[0]  # a clear sky is bluer than neutral


@pytest.mark.req("FR-009-02")
def test_the_sky_is_a_function_of_the_row_only() -> None:
    row = _unstructured(3.0)
    before = render_settings.sky_settings(row)
    render_settings.sky_settings(_unstructured(0.2))  # another row in between
    assert render_settings.sky_settings(copy.deepcopy(row)) == before
    assert render_settings.sky_settings(_unstructured(0.2)) != before


@pytest.mark.req("FR-009-08")
def test_the_sky_leaves_the_fill_light_of_the_terrain_unchanged() -> None:
    nominal = scene_render.light_for_row(_row())
    assert nominal["dome_intensity"] == 800.0 * render_settings.DOME_FILL_GAIN
    s = render_settings.render_settings(_row())
    for key in ("/rtx/post/histogram/enabled", "/rtx/post/tonemap/op", "/rtx/post/tonemap/filmIso"):
        assert key in s  # the exposure settings stay
    assert set(render_settings.fog_settings(0.5)) <= set(s)  # and so does the fog
    assert not [k for k in s if "dome" in k.lower() or k.startswith("/rtx/lights")]  # no setting acts on the dome light
    assert s[TYPE] == "color"  # while the dome is not the background: it only lights the terrain


@pytest.mark.req("FR-009-02")
@pytest.mark.parametrize("factor", [0.0, -1.0, math.nan, math.inf])
def test_a_light_factor_that_is_not_positive_and_finite_is_refused(factor: float) -> None:
    with pytest.raises(ValueError, match="light factor"):
        render_settings.sky_settings(_unstructured(factor))


@pytest.mark.req("NFR-009-03")
def test_the_render_settings_model_records_the_sky() -> None:
    doc = render_settings.describe()
    assert doc["sky"]["source"] == "color"
    assert doc["sky"]["luminance_ratio_to_sunlit_ground"] == render_settings.SKY_LUMINANCE_RATIO
    assert doc["sky"]["ground_radiance"] == {
        "structured": render_settings.STRUCTURED_GROUND_RADIANCE,
        "unstructured_per_light_factor": render_settings.UNSTRUCTURED_GROUND_RADIANCE,
    }


@pytest.mark.req("FR-009-02")
def test_the_film_iso_is_calibrated_on_the_open_carved_scene() -> None:
    # Sweep of 2026-11-23 (job 88d, 24 rows per arm, ISO 25 to 0.1): the ISO 100 of the buried-geometry calibration
    # (cameras under the DEM, the dome fill reached the terrain 1000 times weaker) left every frame white on the carved
    # surface; frames with more than 25 percent clipped pixels: structured 24 / 24 at ISO 25, 8 at 6.25, 0 at 1.5 and
    # 0.4; unstructured 19 / 24 at ISO 25, 11 at 6.25, 5 at 1.5, 1 at 0.4, 0 at 0.1.
    assert render_settings.FILM_ISO == {"structured": 0.4, "unstructured": 0.3}
