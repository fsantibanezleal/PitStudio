"""T-011-017 - FR-011-12, FR-011-13, P-011-03: rollout loop, divergence stop, conservation, overflow flag.

Oracles (independent of the code under test; plan 011 test strategy FR-011-12 / FR-011-13):
- constructed states: a step function that drifts every particle by a constant velocity gives the closed form
  x_k = x_0 + k v dt (hand calculation) at every step; a step that returns NaN at a chosen step; a particle placed
      beyond the
  domain bounds by R + 1e-6, by exactly R and by 0.9 R;
- conservation (P-011-03): the particle count and the type of every particle are those of the initial state at
    every step;
- overflow (FR-011-13): a cluster of 41 particles all within R of each other has 40 neighbours each (hand count),
    so the step
  receives exactly 32 listed neighbours per particle and the overflow count of every step is 41.

Rollout convention fixed here: the initial state is state 0; step s = 1 ... n builds the radius graph of state s -
    1, calls the
step and obtains state s. A non-finite state s, or a particle of state s farther than R beyond the bounds (strictly
    more than
R), stops the rollout at step s: the bad state is not stored, `diverged_at_step` is s and the label is "diverged at
    step s".

Expected public API (module `pitstudio.granular.rollout`, under `src/pitstudio/granular/`; errors in
    `pitstudio.granular.errors`):

    run_rollout(step, positions, velocities, particle_type, *, bounds, radius, n_steps) -> RolloutResult
        step(positions [N, 2] f32, velocities [N, 5, 2] f32, particle_type [N] i64, bounds [4] f32,
             neighbour_index [N, 32] i64, neighbour_mask [N, 32] bool) -> (positions_next [N, 2], velocities_next
                 [N, 5, 2])
        bounds = (x_min, y_min, x_max, y_max).
        RolloutResult attributes: positions (float array [S + 1, N, 2], the states 0 ... S that were obtained),
            steps_completed
        (int S), status ("ok" | "diverged"), diverged_at_step (int | None), label ("" or "diverged at step s"),
        overflow_counts (list of int, one per graph built), neighbour_overflow (bool, any overflow), particle_types
            ([N]).
        Raises `pitstudio.granular.errors.RolloutError` (error_class "rollout-step-invalid") when the step returns
            arrays whose
        particle count differs from N or whose shapes are not [N, 2] and [N, 5, 2]; raises InvalidGraphError
            (before any step)
        for an invalid initial state (N = 0, wrong shapes, non-finite values) and ValueError for n_steps < 0.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
import yaml
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))

from pitstudio.granular.errors import InvalidGraphError, RolloutError  # noqa: E402
from pitstudio.granular.rollout import run_rollout  # noqa: E402

EXAMPLES = yaml.safe_load((ROOT / "specs" / "000-foundation" / "thresholds.yaml").read_text(encoding="utf-8"))[
    "property_tests"
]["ci_examples_per_test"]
DT = 0.01
R = 0.5
BOUNDS = (0.0, 0.0, 10.0, 10.0)


def state(n: int, seed: int = 0):
    rng = np.random.default_rng(seed)
    pos = rng.uniform(2.0, 8.0, (n, 2)).astype(np.float32)
    vel = np.zeros((n, 5, 2), dtype=np.float32)
    vel[:, -1, :] = rng.uniform(-0.5, 0.5, (n, 2)).astype(np.float32)
    return pos, vel, np.zeros(n, dtype=np.int64)


def drift_step(pos, vel, types, bounds, index, mask):
    v = vel[:, -1, :]
    new_vel = np.concatenate([vel[:, 1:, :], v[:, None, :]], axis=1)
    return (pos + v * DT).astype(np.float32), new_vel


# ------------------------------------------------------------------ closed form and conservation


@pytest.mark.req("P-011-03")
def test_a_constant_drift_rollout_follows_the_closed_form_and_conserves_count_and_types() -> None:
    pos, vel, types = state(30, 1)
    types[::3] = 1
    res = run_rollout(drift_step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=25)
    assert res.status == "ok"
    assert res.label == ""
    assert res.diverged_at_step is None
    assert res.steps_completed == 25
    assert res.positions.shape == (26, 30, 2)
    for k in (0, 1, 7, 25):
        assert np.allclose(res.positions[k], pos + k * vel[:, -1, :] * DT, atol=1e-5)  # x_k = x_0 + k v dt
    assert np.array_equal(res.particle_types, types)
    assert len(res.overflow_counts) == 25


@pytest.mark.req("P-011-03")
@settings(max_examples=EXAMPLES, deadline=None)
@given(n=st.integers(1, 80), steps=st.integers(0, 40), seed=st.integers(0, 2**32 - 1))
def test_property_count_and_types_are_the_same_at_every_step(n: int, steps: int, seed: int) -> None:
    pos, vel, types = state(n, seed)
    types = np.random.default_rng(seed).integers(0, 3, n).astype(np.int64)
    seen: list[tuple[int, bytes]] = []

    def spy(p, v, t, b, idx, m):
        seen.append((p.shape[0], t.tobytes()))
        assert idx.shape == (n, 32)
        assert m.shape == (n, 32)
        return drift_step(p, v, t, b, idx, m)

    res = run_rollout(spy, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=steps)
    assert res.positions.shape[1] == n
    assert all(count == n and raw == types.tobytes() for count, raw in seen)
    assert np.array_equal(res.particle_types, types)
    assert res.positions.shape[0] == res.steps_completed + 1


@pytest.mark.req("FR-011-12")
def test_zero_steps_returns_only_the_initial_state() -> None:
    pos, vel, types = state(5)
    res = run_rollout(drift_step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=0)
    assert res.positions.shape == (1, 5, 2)
    assert np.array_equal(res.positions[0], pos)
    assert res.status == "ok"


# ------------------------------------------------------------------ FR-011-12 divergence


@pytest.mark.req("FR-011-12")
@pytest.mark.parametrize("bad_at", [1, 3, 7])
@pytest.mark.parametrize("poison", [np.nan, np.inf, -np.inf])
def test_a_non_finite_state_stops_the_rollout_at_that_step(bad_at: int, poison: float) -> None:
    pos, vel, types = state(10)
    calls = {"n": 0}

    def step(p, v, t, b, idx, m):
        calls["n"] += 1
        new_p, new_v = drift_step(p, v, t, b, idx, m)
        if calls["n"] == bad_at:
            new_p = new_p.copy()
            new_p[4, 1] = poison
        return new_p, new_v

    res = run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=20)
    assert res.status == "diverged"
    assert res.diverged_at_step == bad_at
    assert res.label == f"diverged at step {bad_at}"
    assert res.positions.shape[0] == bad_at  # states 0 ... bad_at - 1; the bad state is not stored
    assert calls["n"] == bad_at  # the loop stopped, no further step was called
    assert np.isfinite(res.positions).all()


@pytest.mark.req("FR-011-12")
def test_a_non_finite_velocity_history_also_stops_the_rollout() -> None:
    pos, vel, types = state(6)

    def step(p, v, t, b, idx, m):
        new_p, new_v = drift_step(p, v, t, b, idx, m)
        new_v = new_v.copy()
        new_v[2, -1, 0] = np.nan
        return new_p, new_v

    res = run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=5)
    assert res.status == "diverged"
    assert res.diverged_at_step == 1


@pytest.mark.req("FR-011-12")
@pytest.mark.parametrize(
    ("excess", "diverges"),
    [(0.9 * R, False), (R, False), (R + 1e-4, True), (3 * R, True)],
    ids=["0.9R", "R", "R+eps", "3R"],
)
def test_a_particle_more_than_r_beyond_the_bounds_stops_the_rollout(excess: float, diverges: bool) -> None:
    pos, vel, types = state(8)
    target = np.float32(BOUNDS[2] + excess)

    def step(p, v, t, b, idx, m):
        new_p, new_v = drift_step(p, v, t, b, idx, m)
        new_p = new_p.copy()
        new_p[0, 0] = target
        return new_p, new_v

    res = run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=4)
    if diverges:
        assert res.status == "diverged"
        assert res.diverged_at_step == 1
        assert res.positions.shape[0] == 1
    else:
        assert res.status == "ok"
        assert res.steps_completed == 4


@pytest.mark.req("FR-011-12")
@pytest.mark.parametrize("side", ["x_min", "y_min", "x_max", "y_max"])
def test_every_side_of_the_domain_is_guarded(side: str) -> None:
    pos, vel, types = state(5)
    new = {
        "x_min": (0, BOUNDS[0] - 2 * R),
        "y_min": (1, BOUNDS[1] - 2 * R),
        "x_max": (0, BOUNDS[2] + 2 * R),
        "y_max": (1, BOUNDS[3] + 2 * R),
    }[side]

    def step(p, v, t, b, idx, m):
        new_p, new_v = drift_step(p, v, t, b, idx, m)
        new_p = new_p.copy()
        new_p[2, new[0]] = np.float32(new[1])
        return new_p, new_v

    res = run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=3)
    assert res.status == "diverged"
    assert res.label == "diverged at step 1"


@pytest.mark.req("FR-011-12")
def test_a_diverged_rollout_is_not_silently_completed_to_the_requested_length() -> None:
    pos, vel, types = state(5)

    def step(p, v, t, b, idx, m):
        return np.full_like(p, np.nan), v

    res = run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=100)
    assert res.steps_completed == 0
    assert res.positions.shape == (1, 5, 2)


# ------------------------------------------------------------------ FR-011-13 overflow


@pytest.mark.req("FR-011-13")
def test_neighbour_overflow_is_counted_flagged_and_the_step_receives_the_32_nearest() -> None:
    rng = np.random.default_rng(7)
    pos = (rng.uniform(-0.5, 0.5, (41, 2)) + 5.0).astype(
        np.float32
    )  # 41 particles, all within 1.5 < R = 2.5 of each other
    vel = np.zeros((41, 5, 2), dtype=np.float32)
    types = np.zeros(41, dtype=np.int64)
    masks: list[np.ndarray] = []

    def step(p, v, t, b, idx, m):
        masks.append(m.copy())
        return p, v

    res = run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=2.5, n_steps=3)
    assert res.status == "ok"
    assert res.neighbour_overflow is True
    assert res.overflow_counts == [41, 41, 41]
    assert all(m.sum(axis=1).tolist() == [32] * 41 for m in masks)  # 40 neighbours each, 32 kept


@pytest.mark.req("FR-011-13")
def test_no_overflow_means_no_flag() -> None:
    pos, vel, types = state(20, 3)
    res = run_rollout(drift_step, pos, vel, types, bounds=BOUNDS, radius=0.2, n_steps=5)
    assert res.neighbour_overflow is False
    assert res.overflow_counts == [0] * 5


@pytest.mark.req("FR-011-13")
def test_an_overflow_that_appears_mid_rollout_is_flagged() -> None:
    n = 41
    pos = np.column_stack([np.linspace(1.0, 9.0, n), np.full(n, 5.0)]).astype(
        np.float32
    )  # spread out, no overflow at step 0
    vel = np.zeros((n, 5, 2), dtype=np.float32)
    types = np.zeros(n, dtype=np.int64)
    calls = {"n": 0}

    def collapse(p, v, t, b, idx, m):
        calls["n"] += 1
        if calls["n"] == 2:
            return (np.full_like(p, 5.0) + np.random.default_rng(0).uniform(-0.2, 0.2, p.shape)).astype(np.float32), v
        return p, v

    res = run_rollout(collapse, pos, vel, types, bounds=BOUNDS, radius=2.5, n_steps=4)
    assert res.overflow_counts[0] == 0
    assert res.overflow_counts[2] == 41  # the graph of state 2 (after the collapse) overflows
    assert res.neighbour_overflow is True


# ------------------------------------------------------------------ hostile inputs and steps


@pytest.mark.req("FR-011-12")
@pytest.mark.parametrize("bad_n", [0, 1, 3])
def test_a_step_that_changes_the_particle_count_is_refused(bad_n: int) -> None:
    pos, vel, types = state(5)

    def step(p, v, t, b, idx, m):
        return p[:bad_n], v[:bad_n]

    with pytest.raises(RolloutError) as info:
        run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=2)
    assert info.value.error_class == "rollout-step-invalid"


@pytest.mark.req("FR-011-12")
def test_a_step_that_returns_the_wrong_shape_is_refused() -> None:
    pos, vel, types = state(5)

    def step(p, v, t, b, idx, m):
        return np.zeros((5, 3), dtype=np.float32), v

    with pytest.raises(RolloutError):
        run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=2)


@pytest.mark.req("FR-011-15")
@pytest.mark.parametrize(
    "case",
    ["n0", "wrong-velocity-shape", "wrong-type-length", "nan-position", "inf-velocity", "negative-steps"],
)
def test_an_invalid_initial_state_is_refused_before_any_step(case: str) -> None:
    pos, vel, types = state(6)
    steps = 3
    if case == "n0":
        pos, vel, types = pos[:0], vel[:0], types[:0]
    elif case == "wrong-velocity-shape":
        vel = vel[:, :4, :]
    elif case == "wrong-type-length":
        types = types[:5]
    elif case == "nan-position":
        pos[2, 0] = np.nan
    elif case == "inf-velocity":
        vel[1, 0, 1] = np.inf
    elif case == "negative-steps":
        steps = -1
    called = []

    def step(*args):
        called.append(1)
        return drift_step(*args)

    expected = ValueError if case == "negative-steps" else InvalidGraphError
    with pytest.raises(expected):
        run_rollout(step, pos, vel, types, bounds=BOUNDS, radius=R, n_steps=steps)
    assert called == []
