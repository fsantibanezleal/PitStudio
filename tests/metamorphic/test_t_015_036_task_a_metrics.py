# ruff: noqa: E501
"""T-015-036: task-A scoring statistics: balanced accuracy, F1, stratified bootstrap intervals, AUROC, Wilson; hostile inputs.

Requirements: FR-015-30, FR-015-32, P-015-01, P-015-03, P-015-04, SC-015-02.

Spec: specs/015-vlm/spec.md
- FR-015-30: for every arm and type the scoring reports balanced accuracy (mean per-class recall), F1 (macro-F1 for type 3),
  their 95 % intervals by a stratified percentile bootstrap (10,000 resamples within each true class, fixed seed), the
  unparseable rate, a breakdown by condition, and, for binary types and the Cosmos Q8_0 and Qwen arms, the AUROC of
  s = log p(yes) - log p(no) at the first answer token (from the top-20 log-probabilities; an absent token takes the 20th).
- FR-015-32: unequal lengths, n = 0, k > n or k < 0, a non-finite score or a label outside the type's classes raise ValueError.
- P-015-01 (balanced accuracy MRs: duplication, label swap, permutation; constant predictor gives 1/K; hand calculation 200
  positives, 800 negatives, TP = 180, TN = 560 gives accuracy 0.74, BA = 0.80, exact), P-015-03 (Wilson MRs and the values
  485/500 -> [0.9511, 0.9817] and half-width 0.0298 at 540/1,080), P-015-04 (AUROC MRs; equals the pair-counting definition).
- SC-015-02: per-type balanced accuracy is reported with its interval for every arm; the row follows
  `contracts/vlm-metrics.schema.json#/$defs/row_a`.

Oracle: hand calculations written out below; exact rational arithmetic and pair counting from `_p015_kit` (checked against
scikit-learn, SciPy and the published values in tests/pipeline/test_t_015_036_reference_parity.py, where those libraries
exist); the normal approximation of the variance of balanced accuracy for the interval width (delta method:
Var(BA) = 1/4 * sum_c r_c (1 - r_c) / n_c, half-width 1.96 sd).

Expected API of the implementation (package `pitstudio`, root environment, NumPy), `pitstudio.reason.stats`:
- `balanced_accuracy(truth, pred, labels) -> fractions.Fraction`: mean over the classes present in `truth` of the recall; `labels`
  is the type's class tuple, `truth` entries must be in it, `pred` entries in it or "unparseable" (always wrong).
- `f1_score(truth, pred, labels) -> float`: F1 of the class "yes" when `labels == ("yes", "no")`, macro-F1 otherwise.
- `bootstrap_ci(truth, pred, labels, *, metric, n_resamples=10_000, seed=0, level=0.95) -> (lo, hi)`; `metric` is
  "balanced_accuracy" or "f1"; resampling is stratified within each true class (class counts fixed), percentile interval.
- `answer_score(top_logprobs: Mapping[str, float]) -> float`: log p("yes") - log p("no") from the first-token top-20 table;
  a token that is absent takes the smallest (20th) log-probability of the table.
- `auroc(scores, positive) -> float`: P(s_pos > s_neg) + 0.5 P(tie); `positive` is a sequence of bool.
- `wilson_interval(k, n, z=1.959963984540054) -> (lo, hi)`.
- `score_row(records, *, arm, qtype, reasoning=False, seed=0, n_resamples=10_000) -> dict`: `records` are dicts with `truth`, `parsed`,
  `condition`, optional `score` (float) and optional `status` ("ok" by default, "error" for an errored query, excluded from the
  scores and counted in `error_rate`); returns a `row_a` of the metrics contract (`status` "measured", `balanced_accuracy` and
  `f1` as `{"value", "lo", "hi"}`, `unparseable_rate`, `error_rate`, `auroc` (None unless `arm` is "cosmos-q8_0" or
  "qwen-base", the type is binary and every record has a score), `by_condition` as `[{"condition", "n", "balanced_accuracy"}]`).
"""

from __future__ import annotations

