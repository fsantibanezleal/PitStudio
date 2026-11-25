# ruff: noqa: E501
"""Road-network builder (FR-007-38, FR-007-45): A* routes between the declared loader, dump and junction cells become the road
network of a scenario bundle (`contracts/haul-scenario.schema.json`, `$defs/network`).

Each route is simplified with Douglas-Peucker (tolerance epsilon from the recipe), cut into straight segments, and any segment
whose |grade| exceeds g_max is refined with intermediate route points until none does (every single route edge is feasible, so
the refinement always ends). Geometry convention: the centre of cell (row, col) is at x = col x cell_m, y = row x cell_m,
z = dem.z[row, col]; a segment's grade is 100 (z_b - z_a) / horizontal distance and its length is the 3-D chord, rounded to 1 mm.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

from .errors import DisconnectedNetwork, InvalidRouteInput, InvalidRouteRequest
from .routing import STANDARD_GRAVITY, Dem, NoFeasibleRoute, _validate_dem, find_route

KINDS = {"loaders": "face", "dumps": "dump", "junctions": "junction"}


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))


def _chord_distance(p: np.ndarray, a: np.ndarray, b: np.ndarray) -> float:
    ab, ap = b - a, p - a
    denom = float(ab @ ab)
    if denom == 0.0:
        return float(np.linalg.norm(ap))
    t = min(1.0, max(0.0, float(ap @ ab) / denom))  # distance to the chord (the segment a-b)
    return float(np.linalg.norm(p - (a + t * ab)))


def douglas_peucker(points: Any, epsilon: float) -> list[int]:
    """Indices kept by Douglas-Peucker: the farthest point (lowest index on ties) of a span is kept when its distance to the chord exceeds epsilon."""
    if not _is_number(epsilon) or not math.isfinite(epsilon) or epsilon <= 0.0:
        raise InvalidRouteInput("epsilon", epsilon, "must be a finite number > 0")
    pts = np.asarray(points, dtype=float)
    if pts.ndim != 2 or pts.shape[0] < 2 or pts.shape[1] < 1:
        raise InvalidRouteInput(
            "points", f"<array of shape {pts.shape}>", "needs at least 2 points of at least 1 coordinate"
        )
    if not np.all(np.isfinite(pts)):
        raise InvalidRouteInput("points", "<non-finite coordinates>", "every coordinate must be finite")
    keep = {0, len(pts) - 1}
    stack = [(0, len(pts) - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        dists = [_chord_distance(pts[k], pts[i], pts[j]) for k in range(i + 1, j)]
        m = max(dists)
        if m > epsilon:
            k = i + 1 + dists.index(m)
            keep.add(k)
            stack.append((i, k))
            stack.append((k, j))
    return sorted(keep)


def _check_scalar(field: str, v: Any, *, lo: float, lo_open: bool, hi: float | None = None) -> float:
    if not _is_number(v) or not math.isfinite(v):
        raise InvalidRouteInput(field, v, "must be a finite number")
    if (v <= lo) if lo_open else (v < lo):
        raise InvalidRouteInput(field, v, f"must be {'>' if lo_open else '>='} {lo}")
    if hi is not None and v > hi:
        raise InvalidRouteInput(field, v, f"must be <= {hi}")
    return float(v)


def _declared(
    declared: Any, dem_shape: tuple[int, int], nodata: np.ndarray | None
) -> list[tuple[str, int, tuple[int, int]]]:
    """(kind key, id, cell) of every declared node, validated; loaders first, then dumps, then junctions."""
    if not isinstance(declared, dict) or set(declared) - set(KINDS):
        raise InvalidRouteInput(
            "declared",
            declared if not isinstance(declared, dict) else sorted(declared),
            "must be an object with the keys loaders, dumps and junctions only",
        )
    if not declared.get("loaders") or not declared.get("dumps"):
        raise InvalidRouteInput("declared", "<loaders or dumps empty>", "at least one loader and one dump are required")
    out: list[tuple[str, int, tuple[int, int]]] = []
    ids: set[int] = set()
    cells: set[tuple[int, int]] = set()
    for key in KINDS:
        for d in declared.get(key, []):
            if not isinstance(d, dict) or "id" not in d or "cell" not in d:
                raise InvalidRouteInput("declared", d, "every entry needs an id and a cell")
            i = d["id"]
            if isinstance(i, bool) or not isinstance(i, (int, np.integer)) or i < 0:
                raise InvalidRouteInput("id", i, "must be an integer >= 0")
            if int(i) in ids:
                raise InvalidRouteInput("id", i, "duplicate declared id")
            cell = d["cell"]
            ok = (
                isinstance(cell, (tuple, list))
                and len(cell) == 2
                and all(isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)) for v in cell)
            )
            if not ok:
                raise InvalidRouteInput("cell", cell, "must be a (row, col) pair of integers")
            r, c = int(cell[0]), int(cell[1])
            if not (0 <= r < dem_shape[0] and 0 <= c < dem_shape[1]):
                raise InvalidRouteInput("cell", cell, "outside the grid")
            if nodata is not None and nodata[r, c]:
                raise InvalidRouteInput("cell", cell, "on a no-data cell")
            if (r, c) in cells:
                raise InvalidRouteInput("cell", cell, "duplicate declared cell")
            ids.add(int(i))
            cells.add((r, c))
            out.append((key, int(i), (r, c)))
    return out


def build_network(
    dem: Dem,
    declared: Any,
    *,
    epsilon_m: float,
    g_max: float,
    mass_kg: float,
    rr_pct: float,
    eta: float = 1.0,
    g: float | None = None,
    speed_limit_kmh: float = 30.0,
    width_class: int = 2,
) -> dict:
    """The bundle network {"nodes", "segments", "zones", "junctions"} from A* routes between the declared cells."""
    _check_scalar("epsilon_m", epsilon_m, lo=0.0, lo_open=True)
    z, nodata, cell_m = _validate_dem(dem)
    nodes_decl = _declared(declared, z.shape, nodata)
    _check_scalar("g_max", g_max, lo=0.0, lo_open=True, hi=1.0)
    _check_scalar("mass_kg", mass_kg, lo=0.0, lo_open=True)
    _check_scalar("rr_pct", rr_pct, lo=0.0, lo_open=False)
    _check_scalar("eta", eta, lo=0.0, lo_open=True, hi=1.0)
    _check_scalar("g", STANDARD_GRAVITY if g is None else g, lo=0.0, lo_open=True)

    by_key: dict[str, list[tuple[int, tuple[int, int]]]] = {k: [] for k in KINDS}
    cell_id: dict[tuple[int, int], int] = {}
    kind_of: dict[tuple[int, int], str] = {}
    for key, i, cell in nodes_decl:
        by_key[key].append((i, cell))
        cell_id[cell] = i
        kind_of[cell] = KINDS[key]
    next_id = max(i for _, i, _ in nodes_decl) + 1

    requests = [(lc, dc, lid, did) for lid, lc in by_key["loaders"] for did, dc in by_key["dumps"]]
    for jid, jc in by_key["junctions"]:
        requests += [(jc, lc, jid, lid) for lid, lc in by_key["loaders"]]
        requests += [(jc, dc, jid, did) for did, dc in by_key["dumps"]]
    routes, missing = [], []
    for start, goal, a_id, b_id in requests:
        try:
            res = find_route(dem, start, goal, mass_kg=mass_kg, rr_pct=rr_pct, g_max=g_max, eta=eta, g=g)
        except InvalidRouteRequest as exc:  # cannot happen after the checks above; never swallowed silently
            raise InvalidRouteInput(exc.field, exc.value, str(exc)) from None
        if isinstance(res, NoFeasibleRoute):
            missing.append((a_id, b_id))
        else:
            routes.append(res.cells)
    if missing:
        raise DisconnectedNetwork(missing)

    def xyz(cell: tuple[int, int]) -> np.ndarray:
        return np.array([cell[1] * cell_m, cell[0] * cell_m, float(z[cell])])

    def horizontal(a: tuple[int, int], b: tuple[int, int]) -> float:
        return math.hypot((b[1] - a[1]) * cell_m, (b[0] - a[0]) * cell_m)

    def grade(a: tuple[int, int], b: tuple[int, int]) -> float:
        return 100.0 * (float(z[b]) - float(z[a])) / horizontal(a, b)

    segments: list[dict] = []
    seen_pairs: set[frozenset[tuple[int, int]]] = set()
    for cells in routes:
        pts = np.array([xyz(c) for c in cells])
        kept = douglas_peucker(pts, epsilon_m)
        spans = [(kept[i], kept[i + 1]) for i in range(len(kept) - 1)]
        pieces: list[tuple[int, int]] = []
        while spans:
            i, j = spans.pop(0)
            if j - i > 1 and abs(grade(cells[i], cells[j])) / 100.0 > g_max:
                k = (i + j) // 2
                spans[0:0] = [(i, k), (k, j)]
            else:
                pieces.append((i, j))
        for i, j in pieces:
            a, b = cells[i], cells[j]
            pair = frozenset((a, b))
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            for cell in (a, b):
                if cell not in cell_id:
                    cell_id[cell] = next_id
                    kind_of[cell] = "waypoint"
                    next_id += 1
            pa, pb = xyz(a), xyz(b)
            segments.append(
                {
                    "id": len(segments),
                    "a": cell_id[a],
                    "b": cell_id[b],
                    "polyline_m": [pa.tolist(), pb.tolist()],
                    "length_m": round(float(np.linalg.norm(pb - pa)), 3),
                    "grade_pct": grade(a, b),
                    "width_class": width_class,
                    "one_way": False,
                    "speed_limit_kmh": speed_limit_kmh,
                    "rolling_resistance_pct": rr_pct,
                    "zone_id": None,
                    "single_lane_op": False,
                }
            )
    used = {c for s in seen_pairs for c in s} | set(cell_id) & {c for _, _, c in nodes_decl}
    nodes = [
        {"id": cell_id[c], "kind": kind_of[c], "pos_m": xyz(c).tolist()} for c in sorted(used, key=lambda c: cell_id[c])
    ]
    return {"nodes": nodes, "segments": segments, "zones": [], "junctions": []}
