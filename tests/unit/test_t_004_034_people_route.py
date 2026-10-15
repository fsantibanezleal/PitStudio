# ruff: noqa: E501, PT018
"""T-004-034: MakeHuman route versus procedural mannequins, recorded.

Requirements: FR-004-28.

Oracle: expected provenance attribute values and the expected route strings are written in this test (spec section 3.3:
"procedural-mannequin" provenance, route recorded in the scene manifest as `people_route`); the MakeHuman export set is a
fixture directory holding one 8-vertex OBJ box (a stand-in for a CC0 export), whose vertex count is the reference for the
imported mesh; the manifest field is validated with the DC-004-02 draft schema.

Expected API (package `pitstudio_studio.scene.assets`, studio environment): `assets.build_assets(spec, out_dir, *,
makehuman_dir=None, makehuman_smoke_passed=False)` (see test_t_004_030) sets `AssetBuild.people_route` to `"makehuman"`
when `makehuman_dir` holds at least one `.obj` export and `makehuman_smoke_passed` is true, otherwise to
`"procedural-mannequin"`. `AssetBuild.fleet_layer` has `spec["people_count"]` person instances as direct children of
`/World/People`; each person root prim has `pitstudio:provenance` = `"procedural-mannequin"` or `"makehuman-export"` (the
route used), and every geometry prim below it has the class label `person`. In the MakeHuman route the person mesh is the
OBJ mesh (same vertex count); in the mannequin route it is built from boxes and capsules by our code.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import assets  # noqa: E402

BOX_OBJ = """# fixture: a 0.5 x 0.5 x 1.8 m box standing on z = 0
v 0 0 0
v 0.5 0 0
v 0.5 0.5 0
v 0 0.5 0
v 0 0 1.8
v 0.5 0 1.8
v 0.5 0.5 1.8
v 0 0.5 1.8
f 1 3 2
f 1 4 3
f 5 6 7
f 5 7 8
f 1 2 6
f 1 6 5
f 2 3 7
f 2 7 6
f 3 4 8
f 3 8 7
f 4 1 5
f 4 5 8
"""


def _spec(people: int) -> dict:
    spec = kit.machine_spec(("haul_truck",))
    spec["people_count"] = people
    return spec


_STAGES: list = []  # the stages stay open as long as the prims returned from them are used


def _people(build) -> list:
    from pxr import Usd

    stage = Usd.Stage.Open(str(build.fleet_layer))
    _STAGES.append(stage)
    root = stage.GetPrimAtPath("/World/People")
    return [c for c in root.GetChildren()] if root.IsValid() else []


def _gprims(prim) -> list:
    from pxr import Usd, UsdGeom

    return [p for p in Usd.PrimRange(prim, Usd.TraverseInstanceProxies()) if p.IsA(UsdGeom.Gprim)]


def _check_people(build, count: int, provenance: str) -> None:
    from pxr import UsdSemantics

    people = _people(build)
    assert len(people) == count
    for person in people:
        assert person.GetAttribute("pitstudio:provenance").Get() == provenance
        geometry = _gprims(person)
        assert geometry
        for g in geometry:
            assert list(UsdSemantics.LabelsAPI(g, "class").GetLabelsAttr().Get()) == ["person"]


@pytest.mark.req("FR-004-28")
def test_without_a_makehuman_set_people_are_labelled_procedural_mannequins(tmp_path: Path) -> None:
    build = assets.build_assets(_spec(4), tmp_path / "out")
    assert build.people_route == "procedural-mannequin"
    _check_people(build, 4, "procedural-mannequin")


@pytest.mark.req("FR-004-28")
def test_an_export_set_whose_smoke_test_did_not_pass_is_not_used(tmp_path: Path) -> None:
    export = tmp_path / "mh"
    export.mkdir()
    (export / "person_01.obj").write_text(BOX_OBJ, encoding="utf-8")
    build = assets.build_assets(_spec(2), tmp_path / "out", makehuman_dir=export, makehuman_smoke_passed=False)
    assert build.people_route == "procedural-mannequin"
    _check_people(build, 2, "procedural-mannequin")


@pytest.mark.req("FR-004-28")
def test_a_passed_smoke_test_without_an_export_falls_back_to_mannequins(tmp_path: Path) -> None:
    empty = tmp_path / "mh_empty"
    empty.mkdir()
    for directory in (empty, tmp_path / "mh_missing"):
        build = assets.build_assets(
            _spec(3), tmp_path / f"out_{directory.name}", makehuman_dir=directory, makehuman_smoke_passed=True
        )
        assert build.people_route == "procedural-mannequin"
        _check_people(build, 3, "procedural-mannequin")


@pytest.mark.req("FR-004-28")
def test_a_present_and_smoke_tested_export_set_is_used_for_people(tmp_path: Path) -> None:
    from pxr import UsdGeom

    export = tmp_path / "mh"
    export.mkdir()
    (export / "person_01.obj").write_text(BOX_OBJ, encoding="utf-8")
    build = assets.build_assets(_spec(3), tmp_path / "out", makehuman_dir=export, makehuman_smoke_passed=True)
    assert build.people_route == "makehuman"
    _check_people(build, 3, "makehuman-export")
    for person in _people(build):
        meshes = [g for g in _gprims(person) if g.IsA(UsdGeom.Mesh)]
        assert any(len(UsdGeom.Mesh(m).GetPointsAttr().Get()) == 8 for m in meshes)  # the OBJ box, 8 vertices


@pytest.mark.req("FR-004-28")
def test_the_route_is_a_valid_manifest_field_in_both_branches(tmp_path: Path) -> None:
    export = tmp_path / "mh"
    export.mkdir()
    (export / "person_01.obj").write_text(BOX_OBJ, encoding="utf-8")
    manifest = json.loads((kit.EXAMPLES / "scene-manifest.valid.json").read_text(encoding="utf-8"))
    for kwargs, route in (
        ({}, "procedural-mannequin"),
        ({"makehuman_dir": export, "makehuman_smoke_passed": True}, "makehuman"),
    ):
        build = assets.build_assets(_spec(1), tmp_path / f"out_{route}", **kwargs)
        assert build.people_route == route
        manifest["people_route"] = build.people_route
        assert kit.schema_errors("scene-manifest.schema.json", manifest) == []


@pytest.mark.req("FR-004-28")
def test_zero_people_add_no_person_prims(tmp_path: Path) -> None:
    build = assets.build_assets(_spec(0), tmp_path / "out")
    assert _people(build) == [] and build.people_route == "procedural-mannequin"
