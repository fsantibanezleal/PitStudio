# ruff: noqa: E501, PT018
"""T-006-011: VMAF aggregation (mean and 5th percentile of per-frame scores) and the libvmaf JSON log reader.

Requirements: P-006-05 (and FR-006-02 for the log reader).

Spec: specs/006-media-telemetry/spec.md P-006-05 (the mean and the 5th percentile of per-frame scores are invariant to frame
order; adding a constant c to every score adds c to both; the mean over two equal-length halves equals the mean of their
means; 2 to 10,000 scores in [0, 100]; exact for order, atol 1e-9 otherwise) and FR-006-02 (the 5th percentile is Hyndman-Fan
type 7; per-frame scores are read from the JSON log of libvmaf).

Oracle: NumPy `percentile(..., method="linear")` (NumPy documents "linear" as Hyndman-Fan type 7), `math.fsum` for the mean,
the type-7 definition written out by hand (Hyndman and Fan 1996, Am. Statistician 50(4):361-365: Q(p) = x[j] + g (x[j+1] - x[j])
with h = (n - 1) p, j = floor(h), g = h - j, 0-based), and the JSON layout libvmaf writes (`frames[i].metrics.vmaf`).

Expected API (module `pitstudio_studio.media.search`):
    aggregate_vmaf(scores: Sequence[float]) -> tuple[float, float]       (mean, p5); float64 arithmetic; no clipping to [0, 100];
        raises ValueError for an empty sequence or any NaN or infinite score. The mean must not depend on the order of the
        scores (use math.fsum or an equivalent exact summation), the percentile sorts first.
    parse_vmaf_log(text: str, *, expected_frames: int | None = None) -> list[float]
        the per-frame scores `frames[*].metrics.vmaf` of a libvmaf JSON log, in frameNum order; raises ValueError for malformed JSON,
        a frame without a finite `metrics.vmaf`, a duplicate or missing frameNum, or (when given) a frame count other than
        `expected_frames`.
"""

from __future__ import annotations

import json
import math
import random
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p006_kit  # noqa: F401
from pitstudio_studio.media.search import aggregate_vmaf, parse_vmaf_log

SETTINGS = settings(
    max_examples=200, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large]
)
SCORES = st.lists(st.floats(0, 100, allow_nan=False, allow_infinity=False), min_size=2, max_size=2000)


def type7(sorted_x: list[float], p: float) -> float:
    n = len(sorted_x)
    h = (n - 1) * p
    j = math.floor(h)
    if j + 1 >= n:
        return sorted_x[-1]
    return sorted_x[j] + (h - j) * (sorted_x[j + 1] - sorted_x[j])


@pytest.mark.req("P-006-05")
@pytest.mark.parametrize(
    ("scores", "mean", "p5"),
    [
        (list(range(1, 12)), 6.0, 1.5),  # n = 11: h = 0.5 -> 1 + 0.5 (2 - 1) = 1.5
        (list(range(0, 21)), 10.0, 1.0),  # n = 21: h = 1.0 -> x[1] = 1
        ([0.0, 100.0], 50.0, 5.0),  # n = 2: h = 0.05 -> 0 + 0.05 * 100
        ([90.0] * 7, 90.0, 90.0),  # constant sequence
    ],
)
def test_hand_calculated_mean_and_type7_percentile(scores, mean, p5):
    m, p = aggregate_vmaf([float(s) for s in scores])
    assert m == pytest.approx(mean, abs=1e-12) and p == pytest.approx(p5, abs=1e-12)


@pytest.mark.req("P-006-05")
@SETTINGS
@given(SCORES)
def test_matches_numpy_reference_and_the_type7_definition(scores):
    m, p = aggregate_vmaf(scores)
    arr = np.asarray(scores, dtype=np.float64)
    assert m == pytest.approx(float(arr.mean()), abs=1e-9)
    assert p == pytest.approx(float(np.percentile(arr, 5, method="linear")), abs=1e-9)
    assert p == pytest.approx(type7(sorted(scores), 0.05), abs=1e-9)


@pytest.mark.req("P-006-05")
@SETTINGS
@given(SCORES, st.randoms(use_true_random=False))
def test_invariant_to_frame_order_exactly(scores, rnd):
    shuffled = list(scores)
    rnd.shuffle(shuffled)
    assert aggregate_vmaf(shuffled) == aggregate_vmaf(scores)  # exact, as P-006-05 states


