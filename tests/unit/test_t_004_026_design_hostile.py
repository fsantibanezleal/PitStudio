# ruff: noqa: PT018
"""T-004-026: hostile design parameters and outlines.

Requirements: FR-004-22, FR-004-23.

Oracle: the spec's hard domain written out (H in [5, 30] m, alpha in [40, 85] deg, b in [3, 60] m, g in [0, 15] %,
W in [8, 60] m, windrow in (0, 5] m) with boundary values on both sides, NaN and infinities; a collapsing outline whose
inward offsets are hand calculated (R = 100 m, step H / tan(alpha) + b = 15.46 m per bench: the pit closes after
bench 6); invalid polygons (bow-tie, 2 vertices, tiny, off-grid). plan.md "FR-004-22", "FR-004-23".

Expected API (package `pitstudio_studio.scene.design`, studio environment):
- `design.check_parameters(design_block)`: `design_block` is the SceneSpec `design` block. Raises
  `common.SceneStageError("design-infeasible")`, message `"design-infeasible: ..."` naming the parameter key (for
  example `bench_height_m`), when a value is non-finite or outside its hard domain, or outside the design-code range
  `[code_min, code_max]` the recipe declares for it. Never clips a value.
- `design.check_outline(outline_xy, *, ramp_width_m, grid)`: raises `outline-invalid` for a polygon that is not closed
  and simple (self-intersecting, repeated-vertex zero area), has fewer than 3 vertices, non-finite coordinates, an area
  below (2 W)^2, or lies partly outside the grid (extent `x_min_m .. x_min_m + cols * cell`, `y_max_m - rows * cell ..
  y_max_m`).
- `design.benches.generate_benches` and `design.build_design` call both checks first; a bench polygon that collapses
  before the floor is reached raises `design-infeasible` naming the bench index.
"""

from __future__ import annotations

import math
import re
import sys
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, design  # noqa: E402

DOMAIN = {  # key: (lowest accepted, highest accepted, just below, just above)
    "bench_height_m": (5.0, 30.0, 4.999, 30.001),
    "face_angle_deg": (40.0, 85.0, 39.999, 85.001),
    "berm_width_m": (3.0, 60.0, 2.999, 60.001),
    "ramp_grade_pct": (0.0, 15.0, -0.001, 15.001),
    "ramp_width_m": (8.0, 60.0, 7.999, 60.001),
}
BASE = {
    "bench_height_m": 15.0,
    "face_angle_deg": 70.0,
    "berm_width_m": 10.0,
    "ramp_grade_pct": 8.0,
    "ramp_width_m": 30.0,
    "windrow_height_m": 2.5,
}


def _block(**values: float) -> dict:
    """A `design` block with wide declared design-code ranges; `values` override single parameter values."""
    block = kit.design_block()
    for key, value in values.items():
        block[key]["value"] = value
    return block


def _reject(block: dict, key: str) -> None:
    with pytest.raises(common.SceneStageError) as exc:
        design.check_parameters(block)
    assert exc.value.error_class == "design-infeasible"
    assert str(exc.value).startswith("design-infeasible: ") and key in str(exc.value), str(exc.value)


@pytest.mark.req("FR-004-22")
def test_the_example_design_block_is_accepted() -> None:
    design.check_parameters(kit.design_block())


@pytest.mark.req("FR-004-22")
@pytest.mark.parametrize("key", list(DOMAIN))
def test_hard_domain_boundaries_are_accepted_and_just_outside_is_rejected(key: str) -> None:
    lo, hi, below, above = DOMAIN[key]
    design.check_parameters(_block(**{key: lo}))
    design.check_parameters(_block(**{key: hi}))
    _reject(_block(**{key: below}), key)
    _reject(_block(**{key: above}), key)


@pytest.mark.req("FR-004-22")
def test_windrow_height_domain_is_open_at_zero_and_closed_at_five() -> None:
    design.check_parameters(_block(windrow_height_m=5.0))
    design.check_parameters(_block(windrow_height_m=0.002))  # just above the 0.001 m declared minimum
    for bad in (0.0, -0.5, 5.001):
        _reject(_block(windrow_height_m=bad), "windrow_height_m")


@pytest.mark.req("FR-004-22")
@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
@pytest.mark.parametrize("key", list(BASE))
def test_non_finite_parameters_are_rejected(key: str, bad: float) -> None:
    _reject(_block(**{key: bad}), key)


@pytest.mark.req("FR-004-22")
def test_value_outside_the_declared_design_code_range_is_rejected_even_inside_the_hard_domain() -> None:
    block = kit.design_block()
    block["bench_height_m"] = kit.param(20.0, 12.0, 15.0)  # H = 20 m is in [5, 30] but outside the recipe's 12-15 m
    _reject(block, "bench_height_m")
    block = kit.design_block()
    block["ramp_grade_pct"] = kit.param(7.9, 8.0, 10.0)
    _reject(block, "ramp_grade_pct")
    block = kit.design_block()
    block["face_angle_deg"] = kit.param(60.0, 60.0, 75.0)  # exactly on the declared minimum: accepted
    design.check_parameters(block)


