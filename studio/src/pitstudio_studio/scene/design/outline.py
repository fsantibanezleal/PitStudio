"""The pit outline from a terrain contour at the declared rim elevation (FR-004-16): marching squares on cell
centres."""

from __future__ import annotations

import numpy as np

from pitstudio_studio.scene.common import SceneStageError

# marching-squares cases: corner bits TL*8 + TR*4 + BR*2 + BL (1 = below the level); edges T, R, B, L of the quad
_SEGMENTS: dict[int, list[tuple[str, str]]] = {
    1: [("L", "B")],
    2: [("B", "R")],
    3: [("L", "R")],
    4: [("T", "R")],
    6: [("T", "B")],
    7: [("L", "T")],
    8: [("L", "T")],
    9: [("T", "B")],
    11: [("T", "R")],
    12: [("L", "R")],
    13: [("B", "R")],
    14: [("L", "B")],
}


def _edge_id(edge: str, r: int, c: int) -> tuple[str, int, int]:
    """Identity of a quad edge shared with its neighbours: `h` between (r, c)-(r, c+1), `v` between (r, c)-(r+1, c)."""
    return {"T": ("h", r, c), "B": ("h", r + 1, c), "L": ("v", r, c), "R": ("v", r, c + 1)}[edge]


def _segments(z: np.ndarray, level: float) -> list[tuple[tuple[str, int, int], tuple[str, int, int]]]:
    below = z < level
    finite = np.isfinite(z)
    tl, tr, bl, br = below[:-1, :-1], below[:-1, 1:], below[1:, :-1], below[1:, 1:]
    ok = finite[:-1, :-1] & finite[:-1, 1:] & finite[1:, :-1] & finite[1:, 1:]
    case = tl * 8 + tr * 4 + br * 2 + bl
    active = ok & (case != 0) & (case != 15)
    out: list[tuple[tuple[str, int, int], tuple[str, int, int]]] = []
    for r, c in zip(*np.nonzero(active), strict=True):
        k = int(case[r, c])
        r, c = int(r), int(c)
        if k in (5, 10):
            centre_below = (z[r, c] + z[r, c + 1] + z[r + 1, c] + z[r + 1, c + 1]) / 4.0 < level
            if k == 5:  # TR and BL below
                pairs = [("L", "T"), ("B", "R")] if centre_below else [("T", "R"), ("L", "B")]
            else:  # TL and BR below
                pairs = [("T", "R"), ("L", "B")] if centre_below else [("L", "T"), ("B", "R")]
        else:
            pairs = _SEGMENTS[k]
        out.extend((_edge_id(a, r, c), _edge_id(b, r, c)) for a, b in pairs)
    return out


def rim_contour(
    elevation: np.ndarray, *, x_min_m: float, y_max_m: float, cell_size_m: float, rim_z_m: float
) -> list[list[float]]:
    """The ring of the region below `rim_z_m` around the lowest cell, as `[x, y]` site-frame vertices (not closed).

    Linear interpolation between cell centres; of all closed contours that enclose the lowest cell the innermost wins.
    Raises `outline-invalid` when no closed contour surrounds the lowest cell (the pit touches the grid edge).
    """
    from shapely.geometry import Point, Polygon
    from shapely.geometry.polygon import orient

    z = np.asarray(elevation, dtype=np.float64)
    rows, cols = z.shape
    xs = x_min_m + (np.arange(cols) + 0.5) * cell_size_m
    ys = y_max_m - (np.arange(rows) + 0.5) * cell_size_m

    def point(edge: tuple[str, int, int]) -> tuple[float, float]:
        kind, r, c = edge
        if kind == "h":
            a, b = z[r, c], z[r, c + 1]
            t = (rim_z_m - a) / (b - a)
            return float(xs[c] + t * cell_size_m), float(ys[r])
        a, b = z[r, c], z[r + 1, c]
        t = (rim_z_m - a) / (b - a)
        return float(xs[c]), float(ys[r] - t * cell_size_m)

    adjacency: dict[tuple[str, int, int], list[tuple[str, int, int]]] = {}
    for a, b in _segments(z, rim_z_m):
        adjacency.setdefault(a, []).append(b)
        adjacency.setdefault(b, []).append(a)
    rings: list[list[tuple[float, float]]] = []
    seen: set[tuple[str, int, int]] = set()
    for start in sorted(adjacency):
        if start in seen:
            continue
        chain = [start]
        seen.add(start)
        previous, current = None, start
        closed = False
        while True:
            options = [n for n in adjacency[current] if n != previous]
            nxt = next((n for n in options if n not in seen), None)
            if nxt is None:
                closed = start in adjacency[current] and len(chain) > 2
                break
            chain.append(nxt)
            seen.add(nxt)
            previous, current = current, nxt
        if closed:
            rings.append([point(e) for e in chain])
    finite = np.where(np.isfinite(z), z, np.inf)
    r0, c0 = np.unravel_index(int(np.argmin(finite)), z.shape)
    lowest = Point(float(xs[c0]), float(ys[r0]))
    candidates = []
    for ring in rings:
        poly = Polygon(ring)
        if poly.is_valid and poly.area > 0 and poly.contains(lowest):
            candidates.append(poly)
    if not candidates:
        raise SceneStageError("outline-invalid", "no closed contour at the rim elevation surrounds the lowest cell")
    best = orient(min(candidates, key=lambda p: p.area), 1.0)
    return [[float(x), float(y)] for x, y in list(best.exterior.coords)[:-1]]
