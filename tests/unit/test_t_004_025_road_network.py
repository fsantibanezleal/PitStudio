# ruff: noqa: E501, PT018, RUF007
"""T-004-025: haul-road network GeoJSON with edge lengths and grades, every node connected to the pit exit.

Requirements: FR-004-21.

Oracle: a hand-built two-segment fixture with known edge lengths and grades (3-D length = sqrt(run^2 + rise^2), signed
mean grade = rise / run x 100, hand calculated below), the draft DC-004-06 schema, and a breadth-first search written
here (no graph library in the studio environment) for the connectivity claim.

Expected API (package `pitstudio_studio.scene.design`, studio environment):
- `design.roads.build_road_network(ramp_centreline, bench_roads, *, origin) -> dict`: the DC-004-06 GeoJSON
  FeatureCollection (site frame, metres). `ramp_centreline` is a float [n, 3] polyline from the pit exit (rim) down; each
  entry of `bench_roads` is a float [m, 3] polyline whose first vertex coincides with a vertex of the ramp (or of an
  earlier bench road). A vertex where a road branches becomes a junction node and splits the edge there; the first
  ramp vertex is the single `exit` node (`exit_node` names it); other degree-1 nodes have role `end`. Every edge is a
  LineString whose end vertices are the coordinates of its `from` and `to` nodes, with `class` `ramp` or `bench-road`,
  `length_m` (3-D polyline length), `grade_mean_pct` (signed: rise from `from` to `to` over the horizontal run x 100)
  and `grade_max_pct` (largest absolute grade between consecutive vertices).
- `DesignResult.road_network` (test_t_004_023) is that network for the generated ramp and bench roads.
"""

from __future__ import annotations

import math
import sys
from collections import deque
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests" / "_scene_kit"))
import scene_kit as kit  # noqa: E402
from pitstudio_studio.scene import design  # noqa: E402

ORIGIN = {"epsg": 26912, "easting_m": kit.E0, "northing_m": kit.N0, "z0_m": kit.Z0}


def _line(points: list[tuple[float, float, float]], step: float = 1.0) -> np.ndarray:
    """Densify a polyline to vertices at most `step` apart horizontally (grade is constant on each input segment)."""
    out = [points[0]]
    for a, b in zip(points, points[1:], strict=False):
        n = max(1, math.ceil(math.hypot(b[0] - a[0], b[1] - a[1]) / step))
        out += [tuple(np.add(a, (np.subtract(b, a) * i / n))) for i in range(1, n + 1)]
    return np.array(out, dtype=np.float64)


def _parts(net: dict) -> tuple[dict, list[dict]]:
    nodes = {f["id"]: f for f in net["features"] if f["properties"]["kind"] == "node"}
    edges = [f for f in net["features"] if f["properties"]["kind"] == "edge"]
    return nodes, edges


def _reachable(nodes: dict, edges: list[dict], start: str) -> set[str]:
    adj: dict[str, set[str]] = {n: set() for n in nodes}
    for e in edges:
        a, b = e["properties"]["from"], e["properties"]["to"]
        adj[a].add(b), adj[b].add(a)
    seen, queue = {start}, deque([start])
    while queue:
        for nxt in adj[queue.popleft()] - seen:
            seen.add(nxt)
            queue.append(nxt)
    return seen


def _check_structure(net: dict) -> tuple[dict, list[dict]]:
    assert kit.schema_errors("road-network.schema.json", net) == []
    nodes, edges = _parts(net)
    assert net["exit_node"] in nodes and nodes[net["exit_node"]]["properties"]["role"] == "exit"
    assert [n for n in nodes.values() if n["properties"]["role"] == "exit"] == [nodes[net["exit_node"]]]
    assert _reachable(nodes, edges, net["exit_node"]) == set(nodes)  # every node is connected to the pit exit
    for e in edges:
        p, coords = e["properties"], np.array(e["geometry"]["coordinates"], dtype=np.float64)
        assert coords[0].tolist() == nodes[p["from"]]["geometry"]["coordinates"]
        assert coords[-1].tolist() == nodes[p["to"]]["geometry"]["coordinates"]
        assert p["length_m"] == pytest.approx(kit.polyline_length_3d(coords), rel=1e-9)
        run = float(np.hypot(*(coords[-1, :2] - coords[0, :2])))
        assert p["grade_mean_pct"] == pytest.approx(100.0 * (coords[-1, 2] - coords[0, 2]) / run, rel=1e-9, abs=1e-9)
        assert p["grade_max_pct"] == pytest.approx(float(kit.segment_grades_pct(coords).max()), rel=1e-9, abs=1e-9)
    return nodes, edges


