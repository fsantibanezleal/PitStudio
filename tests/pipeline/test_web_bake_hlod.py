"""Web bake of the terrain: quantised textured tiles, hierarchical LOD tilesets, texture licence records, validator
availability.

Requirements: FR-016-19, FR-016-37 (the locked task test is test_t_016_033_web_bake_validators.py; this file covers
what the
terrain bake adds on top of it: KHR_mesh_quantization, KHR_texture_transform, external texture URIs, `children` and
`content_uri` of a tileset, the frame conversion and a validator that cannot run).

Oracles: the Khronos glTF Validator and the 3D Tiles Validator themselves (npm, `validate_glb` /
`validate_tileset`); the glTF 2.0
binary layout read back by hand; the rotation determinant by hand.
"""

from __future__ import annotations

import io
import json
import struct
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pitstudio_pipeline.export import web_bake
from pitstudio_pipeline.export.web_bake import (
    BakeError,
    ValidatorUnavailable,
    bake_glb,
    bake_tileset,
    enu_to_gltf,
    validate_glb,
    validate_tileset,
)


def _jpeg() -> bytes:
    """A small baseline JPEG written by Pillow (the validators read the image header)."""
    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (150, 130, 100)).save(buffer, format="JPEG", quality=80)
    return buffer.getvalue()


JPEG = _jpeg()
PD = {"spdx": "LicenseRef-USGov-PD", "licence_class": "public-domain"}
CC0 = {"spdx": "CC0-1.0", "licence_class": "public-domain"}


def _grid_mesh(n: int = 5, name: str = "grid") -> dict:
    """An n x n vertex grid of 2(n-1)^2 triangles with normals and texture coordinates, in the glTF frame."""
    xs, zs = np.meshgrid(np.linspace(0, 100, n), np.linspace(0, 100, n))
    ys = 5.0 * np.sin(xs / 30.0)
    vertices = np.stack([xs, ys, -zs], axis=-1).reshape(-1, 3).astype(np.float32)
    idx = []
    for r in range(n - 1):
        for c in range(n - 1):
            a, b, d, e = r * n + c, r * n + c + 1, (r + 1) * n + c, (r + 1) * n + c + 1
            idx += [(a, d, b), (b, d, e)]
    normals = np.tile(np.array([0.0, 1.0, 0.0], dtype=np.float32), (len(vertices), 1))
    uvs = np.stack([xs.ravel() / 100.0, 1.0 - zs.ravel() / 100.0], axis=-1).astype(np.float32)
    return {
        "name": name,
        "vertices": vertices,
        "indices": np.array(idx, dtype=np.uint32),
        "normals": normals,
        "texcoords": uvs,
    }


def _textured(mesh: dict) -> tuple[dict, dict]:
    mesh = {
        **mesh,
        "quantize": True,
        "material": {
            "base_color": "albedo",
            "normal": "rock-normal",
            "normal_transform": {"scale": [12.5, 12.5], "offset": [0.25, 0.75]},
        },
    }
    textures = {
        "albedo": {"jpeg": JPEG, "licence": PD},
        "rock-normal": {"uri": "../textures/rock-normal.jpg", "licence": CC0},
    }
    return mesh, textures


def _doc(glb: bytes) -> dict:
    length = struct.unpack_from("<I", glb, 12)[0]
    return json.loads(glb[20 : 20 + length])


@pytest.mark.req("FR-016-19")
def test_a_quantised_textured_tile_passes_the_khronos_validator_and_carries_its_licences(tmp_path: Path) -> None:
    (tmp_path / "textures").mkdir()
    (tmp_path / "textures" / "rock-normal.jpg").write_bytes(JPEG)
    mesh, textures = _textured(_grid_mesh())
    out = tmp_path / "tiles" / "tile.glb"
    result = bake_glb(mesh, out, textures=textures)
    assert result.validator.errors == []
    assert validate_glb(out).errors == []
    doc = _doc(out.read_bytes())
    assert doc["extensionsRequired"] == ["KHR_mesh_quantization"]
    assert "KHR_texture_transform" in doc["extensionsUsed"]
    assert doc["accessors"][0]["componentType"] == 5122  # int16 positions under the node transform
    assert doc["asset"]["extras"]["textures"] == {"albedo": PD, "rock-normal": CC0}
    assert {i["name"]: i["extras"]["licence"] for i in doc["images"]} == {"albedo": PD, "rock-normal": CC0}
    assert doc["images"][1]["uri"] == "../textures/rock-normal.jpg"
    assert doc["materials"][0]["normalTexture"]["extensions"]["KHR_texture_transform"]["scale"] == [12.5, 12.5]


