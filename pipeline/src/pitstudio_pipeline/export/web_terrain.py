# SPDX-License-Identifier: Apache-2.0
"""Web bake of the Bingham Canyon terrain: the exchange folder of `pitstudio_studio.scene.web_terrain` to a validated
3D Tiles
set (FR-016-19, FR-016-37, FR-004-48, FR-004-49; ADR-0038).

Two tilesets come out, both in the site frame (x east, y north, z up, metres) with glTF 2.0 binary tiles:

    tiles/lod0/tileset.json         the first view: one whole-site tile (web LOD-0, derived from the scene's `lod2`
    variant)
    tiles/detail/tileset.json       the same root tile and, after a user action, two refinement levels (HLOD, REPLACE):
                                    web LOD-1 = the scene `lod2` tiles and web LOD-2 = the scene `lod1` tiles, merged in
                                    groups of `group` x `group` scene tiles (one file per group, one texture per file)
    tiles/textures/rock-normal.jpg  the arid rock normal map of the scene (CC0), shared by every tile through a
    relative URI

The scene's finest variant (`lod0`, 0.25 m, 4.5 million triangles) is not baked: the orthophoto has 1 m ground
samples after
the scene resamples it onto the DEM grid, and the tile budget of ADR-0038 is 95 MB. The albedo of every tile is a
crop of the
scene orthophoto (NAIP 2018, public domain), the normal map repeats every 8 m through KHR_texture_transform, and every
texture carries its licence record inside the file (FR-016-37).
"""

from __future__ import annotations

import hashlib
import io
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
from PIL import Image

from pitstudio_pipeline.export.web_bake import (
    BakeError,
    BakeResult,
    ValidatorReport,
    bake_tileset,
    enu_to_gltf,
)

GROUP = 3
ROOT_TEXTURE_PX = 1024
LEVEL_TEXTURE_SCALE = {1: 0.5, 2: 1.0}  # ground samples of the crop per orthophoto sample: LOD-1 half, LOD-2 full
JPEG_QUALITY = {0: 80, 1: 78, 2: 85}
ROCK_NORMAL_PX = 512
BOX_PAD_M = 0.5
BUDGET_CLASS = "tiles-glb"
LICENCES = {
    "usda-naip-bingham": {
        "spdx": "LicenseRef-USGov-PD",
        "licence_class": "public-domain",
        "source": "usda-naip-bingham",
    },
    "polyhaven-rock-boulder-dry": {
        "spdx": "CC0-1.0",
        "licence_class": "open-no-attribution",
        "source": "polyhaven-rock-boulder-dry",
    },
}


@dataclass
class _Group:
    key: tuple[int, int]
    ids: list[str]
    positions: np.ndarray
    indices: np.ndarray
    normals: np.ndarray
    st: np.ndarray


def _load(path: Path) -> dict[str, np.ndarray]:
    with np.load(path) as z:
        return {k: z[k] for k in z.files}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.convert("RGB").save(buffer, format="JPEG", quality=quality, subsampling=2, optimize=False, progressive=False)
    return buffer.getvalue()


def _box(positions: np.ndarray) -> list[float]:
    lo, hi = positions.min(axis=0).astype(np.float64) - BOX_PAD_M, positions.max(axis=0).astype(np.float64) + BOX_PAD_M
    c, h = (lo + hi) / 2.0, (hi - lo) / 2.0
    return [float(c[0]), float(c[1]), float(c[2]), float(h[0]), 0.0, 0.0, 0.0, float(h[1]), 0.0, 0.0, 0.0, float(h[2])]


def _fit(values: np.ndarray, coords: np.ndarray) -> tuple[float, float]:
    """`coords = a * values + b` by least squares; the scene's st_ortho is exactly affine in the site position."""
    a, b = np.polyfit(values.astype(np.float64), coords.astype(np.float64), 1)
    residual = float(np.abs(a * values + b - coords).max())
    if residual > 1e-5:
        raise BakeError(f"st_ortho is not affine in the site position (residual {residual:.2e})", "web-bake-input")
    return float(a), float(b)