@pytest.mark.req("P-006-05")
@SETTINGS
@given(SCORES, st.floats(-50, 50, allow_nan=False))
def test_adding_a_constant_adds_it_to_both_statistics(scores, c):
    m0, p0 = aggregate_vmaf(scores)
    m1, p1 = aggregate_vmaf([s + c for s in scores])  # no clipping to [0, 100]
    assert m1 == pytest.approx(m0 + c, abs=1e-9)
    assert p1 == pytest.approx(p0 + c, abs=1e-9)


@pytest.mark.req("P-006-05")
@SETTINGS
@given(st.lists(st.floats(0, 100, allow_nan=False, allow_infinity=False), min_size=1, max_size=1000), st.data())
def test_mean_over_two_equal_halves_is_the_mean_of_their_means(half_a, data):
    half_b = data.draw(
        st.lists(st.floats(0, 100, allow_nan=False, allow_infinity=False), min_size=len(half_a), max_size=len(half_a))
    )
    m_all = aggregate_vmaf(half_a + half_b)[0]
    assert m_all == pytest.approx((aggregate_vmaf(half_a)[0] + aggregate_vmaf(half_b)[0]) / 2, abs=1e-9)


@pytest.mark.req("P-006-05")
def test_ten_thousand_scores_upper_end_of_the_stated_domain():
    rng = random.Random(6)
    scores = [rng.uniform(0, 100) for _ in range(10_000)]
    m, p = aggregate_vmaf(scores)
    assert m == pytest.approx(float(np.mean(scores)), abs=1e-9)
    assert p == pytest.approx(float(np.percentile(scores, 5, method="linear")), abs=1e-9)


@pytest.mark.req("P-006-05")
@pytest.mark.parametrize("bad", [[], [float("nan"), 90.0], [90.0, float("inf")], [90.0, float("-inf")]])
def test_empty_and_non_finite_scores_are_rejected(bad):
    with pytest.raises(ValueError):  # noqa: PT011
        aggregate_vmaf(bad)


# ---------------------------------------------------------------------------------------------------------------------
# libvmaf JSON log (FR-006-02: per-frame scores read from the JSON log)
# ---------------------------------------------------------------------------------------------------------------------
def log_text(scores, order=None):
    frames = [{"frameNum": i, "metrics": {"vmaf": s, "integer_adm2": 0.99}} for i, s in enumerate(scores)]
    if order:
        frames = [frames[i] for i in order]
    return json.dumps(
        {"version": "3.0.0", "frames": frames, "pooled_metrics": {"vmaf": {"mean": sum(scores) / len(scores)}}}
    )


@pytest.mark.req("FR-006-02")
def test_log_reader_returns_scores_in_frame_order_even_when_the_log_is_shuffled():
    scores = [91.5, 92.5, 93.5, 94.5]
    assert parse_vmaf_log(log_text(scores, order=[2, 0, 3, 1])) == scores
    assert parse_vmaf_log(log_text(scores), expected_frames=4) == scores


@pytest.mark.req("FR-006-02")
@pytest.mark.parametrize(
    "text",
    [
        "",
        "not json",
        "{}",
        json.dumps({"frames": [{"frameNum": 0, "metrics": {}}]}),
        json.dumps({"frames": [{"frameNum": 0, "metrics": {"vmaf": None}}]}),
        json.dumps(
            {"frames": [{"frameNum": 0, "metrics": {"vmaf": 90.0}}, {"frameNum": 0, "metrics": {"vmaf": 91.0}}]}
        ),  # duplicate index
        json.dumps(
            {"frames": [{"frameNum": 0, "metrics": {"vmaf": 90.0}}, {"frameNum": 2, "metrics": {"vmaf": 91.0}}]}
        ),  # a missing frame
        '{"frames": [{"frameNum": 0, "metrics": {"vmaf": NaN}}]}',
    ],
)
def test_log_reader_rejects_malformed_logs(text):
    with pytest.raises(ValueError):  # noqa: PT011
        parse_vmaf_log(text)


@pytest.mark.req("FR-006-02")
def test_log_reader_rejects_a_frame_count_that_differs_from_the_source():
    with pytest.raises(ValueError):  # noqa: PT011
        parse_vmaf_log(log_text([90.0, 91.0, 92.0]), expected_frames=300)
