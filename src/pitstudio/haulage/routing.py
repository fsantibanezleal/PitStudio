# ruff: noqa: E501, SIM102
"""Grade-constrained least-energy router over a DEM (FR-007-35, FR-007-36, FR-007-37, P-007-17, P-007-18).

8-neighbour A* between two DEM cells. An edge is feasible only if |dz| / L <= g_max, its cost is
c(e) = (m g / eta) max(0, RR/100 L + dz) and the search uses the admissible heuristic
h(n) = (m g / eta) max(0, RR/100 d_xy + z_goal - z_n); ties are broken by (f, g, cell index = row x cols + col), all ascending,
and a cell is re-parented only on a strictly lower g. An unreachable goal is a value (`NoFeasibleRoute`), never an exception;
each feasible cell is expanded at most once. The gravity default is the `minephys` knowledge-table value.
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field
from typing import Any

import numpy as np
from minephys.knowledge import get_value

from .errors import InvalidDEM, InvalidRouteRequest

STANDARD_GRAVITY = float(get_value("standard_gravity"))  # knowledge-table row, verified (NIST SP 811)
MAX_CELLS = 4096 * 4096  # pipeline limit; the browser limit (1024 x 1024) belongs to the TypeScript port
SQRT2 = math.sqrt(2.0)
NEIGHBOURS = ((-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1))


@dataclass
class Dem:
    """Elevations z [rows, cols] in metres, the square cell size in metres, and an optional no-data mask (True = never entered)."""

    z: Any
    cell_m: Any
    nodata: Any = None


@dataclass(frozen=True)
class Route:
    cells: list[tuple[int, int]]
    cost_j: float
    expanded: int = field(default=0)


@dataclass(frozen=True)
class NoFeasibleRoute:
    expanded: int


def _is_number(v: Any) -> bool:
    return isinstance(v, (int, float, np.integer, np.floating)) and not isinstance(v, (bool, np.bool_))


def _validate_dem(dem: Dem) -> tuple[np.ndarray, np.ndarray | None, float]:
    z = dem.z
    if not isinstance(z, np.ndarray):
        try:
            z = np.asarray(z)
        except TypeError, ValueError:
            raise InvalidDEM("z", "the elevations must be a numeric array") from None
    if z.ndim != 2 or z.size == 0:
        raise InvalidDEM("shape", f"the DEM must be a non-empty 2-D array, got shape {z.shape}", count=int(z.size))
    if z.shape[0] * z.shape[1] > MAX_CELLS:
        raise InvalidDEM(
            "shape", f"more than 4096 x 4096 cells ({z.shape[0] * z.shape[1]})", count=z.shape[0] * z.shape[1]
        )
    if z.dtype.kind not in "fiu":
        raise InvalidDEM("z", f"the elevations must be numeric, got dtype {z.dtype}")
    if not _is_number(dem.cell_m) or not math.isfinite(dem.cell_m) or dem.cell_m <= 0:
        raise InvalidDEM("cell_m", f"the cell size must be a finite number > 0, got {dem.cell_m!r}")
    nodata = dem.nodata
    if nodata is not None:
        if not isinstance(nodata, np.ndarray) or nodata.dtype != np.bool_ or nodata.shape != z.shape:
            raise InvalidDEM("nodata", "the no-data mask must be a boolean array of the DEM's shape")
    z = np.asarray(z, dtype=np.float64)
    bad = ~np.isfinite(z)
    if nodata is not None:
        bad &= ~nodata
    count = int(bad.sum())
    if count:
        first = int(np.flatnonzero(bad.ravel())[0])
        raise InvalidDEM(
            "z", "NaN or infinite elevation outside the no-data mask", cell=divmod(first, z.shape[1]), count=count
        )
    return z, nodata, float(dem.cell_m)


def _check_request(*, mass_kg, rr_pct, g_max, eta, g) -> float:
    def positive(name: str, v: Any, *, lo_open: bool, hi: float | None = None, lo: float = 0.0) -> float:
        if not _is_number(v) or not math.isfinite(v):
            raise InvalidRouteRequest(name, v, "must be a finite number")
        if (v <= lo) if lo_open else (v < lo):
            raise InvalidRouteRequest(name, v, f"must be {'>' if lo_open else '>='} {lo}")
        if hi is not None and v > hi:
            raise InvalidRouteRequest(name, v, f"must be <= {hi}")
        return float(v)

    positive("g_max", g_max, lo_open=True, hi=1.0)
    positive("mass_kg", mass_kg, lo_open=True)
    positive("rr_pct", rr_pct, lo_open=False)
    positive("eta", eta, lo_open=True, hi=1.0)
    return STANDARD_GRAVITY if g is None else positive("g", g, lo_open=True)


def _cell(name: str, value: Any, shape: tuple[int, int], nodata: np.ndarray | None) -> tuple[int, int]:
    ok = (
        isinstance(value, (tuple, list))
        and len(value) == 2
        and all(isinstance(v, (int, np.integer)) and not isinstance(v, (bool, np.bool_)) for v in value)
    )
    if not ok:
        raise InvalidRouteRequest(name, value, "must be a (row, col) pair of integers")
    r, c = int(value[0]), int(value[1])
    if not (0 <= r < shape[0] and 0 <= c < shape[1]):
        raise InvalidRouteRequest(name, (r, c), f"outside the {shape[0]} x {shape[1]} grid")
    if nodata is not None and nodata[r, c]:
        raise InvalidRouteRequest(name, (r, c), "on a no-data cell")
    return r, c


def heuristic(dem: Dem, cell: tuple[int, int], goal: tuple[int, int], *, mass_kg, rr_pct, eta=1.0, g=None) -> float:
    """K max(0, RR/100 d_xy + (z_goal - z_n)) with K = mass g / eta; the elevation difference is formed first."""
    z, _nodata, cell_m = _validate_dem(dem)
    grav = _check_request(mass_kg=mass_kg, rr_pct=rr_pct, g_max=1.0, eta=eta, g=g)
    k = mass_kg * grav / eta
    d_xy = cell_m * math.hypot(cell[0] - goal[0], cell[1] - goal[1])
    return k * max(0.0, rr_pct / 100.0 * d_xy + (float(z[goal]) - float(z[cell])))


def find_route(dem: Dem, start: Any, goal: Any, *, mass_kg, rr_pct, g_max, eta=1.0, g=None) -> Route | NoFeasibleRoute:
    """The least-energy feasible 8-neighbour path from `start` to `goal` (cells are (row, col)), or NoFeasibleRoute."""
    z, nodata, cell_m = _validate_dem(dem)
    grav = _check_request(mass_kg=mass_kg, rr_pct=rr_pct, g_max=g_max, eta=eta, g=g)
    start = _cell("start", start, z.shape, nodata)
    goal = _cell("goal", goal, z.shape, nodata)
    if start == goal:
        return Route([start], 0.0, 1)
    rows, cols = z.shape
    k = mass_kg * grav / eta
    rr = rr_pct / 100.0
    zf = z.ravel().tolist()
    blocked = nodata.ravel().tolist() if nodata is not None else None
    gz, goal_r, goal_c = zf[goal[0] * cols + goal[1]], goal[0], goal[1]
    lengths = [cell_m * (SQRT2 if dr != 0 and dc != 0 else 1.0) for dr, dc in NEIGHBOURS]

    def h(r: int, c: int) -> float:
        return k * max(0.0, rr * (cell_m * math.hypot(r - goal_r, c - goal_c)) + (gz - zf[r * cols + c]))

    s_idx, g_idx = start[0] * cols + start[1], goal[0] * cols + goal[1]
    g_score = {s_idx: 0.0}
    parent: dict[int, int] = {}
    heap = [(h(*start), 0.0, s_idx)]
    closed: set[int] = set()
    expanded = 0
    while heap:
        _f, gs, idx = heapq.heappop(heap)
        if idx in closed or gs > g_score[idx]:
            continue
        closed.add(idx)
        expanded += 1
        if idx == g_idx:
            path = [idx]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            path.reverse()
            return Route([divmod(i, cols) for i in path], gs, expanded)
        r, c = divmod(idx, cols)
        zi = zf[idx]
        for (dr, dc), length in zip(NEIGHBOURS, lengths, strict=True):
            nr, nc = r + dr, c + dc
            if not (0 <= nr < rows and 0 <= nc < cols):
                continue
            nidx = nr * cols + nc
            if nidx in closed or (blocked is not None and blocked[nidx]):
                continue
            dz = zf[nidx] - zi
            if abs(dz) / length > g_max:
                continue
            ng = gs + k * max(0.0, rr * length + dz)
            if nidx not in g_score or ng < g_score[nidx]:
                g_score[nidx] = ng
                parent[nidx] = idx
                heapq.heappush(heap, (ng + h(nr, nc), ng, nidx))
    return NoFeasibleRoute(expanded)
