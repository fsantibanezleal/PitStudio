"""The asset stage `st30_assets`: procedural machines and people with physics and labels, CC0 materials (FR-004-24 ..
28)."""

from __future__ import annotations

import math
import re
import shutil
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import SceneStageError, StageContext, StageRun
from pitstudio_studio.scene.normals import author_normals

CC0_SOURCES = {"polyhaven", "ambientcg"}
OWN_SPDX = "CC-BY-4.0"
PROVENANCE_MANNEQUIN = "procedural-mannequin"
PROVENANCE_MAKEHUMAN = "makehuman-export"
BOX_FACES = [0, 2, 3, 1, 4, 5, 7, 6, 0, 1, 5, 4, 2, 6, 7, 3, 0, 4, 6, 2, 1, 3, 7, 5]  # counter-clockwise from outside
FLEET_SPACING_M = 20.0
PEOPLE_SPACING_M = 3.0


@dataclass
class AssetBuild:
    """The files of the asset stage and the records the scene manifest takes over."""

    machines: dict[str, Path]
    fleet_layer: Path
    materials_layer: Path
    textures: list[dict[str, Any]]
    people_route: str
    files: list[Path] = field(default_factory=list)


def prim_name(identifier: str) -> str:
    """A USD prim name for a slug (`dump-body` becomes `dump_body`)."""
    name = re.sub(r"[^A-Za-z0-9_]", "_", identifier)
    return name if re.match(r"[A-Za-z_]", name) else f"_{name}"


# ----------------------------------------------------------------------------------------------------------------
# validation (before anything is written)
# ----------------------------------------------------------------------------------------------------------------
def _positive(owner: str, values: Mapping[str, Any], keys: tuple[str, ...]) -> None:
    for key in keys:
        value = values.get(key)
        if not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value) or value <= 0:
            raise SceneStageError("asset-invalid", f"{owner}: {key} must be a positive finite number, got {value!r}")


def _check_parts(asset: Mapping[str, Any], parts: list[Mapping[str, Any]], part_labels: set[str]) -> None:
    owner = asset["id"]
    by_id = {p["id"]: p for p in parts}
    roots = [p["id"] for p in parts if p.get("parent") is None]
    if len(roots) != 1:
        names = ", ".join(roots) if roots else ", ".join(p["id"] for p in parts)
        what = f"{len(roots)} roots ({names})" if roots else f"no root: its parts form a cycle ({names})"
        raise SceneStageError("asset-invalid", f"{owner}: the joint graph has {what}, exactly one root is required")
    for part in parts:
        _positive(f"{owner}/{part['id']}", part, ("mass_kg", "length_m", "width_m", "height_m"))
        if part["part"] not in part_labels:
            raise SceneStageError(
                "asset-invalid", f"{owner}/{part['id']}: part label {part['part']!r} is outside the vocabulary"
            )
        parent = part.get("parent")
        if parent is not None and parent not in by_id:
            raise SceneStageError(
                "asset-invalid", f"{owner}/{part['id']}: parent {parent!r} is not a part of the asset"
            )
    for part in parts:
        seen: set[str] = set()
        node: str | None = part["id"]
        while node is not None:
            if node in seen:
                raise SceneStageError("asset-invalid", f"{owner}/{part['id']}: the joint graph has a cycle")
            seen.add(node)
            node = by_id[node].get("parent")


def validate_spec(spec: Mapping[str, Any], textures: Mapping[str, Path] | None) -> None:
    """`asset-invalid` for a bad dimension, mass, label, joint graph or texture licence (FR-004-27)."""
    classes = set(spec["labels"]["classes"])
    part_labels = set(spec["labels"]["parts"])
    for asset in spec["assets"]:
        _positive(asset["id"], asset, ("mass_kg", "length_m", "width_m", "height_m"))
        if asset["class_label"] not in classes:
            raise SceneStageError(
                "asset-invalid", f"{asset['id']}: class label {asset['class_label']!r} is outside the vocabulary"
            )
        _check_parts(asset, [p for p in spec["parts"] if p["asset"] == asset["id"]], part_labels)
    for material in spec["materials"]:
        source, spdx = material.get("source"), material.get("spdx")
        ok = (source in CC0_SOURCES and spdx == "CC0-1.0") or (source is None and spdx == OWN_SPDX)
        if not ok:
            raise SceneStageError(
                "asset-invalid",
                f"{material['id']}: texture licence {spdx} from source {source!r} is not CC0-1.0 "
                "(Poly Haven, ambientCG) or our own",
            )
        if textures is None or material["id"] not in textures or not Path(textures[material["id"]]).is_file():
            raise SceneStageError("asset-invalid", f"{material['id']}: no texture file was given")


