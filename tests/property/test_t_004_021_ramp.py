# ruff: noqa: E501, PT018
"""T-004-021: helical ramp: grade bound, width, connectivity, widened benches.

Requirements: FR-004-17, P-004-10.

Oracle: the grade of the sampled centreline recomputed from its vertex coordinates (rise over horizontal run between
consecutive samples, plan.md "FR-004-17"); hand calculation of the minimum ramp length implied by the grade bound
(a drop of 150 m at 8.1 % needs at least 150 / 0.081 = 1851.85 m of horizontal run); connectivity from the sample
spacing; star polygons drawn by Hypothesis (P-004-10).

Expected API (package `pitstudio_studio.scene.design`, studio environment):
- `design.ramp.generate_ramp(benches, *, ramp_grade_pct, ramp_width_m, rim_z_m, floor_z_m, sample_spacing_m=1.0)`
  -> `Ramp` with `centreline` (float64 [n, 3], site frame, from the rim at `rim_z_m` down to the floor at `floor_z_m`, one
  connected polyline whose consecutive samples are at most `sample_spacing_m` apart horizontally), `width_m` (float64 [n],
  the ramp width at every sample), `sample_spacing_m` and `widened_bench_indices` (the benches the ramp crosses; the
  berms there are widened by the ramp width). Every sample lies inside the first crest polygon. A ramp that needs more
  horizontal run than one lap of a bench provides uses switchbacks. `benches` come from
  `design.benches.generate_benches` (test_t_004_020); an infeasible pit raises `common.SceneStageError("design-infeasible")`.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, design  # noqa: E402


def _pit(outline, h=15.0, alpha=70.0, b=10.0, rim=0.0, floor=-150.0):
    return design.benches.generate_benches(
        outline, bench_height_m=h, face_angle_deg=alpha, berm_width_m=b, rim_z_m=rim, floor_z_m=floor
    )


def _ramp(benches, g=8.0, w=30.0, rim=0.0, floor=-150.0):
    return design.ramp.generate_ramp(
        benches, ramp_grade_pct=g, ramp_width_m=w, rim_z_m=rim, floor_z_m=floor, sample_spacing_m=1.0
    )


def _check_ramp(ramp, benches, g: float, w: float, rim: float, floor: float) -> None:
    from shapely.geometry import Point

    c = np.asarray(ramp.centreline, dtype=np.float64)
    assert c.ndim == 2 and c.shape[1] == 3 and len(c) >= 2 and np.isfinite(c).all()
    grades = kit.segment_grades_pct(c)
    assert grades.max() <= g + 0.1 + 1e-9, grades.max()  # centreline grade <= g + 0.1 % everywhere
    run = np.hypot(np.diff(c[:, 0]), np.diff(c[:, 1]))
    assert run.max() <= 1.0 + 1e-9  # sampled at <= 1 m: one connected polyline, no jumps
    assert ramp.sample_spacing_m <= 1.0
    assert c[0, 2] == pytest.approx(rim, abs=1e-6) and c[-1, 2] == pytest.approx(floor, abs=1e-6)
    assert np.all(np.diff(c[:, 2]) <= 1e-9)  # it only descends
    assert np.asarray(ramp.width_m).shape == (len(c),) and float(np.min(ramp.width_m)) >= w
    crest0 = benches[0].crest.buffer(1e-6)
    assert all(crest0.contains(Point(x, y)) for x, y in c[:: max(1, len(c) // 400), :2])  # inside the pit rim
    # the grade bound fixes a minimum run: drop / ((g + 0.1) / 100)
    assert run.sum() >= (rim - floor) * 100.0 / (g + 0.1) - 1e-6


@pytest.mark.req("FR-004-17")
def test_helical_ramp_of_the_circular_pit_meets_every_bound() -> None:
    benches = _pit(kit.regular_polygon(720, 500.0))
    ramp = _ramp(benches)
    _check_ramp(ramp, benches, 8.0, 30.0, 0.0, -150.0)
    run = np.hypot(*np.diff(np.asarray(ramp.centreline)[:, :2], axis=0).T).sum()
    assert 1851.0 <= run <= 1875.0 * 1.02  # a drop of 150 m at 8 %: about 1875 m of run (hand calculation)


@pytest.mark.req("FR-004-17")
def test_every_bench_crossed_by_the_ramp_is_widened() -> None:
    benches = _pit(kit.regular_polygon(720, 500.0))
    ramp = _ramp(benches)
    assert sorted(ramp.widened_bench_indices) == list(range(len(benches)))  # a rim-to-floor ramp crosses all ten


@pytest.mark.req("FR-004-17")
@pytest.mark.parametrize("g", [1.0, 5.0, 8.0, 12.0, 15.0])
def test_grade_bound_holds_across_the_hard_domain(g: float) -> None:
    benches = _pit(kit.regular_polygon(360, 450.0), h=10.0, floor=-60.0)
    _check_ramp(_ramp(benches, g=g, w=20.0, floor=-60.0), benches, g, 20.0, 0.0, -60.0)


@pytest.mark.req("FR-004-17")
def test_small_pit_uses_switchbacks_and_still_meets_the_bounds() -> None:
    """R = 80 m, four 12 m benches at 5 %: the deepest benches are shorter than the 240 m of run each needs."""
    benches = _pit(kit.regular_polygon(180, 80.0), h=12.0, alpha=75.0, b=5.0, floor=-48.0)
    assert len(benches) == 4
    ramp = _ramp(benches, g=5.0, w=8.0, floor=-48.0)
    _check_ramp(ramp, benches, 5.0, 8.0, 0.0, -48.0)


@pytest.mark.req("FR-004-17")
def test_concave_outline_ramp_meets_the_bounds() -> None:
    benches = _pit(kit.star_polygon(5, 14, 340.0, 440.0), h=12.0, alpha=70.0, b=10.0, floor=-72.0)
    _check_ramp(_ramp(benches, g=10.0, w=25.0, floor=-72.0), benches, 10.0, 25.0, 0.0, -72.0)


@pytest.mark.req("P-004-10")
@settings(max_examples=30, deadline=None, suppress_health_check=[HealthCheck.too_slow, HealthCheck.filter_too_much])
@given(
    seed=st.integers(0, 2**31 - 1),
    n=st.integers(6, 18),
    h=st.floats(5.0, 20.0),
    alpha=st.floats(55.0, 85.0),
    b=st.floats(3.0, 25.0),
    g=st.floats(1.0, 15.0),
    w=st.floats(8.0, 60.0),
    n_benches=st.integers(2, 5),
)
def test_grade_and_width_bounds_hold_for_random_star_polygons(
    seed: int, n: int, h: float, alpha: float, b: float, g: float, w: float, n_benches: int
) -> None:
    """P-004-10: for any feasible star-polygon outline and parameters, max grade <= g + 0.1 % and min width >= W."""
    outline = kit.star_polygon(seed, n, 260.0, 480.0)
    floor = -n_benches * h
    try:
        benches = _pit(outline, h=h, alpha=alpha, b=b, floor=floor)
        ramp = _ramp(benches, g=g, w=w, floor=floor)
    except common.SceneStageError as exc:
        assume(exc.error_class != "design-infeasible")  # infeasible combinations are rejected, never clipped
        raise
    _check_ramp(ramp, benches, g, w, 0.0, floor)
