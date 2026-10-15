# ruff: noqa: PT018
"""T-009-016 (fix): the SDG parameter table is built from the real spec 004 scene format (FR-009-04 .. FR-009-08).

Requirements: FR-009-02, FR-009-03, FR-009-04, FR-009-05, FR-009-06, FR-009-07, FR-009-08, FR-009-44.

`scene_inputs` reads the validated scene (manifest, pit design report, road network), `dust_field` is the scenario plume
field, `table` draws every per-image value and `finalize` turns the rendered frames into frame states and the dataset
index. The scene here is built by hand in the formats of `specs/004-scene-pipeline/contracts`: three straight road edges
with a known slope, so heights, polygons and distances are hand calculations.

Oracles: shapely point-in-polygon for the placements, the road slope for the design height, the infinite-line formula of
`minephys.environment.line_source_plume` for the plume of a very long road, the worked geometry of the UTM zone for the
site centroid, the dataset and frame-state schemas for every row and index record.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import math
import sys
from pathlib import Path

import numpy as np
import pytest
import shapely
from minephys import environment

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "studio" / "isaac" / "src"))
from pitstudio_isaac.sdg import driver  # noqa: E402
from pitstudio_isaac.sdg.cpu_renderer import CpuRenderer  # noqa: E402
from pitstudio_studio.sdg import dust_field, finalize, table  # noqa: E402
from pitstudio_studio.sdg.config import validate_config  # noqa: E402
from pitstudio_studio.sdg.scene_inputs import SceneInputsError, load_scene_inputs  # noqa: E402

POOL = [{"id": f"tex-{i}", "source_id": "polyhaven", "sha256": f"{i:064x}", "spdx": "CC0-1.0"} for i in range(1, 6)]
RECIPE = {
    "schema_version": "1.0",
    "seed": 20261007,
    "x_os_m": 1.0,
    "drying_time_min": 60,
    "arms": [
        {"family": "pit", "arm": "structured", "image_count": 30, "seed_source": "own"},
        {"family": "crusher", "arm": "structured", "image_count": 30, "seed_source": "own"},
        {"family": "pit", "arm": "unstructured", "image_count": 40, "seed_source": "structured-pit-train"},
    ],
    "structured": {
        "sun": {"source": "solar-position", "year": 2025, "min_elevation_deg": 5},
        "dust": {"source": "plume-field"},
        "wet_roads": {"source": "watering-schedule"},
        "placement": {"source": "pit-design", "max_base_offset_m": 0.05},
        "rock_textures": {
            "source": "lithology-cc0",
            "lithologies": {"quartz_monzonite": ["tex-1", "tex-2"], "limestone": ["tex-3"]},
        },
    },
    "unstructured": {
        "textures": "whole-pool-uniform",
        "light_intensity_factor": {"distribution": "log-uniform", "min": 0.1, "max": 10},
        "colour_temperature_k": {"distribution": "uniform", "min": 2000, "max": 12000},
        "sun_direction": "upper-hemisphere-uniform",
        "object_positions": "visible-ground-uniform",
        "distractors": {"distribution": "uniform-integer", "min": 0, "max": 20},
    },
    "texture_pool": POOL,
}


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _line(p0: tuple[float, float, float], p1: tuple[float, float, float], step: float = 10.0) -> list[list[float]]:
    n = round(math.dist(p0[:2], p1[:2]) / step)
    return [[p0[i] + (p1[i] - p0[i]) * k / n for i in range(3)] for k in range(n + 1)]


def make_scene(tmp: Path, *, status: str = "complete", edges: list[list[list[float]]] | None = None) -> Path:
    """A scene folder of the `st45_validate/scene` layout: three straight edges, 30 m wide, falling 0.075 m per m."""
    scene = tmp / "scene"
    (scene / "design").mkdir(parents=True)
    (scene / "terrain").mkdir(parents=True)
    edges = edges or [
        _line((0, 0, 0), (400, 0, -30)),
        _line((400, 0, -30), (400, 300, -52.5)),
        _line((400, 300, -52.5), (0, 300, -82.5)),
    ]
    features = []
    for i, coords in enumerate(edges):
        features.append(
            {
                "type": "Feature",
                "id": f"e{i}",
                "properties": {"kind": "edge", "class": "ramp", "from": f"n{i}", "to": f"n{i + 1}"},
                "geometry": {"type": "LineString", "coordinates": coords},
            }
        )
    features.append(
        {
            "type": "Feature",
            "id": "n0",
            "properties": {"kind": "node"},
            "geometry": {"type": "Point", "coordinates": [0, 0, 0]},
        }
    )
    files = {
        "design/road-network.geojson": json.dumps({"type": "FeatureCollection", "features": features}).encode(),
        "design/pit-design-report.json": json.dumps({"ramp": {"min_width_m": 30.0}}).encode(),
        "terrain/tiles.json": json.dumps({"kind": "terrain-tiles"}).encode(),
    }
    for rel, data in files.items():
        (scene / rel).write_bytes(data)
    ref = {rel: {"path": rel, "sha256": _sha(data)} for rel, data in files.items()}
    manifest = {
        "case": "A1",
        "manifest_id": "t-scene-0001",
        "validation": {"status": status},
        "design": {"report": ref["design/pit-design-report.json"], "road_network": ref["design/road-network.geojson"]},
        "terrain": {"tiles": ref["terrain/tiles.json"]},
        "site": {"origin": {"epsg": 26912, "easting_m": 402500.0, "northing_m": 4486500.0, "z0_m": 1800.0}},
    }
    (scene / "scene.manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return scene


@pytest.fixture(scope="module")
def scene_inputs(tmp_path_factory: pytest.TempPathFactory):
    return load_scene_inputs(make_scene(tmp_path_factory.mktemp("scene")))


# ---------------------------------------------------------------------------------------------------------------
# scene inputs
# ---------------------------------------------------------------------------------------------------------------
def test_the_recipe_of_the_tests_is_a_valid_config() -> None:
    validate_config(RECIPE)


@pytest.mark.req("FR-009-04")
def test_the_site_centroid_is_the_utm_origin_in_wgs84(scene_inputs) -> None:
    # Hand calculation. Latitude: the meridian arc to 40 N is 4,429.3 km and a degree there is 111.3 km, so
    # 4,486,500 m / 0.9996 (the UTM scale factor) gives 40 + (4,488.3 - 4,429.3) / 111.3 = 40.53 deg. Longitude: zone
    # 12N has its central meridian at 111 W; 97.5 km west of it (easting 402.5 km - 500 km) at 40.5 N is
    # 97.5 / (111.32 x cos 40.5 deg x 0.9996) = 1.15 deg, so 112.15 W.
    assert scene_inputs.latitude_deg == pytest.approx(40.53, abs=0.02)
    assert scene_inputs.longitude_deg == pytest.approx(-112.15, abs=0.02)
    assert scene_inputs.z0_m == 1800.0


@pytest.mark.req("FR-009-07")
def test_the_design_height_follows_the_road_slope(scene_inputs) -> None:
    assert scene_inputs.height_at(200.0, 0.0) == pytest.approx(-15.0, abs=1e-9)
    assert scene_inputs.height_at(200.0, 7.0) == pytest.approx(-15.0, abs=1e-9)  # a flat cross-section
    assert scene_inputs.height_at(400.0, 150.0) == pytest.approx(-41.25, abs=1e-9)
    x, y, z, heading = scene_inputs.position_on_edge("edge-n0-n1", 0.5)
    assert (x, y) == pytest.approx((200.0, 0.0)) and z == pytest.approx(-15.0) and heading == pytest.approx(0.0)


@pytest.mark.req("FR-009-02")
def test_an_incomplete_or_tampered_scene_is_refused(tmp_path: Path) -> None:
    with pytest.raises(SceneInputsError, match="status"):
        load_scene_inputs(make_scene(tmp_path / "a", status="incomplete"))
    scene = make_scene(tmp_path / "b")
    (scene / "design" / "road-network.geojson").write_bytes(b"{}")
    with pytest.raises(SceneInputsError, match="SHA-256"):
        load_scene_inputs(scene)
    with pytest.raises(SceneInputsError, match="absent"):
        load_scene_inputs(tmp_path / "nothing")


# ---------------------------------------------------------------------------------------------------------------
# scenario geometry, structured and unstructured rows
# ---------------------------------------------------------------------------------------------------------------
def test_the_scenario_seed_and_geometry_are_deterministic(scene_inputs) -> None:
    assert table.scenario_seed(1, 5) == table.scenario_seed(1, 5) != table.scenario_seed(1, 6)
    assert 0 <= table.scenario_seed(1, 5) < 2**63
    a = table.scenario_geometry(scene_inputs, RECIPE["seed"], 123)
    b = table.scenario_geometry(scene_inputs, RECIPE["seed"], 123)
    assert a["camera"] == b["camera"] and a["layout_id"] == b["layout_id"]
    assert a["layout_id"] in {e.edge_id for e in scene_inputs.edges}
    assert np.linalg.norm(a["camera"]["forward"]) == pytest.approx(1.0)
    assert a["camera"]["fx_px"] == pytest.approx(0.5 * 1280 / math.tan(math.radians(a["hfov_deg"]) / 2))
    union = scene_inputs.road_union()
    assert all(union.buffer(1e-6).contains(area) for area in a["areas"])


@pytest.mark.req("FR-009-04")
@pytest.mark.req("FR-009-05")
@pytest.mark.req("FR-009-06")
@pytest.mark.req("FR-009-07")
def test_a_structured_row_satisfies_the_sampling_rules(scene_inputs) -> None:
    for i in range(12):
        seed = table.scenario_seed(RECIPE["seed"], i)
        geometry = table.scenario_geometry(scene_inputs, RECIPE["seed"], seed)
        row = table.structured_row(scene_inputs, RECIPE, seed, geometry)
        row |= {"arm": "structured", "record_id": f"pit-s-{i:05d}"}
        table.check_dr(row)  # DC-009-01 dr_structured
        dr = row["dr"]
        assert dr["sun_elevation_deg"] >= 5.0
        assert math.isfinite(dr["dust_extinction_per_km"]) and 0.0 <= dr["dust_extinction_per_km"] <= 1000.0
        assert {w["segment_id"] for w in dr["wet_segments"]} == {e.edge_id for e in scene_inputs.edges}
        assert set(dr["rock_texture_ids"]) <= {"tex-1", "tex-2", "tex-3"}
        assert len(dr["placements"]) == len(row["objects"]) >= 1
        union = scene_inputs.road_union()
        for p in dr["placements"]:
            assert shapely.contains_xy(union, p["x_m"], p["y_m"])  # FR-009-07: on a road polygon
            assert abs(p["z_m"] - scene_inputs.height_at(p["x_m"], p["y_m"])) <= 0.05 + 1e-9
        when = dt.datetime.fromisoformat(dr["sun_utc"].replace("Z", "+00:00"))
        wet = {w["segment_id"]: w for w in dr["wet_segments"]}
        for w in wet.values():  # FR-009-06: wet iff the last pass was at most the drying time ago
            assert w["wet"] == ("minutes_since_watering" in w and w["minutes_since_watering"] <= 60.0)
        assert when.year == 2025


@pytest.mark.req("FR-009-08")
def test_an_unstructured_row_draws_from_the_ranges_and_the_whole_pool(scene_inputs) -> None:
    seen_textures: set[str] = set()
    for i in range(20):
        seed = table.scenario_seed(RECIPE["seed"], i)
        geometry = table.scenario_geometry(scene_inputs, RECIPE["seed"], seed)
        row = table.unstructured_row(scene_inputs, RECIPE, seed, 0, geometry)
        row |= {"arm": "unstructured", "record_id": f"pit-u-{i:05d}"}
        table.check_dr(row)
        dr = row["dr"]
        assert 0.1 <= dr["light_intensity_factor"] <= 10.0 and 2000.0 <= dr["colour_temperature_k"] <= 12000.0
        assert len(row["distractors"]) == dr["distractor_count"] <= 20
        seen_textures |= set(dr["texture_ids"])
        assert row["condition"] == "day" and row["dust_scenario"] is None
    assert seen_textures <= {p["id"] for p in POOL} and len(seen_textures) >= 3


def test_a_repeated_seed_of_the_unstructured_arm_draws_again(scene_inputs) -> None:
    seed = table.scenario_seed(RECIPE["seed"], 0)
    geometry = table.scenario_geometry(scene_inputs, RECIPE["seed"], seed)
    first = table.unstructured_row(scene_inputs, RECIPE, seed, 0, geometry)
    again = table.unstructured_row(scene_inputs, RECIPE, seed, 0, geometry)
    second = table.unstructured_row(scene_inputs, RECIPE, seed, 1, geometry)
    assert first["dr"] == again["dr"] != second["dr"]


# ---------------------------------------------------------------------------------------------------------------
# dust field
# ---------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-009-05")
def test_a_very_long_road_gives_the_infinite_line_plume_downwind_and_nothing_upwind(tmp_path: Path) -> None:
    long_road = [[[x, 0.0, 0.0] for x in np.arange(-20000.0, 20001.0, 10.0).tolist()]]
    scene = load_scene_inputs(make_scene(tmp_path, edges=long_road))
    scenario = dust_field.DustScenario(0.05, 200000.0, 0.01, 4.0, 0.0, "D")  # wind from the north: blows toward -y
    field = dust_field.RoadPlumeField(scene, scenario, ground=lambda _x, _y: 0.0)
    _, sigma_z = environment.pasquill_sigmas(100.0, "D")
    expected = float(environment.line_source_plume(field._q_line, 4.0, 2.0, dust_field.SOURCE_HEIGHT_M, sigma_z))
    got = field.concentration_kg_m3(0.0, -100.0, 2.0)  # 100 m downwind of the road
    assert got == pytest.approx(expected, rel=0.02)
    assert field.concentration_kg_m3(0.0, 100.0, 2.0) == 0.0  # upwind
    assert field.concentration_kg_m3(0.0, -2.0, 2.0) == 0.0  # inside the minimum downwind distance of every piece


# ---------------------------------------------------------------------------------------------------------------
# the whole table, the driver and the finalize step
# ---------------------------------------------------------------------------------------------------------------
def _splits(seeds: list[int]) -> dict[str, list[int]]:
    return {"train": seeds[:20], "validation": seeds[20:25], "test": seeds[25:]}


@pytest.mark.req("FR-009-03")
def test_the_table_has_both_pit_arms_and_the_unstructured_arm_reuses_training_seeds(scene_inputs) -> None:
    seeds = [table.scenario_seed(RECIPE["seed"], i) for i in range(30)]
    splits = _splits(seeds)
    rows = list(table.build_rows(scene_inputs, RECIPE, splits, {"structured": 30, "unstructured": 40}))
    structured = [r for r in rows if r["arm"] == "structured"]
    unstructured = [r for r in rows if r["arm"] == "unstructured"]
    assert len(structured) == 30 and len(unstructured) == 40
    assert {r["split"] for r in unstructured} == {"train"}
    assert {r["scenario_seed"] for r in unstructured} <= set(splits["train"])
    by_seed = {r["scenario_seed"]: r for r in structured}
    for u in unstructured:
        assert (
            u["camera"] == by_seed[u["scenario_seed"]]["camera"]
            and u["layout_id"] == by_seed[u["scenario_seed"]]["layout_id"]
        )
    assert len({r["record_id"] for r in rows}) == 70
    assert [by_seed[s]["split"] for s in splits["test"]] == ["test"] * 5


@pytest.mark.req("FR-009-44")
def test_camera_quaternion_looks_along_the_forward_vector() -> None:
    for forward in ([1.0, 0.0, 0.0], [0.0, 1.0, -0.1], [-0.7, -0.7, -0.14]):
        x, y, z, w = finalize.camera_quaternion_xyzw(forward, [0.0, 0.0, 1.0])
        assert math.sqrt(x * x + y * y + z * z + w * w) == pytest.approx(1.0)
        # rotate the camera's -Z axis (its viewing direction) by q: v + 2w(q x v) + 2 q x (q x v)
        q, v = np.array([x, y, z]), np.array([0.0, 0.0, -1.0])
        view = v + 2 * w * np.cross(q, v) + 2 * np.cross(q, np.cross(q, v))
        assert view == pytest.approx(np.array(forward) / np.linalg.norm(forward), abs=1e-12)


@pytest.mark.req("FR-009-02")
@pytest.mark.req("FR-009-44")
def test_the_whole_chain_writes_a_valid_index_frame_states_and_card(tmp_path: Path) -> None:
    scene_dir = make_scene(tmp_path)
    seeds = [table.scenario_seed(RECIPE["seed"], i) for i in range(30)]
    table_dir = tmp_path / "root" / "param_table"
    plan = {
        "recipe_seed": RECIPE["seed"],
        "counts": {"structured": 30, "unstructured": 40},
        "skipped": [],
        "scenarios": [],
    }
    scene = load_scene_inputs(scene_dir)
    table_dir.mkdir(parents=True)
    files = {}
    for arm in ("structured", "unstructured"):
        path = table_dir / f"pit-{arm}.jsonl"
        rows = [r for r in table.build_rows(scene, RECIPE, _splits(seeds), plan["counts"]) if r["arm"] == arm]
        path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")
        files[arm] = {"path": path.name, "sha256": _sha(path.read_bytes()), "rows": len(rows)}
    (table_dir / "table.manifest.json").write_text(
        json.dumps(
            {
                "scene_manifest_id": scene.manifest_id,
                "recipe_sha256": "0" * 64,
                "recipe_seed": RECIPE["seed"],
                "files": files,
                "skipped_arms": [{"family": "crusher", "arm": "structured", "reason": "handoff"}],
                "assumptions": {},
            }
        ),
        encoding="utf-8",
    )
    root = tmp_path / "root"
    session = driver.no_gpu_session
    result = driver.run(rows=driver.read_rows(table_dir), root=root, renderer_factory=CpuRenderer, session=session)
    assert result["remaining"] == 0
    counts = finalize.finalize(root, table_dir, scene_dir)
    assert counts["indexed"] == 70, counts
    assert counts["frame_state_excluded"] == [] and counts["record_invalid"] == []
    lines = [json.loads(line) for line in (root / "index.jsonl").read_text(encoding="utf-8").splitlines()]
    assert [r["record_id"] for r in lines[:2]] == ["pit-s-00000", "pit-s-00001"]
    state = json.loads((root / lines[0]["frame_state"]["path"]).read_text(encoding="utf-8"))
    assert (
        state["case"] == "B2"
        and state["metersPerUnit"] == 1.0
        and state["terrain"]["path"] == "scene_ref/terrain-tiles.json"
    )
    assert len(state["objects"]) == len(lines[0]["dr"]["placements"])
    card = json.loads((root / "sdg-card.json").read_text(encoding="utf-8"))
    assert card["people_source"] == "mannequins" and card["indexed_frames"] == 70
