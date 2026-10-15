# ruff: noqa: E501, PT018
"""T-007-063: the network builder: Douglas-Peucker simplification, constant-grade splitting, grade refinement; every emitted segment satisfies |grade| <= g_max and starts and ends on the bilinear DEM sample within 0.01 m; hostile inputs rejected.

Requirements: FR-007-38, FR-007-45.

Spec: specs/007-haulage-dispatch/spec.md FR-007-38 (the network builder `pitstudio.haulage.network` turns A* routes between the scenario's declared loader, dump and junction cells into the bundle's road network; it simplifies each route with Douglas-Peucker (tolerance epsilon from the recipe), splits it
into segments of constant grade, and refines any segment whose |grade| exceeds g_max until none does; every emitted segment satisfies |grade| <= g_max and its endpoint elevations equal the bilinear DEM sample within 0.01 m), FR-007-45 (a duplicate or out-of-grid declared cell, a Douglas-Peucker
tolerance <= 0, a non-finite length, grade or mass is rejected with `InvalidRouteInput` naming the field and value), the bundle network contract `contracts/haul-scenario.schema.json` (`$defs/network`: nodes {id, kind, pos_m}, segments {id, a, b, polyline_m, length_m (3-D, metres), grade_pct (signed,
100 dz / horizontal length in the a -> b direction), width_class, one_way, speed_limit_kmh, rolling_resistance_pct, zone_id, single_lane_op}; as in `p007_kit.segment_entry`) and FR-007-35 (the routes are the router's).

Oracle: a textbook recursive Douglas-Peucker written in this file (farthest point from the chord, kept when its distance exceeds epsilon, first maximum wins ties); bilinear interpolation between cell centres written in this file; the schema validator; a breadth-first connectivity check; a hand-built two-ramp corridor (0 -> 5 % for 100 m, then flat for 100 m)
whose answer is worked out below; isometry and idempotence relations of Douglas-Peucker.

Geometry convention (stated here because the spec leaves it open): the centre of cell (row, col) is at x = col x cell_m, y = row x cell_m, z = dem.z[row, col]; elevation between centres is bilinear; a segment's grade is 100 (z_b - z_a) / horizontal distance; its length_m is the 3-D polyline length (rounded to 1 mm).

Hand case (two-ramp corridor, 1 x 21 cells of 10 m: z[c] = 0.5 c for c <= 10, then 5.0): the loader at col 0 and the dump at col 20; g_max = 0.1; epsilon = 0.05 m keeps the knee at col 10 (its distance from the chord is about 2.5 m), so the network has nodes at x = 0, 100, 200 and two segments: grade 5 %
(3-D length sqrt(100^2 + 5^2) = 100.125 m) and grade 0 % (100.0 m); epsilon = 10 m drops the knee (2.5 m < 10 m): one segment of grade 2.5 % and length sqrt(200^2 + 5^2) = 200.062 m.

Expected API (module `pitstudio.haulage.network`; errors in `pitstudio.haulage.errors`):
    douglas_peucker(points, epsilon) -> list[int]       points: float array [n, d] (d >= 1), epsilon > 0; the indices kept, strictly increasing, always including 0 and n - 1; a point is kept when its Euclidean distance to the chord of its span exceeds epsilon (the farthest, lowest index on ties, splits the span)
                                                        n < 2, non-finite coordinates or epsilon <= 0 / non-finite raise InvalidRouteInput (field "points" or "epsilon")
    build_network(dem, declared, *, epsilon_m, g_max, mass_kg, rr_pct, eta=1.0, g=None, speed_limit_kmh=30.0, width_class=2) -> dict
        dem: `routing.Dem`; declared: {"loaders": [{"id": int, "cell": (row, col)}], "dumps": [...], "junctions": [...]} (node kinds face, dump, junction), at least one loader and one dump; A* routes (T-007-060) between every loader and every dump, plus junction-to-loader and
        junction-to-dump; returns {"nodes": [...], "segments": [...], "zones": [], "junctions": []} valid against `$defs/network`: one node per distinct cell used (declared cells keep their ids and kinds; split points are `waypoint` nodes with fresh ids above every declared id), at most one segment per unordered node pair,
        segment ids 0, 1, 2, ..., rolling_resistance_pct = rr_pct, one_way False, zone_id None, single_lane_op False. Raises `DisconnectedNetwork` (attribute `pairs`: the (loader id, dump id) pairs with no feasible route) when a loader-dump pair has none.
"""

from __future__ import annotations

