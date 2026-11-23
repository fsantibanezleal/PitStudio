"""USD authoring of the procedural machines and the person mannequin (FR-004-51, FR-004-24, FR-004-25).

Every machine file is an articulation root over one rigid body per part of the asset specification (an `Xform` at the
joint pivot with `MassAPI`, a hidden `guide` collision box and the visible pieces of the part as child meshes) and the
joint tree of the specification; every mesh has one `class` and one `part` label and is bound to a `UsdPreviewSurface`
material of the file's `Looks` scope (paint, rubber, steel, glass, skin or fabric).
"""

from __future__ import annotations

from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pitstudio_studio.scene.assets import machines
from pitstudio_studio.scene.assets.geometry import Piece, bounds
from pitstudio_studio.scene.normals import author_normals

KINDS = ("paint", "rubber", "steel", "glass", "skin", "fabric")
# kind -> (rgb, roughness, metallic); a variant (the text after the first underscore) overrides the colour
_KIND = {
    "paint": ((0.86, 0.58, 0.06), 0.45, 0.0),
    "rubber": ((0.03, 0.03, 0.03), 0.9, 0.0),
    "steel": ((0.46, 0.47, 0.49), 0.45, 0.8),
    "glass": ((0.04, 0.08, 0.11), 0.05, 0.0),
    "skin": ((0.62, 0.45, 0.35), 0.6, 0.0),
    "fabric": ((0.28, 0.32, 0.4), 0.9, 0.0),
}
_VARIANT = {
    "paint_frame": (0.22, 0.22, 0.24), "paint_diff": (0.2, 0.2, 0.22), "paint_tank": (0.25, 0.25, 0.27),
    "paint_counterweight": (0.3, 0.3, 0.32), "paint_roof": (0.78, 0.78, 0.78), "paint_mirror": (0.08, 0.08, 0.08),
    "paint_hat": (0.92, 0.92, 0.9), "paint_white": (0.9, 0.9, 0.88), "paint_deck": (0.3, 0.3, 0.3),
    "paint_rim": (0.8, 0.52, 0.05), "paint_rib": (0.75, 0.48, 0.05),
    "steel_track": (0.18, 0.18, 0.19), "steel_grille": (0.08, 0.08, 0.08), "steel_floor": (0.36, 0.33, 0.3),
    "steel_dipper": (0.3, 0.3, 0.32), "steel_tooth": (0.14, 0.14, 0.15), "steel_door": (0.28, 0.28, 0.3),
    "steel_bumper": (0.2, 0.2, 0.21), "steel_hoist": (0.65, 0.66, 0.68), "steel_rim": (0.55, 0.56, 0.58),
    "steel_cap": (0.6, 0.6, 0.62), "steel_walkway": (0.35, 0.35, 0.37), "steel_rail": (0.8, 0.5, 0.05),
    "glass_lamp": (0.9, 0.88, 0.7), "rubber_boot": (0.1, 0.07, 0.05), "skin_hand": (0.6, 0.43, 0.33),
    "fabric_hivis": (0.78, 0.92, 0.02), "fabric_reflective": (0.82, 0.82, 0.8), "fabric_trousers": (0.14, 0.18, 0.28),
    "fabric_shirt": (0.3, 0.33, 0.38),
}  # fmt: skip


def material_params(name: str) -> tuple[tuple[float, float, float], float, float]:
    """(rgb, roughness, metallic) of a material name `<kind>` or `<kind>_<variant>`."""
    kind = name.split("_")[0]
    if kind not in KINDS:
        raise ValueError(f"material {name!r}: kind {kind!r} is not one of {KINDS}")
    rgb, roughness, metallic = _KIND[kind]
    return _VARIANT.get(name, rgb), roughness, metallic


