"""T-010-021: SNR estimator.

Requirements: FR-010-12, P-010-11.
Spec: specs/010-slope/spec.md section 3.2 (FR-010-12), section 4 (P-010-11); plan.md rows FR-010-12 and the SNR-recovery
tolerance (15 %, 200 derandomised examples).

Expected API (module `pitstudio.slope.snr`, numpy only):
- `estimate(omega) -> (snr, sigma_hat)` with sigma_hat = 1.4826 MAD(second differences) / sqrt(6) over the record
  (second difference d2_i = O_i+1 - 2 O_i + O_i-1, MAD about the median of d2) and SNR = (O_end - O_0) / sigma_hat.
  ValueError for fewer than 4 samples, a non-1-D input or a non-finite value. A record with sigma_hat = 0 (a noise-free
  polynomial of degree <= 2) either raises ValueError or returns a huge SNR (the spec does not say; both are accepted).
- `sigma_hat(omega)` and `snr_obs(t, omega, t_0, t_f)` (the C1 recipe's SNR_obs: the estimator on the series between
  t_0 and
  t_f, inclusive, by time; ValueError when fewer than 4 samples fall in the interval).

Oracles: a hand-computed 6-sample record; the variance of a second difference of white noise is 6 sigma^2 (so the
estimator recovers sigma of pure Gaussian noise: 15 % bound, 4.7 standard deviations of the estimator at n = 2,000, see
the plan); invariance under adding a + b t (a second difference annihilates a line) and equivariance under scaling are
exact relations. Time is normalised to [0, 1] in the trend generator so that rounding stays below 1e-9 of sigma_min.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_ttf_ref as k
from pitstudio.slope import snr

PROP = settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))


@pytest.mark.req("FR-010-12")
def test_hand_computed_six_sample_record() -> None:
    omega = [0.0, 1.0, 0.0, 1.0, 0.0, 1.0]
    # second differences: -2, 2, -2, 2 -> median 0, MAD 2 -> sigma = 1.4826 x 2 / sqrt(6); SNR = (1 - 0) / sigma
    sigma = 1.4826 * 2.0 / math.sqrt(6.0)
    got_snr, got_sigma = snr.estimate(omega)
    assert got_sigma == pytest.approx(sigma, rel=1e-12)
    assert got_snr == pytest.approx(1.0 / sigma, rel=1e-12)
    assert snr.sigma_hat(omega) == pytest.approx(sigma, rel=1e-12)


@pytest.mark.req("FR-010-12")
def test_matches_the_independent_kit_on_a_noisy_ramp() -> None:
    rng = np.random.default_rng(3)
    omega = np.linspace(0.0, 80.0, 3000) + 0.4 * rng.standard_normal(3000)
    got = snr.estimate(omega)
    assert got == pytest.approx(k.snr_estimate(omega), rel=1e-12)
    assert got[0] == pytest.approx(80.0 / 0.4, rel=0.15)


@pytest.mark.req("FR-010-12")
def test_snr_obs_uses_the_series_between_t0_and_tf_only() -> None:
    rng = np.random.default_rng(4)
    t = np.arange(1000, dtype=float)
    omega = 0.05 * t + 0.3 * rng.standard_normal(1000)
    window = (t >= 100.0) & (t <= 800.0)
    assert snr.snr_obs(t, omega, 100.0, 800.0) == pytest.approx(k.snr_estimate(omega[window])[0], rel=1e-12)
    assert snr.snr_obs(t, omega, 100.0, 800.0) != pytest.approx(k.snr_estimate(omega)[0], rel=1e-3)
    with pytest.raises(ValueError, match=r"."):
        snr.snr_obs(t, omega, 10.0, 12.0)  # three samples only


@pytest.mark.req("FR-010-12")
@pytest.mark.parametrize(
    "bad",
    [[], [1.0], [1.0, 2.0, 3.0], [[1.0, 2.0], [3.0, 4.0], [5.0, 6.0], [7.0, 8.0]], [0.0, 1.0, float("nan"), 3.0, 4.0],
     [0.0, 1.0, float("inf"), 3.0, 4.0], np.zeros((4, 0))],
)  # fmt: skip
def test_hostile_records_are_rejected(bad) -> None:
    with pytest.raises(ValueError, match=r"."):
        snr.estimate(bad)


@pytest.mark.req("FR-010-12")
def test_a_noise_free_quadratic_has_zero_noise_estimate() -> None:
    t = np.arange(100, dtype=float)
    omega = 0.01 * t**2 + 3.0 * t + 2.0  # constant second difference 0.02: MAD = 0
    try:
        value, sigma = snr.estimate(omega)
    except ValueError:
        return
    assert sigma < 1e-12  # exactly 0 in exact arithmetic; rounding of the second difference leaves ~1e-14
    assert value > 1e9


@st.composite
def _noise_case(draw):
    n = draw(st.integers(2_000, 100_000))
    sigma = 10.0 ** draw(st.floats(-3.0, 3.0))
    seed = draw(st.integers(0, 2**32 - 1))
    return n, sigma, seed


@pytest.mark.req("P-010-11")
@PROP
@given(_noise_case(), st.floats(-10.0, 10.0), st.floats(-10.0, 10.0))
def test_sigma_hat_is_unchanged_by_adding_a_line(case, a, b) -> None:
    n, sigma, seed = case
    noise = sigma * np.random.default_rng(seed).standard_normal(n)
    s = np.linspace(0.0, 1.0, n)
    assert snr.sigma_hat(noise + a + b * s) == pytest.approx(snr.sigma_hat(noise), rel=1e-9)


@pytest.mark.req("P-010-11")
@PROP
@given(_noise_case(), st.floats(1e-3, 1e3))
def test_sigma_hat_scales_with_the_series(case, kk) -> None:
    n, sigma, seed = case
    noise = sigma * np.random.default_rng(seed).standard_normal(n)
    assert snr.sigma_hat(kk * noise) == pytest.approx(kk * snr.sigma_hat(noise), rel=1e-9)


@pytest.mark.req("P-010-11")
@PROP
@given(_noise_case())
def test_sigma_hat_recovers_the_sigma_of_pure_gaussian_noise(case) -> None:
    n, sigma, seed = case
    noise = sigma * np.random.default_rng(seed).standard_normal(n)
    assert snr.sigma_hat(noise) == pytest.approx(sigma, rel=0.15)


@pytest.mark.req("FR-010-12")
@PROP
@given(_noise_case(), st.floats(10.0, 1000.0))
def test_snr_of_a_ramp_plus_noise_recovers_range_over_sigma(case, ratio) -> None:
    n, sigma, seed = case
    ramp = np.linspace(0.0, ratio * sigma * 10.0, n)  # range = 10 ratio sigma
    series = ramp + sigma * np.random.default_rng(seed).standard_normal(n)
    value, _ = snr.estimate(series)
    assert value == pytest.approx(10.0 * ratio, rel=0.2)
