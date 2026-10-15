"""Windrows at or above the mid-axle height of the largest haul unit (FR-004-18, 30 CFR 56.9300(b))."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any

import numpy as np

from pitstudio_studio.scene.common import SceneStageError


@dataclass(frozen=True)
class WindrowRequirement:
    """The windrow height and the mid-axle height of the largest haul unit that governs it."""

    height_m: float
    mid_axle_height_m: float
    governing_asset: str


@dataclass
class Windrow:
    """A windrow line in the site frame: `kind` is `berm` (on bench `bench_index`) or `ramp`."""

    kind: str
    bench_index: int | None
    line: Any
    height_m: float


def windrow_requirement(
    assets: Sequence[Mapping[str, Any]], fleet: Sequence[Mapping[str, Any]], windrow_height_m: float
) -> WindrowRequirement:
    """The haul unit of the fleet with the greatest mass governs: its mid-axle height is the one to match
    (FR-004-18)."""
    in_fleet = {entry["asset"] for entry in fleet if entry.get("count", 0) > 0}
    haulers = [
        a
        for a in assets
        if a["id"] in in_fleet and a.get("class_label") == "haul_truck" and a.get("mid_axle_height_m") is not None
    ]
    if not haulers:
        raise SceneStageError(
            "design-infeasible", "windrow_height_m: no haul truck with a declared mid-axle height is in the fleet"
        )
    largest = max(haulers, key=lambda a: float(a["mass_kg"]))
    return WindrowRequirement(float(windrow_height_m), float(largest["mid_axle_height_m"]), str(largest["id"]))


def _pieces(geometry: Any) -> list[Any]:
    from shapely.geometry import LineString

    if geometry.is_empty:
        return []
    if geometry.geom_type == "LineString":
        return [geometry]
    return [g for g in getattr(geometry, "geoms", []) if isinstance(g, LineString) and g.length > 1e-6]


def place_windrows(benches: Sequence[Any], ramp: Any, *, height_m: float, ramp_width_m: float) -> list[Windrow]:
    """Berm windrows on the drop-off edge of every berm and ramp windrows on the outer edge of the ramp.

    The berm below bench k lies between `benches[k].toe` and `benches[k + 1].crest`; its windrow follows the next crest
    (the edge towards the lower bench) and is cut where the ramp strip crosses it. The ramp windrow is the centreline
    offset by half the ramp width towards the pit centre (the drop-off side of a counter-clockwise spiral).
    """
    import shapely
    from shapely.geometry import LineString

    footprint = None
    if ramp is not None:
        footprint = LineString(np.asarray(ramp.centreline)[:, :2]).buffer(ramp_width_m / 2.0, cap_style="flat")
    windrows: list[Windrow] = []
    for k in range(len(benches) - 1):
        edge = LineString(benches[k + 1].crest.exterior.coords)
        if footprint is not None:
            edge = edge.difference(footprint)
        windrows.extend(Windrow("berm", k, piece, float(height_m)) for piece in _pieces(edge))
    if ramp is not None:
        xy = np.asarray(ramp.centreline)[:, :2]
        tangent = np.gradient(xy, axis=0)
        norm = np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-12)
        left = np.column_stack([-tangent[:, 1] / norm, tangent[:, 0] / norm])
        centre_line = LineString(xy)
        half = ramp_width_m / 2.0
        # per sample: the smallest offset from W/2 on at which the point is clear of every lap of the spiral (a later
        # lap can run closer than W/2); samples with no clear offset are dropped and the line is split there
        offset = np.full(len(xy), np.nan)
        for step in range(40):
            todo = np.flatnonzero(np.isnan(offset))
            if todo.size == 0:
                break
            trial = half + 0.5 * step
            pts = xy[todo] + trial * left[todo]
            clear = shapely.distance(shapely.points(pts), centre_line) >= half + 1e-6
            offset[todo[clear]] = trial
        edge_xy = xy + np.nan_to_num(offset)[:, None] * left
        ok = ~np.isnan(offset)
        jump = np.r_[False, np.abs(np.diff(np.nan_to_num(offset))) > 2.0]
        start = 0
        for i in range(1, len(xy) + 1):
            if i == len(xy) or not ok[i] or jump[i]:
                run = [j for j in range(start, i) if ok[j]]
                if len(run) >= 2:
                    windrows.append(Windrow("ramp", None, LineString(edge_xy[run]), float(height_m)))
                start = i
    return windrows
