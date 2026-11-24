# ruff: noqa: E501, PT018
"""T-009-103: the film is exposed per row by an incident-light meter, a function of the row only.

Requirements: FR-009-57 (supersedes the fixed exposure of the physical-light tests for rows other than the reference).

Oracles: the ISO 2720 incident-light equation N^2 / t = E * S / C with the calibration constant C = 250 for a flat
receptor (https://en.wikipedia.org/wiki/Light_meter, incident-light metering), solved for the shutter time t at the
fixed f-number N = 16; the sunny-16 rule (ISO 100, f/16, 1/100 s) fixes the reference illuminance of the scene at
E = C * N^2 / (S * t) = 250 * 256 / (100 * 0.01) = 64,000 lux for the reference row (sun 60 degrees, light factor 1).
The horizontal illuminance of a row is the reference times the light factor (1 for the structured arm) times
sin(elevation) over sin(60 degrees): the sun term and the sky term (the fixed ratio 6.0) both scale with sin(elevation).

Expected API (`pitstudio_isaac.sdg.render_settings`):
- `ISO_2720_C == 250.0`, `METERING_CITATION` (names ISO 2720 and the Light_meter page), `REFERENCE_ELEVATION_DEG == 60.0`,
  `REFERENCE_ILLUMINANCE_LUX == 64000.0`, `SHUTTER_RANGE_S == (1/4000, 1/30)`, `ISO_RANGE == (100.0, 1600.0)`;
- `illuminance_lux(row)`: the horizontal illuminance of the row in lux;
- `exposure_for(row) -> {"iso", "shutter_s", "f_number"}`: the shutter time of the metered exposure at ISO 100 when it lies
  in `SHUTTER_RANGE_S`; a longer time takes the slowest shutter and raises the ISO to make up (at most 1600), a shorter
  one takes the fastest shutter at ISO 100; f/16 always;
- `exposure_relative(row)`: ISO times shutter times illuminance over the same product of the reference (1.0 whenever
  the metered exposure is inside the ranges, below 1 when a dark row hits both limits, above 1 when a bright row does);
- `render_settings(row)` writes `/rtx/post/tonemap/filmIso`, `cameraShutter` (1/s) and `fNumber` from `exposure_for`;
- `sky_settings(row)`: the sky luminance is the ratio times the base ISO times the ground radiance times
  `exposure_relative(row)` (the background colour is not scaled by the film);
- `describe()["metering"]` records the constant, the reference illuminance, the shutter range and the ISO range.
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

REC709 = (0.2126, 0.7152, 0.0722)
TYPE = "/rtx/background/source/type"
COLOUR = "/rtx/background/source/color"


def _row(arm: str, elevation: float, factor: float = 1.0) -> dict:
    dr = {
        "sun_elevation_deg": elevation,
        "sun_azimuth_deg": 120.0,
        "dust_extinction_per_km": 0.5,
        "colour_temperature_k": 5600.0,
        "texture_ids": ["a"],
    }
    if arm == "unstructured":
        dr["light_intensity_factor"] = factor
    return {"arm": arm, "dr": dr}


def _luminance(rgb: list[float]) -> float:
    return sum(w * c for w, c in zip(REC709, rgb, strict=True))


@pytest.mark.req("FR-009-57")
def test_the_constants_and_their_sources_are_stated() -> None:
    assert render_settings.ISO_2720_C == 250.0
    assert render_settings.REFERENCE_ELEVATION_DEG == 60.0
    assert pytest.approx(250.0 * 16.0**2 / (100.0 * 0.01)) == render_settings.REFERENCE_ILLUMINANCE_LUX
    assert (pytest.approx(1 / 4000), pytest.approx(1 / 30)) == render_settings.SHUTTER_RANGE_S
    assert render_settings.ISO_RANGE == (100.0, 1600.0)
    for part in ("ISO 2720", "250", "en.wikipedia.org/wiki/Light_meter", "Sunny_16"):
        assert part in render_settings.METERING_CITATION, part


@pytest.mark.req("FR-009-57")
@pytest.mark.parametrize("arm", ["structured", "unstructured"])
def test_the_illuminance_scales_with_the_sine_of_the_elevation_and_the_light_factor(arm: str) -> None:
    ref = render_settings.REFERENCE_ILLUMINANCE_LUX
    assert render_settings.illuminance_lux(_row(arm, 60.0)) == pytest.approx(ref)
    assert render_settings.illuminance_lux(_row(arm, 30.0)) == pytest.approx(ref * 0.5 / math.sin(math.radians(60.0)))
    assert render_settings.illuminance_lux(_row(arm, 90.0)) == pytest.approx(ref / math.sin(math.radians(60.0)))


@pytest.mark.req("FR-009-57")
def test_the_light_factor_scales_the_unstructured_illuminance_and_never_the_structured() -> None:
    ref = render_settings.REFERENCE_ILLUMINANCE_LUX
    assert render_settings.illuminance_lux(_row("unstructured", 60.0, 2.5)) == pytest.approx(2.5 * ref)
    structured = _row("structured", 60.0)
    structured["dr"]["light_intensity_factor"] = 9.0  # a structured row carries no factor: it is ignored
    assert render_settings.illuminance_lux(structured) == pytest.approx(ref)


@pytest.mark.req("FR-009-57")
@pytest.mark.parametrize("arm", ["structured", "unstructured"])
def test_the_reference_row_is_the_sunny_16_exposure(arm: str) -> None:
    e = render_settings.exposure_for(_row(arm, 60.0))
    assert e["iso"] == 100.0 and e["f_number"] == 16.0
    assert e["shutter_s"] == pytest.approx(0.01)
    assert render_settings.exposure_relative(_row(arm, 60.0)) == pytest.approx(1.0)


@pytest.mark.req("FR-009-57")
@pytest.mark.parametrize("elevation", [20.0, 35.0, 60.0, 80.0])
@pytest.mark.parametrize("factor", [0.3, 1.0, 4.0])
def test_inside_the_ranges_the_exposure_satisfies_the_iso_2720_equation(elevation: float, factor: float) -> None:
    row = _row("unstructured", elevation, factor)
    e = render_settings.exposure_for(row)
    lux = render_settings.illuminance_lux(row)
    lo, hi = render_settings.SHUTTER_RANGE_S
    assert lo - 1e-12 <= e["shutter_s"] <= hi + 1e-12
    assert e["f_number"] ** 2 / e["shutter_s"] == pytest.approx(lux * e["iso"] / render_settings.ISO_2720_C, rel=1e-9)
    assert render_settings.exposure_relative(row) == pytest.approx(1.0)


@pytest.mark.req("FR-009-57")
def test_a_dim_row_slows_the_shutter_first_and_raises_the_iso_only_at_the_slowest_shutter() -> None:
    lux_ref = render_settings.REFERENCE_ILLUMINANCE_LUX
    seen_iso_raised = False
    for k in range(1, 400):
        factor = 0.02 + k * 0.005
        row = _row("unstructured", 60.0, factor)
        e = render_settings.exposure_for(row)
        assert 100.0 <= e["iso"] <= 1600.0
        if e["iso"] > 100.0:
            seen_iso_raised = True
            assert e["shutter_s"] == pytest.approx(1 / 30)  # the ISO moves only when the shutter has run out
        assert render_settings.illuminance_lux(row) == pytest.approx(factor * lux_ref)
    assert seen_iso_raised


@pytest.mark.req("FR-009-57")
def test_the_exposure_never_gets_faster_as_the_row_gets_darker() -> None:
    previous = None
    for k in range(0, 120):
        factor = 12.0 * 0.93**k  # from bright to dim over 4 decades
        e = render_settings.exposure_for(_row("unstructured", 45.0, factor))
        product = e["iso"] * e["shutter_s"]
        if previous is not None:
            assert product >= previous - 1e-15, factor
        previous = product


@pytest.mark.req("FR-009-57")
def test_the_table_range_of_the_domain_randomisation_is_inside_the_physical_ranges() -> None:
    # recipe: sun elevation from 5 degrees, light factor 0.1 to 10: the darkest row needs 53 times the reference exposure
    dark = _row("unstructured", 12.0, 0.1)
    bright = _row("unstructured", 89.0, 10.0)
    assert render_settings.exposure_relative(dark) == pytest.approx(1.0)
    assert render_settings.exposure_relative(bright) == pytest.approx(1.0)
    darkest_allowed = render_settings.exposure_relative(_row("unstructured", 5.0, 0.1))
    assert (
        darkest_allowed < 1.0
    )  # sin(5) * 0.1 asks 6.6 stops of the 5.7 the shutter and ISO ranges give: both limits are hit
    e = render_settings.exposure_for(_row("unstructured", 5.0, 0.1))
    assert e["iso"] == 1600.0 and e["shutter_s"] == pytest.approx(1 / 30)


@pytest.mark.req("FR-009-57")
def test_a_row_beyond_the_fastest_shutter_is_over_exposed_not_extrapolated() -> None:
    row = _row("unstructured", 90.0, 100.0)
    e = render_settings.exposure_for(row)
    assert e["iso"] == 100.0 and e["shutter_s"] == pytest.approx(1 / 4000)
    assert render_settings.exposure_relative(row) > 1.0


@pytest.mark.req("FR-009-57")
@pytest.mark.parametrize("arm", ["structured", "unstructured"])
def test_the_render_settings_write_the_metered_exposure_of_the_row(arm: str) -> None:
    row = _row(arm, 25.0, 0.5)
    s = render_settings.render_settings(row)
    e = render_settings.exposure_for(row)
    assert s["/rtx/post/tonemap/filmIso"] == e["iso"]
    assert s["/rtx/post/tonemap/fNumber"] == 16.0
    assert s["/rtx/post/tonemap/cameraShutter"] == pytest.approx(1.0 / e["shutter_s"])
    assert s["/rtx/post/histogram/enabled"] is False


@pytest.mark.req("FR-009-57")
def test_the_exposure_is_a_function_of_the_row_only() -> None:
    a, b = _row("unstructured", 25.0, 0.5), _row("unstructured", 70.0, 5.0)
    before = render_settings.render_settings(a)
    render_settings.render_settings(b)  # another row in between
    assert render_settings.render_settings(_row("unstructured", 25.0, 0.5)) == before


@pytest.mark.req("FR-009-57")
def test_the_sky_follows_the_metered_exposure_and_not_the_light_factor() -> None:
    base = render_settings.FILM_ISO["unstructured"]
    ground = render_settings.UNSTRUCTURED_GROUND_RADIANCE
    for factor in (0.3, 1.0, 4.0):  # inside the ranges: the same display ground, so the same sky
        colour = render_settings.sky_settings(_row("unstructured", 35.0, factor))[COLOUR]
        assert _luminance(colour) == pytest.approx(render_settings.SKY_LUMINANCE_RATIO * base * ground, rel=1e-9)
    dim = _row(
        "unstructured", 5.0, 0.1
    )  # the limits are hit: the ground is darker than the metered one, and so is the sky
    colour = render_settings.sky_settings(dim)[COLOUR]
    expected = render_settings.SKY_LUMINANCE_RATIO * base * ground * render_settings.exposure_relative(dim)
    assert _luminance(colour) == pytest.approx(expected, rel=1e-9)
    assert expected < render_settings.SKY_LUMINANCE_RATIO * base * ground


@pytest.mark.req("FR-009-57")
def test_the_description_records_the_metering() -> None:
    m = render_settings.describe()["metering"]
    assert m["iso_2720_c"] == 250.0
    assert m["reference_illuminance_lux"] == pytest.approx(64000.0)
    assert m["reference_elevation_deg"] == 60.0
    assert tuple(m["shutter_range_s"]) == (pytest.approx(1 / 4000), pytest.approx(1 / 30))
    assert tuple(m["iso_range"]) == (100.0, 1600.0)
    assert "ISO 2720" in m["citation"]
