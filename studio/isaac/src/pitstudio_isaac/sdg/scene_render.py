"""`st55_sdg` renderer of the spec 004 scene: one Isaac Sim application for the whole job, one frame per table row.

`SdgRenderer` opens the composed scene (`root.usda` of `st45_validate/scene`: terrain, pit design, lights), deactivates
the fixture fleet and people of the scene, and for every parameter-table row (see `pitstudio_studio.sdg.table`) sets the
sun, the dome, the dust fog, the rock textures, the objects, the distractors and the camera, then renders RGB, depth
(distance to the image plane) and instance segmentation. Semantic mask, tight boxes, polygons and visible pixels are
derived from the one instance mask, so they cannot disagree. Everything that needs Isaac Sim is imported inside the
methods; the pure helpers (`light_for_row`, `frustum_flags`, `annotate`) run on the CPU and are tested there.
"""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_isaac.sdg.masks import external_polygons
from pitstudio_isaac.sdg.render import CATEGORIES, CATEGORY_IDS, _entry, _start_isaac

NOMINAL_SUN_INTENSITY = 3000.0  # the sun of the scene's lights layer
NOMINAL_DOME_INTENSITY = 800.0
STRUCTURED_SUN_TEMPERATURE_K = 5800.0
DUST_COLOUR = (0.55, 0.49, 0.40)
MIN_INSTANCE_PX = 16  # smaller instances are counted in the frame state but get no annotation
APERTURE_MM = 20.955
OBJECT_ROOT = "/World/Sdg"
CAMERA_PATH = "/World/SdgCamera"
MATERIAL_SCOPE = "/World/SdgMaterials"
DEACTIVATE = ("/World/Fleet", "/World/People")
TEXTURE_SCALE = 1.0 / 8.0  # triplanar world-space mapping: one texture tile per 8 m
# The composed scene binds no material (its materials layer is not in the layer stack), so the job binds two
# triplanar textured materials: `rock` on the terrain, benches and berms, `gravel` on the roads, ramp and windrows.
BINDINGS = {
    "rock": ("/World/Terrain", "/World/Design/Benches", "/World/Design/Berms"),
    "gravel": ("/World/Design/HaulRoads", "/World/Design/Ramp", "/World/Design/Windrows"),
}


# ----------------------------------------------------------------------------------------------------------------
# pure helpers
# ----------------------------------------------------------------------------------------------------------------
def light_for_row(row: Mapping[str, Any]) -> dict[str, Any]:
    """Sun direction (toward the sun), intensities, colour temperature and fog extinction (1/m) of a row."""
    dr = row["dr"]
    el, az = math.radians(dr["sun_elevation_deg"]), math.radians(dr["sun_azimuth_deg"])
    direction = (math.cos(el) * math.sin(az), math.cos(el) * math.cos(az), math.sin(el))
    if row["arm"] == "structured":
        return {
            "direction": direction,
            "sun_intensity": NOMINAL_SUN_INTENSITY,
            "dome_intensity": NOMINAL_DOME_INTENSITY,
            "temperature_k": STRUCTURED_SUN_TEMPERATURE_K,
            "fog_per_m": float(dr["dust_extinction_per_km"]) / 1000.0,
        }
    factor = float(dr["light_intensity_factor"])
    return {
        "direction": direction,
        "sun_intensity": NOMINAL_SUN_INTENSITY * factor,
        "dome_intensity": NOMINAL_DOME_INTENSITY * factor,
        "temperature_k": float(dr["colour_temperature_k"]),
        "fog_per_m": 0.0,
    }


def box_corners(centre_xy: Sequence[float], z_base: float, yaw_deg: float, length: float, width: float, height: float):
    """The eight corners (x, y, z) of an object's oriented bounding box (base at `z_base`)."""
    c, s = math.cos(math.radians(yaw_deg)), math.sin(math.radians(yaw_deg))
    out = []
    for sx in (-0.5, 0.5):
        for sy in (-0.5, 0.5):
            for z in (0.0, height):
                lx, ly = sx * length, sy * width
                out.append((centre_xy[0] + c * lx - s * ly, centre_xy[1] + s * lx + c * ly, z_base + z))
    return out


