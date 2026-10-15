"""The spec 004 scene as the SDG sampler sees it: site, drivable road polygons and the design surface height.

`load_scene_inputs` reads the validated scene (`st45_validate/scene/scene.manifest.json`, `validation.status` must be
`complete`), checks the SHA-256 the manifest records for the pit design report and the road network, and returns the
road edges (centre line with the design height of every vertex, polygon = centre line buffered by half the ramp
width), the site centroid in WGS 84 and the design-surface height function.

The design surface height at a point is the height of the nearest road centre line at its projection: the haul road
is built with a flat cross-section, so inside a road polygon this is the design surface to within the discretisation of
the centre line (1 m vertices). Placement is therefore limited to the roads: the design layer carries benches as
meshes without 2-D footprints, and the source terrain grid is not the carved surface.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from pyproj import Transformer
from shapely.geometry import LineString, Polygon
from shapely.strtree import STRtree

MANIFEST = "scene.manifest.json"
_EDGE_ID = re.compile(r"[^a-z0-9_-]")


class SceneInputsError(ValueError):
    """The scene cannot feed the SDG sampler: incomplete validation, a digest that differs, or no road."""


@dataclass(frozen=True)
class RoadEdge:
    """One road edge of the design: id (a valid artefact id), vertices (x, y, z) in the stage frame, polygon."""

    edge_id: str
    xyz: np.ndarray
    polygon: Polygon
    length_m: float


@dataclass
class SceneInputs:
    """Everything the sampler needs from the validated scene (all lengths in metres, stage frame X east, Y north)."""

    scene_dir: Path
    manifest_id: str
    case: str
    latitude_deg: float
    longitude_deg: float
    z0_m: float
    ramp_width_m: float
    edges: tuple[RoadEdge, ...]
    terrain_tiles: Path

    def __post_init__(self) -> None:
        self._union: shapely.geometry.base.BaseGeometry | None = None
        self._tree = STRtree([LineString(e.xyz[:, :2]) for e in self.edges])
        self._lines = [LineString(e.xyz[:, :2]) for e in self.edges]
        self._cum = [np.concatenate([[0.0], np.cumsum(np.hypot(*np.diff(e.xyz[:, :2], axis=0).T))]) for e in self.edges]

    def edge(self, edge_id: str) -> RoadEdge:
        for e in self.edges:
            if e.edge_id == edge_id:
                return e
        raise KeyError(edge_id)

    def road_union(self) -> shapely.geometry.base.BaseGeometry:
        """The drivable surface: union of the road polygons."""
        if self._union is None:
            self._union = shapely.union_all([e.polygon for e in self.edges])
        return self._union

    def height_at(self, x_m: float, y_m: float) -> float:
        """Design surface height (stage z, m) at a point: that of the nearest road centre line at its projection."""
        point = shapely.Point(float(x_m), float(y_m))
        k = int(self._tree.nearest(point))
        s = self._lines[k].project(point)
        return float(np.interp(s, self._cum[k], self.edges[k].xyz[:, 2]))

    def position_on_edge(self, edge_id: str, fraction: float) -> tuple[float, float, float, float]:
        """(x, y, z, heading_deg) at `fraction` of the edge length; heading is the direction of travel, deg from +X."""
        for k, e in enumerate(self.edges):
            if e.edge_id == edge_id:
                s = min(max(float(fraction), 0.0), 1.0) * self._cum[k][-1]
                x = float(np.interp(s, self._cum[k], e.xyz[:, 0]))
                y = float(np.interp(s, self._cum[k], e.xyz[:, 1]))
                z = float(np.interp(s, self._cum[k], e.xyz[:, 2]))
                s2 = min(s + 5.0, self._cum[k][-1])
                s1 = max(s2 - 10.0, 0.0)
                dx = float(np.interp(s2, self._cum[k], e.xyz[:, 0]) - np.interp(s1, self._cum[k], e.xyz[:, 0]))
                dy = float(np.interp(s2, self._cum[k], e.xyz[:, 1]) - np.interp(s1, self._cum[k], e.xyz[:, 1]))
                return x, y, z, math.degrees(math.atan2(dy, dx))
        raise KeyError(edge_id)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _edge_id(source: str, target: str) -> str:
    return "edge-" + _EDGE_ID.sub("-", f"{source}-{target}".lower())[:80]


def _verified(scene: Path, ref: dict[str, Any], label: str) -> Path:
    path = scene / ref["path"]
    if not path.is_file():
        raise SceneInputsError(f"{label} {ref['path']} is absent from the scene")
    if _sha256(path) != ref["sha256"]:
        raise SceneInputsError(f"{label} {ref['path']} differs from the SHA-256 in the scene manifest")
    return path


def load_scene_inputs(scene_dir: Path) -> SceneInputs:
    """Read the validated scene below `scene_dir` (the `st45_validate/scene` folder); `SceneInputsError` otherwise."""
    scene = Path(scene_dir)
    manifest_path = scene / MANIFEST
    if not manifest_path.is_file():
        raise SceneInputsError(f"{manifest_path} is absent")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    status = (manifest.get("validation") or {}).get("status")
    if status != "complete":
        raise SceneInputsError(f"the validation status of the scene is {status!r}, expected 'complete'")
    report = json.loads(_verified(scene, manifest["design"]["report"], "pit design report").read_text(encoding="utf-8"))
    network = json.loads(_verified(scene, manifest["design"]["road_network"], "road network").read_text("utf-8"))
    tiles = _verified(scene, manifest["terrain"]["tiles"], "terrain tiles")
    ramp_width = float(report["ramp"]["min_width_m"])
    origin = manifest["site"]["origin"]
    lon, lat = Transformer.from_crs(origin["epsg"], 4326, always_xy=True).transform(
        origin["easting_m"], origin["northing_m"]
    )
    edges = []
    for feature in network["features"]:
        if feature["geometry"]["type"] != "LineString":
            continue
        xyz = np.asarray(feature["geometry"]["coordinates"], dtype=np.float64)
        props = feature["properties"]
        line = LineString(xyz[:, :2])
        polygon = line.buffer(ramp_width / 2.0, cap_style="flat", join_style="round")
        edges.append(RoadEdge(_edge_id(props["from"], props["to"]), xyz, polygon, float(line.length)))
    if not edges:
        raise SceneInputsError("the road network has no edge")
    ids = [e.edge_id for e in edges]
    if len(set(ids)) != len(ids):
        raise SceneInputsError("two road edges share an id")
    return SceneInputs(
        scene_dir=scene,
        manifest_id=str(manifest["manifest_id"]),
        case=str(manifest["case"]),
        latitude_deg=float(lat),
        longitude_deg=float(lon),
        z0_m=float(origin["z0_m"]),
        ramp_width_m=ramp_width,
        edges=tuple(edges),
        terrain_tiles=tiles,
    )


def wedge(apex_xy: Sequence[float], heading_deg: float, half_fov_deg: float, near_m: float, far_m: float) -> Polygon:
    """The ground region a camera at `apex_xy` looking along `heading_deg` can see: an annular sector (near, far)."""
    angles = np.radians(np.linspace(heading_deg - half_fov_deg, heading_deg + half_fov_deg, 9))
    outer = [(apex_xy[0] + far_m * math.cos(a), apex_xy[1] + far_m * math.sin(a)) for a in angles]
    inner = [(apex_xy[0] + near_m * math.cos(a), apex_xy[1] + near_m * math.sin(a)) for a in angles[::-1]]
    return Polygon([*outer, *inner])
