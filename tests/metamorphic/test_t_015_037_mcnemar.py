# ruff: noqa: E501
"""T-015-037: exact McNemar verdicts of "Cosmos beats Qwen base", per type and pooled over the binary types.

Requirements: FR-015-31, P-015-02, SC-015-03.

Spec: specs/015-vlm/spec.md
- FR-015-31: for each type and for all binary queries pooled, Cosmos is compared with Qwen on the paired correctness of the two
  arms: b = queries Cosmos answers correctly and Qwen does not, c = the reverse; "Cosmos beats Qwen base" is stated only if
  b > c and the exact two-sided binomial McNemar test gives p < 0.05, otherwise "no significant difference"; b, c, p and, when
  b + c >= 25, the continuity-corrected chi-square are reported.
- P-015-02: (MR1) swapping the arms swaps b and c and leaves p unchanged; (MR2) adding concordant queries leaves p unchanged;
  (MR3) b = c gives p = 1; hand calculation b = 60, c = 35 gives exact p = 0.013379 (chi2_cc = 6.063); b, c in [0, 5,000],
  rtol 1e-6.
- spec section 7: if b + c = 0 the verdict is "no significant difference" (p = 1).
- spec section 8 (clarification): the exact test is used for every b + c.
- SC-015-03: "Cosmos beats Qwen base" only if McNemar p < 0.05. FR-015-32: unequal lengths, n = 0, negative counts raise ValueError.

Oracle: the worked example of the spec (b = 60, c = 35: p = 0.013379, chi2_cc = (|60 - 35| - 1)^2 / 95 = 576 / 95 = 6.0632);
the exact two-sided binomial tail written in rational arithmetic (`_p015_kit.mcnemar_exact_p`, min(1, 2 P(X <= min(b, c))),
X ~ Binomial(b + c, 1/2)), compared with `scipy.stats.binomtest` in tests/pipeline/test_t_015_037_mcnemar_parity.py; hand
counts for every per-type case below.

Expected API of the implementation (package `pitstudio`, root environment), `pitstudio.reason.stats`:
- `mcnemar_exact(b, c) -> float`: the exact two-sided p; ValueError for a negative or non-integer count.
- `mcnemar(correct_a, correct_b) -> dict`: paired boolean sequences (arm A = Cosmos, arm B = Qwen); returns
  `{"b", "c", "p", "chi2_cc", "verdict"}` with `chi2_cc` None unless b + c >= 25 and `verdict` one of "Cosmos beats Qwen base",
  "no significant difference"; ValueError for unequal lengths or n = 0.
- `compare_arms(cosmos, qwen, *, cosmos_arm="cosmos-q8_0") -> list[dict]`: `cosmos` and `qwen` are lists of query records
  `{"query_id", "type", "correct"}` over the same query ids; returns one `mcnemar_row` of the metrics contract per question type
  present (ascending), then the row of type "pooled-binary" (types 1, 2, 4, 5, 6 pooled).
"""

from __future__ import annotations

import random
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator
from pitstudio.reason import stats

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the shared kit lives in tests/unit
import _p015_contracts as contracts
import _p015_kit as kit

BEATS = "Cosmos beats Qwen base"
NSD = "no significant difference"


def _paired(b: int, c: int, both_right: int = 0, both_wrong: int = 0) -> tuple[list[bool], list[bool]]:
    a = [True] * b + [False] * c + [True] * both_right + [False] * both_wrong
    q = [False] * b + [True] * c + [True] * both_right + [False] * both_wrong
    return a, q


@pytest.mark.req("P-015-02")
def test_hand_calculation_b_60_c_35() -> None:
    assert stats.mcnemar_exact(60, 35) == pytest.approx(0.013379, abs=5e-7)  # spec P-015-02
    r = stats.mcnemar(*_paired(60, 35, both_right=400, both_wrong=100))
    assert (r["b"], r["c"]) == (60, 35)
    assert r["p"] == pytest.approx(0.013379, abs=5e-7)
    assert r["chi2_cc"] == pytest.approx(576 / 95, rel=1e-12)  # (|60 - 35| - 1)^2 / 95 = 6.0632
    assert r["verdict"] == BEATS


@pytest.mark.req("FR-015-31")
@pytest.mark.parametrize(
    ("b", "c", "verdict"),
    [
        (60, 35, BEATS),
        (35, 60, NSD),  # p is the same but b < c: Qwen is better, never "Cosmos beats"
        (40, 40, NSD),  # b = c gives p = 1
        (6, 0, BEATS),  # exact p = 2 / 64 = 0.03125 < 0.05
        (5, 0, NSD),  # exact p = 2 / 32 = 0.0625
        (3, 0, NSD),
        (0, 0, NSD),  # b + c = 0: p = 1
        (12, 2, BEATS),  # n = 14: p = 2 * (1 + 14 + 91) / 16384 = 0.012939
        (10, 4, NSD),  # n = 14, min = 4: p = 2 * (1 + 14 + 91 + 364 + 1001) / 16384 = 0.1796
    ],
)
def test_verdict_needs_b_greater_than_c_and_exact_p_below_0_05(b: int, c: int, verdict: str) -> None:
    r = stats.mcnemar(*_paired(b, c, both_right=7, both_wrong=3))
    assert r["verdict"] == verdict
    assert r["p"] == pytest.approx(kit.mcnemar_exact_p(b, c), rel=1e-6)


