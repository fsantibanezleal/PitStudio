# ruff: noqa: E501
"""T-014-034: IL-1 domain-randomisation sampler.
Requirements: FR-014-13, P-014-14 (IL-1 half).

Spec: specs/014-robot-learning/spec.md FR-014-13: "IL-1 domain randomisation shall sample per episode, from the derived seed: payload
U[0, 1] of rated; rolling resistance U[2, 8] %; tyre-road friction dry U[0.55, 0.75] or wet U[0.25, 0.45] with probability 0.5 each;
actuator delay U{0, 1, 2, 3} control steps; ray noise N(0, (0.02 m + 0.01 r)^2); speed noise N(0, 0.1^2 m^2/s^2); heading noise N(0,
(0.5 deg)^2)." P-014-14: every sample lies in its range; the same (seed, episode) reproduces the same sample; samples of distinct
episodes pass a Kolmogorov-Smirnov test against their target distribution (p > 0.001, 10^4 samples); seeds 0 to 2^32 - 1.

Oracle: the ranges of the requirement; the Kolmogorov-Smirnov test of tests/support/robots_oracles.py against the uniform CDFs; a
chi-square goodness-of-fit test written here for the discrete delay and the wet/dry choice (3 degrees of freedom, critical value
16.266 at p = 0.001; 1 degree of freedom, 10.828 at p = 0.001; published chi-square quantiles); the normal CDF from math.erf for the
noise draws (KS against N(0, sigma^2) with sigma = 0.02 + 0.01 r for fixed ranges r, and against the stated speed and heading sigmas).

Expected API of the implementation (module `pitstudio.robots.randomise`, see T-014-025 for the soil half):
    Il1Sample: frozen dataclass with payload_fraction (-, in [0, 1]), rolling_resistance (dimensionless fraction, 0.02 .. 0.08),
        friction (-), wet (bool; friction in the wet range when True), actuator_delay_steps (int 0..3)
    sample_il1(seed, episode, randomisation=None) -> Il1Sample
        pure function of its arguments (same contract and the same errors for seed and episode as `sample_soil`); `randomisation` is the
        IL-1 block of the task parameters (payload_fraction, rolling_resistance_pct, friction_dry, friction_wet, wet_probability,
        actuator_delay_steps, ray_noise_base_m, ray_noise_per_range, speed_noise_sd_m_per_s, heading_noise_sd_deg), None meaning the
        FR-014-13 values; a range with lower > upper, outside the FR-014-13 limits or non-finite raises ValueError naming the key.
    ray_noise(ranges, rng, *, base_m=0.02, per_range=0.01) -> np.ndarray
        independent N(0, (base_m + per_range r)^2) draws for the array of ranges r (m), from the numpy Generator rng
    speed_noise(rng, size, *, sd=0.1) -> np.ndarray               N(0, sd^2) (m/s)
    heading_noise(rng, size, *, sd_deg=0.5) -> np.ndarray         N(0, (sd_deg deg)^2) returned in rad
"""

from __future__ import annotations

import math
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.robots.randomise import heading_noise, ray_noise, sample_il1, speed_noise

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import robots_oracles as ref

N = 10_000
SEED = 20_261_013


def normal_cdf(sigma: float):
    return lambda x: 0.5 * (1.0 + math.erf(x / (sigma * math.sqrt(2.0))))


@pytest.fixture(scope="module")
def samples():
    return [sample_il1(SEED, i) for i in range(N)]


@pytest.mark.req("FR-014-13")
@given(st.integers(0, 2**32 - 1), st.integers(0, 10**6))
@settings(max_examples=300, deadline=None)
def test_every_sample_lies_in_its_range(seed, episode) -> None:
    s = sample_il1(seed, episode)
    assert 0.0 <= s.payload_fraction <= 1.0
    assert 0.02 <= s.rolling_resistance <= 0.08
    assert (0.25 <= s.friction <= 0.45) if s.wet else (0.55 <= s.friction <= 0.75)
    assert s.actuator_delay_steps in (0, 1, 2, 3)
    assert isinstance(s.actuator_delay_steps, int)
    assert isinstance(s.wet, bool)


@pytest.mark.req("P-014-14")
@given(st.integers(0, 2**32 - 1), st.integers(0, 10**6))
@settings(max_examples=200, deadline=None)
def test_the_same_seed_and_episode_reproduce_the_same_sample_in_any_call_order(seed, episode) -> None:
    first = sample_il1(seed, episode)
    sample_il1(seed, episode + 7)
    assert sample_il1(seed, episode) == first


