"""The OpenUSD side of the web bake of the terrain (FR-016-19, ADR-0038): reads the composed scene and writes plain
arrays.

The web bake has two halves because the two environments do not overlap: this module runs in the studio environment (it
opens `terrain.usdc` with `pxr`), `pitstudio_pipeline.export.web_terrain` runs in the pipeline environment (it
writes the
glTF and 3D Tiles files and runs the reference validators). They meet in an exchange folder:

    web-bake-input.json            provenance, extent, levels and tile list (this module writes it)
    levels/root.npz                the coarse whole-site mesh derived from the scene's coarsest `lod` variant
    levels/lod<N>/<tile id>.npz    the tile meshes of a `lod` variant, as authored (positions, indices, normals,
    st_ortho)
    ortho.jpg, rock-normal.jpg     the orthophoto albedo and the rock normal map of the scene, copied unchanged

Frames: positions stay in the site frame of the scene (x east, y north, z up, metres). Nothing is invented: the
tile meshes,
normals and `st_ortho` coordinates are the authored values; only the coarse root is computed here, by sampling the
coarsest
authored LOD on a regular grid and meshing it with the scene's own RTIN builder, so its error against that LOD is
at most
`root_error_m` (and against the elevation model at most `root_error_m` plus the LOD's own `max_error_m`).
"""

from __future__ import annotations

import hashlib
import json
import shutil
from importlib import metadata
from pathlib import Path
from typing import Any

import numpy as np

from pitstudio_studio.scene.assets.build import ROCK_REPEAT_M
from pitstudio_studio.scene.terrain import rtin

ROOT_GRID = 513  # (2^9 + 1) samples per side for the RTIN of the coarse root
DEFAULT_ROOT_ERROR_M = 8.0
TERRAIN_LAYER = Path("layers") / "terrain.usdc"
ORTHO = Path("terrain") / "albedo" / "ortho.jpg"
ROCK_NORMAL = Path("assets") / "textures" / "bench_rock_normal.jpg"


class WebTerrainError(Exception):
    """The scene cannot be read for the web bake: the message says which input is missing or inconsistent."""


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def _read_manifest(scene: Path) -> dict[str, Any]:
    path = scene / "scene.manifest.json"
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except OSError, ValueError:
        raise WebTerrainError(f"{path.name} is missing or not JSON in the scene folder") from None
    if doc.get("kind") != "scene-manifest":
        raise WebTerrainError("scene.manifest.json is not a scene manifest")
    return doc


def _check_digest(scene: Path, relative: Path, expected: str | None, what: str) -> str:
    path = scene / relative
    if not path.is_file():
        raise WebTerrainError(f"{what} {relative.as_posix()} is missing from the scene folder")
    digest = _sha256(path)
    if expected and digest != expected:
        raise WebTerrainError(f"{what} {relative.as_posix()} differs from the digest of the scene manifest")
    return digest


