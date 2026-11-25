# ruff: noqa: E501
"""Test-support module of spec 007 for the router and the network builder (locked with its first user, T-007-060).

Reference implementations written for the tests, independent of the code under test:
    * `edges` / `edge_cost` / `feasible_edge`: the graph of FR-007-35 (8-neighbour, |dz| / L <= g_max, c(e) = K x max(0, RR/100 x L + dz), K = m g / eta);
    * `nx_distance` / `nx_cost_to_go`: networkx Dijkstra on that graph (networkx is imported lazily: it is a root dev dependency added by T-007-002);
    * `reference_astar`: a plain heapq A* with the spec's tie rule (f, g, cell index) and the spec's heuristic, used to write the golden vectors;
    * DEM generators with dyadic elevations (k x 2^-10 m).

Nothing here imports the code under test.
"""

from __future__ import annotations

import heapq
import itertools
import json
import math
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
GOLDENS = ROOT / "tests" / "fixtures" / "haulage" / "routing" / "astar_goldens.json"
G0 = 9.80665  # standard gravity (ISO 80000-3), passed explicitly to the router under test
NEIGHBOURS = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]


def dyadic_dem(
    rng: np.random.Generator, rows: int, cols: int, *, relief: float = 4.0, jitter_units: int = 24
) -> np.ndarray:
    """A smooth-ish DEM whose every elevation is an integer multiple of 2^-10 m with |z| <= 2^12."""
    cr, cc = rows // 4 + 2, cols // 4 + 2
    coarse = rng.integers(-int(relief * 1024), int(relief * 1024) + 1, size=(cr, cc)).astype(np.float64)
    rr = np.linspace(0, cr - 1, rows)
    cc_ = np.linspace(0, cc - 1, cols)
    r0 = np.minimum(rr.astype(int), cr - 2)
    c0 = np.minimum(cc_.astype(int), cc - 2)
    fr, fc = (rr - r0)[:, None], (cc_ - c0)[None, :]
    z = (
        coarse[r0][:, c0] * (1 - fr) * (1 - fc)
        + coarse[r0 + 1][:, c0] * fr * (1 - fc)
        + coarse[r0][:, c0 + 1] * (1 - fr) * fc
        + coarse[r0 + 1][:, c0 + 1] * fr * fc
    )
    z = np.rint(z) + rng.integers(-jitter_units, jitter_units + 1, size=(rows, cols))
    return np.clip(z, -(2**22), 2**22) / 1024.0  # |z| <= 2^12 m, multiples of 2^-10


def feasible_edge(
    dem_z, cell_m: float, a: tuple[int, int], b: tuple[int, int], g_max: float
) -> tuple[bool, float, float]:
    length = cell_m * (math.sqrt(2.0) if a[0] != b[0] and a[1] != b[1] else 1.0)
    dz = float(dem_z[b] - dem_z[a])
    return abs(dz) / length <= g_max, length, dz


def edge_cost(k: float, rr_pct: float, length: float, dz: float) -> float:
    return k * max(0.0, rr_pct / 100.0 * length + dz)


def edges(z, cell_m: float, nodata, g_max: float, k: float, rr_pct: float):
    """Yield (a, b, cost, length) for every feasible directed edge between data cells."""
    rows, cols = z.shape
    for r in range(rows):
        for c in range(cols):
            if nodata is not None and nodata[r, c]:
                continue
            for dr, dc in NEIGHBOURS:
                rb, cb = r + dr, c + dc
                if not (0 <= rb < rows and 0 <= cb < cols) or (nodata is not None and nodata[rb, cb]):
                    continue
                ok, length, dz = feasible_edge(z, cell_m, (r, c), (rb, cb), g_max)
                if ok:
                    yield (r, c), (rb, cb), edge_cost(k, rr_pct, length, dz), length


def k_of(mass_kg: float, eta: float, g: float = G0) -> float:
    return mass_kg * g / eta


def nx_graph(z, cell_m, nodata, g_max, k, rr_pct, *, reverse: bool = False):
    import networkx as nx

    G = nx.DiGraph()
    for a, b, w, _ in edges(z, cell_m, nodata, g_max, k, rr_pct):
        if reverse:
            a, b = b, a
        G.add_edge(a, b, w=w)
    return G


