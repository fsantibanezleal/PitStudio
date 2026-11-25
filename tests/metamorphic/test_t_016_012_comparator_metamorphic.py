"""T-016-012: metamorphic and property tests of the comparator (Hypothesis).

Requirements: P-016-01, P-016-02, P-016-03, P-016-04.

Spec: specs/016-export-acceleration/spec.md section 4 (P-016-01 permutation invariance, P-016-02 tolerance
monotonicity, P-016-03 self-comparison and single-element sensitivity, P-016-04 margin theorem); plan.md test strategy
rows P-016-01 ... P-016-04 and "Tolerances and their justification" (argmax margin 2e-4 = 2 x max_abs).

Oracles: the invariants themselves, evaluated on the outputs of the comparator for transformed inputs, plus numpy
(`argsort`, `argmax`) for the margin theorem. Two further metamorphic relations hold exactly in binary64 and are
checked: negating both tensors (the bound depends on |y| only) and scaling both tensors by a power of two with
atol = 0 and no max_abs (the bound and the difference both scale exactly).

Expected API: `pitstudio.export.comparator.compare` as documented in tests/unit/test_t_016_012_parity_comparator.py
(`verdict`, `max_abs_error`, `mismatch_fraction`, `argmax_agreement`, `argmax_rows`, `argmax_rows_small_gap`).
Sizes: 1 to 4,000 elements under Hypothesis (200 examples, thresholds.yaml property_tests.ci_examples_per_test) and one
fixed 10^5-element case per relation that needs the full domain of the property.
"""

from __future__ import annotations

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from pitstudio.export.comparator import compare

N_EXAMPLES = 200
finite = st.floats(min_value=-1e3, max_value=1e3, allow_nan=False, allow_infinity=False)
seeds = st.integers(min_value=0, max_value=2**32 - 1)
log_scale = st.floats(min_value=-9, max_value=-1)  # noise magnitude 1e-9 ... 1e-1
log_tol = st.floats(min_value=-9, max_value=-1)  # tolerance 1e-9 ... 1e-1


def _pair(n: int, seed: int, scale_exp: float) -> tuple[np.ndarray, np.ndarray]:
    rng = np.random.default_rng(seed)
    ref = rng.uniform(-100, 100, n)
    return ref, ref + rng.uniform(-1, 1, n) * 10**scale_exp


def _verdict(r) -> tuple:
    return (r.verdict, r.max_abs_error, r.mismatch_fraction)


# ----------------------------------------------------------------------------------------------------------------------
# P-016-01: permutation invariance
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-016-01")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(n=st.integers(1, 4000), seed=seeds, scale_exp=log_scale)
def test_same_permutation_of_reference_and_candidate_leaves_verdict_error_and_mismatch_unchanged(n, seed, scale_exp):
    ref, cand = _pair(n, seed, scale_exp)
    perm = np.random.default_rng(seed + 1).permutation(n)
    assert _verdict(compare([ref], [cand])) == _verdict(compare([ref[perm]], [cand[perm]]))


@pytest.mark.req("P-016-01")
def test_permutation_invariance_on_100000_elements() -> None:
    ref, cand = _pair(100_000, 12345, -4.5)
    perm = np.random.default_rng(7).permutation(100_000)
    assert _verdict(compare([ref], [cand])) == _verdict(compare([ref[perm]], [cand[perm]]))


@pytest.mark.req("P-016-01")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(rows=st.integers(1, 200), cols=st.integers(2, 6), seed=seeds)
def test_row_permutation_of_class_scores_leaves_the_argmax_report_unchanged(rows, cols, seed):
    rng = np.random.default_rng(seed)
    ref = rng.uniform(-1, 1, (rows, cols))
    cand = ref + rng.uniform(-1, 1, (rows, cols)) * 1e-4
    perm = rng.permutation(rows)
    a = compare([ref], [cand], class_scores=(0,))
    b = compare([ref[perm]], [cand[perm]], class_scores=(0,))
    assert (a.verdict, a.argmax_rows, a.argmax_rows_small_gap, a.argmax_agreement) == (
        b.verdict,
        b.argmax_rows,
        b.argmax_rows_small_gap,
        b.argmax_agreement,
    )


# ----------------------------------------------------------------------------------------------------------------------
# P-016-02: tolerance monotonicity
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-016-02")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(
    n=st.integers(1, 2000),
    seed=seeds,
    scale_exp=log_scale,
    tight=st.tuples(log_tol, log_tol, log_tol),
    slack=st.tuples(st.floats(0, 4), st.floats(0, 4), st.floats(0, 4)),
)
def test_pass_at_a_tight_triple_implies_pass_at_every_looser_triple(n, seed, scale_exp, tight, slack):
    ref, cand = _pair(n, seed, scale_exp)
    t_rtol, t_atol, t_max = (10**e for e in tight)
    l_rtol, l_atol, l_max = (10 ** (e + s) for e, s in zip(tight, slack, strict=True))
    tight_r = compare([ref], [cand], rtol=t_rtol, atol=t_atol, max_abs=t_max)
    loose_r = compare([ref], [cand], rtol=l_rtol, atol=l_atol, max_abs=l_max)
    if tight_r.verdict == "pass":
        assert loose_r.verdict == "pass"
    if loose_r.verdict == "fail":
        assert tight_r.verdict == "fail"  # contrapositive: fails at every tighter triple
    assert tight_r.mismatch_fraction >= loose_r.mismatch_fraction


