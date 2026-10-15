"""The compose stage `st40_compose`: one root stage with fixed sublayers, variant sets, a manifest and a digest
(FR-004-29 .. 33)."""

from __future__ import annotations

import json
import shutil
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pitstudio_studio.scene import common
from pitstudio_studio.scene.common import DESIGN_LABEL, SceneStageError, StageContext, StageRun

SUBLAYER_ROLES = ("anim", "sensors", "weather", "lights", "fleet", "design", "terrain")  # strongest first
GENERATED_ROLES = ("anim", "sensors", "weather", "lights")
VARIANT_SETS = ("pushback", "scenario", "time_of_day", "weather", "lod")
GRAVITY_MS2 = 9.81


@dataclass
class SceneBuild:
    """A composed scene: the root layer, the manifest (DC-004-02) and the scene digest (DC-004-08)."""

    root: Path
    manifest: dict[str, Any]
    digest: dict[str, Any]
    manifest_path: Path
    digest_path: Path


# ----------------------------------------------------------------------------------------------------------------
# checks on upstream layers (nothing is written before every check passed)
# ----------------------------------------------------------------------------------------------------------------
def _fail(error_class: str, detail: str) -> SceneStageError:
    return SceneStageError(error_class, detail)


def _units_problem(layer: Any) -> str | None:
    root = layer.pseudoRoot
    for key, want in (("upAxis", "Z"), ("metersPerUnit", 1.0), ("kilogramsPerUnit", 1.0)):
        if not root.HasInfo(key):
            return f"{key} is not authored"
        if root.GetInfo(key) != want:
            return f"{key} is {root.GetInfo(key)!r}, expected {want!r}"
    return None


def asset_paths(layer: Any) -> list[tuple[str, str]]:
    """Every asset path of a layer as `(where, value)`: sublayers, references, payloads and asset-typed attributes."""
    from pxr import Sdf

    found: list[tuple[str, str]] = [("subLayers", p) for p in layer.subLayerPaths]

    def visit(path: Any) -> None:
        spec = layer.GetObjectAtPath(path)
        if isinstance(spec, Sdf.PrimSpec):
            for arc, items in (("references", spec.referenceList), ("payloads", spec.payloadList)):
                for listing in (items.explicitItems, items.addedItems, items.prependedItems, items.appendedItems):
                    found.extend((arc, item.assetPath) for item in listing if item.assetPath)
        elif isinstance(spec, Sdf.AttributeSpec):
            values = [spec.default] if spec.default is not None else []
            values.extend(layer.QueryTimeSample(path, t) for t in layer.ListTimeSamplesForPath(path))
            for value in values:
                is_array = hasattr(value, "__iter__") and not isinstance(value, str)
                items = [value] if isinstance(value, Sdf.AssetPath) else (list(value) if is_array else [])
                found.extend((spec.name, v.path) for v in items if isinstance(v, Sdf.AssetPath))

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return [(where, value) for where, value in found if value]


def check_layer(name: str, path: Path, folder: str, *, expect_sha256: str | None = None) -> Any:
    """Open one upstream layer and check its digest, units, axis and asset paths; returns the opened `Sdf.Layer`."""
    from pxr import Sdf

    if not Path(path).is_file():
        raise _fail("compose-invalid", f"layer {name} is missing")
    if expect_sha256 is not None and common.sha256_file(Path(path)) != expect_sha256:
        raise _fail("compose-invalid", f"layer {name} differs from the SHA-256 the upstream stage recorded")
    layer = Sdf.Layer.FindOrOpen(str(path))
    if layer is None:
        raise _fail("compose-invalid", f"layer {name} cannot be opened")
    problem = _units_problem(layer)
    if problem:
        raise _fail("compose-invalid", f"layer {name}: {problem}")
    for where, value in asset_paths(layer):
        why = common.asset_path_problem(value, folder=folder)
        if why:
            raise _fail("path-forbidden", f"layer {name}, {where}: {value!r} is forbidden ({why})")
    return layer


