# ruff: noqa: E501, PT018
"""T-004-030: procedural machines with an articulation root, rigid bodies, mass, collision and a joint tree.

Requirements: FR-004-24.

Oracle: USD schema queries through OpenUSD (`UsdPhysics` `HasAPI` and attribute reads, reference implementation) against
the masses, joint types, axes and limits written in the test's asset specification (hand-written fixture, one machine
per class); the joint-graph tree check is a breadth-first search written here (plan.md names networkx, which is not part
of the studio environment).

Expected API (package `pitstudio_studio.scene.assets`, studio environment):
- `assets.build_assets(spec, out_dir, *, textures=None, makehuman_dir=None, makehuman_smoke_passed=False)` ->
  `AssetBuild`. For every entry of `spec["assets"]` it writes `<out_dir>/assets/<asset id>.usda` and exposes it as
  `AssetBuild.machines[<asset id>]` (a `Path`). A machine file has the default prim of the machine; exactly one prim
  with `UsdPhysics.ArticulationRootAPI`; one rigid body (`RigidBodyAPI`) per entry of `spec["parts"]` of that asset, each
  with `MassAPI` (the part's mass) and a convex collider (`CollisionAPI` on the body or a child; a Mesh collider has
  `MeshCollisionAPI` approximation `convexHull`); one `UsdPhysics.RevoluteJoint` (axis, lower/upper limit in degrees) or
  `PrismaticJoint` (axis, limits in metres) per non-root part, `body0` = the parent body and `body1` = the part, each
  with a `PhysicsLimitAPI:*` and a `PhysicsDriveAPI:*` applied; the joints form a tree over the bodies. A part with
  `exclude_from_articulation: true` has its joint authored with `physics:excludeFromArticulation = true`.
"""

from __future__ import annotations

import sys
from collections import deque
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import assets  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    spec = kit.machine_spec()
    assert kit.schema_errors("scene-spec.schema.json", spec) == []  # the fixture itself is a valid SceneSpec
    out = tmp_path_factory.mktemp("assets")
    return spec, assets.build_assets(spec, out)


def _stage(path: Path):
    from pxr import Usd

    return Usd.Stage.Open(str(path))


def _bodies(stage):
    from pxr import Usd, UsdPhysics

    return [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.RigidBodyAPI)]


def _joints(stage):
    from pxr import Usd, UsdPhysics

    return [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.IsA(UsdPhysics.Joint)]


@pytest.mark.req("FR-004-24")
def test_one_machine_file_per_asset(built) -> None:
    spec, build = built
    assert sorted(build.machines) == sorted(a["id"] for a in spec["assets"])
    assert all(Path(p).is_file() and Path(p).suffix == ".usda" for p in build.machines.values())


@pytest.mark.req("FR-004-24")
def test_exactly_one_articulation_root_per_machine(built) -> None:
    from pxr import Usd, UsdPhysics

    _, build = built
    for aid, path in build.machines.items():
        stage = _stage(path)  # keep the stage alive while its prims are iterated
        roots = [p for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.HasAPI(UsdPhysics.ArticulationRootAPI)]
        assert len(roots) == 1, (aid, [str(r.GetPath()) for r in roots])


@pytest.mark.req("FR-004-24")
def test_every_body_has_positive_mass_equal_to_the_part_mass_and_a_convex_collider(built) -> None:
    from pxr import Usd, UsdGeom, UsdPhysics

    spec, build = built
    for asset in spec["assets"]:
        stage = _stage(build.machines[asset["id"]])
        want = sorted(p["mass_kg"] for p in spec["parts"] if p["asset"] == asset["id"])
        bodies = _bodies(stage)
        masses = sorted(float(UsdPhysics.MassAPI(b).GetMassAttr().Get()) for b in bodies)
        assert masses == pytest.approx(want, rel=1e-9) and min(masses) > 0.0
        assert sum(masses) == pytest.approx(asset["mass_kg"], rel=1e-9)  # parts add up to the machine
        for body in bodies:
            colliders = [p for p in Usd.PrimRange(body) if p.HasAPI(UsdPhysics.CollisionAPI)]
            assert colliders, f"{body.GetPath()} has no collider"
            for c in colliders:
                if c.IsA(UsdGeom.Mesh):
                    assert UsdPhysics.MeshCollisionAPI(c).GetApproximationAttr().Get() == "convexHull"


