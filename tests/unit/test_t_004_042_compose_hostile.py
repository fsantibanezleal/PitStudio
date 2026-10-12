# ruff: noqa: E501, PT018
"""T-004-042: hostile layers: wrong units or axis, missing or tampered sublayer, unknown variant, forbidden paths.

Requirements: FR-004-32, FR-004-33.

Oracle: layers built here with one known defect each (plan.md "FR-004-32": Y up, centimetres, unauthored units, a missing
sublayer, a tampered hash, an unknown variant; "FR-004-33": each forbidden path form), written with OpenUSD; the expected
error class and the named layer or attribute are written in the test; the SHA-256 of the intact upstream layers is
recomputed with hashlib.

Expected API: `compose.compose_scene(spec, upstream, scene_dir)` (test_t_004_040) raises
`common.SceneStageError("compose-invalid")` (message `"compose-invalid: ..."` naming the layer role or file name, or the
variant) when an upstream layer has `upAxis` other than Z, `metersPerUnit` other than 1.0 or unauthored,
`kilogramsPerUnit` other than 1.0 or unauthored; when a sublayer file is missing or its SHA-256 differs from
`upstream["layer_sha256"]`; when a variant name of a layer's variant set, or of `spec["variants"]`, is not in the scene
specification's enumeration. It raises `SceneStageError("path-forbidden")` naming the layer and the attribute (or
`references`, `payloads`, `subLayers`) when any upstream layer holds an asset path that is absolute, has a drive letter
or UNC prefix, contains `..` that escapes the scene folder, or uses the scheme `omniverse://`, `http://`, `https://` or
`file://`. Nothing is written under `scene_dir` in either case, and no unit or axis is ever corrected.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import common, compose  # noqa: E402


def _replace(up: dict, role: str, **stage_kwargs) -> None:
    """Rewrite the upstream layer `role` with the given unit settings and re-record its digest (an upstream defect)."""
    path = Path(up["layers"][role])
    path.unlink()
    st = kit.new_usd_stage(path, **stage_kwargs)
    from pxr import UsdGeom

    st.SetDefaultPrim(UsdGeom.Xform.Define(st, "/World").GetPrim())
    kit.define_quad(
        st,
        "/World/Design/Bench_00" if role == "design" else "/World/Fleet/Q",
        10.0,
        "bench" if role == "design" else "haul_truck",
    )
    st.GetRootLayer().Save()
    up["layer_sha256"][role] = kit.sha256_file(path)


def _expect(tmp_path: Path, up: dict, error_class: str, *names: str, spec: dict | None = None) -> None:
    scene = tmp_path / "scene"
    with pytest.raises(common.SceneStageError) as exc:
        compose.compose_scene(spec or kit.scene_spec(), up, scene)
    assert exc.value.error_class == error_class and str(exc.value).startswith(f"{error_class}: ")
    for name in names:
        assert name in str(exc.value), (name, str(exc.value))
    assert not scene.exists() or list(scene.rglob("*")) == []  # never corrected, never half written


@pytest.mark.req("FR-004-32")
def test_the_intact_fixture_composes(tmp_path: Path) -> None:
    build = compose.compose_scene(kit.scene_spec(), kit.fixture_upstream(tmp_path / "up"), tmp_path / "scene")
    assert build.root.is_file()


@pytest.mark.req("FR-004-32")
@pytest.mark.parametrize("role", ["design", "fleet"])
@pytest.mark.parametrize(
    "defect",
    [
        {"up": "Y"},  # wrong up axis
        {"mpu": 0.01},  # centimetres
        {"mpu": None},  # metersPerUnit unauthored
        {"kpu": 0.001},  # grams
        {"kpu": None},  # kilogramsPerUnit unauthored
    ],
    ids=["y-up", "centimetres", "mpu-unauthored", "grams", "kpu-unauthored"],
)
def test_wrong_or_unauthored_units_and_axis_are_compose_invalid(tmp_path: Path, role: str, defect: dict) -> None:
    up = kit.fixture_upstream(tmp_path / "up")
    _replace(up, role, **defect)
    _expect(tmp_path, up, "compose-invalid", role)


@pytest.mark.req("FR-004-32")
def test_wrong_units_in_the_terrain_crate_layer_are_compose_invalid(tmp_path: Path) -> None:
    up = kit.fixture_upstream(tmp_path / "up")
    path = Path(up["layers"]["terrain"])
    path.unlink()
    st = kit.new_usd_stage(path, mpu=0.01)  # a centimetre terrain
    from pxr import UsdGeom

    st.SetDefaultPrim(UsdGeom.Xform.Define(st, "/World").GetPrim())
    st.GetRootLayer().Save()
    up["layer_sha256"]["terrain"] = kit.sha256_file(path)
    _expect(tmp_path, up, "compose-invalid", "terrain")


@pytest.mark.req("FR-004-32")
def test_a_missing_sublayer_is_compose_invalid(tmp_path: Path) -> None:
    up = kit.fixture_upstream(tmp_path / "up")
    Path(up["layers"]["fleet"]).unlink()
    _expect(tmp_path, up, "compose-invalid", "fleet")


@pytest.mark.req("FR-004-32")
@pytest.mark.parametrize("role", ["design", "fleet", "terrain"])
def test_a_sublayer_whose_digest_differs_from_the_upstream_record_is_compose_invalid(tmp_path: Path, role: str) -> None:
    up = kit.fixture_upstream(tmp_path / "up")
    path = Path(up["layers"][role])
    path.write_bytes(path.read_bytes() + b"\n")  # one byte changed after the upstream stage recorded its digest
    _expect(tmp_path, up, "compose-invalid", role)


@pytest.mark.req("FR-004-32")
def test_a_variant_outside_the_enumeration_is_compose_invalid(tmp_path: Path) -> None:
    # (a) an upstream layer offers a lod variant that the scene specification does not list
    up = kit.fixture_upstream(tmp_path / "up_a")
    from pxr import Usd

    st = Usd.Stage.Open(str(up["layers"]["terrain"]))
    vset = st.GetPrimAtPath("/World/Terrain").GetVariantSet("lod")
    vset.AddVariant("lod9")
    st.GetRootLayer().Save()
    up["layer_sha256"]["terrain"] = kit.sha256_file(Path(up["layers"]["terrain"]))
    _expect(tmp_path / "a", up, "compose-invalid", "lod9")
    # (b) the specification itself names a variant outside the closed enumeration
    for key, bad in (("time_of_day", "sunset"), ("weather", "hail"), ("lod", "lod3")):
        spec = kit.scene_spec()
        spec["variants"][key] = [*spec["variants"][key], bad]
        _expect(tmp_path / f"b_{key}", kit.fixture_upstream(tmp_path / f"up_{key}"), "compose-invalid", bad, spec=spec)


# ------------------------------------------------------------------------------------------------------- FR-004-33
FORBIDDEN = [
    "/etc/passwd.png",
    "/tmp/x.png",
    "C:/data/x.png",
    "c:/data/x.png",
    "C:\\data\\x.png",
    "\\\\server\\share\\x.png",
    "//server/share/x.png",
    "../../escape/x.png",  # from layers/ this leaves the scene folder
    "textures/../../../escape/x.png",
    "omniverse://host/Library/x.png",
    "http://example.org/x.png",
    "https://example.org/x.png",
    "file:///x.png",
    "HTTPS://EXAMPLE.ORG/x.png",
]
ALLOWED = ["ok.png", "textures/ok.png", "../assets/ok.png", "./ok.png"]  # stay inside the scene folder


def _poison_attribute(up: dict, value: str) -> None:
    from pxr import Sdf, Usd

    path = Path(up["layers"]["design"])
    st = Usd.Stage.Open(str(path))
    prim = st.GetPrimAtPath("/World/Design/Bench_00")
    prim.CreateAttribute("pitstudio:testfile", Sdf.ValueTypeNames.Asset).Set(Sdf.AssetPath(value))
    st.GetRootLayer().Save()
    up["layer_sha256"]["design"] = kit.sha256_file(path)


@pytest.mark.req("FR-004-33")
@pytest.mark.parametrize("value", FORBIDDEN)
def test_forbidden_asset_path_in_an_attribute_is_path_forbidden_naming_layer_and_attribute(
    tmp_path: Path, value: str
) -> None:
    up = kit.fixture_upstream(tmp_path / "up")
    _poison_attribute(up, value)
    _expect(tmp_path, up, "path-forbidden", "design", "pitstudio:testfile")


@pytest.mark.req("FR-004-33")
@pytest.mark.parametrize("value", ALLOWED)
def test_relative_paths_inside_the_scene_folder_are_accepted(tmp_path: Path, value: str) -> None:
    up = kit.fixture_upstream(tmp_path / "up")
    _poison_attribute(up, value)
    assert compose.compose_scene(kit.scene_spec(), up, tmp_path / "scene").root.is_file()


@pytest.mark.req("FR-004-33")
@pytest.mark.parametrize(
    "value",
    ["omniverse://host/Library/x.usd", "https://example.org/x.usd", "/abs/x.usd", "C:/abs/x.usd", "../../escape.usd"],
)
@pytest.mark.parametrize("where", ["references", "payloads", "subLayers"])
def test_forbidden_composition_arcs_are_path_forbidden(tmp_path: Path, where: str, value: str) -> None:
    from pxr import Sdf, Usd

    up = kit.fixture_upstream(tmp_path / "up")
    path = Path(up["layers"]["fleet"])
    layer = Sdf.Layer.FindOrOpen(str(path))
    if where == "subLayers":
        layer.subLayerPaths.append(value)
    else:
        st = Usd.Stage.Open(layer)
        prim = st.GetPrimAtPath("/World/Fleet")
        if where == "references":
            prim.GetReferences().AddReference(value)
        else:
            prim.GetPayloads().AddPayload(value)
    layer.Save()
    up["layer_sha256"]["fleet"] = kit.sha256_file(path)
    _expect(tmp_path, up, "path-forbidden", "fleet", where)