import itertools
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import HealthCheck, assume, given, settings
from hypothesis import strategies as st

from pitstudio.haulage.errors import DisconnectedNetwork, InvalidRouteInput
from pitstudio.haulage.network import build_network, douglas_peucker
from pitstudio.haulage.routing import Dem

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "support"))
import p007_kit as kit
import p007_routing as R

SETTINGS = settings(
    max_examples=30,
    deadline=None,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large, HealthCheck.filter_too_much],
)
NETWORK = kit.schema_validator("haul-scenario", "network")
MASS, RR, ETA = 400_000.0, 3.0, 0.9


# ---------------------------------------------------------------------------------------------------------------------
# independent oracles
# ---------------------------------------------------------------------------------------------------------------------
def chord_distance(p, a, b):
    ab, ap = b - a, p - a
    denom = float(ab @ ab)
    if denom == 0.0:
        return float(np.linalg.norm(ap))
    t = float(ap @ ab) / denom
    t = min(1.0, max(0.0, t))  # distance to the segment (the chord), as the textbook form
    return float(np.linalg.norm(p - (a + t * ab)))


def dp_oracle(points, eps):
    pts = np.asarray(points, dtype=float)
    keep = {0, len(pts) - 1}

    def rec(i, j):
        if j <= i + 1:
            return
        dists = [chord_distance(pts[k], pts[i], pts[j]) for k in range(i + 1, j)]
        m = max(dists)
        if m > eps:
            k = i + 1 + dists.index(m)  # the first maximum
            keep.add(k)
            rec(i, k)
            rec(k, j)

    rec(0, len(pts) - 1)
    return sorted(keep)


def bilinear(z, cell_m, x, y):
    c, r = x / cell_m, y / cell_m
    r0, c0 = min(math.floor(r), z.shape[0] - 2), min(math.floor(c), z.shape[1] - 2)
    r0, c0 = max(r0, 0), max(c0, 0)
    fr, fc = r - r0, c - c0
    r1, c1 = min(r0 + 1, z.shape[0] - 1), min(c0 + 1, z.shape[1] - 1)
    return float(
        z[r0, c0] * (1 - fr) * (1 - fc) + z[r1, c0] * fr * (1 - fc) + z[r0, c1] * (1 - fr) * fc + z[r1, c1] * fr * fc
    )


def connected(network, a, b):
    adj: dict[int, set[int]] = {}
    for s in network["segments"]:
        adj.setdefault(s["a"], set()).add(s["b"])
        adj.setdefault(s["b"], set()).add(s["a"])
    seen, stack = {a}, [a]
    while stack:
        for nb in adj.get(stack.pop(), ()):
            if nb not in seen:
                seen.add(nb)
                stack.append(nb)
    return b in seen


def check_network(net, dem, g_max, declared):
    assert not list(NETWORK.iter_errors(net)), [e.message for e in NETWORK.iter_errors(net)][:3]
    nodes = {n["id"]: n for n in net["nodes"]}
    assert len(nodes) == len(net["nodes"])  # unique ids
    assert len({tuple(n["pos_m"][:2]) for n in net["nodes"]}) == len(net["nodes"])  # one node per cell
    assert [s["id"] for s in net["segments"]] == list(range(len(net["segments"])))
    pairs = {frozenset((s["a"], s["b"])) for s in net["segments"]}
    assert len(pairs) == len(net["segments"])  # at most one segment per unordered node pair
    for n in net["nodes"]:
        x, y, zz = n["pos_m"]
        assert abs(zz - bilinear(dem.z, dem.cell_m, x, y)) <= 0.01, (
            n
        )  # endpoint elevation = the bilinear sample within 0.01 m
    for s in net["segments"]:
        a, b = nodes[s["a"]]["pos_m"], nodes[s["b"]]["pos_m"]
        horiz = math.hypot(b[0] - a[0], b[1] - a[1])
        assert horiz > 0
        assert abs(s["grade_pct"]) / 100.0 <= g_max + 1e-9, s  # every emitted segment respects the grade limit
        assert s["grade_pct"] == pytest.approx(100.0 * (b[2] - a[2]) / horiz, abs=2e-3)
        assert s["polyline_m"][0] == pytest.approx(a) and s["polyline_m"][-1] == pytest.approx(b)
        poly = np.asarray(s["polyline_m"], dtype=float)
        assert s["length_m"] == pytest.approx(float(np.linalg.norm(np.diff(poly, axis=0), axis=1).sum()), abs=2e-3)
        assert (
            s["rolling_resistance_pct"] == RR
            and s["one_way"] is False
            and s["zone_id"] is None
            and s["single_lane_op"] is False
        )
    kinds = {"loaders": "face", "dumps": "dump", "junctions": "junction"}
    for key, kind in kinds.items():
        for d in declared.get(key, []):
            n = nodes[d["id"]]
            assert n["kind"] == kind
            r, c = d["cell"]
            assert n["pos_m"] == pytest.approx([c * dem.cell_m, r * dem.cell_m, float(dem.z[r, c])], abs=1e-9)
    for ld in declared["loaders"]:
        for dp in declared["dumps"]:
            assert connected(net, ld["id"], dp["id"]), (ld, dp)


