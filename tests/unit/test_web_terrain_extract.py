"""The OpenUSD side of the web bake: tile meshes of a `lod` variant, the coarse root, the exchange folder (FR-016-19).

Environment: studio (`pxr`, scipy, Pillow). Oracles: arrays authored by the test itself, the RTIN error
bound by hand, the digests of the files the test wrote.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np
import pytest
from PIL import Image
from pxr import Sdf, Usd, UsdGeom, Vt

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.scene import web_terrain  # noqa: E402
from pitstudio_studio.scene.web_terrain import WebTerrainError, coarse_root, extract, read_variant  # noqa: E402

X0, Y0, SIDE = -128.0, -128.0, 256.0  # the site: one 256 m square split into two tiles side by side


def _surface(x: np.ndarray, y: np.ndarray) -> np.ndarray:
    return 20.0 * np.sin(x / 60.0) + 0.1 * y


def _tile(x_min: float, n: int = 17) -> dict:
    xs = np.linspace(x_min, x_min + SIDE / 2, n)
    ys = np.linspace(Y0, Y0 + SIDE, n)
    gx, gy = np.meshgrid(xs, ys)
    points = np.stack([gx.ravel(), gy.ravel(), _surface(gx, gy).ravel()], axis=1).astype(np.float32)
    tris = []
    for r in range(n - 1):
        for c in range(n - 1):
            a, b, d, e = r * n + c, r * n + c + 1, (r + 1) * n + c, (r + 1) * n + c + 1
            tris += [(a, b, e), (a, e, d)]
    uv = np.stack([(points[:, 0] - X0) / SIDE, (points[:, 1] - Y0) / SIDE], axis=1).astype(np.float32)
    normals = np.tile(np.array([0, 0, 1], dtype=np.float32), (len(points), 1))
    return {"points": points, "indices": np.array(tris, dtype=np.int32).ravel(), "uv": uv, "normals": normals}


def _write_layer(path: Path, *, with_uv: bool = True) -> None:
    stage = Usd.Stage.CreateNew(str(path))
    UsdGeom.Xform.Define(stage, "/World")
    terrain = UsdGeom.Xform.Define(stage, "/World/Terrain").GetPrim()
    vset = terrain.GetVariantSets().AddVariantSet("lod")
    for lod in (2, 1):
        vset.AddVariant(f"lod{lod}")
    for lod in (2, 1):
        vset.SetVariantSelection(f"lod{lod}")
        with vset.GetVariantEditContext():
            UsdGeom.Xform.Define(stage, f"/World/Terrain/Lod{lod}")
            for x, x_min in enumerate((X0, X0 + SIDE / 2)):
                t = _tile(x_min)
                mesh = UsdGeom.Mesh.Define(stage, f"/World/Terrain/Lod{lod}/Tile_{lod}_1_{x}_0")
                mesh.CreatePointsAttr(Vt.Vec3fArray.FromNumpy(t["points"]))
                mesh.CreateFaceVertexCountsAttr(
                    Vt.IntArray.FromNumpy(np.full(len(t["indices"]) // 3, 3, dtype=np.int32))
                )
                mesh.CreateFaceVertexIndicesAttr(Vt.IntArray.FromNumpy(t["indices"]))
                mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(t["normals"]))
                mesh.SetNormalsInterpolation("vertex")
                if with_uv:
                    pv = UsdGeom.PrimvarsAPI(mesh).CreatePrimvar(
                        "st_ortho", Sdf.ValueTypeNames.TexCoord2fArray, UsdGeom.Tokens.vertex
                    )
                    pv.Set(Vt.Vec2fArray.FromNumpy(t["uv"]))
    stage.GetRootLayer().Save()


def _scene(tmp: Path, *, with_uv: bool = True, ortho_sha: str | None = None) -> Path:
    scene = tmp / "scene"
    (scene / "layers").mkdir(parents=True)
    (scene / "terrain" / "albedo").mkdir(parents=True)
    (scene / "assets" / "textures").mkdir(parents=True)
    _write_layer(scene / "layers" / "terrain.usdc", with_uv=with_uv)
    Image.new("RGB", (64, 64), (120, 110, 90)).save(scene / "terrain" / "albedo" / "ortho.jpg", quality=90)
    Image.new("RGB", (16, 16), (128, 128, 255)).save(
        scene / "assets" / "textures" / "bench_rock_normal.jpg", quality=90
    )
    sha = lambda p: hashlib.sha256((scene / p).read_bytes()).hexdigest()  # noqa: E731
    tiles = {"lods": [{"lod": 2, "max_error_m": 4.0}, {"lod": 1, "max_error_m": 1.0}]}
    (scene / "terrain" / "tiles.json").write_text(json.dumps(tiles), encoding="utf-8")
    manifest = {
        "kind": "scene-manifest",
        "manifest_id": "a1-scene-test",
        "params_sha256": "f" * 64,
        "layers": [{"path": "layers/terrain.usdc", "sha256": sha("layers/terrain.usdc")}],
        "inputs": [{"source": "usgs-3dep-bingham", "sha256": "1" * 64}],
        "sources": [
            {
                "id": s,
                "spdx": "LicenseRef-USGov-PD",
                "licence_class": "public-domain",
                "attribution": "a",
                "role": r,
                "epoch": 2018,
            }
            for s, r in (("usgs-3dep-bingham", "terrain"), ("usda-naip-bingham", "imagery"))
        ],
        "terrain": {
            "albedo": {
                "source": "usda-naip-bingham",
                "year": 2018,
                "ground_resolution_m": 0.6,
                "images": [
                    {"path": "terrain/albedo/ortho.jpg", "sha256": ortho_sha or sha("terrain/albedo/ortho.jpg")}
                ],
                "inputs": [{"path": "usda-naip-bingham/x.tif", "sha256": "2" * 64}],
            }
        },
        "textures": [
            {"id": "bench-rock-normal", "sha256": sha("assets/textures/bench_rock_normal.jpg"), "spdx": "CC0-1.0"}
        ],
    }
    (scene / "scene.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return scene


def test_the_tiles_of_a_variant_come_back_as_authored(tmp_path: Path) -> None:
    scene = _scene(tmp_path)
    tiles = read_variant(scene / "layers" / "terrain.usdc", 2)
    assert sorted(tiles) == ["2-1-0-0", "2-1-1-0"]
    expected = _tile(X0)
    got = tiles["2-1-0-0"]
    assert got["positions"].dtype == np.float32
    assert np.array_equal(got["positions"], expected["points"])
    assert np.array_equal(got["indices"].ravel(), expected["indices"])
    assert np.allclose(got["st_ortho"], expected["uv"])
    assert (got["x"], got["y"], got["level"]) == (0, 0, 1)
    with pytest.raises(WebTerrainError, match="lod9"):
        read_variant(scene / "layers" / "terrain.usdc", 9)


def test_a_scene_built_without_the_orthophoto_is_refused(tmp_path: Path) -> None:
    scene = _scene(tmp_path, with_uv=False)
    with pytest.raises(WebTerrainError, match="st_ortho"):
        read_variant(scene / "layers" / "terrain.usdc", 2)


def test_the_coarse_root_stays_within_its_error_of_the_surface_and_maps_the_texture_exactly(tmp_path: Path) -> None:
    tiles = read_variant(_scene(tmp_path) / "layers" / "terrain.usdc", 2)
    for error in (0.5, 4.0):
        root = coarse_root(tiles, error_m=error, grid=65)
        p = root["positions"].astype(np.float64)
        assert np.abs(p[:, 2] - _surface(p[:, 0], p[:, 1])).max() <= 1e-3  # a vertex is a surface sample
        assert np.allclose(root["st_ortho"][:, 0], (p[:, 0] - X0) / SIDE, atol=1e-5)
        assert np.allclose(root["st_ortho"][:, 1], (p[:, 1] - Y0) / SIDE, atol=1e-5)
        assert np.allclose(np.linalg.norm(root["normals"], axis=1), 1.0, atol=1e-5)
        assert root["indices"].max() < len(p)
    fine, coarse = coarse_root(tiles, error_m=0.5, grid=65), coarse_root(tiles, error_m=4.0, grid=65)
    assert len(coarse["indices"]) < len(fine["indices"])  # a larger error allows fewer triangles


def test_extract_writes_the_exchange_folder_with_provenance_and_digests(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(web_terrain, "ROOT_GRID", 65)
    scene = _scene(tmp_path)
    doc = extract(scene, tmp_path / "exchange", root_error_m=2.0)
    on_disk = json.loads((tmp_path / "exchange" / "web-bake-input.json").read_text(encoding="utf-8"))
    assert on_disk == json.loads(json.dumps(doc))
    assert [lv["lod"] for lv in doc["levels"]] == [2, 1]
    assert doc["albedo"]["sha256"] == hashlib.sha256((tmp_path / "exchange" / "ortho.jpg").read_bytes()).hexdigest()
    assert doc["rock_normal"]["spdx"] == "CC0-1.0"
    assert doc["rock_normal"]["repeat_m"] == 8.0
    assert doc["input_digests"]["usgs-3dep-bingham"] == "1" * 64
    assert doc["root"]["error_m"] == 2.0 + 4.0
    assert (tmp_path / "exchange" / doc["levels"][0]["tiles"][0]["file"]).is_file()
    assert (tmp_path / "exchange" / "levels" / "root.npz").is_file()
    assert doc["extent"]["x_min_m"] == X0


def test_a_file_that_differs_from_the_manifest_digest_is_refused_and_nothing_is_written(tmp_path: Path) -> None:
    scene = _scene(tmp_path, ortho_sha="0" * 64)
    with pytest.raises(WebTerrainError, match="orthophoto"):
        extract(scene, tmp_path / "exchange")
    assert not (tmp_path / "exchange").exists()