@pytest.mark.req("P-014-14")
def test_distinct_episodes_and_seeds_differ_and_the_seed_extremes_work() -> None:
    base = sample_il1(SEED, 0)
    assert sample_il1(SEED, 1) != base
    assert sample_il1(SEED + 1, 0) != base
    for seed in (0, 2**32 - 1):
        assert 0.0 <= sample_il1(seed, 0).payload_fraction <= 1.0


@pytest.mark.req("P-014-14")
def test_ks_payload_and_rolling_resistance_are_uniform(samples) -> None:
    assert ref.ks_pvalue([s.payload_fraction for s in samples], ref.uniform_cdf(0.0, 1.0)) > 0.001
    assert ref.ks_pvalue([s.rolling_resistance for s in samples], ref.uniform_cdf(0.02, 0.08)) > 0.001


@pytest.mark.req("P-014-14")
def test_ks_friction_is_uniform_within_each_surface_state(samples) -> None:
    dry = [s.friction for s in samples if not s.wet]
    wet = [s.friction for s in samples if s.wet]
    assert ref.ks_pvalue(dry, ref.uniform_cdf(0.55, 0.75)) > 0.001
    assert ref.ks_pvalue(wet, ref.uniform_cdf(0.25, 0.45)) > 0.001


@pytest.mark.req("FR-014-13")
def test_wet_and_dry_are_equally_likely(samples) -> None:
    wet = sum(s.wet for s in samples)
    chi2 = (wet - N / 2) ** 2 / (N / 2) + ((N - wet) - N / 2) ** 2 / (N / 2)
    assert chi2 < 10.828  # chi-square, 1 dof, p = 0.001


@pytest.mark.req("FR-014-13")
def test_the_actuator_delay_is_uniform_over_zero_to_three_steps(samples) -> None:
    counts = Counter(s.actuator_delay_steps for s in samples)
    assert set(counts) == {0, 1, 2, 3}
    chi2 = sum((counts[k] - N / 4) ** 2 / (N / 4) for k in range(4))
    assert chi2 < 16.266  # chi-square, 3 dof, p = 0.001


@pytest.mark.req("P-014-14")
def test_independent_parameters_are_uncorrelated(samples) -> None:
    a = np.array([s.payload_fraction for s in samples])
    b = np.array([s.rolling_resistance for s in samples])
    c = np.array([float(s.actuator_delay_steps) for s in samples])
    d = np.array([float(s.wet) for s in samples])
    for x, y in ((a, b), (a, c), (b, c), (a, d), (b, d), (c, d)):
        assert abs(float(np.corrcoef(x, y)[0, 1])) < 0.05


@pytest.mark.req("FR-014-13")
def test_a_narrower_randomisation_block_is_honoured() -> None:
    block = {
        "payload_fraction": [0.4, 0.4],
        "rolling_resistance_pct": [5, 5],
        "friction_dry": [0.6, 0.6],
        "friction_wet": [0.3, 0.3],
        "wet_probability": 0.5,
        "actuator_delay_steps": [2, 2],
        "ray_noise_base_m": 0.0,
        "ray_noise_per_range": 0.0,
        "speed_noise_sd_m_per_s": 0.0,
        "heading_noise_sd_deg": 0.0,
    }
    for episode in range(20):
        s = sample_il1(SEED, episode, block)
        assert s.payload_fraction == pytest.approx(0.4, rel=1e-12)
        assert s.rolling_resistance == pytest.approx(0.05, rel=1e-12)
        assert s.friction == pytest.approx(0.3 if s.wet else 0.6, rel=1e-12)
        assert s.actuator_delay_steps == 2


@pytest.mark.req("FR-014-13")
@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("payload_fraction", [0.8, 0.2]),
        ("payload_fraction", [0.0, 1.5]),
        ("rolling_resistance_pct", [1, 8]),
        ("rolling_resistance_pct", [2, 9]),
        ("friction_dry", [0.5, 0.75]),
        ("friction_dry", [0.55, 0.8]),
        ("friction_wet", [0.2, 0.45]),
        ("friction_wet", [0.25, 0.5]),
        ("actuator_delay_steps", [0, 4]),
        ("actuator_delay_steps", [-1, 3]),
        ("ray_noise_base_m", 0.05),
        ("ray_noise_per_range", 0.02),
        ("speed_noise_sd_m_per_s", 0.5),
        ("heading_noise_sd_deg", 2.0),
        ("payload_fraction", [math.nan, 1.0]),
        ("wet_probability", 0.7),
    ],
)
def test_a_range_outside_the_limits_or_inverted_raises_value_error_naming_the_key(key, bad) -> None:
    block = {
        "payload_fraction": [0, 1], "rolling_resistance_pct": [2, 8], "friction_dry": [0.55, 0.75],
        "friction_wet": [0.25, 0.45], "wet_probability": 0.5, "actuator_delay_steps": [0, 3], "ray_noise_base_m": 0.02,
        "ray_noise_per_range": 0.01, "speed_noise_sd_m_per_s": 0.1, "heading_noise_sd_deg": 0.5,
    }  # fmt: skip
    block[key] = bad
    with pytest.raises(ValueError, match=rf"\b{key}\b"):
        sample_il1(SEED, 0, block)