def build(dem, declared, eps, g_max, **kw):
    return build_network(dem, declared, epsilon_m=eps, g_max=g_max, mass_kg=MASS, rr_pct=RR, eta=ETA, g=R.G0, **kw)


# ---------------------------------------------------------------------------------------------------------------------
# Douglas-Peucker
# ---------------------------------------------------------------------------------------------------------------------
point_lists = st.lists(
    st.tuples(st.floats(-500, 500), st.floats(-500, 500), st.floats(-50, 50)), min_size=2, max_size=40
)


@pytest.mark.req("FR-007-38")
@SETTINGS
@given(pts=point_lists, eps=st.floats(0.01, 300.0))
def test_douglas_peucker_matches_the_textbook_recursion(pts, eps):
    a = np.array(pts)
    assert douglas_peucker(a, eps) == dp_oracle(a, eps)


@pytest.mark.req("FR-007-38")
@SETTINGS
@given(pts=point_lists, eps=st.floats(0.01, 300.0))
def test_every_dropped_point_lies_within_epsilon_of_the_simplified_polyline_and_the_ends_are_kept(pts, eps):
    a = np.array(pts)
    kept = douglas_peucker(a, eps)
    assert kept[0] == 0 and kept[-1] == len(a) - 1 and kept == sorted(set(kept))
    for i, j in itertools.pairwise(kept):
        for k in range(i + 1, j):
            assert chord_distance(a[k], a[i], a[j]) <= eps * (1 + 1e-12) + 1e-12


@pytest.mark.req("FR-007-38")
@SETTINGS
@given(pts=point_lists, eps=st.floats(0.01, 300.0))
def test_simplifying_twice_with_the_same_tolerance_changes_nothing(pts, eps):
    a = np.array(pts)
    kept = douglas_peucker(a, eps)
    assert douglas_peucker(a[kept], eps) == list(range(len(kept)))


@pytest.mark.req("FR-007-38")
@SETTINGS
@given(
    pts=point_lists,
    eps=st.floats(0.05, 300.0),
    angle=st.floats(0.0, 6.28),
    shift=st.tuples(st.floats(-1e3, 1e3), st.floats(-1e3, 1e3), st.floats(-1e3, 1e3)),
)
def test_a_rigid_motion_of_the_polyline_keeps_the_same_points(pts, eps, angle, shift):
    a = np.array(pts)
    c, s = math.cos(angle), math.sin(angle)
    rot = np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]])
    moved = a @ rot.T + np.array(shift)
    base = douglas_peucker(a, eps)
    got = douglas_peucker(moved, eps)
    # a decision flips only when a distance is within float noise of epsilon: accept the result unless some distance is that close
    margin = 1e-6 * (1 + float(np.abs(a).max()) + float(np.abs(np.array(shift)).max()))
    near = any(
        abs(chord_distance(a[k], a[i], a[j]) - eps) < margin
        for i, j in itertools.pairwise(base)
        for k in range(i + 1, j)
    )
    assume(not near)
    assert got == base


@pytest.mark.req("FR-007-38")
def test_a_collinear_run_collapses_to_its_end_points_and_a_large_epsilon_keeps_only_the_ends():
    line = np.array([[i * 3.0, i * 4.0, i * 0.5] for i in range(10)])
    assert douglas_peucker(line, 1e-6) == [0, 9]
    zig = np.array([[0, 0, 0], [10, 5, 0], [20, -5, 0], [30, 5, 0], [40, 0, 0]], dtype=float)
    assert douglas_peucker(zig, 1000.0) == [0, 4]
    assert douglas_peucker(zig, 1e-6) == [0, 1, 2, 3, 4]


