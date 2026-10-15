# ruff: noqa: E501
"""T-015-060 (reference-library half): Cohen's kappa of the real-probe labellers equals scikit-learn's.

Requirements: FR-015-45.

Spec: specs/015-vlm/plan.md test strategy row FR-015-45 ("Cohen's kappa by hand calculation on a 2 x 2 table; `sklearn.metrics.cohen_kappa_score`").

Oracle: `sklearn.metrics.cohen_kappa_score` called directly on random labelings and the hand calculation (40 / 40 / 10 / 10 table: kappa 0.6). Runs in the
`pipeline/` environment, which owns scikit-learn.

Expected API of the implementation: `pitstudio.reason.records.cohen_kappa(a, b) -> float` as in tests/contract/test_t_015_060_records.py.
"""

from __future__ import annotations

import pitstudio.reason.records as rec
import pytest
from hypothesis import assume, given, settings
from hypothesis import strategies as st
from sklearn.metrics import cohen_kappa_score


@pytest.mark.req("FR-015-45")
def test_the_hand_table_has_kappa_0_6_in_scikit_learn_too() -> None:
    a = ["yes"] * 40 + ["no"] * 40 + ["yes"] * 10 + ["no"] * 10
    b = ["yes"] * 40 + ["no"] * 40 + ["no"] * 10 + ["yes"] * 10
    assert cohen_kappa_score(a, b) == pytest.approx(0.6, abs=1e-12)
    assert rec.cohen_kappa(a, b) == pytest.approx(cohen_kappa_score(a, b), abs=1e-12)


@pytest.mark.req("FR-015-45")
@settings(max_examples=200, deadline=None)
@given(
    st.lists(
        st.tuples(st.sampled_from(["yes", "no", "3+"]), st.sampled_from(["yes", "no", "3+"])), min_size=2, max_size=300
    )
)
def test_cohen_kappa_equals_scikit_learn(pairs: list) -> None:
    a, b = [x for x, _ in pairs], [y for _, y in pairs]
    assume(len(set(a) | set(b)) > 1)
    pe = sum((a.count(c) / len(a)) * (b.count(c) / len(b)) for c in set(a) | set(b))
    assume(abs(1 - pe) > 1e-9)
    assert rec.cohen_kappa(a, b) == pytest.approx(cohen_kappa_score(a, b), abs=1e-12)