def _groups(level: dict[str, Any], root: Path, group: int) -> list[_Group]:
    buckets: dict[tuple[int, int], list[dict[str, Any]]] = {}
    for tile in level["tiles"]:
        buckets.setdefault((tile["x"] // group, tile["y"] // group), []).append(tile)
    out: list[_Group] = []
    for key in sorted(buckets):
        parts = [(t["id"], _load(root / t["file"])) for t in sorted(buckets[key], key=lambda t: t["id"])]
        offsets = np.cumsum([0] + [len(p["positions"]) for _, p in parts])[:-1]
        out.append(
            _Group(
                key=key,
                ids=[i for i, _ in parts],
                positions=np.concatenate([p["positions"] for _, p in parts]),
                indices=np.concatenate(
                    [p["indices"].astype(np.int64) + o for (_, p), o in zip(parts, offsets, strict=True)]
                ),
                normals=np.concatenate([p["normals"] for _, p in parts]),
                st=np.concatenate([p["st_ortho"] for _, p in parts]),
            )
        )
    return out


def _mesh(
    name: str, positions: np.ndarray, indices: np.ndarray, normals: np.ndarray, uv: np.ndarray, extras: dict
) -> dict:
    """A glTF-frame mesh (Y up) of site-frame arrays; `uv` are image coordinates already (origin top left)."""
    return {
        "name": name,
        "vertices": enu_to_gltf(positions).astype(np.float32),
        "indices": np.asarray(indices, dtype=np.int64),
        "normals": enu_to_gltf(normals).astype(np.float32),
        "texcoords": np.clip(uv, 0.0, 1.0).astype(np.float32),
        "quantize": True,
        "extras": extras,
    }


def _crop(
    ortho: Image.Image, st: np.ndarray, scale: float, quality: int
) -> tuple[bytes, np.ndarray, tuple[int, int, int, int]]:
    """The orthophoto crop under the texture coordinates of a tile, its JPEG and the coordinates inside the crop."""
    w, h = ortho.size
    u, v = st[:, 0].astype(np.float64), st[:, 1].astype(np.float64)
    x0, x1 = int(np.floor(u.min() * w)), int(np.ceil(u.max() * w))
    y0, y1 = int(np.floor((1.0 - v.max()) * h)), int(np.ceil((1.0 - v.min()) * h))
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, w), min(y1, h)
    crop = ortho.crop((x0, y0, x1, y1))
    if scale != 1.0:
        crop = crop.resize(
            (max(8, round(crop.width * scale)), max(8, round(crop.height * scale))), Image.Resampling.LANCZOS
        )
    uv = np.stack([(u * w - x0) / (x1 - x0), ((1.0 - v) * h - y0) / (y1 - y0)], axis=1)
    return _jpeg(crop, quality), uv, (x0, y0, x1, y1)


def _normal_transform(
    box: tuple[int, int, int, int],
    size: tuple[int, int],
    fit_u: tuple[float, float],
    fit_v: tuple[float, float],
    repeat_m: float,
) -> dict[str, list[float]]:
    """KHR_texture_transform that lays the rock normal map on the tile, `repeat_m` metres per repeat, world aligned.

    A texture coordinate (u', v') of the crop is a position (x, y) of the site; the rock coordinate is x / repeat and
    -y / repeat
    (the sign keeps the image orientation of the albedo, so the tangent frame is not mirrored). The offsets are reduced
    modulo 1 because the sampler repeats.
    """
    w, h = size
    x0, y0, x1, y1 = box
    (a, b), (c, d) = fit_u, fit_v
    sx = (x1 - x0) / (w * a * repeat_m)
    ox = (x0 / w - b) / (a * repeat_m)
    sy = (y1 - y0) / (h * c * repeat_m)
    oy = (y0 / h - 1.0 + d) / (c * repeat_m)
    return {"scale": [sx, sy], "offset": [ox % 1.0, oy % 1.0]}


def _tile(
    name: str,
    path: str,
    positions: np.ndarray,
    indices: np.ndarray,
    normals: np.ndarray,
    uv: np.ndarray,
    jpeg: bytes,
    transform: dict,
    error: float,
    extras: dict,
) -> dict:
    albedo = {"jpeg": jpeg, "licence": LICENCES["usda-naip-bingham"]}
    rock = {
        "uri": "../../textures/rock-normal.jpg" if "/" in path else "../textures/rock-normal.jpg",
        "licence": LICENCES["polyhaven-rock-boulder-dry"],
    }
    mesh = _mesh(name, positions, indices, normals, uv, extras)
    mesh["material"] = {
        "base_color": "albedo",
        "normal": "rock-normal",
        "normal_transform": transform,
        "name": "terrain-ortho",
    }
    return {
        "name": name,
        "path": path,
        "mesh": mesh,
        "textures": {"albedo": albedo, "rock-normal": rock},
        "bounding_box": _box(positions),
        "geometric_error": error,
    }


def bake_terrain(
    exchange: Path,
    out_dir: Path,
    *,
    group: int = GROUP,
    glb_validator: Any = None,
    validator: Any = None,
) -> dict[str, Any]:
    """Bakes the exchange folder into `out_dir` (see the module text) and returns the bake report (also written as
    `tiles/bake-report.json`). Raises `BakeError` and leaves no tileset when a guard or a validator refuses a tile."""
    exchange, out_dir = Path(exchange), Path(out_dir)
    try:
        doc = json.loads((exchange / "web-bake-input.json").read_text(encoding="utf-8"))
    except OSError, ValueError:
        raise BakeError("web-bake-input.json is missing or not JSON", str(exchange)) from None
    if doc.get("kind") != "web-terrain-input":
        raise BakeError("the exchange folder is not a web terrain input", str(exchange))
    for key in ("albedo", "rock_normal"):
        if _sha(exchange / doc[key]["file"]) != doc[key]["sha256"]:
            raise BakeError(f"{doc[key]['file']} differs from the digest in web-bake-input.json", doc[key]["file"])
    ortho = Image.open(exchange / doc["albedo"]["file"])
    ortho.load()
    w, h = ortho.size
    if (w, h) != (doc["albedo"]["width"], doc["albedo"]["height"]):
        raise BakeError("the orthophoto size differs from web-bake-input.json", doc["albedo"]["file"])
    repeat_m = float(doc["rock_normal"]["repeat_m"])

    root_arrays = _load(exchange / doc["root"]["file"])
    fit_u = _fit(root_arrays["positions"][:, 0], root_arrays["st_ortho"][:, 0])
    fit_v = _fit(root_arrays["positions"][:, 1], root_arrays["st_ortho"][:, 1])
    extras = {
        "scene": doc["scene"]["manifest_id"],
        "sources": ["usgs-3dep-bingham", doc["albedo"]["source"], doc["rock_normal"]["source"]],
        "frame": "site-enu (x east, y north, z up, metres); glTF Y up, 3D Tiles converts back",
    }

    out_tiles = out_dir / "tiles"
    textures_dir = out_tiles / "textures"
    textures_dir.mkdir(parents=True, exist_ok=True)
    rock = Image.open(exchange / doc["rock_normal"]["file"])
    rock.load()
    (textures_dir / "rock-normal.jpg").write_bytes(
        _jpeg(rock.resize((ROCK_NORMAL_PX, ROCK_NORMAL_PX), Image.Resampling.LANCZOS), 85)
    )

    # web LOD-0: the whole-site tile with the whole orthophoto at ROOT_TEXTURE_PX
    root_img = ortho.resize((ROOT_TEXTURE_PX, round(ROOT_TEXTURE_PX * h / w)), Image.Resampling.LANCZOS)
    root_uv = np.stack([root_arrays["st_ortho"][:, 0], 1.0 - root_arrays["st_ortho"][:, 1]], axis=1)
    full = (0, 0, w, h)
    root_tile = _tile(
        "lod0",
        "lod0.glb",
        root_arrays["positions"],
        root_arrays["indices"],
        root_arrays["normals"],
        root_uv,
        _jpeg(root_img, JPEG_QUALITY[0]),
        _normal_transform(full, (w, h), fit_u, fit_v, repeat_m),
        float(doc["root"]["error_m"]),
        {**extras, "level": "web LOD-0", "error_m": doc["root"]["error_m"]},
    )
    lod0 = bake_tileset([root_tile], out_tiles / "lod0", glb_validator=glb_validator, validator=validator)

    # web LOD-1 and LOD-2: groups of scene tiles under the same root content
    levels = {lv["lod"]: lv for lv in doc["levels"]}
    coarse, fine = levels[2], levels[1]
    coarse_groups = {g.key: g for g in _groups(coarse, exchange, group)}
    fine_groups = {g.key: g for g in _groups(fine, exchange, group)}
    if coarse_groups.keys() != fine_groups.keys():
        raise BakeError("the scene LODs do not cover the same tile groups", "web-bake-input")
    children = []
    for gkey in sorted(coarse_groups):
        gx, gy = gkey
        built = []
        for web_level, grp, scene_error in (
            (1, coarse_groups[gkey], coarse["max_error_m"]),
            (2, fine_groups[gkey], fine["max_error_m"]),
        ):
            jpeg, uv, box = _crop(ortho, grp.st, LEVEL_TEXTURE_SCALE[web_level], JPEG_QUALITY[web_level])
            built.append(
                _tile(
                    f"l{web_level}-{gx}-{gy}",
                    f"lod{web_level}/l{web_level}-{gx}-{gy}.glb",
                    grp.positions,
                    grp.indices,
                    grp.normals,
                    uv,
                    jpeg,
                    _normal_transform(box, (w, h), fit_u, fit_v, repeat_m),
                    float(scene_error),
                    {**extras, "level": f"web LOD-{web_level}", "scene_tiles": grp.ids, "error_m": scene_error},
                )
            )
        built[0]["children"] = [built[1]]
        children.append(built[0])
    root_ref = {
        "name": "root",
        "content_uri": "../lod0/lod0.glb",
        "bounding_box": _box(np.concatenate([g.positions for g in coarse_groups.values()])),
        "geometric_error": float(doc["root"]["error_m"]),
        "children": children,
    }
    detail = bake_tileset([root_ref], out_tiles / "detail", glb_validator=glb_validator, validator=validator)
    return _report(doc, out_tiles, lod0, detail, group)


def _entry(path: Path, base: Path, result: BakeResult | None = None, **extra: Any) -> dict[str, Any]:
    data = path.read_bytes()
    row: dict[str, Any] = {
        "path": path.relative_to(base).as_posix(),
        "bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
        **extra,
    }
    if result is not None:
        row["validator"] = {"errors": len(result.validator.errors), "warnings": list(result.validator.warnings)}
    return row


def _report(doc: dict[str, Any], out_tiles: Path, lod0: BakeResult, detail: BakeResult, group: int) -> dict[str, Any]:
    files = [
        _entry(lod0.path, out_tiles.parent, lod0, role="tileset", level="lod0"),
        *[_entry(r.path, out_tiles.parent, r, role="tile", level="lod0") for r in lod0.children],
        _entry(detail.path, out_tiles.parent, detail, role="tileset", level="detail"),
        *[
            _entry(r.path, out_tiles.parent, r, role="tile", level="lod1" if "/lod1/" in r.path.as_posix() else "lod2")
            for r in detail.children
        ],
        _entry(out_tiles / "textures" / "rock-normal.jpg", out_tiles.parent, role="texture", level="shared"),
    ]
    total = sum(f["bytes"] for f in files)
    report = {
        "kind": "web-terrain-bake",
        "schema_version": "1.0",
        "scene": doc["scene"],
        "producer": doc["producer"],
        "level_scheme": {
            "web_lod0": f"one whole-site tile derived from the scene lod{doc['root']['derived_from_lod']} variant, "
            f"{doc['root']['triangles']} triangles, error {doc['root']['error_m']} m against the elevation model",
            "web_lod1": f"the scene lod2 tiles ({doc['levels'][0]['max_error_m']} m), {group} x {group} tiles per file",
            "web_lod2": f"the scene lod1 tiles ({doc['levels'][1]['max_error_m']} m), {group} x {group} tiles per file",
            "not_baked": "the scene lod0 variant (0.25 m): the orthophoto has 1 m samples, the tile budget is 95 MB",
        },
        "textures": {
            "albedo": {k: doc["albedo"][k] for k in ("source", "year", "ground_resolution_m", "sha256")},
            "rock_normal": {k: doc["rock_normal"][k] for k in ("source", "spdx", "repeat_m", "sha256")},
        },
        "files": files,
        "totals": {
            "files": len(files),
            "bytes": total,
            "validator_errors": sum(f.get("validator", {}).get("errors", 0) for f in files),
            "validator_warnings": sum(len(f.get("validator", {}).get("warnings", [])) for f in files),
        },
    }
    (out_tiles / "bake-report.json").write_text(json.dumps(report, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main(argv: list[str] | None = None) -> int:
    """`python -m pitstudio_pipeline.export.web_terrain --exchange <dir> --out <dir>`; exit 0, or 1 when refused."""
    import argparse

    parser = argparse.ArgumentParser(description="Bake the exchange folder of the web terrain into 3D Tiles.")
    parser.add_argument("--exchange", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--group", type=int, default=GROUP)
    args = parser.parse_args(argv)
    try:
        report = bake_terrain(args.exchange, args.out, group=args.group)
    except BakeError as e:
        print(f"web-terrain: refused {e.asset}: {e.reason}")
        return 1
    t = report["totals"]
    print(
        f"web-terrain: {t['files']} files, {t['bytes']} bytes, validator errors {t['validator_errors']}, "
        f"warnings {t['validator_warnings']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["ValidatorReport", "bake_terrain", "main"]