import inspect
import math
import random
import sys
from fractions import Fraction
from itertools import pairwise
from pathlib import Path

import numpy as np
import pitstudio.reason.stats as stats
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from jsonschema import Draft202012Validator

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "unit"))  # the shared kit lives in tests/unit
import _p015_contracts as contracts
import _p015_kit as kit

BIN = ("yes", "no")
T3 = ("0", "1", "2", "3+")


# ------------------------------------------------------------------------------------------------ hand calculation
def _hand_table() -> tuple[list[str], list[str]]:
    """200 positives (TP = 180), 800 negatives (TN = 560): accuracy 740/1000 = 0.74, BA = (180/200 + 560/800) / 2 = 0.80."""
    truth = ["yes"] * 200 + ["no"] * 800
    pred = ["yes"] * 180 + ["no"] * 20 + ["no"] * 560 + ["yes"] * 240
    return truth, pred


@pytest.mark.req("P-015-01")
def test_balanced_accuracy_hand_calculation_is_exactly_four_fifths() -> None:
    truth, pred = _hand_table()
    assert sum(t == p for t, p in zip(truth, pred, strict=True)) / len(truth) == 0.74
    assert stats.balanced_accuracy(truth, pred, BIN) == Fraction(4, 5)


@pytest.mark.req("P-015-01")
def test_f1_hand_calculation_binary_and_macro() -> None:
    truth, pred = _hand_table()
    # positive class "yes": TP 180, FP 240, FN 20: F1 = 2 TP / (2 TP + FP + FN) = 360 / 620
    assert stats.f1_score(truth, pred, BIN) == pytest.approx(360 / 620, rel=1e-12)
    # type 3, four classes, hand table: class 0 TP 3 FP 1 FN 1; class 1 TP 2 FP 0 FN 2; class 2 TP 4 FP 1 FN 0; class 3 TP 1 FP 4 FN 2
    truth3 = ["0"] * 4 + ["1"] * 4 + ["2"] * 4 + ["3+"] * 3
    pred3 = [*["0", "0", "0", "1"], *["1", "1", "2", "3+"], *["2", "2", "2", "2"], *["3+", "0", "3+"]]
    #  class 0: TP 3, FP 1 (the "3+" true predicted "0"), FN 1  -> F1 = 6 / 8 = 0.75
    #  class 1: TP 2, FP 1 (the "0" true predicted "1"), FN 2  -> F1 = 4 / 7
    #  class 2: TP 4, FP 1 (the "1" true predicted "2"), FN 0  -> F1 = 8 / 9
    #  class 3: TP 2, FP 1 (the "1" true predicted "3+"), FN 1 -> F1 = 4 / 6
    expected = (0.75 + 4 / 7 + 8 / 9 + 4 / 6) / 4
    assert stats.f1_score(truth3, pred3, T3) == pytest.approx(expected, rel=1e-12)
    assert expected == pytest.approx(kit.macro_f1(truth3, pred3, T3), rel=1e-12)


@pytest.mark.req("P-015-01")
def test_unparseable_predictions_count_as_wrong() -> None:
    truth = ["yes", "yes", "no", "no"]
    assert stats.balanced_accuracy(truth, ["yes", "unparseable", "no", "no"], BIN) == Fraction(3, 4)
    assert stats.balanced_accuracy(truth, ["unparseable"] * 4, BIN) == 0


@pytest.mark.req("P-015-01")
@pytest.mark.parametrize(("labels", "k"), [(BIN, 2), (T3, 4)])
def test_a_constant_predictor_scores_exactly_one_over_k(labels: tuple, k: int) -> None:
    truth = [labels[i % k] for i in range(60 * k)]
    for const in labels:
        assert stats.balanced_accuracy(truth, [const] * len(truth), labels) == Fraction(1, k)


_TABLE2 = st.lists(st.tuples(st.sampled_from(BIN), st.sampled_from([*BIN, "unparseable"])), min_size=2, max_size=600)
_TABLE4 = st.lists(st.tuples(st.sampled_from(T3), st.sampled_from([*T3, "unparseable"])), min_size=4, max_size=600)