def nx_distance(z, cell_m, nodata, g_max, k, rr_pct, start, goal):
    """networkx Dijkstra cost start -> goal on the feasible graph, or None when the goal is unreachable."""
    import networkx as nx

    G = nx_graph(z, cell_m, nodata, g_max, k, rr_pct)
    if start not in G or goal not in G:
        return 0.0 if start == goal else None
    try:
        return float(nx.dijkstra_path_length(G, start, goal, weight="w"))
    except nx.NetworkXNoPath:
        return None


def nx_cost_to_go(z, cell_m, nodata, g_max, k, rr_pct, goal) -> dict:
    """True cost-to-go of every cell: Dijkstra from the goal on the reverse graph."""
    import networkx as nx

    G = nx_graph(z, cell_m, nodata, g_max, k, rr_pct, reverse=True)
    if goal not in G:
        return {goal: 0.0}
    return {n: float(d) for n, d in nx.single_source_dijkstra_path_length(G, goal, weight="w").items()}


def heuristic(z, cell_m, cell, goal, k, rr_pct) -> float:
    d_xy = cell_m * math.hypot(cell[0] - goal[0], cell[1] - goal[1])
    return k * max(
        0.0, rr_pct / 100.0 * d_xy + (float(z[goal]) - float(z[cell]))
    )  # the elevation difference first: exact for dyadic elevations, hence invariant under a dyadic shift


def reference_astar(z, cell_m, nodata, start, goal, g_max, k, rr_pct):
    """A* with the tie rule of FR-007-35: the heap orders (f, g, cell index); returns (cells, cost, expanded) or (None, None, expanded)."""
    rows, cols = z.shape
    idx = lambda cell: cell[0] * cols + cell[1]  # noqa: E731
    g_score = {start: 0.0}
    parent: dict = {}
    heap = [(heuristic(z, cell_m, start, goal, k, rr_pct), 0.0, idx(start), start)]
    closed: set = set()
    expanded = 0
    while heap:
        _f, g, _i, cell = heapq.heappop(heap)
        if cell in closed:
            continue
        if g > g_score[cell]:
            continue
        closed.add(cell)
        expanded += 1
        if cell == goal:
            path = [cell]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            path.reverse()
            return path, g, expanded
        for dr, dc in NEIGHBOURS:
            nb = (cell[0] + dr, cell[1] + dc)
            if not (0 <= nb[0] < rows and 0 <= nb[1] < cols) or (nodata is not None and nodata[nb]):
                continue
            ok, length, dz = feasible_edge(z, cell_m, cell, nb, g_max)
            if not ok or nb in closed:
                continue
            ng = g + edge_cost(k, rr_pct, length, dz)
            if nb not in g_score or ng < g_score[nb]:
                g_score[nb] = ng
                parent[nb] = cell
                heapq.heappush(heap, (ng + heuristic(z, cell_m, nb, goal, k, rr_pct), ng, idx(nb), nb))
    return None, None, expanded


def reachable(z, cell_m, nodata, start, g_max) -> set:
    seen, stack = {start}, [start]
    rows, cols = z.shape
    while stack:
        cell = stack.pop()
        for dr, dc in NEIGHBOURS:
            nb = (cell[0] + dr, cell[1] + dc)
            if nb in seen or not (0 <= nb[0] < rows and 0 <= nb[1] < cols) or (nodata is not None and nodata[nb]):
                continue
            if feasible_edge(z, cell_m, cell, nb, g_max)[0]:
                seen.add(nb)
                stack.append(nb)
    return seen


def octile(d_r: int, d_c: int) -> float:
    lo, hi = sorted((abs(d_r), abs(d_c)))
    return (hi - lo) + math.sqrt(2.0) * lo


def path_cost(z, cell_m, cells, k, rr_pct) -> float:
    total = 0.0
    for a, b in itertools.pairwise(cells):
        _ok, length, dz = feasible_edge(z, cell_m, a, b, math.inf)
        total += edge_cost(k, rr_pct, length, dz)
    return total


def golden_cases() -> list[dict]:
    return json.loads(GOLDENS.read_text(encoding="utf-8"))["cases"]


def case_arrays(case: dict):
    z = np.array(case["z"], dtype=np.float64).reshape(case["rows"], case["cols"])
    nodata = None
    if case["nodata"]:
        nodata = np.zeros((case["rows"], case["cols"]), dtype=bool)
        for i in case["nodata"]:
            nodata[divmod(i, case["cols"])] = True
    return z, nodata
