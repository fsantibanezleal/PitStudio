# ruff: noqa: PT018
"""T-009-016 (fix): the SDG sun and sky are in a cited clear-sky ratio and the film is exposed like a daylight photograph.

Requirements: FR-009-02, FR-009-04 (the sun of a row), FR-009-08 (the unstructured light factor).

Oracles: the clear-day illuminances of the Wikipedia "Daylight" table (https://en.wikipedia.org/wiki/Daylight): direct
sunlight at noon 120,000 lux, shade lit by the whole clear blue sky at midday 20,000 lux, so the ratio of direct sun to
diffuse sky illuminance on a horizontal surface is 6; the sunny-16 rule (https://en.wikipedia.org/wiki/Sunny_16_rule): at
f/16 the shutter time in seconds is the reciprocal of the ISO value, so ISO 100, f/16, 1/100 s; the illuminance of a
distant light on a horizontal plane is its intensity times the sine of the sun elevation (Lambert's cosine law), the
illuminance of the dome on it is independent of the elevation.

Expected API (`pitstudio_isaac.sdg.render_settings`, `scene_render.light_for_row`):
- `SUN_TO_SKY_ILLUMINANCE == 6.0` with the sources in `LIGHT_CITATION` (a string naming both pages and both values);
- `PLANE_RADIANCE_PER_SUN_UNIT` and `PLANE_RADIANCE_PER_DOME_UNIT`: the linear radiance of a horizontal plane per unit of
  sun intensity (sun at the zenith) and per unit of dome intensity, measured on an open grey plane (job 8a, report
  sdg-realism-2026-11-23);
- for every row, `light_for_row` gives a sun and a dome intensity whose horizontal illuminances, sun times sin(elevation)
  over dome, are in the ratio `SUN_TO_SKY_ILLUMINANCE`;
- the film is `FILM_ISO == 100` for both arms with `FILM_SHUTTER_S == 1/100` and `F_NUMBER == 16`, set on every row as
  `/rtx/post/tonemap/filmIso`, `cameraShutter` (in 1/s) and `fNumber`; `describe()` records them and the ratio.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
from pitstudio_isaac.sdg import render_settings, scene_render  # noqa: E402


def _row(arm: str, elevation: float, factor: float = 1.0) -> dict:
    dr = {
        "sun_elevation_deg": elevation,
        "sun_azimuth_deg": 120.0,
        "dust_extinction_per_km": 0.5,
        "light_intensity_factor": factor,
        "colour_temperature_k": 5600.0,
    }
    return {"arm": arm, "dr": dr}


@pytest.mark.req("FR-009-02")
def test_the_ratio_and_its_sources_are_stated() -> None:
    assert render_settings.SUN_TO_SKY_ILLUMINANCE == 6.0
    text = render_settings.LIGHT_CITATION
    for part in ("en.wikipedia.org/wiki/Daylight", "120,000", "20,000", "Sunny_16"):
        assert part in text, part


@pytest.mark.req("FR-009-02")
@pytest.mark.parametrize("arm", ["structured", "unstructured"])
@pytest.mark.parametrize("elevation", [8.0, 20.0, 45.0, 70.0, 89.0])
@pytest.mark.parametrize("factor", [1.0, 0.1, 3.0])
def test_the_horizontal_sun_to_sky_ratio_is_the_cited_one_at_every_elevation(
    arm: str, elevation: float, factor: float
) -> None:
    light = scene_render.light_for_row(_row(arm, elevation, factor))
    sun = light["sun_intensity"] * render_settings.PLANE_RADIANCE_PER_SUN_UNIT * math.sin(math.radians(elevation))
    sky = light["dome_intensity"] * render_settings.PLANE_RADIANCE_PER_DOME_UNIT
    assert sun / sky == pytest.approx(render_settings.SUN_TO_SKY_ILLUMINANCE, rel=1e-9)


@pytest.mark.req("FR-009-08")
def test_the_unstructured_light_factor_scales_sun_and_sky_together() -> None:
    a = scene_render.light_for_row(_row("unstructured", 40.0, 1.0))
    b = scene_render.light_for_row(_row("unstructured", 40.0, 2.5))
    assert b["sun_intensity"] / a["sun_intensity"] == pytest.approx(2.5)
    assert b["dome_intensity"] / a["dome_intensity"] == pytest.approx(2.5)


@pytest.mark.req("FR-009-02")
@pytest.mark.parametrize("arm", ["structured", "unstructured"])
def test_the_film_is_exposed_at_iso_100_f16_and_a_hundredth_of_a_second(arm: str) -> None:
    assert render_settings.FILM_ISO == {"structured": 100.0, "unstructured": 100.0}
    assert render_settings.F_NUMBER == 16.0 and render_settings.FILM_SHUTTER_S == pytest.approx(0.01)
    row = {"arm": arm, "dr": {**_row(arm, 30.0)["dr"], "texture_ids": ["a"]}}
    s = render_settings.render_settings(row)
    assert s["/rtx/post/tonemap/filmIso"] == 100.0
    assert s["/rtx/post/tonemap/fNumber"] == 16.0
    assert s["/rtx/post/tonemap/cameraShutter"] == pytest.approx(100.0)  # the setting is in 1/s
    assert 1.0 / s["/rtx/post/tonemap/cameraShutter"] == pytest.approx(1.0 / s["/rtx/post/tonemap/filmIso"])  # sunny 16


@pytest.mark.req("FR-009-02")
def test_the_description_records_the_exposure_and_the_ratio() -> None:
    d = render_settings.describe()
    assert d["film_iso"] == {"structured": 100.0, "unstructured": 100.0}
    assert d["exposure"] == {"f_number": 16.0, "shutter_s": pytest.approx(0.01)}
    assert d["light"]["sun_to_sky_illuminance"] == 6.0
    assert "en.wikipedia.org/wiki/Daylight" in d["light"]["citation"]