def in_frustum(camera: Mapping[str, Any], points: Sequence[Sequence[float]]) -> bool:
    """True when any point lies in front of the camera and projects inside the image (pinhole)."""
    pos = np.asarray(camera["position_m"], dtype=np.float64)
    fwd = np.asarray(camera["forward"], dtype=np.float64)
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, np.asarray(camera["up"], dtype=np.float64))
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    for p in points:
        d = np.asarray(p, dtype=np.float64) - pos
        depth = float(d @ fwd)
        if depth <= 0.0:
            continue
        u = camera["cx_px"] + camera["fx_px"] * float(d @ right) / depth
        v = camera["cy_px"] - camera["fy_px"] * float(d @ up) / depth
        if 0.0 <= u < camera["width_px"] and 0.0 <= v < camera["height_px"]:
            return True
    return False


def frustum_flags(row: Mapping[str, Any]) -> dict[str, bool]:
    """`in_frustum` of every object of a row, by prim id."""
    flags = {}
    for obj, p in zip(row["objects"], row["dr"]["placements"], strict=True):
        corners = box_corners(
            (p["x_m"], p["y_m"]), p["z_m"], p["yaw_deg"], obj["length_m"], obj["width_m"], obj["height_m"]
        )
        flags[obj["prim_id"]] = in_frustum(row["camera"], corners)
    return flags


def annotate(
    instance_ids: np.ndarray, id_to_path: Mapping[int, str], objects: Sequence[Mapping[str, Any]], image_id: int = 1
) -> tuple[np.ndarray, list[dict[str, Any]], dict[str, int]]:
    """Semantic mask (class ids), COCO annotations and visible pixels per object from one instance-id image.

    An instance belongs to an object when its prim path is the object's prim or below it. Annotations are made for
    objects with at least `MIN_INSTANCE_PX` visible pixels: tight box (x, y, w, h), polygons of the outer outlines,
    area = visible pixel count.
    """
    height, width = instance_ids.shape[:2]
    semantic = np.zeros((height, width), dtype=np.uint8)
    annotations: list[dict[str, Any]] = []
    visible: dict[str, int] = {}
    ids = instance_ids.reshape(height, width)
    for obj in objects:
        prim = obj["prim_id"]
        owned = [int(i) for i, path in id_to_path.items() if path == prim or str(path).startswith(prim + "/")]
        mask = np.isin(ids, owned) if owned else np.zeros((height, width), dtype=bool)
        count = int(mask.sum())
        visible[prim] = count
        if count == 0:
            continue
        semantic[mask] = CATEGORY_IDS[obj["class"]]
        if count < MIN_INSTANCE_PX:
            continue
        ys, xs = np.nonzero(mask)
        x0, y0, x1, y1 = int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1
        polygons = external_polygons(mask) or [[x0, y0, x1, y0, x1, y1, x0, y1]]
        annotations.append(
            {
                "id": len(annotations) + 1,
                "image_id": image_id,
                "category_id": CATEGORY_IDS[obj["class"]],
                "bbox": [float(x0), float(y0), float(x1 - x0), float(y1 - y0)],
                "segmentation": polygons,
                "area": float(count),
                "iscrowd": 0,
            }
        )
    return semantic, annotations, visible


