# ruff: noqa: E501, PT018
"""T-004-100: recognisable procedural machines and the person mannequin of `st30_assets` (FR-004-51).

Requirements: FR-004-51 (with the articulation, labels and people route of FR-004-24, FR-004-25 and FR-004-28 unchanged).

Oracle: OpenUSD (reference implementation: prim hierarchy, `UsdGeom.BBoxCache` extents, `UsdShade` bindings, joint
relationships) read on the files `build_assets` writes; the part lists below are written in this test from the
requirement text (a haul truck with chassis frame, cab, canopy, dump body with sloped floor, front axle with two tyres and
rear axle with four tyres; a rope shovel with crawler tracks, revolving house, boom, dipper handle and dipper; a light
vehicle with body, cabin, windows and four tyres; a person with head, torso, two arms, two legs, a hard hat and a
high-visibility vest). The dimensions are the cited ones of the catalogue (Caterpillar 793F specification sheet, Cat 7495
rope shovel product page, Toyota Land Cruiser 79 single cab sheet); this test checks that the geometry follows them.

Expected API (package `pitstudio_studio.scene.assets`, studio environment):
- `catalogue.machine_specification() -> dict`: the asset specification of the SDG scene (`assets`, `parts`, `fleet`,
  `labels`), one asset per SDG machine class with a citation per dimension and per part; `catalogue.ASSET_IDS` maps a
  class (`haul_truck`, `shovel`, `light_vehicle`, `person`) to its asset file stem and `catalogue.ENVELOPES` to its
  (length, width, height) in metres: the footprint the parameter table places and the box the asset fills.
- `build_assets(spec, out_dir)` writes `assets/<asset id>.usda` for every machine and `assets/person-mannequin.usda`;
  `AssetBuild.person_asset` is the path of the last. Geometry is a function of the specification only (bitwise).
- Every visible gprim carries one `class` label and one `part` label and is bound to a `UsdPreviewSurface` material
  named for paint, rubber, steel, glass, skin or fabric; the collision boxes of the rigid bodies have the `guide` purpose.
- `SdgRenderer._build_object` references `assets/<asset id>.usda` of the scene for every class and authors no mesh.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
from pitstudio_studio.scene import assets  # noqa: E402
from pitstudio_studio.scene.assets import catalogue  # noqa: E402
from pitstudio_studio.scene.common import SceneStageError  # noqa: E402

MATERIAL_KINDS = ("paint", "rubber", "steel", "glass", "skin", "fabric")
CLASSES = ("haul_truck", "shovel", "light_vehicle", "person")
PART_LABELS = {  # the part labels each class must show on its visible geometry
    "haul_truck": {"chassis", "cab", "dump_body", "axle", "wheel"},
    "shovel": {"undercarriage", "track", "house", "boom", "stick", "dipper"},
    "light_vehicle": {"chassis", "cab", "wheel"},
    "person": {"head", "torso", "arm", "leg", "hard_hat", "vest"},
}
MIN_VISIBLE_PIECES = {"haul_truck": 30, "shovel": 30, "light_vehicle": 14, "person": 10}
_OPEN: list = []  # stages stay open as long as the prims taken from them are used


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    spec = catalogue.machine_specification()
    out = tmp_path_factory.mktemp("assets")
    return spec, assets.build_assets(spec, out), out


def _asset_file(build, cls: str) -> Path:
    if cls == "person":
        return Path(build.person_asset)
    return Path(build.machines[catalogue.ASSET_IDS[cls]])


def _stage(path):
    from pxr import Usd

    stage = Usd.Stage.Open(str(path))
    _OPEN.append(stage)
    return stage


def _gprims(stage):
    from pxr import Usd, UsdGeom

    return [p for p in Usd.PrimRange(stage.GetPseudoRoot(), Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Gprim)]


def _visible(stage):
    from pxr import UsdGeom

    return [p for p in _gprims(stage) if UsdGeom.Imageable(p).GetPurposeAttr().Get() != UsdGeom.Tokens.guide]


def _label(prim, instance):
    from pxr import UsdSemantics

    attr = UsdSemantics.LabelsAPI(prim, instance).GetLabelsAttr()
    return list(attr.Get() or []) if attr else []


def _bbox(prims):
    from pxr import Gf, Usd, UsdGeom

    cache = UsdGeom.BBoxCache(Usd.TimeCode.Default(), [UsdGeom.Tokens.default_, UsdGeom.Tokens.render])
    box = Gf.Range3d()
    for prim in prims:
        box.UnionWith(cache.ComputeWorldBound(prim).ComputeAlignedRange())
    return box


def _volume(box) -> float:
    size = box.GetSize()
    return float(size[0] * size[1] * size[2])


@pytest.mark.req("FR-004-51")
def test_the_specification_cites_every_dimension_and_validates(built) -> None:
    spec, _, _ = built
    assets.validate_spec(spec, None) if not spec["materials"] else None
    assert {a["class_label"] for a in spec["assets"]} == {"haul_truck", "shovel", "light_vehicle"}
    for asset in spec["assets"]:
        assert asset["dimensions_citation"].strip() and asset["mass_citation"].strip()
        parts = [p for p in spec["parts"] if p["asset"] == asset["id"]]
        assert len(parts) >= 3 and all(p["citation"].strip() for p in parts)
        assert abs(sum(p["mass_kg"] for p in parts) - asset["mass_kg"]) <= 1e-6 * asset["mass_kg"]
    assert set(catalogue.ASSET_IDS) == set(CLASSES)


@pytest.mark.req("FR-004-51")
def test_a_part_without_a_dimension_fails_naming_the_part(tmp_path: Path) -> None:
    spec = catalogue.machine_specification()
    target = next(p for p in spec["parts"] if p["part"] == "dump_body")
    del target["height_m"]
    with pytest.raises(SceneStageError) as caught:
        assets.build_assets(spec, tmp_path / "out")
    assert target["id"] in str(caught.value) and not (tmp_path / "out").exists()


@pytest.mark.req("FR-004-51")
@pytest.mark.parametrize("cls", CLASSES)
def test_each_class_shows_the_parts_of_the_requirement_on_labelled_geometry(built, cls: str) -> None:
    _, build, _ = built
    stage = _stage(_asset_file(build, cls))
    visible = _visible(stage)
    assert len(visible) >= MIN_VISIBLE_PIECES[cls], (cls, len(visible))
    wanted = "person" if cls == "person" else cls
    for prim in visible:
        assert _label(prim, "class") == [wanted], prim.GetPath()
        assert len(_label(prim, "part")) == 1, prim.GetPath()
    assert {_label(p, "part")[0] for p in visible} >= PART_LABELS[cls]


@pytest.mark.req("FR-004-51")
def test_axle_and_tyre_counts_of_the_haul_truck_and_the_light_vehicle(built) -> None:
    from pxr import Usd, UsdPhysics

    _, build, _ = built
    for cls, wheels, axles in (("haul_truck", 6, 2), ("light_vehicle", 4, 0)):
        stage = _stage(_asset_file(build, cls))
        bodies = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
        labels = [_label(b, "part")[0] for b in bodies]
        assert labels.count("wheel") == wheels and labels.count("axle") == axles, (cls, labels)
    stage = _stage(_asset_file(build, "haul_truck"))
    joints = {
        j.GetPrim().GetName(): (j.GetBody0Rel().GetTargets()[0].name, j.GetBody1Rel().GetTargets()[0].name)
        for j in (UsdPhysics.RevoluteJoint(p) for p in stage.Traverse() if p.IsA(UsdPhysics.RevoluteJoint))
    }
    by_axle: dict[str, int] = {}
    for parent, child in joints.values():
        if "wheel" in child:
            by_axle[parent] = by_axle.get(parent, 0) + 1
    assert sorted(by_axle.values()) == [2, 4], by_axle  # two tyres on the front axle, four on the rear axle


@pytest.mark.req("FR-004-51")
def test_the_shovel_and_the_person_have_their_counts_of_tracks_arms_and_legs(built) -> None:
    from pxr import Usd, UsdPhysics

    _, build, _ = built
    stage = _stage(_asset_file(build, "shovel"))
    bodies = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
    assert [_label(b, "part")[0] for b in bodies].count("track") == 2
    person = _stage(_asset_file(build, "person"))
    names = [p.GetName() for p in _visible(person)]
    for stem, count in (("Arm", 2), ("Leg", 2), ("Head", 1), ("HardHat", 1), ("Vest", 1)):
        assert sum(1 for n in names if n.startswith(stem)) >= count, (stem, names)


@pytest.mark.req("FR-004-51")
@pytest.mark.parametrize("cls", CLASSES)
def test_every_visible_piece_has_a_usd_preview_surface_of_a_named_kind(built, cls: str) -> None:
    from pxr import UsdShade

    _, build, _ = built
    stage = _stage(_asset_file(build, cls))
    kinds = set()
    for prim in _visible(stage):
        material, _ = UsdShade.MaterialBindingAPI(prim).ComputeBoundMaterial()
        assert material, f"{prim.GetPath()} has no material"
        kind = material.GetPrim().GetName().split("_")[0]
        assert kind in MATERIAL_KINDS, material.GetPath()
        shader = UsdShade.Shader(material.ComputeSurfaceSource()[0])
        assert shader.GetShaderId() == "UsdPreviewSurface", material.GetPath()
        kinds.add(kind)
    assert len(kinds) >= (3 if cls != "person" else 3), (cls, kinds)
    if cls == "person":
        assert {"skin", "fabric"} <= kinds
    else:
        assert {"paint", "steel", "glass"} <= kinds
    if cls in ("haul_truck", "light_vehicle"):
        assert "rubber" in kinds


@pytest.mark.req("FR-004-51")
@pytest.mark.parametrize("cls", CLASSES)
def test_no_piece_is_a_single_box_standing_for_the_machine(built, cls: str) -> None:
    _, build, _ = built
    stage = _stage(_asset_file(build, cls))
    visible = _visible(stage)
    whole = _volume(_bbox(visible))
    largest = max(_volume(_bbox([p])) for p in visible)
    assert largest < 0.35 * whole, (cls, largest / whole)
    assert len({p.GetName() for p in visible}) >= MIN_VISIBLE_PIECES[cls] // 2


@pytest.mark.req("FR-004-51")
@pytest.mark.parametrize("cls", CLASSES)
def test_the_asset_fills_the_footprint_the_table_places(built, cls: str) -> None:
    _, build, _ = built
    stage = _stage(_asset_file(build, cls))
    size = _bbox(_visible(stage)).GetSize()
    length, width, height = catalogue.ENVELOPES[cls]
    assert abs(size[2] - height) <= 0.05 * height + 0.02, (cls, size[2], height)
    assert size[0] <= length + 0.05 and size[1] <= width + 0.05, (cls, tuple(size), (length, width))
    assert size[0] >= 0.6 * length and size[1] >= 0.6 * width, (cls, tuple(size), (length, width))
    box = _bbox(_visible(stage))
    assert abs(box.GetMin()[2]) <= 0.02, "the asset stands on z = 0"


@pytest.mark.req("FR-004-51")
def test_the_collision_boxes_are_guides_and_every_body_still_has_mass_and_a_collider(built) -> None:
    from pxr import Usd, UsdGeom, UsdPhysics

    spec, build, _ = built
    for asset in spec["assets"]:
        stage = _stage(build.machines[asset["id"]])
        bodies = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
        assert len(bodies) == len([p for p in spec["parts"] if p["asset"] == asset["id"]])
        for body in bodies:
            colliders = [p for p in Usd.PrimRange(body) if p.HasAPI(UsdPhysics.CollisionAPI)]
            assert colliders
            for c in colliders:
                assert UsdGeom.Imageable(c).GetPurposeAttr().Get() == UsdGeom.Tokens.guide


@pytest.mark.req("FR-004-51")
def test_two_builds_are_identical_byte_for_byte(tmp_path: Path) -> None:
    spec = catalogue.machine_specification()
    a = assets.build_assets(spec, tmp_path / "a")
    b = assets.build_assets(spec, tmp_path / "b")
    for name, path in {**a.machines, "person": a.person_asset}.items():
        other = {**b.machines, "person": b.person_asset}[name]
        assert Path(path).read_bytes() == Path(other).read_bytes(), name


@pytest.mark.req("FR-004-51")
def test_the_people_of_the_fleet_layer_are_the_articulated_mannequin(tmp_path: Path) -> None:
    spec = catalogue.machine_specification()
    spec["people_count"] = 3
    build = assets.build_assets(spec, tmp_path / "out")
    stage = _stage(build.fleet_layer)
    root = stage.GetPrimAtPath("/World/People")
    for person in root.GetChildren():
        assert person.GetAttribute("pitstudio:provenance").Get() == "procedural-mannequin"
        parts = {_label(p, "part")[0] for p in _gprims_below(person)}
        assert parts >= PART_LABELS["person"]


def _gprims_below(prim):
    from pxr import Usd, UsdGeom

    return [p for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Gprim)]


@pytest.mark.req("FR-004-51")
@pytest.mark.parametrize("cls", CLASSES)
def test_the_sdg_renderer_references_the_asset_of_every_class_and_authors_no_mesh(built, cls: str) -> None:
    from pxr import Usd, UsdGeom

    from pitstudio_isaac.sdg import scene_render

    spec, build, out = built
    stage = Usd.Stage.CreateInMemory()
    UsdGeom.Xform.Define(stage, "/World")
    UsdGeom.Xform.Define(stage, scene_render.OBJECT_ROOT)
    renderer = scene_render.SdgRenderer.__new__(scene_render.SdgRenderer)
    renderer._stage, renderer.scene_dir = stage, out  # the scene folder holds `assets/`
    length, width, height = catalogue.ENVELOPES[cls]
    obj = {"prim_id": f"{scene_render.OBJECT_ROOT}/Obj_00", "class": cls, "length_m": length, "width_m": width, "height_m": height}
    renderer._build_object(obj, {"x_m": 1.0, "y_m": 2.0, "z_m": 3.0, "yaw_deg": 30.0})
    prim = stage.GetPrimAtPath(obj["prim_id"])
    assert prim.HasAuthoredReferences()
    own = stage.GetRootLayer().GetPrimAtPath(obj["prim_id"])
    assert len(own.nameChildren) == 0, "the renderer authors no geometry of its own"
    gprims = [p for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Gprim)]
    assert len(gprims) >= MIN_VISIBLE_PIECES[cls]
    assert all(_label(p, "class") == [cls] for p in gprims)
    assert _label(prim, "obj") == ["Obj_00"]