@pytest.mark.req("P-015-01")
@settings(max_examples=300, deadline=None)
@given(_TABLE2)
def test_property_balanced_accuracy_equals_the_exact_oracle_and_its_three_metamorphic_relations_binary(
    table: list,
) -> None:
    truth, pred = [t for t, _ in table], [p for _, p in table]
    assume(len(set(truth)) == 2)
    ba = stats.balanced_accuracy(truth, pred, BIN)
    assert ba == kit.balanced_accuracy(truth, pred, BIN)  # exact
    assert stats.balanced_accuracy(truth * 2, pred * 2, BIN) == ba  # MR1: duplicating every query
    swap = {"yes": "no", "no": "yes", "unparseable": "unparseable"}
    assert (
        stats.balanced_accuracy([swap[t] for t in truth], [swap[p] for p in pred], BIN) == ba
    )  # MR2: swapping the labels
    idx = list(range(len(truth)))
    random.Random(1).shuffle(idx)
    assert (
        stats.balanced_accuracy([truth[i] for i in idx], [pred[i] for i in idx], BIN) == ba
    )  # MR3: permuting the queries


@pytest.mark.req("P-015-01")
@settings(max_examples=300, deadline=None)
@given(_TABLE4)
def test_property_balanced_accuracy_equals_the_exact_oracle_and_its_three_metamorphic_relations_four_classes(
    table: list,
) -> None:
    truth, pred = [t for t, _ in table], [p for _, p in table]
    assume(len(set(truth)) >= 2)
    ba = stats.balanced_accuracy(truth, pred, T3)
    assert ba == kit.balanced_accuracy(truth, pred, T3)
    assert stats.balanced_accuracy(truth * 3, pred * 3, T3) == ba
    perm = {"0": "2", "2": "0", "1": "1", "3+": "3+", "unparseable": "unparseable"}  # a relabelling of the classes
    assert stats.balanced_accuracy([perm[t] for t in truth], [perm[p] for p in pred], T3) == ba
    idx = list(range(len(truth)))
    random.Random(2).shuffle(idx)
    assert stats.balanced_accuracy([truth[i] for i in idx], [pred[i] for i in idx], T3) == ba


@pytest.mark.req("P-015-01")
def test_balanced_accuracy_on_10_000_queries_is_exact() -> None:
    rng = np.random.default_rng(15)
    truth = [BIN[i] for i in rng.integers(0, 2, 10_000)]
    pred = [t if rng.random() < 0.7 else ("no" if t == "yes" else "yes") for t in truth]
    assert stats.balanced_accuracy(truth, pred, BIN) == kit.balanced_accuracy(truth, pred, BIN)


@pytest.mark.req("FR-015-30")
@settings(max_examples=200, deadline=None)
@given(st.lists(st.tuples(st.sampled_from(BIN), st.sampled_from([*BIN, "unparseable"])), min_size=2, max_size=300))
def test_property_f1_equals_the_definition_binary(table: list) -> None:
    truth, pred = [t for t, _ in table], [p for _, p in table]
    tp = sum(1 for t, p in table if t == "yes" and p == "yes")
    fp = sum(1 for t, p in table if t != "yes" and p == "yes")
    fn = sum(1 for t, p in table if t == "yes" and p != "yes")
    expected = 0.0 if 2 * tp + fp + fn == 0 else 2 * tp / (2 * tp + fp + fn)
    assert stats.f1_score(truth, pred, BIN) == pytest.approx(expected, rel=1e-12, abs=1e-15)


# ------------------------------------------------------------------------------------------------ bootstrap interval
def _two_class_table(
    n_yes: int = 500, n_no: int = 500, r_yes: float = 0.8, r_no: float = 0.6
) -> tuple[list[str], list[str]]:
    truth = ["yes"] * n_yes + ["no"] * n_no
    pred = ["yes"] * round(n_yes * r_yes) + ["no"] * (n_yes - round(n_yes * r_yes))
    pred += ["no"] * round(n_no * r_no) + ["yes"] * (n_no - round(n_no * r_no))
    return truth, pred