@pytest.mark.req("P-014-14")
@pytest.mark.parametrize(("seed", "episode", "name"), [(-1, 0, "seed"), (2**32, 0, "seed"), (0, -1, "episode")])
def test_out_of_range_seed_or_episode_raises_value_error_naming_it(seed, episode, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        sample_il1(seed, episode)


@pytest.mark.req("P-014-14")
@pytest.mark.parametrize("seed", [1.5, "7", None, math.nan])
def test_a_non_integer_seed_is_rejected(seed) -> None:
    with pytest.raises((TypeError, ValueError)):
        sample_il1(seed, 0)


# -------------------------------------------------------------------------------------------------- noise draws
@pytest.mark.req("FR-014-13")
@pytest.mark.parametrize("r", [0.0, 5.0, 30.0, 60.0])
def test_ray_noise_is_normal_with_sigma_002_plus_001_r(r) -> None:
    rng = np.random.default_rng(7)
    sigma = 0.02 + 0.01 * r
    draws = ray_noise(np.full(20_000, r), rng)
    assert draws.shape == (20_000,)
    assert float(draws.std()) == pytest.approx(sigma, rel=0.03)  # standard error of the std is about 0.5 %
    assert abs(float(draws.mean())) < 4.0 * sigma / math.sqrt(20_000)
    assert ref.ks_pvalue(draws, normal_cdf(sigma)) > 0.001


@pytest.mark.req("FR-014-13")
def test_ray_noise_sigma_follows_each_range_in_one_call() -> None:
    rng = np.random.default_rng(11)
    ranges = np.repeat([1.0, 50.0], 20_000)
    draws = ray_noise(ranges, rng)
    assert float(draws[:20_000].std()) == pytest.approx(0.03, rel=0.03)  # 0.02 + 0.01 * 1
    assert float(draws[20_000:].std()) == pytest.approx(0.52, rel=0.03)  # 0.02 + 0.01 * 50


@pytest.mark.req("FR-014-13")
def test_ray_noise_with_zero_sigma_is_exactly_zero_and_the_sigmas_are_parameters() -> None:
    rng = np.random.default_rng(3)
    assert np.all(ray_noise(np.full(10, 20.0), rng, base_m=0.0, per_range=0.0) == 0.0)
    draws = ray_noise(np.full(20_000, 10.0), rng, base_m=0.1, per_range=0.0)
    assert float(draws.std()) == pytest.approx(0.1, rel=0.03)


@pytest.mark.req("FR-014-13")
def test_speed_noise_is_normal_with_sd_0_1() -> None:
    draws = speed_noise(np.random.default_rng(5), 20_000)
    assert float(draws.std()) == pytest.approx(0.1, rel=0.03)
    assert ref.ks_pvalue(draws, normal_cdf(0.1)) > 0.001


@pytest.mark.req("FR-014-13")
def test_heading_noise_is_normal_with_sd_half_a_degree_returned_in_radians() -> None:
    sd = math.radians(0.5)
    draws = heading_noise(np.random.default_rng(9), 20_000)
    assert float(draws.std()) == pytest.approx(sd, rel=0.03)
    assert ref.ks_pvalue(draws, normal_cdf(sd)) > 0.001


@pytest.mark.req("FR-014-13")
def test_noise_draws_are_reproducible_from_the_generator_state() -> None:
    a = ray_noise(np.full(32, 12.0), np.random.default_rng(42))
    b = ray_noise(np.full(32, 12.0), np.random.default_rng(42))
    np.testing.assert_array_equal(a, b)


@pytest.mark.req("FR-014-13")
@pytest.mark.parametrize("bad", [np.array([-1.0, 5.0]), np.array([np.nan]), np.array([np.inf])])
def test_ray_noise_rejects_negative_or_non_finite_ranges(bad) -> None:
    with pytest.raises(ValueError, match=r"\branges\b"):
        ray_noise(bad, np.random.default_rng(1))
