# ruff: noqa: E501
"""T-014-025: IL-2 soil randomisation sampler.

Requirements: FR-014-19, P-014-14 (soil half).

Spec: specs/014-robot-learning/spec.md FR-014-19: per episode sample bulk density rho ~ U[1,500, 2,100] kg/m3; cohesion
c ~ U[0, 20] kPa; adhesion c_a ~ U[0, 0.5 c]; friction angle phi ~ U[25 deg, 40 deg]; soil-tool friction delta ~
U[10 deg, min(25 deg, phi)]; surcharge q = 0; initial face profile with +-0.3 m height noise. P-014-14: every sample lies
in its range; the same (seed, episode) reproduces the same sample; samples of distinct episodes pass a
Kolmogorov-Smirnov test against their target distribution (p > 0.001, 10^4 samples); seeds 0 to 2^32 - 1.

Oracle: the ranges of the requirement (hand-written bounds); the Kolmogorov-Smirnov test written in
tests/support/robots_oracles.py (asymptotic series with the Stephens correction, checked there against the classical
critical value 1.358 at p = 0.05) applied to the target uniform CDFs, with the conditional distributions of c_a and delta
reduced to a unit uniform by the transformations u = c_a / (0.5 c) and u = (delta - 10 deg) / (min(25 deg, phi) - 10 deg);
sample correlations of independently drawn parameters (|r| < 0.05, five standard errors of 1/sqrt(10^4)).

Expected API of the implementation (module `pitstudio.robots.randomise`):
    SoilSample: frozen dataclass with float fields rho (kg/m3), c (Pa), c_a (Pa), phi (rad), delta (rad), q (Pa, 0.0),
        face_noise (m, a signed height offset of the initial face profile, |face_noise| <= 0.3 by default)
    sample_soil(seed, episode, randomisation=None) -> SoilSample
        seed: int in [0, 2**32 - 1]; episode: int >= 0. A pure function of (seed, episode, randomisation): the same
        arguments always give the same sample, independent of call order. `randomisation` is the `randomisation` block of
        the IL-2 task parameters (contracts/il-task.schema.json, units as there: bulk_density_kg_m3, cohesion_kpa,
        adhesion_ratio, friction_angle_deg, soil_tool_friction_deg, surcharge_kpa, face_height_noise_m); None means the
        FR-014-19 ranges. A narrower range is honoured; a range with lower > upper or outside the FR-014-19 limits raises
        ValueError naming the key; an out-of-range seed or episode raises ValueError naming `seed` or `episode`; a
        non-integer seed or episode raises TypeError or ValueError.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import robots_oracles as ref
from pitstudio.robots.randomise import sample_soil

DEG = math.pi / 180.0
N = 10_000
SEED = 20_261_012


@pytest.fixture(scope="module")
def samples():
    return [sample_soil(SEED, i) for i in range(N)]


@pytest.mark.req("P-014-14")
def test_the_ks_oracle_reproduces_the_classical_critical_value() -> None:
    # Kolmogorov distribution: Q(1.3581) = 0.05 and Q(1.6276) = 0.01 (published critical values, e.g. Smirnov 1948)
    assert ref.kolmogorov_sf(1.3581) == pytest.approx(0.05, abs=5e-4)
    assert ref.kolmogorov_sf(1.6276) == pytest.approx(0.01, abs=2e-4)
    assert ref.kolmogorov_sf(0.0) == 1.0


@pytest.mark.req("FR-014-19")
@given(st.integers(0, 2**32 - 1), st.integers(0, 10**6))
@settings(max_examples=300, deadline=None)
def test_every_sample_lies_in_its_range(seed, episode) -> None:
    s = sample_soil(seed, episode)
    assert 1500.0 <= s.rho <= 2100.0
    assert 0.0 <= s.c <= 20_000.0
    assert 0.0 <= s.c_a <= 0.5 * s.c
    assert 25.0 * DEG <= s.phi <= 40.0 * DEG
    assert 10.0 * DEG <= s.delta <= min(25.0 * DEG, s.phi)
    assert s.q == 0.0
    assert abs(s.face_noise) <= 0.3
    assert all(math.isfinite(x) for x in (s.rho, s.c, s.c_a, s.phi, s.delta, s.q, s.face_noise))


@pytest.mark.req("P-014-14")
@given(st.integers(0, 2**32 - 1), st.integers(0, 10**6))
@settings(max_examples=200, deadline=None)
def test_the_same_seed_and_episode_reproduce_the_same_sample_in_any_call_order(seed, episode) -> None:
    first = sample_soil(seed, episode)
    sample_soil(seed, episode + 1)  # an unrelated call in between
    again = sample_soil(seed, episode)
    assert first == again


@pytest.mark.req("P-014-14")
def test_distinct_episodes_and_distinct_seeds_give_distinct_samples() -> None:
    base = sample_soil(SEED, 0)
    assert sample_soil(SEED, 1) != base
    assert sample_soil(SEED + 1, 0) != base
    assert len({sample_soil(SEED, i).rho for i in range(200)}) == 200


@pytest.mark.req("P-014-14")
def test_the_seed_extremes_are_accepted() -> None:
    for seed in (0, 2**32 - 1):
        s = sample_soil(seed, 0)
        assert 1500.0 <= s.rho <= 2100.0


@pytest.mark.req("P-014-14")
def test_ks_bulk_density_cohesion_and_friction_angle_are_uniform(samples) -> None:
    rho = [s.rho for s in samples]
    c = [s.c for s in samples]
    phi = [s.phi for s in samples]
    assert ref.ks_pvalue(rho, ref.uniform_cdf(1500.0, 2100.0)) > 0.001
    assert ref.ks_pvalue(c, ref.uniform_cdf(0.0, 20_000.0)) > 0.001
    assert ref.ks_pvalue(phi, ref.uniform_cdf(25.0 * DEG, 40.0 * DEG)) > 0.001


@pytest.mark.req("P-014-14")
def test_ks_adhesion_ratio_and_soil_tool_friction_are_uniform_given_their_parents(samples) -> None:
    ratio = [s.c_a / (0.5 * s.c) for s in samples if s.c > 0.0]
    assert len(ratio) > 0.99 * N
    assert ref.ks_pvalue(ratio, ref.uniform_cdf(0.0, 1.0)) > 0.001
    unit_delta = [(s.delta - 10.0 * DEG) / (min(25.0 * DEG, s.phi) - 10.0 * DEG) for s in samples]
    assert ref.ks_pvalue(unit_delta, ref.uniform_cdf(0.0, 1.0)) > 0.001


@pytest.mark.req("P-014-14")
def test_independent_parameters_are_uncorrelated(samples) -> None:
    rho = np.array([s.rho for s in samples])
    c = np.array([s.c for s in samples])
    phi = np.array([s.phi for s in samples])
    noise = np.array([s.face_noise for s in samples])
    for a, b in ((rho, c), (rho, phi), (c, phi), (rho, noise), (c, noise), (phi, noise)):
        assert abs(float(np.corrcoef(a, b)[0, 1])) < 0.05


@pytest.mark.req("FR-014-19")
def test_the_face_height_noise_spans_both_signs_up_to_the_stated_amplitude(samples) -> None:
    noise = np.array([s.face_noise for s in samples])
    assert noise.min() < -0.15
    assert noise.max() > 0.15
    assert abs(float(noise.mean())) < 0.01


@pytest.mark.req("FR-014-19")
def test_a_narrower_randomisation_block_is_honoured() -> None:
    block = {
        "bulk_density_kg_m3": [1800, 1800],
        "cohesion_kpa": [5, 5],
        "adhesion_ratio": [0.5, 0.5],
        "friction_angle_deg": [30, 30],
        "soil_tool_friction_deg": [20, 20],
        "surcharge_kpa": 0,
        "face_height_noise_m": 0.0,
    }
    s = sample_soil(SEED, 3, block)
    assert s.rho == pytest.approx(1800.0, rel=1e-12)
    assert s.c == pytest.approx(5000.0, rel=1e-12)
    assert s.c_a == pytest.approx(2500.0, rel=1e-12)  # 0.5 * 5 kPa
    assert s.phi == pytest.approx(30.0 * DEG, rel=1e-12)
    assert s.delta == pytest.approx(20.0 * DEG, rel=1e-12)
    assert s.q == 0.0
    assert s.face_noise == 0.0


@pytest.mark.req("FR-014-19")
@pytest.mark.parametrize(
    ("key", "bad"),
    [
        ("bulk_density_kg_m3", [2100, 1500]),  # lower > upper
        ("bulk_density_kg_m3", [1000, 2000]),  # below the FR-014-19 limit
        ("bulk_density_kg_m3", [1500, 2500]),  # above it
        ("cohesion_kpa", [0, 25]),
        ("adhesion_ratio", [0, 0.6]),
        ("friction_angle_deg", [20, 40]),
        ("friction_angle_deg", [25, 45]),
        ("soil_tool_friction_deg", [5, 25]),
        ("soil_tool_friction_deg", [10, 30]),
        ("face_height_noise_m", 0.5),
        ("cohesion_kpa", [math.nan, 10]),
    ],
)
def test_a_range_outside_the_limits_or_inverted_raises_value_error_naming_the_key(key, bad) -> None:
    block = {
        "bulk_density_kg_m3": [1500, 2100],
        "cohesion_kpa": [0, 20],
        "adhesion_ratio": [0, 0.5],
        "friction_angle_deg": [25, 40],
        "soil_tool_friction_deg": [10, 25],
        "surcharge_kpa": 0,
        "face_height_noise_m": 0.3,
    }
    block[key] = bad
    with pytest.raises(ValueError, match=rf"\b{key}\b"):
        sample_soil(SEED, 0, block)


@pytest.mark.req("P-014-14")
@pytest.mark.parametrize(
    ("seed", "episode", "name"), [(-1, 0, "seed"), (2**32, 0, "seed"), (0, -1, "episode"), (5, -(10**6), "episode")]
)
def test_out_of_range_seed_or_episode_raises_value_error_naming_it(seed, episode, name) -> None:
    with pytest.raises(ValueError, match=rf"\b{name}\b"):
        sample_soil(seed, episode)


@pytest.mark.req("P-014-14")
@pytest.mark.parametrize("seed", [1.5, "7", None, math.nan, [1]])
def test_a_non_integer_seed_is_rejected(seed) -> None:
    with pytest.raises((TypeError, ValueError)):
        sample_soil(seed, 0)