@pytest.mark.req("FR-015-30")
def test_bootstrap_defaults_to_10_000_resamples_and_a_95_percent_level() -> None:
    p = inspect.signature(stats.bootstrap_ci).parameters
    assert p["n_resamples"].default == 10_000
    assert p["level"].default == 0.95


@pytest.mark.req("FR-015-30")
def test_bootstrap_interval_brackets_the_estimate_and_matches_the_delta_method_width() -> None:
    truth, pred = _two_class_table()
    ba = float(stats.balanced_accuracy(truth, pred, BIN))
    assert ba == pytest.approx(0.70, abs=1e-12)
    lo, hi = stats.bootstrap_ci(truth, pred, BIN, metric="balanced_accuracy", seed=11)
    assert lo < ba < hi
    # delta method: Var = 1/4 (0.8*0.2/500 + 0.6*0.4/500) = 0.0002 -> sd 0.014142 -> half-width 1.96 sd = 0.02772
    expected_half = 1.959964 * math.sqrt(0.25 * (0.8 * 0.2 / 500 + 0.6 * 0.4 / 500))
    assert (hi - lo) / 2 == pytest.approx(expected_half, rel=0.15)
    assert (lo + hi) / 2 == pytest.approx(ba, abs=0.005)


@pytest.mark.req("FR-015-30")
def test_bootstrap_is_stratified_within_each_true_class() -> None:
    """A constant predictor has recall 1 on one class and 0 on the other, so every stratified resample (class counts fixed)
    gives BA = 0.5 exactly and the interval is the point [0.5, 0.5]; an unstratified resample would vary."""
    truth = ["yes"] * 30 + ["no"] * 170
    lo, hi = stats.bootstrap_ci(truth, ["no"] * 200, BIN, metric="balanced_accuracy", seed=3)
    assert (lo, hi) == (0.5, 0.5)
    lo, hi = stats.bootstrap_ci(truth, truth, BIN, metric="balanced_accuracy", seed=3)
    assert (lo, hi) == (1.0, 1.0)


@pytest.mark.req("FR-015-30")
def test_bootstrap_is_deterministic_for_a_seed_and_stable_across_seeds() -> None:
    truth, pred = _two_class_table(200, 300, 0.75, 0.65)
    a = stats.bootstrap_ci(truth, pred, BIN, metric="balanced_accuracy", seed=5)
    assert a == stats.bootstrap_ci(truth, pred, BIN, metric="balanced_accuracy", seed=5)
    b = stats.bootstrap_ci(truth, pred, BIN, metric="balanced_accuracy", seed=6)
    assert a != b
    assert a[0] == pytest.approx(b[0], abs=0.012)
    assert a[1] == pytest.approx(b[1], abs=0.012)


@pytest.mark.req("FR-015-30")
def test_bootstrap_of_f1_brackets_the_point_estimate() -> None:
    truth, pred = _hand_table()
    point = stats.f1_score(truth, pred, BIN)
    lo, hi = stats.bootstrap_ci(truth, pred, BIN, metric="f1", seed=2)
    assert lo < point < hi
    truth3 = [T3[i % 4] for i in range(400)]
    pred3 = [t if i % 3 else T3[(i + 1) % 4] for i, t in enumerate(truth3)]
    lo3, hi3 = stats.bootstrap_ci(truth3, pred3, T3, metric="f1", seed=2)
    assert lo3 < stats.f1_score(truth3, pred3, T3) < hi3


# ------------------------------------------------------------------------------------------------ AUROC
@pytest.mark.req("FR-015-30")
def test_answer_score_is_the_difference_of_the_first_token_log_probabilities() -> None:
    table = {"yes": -0.1, "no": -2.3, **{f"t{i}": -3.0 - i for i in range(18)}}
    assert len(table) == 20
    assert stats.answer_score(table) == pytest.approx(-0.1 - (-2.3), abs=1e-12)  # = 2.2


