"""T-005-031 - FR-005-24, FR-005-25, P-005-19: Ritter and Stoker dam breaks with grid convergence, and a 2-D radial dam break.

Oracles (the solver is never the reference):
- Ritter dry-bed fan and Stoker wet-bed middle state and bore: the closed forms of the SWASHES compilation (Delestre et
  al., Int. J. Numer. Methods Fluids 72(3), 2013, DOI 10.1002/fld.3741, sections 4.1.1 and 4.1.2); the Stoker middle state
  is the root found with SciPy `brentq`.
- the radial case: an independent axisymmetric finite-volume solver written here in NumPy on 4000 cells.
The 1-D problems run in a channel 4 cells wide with reflective walls (x in [0, 10] m, x0 = 5 m, t = 6 s).
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.optimize import brentq

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))

from pitstudio_studio.physics.swe import SweParams, SweSimulation  # noqa: E402

G, HL, X0, LEN, T = 9.81, 0.005, 5.0, 10.0, 6.0
CELLS = (400, 800, 1600)


def channel(n, hr, h_dry=1.0e-4):
    dx = LEN / n
    x = (np.arange(n) + 0.5) * dx
    h0 = np.where(x < X0, HL, hr)[None, :].repeat(4, axis=0)
    s = SweSimulation(np.zeros((4, n)), h0, dx=dx, params=SweParams(h_dry=h_dry), device="cpu")
    s.advance(T)
    return x, dx, s.h[1]


def ritter(x):
    c0 = math.sqrt(G * HL)
    xi = (x - X0) / T
    return np.where(xi < -c0, HL, np.where(xi < 2 * c0, (2 * c0 - xi) ** 2 / (9 * G), 0.0))


def stoker_state(hr):
    cl = math.sqrt(G * HL)
    f = lambda cm: -8 * G * hr * cm**2 * (cl - cm) ** 2 + (cm**2 - G * hr) ** 2 * (cm**2 + G * hr)  # noqa: E731
    cm = brentq(f, math.sqrt(G * hr) * (1 + 1e-9), cl)
    bore = X0 + T * 2 * cm**2 * (cl - cm) / (cm**2 - G * hr)
    fan_end = X0 + T * (2 * cl - 3 * cm)
    return cl, cm, cm**2 / G, bore, fan_end


def stoker(x, hr):
    cl, _, hm, bore, fan_end = stoker_state(hr)
    xi = (x - X0) / T
    fan = 4 / (9 * G) * (cl - xi / 2) ** 2
    return np.where(x < X0 - cl * T, HL, np.where(x < fan_end, fan, np.where(x < bore, hm, hr)))


def l1(h, ref):
    return float(np.abs(h - ref).sum() / np.abs(ref).sum())


@pytest.fixture(scope="module")
def ritter_runs():
    # The default h_dry (1e-4 m) is 2 % of h_l: it freezes the thin leading tail of the dry-bed fan, so the benchmark
    # declares h_dry = 1e-8 m (FR-005-27 gives 1e-4 m as the default only). Stoker keeps the default.
    return {n: channel(n, 0.0, h_dry=1.0e-8) for n in CELLS}


@pytest.fixture(scope="module")
def stoker_runs():
    return {n: channel(n, 0.001) for n in CELLS}


def test_ritter_l1_error_at_400_cells_is_within_five_percent(ritter_runs):
    x, _, h = ritter_runs[400]
    assert l1(h, ritter(x)) <= 0.05


def front_error(ritter_run, level):
    """Relative error of the wet front, the last cell with h > level h_l, against the analytical travel distance to the
    point where the Ritter depth equals level h_l, (2 - 3 sqrt(level)) c0 t."""
    x, _, h = ritter_run
    c0 = math.sqrt(G * HL)
    travel = (2.0 - 3.0 * math.sqrt(level)) * c0 * T
    front = x[np.where(h > level * HL)[0][-1]]
    return ((front - X0) - travel) / travel


def test_ritter_wet_front_at_a_tenth_of_the_left_depth_is_within_five_percent(ritter_runs):
    for n in CELLS:
        assert abs(front_error(ritter_runs[n], 0.1)) <= 0.05, n


def test_ritter_wet_front_at_the_spec_threshold_lags_and_converges():
    """FINDING against FR-005-24: the specified threshold is 1e-3 h_l with +-5 %. A first-order Rusanov scheme smears the
    tip of the fan: an independent NumPy implementation of the same scheme gives the same front (-20.5 % at 400 cells), so
    the tolerance is not attainable by FR-005-23's scheme. This test pins what the solver does (the lag shrinks with the
    grid and stays below 25 %, 20 % and 15 %), and the report asks the owner how to restate FR-005-24."""
    runs = {n: channel(n, 0.0, h_dry=1.0e-8) for n in CELLS}
    err = [front_error(runs[n], 1.0e-3) for n in CELLS]
    assert all(e < 0 for e in err)
    assert abs(err[0]) > abs(err[1]) > abs(err[2])
    assert [abs(e) <= b for e, b in zip(err, (0.25, 0.20, 0.15), strict=True)] == [True] * 3


def test_ritter_error_decreases_with_order_at_least_half(ritter_runs):
    e = [l1(ritter_runs[n][2], ritter(ritter_runs[n][0])) for n in CELLS]
    assert e[0] > e[1] > e[2]
    assert all(math.log2(e[k] / e[k + 1]) >= 0.5 for k in (0, 1))


def test_stoker_l1_error_at_400_cells_is_within_five_percent(stoker_runs):
    x, _, h = stoker_runs[400]
    assert l1(h, stoker(x, 0.001)) <= 0.05


def test_stoker_middle_state_and_bore_position(stoker_runs):
    _, _, hm, bore, fan_end = stoker_state(0.001)
    for n in CELLS:
        x, dx, h = stoker_runs[n]
        plateau = h[(x > fan_end + 0.2) & (x < bore - 0.2)]
        assert abs(plateau.mean() - hm) <= 0.02 * hm, n
        level = 0.5 * (hm + 0.001)  # the bore sits where the depth crosses the middle of its jump
        k = np.where((h[:-1] > level) & (h[1:] <= level) & (x[:-1] > fan_end))[0][-1]
        xb = x[k] + (h[k] - level) / (h[k] - h[k + 1]) * dx
        assert abs(xb - bore) <= 0.02 * (bore - X0), n


def test_stoker_error_decreases_monotonically_with_resolution(stoker_runs):
    e = [l1(stoker_runs[n][2], stoker(stoker_runs[n][0], 0.001)) for n in CELLS]
    assert e[0] > e[1] > e[2]
    assert all(math.log2(e[k] / e[k + 1]) >= 0.5 for k in (0, 1))


# -- radial dam break against an independent axisymmetric solver -----------------------------------------------------
H_IN, H_OUT, R0, T_RADIAL = 0.5, 0.2, 2.0, 1.2


def radial_reference(n=4000, r_max=10.0):
    """Axisymmetric shallow water, d(r h)/dt + d(r h u)/dr = 0 and the momentum equation with the geometric source
    g h^2 / 2, by Rusanov fluxes in conservative variables (r h, r h u); an independent implementation."""
    dr = r_max / n
    r = (np.arange(n) + 0.5) * dr
    re = np.arange(n + 1) * dr  # face radii
    h = np.where(r < R0, H_IN, H_OUT)
    q = np.zeros(n)
    t = 0.0
    while t < T_RADIAL - 1e-12:
        u = q / h
        dt = min(0.4 * dr / np.max(np.abs(u) + np.sqrt(G * h)), T_RADIAL - t)
        hl_, hr_ = np.concatenate(([h[0]], h)), np.concatenate((h, [h[-1]]))
        ql, qr = np.concatenate(([-q[0]], q)), np.concatenate((q, [-q[-1]]))  # walls at r = 0 and r = r_max
        ul, ur = ql / hl_, qr / hr_
        a = np.maximum(np.abs(ul) + np.sqrt(G * hl_), np.abs(ur) + np.sqrt(G * hr_))
        f1 = 0.5 * (hl_ * ul + hr_ * ur) - 0.5 * a * (hr_ - hl_)
        f2 = 0.5 * (hl_ * ul**2 + 0.5 * G * hl_**2 + hr_ * ur**2 + 0.5 * G * hr_**2) - 0.5 * a * (hr_ * ur - hl_ * ul)
        h = h - dt / (r * dr) * (re[1:] * f1[1:] - re[:-1] * f1[:-1])
        q = q - dt / (r * dr) * (re[1:] * f2[1:] - re[:-1] * f2[:-1]) + dt * 0.5 * G * (h * h) / r
        t += dt
    return r, h


def test_radial_dam_break_matches_the_axisymmetric_reference_and_is_symmetric():
    n, dx = 100, 0.2  # a 20 m square, the dam at its centre
    xc = (np.arange(n) + 0.5) * dx - 0.5 * n * dx
    rr = np.hypot(*np.meshgrid(xc, xc))
    s = SweSimulation(np.zeros((n, n)), np.where(rr < R0, H_IN, H_OUT), dx=dx, device="cpu")
    s.advance(T_RADIAL)
    h = s.h
    r_ref, h_ref = radial_reference()
    ref_at_cells = np.interp(rr, r_ref, h_ref)
    assert float(np.abs(h - ref_at_cells).sum() / ref_at_cells.sum()) <= 0.03
    assert np.abs(h - h.T).max() <= 1e-12 and np.abs(h - h[::-1, :]).max() <= 1e-12  # square-grid symmetry
    assert math.isclose(s.volume(), s.initial_volume(), rel_tol=1e-13)
