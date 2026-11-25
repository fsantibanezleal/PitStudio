"""T-005-032 - FR-005-26, FR-005-28: lake at rest over benched terrain; volume conservation with sources and open
boundaries.

Oracles: exact identities and closed forms, never the solver: a free surface of constant height over any terrain is a
steady state (velocities stay at round-off); the volume balance V(t) = V0 + injected - outflow is an identity of the
finite-volume update (every face flux is added to one cell and subtracted from its neighbour), so the residual is
round-off; a triangular hydrograph integrates to its volume.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.swe import Breach, SweParams, SweSimulation  # noqa: E402

G = 9.81


def benched_terrain(n=128):
    """Terraces 0.5 m high and 16 cells wide, a ramp, a pit and a ridge above the lake: steps and dry cells."""
    j, i = np.mgrid[0:n, 0:n]
    z = 0.5 * (i // 16) + 0.3 * np.sin(j / 9.0)
    z[40:60, 60:90] -= 1.2  # a pit
    z[100:110, :] += 4.0  # a ridge standing above the free surface
    return z


def test_lake_at_rest_over_benched_terrain_128_squared_stays_at_rest_for_1000_steps():
    z = benched_terrain()
    eta = 2.6  # constant free surface
    h0 = np.maximum(0.0, eta - z)
    s = SweSimulation(z, h0, dx=2.0, device="cpu")
    dt = 0.45 * 2.0 / math.sqrt(G * h0.max())
    t_end = 1000 * dt * 1.02  # a few more than 1000 steps
    s.advance(t_end)
    assert s.steps >= 1000
    speed = np.hypot(s.qx, s.qy) / np.maximum(s.h, 1e-300)
    assert np.where(s.h > 0, speed, 0.0).max() <= 1e-3  # FR-005-26: well below, round-off
    assert s.h.min() >= 0.0
    assert np.abs(s.h - h0).max() <= 1e-9
    assert math.isclose(s.volume(), s.initial_volume(), rel_tol=1e-12)


def test_closed_domain_conserves_volume_over_ten_thousand_steps():
    rng = np.random.default_rng(3)
    z = rng.uniform(0.0, 0.4, (12, 12))
    h0 = np.where(rng.uniform(size=(12, 12)) < 0.4, rng.uniform(0.0, 1.0, (12, 12)), 0.0)
    s = SweSimulation(z, h0, dx=1.0, device="cpu")
    t = 0.0
    while s.steps < 10_000:
        t += 5.0
        s.advance(t)
    assert s.steps >= 10_000
    assert abs(s.volume() - s.initial_volume()) / s.initial_volume() <= 1e-10  # FR-005-28 asks 1e-5
    assert abs(s.balance_residual()) <= 1e-12


def test_open_boundary_volume_is_accumulated_and_the_balance_holds():
    n = 80
    x = (np.arange(n) + 0.5) * 0.25
    h0 = np.where(x < 5.0, 1.0, 0.0)[None, :].repeat(6, axis=0)
    s = SweSimulation(np.zeros((6, n)), h0, dx=0.25, boundaries={"x-max": "open"}, device="cpu")
    s.advance(12.0)
    out = s.boundary_outflow()
    assert out > 0.1 * s.initial_volume()  # the bore leaves through x-max
    assert abs(s.volume() - (s.initial_volume() - out)) <= 1e-12 * s.initial_volume()
    assert abs(s.balance_residual()) <= 1e-12


def test_breach_volume_and_open_boundary_balance_together():
    z = np.linspace(0.0, 1.0, 40)[None, :].repeat(10, axis=0)[:, ::-1].copy()  # slopes down to x-max
    br = Breach(cells=[(4, 2), (5, 2)], volume=500.0, peak_discharge=25.0)  # T = 40 s
    s = SweSimulation(
        z, np.zeros_like(z), dx=1.0, boundaries={"x-max": "open"}, breach=br, params=SweParams(max_dt=0.1)
    )
    s.advance(60.0)
    assert math.isclose(s.injected_volume(), 500.0, rel_tol=1e-12)
    assert s.boundary_outflow() > 0.0
    assert abs(s.balance_residual()) <= 1e-12


@settings(max_examples=12, deadline=None, suppress_health_check=[HealthCheck.too_slow])
@given(seed=st.integers(0, 10_000), shape=st.sampled_from([(8, 8), (6, 14), (16, 5)]), frac=st.floats(0.05, 0.6))
def test_property_random_terrain_keeps_depth_non_negative_and_the_balance_exact(seed, shape, frac):
    rng = np.random.default_rng(seed)
    z = rng.uniform(0.0, 1.0, shape)
    h0 = np.where(rng.uniform(size=shape) < frac, rng.uniform(0.0, 1.5, shape), 0.0)
    if not h0.any():
        h0[0, 0] = 1.0
    s = SweSimulation(z, h0, dx=1.0, boundaries={"x-max": "open"}, device="cpu")
    low = [np.inf]
    s.advance(10.0, between=lambda sm: low.__setitem__(0, min(low[0], float(sm.h.min()))))
    assert low[0] >= 0.0
    assert s.clipped_volume() <= 1e-12 * max(s.initial_volume(), 1.0)
    assert abs(s.balance_residual()) <= 1e-12


@settings(max_examples=12, deadline=None)
@given(
    volume=st.floats(10.0, 1e5),
    base=st.floats(20.0, 400.0),
    frac=st.floats(0.05, 0.95),
    steps=st.integers(1, 7),
)
def test_property_hydrograph_released_volume_is_exact_however_the_run_is_split(volume, base, frac, steps):
    """FR-005-31: the integral of the triangular hydrograph over the breach cells is V (rtol 1e-6), independent of the
    steps and of how the run is cut into `advance` calls. The box is sized so the released water is about 1 m deep."""
    z = np.zeros((5, 5))
    dx = math.sqrt(volume / 25.0)
    br = Breach(cells=[(2, 2), (2, 3), (3, 2)], volume=volume, peak_discharge=2.0 * volume / base, peak_fraction=frac)
    s = SweSimulation(z, np.zeros_like(z), dx=dx, breach=br, params=SweParams(max_dt=base / 40.0), device="cpu")
    end = 1.05 * base
    for k in range(1, steps + 1):
        s.advance(end * k / steps)
        assert math.isclose(s.injected_volume(), br.released(s.time), rel_tol=1e-9, abs_tol=1e-9)
    assert math.isclose(s.injected_volume(), volume, rel_tol=1e-6)
    assert math.isclose(s.volume(), volume, rel_tol=1e-9)  # a closed box keeps what was released


def test_lake_at_rest_breaks_without_the_hydrostatic_reconstruction_guard():
    """Sanity of the oracle: a surface that is not level is not at rest (the test above is not vacuous)."""
    z = benched_terrain(32)
    h0 = np.maximum(0.0, 2.6 - z)
    h0[10:14, 10:14] += 0.5  # a bump on the free surface
    s = SweSimulation(z, h0, dx=2.0, device="cpu")
    s.advance(4.0)
    assert np.abs(s.qx).max() > 1e-3
