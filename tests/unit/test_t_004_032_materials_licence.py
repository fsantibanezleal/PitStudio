# ruff: noqa: E501, PT018
"""T-004-032: UsdPreviewSurface materials only, CC0 textures recorded with source id and SHA-256, no NVIDIA or URL references.

Requirements: FR-004-26.

Oracle: a text search of every written layer for the forbidden schemes and NVIDIA references (plan.md "FR-004-26"), the
OpenUSD shader ids read back with `pxr.UsdShade`, SHA-256 of the fixture texture files recomputed with hashlib, and the
licence table of the data registry (CC0-1.0 for the CC0 sources, CC-BY-4.0 for our own textures; spec DC-004-01).

Expected API (package `pitstudio_studio.scene.assets`, studio environment): `assets.build_assets(spec, out_dir,
textures={material id: path of the texture file})` (see test_t_004_030) additionally writes `<out_dir>/textures/` (the
texture files, copied), `AssetBuild.materials_layer` (a `.usda` layer holding one `UsdShade.Material` per `spec["materials"]`
entry whose surface is a `UsdPreviewSurface`, with `UsdUVTexture` inputs `inputs:file` as relative asset paths of the
copied files) and `AssetBuild.textures`: one record per material, `{"id", "source", "spdx", "sha256"}` (the DC-004-02
`textures[]` item; sha256 of the texture file's bytes).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import assets  # noqa: E402

FORBIDDEN = re.compile(r"omniverse://|https?://|file://|nvidia", re.IGNORECASE)
ALLOWED_SHADERS = {
    "UsdPreviewSurface",
    "UsdUVTexture",
    "UsdPrimvarReader_float2",
    "UsdPrimvarReader_float",
    "UsdTransform2d",
}


def _spec_and_textures(tmp: Path) -> tuple[dict, dict[str, Path]]:
    spec = kit.machine_spec(("haul_truck",))
    spec["materials"] = [
        {"id": "gravel-road", "source": "polyhaven", "spdx": "CC0-1.0"},
        {"id": "rock-face", "source": "ambientcg", "spdx": "CC0-1.0"},
        {"id": "own-paint", "source": None, "spdx": "CC-BY-4.0"},
    ]
    tex = {
        m["id"]: kit.tiny_png(tmp / f"src_{m['id']}.png", (10 * i + 50, 90, 60))
        for i, m in enumerate(spec["materials"])
    }
    return spec, tex


@pytest.mark.req("FR-004-26")
def test_materials_are_usd_preview_surface_networks(tmp_path: Path) -> None:
    from pxr import Usd, UsdShade

    spec, tex = _spec_and_textures(tmp_path)
    build = assets.build_assets(spec, tmp_path / "out", textures=tex)
    stage = Usd.Stage.Open(str(build.materials_layer))
    materials = [p for p in stage.Traverse() if p.IsA(UsdShade.Material)]
    assert len(materials) == 3
    for mat in materials:
        shader = UsdShade.Material(mat).ComputeSurfaceSource()[0]  # (shader, output name, source type)
        assert shader and shader.GetShaderId() == "UsdPreviewSurface", mat.GetPath()
    shaders = [UsdShade.Shader(p) for p in stage.Traverse() if p.IsA(UsdShade.Shader)]
    assert shaders and {s.GetShaderId() for s in shaders} <= ALLOWED_SHADERS
    assert not any(p.HasAttribute("info:mdl:sourceAsset") for p in stage.Traverse())  # no MDL


@pytest.mark.req("FR-004-26")
def test_textures_are_relative_files_recorded_with_source_and_sha256(tmp_path: Path) -> None:
    from pxr import Usd, UsdShade

    spec, tex = _spec_and_textures(tmp_path)
    out = tmp_path / "out"
    build = assets.build_assets(spec, out, textures=tex)
    assert [t["id"] for t in build.textures] == ["gravel-road", "rock-face", "own-paint"]
    for rec, mat in zip(build.textures, spec["materials"], strict=True):
        assert rec == {
            "id": mat["id"],
            "source": mat["source"],
            "spdx": mat["spdx"],
            "sha256": kit.sha256_file(tex[mat["id"]]),
        }
        assert rec["spdx"] in ("CC0-1.0", "CC-BY-4.0") and (rec["spdx"] == "CC0-1.0") == (rec["source"] is not None)
    stage = Usd.Stage.Open(str(build.materials_layer))
    files = [
        UsdShade.Shader(p).GetInput("file").Get()
        for p in stage.Traverse()
        if p.IsA(UsdShade.Shader) and UsdShade.Shader(p).GetShaderId() == "UsdUVTexture"
    ]
    assert len(files) == 3
    for f in files:
        rel = f.path
        assert not re.match(r"^([A-Za-z]:|/|\\\\)", rel) and ".." not in rel.split("/"), rel
        resolved = (Path(build.materials_layer).parent / rel).resolve()
        assert resolved.is_file() and out.resolve() in resolved.parents
        assert kit.sha256_file(resolved) in {t["sha256"] for t in build.textures}  # the copied file is the recorded one


@pytest.mark.req("FR-004-26")
def test_texture_records_fit_the_scene_manifest_schema(tmp_path: Path) -> None:
    import json

    spec, tex = _spec_and_textures(tmp_path)
    build = assets.build_assets(spec, tmp_path / "out", textures=tex)
    manifest = json.loads((kit.EXAMPLES / "scene-manifest.valid.json").read_text(encoding="utf-8"))
    manifest["textures"] = build.textures
    assert kit.schema_errors("scene-manifest.schema.json", manifest) == []


@pytest.mark.req("FR-004-26")
def test_no_layer_holds_a_url_scheme_or_an_nvidia_reference(tmp_path: Path) -> None:
    from pxr import Sdf

    spec, tex = _spec_and_textures(tmp_path)
    spec["people_count"] = 3
    out = tmp_path / "out"
    build = assets.build_assets(spec, out, textures=tex)
    layers = sorted(out.rglob("*.usda"))
    assert len(layers) >= 3  # materials, machine, fleet
    for path in layers:
        text = path.read_text(encoding="utf-8")
        assert not FORBIDDEN.search(text), (path.name, FORBIDDEN.search(text).group(0))
        layer = Sdf.Layer.FindOrOpen(str(path))
        for ref in [*layer.GetExternalReferences(), *layer.GetCompositionAssetDependencies()]:
            assert not FORBIDDEN.search(ref) and not re.match(r"^([A-Za-z]:|/|\\\\)", ref), ref
    assert build.materials_layer in layers or Path(build.materials_layer).resolve() in [p.resolve() for p in layers]
