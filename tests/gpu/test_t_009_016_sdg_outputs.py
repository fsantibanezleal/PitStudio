# ruff: noqa: E501
"""T-009-016 (GPU): `st55_sdg` outputs on a one-wall, one-cube scene (FR-009-02). Marked `gpu`: never run in CI and not run
during the red phase (the GPU belongs to the scheduled jobs; it needs Isaac Sim / Replicator in the `studio/isaac` env).

Oracles (independent of the code under test, plan 009 test strategy row FR-009-02):
- analytical pinhole geometry of the fixture: the camera sits at (-10, 0, 1.5) m looking along +X with the optical
  axis through the principal point; a wall in the plane x = 0 perpendicular to the axis is 10.0 m from the image plane at
  EVERY pixel (depth is the distance to the image plane, not the ray length), so wall pixels read 10.0 +- 0.01 m
  (renderer float32 depth, plan 009 tolerances); a 1 m cube centred at (-5, 0, 1.5) shows a front face at 4.5 m,
  and its silhouette is that face: half-width = 0.5 * fx / 4.5 = 123.1667 px about the principal point (640, 360), i.e. the
  tight box [516.83, 236.83, 246.33, 246.33] (x, y, w, h) +- 1 px (pixel-centre conventions, plan 009 tolerances);
- the output files are checked with `hashlib` (SHA-256), `PIL` (PNG size and mode), `numpy` (`.npy`), `jsonschema`
  (DC-009-01 record against `perception-dataset.schema.json`, DC-009-02 against `coco-instances.schema.json`).

Expected public API (module `pitstudio_isaac.sdg.render`, package under `studio/isaac/src/`, Python 3.12 Isaac env):

    render_frame(scene: Mapping, camera: Mapping, out_dir: pathlib.Path, *, family: str, arm: str, scenario_seed: int,
                 layout_id: str, split: str, dr: Mapping) -> dict
        Renders ONE frame of `scene` and writes, below `out_dir`: `rgb/000000.png`, `semantic/000000.png`,
        `depth/000000.npy`, `coco_instances.json` (the COCO file of the frame: images/annotations/categories only); returns the
        DC-009-01 dataset-index record of the frame (paths relative to `out_dir`, SHA-256 and byte sizes of every file
        written, intrinsics of `camera`, `synthetic: true`, `instance_source: "replicator"`, `dr` copied from the argument;
        the `frame_state` entry of a pit record is added by T-009-021, so this test tolerates its absence).
        scene: {"meters_per_unit": 1.0, "up_axis": "Z", "objects": [{"prim_id": "/World/Wall", "shape": "plane",
                 "label": "terrain", "centre_m": [0, 0, 0], "normal": [-1, 0, 0], "size_m": [400, 400]},
                {"prim_id": "/World/Cube", "shape": "cube", "label": "haul_truck", "centre_m": [-5, 0, 1.5], "size_m": 1.0}]}
        camera: {"position_m": [-10, 0, 1.5], "forward": [1, 0, 0], "up": [0, 0, 1], "width_px": 1280, "height_px": 720,
                 "fx_px": 1108.5, "fy_px": 1108.5, "cx_px": 640.0, "cy_px": 360.0}
        Outputs: RGB sRGB PNG 1280 x 720; semantic PNG (uint8 class ids: 0 background, COCO category id of the label for
        the five perception classes; the wall's `terrain` label is background 0); depth float32 (720, 1280) metres to the
        image plane; COCO: one image (id 0, file_name "rgb/000000.png", 1280 x 720), one annotation per perception-class
        prim (here the cube, category 1) with the tight box, polygon segmentation, `area`, `iscrowd` 0.
        Raises RuntimeError("isaac-sim-not-available") when Replicator cannot start (FR-009-40 owns the "not run" report).
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))  # Isaac lane package (Python 3.12, uv `package = false`)

from pitstudio_isaac.sdg import render  # noqa: E402

FX = 1108.5
HALF = 0.5 * FX / 4.5  # 123.1667 px, hand calculation above
SCENE = {
    "meters_per_unit": 1.0,
    "up_axis": "Z",
    "objects": [
        {
            "prim_id": "/World/Wall",
            "shape": "plane",
            "label": "terrain",
            "centre_m": [0.0, 0.0, 0.0],
            "normal": [-1.0, 0.0, 0.0],
            "size_m": [400.0, 400.0],
        },
        {
            "prim_id": "/World/Cube",
            "shape": "cube",
            "label": "haul_truck",
            "centre_m": [-5.0, 0.0, 1.5],
            "size_m": 1.0,
        },
    ],
}
CAMERA = {
    "position_m": [-10.0, 0.0, 1.5],
    "forward": [1.0, 0.0, 0.0],
    "up": [0.0, 0.0, 1.0],
    "width_px": 1280,
    "height_px": 720,
    "fx_px": FX,
    "fy_px": FX,
    "cx_px": 640.0,
    "cy_px": 360.0,
}
DR = {
    "sun_utc": "2025-03-14T18:42:07Z",
    "sun_elevation_deg": 41.7,
    "sun_azimuth_deg": 203.4,
    "dust_extinction_per_km": 0.0,
    "wet_segments": [],
    "rock_texture_ids": ["rock-quartz-monzonite-01"],
    "placements": [{"class": "haul_truck", "x_m": -5.0, "y_m": 0.0, "z_m": 1.5, "yaw_deg": 0.0}],
}


def _schema(name: str) -> dict:
    for p in (ROOT / "contracts" / name, ROOT / "specs" / "009-perception" / "contracts" / name):
        if p.is_file():
            return json.loads(p.read_text(encoding="utf-8"))
    raise AssertionError(name)


@pytest.fixture(scope="module")
def frame(tmp_path_factory: pytest.TempPathFactory) -> tuple[dict, Path]:
    out = tmp_path_factory.mktemp("sdg-frame")
    record = render.render_frame(
        SCENE,
        CAMERA,
        out,
        family="pit",
        arm="structured",
        scenario_seed=4211,
        layout_id="layout-0042",
        split="test",
        dr=DR,
    )
    return record, out


@pytest.mark.gpu
@pytest.mark.req("FR-009-02")
def test_the_rgb_is_an_srgb_png_of_1280_by_720(frame: tuple[dict, Path]) -> None:
    from PIL import Image

    record, out = frame
    path = out / record["image"]["path"]
    with Image.open(path) as im:
        assert im.format == "PNG"
        assert im.size == (1280, 720)
        assert im.mode in ("RGB", "RGBA")
    assert (record["image"]["width_px"], record["image"]["height_px"]) == (1280, 720)
    assert record["image"]["colour_space"] == "srgb"


@pytest.mark.gpu
@pytest.mark.req("FR-009-02")
def test_wall_pixels_have_a_depth_of_ten_metres_to_the_image_plane(frame: tuple[dict, Path]) -> None:
    import numpy as np

    record, out = frame
    depth = np.load(out / record["depth"]["path"])
    assert depth.dtype == np.float32
    assert depth.shape == (720, 1280)
    assert record["depth"]["quantity"] == "distance-to-image-plane"
    assert record["depth"]["unit"] == "m"
    corner = depth[:100, :100]  # far from the cube: wall only
    assert np.all(np.abs(corner - 10.0) <= 0.01)
    assert abs(float(depth[0, 1279]) - 10.0) <= 0.01  # image plane distance, not the longer ray length


@pytest.mark.gpu
@pytest.mark.req("FR-009-02")
def test_the_cube_front_face_is_at_4_5_metres(frame: tuple[dict, Path]) -> None:
    import numpy as np

    record, out = frame
    depth = np.load(out / record["depth"]["path"])
    assert abs(float(depth[360, 640]) - 4.5) <= 0.01


@pytest.mark.gpu
@pytest.mark.req("FR-009-02")
def test_the_coco_box_of_the_cube_equals_its_pinhole_projection_within_one_pixel(frame: tuple[dict, Path]) -> None:
    from jsonschema import Draft202012Validator

    record, out = frame
    coco = json.loads((out / record["coco"]["path"]).read_text(encoding="utf-8"))
    assert list(Draft202012Validator(_schema("coco-instances.schema.json")).iter_errors(coco)) == []
    (image,) = coco["images"]
    assert (image["width"], image["height"]) == (1280, 720)
    (ann,) = coco["annotations"]  # the wall is `terrain`: no perception class, no annotation
    assert ann["category_id"] == 1
    assert ann["iscrowd"] == 0
    assert ann["image_id"] == image["id"]
    x, y, w, h = ann["bbox"]
    for got, want in [(x, 640.0 - HALF), (y, 360.0 - HALF), (w, 2.0 * HALF), (h, 2.0 * HALF)]:
        assert abs(got - want) <= 1.0, (ann["bbox"], want)
    assert (
        abs(ann["area"] - (2.0 * HALF) ** 2) <= 4.0 * (2.0 * HALF) * 1.0
    )  # within a one-pixel ring (perimeter x 1 px)
    assert len(ann["segmentation"][0]) >= 6


@pytest.mark.gpu
@pytest.mark.req("FR-009-02")
def test_the_semantic_mask_labels_the_cube_with_its_class_id_and_the_rest_as_background(
    frame: tuple[dict, Path],
) -> None:
    import numpy as np
    from PIL import Image

    record, out = frame
    with Image.open(out / record["semantic_mask"]["path"]) as im:
        sem = np.asarray(im)
    assert sem.shape == (720, 1280)
    assert set(np.unique(sem).tolist()) == {0, 1}
    assert sem[360, 640] == 1
    assert sem[5, 5] == 0
    inside = int((sem == 1).sum())
    assert abs(inside - (2.0 * HALF) ** 2) <= 4.0 * 2.0 * HALF  # a one-pixel ring of tolerance


@pytest.mark.gpu
@pytest.mark.req("FR-009-02")
def test_the_record_carries_intrinsics_dr_values_file_digests_and_validates(frame: tuple[dict, Path]) -> None:
    from jsonschema import Draft202012Validator

    record, out = frame
    errors = list(Draft202012Validator(_schema("perception-dataset.schema.json")).iter_errors(record))
    assert [e.message for e in errors if "frame_state" not in e.message] == []  # frame_state is T-009-021 (FR-009-44)
    assert record["family"] == "pit"
    assert record["arm"] == "structured"
    assert record["scenario_seed"] == 4211
    assert record["layout_id"] == "layout-0042"
    assert record["synthetic"] is True
    assert record["instance_source"] == "replicator"
    assert record["dr"] == DR
    assert record["intrinsics"] == {"model": "pinhole", "fx_px": FX, "fy_px": FX, "cx_px": 640.0, "cy_px": 360.0}
    for key in ("image", "coco", "semantic_mask", "depth"):
        data = (out / record[key]["path"]).read_bytes()
        assert record[key]["sha256"] == hashlib.sha256(data).hexdigest()
        assert record[key]["size_bytes"] == len(data)