def read_variant(layer: Path, lod: int) -> dict[str, dict[str, Any]]:
    """The tile meshes of variant `lod<lod>` of `/World/Terrain`, keyed by tile id (`<lod>-<level>-<x>-<y>`)."""
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(layer))
    terrain = stage.GetPrimAtPath("/World/Terrain")
    if not terrain:
        raise WebTerrainError("the terrain layer has no /World/Terrain")
    variants = terrain.GetVariantSets().GetVariantSet("lod")
    if f"lod{lod}" not in variants.GetVariantNames():
        raise WebTerrainError(f"the terrain layer has no lod variant lod{lod}")
    variants.SetVariantSelection(f"lod{lod}")
    tiles: dict[str, dict[str, Any]] = {}
    for prim in Usd.PrimRange(terrain):
        if not prim.IsA(UsdGeom.Mesh):
            continue
        parts = prim.GetName().split("_")  # Tile_<lod>_<level>_<x>_<y>
        if len(parts) != 5 or parts[0] != "Tile":
            raise WebTerrainError(f"unexpected terrain prim name {prim.GetName()}")
        mesh = UsdGeom.Mesh(prim)
        points = np.asarray(mesh.GetPointsAttr().Get(), dtype=np.float32)
        counts = np.asarray(mesh.GetFaceVertexCountsAttr().Get())
        indices = np.asarray(mesh.GetFaceVertexIndicesAttr().Get(), dtype=np.int64)
        normals = np.asarray(mesh.GetNormalsAttr().Get(), dtype=np.float32)
        st = UsdGeom.PrimvarsAPI(prim).GetPrimvar("st_ortho")
        if not st or not st.IsDefined():
            raise WebTerrainError(
                f"{prim.GetPath()} has no st_ortho primvar (the scene was built without the orthophoto)"
            )
        uv = np.asarray(st.Get(), dtype=np.float32)
        if not (len(counts) and (counts == 3).all()) or len(indices) != 3 * len(counts):
            raise WebTerrainError(f"{prim.GetPath()} is not a triangle mesh")
        if len(normals) != len(points) or len(uv) != len(points):
            raise WebTerrainError(f"{prim.GetPath()} does not carry one normal and one st_ortho per vertex")
        tiles["-".join(parts[1:])] = {
            "positions": points,
            "indices": indices.reshape(-1, 3).astype(np.uint32),
            "normals": normals,
            "st_ortho": uv,
            "x": int(parts[3]),
            "y": int(parts[4]),
            "level": int(parts[2]),
        }
    if not tiles:
        raise WebTerrainError(f"variant lod{lod} holds no mesh")
    return tiles


def _vertex_normals(points: np.ndarray, triangles: np.ndarray) -> np.ndarray:
    """Area-weighted vertex normals of a triangle mesh (counter-clockwise winding seen from +z gives +z on flat
    ground)."""
    tri = points[triangles].astype(np.float64)
    face = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    out = np.zeros((len(points), 3))
    for k in range(3):
        np.add.at(out, triangles[:, k], face)
    length = np.linalg.norm(out, axis=1, keepdims=True)
    return (out / np.where(length > 1e-12, length, 1.0)).astype(np.float32)


def coarse_root(tiles: dict[str, dict[str, Any]], *, error_m: float, grid: int = ROOT_GRID) -> dict[str, Any]:
    """One mesh over the whole extent of `tiles`, within `error_m` (vertical) of their surface.

    The surface is sampled on a `grid` x `grid` lattice by linear interpolation of the tile vertices (skirt vertices
    share the
    horizontal position of the edge they hang from and are dropped by keeping the highest vertex per position), then
    meshed
    by the scene's RTIN builder. Texture coordinates come from the exact affine map of the tile `st_ortho` values.
    """
    from scipy.interpolate import LinearNDInterpolator, NearestNDInterpolator

    pts = np.concatenate([t["positions"] for t in tiles.values()]).astype(np.float64)
    uv = np.concatenate([t["st_ortho"] for t in tiles.values()]).astype(np.float64)
    keys = np.round(pts[:, :2] * 1000.0).astype(np.int64)
    order = np.lexsort((pts[:, 2], keys[:, 1], keys[:, 0]))  # per position the highest vertex comes last
    keys, pts, uv = keys[order], pts[order], uv[order]
    last = np.ones(len(keys), dtype=bool)
    last[:-1] = (keys[1:] != keys[:-1]).any(axis=1)
    pts, uv = pts[last], uv[last]
    x0, x1, y0, y1 = pts[:, 0].min(), pts[:, 0].max(), pts[:, 1].min(), pts[:, 1].max()
    gx, gy = np.linspace(x0, x1, grid), np.linspace(y1, y0, grid)  # row 0 is the northern edge, as in the tiles
    mesh_x, mesh_y = np.meshgrid(gx, gy)
    query = np.stack([mesh_x.ravel(), mesh_y.ravel()], axis=1)
    heights = LinearNDInterpolator(pts[:, :2], pts[:, 2])(query)
    holes = np.isnan(heights)
    if holes.any():
        heights[holes] = NearestNDInterpolator(pts[:, :2], pts[:, 2])(query[holes])
    heights = heights.reshape(grid, grid)
    mesh = rtin.build_rtin(heights, error_m)
    if not len(mesh.triangles):
        raise WebTerrainError("the coarse root has no triangle")
    rows, cols = mesh.rc[:, 0], mesh.rc[:, 1]
    positions = np.stack([gx[cols], gy[rows], mesh.z.astype(np.float64)], axis=1).astype(np.float32)
    triangles = mesh.triangles.astype(np.uint32)
    # st_ortho is affine in the horizontal position (one image over the site): fit it and check the fit
    basis = np.stack([pts[:, 0], pts[:, 1], np.ones(len(pts))], axis=1)
    coef, *_ = np.linalg.lstsq(basis, uv, rcond=None)
    residual = float(np.abs(basis @ coef - uv).max())
    if residual > 1e-5:
        raise WebTerrainError(f"st_ortho is not an affine map of the site position (largest residual {residual:.2e})")
    root_uv = np.stack([positions[:, 0], positions[:, 1], np.ones(len(positions))], axis=1).astype(np.float64) @ coef
    return {
        "positions": positions,
        "indices": triangles,
        "normals": _vertex_normals(positions, triangles),
        "st_ortho": root_uv.astype(np.float32),
    }