@pytest.mark.req("FR-016-19")
def test_quantised_positions_stay_within_the_int16_step_of_the_source(tmp_path: Path) -> None:
    mesh = {**_grid_mesh(), "quantize": True}
    out = tmp_path / "q.glb"
    bake_glb(mesh, out)
    data = out.read_bytes()
    doc = _doc(data)
    js_len = struct.unpack_from("<I", data, 12)[0]
    binary = data[20 + js_len + 8 :]
    view = doc["bufferViews"][doc["accessors"][0]["bufferView"]]
    raw = np.frombuffer(binary, dtype="<i2", count=view["byteLength"] // 2, offset=view["byteOffset"]).reshape(-1, 4)[
        :, :3
    ]
    scale, shift = np.array(doc["nodes"][0]["scale"]), np.array(doc["nodes"][0]["translation"])
    back = raw * scale + shift
    step = np.array([100.0, 10.0, 100.0]) / 65535.0
    assert np.all(np.abs(back - mesh["vertices"]) <= step + 1e-4)


@pytest.mark.req("FR-016-19")
def test_two_bakes_of_the_same_tile_are_byte_identical(tmp_path: Path) -> None:
    mesh, textures = _textured(_grid_mesh())
    a = bake_glb(mesh, tmp_path / "a.glb", textures=textures, validator=lambda _p: web_bake.ValidatorReport())
    b = bake_glb(mesh, tmp_path / "b.glb", textures=textures, validator=lambda _p: web_bake.ValidatorReport())
    assert a.sha256 == b.sha256
    assert (tmp_path / "a.glb").read_bytes() == (tmp_path / "b.glb").read_bytes()


@pytest.mark.req("FR-016-37")
def test_an_external_texture_without_a_licence_record_fails_the_bake(tmp_path: Path) -> None:
    mesh, textures = _textured(_grid_mesh())
    textures["rock-normal"]["licence"] = {"spdx": "CC0-1.0"}  # no licence class
    with pytest.raises(BakeError) as info:
        bake_glb(mesh, tmp_path / "x.glb", textures=textures, validator=lambda _p: web_bake.ValidatorReport())
    assert "rock-normal" in info.value.reason
    assert "licence" in info.value.reason
    assert not (tmp_path / "x.glb").exists()


@pytest.mark.req("FR-016-37")
@pytest.mark.parametrize(
    "spec", [{"png": b"not a png", "licence": PD}, {"jpeg": b"\x00\x01", "licence": PD}, {"licence": PD}]
)
def test_a_texture_that_is_not_an_image_or_has_no_body_is_refused(spec: dict, tmp_path: Path) -> None:
    mesh = {**_grid_mesh(), "material": {"base_color": "albedo"}}
    with pytest.raises(BakeError):
        bake_glb(mesh, tmp_path / "x.glb", textures={"albedo": spec}, validator=lambda _p: web_bake.ValidatorReport())
    assert not (tmp_path / "x.glb").exists()


@pytest.mark.req("FR-016-37")
def test_a_material_naming_a_texture_that_was_not_given_is_refused(tmp_path: Path) -> None:
    mesh = {**_grid_mesh(), "material": {"base_color": "missing"}}
    with pytest.raises(BakeError):
        bake_glb(mesh, tmp_path / "x.glb", textures={}, validator=lambda _p: web_bake.ValidatorReport())


@pytest.mark.req("FR-016-37")
def test_a_texture_coordinate_outside_the_unit_square_cannot_be_quantised(tmp_path: Path) -> None:
    mesh = _grid_mesh()
    mesh["texcoords"][3, 0] = 1.5
    with pytest.raises(BakeError):
        bake_glb({**mesh, "quantize": True}, tmp_path / "x.glb", validator=lambda _p: web_bake.ValidatorReport())
    assert not (tmp_path / "x.glb").exists()