def _looks(stage: Any, root: str, names: set[str]) -> dict[str, Any]:
    from pxr import Gf, Sdf, UsdGeom, UsdShade

    UsdGeom.Scope.Define(stage, f"{root}/Looks")
    out = {}
    for name in sorted(names):
        rgb, roughness, metallic = material_params(name)
        mat = UsdShade.Material.Define(stage, f"{root}/Looks/{name}")
        shader = UsdShade.Shader.Define(stage, f"{root}/Looks/{name}/Surface")
        shader.CreateIdAttr("UsdPreviewSurface")
        shader.CreateInput("diffuseColor", Sdf.ValueTypeNames.Color3f).Set(Gf.Vec3f(*rgb))
        shader.CreateInput("roughness", Sdf.ValueTypeNames.Float).Set(float(roughness))
        shader.CreateInput("metallic", Sdf.ValueTypeNames.Float).Set(float(metallic))
        shader.CreateOutput("surface", Sdf.ValueTypeNames.Token)
        mat.CreateSurfaceOutput().ConnectToSource(shader.GetOutput("surface"))
        out[name] = mat
    return out


def _mesh(
    stage: Any,
    path: str,
    piece: Piece,
    origin: tuple[float, float, float],
    class_label: str,
    materials: Mapping[str, Any],
) -> Any:
    from pxr import Gf, UsdGeom, UsdShade, Vt

    from pitstudio_studio.scene.assets.build import _label

    points = piece.points - origin
    mesh = UsdGeom.Mesh.Define(stage, path)
    mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(points.astype("float32")))
    mesh.CreateFaceVertexCountsAttr(list(piece.counts))
    mesh.CreateFaceVertexIndicesAttr(list(piece.indices))
    mesh.CreateSubdivisionSchemeAttr("none")
    author_normals(mesh, points, piece.counts, piece.indices, interpolation="uniform")
    lo, hi = points.min(axis=0), points.max(axis=0)
    mesh.CreateExtentAttr([Gf.Vec3f(*map(float, lo)), Gf.Vec3f(*map(float, hi))])
    prim = mesh.GetPrim()
    _label(prim, "class", class_label)
    _label(prim, "part", piece.part)
    UsdShade.MaterialBindingAPI.Apply(prim).Bind(materials[piece.material])
    return mesh


