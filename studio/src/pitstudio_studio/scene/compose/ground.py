"""Stand the fleet and the people on the terrain: stations on the design haul road, heights from the DEM.

The scene specification names the fleet by asset and count only, so the positions come from the haul-road centreline of
the design layer (`design/road-network.geojson`): the flattest stations of the `ramp` edges, measured on the grid.
Heights are the bilinear grid height at the station (never the design height, which disagrees with the DEM); nothing is
invented: no geometry is added and each placement records its edge and chainage in `pitstudio:placement`.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene.common import SceneStageError
from pitstudio_studio.scene.compose.grid import Grid

EDGE_CLASS = "ramp"
STEP_M = 10.0  # chainage step of the candidate stations
FOOTPRINT_M = 16.0  # side of the square the flatness is measured over (a truck is 12.8 x 7.3 m)
FOOTPRINT_STEP_M = 2.0
MIN_SPACING_M = 30.0  # between two stations of one edge
FLATNESS_ROUND_M = 0.01  # height ranges closer than this tie; ties go to the earlier edge and chainage
PEOPLE_AHEAD_M = 10.0  # people stand ahead of the first truck, to its side, 3 m apart
PEOPLE_SIDE_M = 6.0
PEOPLE_GAP_M = 3.0


@dataclass(frozen=True)
class Station:
    edge: str
    chainage_m: float
    x: float
    y: float
    heading_deg: float


def _edges(road: Mapping[str, Any]) -> list[tuple[str, np.ndarray]]:
    out = []
    for feature in road["features"]:
        props, geometry = feature["properties"], feature["geometry"]
        if props.get("kind") == "edge" and props.get("class") == EDGE_CLASS and geometry["type"] == "LineString":
            out.append((f"{props['from']}-{props['to']}", np.asarray(geometry["coordinates"], dtype=np.float64)[:, :2]))
    return out


def _flatness(grid: Grid, x: float, y: float) -> float:
    offsets = np.arange(-FOOTPRINT_M / 2, FOOTPRINT_M / 2 + 1e-9, FOOTPRINT_STEP_M)
    gx, gy = np.meshgrid(x + offsets, y + offsets)
    heights = grid.height(gx, gy)
    return float(heights.max() - heights.min())


def flattest_stations(road: Mapping[str, Any], grid: Grid, count: int) -> list[Station]:
    """`count` stations on the `ramp` edges, flattest first, at least 30 m apart on one edge."""
    candidates: list[tuple[float, int, float, Station]] = []
    for index, (name, line) in enumerate(_edges(road)):
        seg = np.diff(line, axis=0)
        length = np.hypot(seg[:, 0], seg[:, 1])
        along = np.concatenate([[0.0], np.cumsum(length)])
        for chainage in np.arange(0.0, along[-1] + 1e-9, STEP_M):
            k = min(int(np.searchsorted(along, chainage, side="right")) - 1, len(seg) - 1)
            t = (chainage - along[k]) / length[k]
            x, y = line[k] + t * seg[k]
            heading = math.degrees(math.atan2(seg[k][1], seg[k][0]))
            flat = round(_flatness(grid, float(x), float(y)) / FLATNESS_ROUND_M) * FLATNESS_ROUND_M
            candidates.append(
                (flat, index, float(chainage), Station(name, float(chainage), float(x), float(y), heading))
            )
    candidates.sort(key=lambda c: (c[0], c[1], c[2]))
    chosen: list[Station] = []
    for _, _, _, station in candidates:
        if all(s.edge != station.edge or abs(s.chainage_m - station.chainage_m) >= MIN_SPACING_M for s in chosen):
            chosen.append(station)
        if len(chosen) == count:
            return chosen
    raise SceneStageError(
        "compose-invalid",
        f"the haul road of the design layer holds {len(chosen)} station(s) {MIN_SPACING_M:.0f} m apart, {count} needed",
    )


def _set_pose(prim: Any, x: float, y: float, z: float, heading_deg: float | None, note: str) -> None:
    from pxr import Gf, Sdf, UsdGeom

    xform = UsdGeom.Xformable(prim)
    ops = {op.GetOpName(): op for op in xform.GetOrderedXformOps()}
    ops["xformOp:translate"].Set(Gf.Vec3d(x, y, z))
    if heading_deg is not None:
        rotate = ops.get("xformOp:rotateZ") or xform.AddRotateZOp()
        rotate.Set(float(heading_deg))
    prim.CreateAttribute("pitstudio:placement", Sdf.ValueTypeNames.String, custom=True).Set(note)


def ground_fleet(fleet_layer: Path, grid: Grid, road: Mapping[str, Any]) -> list[dict[str, Any]]:
    """Place every prim under `/World/Fleet` and `/World/People` of the fleet layer; returns the placements."""
    from pxr import Usd

    stage = Usd.Stage.Open(str(fleet_layer))
    trucks = list(stage.GetPrimAtPath("/World/Fleet").GetChildren())
    people = list(stage.GetPrimAtPath("/World/People").GetChildren())
    stations = flattest_stations(road, grid, len(trucks)) if trucks else []
    placements: list[dict[str, Any]] = []
    for prim, s in zip(trucks, stations, strict=True):
        z = float(grid.height(s.x, s.y))
        note = f"design haul-road edge {s.edge}, chainage {s.chainage_m:.1f} m, height from the DEM"
        _set_pose(prim, s.x, s.y, z, s.heading_deg, note)
        placements.append({"prim": str(prim.GetPath()), "x": s.x, "y": s.y, "z": z, "heading_deg": s.heading_deg})
    if stations:
        lead = stations[0]
        a = math.radians(lead.heading_deg)
        for i, prim in enumerate(people):
            ahead, side = PEOPLE_AHEAD_M + PEOPLE_GAP_M * i, PEOPLE_SIDE_M
            x = lead.x + ahead * math.cos(a) - side * math.sin(a)
            y = lead.y + ahead * math.sin(a) + side * math.cos(a)
            z = float(grid.height(x, y))
            note = f"beside the first truck on design haul-road edge {lead.edge}, height from the DEM"
            _set_pose(prim, x, y, z, None, note)
            placements.append({"prim": str(prim.GetPath()), "x": x, "y": y, "z": z, "heading_deg": None})
    stage.GetRootLayer().Save()
    return placements


def read_road(path: Path) -> dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))