@pytest.mark.req("FR-015-30")
def test_answer_score_an_absent_token_takes_the_20th_log_probability() -> None:
    lows = {f"t{i}": -1.0 - i for i in range(19)}  # 19 other tokens, the lowest is -19.0
    only_yes = {"yes": -0.5, **lows}
    assert len(only_yes) == 20
    assert stats.answer_score(only_yes) == pytest.approx(-0.5 - (-19.0), abs=1e-12)  # "no" absent: 20th = -19.0
    only_no = {"no": -0.25, **lows}
    assert stats.answer_score(only_no) == pytest.approx(-19.0 - (-0.25), abs=1e-12)  # "yes" absent


@pytest.mark.req("P-015-04")
def test_auroc_hand_calculation() -> None:
    # positives 0.9, 0.8, 0.4; negatives 0.7, 0.4, 0.2: pairs won = 3 + 2 + 1.5 (one tie 0.4 = 0.4 counts 1/2) -> (3 + 2 + 0.5 + 2... see below)
    # pos 0.9 beats 0.7, 0.4, 0.2 (3); pos 0.8 beats 0.7, 0.4, 0.2 (3); pos 0.4 beats 0.2 (1), ties 0.4 (0.5), loses to 0.7 (0): 7.5 of 9
    assert stats.auroc([0.9, 0.8, 0.4, 0.7, 0.4, 0.2], [True, True, True, False, False, False]) == pytest.approx(
        7.5 / 9, rel=1e-12
    )


_SCORES = st.lists(
    st.tuples(st.sampled_from([-3.0, -1.5, -0.5, 0.0, 0.25, 1.0, 2.5, 7.0]), st.booleans()), min_size=2, max_size=120
)


@pytest.mark.req("P-015-04")
@settings(max_examples=300, deadline=None)
@given(_SCORES)
def test_property_auroc_equals_pair_counting_and_its_metamorphic_relations(table: list) -> None:
    s, y = [a for a, _ in table], [b for _, b in table]
    assume(0 < sum(y) < len(y))
    a = stats.auroc(s, y)
    assert a == pytest.approx(kit.auroc_pairs(s, y), rel=1e-12)
    assert stats.auroc([3.0 * v + 5.0 for v in s], y) == pytest.approx(
        a, rel=1e-12
    )  # MR1: strictly increasing transform
    assert stats.auroc([math.exp(v / 4) for v in s], y) == pytest.approx(a, rel=1e-12)
    assert stats.auroc([-v for v in s], y) == pytest.approx(1 - a, rel=1e-12)  # MR2: AUROC(-s) = 1 - AUROC(s)
    idx = list(range(len(s)))
    random.Random(4).shuffle(idx)
    assert stats.auroc([s[i] for i in idx], [y[i] for i in idx]) == pytest.approx(a, rel=1e-12)  # MR3: permutation


@pytest.mark.req("P-015-04")
def test_auroc_of_a_perfect_a_reversed_and_a_constant_scorer() -> None:
    y = [True] * 5 + [False] * 5
    assert stats.auroc([2.0] * 5 + [1.0] * 5, y) == 1.0
    assert stats.auroc([1.0] * 5 + [2.0] * 5, y) == 0.0
    assert stats.auroc([0.3] * 10, y) == 0.5


# ------------------------------------------------------------------------------------------------ Wilson
@pytest.mark.req("P-015-03")
def test_wilson_published_hand_values() -> None:
    lo, hi = stats.wilson_interval(485, 500)
    assert lo == pytest.approx(0.9511, abs=5e-5)  # spec P-015-03, rounded to four decimals
    assert hi == pytest.approx(0.9817, abs=5e-5)
    lo, hi = stats.wilson_interval(540, 1080)
    assert (hi - lo) / 2 == pytest.approx(0.0298, abs=5e-5)  # spec P-015-03 and the method page: +-3.0 points at 0.5