def _save(path: Path, tile: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    np.savez_compressed(
        path, positions=tile["positions"], indices=tile["indices"], normals=tile["normals"], st_ortho=tile["st_ortho"]
    )


def _bbox(positions: np.ndarray) -> dict[str, float]:
    lo, hi = positions.min(axis=0), positions.max(axis=0)
    return {
        "x_min_m": float(lo[0]),
        "y_min_m": float(lo[1]),
        "z_min_m": float(lo[2]),
        "x_max_m": float(hi[0]),
        "y_max_m": float(hi[1]),
        "z_max_m": float(hi[2]),
    }


def extract(
    scene: Path,
    out_dir: Path,
    *,
    lods: tuple[int, ...] = (2, 1),
    root_error_m: float = DEFAULT_ROOT_ERROR_M,
) -> dict[str, Any]:
    """Writes the exchange folder of the web bake from the composed scene folder `scene` (a `st45_validate/scene`
    folder).

    `lods` lists the scene `lod` variants to carry, coarsest first; the coarse root is derived from the first one.
    Raises
    `WebTerrainError` when an input file is missing or differs from the digest the scene manifest records.
    """
    scene, out_dir = Path(scene), Path(out_dir)
    manifest = _read_manifest(scene)
    albedo = (manifest.get("terrain") or {}).get("albedo")
    if not albedo or not albedo.get("images"):
        raise WebTerrainError("the scene manifest records no orthophoto albedo (terrain.albedo)")
    ortho_sha = _check_digest(scene, ORTHO, albedo["images"][0].get("sha256"), "the orthophoto")
    textures = {t["id"]: t for t in manifest.get("textures", [])}
    rock = textures.get("bench-rock-normal")
    if not rock:
        raise WebTerrainError("the scene manifest records no bench-rock-normal texture")
    rock_sha = _check_digest(scene, ROCK_NORMAL, rock.get("sha256"), "the rock normal map")
    layer = scene / TERRAIN_LAYER
    layer_sha = next((x["sha256"] for x in manifest["layers"] if x["path"] == TERRAIN_LAYER.as_posix()), None)
    layer_digest = _check_digest(scene, TERRAIN_LAYER, layer_sha, "the terrain layer")
    sources = {s["id"]: s for s in manifest["sources"]}
    for needed in ("usgs-3dep-bingham", albedo["source"]):
        if needed not in sources:
            raise WebTerrainError(f"the scene manifest names no source {needed}")

    from PIL import Image

    with Image.open(scene / ORTHO) as image:
        width, height = image.size
    shutil.rmtree(out_dir, ignore_errors=True)
    out_dir.mkdir(parents=True)
    shutil.copyfile(scene / ORTHO, out_dir / "ortho.jpg")
    shutil.copyfile(scene / ROCK_NORMAL, out_dir / "rock-normal.jpg")

    index = json.loads((scene / "terrain" / "tiles.json").read_text(encoding="utf-8"))
    errors = {int(row["lod"]): float(row["max_error_m"]) for row in index["lods"]}
    levels: list[dict[str, Any]] = []
    first: dict[str, dict[str, Any]] | None = None
    for lod in lods:
        tiles = read_variant(layer, lod)
        first = first or tiles
        rows = []
        for tile_id, tile in sorted(tiles.items()):
            _save(out_dir / "levels" / f"lod{lod}" / f"{tile_id}.npz", tile)
            rows.append(
                {
                    "id": tile_id,
                    "x": tile["x"],
                    "y": tile["y"],
                    "file": f"levels/lod{lod}/{tile_id}.npz",
                    "bbox": _bbox(tile["positions"]),
                    "vertices": len(tile["positions"]),
                    "triangles": len(tile["indices"]),
                }
            )
        levels.append({"lod": lod, "max_error_m": errors[lod], "tiles": rows})
    assert first is not None
    root = coarse_root(first, error_m=root_error_m, grid=ROOT_GRID)
    _save(out_dir / "levels" / "root.npz", root)
    all_x = [r["bbox"] for lv in levels for r in lv["tiles"]]
    doc = {
        "kind": "web-terrain-input",
        "schema_version": "1.0",
        "scene": {
            "manifest_id": manifest["manifest_id"],
            "params_sha256": manifest["params_sha256"],
            "terrain_layer_sha256": layer_digest,
        },
        "producer": {"tool": "openusd", "package": "usd-core", "version": metadata.version("usd-core")},
        "frame": "site-enu",
        "input_digests": {
            "usgs-3dep-bingham": next(i["sha256"] for i in manifest["inputs"] if i["source"] == "usgs-3dep-bingham"),
            albedo["source"]: albedo["inputs"][0]["sha256"],
            "polyhaven-rock-boulder-dry": rock_sha,
        },
        "extent": {
            "x_min_m": min(b["x_min_m"] for b in all_x),
            "x_max_m": max(b["x_max_m"] for b in all_x),
            "y_min_m": min(b["y_min_m"] for b in all_x),
            "y_max_m": max(b["y_max_m"] for b in all_x),
        },
        "sources": {
            sid: {k: sources[sid][k] for k in ("id", "spdx", "licence_class", "attribution", "role", "epoch")}
            for sid in ("usgs-3dep-bingham", albedo["source"])
        },
        "albedo": {
            "file": "ortho.jpg",
            "sha256": ortho_sha,
            "width": width,
            "height": height,
            "source": albedo["source"],
            "year": albedo["year"],
            "ground_resolution_m": albedo["ground_resolution_m"],
        },
        "rock_normal": {
            "file": "rock-normal.jpg",
            "sha256": rock_sha,
            "source": "polyhaven-rock-boulder-dry",
            "spdx": rock["spdx"],
            "repeat_m": ROCK_REPEAT_M,
        },
        "root": {
            "file": "levels/root.npz",
            "derived_from_lod": lods[0],
            "mesh_error_m": root_error_m,
            "error_m": root_error_m + errors[lods[0]],
            "vertices": len(root["positions"]),
            "triangles": len(root["indices"]),
            "bbox": _bbox(root["positions"]),
        },
        "levels": levels,
    }
    (out_dir / "web-bake-input.json").write_text(json.dumps(doc, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    return doc


def main(argv: list[str] | None = None) -> int:
    """`python -m pitstudio_studio.scene.web_terrain --scene <st45 scene folder> --out <exchange folder>`; exit 0 or
    2."""
    import argparse

    parser = argparse.ArgumentParser(description="Extract the terrain of a composed scene for the web bake.")
    parser.add_argument("--scene", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--root-error-m", type=float, default=DEFAULT_ROOT_ERROR_M)
    args = parser.parse_args(argv)
    try:
        doc = extract(args.scene, args.out, root_error_m=args.root_error_m)
    except WebTerrainError as e:
        print(f"web-terrain: {e}")
        return 2
    print(
        f"web-terrain: root {doc['root']['triangles']} triangles; "
        + ", ".join(f"lod{lv['lod']} {len(lv['tiles'])} tiles" for lv in doc["levels"])
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


__all__ = ["WebTerrainError", "coarse_root", "extract", "main", "read_variant"]
