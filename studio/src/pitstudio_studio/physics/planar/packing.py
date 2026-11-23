"""Initial states of the planar reference rollouts (spec 011, FR-011-03): a settled-column lattice and a funnel hopper.

Pure NumPy. Every state is a monolayer: positions are (x, 0, z) metres, radii are D/2 U(1 - poly, 1 + poly). The hopper
is
made of FROZEN spheres (radius D/2, centre spacing 0.8 D) that the engine holds in place with a kernel inside the CUDA
graph; they are recorded as the static boundary particles of the rollout.
A funnel (plates rising from the orifice edges at FUNNEL_DEG
from the horizontal, then vertical side walls) drains completely, so a finished feed leaves almost no grain on the
plates.
"""

from __future__ import annotations

import dataclasses
import math
from collections.abc import Mapping

import numpy as np

from . import space
from .space import HOPPER_W_D, LOOSE_PITCH, D

FILL_PITCH = 1.35  # loose lattice pitch of the hopper fill, D
WALL_PITCH = 0.8  # centre spacing of the frozen wall spheres, D
WALL_CLEARANCE = 1.15  # minimum centre distance between a grain and a wall sphere, D
TOP_MARGIN_D = 8.0  # side walls reach this far above the highest grain, D


def radii(rng: np.random.Generator, n: int, poly: float = space.POLY) -> np.ndarray:
    return D / 2.0 * rng.uniform(1.0 - poly, 1.0 + poly, n)


def column_state(
    p: Mapping[str, float], rng: np.random.Generator, poly: float = space.POLY
) -> tuple[np.ndarray, np.ndarray]:
    """Loose lattice of a column of width L0 (30 % more grains than the design; the settled column is trimmed to a
    L0)."""
    width = p["L0_D"]
    n = int(1.3 * p["n"])
    nx = max(2, int(width / LOOSE_PITCH))
    px = width / nx * D
    layers = math.ceil(n / nx)
    pts = [
        (
            (i + 0.5) * px + rng.uniform(-0.08, 0.08) * D,
            0.0,
            (0.7 + j * LOOSE_PITCH) * D + rng.uniform(-0.08, 0.08) * D,
        )
        for j in range(layers)
        for i in range(nx)
    ]
    pts = np.array(pts)
    pts[:, 0] = np.clip(pts[:, 0], 0.65 * D, width * D - 0.65 * D)
    keep = np.sort(rng.permutation(len(pts))[:n]) if len(pts) > n else np.arange(len(pts))
    return pts[keep], radii(rng, len(keep), poly)


@dataclasses.dataclass(frozen=True)
class Hopper:
    """Frozen walls first, then the grains. `x_center` and `z_orifice` are in the frame of the state (metres)."""

    positions: np.ndarray  # (n_walls + n_grains, 3)
    radii: np.ndarray
    frozen: np.ndarray  # int32, 1 for a wall sphere
    n_grains: int
    n_walls: int
    x_center: float
    z_orifice: float  # height of the orifice plane (the lower edge of the funnel plates)
    top_z: float  # highest point of the hopper walls

    @property
    def grain_slice(self) -> slice:
        return slice(self.n_walls, self.n_walls + self.n_grains)


def _line(p0: tuple[float, float], p1: tuple[float, float]) -> list[tuple[float, float, float]]:
    length = math.hypot(p1[0] - p0[0], p1[1] - p0[1])
    n = max(1, round(length / (WALL_PITCH * D)))
    return [(p0[0] + (p1[0] - p0[0]) * t, 0.0, p0[1] + (p1[1] - p0[1]) * t) for t in np.arange(n) / n]


def funnel_walls(x_center: float, z_orifice: float, w_o: float, z_top: float) -> np.ndarray:
    """Frozen sphere centres of the funnel: two plates from the orifice edges to the side walls, then the side walls."""
    half = HOPPER_W_D * D / 2.0 + 0.5 * D
    z0 = z_orifice - 0.5 * D
    tan = math.tan(math.radians(space.FUNNEL_DEG))
    run = half - w_o / 2.0
    z_corner = z0 + run * tan
    pts: list[tuple[float, float, float]] = []
    for sgn in (-1.0, 1.0):
        pts += _line((x_center + sgn * w_o / 2.0, z0), (x_center + sgn * half, z_corner))
        pts += _line((x_center + sgn * half, z_corner), (x_center + sgn * half, z_top))
    pts += [(x_center - half, 0.0, z_top), (x_center + half, 0.0, z_top)]
    return np.array(pts)


