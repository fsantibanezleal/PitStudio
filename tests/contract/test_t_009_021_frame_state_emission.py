# ruff: noqa: E501
"""T-009-021 (contract half) - FR-009-44: per-frame frame-state files from `st55_sdg`, valid against spec 015's schema.

Oracles (independent of the code under test):
- hand calculation of plan 009 (test strategy row FR-009-44): a stage with `metersPerUnit` 0.01 and a cube translated by
  500 stage units has a 5 m transform; its half-extents of 50 units are 0.5 m; a camera at 150 units is at 1.5 m; the
  quaternion and the pixel counts are copied unchanged; the stage's own `metersPerUnit` and `upAxis` are recorded;
- reference validator `jsonschema` (Draft 2020-12) against `contracts/frame-state.schema.json` (DC-015-01, owned by spec 015;
  the spec's valid example `specs/015-vlm/contracts/examples/frame-state.valid.json` is validated first, as a control);
- reference implementation `hashlib.sha256` of the image, depth, dust-field and terrain files and of the written frame-state
  file; linearity of the unit conversion (translation_m = metersPerUnit x translation) checked for random vectors.

Expected public API (module `pitstudio_studio.sdg.frame_state`, package under `studio/src/`; the Isaac stage calls it):

    build_frame_state(frame: Mapping, root: pathlib.Path) -> dict
        `frame` (stage units, as read from the USD stage by the Isaac stage):
            {"frame_id": str, "run_id": str, "case": str, "location": str, "condition": str,
             "stage": {"metersPerUnit": float, "upAxis": "Y" | "Z"},
             "image": {"path": relpath, "width_px": int, "height_px": int},
             "depth": {"path": relpath}, "dust_field": {"path": relpath} | None, "terrain": {"path": relpath},
             "camera": {"intrinsics": {fx_px, fy_px, cx_px, cy_px}, "translation": [x, y, z] (stage units),
                        "rotation_xyzw": [4 floats]},
             "objects": [{"prim_id": str, "class": str, "asset_id": str (optional), "translation": [x, y, z] (stage units),
                          "rotation_xyzw": [4 floats], "footprint": {"centre": [x, y], "half_extents": [hx, hy] (stage
                          units), "heading_deg": float}, "visible_px": int, "in_frustum": bool}],
             "bench_edges": [{"edge_id": str, "berm_present": bool, "visible_px": int}]}
        Files are read below `root` (relative paths). Returns the DC-015-01 document: transforms and footprints multiplied by
        metersPerUnit (metres), `metersPerUnit` and `upAxis` copied, `image`, `depth`, `terrain` and (when not None) `dust_field`
        carry "path" and the SHA-256 of that file (image also width_px, height_px), `dust_field` is null when None,
        `synthetic` true, `schema_version` "1.0", camera pose {translation_m, rotation_xyzw}, objects in input order, `asset_id`
        only when given. The result validates against frame-state.schema.json.
    write_frame_state(frame: Mapping, root: pathlib.Path, out_relpath: str) -> dict
        build_frame_state, then writes the JSON (UTF-8) to root / out_relpath and returns {"path": out_relpath, "sha256":
        SHA-256 of the written bytes, "size_bytes": their length}: the `frame_state` entry of the dataset-index record (DC-009-01).
        Nothing is written when build_frame_state raises.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)
sys.path.insert(0, str(ROOT / "tests" / "unit"))

import _p009_kit as kit  # noqa: E402
from pitstudio_studio.sdg import frame_state  # noqa: E402

EXAMPLES = 200


def _validator():
    from jsonschema import Draft202012Validator

    for p in (
        ROOT / "contracts" / "frame-state.schema.json",
        ROOT / "specs" / "015-vlm" / "contracts" / "frame-state.schema.json",
    ):
        if p.is_file():
            return Draft202012Validator(json.loads(p.read_text(encoding="utf-8")))
    raise AssertionError("frame-state.schema.json not found")


def _put(root: Path, rel: str, seed: int) -> bytes:
    data = kit.payload(300, seed)
    (root / rel).parent.mkdir(parents=True, exist_ok=True)
    (root / rel).write_bytes(data)
    return data


def make_frame(
    root: Path, *, mpu: float = 0.01, translation=(500.0, 0.0, 0.0), dust: bool = False, up_axis: str = "Z"
) -> dict:
    files = {
        "image": _put(root, "sdg/pit/rgb/000007.png", 1),
        "depth": _put(root, "sdg/pit/depth/000007.npy", 2),
        "terrain": _put(root, "scenes/b2/terrain.tif", 3),
    }
    frame = {
        "frame_id": "b2-pit-s0042-f0007",
        "run_id": "20261012T013000Z-b2",
        "case": "B2",
        "location": "haul_road",
        "condition": "dust",
        "stage": {"metersPerUnit": mpu, "upAxis": up_axis},
        "image": {"path": "sdg/pit/rgb/000007.png", "width_px": 1280, "height_px": 720},
        "depth": {"path": "sdg/pit/depth/000007.npy"},
        "dust_field": None,
        "terrain": {"path": "scenes/b2/terrain.tif"},
        "camera": {
            "intrinsics": {"fx_px": 1108.5, "fy_px": 1108.5, "cx_px": 640.0, "cy_px": 360.0},
            "translation": [0.0, 0.0, 150.0],
            "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
        },
        "objects": [
            {
                "prim_id": "/World/Cube",
                "class": "boulder",
                "translation": list(translation),
                "rotation_xyzw": [0.0, 0.0, 0.0, 1.0],
                "footprint": {
                    "centre": [translation[0], translation[1]],
                    "half_extents": [50.0, 50.0],
                    "heading_deg": 0.0,
                },
                "visible_px": 1200,
                "in_frustum": True,
            }
        ],
        "bench_edges": [],
    }
    if dust:
        files["dust_field"] = _put(root, "sdg/pit/dust_field.npz", 4)
        frame["dust_field"] = {"path": "sdg/pit/dust_field.npz"}
    frame["_digests"] = {k: hashlib.sha256(v).hexdigest() for k, v in files.items()}  # test-side oracle, removed below
    return frame


def _split(frame: dict) -> tuple[dict, dict]:
    frame = dict(frame)
    return frame, frame.pop("_digests")


def _close(a, b, tol: float = 1e-12) -> bool:
    if isinstance(a, dict):
        return isinstance(b, dict) and a.keys() == b.keys() and all(_close(a[k], b[k], tol) for k in a)
    if isinstance(a, list):
        return isinstance(b, list) and len(a) == len(b) and all(_close(x, y, tol) for x, y in zip(a, b, strict=True))
    if isinstance(a, float) or isinstance(b, float):
        return isinstance(b, (int, float)) and abs(a - b) <= tol
    return a == b


@pytest.mark.req("FR-009-44")
def test_the_spec_015_valid_example_passes_the_schema_control() -> None:
    doc = json.loads(
        (ROOT / "specs" / "015-vlm" / "contracts" / "examples" / "frame-state.valid.json").read_text(encoding="utf-8")
    )
    assert list(_validator().iter_errors(doc)) == []


@pytest.mark.req("FR-009-44")
def test_a_cube_translated_by_500_units_on_a_centimetre_stage_is_5_metres(tmp_path: Path) -> None:
    frame, d = _split(make_frame(tmp_path))
    doc = frame_state.build_frame_state(frame, tmp_path)
    expected = {
        "schema_version": "1.0",
        "frame_id": "b2-pit-s0042-f0007",
        "run_id": "20261012T013000Z-b2",
        "synthetic": True,
        "case": "B2",
        "location": "haul_road",
        "condition": "dust",
        "metersPerUnit": 0.01,
        "upAxis": "Z",
        "image": {"path": "sdg/pit/rgb/000007.png", "sha256": d["image"], "width_px": 1280, "height_px": 720},
        "depth": {"path": "sdg/pit/depth/000007.npy", "sha256": d["depth"]},
        "dust_field": None,
        "terrain": {"path": "scenes/b2/terrain.tif", "sha256": d["terrain"]},
        "camera": {
            "intrinsics": {"fx_px": 1108.5, "fy_px": 1108.5, "cx_px": 640.0, "cy_px": 360.0},
            "pose": {"translation_m": [0.0, 0.0, 1.5], "rotation_xyzw": [0.0, 0.0, 0.0, 1.0]},
        },
        "objects": [
            {
                "prim_id": "/World/Cube",
                "class": "boulder",
                "pose": {"translation_m": [5.0, 0.0, 0.0], "rotation_xyzw": [0.0, 0.0, 0.0, 1.0]},
                "footprint": {"centre_m": [5.0, 0.0], "half_extents_m": [0.5, 0.5], "heading_deg": 0.0},
                "visible_px": 1200,
                "in_frustum": True,
            }
        ],
        "bench_edges": [],
    }
    assert _close(doc, expected)


@pytest.mark.req("FR-009-44")
def test_the_document_validates_against_the_frame_state_schema(tmp_path: Path) -> None:
    frame, _ = _split(make_frame(tmp_path, dust=True))
    doc = frame_state.build_frame_state(frame, tmp_path)
    assert list(_validator().iter_errors(doc)) == []
    assert doc["dust_field"]["path"] == "sdg/pit/dust_field.npz"


@pytest.mark.req("FR-009-44")
def test_the_image_depth_dust_and_terrain_digests_equal_hashlib(tmp_path: Path) -> None:
    frame, d = _split(make_frame(tmp_path, dust=True))
    doc = frame_state.build_frame_state(frame, tmp_path)
    assert doc["image"]["sha256"] == hashlib.sha256((tmp_path / "sdg/pit/rgb/000007.png").read_bytes()).hexdigest()
    assert doc["image"]["sha256"] == d["image"]
    assert doc["depth"]["sha256"] == d["depth"]
    assert doc["terrain"]["sha256"] == d["terrain"]
    assert doc["dust_field"]["sha256"] == d["dust_field"]


@pytest.mark.req("FR-009-44")
def test_the_written_file_is_the_document_and_its_entry_lists_path_digest_and_size(tmp_path: Path) -> None:
    frame, _ = _split(make_frame(tmp_path))
    entry = frame_state.write_frame_state(frame, tmp_path, "sdg/pit/frame_state/000007.json")
    path = tmp_path / "sdg/pit/frame_state/000007.json"
    raw = path.read_bytes()
    assert entry == {
        "path": "sdg/pit/frame_state/000007.json",
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
    }
    assert json.loads(raw.decode("utf-8")) == frame_state.build_frame_state(frame, tmp_path)
    assert list(_validator().iter_errors(json.loads(raw.decode("utf-8")))) == []


@pytest.mark.req("FR-009-44")
@pytest.mark.parametrize("mpu", [1.0, 0.01, 0.001, 0.0254, 2.0])
def test_every_transform_is_scaled_to_metres_by_the_stage_unit(tmp_path: Path, mpu: float) -> None:
    frame, _ = _split(make_frame(tmp_path, mpu=mpu, translation=(500.0, -250.0, 40.0)))
    doc = frame_state.build_frame_state(frame, tmp_path)
    assert doc["metersPerUnit"] == mpu
    obj = doc["objects"][0]
    assert _close(obj["pose"]["translation_m"], [500.0 * mpu, -250.0 * mpu, 40.0 * mpu], 1e-9)
    assert _close(obj["footprint"]["half_extents_m"], [50.0 * mpu, 50.0 * mpu], 1e-9)
    assert _close(doc["camera"]["pose"]["translation_m"], [0.0, 0.0, 150.0 * mpu], 1e-9)
    assert obj["pose"]["rotation_xyzw"] == [0.0, 0.0, 0.0, 1.0]  # not scaled
    assert obj["footprint"]["heading_deg"] == 0.0
    assert obj["visible_px"] == 1200


@pytest.mark.req("FR-009-44")
@given(
    mpu=st.floats(1e-3, 2.0),
    t=st.tuples(st.floats(-1e3, 1e3), st.floats(-1e3, 1e3), st.floats(-1e3, 1e3)),
)
@settings(max_examples=EXAMPLES, deadline=None)
def test_property_translation_in_metres_is_linear_in_the_stage_unit(
    tmp_path_factory: pytest.TempPathFactory, mpu: float, t: tuple
) -> None:
    root = tmp_path_factory.mktemp("fs")
    frame, _ = _split(make_frame(root, mpu=mpu, translation=t))
    got = frame_state.build_frame_state(frame, root)["objects"][0]["pose"]["translation_m"]
    assert _close(got, [x * mpu for x in t], 1e-9)


@pytest.mark.req("FR-009-44")
def test_the_y_up_stage_is_recorded_as_such(tmp_path: Path) -> None:
    frame, _ = _split(make_frame(tmp_path, up_axis="Y"))
    assert frame_state.build_frame_state(frame, tmp_path)["upAxis"] == "Y"


@pytest.mark.req("FR-009-44")
def test_objects_keep_their_order_and_an_asset_id_only_when_given(tmp_path: Path) -> None:
    frame, _ = _split(make_frame(tmp_path))
    second = dict(frame["objects"][0], prim_id="/World/Truck", **{"class": "haul_truck"}, asset_id="haul-truck-240t")
    frame["objects"] = [*frame["objects"], second]
    doc = frame_state.build_frame_state(frame, tmp_path)
    assert [o["prim_id"] for o in doc["objects"]] == ["/World/Cube", "/World/Truck"]
    assert "asset_id" not in doc["objects"][0]
    assert doc["objects"][1]["asset_id"] == "haul-truck-240t"
    assert list(_validator().iter_errors(doc)) == []


@pytest.mark.req("FR-009-44")
def test_build_does_not_modify_the_input_frame(tmp_path: Path) -> None:
    import copy

    frame, _ = _split(make_frame(tmp_path))
    before = copy.deepcopy(frame)
    frame_state.build_frame_state(frame, tmp_path)
    assert frame == before
