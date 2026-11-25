"""T-005-030 - FR-005-23, FR-005-27: Rusanov flux, hydrostatic reconstruction, CFL step, positivity and dry threshold.

Oracles: a two-cell box whose first explicit step is worked by hand from the Rusanov formula (no solver code); the step
count of a lake at rest, where the wave speed sqrt(g h) is constant so dt = C_CFL dx / sqrt(g h) is known in closed
form;
the exact balance of volume in a closed domain.

Expected public API (module `pitstudio_studio.physics.swe`):
    SweParams(gravity, rho, tau_y, mu_b, cfl, h_dry, h_thr, max_dt)
    SweSimulation(bed, depth, *, dx, dy=None, params=None, boundaries=None, inflow=None, breach=None, device="cpu")
        .advance(t_end, between=None)   .time .steps .h .qx .qy  .volume() .clipped_volume() .balance_residual()
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.swe import SweParams, SweSimulation  # noqa: E402

G = 9.81
DEVICE = "cpu"


def sim(bed, depth, dx=1.0, **kw):
    return SweSimulation(np.asarray(bed, float), np.asarray(depth, float), dx=dx, device=DEVICE, **kw)


def test_first_step_of_two_cells_matches_the_rusanov_formula_by_hand():
    """Two cells (h = 2 and 1 m, flat bed, at rest, walls at both ends): one step of dt = C_CFL dx / sqrt(g h_max)."""
    hl, hr, dx, cfl = 2.0, 1.0, 1.0, 0.45
    a = max(math.sqrt(G * hl), math.sqrt(G * hr))  # Rusanov speed at the face (u = 0)
    dt = cfl * dx / a  # the largest wave speed of the domain is that of the deep cell
    f_mass = -0.5 * a * (hr - hl)  # F1 = 0.5 (0 + 0) - 0.5 a (hr - hl)
    f_mom = 0.5 * (0.5 * G * hl**2 + 0.5 * G * hr**2)  # F2 at the face; the dissipation of momentum is zero at rest
    wall_l, wall_r = 0.5 * G * hl**2, 0.5 * G * hr**2  # pressure flux at the reflective walls
    s = sim(np.zeros((1, 2)), [[hl, hr]], params=SweParams(cfl=cfl))
    s.advance(dt)
    assert s.steps == 1
    h, qx = s.h[0], s.qx[0]
    assert h[0] == pytest.approx(hl - dt / dx * f_mass, rel=1e-13)
    assert h[1] == pytest.approx(hr + dt / dx * f_mass, rel=1e-13)
    assert qx[0] == pytest.approx(-dt / dx * (f_mom - wall_l), rel=1e-13)
    assert qx[1] == pytest.approx(-dt / dx * (wall_r - f_mom), rel=1e-13)


@pytest.mark.parametrize("cfl", [0.2, 0.45, 0.5])
def test_the_step_is_the_cfl_step_of_the_largest_wave_speed(cfl):
    """Lake at rest, h = 1 m, dx = 2 m: every step is C_CFL dx / sqrt(g h), the last one clamped to the end time."""
    t_end, dx, h = 10.0, 2.0, 1.0
    dt = cfl * dx / math.sqrt(G * h)
    s = sim(np.zeros((3, 3)), np.full((3, 3), h), dx=dx, params=SweParams(cfl=cfl))
    s.advance(t_end)
    assert s.time == t_end
    assert s.steps == math.ceil(t_end / dt - 1e-9)


def test_a_step_shorter_than_the_cfl_step_ends_exactly_at_the_requested_time():
    s = sim(np.zeros((2, 2)), np.full((2, 2), 1.0))
    s.advance(0.01)
    assert (s.time, s.steps) == (0.01, 1)
    s.advance(0.02)
    assert (s.time, s.steps) == (0.02, 2)


def test_depth_stays_non_negative_and_no_water_is_clipped_on_a_rough_dam_break():
    rng = np.random.default_rng(7)
    bed = rng.uniform(0.0, 0.6, (24, 24))
    depth = np.where(rng.uniform(size=(24, 24)) < 0.3, rng.uniform(0.0, 2.0, (24, 24)), 0.0)
    s = sim(bed, depth, dx=1.0)
    worst = [np.inf]

    def watch(sm):
        worst[0] = min(worst[0], float(sm.h.min()))

    s.advance(8.0, between=watch)
    assert worst[0] >= 0.0
    assert s.clipped_volume() <= 1e-12 * s.initial_volume()
    assert abs(s.balance_residual()) <= 1e-12


def test_the_dry_threshold_zeroes_velocity_and_never_removes_water():
    """A film below h_dry on a flat bed keeps its volume and has no velocity; nothing is added or removed."""
    film = np.full((6, 6), 5.0e-5)
    film[2:4, 2:4] = 8.0e-5
    s = sim(np.zeros((6, 6)), film, params=SweParams(h_dry=1.0e-4))
    s.advance(5.0)
    assert math.isclose(s.volume(), s.initial_volume(), rel_tol=1e-13)
    assert np.all(s.qx == 0.0)
    assert np.all(s.qy == 0.0)
    assert s.h.min() > 0.0


def test_the_hydrostatic_reconstruction_makes_a_pond_on_a_step_a_steady_state():
    """Free surface 1 m over a bed with a 0.7 m step: the exact discrete steady state (Audusse et al. 2004)."""
    bed = np.zeros((4, 40))
    bed[:, 20:] = 0.7
    depth = np.maximum(0.0, 1.0 - bed)
    s = sim(bed, depth, dx=0.5)
    s.advance(20.0)
    assert np.abs(s.qx).max() <= 1e-12
    assert np.abs(s.qy).max() <= 1e-12
    assert np.abs(s.h - depth).max() <= 1e-13
