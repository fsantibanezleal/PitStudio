"""T-010-015: candidate-set Monte-Carlo probability of failure, Wilson interval, sampling guards.

Requirements: FR-010-03, FR-010-08, P-010-07.
Spec: specs/010-slope/spec.md section 3.1 (FR-010-03, FR-010-08), section 4 (P-010-07), section 7 ("Monte Carlo" row);
plan.md "Test strategy" (FR-010-03 row and the degenerate-distribution identity).

Expected API (module `pitstudio.slope.pof`, numpy only, root environment):
- `InvalidSamplingError(ValueError)`.
- `wilson_interval(k: int, n: int, z: float = 1.96) -> (lower, upper)`.
- `draw_samples(distributions: list[dict], n: int, seed: int) -> dict[str, np.ndarray]`: one float64 array of n values
  per
  distribution (distribution dicts as in `slope-section.schema.json#/$defs/distribution`), keyed
  "<material_id>.<parameter>" (e.g. "fill.cohesion_kpa") or "pore_pressure_ratio". The generator is
  `np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))`; each distribution consumes n uniform draws
  `rng.random(n)` in list order; uniform = lower + (upper - lower) u; normal truncated to [lo, hi] = mean + sd
  Phi^-1(Phi(a) +
  u (Phi(b) - Phi(a))) with a, b the standardised bounds (inverse CDF, never rejection); lognormal with arithmetic
  mean and coefficient of variation cv. Raises InvalidSamplingError for n <= 0 or > 1e6 (or not an int), a scale
  (sd or cv) <= 0 or non-finite, a lognormal mean <= 0, an empty truncation or uniform interval, an unknown
  distribution, or a seed that is not an int in [0, 2**64), before drawing anything.
- `probability_of_failure(section, *, n=None, candidates=None, seed=None, factor_of=None) -> dict` shaped as
  `slope-results.schema.json#/$defs/pof_result`: method "bishop", candidate_set "lowest-F circles of the mean-parameter
  Bishop search", samples, candidates, failures k, pof k / n, wilson_95 {lower, upper, z: 1.96}, seed. Defaults come
  from
  `section["analysis"]["pof"]`. The candidate set is the K lowest-F circles of the mean-parameter Bishop search of the
  section (K <= the number of valid circles); for each sample the factor is the minimum over the candidates and the
  sample fails when it is < 1. `factor_of(samples, circle) -> np.ndarray` (test seam) returns the factors of all
  samples on
  one candidate circle (`pitstudio.slope.lem.Circle`); by default it is Bishop's factor with the sampled parameters.
  Raises InvalidSamplingError (before drawing and before any factor_of call) for n, K, seed out of range as above.

Oracles (independent): Wilson by hand (230 of 10,000 -> 2.02 % to 2.61 %, docs/methods/m13; the closed forms at k = 0
and k = n); the standard library `statistics.NormalDist` for the inverse CDF; the numpy bit generator for the uniforms;
a fake per-circle factor linear in c' (PoF = Phi((c_crit - mu) / sigma) within 3 binomial standard errors); the
section's
own samples counted in the test (k = #(min F < 1)); Kolmogorov-Smirnov distance computed with numpy against the
truncated
normal CDF; zero-variance distributions (k = N x 1[F < 1] exactly); the K lowest circles ranked by the textbook kit.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path
from statistics import NormalDist

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_lem_ref as ref
from pitstudio.slope import lem, pof

PHI = NormalDist()
SMALL = {"entry_points": 6, "exit_points": 6, "radius_ratios": 3, "rho_min": 1.3, "rho_max": 3.0}


def _dist(parameter="cohesion_kpa", kind="normal", material="fill", **kw) -> dict:
    d = {"parameter": parameter, "distribution": kind, **kw}
    if parameter != "pore_pressure_ratio":
        d["material_id"] = material
    return d


def _section(distributions, *, n=2000, k=64, seed=12345, **kw) -> dict:
    sec = ref.planar_section(
        height_m=20.0, slope_deg=35.0, cohesion=kw.pop("cohesion", 25.0), friction=kw.pop("friction", 32.0),
        mode="live", slices=20, methods=("bishop",), search=SMALL,
        pof={"samples": n, "candidates": k, "seed": seed, "distributions": distributions},
        **kw,
    )  # fmt: skip
    return sec


def _ks(sample: np.ndarray, cdf) -> float:
    x = np.sort(sample)
    f = np.array([cdf(v) for v in x])
    n = len(x)
    return float(max(np.max(np.arange(1, n + 1) / n - f), np.max(f - np.arange(0, n) / n)))


def _rng(seed: int) -> np.random.Generator:
    return np.random.Generator(np.random.PCG64(np.random.SeedSequence(seed)))


# ---------------------------------------------------------------------------------------------------------------------
# Wilson interval


@pytest.mark.req("FR-010-03")
def test_wilson_interval_230_of_10000_is_2_02_to_2_61_percent() -> None:
    lo, hi = pof.wilson_interval(230, 10_000)
    assert (round(100 * lo, 2), round(100 * hi, 2)) == (2.02, 2.61)  # published worked example (M13 page)
    assert (lo, hi) == pytest.approx(ref.wilson(230, 10_000), rel=1e-12)


@pytest.mark.req("FR-010-03")
@pytest.mark.parametrize(
    ("k", "n", "lower", "upper"),
    [
        (0, 100, 0.0, 1.96**2 / (100 + 1.96**2)),  # k = 0: lower bound exactly 0, upper = z^2 / (n + z^2)
        (100, 100, 100 / (100 + 1.96**2), 1.0),  # k = n: upper bound exactly 1, lower = n / (n + z^2)
        (1, 1, 1 / (1 + 1.96**2), 1.0),
        (0, 1, 0.0, 1.96**2 / (1 + 1.96**2)),
    ],
)
def test_wilson_interval_closed_forms_at_the_ends(k, n, lower, upper) -> None:
    lo, hi = pof.wilson_interval(k, n)
    assert lo == pytest.approx(lower, abs=1e-12)
    assert hi == pytest.approx(upper, abs=1e-12)


@pytest.mark.req("P-010-07")
@settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
@given(st.integers(10, 100_000), st.data())
def test_wilson_interval_contains_the_estimate_lies_in_unit_interval_and_narrows_with_n(n, data) -> None:
    k = data.draw(st.integers(0, n))
    lo, hi = pof.wilson_interval(k, n)
    assert 0.0 <= lo <= hi <= 1.0  # exactly: DC-010-04 types the bounds as probabilities (clamp the rounding noise)
    assert lo - 1e-15 <= k / n <= hi + 1e-15  # containment up to the last ulp (the textbook form rounds at 1e-16)
    # same proportion, four times the samples: strictly narrower (k = 0 and k = n give the same sign of change)
    if 4 * n <= 400_000:
        lo4, hi4 = pof.wilson_interval(4 * k, 4 * n)
        assert hi4 - lo4 < hi - lo
    assert (lo, hi) == pytest.approx(ref.wilson(k, n), rel=1e-12, abs=1e-15)


# ---------------------------------------------------------------------------------------------------------------------
# sampling: generator, inverse-CDF truncation, reproducibility


@pytest.mark.req("FR-010-03")
def test_uniform_samples_are_the_pcg64_seed_sequence_stream() -> None:
    n, seed = 1000, 20261007
    out = pof.draw_samples([_dist("friction_angle_deg", "uniform", lower=20.0, upper=40.0)], n, seed)
    expected = 20.0 + 20.0 * _rng(seed).random(n)
    assert out["fill.friction_angle_deg"] == pytest.approx(expected, rel=1e-12)


@pytest.mark.req("FR-010-03")
@pytest.mark.parametrize(
    ("mean", "sd", "lo", "hi"),
    [(20.0, 4.0, 0.0, None), (30.0, 3.0, 5.0, 60.0), (0.0, 1.0, 6.0, None), (10.0, 2.0, None, 11.0)],
)
def test_truncated_normal_is_drawn_by_inverse_cdf_never_by_rejection(mean, sd, lo, hi) -> None:
    n, seed = 2000, 99
    d = _dist(kind="normal", mean=mean, sd=sd)
    if lo is not None:
        d["truncate_lower"] = lo
    if hi is not None:
        d["truncate_upper"] = hi
    got = pof.draw_samples([d], n, seed)["fill.cohesion_kpa"]
    a = PHI.cdf((lo - mean) / sd) if lo is not None else 0.0
    b = PHI.cdf((hi - mean) / sd) if hi is not None else 1.0
    u = _rng(seed).random(n)
    if lo is not None and (lo - mean) / sd >= 4.0:  # far upper tail: use the survival function for accuracy
        tail = 1.0 - a
        expected = np.array([mean + sd * -PHI.inv_cdf(tail * (1.0 - ui)) for ui in u])
        assert got == pytest.approx(expected, rel=1e-6)
    else:
        expected = np.array([mean + sd * PHI.inv_cdf(a + ui * (b - a)) for ui in u])
        assert got == pytest.approx(expected, rel=1e-9, abs=1e-9)
    assert np.all(np.isfinite(got))
    if lo is not None:
        assert got.min() >= lo
    if hi is not None:
        assert got.max() <= hi


@pytest.mark.req("FR-010-03")
def test_truncated_normal_matches_its_cdf_in_the_kolmogorov_smirnov_sense() -> None:
    n = 20_000
    got = pof.draw_samples([_dist(kind="normal", mean=20.0, sd=4.0, truncate_lower=0.0, truncate_upper=26.0)], n, 5)[
        "fill.cohesion_kpa"
    ]
    a, b = PHI.cdf(-5.0), PHI.cdf(1.5)
    d_stat = _ks(got, lambda x: (PHI.cdf((x - 20.0) / 4.0) - a) / (b - a))
    assert d_stat < 1.628 / math.sqrt(n)  # 99 % critical value of the one-sample KS test (fixed seed: deterministic)


@pytest.mark.req("FR-010-03")
def test_untruncated_normal_and_lognormal_have_the_declared_moments() -> None:
    n = 200_000
    out = pof.draw_samples(
        [_dist(kind="normal", mean=30.0, sd=3.0), _dist("sigma_ci_mpa", "lognormal", mean=80.0, cv=0.3)], n, 11
    )
    normal, logn = out["fill.cohesion_kpa"], out["fill.sigma_ci_mpa"]
    assert normal.mean() == pytest.approx(30.0, abs=5 * 3.0 / math.sqrt(n))
    assert normal.std(ddof=1) == pytest.approx(3.0, rel=0.01)
    assert logn.min() > 0
    assert logn.mean() == pytest.approx(80.0, rel=0.01)  # arithmetic mean (assumption recorded in the report)
    assert logn.std(ddof=1) / logn.mean() == pytest.approx(0.3, rel=0.03)
    # independent distributions: sample correlation within 5 standard errors of 0
    assert abs(np.corrcoef(normal, logn)[0, 1]) < 5 / math.sqrt(n)


@pytest.mark.req("FR-010-03")
def test_same_seed_same_samples_prefix_property_and_different_seed_differs() -> None:
    d = [_dist(kind="normal", mean=20.0, sd=4.0, truncate_lower=0.0)]
    a, b = pof.draw_samples(d, 300, 7), pof.draw_samples(d, 300, 7)
    assert np.array_equal(a["fill.cohesion_kpa"], b["fill.cohesion_kpa"])
    longer = pof.draw_samples(d, 500, 7)
    assert np.array_equal(longer["fill.cohesion_kpa"][:300], a["fill.cohesion_kpa"])  # common random numbers across N
    assert not np.array_equal(pof.draw_samples(d, 300, 8)["fill.cohesion_kpa"], a["fill.cohesion_kpa"])
    for seed in (0, 2**64 - 1):
        assert len(pof.draw_samples(d, 10, seed)["fill.cohesion_kpa"]) == 10


# ---------------------------------------------------------------------------------------------------------------------
# the PoF function with a fake per-circle factor


def _linear_factor(c_crit: float):
    def factor_of(samples, circle):
        return samples["fill.cohesion_kpa"] / c_crit  # F < 1 iff c' < c_crit, the same on every circle

    return factor_of


@pytest.mark.req("FR-010-03")
def test_pof_of_a_factor_linear_in_cohesion_is_the_normal_cdf_within_three_binomial_standard_errors() -> None:
    n, mu, sd, c_crit = 20_000, 30.0, 5.0, 26.0
    sec = _section([_dist(kind="normal", mean=mu, sd=sd)], n=n)
    res = pof.probability_of_failure(sec, factor_of=_linear_factor(c_crit))
    p = PHI.cdf((c_crit - mu) / sd)
    assert abs(res["failures"] / n - p) <= 3 * math.sqrt(p * (1 - p) / n)
    assert res["pof"] == pytest.approx(res["failures"] / n, rel=1e-12)
    assert res["samples"] == n
    assert res["wilson_95"]["z"] == 1.96
    assert (res["wilson_95"]["lower"], res["wilson_95"]["upper"]) == pytest.approx(ref.wilson(res["failures"], n))
    assert ref.schema_errors(res, "slope-results", "pof_result") == []


@pytest.mark.req("FR-010-03")
def test_k_counts_the_samples_strictly_below_one_and_takes_the_minimum_over_the_candidates() -> None:
    sec = _section([_dist(kind="normal", mean=20.0, sd=4.0)], n=500, k=20)
    seen: list = []

    def factor_of(samples, circle):
        seen.append((circle, samples["fill.cohesion_kpa"].copy()))
        # F = 1 + (entry - 3) / 100 + (c' - 20) / 50 : minimal over circles at the smallest entry x
        return 1.0 + (circle.entry_x_m - 3.0) / 100.0 + (samples["fill.cohesion_kpa"] - 20.0) / 50.0

    res = pof.probability_of_failure(sec, factor_of=factor_of)
    circles = [c for c, _ in seen]
    assert len(circles) == len(set(circles)) == 20  # exactly the K candidates, each asked once
    c_values = seen[0][1]
    min_entry = min(c.entry_x_m for c in circles)
    f_min = 1.0 + (min_entry - 3.0) / 100.0 + (c_values - 20.0) / 50.0
    assert res["failures"] == int(np.sum(f_min < 1.0))
    assert res["candidates"] == 20


@pytest.mark.req("FR-010-03")
def test_a_sample_with_factor_exactly_one_is_not_a_failure() -> None:
    sec = _section([_dist(kind="normal", mean=20.0, sd=4.0)], n=100, k=10)
    assert pof.probability_of_failure(sec, factor_of=lambda s, c: np.ones(100))["failures"] == 0
    below = np.nextafter(1.0, 0.0)
    assert pof.probability_of_failure(sec, factor_of=lambda s, c: np.full(100, below))["failures"] == 100


@pytest.mark.req("FR-010-03")
def test_the_candidates_are_the_k_lowest_circles_of_the_mean_parameter_bishop_search() -> None:
    sec = _section([_dist(kind="normal", mean=25.0, sd=3.0)], n=50, k=24, cohesion=25.0)
    circles, f = ref.grid_bishop(sec, 20)
    order = np.argsort(np.where(np.isnan(f), np.inf, f))[:24]
    expected = {tuple(round(float(a[i]), 6) for a in circles) for i in order}
    seen = set()

    def factor_of(samples, c):
        seen.add(tuple(round(v, 6) for v in (c.entry_x_m, c.exit_x_m, c.centre_x_m, c.centre_z_m, c.radius_m)))
        return np.full(50, 2.0)

    pof.probability_of_failure(sec, factor_of=factor_of)
    assert seen == expected


@pytest.mark.req("FR-010-03")
def test_defaults_come_from_the_section_and_can_be_overridden() -> None:
    sec = _section([_dist(kind="normal", mean=20.0, sd=4.0)], n=120, k=7, seed=77)
    res = pof.probability_of_failure(sec, factor_of=lambda s, c: np.ones(len(s["fill.cohesion_kpa"])))
    assert (res["samples"], res["candidates"], res["seed"]) == (120, 7, 77)
    res = pof.probability_of_failure(sec, n=60, candidates=3, seed=5, factor_of=lambda s, c: np.ones(60))
    assert (res["samples"], res["candidates"], res["seed"]) == (60, 3, 5)


@pytest.mark.req("FR-010-03")
def test_zero_variance_distributions_give_k_equal_n_times_the_indicator_of_f_below_one_with_the_real_solver() -> None:
    n = 60
    tiny = [
        _dist("cohesion_kpa", "normal", mean=60.0, sd=1e-12),
        _dist("friction_angle_deg", "normal", mean=40.0, sd=1e-12),
    ]
    strong = _section(tiny, n=n, k=8, cohesion=60.0, friction=40.0)
    assert pof.probability_of_failure(strong)["failures"] == 0  # F well above 1 on every candidate
    weak_d = [
        _dist("cohesion_kpa", "normal", mean=0.0, sd=1e-12, truncate_lower=-1.0),
        _dist("friction_angle_deg", "normal", mean=20.0, sd=1e-12),
    ]
    weak = _section(weak_d, n=n, k=8, cohesion=0.0, friction=20.0)  # infinite-slope F = tan 20 / tan 35 = 0.52
    res = pof.probability_of_failure(weak)
    assert res["failures"] == n
    assert res["wilson_95"]["upper"] == pytest.approx(1.0, abs=1e-12)


@pytest.mark.req("P-010-07")
def test_raising_every_cohesion_sample_by_delta_never_increases_k_with_the_real_solver() -> None:
    # normal without truncation: with the same seed and N the samples of the shifted mean are the old ones plus delta;
    # K = all valid circles, so the candidate set does not move with the mean
    n = 120
    ks = []
    for mean in (10.0, 14.0, 20.0, 30.0):
        sec = _section([_dist(kind="normal", mean=mean, sd=6.0)], n=n, k=1, cohesion=mean, friction=25.0)
        valid = lem.analyse_section(sec)["fos"][0]
        v = valid["circles_evaluated"] - valid["rejected_circles"]
        res = pof.probability_of_failure(sec, candidates=v)
        ks.append(res["failures"])
        assert res["candidates"] == v
    assert ks == sorted(ks, reverse=True)
    assert ks[0] > ks[-1]


# ---------------------------------------------------------------------------------------------------------------------
# FR-010-08: sampling guards


class _Spy:
    def __init__(self) -> None:
        self.calls = 0

    def __call__(self, samples, circle):
        self.calls += 1
        return np.ones(len(next(iter(samples.values()))))


BAD_SEEDS = [-1, 2**64, 2**100, 1.5, "7", float("nan"), [7]]
BAD_DISTRIBUTIONS = [
    ("sd-zero", _dist(kind="normal", mean=20.0, sd=0.0)),
    ("sd-negative", _dist(kind="normal", mean=20.0, sd=-4.0)),
    ("sd-nan", _dist(kind="normal", mean=20.0, sd=float("nan"))),
    ("sd-inf", _dist(kind="normal", mean=20.0, sd=float("inf"))),
    ("cv-zero", _dist("sigma_ci_mpa", "lognormal", mean=80.0, cv=0.0)),
    ("cv-negative", _dist("sigma_ci_mpa", "lognormal", mean=80.0, cv=-0.3)),
    ("cv-nan", _dist("sigma_ci_mpa", "lognormal", mean=80.0, cv=float("nan"))),
    ("lognormal-mean-zero", _dist("sigma_ci_mpa", "lognormal", mean=0.0, cv=0.3)),
    ("lognormal-mean-negative", _dist("sigma_ci_mpa", "lognormal", mean=-5.0, cv=0.3)),
    ("mean-nan", _dist(kind="normal", mean=float("nan"), sd=3.0)),
    ("truncation-empty", _dist(kind="normal", mean=20.0, sd=4.0, truncate_lower=30.0, truncate_upper=10.0)),
    ("truncation-zero-width", _dist(kind="normal", mean=20.0, sd=4.0, truncate_lower=20.0, truncate_upper=20.0)),
    ("uniform-empty", _dist("friction_angle_deg", "uniform", lower=40.0, upper=20.0)),
    ("uniform-zero-width", _dist("friction_angle_deg", "uniform", lower=30.0, upper=30.0)),
    ("uniform-nan", _dist("friction_angle_deg", "uniform", lower=float("nan"), upper=30.0)),
    ("unknown-distribution", _dist(kind="weibull", mean=20.0, sd=4.0)),
]


@pytest.mark.req("FR-010-08")
@pytest.mark.parametrize("n", [0, -1, -1000, 10**6 + 1, 10**9, 2.5, "100", float("nan")])
def test_n_out_of_range_raises_before_any_sample_is_drawn(n) -> None:
    spy = _Spy()
    sec = _section([_dist(kind="normal", mean=20.0, sd=4.0)])
    with pytest.raises(pof.InvalidSamplingError):
        pof.probability_of_failure(sec, n=n, factor_of=spy)
    with pytest.raises(pof.InvalidSamplingError):
        pof.draw_samples([_dist(kind="normal", mean=20.0, sd=4.0)], n, 1)
    assert spy.calls == 0


@pytest.mark.req("FR-010-08")
@pytest.mark.parametrize("seed", BAD_SEEDS, ids=[repr(s) for s in BAD_SEEDS])
def test_seed_that_is_not_an_integer_in_0_to_2_pow_64_raises(seed) -> None:
    spy = _Spy()
    sec = _section([_dist(kind="normal", mean=20.0, sd=4.0)])
    with pytest.raises(pof.InvalidSamplingError):
        pof.probability_of_failure(sec, seed=seed, factor_of=spy)
    with pytest.raises(pof.InvalidSamplingError):
        pof.draw_samples([_dist(kind="normal", mean=20.0, sd=4.0)], 10, seed)
    assert spy.calls == 0


@pytest.mark.req("FR-010-08")
@pytest.mark.parametrize(("name", "dist"), BAD_DISTRIBUTIONS, ids=[b[0] for b in BAD_DISTRIBUTIONS])
def test_invalid_distribution_parameters_raise_before_drawing(name, dist) -> None:
    with pytest.raises(pof.InvalidSamplingError):
        pof.draw_samples([dist], 10, 1)


@pytest.mark.req("FR-010-08")
def test_an_invalid_distribution_among_valid_ones_prevents_all_drawing() -> None:
    good = _dist(kind="normal", mean=20.0, sd=4.0)
    bad = _dist("friction_angle_deg", "normal", mean=30.0, sd=-1.0)
    with pytest.raises(pof.InvalidSamplingError):
        pof.draw_samples([good, bad], 10, 1)


@pytest.mark.req("FR-010-08")
def test_k_outside_one_to_the_number_of_valid_circles_raises_and_the_limits_are_accepted() -> None:
    sec = _section([_dist(kind="normal", mean=20.0, sd=4.0)], n=40)
    row = lem.analyse_section(sec)["fos"][0]
    valid = row["circles_evaluated"] - row["rejected_circles"]
    spy = _Spy()
    for k in (0, -1, valid + 1, 10**6, 2.5):
        with pytest.raises(pof.InvalidSamplingError):
            pof.probability_of_failure(sec, candidates=k, factor_of=spy)
    assert spy.calls == 0
    for k in (1, valid):
        res = pof.probability_of_failure(sec, candidates=k, factor_of=lambda s, c: np.full(40, 2.0))
        assert res["candidates"] == k


@pytest.mark.req("FR-010-08")
def test_the_boundary_values_of_n_and_seed_are_accepted() -> None:
    sec = _section([_dist(kind="normal", mean=20.0, sd=4.0)], n=1000, k=2)
    one = pof.probability_of_failure(sec, n=1, factor_of=lambda s, c: np.array([0.5]))
    assert (one["samples"], one["failures"], one["pof"]) == (1, 1, 1.0)
    big = pof.probability_of_failure(sec, n=10**6, seed=2**64 - 1, factor_of=lambda s, c: np.full(10**6, 2.0))
    assert (big["samples"], big["failures"], big["seed"]) == (10**6, 0, 2**64 - 1)
