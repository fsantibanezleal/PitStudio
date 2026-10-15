"""Polygons of a binary instance mask for the COCO files of `st55_sdg`: the exact outer outline of each component.

`external_polygons(mask)` labels the 4-connected components of the mask (SciPy) and walks the outer boundary of each
one along the pixel edges, keeping only the corner vertices, so the polygon's area equals the component's pixel count
for a component without holes. Vertices are pixel-corner coordinates (x to the right, y down), the convention of COCO
polygons. Pure NumPy and SciPy: it runs in the Isaac Sim environment and in the CPU test environments alike.
"""

from __future__ import annotations

import numpy as np
from scipy import ndimage

_FOUR = ndimage.generate_binary_structure(2, 1)
# directions in image coordinates (x right, y down) in clockwise order: right, down, left, up
_DIRS = ((1, 0), (0, 1), (-1, 0), (0, -1))


def _sharpest_right(here: tuple[int, int], heading: int, options: list[tuple[int, int]]) -> tuple[int, int]:
    """Of the edges leaving `here`, the one that turns most to the right of `heading` (right, straight, left, back)."""
    rank = {1: 0, 0: 1, 3: 2, 2: 3}
    return min(options, key=lambda c: rank[(_DIRS.index((c[0] - here[0], c[1] - here[1])) - heading) % 4])


def _outer_loop(component: np.ndarray) -> list[tuple[int, int]]:
    """Corner vertices of the outer boundary of one 4-connected component, clockwise in image coordinates."""
    padded = np.pad(component, 1)
    ys, xs = np.nonzero(padded)
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for y, x in zip(ys.tolist(), xs.tolist(), strict=True):
        px, py = x - 1, y - 1  # pixel (px, py) of the unpadded mask; its corners are (px, py) .. (px + 1, py + 1)
        if not padded[y - 1, x]:
            edges.setdefault((px, py), []).append((px + 1, py))
        if not padded[y, x + 1]:
            edges.setdefault((px + 1, py), []).append((px + 1, py + 1))
        if not padded[y + 1, x]:
            edges.setdefault((px + 1, py + 1), []).append((px, py + 1))
        if not padded[y, x - 1]:
            edges.setdefault((px, py + 1), []).append((px, py))
    start = min(edges, key=lambda v: (v[1], v[0]))
    loop = [start]
    here, heading = start, 0  # the first edge out of the top-left vertex runs right along the top
    first = True
    while True:
        options = edges[here]
        if first:
            nxt = (here[0] + 1, here[1])
            first = False
        elif len(options) == 1:
            nxt = options[0]
        else:  # a pinch vertex: take the sharpest right turn so that the walk stays on the outer boundary
            nxt = _sharpest_right(here, heading, options)
        heading = _DIRS.index((nxt[0] - here[0], nxt[1] - here[1]))
        here = nxt
        if here == start:
            break
        loop.append(here)
    # keep the corners only
    corners = []
    for i, v in enumerate(loop):
        prev, nxt = loop[i - 1], loop[(i + 1) % len(loop)]
        if (v[0] - prev[0], v[1] - prev[1]) != (nxt[0] - v[0], nxt[1] - v[1]):
            corners.append(v)
    return corners


def external_polygons(mask: np.ndarray, *, max_polygons: int = 64) -> list[list[float]]:
    """Flat `[x0, y0, x1, y1, ...]` polygons, largest first, one per 4-connected component (at most `max_polygons`)."""
    labels, _ = ndimage.label(np.asarray(mask, dtype=bool), structure=_FOUR)
    found: list[tuple[int, list[float]]] = []
    for k, region in enumerate(ndimage.find_objects(labels), start=1):
        component = labels[region] == k
        loop = _outer_loop(component)
        dx, dy = region[1].start, region[0].start
        flat = [float(c) for vertex in loop for c in (vertex[0] + dx, vertex[1] + dy)]
        if len(flat) >= 6:
            found.append((int(component.sum()), flat))
    found.sort(key=lambda item: -item[0])
    return [flat for _, flat in found[:max_polygons]]
