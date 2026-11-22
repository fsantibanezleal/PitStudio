# ruff: noqa: PT018
"""T-009-016 (fix): exposure and fog of the SDG renderer are functions of the row only and the fog follows Beer-Lambert.

Requirements: FR-009-02, FR-009-05, FR-009-08.

Probes of 2026-11-22 on Isaac Sim 6.1 (queue jobs 88 to 89k, see the report sdg-exposure-2026-11-22):
- the setting `/rtx/fog/fogDensity` of job 89 does not exist in the RTX renderer: the transmittance at 100, 300 and
  1000 m was the same (0.79, 0.46, 0.18) for sigma = 0.75, 3 and 12 per km, the renderer's default fog colour veil;
- the simple fog `/rtx/fog/fogDistanceDensity` with the height fog off (`fogHeightDensity` 0) renders the transmittance
  exp(-sigma * d) with the density equal to sigma in 1/km, measured on a plane at 100, 300 and 1000 m with the linear
  tonemapper: within 4 percent (relative) wherever exp(-sigma * d) is at least 0.1 (8-bit floor below that);
- the histogram auto exposure is off by default, and switching it on made a frame depend on the frames before it
  (mean luminance differences of 5 to 69 levels in the probe grid), so it is never used: the exposure is `filmIso`;
- the dome fill of the nominal lights reached the terrain about 1000 times weaker than the sun, so the dome intensity
  carries a fill gain of 1000 (probes `lights` and `lights2`).

Oracles: the settings listed above, the Beer-Lambert transmittance exp(-sigma * d) by hand, the frame-row independence
(the same row gives the same settings whatever was rendered before).
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
from pitstudio_isaac.sdg import driver, exposure, scene_render  # noqa: E402
from test_t_009_016_shard_driver import _row  # noqa: E402


@pytest.mark.req("FR-009-05")
def test_the_fog_density_of_the_renderer_is_the_dust_extinction_in_one_per_km() -> None:
    s = exposure.fog_settings(3.0)
    assert s["/rtx/fog/enabled"] is True
    assert s["/rtx/fog/fogDistanceDensity"] == 3.0  # measured: the density is sigma in 1/km (fog check, 9 distances)
    assert s["/rtx/fog/fogHeightDensity"] == 0.0  # the default height fog added a constant veil in every probe
    assert s["/rtx/fog/fogStartDist"] == 0.0
    assert "/rtx/fog/fogDensity" not in s and "/rtx/fog/color" not in s  # settings the renderer does not have
    assert tuple(s["/rtx/fog/fogColor"]) == exposure.FOG_COLOUR


@pytest.mark.req("FR-009-05")
def test_no_dust_means_no_fog_and_a_negative_extinction_is_refused() -> None:
    assert exposure.fog_settings(0.0) == {"/rtx/fog/enabled": False}
    with pytest.raises(ValueError, match="negative"):
        exposure.fog_settings(-0.1)


@pytest.mark.req("FR-009-05")
@pytest.mark.parametrize("sigma", [0.75, 3.0, 12.0])
def test_the_modelled_transmittance_is_beer_lambert_at_the_three_check_distances(sigma: float) -> None:
    for d in (100.0, 300.0, 1000.0):
        assert exposure.transmittance_of(exposure.fog_settings(sigma), d) == pytest.approx(
            math.exp(-sigma * d / 1000.0)
        )


@pytest.mark.req("FR-009-02")
def test_the_auto_exposure_is_off_and_the_exposure_is_the_film_iso_of_the_arm() -> None:
    s = exposure.render_settings(_row())
    assert s["/rtx/post/histogram/enabled"] is False  # a history-dependent exposure is refused
    assert s["/rtx/post/tonemap/filmIso"] == exposure.FILM_ISO["structured"]
    u = exposure.render_settings(_row("pit-u-00000", arm="unstructured"))
    assert u["/rtx/post/tonemap/filmIso"] == exposure.FILM_ISO["unstructured"]
    assert u["/rtx/fog/enabled"] is False  # the unstructured arm has no fog


@pytest.mark.req("FR-009-02")
def test_the_settings_are_a_function_of_the_row_only() -> None:
    row = _row()
    other = copy.deepcopy(row)
    other["dr"]["dust_extinction_per_km"] = 7.0
    before = exposure.render_settings(row)
    exposure.render_settings(other)  # a different row in between
    assert exposure.render_settings(row) == before
    assert exposure.render_settings(row) != exposure.render_settings(other)


@pytest.mark.req("FR-009-08")
def test_the_light_factor_scales_sun_and_dome_alike_and_the_dome_carries_the_fill_gain() -> None:
    lit = scene_render.light_for_row(_row("pit-u-00000", arm="unstructured") | {"dr": _u_dr(0.1)})
    bright = scene_render.light_for_row(_row("pit-u-00001", arm="unstructured") | {"dr": _u_dr(10.0)})
    assert bright["sun_intensity"] / lit["sun_intensity"] == pytest.approx(100.0)
    assert bright["dome_intensity"] / lit["dome_intensity"] == pytest.approx(100.0)
    nominal = scene_render.light_for_row(_row())
    assert nominal["dome_intensity"] == 800.0 * exposure.DOME_FILL_GAIN
    assert exposure.DOME_FILL_GAIN == 1000.0


def _u_dr(factor: float) -> dict:
    return {
        "sun_elevation_deg": 40.0,
        "sun_azimuth_deg": 90.0,
        "light_intensity_factor": factor,
        "colour_temperature_k": 6500.0,
        "texture_ids": ["t"],
        "placements": [],
    }


class _Settings:
    def __init__(self) -> None:
        self.values: dict = {}

    def set(self, path, value) -> None:
        self.values[path] = value


class _Carb:
    def __init__(self) -> None:
        self.s = _Settings()
        self.settings = self

    def get_settings(self) -> _Settings:
        return self.s


@pytest.mark.req("FR-009-02")
def test_the_renderer_applies_the_row_settings_by_default_and_returns_them() -> None:
    renderer = scene_render.SdgRenderer.__new__(scene_render.SdgRenderer)
    renderer._carb = _Carb()
    renderer.settings_fn = None
    row = _row()
    applied = renderer._apply_render_settings(row)
    assert applied == exposure.render_settings(row)
    assert renderer._carb.s.values == applied


@pytest.mark.req("NFR-009-03")
def test_the_run_file_records_the_render_settings_model(tmp_path: Path) -> None:
    from test_t_009_016_resume_quality import _Scripted, _no_session

    driver.run(
        rows=[_row("pit-s-00000")],
        root=tmp_path,
        renderer_factory=lambda: _Scripted(set()),
        session=_no_session,
        run_info={"render_settings": exposure.describe()},
    )
    import json

    doc = json.loads((tmp_path / driver.RUN_FILE).read_text(encoding="utf-8"))
    assert doc["render_settings"]["film_iso"] == exposure.FILM_ISO
    assert doc["render_settings"]["auto_exposure"] is False
    assert doc["render_settings"]["fog"]["density_per_km_equals_sigma"] is True