@pytest.mark.req("P-015-03")
@settings(max_examples=300, deadline=None)
@given(st.integers(1, 100_000).flatmap(lambda n: st.tuples(st.just(n), st.integers(0, n))))
def test_property_wilson_equals_the_closed_form_and_its_relations(nk: tuple[int, int]) -> None:
    n, k = nk
    lo, hi = stats.wilson_interval(k, n)
    elo, ehi = kit.wilson(k, n)
    assert lo == pytest.approx(elo, rel=1e-9, abs=1e-12)
    assert hi == pytest.approx(ehi, rel=1e-9, abs=1e-12)
    assert 0.0 <= lo <= hi <= 1.0
    assert lo - 1e-12 <= k / n <= hi + 1e-12  # the point estimate lies inside (up to rounding at k = 0 and k = n)
    lo2, hi2 = stats.wilson_interval(n - k, n)  # MR1
    assert (lo2, hi2) == pytest.approx((1 - hi, 1 - lo), rel=1e-9, abs=1e-12)


@pytest.mark.req("P-015-03")
@settings(max_examples=200, deadline=None)
@given(st.integers(2, 5000).flatmap(lambda n: st.tuples(st.just(n), st.integers(0, n - 1))))
def test_property_wilson_bounds_do_not_decrease_with_k(nk: tuple[int, int]) -> None:
    n, k = nk
    a, b = stats.wilson_interval(k, n), stats.wilson_interval(k + 1, n)
    assert b[0] >= a[0] - 1e-15
    assert b[1] >= a[1] - 1e-15  # MR2


@pytest.mark.req("P-015-03")
@pytest.mark.parametrize("ratio", [0.1, 0.5, 0.9])
def test_wilson_interval_narrows_as_n_grows_at_a_fixed_ratio(ratio: float) -> None:
    widths = []
    for n in (20, 100, 500, 2500, 12_500):
        lo, hi = stats.wilson_interval(round(ratio * n), n)
        widths.append(hi - lo)
    assert all(a > b for a, b in pairwise(widths))  # MR3


# ------------------------------------------------------------------------------------------------ hostile inputs (FR-015-32)
@pytest.mark.req("FR-015-32")
@pytest.mark.parametrize(
    "call",
    [
        pytest.param(lambda: stats.balanced_accuracy(["yes", "no"], ["yes"], BIN), id="case-1"),  # unequal length
        pytest.param(lambda: stats.balanced_accuracy([], [], BIN), id="case-2"),  # n = 0
        pytest.param(
            lambda: stats.balanced_accuracy(["maybe", "no"], ["yes", "no"], BIN), id="case-3"
        ),  # label outside the classes
        pytest.param(lambda: stats.balanced_accuracy(["yes", "no"], ["perhaps", "no"], BIN), id="case-4"),
        pytest.param(
            lambda: stats.balanced_accuracy(["unparseable", "no"], ["yes", "no"], BIN), id="case-5"
        ),  # truth is never "unparseable"
        pytest.param(
            lambda: stats.balanced_accuracy(["yes", "no"], ["yes", "no"], T3), id="case-6"
        ),  # binary labels on a type-3 class set
        pytest.param(lambda: stats.balanced_accuracy(["4", "1"], ["1", "1"], T3), id="case-7"),
        pytest.param(lambda: stats.f1_score(["yes"], [], BIN), id="case-8"),
        pytest.param(lambda: stats.f1_score([], [], T3), id="case-9"),
        pytest.param(lambda: stats.f1_score(["x"], ["yes"], BIN), id="case-10"),
        pytest.param(lambda: stats.bootstrap_ci(["yes", "no"], ["yes"], BIN, metric="balanced_accuracy"), id="case-11"),
        pytest.param(lambda: stats.bootstrap_ci([], [], BIN, metric="f1"), id="case-12"),
        pytest.param(lambda: stats.bootstrap_ci(["yes", "z"], ["yes", "no"], BIN, metric="f1"), id="case-13"),
        pytest.param(lambda: stats.auroc([0.1, 0.2], [True]), id="case-14"),
        pytest.param(lambda: stats.auroc([], []), id="case-15"),
        pytest.param(lambda: stats.auroc([math.nan, 0.2], [True, False]), id="case-16"),
        pytest.param(lambda: stats.auroc([math.inf, 0.2], [True, False]), id="case-17"),
        pytest.param(lambda: stats.auroc([-math.inf, 0.2], [True, False]), id="case-18"),
        pytest.param(lambda: stats.answer_score({"yes": math.nan, "no": -1.0}), id="case-19"),
        pytest.param(lambda: stats.answer_score({"yes": math.inf, "no": -1.0}), id="case-20"),
        pytest.param(lambda: stats.wilson_interval(1, 0), id="case-21"),  # n = 0
        pytest.param(lambda: stats.wilson_interval(0, 0), id="case-22"),
        pytest.param(lambda: stats.wilson_interval(6, 5), id="case-23"),  # k > n
        pytest.param(lambda: stats.wilson_interval(-1, 5), id="case-24"),  # k < 0
        pytest.param(lambda: stats.wilson_interval(math.nan, 5), id="case-25"),
        pytest.param(lambda: stats.wilson_interval(1, -3), id="case-26"),
    ],
)
def test_hostile_inputs_raise_value_error(call) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        call()


