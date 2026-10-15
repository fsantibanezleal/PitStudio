"""Benches from a pit outline: crest and toe polygons by mitre offsets (FR-004-16, P-004-08, P-004-09)."""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

from pitstudio_studio.scene.common import SceneStageError
from pitstudio_studio.scene.design.checks import check_value, outline_polygon

MITRE_LIMIT = 10.0


@dataclass
class Bench:
    """One bench: `crest` and `toe` shapely polygons and their elevations (m); index 0 is at the rim."""

    index: int
    crest: Any
    toe: Any
    crest_z: float
    toe_z: float

    @property
    def height_m(self) -> float:
        return self.crest_z - self.toe_z


def _inset(poly: Any, distance: float, what: str, index: int) -> Any:
    """`poly` offset inward by `distance` with mitre joins; a collapse is `design-infeasible` naming the bench."""
    out = poly.buffer(-distance, join_style="mitre", mitre_limit=MITRE_LIMIT)
    if out.is_empty or out.geom_type != "Polygon" or out.area <= 1e-9:
        reason = "collapses" if out.is_empty or out.area <= 1e-9 else "splits into several parts"
        raise SceneStageError(
            "design-infeasible",
            f"the {what} of bench {index} {reason} before the floor is reached (offset {distance:.2f} m)",
        )
    return out


def generate_benches(
    outline_xy: Sequence[Sequence[float]],
    *,
    bench_height_m: float,
    face_angle_deg: float,
    berm_width_m: float,
    rim_z_m: float,
    floor_z_m: float,
) -> list[Bench]:
    """Per-bench crest and toe polygons down to the floor (FR-004-16).

    Each toe is its crest offset inward by `H / tan(alpha)`; each next crest is the toe offset inward by the berm
    width (mitre joins). The last bench is shortened when the depth is not a multiple of `H`.
    """
    height = check_value("bench_height_m", bench_height_m)
    angle = check_value("face_angle_deg", face_angle_deg)
    berm = check_value("berm_width_m", berm_width_m)
    if not (math.isfinite(rim_z_m) and math.isfinite(floor_z_m)) or floor_z_m >= rim_z_m:
        raise SceneStageError("design-infeasible", "the floor elevation must be finite and below the rim elevation")
    crest = outline_polygon(outline_xy)
    depth = rim_z_m - floor_z_m
    count = max(1, math.ceil(depth / height - 1e-9))
    benches: list[Bench] = []
    tan_alpha = math.tan(math.radians(angle))
    for k in range(count):
        crest_z = rim_z_m - k * height
        toe_z = max(crest_z - height, floor_z_m)
        run = (crest_z - toe_z) / tan_alpha
        toe = _inset(crest, run, "toe", k)
        benches.append(Bench(k, crest, toe, crest_z, toe_z))
        if k + 1 < count:
            crest = _inset(toe, berm, "crest", k + 1)
    return benches
