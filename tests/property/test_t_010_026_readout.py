"""T-010-026: the TTF read-out shared by every learned forecaster.

Requirements: FR-010-22, P-010-13.
Spec: specs/010-slope/spec.md section 3.3 (FR-010-22), section 4 (P-010-13); plan.md row FR-010-22 (linear median paths,
hand-built paths with a crossing, an extrapolation and no failure).

Expected API (module `pitstudio.slope.readout`, numpy only; mirrored by the `forecasters` web worker):
- `ReadOut(outcome, t_hat_f, scored_at_cap)`: outcome "predicted" or "no failure predicted"; for "no failure predicted"
  `t_hat_f` is `cap_time` and `scored_at_cap` is True.
- `read_out(path, times, cap_time) -> ReadOut`: `path` the median path y at the strictly increasing `times`. t_hat_f
  is the
  first time the path reaches y <= 0, linearly interpolated between the last positive and the first non-positive step (a
  path whose first step is already <= 0 reads the first step time: the spec names no "last positive step" for that
  case);
  if no step reaches 0, the least-squares line through the last 16 steps is extrapolated when its slope is negative
  and its
  root lies within `cap_time`; otherwise no failure predicted, scored at the cap. ValueError for fewer than 2 steps, a
  length mismatch, a non-finite value, non-increasing times, a non-finite or non-positive cap, or (when no step
  reaches 0)
  fewer than 16 steps.
- `read_out_interval(quantile_paths, times, cap_time, quantiles=(0.1, ..., 0.9)) -> (lower, upper)`: the 80 % interval,
  `read_out` of the 0.1 path and of the 0.9 path (rows of the (9, steps) array selected by quantile value).

Oracles: hand-built paths (a crossing between steps 3 and 4 at the midpoint, an exact zero at a step, a line whose root
is 100 h beyond the path but inside the cap, a rising line); the exact root a / b of a linear path y = a - b s
(P-010-13,
rtol 1e-12) with a, b log-uniform in [1e-3, 1e3] and the root placed 1.5 to 256 steps after the first step; raising a
path by
c > 0 never lowers t_hat (an order relation, exact).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tests"))

import _slope_ttf_ref as k
from pitstudio.slope import readout

PROP = settings(max_examples=200, deadline=None, derandomize=True, suppress_health_check=list(HealthCheck))
TIMES = 10.0 * np.arange(1, 9, dtype=float)  # 10, 20, ..., 80
QS = (0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9)


@pytest.mark.req("FR-010-22")
def test_crossing_is_interpolated_between_the_last_positive_and_first_non_positive_step() -> None:
    path = [3.0, 2.0, 1.0, -1.0, -2.0, -3.0, -4.0, -5.0]  # +1 at 30 h, -1 at 40 h: zero at the midpoint
    r = readout.read_out(path, TIMES, 1000.0)
    assert (r.outcome, r.scored_at_cap) == ("predicted", False)
    assert r.t_hat_f == pytest.approx(35.0, rel=1e-12)
    # unequal values: +3 at 20 h, -1 at 30 h: zero at 20 + 10 x 3 / 4 = 27.5 h
    assert readout.read_out([5.0, 3.0, -1.0, -2.0, -3.0, -4.0, -5.0, -6.0], TIMES, 1000.0).t_hat_f == pytest.approx(
        27.5
    )


@pytest.mark.req("FR-010-22")
def test_an_exact_zero_is_the_first_non_positive_step() -> None:
    path = [4.0, 3.0, 2.0, 0.0, -1.0, -2.0, -3.0, -4.0]
    assert readout.read_out(path, TIMES, 1000.0).t_hat_f == pytest.approx(40.0, rel=1e-12)


@pytest.mark.req("FR-010-22")
def test_only_the_first_crossing_counts() -> None:
    path = [2.0, 1.0, -1.0, 5.0, 4.0, -2.0, 3.0, 2.0]
    assert readout.read_out(path, TIMES, 1000.0).t_hat_f == pytest.approx(25.0, rel=1e-12)


@pytest.mark.req("FR-010-22")
def test_a_path_that_starts_at_or_below_zero_reads_the_first_step() -> None:
    assert readout.read_out([-1.0, -2.0, -3.0, -4.0, -5.0, -6.0, -7.0, -8.0], TIMES, 1000.0).t_hat_f == 10.0
    assert readout.read_out([0.0, 1.0, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0], TIMES, 1000.0).t_hat_f == 10.0


@pytest.mark.req("FR-010-22")
def test_without_a_crossing_the_last_16_steps_are_extrapolated_when_the_root_is_within_the_cap() -> None:
    times = 10.0 * np.arange(1, 65, dtype=float)  # 64 steps, 10 h apart, up to 640 h
    path = 100.0 - 0.1 * times + 5.0  # y = 105 - 0.1 s: root 1,050 h, beyond the path
    junk = path.copy()
    junk[:48] += 1000.0 * (1.5 + np.sin(np.arange(48)))  # positive junk: the first 48 steps must not influence the fit
    r = readout.read_out(junk, times, 1100.0)
    assert (r.outcome, r.scored_at_cap) == ("predicted", False)
    assert r.t_hat_f == pytest.approx(1050.0, rel=1e-12)
    far = readout.read_out(path, times, 1000.0)  # the same root, cap 1,000 h: beyond the cap
    assert (far.outcome, far.scored_at_cap, far.t_hat_f) == ("no failure predicted", True, 1000.0)


@pytest.mark.req("FR-010-22")
@pytest.mark.parametrize("slope", [0.0, 0.1, 5.0])
def test_a_non_negative_slope_is_no_failure_predicted_scored_at_the_cap(slope) -> None:
    times = 10.0 * np.arange(1, 65, dtype=float)
    r = readout.read_out(10.0 + slope * times, times, 2000.0)
    assert (r.outcome, r.scored_at_cap, r.t_hat_f) == ("no failure predicted", True, 2000.0)


@pytest.mark.req("FR-010-22")
def test_the_interval_reads_the_01_and_09_quantile_paths_by_the_same_rule() -> None:
    # nine linear paths y_j = c_j - 0.5 s with intercepts rising with the quantile: roots c_j / 0.5
    times = 10.0 * np.arange(1, 9, dtype=float)
    intercepts = np.array([20.0, 22.0, 24.0, 26.0, 28.0, 30.0, 32.0, 34.0, 36.0])
    paths = intercepts[:, None] - 0.5 * times[None, :]
    lo, hi = readout.read_out_interval(paths, times, 1000.0, QS)
    assert lo.t_hat_f == pytest.approx(40.0, rel=1e-12)  # 20 / 0.5, interpolated exactly (the path is linear)
    assert hi.t_hat_f == pytest.approx(72.0, rel=1e-12)  # 36 / 0.5
    assert lo.t_hat_f < readout.read_out(paths[4], times, 1000.0).t_hat_f < hi.t_hat_f
    shuffled = paths[::-1]
    lo2, hi2 = readout.read_out_interval(shuffled, times, 1000.0, QS[::-1])  # rows selected by quantile value
    assert (lo2.t_hat_f, hi2.t_hat_f) == (lo.t_hat_f, hi.t_hat_f)


@pytest.mark.req("FR-010-22")
@pytest.mark.parametrize(
    ("path", "times", "cap"),
    [
        ([1.0], [1.0], 10.0),
        ([1.0, 2.0, 3.0], [1.0, 2.0], 10.0),
        ([1.0, float("nan"), 3.0], [1.0, 2.0, 3.0], 10.0),
        ([1.0, 2.0, 3.0], [1.0, float("inf"), 3.0], 10.0),
        ([1.0, 2.0, 3.0], [1.0, 1.0, 3.0], 10.0),
        ([1.0, 2.0, 3.0], [3.0, 2.0, 1.0], 10.0),
        ([1.0, -2.0, 3.0], [1.0, 2.0, 3.0], 0.0),
        ([1.0, -2.0, 3.0], [1.0, 2.0, 3.0], float("nan")),
        ([5.0, 4.0, 3.0], [1.0, 2.0, 3.0], 10.0),  # no crossing and fewer than 16 steps to extrapolate
    ],
)
def test_hostile_paths_raise_value_error(path, times, cap) -> None:
    with pytest.raises(ValueError, match=r"."):
        readout.read_out(path, times, cap)


@st.composite
def _linear_path(draw):
    a = 10.0 ** draw(st.floats(-3.0, 3.0))
    b = 10.0 ** draw(st.floats(-3.0, 3.0))
    m = draw(st.floats(1.5, 256.0))  # the root a / b lies m steps after the start
    h = (a / b) / m
    return a, b, h, 64


@pytest.mark.req("P-010-13")
@PROP
@given(_linear_path())
def test_a_linear_median_path_reads_its_root_inside_the_forecast_or_extrapolated(case) -> None:
    a, b, h, n = case
    times = h * np.arange(1, n + 1, dtype=float)
    path = a - b * times
    cap = 256 * h  # 4 blocks of 64 steps
    r = readout.read_out(path, times, cap * (1 + 1e-9))
    assert r.outcome == "predicted"
    assert r.t_hat_f == pytest.approx(a / b, rel=1e-9)


@st.composite
def _random_path(draw):
    values = draw(st.lists(st.floats(-5.0, 5.0), min_size=24, max_size=64))
    return np.array(values), draw(st.floats(1e-3, 10.0))


def _t_hat(path, times, cap) -> float:
    return readout.read_out(path, times, cap).t_hat_f  # "no failure predicted" is scored at the cap


@pytest.mark.req("P-010-13")
@PROP
@given(_random_path())
def test_raising_the_whole_path_never_lowers_the_read_out_time(case) -> None:
    path, c = case
    times = 4.0 * np.arange(1, len(path) + 1, dtype=float)
    cap = 4.0 * 256
    assert _t_hat(path + c, times, cap) >= _t_hat(path, times, cap) - 1e-9


@pytest.mark.req("FR-010-22")
@PROP
@given(_random_path())
def test_the_read_out_matches_the_independent_textbook_rule(case) -> None:
    path, _ = case
    times = 4.0 * np.arange(1, len(path) + 1, dtype=float)
    cap = 4.0 * 256
    got = readout.read_out(path, times, cap)
    outcome, t = k.read_out(path, times, cap)
    assert got.outcome == outcome
    assert got.t_hat_f == pytest.approx(t, rel=1e-9, abs=1e-9)
    assert math.isfinite(got.t_hat_f)
