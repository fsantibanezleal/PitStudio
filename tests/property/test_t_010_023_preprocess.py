"""T-010-023: the shared preprocessor of every C1 forecaster.

Requirements: FR-010-18, P-010-08.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-18), section 4 (P-010-08); plan.md rows FR-010-18 and the
noise-free-bias tolerance (0.2 % of the lead time).

Expected API:
- module `pitstudio.slope.errors`: `InvalidWindowError(ValueError)` (shared with FR-010-29).
- module `pitstudio.slope.preprocess`: `preprocess_window(t, omega, t_c) -> Window` for the observed window [t_0, t_c]
  with
  t_0 = t[0]; uses only the samples with t <= t_c (nothing after the cut-off may influence the result). `Window` has
  `t` and `omega` (512 values: `numpy.linspace(t_0, t_c, 512)` and the linear interpolation of the series on it),
  `delta = (t_c - t_0) / 511`, `v` (512 values: the least-squares slope over 9 consecutive samples assigned to the
  centre
  sample, NaN for the first and last 4), `y` (512 values: 1 / v where v > 0, NaN elsewhere) and `mask` (bool, True
  where y is
  valid). Raises InvalidWindowError for fewer than 2 samples, mismatched lengths, a non-finite value, timestamps that
  are not
  strictly increasing, t_c <= t_0 or t_c beyond the last sample.
- module `pitstudio.slope.baselines`: `inverse_velocity(window) -> Forecast` (T-010-024; used here for P-010-08).

Oracles: the centred least-squares slope of a quadratic equals its derivative at the centre exactly (FR-010-18 row of
the
plan); linear displacement gives a constant velocity; `numpy.interp` and `numpy.linspace` for the resampling; the
closed-form
Voight integral for alpha = 2 (tests/_slope_ttf_ref.py) for P-010-08 (bias bound 0.2 % of the lead time, tolerance
justified
in the plan: the centred 9-point slope of the logarithmic displacement has relative error 3.93 (delta / tau)^2).
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_ttf_ref as k
from pitstudio.slope import baselines, preprocess
from pitstudio.slope.errors import InvalidWindowError

PROP = settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))


@pytest.mark.req("FR-010-18")
def test_the_window_has_512_uniform_samples_and_the_stated_step() -> None:
    t = np.linspace(0.0, 100.0, 301)
    w = preprocess.preprocess_window(t, 0.2 * t, 80.0)
    assert w.t.shape == w.omega.shape == w.v.shape == w.y.shape == w.mask.shape == (512,)
    assert w.t == pytest.approx(np.linspace(0.0, 80.0, 512), rel=1e-12, abs=1e-12)
    assert w.delta == pytest.approx(80.0 / 511.0, rel=1e-12)
    assert w.omega == pytest.approx(0.2 * w.t, rel=1e-12, abs=1e-12)


@pytest.mark.req("FR-010-18")
def test_resampling_is_linear_interpolation_of_an_irregular_series() -> None:
    rng = np.random.default_rng(11)
    t = np.sort(rng.uniform(0.0, 50.0, 120))
    t[0] = 0.0
    omega = np.cumsum(rng.uniform(0.0, 1.0, 120))
    t_c = float(t[100])
    w = preprocess.preprocess_window(t, omega, t_c)
    assert w.omega == pytest.approx(np.interp(np.linspace(t[0], t_c, 512), t, omega), rel=1e-12)


@pytest.mark.req("FR-010-18")
def test_the_centred_least_squares_slope_of_a_quadratic_is_its_derivative_exactly() -> None:
    a, b, c = 0.003, 0.4, 1.0
    t = np.linspace(0.0, 160.0, 512)  # the resampling grid coincides with the samples: no interpolation error
    w = preprocess.preprocess_window(t, a * t**2 + b * t + c, 160.0)
    inner = slice(4, 508)  # 9-point windows are complete from the 5th to the 508th sample
    assert w.v[inner] == pytest.approx(2 * a * w.t[inner] + b, rel=1e-9)
    assert np.all(np.isnan(w.v[:4]))
    assert np.all(np.isnan(w.v[508:]))
    assert not w.mask[:4].any()
    assert not w.mask[508:].any()
    assert w.mask[inner].all()
    assert w.y[inner] == pytest.approx(1.0 / (2 * a * w.t[inner] + b), rel=1e-9)


@pytest.mark.req("FR-010-18")
def test_linear_displacement_gives_a_constant_velocity() -> None:
    t = np.linspace(0.0, 90.0, 400)
    w = preprocess.preprocess_window(t, 3.5 * t - 2.0, 90.0)
    assert w.v[4:508] == pytest.approx(3.5, rel=1e-9)
    assert w.y[4:508] == pytest.approx(1 / 3.5, rel=1e-9)


@pytest.mark.req("FR-010-18")
def test_non_positive_velocities_are_masked_never_inverted() -> None:
    t = np.linspace(0.0, 100.0, 1001)
    omega = np.where(t < 50.0, t, np.where(t < 70.0, 50.0, 50.0 + 2.0 * (t - 70.0)))  # rise, plateau (v = 0), rise
    w = preprocess.preprocess_window(t, omega, 100.0)
    plateau = (w.t > 51.5) & (w.t < 68.5)
    assert not w.mask[plateau].any()
    assert np.all(np.isnan(w.y[plateau]))
    assert np.array_equal(w.mask, np.isfinite(w.y))
    assert np.all(w.y[w.mask] > 0)
    assert np.array_equal(w.mask[4:508], w.v[4:508] > 0)
    down = preprocess.preprocess_window(t, -t, 100.0)  # a wall moving back: nothing is valid
    assert not down.mask.any()


@pytest.mark.req("FR-010-18")
def test_nothing_after_the_cutoff_influences_the_window() -> None:
    rng = np.random.default_rng(12)
    t = np.linspace(0.0, 100.0, 801)
    omega = np.cumsum(rng.uniform(0.0, 1.0, 801))
    a = preprocess.preprocess_window(t, omega, 60.0)
    future = omega.copy()
    future[t > 60.0] += 1e6 * rng.standard_normal(int((t > 60.0).sum()))
    b = preprocess.preprocess_window(t, future, 60.0)
    c = preprocess.preprocess_window(t[t <= 60.0], omega[t <= 60.0], 60.0)
    for other in (b, c):
        assert np.array_equal(a.omega, other.omega)
        assert np.array_equal(np.nan_to_num(a.y, nan=-1.0), np.nan_to_num(other.y, nan=-1.0))


@pytest.mark.req("FR-010-18")
@pytest.mark.parametrize(
    ("t", "omega", "t_c"),
    [
        ([0.0], [0.0], 0.0),
        ([0.0, 1.0, 2.0], [0.0, 1.0], 2.0),
        ([0.0, 1.0, 1.0, 2.0], [0.0, 1.0, 2.0, 3.0], 2.0),  # duplicate timestamp
        ([0.0, 2.0, 1.0, 3.0], [0.0, 1.0, 2.0, 3.0], 3.0),  # non-monotonic
        ([0.0, 1.0, 2.0, 3.0], [0.0, float("nan"), 2.0, 3.0], 3.0),
        ([0.0, 1.0, float("inf"), 3.0], [0.0, 1.0, 2.0, 3.0], 3.0),
        ([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0], 0.0),  # t_c = t_0
        ([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0], -1.0),
        ([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0], 3.5),  # t_c beyond the record
        ([0.0, 1.0, 2.0, 3.0], [0.0, 1.0, 2.0, 3.0], float("nan")),
        ([], [], 1.0),
    ],
)
def test_hostile_windows_raise_invalid_window_error(t, omega, t_c) -> None:
    with pytest.raises(InvalidWindowError):
        preprocess.preprocess_window(t, omega, t_c)
    assert issubclass(InvalidWindowError, ValueError)


@st.composite
def _terminal_case(draw):
    return {
        "terminal_h": draw(st.floats(24.0, 720.0)),
        "v_on_per_day": 10.0 ** draw(st.floats(-1.0, 1.0)),  # 0.1 .. 10 mm/day
        "n": 10 * draw(st.integers(100, 1000)),  # 1,000 .. 10,000 samples, the cut-offs fall on samples
        "cutoff": draw(st.sampled_from([0.5, 0.8])),
    }


@pytest.mark.req("P-010-08")
@PROP
@given(_terminal_case())
def test_noise_free_alpha_2_event_is_forecast_within_0_2_percent_of_the_lead_time(case) -> None:
    s = k.terminal_series(
        alpha=2.0, v_onset_per_day=case["v_on_per_day"], terminal_h=case["terminal_h"], steady_fraction=0.0, n=case["n"]
    )
    t_c = s["t_0"] + case["cutoff"] * (s["t_f"] - s["t_0"])
    seen = s["t"] <= t_c + 1e-9
    w = preprocess.preprocess_window(s["t"][seen], s["omega"][seen], float(t_c))
    f = baselines.inverse_velocity(w)
    assert f.outcome == "predicted"
    assert abs(f.t_hat_f - s["t_f"]) / (s["t_f"] - t_c) <= 0.002
