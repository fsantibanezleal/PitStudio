"""T-011-034 - FR-011-17, FR-011-19, FR-011-21, P-011-11: gradient (tape) arm; tape against the sliding-sphere
    closed form.

The CUDA smoke test of this task lives in tests/gpu/test_t_011_034_tape_cuda.py (marked `gpu`, not part of this file).

Oracles (independent of the code under test):
- closed form of a sphere launched sliding on a horizontal plate (plan 011 test strategy FR-011-17 / FR-011-19;
  Coulomb friction decelerates the centre of mass at mu g while it slides, spec 005 FR-005-05): for T < 2 v0 / (7 mu g)
      x(T) = v0 T - (1/2) mu g T^2,      dx/dmu = -(1/2) g T^2     (independent of v0 and of the sphere).
  Numbers by hand, g = 9.81, v0 = 1.0 m/s: mu = 0.5, T = 0.04 s (< 0.0582 s): x = 0.04 - 0.0039240 = 0.0360760 m,
  dx/dmu = -0.0078480; mu = 0.3, T = 0.05 s (< 0.0970 s): x = 0.05 - 0.00367875 = 0.04632125 m, dx/dmu = -0.0122625;
  tolerance 2 % on the gradient and 1 % on the displacement (plan 011);
- the settling phase is not recorded (FR-011-19): with 1,000 settling steps (0.02 s) and 1,000 recorded steps the
    state at
  the start of the window does not depend on mu in the adjoint, so dx/dmu = -(1/2) g (0.02)^2 = -0.001962 while the
  displacement is the same as for the full 0.04 s run;
- Adam as published (Kingma and Ba, ICLR 2015, Algorithm 1; beta1 = 0.9, beta2 = 0.999, eps = 1e-8) applied in this file
  to the exact gradient dL/dmu = 2 (theta - theta*) b of the noise-free fake (tests/_calib_fake.py), compared with
      the arm's
  iterates; the budget arithmetic of FR-011-21 (one forward pass with its adjoint = 3 forward-equivalent simulations per
  heap, S = 2 heaps per iterate = 6 per iteration, so 60 allow 10 iterations);
- determinism (P-011-11): two tape gradients from identical inputs are bitwise identical (exact equality).

Expected public API (module `pitstudio_studio.physics.calibration.tape`, package under `studio/src/`; error class
`pitstudio.calibration.errors.InvalidCalibrationError`):

    TapeScene(positions, velocities, radii, density, youngs_modulus, poisson_ratio, restitution, rolling_friction=0.0)
        positions, velocities: float arrays [N, 3] (m, m/s); radii [N] (m); material scalars in SI units. A rigid plane
        z = 0 with the particle material is the floor; gravity is (0, 0, -9.81).
    rollout_gradient(scene, mu, *, settle_steps=0, record_steps, dt, objective="mean_x", device="cpu") -> TapeRollout
        Runs settle_steps without recording, then record_steps under `wp.Tape` with deterministic atomic accumulation,
        per-contact force buffers and fixed iteration counts; differentiates `objective` (the mean over particles of the
        final x, or of the final z for "mean_z") with respect to the sliding friction mu of the DEM contact law.
        TapeRollout attributes: objective (float), gradient (float, d objective / d mu), final_positions [N, 3],
        final_velocities [N, 3], deterministic (bool, True).
        Raises InvalidCalibrationError for mu outside [0.05, 2], record_steps < 1, dt <= 0 or non-finite, an empty
            scene or
        a non-finite entry before any simulation.
    run_gradient_arm(simulator, *, theta_star, packing_seeds, mu0=0.55, bounds=(0.1, 1.0), budget=60, adam_lr=0.02,
                     loss_tolerance_deg=0.1) -> ArmResult
        simulator: the protocol of tests/_calib_fake.py; each iterate evaluates theta and d theta / d mu with
        `theta_and_grad(mu, seed)` on every packing seed, L = mean (theta - theta*)^2, dL/dmu = mean 2 (theta -
            theta*) dtheta/dmu,
        then an Adam step (defaults above) clipped to `bounds`; stops when L <= loss_tolerance_deg^2 or when another
        iteration would exceed `budget` forward-equivalent simulations (3 per heap). The budget is never exceeded.
        ArmResult attributes: mu_hat (the evaluated iterate of smallest L), best_loss, simulations, wall_time_s,
        stop_reason in {"loss-tolerance", "budget"}, path (the evaluated iterates, path[0] = mu0), gradients (dL/dmu at
        each evaluated iterate), evaluations (list of (mu, loss)).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))
sys.path.insert(0, str(ROOT / "tests"))

from _calib_fake import FakeDem  # noqa: E402
from pitstudio_studio.physics.calibration import tape  # noqa: E402

from pitstudio.calibration.errors import InvalidCalibrationError  # noqa: E402

G = 9.81
R = 5.0e-3
E = 50.0e6
NU = 0.25
RHO = 2650.0
MASS = RHO * 4.0 / 3.0 * math.pi * R**3
E_STAR_WALL = E / (2.0 * (1.0 - NU**2))  # 1/E* = 2 (1 - nu^2) / E, sphere against a wall of the same material
DT = 2.0e-5  # s, below the Rayleigh limit of this material (spec 005 FR-005-08 worked example)
SEEDS = [11, 12]


def static_overlap() -> float:
    return (MASS * G / (4.0 / 3.0 * E_STAR_WALL * math.sqrt(R))) ** (2.0 / 3.0)


def sliding_scene(v0: float) -> tape.TapeScene:
    z0 = R - static_overlap()  # start in static equilibrium so no bounce disturbs the friction force
    return tape.TapeScene(
        positions=np.array([[0.0, 0.0, z0]]),
        velocities=np.array([[v0, 0.0, 0.0]]),
        radii=np.array([R]),
        density=RHO,
        youngs_modulus=E,
        poisson_ratio=NU,
        restitution=0.5,
        rolling_friction=0.0,
    )


# ------------------------------------------------------------------ FR-011-17 / FR-011-19 closed form on the Warp
#   CPU device


@pytest.mark.req("FR-011-17")
@pytest.mark.req("FR-011-19")
@pytest.mark.parametrize(("mu", "t_end"), [(0.5, 0.04), (0.3, 0.05)])
def test_tape_gradient_of_a_sliding_sphere_matches_the_closed_form_within_two_percent(mu: float, t_end: float) -> None:
    steps = round(t_end / DT)
    out = tape.rollout_gradient(sliding_scene(1.0), mu, record_steps=steps, dt=DT, objective="mean_x", device="cpu")
    assert out.gradient == pytest.approx(-0.5 * G * t_end**2, rel=0.02)
    assert out.objective == pytest.approx(1.0 * t_end - 0.5 * mu * G * t_end**2, rel=0.01)


@pytest.mark.req("FR-011-19")
def test_the_gradient_does_not_depend_on_the_launch_speed() -> None:
    steps = round(0.04 / DT)
    slow = tape.rollout_gradient(sliding_scene(0.8), 0.5, record_steps=steps, dt=DT, device="cpu")
    fast = tape.rollout_gradient(sliding_scene(1.2), 0.5, record_steps=steps, dt=DT, device="cpu")
    assert slow.gradient == pytest.approx(-0.5 * G * 0.04**2, rel=0.02)
    assert fast.gradient == pytest.approx(-0.5 * G * 0.04**2, rel=0.02)


@pytest.mark.req("FR-011-19")
def test_settling_steps_are_not_recorded_so_only_the_window_contributes_to_the_gradient() -> None:
    out = tape.rollout_gradient(
        sliding_scene(1.0), 0.5, settle_steps=1000, record_steps=1000, dt=DT, objective="mean_x", device="cpu"
    )
    assert out.gradient == pytest.approx(-0.5 * G * 0.02**2, rel=0.02)  # -0.001962: the 0.02 s window only
    assert out.objective == pytest.approx(
        1.0 * 0.04 - 0.5 * 0.5 * G * 0.04**2, rel=0.01
    )  # same trajectory as 2,000 steps


@pytest.mark.req("P-011-11")
def test_two_tape_gradients_from_identical_inputs_are_bitwise_identical_on_a_small_heap() -> None:
    rng = np.random.default_rng(5)
    pos = np.array([[i * 0.0125, j * 0.0125, 0.006 + k * 0.0115] for i in range(2) for j in range(2) for k in range(2)])
    pos = pos + rng.uniform(-1e-4, 1e-4, pos.shape)
    scene = tape.TapeScene(
        positions=pos,
        velocities=np.zeros_like(pos) + np.array([0.3, 0.0, 0.0]),
        radii=np.full(8, R),
        density=RHO,
        youngs_modulus=E,
        poisson_ratio=NU,
        restitution=0.5,
        rolling_friction=0.1,
    )
    a = tape.rollout_gradient(scene, 0.5, settle_steps=100, record_steps=200, dt=DT, objective="mean_x", device="cpu")
    b = tape.rollout_gradient(scene, 0.5, settle_steps=100, record_steps=200, dt=DT, objective="mean_x", device="cpu")
    assert a.gradient == b.gradient
    assert a.objective == b.objective
    assert np.array_equal(a.final_positions, b.final_positions)
    assert np.array_equal(a.final_velocities, b.final_velocities)
    assert a.deterministic is True
    assert np.isfinite(a.gradient)


@pytest.mark.req("FR-011-19")
@pytest.mark.parametrize(
    "bad",
    [
        {"mu": 0.01},
        {"mu": 2.5},
        {"mu": float("nan")},
        {"record_steps": 0},
        {"dt": 0.0},
        {"dt": float("nan")},
    ],
    ids=["mu-low", "mu-high", "mu-nan", "no-record", "dt-zero", "dt-nan"],
)
def test_hostile_tape_arguments_raise_before_any_simulation(bad: dict) -> None:
    args = {"mu": 0.5, "record_steps": 10, "dt": DT}
    args.update(bad)
    mu = args.pop("mu")
    with pytest.raises(InvalidCalibrationError):
        tape.rollout_gradient(sliding_scene(1.0), mu, device="cpu", **args)


@pytest.mark.req("FR-011-19")
def test_an_empty_or_non_finite_scene_is_rejected() -> None:
    empty = tape.TapeScene(
        positions=np.zeros((0, 3)),
        velocities=np.zeros((0, 3)),
        radii=np.zeros(0),
        density=RHO,
        youngs_modulus=E,
        poisson_ratio=NU,
        restitution=0.5,
    )
    with pytest.raises(InvalidCalibrationError):
        tape.rollout_gradient(empty, 0.5, record_steps=10, dt=DT, device="cpu")
    bad = tape.TapeScene(
        positions=np.array([[float("nan"), 0.0, R]]),
        velocities=np.zeros((1, 3)),
        radii=np.array([R]),
        density=RHO,
        youngs_modulus=E,
        poisson_ratio=NU,
        restitution=0.5,
    )
    with pytest.raises(InvalidCalibrationError):
        tape.rollout_gradient(bad, 0.5, record_steps=10, dt=DT, device="cpu")


# ------------------------------------------------------------------ FR-011-19 / FR-011-21 Adam arm on the fake
#   simulator


def reference_adam_path(mu0: float, a: float, b: float, theta_star: float, lr: float, n: int, bounds=(0.1, 1.0)):
    beta1, beta2, eps = 0.9, 0.999, 1e-8
    mu, m, v = mu0, 0.0, 0.0
    path, grads = [mu], []
    for t in range(1, n + 1):
        g = 2.0 * (a + b * mu - theta_star) * b
        grads.append(g)
        m = beta1 * m + (1 - beta1) * g
        v = beta2 * v + (1 - beta2) * g * g
        step = lr * (m / (1 - beta1**t)) / (math.sqrt(v / (1 - beta2**t)) + eps)
        mu = min(max(mu - step, bounds[0]), bounds[1])
        path.append(mu)
    return path[:n], grads


@pytest.mark.req("FR-011-19")
def test_the_iterates_follow_adam_from_mu0_on_the_exact_gradient() -> None:
    a, b, theta_star = 24.0, 20.0, 24.0 + 20.0 * 0.30
    fake = FakeDem(a, b)
    res = tape.run_gradient_arm(fake, theta_star=theta_star, packing_seeds=SEEDS, budget=30, adam_lr=0.02)
    expected_path, expected_grads = reference_adam_path(0.55, a, b, theta_star, 0.02, 5)
    assert len(res.path) == 5  # 30 / 6 iterations
    assert res.path == pytest.approx(expected_path, rel=1e-9)
    assert res.gradients == pytest.approx(expected_grads, rel=1e-9)


@pytest.mark.req("FR-011-19")
def test_the_first_adam_step_moves_mu_by_the_learning_rate_against_the_gradient_sign() -> None:
    fake = FakeDem(24.0, 20.0)
    res = tape.run_gradient_arm(fake, theta_star=24.0 + 20.0 * 0.30, packing_seeds=SEEDS, budget=12, adam_lr=0.05)
    # g > 0 at mu0 = 0.55 (theta = 35 > theta* = 30); bias-corrected m / sqrt(v) = 1 at the first step
    assert res.path[1] == pytest.approx(0.55 - 0.05, rel=1e-6)


@pytest.mark.req("FR-011-19")
def test_the_iterates_never_leave_the_bounds() -> None:
    fake = FakeDem(24.0, 20.0)
    res = tape.run_gradient_arm(fake, theta_star=24.0 + 20.0 * 5.0, packing_seeds=SEEDS, budget=60, adam_lr=0.5)
    assert all(0.1 <= mu <= 1.0 for mu in res.path)
    assert max(res.path) == 1.0  # driven against the upper bound
    assert all(0.1 <= mu <= 1.0 for mu, _ in fake.grad_calls)


@pytest.mark.req("FR-011-21")
def test_one_iteration_costs_three_forward_equivalents_per_heap_and_the_budget_is_never_exceeded() -> None:
    fake = FakeDem(24.0, 0.0)
    res = tape.run_gradient_arm(fake, theta_star=24.0 + 40.0, packing_seeds=SEEDS, budget=60)  # flat: cannot converge
    assert res.stop_reason == "budget"
    assert res.simulations == 60  # 10 iterations x 2 heaps x 3
    assert len(fake.grad_calls) == 20
    assert fake.equivalent_simulations == res.simulations


@pytest.mark.req("FR-011-21")
@pytest.mark.parametrize("budget", [6, 17, 30])
def test_a_partial_iteration_is_never_started(budget: int) -> None:
    fake = FakeDem(24.0, 20.0)
    res = tape.run_gradient_arm(fake, theta_star=24.0 + 20.0 * 0.3, packing_seeds=SEEDS, budget=budget)
    assert res.simulations == 6 * (budget // 6)
    assert res.simulations == fake.equivalent_simulations
    assert res.simulations <= budget


@pytest.mark.req("FR-011-21")
def test_a_converged_start_stops_on_the_loss_tolerance_after_one_iteration() -> None:
    fake = FakeDem(24.0, 0.0)
    res = tape.run_gradient_arm(fake, theta_star=24.0, packing_seeds=SEEDS)
    assert res.stop_reason == "loss-tolerance"
    assert res.simulations == 6
    assert res.mu_hat == pytest.approx(0.55, rel=1e-12)
    assert res.best_loss == 0.0


@pytest.mark.req("FR-011-21")
def test_the_best_evaluated_iterate_is_returned_and_the_run_is_reproducible() -> None:
    a, b, theta_star = 24.0, 20.0, 24.0 + 20.0 * 0.40

    def go():
        return tape.run_gradient_arm(FakeDem(a, b, sigma=0.2), theta_star=theta_star, packing_seeds=SEEDS, adam_lr=0.1)

    res = go()
    fake = FakeDem(a, b, sigma=0.2)
    losses = [fake.loss(mu, SEEDS, theta_star) for mu in res.path]
    assert res.mu_hat == pytest.approx(res.path[int(np.argmin(losses))], rel=1e-12)
    assert res.best_loss == pytest.approx(min(losses), rel=1e-9, abs=1e-12)
    again = go()
    assert again.path == res.path
    assert again.mu_hat == res.mu_hat
    assert isinstance(res.wall_time_s, float)
    assert res.wall_time_s >= 0.0
