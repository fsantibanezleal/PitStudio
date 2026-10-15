"""T-016-012: the layer-1 comparator and its fail-closed guard (unit, hostile).

Requirements: FR-016-04, FR-016-39.

Spec: specs/016-export-acceleration/spec.md FR-016-04 (|y_ort - y_pt| <= 1e-5 + 1e-3 |y_pt| for every raw output
element, maximum |y_ort - y_pt| <= 1e-4, argmax agreement for 100 % of the rows of every `class_scores` output whose
reference top-2 gap exceeds 2e-4, smaller-gap rows counted and reported) and FR-016-39 (differing number, shape or dtype
class of outputs, or a non-finite candidate value where the reference is finite, returns `fail` with that reason, never
`pass`); plan.md test strategy rows FR-016-04 and FR-016-39.

Oracles (hand calculation, nothing from the code under test):
- the tolerance boundaries use dyadic numbers (rtol 0.125, atol 0.25, y = 2.0, so the bound is exactly 0.5 and every
  difference below is exact in binary64): a perturbation of exactly 0.5 passes, 0.5 + 2^-20 fails;
- the layer-1 constants (1e-3, 1e-5, 1e-4) are exercised with a 1 percent margin on either side of each bound;
- the argmax rule on hand-built 2 x 2 score matrices, with a dyadic `argmax_gap` of 0.25 so that "gap exactly at the
  threshold" and "gap just above" are exact;
- the mismatch fraction and maximum error of a four-element fixture by hand.

Expected public API (module `pitstudio.export.comparator`, root environment, numpy only):
    compare(reference: Sequence[np.ndarray], candidate: Sequence[np.ndarray], *, rtol: float = 1e-3,
            atol: float = 1e-5, max_abs: float = 1e-4, class_scores: Sequence[int] = (),
            argmax_gap: float = 2e-4) -> ComparisonResult
      `reference` and `candidate` hold one array per graph output; `class_scores` lists the indices of the outputs that
      are class-score matrices (argmax along the last axis, rows = all leading axes flattened).
      ComparisonResult (frozen dataclass or equivalent) with
        verdict: "pass" | "fail"
        reason: str | None          (None exactly when verdict == "pass"; otherwise names the cause, containing for the
                                     FR-016-39 guards the words "output count", "shape", "dtype" or "non-finite"; for
                                     the tolerance causes "tolerance", "max_abs" or "argmax")
        max_abs_error: float | None         (max over all elements and outputs of |candidate - reference|; None when a
                                             structural guard failed before any element was compared)
        mismatch_fraction: float | None     (share of elements with |c - r| > atol + rtol |r|)
        argmax_rows: int | None             (rows of the class_scores outputs)
        argmax_rows_small_gap: int | None   (rows whose reference top-2 gap is <= argmax_gap)
        argmax_agreement: float | None      (share of the rows with gap > argmax_gap where the argmax agrees;
                                             1.0 when there is no such row)
    The verdict is `pass` iff every element is within tolerance AND max_abs_error <= max_abs AND argmax_agreement == 1.
    `compare` never raises for the hostile inputs below; it returns `fail`.
"""

from __future__ import annotations

import numpy as np
import pytest
from pitstudio.export.comparator import compare

DY = {"rtol": 0.125, "atol": 0.25, "max_abs": np.inf}  # dyadic tolerances: bound for y = 2.0 is exactly 0.5


def _one(ref, cand, **kw):
    return compare([np.asarray(ref)], [np.asarray(cand)], **kw)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-04: element tolerance
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-04")
def test_difference_exactly_at_atol_plus_rtol_abs_y_passes_and_just_beyond_fails() -> None:
    at = _one([2.0], [2.5], **DY)
    beyond = _one([2.0], [2.5 + 2.0**-20], **DY)
    assert at.verdict == "pass"
    assert at.reason is None
    assert beyond.verdict == "fail"
    assert beyond.reason is not None
    assert "tolerance" in beyond.reason
    assert at.mismatch_fraction == 0.0
    assert beyond.mismatch_fraction == 1.0


@pytest.mark.req("FR-016-04")
def test_bound_scales_with_the_reference_magnitude_and_is_symmetric_in_sign() -> None:
    # |y| = 8: bound = 0.25 + 0.125 * 8 = 1.25; the candidate may sit on either side of the reference
    assert _one([8.0], [9.25], **DY).verdict == "pass"
    assert _one([8.0], [6.75], **DY).verdict == "pass"
    assert _one([-8.0], [-9.25], **DY).verdict == "pass"
    assert _one([8.0], [9.25 + 2.0**-20], **DY).verdict == "fail"
    assert _one([8.0], [6.75 - 2.0**-20], **DY).verdict == "fail"