@pytest.mark.req("FR-015-32")
@pytest.mark.parametrize("scores", [[0.1, 0.2, 0.3], [-1e308, 1e308, 0.0]])
def test_extreme_but_finite_scores_are_accepted(scores: list[float]) -> None:
    assert 0.0 <= stats.auroc(scores, [True, False, True]) <= 1.0


# ------------------------------------------------------------------------------------------------ the scored row
def _records() -> list[dict]:
    """1,000 queries of one binary type: per condition 50 yes (45 correct) and 200 no (day 160, night 160, dust 120, rain 120
    correct). Of the 20 wrong yes answers, 20 are unparseable. Hand calculation: BA(day) = BA(night) = (0.9 + 0.8) / 2 = 0.85,
    BA(dust) = BA(rain) = (0.9 + 0.6) / 2 = 0.75, overall (180 / 200 + 560 / 800) / 2 = 0.80, unparseable rate 20 / 1000 = 0.02."""
    recs = []
    for cond, no_ok in [("day", 160), ("night", 160), ("dust", 120), ("rain", 120)]:
        for i in range(50):
            ok = i < 45
            recs.append(
                {
                    "truth": "yes",
                    "parsed": "yes" if ok else "unparseable",
                    "condition": cond,
                    "score": 1.0 if ok else -1.0 + 0.001 * i,
                }
            )
        for i in range(200):
            ok = i < no_ok
            recs.append(
                {
                    "truth": "no",
                    "parsed": "no" if ok else "yes",
                    "condition": cond,
                    "score": -1.0 - 0.001 * i if ok else 2.0,
                }
            )
    return recs


def _row_errors(row: dict) -> list[str]:
    v = Draft202012Validator(
        {"$ref": contracts.validator("vlm-metrics.schema.json").schema["$id"] + "#/$defs/row_a"},
        registry=contracts._registry(),
    )
    return [e.message for e in v.iter_errors(row)]


@pytest.mark.req("FR-015-30")
@pytest.mark.req("SC-015-02")
def test_score_row_reports_balanced_accuracy_with_interval_unparseable_rate_and_condition_breakdown() -> None:
    row = stats.score_row(_records(), arm="cosmos-q8_0", qtype=1, seed=9)
    assert row["n"] == 1000
    assert row["balanced_accuracy"]["value"] == pytest.approx(0.80, abs=1e-12)
    lo, hi = row["balanced_accuracy"]["lo"], row["balanced_accuracy"]["hi"]
    assert lo < 0.80 < hi
    # delta method: Var = 1/4 (0.9*0.1/200 + 0.7*0.3/800) = 0.000178125, sd = 0.013346, half-width 0.02616
    assert (hi - lo) / 2 == pytest.approx(1.959964 * math.sqrt(0.000178125), rel=0.15)
    assert row["unparseable_rate"] == pytest.approx(0.02, abs=1e-12)
    assert row["error_rate"] == 0
    by = {c["condition"]: c for c in row["by_condition"]}
    assert set(by) == {"day", "night", "dust", "rain"}
    assert {c: by[c]["n"] for c in by} == dict.fromkeys(by, 250)
    assert by["day"]["balanced_accuracy"] == pytest.approx(0.85, abs=1e-12)
    assert by["night"]["balanced_accuracy"] == pytest.approx(0.85, abs=1e-12)
    assert by["dust"]["balanced_accuracy"] == pytest.approx(0.75, abs=1e-12)
    assert by["rain"]["balanced_accuracy"] == pytest.approx(0.75, abs=1e-12)
    assert row["f1"]["lo"] < row["f1"]["value"] < row["f1"]["hi"]
    assert row["f1"]["value"] == pytest.approx(360 / 620, rel=1e-12)


