"""T-017-011 (D2 sensitivity sweeps): Sobol first-order and total indices (unit, property).

Requirements: FR-017-02 (the seeded Sobol design over the box of section 7; the spec names no index requirement, see the
test-change-requests row of d-cases-2026-11-23).

Oracles (closed forms, independent of the estimator):
- a linear function f = sum a_i x_i of independent uniform inputs is additive, so with V_i = a_i^2 (h_i - l_i)^2 / 12 the
  first-order and the total index of input i are both V_i / sum_j V_j;
- the Ishigami function f = sin x1 + 7 sin^2 x2 + 0.1 x3^4 sin x1 on [-pi, pi]^3 has the published indices
  S = (0.3139, 0.4424, 0) and S_T = (0.5576, 0.4424, 0.2437) (Saltelli et al. 2008, Primer, section 4.6, closed form:
  V = 1/2 + a^2/8 + b pi^4 / 5 + b^2 pi^8 / 18, S1 = (1/2 (1 + b pi^4 / 5)^2) / V, S2 = (a^2 / 8) / V, S13 = 8 b^2 pi^8 /
  225 / V), computed here from the closed form;
- invariance of the indices under f -> c f + d (c != 0);
- determinism in the seed, and hostile arguments named in the ValueError.

Expected public API (module `pitstudio_pipeline.mine_to_mill.sensitivity`, `pipeline/` environment):
    sobol_indices(func, bounds, *, n_base, seed, n_bootstrap=0) -> SobolResult
        func: (m, d) array -> (m,) or (m, k) array; bounds: mapping name -> (low, high), in the column order of the
        mapping; n_base: base sample size N (the function is evaluated N (d + 2) times); seed: scrambling seed.
        SobolResult: names, first_order (d, k), total (d, k), first_order_ci / total_ci ((d, k, 2) or None),
        n_evaluations, n_base, seed, variance (k,).
"""
# ruff: noqa: E501, PT018

from __future__ import annotations

import math

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio_pipeline.mine_to_mill.sensitivity import sobol_indices

PI = math.pi


def _linear(a: np.ndarray):
    return lambda x: x @ a


@pytest.mark.req("FR-017-02")
def test_the_linear_test_function_gives_the_analytical_first_order_and_total_indices() -> None:
    a = np.array([1.0, 2.0, 3.0, 0.5])
    lo = np.array([0.0, -1.0, 2.0, 0.0])
    hi = np.array([1.0, 1.0, 3.0, 4.0])
    bounds = {f"x{i}": (lo[i], hi[i]) for i in range(4)}
    variance = a**2 * (hi - lo) ** 2 / 12.0
    expected = variance / variance.sum()
    result = sobol_indices(_linear(a), bounds, n_base=4096, seed=7)
    assert result.first_order[:, 0] == pytest.approx(expected, abs=0.01)
    assert result.total[:, 0] == pytest.approx(expected, abs=0.01)
    assert result.variance[0] == pytest.approx(variance.sum(), rel=0.02)
    assert result.n_evaluations == 4096 * (4 + 2)


@pytest.mark.req("FR-017-02")
def test_an_input_the_function_ignores_has_zero_first_order_and_total_index() -> None:
    result = sobol_indices(lambda x: 3.0 * x[:, 0] + 0.0 * x[:, 1], {"a": (0, 1), "b": (0, 1)}, n_base=2048, seed=1)
    assert result.first_order[0, 0] == pytest.approx(1.0, abs=0.01)
    assert result.first_order[1, 0] == pytest.approx(0.0, abs=0.01)
    assert result.total[1, 0] == pytest.approx(0.0, abs=0.01)


@pytest.mark.req("FR-017-02")
def test_the_ishigami_function_gives_its_closed_form_indices() -> None:
    a, b = 7.0, 0.1

    def f(x: np.ndarray) -> np.ndarray:
        return np.sin(x[:, 0]) + a * np.sin(x[:, 1]) ** 2 + b * x[:, 2] ** 4 * np.sin(x[:, 0])

    v = 0.5 + a**2 / 8 + b * PI**4 / 5 + b**2 * PI**8 / 18
    s1 = 0.5 * (1 + b * PI**4 / 5) ** 2 / v
    s2 = a**2 / 8 / v
    s13 = 8 * b**2 * PI**8 / 225 / v
    expected_first = np.array([s1, s2, 0.0])
    expected_total = np.array([s1 + s13, s2, s13])
    assert expected_first[0] == pytest.approx(0.3139, abs=1e-4)
    assert expected_total[2] == pytest.approx(0.2437, abs=1e-4)
    result = sobol_indices(f, {"x1": (-PI, PI), "x2": (-PI, PI), "x3": (-PI, PI)}, n_base=8192, seed=3)
    assert result.first_order[:, 0] == pytest.approx(expected_first, abs=0.02)
    assert result.total[:, 0] == pytest.approx(expected_total, abs=0.02)