@pytest.mark.req("FR-015-31")
def test_hand_values_of_the_small_exact_cases() -> None:
    assert stats.mcnemar_exact(6, 0) == pytest.approx(2 / 64, rel=1e-12)
    assert stats.mcnemar_exact(5, 0) == pytest.approx(2 / 32, rel=1e-12)
    assert stats.mcnemar_exact(12, 2) == pytest.approx(2 * (1 + 14 + 91) / 16384, rel=1e-12)
    assert stats.mcnemar_exact(10, 4) == pytest.approx(2 * (1 + 14 + 91 + 364 + 1001) / 16384, rel=1e-12)
    assert stats.mcnemar_exact(0, 0) == 1.0
    assert stats.mcnemar_exact(7, 7) == 1.0  # the two-sided p is capped at 1


@pytest.mark.req("FR-015-31")
@pytest.mark.parametrize(
    ("b", "c", "has_chi2"),
    [(12, 12, False), (13, 11, False), (14, 11, True), (20, 5, True), (24, 0, False), (25, 0, True)],
)
def test_the_continuity_corrected_chi_square_is_reported_from_b_plus_c_of_25(b: int, c: int, has_chi2: bool) -> None:
    r = stats.mcnemar(*_paired(b, c))
    if has_chi2:
        assert r["chi2_cc"] == pytest.approx((abs(b - c) - 1) ** 2 / (b + c), rel=1e-12)
    else:
        assert r["chi2_cc"] is None


@pytest.mark.req("P-015-02")
@settings(max_examples=300, deadline=None)
@given(st.integers(0, 5000), st.integers(0, 5000))
def test_property_exact_p_equals_the_rational_reference_and_the_relations(b: int, c: int) -> None:
    p = stats.mcnemar_exact(b, c)
    assert p == pytest.approx(kit.mcnemar_exact_p(b, c), rel=1e-6, abs=1e-300)
    assert stats.mcnemar_exact(c, b) == pytest.approx(p, rel=1e-12, abs=1e-300)  # MR1: swapping the arms
    if b == c:
        assert p == 1.0  # MR3
    assert 0.0 <= p <= 1.0


@pytest.mark.req("P-015-02")
@settings(max_examples=200, deadline=None)
@given(
    st.integers(0, 80), st.integers(0, 80), st.integers(0, 300), st.integers(0, 300), st.randoms(use_true_random=False)
)
def test_property_swapping_the_arms_and_adding_concordant_queries_leave_p_unchanged(
    b: int, c: int, both_right: int, both_wrong: int, rnd
) -> None:
    base = stats.mcnemar(*_paired(b, c, both_right=1))
    swapped = stats.mcnemar(*reversed(_paired(b, c, both_right=1)))
    assert (swapped["b"], swapped["c"]) == (c, b)  # MR1
    assert swapped["p"] == pytest.approx(base["p"], rel=1e-12, abs=1e-300)
    a, q = _paired(b, c, both_right + 1, both_wrong)  # MR2 (one concordant query always present, so n > 0)
    idx = list(range(len(a)))
    rnd.shuffle(idx)
    more = stats.mcnemar([a[i] for i in idx], [q[i] for i in idx])
    assert (more["b"], more["c"]) == (b, c)
    assert more["p"] == pytest.approx(base["p"], rel=1e-12, abs=1e-300)
    assert more["verdict"] == base["verdict"]


@pytest.mark.req("SC-015-03")
@settings(max_examples=300, deadline=None)
@given(st.integers(0, 400), st.integers(0, 400))
def test_property_the_claim_is_made_if_and_only_if_b_exceeds_c_and_p_is_below_0_05(b: int, c: int) -> None:
    r = stats.mcnemar(*_paired(b, c, both_right=1))
    expected = BEATS if (b > c and kit.mcnemar_exact_p(b, c) < 0.05) else NSD
    assert r["verdict"] == expected


# ------------------------------------------------------------------------------------------------ per type and pooled
def _records(spec: dict[int, tuple[int, int, int, int]]) -> tuple[list[dict], list[dict]]:
    """spec[type] = (b, c, both right, both wrong); same query ids in both arms."""
    cos, qwn = [], []
    for t, (b, c, rr, ww) in spec.items():
        a, q = _paired(b, c, rr, ww)
        for i, (x, y) in enumerate(zip(a, q, strict=True)):
            cos.append({"query_id": f"t{t}-q{i:04d}", "type": t, "correct": x})
            qwn.append({"query_id": f"t{t}-q{i:04d}", "type": t, "correct": y})
    return cos, qwn