@pytest.mark.req("FR-016-04")
def test_layer1_constants_are_the_defaults_atol_part() -> None:
    # reference 0: the bound is atol = 1e-5 (rtol term vanishes); 1 percent margins
    assert _one([0.0], [0.99e-5]).verdict == "pass"
    bad = _one([0.0], [1.01e-5])
    assert bad.verdict == "fail"
    assert "tolerance" in (bad.reason or "")


@pytest.mark.req("FR-016-04")
def test_layer1_constants_are_the_defaults_rtol_part() -> None:
    # reference 0.05: bound = 1e-5 + 1e-3 * 0.05 = 6e-5 (below max_abs 1e-4)
    assert _one([0.05], [0.05 + 0.99 * 6e-5]).verdict == "pass"
    assert _one([0.05], [0.05 + 1.01 * 6e-5]).verdict == "fail"


@pytest.mark.req("FR-016-04")
def test_maximum_absolute_difference_above_max_abs_fails_even_when_every_element_is_within_rtol() -> None:
    # reference 100: elementwise bound = 1e-5 + 0.1 = 0.10001 >> 2e-4, but max_abs = 1e-4 is violated
    result = _one([100.0], [100.0002])
    assert result.verdict == "fail"
    assert "max_abs" in (result.reason or "")
    assert result.mismatch_fraction == 0.0
    assert result.max_abs_error == pytest.approx(2e-4, rel=1e-6)
    assert _one([100.0], [100.00009]).verdict == "pass"


@pytest.mark.req("FR-016-04")
def test_max_abs_error_and_mismatch_fraction_of_a_four_element_fixture_by_hand() -> None:
    ref = np.array([0.0, 2.0, 4.0, -4.0])
    cand = np.array([0.0, 2.5, 4.0, -3.0])  # differences 0, 0.5, 0, 1.0; bounds 0.25, 0.5, 0.75, 0.75
    result = _one(ref, cand, **DY)
    assert result.max_abs_error == 1.0
    assert result.mismatch_fraction == 0.25  # only the last element (1.0 > 0.75) violates
    assert result.verdict == "fail"


@pytest.mark.req("FR-016-04")
def test_multiple_outputs_are_all_compared() -> None:
    a, b = np.array([1.0, 2.0]), np.array([[3.0, 4.0]])
    assert compare([a, b], [a.copy(), b.copy()]).verdict == "pass"
    worse = compare([a, b], [a.copy(), b + 1.0])
    assert worse.verdict == "fail"
    assert worse.max_abs_error == 1.0


@pytest.mark.req("FR-016-04")
def test_float32_candidate_against_float64_reference_is_the_same_dtype_class() -> None:
    ref = np.array([0.5, 1.5], dtype=np.float64)
    assert compare([ref], [ref.astype(np.float32)]).verdict == "pass"  # exactly representable values


@pytest.mark.req("FR-016-04")
def test_a_tensor_compared_with_itself_passes_with_zero_error() -> None:
    x = np.random.default_rng(0).standard_normal((4, 5))
    r = compare([x], [x.copy()], class_scores=(0,))
    assert (r.verdict, r.max_abs_error, r.mismatch_fraction, r.argmax_agreement) == ("pass", 0.0, 0.0, 1.0)


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-04: the margin-aware argmax rule
# ----------------------------------------------------------------------------------------------------------------------

LOOSE = {"rtol": 10.0, "atol": 10.0, "max_abs": np.inf, "argmax_gap": 0.25}  # only the argmax rule can fail


@pytest.mark.req("FR-016-04")
def test_argmax_flip_on_a_row_with_gap_above_the_threshold_fails() -> None:
    ref = np.array([[1.0, 0.7]])  # gap 0.3 > 0.25
    cand = np.array([[0.7, 1.0]])
    r = _one(ref, cand, class_scores=(0,), **LOOSE)
    assert r.verdict == "fail"
    assert "argmax" in (r.reason or "")
    assert (r.argmax_rows, r.argmax_rows_small_gap, r.argmax_agreement) == (1, 0, 0.0)


@pytest.mark.req("FR-016-04")
def test_argmax_flip_on_a_row_with_gap_exactly_at_the_threshold_is_allowed_and_counted() -> None:
    ref = np.array([[1.0, 0.75]])  # gap exactly 0.25: not "exceeding" the threshold
    cand = np.array([[0.75, 1.0]])
    r = _one(ref, cand, class_scores=(0,), **LOOSE)
    assert r.verdict == "pass"
    assert (r.argmax_rows, r.argmax_rows_small_gap, r.argmax_agreement) == (1, 1, 1.0)


