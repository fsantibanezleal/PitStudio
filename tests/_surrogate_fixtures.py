"""Small deterministic fixtures shared by T-011-095 (fixture propagation) and T-011-096 (partial evaluation sets).

Hand-checkable constructions, the same ones the dedicated tests of T-011-014 (tiny rollouts for training),
    T-011-015 (analytic piles with a known
repose angle and run-out, see its docstring) and T-011-053 (fields with a known relative L2) document; no value
    here comes from the code under test.
"""

from __future__ import annotations

import math

import numpy as np

D = 0.004
DT = 0.01
L0 = 0.2
FRAMES = 4
REF_THETA = (30.0, 33.0, 36.0)
REF_TAIL = (1.00, 1.10, 1.20)


# ---- tiny rollouts for training (constant acceleration per rollout)


def tiny_rollout(seed: int, accel: tuple[float, float], n: int = 8, frames: int = 9, dt: float = 0.01) -> dict:
    rng = np.random.default_rng(seed)
    x0 = rng.uniform(0.2, 0.8, (n, 2))
    v0 = rng.normal(0.0, 0.05, (n, 2))
    t = np.arange(frames)[:, None, None] * dt
    pos = (x0[None] + v0[None] * t + 0.5 * np.array(accel)[None, None, :] * t**2).astype(np.float32)
    return {
        "positions": pos,
        "particle_types": np.zeros(n, dtype=np.int64),
        "bounds": np.array([-5, -5, 5, 5], dtype=np.float32),
        "d": 0.04,
        "dt": dt,
    }


class Splits:
    def __init__(self, train, val):
        self._data = {"train": train, "val": val}

    def rollouts(self, name: str):
        if name == "test":
            raise AssertionError("the test split was read during training")
        return self._data[name]


TRAIN_CONFIG = {
    "noise_scales": [0.0],
    "epochs": 2,
    "batch_size": 2,
    "lr": 3e-3,
    "latent": 8,
    "steps": 1,
    "connectivity_radius": 0.1,
}


def tiny_splits() -> Splits:
    train = [tiny_rollout(i, a) for i, a in enumerate(((1.0, -9.8), (2.0, -9.0), (-1.0, -10.5)))]
    val = [tiny_rollout(100 + i, a) for i, a in enumerate(((1.5, -9.4), (0.0, -9.9)))]
    return Splits(train, val)


# ---- analytic piles for the held-out evaluation


def flank(theta_deg: float, x0: float, sign: int, h: float = 40 * D, n: int = 700) -> np.ndarray:
    th = math.radians(theta_deg)
    step = (h - D) / math.sin(th) / n
    xs = x0 + sign * (np.arange(n) + 0.37) * step * math.cos(th)
    ys = h - math.tan(th) * np.abs(xs - x0) - D / 2
    return np.column_stack([xs, ys])


def tail(x: float, n: int = 60) -> np.ndarray:
    return np.column_stack([np.full(n, x), np.full(n, D / 2)])


def collapse_cloud(theta: float, x_far: float) -> np.ndarray:
    return np.vstack([flank(theta, 0.0, +1), tail(x_far)])


def collapse_geometry(gid: str) -> dict:
    refs = []
    for i in range(3):
        final = collapse_cloud(REF_THETA[i], REF_TAIL[i]).astype(np.float32)
        frames = [final + np.float32(0.01)] + [final.copy() for _ in range(FRAMES - 1)]
        refs.append(
            {"seed": 1 + i, "positions": np.stack(frames), "particle_types": np.zeros(final.shape[0], dtype=np.int64)}
        )
    return {
        "geometry_id": gid,
        "family": "column-collapse",
        "geometry": {"column_width_m": L0},
        "d": D,
        "dt": DT,
        "bounds": [-2.0, 0.0, 3.0, 1.0],
        "references": refs,
    }


class Result:
    def __init__(self, positions, status="ok", diverged_at_step=None, overflow_counts=None):
        self.positions = positions
        self.status = status
        self.diverged_at_step = diverged_at_step
        self.overflow_counts = overflow_counts if overflow_counts is not None else [0] * (len(positions) - 1)


def identity_surrogate(geometries):
    lookup = {(g["geometry_id"], r["seed"]): r["positions"][-1] for g in geometries for r in g["references"]}

    def run(state, n_steps):
        return Result(np.stack([lookup[(state["geometry_id"], state["seed"])]] * (n_steps + 1)))

    return run


# ---- fields for the FNO evaluation


def tailings_set(n_scenarios: int, offset: float = 0.01) -> tuple[np.ndarray, np.ndarray]:
    truth = np.ones((n_scenarios, 9, 4, 4))
    pred = truth.copy()
    pred[:, 8] += offset  # relative error of h_max exactly `offset`
    return pred, truth


TAILINGS_FIELDS = [f"depth_t{k}" for k in range(1, 9)] + ["depth_max"]