SPEC = {
    1: (60, 35, 300, 100),
    2: (35, 60, 300, 100),
    3: (12, 2, 400, 50),
    4: (40, 40, 200, 200),
    5: (6, 0, 100, 100),
    6: (0, 0, 250, 250),
}


@pytest.mark.req("FR-015-31")
@pytest.mark.req("SC-015-03")
def test_compare_arms_gives_one_row_per_type_and_a_pooled_binary_row() -> None:
    rows = stats.compare_arms(*_records(SPEC), cosmos_arm="cosmos-q8_0")
    assert [r["type"] for r in rows] == [1, 2, 3, 4, 5, 6, "pooled-binary"]
    by = {r["type"]: r for r in rows}
    expected_verdict = {1: BEATS, 2: NSD, 3: BEATS, 4: NSD, 5: BEATS, 6: NSD}
    for t, (b, c, *_rest) in SPEC.items():
        assert (by[t]["b"], by[t]["c"]) == (b, c)
        assert by[t]["p"] == pytest.approx(kit.mcnemar_exact_p(b, c), rel=1e-6)
        assert by[t]["verdict"] == expected_verdict[t]
        assert by[t]["cosmos_arm"] == "cosmos-q8_0"
        assert (by[t]["chi2_cc"] is not None) == (b + c >= 25)
    pooled = by["pooled-binary"]  # types 1, 2, 4, 5, 6: b = 60 + 35 + 40 + 6 + 0, c = 35 + 60 + 40 + 0 + 0
    assert (pooled["b"], pooled["c"]) == (141, 135)
    assert pooled["p"] == pytest.approx(kit.mcnemar_exact_p(141, 135), rel=1e-6)
    assert pooled["verdict"] == NSD  # b > c but p is far above 0.05
    assert pooled["chi2_cc"] == pytest.approx((abs(141 - 135) - 1) ** 2 / 276, rel=1e-12)


@pytest.mark.req("FR-015-31")
def test_the_rows_follow_the_metrics_contract() -> None:
    v = Draft202012Validator(
        {"$ref": contracts.validator("vlm-metrics.schema.json").schema["$id"] + "#/$defs/mcnemar_row"},
        registry=contracts._registry(),
    )
    for arm in ("cosmos-q8_0", "cosmos-bf16"):
        for row in stats.compare_arms(*_records(SPEC), cosmos_arm=arm):
            assert [e.message for e in v.iter_errors(row)] == []


@pytest.mark.req("FR-015-31")
def test_the_pooled_row_ignores_type_3_and_the_record_order() -> None:
    cos, qwn = _records(SPEC)
    rows = stats.compare_arms(cos, qwn)
    shuffled_c, shuffled_q = list(cos), list(qwn)
    random.Random(9).shuffle(shuffled_c)
    random.Random(10).shuffle(shuffled_q)
    again = stats.compare_arms(shuffled_c, shuffled_q)
    assert {r["type"]: (r["b"], r["c"], r["p"]) for r in rows} == {r["type"]: (r["b"], r["c"], r["p"]) for r in again}


@pytest.mark.req("FR-015-31")
def test_a_pooled_binary_win_can_hold_while_single_types_do_not() -> None:
    spec = dict.fromkeys(
        (1, 2, 4, 5, 6), (30, 20, 100, 100)
    )  # each type: n = 50, p = 0.20 (no); pooled b = 150, c = 100
    rows = stats.compare_arms(*_records(spec))
    by = {r["type"]: r for r in rows}
    assert all(by[t]["verdict"] == NSD for t in (1, 2, 4, 5, 6))
    assert by["pooled-binary"]["verdict"] == BEATS  # exact p for (150, 100) is about 0.0019
    assert by["pooled-binary"]["p"] == pytest.approx(kit.mcnemar_exact_p(150, 100), rel=1e-6)


# ------------------------------------------------------------------------------------------------ hostile inputs
@pytest.mark.req("FR-015-32")
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: stats.mcnemar([True, False], [True]), id="unequal-lengths"),
        pytest.param(lambda: stats.mcnemar([], []), id="empty"),
        pytest.param(lambda: stats.mcnemar_exact(-1, 3), id="negative-b"),
        pytest.param(lambda: stats.mcnemar_exact(3, -1), id="negative-c"),
        pytest.param(lambda: stats.mcnemar_exact(1.5, 3), id="fractional-b"),
        pytest.param(lambda: stats.mcnemar_exact(float("nan"), 3), id="nan-b"),
        pytest.param(lambda: stats.compare_arms([], []), id="no-records"),
        pytest.param(
            lambda: stats.compare_arms([{"query_id": "a", "type": 1, "correct": True}], []), id="arms-differ-in-length"
        ),
        pytest.param(
            lambda: stats.compare_arms(
                [{"query_id": "a", "type": 9, "correct": True}], [{"query_id": "a", "type": 9, "correct": True}]
            ),
            id="unknown-type",
        ),
    ],
)
def test_hostile_inputs_raise_value_error(call) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        call()