@pytest.mark.req("FR-016-04")
def test_argmax_rule_counts_rows_and_reports_agreement_per_the_hand_table() -> None:
    ref = np.array(
        [
            [1.0, 0.0, 0.5],  # gap 0.5 > 0.25, argmax 0
            [0.0, 2.0, 0.0],  # gap 2.0, argmax 1
            [0.5, 0.5, 0.0],  # gap 0 (tie), small
            [0.9, 1.0, 0.0],  # gap 0.1, small
        ]
    )
    cand = np.array(
        [
            [1.0, 0.0, 0.5],  # agrees
            [0.0, 2.0, 0.0],  # agrees
            [0.0, 0.5, 0.5],  # differs, but small gap
            [1.0, 0.9, 0.0],  # differs, small gap
        ]
    )
    r = _one(ref, cand, class_scores=(0,), **LOOSE)
    assert r.verdict == "pass"
    assert (r.argmax_rows, r.argmax_rows_small_gap, r.argmax_agreement) == (4, 2, 1.0)


@pytest.mark.req("FR-016-04")
def test_argmax_rows_are_all_leading_axes_flattened() -> None:
    ref = np.zeros((2, 3, 4))
    ref[..., 0] = 1.0  # every row has gap 1.0 and argmax 0
    r = _one(ref, ref.copy(), class_scores=(0,), **LOOSE)
    assert (r.argmax_rows, r.argmax_rows_small_gap) == (6, 0)


@pytest.mark.req("FR-016-04")
def test_outputs_not_listed_as_class_scores_are_not_subject_to_the_argmax_rule() -> None:
    ref = np.array([[1.0, 0.7]])
    cand = np.array([[0.7, 1.0]])
    r = _one(ref, cand, **LOOSE)  # no class_scores output: argmax is not evaluated
    assert r.verdict == "pass"
    assert r.argmax_rows in (0, None)


@pytest.mark.req("FR-016-04")
def test_default_gap_threshold_is_2e_minus_4() -> None:
    # gap 3e-4 > 2e-4 must agree; the candidate flips it by 1e-4 moves on each score (inside max_abs 1e-4 only
    # marginally), so use a loose max_abs to isolate the argmax rule with the default threshold
    ref = np.array([[1.0, 1.0 - 3e-4]])
    cand = np.array([[1.0 - 2e-4, 1.0 - 1e-4]])  # flipped
    r = _one(ref, cand, class_scores=(0,), rtol=1.0, atol=1.0, max_abs=1.0)
    assert r.verdict == "fail"
    assert "argmax" in (r.reason or "")
    ref2 = np.array([[1.0, 1.0 - 1.5e-4]])  # gap 1.5e-4 <= 2e-4: a flip is tolerated and counted
    cand2 = np.array([[1.0 - 1.5e-4, 1.0]])
    r2 = _one(ref2, cand2, class_scores=(0,), rtol=1.0, atol=1.0, max_abs=1.0)
    assert r2.verdict == "pass"
    assert r2.argmax_rows_small_gap == 1


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-39: fail closed
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-39")
def test_different_shapes_fail_with_the_reason_never_pass() -> None:
    r = _one(np.zeros((2, 3)), np.zeros((3, 2)))
    assert r.verdict == "fail"
    assert "shape" in (r.reason or "")


@pytest.mark.req("FR-016-39")
def test_two_outputs_against_one_fail_with_the_reason() -> None:
    a = np.zeros((2, 3))
    r = compare([a, a], [a])
    assert r.verdict == "fail"
    assert "output count" in (r.reason or "")
    assert compare([a], [a, a]).verdict == "fail"


@pytest.mark.req("FR-016-39")
def test_dtype_class_mismatch_fails_with_the_reason() -> None:
    r = _one(np.zeros(3, dtype=np.float32), np.zeros(3, dtype=np.int64))
    assert r.verdict == "fail"
    assert "dtype" in (r.reason or "")
    assert _one(np.zeros(3, dtype=np.int64), np.zeros(3, dtype=np.float32)).verdict == "fail"


@pytest.mark.req("FR-016-39")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_non_finite_candidate_where_the_reference_is_finite_fails_with_the_reason(bad: float) -> None:
    ref = np.array([1.0, 2.0, 3.0])
    cand = np.array([1.0, bad, 3.0])
    r = _one(ref, cand, rtol=1.0, atol=1.0, max_abs=np.inf)  # tolerances so loose that only the guard can fail it
    assert r.verdict == "fail"
    assert "non-finite" in (r.reason or "")


@pytest.mark.req("FR-016-39")
def test_the_guards_fire_before_any_element_comparison_so_numbers_are_not_reported_as_a_pass() -> None:
    r = _one(np.zeros((2, 3)), np.zeros((3, 2)))
    assert r.verdict != "pass"
    assert r.reason


@pytest.mark.req("FR-016-39")
def test_guard_applies_to_every_output_not_only_the_first() -> None:
    a = np.zeros(3)
    r = compare([a, a], [a, np.array([0.0, np.nan, 0.0])])
    assert r.verdict == "fail"
    assert "non-finite" in (r.reason or "")