@pytest.mark.req("FR-004-24")
def test_joints_match_the_part_specification_and_carry_limit_and_drive_apis(built) -> None:
    from pxr import UsdPhysics

    spec, build = built
    for asset in spec["assets"]:
        stage = _stage(build.machines[asset["id"]])
        parts = [p for p in spec["parts"] if p["asset"] == asset["id"] and p["parent"] is not None]
        joints = _joints(stage)
        assert len(joints) == len(parts)
        got, want = [], []
        for j in joints:
            schemas = j.GetAppliedSchemas()
            assert any(s.startswith("PhysicsLimitAPI:") for s in schemas), (j.GetPath(), schemas)
            assert any(s.startswith("PhysicsDriveAPI:") for s in schemas), (j.GetPath(), schemas)
            if j.IsA(UsdPhysics.RevoluteJoint):
                r = UsdPhysics.RevoluteJoint(j)
                got.append(
                    (
                        "revolute",
                        r.GetAxisAttr().Get(),
                        float(r.GetLowerLimitAttr().Get()),
                        float(r.GetUpperLimitAttr().Get()),
                    )
                )
            else:
                assert j.IsA(UsdPhysics.PrismaticJoint), j.GetTypeName()
                p = UsdPhysics.PrismaticJoint(j)
                got.append(
                    (
                        "prismatic",
                        p.GetAxisAttr().Get(),
                        float(p.GetLowerLimitAttr().Get()),
                        float(p.GetUpperLimitAttr().Get()),
                    )
                )
        for part in parts:
            lo, hi = (
                (part["lower_deg"], part["upper_deg"])
                if part["joint"] == "revolute"
                else (part["lower_m"], part["upper_m"])
            )
            want.append((part["joint"], part["axis"], float(lo), float(hi)))
        assert sorted(got) == sorted(want)


@pytest.mark.req("FR-004-24")
def test_joint_graph_is_a_tree_over_the_bodies(built) -> None:
    from pxr import UsdPhysics

    spec, build = built
    for asset in spec["assets"]:
        stage = _stage(build.machines[asset["id"]])
        bodies = {str(b.GetPath()) for b in _bodies(stage)}
        adj: dict[str, set[str]] = {b: set() for b in bodies}
        edges = 0
        for j in _joints(stage):
            joint = UsdPhysics.Joint(j)
            if j.GetAttribute("physics:excludeFromArticulation").Get():
                continue
            (b0,), (b1,) = joint.GetBody0Rel().GetTargets(), joint.GetBody1Rel().GetTargets()
            adj[str(b0)].add(str(b1))
            adj[str(b1)].add(str(b0))
            edges += 1
        assert edges == len(bodies) - 1  # a tree has N - 1 edges ...
        start = next(iter(bodies))
        seen, queue = {start}, deque([start])
        while queue:
            for nxt in adj[queue.popleft()] - seen:
                seen.add(nxt)
                queue.append(nxt)
        assert seen == bodies  # ... and is connected: no cycle, one root


@pytest.mark.req("FR-004-24")
def test_all_seven_machine_classes_are_built(built) -> None:
    spec, _ = built
    assert {a["class_label"] for a in spec["assets"]} == {
        "haul_truck",
        "shovel",
        "excavator",
        "wheel_loader",
        "water_truck",
        "light_vehicle",
        "crusher",
    }


@pytest.mark.req("FR-004-24")
def test_a_loop_closing_joint_is_excluded_from_the_articulation(tmp_path: Path) -> None:
    spec = kit.machine_spec(("wheel_loader",))
    for part in spec["parts"]:
        if part["id"] == "lift-arm":
            part["exclude_from_articulation"] = True  # this joint closes a kinematic loop
    stage = _stage(assets.build_assets(spec, tmp_path).machines["loader-l1350"])
    flags = {
        str(j.GetPath()).rsplit("/", 1)[-1]: bool(j.GetAttribute("physics:excludeFromArticulation").Get())
        for j in _joints(stage)
    }
    assert sorted(flags.values()) == [False, False, True]  # one of three joints is excluded; the others are not
