"""T-016-033: glTF, 3D Tiles and shards with validator runs; hostile scene inputs (pipeline, integration).

Requirements: FR-016-19, FR-016-37.

Spec: specs/016-export-acceleration/spec.md
- FR-016-19: bake the composed scene into glTF 2.0 binaries that pass the Khronos glTF Validator with 0 errors and 3D
  Tiles 1.1 tilesets that pass the 3D Tiles Validator with 0 errors, and write replay shards of <= 10 x 10^6 bytes each
  with their SHA-256 in the manifest;
- FR-016-37: a scene mesh with a non-finite vertex coordinate or an out-of-range index, a texture without a licence
  record, or a validator that reports any error fails the bake of that asset with the validator message and publishes
  nothing for it.
plan.md test strategy rows FR-016-19 (the Khronos glTF Validator and the 3D Tiles Validator report 0 errors on a
two-triangle fixture bake and >= 1 error on a deliberately invalid fixture; shard sizes by hand) and FR-016-37 (a NaN
vertex, index 3 in a two-vertex mesh, an unlicensed texture; a validator error fails the asset).

Oracles:
- the reference validators themselves (Khronos glTF Validator, 3D Tiles Validator; project-local npm tools resolved in
  T-016-000), run by `validate_glb` / `validate_tileset` on GLB bytes and tileset JSON written in this test with
  `struct` and `json` (checked with gltf-validator and 3d-tiles-validator while writing the test; a valid
  single-triangle GLB; the same GLB with a bufferView longer than its buffer, which the Khronos
  validator reports as BUFFER_VIEW_TOO_LONG; a tileset whose root lacks `geometricError`);
- the glTF 2.0 binary container layout (header magic `glTF`, version 2, total length, JSON and BIN chunks) read back by
  hand;
- 3D Tiles 1.1 structure: `asset.version == "1.1"`, `root.boundingVolume.box` with 12 numbers, `root.content.uri`;
- shard sizes and digests by hand with `hashlib`.
Hostile cases use an injected validator so that they do not depend on the npm tools; the validator-error case injects
a validator that reports a message and the bake must carry that message.

Expected public API (module `pitstudio_pipeline.export.web_bake`, `pipeline/` environment):
    class BakeError(Exception)              # `.reason: str` (also the message), `.asset: str` (asset name or path)
    @dataclass ValidatorReport              # errors: list[str], warnings: list[str]
    validate_glb(path: Path) -> ValidatorReport                 # runs the Khronos glTF Validator
    validate_tileset(path: Path) -> ValidatorReport             # runs the 3D Tiles Validator
    bake_glb(mesh: Mapping, out_path: Path, *, textures: Mapping | None = None,
             validator: Callable[[Path], ValidatorReport] | None = None) -> BakeResult
        mesh: {"name": str, "vertices": float32 array (N, 3), "indices": integer array (M, 3)};
        textures: {name: {"png": bytes, "licence": {"spdx": str, "licence_class": str} | None}}.
        `validator` defaults to `validate_glb`. Writes a GLB at `out_path` only when every guard and the validator pass;
        BakeResult: path, bytes, sha256, validator (ValidatorReport).
        Raises BakeError (no file left behind) for a non-finite vertex, an index outside [0, N), a texture without a
        licence record, or a validator report with errors (the reason contains the first validator message).
    bake_tileset(tiles: Sequence[Mapping], out_dir: Path, *, glb_validator=None, validator=None) -> BakeResult
        tiles: {"name": str, "mesh": mesh, "bounding_box": 12 floats, "geometric_error": float}; writes
        `<out_dir>/tileset.json` (3D Tiles 1.1, root tile content `<name>.glb`) plus the GLB files, validates each GLB
        and the tileset (`validator` defaults to `validate_tileset`), and raises BakeError without a tileset file when
        any validator reports an error.
    pack_shards(items: Sequence[tuple[str, bytes]], out_dir: Path, *, cap_bytes: int = 10_000_000) -> list[ShardInfo]
        ShardInfo: path, bytes, sha256, members (the item names in the shard, in input order); every shard file is at
        most `cap_bytes`; every item appears in exactly one shard; the digests are those of the files; an item larger
        than `cap_bytes` raises BakeError.
"""

from __future__ import annotations

import hashlib
import json
import struct
import zlib
from pathlib import Path

