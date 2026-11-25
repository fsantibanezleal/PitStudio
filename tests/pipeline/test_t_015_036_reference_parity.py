# ruff: noqa: E501
"""T-015-036 (reference-library half): the scoring statistics agree with scikit-learn and SciPy.

Requirements: FR-015-30, P-015-03, P-015-04, P-015-01.

Spec: specs/015-vlm/plan.md test strategy rows FR-015-30 ("reference implementations `sklearn.metrics.balanced_accuracy_score`,
`f1_score`, `roc_auc_score`, `scipy.stats.bootstrap`") and the P-015 rows (Wilson equals `proportion_confint(method="wilson")`).

Oracle: the reference libraries called directly: `sklearn.metrics.balanced_accuracy_score`, `f1_score`, `roc_auc_score`, and
`scipy.stats.binomtest(k, n).proportion_ci(method="wilson")` (SciPy provides the Wilson score interval, so statsmodels is not
needed). This file runs in the `pipeline/` environment, which owns scikit-learn and SciPy (spec 000, FR-000-17); the root
environment has neither. The same statistics are checked against hand calculations and exact arithmetic in
tests/metamorphic/test_t_015_036_task_a_metrics.py.

Expected API of the implementation: as in tests/metamorphic/test_t_015_036_task_a_metrics.py (`pitstudio.reason.stats`:
`balanced_accuracy`, `f1_score`, `auroc`, `wilson_interval`).
"""

from __future__ import annotations

import numpy as np
import pitstudio.reason.stats as stats
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from scipy.stats import binomtest
from sklearn.metrics import balanced_accuracy_score, f1_score, roc_auc_score

BIN = ("yes", "no")
T3 = ("0", "1", "2", "3+")


@pytest.mark.req("P-015-01")
@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(T3), st.sampled_from([*T3, "unparseable"])), min_size=4, max_size=400))
def test_balanced_accuracy_equals_scikit_learn(table: list) -> None:
    truth, pred = [t for t, _ in table], [p for _, p in table]
    assume(len(set(truth)) >= 2)
    assert float(stats.balanced_accuracy(truth, pred, T3)) == pytest.approx(
        balanced_accuracy_score(truth, pred), rel=1e-12
    )


@pytest.mark.req("FR-015-30")
@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(BIN), st.sampled_from([*BIN, "unparseable"])), min_size=2, max_size=400))
def test_binary_f1_equals_scikit_learn(table: list) -> None:
    truth, pred = [t for t, _ in table], [p for _, p in table]
    assert stats.f1_score(truth, pred, BIN) == pytest.approx(
        f1_score(truth, pred, labels=["yes"], average="macro", zero_division=0), rel=1e-12, abs=1e-15
    )


@pytest.mark.req("FR-015-30")
@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(T3), st.sampled_from([*T3, "unparseable"])), min_size=4, max_size=400))
def test_macro_f1_equals_scikit_learn(table: list) -> None:
    truth, pred = [t for t, _ in table], [p for _, p in table]
    expected = f1_score(truth, pred, labels=list(T3), average="macro", zero_division=0)
    assert stats.f1_score(truth, pred, T3) == pytest.approx(expected, rel=1e-12, abs=1e-15)


@pytest.mark.req("P-015-04")
@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from([-3.0, -1.5, -0.5, 0.0, 0.25, 1.0, 2.5, 7.0]), st.booleans()),
        min_size=2,
        max_size=200,
    )
)
def test_auroc_equals_scikit_learn_including_ties(table: list) -> None:
    s, y = [a for a, _ in table], [b for _, b in table]
    assume(0 < sum(y) < len(y))
    assert stats.auroc(s, y) == pytest.approx(roc_auc_score(y, s), rel=1e-12)


@pytest.mark.req("P-015-04")
def test_auroc_equals_scikit_learn_on_continuous_scores() -> None:
    rng = np.random.default_rng(15)
    y = rng.integers(0, 2, 5000).astype(bool)
    s = rng.normal(size=5000) + 0.8 * y
    assert stats.auroc(list(s), list(y)) == pytest.approx(roc_auc_score(y, s), rel=1e-12)


@pytest.mark.req("P-015-03")
@settings(max_examples=300, deadline=None)
@given(st.integers(1, 100_000).flatmap(lambda n: st.tuples(st.just(n), st.integers(0, n))))
def test_wilson_interval_equals_scipy(nk: tuple[int, int]) -> None:
    n, k = nk
    ci = binomtest(k, n).proportion_ci(confidence_level=0.95, method="wilson")
    lo, hi = stats.wilson_interval(k, n)
    assert lo == pytest.approx(ci.low, rel=1e-9, abs=1e-12)
    assert hi == pytest.approx(ci.high, rel=1e-9, abs=1e-12)
