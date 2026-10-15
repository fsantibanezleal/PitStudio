"""T-010-055: hostile displacement fields, scan times, wavelength, noise and AR(1) inputs of the radar-series builder.

Requirement: FR-010-42 ("If the displacement field passed to the radar-series builder contains a NaN or infinite
value, the
scan times are not strictly increasing, lambda is outside (1 mm, 1 m), a noise standard deviation is negative or
non-finite, or
the AR(1) coefficient has |rho| >= 1, then the builder shall raise `InvalidRadarConfigError` naming the input and
write no
series").
Spec: specs/010-slope/spec.md section 3.4; plan.md row FR-010-42 ("invalid displacement fields, scan times, lambda,
noise and
rho values written in the test", pytest + Hypothesis).

Expected API (module `pitstudio.slope.radar`, see T-010-050/051): `build_radar_series(..., snr, ar1_rho, sink)` raises
`InvalidRadarConfigError` with `.field` for: a non-finite value in any pixel's `displacement_mm`
("pixels/<i>/displacement_mm");
`t_h` that is not strictly increasing or not finite ("t_h"); a wavelength <= 1 mm or >= 1000 mm
("radar/wavelength_mm"); a
non-positive or non-finite `snr`, hence a negative or non-finite noise sd ("snr"); `ar1_rho` with |rho| >= 1 or
non-finite
("ar1_rho"). `noise_series(run_seed, pixel_id, n, sd_mm, rho=None)` raises for a negative or non-finite `sd_mm`
("sd_mm") and
for |rho| >= 1 ("rho"). The whole input is validated first: no series is produced (`sink` never called, nothing
returned),
even when the invalid value belongs to the last pixel.

Oracle: one case per class written in the test; the interval ends (lambda = 1 mm and 1000 mm are outside, 1.0001 and
999.9
inside; |rho| = 0.999999 inside); a Hypothesis injection of NaN / inf at a random place of a random pixel.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "src"))

from pitstudio.slope import radar

N = 8


def _pixels(count=3):
    return [
        {
            "pixel_id": i + 1,
            "position_m": [10.0 * i, 0.0, 0.0],
            "displacement_mm": np.column_stack([0.05 * np.arange(N)] * 3),
        }
        for i in range(count)
    ]


def _args(**kw):
    base = {
        "event_id": "voight-test-snr-obs-000001",
        "t_h": 0.1 * np.arange(N),
        "radar": {"position_m": [0.0, -500.0, 10.0], "wavelength_mm": 17.4, "scan_interval_min": 6.0},
        "pixels": _pixels(),
        "snr": 50.0,
        "run_seed": 1,
    }
    base.update(kw)
    return base


def _with_pixel_value(index, value, where=(2, 1)):
    pixels = _pixels()
    pixels[index]["displacement_mm"][where] = value
    return pixels


CASES = [
    ("nan-in-first-pixel", {"pixels": _with_pixel_value(0, float("nan"))}, "pixels/0/displacement_mm"),
    ("inf-in-middle-pixel", {"pixels": _with_pixel_value(1, float("inf"))}, "pixels/1/displacement_mm"),
    (
        "minus-inf-in-last-pixel",
        {"pixels": _with_pixel_value(2, float("-inf"), (N - 1, 0))},
        "pixels/2/displacement_mm",
    ),
    ("scan-times-equal", {"t_h": np.array([0.0, 0.1, 0.1, 0.3, 0.4, 0.5, 0.6, 0.7])}, "t_h"),
    ("scan-times-decreasing", {"t_h": np.array([0.0, 0.1, 0.2, 0.15, 0.4, 0.5, 0.6, 0.7])}, "t_h"),
    ("scan-times-reversed", {"t_h": 0.1 * np.arange(N)[::-1]}, "t_h"),
    ("scan-times-nan", {"t_h": np.array([0.0, 0.1, float("nan"), 0.3, 0.4, 0.5, 0.6, 0.7])}, "t_h"),
    (
        "wavelength-1-mm",
        {"radar": {"position_m": [0.0, -500.0, 10.0], "wavelength_mm": 1.0, "scan_interval_min": 6.0}},
        "radar/wavelength_mm",
    ),
    (
        "wavelength-below-1-mm",
        {"radar": {"position_m": [0.0, -500.0, 10.0], "wavelength_mm": 0.3, "scan_interval_min": 6.0}},
        "radar/wavelength_mm",
    ),
    (
        "wavelength-1-m",
        {"radar": {"position_m": [0.0, -500.0, 10.0], "wavelength_mm": 1000.0, "scan_interval_min": 6.0}},
        "radar/wavelength_mm",
    ),
    (
        "wavelength-above-1-m",
        {"radar": {"position_m": [0.0, -500.0, 10.0], "wavelength_mm": 5e5, "scan_interval_min": 6.0}},
        "radar/wavelength_mm",
    ),
    ("snr-zero", {"snr": 0.0}, "snr"),
    ("snr-negative", {"snr": -10.0}, "snr"),
    ("snr-nan", {"snr": float("nan")}, "snr"),
    ("snr-inf", {"snr": float("inf")}, "snr"),
    ("rho-one", {"ar1_rho": 1.0}, "ar1_rho"),
    ("rho-minus-one", {"ar1_rho": -1.0}, "ar1_rho"),
    ("rho-above-one", {"ar1_rho": 1.5}, "ar1_rho"),
    ("rho-nan", {"ar1_rho": float("nan")}, "ar1_rho"),
]


@pytest.mark.req("FR-010-42")
@pytest.mark.parametrize(("name", "kwargs", "field"), CASES, ids=[c[0] for c in CASES])
def test_hostile_input_raises_naming_the_input_and_writes_no_series(name, kwargs, field) -> None:
    sink: list = []
    with pytest.raises(radar.InvalidRadarConfigError) as exc:
        radar.build_radar_series(sink=sink.append, **_args(**kwargs))
    assert exc.value.field.startswith(field), (name, exc.value.field)
    assert field.rsplit("/", 1)[-1] in str(exc.value)
    assert isinstance(exc.value, ValueError)
    assert sink == []


@pytest.mark.req("FR-010-42")
@pytest.mark.parametrize(("sd", "field"), [(-0.1, "sd_mm"), (float("nan"), "sd_mm"), (float("inf"), "sd_mm")])
def test_a_negative_or_non_finite_noise_sd_is_rejected(sd, field) -> None:
    with pytest.raises(radar.InvalidRadarConfigError) as exc:
        radar.noise_series(1, 2, 10, sd)
    assert exc.value.field.startswith(field)


@pytest.mark.req("FR-010-42")
@pytest.mark.parametrize("rho", [1.0, -1.0, 1.2, float("nan")])
def test_noise_series_rejects_a_unit_root_ar1_coefficient(rho) -> None:
    with pytest.raises(radar.InvalidRadarConfigError) as exc:
        radar.noise_series(1, 2, 10, 0.3, rho=rho)
    assert exc.value.field.startswith("rho")


@pytest.mark.req("FR-010-42")
def test_the_valid_neighbours_of_each_limit_are_accepted() -> None:
    for kwargs in (
        {"radar": {"position_m": [0.0, -500.0, 10.0], "wavelength_mm": 1.0001, "scan_interval_min": 6.0}},
        {"radar": {"position_m": [0.0, -500.0, 10.0], "wavelength_mm": 999.9, "scan_interval_min": 6.0}},
        {"ar1_rho": 0.999999},
        {"ar1_rho": -0.999999},
        {"snr": 1e-6},
        {"snr": None},
    ):
        sink: list = []
        out = radar.build_radar_series(sink=sink.append, **_args(**kwargs))
        assert len(out) == len(sink) == 3
    assert radar.noise_series(1, 2, 10, 0.0).tolist() == [0.0] * 10  # sd = 0 is a valid (noise-free) series


@pytest.mark.req("FR-010-42")
@settings(max_examples=100, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(
    st.integers(0, 2),
    st.integers(0, N - 1),
    st.integers(0, 2),
    st.sampled_from([float("nan"), float("inf"), float("-inf")]),
)
def test_a_non_finite_value_anywhere_in_the_field_is_rejected_and_no_series_is_written(pixel, scan, comp, bad) -> None:
    pixels = _pixels()
    pixels[pixel]["displacement_mm"][scan, comp] = bad
    sink: list = []
    with pytest.raises(radar.InvalidRadarConfigError) as exc:
        radar.build_radar_series(sink=sink.append, **_args(pixels=pixels))
    assert exc.value.field.startswith(f"pixels/{pixel}")
    assert sink == []