@pytest.mark.req("P-016-02")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(rows=st.integers(1, 100), seed=seeds, e1=log_tol, e2=log_tol)
def test_monotonicity_also_holds_with_a_class_scores_output(rows, seed, e1, e2):
    rng = np.random.default_rng(seed)
    ref = rng.uniform(-1, 1, (rows, 4))
    cand = ref + rng.uniform(-1, 1, (rows, 4)) * 10**e1
    lo, hi = sorted((e1 - 1, e2 + 1))
    tight = compare([ref], [cand], rtol=10**lo, atol=10**lo, max_abs=10**lo, class_scores=(0,))
    loose = compare([ref], [cand], rtol=10**hi, atol=10**hi, max_abs=10**hi, class_scores=(0,))
    if tight.verdict == "pass":
        assert loose.verdict == "pass"


# ----------------------------------------------------------------------------------------------------------------------
# P-016-03: self-comparison and single-element sensitivity
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-016-03")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(values=st.lists(finite, min_size=1, max_size=2000))
def test_a_tensor_compared_with_itself_passes_with_maximum_error_zero(values):
    x = np.array(values)
    r = compare([x], [x.copy()])
    assert (r.verdict, r.max_abs_error, r.mismatch_fraction) == ("pass", 0.0, 0.0)


@pytest.mark.req("P-016-03")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(
    values=st.lists(finite, min_size=1, max_size=500),
    idx=st.integers(min_value=0, max_value=10**6),
    atol_e=st.floats(-9, -3),
    rtol_e=st.floats(-9, -3),
    sign=st.sampled_from([-1.0, 1.0]),
)
def test_one_element_changed_beyond_atol_plus_rtol_abs_y_makes_the_pair_fail(values, idx, atol_e, rtol_e, sign):
    y = np.array(values)
    i = idx % y.size
    atol, rtol = 10**atol_e, 10**rtol_e
    cand = y.copy()
    cand[i] = y[i] + sign * 1.5 * (atol + rtol * abs(y[i]))
    r = compare([y], [cand], rtol=rtol, atol=atol, max_abs=np.inf)
    assert r.verdict == "fail"
    assert r.mismatch_fraction == pytest.approx(1 / y.size)


@pytest.mark.req("P-016-03")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(values=st.lists(finite, min_size=1, max_size=500), idx=st.integers(0, 10**6), max_e=st.floats(-9, -3))
def test_one_element_changed_beyond_max_abs_makes_the_pair_fail(values, idx, max_e):
    y = np.array(values)
    i = idx % y.size
    max_abs = 10**max_e
    cand = y.copy()
    cand[i] = y[i] + 1.5 * max_abs
    r = compare([y], [cand], rtol=1e6, atol=1e6, max_abs=max_abs)  # elementwise bound is huge: max_abs alone decides
    assert r.verdict == "fail"


# ----------------------------------------------------------------------------------------------------------------------
# P-016-04: the margin theorem
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("P-016-04")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(rows=st.integers(1, 300), cols=st.integers(2, 8), seed=seeds, tau_e=st.floats(-6, -2))
def test_if_the_maximum_difference_is_at_most_tau_argmax_agrees_on_rows_with_gap_above_two_tau(rows, cols, seed, tau_e):
    tau = 10**tau_e
    rng = np.random.default_rng(seed)
    b = rng.uniform(0, 20 * tau, (rows, cols))  # gaps of the order of tau, so both kinds of row occur
    a = b + rng.uniform(-0.99, 0.99, (rows, cols)) * tau
    top2 = np.sort(b, axis=1)[:, -2:]
    gap = top2[:, 1] - top2[:, 0]
    big = gap > 2 * tau
    assert np.all(np.argmax(a, axis=1)[big] == np.argmax(b, axis=1)[big])  # the theorem, by numpy
    r = compare([b], [a], rtol=0.0, atol=tau, max_abs=tau, class_scores=(0,), argmax_gap=2 * tau)
    assert r.verdict == "pass"
    assert r.argmax_agreement == 1.0
    assert r.argmax_rows == rows
    assert r.argmax_rows_small_gap == int(np.sum(~big))


# ----------------------------------------------------------------------------------------------------------------------
# Further exact relations: sign flip, power-of-two scaling
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-04")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(n=st.integers(1, 2000), seed=seeds, scale_exp=log_scale)
def test_negating_both_tensors_leaves_the_verdict_unchanged(n, seed, scale_exp):
    ref, cand = _pair(n, seed, scale_exp)
    assert _verdict(compare([ref], [cand])) == _verdict(compare([-ref], [-cand]))


@pytest.mark.req("FR-016-04")
@settings(max_examples=N_EXAMPLES, deadline=None)
@given(n=st.integers(1, 2000), seed=seeds, scale_exp=log_scale, k=st.integers(-20, 20))
def test_scaling_both_tensors_by_a_power_of_two_with_atol_zero_leaves_the_verdict_unchanged(n, seed, scale_exp, k):
    ref, cand = _pair(n, seed, scale_exp)
    factor = 2.0**k
    kw = {"rtol": 1e-3, "atol": 0.0, "max_abs": np.inf}
    a = compare([ref], [cand], **kw)
    b = compare([ref * factor], [cand * factor], **kw)
    assert (a.verdict, a.mismatch_fraction) == (b.verdict, b.mismatch_fraction)
    assert b.max_abs_error == pytest.approx(a.max_abs_error * factor, rel=1e-12, abs=0.0)