@pytest.mark.req("FR-015-30")
def test_score_row_follows_the_metrics_contract_and_computes_auroc_only_where_the_spec_says() -> None:
    row = stats.score_row(_records(), arm="cosmos-q8_0", qtype=1, seed=9)
    assert _row_errors(row) == []
    recs = _records()
    pos = [r["score"] for r in recs if r["truth"] == "yes"]
    neg = [r["score"] for r in recs if r["truth"] == "no"]
    assert row["auroc"] == pytest.approx(kit.auroc_pairs(pos + neg, [True] * len(pos) + [False] * len(neg)), rel=1e-12)
    for arm in ("cosmos-bf16", "detector-rule", "constant"):
        assert stats.score_row(recs, arm=arm, qtype=1, seed=9)["auroc"] is None
    assert stats.score_row(recs, arm="qwen-base", qtype=1, seed=9)["auroc"] is not None
    no_scores = [{k: v for k, v in r.items() if k != "score"} for r in recs]
    assert stats.score_row(no_scores, arm="cosmos-q8_0", qtype=1, seed=9)["auroc"] is None


@pytest.mark.req("FR-015-30")
def test_score_row_for_type_3_uses_macro_f1_and_never_reports_an_auroc() -> None:
    recs = [{"truth": t, "parsed": t if i % 4 else "unparseable", "condition": "day"} for i, t in enumerate(T3 * 50)]
    row = stats.score_row(recs, arm="cosmos-q8_0", qtype=3, seed=1)
    assert row["auroc"] is None
    truth = [r["truth"] for r in recs]
    pred = [r["parsed"] for r in recs]
    assert row["f1"]["value"] == pytest.approx(kit.macro_f1(truth, pred, T3), rel=1e-12)
    assert row["balanced_accuracy"]["value"] == pytest.approx(float(kit.balanced_accuracy(truth, pred, T3)), abs=1e-12)
    assert _row_errors(row) == []


@pytest.mark.req("FR-015-30")
def test_score_row_excludes_errored_queries_from_the_scores_and_reports_the_error_rate() -> None:
    recs = _records()
    base = stats.score_row(recs, arm="cosmos-q8_0", qtype=1, seed=9)
    errored = [
        *recs,
        *({"truth": "yes", "parsed": "unparseable", "condition": "day", "status": "error"} for _ in range(10)),
    ]
    row = stats.score_row(errored, arm="cosmos-q8_0", qtype=1, seed=9)
    assert row["n"] == 1000
    assert row["error_rate"] == pytest.approx(10 / 1010, abs=1e-12)
    assert row["balanced_accuracy"] == base["balanced_accuracy"]
    assert row["unparseable_rate"] == base["unparseable_rate"]


@pytest.mark.req("FR-015-32")
@pytest.mark.parametrize(
    "records",
    [
        [],
        [{"truth": "yes", "parsed": "maybe", "condition": "day"}],
        [{"truth": "3+", "parsed": "yes", "condition": "day"}],
        [{"truth": "yes", "parsed": "yes", "condition": "day", "score": math.nan}],
    ],
)
def test_score_row_hostile_records_raise_value_error(records: list[dict]) -> None:
    with pytest.raises(ValueError):  # noqa: PT011
        stats.score_row(records, arm="cosmos-q8_0", qtype=1, seed=0)
