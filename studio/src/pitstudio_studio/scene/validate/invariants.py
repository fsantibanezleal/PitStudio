"""The scene invariants of FR-004-35, each with its measured value, unit, limit and verdict (DC-004-07 `invariants`)."""

from __future__ import annotations

import json
from collections import deque
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pitstudio_studio.scene import common
from pitstudio_studio.scene.compose.build import asset_paths

SIZE_LIMIT_BYTES = 10_000_000  # NFR-004-05


def _inv(measured: float, unit: str, limit: float, comparison: str) -> dict[str, Any]:
    passed = measured <= limit if comparison == "le" else measured >= limit
    return {"measured": measured, "unit": unit, "limit": limit, "comparison": comparison, "passed": bool(passed)}


def _units_wrong(layer: Any) -> bool:
    root = layer.pseudoRoot
    for key, want in (("upAxis", "Z"), ("metersPerUnit", 1.0), ("kilogramsPerUnit", 1.0)):
        if not root.HasInfo(key) or root.GetInfo(key) != want:
            return True
    return False


def _machine_stats(path: Path) -> tuple[bool, int, bool, int]:
    """For a machine layer: (is a machine, articulation roots, joint graph is a tree, bodies with mass <= 0)."""
    from pxr import Usd, UsdPhysics

    stage = Usd.Stage.Open(str(path))
    prims = list(Usd.PrimRange(stage.GetPseudoRoot()))
    bodies = [p for p in prims if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    roots = [p for p in prims if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
    if not bodies and not roots:
        return False, 0, True, 0
    adjacency: dict[str, set[str]] = {str(b.GetPath()): set() for b in bodies}
    edges = 0
    for prim in prims:
        if not prim.IsA(UsdPhysics.Joint):
            continue
        flag = prim.GetAttribute("physics:excludeFromArticulation")
        if flag.IsValid() and flag.Get():
            continue
        joint = UsdPhysics.Joint(prim)
        b0, b1 = joint.GetBody0Rel().GetTargets(), joint.GetBody1Rel().GetTargets()
        if len(b0) != 1 or len(b1) != 1:
            return True, len(roots), False, 0
        edges += 1
        adjacency.setdefault(str(b0[0]), set()).add(str(b1[0]))
        adjacency.setdefault(str(b1[0]), set()).add(str(b0[0]))
    tree = False
    if adjacency:
        start = next(iter(adjacency))
        seen, queue = {start}, deque([start])
        while queue:
            for nxt in adjacency[queue.popleft()] - seen:
                seen.add(nxt)
                queue.append(nxt)
        tree = edges == len(adjacency) - 1 and len(seen) == len(adjacency)
    bad_mass = 0
    for body in bodies:
        mass = UsdPhysics.MassAPI(body).GetMassAttr().Get()
        bad_mass += 1 if mass is None or not mass > 0 else 0
    return True, len(roots), tree, bad_mass


def _label_stats(root: Path, lods: list[str]) -> tuple[int, int, int]:
    """(geometry prims with exactly one class label, geometry prims, label attributes with time samples)."""
    from pxr import Usd, UsdGeom, UsdSemantics

    stage = Usd.Stage.Open(str(root))
    ok = total = 0
    sampled: set[tuple[str, str]] = set()
    for lod in lods:
        stage.GetPrimAtPath("/World").GetVariantSet("lod").SetVariantSelection(lod)
        for prim in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()):
            for attr in prim.GetAttributes():
                if attr.GetName().startswith("semantics:labels") and attr.GetNumTimeSamples() > 0:
                    sampled.add((str(prim.GetPath()), attr.GetName()))
            if not prim.IsA(UsdGeom.Gprim):
                continue
            total += 1
            label_attr = UsdSemantics.LabelsAPI(prim, "class").GetLabelsAttr()
            labels = list(label_attr.Get() or []) if label_attr else []
            ok += 1 if len(labels) == 1 else 0
    return ok, total, len(sampled)


def _terrain_excess(scene: Path, manifest: Mapping[str, Any], z0: float) -> float:
    """Largest excess (m) of a terrain mesh point's elevation over the source range widened by the tile error."""
    from pxr import Usd, UsdGeom

    grid_attrs = json.loads((scene / manifest["terrain"]["grid"]["path"]).read_text(encoding="utf-8"))["attributes"]
    tiles = json.loads((scene / manifest["terrain"]["tiles"]["path"]).read_text(encoding="utf-8"))
    lo, hi = grid_attrs["source_elevation_range_m"]["min"], grid_attrs["source_elevation_range_m"]["max"]
    by_prim = {t["prim"]: t["max_error_m"] for t in tiles["tiles"]}
    by_lod = {lod["lod"]: lod["max_error_m"] for lod in tiles["lods"]}
    stage = Usd.Stage.Open(str(scene / "layers" / "terrain.usdc"))
    terrain = stage.GetPrimAtPath("/World/Terrain")
    vset = terrain.GetVariantSet("lod")
    worst = 0.0
    for name in vset.GetVariantNames():
        vset.SetVariantSelection(name)
        lod = int(name.removeprefix("lod")) if name.removeprefix("lod").isdigit() else 0
        for prim in Usd.PrimRange(terrain):
            if not prim.IsA(UsdGeom.Mesh):
                continue
            margin = by_prim.get(str(prim.GetPath()), by_lod.get(lod, 0.0))
            points = UsdGeom.Mesh(prim).GetPointsAttr().Get() or []
            for p in points:
                z = float(p[2]) + z0
                worst = max(worst, z - (hi + margin), (lo - margin) - z)
    return max(worst, 0.0)


def compute_invariants(scene_dir: Path | str, spec: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """The 14 invariants of a scene folder written by `compose_scene` (design report and terrain records included)."""
    from pxr import Sdf

    scene = Path(scene_dir)
    manifest = json.loads((scene / "scene.manifest.json").read_text(encoding="utf-8"))
    entries = manifest["layers"]
    design = spec["design"]
    wrong_units = 0
    for entry in entries:
        layer = Sdf.Layer.FindOrOpen(str(scene / entry["path"]))
        wrong_units += 1 if layer is None or _units_wrong(layer) else 0
    ok, total, sampled = _label_stats(scene / "root.usda", list(spec["variants"]["lod"]))
    bad_roots = cyclic = bad_mass = 0
    for entry in entries:
        if entry["role"] != "asset" or entry["format"] != "usda":
            continue
        is_machine, roots, tree, masses = _machine_stats(scene / entry["path"])
        if not is_machine:
            continue
        bad_roots += 1 if roots != 1 else 0
        cyclic += 0 if tree else 1
        bad_mass += masses
    report = json.loads((scene / manifest["design"]["report"]["path"]).read_text(encoding="utf-8"))
    height = float(design["bench_height_m"]["value"])
    angle = float(design["face_angle_deg"]["value"])
    grade = float(design["ramp_grade_pct"]["value"])
    forbidden = 0
    for entry in entries:
        folder = str(Path(entry["path"]).parent.as_posix()).removeprefix(".")
        layer = Sdf.Layer.FindOrOpen(str(scene / entry["path"]))
        forbidden += sum(1 for _, value in asset_paths(layer) if common.asset_path_problem(value, folder=folder))
    small = [(scene / e["path"]).stat().st_size for e in entries if e["format"] == "usda" and e["role"] != "asset"]
    z0 = float(spec["site"]["origin"]["z0_m"])
    windrows = report["windrows"]
    return {
        "layer_units_axis": _inv(wrong_units, "count", 0, "le"),
        "class_label_coverage": _inv(ok / total if total else 1.0, "fraction", 1.0, "ge"),
        "time_sampled_labels": _inv(sampled, "count", 0, "le"),
        "articulation_roots": _inv(bad_roots, "count", 0, "le"),
        "cyclic_joint_graphs": _inv(cyclic, "count", 0, "le"),
        "non_positive_masses": _inv(bad_mass, "count", 0, "le"),
        "bench_height_deviation": _inv(max(abs(b["height_m"] - height) for b in report["benches"]), "m", 0.5, "le"),
        "face_angle_deviation": _inv(
            max(abs(b["face_angle_deg"] - angle) for b in report["benches"]), "deg", 1.0, "le"
        ),
        "ramp_grade_max": _inv(report["ramp"]["max_grade_pct"], "pct", grade + 0.1, "le"),
        "windrow_margin": _inv(windrows["height_m"] - windrows["mid_axle_height_m"], "m", 0, "ge"),
        "terrain_range_excess": _inv(_terrain_excess(scene, manifest, z0), "m", 0, "le"),
        "cut_fill_identity_residual": _inv(report["volumes"]["identity_residual_rel"], "rel", 1e-12, "le"),
        "forbidden_paths": _inv(forbidden, "count", 0, "le"),
        "layer_size_max": _inv(max(small) if small else 0, "bytes", SIZE_LIMIT_BYTES, "le"),
    }
