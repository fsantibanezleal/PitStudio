# ruff: noqa: E501
"""T-015-037 (reference-library half): the exact McNemar p equals SciPy's exact binomial test.

Requirements: FR-015-31, P-015-02.

Spec: specs/015-vlm/plan.md test strategy row FR-015-31 ("`scipy.stats.binomtest`, `statsmodels.stats.contingency_tables.mcnemar
(exact=True)`; worked example b = 60, c = 35"). statsmodels is not in the pipeline environment; its exact McNemar is the
two-sided binomial test on the discordant pairs with success probability 1/2, which `scipy.stats.binomtest` computes directly.

Oracle: `scipy.stats.binomtest(min(b, c), b + c, 0.5).pvalue` (two-sided, p = 1 when b + c = 0 by the spec's edge case) and
the worked example p = 0.013379 (b = 60, c = 35). This file runs in the `pipeline/` environment (scipy lives there).

Expected API of the implementation: `pitstudio.reason.stats.mcnemar_exact(b, c) -> float` as in
tests/metamorphic/test_t_015_037_mcnemar.py.
"""

from __future__ import annotations

import pitstudio.reason.stats as stats
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st
from scipy.stats import binomtest


@pytest.mark.req("P-015-02")
def test_worked_example_equals_scipy_and_the_published_value() -> None:
    ref = binomtest(35, 95, 0.5).pvalue
    assert ref == pytest.approx(0.013379, abs=5e-7)
    assert stats.mcnemar_exact(60, 35) == pytest.approx(ref, rel=1e-6)


@pytest.mark.req("P-015-02")
@settings(max_examples=300, deadline=None)
@given(st.integers(0, 5000), st.integers(0, 5000))
def test_exact_p_equals_scipy_binomtest(b: int, c: int) -> None:
    ref = 1.0 if b + c == 0 else binomtest(min(b, c), b + c, 0.5).pvalue
    assert stats.mcnemar_exact(b, c) == pytest.approx(ref, rel=1e-6, abs=1e-300)