def variant_problems(spec: Mapping[str, Any]) -> list[str]:
    """Variant names of the scene specification outside its closed enumerations."""
    from jsonschema import Draft202012Validator

    validator = Draft202012Validator(
        {"$ref": common.contract_validator("scene-spec").schema["$id"] + "#/$defs/variants"},
        registry=common.contract_registry(),
    )
    names: list[str] = []
    for error in validator.iter_errors(spec["variants"]):
        parts = list(error.absolute_path)
        if len(parts) == 2 and error.validator in ("enum", "pattern", "maxLength"):
            names.append(str(spec["variants"][parts[0]][parts[1]]))
    return names


def _layer_variant_names(layer: Any) -> dict[str, set[str]]:
    from pxr import Sdf

    found: dict[str, set[str]] = {}

    def visit(path: Any) -> None:
        spec = layer.GetObjectAtPath(path)
        if isinstance(spec, Sdf.PrimSpec):
            for set_name, vset in spec.variantSets.items():
                found.setdefault(set_name, set()).update(vset.variants.keys())

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    return found


# ----------------------------------------------------------------------------------------------------------------
# authoring
# ----------------------------------------------------------------------------------------------------------------
def _small_stage(path: Path, group: str, extra: str | None = None) -> None:
    from pxr import Usd, UsdGeom, UsdLux, UsdPhysics

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    stage.SetDefaultPrim(UsdGeom.Xform.Define(stage, "/World").GetPrim())
    UsdGeom.Scope.Define(stage, f"/World/{group}")
    if extra == "sun":
        sun = UsdLux.DistantLight.Define(stage, "/World/Lights/Sun")
        sun.CreateIntensityAttr(3000.0)
    stage.GetRootLayer().Save()


def _strip_lod_selection(path: Path) -> None:
    """Drop the terrain layer's authored default `lod` selection: the root stage's `lod` variant drives the terrain.

    A selection authored in a sublayer is stronger than one authored inside a variant of `/World`, so it would pin the
    terrain to one LOD whatever `/World` selects.
    """
    from pxr import Sdf

    layer = Sdf.Layer.FindOrOpen(str(path))

    def visit(spec_path: Any) -> None:
        if not spec_path.IsPrimPath():
            return
        spec = layer.GetPrimAtPath(spec_path)
        if spec is not None and "lod" in spec.variantSelections:
            del spec.variantSelections["lod"]

    layer.Traverse(Sdf.Path.absoluteRootPath, visit)
    layer.Save()


def _write_root(path: Path, spec: Mapping[str, Any], manifest_id: str, params_sha256: str, terrain_layer: Any) -> None:
    from pxr import Gf, Sdf, Usd, UsdGeom, UsdPhysics

    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z)
    UsdGeom.SetStageMetersPerUnit(stage, 1.0)
    UsdPhysics.SetStageKilogramsPerUnit(stage, 1.0)
    root = stage.GetRootLayer()
    root.subLayerPaths = [f"layers/{role}.usd{'c' if role == 'terrain' else 'a'}" for role in SUBLAYER_ROLES]
    world = UsdGeom.Xform.Define(stage, "/World")
    stage.SetDefaultPrim(world.GetPrim())
    scene = UsdPhysics.Scene.Define(stage, "/World/PhysicsScene")
    scene.CreateGravityDirectionAttr(Gf.Vec3f(0.0, 0.0, -1.0))
    scene.CreateGravityMagnitudeAttr(GRAVITY_MS2)
    terrain_lods = _layer_variant_names(terrain_layer).get("lod", set())
    for set_name in VARIANT_SETS:
        names = spec["variants"][set_name]
        vset = world.GetPrim().GetVariantSets().AddVariantSet(set_name)
        for name in names:
            vset.AddVariant(name)
        for name in names:
            vset.SetVariantSelection(name)
            with vset.GetVariantEditContext():
                if set_name == "lod" and name in terrain_lods:
                    terrain = stage.OverridePrim("/World/Terrain")
                    terrain.GetVariantSet("lod").SetVariantSelection(name)
                else:
                    world.GetPrim().CreateAttribute(f"pitstudio:{set_name}", Sdf.ValueTypeNames.String).Set(name)
        vset.SetVariantSelection(names[0])
    root.customLayerData = {"manifest_id": manifest_id, "sha256_of_params": params_sha256}
    root.Save()


