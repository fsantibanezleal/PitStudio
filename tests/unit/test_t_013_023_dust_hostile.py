# ruff: noqa: E501, PT018, PT011
"""T-013-023: dust post-model hostile inputs.

Requirements: FR-013-15.

Oracle: a hostile profile and cloud corpus, one defect per case, with the offending beam index written in the test (beam
indices are 1000 + row, so the message must contain "1002" for row 2: a row number alone would not do); the boundary cases that
must still be accepted (spacing exactly 0.5 m, zero extinction, a profile that just reaches the range); Hypothesis corrupts
random rows.

Expected API: `pitstudio.sensors.dust.apply_dust(...)` and `dust.optical_depth(...)` (test_t_013_020). Any of: a negative, NaN or
infinite extinction sample (in the part of the profile that matters or not: every sample is checked), a spacing <= 0 or > 0.5 m or
non-finite, a profile that does not reach a return's range ((m - 1) * spacing < range), a non-finite or non-positive range, a
material class other than "retro" or "diffuse", arrays of mismatched length, raises `ValueError`; for a defect of one return the
message names that return's beam index; nothing is returned (no partial cloud).
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
import sensor_kit as kit  # noqa: E402
from pitstudio.sensors import dust  # noqa: E402

N, M, SPACING = 6, 400, 0.25  # profiles reach 99.75 m
BAD_ROW = 2
BAD_BEAM = 1000 + BAD_ROW


def _inputs() -> dict:
    rng = np.random.default_rng(1)
    return {
        "beam": (1000 + np.arange(N)).astype(np.uint32),
        "range_m": np.array([10.0, 20.0, 30.0, 40.0, 50.0, 60.0]),
        "material": np.array(["retro", "diffuse"] * 3),
        "intensity": rng.uniform(0.1, 1.0, N),
        "xyz": rng.normal(size=(N, 3)),
        "beta": rng.uniform(0.0, 0.01, (N, M)),
        "spacing": SPACING,
    }


def _call(d: dict):
    return dust.apply_dust(
        d["beam"],
        d["range_m"],
        d["material"],
        d["intensity"],
        d["xyz"],
        d["beta"],
        d["spacing"],
        frame=0,
        seed=1,
        dust_return_intensity=0.05,
        max_returns=2,
    )


def _row_case(mutate):
    def apply(d: dict) -> None:
        mutate(d)

    return apply


def _set_beta(value: float):
    def apply(d: dict) -> None:
        d["beta"] = d["beta"].copy()
        d["beta"][BAD_ROW, 17] = value

    return apply


def _set_range(value: float):
    def apply(d: dict) -> None:
        d["range_m"] = d["range_m"].copy()
        d["range_m"][BAD_ROW] = value

    return apply


def _set_material(value: str):
    def apply(d: dict) -> None:
        d["material"] = d["material"].copy()
        d["material"][BAD_ROW] = value

    return apply


def _short_profile(d: dict) -> None:
    d["range_m"] = d["range_m"].copy()
    d["range_m"][BAD_ROW] = 150.0  # beyond the 99.75 m the profile covers


ROW_CASES = [
    ("beta-negative", _set_beta(-0.001)),
    ("beta-tiny-negative", _set_beta(-1e-300)),
    ("beta-nan", _set_beta(np.nan)),
    ("beta-inf", _set_beta(np.inf)),
    ("beta-neg-inf", _set_beta(-np.inf)),
    ("range-nan", _set_range(np.nan)),
    ("range-inf", _set_range(np.inf)),
    ("range-zero", _set_range(0.0)),
    ("range-negative", _set_range(-3.0)),
    ("range-beyond-profile", _short_profile),
    ("class-dust", _set_material("dust")),
    ("class-upper", _set_material("RETRO")),
    ("class-empty", _set_material("")),
    ("class-other", _set_material("glass")),
]


@pytest.mark.req("FR-013-15")
def test_the_unmodified_inputs_are_accepted() -> None:
    res = _call(_inputs())
    assert res.tau.shape == (N,) and res.cloud["range_m"].shape[0] >= 1


@pytest.mark.req("FR-013-15")
@pytest.mark.parametrize("mutate", [c[1] for c in ROW_CASES], ids=[c[0] for c in ROW_CASES])
def test_a_defective_return_raises_value_error_naming_its_beam_index(mutate) -> None:
    d = _inputs()
    mutate(d)
    with pytest.raises(ValueError) as exc:
        _call(d)
    assert str(BAD_BEAM) in str(exc.value), str(exc.value)


@pytest.mark.req("FR-013-15")
@pytest.mark.parametrize("spacing", [0.0, -0.25, 0.5000001, 1.0, np.nan, np.inf])
def test_a_spacing_outside_zero_to_half_a_metre_is_rejected(spacing: float) -> None:
    d = _inputs()
    d["spacing"] = spacing
    with pytest.raises(ValueError):
        _call(d)
    with pytest.raises(ValueError):
        dust.optical_depth(d["beta"][0], spacing, np.array([10.0]))


@pytest.mark.req("FR-013-15")
@pytest.mark.parametrize("field", ["beam", "range_m", "material", "intensity", "xyz"])
def test_arrays_of_mismatched_length_are_rejected(field: str) -> None:
    d = _inputs()
    d[field] = d[field][:-1]
    with pytest.raises(ValueError):
        _call(d)


@pytest.mark.req("FR-013-15")
def test_a_profile_per_return_with_the_wrong_number_of_rows_is_rejected() -> None:
    d = _inputs()
    d["beta"] = d["beta"][:-1]
    with pytest.raises(ValueError):
        _call(d)


@pytest.mark.req("FR-013-15")
def test_the_accepted_boundaries_still_work() -> None:
    d = _inputs()
    d["spacing"] = 0.5  # exactly the largest allowed spacing: 400 samples reach 199.5 m
    assert _call(d).tau.shape == (N,)
    d = _inputs()
    d["beta"] = np.zeros((N, M))  # zero extinction is fine
    assert not _call(d).emit_dust.any()
    d = _inputs()
    d["range_m"] = d["range_m"].copy()
    d["range_m"][0] = (M - 1) * SPACING  # the profile just reaches the range
    d["range_m"][1] = 1e-9  # a tiny positive range is a valid range
    assert np.isfinite(_call(d).tau).all()


@pytest.mark.req("FR-013-15")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    row=st.integers(0, N - 1),
    sample=st.integers(0, M - 1),
    bad=st.sampled_from([-1e-12, -5.0, np.nan, np.inf, -np.inf]),
)
def test_any_single_bad_extinction_sample_is_found_wherever_it_is(row: int, sample: int, bad: float) -> None:
    d = _inputs()
    d["beta"] = d["beta"].copy()
    d["beta"][row, sample] = bad  # even beyond the return's range: the whole profile is validated
    with pytest.raises(ValueError) as exc:
        _call(d)
    assert str(1000 + row) in str(exc.value)


@pytest.mark.req("FR-013-15")
def test_no_partial_cloud_is_returned_and_the_inputs_are_not_modified() -> None:
    d = _inputs()
    _set_beta(-1.0)(d)
    before = {k: np.array(v, copy=True) if isinstance(v, np.ndarray) else v for k, v in d.items()}
    with pytest.raises(ValueError):
        _call(d)
    for key, value in before.items():
        if isinstance(value, np.ndarray):
            np.testing.assert_array_equal(d[key], value)
    assert kit.TAU_ON == 0.3216  # (the kit constants used by the sibling tests)
