"""The design USD layer: benches, berms, ramp, windrows and haul roads, all marked as design-code output (FR-004-20)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import DESIGN_LABEL

PROVENANCE = "design-code"
ROAD_WIDTH_M = 8.0
WINDROW_BASE_HALF_WIDTH_M = 1.0


def _ring_xyz(ring: Any, z: float) -> np.ndarray:
    from shapely.geometry.polygon import Polygon, orient

    xy = np.asarray(orient(Polygon(ring), 1.0).exterior.coords, dtype=np.float64)[:-1]
    return np.column_stack([xy, np.full(len(xy), z)])


def _loft(outer: np.ndarray, inner: np.ndarray) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """Triangles between two nested closed rings (greedy shorter diagonal); the inner ring is rotated to start
    nearest."""
    start = int(np.argmin(np.hypot(*(inner[:, :2] - outer[0, :2]).T)))
    inner = np.roll(inner, -start, axis=0)
    n, m = len(outer), len(inner)
    i = j = 0
    triangles = []
    while i < n or j < m:
        a0, a1 = outer[i % n], outer[(i + 1) % n]
        b0, b1 = inner[j % m], inner[(j + 1) % m]
        advance_outer = j >= m or (i < n and np.linalg.norm(a1 - b0) <= np.linalg.norm(a0 - b1))
        if advance_outer:
            triangles.append((a0, a1, b0))
            i += 1
        else:
            triangles.append((a0, b1, b0))
            j += 1
    return triangles


def _strip(
    points: np.ndarray, half_width: float, widths: np.ndarray | None = None
) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """A flat strip along a 3-D polyline: quads between the left and right edges, two triangles each."""
    xy = points[:, :2]
    tangent = np.gradient(xy, axis=0)
    norm = np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-12)
    left = np.column_stack([-tangent[:, 1] / norm, tangent[:, 0] / norm])
    half = half_width if widths is None else widths[:, None] / 2.0
    lo = np.column_stack([xy + half * left, points[:, 2]])
    hi = np.column_stack([xy - half * left, points[:, 2]])
    out = []
    for k in range(len(points) - 1):
        out.append((lo[k], lo[k + 1], hi[k + 1]))
        out.append((lo[k], hi[k + 1], hi[k]))
    return out


def _ridge(points: np.ndarray, height: float) -> list[tuple[np.ndarray, np.ndarray, np.ndarray]]:
    """A triangular ridge of the given height along a 3-D polyline."""
    xy = points[:, :2]
    tangent = np.gradient(xy, axis=0)
    norm = np.maximum(np.hypot(tangent[:, 0], tangent[:, 1]), 1e-12)
    left = np.column_stack([-tangent[:, 1] / norm, tangent[:, 0] / norm])
    w = WINDROW_BASE_HALF_WIDTH_M
    lo = np.column_stack([xy + w * left, points[:, 2]])
    top = np.column_stack([xy, points[:, 2] + height])
    hi = np.column_stack([xy - w * left, points[:, 2]])
    out = []
    for k in range(len(points) - 1):
        out.append((lo[k], lo[k + 1], top[k + 1]))
        out.append((lo[k], top[k + 1], top[k]))
        out.append((top[k], top[k + 1], hi[k + 1]))
        out.append((top[k], hi[k + 1], hi[k]))
    return out


def _mesh_arrays(triangles: list[tuple[np.ndarray, np.ndarray, np.ndarray]]) -> tuple[np.ndarray, np.ndarray]:
    """Vertex and index arrays of the triangles, each oriented counter-clockwise seen from above (normal up)."""
    tri = np.asarray(triangles, dtype=np.float64).reshape(-1, 3, 3)
    area = (tri[:, 1, 0] - tri[:, 0, 0]) * (tri[:, 2, 1] - tri[:, 0, 1]) - (tri[:, 2, 0] - tri[:, 0, 0]) * (
        tri[:, 1, 1] - tri[:, 0, 1]
    )
    keep = np.abs(area) > 1e-12
    tri, area = tri[keep], area[keep]
    flip = area < 0
    tri[flip] = tri[flip][:, [0, 2, 1], :]
    unique, inverse = np.unique(tri.reshape(-1, 3).astype(np.float32), axis=0, return_inverse=True)
    return unique, inverse.reshape(-1).astype(np.int32)


def write_design_layer(path: Path | str, result: Any, *, rel_path: str = "layers/design.usda") -> dict[str, Any]:
    """Write the `.usda` design layer of a `DesignResult` and return its DC-004-02 `layers[]` entry."""
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics, UsdSemantics, Vt
    from shapely import constrained_delaunay_triangles
    from shapely.geometry.polygon import orient

    path = Path(path)
    if path.exists():
        path.unlink()
    benches = result.benches
    meshes: dict[str, tuple[str, list[tuple[np.ndarray, np.ndarray, np.ndarray]]]] = {}  # path -> (class, triangles)
    for bench in benches:
        crest_ring = _ring_xyz(bench.crest.exterior, bench.crest_z)
        toe_ring = _ring_xyz(bench.toe.exterior, bench.toe_z)
        meshes[f"/World/Design/Benches/Bench_{bench.index:02d}"] = ("bench", _loft(crest_ring, toe_ring))
        if bench.index + 1 < len(benches):
            nxt = _ring_xyz(benches[bench.index + 1].crest.exterior, bench.toe_z)
            meshes[f"/World/Design/Berms/Berm_{bench.index:02d}"] = ("berm", _loft(toe_ring, nxt))
    floor = orient(benches[-1].toe, 1.0)
    floor_tris = [
        tuple(np.array([x, y, benches[-1].toe_z]) for x, y in list(t.exterior.coords)[:3])
        for t in constrained_delaunay_triangles(floor).geoms
    ]
    meshes["/World/Design/Benches/Bench_Floor"] = ("bench", floor_tris)
    if result.ramp is not None:
        centre = result.ramp.centreline
        meshes["/World/Design/Ramp/Ramp_00"] = ("ramp", _strip(centre, 0.0, result.ramp.width_m))
    for index, road in enumerate(result.bench_roads):
        meshes[f"/World/Design/HaulRoads/Road_{index:02d}"] = ("haul_road", _strip(road, ROAD_WIDTH_M / 2.0))
    for index, w in enumerate(result.windrows):
        coords = np.asarray(w.line.coords)
        if w.kind == "ramp":
            z = result.ramp.centreline[:, 2]
            line = np.column_stack([coords[:, :2], z[: len(coords)]])
            name = f"/World/Design/Windrows/Windrow_Ramp_{index:03d}"
        else:
            level = benches[w.bench_index].toe_z
            line = np.column_stack([coords[:, :2], np.full(len(coords), level)])
            name = f"/World/Design/Windrows/Windrow_Berm{w.bench_index:02d}_{index:03d}"
        meshes[name] = ("windrow", _ridge(line, w.height_m))

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    prim_paths = {"/World", "/World/Design"}
    for mesh_path in meshes:
        parts = mesh_path.split("/")
        prim_paths.update("/".join(parts[:k]) for k in range(3, len(parts) + 1))
    for prim_path in sorted(prim_paths):
        if prim_path in meshes:
            kind, tris = meshes[prim_path]
            points, indices = _mesh_arrays(tris)
            mesh = UsdGeom.Mesh.Define(stage, prim_path)
            mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points))
            mesh.CreateFaceVertexCountsAttr(Vt.IntArray.FromNumpy(np.full(len(indices) // 3, 3, dtype=np.int32)))
            mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(indices))
            mesh.CreateSubdivisionSchemeAttr("none")
            mesh.CreateExtentAttr(
                [Gf.Vec3f(*map(float, points.min(axis=0))), Gf.Vec3f(*map(float, points.max(axis=0)))]
            )
            prim = mesh.GetPrim()
            UsdSemantics.LabelsAPI.Apply(prim, "class").CreateLabelsAttr([kind])
        else:
            prim = UsdGeom.Xform.Define(stage, prim_path).GetPrim()
        if prim_path != "/World":
            prim.CreateAttribute("pitstudio:provenance", Sdf.ValueTypeNames.String).Set(PROVENANCE)
    stage.SetDefaultPrim(stage.GetPrimAtPath("/World"))
    stage.GetRootLayer().Save()
    data = path.read_bytes()
    return {
        "role": "design",
        "path": rel_path,
        "format": "usda",
        "sha256": common.sha256_bytes(data),
        "bytes": len(data),
        "up_axis": "Z",
        "meters_per_unit": 1.0,
        "kilograms_per_unit": 1.0,
        "label": DESIGN_LABEL,
    }
