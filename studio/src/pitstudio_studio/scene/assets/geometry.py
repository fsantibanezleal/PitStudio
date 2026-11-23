"""Mesh primitives of the procedural machines and the person mannequin (FR-004-51).

Every builder returns a `Piece`: a closed polygon mesh in the frame of the asset (x forward, y left, z up, metres) with
the part label and the material kind it carries. Orientation is made outward by the sign of the enclosed volume, so
each builder only has to be consistent. Everything is a pure function of its arguments (bitwise deterministic).
"""

from __future__ import annotations

import itertools
import math
from collections.abc import Sequence
from dataclasses import dataclass

import numpy as np

Vec = tuple[float, float, float]


@dataclass(frozen=True)
class Piece:
    """One visible part of an asset: a closed mesh, its `part` label and its material kind."""

    name: str
    part: str  # a part label of the SceneSpec vocabulary (FR-004-25), or a person part label
    material: str  # paint, rubber, steel, glass, skin or fabric, optionally followed by `_<variant>`
    points: np.ndarray  # (n, 3) float64
    counts: tuple[int, ...]
    indices: tuple[int, ...]

    def moved(self, delta: Sequence[float]) -> Piece:
        return Piece(
            self.name, self.part, self.material, self.points + np.asarray(delta, float), self.counts, self.indices
        )

    def retag(self, name: str, part: str | None = None, material: str | None = None) -> Piece:
        return Piece(name, part or self.part, material or self.material, self.points, self.counts, self.indices)


def _outward(points: np.ndarray, counts: list[int], indices: list[int]) -> list[int]:
    """The face indices with every face reversed when the mesh encloses a negative volume."""
    volume, at = 0.0, 0
    centre = points.mean(axis=0)
    for count in counts:
        ring = points[indices[at : at + count]] - centre
        for k in range(1, count - 1):
            volume += float(np.dot(ring[0], np.cross(ring[k], ring[k + 1]))) / 6.0
        at += count
    if volume >= 0.0:
        return indices
    out, at = [], 0
    for count in counts:
        out.extend(reversed(indices[at : at + count]))
        at += count
    return out


def _piece(name: str, part: str, material: str, points, counts, indices) -> Piece:
    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    cnt, idx = list(counts), list(indices)
    return Piece(name, part, material, pts, tuple(cnt), tuple(_outward(pts, cnt, idx)))


def box(name: str, part: str, material: str, lo: Vec, hi: Vec) -> Piece:
    """An axis-aligned box from the corner `lo` to the corner `hi`."""
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    pts = [(x, y, z) for z in (z0, z1) for y in (y0, y1) for x in (x0, x1)]
    faces = [(0, 2, 3, 1), (4, 5, 7, 6), (0, 1, 5, 4), (2, 6, 7, 3), (0, 4, 6, 2), (1, 3, 7, 5)]
    return _piece(name, part, material, pts, [4] * 6, [i for f in faces for i in f])


def prism(name: str, part: str, material: str, profile: Sequence[tuple[float, float]], y0: float, y1: float) -> Piece:
    """A polygon of (x, z) points extruded across y from `y0` to `y1` (a convex profile)."""
    n = len(profile)
    pts = [(x, y0, z) for x, z in profile] + [(x, y1, z) for x, z in profile]
    faces = [tuple(range(n)), tuple(range(2 * n - 1, n - 1, -1))]
    faces += [(i, (i + 1) % n, n + (i + 1) % n, n + i) for i in range(n)]
    return _piece(name, part, material, pts, [len(f) for f in faces], [i for f in faces for i in f])


def _frame(axis: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    helper = np.array([0.0, 0.0, 1.0]) if abs(axis[2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    u = np.cross(axis, helper)
    u /= np.linalg.norm(u)
    return u, np.cross(axis, u)


def lathe(
    name: str,
    part: str,
    material: str,
    centre: Vec,
    axis: Vec,
    profile: Sequence[tuple[float, float]],
    segments: int = 24,
    closed: bool = False,
) -> Piece:
    """A surface of revolution about `axis` through `centre`: `profile` lists (radius, offset along the axis) points.

    A point with radius 0 is a pole (one vertex). With `closed` the last profile point joins the first (a torus-like
    ring such as a tyre); otherwise both ends must be poles or are capped by a flat fan.
    """
    a = np.asarray(axis, float)
    a = a / np.linalg.norm(a)
    u, v = _frame(a)
    c = np.asarray(centre, float)
    pts: list[np.ndarray] = []
    rings: list[list[int]] = []
    for radius, offset in profile:
        if radius <= 1e-9:
            rings.append([len(pts)])
            pts.append(c + a * offset)
        else:
            ring = []
            for k in range(segments):
                t = 2.0 * math.pi * k / segments
                ring.append(len(pts))
                pts.append(c + a * offset + radius * (math.cos(t) * u + math.sin(t) * v))
            rings.append(ring)
    faces: list[tuple[int, ...]] = []
    links = list(itertools.pairwise(rings)) + ([(rings[-1], rings[0])] if closed else [])
    for r0, r1 in links:
        for k in range(segments):
            k2 = (k + 1) % segments
            if len(r0) == 1:
                faces.append((r0[0], r1[k2], r1[k]))
            elif len(r1) == 1:
                faces.append((r0[k], r0[k2], r1[0]))
            else:
                faces.append((r0[k], r0[k2], r1[k2], r1[k]))
    if not closed:
        faces.extend(tuple(ring) for ring in (rings[0], rings[-1]) if len(ring) > 1)
    return _piece(name, part, material, pts, [len(f) for f in faces], [i for f in faces for i in f])


def tube(
    name: str, part: str, material: str, p0: Vec, p1: Vec, r0: float, r1: float | None = None, segments: int = 12
) -> Piece:
    """A capped cone frustum between the points `p0` and `p1` (a cylinder when the radii are equal)."""
    start, end = np.asarray(p0, float), np.asarray(p1, float)
    axis = end - start
    length = float(np.linalg.norm(axis))
    radius1 = r0 if r1 is None else r1
    return lathe(name, part, material, tuple(start), tuple(axis / length), [(r0, 0.0), (radius1, length)], segments)


def ellipsoid(name: str, part: str, material: str, centre: Vec, radii: Vec, segments: int = 14) -> Piece:
    """An ellipsoid with the semi-axes `radii` (a sphere when they are equal)."""
    rings = max(segments // 2, 4)
    prof = [(math.sin(math.pi * i / rings), -math.cos(math.pi * i / rings)) for i in range(rings + 1)]
    unit = lathe(name, part, material, (0.0, 0.0, 0.0), (0.0, 0.0, 1.0), prof, segments)
    pts = unit.points * np.asarray(radii, float) + np.asarray(centre, float)
    return _piece(name, part, material, pts, unit.counts, unit.indices)


def bounds(pieces: Sequence[Piece]) -> tuple[np.ndarray, np.ndarray]:
    """The (min, max) corners of the union of `pieces`."""
    stack = np.vstack([p.points for p in pieces])
    return stack.min(axis=0), stack.max(axis=0)
