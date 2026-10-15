# ruff: noqa: E501, PT018
"""T-004-041: scene digest for the export parity test.

Requirements: FR-004-31.

Oracle: the hand-computed world transform of a two-level transform hierarchy (see `scene_kit.CHASSIS_WORLD`: truck
translate (10, 20, 5), body rotate Z 90 deg, chassis translate (1, 0, 0), USD row-vector convention, translation in
elements 12-14; the origin of the chassis maps to (10, 21, 5)), the vertex and face counts of the fixture quads (4 and 2),
and the DC-004-08 draft schema.

Expected API: `compose.compose_scene` (test_t_004_040) also writes `scene.digest.json` (`SceneBuild.digest`,
`SceneBuild.digest_path`): for every lod name of `spec["variants"]["lod"]`, the geometry prims (`UsdGeom.Mesh`) of the
stage flattened with that lod variant selected on `/World`, sorted by path, each with `path`, `transform` (the world
transform, 16 floats, row-major, float64), `vertices`, `faces` (face counts), `class` and, when present, `part`.
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
from pitstudio_studio.scene import compose  # noqa: E402


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory):
    base = tmp_path_factory.mktemp("digest")
    spec = kit.scene_spec()
    up = kit.fixture_upstream(base / "up")
    return spec, compose.compose_scene(spec, up, base / "scene")


@pytest.mark.req("FR-004-31")
def test_digest_is_valid_and_written_next_to_the_manifest(built) -> None:
    spec, build = built
    on_disk = json.loads(build.digest_path.read_text(encoding="utf-8"))
    assert on_disk == build.digest and build.digest_path.name == "scene.digest.json"
    assert kit.schema_errors("scene-digest.schema.json", on_disk) == []
    d = build.digest
    assert (d["case"], d["manifest_id"], d["params_sha256"]) == (
        spec["case"],
        build.manifest["manifest_id"],
        build.manifest["params_sha256"],
    )
    assert [lod["lod"] for lod in d["lods"]] == spec["variants"]["lod"]


@pytest.mark.req("FR-004-31")
def test_geometry_prims_per_lod_are_sorted_by_path_with_counts_and_labels(built) -> None:
    _, build = built
    for i, lod in enumerate(build.digest["lods"]):
        paths = [p["path"] for p in lod["prims"]]
        assert paths == sorted(paths)
        assert paths == [
            "/World/Design/Bench_00",
            "/World/Fleet/Truck_00/Body/Chassis",
            f"/World/Terrain/Lod{i}/Tile_{i}_0_0_0",
        ]  # only the selected lod's terrain tile
        by_path = {p["path"]: p for p in lod["prims"]}
        assert all((p["vertices"], p["faces"]) == (4, 2) for p in lod["prims"])  # quads: 4 vertices, 2 triangles
        assert by_path["/World/Design/Bench_00"]["class"] == "bench"
        assert by_path[f"/World/Terrain/Lod{i}/Tile_{i}_0_0_0"]["class"] == "terrain"
        chassis = by_path["/World/Fleet/Truck_00/Body/Chassis"]
        assert (chassis["class"], chassis["part"]) == ("haul_truck", "chassis")
        assert "part" not in by_path["/World/Design/Bench_00"]


@pytest.mark.req("FR-004-31")
def test_world_transform_of_a_two_level_hierarchy_matches_the_hand_calculation(built) -> None:
    _, build = built
    for lod in build.digest["lods"]:
        by_path = {p["path"]: p for p in lod["prims"]}
        chassis = by_path["/World/Fleet/Truck_00/Body/Chassis"]["transform"]
        assert len(chassis) == 16
        assert chassis == pytest.approx(kit.CHASSIS_WORLD, abs=1e-12)  # row-major, translation in 12-14
        assert by_path["/World/Design/Bench_00"]["transform"] == pytest.approx(kit.IDENTITY16, abs=1e-12)
        assert all(isinstance(x, float) for x in chassis)


@pytest.mark.req("FR-004-31")
def test_digest_agrees_with_the_flattened_stage_under_each_lod_selection(built) -> None:
    from pxr import Usd, UsdGeom

    _, build = built
    stage = Usd.Stage.Open(str(build.root))
    for lod in build.digest["lods"]:
        stage.GetPrimAtPath("/World").GetVariantSet("lod").SetVariantSelection(lod["lod"])
        meshes = sorted(str(p.GetPath()) for p in Usd.PrimRange(stage.GetPseudoRoot()) if p.IsA(UsdGeom.Mesh))
        assert meshes == [p["path"] for p in lod["prims"]]
        for entry in lod["prims"]:
            xf = UsdGeom.Xformable(stage.GetPrimAtPath(entry["path"])).ComputeLocalToWorldTransform(
                Usd.TimeCode.Default()
            )
            assert entry["transform"] == pytest.approx([xf[i][j] for i in range(4) for j in range(4)], abs=1e-12)