def hopper_state(
    p: Mapping[str, float], rng: np.random.Generator, *, x_center: float, z_orifice: float, poly: float = space.POLY
) -> Hopper:
    """N grains on a loose lattice inside a funnel whose orifice (width w_o_D) is at `z_orifice` (metres).

    The lattice is cut by the funnel (points closer than WALL_CLEARANCE to a wall sphere are dropped) and the lowest
    `n` points are kept, so the fill is a solid block resting on the closed funnel with a free top; the side walls end
    TOP_MARGIN_D above the highest grain.
    """
    n, w_o = int(p["n"]), p["w_o_D"] * D
    half = HOPPER_W_D * D / 2.0
    tan = math.tan(math.radians(space.FUNNEL_DEG))
    z_corner = z_orifice - 0.5 * D + (half + 0.5 * D - w_o / 2.0) * tan
    cols = int((HOPPER_W_D - 1.2) / FILL_PITCH) - 1  # one pitch of slack for the half-pitch shift of odd rows
    rows = math.ceil(n / cols) + math.ceil((z_corner - z_orifice) / (FILL_PITCH * D)) + 2
    grid = []
    for j in range(rows):
        for i in range(cols):
            x = x_center + (i - (cols - 1) / 2.0 - 0.25 + (0.5 if j % 2 else 0.0)) * FILL_PITCH * D
            x += rng.uniform(-0.08, 0.08) * D
            x = float(np.clip(x, x_center - half + 0.65 * D, x_center + half - 0.65 * D))
            grid.append((x, 0.0, z_orifice + (0.7 + j * FILL_PITCH) * D + rng.uniform(-0.08, 0.08) * D))
    grid = np.array(grid)
    walls_probe = funnel_walls(x_center, z_orifice, w_o, z_corner + (rows + 2) * FILL_PITCH * D)
    d_wall = np.hypot(grid[:, None, 0] - walls_probe[None, :, 0], grid[:, None, 2] - walls_probe[None, :, 2]).min(
        axis=1
    )
    plate = z_orifice - 0.5 * D + np.maximum(0.0, np.abs(grid[:, 0] - x_center) - w_o / 2.0) * tan
    valid = grid[(d_wall >= WALL_CLEARANCE * D) & (grid[:, 2] > plate)]  # inside the funnel, clear of its walls
    valid = valid[np.lexsort((valid[:, 0], valid[:, 2]))]
    if len(valid) < n:
        raise ValueError(f"the funnel lattice holds {len(valid)} grains, {n} requested")
    grains = valid[:n]
    top = float(grains[:, 2].max()) + TOP_MARGIN_D * D
    walls = funnel_walls(x_center, z_orifice, w_o, top)
    pos = np.vstack([walls, grains])
    rad = np.concatenate([np.full(len(walls), 0.5 * D), radii(rng, n, poly)])
    frozen = np.concatenate([np.ones(len(walls), dtype=np.int32), np.zeros(n, dtype=np.int32)])
    return Hopper(pos, rad, frozen, n, len(walls), x_center, z_orifice, top)


def dump_solid(lx0: float, crest: float, crest_z: float) -> np.ndarray:
    """Boundary points (x, z) of the solid under a dump platform: its top row and its crest face.

    The generator holds the grains with two planes (the platform top z = crest_z for x < crest, the crest face x = crest
    below it). A plane touches a grain of radius D/2 at a centre distance D/2, so the points sit D/2 inside the solid:
    a grain resting on the row is at the contact distance D of a boundary sphere, as on a wall sphere of the funnel.
    The row and the face are closed at the WALL_PITCH of the funnel, from the left wall of the box to the crest and from
    the crest foot to the platform.
    """
    z_top, x_face = crest_z - 0.5 * D, crest - 0.5 * D
    n_top = max(1, math.ceil((x_face - lx0) / (WALL_PITCH * D)))
    top = [(lx0 + (x_face - lx0) * i / n_top, z_top) for i in range(n_top + 1)]
    n_face = max(1, math.ceil(z_top / (WALL_PITCH * D)))
    face = [(x_face, z_top * i / n_face) for i in range(n_face)]  # the corner is the last point of the top row
    return np.array(top + face)