import numpy as np
import pytest
from pitstudio_pipeline.export.web_bake import (
    BakeError,
    ValidatorReport,
    bake_glb,
    bake_tileset,
    pack_shards,
    validate_glb,
    validate_tileset,
)


def _ok(_path: Path) -> ValidatorReport:
    return ValidatorReport(errors=[], warnings=[])


def _square() -> dict:
    return {
        "name": "two-triangles",
        "vertices": np.array([[0, 0, 0], [1, 0, 0], [1, 1, 0], [0, 1, 0]], dtype=np.float32),
        "indices": np.array([[0, 1, 2], [0, 2, 3]], dtype=np.uint32),
    }


def _png() -> bytes:
    """A valid 1 x 1 RGB PNG, built from the PNG specification (chunk = length, tag, data, CRC-32)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0)
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", ihdr)
        + chunk(b"IDAT", zlib.compress(b"\x00\xff\x00\x00"))
        + chunk(b"IEND", b"")
    )


def _glb_bytes(*, view_length: int = 36) -> bytes:
    """Hand-built single-triangle GLB (glTF 2.0 binary container); `view_length` > 36 makes it invalid."""
    positions = struct.pack("<9f", 0, 0, 0, 1, 0, 0, 0, 1, 0)
    indices = struct.pack("<3H", 0, 1, 2) + b"\x00\x00"
    binary = positions + indices  # 44 bytes
    doc = {
        "asset": {"version": "2.0"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [{"mesh": 0}],
        "meshes": [{"primitives": [{"attributes": {"POSITION": 0}, "indices": 1}]}],
        "buffers": [{"byteLength": len(binary)}],
        "bufferViews": [
            {"buffer": 0, "byteOffset": 0, "byteLength": view_length, "target": 34962},
            {"buffer": 0, "byteOffset": 36, "byteLength": 6, "target": 34963},
        ],
        "accessors": [
            {"bufferView": 0, "componentType": 5126, "count": 3, "type": "VEC3", "min": [0, 0, 0], "max": [1, 1, 0]},
            {"bufferView": 1, "componentType": 5123, "count": 3, "type": "SCALAR"},
        ],
    }
    js = json.dumps(doc, separators=(",", ":")).encode()
    js += b" " * (-len(js) % 4)
    body = struct.pack("<I", len(js)) + b"JSON" + js + struct.pack("<I", len(binary)) + b"BIN\x00" + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-19: the reference validators on hand-built fixtures (integration)
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-19")
def test_the_khronos_validator_reports_zero_errors_on_a_valid_glb_and_errors_on_an_invalid_one(tmp_path: Path) -> None:
    good, bad = tmp_path / "good.glb", tmp_path / "bad.glb"
    good.write_bytes(_glb_bytes())
    bad.write_bytes(_glb_bytes(view_length=100))  # bufferView longer than the buffer: BUFFER_VIEW_TOO_LONG
    assert validate_glb(good).errors == []
    assert len(validate_glb(bad).errors) >= 1


@pytest.mark.req("FR-016-19")
def test_the_3d_tiles_validator_reports_zero_errors_on_a_valid_tileset_and_errors_on_an_invalid_one(
    tmp_path: Path,
) -> None:
    (tmp_path / "tile.glb").write_bytes(_glb_bytes())
    box = [0.5, 0.5, 0, 0.5, 0, 0, 0, 0.5, 0, 0, 0, 0.001]
    root = {"boundingVolume": {"box": box}, "geometricError": 0, "refine": "ADD", "content": {"uri": "tile.glb"}}
    good, bad = tmp_path / "good" / "tileset.json", tmp_path / "bad" / "tileset.json"
    for path, tile in ((good, root), (bad, {k: v for k, v in root.items() if k != "geometricError"})):
        path.parent.mkdir()
        (path.parent / "tile.glb").write_bytes(_glb_bytes())
        path.write_text(json.dumps({"asset": {"version": "1.1"}, "geometricError": 1, "root": tile}), encoding="utf-8")
    assert validate_tileset(good).errors == []
    assert len(validate_tileset(bad).errors) >= 1


@pytest.mark.req("FR-016-19")
def test_a_two_triangle_mesh_bakes_to_a_gltf_2_binary_that_the_validator_accepts(tmp_path: Path) -> None:
    out = tmp_path / "scene.glb"
    result = bake_glb(_square(), out)  # default validator: the Khronos glTF Validator
    data = out.read_bytes()
    magic, version, length = struct.unpack_from("<4sII", data)
    assert (magic, version, length) == (b"glTF", 2, len(data))
    assert result.path == out
    assert result.bytes == len(data)
    assert result.sha256 == hashlib.sha256(data).hexdigest()
    assert result.validator.errors == []
    assert validate_glb(out).errors == []


@pytest.mark.req("FR-016-19")
def test_a_baked_tileset_is_3d_tiles_1_1_with_valid_content_and_passes_the_validators(tmp_path: Path) -> None:
    tile = {
        "name": "tile0",
        "mesh": _square(),
        "bounding_box": [0.5, 0.5, 0.0, 0.5, 0.0, 0.0, 0.0, 0.5, 0.0, 0.0, 0.0, 0.001],
        "geometric_error": 0.0,
    }
    result = bake_tileset([tile], tmp_path)
    doc = json.loads((tmp_path / "tileset.json").read_text(encoding="utf-8"))
    assert doc["asset"]["version"] == "1.1"
    assert len(doc["root"]["boundingVolume"]["box"]) == 12
    assert doc["root"]["content"]["uri"] == "tile0.glb"
    assert (tmp_path / "tile0.glb").is_file()
    assert result.validator.errors == []
    assert validate_tileset(tmp_path / "tileset.json").errors == []


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-19: shards
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-19")
def test_shards_are_at_most_the_cap_hold_every_item_once_and_carry_their_sha256(tmp_path: Path) -> None:
    items = [(f"frame-{i:03d}", bytes([i]) * 3_000_000) for i in range(7)]  # 21,000,000 bytes of payload
    shards = pack_shards(items, tmp_path)
    assert len(shards) >= 3  # at most 3 payload items fit in 10,000,000 bytes (3 x 3,000,000 + container overhead)
    for shard in shards:
        data = Path(shard.path).read_bytes()
        assert len(data) == shard.bytes <= 10_000_000
        assert shard.sha256 == hashlib.sha256(data).hexdigest()
    members = [m for s in shards for m in s.members]
    assert members == [name for name, _ in items]  # each item exactly once, in input order


@pytest.mark.req("FR-016-19")
def test_shard_cap_is_a_parameter_and_an_item_above_it_is_refused(tmp_path: Path) -> None:
    shards = pack_shards([("a", b"x" * 400), ("b", b"y" * 400), ("c", b"z" * 400)], tmp_path / "s", cap_bytes=1_500)
    assert all(s.bytes <= 1_500 for s in shards)
    assert [m for s in shards for m in s.members] == ["a", "b", "c"]
    with pytest.raises(BakeError):
        pack_shards([("huge", b"x" * 5_000)], tmp_path / "t", cap_bytes=1_500)


@pytest.mark.req("FR-016-19")
def test_packing_the_same_items_twice_gives_identical_shards(tmp_path: Path) -> None:
    items = [(f"f{i}", bytes([i]) * 1000) for i in range(5)]
    a = pack_shards(items, tmp_path / "a", cap_bytes=3_000)
    b = pack_shards(items, tmp_path / "b", cap_bytes=3_000)
    assert [s.sha256 for s in a] == [s.sha256 for s in b]


# ----------------------------------------------------------------------------------------------------------------------
# FR-016-37: hostile inputs (injected validator)
# ----------------------------------------------------------------------------------------------------------------------


@pytest.mark.req("FR-016-37")
@pytest.mark.parametrize("bad", [np.nan, np.inf, -np.inf])
def test_a_non_finite_vertex_coordinate_fails_the_bake_and_publishes_nothing(bad: float, tmp_path: Path) -> None:
    mesh = _square()
    mesh["vertices"][2, 1] = bad
    out = tmp_path / "scene.glb"
    with pytest.raises(BakeError) as info:
        bake_glb(mesh, out, validator=_ok)
    assert info.value.reason
    assert "finite" in info.value.reason.lower() or "vertex" in info.value.reason.lower()
    assert not out.exists()


@pytest.mark.req("FR-016-37")
def test_index_3_in_a_two_vertex_mesh_is_out_of_range(tmp_path: Path) -> None:
    mesh = {
        "name": "bad",
        "vertices": np.array([[0, 0, 0], [1, 0, 0]], dtype=np.float32),
        "indices": np.array([[0, 1, 3]], dtype=np.uint32),
    }
    out = tmp_path / "bad.glb"
    with pytest.raises(BakeError) as info:
        bake_glb(mesh, out, validator=_ok)
    assert "index" in info.value.reason.lower()
    assert not out.exists()


@pytest.mark.req("FR-016-37")
@pytest.mark.parametrize("index", [4, 5, 2**31, -1])
def test_an_index_outside_the_vertex_range_is_refused(index: int, tmp_path: Path) -> None:
    mesh = _square()
    mesh["indices"] = np.array([[0, 1, index]], dtype=np.int64)
    with pytest.raises(BakeError):
        bake_glb(mesh, tmp_path / "x.glb", validator=_ok)
    assert not (tmp_path / "x.glb").exists()


@pytest.mark.req("FR-016-37")
def test_a_texture_without_a_licence_record_fails_the_bake_naming_the_texture(tmp_path: Path) -> None:
    textures = {"rock_albedo": {"png": _png(), "licence": None}}
    out = tmp_path / "t.glb"
    with pytest.raises(BakeError) as info:
        bake_glb(_square(), out, textures=textures, validator=_ok)
    assert "rock_albedo" in info.value.reason or info.value.asset == "rock_albedo"
    assert "licence" in info.value.reason.lower()
    assert not out.exists()


@pytest.mark.req("FR-016-37")
def test_a_texture_with_a_licence_record_does_not_trip_the_licence_guard(tmp_path: Path) -> None:
    licence = {"spdx": "CC0-1.0", "licence_class": "public-domain"}
    textures = {"rock_albedo": {"png": _png(), "licence": licence}}
    result = bake_glb(_square(), tmp_path / "t.glb", textures=textures, validator=_ok)
    assert result.validator.errors == []
    assert (tmp_path / "t.glb").is_file()


@pytest.mark.req("FR-016-37")
def test_a_validator_error_fails_the_asset_with_the_validator_message_and_publishes_nothing(tmp_path: Path) -> None:
    def failing(_path: Path) -> ValidatorReport:
        return ValidatorReport(errors=["ACCESSOR_INDEX_OOB: Accessor index 5 exceeds the vertex count"], warnings=[])

    out = tmp_path / "scene.glb"
    with pytest.raises(BakeError) as info:
        bake_glb(_square(), out, validator=failing)
    assert "ACCESSOR_INDEX_OOB" in info.value.reason
    assert not out.exists()


@pytest.mark.req("FR-016-37")
def test_validator_warnings_alone_do_not_fail_the_bake(tmp_path: Path) -> None:
    def warns(_path: Path) -> ValidatorReport:
        return ValidatorReport(errors=[], warnings=["UNUSED_OBJECT"])

    assert bake_glb(_square(), tmp_path / "w.glb", validator=warns).validator.warnings == ["UNUSED_OBJECT"]


@pytest.mark.req("FR-016-37")
def test_a_tileset_validator_error_fails_the_bake_and_leaves_no_tileset(tmp_path: Path) -> None:
    def bad_tileset(_path: Path) -> ValidatorReport:
        return ValidatorReport(errors=["TILESET_INVALID: root.geometricError missing"], warnings=[])

    tile = {"name": "t0", "mesh": _square(), "bounding_box": [0.5, 0.5, 0, 0.5, 0, 0, 0, 0.5, 0, 0, 0, 0.001]}
    with pytest.raises(BakeError) as info:
        bake_tileset([{**tile, "geometric_error": 0.0}], tmp_path, glb_validator=_ok, validator=bad_tileset)
    assert "TILESET_INVALID" in info.value.reason
    assert not (tmp_path / "tileset.json").exists()


@pytest.mark.req("FR-016-37")
def test_a_hostile_mesh_inside_a_tile_fails_the_whole_tileset(tmp_path: Path) -> None:
    mesh = _square()
    mesh["vertices"][0, 0] = np.nan
    tile = {"name": "t0", "mesh": mesh, "bounding_box": [0.5, 0.5, 0, 0.5, 0, 0, 0, 0.5, 0, 0, 0, 0.001]}
    with pytest.raises(BakeError):
        bake_tileset([{**tile, "geometric_error": 0.0}], tmp_path, glb_validator=_ok, validator=_ok)
    assert not (tmp_path / "tileset.json").exists()
