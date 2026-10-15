"""Hard-domain and outline checks of the pit design (FR-004-22, FR-004-23): errors, never clipping."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

from pitstudio_studio.scene.common import SceneStageError

# parameter key -> (lowest, highest, lower bound exclusive); lengths m, angles degrees, grades percent (FR-004-22)
HARD_DOMAIN: dict[str, tuple[float, float, bool]] = {
    "bench_height_m": (5.0, 30.0, False),
    "face_angle_deg": (40.0, 85.0, False),
    "berm_width_m": (3.0, 60.0, False),
    "ramp_grade_pct": (0.0, 15.0, False),
    "ramp_width_m": (8.0, 60.0, False),
    "windrow_height_m": (0.0, 5.0, True),
}


def check_value(key: str, value: Any) -> float:
    """The value of design parameter `key` when it is finite and inside its hard domain, else `design-infeasible`."""
    lo, hi, exclusive = HARD_DOMAIN[key]
    try:
        number = float(value)
    except (TypeError, ValueError) as error:
        raise SceneStageError("design-infeasible", f"{key} is not a number") from error
    if not math.isfinite(number):
        raise SceneStageError("design-infeasible", f"{key} is not finite")
    if number < lo or number > hi or (exclusive and number <= lo):
        bound = f"({lo}, {hi}]" if exclusive else f"[{lo}, {hi}]"
        raise SceneStageError("design-infeasible", f"{key}={number} is outside its hard domain {bound}")
    return number


def check_parameters(design_block: Mapping[str, Any]) -> dict[str, float]:
    """Check the declared parameters of a SceneSpec `design` block; returns their values (never clipped).

    A value that is not finite, outside the hard domain, or outside the `[code_min, code_max]` design-code range the
    recipe declares for it raises `design-infeasible` naming the parameter.
    """
    values: dict[str, float] = {}
    for key in HARD_DOMAIN:
        param = design_block[key]
        number = check_value(key, param["value"])
        lo, hi = param.get("code_min"), param.get("code_max")
        if lo is not None and hi is not None:
            if not (math.isfinite(lo) and math.isfinite(hi)):
                raise SceneStageError("design-infeasible", f"{key} has a non-finite design-code range")
            if number < lo or number > hi:
                raise SceneStageError(
                    "design-infeasible", f"{key}={number} is outside the declared design-code range [{lo}, {hi}]"
                )
        values[key] = number
    return values


def outline_polygon(outline_xy: Sequence[Sequence[float]]) -> Any:
    """The outline as a valid, counter-clockwise shapely polygon, or `outline-invalid` (FR-004-23)."""
    from shapely.geometry import Polygon
    from shapely.geometry.polygon import orient

    try:
        points = [(float(x), float(y)) for x, y in outline_xy]
    except (TypeError, ValueError) as error:
        raise SceneStageError("outline-invalid", "the outline is not a list of [x, y] vertices") from error
    if len(points) < 3:
        raise SceneStageError("outline-invalid", f"the outline has {len(points)} vertices, at least 3 are required")
    if not all(math.isfinite(c) for p in points for c in p):
        raise SceneStageError("outline-invalid", "the outline has a non-finite coordinate")
    poly = Polygon(points)
    if not poly.is_valid:
        raise SceneStageError("outline-invalid", "the outline is not a closed simple polygon (self-intersection)")
    if poly.area <= 0.0:
        raise SceneStageError("outline-invalid", "the outline has zero area")
    return orient(poly, 1.0)


def check_outline(outline_xy: Sequence[Sequence[float]], *, ramp_width_m: float, grid: Any) -> Any:
    """Raise `outline-invalid` unless the outline is a closed simple polygon of area at least (2 W)^2 inside the
    grid."""
    poly = outline_polygon(outline_xy)
    limit = (2.0 * ramp_width_m) ** 2
    if poly.area < limit:
        raise SceneStageError(
            "outline-invalid", f"the outline area {poly.area:.1f} m2 is below (2 x ramp width)^2 = {limit:.1f} m2"
        )
    rows, cols = grid.elevation.shape
    x0, x1 = grid.x_min_m, grid.x_min_m + cols * grid.cell_size_m
    y0, y1 = grid.y_max_m - rows * grid.cell_size_m, grid.y_max_m
    bx0, by0, bx1, by1 = poly.bounds
    eps = 1e-9
    if bx0 < x0 - eps or bx1 > x1 + eps or by0 < y0 - eps or by1 > y1 + eps:
        raise SceneStageError("outline-invalid", "the outline lies partly outside the terrain grid")
    return poly