# ----------------------------------------------------------------------------------------------------------------
# USD authoring
# ----------------------------------------------------------------------------------------------------------------
def _new_stage(path: Path) -> Any:
    from pxr import Usd, UsdGeom, UsdPhysics

    if path.exists():
        path.unlink()
    path.parent.mkdir(parents=True, exist_ok=True)
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    return stage


def _box_mesh(stage: Any, path: str, size: tuple[float, float, float], centre: tuple[float, float, float]) -> Any:
    from pxr import Gf, UsdGeom

    hx, hy, hz = (s / 2.0 for s in size)
    cx, cy, cz = centre
    corners = [(x, y, z) for z in (-hz, hz) for y in (-hy, hy) for x in (-hx, hx)]
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr([Gf.Vec3f(cx + x, cy + y, cz + z) for x, y, z in corners])
    mesh.CreateFaceVertexCountsAttr([4] * 6)
    mesh.CreateFaceVertexIndicesAttr(BOX_FACES)
    mesh.CreateSubdivisionSchemeAttr("none")
    author_normals(mesh, [(cx + x, cy + y, cz + z) for x, y, z in corners], [4] * 6, BOX_FACES, interpolation="uniform")
    mesh.CreateExtentAttr([Gf.Vec3f(cx - hx, cy - hy, cz - hz), Gf.Vec3f(cx + hx, cy + hy, cz + hz)])
    return mesh


def _label(prim: Any, instance: str, value: str) -> None:
    from pxr import UsdSemantics

    UsdSemantics.LabelsAPI.Apply(prim, instance).CreateLabelsAttr([value])


def _write_machine(path: Path, asset: Mapping[str, Any], parts: list[Mapping[str, Any]]) -> None:
    """One machine: an articulation root over rigid-body boxes (one per part) and a tree of limited, driven joints."""
    from pxr import Gf, Sdf, UsdGeom, UsdPhysics

    stage = _new_stage(path)
    root_name = prim_name(asset["id"])
    root = UsdGeom.Xform.Define(stage, f"/{root_name}")
    stage.SetDefaultPrim(root.GetPrim())
    UsdPhysics.ArticulationRootAPI.Apply(root.GetPrim())
    root.GetPrim().CreateAttribute("pitstudio:provenance", Sdf.ValueTypeNames.String).Set("procedural-machine")
    by_id = {p["id"]: p for p in parts}
    position: dict[str, tuple[float, float, float]] = {}
    paths: dict[str, str] = {}

    def place(part_id: str) -> tuple[float, float, float]:
        if part_id in position:
            return position[part_id]
        part = by_id[part_id]
        if part.get("parent") is None:
            position[part_id] = (0.0, 0.0, part["height_m"] / 2.0)
        else:
            px, py, pz = place(part["parent"])
            parent = by_id[part["parent"]]
            position[part_id] = (px, py, pz + (parent["height_m"] + part["height_m"]) / 2.0)
        return position[part_id]

    for part in sorted(parts, key=lambda p: prim_name(p["id"])):
        paths[part["id"]] = f"/{root_name}/{prim_name(part['id'])}"
    for part in sorted(parts, key=lambda p: prim_name(p["id"])):
        pos = place(part["id"])
        mesh = _box_mesh(stage, paths[part["id"]], (part["length_m"], part["width_m"], part["height_m"]), pos)
        prim = mesh.GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(prim)
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(float(part["mass_kg"]))
        UsdPhysics.CollisionAPI.Apply(prim)
        UsdPhysics.MeshCollisionAPI.Apply(prim).CreateApproximationAttr("convexHull")
        _label(prim, "class", asset["class_label"])
        _label(prim, "part", part["part"])
    UsdGeom.Scope.Define(stage, f"/{root_name}/Joints")
    for part in sorted((p for p in parts if p.get("parent") is not None), key=lambda p: prim_name(p["id"])):
        jpath = f"/{root_name}/Joints/{prim_name(part['id'])}"
        revolute = part.get("joint", "revolute") == "revolute"
        joint = (
            UsdPhysics.RevoluteJoint.Define(stage, jpath)
            if revolute
            else UsdPhysics.PrismaticJoint.Define(stage, jpath)
        )
        joint.CreateBody0Rel().SetTargets([Sdf.Path(paths[part["parent"]])])
        joint.CreateBody1Rel().SetTargets([Sdf.Path(paths[part["id"]])])
        axis = part.get("axis", "Y")
        joint.CreateAxisAttr(axis)
        lo, hi = (part["lower_deg"], part["upper_deg"]) if revolute else (part["lower_m"], part["upper_m"])
        joint.CreateLowerLimitAttr(float(lo))
        joint.CreateUpperLimitAttr(float(hi))
        parent_pos, own_pos = position[part["parent"]], position[part["id"]]
        joint.CreateLocalPos0Attr(Gf.Vec3f(*(o - p for o, p in zip(own_pos, parent_pos, strict=True))))
        joint.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))
        joint.CreateExcludeFromArticulationAttr(bool(part.get("exclude_from_articulation", False)))
        dof = f"rot{axis}" if revolute else f"trans{axis}"
        UsdPhysics.LimitAPI.Apply(joint.GetPrim(), dof)
        UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular" if revolute else "linear")
    stage.GetRootLayer().Save()


