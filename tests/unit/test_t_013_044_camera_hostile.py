# ruff: noqa: E501, PT018, RUF043
"""T-013-044: camera post-model hostile inputs.

Requirements: FR-013-20.

Oracle: a hostile parameter corpus, one defect per case, with the parameter name each message must carry written in the test (plan.md
"FR-013-20"); Hypothesis corrupts random pixels and parameters. A non-finite distance is NOT a defect (it is a pixel without a hit, FR-013-16);
a finite distance <= 0 is.

Expected API: `pitstudio.sensors.camera.haze` and `camera.expose` (tests T-013-040 and T-013-042). Each raises `ValueError` naming the
offending parameter (`radiance`, `distance`, `airlight`, `exposure_time_s`, `f_number`, `kappa`, `gain`, `read_noise_e`, `dn_max`) for: NaN or infinite
radiance; a finite distance <= 0; `radiance` and `distance` (or, for `expose`, `L` and the intrinsics grid) of different shapes; t_e <= 0, N <= 0, kappa <= 0, G <= 0,
sigma_read < 0, DN_max < 1; an airlight component outside [0, 10^6] or not finite; and returns nothing (no image).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_sensor_kit"))
from pitstudio.sensors import camera  # noqa: E402

A = np.array([0.5, 0.4, 0.3])
EXPOSE = {
    "exposure_time_s": 0.002,
    "f_number": 5.6,
    "kappa": 2.0e6,
    "gain": 0.25,
    "read_noise_e": 3.0,
    "dn_max": 4095,
    "vignetting": False,
    "intrinsics": {"fx_px": 100.0, "fy_px": 100.0, "cx_px": 4.0, "cy_px": 3.0},
    "seed": 1,
    "image_index": 0,
}


def _haze(**override):
    args = {"radiance": np.ones((6, 8, 3), np.float32), "distance": np.full((6, 8), 30.0), "airlight": A, "beta": 0.01}
    args.update(override)
    return camera.haze(args.pop("radiance"), args.pop("distance"), args.pop("airlight"), **args)


def _expose(**override):
    args = {"L": np.full((6, 8), 10.0), **EXPOSE}
    args.update(override)
    return camera.expose(args.pop("L"), **args)


@pytest.mark.req("FR-013-20")
def test_the_unmodified_inputs_are_accepted() -> None:
    assert _haze().shape == (6, 8, 3) and _expose().shape == (6, 8)


@pytest.mark.req("FR-013-20")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_radiance_is_rejected(bad: float) -> None:
    radiance = np.ones((6, 8, 3), np.float32)
    radiance[2, 3, 1] = bad
    with pytest.raises(ValueError, match="radiance"):
        _haze(radiance=radiance)
    luminance = np.full((6, 8), 10.0)
    luminance[0, 0] = bad
    with pytest.raises(ValueError, match="L|radiance"):
        _expose(L=luminance)


@pytest.mark.req("FR-013-20")
@pytest.mark.parametrize("bad", [0.0, -1.0, -1e-9])
def test_a_finite_distance_that_is_not_positive_is_rejected(bad: float) -> None:
    d = np.full((6, 8), 30.0)
    d[1, 1] = bad
    with pytest.raises(ValueError, match="distance"):
        _haze(distance=d)


@pytest.mark.req("FR-013-20")
def test_non_finite_distances_are_pixels_without_a_hit_not_errors() -> None:
    d = np.full((6, 8), 30.0)
    d[0, 0], d[1, 1] = np.inf, np.nan
    out = _haze(distance=d, exit_distance=100.0)
    assert np.isfinite(out).all()


@pytest.mark.req("FR-013-20")
@pytest.mark.parametrize("shape", [(6, 7), (5, 8), (8, 6), (48,)])
def test_arrays_of_different_shapes_are_rejected(shape: tuple[int, ...]) -> None:
    with pytest.raises(ValueError, match="distance|shape"):
        _haze(distance=np.full(shape, 30.0))
    with pytest.raises(ValueError, match="radiance|shape"):
        _haze(radiance=np.ones((6, 8), np.float32))  # a grey image is not (h, w, 3)


@pytest.mark.req("FR-013-20")
@pytest.mark.parametrize(
    ("name", "bad"),
    [
        ("exposure_time_s", 0.0),
        ("exposure_time_s", -0.002),
        ("f_number", 0.0),
        ("f_number", -2.0),
        ("kappa", 0.0),
        ("kappa", -1.0),
        ("gain", 0.0),
        ("gain", -0.25),
        ("read_noise_e", -0.001),
        ("dn_max", 0),
        ("dn_max", -5),
        ("exposure_time_s", np.nan),
        ("f_number", np.inf),
        ("kappa", np.nan),
        ("gain", np.inf),
        ("read_noise_e", np.nan),
    ],
)
def test_bad_exposure_parameters_are_rejected_by_name(name: str, bad: float) -> None:
    with pytest.raises(ValueError, match=name):
        _expose(**{name: bad})


@pytest.mark.req("FR-013-20")
@pytest.mark.parametrize(
    "airlight", [[-0.001, 0.4, 0.3], [0.5, 1_000_000.001, 0.3], [0.5, 0.4, np.nan], [np.inf, 0.4, 0.3]]
)
def test_an_airlight_outside_the_valid_range_is_rejected(airlight: list[float]) -> None:
    with pytest.raises(ValueError, match="airlight"):
        _haze(airlight=np.array(airlight))
    _haze(airlight=np.array([0.0, 1_000_000.0, 0.3]))  # the closed range [0, 10^6] is accepted at both ends


@pytest.mark.req("FR-013-20")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(y=st.integers(0, 5), x=st.integers(0, 7), c=st.integers(0, 2), bad=st.sampled_from([np.nan, np.inf, -np.inf]))
def test_any_single_bad_radiance_value_is_found_wherever_it_is(y: int, x: int, c: int, bad: float) -> None:
    radiance = np.ones((6, 8, 3), np.float32)
    radiance[y, x, c] = bad
    with pytest.raises(ValueError, match="radiance"):
        _haze(radiance=radiance)