def write_procedural_machine(
    path: Path, asset: Mapping[str, Any], parts: list[Mapping[str, Any]], bodies: Mapping[str, machines.Body]
) -> None:
    """Write the machine file of `asset`: its bodies at their pivots, their colliders, pieces and the joint tree."""
    from pxr import Gf, Sdf, UsdGeom, UsdPhysics

    from pitstudio_studio.scene.assets.build import _label, _new_stage, prim_name

    stage = _new_stage(path)
    root_name = prim_name(asset["id"])
    root = UsdGeom.Xform.Define(stage, f"/{root_name}")
    stage.SetDefaultPrim(root.GetPrim())
    UsdPhysics.ArticulationRootAPI.Apply(root.GetPrim())
    root.GetPrim().CreateAttribute("pitstudio:provenance", Sdf.ValueTypeNames.String).Set("procedural-machine")
    by_id = {p["id"]: p for p in parts}
    materials = _looks(stage, f"/{root_name}", {piece.material for pid in by_id for piece in bodies[pid].pieces})
    paths = {pid: f"/{root_name}/{prim_name(pid)}" for pid in by_id}
    for pid in sorted(by_id, key=prim_name):
        part, body = by_id[pid], bodies[pid]
        origin = tuple(float(v) for v in body.origin)
        xform = UsdGeom.Xform.Define(stage, paths[pid])
        xform.AddTranslateOp().Set(Gf.Vec3d(*origin))
        prim = xform.GetPrim()
        UsdPhysics.RigidBodyAPI.Apply(prim)
        UsdPhysics.MassAPI.Apply(prim).CreateMassAttr(float(part["mass_kg"]))
        _label(prim, "class", asset["class_label"])
        _label(prim, "part", part["part"])
        lo, hi = bounds(body.pieces)
        centre, size = (lo + hi) / 2.0 - origin, hi - lo
        guide = UsdGeom.Mesh.Define(stage, f"{paths[pid]}/Collider")
        gx, gy, gz = (s / 2.0 for s in size)
        corners = [
            (centre[0] + sx * gx, centre[1] + sy * gy, centre[2] + sz * gz)
            for sz in (-1, 1)
            for sy in (-1, 1)
            for sx in (-1, 1)
        ]
        guide.CreatePointsAttr([Gf.Vec3f(*map(float, c)) for c in corners])
        guide.CreateFaceVertexCountsAttr([4] * 6)
        guide.CreateFaceVertexIndicesAttr([0, 2, 3, 1, 4, 5, 7, 6, 0, 1, 5, 4, 2, 6, 7, 3, 0, 4, 6, 2, 1, 3, 7, 5])
        guide.CreateSubdivisionSchemeAttr("none")
        author_normals(
            guide,
            corners,
            [4] * 6,
            [0, 2, 3, 1, 4, 5, 7, 6, 0, 1, 5, 4, 2, 6, 7, 3, 0, 4, 6, 2, 1, 3, 7, 5],
            interpolation="uniform",
        )
        guide.CreateExtentAttr(
            [
                Gf.Vec3f(*map(float, (centre[i] - size[i] / 2.0 for i in range(3)))),
                Gf.Vec3f(*map(float, (centre[i] + size[i] / 2.0 for i in range(3)))),
            ]
        )
        guide.CreatePurposeAttr(UsdGeom.Tokens.guide)
        gprim = guide.GetPrim()
        UsdPhysics.CollisionAPI.Apply(gprim)
        UsdPhysics.MeshCollisionAPI.Apply(gprim).CreateApproximationAttr("convexHull")
        _label(gprim, "class", asset["class_label"])
        _label(gprim, "part", part["part"])
        for piece in body.pieces:
            _mesh(stage, f"{paths[pid]}/{prim_name(piece.name)}", piece, origin, asset["class_label"], materials)
    UsdGeom.Scope.Define(stage, f"/{root_name}/Joints")
    for pid in sorted((p for p in by_id if by_id[p].get("parent") is not None), key=prim_name):
        part = by_id[pid]
        jpath = f"/{root_name}/Joints/{prim_name(pid)}"
        revolute = part.get("joint", "revolute") == "revolute"
        joint = (
            UsdPhysics.RevoluteJoint.Define(stage, jpath)
            if revolute
            else UsdPhysics.PrismaticJoint.Define(stage, jpath)
        )
        joint.CreateBody0Rel().SetTargets([Sdf.Path(paths[part["parent"]])])
        joint.CreateBody1Rel().SetTargets([Sdf.Path(paths[pid])])
        axis = part.get("axis", "Y")
        joint.CreateAxisAttr(axis)
        lo_v, hi_v = (part["lower_deg"], part["upper_deg"]) if revolute else (part["lower_m"], part["upper_m"])
        joint.CreateLowerLimitAttr(float(lo_v))
        joint.CreateUpperLimitAttr(float(hi_v))
        parent_origin, own_origin = bodies[part["parent"]].origin, bodies[pid].origin
        joint.CreateLocalPos0Attr(Gf.Vec3f(*(float(o - q) for o, q in zip(own_origin, parent_origin, strict=True))))
        joint.CreateLocalPos1Attr(Gf.Vec3f(0.0, 0.0, 0.0))
        joint.CreateExcludeFromArticulationAttr(bool(part.get("exclude_from_articulation", False)))
        dof = f"rot{axis}" if revolute else f"trans{axis}"
        UsdPhysics.LimitAPI.Apply(joint.GetPrim(), dof)
        UsdPhysics.DriveAPI.Apply(joint.GetPrim(), "angular" if revolute else "linear")
    stage.GetRootLayer().Save()


PERSON_ASSET_ID = "person-mannequin"


def write_person_asset(path: Path) -> None:
    """The mannequin file: head, neck, hard hat, torso, high-visibility vest, two arms and two legs (no physics)."""
    from pxr import Sdf, UsdGeom

    from pitstudio_studio.scene.assets.build import _new_stage, prim_name

    stage = _new_stage(path)
    root = UsdGeom.Xform.Define(stage, "/PersonMannequin")
    stage.SetDefaultPrim(root.GetPrim())
    root.GetPrim().CreateAttribute("pitstudio:provenance", Sdf.ValueTypeNames.String).Set("procedural-mannequin")
    pieces = machines.person_centred()
    materials = _looks(stage, "/PersonMannequin", {p.material for p in pieces})
    for piece in pieces:
        _mesh(stage, f"/PersonMannequin/{prim_name(piece.name)}", piece, (0.0, 0.0, 0.0), "person", materials)
    stage.GetRootLayer().Save()