def write_frame(
    row: Mapping[str, Any],
    out: Path,
    rgb: np.ndarray,
    depth: np.ndarray,
    instance_ids: np.ndarray,
    id_to_path: Mapping[int, str],
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Write the files of one frame below `out` and return its DC-009-01 record and what was measured.

    The same function serves the Isaac renderer and the CPU renderer of the dry run, so the dry run exercises the
    file layout, the COCO file, the digests and the record exactly as the real run writes them.
    """
    from PIL import Image

    dr = row["dr"]
    width, height = int(row["camera"]["width_px"]), int(row["camera"]["height_px"])
    for sub in ("rgb", "semantic", "depth"):
        (out / sub).mkdir(parents=True, exist_ok=True)
    Image.fromarray(rgb).save(out / "rgb" / "000000.png")
    np.save(out / "depth" / "000000.npy", depth)
    semantic, annotations, visible = annotate(instance_ids, id_to_path, row["objects"])
    Image.fromarray(semantic).save(out / "semantic" / "000000.png")
    coco = {
        "images": [{"id": 1, "file_name": "rgb/000000.png", "width": width, "height": height}],
        "annotations": annotations,
        "categories": CATEGORIES,
    }
    (out / "coco_instances.json").write_text(json.dumps(coco), encoding="utf-8")
    size = {"width_px": width, "height_px": height}
    camera = row["camera"]
    record = {
        "record_id": row["record_id"],
        "synthetic": True,
        "family": row["family"],
        "arm": row["arm"],
        "split": row["split"],
        "scenario_seed": row["scenario_seed"],
        "layout_id": row["layout_id"],
        "image": _entry(out, "rgb/000000.png", **size, format="png", colour_space="srgb"),
        "coco": _entry(out, "coco_instances.json"),
        "coco_image_id": 1,
        "semantic_mask": _entry(out, "semantic/000000.png", **size, format="png"),
        "depth": _entry(
            out, "depth/000000.npy", **size, format="npy", dtype="float32", unit="m", quantity="distance-to-image-plane"
        ),
        "intrinsics": {
            "model": "pinhole",
            "fx_px": camera["fx_px"],
            "fy_px": camera["fy_px"],
            "cx_px": camera["cx_px"],
            "cy_px": camera["cy_px"],
        },
        "instance_source": "replicator",
        "dr": dict(dr),
        "licence": {"spdx": "CC-BY-4.0", "licence_class": "own"},
    }
    measured = {
        "visible_px": visible,
        "in_frustum": frustum_flags(row),
        "annotations": len(annotations),
        "depth_finite_fraction": float(np.isfinite(depth).mean()),
        "rgb_std": float(rgb.std()),
    }
    return record, measured


# ----------------------------------------------------------------------------------------------------------------
# Isaac Sim part
# ----------------------------------------------------------------------------------------------------------------
class SdgRenderer:
    """One SimulationApp with the scene loaded; `render_row` renders a parameter-table row below an output folder.

    `_prepare_stage` holds every stage edit that is plain OpenUSD (`pxr`); it is separate from `_start` so that the
    dry run can check the whole stage logic against the real scene without starting Isaac Sim (`stage_selfcheck`).
    """

    def __init__(self, scene_dir: Path, textures: Mapping[str, Path]) -> None:
        self.scene_dir = Path(scene_dir)
        self.textures = dict(textures)
        self._app: Any = None
        self._carb: Any = None
        self._rep: Any = None
        self._annotators: dict[str, Any] = {}
        self._start()

    # -- start-up ------------------------------------------------------------------------------------------------
    def _start(self) -> None:
        self._app = _start_isaac()
        import carb
        import isaacsim.core.experimental.utils.stage as stage_utils
        import omni.replicator.core as rep

        self._rep, self._carb = rep, carb
        rep.orchestrator.set_capture_on_play(False)  # frames are captured by `orchestrator.step`, not by the timeline
        opened, stage = stage_utils.open_stage(str(self.scene_dir / "root.usda"))
        if not opened or stage is None:
            raise RuntimeError(f"cannot open the scene {self.scene_dir / 'root.usda'}")
        for _ in range(60):
            self._app.update()  # let the payloads and the terrain tiles load
        self._prepare_stage(stage)
        self._product = rep.create.render_product(CAMERA_PATH, (1280, 720))
        for name, init in (
            ("rgb", None),
            ("distance_to_image_plane", None),
            ("instance_segmentation", {"colorize": False}),
        ):
            annotator = (
                rep.AnnotatorRegistry.get_annotator(name, init_params=init)
                if init
                else rep.AnnotatorRegistry.get_annotator(name)
            )
            annotator.attach([self._product])
            self._annotators[name] = annotator

    def _prepare_stage(self, stage: Any) -> None:
        """Deactivate the fixture fleet and people; take the sun; add the dome, camera and textured materials."""
        from pxr import Gf, UsdGeom, UsdLux, UsdShade

        self._stage = stage
        for path in DEACTIVATE:
            prim = stage.GetPrimAtPath(path)
            if prim.IsValid():
                prim.SetActive(False)
        if not stage.GetPrimAtPath("/World/Lights/Sun").IsValid():
            raise RuntimeError("the scene has no /World/Lights/Sun")
        self._sun = UsdLux.DistantLight(stage.GetPrimAtPath("/World/Lights/Sun"))
        xform = UsdGeom.Xformable(self._sun.GetPrim())
        xform.ClearXformOpOrder()
        self._sun_orient = xform.AddOrientOp(UsdGeom.XformOp.PrecisionDouble)
        self._dome = UsdLux.DomeLight.Define(stage, "/World/Lights/Sky")
        UsdGeom.Scope.Define(stage, MATERIAL_SCOPE)
        cam = UsdGeom.Camera.Define(stage, CAMERA_PATH)
        cam.CreateClippingRangeAttr(Gf.Vec2f(0.3, 4000.0))
        self._camera = cam
        self._camera_op = UsdGeom.Xformable(cam.GetPrim()).AddTransformOp()
        self._texture_inputs: dict[str, Any] = {}
        for slot, targets in BINDINGS.items():
            material, shader = self._pbr_material(f"{MATERIAL_SCOPE}/{slot}", None)
            self._texture_inputs[slot] = shader.GetInput("diffuse_texture")
            for target in targets:
                prim = stage.GetPrimAtPath(target)
                if not prim.IsValid():
                    raise RuntimeError(f"the scene has no {target} to bind the {slot} material to")
                UsdShade.MaterialBindingAPI.Apply(prim).Bind(material)

    def close(self) -> None:
        if self._app is not None:
            self._app.close()
            self._app = None

    # -- stage edits (OpenUSD) -----------------------------------------------------------------------------------
    def _pbr_material(self, path: str, texture_id: str | None) -> tuple[Any, Any]:
        """An OmniPBR material with a triplanar world-space diffuse texture (no UVs needed): (material, shader)."""
        from pxr import Gf, Sdf, UsdShade

        material = UsdShade.Material.Define(self._stage, path)
        shader = UsdShade.Shader.Define(self._stage, f"{path}/Shader")
        shader.SetSourceAsset(Sdf.AssetPath("OmniPBR.mdl"), "mdl")
        shader.SetSourceAssetSubIdentifier("OmniPBR", "mdl")
        texture = shader.CreateInput("diffuse_texture", Sdf.ValueTypeNames.Asset)
        if texture_id is not None:
            texture.Set(Sdf.AssetPath(self.textures[texture_id].as_posix()))
        shader.CreateInput("project_uvw", Sdf.ValueTypeNames.Bool).Set(True)
        shader.CreateInput("world_or_object", Sdf.ValueTypeNames.Bool).Set(True)
        shader.CreateInput("texture_scale", Sdf.ValueTypeNames.Float2).Set(Gf.Vec2f(TEXTURE_SCALE, TEXTURE_SCALE))
        shader.CreateInput("reflection_roughness_constant", Sdf.ValueTypeNames.Float).Set(0.8)
        shader.CreateOutput("out", Sdf.ValueTypeNames.Token)
        material.CreateSurfaceOutput("mdl").ConnectToSource(shader.ConnectableAPI(), "out")
        return material, shader

    def _set_texture(self, slot: str, texture_id: str) -> None:
        from pxr import Sdf

        self._texture_inputs[slot].Set(Sdf.AssetPath(self.textures[texture_id].as_posix()))

    def _label(self, prim: Any, label: str) -> None:
        from pxr import UsdSemantics

        UsdSemantics.LabelsAPI.Apply(prim, "class").CreateLabelsAttr().Set([label])

    def _box(self, path: str, size: Sequence[float], centre: Sequence[float], colour: Sequence[float]) -> Any:
        """A box mesh (size x, y, z; `centre` in the parent frame) with a display colour."""
        from pxr import Gf, UsdGeom, Vt

        mesh = UsdGeom.Mesh.Define(self._stage, path)
        hx, hy, hz = (v / 2.0 for v in size)
        pts = [(sx * hx, sy * hy, sz * hz) for sx in (-1, 1) for sy in (-1, 1) for sz in (-1, 1)]
        mesh.GetPointsAttr().Set(Vt.Vec3fArray([Gf.Vec3f(*p) for p in pts]))
        mesh.GetFaceVertexCountsAttr().Set([4] * 6)
        mesh.GetFaceVertexIndicesAttr().Set([0, 1, 3, 2, 4, 6, 7, 5, 0, 4, 5, 1, 2, 3, 7, 6, 0, 2, 6, 4, 1, 5, 7, 3])
        mesh.GetDisplayColorAttr().Set([Gf.Vec3f(*colour)])
        UsdGeom.XformCommonAPI(mesh).SetTranslate(Gf.Vec3d(*centre))
        return mesh

    def _build_object(self, obj: Mapping[str, Any], placement: Mapping[str, Any]) -> None:
        from pxr import Gf, UsdGeom

        path = obj["prim_id"]
        root = UsdGeom.Xform.Define(self._stage, path)
        api = UsdGeom.XformCommonAPI(root)
        api.SetTranslate(Gf.Vec3d(placement["x_m"], placement["y_m"], placement["z_m"]))
        api.SetRotate(Gf.Vec3f(0.0, 0.0, float(placement["yaw_deg"])), UsdGeom.XformCommonAPI.RotationOrderXYZ)
        cls = obj["class"]
        length, width, height = obj["length_m"], obj["width_m"], obj["height_m"]
        if cls == "haul_truck":
            prim = self._stage.GetPrimAtPath(path)
            prim.GetReferences().AddReference(str(self.scene_dir / "assets" / "haul-truck-220t.usda"))
            return  # the asset carries its own class labels
        if cls == "person":
            capsule = UsdGeom.Capsule.Define(self._stage, f"{path}/Body")
            capsule.GetAxisAttr().Set("Z")
            capsule.GetHeightAttr().Set(0.9)
            capsule.GetRadiusAttr().Set(0.22)
            UsdGeom.XformCommonAPI(capsule).SetTranslate(Gf.Vec3d(0, 0, 0.85))
            head = UsdGeom.Sphere.Define(self._stage, f"{path}/Head")
            head.GetRadiusAttr().Set(0.12)
            UsdGeom.XformCommonAPI(head).SetTranslate(Gf.Vec3d(0, 0, 1.63))
            for child in (capsule.GetPrim(), head.GetPrim()):
                self._label(child, "person")
            return
        if cls == "shovel":
            house = (length * 0.65, width * 0.9, height - 3.0)
            parts = [
                ("Tracks", (length, width, 3.0), (0, 0, 1.5), (0.35, 0.35, 0.33)),
                ("House", house, (-1.0, 0, 3.0 + house[2] / 2), (0.85, 0.65, 0.1)),
            ]
        elif cls == "light_vehicle":
            cabin = (length * 0.45, width * 0.9, height - 1.3)
            parts = [
                ("Body", (length, width, 1.1), (0, 0, 0.75), (0.9, 0.9, 0.9)),
                ("Cabin", cabin, (-0.3, 0, 1.3 + cabin[2] / 2), (0.75, 0.75, 0.8)),
            ]
        else:
            raise ValueError(f"unknown class {cls!r}")
        for name, size, centre, colour in parts:
            self._label(self._box(f"{path}/{name}", size, centre, colour).GetPrim(), cls)

    def _clear_frame(self) -> None:
        from pxr import UsdGeom

        if self._stage.GetPrimAtPath(OBJECT_ROOT).IsValid():
            self._stage.RemovePrim(OBJECT_ROOT)
        UsdGeom.Xform.Define(self._stage, OBJECT_ROOT)
        for child in list(self._stage.GetPrimAtPath(MATERIAL_SCOPE).GetChildren()):
            if child.GetName() not in BINDINGS:
                self._stage.RemovePrim(child.GetPath())

    def _place_distractors(self, row: Mapping[str, Any]) -> None:
        from pxr import UsdShade

        texture_ids = row["dr"]["texture_ids"]
        for k, d in enumerate(row["distractors"]):
            texture = texture_ids[(2 + k) % len(texture_ids)]
            material, _ = self._pbr_material(f"{MATERIAL_SCOPE}/Distractor_{k:02d}", texture)
            mesh = self._box(d["prim_id"], [d["size_m"]] * 3, d["centre_m"], d["colour_rgb"])
            UsdShade.MaterialBindingAPI.Apply(mesh.GetPrim()).Bind(material)

    def _apply_light(self, light: Mapping[str, Any]) -> None:
        from pxr import Gf

        d = Gf.Vec3d(*light["direction"])
        rotation = Gf.Rotation(Gf.Vec3d(0.0, 0.0, -1.0), -d)  # a distant light shines along its local -Z
        self._sun_orient.Set(rotation.GetQuat())
        self._sun.GetIntensityAttr().Set(float(light["sun_intensity"]))
        self._sun.GetEnableColorTemperatureAttr().Set(True)
        self._sun.GetColorTemperatureAttr().Set(float(light["temperature_k"]))
        self._dome.GetIntensityAttr().Set(float(light["dome_intensity"]))
        self._dome.GetEnableColorTemperatureAttr().Set(True)
        self._dome.GetColorTemperatureAttr().Set(float(light["temperature_k"]))
        if self._carb is None:
            return  # the stage self-check has no renderer settings
        settings = self._carb.settings.get_settings()
        fog = float(light["fog_per_m"])
        settings.set("/rtx/fog/enabled", fog > 0.0)
        if fog > 0.0:
            settings.set("/rtx/fog/fogDensity", fog)
            settings.set("/rtx/fog/color", DUST_COLOUR)

    def _apply_camera(self, camera: Mapping[str, Any]) -> None:
        from pxr import Gf

        eye = Gf.Vec3d(*camera["position_m"])
        centre = eye + Gf.Vec3d(*camera["forward"])
        view = Gf.Matrix4d().SetLookAt(eye, centre, Gf.Vec3d(*camera["up"]))
        self._camera_op.Set(view.GetInverse())
        width, height = int(camera["width_px"]), int(camera["height_px"])
        focal = camera["fx_px"] * APERTURE_MM / width
        self._camera.GetFocalLengthAttr().Set(float(focal))
        self._camera.GetHorizontalApertureAttr().Set(APERTURE_MM)
        self._camera.GetVerticalApertureAttr().Set(APERTURE_MM * height / width)

    def _compose_frame(self, row: Mapping[str, Any]) -> None:
        """Every stage edit of a row: textures, objects, distractors, light, camera."""
        dr = row["dr"]
        self._clear_frame()
        ids = dr["rock_texture_ids"] if row["arm"] == "structured" else dr["texture_ids"]
        self._set_texture("rock", ids[0])
        self._set_texture("gravel", ids[1 % len(ids)])
        for obj, placement in zip(row["objects"], dr["placements"], strict=True):
            self._build_object(obj, placement)
        if row["distractors"]:
            self._place_distractors(row)
        self._apply_light(light_for_row(row))
        self._apply_camera(row["camera"])

    def render_row(self, row: Mapping[str, Any], out_dir: Path) -> tuple[dict[str, Any], dict[str, Any]]:
        """Render one row below `out_dir`: its DC-009-01 record (paths relative to `out_dir`) and what was measured."""
        self._compose_frame(row)
        self._rep.orchestrator.step(delta_time=0.0, rt_subframes=16)
        height = int(row["camera"]["height_px"])
        width = int(row["camera"]["width_px"])
        rgb = np.asarray(self._annotators["rgb"].get_data())[..., :3].astype(np.uint8)
        depth = np.asarray(self._annotators["distance_to_image_plane"].get_data(), dtype=np.float32)
        seg = self._annotators["instance_segmentation"].get_data()
        id_to_path = {int(k): v for k, v in seg["info"]["idToLabels"].items()}
        return write_frame(row, Path(out_dir), rgb, depth.reshape(height, width), np.asarray(seg["data"]), id_to_path)


def stage_selfcheck(scene_dir: Path, textures: Mapping[str, Path], rows: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    """Run every OpenUSD edit of the renderer on the real scene without Isaac Sim (the dry run's stage-logic check).

    Opens `root.usda` with `pxr`, prepares the stage and composes each row (textures, every class of object,
    distractors, sun, camera) exactly as `render_row` does before it renders; then checks what a render depends on:
    the objects exist with their class labels, the materials are bound and the camera is where the row says.
    """
    from pxr import Usd, UsdGeom, UsdSemantics, UsdShade

    stage = Usd.Stage.Open(str(Path(scene_dir) / "root.usda"))
    renderer = SdgRenderer.__new__(SdgRenderer)
    renderer.scene_dir, renderer.textures, renderer._carb = Path(scene_dir), dict(textures), None
    renderer._prepare_stage(stage)
    counts = {"rows": 0, "objects": 0, "distractors": 0}
    for row in rows:
        renderer._compose_frame(row)
        for obj in row["objects"]:
            prim = stage.GetPrimAtPath(obj["prim_id"])
            if not prim.IsValid():
                raise RuntimeError(f"{row['record_id']}: object {obj['prim_id']} was not authored")
            labelled = [
                p
                for p in Usd.PrimRange(prim)
                if p.HasAPI(UsdSemantics.LabelsAPI, "class")
                and list(UsdSemantics.LabelsAPI(p, "class").GetLabelsAttr().Get()) == [obj["class"]]
            ]
            if not labelled:
                raise RuntimeError(f"{row['record_id']}: {obj['prim_id']} has no `{obj['class']}` class label")
            counts["objects"] += 1
        for d in row["distractors"]:
            if not UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(d["prim_id"])).ComputeBoundMaterial()[0]:
                raise RuntimeError(f"{row['record_id']}: distractor {d['prim_id']} has no material")
            counts["distractors"] += 1
        for slot, targets in BINDINGS.items():
            for target in targets:
                bound = UsdShade.MaterialBindingAPI(stage.GetPrimAtPath(target)).ComputeBoundMaterial()[0]
                if not bound or bound.GetPath().pathString != f"{MATERIAL_SCOPE}/{slot}":
                    raise RuntimeError(f"{target} is not bound to the {slot} material")
        camera_prim = stage.GetPrimAtPath(CAMERA_PATH)
        eye = UsdGeom.Xformable(camera_prim).ComputeLocalToWorldTransform(Usd.TimeCode.Default()).ExtractTranslation()
        if max(abs(eye[i] - row["camera"]["position_m"][i]) for i in range(3)) > 1e-6:
            raise RuntimeError(f"{row['record_id']}: the camera is not at the row's position")
        counts["rows"] += 1
    return counts


def texture_files(textures_root: Path, pool_manifest: Mapping[str, Any]) -> dict[str, Path]:
    """Texture id -> file of the staged CC0 pool (`raw/textures/manifest.json`)."""
    return {t["id"]: Path(textures_root) / t["file"] for t in pool_manifest["textures"]}
