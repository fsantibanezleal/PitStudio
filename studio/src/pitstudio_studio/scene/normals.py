"""Normals of the meshes the scene stages author (FR-004-34): `usd-validation-nvidia` reports every mesh without
authored normals as an error (`NormalsExistChecker`), so each writer of a mesh sets them here."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

_FALLBACK = np.array([0.0, 0.0, 1.0])


def _face_normals(points: np.ndarray, counts: np.ndarray, indices: np.ndarray) -> np.ndarray:
    """Unit normal of every face (Newell's method, counter-clockwise winding), `(+z)` for a degenerate face."""
    if len(counts) and np.all(counts == 3):  # triangles: one vectorised cross product
        tri = points[indices.reshape(-1, 3)]
        out = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
        length = np.linalg.norm(out, axis=1, keepdims=True)
        return np.where(length > 1e-12, out / np.where(length > 1e-12, length, 1.0), _FALLBACK)
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    out = np.zeros((len(counts), 3))
    for face, (start, count) in enumerate(zip(starts, counts, strict=True)):
        ring = points[indices[start : start + count]]
        nxt = np.roll(ring, -1, axis=0)
        out[face] = [
            np.sum((ring[:, 1] - nxt[:, 1]) * (ring[:, 2] + nxt[:, 2])),
            np.sum((ring[:, 2] - nxt[:, 2]) * (ring[:, 0] + nxt[:, 0])),
            np.sum((ring[:, 0] - nxt[:, 0]) * (ring[:, 1] + nxt[:, 1])),
        ]
    length = np.linalg.norm(out, axis=1, keepdims=True)
    return np.where(length > 1e-12, out / np.where(length > 1e-12, length, 1.0), _FALLBACK)


def author_normals(
    mesh: Any,
    points: Sequence[Sequence[float]] | np.ndarray,
    counts: Sequence[int] | np.ndarray,
    indices: Sequence[int] | np.ndarray,
    *,
    interpolation: str = "vertex",
) -> None:
    """Author `normals` on a `UsdGeom.Mesh`: per vertex (area-weighted mean of the faces around it) or, with
    `interpolation="uniform"`, per face."""
    from pxr import Vt

    pts = np.asarray(points, dtype=np.float64).reshape(-1, 3)
    cnt = np.asarray(counts, dtype=np.int64)
    idx = np.asarray(indices, dtype=np.int64)
    face = _face_normals(pts, cnt, idx)
    if interpolation == "uniform":
        values = face
    elif interpolation == "vertex":
        values = np.zeros((len(pts), 3))
        np.add.at(values, idx, np.repeat(face, cnt, axis=0))
        length = np.linalg.norm(values, axis=1, keepdims=True)
        values = np.where(length > 1e-12, values / np.where(length > 1e-12, length, 1.0), _FALLBACK)
    else:
        raise ValueError(f"interpolation must be 'vertex' or 'uniform', got {interpolation!r}")
    mesh.CreateNormalsAttr(Vt.Vec3fArray.FromNumpy(values.astype(np.float32)))
    mesh.SetNormalsInterpolation(interpolation)
