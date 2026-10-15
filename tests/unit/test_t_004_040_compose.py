# ruff: noqa: PT018, RUF059
"""T-004-040: root stage, sublayer order, variant sets, physics scene, USDA sorted order, custom layer data, manifest.

Requirements: FR-004-29, FR-004-30.

Oracle: the expected sublayer list, variant names, gravity vector and units written in this test from the spec text;
OpenUSD read back (reference implementation); the manifest is validated with the DC-004-02 draft schema and its digests
and sizes recomputed with hashlib; `sha256_of_params` is the SHA-256 of the RFC 8785 canonical JSON of the params
(`scene_kit.params_sha256`, written from the RFC).

Expected API (package `pitstudio_studio.scene.compose`, studio environment):
- `compose.compose_scene(spec, upstream, scene_dir) -> SceneBuild`. `spec`: SceneSpec dict; `upstream`: a mapping with
  `layers` (role -> path of the upstream `terrain`, `design` and `fleet` layers), `layer_sha256` (role -> the upstream
  stage's recorded SHA-256 of that file), `assets` (list of machine/material layer paths, role `asset`), `files` (record
  files, scene-relative path -> source path: the terrain grid attributes, tile index, design report and road network)
  and `records` (the DC-004-02 `sources`, `inputs`, `terrain`, `design`, `textures`, `people_route` and `site` records,
  taken over unchanged).
  It writes under `scene_dir`: `root.usda`; `layers/anim.usda`, `layers/sensors.usda`, `layers/weather.usda`,
  `layers/lights.usda`, `layers/fleet.usda`, `layers/design.usda` and `layers/terrain.usdc`; `assets/<file>` for every
  asset; every record file at its scene-relative path; `scene.manifest.json` and `scene.digest.json`. Returns
  `SceneBuild` with `root` (Path), `manifest` (dict), `digest` (dict), `manifest_path`, `digest_path`.
- `root.usda`: `upAxis`, `metersPerUnit`, `kilogramsPerUnit` authored; default prim `World`; `subLayerPaths` (strongest
  first) `layers/anim.usda`, `layers/sensors.usda`, `layers/weather.usda`, `layers/lights.usda`, `layers/fleet.usda`,
  `layers/design.usda`, `layers/terrain.usdc`; variant sets `pushback`, `scenario`, `time_of_day`, `weather`, `lod` on
  `/World` with the names of `spec["variants"]`, the first name selected; a `UsdPhysics.Scene` with gravity direction
  (0, 0, -1) and magnitude 9.81; `customLayerData = {manifest_id, sha256_of_params}`.
- Every small generated layer is `.usda` with all sibling prims authored in sorted name order.
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose  # noqa: E402

SUBLAYERS = [
    "layers/anim.usda",
    "layers/sensors.usda",
    "layers/weather.usda",
    "layers/lights.usda",
    "layers/fleet.usda",
    "layers/design.usda",
    "layers/terrain.usdc",
]
SMALL = [
    "root.usda",
    "layers/anim.usda",
    "layers/sensors.usda",
    "layers/weather.usda",
    "layers/lights.usda",
    "layers/fleet.usda",
    "layers/design.usda",
]


def _spec() -> dict:
    spec = kit.scene_spec()
    spec["variants"] = {
        "pushback": ["pb0", "pb1"],
        "scenario": ["baseline", "stress"],
        "time_of_day": ["noon", "dawn", "night"],
        "weather": ["clear", "dust"],
        "lod": ["lod0", "lod1", "lod2"],
    }
    return spec


@pytest.fixture(scope="module")
def scene(tmp_path_factory: pytest.TempPathFactory):
    base = tmp_path_factory.mktemp("compose")
    spec = _spec()
    up = kit.fixture_upstream(base / "up")
    build = compose.compose_scene(spec, up, base / "scene")
    return spec, up, build, base / "scene"


@pytest.mark.req("FR-004-29")
def test_sublayers_are_in_the_specified_order_strongest_first(scene) -> None:
    from pxr import Sdf

    _, _, build, _ = scene
    layer = Sdf.Layer.FindOrOpen(str(build.root))
    assert list(layer.subLayerPaths) == SUBLAYERS
    assert layer.defaultPrim == "World"


@pytest.mark.req("FR-004-29")
def test_units_and_up_axis_are_authored_explicitly_in_every_layer(scene) -> None:
    from pxr import Sdf

    _, _, _, folder = scene
    for rel in [*SMALL, "layers/terrain.usdc"]:
        layer = Sdf.Layer.FindOrOpen(str(folder / rel))
        assert layer is not None, rel
        for key, want in (("upAxis", "Z"), ("metersPerUnit", 1.0), ("kilogramsPerUnit", 1.0)):
            assert layer.pseudoRoot.HasInfo(key) and layer.pseudoRoot.GetInfo(key) == want, (rel, key)


@pytest.mark.req("FR-004-29")
def test_variant_sets_carry_the_spec_names_with_the_first_selected(scene) -> None:
    from pxr import Usd

    spec, _, build, _ = scene
    stage = Usd.Stage.Open(str(build.root))
    world = stage.GetPrimAtPath("/World")
    sets = world.GetVariantSets()
    assert sorted(sets.GetNames()) == ["lod", "pushback", "scenario", "time_of_day", "weather"]
    for name, variants in spec["variants"].items():
        vs = sets.GetVariantSet(name)
        assert sorted(vs.GetVariantNames()) == sorted(variants)  # USD returns the names sorted, not in spec order
        assert vs.GetVariantSelection() == variants[0]


@pytest.mark.req("FR-004-29")
def test_physics_scene_has_gravity_down_at_9_81(scene) -> None:
    from pxr import Usd, UsdPhysics

    _, _, build, _ = scene
    stage = Usd.Stage.Open(str(build.root))
    scenes = [p for p in stage.Traverse() if p.IsA(UsdPhysics.Scene)]
    assert len(scenes) == 1
    phys = UsdPhysics.Scene(scenes[0])
    assert tuple(phys.GetGravityDirectionAttr().Get()) == (0.0, 0.0, -1.0)
    assert phys.GetGravityMagnitudeAttr().Get() == pytest.approx(9.81, abs=1e-12)


def _check_sorted(spec_obj) -> None:
    names = [c.name for c in spec_obj.nameChildren]
    assert names == sorted(names), (spec_obj.path, names)
    for child in spec_obj.nameChildren:
        _check_sorted(child)


@pytest.mark.req("FR-004-30")
def test_small_layers_are_usda_text_with_prims_in_sorted_path_order(scene) -> None:
    from pxr import Sdf

    _, _, _, folder = scene
    for rel in SMALL:
        path = folder / rel
        assert path.read_bytes().startswith(b"#usda 1.0"), rel  # text layer, not crate
        assert path.stat().st_size <= 10_000_000
        _check_sorted(Sdf.Layer.FindOrOpen(str(path)).pseudoRoot)


@pytest.mark.req("FR-004-30")
def test_root_layer_custom_data_holds_the_manifest_id_and_the_params_hash(scene) -> None:
    from pxr import Sdf

    spec, _, build, _ = scene
    data = dict(Sdf.Layer.FindOrOpen(str(build.root)).customLayerData)
    assert sorted(data) == ["manifest_id", "sha256_of_params"]
    assert data["sha256_of_params"] == kit.params_sha256(spec)
    assert data["manifest_id"] == build.manifest["manifest_id"]
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]{0,63}", data["manifest_id"])


@pytest.mark.req("FR-004-30")
def test_manifest_is_written_valid_and_describes_every_layer(scene) -> None:
    spec, up, build, folder = scene
    on_disk = json.loads(build.manifest_path.read_text(encoding="utf-8"))
    assert on_disk == build.manifest and build.manifest_path == folder / "scene.manifest.json"
    assert kit.schema_errors("scene-manifest.schema.json", on_disk) == []
    assert on_disk["params_sha256"] == kit.params_sha256(spec) and on_disk["seed"] == spec["seed"]
    assert on_disk["case"] == spec["case"] and on_disk["kind"] == "scene-manifest"
    layers = {entry["role"]: entry for entry in on_disk["layers"] if entry["role"] != "asset"}
    assert sorted(layers) == ["anim", "design", "fleet", "lights", "root", "sensors", "terrain", "weather"]
    for entry in on_disk["layers"]:
        data = (folder / entry["path"]).read_bytes()
        assert entry["sha256"] == hashlib.sha256(data).hexdigest() and entry["bytes"] == len(data)
        assert entry["format"] == ("usdc" if entry["path"].endswith(".usdc") else "usda")
        assert (entry["up_axis"], entry["meters_per_unit"], entry["kilograms_per_unit"]) == ("Z", 1.0, 1.0)
        assert ("label" in entry) == (entry["role"] == "design")
    assert layers["design"]["label"] == "regenerated by design code, not observed"
    assert layers["root"]["path"] == "root.usda" and layers["terrain"]["format"] == "usdc"
    assert [entry["path"] for entry in on_disk["layers"] if entry["role"] != "asset"].count("root.usda") == 1


@pytest.mark.req("FR-004-30")
def test_manifest_variants_site_and_records_follow_the_inputs(scene) -> None:
    spec, up, build, _ = scene
    m = build.manifest
    for key, names in spec["variants"].items():
        assert m["variants"][key] == {"names": names, "default": names[0]}
    assert m["site"]["origin"] == spec["site"]["origin"]
    for key, value in up["records"].items():
        assert m[key] == value  # sources, inputs, terrain, design, textures, people_route, site: taken over
    assert m["validation"] == {"status": "pending"}  # st45_validate has not run yet


@pytest.mark.req("FR-004-30")
def test_assets_and_record_files_are_copied_into_the_scene_folder(scene) -> None:
    _, up, build, folder = scene
    assets = [e for e in build.manifest["layers"] if e["role"] == "asset"]
    assert [e["path"] for e in assets] == ["assets/truck.usda"]
    assert (folder / "assets" / "truck.usda").read_bytes() == Path(up["assets"][0]).read_bytes()
    for rel, source in up["files"].items():
        assert (folder / rel).read_bytes() == Path(source).read_bytes(), rel
    m = build.manifest
    assert m["design"]["report"]["sha256"] == kit.sha256_file(folder / "design" / "pit-design-report.json")
    assert m["terrain"]["grid"]["sha256"] == kit.sha256_file(folder / "terrain" / "grid.zarr" / "zarr.json")


@pytest.mark.req("FR-004-30")
def test_composing_twice_gives_identical_small_layers(scene, tmp_path: Path) -> None:
    spec, _, build, folder = scene
    up = kit.fixture_upstream(tmp_path / "up")
    again = compose.compose_scene(spec, up, tmp_path / "scene2")
    for rel in SMALL:
        assert (folder / rel).read_bytes() == (tmp_path / "scene2" / rel).read_bytes(), rel
    assert again.manifest["params_sha256"] == build.manifest["params_sha256"]
