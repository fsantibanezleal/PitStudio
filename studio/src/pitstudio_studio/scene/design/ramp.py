"""One helical haul ramp from the rim to the floor with a grade bound (FR-004-17, P-004-10).

The centreline is a spiral that follows the inward offsets of the first crest. Between two laps the lateral distance is
at least the ramp width, so the strips never overlap. Elevation falls linearly with the *chord* length along the
sampled polyline, so the grade of every sample pair is exactly the declared grade, whatever the curvature.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio_studio.scene.common import SceneStageError
from pitstudio_studio.scene.design.benches import MITRE_LIMIT, Bench
from pitstudio_studio.scene.design.checks import check_value

RING_STEP_M = 1.0  # inward distance between two consecutive rings of the spiral


@dataclass
class Ramp:
    """The ramp centreline `[n, 3]` (site frame, rim to floor), its width at every sample and the benches it crosses."""

    centreline: np.ndarray
    width_m: np.ndarray
    sample_spacing_m: float
    widened_bench_indices: list[int]

    @property
    def length_m(self) -> float:
        return float(np.sum(np.linalg.norm(np.diff(self.centreline, axis=0), axis=1)))


def _ring_xy(poly: Any) -> np.ndarray:
    from shapely.geometry.polygon import orient

    return np.asarray(orient(poly, 1.0).exterior.coords, dtype=np.float64)


def _points_along(ring_xy: np.ndarray, start: float, length: float) -> tuple[np.ndarray, float]:
    """Points every metre along a closed ring from arc position `start` for `length` metres; returns them and the
    end."""
    import shapely
    from shapely.geometry import LinearRing

    ring = LinearRing(ring_xy)
    total = ring.length
    distances = start + np.arange(0.0, length + 1e-9, 1.0)
    if distances[-1] < start + length - 1e-9:
        distances = np.append(distances, start + length)
    pts = shapely.line_interpolate_point(ring, distances % total)
    return shapely.get_coordinates(pts), float((start + length) % total)


def _nearest_arc(ring_xy: np.ndarray, point: np.ndarray) -> float:
    from shapely.geometry import LinearRing, Point

    return float(LinearRing(ring_xy).project(Point(*point)))


def generate_ramp(
    benches: Sequence[Bench],
    *,
    ramp_grade_pct: float,
    ramp_width_m: float,
    rim_z_m: float,
    floor_z_m: float,
    sample_spacing_m: float = 1.0,
) -> Ramp:
    """The helical ramp of a bench set (FR-004-17): grade <= g, width >= W, one connected polyline, all inside the
    rim."""
    grade = check_value("ramp_grade_pct", ramp_grade_pct)
    width = check_value("ramp_width_m", ramp_width_m)
    spacing = min(float(sample_spacing_m), 1.0)
    if grade <= 0.0:
        raise SceneStageError("design-infeasible", "ramp_grade_pct=0 cannot descend from the rim to the floor")
    depth = rim_z_m - floor_z_m
    if not depth > 0:
        raise SceneStageError("design-infeasible", "the floor elevation must be below the rim elevation")
    needed = depth * 100.0 / grade  # chord length of the centreline
    crest0 = benches[0].crest
    if len(benches) > 1:
        gap = (crest0.area - benches[1].crest.area) / (0.5 * (crest0.length + benches[1].crest.length))
    else:
        gap = width
    gap = max(gap, RING_STEP_M)
    per_bench = 100.0 * (benches[0].crest_z - benches[0].toe_z) / grade  # path length per bench at the grade
    pieces: list[np.ndarray] = []
    travelled = 0.0
    arc = 0.0
    j = 0
    previous = None
    while travelled < needed * 1.05 + 10.0:
        ring_poly = crest0.buffer(-(width / 2.0 + j * RING_STEP_M), join_style="mitre", mitre_limit=MITRE_LIMIT)
        if ring_poly.is_empty or ring_poly.geom_type != "Polygon":
            raise SceneStageError(
                "design-infeasible",
                f"the pit offers {travelled:.0f} m of ramp at this width, "
                f"{needed:.0f} m are needed for grade {grade} %",
            )
        ring = _ring_xy(ring_poly)
        perimeter = float(np.sum(np.hypot(*np.diff(ring, axis=0).T)))
        if previous is not None:
            arc = _nearest_arc(ring, previous)
        run = max(1.0, min(per_bench * RING_STEP_M / gap, RING_STEP_M * perimeter / width, perimeter * 0.98))
        pts, arc = _points_along(ring, arc, run)
        pieces.append(pts)
        travelled += run + RING_STEP_M
        previous = pts[-1]
        j += 1
    path = np.vstack(pieces)
    # resample at the sample spacing by arc length, then let elevation follow the chord length
    seg = np.hypot(*np.diff(path, axis=0).T)
    keep = np.r_[True, seg > 1e-12]
    path, seg = path[keep], np.hypot(*np.diff(path[keep], axis=0).T)
    cumulative = np.r_[0.0, np.cumsum(seg)]
    stations = np.arange(0.0, cumulative[-1], spacing)
    xy = np.column_stack([np.interp(stations, cumulative, path[:, 0]), np.interp(stations, cumulative, path[:, 1])])
    chord = np.hypot(*np.diff(xy, axis=0).T)
    along = np.r_[0.0, np.cumsum(chord)]
    if along[-1] < needed:
        raise SceneStageError("design-infeasible", f"the sampled ramp is {along[-1]:.0f} m long, {needed:.0f} m needed")
    last = int(np.searchsorted(along, needed))
    t = (needed - along[last - 1]) / (along[last] - along[last - 1])
    end = xy[last - 1] + t * (xy[last] - xy[last - 1])
    xy = np.vstack([xy[:last], end])
    along = np.r_[along[:last], needed]
    z = rim_z_m - grade / 100.0 * along
    z[0], z[-1] = rim_z_m, floor_z_m
    centreline = np.column_stack([xy, z])
    inside = crest0.buffer(1e-6)
    import shapely

    if not shapely.contains_xy(inside, centreline[:, 0], centreline[:, 1]).all():
        raise SceneStageError("design-infeasible", "the ramp centreline leaves the pit rim")
    widened = [b.index for b in benches if b.toe_z >= floor_z_m - 1e-9 and b.crest_z <= rim_z_m + 1e-9]
    return Ramp(
        centreline=centreline,
        width_m=np.full(len(centreline), width, dtype=np.float64),
        sample_spacing_m=float(spacing),
        widened_bench_indices=widened,
    )
