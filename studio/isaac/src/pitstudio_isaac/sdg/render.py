"""`st55_sdg` frame renderer (FR-009-02): one frame to RGB, semantic mask, depth, COCO and the index record.

Runs in the Isaac Sim environment (Python 3.12) under Replicator; it is local-only and never part of CI (FR-009-41).
The sampling
and the guards live in `pitstudio_studio.sdg` (CPU); this module only renders what they decided. Everything that
needs Isaac Sim is imported inside `render_frame`, so importing the module never starts the application.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import numpy as np

CATEGORY_IDS = {"haul_truck": 1, "shovel": 2, "light_vehicle": 3, "person": 4, "boulder": 5}
CATEGORIES = [{"id": i, "name": n} for n, i in CATEGORY_IDS.items()]


def _entry(root: Path, rel: str, **extra: Any) -> dict[str, Any]:
    data = (root / rel).read_bytes()
    return {"path": rel, "sha256": hashlib.sha256(data).hexdigest(), "size_bytes": len(data), **extra}


def _box_polygon(x: float, y: float, w: float, h: float) -> list[float]:
    return [x, y, x + w, y, x + w, y + h, x, y + h]


def _start_isaac() -> Any:
    try:
        from isaacsim import SimulationApp

        return SimulationApp({"headless": True, "renderer": "RaytracedLighting"})
    except Exception as exc:  # the capability report (FR-009-40) turns this into "not run"
        raise RuntimeError("isaac-sim-not-available") from exc


def render_frame(
    scene: Mapping[str, Any],
    camera: Mapping[str, Any],
    out_dir: Path,
    *,
    family: str,
    arm: str,
    scenario_seed: int,
    layout_id: str,
    split: str,
    dr: Mapping[str, Any],
) -> dict[str, Any]:
    """Render one frame below `out_dir` and return its DC-009-01 record (paths relative to `out_dir`)."""
    app = _start_isaac()
    try:
        import omni.replicator.core as rep
        import omni.usd
        from PIL import Image
        from pxr import Gf, UsdGeom

        out = Path(out_dir)
        for sub in ("rgb", "semantic", "depth"):
            (out / sub).mkdir(parents=True, exist_ok=True)
        ctx = omni.usd.get_context()
        ctx.new_stage()
        stage = ctx.get_stage()
        UsdGeom.SetStageUpAxis(stage, UsdGeom.Tokens.z if scene["up_axis"] == "Z" else UsdGeom.Tokens.y)
        UsdGeom.SetStageMetersPerUnit(stage, float(scene["meters_per_unit"]))
        mpu = float(scene["meters_per_unit"])
        for obj in scene["objects"]:
            if obj["shape"] == "cube":
                prim = UsdGeom.Cube.Define(stage, obj["prim_id"])
                prim.GetSizeAttr().Set(float(obj["size_m"]) / mpu)
                UsdGeom.XformCommonAPI(prim).SetTranslate(Gf.Vec3d(*[c / mpu for c in obj["centre_m"]]))
            elif obj["shape"] == "plane":
                nx, ny, nz = obj["normal"]
                sx, sy = obj["size_m"]
                prim = UsdGeom.Mesh.Define(stage, obj["prim_id"])
                # a quad perpendicular to the normal: two in-plane axes from the normal
                n = np.array([nx, ny, nz], dtype=float)
                a = np.cross(n, [0.0, 0.0, 1.0] if abs(nz) < 0.9 else [1.0, 0.0, 0.0])
                a /= np.linalg.norm(a)
                b = np.cross(n, a)
                c = np.array(obj["centre_m"], dtype=float)
                pts = [c + s1 * sx / 2 * a + s2 * sy / 2 * b for s1, s2 in ((-1, -1), (1, -1), (1, 1), (-1, 1))]
                prim.GetPointsAttr().Set([Gf.Vec3f(*(p / mpu)) for p in pts])
                prim.GetFaceVertexCountsAttr().Set([4])
                prim.GetFaceVertexIndicesAttr().Set([0, 1, 2, 3])
            else:
                raise ValueError(f"unknown shape {obj['shape']!r}")
            with rep.get.prims(path_match=obj["prim_id"]):
                rep.modify.semantics([("class", obj["label"])])
        width, height = int(camera["width_px"]), int(camera["height_px"])
        aperture = 20.955  # mm, USD default horizontal aperture
        focal = camera["fx_px"] * aperture / width
        cam = rep.create.camera(
            position=tuple(camera["position_m"]),
            look_at=tuple(np.array(camera["position_m"]) + np.array(camera["forward"])),
            focal_length=focal,
            horizontal_aperture=aperture,
        )
        product = rep.create.render_product(cam, (width, height))
        rgb = rep.AnnotatorRegistry.get_annotator("rgb")
        depth = rep.AnnotatorRegistry.get_annotator("distance_to_image_plane")
        sem = rep.AnnotatorRegistry.get_annotator("semantic_segmentation", init_params={"colorize": False})
        boxes = rep.AnnotatorRegistry.get_annotator("bounding_box_2d_tight")
        for a in (rgb, depth, sem, boxes):
            a.attach([product])
        rep.orchestrator.step(rt_subframes=8)
        image = np.asarray(rgb.get_data())[..., :3].astype(np.uint8)
        Image.fromarray(image).save(out / "rgb" / "000000.png")
        dmap = np.asarray(depth.get_data(), dtype=np.float32)
        np.save(out / "depth" / "000000.npy", dmap)
        sem_data = sem.get_data()
        labels = {int(k): v["class"] for k, v in sem_data["info"]["idToLabels"].items()}
        mask = np.zeros(sem_data["data"].shape[:2], dtype=np.uint8)
        for sid, name in labels.items():
            if name in CATEGORY_IDS:
                mask[np.asarray(sem_data["data"]).reshape(mask.shape) == sid] = CATEGORY_IDS[name]
        Image.fromarray(mask).save(out / "semantic" / "000000.png")
        annotations = []
        box_data = boxes.get_data()
        box_labels = {int(k): v["class"] for k, v in box_data["info"]["idToLabels"].items()}
        for k, row in enumerate(box_data["data"]):
            name = box_labels.get(int(row["semanticId"]))
            if name not in CATEGORY_IDS:
                continue
            x0, y0, x1, y1 = (float(row[c]) for c in ("x_min", "y_min", "x_max", "y_max"))
            w, h = x1 - x0, y1 - y0
            annotations.append(
                {
                    "id": k + 1,
                    "image_id": 0,
                    "category_id": CATEGORY_IDS[name],
                    "bbox": [x0, y0, w, h],
                    "segmentation": [_box_polygon(x0, y0, w, h)],
                    "area": w * h,
                    "iscrowd": 0,
                }
            )
        coco = {
            "images": [{"id": 0, "file_name": "rgb/000000.png", "width": width, "height": height}],
            "annotations": annotations,
            "categories": CATEGORIES,
        }
        (out / "coco_instances.json").write_text(json.dumps(coco), encoding="utf-8")
        size = {"width_px": width, "height_px": height}
        return {
            "record_id": f"{family}-{arm[0]}-{scenario_seed:06d}",
            "synthetic": True,
            "family": family,
            "arm": arm,
            "split": split,
            "scenario_seed": scenario_seed,
            "layout_id": layout_id,
            "image": _entry(out, "rgb/000000.png", **size, format="png", colour_space="srgb"),
            "coco": _entry(out, "coco_instances.json"),
            "coco_image_id": 0,
            "semantic_mask": _entry(out, "semantic/000000.png", **size, format="png"),
            "depth": _entry(
                out,
                "depth/000000.npy",
                **size,
                format="npy",
                dtype="float32",
                unit="m",
                quantity="distance-to-image-plane",
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
    finally:
        app.close()
