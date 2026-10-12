"""T-011-031 - FR-011-22, P-011-09: seed-ensemble delta interval and its coverage on the fake simulator.

Oracles (independent of the code under test; plan 011 test strategy FR-011-22 and P-011-09):
- the interval formula by hand on fixed numbers: CI = mu_hat +/- t_{0.975, R-1} * sigma_hat * sqrt(1 + 1/S) /
    |g_hat|, with
  sigma_hat the sample standard deviation (R - 1 degrees of freedom) of the R values theta(mu_hat, seed_r) and g_hat the
  central-difference slope of the seed means at mu_hat -/+ h, h = 0.05 mu_hat. Student quantiles are published table
  values: t_{0.975,3} = 3.182446, t_{0.975,7} = 2.364624, t_{0.975,15} = 2.131450 (any t table, e.g. NIST/SEMATECH
      e-Handbook
  1.3.6.7.2). The standard deviation is computed here with `statistics.stdev`;
- the fake simulator of spec P-011-09: theta(mu, seed) = a + b mu + sigma z(seed), z(seed) a standard normal drawn from
  a generator seeded with the packing seed (the same packing seed gives the same noise at every mu, the paired structure
  of a real packing seed);
- binomial arithmetic for the coverage band: over 2,000 trials a true coverage of 0.95 has standard deviation
    0.0049, the
  band [0.93, 0.97] is +/- 4 standard deviations (plan 011, "Coverage band");
- the metamorphic relations of P-011-09: the half-width scales linearly in sigma, as 1 / |b|, is unchanged by a (the
  offset), and by a permutation of the interval seeds.

The identification rule of FR-011-22 ("if the 95 % interval of g_hat contains 0 the parameter is not identified") is
read as the paired per-seed slope interval g_hat +/- t_{0.975,R-1} sd(g_r) / sqrt(R), g_r = (theta_r(mu_hat + h) -
theta_r(mu_hat - h)) / (2 h) (same seed at both ends). Cases below are chosen so that an unpaired reading agrees except
the coverage runs, which are specified by P-011-09 over sigma up to 1 deg and slopes down to 10 deg / unit.

Expected public API (module `pitstudio.calibration.interval`, under `src/pitstudio/calibration/`; the error class is
`pitstudio.calibration.errors.InvalidCalibrationError`):

    seed_ensemble_interval(simulate, mu_hat, *, interval_seeds, n_packing_seeds) -> IntervalResult
        simulate(mu: float, seed: int) -> float          repose angle theta (deg) of one forward simulation;
        interval_seeds: sequence of R >= 2 distinct ints (R = 8 in the protocol);
        n_packing_seeds: S, the number of packing seeds averaged in the loss (S = 2).
        Runs simulate at mu_hat - h, mu_hat, mu_hat + h (h = 0.05 mu_hat) for every interval seed (3 R calls).
        IntervalResult attributes: mu_hat, h, sigma_theta_deg, slope_deg_per_unit, slope_interval_deg_per_unit
        (tuple of 2), t_quantile, half_width, lower, upper (None when not identified), identified (bool),
        simulations (int, = 3 R);  method covers(truth: float) -> bool  (False whenever not identified).
    Raises InvalidCalibrationError for R < 2, repeated interval seeds, mu_hat <= 0 or non-finite, n_packing_seeds < 1,
    or a non-finite simulate output.
"""

from __future__ import annotations

import math
import statistics
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.calibration.errors import InvalidCalibrationError  # noqa: E402
from pitstudio.calibration.interval import seed_ensemble_interval  # noqa: E402

T975 = {3: 3.182446, 7: 2.364624, 15: 2.131450}  # published Student t quantiles, df = R - 1


def noise(seed: int) -> float:
    return float(np.random.default_rng(seed).standard_normal())


class FakeSim:
    """theta(mu, seed) = a + b mu + sigma z(seed); records every call."""

    def __init__(self, a: float, b: float, sigma: float) -> None:
        self.a, self.b, self.sigma = a, b, sigma
        self.calls: list[tuple[float, int]] = []

    def __call__(self, mu: float, seed: int) -> float:
        self.calls.append((mu, seed))
        return self.a + self.b * mu + self.sigma * noise(seed)


SEEDS8 = list(range(1000, 1008))


# ------------------------------------------------------------------ FR-011-22 formula by hand