@pytest.mark.req("FR-004-22")
@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    key=st.sampled_from(sorted(BASE)),
    inside=st.floats(0.0, 1.0),
    outside=st.one_of(st.floats(-1e6, -1e-3), st.floats(1e3, 1e6)),
)
def test_values_inside_the_domain_pass_and_values_far_outside_never_do(key: str, inside: float, outside: float) -> None:
    lo, hi = {**{k: v[:2] for k, v in DOMAIN.items()}, "windrow_height_m": (0.001, 5.0)}[key]
    design.check_parameters(_block(**{key: lo + inside * (hi - lo)}))
    _reject(_block(**{key: outside}), key)


@pytest.mark.req("FR-004-22")
def test_a_collapsing_pit_is_design_infeasible_and_names_the_bench() -> None:
    """R = 100 m, step 15.46 m per bench (H = 15, alpha = 70, b = 10): the offsets close the pit at bench 6 or 7."""
    with pytest.raises(common.SceneStageError) as exc:
        design.benches.generate_benches(
            kit.regular_polygon(360, 100.0),
            bench_height_m=15.0,
            face_angle_deg=70.0,
            berm_width_m=10.0,
            rim_z_m=0.0,
            floor_z_m=-150.0,
        )
    assert exc.value.error_class == "design-infeasible"
    assert "bench" in str(exc.value).lower() and re.search(r"\b[67]\b", str(exc.value)), str(exc.value)


@pytest.mark.req("FR-004-22")
def test_build_design_rejects_bad_parameters_and_collapse_without_clipping() -> None:
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    spec = kit.design_spec(h=15.0, floor_z=-150.0)
    with pytest.raises(common.SceneStageError) as exc:
        design.build_design(grid, spec, outline_xy=kit.regular_polygon(360, 100.0))  # collapses
    assert exc.value.error_class == "design-infeasible"
    bad = kit.design_spec()
    bad["design"]["bench_height_m"]["value"] = math.nan
    with pytest.raises(common.SceneStageError) as exc2:
        design.build_design(grid, bad, outline_xy=kit.regular_polygon(360, 100.0))
    assert exc2.value.error_class == "design-infeasible" and "bench_height_m" in str(exc2.value)


# ------------------------------------------------------------------------------------------------------- FR-004-23
def _square(side: float, x0: float = -20.0) -> list[list[float]]:
    return [[x0, x0], [x0 + side, x0], [x0 + side, x0 + side], [x0, x0 + side]]


@pytest.mark.req("FR-004-23")
@pytest.mark.parametrize(
    "outline",
    [
        [],
        [[0.0, 0.0], [10.0, 10.0]],
        [[-30.0, -30.0], [30.0, 30.0], [30.0, -30.0], [-30.0, 30.0]],  # bow-tie
        [[-30.0, 0.0], [0.0, 0.0], [30.0, 0.0]],  # zero area
        [[-30.0, -30.0], [30.0, -30.0], [30.0, float("nan")], [-30.0, 30.0]],
        [[-30.0, -30.0], [30.0, -30.0], [float("inf"), 30.0], [-30.0, 30.0]],
        _square(59.0, -29.5),  # area 3,481 m2 < (2 x 30)^2 = 3,600 m2
        [[100.0, 100.0], [160.0, 100.0], [160.0, 160.0], [100.0, 160.0]],  # partly outside the 100 m half-extent grid
    ],
    ids=["empty", "two-vertices", "bow-tie", "zero-area", "nan", "inf", "tiny", "off-grid"],
)
def test_invalid_outline_is_rejected(outline: list[list[float]]) -> None:
    grid = kit.flat_grid(100.0, 1.0, 0.0)
    with pytest.raises(common.SceneStageError) as exc:
        design.check_outline(outline, ramp_width_m=30.0, grid=grid)
    assert exc.value.error_class == "outline-invalid" and str(exc.value).startswith("outline-invalid: ")


@pytest.mark.req("FR-004-23")
def test_valid_outlines_are_accepted_at_the_area_limit_and_inside_the_grid() -> None:
    grid = kit.flat_grid(100.0, 1.0, 0.0)
    design.check_outline(_square(61.0, -30.5), ramp_width_m=30.0, grid=grid)  # 3,721 m2 >= 3,600 m2
    design.check_outline(_square(60.0, -30.0), ramp_width_m=30.0, grid=grid)  # exactly (2 W)^2 is not below the limit
    design.check_outline(_square(200.0, -100.0), ramp_width_m=30.0, grid=grid)  # touching the grid edge is inside it


@pytest.mark.req("FR-004-23")
def test_build_design_rejects_a_bow_tie_outline_before_doing_any_work() -> None:
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    with pytest.raises(common.SceneStageError) as exc:
        design.build_design(
            grid, kit.design_spec(), outline_xy=[[-90.0, -90.0], [90.0, 90.0], [90.0, -90.0], [-90.0, 90.0]]
        )
    assert exc.value.error_class == "outline-invalid"
