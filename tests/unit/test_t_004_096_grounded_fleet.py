# ruff: noqa: E501, PT018
"""T-004-096: the fleet and the people stand on the terrain at haul-road centreline stations.

Requirements: FR-004-47.

Oracle: the analytic terrain of `dem_kit` (`plane_z`, piecewise linear, exact under bilinear sampling on its 1 m grid);
the road geometry (a straight `ramp` edge at a known bearing) written in the test; spacing and chainage by hand.

Expected API (package `pitstudio_studio.scene.compose`, studio environment):
- `compose.compose_scene` as in T-004-040: with `terrain/grid.zarr/elevation` and `design/road-network.geojson` among the
  record files, every prim under `/World/Fleet` and `/World/People` of the composed `layers/fleet.usda` has a translate
  whose z equals the terrain height at its x, y and a `pitstudio:placement` string; trucks lie on a `ramp` edge of the
  road network with a heading (rotateZ, degrees) equal to the edge bearing; trucks are at least 30 m apart; the people
  stand within 25 m of the first truck. Without a grid or a road network the fleet layer is left as authored; more
  prims than stations is `SceneStageError("compose-invalid")`.
- `compose.ground.flattest_stations(road, grid, count)` -> list of `Station(edge, chainage_m, x, y, heading_deg)`.
- `compose.grid.Grid(elevation, x_min, y_max, cell).height(x, y)`: bilinear, row 0 is the north row.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import dem_kit as dk  # noqa: E402
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import compose  # noqa: E402
from pitstudio_studio.scene.common import SceneStageError  # noqa: E402
from pitstudio_studio.scene.compose import ground  # noqa: E402
from pitstudio_studio.scene.compose.grid import Grid  # noqa: E402


def _spec() -> dict:
    spec = kit.scene_spec()
    spec["variants"] = {"pushback": ["pb0"], "scenario": ["baseline"], "time_of_day": ["noon"], "weather": ["clear"], "lod": ["lod0", "lod1", "lod2"]}
    return spec


def _grid() -> Grid:
    return Grid(dk.elevation(), dk.X_MIN, dk.Y_MAX, dk.CELL)


def _fleet(folder: Path) -> dict[str, dict]:
    from pxr import Usd, UsdGeom

    stage = Usd.Stage.Open(str(folder / "layers" / "fleet.usda"))
    out = {}
    for group in ("Fleet", "People"):
        for prim in stage.GetPrimAtPath(f"/World/{group}").GetChildren():
            ops = {op.GetOpName(): op for op in UsdGeom.Xformable(prim).GetOrderedXformOps()}
            attr = prim.GetAttribute("pitstudio:placement")
            out[str(prim.GetPath())] = {
                "t": tuple(ops["xformOp:translate"].Get()),
                "yaw": ops["xformOp:rotateZ"].Get() if "xformOp:rotateZ" in ops else None,
                "placement": attr.Get() if attr else None,
            }
    return out


@pytest.mark.req("FR-004-47")
def test_grid_height_is_bilinear_and_matches_the_analytic_surface() -> None:
    grid = _grid()
    for x, y in [(-150.0, 20.0), (12.34, -77.7), (59.5, 3.3), (60.0, 0.0), (130.25, 99.75)]:
        assert grid.height(x, y) == pytest.approx(dk.plane_z(x, y), abs=2e-3)  # float32 grid values
    assert grid.height(-1000.0, 0.0) == pytest.approx(grid.height(-200.0, 0.0))  # clamped at the border, never extrapolated


@pytest.mark.req("FR-004-47")
def test_stations_are_the_flattest_on_ramp_edges_spaced_and_headed_along_the_road() -> None:
    stations = ground.flattest_stations(dk.road_network(), _grid(), 3)
    assert len(stations) == 3
    for s in stations:
        assert s.edge == "n1-n2" and s.heading_deg == pytest.approx(0.0, abs=1e-6)
        assert s.y == pytest.approx(-10.0, abs=1e-6) and s.x >= dk.PLATEAU_X + 8.0 - 1e-6  # whole 16 m footprint on the plateau
    xs = sorted(s.x for s in stations)
    assert all(b - a >= 30.0 - 1e-6 for a, b in zip(xs, xs[1:], strict=False))
    assert stations == ground.flattest_stations(dk.road_network(), _grid(), 3)  # deterministic


@pytest.mark.req("FR-004-47")
def test_station_heading_follows_a_diagonal_road() -> None:
    stations = ground.flattest_stations(dk.road_network(edge_m=200.0, angle_deg=30.0), _grid(), 1)
    assert stations[0].heading_deg == pytest.approx(30.0, abs=1e-6)


@pytest.mark.req("FR-004-47")
def test_composed_fleet_stands_on_the_terrain_on_the_road_with_its_heading(tmp_path: Path) -> None:
    up = dk.upstream(tmp_path / "up", trucks=3)
    compose.compose_scene(_spec(), up, tmp_path / "scene")
    placed = _fleet(tmp_path / "scene")
    trucks = {k: v for k, v in placed.items() if "/Fleet/" in k}
    assert len(trucks) == 3
    for path, item in placed.items():
        x, y, z = item["t"]
        assert z == pytest.approx(dk.plane_z(x, y), abs=2e-3), path
        assert item["placement"] and "n1-n2" in item["placement"], path
        assert (x, y) != (0.0, 0.0)
    for item in trucks.values():
        assert item["t"][1] == pytest.approx(-10.0, abs=1e-6) and item["yaw"] == pytest.approx(0.0, abs=1e-6)
        assert "chainage" in item["placement"]
    xs = sorted(v["t"][0] for v in trucks.values())
    assert all(b - a >= 30.0 - 1e-6 for a, b in zip(xs, xs[1:], strict=False))
    first = placed["/World/Fleet/Truck_00"]["t"]
    person = placed["/World/People/Person_00"]["t"]
    assert 0.0 < math.hypot(person[0] - first[0], person[1] - first[1]) <= 25.0


@pytest.mark.req("FR-004-47")
@pytest.mark.parametrize("kw", [{"road": False}, {"grid": False}])
def test_without_a_grid_or_a_road_network_the_fleet_is_left_as_authored(tmp_path: Path, kw: dict) -> None:
    up = dk.upstream(tmp_path / "up", **kw)
    compose.compose_scene(_spec(), up, tmp_path / "scene")
    assert (tmp_path / "scene" / "layers" / "fleet.usda").read_bytes() == Path(up["layers"]["fleet"]).read_bytes()


@pytest.mark.req("FR-004-47")
def test_more_prims_than_stations_is_a_compose_error_that_writes_nothing_new(tmp_path: Path) -> None:
    up = dk.upstream(tmp_path / "up", trucks=3, edge_m=40.0)  # a 40 m edge holds one 30 m-spaced truck, no plateau
    with pytest.raises(SceneStageError) as caught:
        compose.compose_scene(_spec(), up, tmp_path / "scene")
    assert caught.value.error_class == "compose-invalid"