@pytest.mark.req("FR-004-21")
def test_ramp_and_one_bench_road_by_hand() -> None:
    """Ramp (0,0,0) -> (100,0,-8): length sqrt(100^2 + 8^2) = 100.3195 m, grade -8 %; bench road 50 m level."""
    net = design.roads.build_road_network(
        _line([(0, 0, 0), (100, 0, -8)]), [_line([(100, 0, -8), (100, 50, -8)])], origin=ORIGIN
    )
    nodes, edges = _check_structure(net)
    assert len(nodes) == 3 and len(edges) == 2
    ramp = next(e for e in edges if e["properties"]["class"] == "ramp")["properties"]
    road = next(e for e in edges if e["properties"]["class"] == "bench-road")["properties"]
    assert ramp["length_m"] == pytest.approx(math.sqrt(100.0**2 + 8.0**2), abs=1e-9)
    assert (ramp["grade_mean_pct"], ramp["grade_max_pct"]) == pytest.approx((-8.0, 8.0), abs=1e-9)
    assert (road["length_m"], road["grade_mean_pct"], road["grade_max_pct"]) == pytest.approx(
        (50.0, 0.0, 0.0), abs=1e-9
    )
    assert nodes[net["exit_node"]]["geometry"]["coordinates"] == [0.0, 0.0, 0.0]
    far_end = next(n for n in nodes.values() if n["geometry"]["coordinates"] == [100.0, 50.0, -8.0])
    assert far_end["properties"]["role"] == "end"  # a degree-1 node that is not the exit
    assert net["frame"] == "site-enu" and net["site_origin"] == ORIGIN and net["provenance"] == "design-code"


@pytest.mark.req("FR-004-21")
def test_a_bench_road_in_mid_ramp_splits_the_ramp_at_a_junction() -> None:
    """Junction at x = 40: ramp edges sqrt(40^2 + 3.2^2) = 40.1277 m and sqrt(60^2 + 4.8^2) = 60.1917 m, both -8 %."""
    net = design.roads.build_road_network(
        _line([(0, 0, 0), (100, 0, -8)]), [_line([(40, 0, -3.2), (40, 30, -3.2)])], origin=ORIGIN
    )
    nodes, edges = _check_structure(net)
    ramp = sorted((e["properties"] for e in edges if e["properties"]["class"] == "ramp"), key=lambda p: p["length_m"])
    assert [round(p["length_m"], 4) for p in ramp] == [40.1277, 60.1917]
    assert all(p["grade_mean_pct"] == pytest.approx(-8.0, abs=1e-9) for p in ramp)
    roles = sorted(n["properties"]["role"] for n in nodes.values())
    assert roles == ["end", "end", "exit", "junction"]
    assert sum(p["length_m"] for p in ramp) == pytest.approx(math.sqrt(100.0**2 + 8.0**2), abs=1e-9)


@pytest.mark.req("FR-004-21")
def test_uneven_grade_edge_reports_the_steepest_sample() -> None:
    """(0,0,0) -> (50,0,-2) -> (100,0,-8): 4 % then 12 %; mean -8 %, max 12 %; length 50.0400 + 50.3587 m."""
    net = design.roads.build_road_network(_line([(0, 0, 0), (50, 0, -2), (100, 0, -8)]), [], origin=ORIGIN)
    _, edges = _check_structure(net)
    (edge,) = edges
    p = edge["properties"]
    assert p["class"] == "ramp"
    assert (p["grade_mean_pct"], p["grade_max_pct"]) == pytest.approx((-8.0, 12.0), abs=1e-9)
    assert p["length_m"] == pytest.approx(math.hypot(50, 2) + math.hypot(50, 6), abs=1e-9)


@pytest.mark.req("FR-004-21")
def test_the_generated_design_has_a_connected_network_covering_the_whole_ramp() -> None:
    grid = kit.flat_grid(130.0, 1.0, 0.0)
    spec = kit.design_spec(h=12.0, alpha=70.0, b=10.0, g=8.0, w=20.0, floor_z=-36.0)
    res = design.build_design(grid, spec, outline_xy=kit.regular_polygon(180, 100.0))
    nodes, edges = _check_structure(res.road_network)
    assert res.road_network["site_origin"] == spec["site"]["origin"]
    ramp_edges = [e for e in edges if e["properties"]["class"] == "ramp"]
    assert ramp_edges
    assert sum(e["properties"]["length_m"] for e in ramp_edges) == pytest.approx(
        kit.polyline_length_3d(res.ramp.centreline), rel=1e-9
    )
    assert all(abs(e["properties"]["grade_max_pct"]) <= 8.1 + 1e-9 for e in ramp_edges)
    exit_xyz = nodes[res.road_network["exit_node"]]["geometry"]["coordinates"]
    assert exit_xyz[2] == pytest.approx(0.0, abs=1e-6)  # the exit is at the rim elevation
    assert any(e["properties"]["class"] == "bench-road" for e in edges)