@pytest.mark.req("FR-011-22")
def test_half_width_equals_the_hand_formula_on_fixed_numbers() -> None:
    sim = FakeSim(a=24.0, b=20.0, sigma=0.1)
    res = seed_ensemble_interval(sim, 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    z = [noise(s) for s in SEEDS8]
    sd = 0.1 * statistics.stdev(z)
    expected = T975[7] * sd * math.sqrt(1.0 + 1.0 / 2.0) / 20.0
    assert res.half_width == pytest.approx(expected, rel=1e-6)  # t quantile quoted to 7 digits
    assert res.sigma_theta_deg == pytest.approx(sd, rel=1e-9)
    assert res.slope_deg_per_unit == pytest.approx(20.0, rel=1e-9)
    assert res.t_quantile == pytest.approx(T975[7], rel=1e-6)
    assert res.identified is True
    assert res.lower == pytest.approx(0.4 - expected, rel=1e-6)
    assert res.upper == pytest.approx(0.4 + expected, rel=1e-6)
    assert res.simulations == 24
    assert res.mu_hat == 0.4
    assert res.h == pytest.approx(0.02, rel=1e-12)


@pytest.mark.req("FR-011-22")
def test_it_runs_exactly_three_mu_values_times_the_interval_seeds() -> None:
    sim = FakeSim(24.0, 20.0, 0.1)
    seed_ensemble_interval(sim, 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    expected = {(mu, s) for mu in (0.4 - 0.02, 0.4, 0.4 + 0.02) for s in SEEDS8}
    assert len(sim.calls) == 24
    assert {(round(mu, 12), s) for mu, s in sim.calls} == {(round(mu, 12), s) for mu, s in expected}


@pytest.mark.req("FR-011-22")
@pytest.mark.parametrize("r", [4, 16])
def test_the_student_quantile_follows_the_number_of_interval_seeds(r: int) -> None:
    sim = FakeSim(24.0, 30.0, 0.05)
    seeds = list(range(200, 200 + r))
    res = seed_ensemble_interval(sim, 0.5, interval_seeds=seeds, n_packing_seeds=3)
    sd = 0.05 * statistics.stdev([noise(s) for s in seeds])
    assert res.t_quantile == pytest.approx(T975[r - 1], rel=1e-6)
    assert res.half_width == pytest.approx(T975[r - 1] * sd * math.sqrt(1.0 + 1.0 / 3.0) / 30.0, rel=1e-6)
    assert res.simulations == 3 * r


@pytest.mark.req("FR-011-22")
def test_a_flat_response_is_not_identified_has_no_bounds_and_never_covers() -> None:
    sim = FakeSim(a=24.0, b=0.0, sigma=0.5)
    res = seed_ensemble_interval(sim, 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    assert res.identified is False
    assert res.lower is None
    assert res.upper is None
    assert res.covers(0.4) is False  # even exactly at the estimate: an unbounded interval cannot inflate coverage
    assert res.slope_interval_deg_per_unit[0] <= 0.0 <= res.slope_interval_deg_per_unit[1]


@pytest.mark.req("FR-011-22")
def test_a_strong_response_is_identified_and_covers_its_own_estimate() -> None:
    res = seed_ensemble_interval(FakeSim(24.0, 40.0, 0.1), 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    assert res.identified is True
    assert res.covers(0.4) is True
    assert res.covers(0.4 + 2.0 * res.half_width) is False
    assert res.covers(0.4 - 2.0 * res.half_width) is False


# ------------------------------------------------------------------ P-011-09 metamorphic relations of the half-width


@pytest.mark.req("P-011-09")
@pytest.mark.parametrize("k", [0.5, 2.0, 3.0])
def test_half_width_scales_linearly_with_sigma(k: float) -> None:
    base = seed_ensemble_interval(FakeSim(24.0, 40.0, 0.05), 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    scaled = seed_ensemble_interval(FakeSim(24.0, 40.0, 0.05 * k), 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    assert scaled.half_width == pytest.approx(k * base.half_width, rel=1e-9)
    assert scaled.sigma_theta_deg == pytest.approx(k * base.sigma_theta_deg, rel=1e-9)


@pytest.mark.req("P-011-09")
@pytest.mark.parametrize("c", [0.5, 2.0, 4.0])
def test_half_width_scales_as_the_inverse_slope(c: float) -> None:
    base = seed_ensemble_interval(FakeSim(24.0, 20.0, 0.05), 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    steeper = seed_ensemble_interval(FakeSim(24.0, 20.0 * c, 0.05), 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    assert steeper.half_width == pytest.approx(base.half_width / c, rel=1e-9)


@pytest.mark.req("P-011-09")
def test_half_width_is_unchanged_by_the_offset_and_by_the_order_of_the_interval_seeds() -> None:
    base = seed_ensemble_interval(FakeSim(24.0, 30.0, 0.1), 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    shifted = seed_ensemble_interval(FakeSim(-3.0, 30.0, 0.1), 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)
    shuffled = seed_ensemble_interval(FakeSim(24.0, 30.0, 0.1), 0.4, interval_seeds=SEEDS8[::-1], n_packing_seeds=2)
    assert shifted.half_width == pytest.approx(base.half_width, rel=1e-9)
    assert shuffled.half_width == pytest.approx(base.half_width, rel=1e-9)


@pytest.mark.req("P-011-09")
def test_half_width_follows_sqrt_one_plus_one_over_s() -> None:
    one = seed_ensemble_interval(FakeSim(24.0, 30.0, 0.1), 0.4, interval_seeds=SEEDS8, n_packing_seeds=1)
    four = seed_ensemble_interval(FakeSim(24.0, 30.0, 0.1), 0.4, interval_seeds=SEEDS8, n_packing_seeds=4)
    assert one.half_width / four.half_width == pytest.approx(math.sqrt(2.0) / math.sqrt(1.25), rel=1e-9)


# ------------------------------------------------------------------ P-011-09 coverage of the full pipeline


@pytest.mark.req("P-011-09")
@pytest.mark.parametrize(
    ("a", "b", "sigma", "base_seed"),
    [(22.0, 10.0, 1.0, 11), (25.0, 25.0, 0.5, 12), (28.0, 40.0, 0.2, 13), (20.0, 15.0, 0.8, 14)],
)
def test_coverage_over_2000_trials_is_in_the_binomial_band(a: float, b: float, sigma: float, base_seed: int) -> None:
    """Calibration pipeline on the fake: target theta* from one packing seed, the optimiser returns the exact minimiser
    of L(mu) = mean over S = 2 optimisation seeds of (theta - theta*)^2 within the bounds [0.1, 1] (optimiser error 0),
    then the FR-011-22 interval
    with 8 fresh seeds. Truth mu_dagger ~ U[0.3, 0.8]. Seed sets are disjoint by construction."""
    rng = np.random.default_rng(base_seed)
    n_trials = 2000
    covered = 0
    for j in range(n_trials):
        mu_true = float(rng.uniform(0.3, 0.8))
        s_target = 10_000_000 + j * 16
        s_opt = [s_target + 1, s_target + 2]
        s_int = [s_target + 3 + i for i in range(8)]
        theta_star = a + b * mu_true + sigma * noise(s_target)
        mean_opt_noise = sigma * float(np.mean([noise(s) for s in s_opt]))
        mu_hat = (theta_star - a - mean_opt_noise) / b  # argmin of L for the linear fake ...
        mu_hat = min(max(mu_hat, 0.1), 1.0)  # ... inside the optimiser bounds of FR-011-17
        res = seed_ensemble_interval(FakeSim(a, b, sigma), mu_hat, interval_seeds=s_int, n_packing_seeds=2)
        covered += int(res.covers(mu_true))
    assert 0.93 <= covered / n_trials <= 0.97


# ------------------------------------------------------------------ hostile inputs


@pytest.mark.req("FR-011-22")
@pytest.mark.parametrize("seeds", [[5], [], [7, 7, 8, 9]], ids=["one-seed", "no-seed", "repeated-seed"])
def test_too_few_or_repeated_interval_seeds_are_rejected(seeds: list[int]) -> None:
    with pytest.raises(InvalidCalibrationError):
        seed_ensemble_interval(FakeSim(24.0, 20.0, 0.1), 0.4, interval_seeds=seeds, n_packing_seeds=2)


@pytest.mark.req("FR-011-22")
@pytest.mark.parametrize("mu_hat", [0.0, -0.4, float("nan"), float("inf")])
def test_a_non_positive_or_non_finite_estimate_is_rejected(mu_hat: float) -> None:
    with pytest.raises(InvalidCalibrationError):
        seed_ensemble_interval(FakeSim(24.0, 20.0, 0.1), mu_hat, interval_seeds=SEEDS8, n_packing_seeds=2)


@pytest.mark.req("FR-011-22")
def test_a_non_finite_simulator_output_is_rejected() -> None:
    def broken(mu: float, seed: int) -> float:
        return float("nan") if seed == SEEDS8[3] else 24.0 + 20.0 * mu

    with pytest.raises(InvalidCalibrationError):
        seed_ensemble_interval(broken, 0.4, interval_seeds=SEEDS8, n_packing_seeds=2)


@pytest.mark.req("FR-011-22")
def test_zero_packing_seeds_are_rejected() -> None:
    with pytest.raises(InvalidCalibrationError):
        seed_ensemble_interval(FakeSim(24.0, 20.0, 0.1), 0.4, interval_seeds=SEEDS8, n_packing_seeds=0)