def _parse_obj(path: Path) -> tuple[list[tuple[float, float, float]], list[list[int]]]:
    vertices: list[tuple[float, float, float]] = []
    faces: list[list[int]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        parts = line.split()
        if not parts:
            continue
        if parts[0] == "v" and len(parts) >= 4:
            vertices.append((float(parts[1]), float(parts[2]), float(parts[3])))
        elif parts[0] == "f" and len(parts) >= 4:
            faces.append([int(p.split("/")[0]) - 1 for p in parts[1:]])
    return vertices, faces


def _person_mannequin(stage: Any, base: str, route_files: list[Path]) -> None:
    from pxr import Gf, UsdGeom

    body = UsdGeom.Capsule.Define(stage, f"{base}/Body")
    body.CreateRadiusAttr(0.22)
    body.CreateHeightAttr(0.9)
    body.CreateAxisAttr("Z")
    body.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 0.85))
    head = UsdGeom.Sphere.Define(stage, f"{base}/Head")
    head.CreateRadiusAttr(0.11)
    head.AddTranslateOp().Set(Gf.Vec3d(0.0, 0.0, 1.62))
    for gprim in (body, head):
        _label(gprim.GetPrim(), "class", "person")


def _person_makehuman(stage: Any, base: str, obj: Path) -> None:
    from pxr import Gf, UsdGeom

    vertices, faces = _parse_obj(obj)
    mesh = UsdGeom.Mesh.Define(stage, f"{base}/Body")
    mesh.CreatePointsAttr([Gf.Vec3f(*v) for v in vertices])
    mesh.CreateFaceVertexCountsAttr([len(f) for f in faces])
    mesh.CreateFaceVertexIndicesAttr([i for f in faces for i in f])
    mesh.CreateSubdivisionSchemeAttr("none")
    author_normals(mesh, vertices, [len(f) for f in faces], [i for f in faces for i in f])
    _label(mesh.GetPrim(), "class", "person")


