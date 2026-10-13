"""T-016-042: metamorphic tests of the latency statistics (Hypothesis).

Requirements: P-016-05.

Spec: specs/016-export-acceleration/spec.md P-016-05: multiplying every latency sample by k > 0 multiplies p50, p90,
p95, p99 and their interval bounds by k; adding c > 0 adds c; permuting the samples changes nothing (unit change, shift,
permutation); samples of 50 to 5,000 positive floats; tolerance rtol 1e-12.

Oracles: the three relations themselves, evaluated on `latency_stats` with the same seed for every transformed sample
(the bootstrap resamples the SORTED sample with `default_rng(seed)`, so the resampled indices are identical for a
monotone transformation and for a permutation); `numpy.percentile(method="linear")` for the point values.

Expected API: `pitstudio.accel.stats.latency_stats(samples_ms, *, resamples, seed)` and `percentiles(samples_ms)` as in
tests/unit/test_t_016_042_latency_stats.py. The property tests use `resamples=200` to keep the run short; one fixed
5,000-sample case uses the default 2,000.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.accel.stats import latency_stats, percentiles

KEYS = ("p50", "p90", "p95", "p99")
FIELDS = ("value_ms", "lo_ms", "hi_ms")
RTOL = 1e-12


def _sample(n: int, seed: int) -> np.ndarray:
    return np.random.default_rng(seed).uniform(0.05, 500.0, n)


def _flat(stats: dict) -> np.ndarray:
    return np.array([stats[k][f] for k in KEYS for f in FIELDS])


@pytest.mark.req("P-016-05")
@settings(max_examples=200, deadline=None)
@given(n=st.integers(50, 1000), seed=st.integers(0, 2**32 - 1), k=st.floats(1e-3, 1e3), boot_seed=st.integers(0, 999))
def test_scaling_every_sample_by_k_scales_every_percentile_and_bound_by_k(n, seed, k, boot_seed):
    x = _sample(n, seed)
    base = _flat(latency_stats(x.tolist(), resamples=200, seed=boot_seed))
    scaled = _flat(latency_stats((x * k).tolist(), resamples=200, seed=boot_seed))
    np.testing.assert_allclose(scaled, base * k, rtol=RTOL, atol=0)


@pytest.mark.req("P-016-05")
@settings(max_examples=200, deadline=None)
@given(n=st.integers(50, 1000), seed=st.integers(0, 2**32 - 1), c=st.floats(1e-3, 1e3), boot_seed=st.integers(0, 999))
def test_adding_c_to_every_sample_adds_c_to_every_percentile_and_bound(n, seed, c, boot_seed):
    x = _sample(n, seed)
    base = _flat(latency_stats(x.tolist(), resamples=200, seed=boot_seed))
    shifted = _flat(latency_stats((x + c).tolist(), resamples=200, seed=boot_seed))
    np.testing.assert_allclose(shifted, base + c, rtol=RTOL, atol=0)


@pytest.mark.req("P-016-05")
@settings(max_examples=200, deadline=None)
@given(n=st.integers(50, 1000), seed=st.integers(0, 2**32 - 1), boot_seed=st.integers(0, 999))
def test_permuting_the_samples_changes_nothing(n, seed, boot_seed):
    x = _sample(n, seed)
    perm = np.random.default_rng(seed + 1).permutation(n)
    a = latency_stats(x.tolist(), resamples=200, seed=boot_seed)
    b = latency_stats(x[perm].tolist(), resamples=200, seed=boot_seed)
    assert a == b  # exact: the bootstrap works on the sorted sample


@pytest.mark.req("P-016-05")
@settings(max_examples=200, deadline=None)
@given(n=st.integers(50, 5000), seed=st.integers(0, 2**32 - 1), k=st.floats(1e-3, 1e3), c=st.floats(1e-3, 1e3))
def test_point_percentiles_obey_the_three_relations_and_numpy(n, seed, k, c):
    x = _sample(n, seed)
    base = percentiles(x.tolist())
    for key, q in zip(KEYS, (50, 90, 95, 99), strict=True):
        assert base[key] == pytest.approx(float(np.percentile(x, q, method="linear")), rel=RTOL)
    scaled, shifted = percentiles((x * k).tolist()), percentiles((x + c).tolist())
    perm = percentiles(x[np.random.default_rng(seed).permutation(n)].tolist())
    for key in KEYS:
        assert scaled[key] == pytest.approx(base[key] * k, rel=RTOL)
        assert shifted[key] == pytest.approx(base[key] + c, rel=RTOL)
        assert perm[key] == base[key]


@pytest.mark.req("P-016-05")
def test_the_three_relations_hold_with_the_default_2000_resamples_on_5000_samples() -> None:
    x = _sample(5000, 42)
    base = _flat(latency_stats(x.tolist(), seed=3))
    np.testing.assert_allclose(_flat(latency_stats((x * 2.5).tolist(), seed=3)), base * 2.5, rtol=RTOL, atol=0)
    np.testing.assert_allclose(_flat(latency_stats((x + 7.25).tolist(), seed=3)), base + 7.25, rtol=RTOL, atol=0)
    perm = np.random.default_rng(9).permutation(5000)
    np.testing.assert_array_equal(_flat(latency_stats(x[perm].tolist(), seed=3)), base)
