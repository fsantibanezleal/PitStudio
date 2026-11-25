"""An open boundary of the shallow-water solver lets water leave and never makes water (spec 005, FR-005-28).

Found by the first CPU run of case C2: with the depth copied and the bed continued linearly beyond the edge, an
edge cell on
terrain that rises outwards faced a ghost cell with a higher free surface and pulled water into the domain (634,000
m3 entered
a domain into which 100,000 m3 had been released). The rule tested here: the ghost bed is never higher than the
edge cell's,
and a velocity pointing into the domain meets a reflective ghost, so the volume that enters through an open
boundary is zero
unless the boundary is an inflow. Oracle: the exact volume balance of the finite-volume update and the sign of the
flux.
"""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.swe import Breach, SweParams, SweSimulation  # noqa: E402

ALL_OPEN = {"x-min": "open", "x-max": "open", "y-min": "open", "y-max": "open"}


def bowl(n=24, rise=0.6):
    """Terrain that rises towards every edge: a bowl whose rim is the domain boundary."""
    j, i = np.mgrid[0:n, 0:n]
    return rise * (np.hypot(i - (n - 1) / 2, j - (n - 1) / 2))


def test_a_pond_in_a_bowl_with_open_edges_never_gains_water():
    z = bowl()
    h0 = np.maximum(0.0, 8.0 - z)  # a pond whose surface is above the rim bed on the sides: the edge cells are wet
    s = SweSimulation(z, h0, dx=2.0, boundaries=ALL_OPEN, device="cpu")
    top = [s.volume()]
    s.advance(60.0, between=lambda sm: top.append(max(top[-1], sm.volume())))
    assert max(top) <= s.initial_volume() * (1 + 1e-12)
    assert s.boundary_outflow() >= -1e-12 * s.initial_volume()  # nothing entered
    assert s.h.min() >= 0.0


def test_a_breach_on_a_rim_slope_conserves_what_was_released_through_open_edges():
    z = bowl(20, 1.0)
    br = Breach(cells=[(18, 10)], volume=2000.0, peak_discharge=20.0)  # one cell from the north edge
    s = SweSimulation(
        z, np.zeros_like(z), dx=5.0, boundaries=ALL_OPEN, breach=br, params=SweParams(max_dt=0.5), device="cpu"
    )
    s.advance(400.0)
    assert s.injected_volume() > 1900.0
    assert s.volume() <= s.injected_volume() * (1 + 1e-12)
    assert s.boundary_outflow() >= -1e-12 * s.injected_volume()
    assert abs(s.balance_residual()) <= 1e-12


def test_an_inflowing_velocity_at_an_open_edge_brings_no_water_in():
    n = 12
    z = np.zeros((n, n))
    h0 = np.full((n, n), 0.5)
    qx = np.full((n, n), 0.4)  # everything moves towards +x: the x-min edge sees flow into the domain
    s = SweSimulation(z, h0, dx=1.0, boundaries={"x-min": "open"}, momentum=(qx, np.zeros((n, n))), device="cpu")
    s.advance(0.05)
    out = s.boundary_outflow()
    assert out <= 0.0 + 1e-15 or abs(out) < 1e-12  # water does not enter through an open edge
    assert s.volume() <= s.initial_volume() * (1 + 1e-12)
