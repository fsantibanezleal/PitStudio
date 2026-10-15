"""T-010-024: inverse-velocity and Bayesian time-to-failure baselines.

Requirements: FR-010-19, FR-010-20, P-010-12.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-19, FR-010-20), section 4 (P-010-12); plan.md rows FR-010-19 (the M14
worked example), FR-010-20 (closed-form conjugate posterior by hand on a 4-point example).

Expected API (module `pitstudio.slope.baselines`, numpy only; `Window` from `pitstudio.slope.preprocess`):
- `Forecast(outcome, t_hat_f, scored_at_cap, q10=None, q90=None)`: outcome "predicted" or "no failure predicted"; for
  "no failure predicted" `t_hat_f` is the horizon cap t_c + 1,024 delta and `scored_at_cap` is True.
- `inverse_velocity_ttf(t, y, *, last_fraction=0.25, min_points=10) -> float | None`: OLS of y on t over the last
  `last_fraction` of the unmasked (finite) samples, at least `min_points` of them; the root -b0 / b1 when b1 < 0 else
  None.
  InvalidWindowError (`pitstudio.slope.errors`) when fewer than `min_points` unmasked samples exist.
- `inverse_velocity(window) -> Forecast`.
- `bayes_posterior(t, y, sigma2, prior_variance=100.0) -> (mean (2,), cov (2, 2))`: conjugate posterior of (b0, b1) for
  y = b0 + b1 t + noise (variance sigma2) with prior N(0, prior_variance I); no standardisation inside.
- `bayesian_ttf(window, *, seed=0, draws=4000) -> Forecast`: on the same last-25 % points in standardised coordinates,
  prior
  N(0, 10^2 I), sigma^2 from the least-squares residuals, `draws` seeded posterior samples (PCG64 through
  SeedSequence), the
  samples with b1 < 0 kept; `t_hat_f` the median and `q10`, `q90` the 10 % and 90 % quantiles of t_f = -b0 / b1 in
  original
  units; fewer than half of the draws with b1 < 0 gives "no failure predicted" scored at the cap.

Oracles (independent): the M14 worked example (1/v = 0.5 - 0.1 t at t = 0, 1, 2, 3 d -> t_f = 5 d); explicit linear
algebra written out for the 4-point posterior (sigma^2 = 1, prior variance 100: precision [[4.01, 6], [6, 14.01]],
determinant 20.1801, mean (10.014, -1.984) / 20.1801); the textbook formulas of the kit for the general posterior and
the
OLS fit (kit: tests/_slope_ttf_ref.py); the delta-method standard deviation of t_f from the OLS covariance for the
width of
the Bayesian interval (the flat-prior limit of the posterior). Tolerances: closed form rtol 1e-12, OLS limit rtol 1e-6
(prior variance 1e8), interval width within 25 % of the delta-method value (4,000 draws, seeded).
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


def _window(noise: float = 0.0, seed: int = 1, cutoff: float = 0.8, n: int = 2400):
    s = k.terminal_series(alpha=2.0, v_onset_per_day=1.0, terminal_h=240.0, steady_fraction=0.2, n=n)
    omega = s["omega"] + noise * np.random.default_rng(seed).standard_normal(n)
    t_c = float(cutoff * s["t_f"])
    keep = s["t"] <= t_c + 1e-9
    return preprocess.preprocess_window(s["t"][keep], omega[keep], t_c), s, t_c


# ---------------------------------------------------------------------------------------------------------------------
# inverse velocity


@pytest.mark.req("FR-010-19")
def test_m14_worked_example_gives_five_days() -> None:
    t = np.array([0.0, 1.0, 2.0, 3.0])
    y = np.array([0.50, 0.40, 0.30, 0.20])  # 1/v = 0.5 - 0.1 t
    assert baselines.inverse_velocity_ttf(t, y, last_fraction=1.0, min_points=2) == pytest.approx(5.0, rel=1e-12)
    # the lead time at t = 3 d is 2 d; the tolerance of 10 % is +-0.2 d (+-4.8 h), as on the M14 page
    assert abs(5.0 - 5.0) <= 0.1 * (5.0 - 3.0)


@pytest.mark.req("FR-010-19")
def test_only_the_last_quarter_of_the_unmasked_samples_is_fitted() -> None:
    t = np.arange(100, dtype=float)
    y = np.where(t < 75, 1000.0 - t, 50.0 - 0.5 * (t - 75.0))  # garbage first, then a line with its root at t = 175
    assert baselines.inverse_velocity_ttf(t, y) == pytest.approx(175.0, rel=1e-12)


@pytest.mark.req("FR-010-19")
def test_at_least_ten_points_are_fitted_even_when_a_quarter_is_fewer() -> None:
    t = np.arange(20, dtype=float)
    y = np.where(t < 10, 5.0, 30.0 - 2.0 * (t - 10.0))  # a quarter of 20 is 5 points, ten are fitted: root of the line
    assert baselines.inverse_velocity_ttf(t, y) == pytest.approx(25.0, rel=1e-12)


@pytest.mark.req("FR-010-19")
def test_masked_samples_are_skipped_when_counting_the_last_quarter() -> None:
    t = np.arange(120, dtype=float)
    y = 100.0 - 0.5 * t
    y[::3] = np.nan  # a third masked
    assert baselines.inverse_velocity_ttf(t, y) == pytest.approx(200.0, rel=1e-12)
    # unmasked points lie on the same line, so the root is its root whatever subset is used; a kinked series pins the
    # subset
    y2 = np.where(t < 90, 400.0, 100.0 - 0.5 * t)
    y2[::3] = np.nan
    assert baselines.inverse_velocity_ttf(t, y2) == pytest.approx(200.0, rel=1e-12)


@pytest.mark.req("FR-010-19")
def test_a_decelerating_fit_is_no_failure_predicted_scored_at_the_cap() -> None:
    t = np.arange(100, dtype=float)
    assert baselines.inverse_velocity_ttf(t, 1.0 + 0.1 * t) is None  # y grows: decelerating
    assert baselines.inverse_velocity_ttf(t, np.full(100, 3.0)) is None  # b1 = 0: not < 0
    w = preprocess.preprocess_window(t, np.sqrt(t) * 5.0, 99.0)  # velocity falls with time
    f = baselines.inverse_velocity(w)
    assert f.outcome == "no failure predicted"
    assert f.scored_at_cap is True
    assert f.t_hat_f == pytest.approx(w.t[-1] + 1024 * w.delta, rel=1e-12)


@pytest.mark.req("FR-010-19")
def test_window_forecast_equals_the_textbook_fit_of_the_window() -> None:
    w, s, t_c = _window(noise=0.0)
    f = baselines.inverse_velocity(w)
    assert f.outcome == "predicted"
    assert f.scored_at_cap is False
    assert f.t_hat_f == pytest.approx(k.iv_ttf(w.t, w.y)[2], rel=1e-9)
    assert abs(f.t_hat_f - s["t_f"]) / (s["t_f"] - t_c) < 2e-3  # P-010-08 regime: the Voight alpha = 2 line


@pytest.mark.req("FR-010-19")
def test_too_few_unmasked_samples_is_an_invalid_window() -> None:
    t = np.arange(50, dtype=float)
    y = np.full(50, np.nan)
    y[:9] = 1.0
    with pytest.raises(InvalidWindowError):
        baselines.inverse_velocity_ttf(t, y)
    with pytest.raises(InvalidWindowError):
        baselines.inverse_velocity_ttf(t, np.full(50, np.nan))
    w = preprocess.preprocess_window(t, -t, 49.0)  # no positive velocity
    with pytest.raises(InvalidWindowError):
        baselines.inverse_velocity(w)


# ---------------------------------------------------------------------------------------------------------------------
# Bayesian time to failure


@pytest.mark.req("FR-010-20")
def test_four_point_posterior_by_hand() -> None:
    t = [0.0, 1.0, 2.0, 3.0]
    y = [0.50, 0.40, 0.30, 0.20]
    mean, cov = baselines.bayes_posterior(t, y, sigma2=1.0, prior_variance=100.0)
    # X'X = [[4, 6], [6, 14]]; precision = X'X + I / 100 = [[4.01, 6], [6.01 - 0.0, 14.01]]; det = 4.01 x 14.01 - 36
    det = 4.01 * 14.01 - 36.0
    assert det == pytest.approx(20.1801, rel=1e-12)
    want_cov = np.array([[14.01, -6.0], [-6.0, 4.01]]) / det
    want_mean = np.array([14.01 * 1.4 - 6.0 * 1.6, -6.0 * 1.4 + 4.01 * 1.6]) / det  # X'y = (1.4, 1.6)
    assert cov == pytest.approx(want_cov, rel=1e-12)
    assert mean == pytest.approx(want_mean, rel=1e-12)


@st.composite
def _regression(draw):
    n = draw(st.integers(4, 500))
    seed = draw(st.integers(0, 2**32 - 1))
    rng = np.random.default_rng(seed)
    t = rng.standard_normal(n)
    y = draw(st.floats(-3, 3)) + draw(st.floats(-3, 3)) * t + 0.3 * rng.standard_normal(n)
    return t, y, draw(st.floats(0.05, 5.0)), draw(st.floats(0.5, 50.0))


@pytest.mark.req("P-010-12")
@PROP
@given(_regression())
def test_posterior_equals_the_closed_form_conjugate_update(case) -> None:
    t, y, sigma2, prior = case
    mean, cov = baselines.bayes_posterior(t, y, sigma2, prior)
    want_mean, want_cov = k.bayes_posterior(t, y, sigma2, prior)
    assert cov == pytest.approx(want_cov, rel=1e-9, abs=1e-12)
    assert mean == pytest.approx(want_mean, rel=1e-9, abs=1e-12)


@pytest.mark.req("P-010-12")
@PROP
@given(_regression())
def test_with_prior_variance_1e8_the_posterior_mean_is_the_ols_fit(case) -> None:
    t, y, sigma2, _ = case
    mean, _ = baselines.bayes_posterior(t, y, sigma2, 1e8)
    ols, *_ = np.linalg.lstsq(np.column_stack([np.ones(len(t)), t]), y, rcond=None)
    assert mean == pytest.approx(ols, rel=1e-6, abs=1e-9)


@pytest.mark.req("P-010-12")
@PROP
@given(_regression(), st.integers(0, 2**32 - 1))
def test_permuting_the_observations_leaves_the_posterior_unchanged(case, seed) -> None:
    t, y, sigma2, prior = case
    order = np.random.default_rng(seed).permutation(len(t))
    m1, c1 = baselines.bayes_posterior(t, y, sigma2, prior)
    m2, c2 = baselines.bayes_posterior(t[order], y[order], sigma2, prior)
    assert m2 == pytest.approx(m1, rel=1e-12, abs=1e-12)
    assert c2 == pytest.approx(c1, rel=1e-12, abs=1e-12)


@pytest.mark.req("FR-010-20")
def test_bayesian_ttf_median_and_interval_follow_the_ols_delta_method() -> None:
    w, _, _ = _window(noise=0.004, seed=5)
    f = baselines.bayesian_ttf(w, seed=9, draws=4000)
    assert f.outcome == "predicted"
    assert f.scored_at_cap is False
    # independent: OLS on the same last quarter of the unmasked points, delta method for the sd of t_f = -b0 / b1
    ok = np.isfinite(w.y)
    tt, yy = w.t[ok][-max(10, -(-ok.sum() // 4)) :], w.y[ok][-max(10, -(-ok.sum() // 4)) :]
    b0, b1, root = k.iv_ttf(w.t, w.y)
    x = np.column_stack([np.ones(len(tt)), tt])
    resid = yy - x @ np.array([b0, b1])
    cov = (resid @ resid / (len(tt) - 2)) * np.linalg.inv(x.T @ x)
    grad = np.array([-1.0 / b1, b0 / b1**2])
    sd = float(np.sqrt(grad @ cov @ grad))
    assert f.t_hat_f == pytest.approx(root, abs=3 * sd + 1e-9)
    assert f.q10 < f.t_hat_f < f.q90
    assert (f.q90 - f.q10) == pytest.approx(2 * 1.2816 * sd, rel=0.25)


@pytest.mark.req("FR-010-20")
def test_bayesian_ttf_is_reproducible_for_a_seed_and_handles_a_noise_free_line() -> None:
    w, _, _ = _window(noise=0.004, seed=5)
    a, b = baselines.bayesian_ttf(w, seed=3), baselines.bayesian_ttf(w, seed=3)
    assert a == b
    other = baselines.bayesian_ttf(w, seed=4)
    assert other.t_hat_f == pytest.approx(a.t_hat_f, rel=5e-3)
    exact, s, t_c = _window(noise=0.0)
    g = baselines.bayesian_ttf(exact, seed=1)  # residuals ~ 0: the noise variance must not make the update singular
    assert g.outcome == "predicted"
    assert abs(g.t_hat_f - s["t_f"]) / (s["t_f"] - t_c) < 5e-3
    assert np.isfinite([g.q10, g.q90]).all()


@pytest.mark.req("FR-010-20")
def test_a_rising_inverse_velocity_is_no_failure_predicted_scored_at_the_cap() -> None:
    t = np.linspace(0.0, 100.0, 600)
    w = preprocess.preprocess_window(t, 20.0 * np.sqrt(t + 1.0), 100.0)  # velocity decays: 1 / v grows
    f = baselines.bayesian_ttf(w, seed=2)
    assert f.outcome == "no failure predicted"
    assert f.scored_at_cap is True
    assert f.t_hat_f == pytest.approx(w.t[-1] + 1024 * w.delta, rel=1e-12)
