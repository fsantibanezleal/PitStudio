"""Smoke test of the Warp heap simulator of the calibration driver on the CPU device (not a locked test).

A small column of grains collapses and settles; the checks are the ones the driver relies on: the angle is a finite repose angle,
the same call repeats bitwise, a higher sliding friction does not give a flatter heap, and the tape gradient has the sign and the
order of magnitude of a central finite difference of the forward angle (the gate of FR-011-23 decides on the real runs, on repeated
runs; this only guards against a broken adjoint).
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

pytest.importorskip("warp")

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.calibration.simulator import HeapSimulator, column_scene  # noqa: E402


def small(**kw) -> HeapSimulator:
    args = {
        "particle_count": 120,
        "radius_m": 0.005,
        "settle_steps": 14000,
        "window_steps": 150,
        "dt": 2.0e-5,
        "device": "cpu",
        "column_radius_over_r": 5.0,
    }
    args.update(kw)
    return HeapSimulator(**args)


@pytest.fixture(scope="module")
def sim() -> HeapSimulator:
    return small()


def test_the_column_is_reproducible_by_seed_and_the_seed_changes_it() -> None:
    from pitstudio_studio.physics.calibration.simulator import HeapMaterial

    a = column_scene(40, 0.005, HeapMaterial(), 3)
    b = column_scene(40, 0.005, HeapMaterial(), 3)
    c = column_scene(40, 0.005, HeapMaterial(), 4)
    assert (a.positions == b.positions).all()
    assert not (a.positions == c.positions).all()
    assert a.positions[:, 2].min() > 0.005  # above the plate, no initial overlap with it


def test_theta_is_a_finite_angle_and_repeats_bitwise(sim: HeapSimulator) -> None:
    first = sim.theta(0.5, 11)
    assert 0.0 < first < 90.0
    assert sim.theta(0.5, 11) == first
    assert sim.hard_theta(0.5, 11) > 0.0


def test_more_friction_does_not_flatten_the_heap(sim: HeapSimulator) -> None:
    assert sim.theta(0.9, 11) >= sim.theta(0.2, 11) - 1.0


def test_the_tape_gradient_matches_the_finite_difference_of_the_recorded_window(sim: HeapSimulator) -> None:
    """The tape differentiates the recorded window only (FR-011-19): the settled heap is an input. Its gradient must equal the
    central difference of the angle when mu changes in the window alone; the response through the settling phase (a heap that
    formed at another friction) is not in it, which is why the gate of FR-011-23 checks the gradient against full re-runs."""
    from pitstudio.calibration import observables as obs
    from pitstudio_studio.physics.calibration import tape

    mu, h = 0.5, 0.2
    scene = sim._scene(11)
    dem, x, v, w = tape._settle(scene, mu, sim.settle_steps, sim.dt, "cpu")
    d = 2.0 * sim.radius_m
    axis = (float(x[:, 0].mean()), float(x[:, 1].mean()))
    bins = obs.freeze_bin_range(x, d=d, axis_xy=axis)

    def window_theta(m: float) -> float:
        _, end, _, _ = tape._settle_continue(tape._Dem(scene, m, sim.dt, "cpu"), (x, v, w), m, sim.window_steps, "cpu")
        return obs.smooth_repose_deg(end, d=d, axis_xy=axis, bin_range=bins)

    fd_window = (window_theta(mu + h) - window_theta(mu - h)) / (2 * h)
    theta, grad = sim.theta_and_grad(mu, 11)
    assert theta == pytest.approx(sim.theta(mu, 11), abs=1e-4)
    assert grad == pytest.approx(fd_window, abs=0.004)