def _label_of(prim: Any, instance: str) -> str | None:
    from pxr import UsdSemantics

    attr = UsdSemantics.LabelsAPI(prim, instance).GetLabelsAttr()
    labels = list(attr.Get() or []) if attr else []
    return str(labels[0]) if labels else None


def build_digest(root: Path, spec: Mapping[str, Any], manifest_id: str, params_sha256: str) -> dict[str, Any]:
    """`scene.digest.json` (DC-004-08): world transforms, counts and labels of every mesh under each `lod` variant."""
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(root))
    world = stage.GetPrimAtPath("/World")
    lods: list[dict[str, Any]] = []
    for lod in spec["variants"]["lod"]:
        world.GetVariantSet("lod").SetVariantSelection(lod)
        prims = []
        for prim in sorted(
            (p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.IsA(UsdGeom.Mesh)), key=lambda p: str(p.GetPath())
        ):
            mesh = UsdGeom.Mesh(prim)
            matrix = UsdGeom.Xformable(prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default())
            entry: dict[str, Any] = {
                "path": str(prim.GetPath()),
                "transform": [float(matrix[i][j]) for i in range(4) for j in range(4)],
                "vertices": len(mesh.GetPointsAttr().Get() or []),
                "faces": len(mesh.GetFaceVertexCountsAttr().Get() or []),
                "class": _label_of(prim, "class") or "",
            }
            part = _label_of(prim, "part")
            if part:
                entry["part"] = part
            prims.append(entry)
        lods.append({"lod": lod, "prims": prims})
    return {
        "schema_version": "1.0",
        "kind": "scene-digest",
        "case": spec["case"],
        "manifest_id": manifest_id,
        "params_sha256": params_sha256,
        "up_axis": "Z",
        "meters_per_unit": 1.0,
        "kilograms_per_unit": 1.0,
        "lods": lods,
    }


def _layer_entry(role: str, scene: Path, rel: str, label: str | None = None) -> dict[str, Any]:
    from pxr import Sdf

    data = (scene / rel).read_bytes()
    layer = Sdf.Layer.FindOrOpen(str(scene / rel))
    entry: dict[str, Any] = {
        "role": role,
        "path": rel,
        "format": "usdc" if rel.endswith(".usdc") else "usda",
        "sha256": common.sha256_bytes(data),
        "bytes": len(data),
        "up_axis": str(layer.pseudoRoot.GetInfo("upAxis")),
        "meters_per_unit": float(layer.pseudoRoot.GetInfo("metersPerUnit")),
        "kilograms_per_unit": float(layer.pseudoRoot.GetInfo("kilogramsPerUnit")),
    }
    if label:
        entry["label"] = label
    return entry


