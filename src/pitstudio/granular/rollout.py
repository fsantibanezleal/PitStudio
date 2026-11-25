"""Rollout loop of the GNS with divergence stop, conservation and overflow accounting (FR-011-12, FR-011-13, P-011-03).

The step is passed in as a callable so the loop serves PyTorch, ONNX Runtime and test fakes alike. State 0 is the
initial
state; step s = 1 ... n builds the radius graph of state s - 1, calls the step and obtains state s. A non-finite state
s, or a
particle of state s farther than R beyond the bounds, stops the rollout at step s: the bad state is not stored,
`diverged_at_step` is s and the label is "diverged at step s".
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, field

import numpy as np

from pitstudio.granular.errors import InvalidGraphError, RolloutError
from pitstudio.granular.graph import K_MAX, build_radius_graph, validate_positions

N_HISTORY = 5  # the last C = 5 velocities (FR-011-01)

StepFn = Callable[
    [np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray], tuple[np.ndarray, np.ndarray]
]


@dataclass
class RolloutResult:
    positions: np.ndarray  # float32 [S + 1, N, 2]: the states 0 ... S that were obtained
    steps_completed: int
    status: str  # "ok" | "diverged"
    diverged_at_step: int | None
    label: str
    overflow_counts: list[int] = field(default_factory=list)  # one per graph built (state 0, 1, ...)
    neighbour_overflow: bool = False
    particle_types: np.ndarray = field(default_factory=lambda: np.zeros(0, dtype=np.int64))


def _check_initial(positions: np.ndarray, velocities: np.ndarray, particle_type: np.ndarray) -> int:
    pos = validate_positions(positions)
    n = pos.shape[0]
    if velocities.shape != (n, N_HISTORY, 2):
        raise InvalidGraphError(f"velocities must have shape [{n}, {N_HISTORY}, 2], got {list(velocities.shape)}")
    if particle_type.shape != (n,):
        raise InvalidGraphError(f"particle_type must have shape [{n}], got {list(particle_type.shape)}")
    if not np.isfinite(velocities).all():
        raise InvalidGraphError("velocities contain a non-finite value")
    return n


def run_rollout(
    step: StepFn,
    positions: np.ndarray,
    velocities: np.ndarray,
    particle_type: np.ndarray,
    *,
    bounds: Sequence[float],
    radius: float,
    n_steps: int,
) -> RolloutResult:
    """Roll `step` out for `n_steps` from the given state; see the module docstring for the conventions."""
    pos = np.asarray(positions, dtype=np.float32)
    vel = np.asarray(velocities, dtype=np.float32)
    types = np.asarray(particle_type, dtype=np.int64)
    n = _check_initial(pos, vel, types)
    if n_steps < 0:
        raise ValueError(f"n_steps must not be negative, got {n_steps}")
    bounds_arr = np.asarray(bounds, dtype=np.float32)
    if bounds_arr.shape != (4,) or not np.isfinite(bounds_arr).all():
        raise InvalidGraphError("bounds must be four finite numbers (x_min, y_min, x_max, y_max)")
    x_min, y_min, x_max, y_max = (float(b) for b in bounds_arr)

    states = [pos]
    overflow_counts: list[int] = []
    status, diverged_at = "ok", None
    for s in range(1, n_steps + 1):
        graph = build_radius_graph(pos, radius, K_MAX)
        overflow_counts.append(graph.overflow_count)
        new_pos, new_vel = step(pos, vel, types, bounds_arr, graph.neighbour_index, graph.neighbour_mask)
        new_pos = np.asarray(new_pos)
        new_vel = np.asarray(new_vel)
        if new_pos.shape != (n, 2) or new_vel.shape != (n, N_HISTORY, 2):
            raise RolloutError(
                "rollout-step-invalid",
                f"step {s} returned shapes {list(new_pos.shape)} and {list(new_vel.shape)}; "
                f"expected [{n}, 2] and [{n}, {N_HISTORY}, 2]",
            )
        new_pos = new_pos.astype(np.float32, copy=False)
        new_vel = new_vel.astype(np.float32, copy=False)
        if not (np.isfinite(new_pos).all() and np.isfinite(new_vel).all()) or _outside(
            new_pos, x_min, y_min, x_max, y_max, float(radius)
        ):
            status, diverged_at = "diverged", s
            break
        pos, vel = new_pos, new_vel
        states.append(pos)
    return RolloutResult(
        positions=np.stack(states, axis=0),
        steps_completed=len(states) - 1,
        status=status,
        diverged_at_step=diverged_at,
        label="" if diverged_at is None else f"diverged at step {diverged_at}",
        overflow_counts=overflow_counts,
        neighbour_overflow=any(c > 0 for c in overflow_counts),
        particle_types=types,
    )


def _outside(pos: np.ndarray, x_min: float, y_min: float, x_max: float, y_max: float, radius: float) -> bool:
    p = pos.astype(np.float64)
    return bool(
        (p[:, 0] < x_min - radius).any()
        or (p[:, 0] > x_max + radius).any()
        or (p[:, 1] < y_min - radius).any()
        or (p[:, 1] > y_max + radius).any()
    )