@pytest.mark.req("FR-017-02")
def test_several_outputs_are_estimated_on_the_same_samples() -> None:
    a = np.array([1.0, 2.0, 0.0])
    b = np.array([0.0, 1.0, 1.0])
    result = sobol_indices(
        lambda x: np.stack([x @ a, x @ b], axis=1), {"p": (0, 1), "q": (0, 1), "r": (0, 1)}, n_base=4096, seed=5
    )
    assert result.first_order.shape == (3, 2)
    assert result.first_order[:, 0] == pytest.approx([0.2, 0.8, 0.0], abs=0.01)
    assert result.first_order[:, 1] == pytest.approx([0.0, 0.5, 0.5], abs=0.01)


@pytest.mark.req("FR-017-02")
def test_the_bootstrap_interval_brackets_the_estimate_and_the_truth_for_the_linear_function() -> None:
    bounds = {"u": (0.0, 1.0), "v": (0.0, 1.0)}
    result = sobol_indices(lambda x: x[:, 0] + 2.0 * x[:, 1], bounds, n_base=2048, seed=11, n_bootstrap=200)
    assert result.first_order_ci is not None and result.total_ci is not None
    assert result.first_order_ci.shape == (2, 1, 2)
    for i, truth in enumerate((0.2, 0.8)):
        lo, hi = result.first_order_ci[i, 0]
        assert lo <= result.first_order[i, 0] <= hi
        assert lo - 0.01 <= truth <= hi + 0.01


@pytest.mark.req("FR-017-02")
def test_the_estimate_is_a_deterministic_function_of_the_seed() -> None:
    bounds = {"u": (0.0, 1.0), "v": (0.0, 1.0), "w": (0.0, 1.0)}

    def f(x: np.ndarray) -> np.ndarray:
        return x[:, 0] * x[:, 1] + np.sin(x[:, 2])

    a = sobol_indices(f, bounds, n_base=512, seed=21)
    b = sobol_indices(f, bounds, n_base=512, seed=21)
    c = sobol_indices(f, bounds, n_base=512, seed=22)
    assert np.array_equal(a.first_order, b.first_order)
    assert np.array_equal(a.total, b.total)
    assert not np.array_equal(a.first_order, c.first_order)


@pytest.mark.req("FR-017-02")
@settings(max_examples=40, deadline=None)
@given(scale=st.floats(0.1, 50.0), shift=st.floats(-100.0, 100.0), sign=st.sampled_from([-1.0, 1.0]))
def test_the_indices_do_not_change_under_an_affine_map_of_the_output(scale, shift, sign):
    bounds = {"u": (0.0, 1.0), "v": (0.0, 2.0), "w": (-1.0, 1.0)}

    def f(x: np.ndarray) -> np.ndarray:
        return x[:, 0] * x[:, 1] + x[:, 2] ** 2

    base = sobol_indices(f, bounds, n_base=256, seed=4)
    moved = sobol_indices(lambda x: sign * scale * f(x) + shift, bounds, n_base=256, seed=4)
    assert moved.first_order == pytest.approx(base.first_order, abs=1e-6)
    assert moved.total == pytest.approx(base.total, abs=1e-6)


@pytest.mark.req("FR-017-02")
@pytest.mark.parametrize(
    ("kwargs", "name"),
    [
        ({"n_base": 1}, "n_base"),
        ({"n_base": 2.5}, "n_base"),
        ({"n_base": 64, "seed": -1}, "seed"),
        ({"n_base": 64, "n_bootstrap": -3}, "n_bootstrap"),
    ],
)
def test_hostile_sample_arguments_are_refused_naming_the_argument(kwargs: dict, name: str) -> None:
    args = {"n_base": 64, "seed": 1, **kwargs}
    with pytest.raises(ValueError, match=name):
        sobol_indices(lambda x: x[:, 0], {"u": (0.0, 1.0)}, **args)


@pytest.mark.req("FR-017-02")
@pytest.mark.parametrize(
    "bounds",
    [{}, {"u": (1.0, 0.0)}, {"u": (0.0, float("nan"))}, {"u": (0.0, float("inf"))}, {"u": (0.0, 1.0, 2.0)}],
)
def test_hostile_bounds_are_refused(bounds: dict) -> None:
    with pytest.raises(ValueError, match="bounds"):
        sobol_indices(lambda x: x[:, 0], bounds, n_base=64, seed=1)


@pytest.mark.req("FR-017-02")
def test_a_constant_or_non_finite_or_misshapen_output_is_refused() -> None:
    bounds = {"u": (0.0, 1.0), "v": (0.0, 1.0)}
    with pytest.raises(ValueError, match="variance"):
        sobol_indices(lambda x: np.ones(len(x)), bounds, n_base=64, seed=1)
    with pytest.raises(ValueError, match="finite"):
        sobol_indices(lambda x: np.where(x[:, 0] > 0.5, np.nan, 1.0), bounds, n_base=64, seed=1)
    with pytest.raises(ValueError, match="shape"):
        sobol_indices(lambda x: x[:5, 0], bounds, n_base=64, seed=1)