def compose_scene(spec: Mapping[str, Any], upstream: Mapping[str, Any], scene_dir: Path | str) -> SceneBuild:
    """Compose the upstream layers into one scene folder with a root stage, a manifest and a digest.

    `upstream`: `layers` (role to path: `terrain`, `design`, `fleet`), `layer_sha256` (the digests the upstream stages
    recorded), `assets` (machine and material layers), `files` (record files, scene-relative path to source path) and
    `records` (the DC-004-02 `sources`, `inputs`, `terrain`, `design`, `textures`, `people_route` and `site` entries).
    Nothing is written when a check fails; units and axes are never corrected (FR-004-32).
    """
    scene = Path(scene_dir)
    bad = variant_problems(spec)
    if bad:
        raise _fail(
            "compose-invalid", f"variant name(s) {', '.join(sorted(set(bad)))} are outside the closed enumeration"
        )
    layers = {role: Path(upstream["layers"][role]) for role in ("terrain", "design", "fleet")}
    opened = {}
    for role, path in layers.items():
        folder = "layers"
        opened[role] = check_layer(role, path, folder, expect_sha256=upstream["layer_sha256"].get(role))
    for asset in upstream.get("assets", []):
        check_layer(Path(asset).name, Path(asset), "assets")
    allowed = {name: set(vals) for name, vals in spec["variants"].items()}
    for role, layer in opened.items():
        for set_name, names in _layer_variant_names(layer).items():
            extra = sorted(names - allowed.get(set_name, names))
            if extra:
                raise _fail(
                    "compose-invalid",
                    f"layer {role} offers the variant {extra[0]!r} of {set_name} outside the specification",
                )
    params_sha = common.params_sha256(spec)
    manifest_id = f"{spec['case'].lower()}-scene-{params_sha[:12]}"
    scene.mkdir(parents=True, exist_ok=True)
    (scene / "layers").mkdir(exist_ok=True)
    for role, path in layers.items():
        shutil.copyfile(path, scene / "layers" / f"{role}{path.suffix}")
    _strip_lod_selection(scene / "layers" / "terrain.usdc")
    for role in GENERATED_ROLES:
        group = {"anim": "Anim", "sensors": "Sensors", "weather": "Weather", "lights": "Lights"}[role]
        _small_stage(scene / "layers" / f"{role}.usda", group, "sun" if role == "lights" else None)
    asset_rels: list[str] = []
    for asset in sorted(upstream.get("assets", []), key=lambda p: Path(p).name):
        (scene / "assets").mkdir(exist_ok=True)
        shutil.copyfile(asset, scene / "assets" / Path(asset).name)
        asset_rels.append(f"assets/{Path(asset).name}")
        textures = Path(asset).parent / "textures"
        if textures.is_dir():
            shutil.copytree(textures, scene / "assets" / "textures", dirs_exist_ok=True)
    for rel, source in upstream.get("files", {}).items():
        target = scene / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, target)
    root = scene / "root.usda"
    _write_root(root, spec, manifest_id, params_sha, opened["terrain"])
    entries = [_layer_entry("root", scene, "root.usda")]
    for role in SUBLAYER_ROLES:
        rel = f"layers/{role}.usd{'c' if role == 'terrain' else 'a'}"
        entries.append(_layer_entry(role, scene, rel, DESIGN_LABEL if role == "design" else None))
    entries.extend(_layer_entry("asset", scene, rel) for rel in asset_rels)
    records = upstream["records"]
    records = json.loads(json.dumps(records))
    for key in ("grid", "tiles"):
        rel = records["terrain"][key]["path"]
        if (scene / rel).is_file():
            records["terrain"][key]["sha256"] = common.sha256_file(scene / rel)
    for key in ("report", "road_network"):
        rel = records["design"][key]["path"]
        if (scene / rel).is_file():
            records["design"][key]["sha256"] = common.sha256_file(scene / rel)
    manifest: dict[str, Any] = {
        "schema_version": "1.0",
        "kind": "scene-manifest",
        "manifest_id": manifest_id,
        "case": spec["case"],
        "params_sha256": params_sha,
        "seed": spec["seed"],
        "site": records["site"],
        "sources": records["sources"],
        "inputs": records["inputs"],
        "terrain": records["terrain"],
        "design": records["design"],
        "layers": entries,
        "textures": records["textures"],
        "people_route": records["people_route"],
        "variants": {
            name: {"names": list(spec["variants"][name]), "default": spec["variants"][name][0]} for name in VARIANT_SETS
        },
        "validation": {"status": "pending"},
        "fixture": bool(upstream.get("fixture", False) or spec.get("fixture", False)),
    }
    digest = build_digest(root, spec, manifest_id, params_sha)
    digest["fixture"] = manifest["fixture"]
    manifest_path, digest_path = scene / "scene.manifest.json", scene / "scene.digest.json"
    manifest_path.write_text(
        json.dumps(manifest, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8", newline="\n"
    )
    digest_path.write_text(json.dumps(digest, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
    return SceneBuild(root=root, manifest=manifest, digest=digest, manifest_path=manifest_path, digest_path=digest_path)


# ----------------------------------------------------------------------------------------------------------------
# stage
# ----------------------------------------------------------------------------------------------------------------
def upstream_from_results(inputs: Mapping[str, list[dict[str, str]]], roots: list[Path]) -> dict[str, Any]:
    """The `upstream` mapping of `compose_scene` from the stage outputs named `terrain`, `design` and `assets`.

    Each input is the `result.json` of that stage's output folder; its sibling `digests.json` holds the SHA-256 of every
    output the stage recorded.
    """
    from pitstudio_studio.scene.terrain import io as terrain_io

    folders: dict[str, Path] = {}
    digests: dict[str, dict[str, str]] = {}
    for name in ("terrain", "design", "assets"):
        items = inputs.get(name)
        if not items:
            raise SceneStageError("input-corrupt", f"the job has no `{name}` input (the result.json of that stage)")
        result = terrain_io.resolve_input(items[0]["path"], roots=roots, sha256=items[0].get("sha256"))
        folders[name] = result.parent
        digests[name] = json.loads((result.parent / "digests.json").read_text(encoding="utf-8"))
    terrain_records = json.loads((folders["terrain"] / "terrain" / "records.json").read_text(encoding="utf-8"))
    asset_records = json.loads((folders["assets"] / "assets" / "records.json").read_text(encoding="utf-8"))
    design_report = folders["design"] / "design" / "pit-design-report.json"
    road_network = folders["design"] / "design" / "road-network.geojson"
    layers = {
        "terrain": folders["terrain"] / "layers" / "terrain.usdc",
        "design": folders["design"] / "layers" / "design.usda",
        "fleet": folders["assets"] / "layers" / "fleet.usda",
    }
    files: dict[str, Path] = {}
    for rel in digests["terrain"]:
        if rel.startswith("terrain/") and rel != "terrain/records.json":
            files[rel] = folders["terrain"] / rel
    files["design/pit-design-report.json"] = design_report
    files["design/road-network.geojson"] = road_network
    assets = sorted(
        folders["assets"] / rel for rel in digests["assets"] if rel.startswith("assets/") and rel.endswith(".usda")
    )
    records = {
        "sources": terrain_records["sources"],
        "inputs": terrain_records["inputs"],
        "terrain": terrain_records["terrain"],
        "design": {
            "report": {"path": "design/pit-design-report.json", "sha256": common.sha256_file(design_report)},
            "road_network": {"path": "design/road-network.geojson", "sha256": common.sha256_file(road_network)},
            "provenance": "design-code",
        },
        "textures": asset_records["textures"],
        "people_route": asset_records["people_route"],
        "site": terrain_records["site"],
    }
    return {
        "layers": layers,
        "layer_sha256": {
            "terrain": digests["terrain"]["layers/terrain.usdc"],
            "design": digests["design"]["layers/design.usda"],
            "fleet": digests["assets"]["layers/fleet.usda"],
        },
        "assets": assets,
        "files": files,
        "records": records,
        "fixture": bool(terrain_records.get("fixture", False)),
    }


def _body(ctx: StageContext) -> str:
    roots = common.job_roots()
    if not roots:
        raise SceneStageError("input-path", "no store or data root is configured for the job inputs")
    upstream = upstream_from_results(ctx.inputs, roots)
    build = compose_scene(ctx.params, upstream, ctx.work / "scene")
    return f"scene {build.manifest['manifest_id']}"


def run(job: Mapping[str, Any]) -> StageRun:
    """The stage entry `pitstudio_studio.scene.compose`: job spec in, stage result out (see `common.run_stage`)."""
    return common.run_stage(job, _body)
