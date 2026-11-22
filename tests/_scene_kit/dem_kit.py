"""Hand-written inputs of the compose look and grounding tests (T-004-095, T-004-096).

The terrain is an analytic surface so every expected value is a hand calculation, never the code under test:
`z(x, y) = 0.1 x + 0.05 y + 3` for x < 60 and `z = 9 + 0.05 y` for x >= 60 (continuous at x = 60, a plateau with a
slope along y only). Grid: 400 x 400 cells of 1 m, x from -200 to 200, y from -200 to 200 (row 0 is the north row).
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path
from typing import Any

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402

X_MIN, Y_MAX, CELL, ROWS, COLS = -200.0, 200.0, 1.0, 400, 400
PLATEAU_X = 60.0


def plane_z(x: float, y: float) -> float:
    return 0.1 * x + 0.05 * y + 3.0 if x < PLATEAU_X else 9.0 + 0.05 * y


def plane_gradient(x: float, y: float) -> tuple[float, float]:
    return (0.1, 0.05) if x < PLATEAU_X else (0.0, 0.05)


def analytic_normal(x: float, y: float) -> np.ndarray:
    gx, gy = plane_gradient(x, y)
    n = np.array([-gx, -gy, 1.0])
    return n / np.linalg.norm(n)


def elevation() -> np.ndarray:
    xs = X_MIN + np.arange(COLS) * CELL
    ys = Y_MAX - np.arange(ROWS) * CELL
    return np.array([[plane_z(x, y) for x in xs] for y in ys], dtype=np.float64)


def write_grid(root: Path) -> dict[str, Path]:
    """The terrain grid as the terrain stage writes it (zarr v3 group, `elevation` array); returns scene-relative files."""
    import zarr

    folder = root / "records" / "terrain" / "grid.zarr"
    attrs = {
        "schema_version": "1.0",
        "kind": "terrain-grid",
        "frame": "site-enu",
        "layout": "north-up",
        "cell_size_m": CELL,
        "rows": ROWS,
        "cols": COLS,
        "x_min_m": X_MIN,
        "y_max_m": Y_MAX,
    }
    group = zarr.open_group(str(folder), mode="w", zarr_format=3)
    group.attrs.update(attrs)
    group.create_array("elevation", data=elevation().astype(np.float32), chunks=(200, 200))
    return {
        f"terrain/grid.zarr/{p.relative_to(folder).as_posix()}": p for p in sorted(folder.rglob("*")) if p.is_file()
    }


def terrain_layer(path: Path) -> None:
    """Terrain layer: variant set `lod`, per lod two adjacent 20 m tiles with a skirt ring and wrong (+y) normals."""
    from pxr import UsdGeom, UsdSemantics

    st = kit.new_usd_stage(path)
    world = UsdGeom.Xform.Define(st, "/World")
    st.SetDefaultPrim(world.GetPrim())
    terrain = UsdGeom.Xform.Define(st, "/World/Terrain")
    vset = terrain.GetPrim().GetVariantSets().AddVariantSet("lod")
    for i in range(3):
        vset.AddVariant(f"lod{i}")
        vset.SetVariantSelection(f"lod{i}")
        with vset.GetVariantEditContext():
            UsdGeom.Xform.Define(st, f"/World/Terrain/Lod{i}")
            for t, x0 in enumerate((0.0, 20.0)):
                points, counts, indices = _tile(x0, 0.0, 20.0, 4)
                mesh = UsdGeom.Mesh.Define(st, f"/World/Terrain/Lod{i}/Tile_{i}_0_{t}_0")
                mesh.CreatePointsAttr(points)
                mesh.CreateFaceVertexCountsAttr(counts)
                mesh.CreateFaceVertexIndicesAttr(indices)
                mesh.CreateSubdivisionSchemeAttr("none")
                mesh.CreateNormalsAttr([(0.0, 1.0, 0.0)] * len(points))
                mesh.SetNormalsInterpolation("vertex")
                UsdSemantics.LabelsAPI.Apply(mesh.GetPrim(), "class").CreateLabelsAttr(["terrain"])
    vset.SetVariantSelection("lod0")
    st.GetRootLayer().Save()


def _tile(x0: float, y0: float, size: float, n: int) -> tuple[list[tuple[float, float, float]], list[int], list[int]]:
    """An (n+1) x (n+1) surface lattice on the analytic terrain plus a skirt ring 0.5 m below the border."""
    step = size / n
    pts = [(x0 + i * step, y0 + j * step, plane_z(x0 + i * step, y0 + j * step)) for j in range(n + 1) for i in range(n + 1)]
    idx: list[int] = []
    for j in range(n):
        for i in range(n):
            a, b = j * (n + 1) + i, j * (n + 1) + i + 1
            c, d = (j + 1) * (n + 1) + i, (j + 1) * (n + 1) + i + 1
            idx += [a, b, d, a, d, c]
    ring = [j * (n + 1) + i for j in range(n + 1) for i in range(n + 1) if i in (0, n) or j in (0, n)]
    skirt = {v: len(pts) + k for k, v in enumerate(ring)}
    pts += [(pts[v][0], pts[v][1], pts[v][2] - 0.5) for v in ring]
    for v in ring:  # a degenerate-free wall: one triangle per ring vertex with its successor on the ring (cosmetic)
        w = ring[(ring.index(v) + 1) % len(ring)]
        idx += [v, w, skirt[v]]
    return pts, [3] * (len(idx) // 3), idx


def fleet_layer(path: Path, trucks: int = 2) -> None:
    from pxr import Gf, UsdGeom

    st = kit.new_usd_stage(path)
    st.SetDefaultPrim(UsdGeom.Xform.Define(st, "/World").GetPrim())
    UsdGeom.Xform.Define(st, "/World/Fleet")
    for i in range(trucks):
        UsdGeom.Xform.Define(st, f"/World/Fleet/Truck_{i:02d}").AddTranslateOp().Set(Gf.Vec3d(20.0 * i, 0.0, 0.0))
    UsdGeom.Xform.Define(st, "/World/People")
    UsdGeom.Xform.Define(st, "/World/People/Person_00").AddTranslateOp().Set(Gf.Vec3d(0.0, -3.0, 0.0))
    st.GetRootLayer().Save()


def design_layer(path: Path) -> None:
    from pxr import UsdGeom

    st = kit.new_usd_stage(path)
    st.SetDefaultPrim(UsdGeom.Xform.Define(st, "/World").GetPrim())
    UsdGeom.Xform.Define(st, "/World/Design")
    UsdGeom.Xform.Define(st, "/World/Design/HaulRoads")
    kit.define_quad(st, "/World/Design/HaulRoads/Road_00", 30.0, "haul_road")
    st.GetRootLayer().Save()


def road_network(*, edge_m: float = 360.0, angle_deg: float = 0.0) -> dict[str, Any]:
    """A `ramp` edge of `edge_m` metres through (-180, -10) at `angle_deg`, plus a bench road that must be ignored."""
    a = math.radians(angle_deg)
    start = (-180.0, -10.0)
    end = (start[0] + edge_m * math.cos(a), start[1] + edge_m * math.sin(a))

    def line(frm: str, to: str, cls: str, p: tuple[float, float], q: tuple[float, float]) -> dict[str, Any]:
        props = {"kind": "edge", "class": cls, "from": frm, "to": to, "length_m": edge_m}
        return {"type": "Feature", "properties": props, "geometry": {"type": "LineString", "coordinates": [[*p, 0.0], [*q, -15.0]]}}

    flat_bench = line("n8", "n9", "bench-road", (65.0, 100.0), (180.0, 100.0))  # flatter than any ramp: not a ramp
    return {"type": "FeatureCollection", "features": [line("n1", "n2", "ramp", start, end), flat_bench]}


MATERIALS = """#usda 1.0
(
    defaultPrim = "Materials"
    kilogramsPerUnit = 1
    metersPerUnit = 1
    upAxis = "Z"
)