def _write_fleet(
    path: Path, spec: Mapping[str, Any], machines: dict[str, Path], route: str, exports: list[Path]
) -> None:
    from pxr import Gf, Sdf, UsdGeom

    stage = _new_stage(path)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    UsdGeom.Xform.Define(stage, "/World/Fleet")
    names = [
        (f"{prim_name(entry['asset'])}_{n:02d}", entry["asset"])
        for entry in spec["fleet"]
        for n in range(int(entry["count"]))
    ]
    for index, (name, asset) in enumerate(sorted(names)):
        xform = UsdGeom.Xform.Define(stage, f"/World/Fleet/{name}")
        xform.GetPrim().GetReferences().AddReference(f"../assets/{machines[asset].name}")
        xform.AddTranslateOp().Set(Gf.Vec3d(FLEET_SPACING_M * (index % 8), FLEET_SPACING_M * (index // 8), 0.0))
    count = int(spec.get("people_count", 0))
    if count:
        UsdGeom.Xform.Define(stage, "/World/People")
        provenance = PROVENANCE_MAKEHUMAN if route == "makehuman" else PROVENANCE_MANNEQUIN
        for n in range(count):
            base = f"/World/People/Person_{n:02d}"
            person = UsdGeom.Xform.Define(stage, base)
            person.AddTranslateOp().Set(Gf.Vec3d(PEOPLE_SPACING_M * (n % 10), -PEOPLE_SPACING_M * (1 + n // 10), 0.0))
            person.GetPrim().CreateAttribute("pitstudio:provenance", Sdf.ValueTypeNames.String).Set(provenance)
            if route == "makehuman":
                _person_makehuman(stage, base, exports[n % len(exports)])
            else:
                _person_mannequin(stage, base, exports)
    stage.GetRootLayer().Save()


def _write_materials(path: Path, spec: Mapping[str, Any], copied: dict[str, str]) -> None:
    """One `UsdShade.Material` per material: a UsdPreviewSurface fed by a UsdUVTexture of the copied CC0 file."""
    from pxr import Sdf, UsdGeom, UsdShade

    stage = _new_stage(path)
    stage.SetDefaultPrim(UsdGeom.Scope.Define(stage, "/Materials").GetPrim())
    for material in sorted(spec["materials"], key=lambda m: prim_name(m["id"])):
        name = prim_name(material["id"])
        mat = UsdShade.Material.Define(stage, f"/Materials/{name}")
        surface = UsdShade.Shader.Define(stage, f"/Materials/{name}/Surface")
        surface.CreateIdAttr("UsdPreviewSurface")
        surface.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(0.8)
        reader = UsdShade.Shader.Define(stage, f"/Materials/{name}/UV")
        reader.CreateIdAttr("UsdPrimvarReader_float2")
        reader.CreateInput("varname", Sdf.ValueTypeNames.Token).Set("st")
        reader.CreateOutput("result", Sdf.ValueTypeNames.Float2)
        texture = UsdShade.Shader.Define(stage, f"/Materials/{name}/Texture")
        texture.CreateIdAttr("UsdUVTexture")
        texture.CreateInput("file", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(copied[material["id"]]))
        texture.CreateInput("st", Sdf.ValueTypeNames.Float2).ConnectToSource(reader.GetOutput("result"))
        texture.CreateOutput("rgb", Sdf.ValueTypeNames.Float3)
        surface.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).ConnectToSource(texture.GetOutput("rgb"))
        surface.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        mat.CreateSurfaceOutput().ConnectToSource(surface.GetOutput("surface"))
    stage.GetRootLayer().Save()


# ----------------------------------------------------------------------------------------------------------------
# the stage
# ----------------------------------------------------------------------------------------------------------------
def build_assets(
    spec: Mapping[str, Any],
    out_dir: Path | str,
    *,
    textures: Mapping[str, Path] | None = None,
    makehuman_dir: Path | str | None = None,
    makehuman_smoke_passed: bool = False,
) -> AssetBuild:
    """Build the machines, materials and the fleet layer under `out_dir` (nothing is written when the spec is invalid).

    Writes `assets/<asset id>.usda`, `assets/materials.usda` with `assets/textures/<file>`, and `layers/fleet.usda`.
    """
    validate_spec(spec, textures)
    out = Path(out_dir)
    machines: dict[str, Path] = {}
    files: list[Path] = []
    for asset in spec["assets"]:
        path = out / "assets" / f"{asset['id']}.usda"
        _write_machine(path, asset, [p for p in spec["parts"] if p["asset"] == asset["id"]])
        machines[asset["id"]] = path
        files.append(path)
    records: list[dict[str, Any]] = []
    copied: dict[str, str] = {}
    for material in spec["materials"]:
        source = Path(textures[material["id"]])  # type: ignore[index]
        target = out / "assets" / "textures" / f"{prim_name(material['id'])}{source.suffix.lower()}"
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
        copied[material["id"]] = f"textures/{target.name}"
        records.append(
            {
                "id": material["id"],
                "source": material["source"],
                "spdx": material["spdx"],
                "sha256": common.sha256_file(target),
            }
        )
    materials_layer = out / "assets" / "materials.usda"
    _write_materials(materials_layer, spec, copied)
    files.append(materials_layer)
    exports: list[Path] = []
    if makehuman_smoke_passed and makehuman_dir is not None and Path(makehuman_dir).is_dir():
        exports = sorted(Path(makehuman_dir).glob("*.obj"))
    route = "makehuman" if exports else "procedural-mannequin"
    fleet_layer = out / "layers" / "fleet.usda"
    _write_fleet(fleet_layer, spec, machines, route, exports)
    files.append(fleet_layer)
    return AssetBuild(machines, fleet_layer, materials_layer, records, route, files)


def _body(ctx: StageContext) -> str:
    from pitstudio_studio.scene.terrain import io as terrain_io

    roots = common.job_roots()
    textures: dict[str, Path] = {}
    for name, items in ctx.inputs.items():
        if roots:
            textures[name] = terrain_io.resolve_input(items[0]["path"], roots=roots, sha256=items[0].get("sha256"))
    build = build_assets(ctx.params, ctx.work, textures=textures)
    import json

    (ctx.work / "assets" / "records.json").write_text(
        json.dumps({"textures": build.textures, "people_route": build.people_route}, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return f"{len(build.machines)} machines, route {build.people_route}"


def run(job: Mapping[str, Any]) -> StageRun:
    """The stage entry `pitstudio_studio.scene.assets`: job spec in, stage result out (see `common.run_stage`)."""
    return common.run_stage(job, _body)
