# ruff: noqa: E501
"""T-015-041 (reference-library half): the task-B accuracy interval equals SciPy's one-sample t interval over pairs.

Requirements: FR-015-37, SC-015-05.

Spec: specs/015-vlm/plan.md test strategy row FR-015-37 ("hand calculation on fixture tables; `scipy.stats.ttest_1samp`") and
spec FR-015-37 (interval s_bar +- t(0.975, 99) sd(s) / sqrt(100) over the 100 pairs).

Oracle: `scipy.stats.t.ppf(0.975, 99)` and `scipy.stats.ttest_1samp(s, 0.5).confidence_interval(0.95)` on the per-pair scores
s_i of the same fixture tables (the interval of a one-sample t test is s_bar -+ t(0.975, n - 1) sd / sqrt(n)). Runs in the
`pipeline/` environment (SciPy lives there).

Expected API of the implementation: `pitstudio.reason.taskb.score_task_b` as in tests/metamorphic/test_t_015_041_task_b_scoring.py.
"""

from __future__ import annotations

import pitstudio.reason.taskb as taskb
import pytest
from scipy.stats import t, ttest_1samp

CORR = ("gravity-x0.3", "zero-friction", "mass-injection", "time-reversal", "interpenetration", "frozen-particles")


def _records(n_full: int, n_half: int, n_zero: int) -> tuple[list[dict], list[float]]:
    recs, s = [], []
    for kind, n in (("full", n_full), ("half", n_half), ("zero", n_zero)):
        for _ in range(n):
            a = {"full": ("first", "second"), "half": ("first", "first"), "zero": ("second", "first")}[kind]
            recs.append(
                {
                    "pair_id": f"pair-{len(recs) + 1:03d}",
                    "corruption": CORR[len(recs) % 6],
                    "answers": {"pair-calibrated-first": a[0], "pair-corrupted-first": a[1]},
                }
            )
            s.append({"full": 1.0, "half": 0.5, "zero": 0.0}[kind])
    return recs, s


@pytest.mark.req("FR-015-37")
def test_the_t_quantile_for_99_degrees_of_freedom() -> None:
    assert t.ppf(0.975, 99) == pytest.approx(1.984216951586417, rel=1e-12)


@pytest.mark.req("FR-015-37")
@pytest.mark.parametrize("counts", [(60, 20, 20), (30, 50, 20), (10, 10, 80), (85, 10, 5)])
def test_the_accuracy_interval_equals_the_scipy_one_sample_t_interval(counts: tuple[int, int, int]) -> None:
    recs, s = _records(*counts)
    row = taskb.score_task_b(recs, arm="cosmos-bf16", input_mode="native-video")
    ci = ttest_1samp(s, 0.5).confidence_interval(confidence_level=0.95)
    assert row["accuracy"]["lo"] == pytest.approx(ci.low, rel=1e-9, abs=1e-12)
    assert row["accuracy"]["hi"] == pytest.approx(ci.high, rel=1e-9, abs=1e-12)
    assert row["verdict"] == ("above chance" if ci.low > 0.5 else "not above chance")