@pytest.mark.req("FR-007-38")
def test_two_points_are_returned_as_they_are():
    assert douglas_peucker(np.array([[0.0, 0.0], [3.0, 4.0]]), 1.0) == [0, 1]
    assert douglas_peucker(np.array([[1.0, 1.0], [1.0, 1.0]]), 1.0) == [0, 1]  # a degenerate chord


# ---------------------------------------------------------------------------------------------------------------------
# the two-ramp hand case
# ---------------------------------------------------------------------------------------------------------------------
def corridor():
    z = np.zeros((1, 21))
    for c in range(21):
        z[0, c] = 0.5 * min(c, 10)
    return Dem(z, 10.0), {"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (0, 20)}]}


@pytest.mark.req("FR-007-38")
def test_the_two_ramp_corridor_is_split_at_the_knee_with_grades_5_and_0_percent():
    dem, declared = corridor()
    net = build(dem, declared, 0.05, 0.1)
    check_network(net, dem, 0.1, declared)
    xs = sorted(n["pos_m"][0] for n in net["nodes"])
    assert xs == [0.0, 100.0, 200.0]
    segs = sorted(net["segments"], key=lambda s: min(net_pos(net, s["a"])[0], net_pos(net, s["b"])[0]))
    first, second = segs
    assert first["grade_pct"] == pytest.approx(5.0, abs=1e-3) and first["length_m"] == pytest.approx(
        math.hypot(100.0, 5.0), abs=1e-3
    )
    assert second["grade_pct"] == pytest.approx(0.0, abs=1e-3) and second["length_m"] == pytest.approx(100.0, abs=1e-3)
    waypoint = next(n for n in net["nodes"] if n["pos_m"][0] == 100.0)
    assert waypoint["kind"] == "waypoint" and waypoint["id"] > 2 and waypoint["pos_m"][2] == pytest.approx(5.0)


def net_pos(net, nid):
    return next(n["pos_m"] for n in net["nodes"] if n["id"] == nid)


@pytest.mark.req("FR-007-38")
def test_a_tolerance_above_the_knee_deviation_merges_the_corridor_into_one_segment():
    dem, declared = corridor()
    net = build(dem, declared, 10.0, 0.1)
    check_network(net, dem, 0.1, declared)
    assert len(net["segments"]) == 1 and len(net["nodes"]) == 2
    s = net["segments"][0]
    assert s["grade_pct"] == pytest.approx(2.5, abs=1e-3) and s["length_m"] == pytest.approx(
        math.hypot(200.0, 5.0), abs=1e-3
    )


@pytest.mark.req("FR-007-38")
def test_a_chord_steeper_than_the_limit_is_refined_until_no_segment_exceeds_it():
    """A U-shaped detour around a no-data wall climbs 4 m: the simplified chord (horizontal distance 20 m) would be 20 %, the limit is 12 %."""
    z = np.zeros((6, 3))
    path_cells = [
        (0, 0),
        (1, 0),
        (2, 0),
        (3, 0),
        (4, 0),
        (5, 0),
        (5, 1),
        (5, 2),
        (4, 2),
        (3, 2),
        (2, 2),
        (1, 2),
        (0, 2),
    ]
    for i, cell in enumerate(path_cells):
        z[cell] = 0.3 * i  # 3 m per 100 m of path ... 0.3 m per 10 m cell: 3 % along the loop, 3.6 m in total
    nodata = np.zeros((6, 3), bool)
    nodata[0:5, 1] = True  # the wall between the two columns
    dem = Dem(z, 10.0, nodata)
    declared = {"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (0, 2)}]}
    chord_grade = 100.0 * (z[0, 2] - z[0, 0]) / 20.0
    assert chord_grade > 12.0  # the simplified chord alone would break the limit
    net = build(dem, declared, 1000.0, 0.12)
    check_network(net, dem, 0.12, declared)
    assert len(net["segments"]) > 1  # the chord was refined


# ---------------------------------------------------------------------------------------------------------------------
# random DEMs
# ---------------------------------------------------------------------------------------------------------------------
@pytest.mark.req("FR-007-38")
@SETTINGS
@given(
    seed=st.integers(0, 2**31 - 1),
    size=st.tuples(st.integers(6, 20), st.integers(6, 20)),
    eps=st.floats(0.05, 200.0),
    g_max=st.floats(0.1, 0.3),
    n_load=st.integers(1, 2),
    n_dump=st.integers(1, 2),
    junction=st.booleans(),
)
def test_every_emitted_segment_respects_the_grade_limit_and_every_node_sits_on_the_dem(
    seed, size, eps, g_max, n_load, n_dump, junction
):
    rows, cols = size
    rng = np.random.default_rng(seed)
    z = R.dyadic_dem(rng, rows, cols, relief=1.0)
    dem = Dem(z, 10.0)
    cells = [(int(rng.integers(0, rows)), int(rng.integers(0, cols))) for _ in range(n_load + n_dump + int(junction))]
    assume(len(set(cells)) == len(cells))
    declared = {
        "loaders": [{"id": i + 1, "cell": cells[i]} for i in range(n_load)],
        "dumps": [{"id": 10 + i, "cell": cells[n_load + i]} for i in range(n_dump)],
        "junctions": [{"id": 20, "cell": cells[-1]}] if junction else [],
    }
    reach = [R.reachable(z, 10.0, None, tuple(d["cell"]), g_max) for d in declared["loaders"]]
    assume(all(tuple(dp["cell"]) in r for r in reach for dp in declared["dumps"]))
    if junction:
        assume(all(tuple(cells[-1]) in r for r in reach))
    net = build(dem, declared, eps, g_max)
    check_network(net, dem, g_max, declared)
    ids = {n["id"] for n in net["nodes"]}
    for d in declared["loaders"] + declared["dumps"] + declared["junctions"]:
        assert d["id"] in ids
    waypoints = [n["id"] for n in net["nodes"] if n["kind"] == "waypoint"]
    assert all(
        w > max(d["id"] for d in declared["loaders"] + declared["dumps"] + declared["junctions"]) for w in waypoints
    )


@pytest.mark.req("FR-007-38")
def test_the_builder_is_deterministic_and_leaves_its_inputs_untouched():
    rng = np.random.default_rng(3)
    z = R.dyadic_dem(rng, 14, 14, relief=1.0)
    dem = Dem(z.copy(), 10.0)
    declared = {"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (13, 13)}]}
    before = z.copy()
    a = build(dem, declared, 5.0, 0.3)
    b = build(dem, declared, 5.0, 0.3)
    assert (
        a == b
        and np.array_equal(dem.z, before)
        and declared == {"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (13, 13)}]}
    )


@pytest.mark.req("FR-007-38")
def test_a_loader_dump_pair_without_a_feasible_route_is_a_disconnected_network():
    z = np.zeros((5, 5))
    z[:, 2] = 5.0  # a 5 m wall over 10 m cells: grade 0.5
    declared = {"loaders": [{"id": 1, "cell": (2, 0)}], "dumps": [{"id": 2, "cell": (2, 4)}]}
    with pytest.raises(DisconnectedNetwork) as ei:
        build(Dem(z, 10.0), declared, 1.0, 0.1)
    assert list(ei.value.pairs) == [(1, 2)]


# ---------------------------------------------------------------------------------------------------------------------
# FR-007-45: hostile inputs
# ---------------------------------------------------------------------------------------------------------------------
GOOD = {"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (3, 3)}]}


def flat_dem():
    return Dem(np.zeros((5, 5)), 10.0)


def rejected(field, value, declared=None, dem=None, eps=1.0, **kw):
    with pytest.raises(InvalidRouteInput) as ei:
        build_network(
            dem or flat_dem(),
            declared if declared is not None else GOOD,
            epsilon_m=eps,
            g_max=0.1,
            mass_kg=MASS,
            rr_pct=RR,
            eta=ETA,
            g=R.G0,
            **kw,
        )
    e = ei.value
    assert e.field == field and field in str(e) and repr(value)[:40] in str(e)


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("eps", [0.0, -1.0, -1e-12, float("nan"), float("inf"), float("-inf")])
def test_a_douglas_peucker_tolerance_that_is_not_positive_and_finite_is_rejected(eps):
    rejected("epsilon_m", eps, eps=eps)
    with pytest.raises(InvalidRouteInput) as ei:
        douglas_peucker(np.array([[0.0, 0.0], [1.0, 1.0], [2.0, 0.0]]), eps)
    assert ei.value.field == "epsilon"


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("eps", ["1", None, True, [1.0]])
def test_a_tolerance_of_the_wrong_type_is_rejected(eps):
    with pytest.raises((InvalidRouteInput, TypeError)):
        build(flat_dem(), GOOD, eps, 0.1)


@pytest.mark.req("FR-007-45")
def test_a_duplicate_declared_cell_is_rejected_naming_the_cell():
    dup = {"loaders": [{"id": 1, "cell": (1, 1)}], "dumps": [{"id": 2, "cell": (1, 1)}]}
    rejected("cell", (1, 1), declared=dup)
    dup2 = {"loaders": [{"id": 1, "cell": (0, 0)}, {"id": 3, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (3, 3)}]}
    rejected("cell", (0, 0), declared=dup2)


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("cell", [(-1, 0), (0, -1), (5, 0), (0, 5), (99, 99), (2**40, 0)])
def test_an_out_of_grid_declared_cell_is_rejected_naming_the_cell(cell):
    rejected("cell", cell, declared={"loaders": [{"id": 1, "cell": cell}], "dumps": [{"id": 2, "cell": (3, 3)}]})


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize("cell", [(0.5, 1), ("0", "0"), (None, None), (1,), (1, 2, 3), "00", None, (True, 0)])
def test_a_malformed_declared_cell_is_rejected(cell):
    with pytest.raises((InvalidRouteInput, TypeError)) as ei:
        build_network(
            flat_dem(),
            {"loaders": [{"id": 1, "cell": cell}], "dumps": [{"id": 2, "cell": (3, 3)}]},
            epsilon_m=1.0,
            g_max=0.1,
            mass_kg=MASS,
            rr_pct=RR,
            eta=ETA,
            g=R.G0,
        )
    if isinstance(ei.value, InvalidRouteInput):
        assert ei.value.field == "cell"


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize(
    ("declared", "field"),
    [
        ({"loaders": [], "dumps": [{"id": 2, "cell": (3, 3)}]}, "declared"),
        ({"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": []}, "declared"),
        ({}, "declared"),
        (None, "declared"),
        (
            {"loaders": [{"id": 1, "cell": (0, 0)}, {"id": 1, "cell": (0, 1)}], "dumps": [{"id": 2, "cell": (3, 3)}]},
            "id",
        ),
        ({"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": [{"id": 1, "cell": (3, 3)}]}, "id"),
        ({"loaders": [{"id": -1, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (3, 3)}]}, "id"),
        ({"loaders": [{"id": "1", "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (3, 3)}]}, "id"),
        ({"loaders": [{"id": 1, "cell": (0, 0)}], "dumps": [{"id": 2, "cell": (3, 3)}], "crushers": []}, "declared"),
    ],
)
def test_incomplete_or_inconsistent_declarations_are_rejected_naming_the_field(declared, field):
    with pytest.raises(InvalidRouteInput) as ei:
        build_network(flat_dem(), declared, epsilon_m=1.0, g_max=0.1, mass_kg=MASS, rr_pct=RR, eta=ETA, g=R.G0)
    assert ei.value.field == field


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize(
    ("field", "bad"),
    [
        ("mass_kg", float("nan")),
        ("mass_kg", float("inf")),
        ("mass_kg", 0.0),
        ("mass_kg", -5.0),
        ("rr_pct", float("nan")),
        ("rr_pct", -1.0),
        ("g_max", float("nan")),
        ("g_max", 0.0),
        ("g_max", 1.5),
    ],
)
def test_non_finite_or_non_physical_truck_and_limit_parameters_are_rejected(field, bad):
    kw = {"epsilon_m": 1.0, "g_max": 0.1, "mass_kg": MASS, "rr_pct": RR, "eta": ETA, "g": R.G0, field: bad}
    with pytest.raises(InvalidRouteInput) as ei:
        build_network(flat_dem(), GOOD, **kw)
    assert ei.value.field == field


@pytest.mark.req("FR-007-45")
def test_a_declared_cell_on_no_data_is_rejected_and_nothing_partial_is_returned():
    nodata = np.zeros((5, 5), bool)
    nodata[3, 3] = True
    with pytest.raises(InvalidRouteInput) as ei:
        build_network(
            Dem(np.zeros((5, 5)), 10.0, nodata),
            GOOD,
            epsilon_m=1.0,
            g_max=0.1,
            mass_kg=MASS,
            rr_pct=RR,
            eta=ETA,
            g=R.G0,
        )
    assert ei.value.field == "cell"


@pytest.mark.req("FR-007-45")
@pytest.mark.parametrize(
    "pts",
    [
        np.zeros((1, 2)),
        np.zeros((0, 2)),
        np.array([[0.0, float("nan")], [1.0, 1.0]]),
        np.array([[0.0, 0.0], [float("inf"), 1.0]]),
        np.zeros(5),
        np.zeros((3, 0)),
    ],
)
def test_douglas_peucker_rejects_degenerate_or_non_finite_input(pts):
    with pytest.raises(InvalidRouteInput) as ei:
        douglas_peucker(pts, 1.0)
    assert ei.value.field == "points"
