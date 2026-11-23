# SPDX-License-Identifier: Apache-2.0
"""Web bake of s60_export: glTF 2.0 binaries, 3D Tiles 1.1 tilesets and replay shards with validator runs and input
guards
(FR-016-19, FR-016-37; ADR-0038).

A composed scene is baked in two steps. The studio environment reads the OpenUSD scene and hands over plain arrays
(`pitstudio_studio.scene.web_terrain`); this module, in the `pipeline/` environment, turns the arrays into files, checks
every input before a byte is written, runs the reference validators on every file it wrote and keeps nothing that a
guard or a
validator rejected: `bake_glb` and `bake_tileset` leave no file behind when they raise.

The reference validators are the Khronos glTF Validator and the CesiumGS 3D Tiles Validator, both npm packages pinned in
`web/package.json` and run by `web/scripts/validate-3d.mjs` (exit code 0 no error, 1 an error, 2 a validator that
could not
run). A validator that cannot run is never read as a pass: it raises `ValidatorUnavailable`.

Writing is deterministic: no timestamp, sorted keys where a mapping is serialised, a fixed layout of the binary
chunk, so two
bakes of the same input give the same bytes (the digests of the manifest depend on it).
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import shutil
import struct
import subprocess
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np

# glTF 2.0 constants (the specification, sections 3.6.2 and 5)
FLOAT, SHORT, UNSIGNED_SHORT, UNSIGNED_INT, BYTE = 5126, 5122, 5123, 5125, 5120
ARRAY_BUFFER, ELEMENT_ARRAY_BUFFER = 34962, 34963
LINEAR, LINEAR_MIPMAP_LINEAR, CLAMP_TO_EDGE, REPEAT = 9729, 9987, 33071, 10497
PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
JPEG_MAGIC = b"\xff\xd8\xff"

DEFAULT_SHARD_CAP = 10_000_000
SHARD_MAGIC = b"PSHD"
ENV_WEB_DIR = "PITSTUDIO_WEB_DIR"
VALIDATOR_TIMEOUT_S = 900


class BakeError(Exception):
    """A guard or a validator refused an asset: `.reason` is the message and `.asset` names the asset (a name or a
    path)."""

    def __init__(self, reason: str, asset: str = "") -> None:
        super().__init__(reason)
        self.reason = reason
        self.asset = asset


class ValidatorUnavailable(BakeError):
    """The validator could not run (no node, a missing package): the asset is neither accepted nor judged invalid."""


@dataclass
class ValidatorReport:
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


@dataclass
class BakeResult:
    path: Path
    bytes: int
    sha256: str
    validator: ValidatorReport
    children: list[BakeResult] = field(
        default_factory=list
    )  # the GLB files of a tileset, in the order they were written


@dataclass
class ShardInfo:
    path: Path
    bytes: int
    sha256: str
    members: list[str]


# ----------------------------------------------------------------------------------------------------------------------
# validators
# ----------------------------------------------------------------------------------------------------------------------


def web_dir() -> Path:
    """The `web/` folder that holds the pinned validators (`PITSTUDIO_WEB_DIR` overrides the folder next to
    `pipeline/`)."""
    override = os.environ.get(ENV_WEB_DIR)
    return Path(override) if override else Path(__file__).resolve().parents[4] / "web"


def _run_validator(mode: str, path: Path) -> ValidatorReport:
    node = shutil.which("node")
    script = web_dir() / "scripts" / "validate-3d.mjs"
    if node is None or not script.is_file():
        raise ValidatorUnavailable(f"the {mode} validator cannot run: node or {script.name} is missing", str(path))
    try:
        proc = subprocess.run(
            [node, str(script), mode, str(path)],
            capture_output=True,
            text=True,
            cwd=script.parent.parent,
            timeout=VALIDATOR_TIMEOUT_S,
            check=False,
        )
    except subprocess.TimeoutExpired:
        raise ValidatorUnavailable(f"the {mode} validator timed out on {path.name}", str(path)) from None
    if proc.returncode not in (0, 1):
        raise ValidatorUnavailable(
            f"the {mode} validator could not run (exit {proc.returncode}): {proc.stderr.strip()[:300]}", str(path)
        )
    try:
        doc = json.loads(proc.stdout.strip().splitlines()[-1])
        return ValidatorReport(errors=[str(e) for e in doc["errors"]], warnings=[str(w) for w in doc["warnings"]])
    except ValueError, KeyError, IndexError:
        raise ValidatorUnavailable(f"the {mode} validator printed no report for {path.name}", str(path)) from None


def validate_glb(path: Path) -> ValidatorReport:
    """Runs the Khronos glTF Validator on a GLB file."""
    return _run_validator("glb", Path(path))


def validate_tileset(path: Path) -> ValidatorReport:
    """Runs the 3D Tiles Validator on a `tileset.json` (its content files are validated through it)."""
    return _run_validator("tileset", Path(path))


# ----------------------------------------------------------------------------------------------------------------------
# guards
# ----------------------------------------------------------------------------------------------------------------------


def _array(value: Any, shape_tail: int, what: str, asset: str, *, dtype: Any = np.float32) -> np.ndarray:
    try:
        arr = np.asarray(value)
    except TypeError, ValueError:
        raise BakeError(f"{what} is not an array", asset) from None
    if arr.ndim != 2 or arr.shape[1] != shape_tail or arr.shape[0] == 0:
        raise BakeError(f"{what} must have shape (n, {shape_tail}) with n >= 1, got {arr.shape}", asset)
    if arr.dtype.kind not in "fiu":
        raise BakeError(f"{what} has the non-numeric type {arr.dtype}", asset)
    return arr.astype(dtype)


def _guard_mesh(mesh: Mapping[str, Any]) -> tuple[str, np.ndarray, np.ndarray, np.ndarray | None, np.ndarray | None]:
    name = str(mesh.get("name") or "mesh")
    vertices = _array(mesh.get("vertices"), 3, "the vertex array", name)
    if not np.isfinite(vertices).all():
        bad = np.argwhere(~np.isfinite(vertices))[0]
        raise BakeError(
            f"vertex {int(bad[0])} has a non-finite coordinate (axis {int(bad[1])}); coordinates must be finite", name
        )
    raw = np.asarray(mesh.get("indices"))
    if raw.ndim != 2 or raw.shape[1] != 3 or raw.shape[0] == 0 or raw.dtype.kind not in "iu":
        raise BakeError(
            f"the index array must be an integer array of shape (m, 3) with m >= 1, got {raw.shape} {raw.dtype}", name
        )
    indices = raw.astype(np.int64)
    n = len(vertices)
    outside = (indices < 0) | (indices >= n)
    if outside.any():
        value = int(indices[outside][0])
        raise BakeError(f"index {value} is outside the vertex range [0, {n})", name)
    normals = uvs = None
    if mesh.get("normals") is not None:
        normals = _array(mesh["normals"], 3, "the normal array", name)
        if len(normals) != n or not np.isfinite(normals).all():
            raise BakeError(
                "the normal array must be finite and hold one normal per vertex (non-finite or wrong length)", name
            )
    if mesh.get("texcoords") is not None:
        uvs = _array(mesh["texcoords"], 2, "the texture coordinate array", name)
        if len(uvs) != n or not np.isfinite(uvs).all():
            raise BakeError("the texture coordinate array must be finite and hold one pair per vertex", name)
    return name, vertices, indices, normals, uvs


def _guard_textures(textures: Mapping[str, Mapping[str, Any]] | None) -> dict[str, dict[str, Any]]:
    """A texture needs a licence record (SPDX id and licence class) and a PNG or JPEG body or an external URI
    (FR-016-37)."""
    out: dict[str, dict[str, Any]] = {}
    for name, tex in (textures or {}).items():
        licence = tex.get("licence")
        if not isinstance(licence, Mapping) or not licence.get("spdx") or not licence.get("licence_class"):
            raise BakeError(f"texture {name!r} has no licence record (SPDX id and licence class)", name)
        body = tex.get("png") if tex.get("png") is not None else tex.get("jpeg")
        uri = tex.get("uri")
        if body is not None:
            data = bytes(body)
            png = tex.get("png") is not None
            if not data.startswith(PNG_MAGIC if png else JPEG_MAGIC):
                raise BakeError(f"texture {name!r} is not a valid {'PNG' if png else 'JPEG'} file", name)
            out[name] = {"data": data, "mime": "image/png" if png else "image/jpeg", "licence": dict(licence)}
        elif (
            isinstance(uri, str)
            and uri
            and "\\" not in uri
            and not uri.startswith("/")
            and ":" not in uri.split("/")[0]
        ):
            out[name] = {"uri": uri, "mime": str(tex.get("mime") or "image/jpeg"), "licence": dict(licence)}
        else:
            raise BakeError(f"texture {name!r} has neither an image body nor a relative URI", name)
    return out


# ----------------------------------------------------------------------------------------------------------------------
# GLB writer
# ----------------------------------------------------------------------------------------------------------------------


def enu_to_gltf(points: np.ndarray) -> np.ndarray:
    """Site frame (x east, y north, z up) to glTF (x, y up, z): (x, y, z) -> (x, z, -y), a proper rotation.

    The winding of a triangle is kept.

    A 3D Tiles viewer turns glTF Y-up into the tileset's Z-up frame with (x, y, z) -> (x, -z, y), so a tile baked this
    way
    sits in the site frame without a tile transform.
    """
    p = np.asarray(points)
    return np.stack([p[..., 0], p[..., 2], -p[..., 1]], axis=-1)


def _pad4(data: bytes, fill: bytes = b"\x00") -> bytes:
    return data + fill * (-len(data) % 4)


class _Binary:
    """The BIN chunk and its buffer views, every view 4-byte aligned."""

    def __init__(self) -> None:
        self.chunks: list[bytes] = []
        self.size = 0
        self.views: list[dict[str, Any]] = []

    def view(
        self, data: bytes, *, target: int | None = None, stride: int | None = None, name: str | None = None
    ) -> int:
        offset = self.size
        padded = _pad4(data)
        self.chunks.append(padded)
        self.size += len(padded)
        entry: dict[str, Any] = {"buffer": 0, "byteOffset": offset, "byteLength": len(data)}
        if stride:
            entry["byteStride"] = stride
        if target:
            entry["target"] = target
        if name:
            entry["name"] = name
        self.views.append(entry)
        return len(self.views) - 1

    def bytes(self) -> bytes:
        return b"".join(self.chunks)


def _pack_rows(rows: np.ndarray, stride: int) -> bytes:
    """Rows of a 2-D array padded with zero bytes to `stride` bytes (glTF aligns each vertex element to 4 bytes)."""
    flat = np.ascontiguousarray(rows)
    width = flat.shape[1] * flat.dtype.itemsize
    out = np.zeros((flat.shape[0], stride), dtype=np.uint8)
    out[:, :width] = flat.view(np.uint8).reshape(flat.shape[0], width)
    return out.tobytes()


def _glb_container(doc: dict[str, Any], binary: bytes) -> bytes:
    js = _pad4(json.dumps(doc, separators=(",", ":"), sort_keys=False).encode(), b" ")
    body = struct.pack("<I4s", len(js), b"JSON") + js
    if binary:
        body += struct.pack("<I4s", len(binary), b"BIN\x00") + binary
    return struct.pack("<4sII", b"glTF", 2, 12 + len(body)) + body


def _build_glb(mesh: Mapping[str, Any], textures: dict[str, dict[str, Any]]) -> tuple[bytes, dict[str, Any]]:
    name, vertices, indices, normals, uvs = _guard_mesh(mesh)
    quantize = bool(mesh.get("quantize"))
    binary = _Binary()
    accessors: list[dict[str, Any]] = []
    attributes: dict[str, int] = {}
    node: dict[str, Any] = {"mesh": 0, "name": name}
    extensions_used: list[str] = []

    lo, hi = vertices.min(axis=0).astype(np.float64), vertices.max(axis=0).astype(np.float64)
    if quantize:
        center, half = (lo + hi) / 2.0, np.maximum((hi - lo) / 2.0, 1e-6)
        q = np.rint((vertices.astype(np.float64) - center) / half * 32767.0).astype(np.int16)
        node["translation"] = [float(c) for c in center]
        node["scale"] = [float(h / 32767.0) for h in half]
        pos_view = binary.view(_pack_rows(q, 8), target=ARRAY_BUFFER, stride=8, name="POSITION")
        accessors.append(
            {
                "bufferView": pos_view,
                "componentType": SHORT,
                "count": len(q),
                "type": "VEC3",
                "min": [int(v) for v in q.min(axis=0)],
                "max": [int(v) for v in q.max(axis=0)],
            }
        )
        extensions_used.append("KHR_mesh_quantization")
    else:
        view = binary.view(np.ascontiguousarray(vertices, dtype="<f4").tobytes(), target=ARRAY_BUFFER, name="POSITION")
        accessors.append(
            {
                "bufferView": view,
                "componentType": FLOAT,
                "count": len(vertices),
                "type": "VEC3",
                "min": [float(v) for v in vertices.min(axis=0)],
                "max": [float(v) for v in vertices.max(axis=0)],
            }
        )
    attributes["POSITION"] = 0

    if normals is not None:
        unit = normals / np.maximum(np.linalg.norm(normals, axis=1, keepdims=True), 1e-12)
        if quantize:
            q16 = np.rint(np.clip(unit, -1.0, 1.0) * 32767.0).astype(np.int16)
            view = binary.view(_pack_rows(q16, 8), target=ARRAY_BUFFER, stride=8, name="NORMAL")
            accessors.append(
                {"bufferView": view, "componentType": SHORT, "normalized": True, "count": len(q16), "type": "VEC3"}
            )
        else:
            view = binary.view(np.ascontiguousarray(unit, dtype="<f4").tobytes(), target=ARRAY_BUFFER, name="NORMAL")
            accessors.append({"bufferView": view, "componentType": FLOAT, "count": len(unit), "type": "VEC3"})
        attributes["NORMAL"] = len(accessors) - 1

    if uvs is not None:
        if quantize:
            if uvs.min() < 0.0 or uvs.max() > 1.0:
                raise BakeError("texture coordinates must lie in [0, 1] to be quantized", name)
            qu = np.rint(uvs * 65535.0).astype("<u2")
            view = binary.view(np.ascontiguousarray(qu).tobytes(), target=ARRAY_BUFFER, name="TEXCOORD_0")
            accessors.append(
                {
                    "bufferView": view,
                    "componentType": UNSIGNED_SHORT,
                    "normalized": True,
                    "count": len(qu),
                    "type": "VEC2",
                }
            )
        else:
            view = binary.view(np.ascontiguousarray(uvs, dtype="<f4").tobytes(), target=ARRAY_BUFFER, name="TEXCOORD_0")
            accessors.append({"bufferView": view, "componentType": FLOAT, "count": len(uvs), "type": "VEC2"})
        attributes["TEXCOORD_0"] = len(accessors) - 1

    wide = len(vertices) > 65535
    index_data = indices.astype("<u4" if wide else "<u2").ravel()
    view = binary.view(index_data.tobytes(), target=ELEMENT_ARRAY_BUFFER, name="indices")
    accessors.append(
        {
            "bufferView": view,
            "componentType": UNSIGNED_INT if wide else UNSIGNED_SHORT,
            "count": int(index_data.size),
            "type": "SCALAR",
        }
    )
    primitive: dict[str, Any] = {"attributes": attributes, "indices": len(accessors) - 1, "mode": 4}

    images: list[dict[str, Any]] = []
    gl_textures: list[dict[str, Any]] = []
    samplers: list[dict[str, Any]] = []
    tex_index: dict[str, int] = {}
    licences: dict[str, Any] = {}
    material_spec: Mapping[str, Any] = mesh["material"] if isinstance(mesh.get("material"), Mapping) else {}
    bound = {n for n in (material_spec.get("base_color"), material_spec.get("normal")) if n}
    if uvs is not None and bound:
        for tname in sorted(bound):
            if tname not in textures:
                raise BakeError(f"the material names texture {tname!r}, which was not given", name)
    for tname in sorted(textures):
        tex = textures[tname]
        licences[tname] = tex["licence"]
        if uvs is None or tname not in bound:
            continue  # without texture coordinates or a material slot a texture would only be an unused object
        image: dict[str, Any] = {"name": tname, "mimeType": tex["mime"], "extras": {"licence": tex["licence"]}}
        if "data" in tex:
            image["bufferView"] = binary.view(tex["data"], name=f"image {tname}")
        else:
            image["uri"] = tex["uri"]
        images.append(image)
        repeat = tname == material_spec.get("normal")
        samplers.append(
            {
                "magFilter": LINEAR,
                "minFilter": LINEAR_MIPMAP_LINEAR,
                "wrapS": REPEAT if repeat else CLAMP_TO_EDGE,
                "wrapT": REPEAT if repeat else CLAMP_TO_EDGE,
            }
        )
        gl_textures.append({"name": tname, "sampler": len(samplers) - 1, "source": len(images) - 1})
        tex_index[tname] = len(gl_textures) - 1

    material: dict[str, Any] | None = None
    if tex_index:
        pbr: dict[str, Any] = {
            "metallicFactor": float(material_spec.get("metallic", 0.0)),
            "roughnessFactor": float(material_spec.get("roughness", 0.85)),
        }
        material = {
            "name": str(material_spec.get("name") or f"{name}-material"),
            "pbrMetallicRoughness": pbr,
            "doubleSided": False,
        }
        if material_spec.get("base_color"):
            pbr["baseColorTexture"] = {"index": tex_index[material_spec["base_color"]], "texCoord": 0}
        if material_spec.get("normal"):
            normal_ref: dict[str, Any] = {"index": tex_index[material_spec["normal"]], "texCoord": 0}
            tr = material_spec.get("normal_transform")
            if tr:
                normal_ref["extensions"] = {
                    "KHR_texture_transform": {
                        "offset": [float(v) for v in tr["offset"]],
                        "scale": [float(v) for v in tr["scale"]],
                    }
                }
                extensions_used.append("KHR_texture_transform")
            material["normalTexture"] = normal_ref
        primitive["material"] = 0

    doc: dict[str, Any] = {
        "asset": {"version": "2.0", "generator": "pitstudio web bake (s60_export)"},
        "scene": 0,
        "scenes": [{"nodes": [0]}],
        "nodes": [node],
        "meshes": [{"name": name, "primitives": [primitive]}],
        "accessors": accessors,
        "bufferViews": binary.views,
        "buffers": [{"byteLength": binary.size}],
    }
    extras = dict(mesh.get("extras") or {})
    if licences:
        extras["textures"] = licences
    if extras:
        doc["asset"]["extras"] = extras
    if extensions_used:
        doc["extensionsUsed"] = sorted(set(extensions_used))
        if "KHR_mesh_quantization" in extensions_used:
            doc["extensionsRequired"] = ["KHR_mesh_quantization"]
    if material is not None:
        doc["materials"] = [material]
        doc["images"], doc["textures"], doc["samplers"] = images, gl_textures, samplers
    return _glb_container(doc, binary.bytes()), {"vertices": vertices, "extent": (lo, hi)}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _check(report: ValidatorReport, asset: str, what: str) -> None:
    if report.errors:
        raise BakeError(f"{what} failed validation: {report.errors[0]}", asset)


def bake_glb(
    mesh: Mapping[str, Any],
    out_path: Path,
    *,
    textures: Mapping[str, Mapping[str, Any]] | None = None,
    validator: Callable[[Path], ValidatorReport] | None = None,
) -> BakeResult:
    """Writes `out_path` as a glTF 2.0 binary only when every guard and the validator pass (FR-016-19, FR-016-37).

    `mesh` holds `name`, `vertices` (n, 3) and `indices` (m, 3) and optionally `normals` (n, 3), `texcoords` (n, 2) in
    [0, 1],
    `quantize` (KHR_mesh_quantization: int16 positions under the node transform, int16 normals, uint16 texture
    coordinates),
    `material` (`base_color` and `normal` name entries of `textures`, `normal_transform` {scale, offset} as
    KHR_texture_transform, `roughness`, `metallic`) and `extras` (copied into the asset). `textures` maps a name to
    {"png" | "jpeg": bytes, or "uri": a relative URI, "licence": {"spdx", "licence_class", ...}}; every texture needs
    its
    licence record, which is written into the file next to the image. Raises `BakeError` and leaves no file behind.
    """
    out_path = Path(out_path)
    guarded = _guard_textures(textures)
    data, _ = _build_glb(mesh, guarded)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    try:
        out_path.write_bytes(data)
        report = (validator or validate_glb)(out_path)
        _check(report, str(mesh.get("name") or out_path.name), "the glTF binary")
    except BaseException:
        out_path.unlink(missing_ok=True)
        raise
    return BakeResult(path=out_path, bytes=len(data), sha256=_sha256(data), validator=report)


# ----------------------------------------------------------------------------------------------------------------------
# 3D Tiles
# ----------------------------------------------------------------------------------------------------------------------


def _tile_json(
    tile: Mapping[str, Any], out_dir: Path, written: list[Path], results: list[BakeResult], glb_validator: Any
) -> dict:
    name = str(tile["name"])
    box = [float(v) for v in tile["bounding_box"]]
    if len(box) != 12 or not all(math.isfinite(v) for v in box):
        raise BakeError("a tile bounding box needs 12 finite numbers", name)
    error = float(tile.get("geometric_error", 0.0))
    if not math.isfinite(error) or error < 0:
        raise BakeError("a tile geometric error must be finite and not negative", name)
    node: dict[str, Any] = {
        "boundingVolume": {"box": box},
        "geometricError": error,
        "refine": str(tile.get("refine", "REPLACE")),
    }
    if tile.get("content_uri"):
        node["content"] = {
            "uri": str(tile["content_uri"])
        }  # a file baked by another call (not written or validated here)
    elif tile.get("mesh") is not None:
        rel = str(tile.get("path") or f"{name}.glb")
        glb = out_dir / rel
        written.append(glb)
        result = bake_glb(tile["mesh"], glb, textures=tile.get("textures"), validator=glb_validator)
        results.append(result)
        node["content"] = {"uri": rel.replace(os.sep, "/")}
    children = [_tile_json(c, out_dir, written, results, glb_validator) for c in tile.get("children", [])]
    if children:
        node["children"] = children
    return node


def _union_box(boxes: Sequence[Sequence[float]]) -> list[float]:
    lo = np.min([[b[0] - abs(b[3]), b[1] - abs(b[7]), b[2] - abs(b[11])] for b in boxes], axis=0)
    hi = np.max([[b[0] + abs(b[3]), b[1] + abs(b[7]), b[2] + abs(b[11])] for b in boxes], axis=0)
    c, h = np.asarray((lo + hi) / 2.0), np.asarray((hi - lo) / 2.0)
    return [float(c[0]), float(c[1]), float(c[2]), float(h[0]), 0.0, 0.0, 0.0, float(h[1]), 0.0, 0.0, 0.0, float(h[2])]


def bake_tileset(
    tiles: Sequence[Mapping[str, Any]],
    out_dir: Path,
    *,
    glb_validator: Callable[[Path], ValidatorReport] | None = None,
    validator: Callable[[Path], ValidatorReport] | None = None,
    geometric_error: float | None = None,
) -> BakeResult:
    """Writes `<out_dir>/tileset.json` (3D Tiles 1.1) and the GLB content of every tile, then validates each GLB and the
    tileset.

    A tile is {"name", "mesh", "bounding_box" (12 numbers), "geometric_error"} and optionally `textures`, `path` (the
    GLB path
    under `out_dir`, default `<name>.glb`), `content_uri` (content baked elsewhere, written as given), `refine` and
    `children`
    (tiles of the same form: the levels of a hierarchical LOD). One tile is the root; several tiles hang under a root
    without
    content that holds their union. Any guard or validator error raises `BakeError`, removes every file written by the
    call and
    leaves no tileset file.
    """
    out_dir = Path(out_dir)
    if not tiles:
        raise BakeError("a tileset needs at least one tile", str(out_dir))
    out_dir.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    results: list[BakeResult] = []
    tileset_path = out_dir / "tileset.json"
    try:
        nodes = [_tile_json(t, out_dir, written, results, glb_validator) for t in tiles]
        if len(nodes) == 1:
            root = nodes[0]
        else:
            boxes = [n["boundingVolume"]["box"] for n in nodes]
            root = {
                "boundingVolume": {"box": _union_box(boxes)},
                "geometricError": float(
                    geometric_error if geometric_error is not None else max(n["geometricError"] for n in nodes)
                ),
                "refine": "REPLACE",
                "children": nodes,
            }
        top = float(geometric_error) if geometric_error is not None else float(root["geometricError"])
        doc = {"asset": {"version": "1.1"}, "geometricError": top, "root": root}
        text = json.dumps(doc, separators=(",", ":")) + "\n"
        tileset_path.write_text(text, encoding="utf-8", newline="\n")
        report = (validator or validate_tileset)(tileset_path)
        _check(report, str(tileset_path), "the 3D Tiles tileset")
    except BaseException:
        tileset_path.unlink(missing_ok=True)
        for f in written:
            f.unlink(missing_ok=True)
        raise
    data = tileset_path.read_bytes()
    return BakeResult(path=tileset_path, bytes=len(data), sha256=_sha256(data), validator=report, children=results)


# ----------------------------------------------------------------------------------------------------------------------
# shards
# ----------------------------------------------------------------------------------------------------------------------


def _shard_header(items: Sequence[tuple[str, bytes]]) -> bytes:
    head = SHARD_MAGIC + struct.pack("<II", 1, len(items))
    for name, data in items:
        raw = name.encode("utf-8")
        head += struct.pack("<H", len(raw)) + raw + struct.pack("<Q", len(data))
    return head


def pack_shards(
    items: Sequence[tuple[str, bytes]], out_dir: Path, *, cap_bytes: int = DEFAULT_SHARD_CAP
) -> list[ShardInfo]:
    """Packs named byte items, in order, into shard files of at most `cap_bytes` (FR-016-19).

    A shard is `PSHD`, a version and an item count (little endian), one (name length, name, byte length) row per item,
    then the
    item bodies in the same order. Items fill a shard until the next one would not fit; every item is in exactly one
    shard and
    an item that cannot fit in a shard of its own raises `BakeError`. The files are named `shard-0000.bin`, ...
    """
    out_dir = Path(out_dir)
    groups: list[list[tuple[str, bytes]]] = []
    current: list[tuple[str, bytes]] = []
    for name, data in items:
        if len(_shard_header([(name, data)])) + len(data) > cap_bytes:
            raise BakeError(f"item {name!r} of {len(data)} bytes does not fit a shard of {cap_bytes} bytes", name)
        candidate = [*current, (name, data)]
        if current and len(_shard_header(candidate)) + sum(len(d) for _, d in candidate) > cap_bytes:
            groups.append(current)
            candidate = [(name, data)]
        current = candidate
    if current:
        groups.append(current)
    out_dir.mkdir(parents=True, exist_ok=True)
    shards: list[ShardInfo] = []
    for i, group in enumerate(groups):
        blob = _shard_header(group) + b"".join(d for _, d in group)
        path = out_dir / f"shard-{i:04d}.bin"
        path.write_bytes(blob)
        shards.append(ShardInfo(path=path, bytes=len(blob), sha256=_sha256(blob), members=[n for n, _ in group]))
    return shards


__all__ = [
    "BakeError",
    "BakeResult",
    "ShardInfo",
    "ValidatorReport",
    "ValidatorUnavailable",
    "bake_glb",
    "bake_tileset",
    "enu_to_gltf",
    "pack_shards",
    "validate_glb",
    "validate_tileset",
    "web_dir",
]