@pytest.mark.req("FR-016-19")
def test_a_hierarchical_lod_tileset_with_external_content_passes_both_validators(tmp_path: Path) -> None:
    (tmp_path / "tiles" / "textures").mkdir(parents=True)
    (tmp_path / "tiles" / "textures" / "rock-normal.jpg").write_bytes(JPEG)
    root_mesh, root_tex = _textured(_grid_mesh(3, "root"))
    base = [50.0, -50.0, 0.0, 50.0, 0.0, 0.0, 0.0, 50.0, 0.0, 0.0, 0.0, 10.0]
    # level 0: a tileset of its own; the detail tileset refers to the same tile file through a relative URI
    lod0 = bake_tileset(
        [{"name": "lod0", "mesh": root_mesh, "textures": root_tex, "bounding_box": base, "geometric_error": 10.0}],
        tmp_path / "tiles" / "lod0",
    )
    assert lod0.validator.errors == []
    child_mesh, child_tex = _textured(_grid_mesh(9, "child"))
    child = {
        "name": "c0",
        "path": "lod1/c0.glb",
        "mesh": child_mesh,
        "textures": {**child_tex, "rock-normal": {**child_tex["rock-normal"], "uri": "../../textures/rock-normal.jpg"}},
        "bounding_box": base,
        "geometric_error": 1.0,
    }
    detail = bake_tileset(
        [
            {
                "name": "root",
                "content_uri": "../lod0/lod0.glb",
                "bounding_box": base,
                "geometric_error": 10.0,
                "children": [child],
            }
        ],
        tmp_path / "tiles" / "detail",
    )
    assert detail.validator.errors == []
    assert [Path(r.path).name for r in detail.children] == ["c0.glb"]
    doc = json.loads((tmp_path / "tiles" / "detail" / "tileset.json").read_text(encoding="utf-8"))
    assert doc["root"]["content"]["uri"] == "../lod0/lod0.glb"
    assert doc["root"]["children"][0]["content"]["uri"] == "lod1/c0.glb"
    assert validate_tileset(tmp_path / "tiles" / "detail" / "tileset.json").errors == []


@pytest.mark.req("FR-016-19")
def test_several_tiles_hang_under_a_root_without_content_that_holds_their_union(tmp_path: Path) -> None:
    def tile(name: str, x: float) -> dict:
        return {
            "name": name,
            "mesh": _grid_mesh(3, name),
            "bounding_box": [x, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 10.0, 0.0, 0.0, 0.0, 5.0],
            "geometric_error": 0.0,
        }

    result = bake_tileset([tile("a", 0.0), tile("b", 40.0)], tmp_path)
    assert result.validator.errors == []
    doc = json.loads((tmp_path / "tileset.json").read_text(encoding="utf-8"))
    assert "content" not in doc["root"]
    assert len(doc["root"]["children"]) == 2
    box = doc["root"]["boundingVolume"]["box"]
    assert box[0] == 20.0  # centre of the union of two 20 m boxes 40 m apart
    assert box[3] == 30.0  # its half length


@pytest.mark.req("FR-016-37")
def test_a_failed_tile_removes_every_file_the_call_wrote(tmp_path: Path) -> None:
    bad = _grid_mesh(3, "bad")
    bad["vertices"][1, 0] = np.nan
    box = [0, 0, 0, 10, 0, 0, 0, 10, 0, 0, 0, 5]
    tiles = [
        {"name": "ok", "mesh": _grid_mesh(3, "ok"), "bounding_box": box, "geometric_error": 0.0},
        {"name": "bad", "mesh": bad, "bounding_box": box, "geometric_error": 0.0},
    ]
    with pytest.raises(BakeError):
        bake_tileset(
            tiles,
            tmp_path,
            glb_validator=lambda _p: web_bake.ValidatorReport(),
            validator=lambda _p: web_bake.ValidatorReport(),
        )
    assert list(tmp_path.iterdir()) == []


@pytest.mark.req("FR-016-37")
def test_a_validator_that_cannot_run_is_never_read_as_a_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(web_bake.ENV_WEB_DIR, str(tmp_path / "no-web-folder"))
    with pytest.raises(ValidatorUnavailable):
        bake_glb(_grid_mesh(), tmp_path / "x.glb")
    assert not (tmp_path / "x.glb").exists()


@pytest.mark.req("FR-016-19")
def test_the_site_frame_maps_to_gltf_by_a_proper_rotation() -> None:
    east, north, up = np.eye(3)
    mapped = enu_to_gltf(np.stack([east, north, up]))
    assert mapped.tolist() == [[1, 0, 0], [0, 0, -1], [0, 1, 0]]  # east -> +x, north -> -z, up -> +y
    assert np.linalg.det(mapped) == pytest.approx(1.0)  # a rotation: triangle winding is kept