def Scope "Materials"
{
%s}
"""
MATERIAL = """    def Material "%(name)s"
    {
        token outputs:surface.connect = </Materials/%(name)s/Surface.outputs:surface>

        def Shader "Surface"
        {
            uniform token info:id = "UsdPreviewSurface"
            color3f inputs:diffuseColor.connect = </Materials/%(name)s/Texture.outputs:rgb>
            float inputs:roughness = 0.8
            token outputs:surface
        }

        def Shader "UV"
        {
            uniform token info:id = "UsdPrimvarReader_float2"
            token inputs:varname = "st"
            float2 outputs:result
        }

        def Shader "Texture"
        {
            uniform token info:id = "UsdUVTexture"
            asset inputs:file = @textures/%(name)s.jpg@
            float2 inputs:st.connect = </Materials/%(name)s/UV.outputs:result>
            float3 outputs:rgb
        }
    }
"""


def materials_asset(folder: Path, *, textures: tuple[str, ...] = ("bench_rock",)) -> Path:
    """`materials.usda` with `bench_rock` and `gravel_road`, and a texture file only for the names in `textures`."""
    folder.mkdir(parents=True, exist_ok=True)
    body = "\n".join(MATERIAL % {"name": n} for n in ("bench_rock", "gravel_road"))
    path = folder / "materials.usda"
    path.write_text(MATERIALS % body, encoding="utf-8", newline="\n")
    (folder / "textures").mkdir(exist_ok=True)
    for name in textures:
        kit.tiny_png(folder / "textures" / f"{name}.jpg")
    return path


def upstream(root: Path, *, textures: tuple[str, ...] = ("bench_rock",), trucks: int = 2, road: bool = True,
             grid: bool = True, materials: bool = True, edge_m: float = 360.0, angle_deg: float = 0.0) -> dict[str, Any]:
    """`kit.fixture_upstream` with an analytic terrain, a fleet at the origin, a grid, a road network and materials."""
    up = kit.fixture_upstream(root)
    layers = root / "layers"
    terrain_layer(layers / "terrain.usdc")
    fleet_layer(layers / "fleet.usda", trucks)
    design_layer(layers / "design.usda")
    up["layer_sha256"] = {k: kit.sha256_file(v) for k, v in up["layers"].items()}
    files = dict(up["files"])
    if grid:
        files = {k: v for k, v in files.items() if not k.startswith("terrain/grid.zarr")}
        files.update(write_grid(root))
        up["records"]["terrain"]["grid"]["sha256"] = kit.sha256_file(files["terrain/grid.zarr/zarr.json"])
    if road:
        target = root / "records" / "design" / "road-network.geojson"
        target.write_text(json.dumps(road_network(edge_m=edge_m, angle_deg=angle_deg)), encoding="utf-8", newline="\n")
        files["design/road-network.geojson"] = target
        up["records"]["design"]["road_network"]["sha256"] = kit.sha256_file(target)
    up["files"] = files
    if materials:
        up["assets"] = [*up["assets"], materials_asset(root / "assets_src", textures=textures)]
    return up
