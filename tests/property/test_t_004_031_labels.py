# ruff: noqa: E501, PT018
"""T-004-031: class and part labels from the closed vocabulary, no time samples; label completeness.

Requirements: FR-004-25, P-004-12.

Oracle: the closed vocabularies of the SceneSpec (DC-004-01: 15 class labels, 18 part labels), the part labels written
in the test's asset specification, and OpenUSD (`UsdSemantics.LabelsAPI`, `GetNumTimeSamples`, reference implementation);
P-004-12 is checked by exact counts on a composed fleet layer for random fleets (0-20 machines) and people (0-30).

Expected API (package `pitstudio_studio.scene.assets`, studio environment): `assets.build_assets(spec, out_dir)` as in
test_t_004_030, plus `AssetBuild.fleet_layer` (a `Path` to `<out_dir>/layers/fleet.usda`): a layer that references the
machine files `spec["fleet"][i]["count"]` times each and adds `spec["people_count"]` people (procedural mannequins unless
a MakeHuman set is supplied), with the machine files referenced by relative paths. Labels follow the `SemanticsLabelsAPI`
schema (`UsdSemantics.LabelsAPI` with the instance names `class` and `part`):
- every geometry prim (`UsdGeom.Gprim`) has exactly one `class` label, from `spec["labels"]["classes"]`: the machine's
  `class_label`, or `person`;
- every articulated body of a machine (each prim with `UsdPhysics.RigidBodyAPI`) has a `part` label, from
  `spec["labels"]["parts"]`: the part's `part` value;
- no label attribute has time samples.
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import assets  # noqa: E402


def _traverse(stage):
    from pxr import Usd

    return Usd.PrimRange.Stage(stage, Usd.TraverseInstanceProxies())


def _labels(prim, instance: str):
    from pxr import UsdSemantics

    attr = UsdSemantics.LabelsAPI(prim, instance).GetLabelsAttr()
    return list(attr.Get() or []) if attr else [], attr


@pytest.mark.req("FR-004-25")
def test_machine_geometry_has_one_class_label_and_bodies_have_part_labels(tmp_path: Path) -> None:
    from pxr import Usd, UsdGeom, UsdPhysics

    spec = kit.machine_spec()
    build = assets.build_assets(spec, tmp_path)
    for asset in spec["assets"]:
        stage = Usd.Stage.Open(str(build.machines[asset["id"]]))
        gprims = [p for p in _traverse(stage) if p.IsA(UsdGeom.Gprim)]
        assert gprims
        for prim in gprims:
            labels, attr = _labels(prim, "class")
            assert labels == [asset["class_label"]], (prim.GetPath(), labels)
            assert attr.GetNumTimeSamples() == 0
        bodies = [p for p in _traverse(stage) if p.HasAPI(UsdPhysics.RigidBodyAPI)]
        got = sorted(_labels(b, "part")[0][0] for b in bodies if _labels(b, "part")[0])
        assert got == sorted(p["part"] for p in spec["parts"] if p["asset"] == asset["id"])
        for b in bodies:
            labels, attr = _labels(b, "part")
            assert len(labels) == 1 and labels[0] in kit.ALL_PARTS
            assert attr.GetNumTimeSamples() == 0


@pytest.mark.req("FR-004-25")
def test_labels_are_never_animated_anywhere_in_the_layer_text(tmp_path: Path) -> None:
    build = assets.build_assets(kit.machine_spec(), tmp_path)
    for path in build.machines.values():
        assert "semantics:labels" in Path(path).read_text(encoding="utf-8")
    # an animated label would be authored as `token[] semantics:labels:class.timeSamples = {`
    for path in [*build.machines.values(), build.fleet_layer]:
        for line in Path(path).read_text(encoding="utf-8").splitlines():
            assert not ("semantics:labels" in line and "timeSamples" in line), line


@pytest.mark.req("P-004-12")
@settings(max_examples=15, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(
    counts=st.lists(st.integers(0, 4), min_size=7, max_size=7).filter(lambda c: sum(c) <= 20),
    people=st.integers(0, 30),
)
def test_every_geometry_prim_of_a_random_composed_fleet_has_exactly_one_class_label(
    counts: list[int], people: int
) -> None:
    """P-004-12: random fleets (0-20 machines) and people (0-30): exact label counts on the composed layer."""
    from pxr import Usd, UsdGeom, UsdPhysics

    spec = kit.machine_spec()
    spec["fleet"] = [{"asset": a["id"], "count": n} for a, n in zip(spec["assets"], counts, strict=True) if n > 0]
    spec["people_count"] = people
    with tempfile.TemporaryDirectory() as td:
        build = assets.build_assets(spec, Path(td))
        stage = Usd.Stage.Open(str(build.fleet_layer))
        vocabulary = set(spec["labels"]["classes"])
        n_person_gprims = 0
        for prim in _traverse(stage):
            if prim.IsA(UsdGeom.Gprim):
                labels, attr = _labels(prim, "class")
                assert len(labels) == 1 and labels[0] in vocabulary, (prim.GetPath(), labels)
                assert attr.GetNumTimeSamples() == 0
                n_person_gprims += labels[0] == "person"
        roots = [p for p in _traverse(stage) if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        assert len(roots) == sum(counts)  # one articulation root per machine instance
        assert (n_person_gprims >= people) and (people > 0 or n_person_gprims == 0)
