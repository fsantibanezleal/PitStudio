"""T-005-017 - P-005-01 ... P-005-06: metamorphic relations of the Warp DEM.

Each relation compares the DEM with itself under a transformation whose effect is known exactly (plan 005 test
strategy, "metamorphic"); no expected value comes from a single run of the code under test.
- P-005-01 Froude similarity (dimensional analysis of the Hertz-Mindlin law): lengths x lambda, times and dt
  x sqrt(lambda), E x lambda, with rho, nu, e, mu_s, mu_r and g fixed. Hertz force ~ E sqrt(R) delta^(3/2) ~ lambda^3,
  mass ~ rho lambda^3, so accelerations are unchanged and match g; damping ~ sqrt(S_n m) v ~ lambda^(5/2) lambda^(1/2);
  Rayleigh step ~ R sqrt(rho / G) ~ sqrt(lambda), so the scaled run is equally stable. Positions scale by lambda,
  velocities by sqrt(lambda), angular velocities by 1 / sqrt(lambda).
- P-005-02 translation invariance; P-005-03 rotation about the gravity axis by 90, 180, 270 deg (exact axis
  permutations of x and y; gravity along -z is unchanged); P-005-05 permutation of the particle array.
- P-005-04 time-step self-convergence |O(dt) - O(dt/2)| <= |O(2 dt) - O(dt)| and |O(dt) - O(dt/2)| <= 1 % of O for
  restitution, rolling acceleration and slot discharge, with dt from t_c/50 to t_c/400, t_c the elastic contact
  time of the FR-005-02 impact at 1 m/s (2.9433 delta_max / v0 = 5.55e-4 s; constant in closed form
  (2/5) B(2/5, 1/2) * 2, see T-005-011).
- P-005-06 monotonicity: raising mu_s or mu_r never lowers the repose angle (>= -0.5 deg); widening the orifice never
  lowers Q (>= -2 %).
Tolerances are the spec's (section 4): two-body P-005-01 rtol 1e-4, P-005-02 atol 1e-5 m, P-005-03 atol 1e-6 m;
pile observables P-005-01 +- 1 %, P-005-02 repose +- 0.5 deg and run-out +- 1 %, P-005-03 and P-005-05 +- 0.5 deg.
Pile observables: run-out = 99th percentile of the particles' horizontal distance from the column axis (spec 005
FR-005-14 definition); repose = `pitstudio_studio.physics.measure.repose_angle` (FR-005-13, T-005-016) about the
known axis. The 500-sphere pile, the rolling time-step series and the slot runs are marked `slow` (serial Warp CPU).

Expected public API: `pitstudio_studio.physics.dem.step` (DemMaterial, DemSimulation, Plane; T-005-011),
`pitstudio_studio.physics.measure.repose_angle` (T-005-016), and from `pitstudio_studio.physics.dem.benchmarks`:
    slot_discharge(slot_width_over_d: float, *, dt_scale: float = 1.0, device: str = "cpu") -> float
        the FR-005-11 quasi-2-D slot benchmark (box 30 d x 45 d, periodic over 4 d) with its benchmark material card,
        run at dt_scale times the benchmark's declared step; returns the steady flow rate per unit thickness
        Q [kg m^-1 s^-1]. Its internals and its own acceptance test belong to T-005-018; this file fixes only the
        signature used by the P-005-04 and P-005-06 relations.
"""

from __future__ import annotations

import functools
import math
import sys
from pathlib import Path

import numpy as np
import pytest
from hypothesis import given, settings
from hypothesis import strategies as st

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "studio" / "src"))  # studio lane package (uv `package = false`)

from pitstudio_studio.physics.dem.benchmarks import slot_discharge  # noqa: E402
from pitstudio_studio.physics.dem.step import DemMaterial, DemSimulation, Plane  # noqa: E402
from pitstudio_studio.physics.measure import repose_angle  # noqa: E402

DEVICE = "cpu"
G = 9.81
RHO = 2650.0
NU = 0.25

# ---------------------------------------------------------------- two-body scene (oblique impact with spin)
R = 5.0e-3
E = 50.0e6
DT2 = 2.0e-6  # s; Rayleigh limit 3.94e-5 s
SAMPLES = 10
EVERY = 500  # 10 samples over 10 ms; the contact lasts about 0.5 ms around t = 3.5 ms


def mat(e_mod: float = E, *, e: float = 0.5, mu_s: float = 0.5, mu_r: float = 0.1) -> DemMaterial:
    return DemMaterial(
        density=RHO, youngs_modulus=e_mod, poisson_ratio=NU, restitution=e, friction_static=mu_s,
        friction_rolling=mu_r,
    )  # fmt: skip


BASE_POS = np.array([[0.0, 0.0, 0.0], [2.5 * R, 0.8 * R, 0.3 * R]])
BASE_VEL = np.array([[1.0, 0.0, 0.0], [0.0, 0.0, 0.0]])
BASE_ANG = np.array([[0.0, 0.0, 30.0], [0.0, -10.0, 0.0]])


def two_body(pos, vel, ang, *, scale: float = 1.0):
    """Run the oblique two-body impact; returns stacked (SAMPLES, 2, 3) positions, velocities, angular velocities."""
    sim = DemSimulation(
        pos, np.full(2, R * scale), mat(E * scale), DT2 * math.sqrt(scale), velocities=vel, angular_velocities=ang,
        gravity=(0.0, 0.0, -G), device=DEVICE,
    )  # fmt: skip
    p, v, w = [], [], []
    for _ in range(SAMPLES):
        sim.step(EVERY)
        p.append(sim.positions)
        v.append(sim.velocities)
        w.append(sim.angular_velocities)
    return np.asarray(p, float), np.asarray(v, float), np.asarray(w, float)


@functools.cache
def base_two_body():
    return two_body(BASE_POS, BASE_VEL, BASE_ANG)


def rot_z(k: int) -> np.ndarray:
    """Exact rotation by k * 90 deg about z (integer matrix)."""
    c, s = [(1, 0), (0, 1), (-1, 0), (0, -1)][k % 4]
    return np.array([[c, -s, 0], [s, c, 0], [0, 0, 1]], dtype=float)


@pytest.mark.req("P-005-01")
def test_two_body_contact_happens_in_the_window() -> None:
    """Fixture check: the spheres do collide (the relations would be vacuous otherwise)."""
    p, v, _ = base_two_body()
    assert float(np.linalg.norm(v[-1, 1])) > 0.1  # sphere 1 started at rest and was hit
    gap0 = np.linalg.norm(BASE_POS[1] - BASE_POS[0]) - 2 * R
    assert gap0 > 0.0
    assert float(np.linalg.norm(p[-1, 1] - p[-1, 0])) > 2 * R  # and separated again


@pytest.mark.req("P-005-01")
@pytest.mark.parametrize("lam", [0.5, 2.0, 10.0])
def test_froude_similarity_two_body(lam: float) -> None:
    p1, v1, w1 = base_two_body()
    pl, vl, wl = two_body(BASE_POS * lam, BASE_VEL * math.sqrt(lam), BASE_ANG / math.sqrt(lam), scale=lam)
    np.testing.assert_allclose(pl / lam, p1, rtol=1e-4, atol=1e-4 * R)
    np.testing.assert_allclose(vl / math.sqrt(lam), v1, rtol=1e-4, atol=1e-4 * 1.0)
    np.testing.assert_allclose(wl * math.sqrt(lam), w1, rtol=1e-4, atol=1e-4 * 30.0)


@pytest.mark.req("P-005-02")
@settings(max_examples=20, deadline=None)
@given(
    direction=st.lists(st.floats(-1.0, 1.0), min_size=3, max_size=3).filter(lambda u: np.linalg.norm(u) > 1e-3),
    length=st.floats(0.0, 100.0),
)
def test_translation_invariance_two_body(direction, length) -> None:
    shift = np.asarray(direction) / np.linalg.norm(direction) * length
    p1, _, _ = base_two_body()
    ps, _, _ = two_body(BASE_POS + shift, BASE_VEL, BASE_ANG)
    np.testing.assert_allclose(ps - shift, p1, rtol=0.0, atol=1e-5)


@pytest.mark.req("P-005-02")
@pytest.mark.parametrize("shift", [(100.0, 0.0, 0.0), (57.735, -57.735, 57.735), (0.0, 0.0, -100.0)])
def test_translation_invariance_two_body_largest_shifts(shift) -> None:
    s = np.asarray(shift)
    p1, _, _ = base_two_body()
    ps, _, _ = two_body(BASE_POS + s, BASE_VEL, BASE_ANG)
    np.testing.assert_allclose(ps - s, p1, rtol=0.0, atol=1e-5)


@pytest.mark.req("P-005-03")
@pytest.mark.parametrize("k", [1, 2, 3])
def test_rotation_invariance_two_body(k: int) -> None:
    q = rot_z(k)
    p1, _, _ = base_two_body()
    pr, _, _ = two_body(BASE_POS @ q.T, BASE_VEL @ q.T, BASE_ANG @ q.T)
    np.testing.assert_allclose(pr, p1 @ q.T, rtol=0.0, atol=1e-6)


# ---------------------------------------------------------------- P-005-04 time-step convergence

T_C = (2.0 * 0.4 * math.gamma(0.4) * math.gamma(0.5) / math.gamma(0.9)) * (
    15.0 * (RHO * 4.0 / 3.0 * math.pi * R**3 / 2.0) / (16.0 * (E / (2.0 * (1.0 - NU**2))) * math.sqrt(R / 2.0))
) ** 0.4  # = 2.9433 * delta_max / v0 at v0 = 1 m/s: 5.55e-4 s


def converges(o2: float, o1: float, oh: float) -> None:
    """|O(dt) - O(dt/2)| <= |O(2dt) - O(dt)| and |O(dt) - O(dt/2)| <= 1 % of O."""
    assert abs(o1 - oh) <= abs(o2 - o1), f"not converging: O(2dt)={o2}, O(dt)={o1}, O(dt/2)={oh}"
    assert abs(o1 - oh) <= 0.01 * abs(o1), f"step error above 1 %: O(dt)={o1}, O(dt/2)={oh}"


def restitution_at(dt: float, e: float = 0.5, v0: float = 1.0) -> float:
    sim = DemSimulation(
        np.array([[-R, 0.0, 0.0], [R, 0.0, 0.0]]), np.full(2, R), mat(e=e, mu_s=0.0, mu_r=0.0), dt,
        velocities=np.array([[0.5 * v0, 0.0, 0.0], [-0.5 * v0, 0.0, 0.0]]), gravity=(0.0, 0.0, 0.0), device=DEVICE,
    )  # fmt: skip
    sim.step(round(3.0 * T_C / dt))  # contact over well before 3 t_c
    v = sim.velocities
    return float(v[1, 0] - v[0, 0]) / v0


@pytest.mark.req("P-005-04")
def test_time_step_convergence_of_restitution() -> None:
    e = {k: restitution_at(T_C / k) for k in (50, 100, 200, 400)}
    converges(e[50], e[100], e[200])
    converges(e[100], e[200], e[400])


def rolling_acceleration_at(dt: float, ratio: float = 2.0, mu_r: float = 0.1) -> float:
    theta = math.atan(ratio * mu_r)
    e_wall = E / (2.0 * (1.0 - NU**2))
    m = RHO * 4.0 / 3.0 * math.pi * R**3
    z0 = R - (m * G * math.cos(theta) / (4.0 / 3.0 * e_wall * math.sqrt(R))) ** (2.0 / 3.0)
    sim = DemSimulation(
        np.array([[0.0, 0.0, z0]]), np.array([R]), mat(mu_s=0.5, mu_r=mu_r), dt,
        gravity=(G * math.sin(theta), 0.0, -G * math.cos(theta)),
        walls=(Plane(point=(0.0, 0.0, 0.0), normal=(0.0, 0.0, 1.0)),), device=DEVICE,
    )  # fmt: skip
    sim.step(round(0.15 / dt))
    t, v = [], []
    for _ in range(16):  # 0.15 ... 0.30 s
        t.append(sim.time)
        v.append(float(sim.velocities[0, 0]))
        sim.step(round(0.01 / dt))
    return float(np.polyfit(np.asarray(t), np.asarray(v), 1)[0])


@pytest.mark.slow
@pytest.mark.req("P-005-04")
def test_time_step_convergence_of_rolling_acceleration() -> None:
    a = {k: rolling_acceleration_at(T_C / k) for k in (50, 100, 200)}
    converges(a[50], a[100], a[200])


@pytest.mark.slow
@pytest.mark.req("P-005-04")
def test_time_step_convergence_of_slot_discharge() -> None:
    q = {s: slot_discharge(6.0, dt_scale=s, device=DEVICE) for s in (1.0, 0.5, 0.25)}
    converges(q[1.0], q[0.5], q[0.25])


# ---------------------------------------------------------------- 500-sphere pile

D = 0.01  # m
E_PILE = 5.0e6  # Pa; Rayleigh limit 0.2 * 6.23e-4 s = 1.25e-4 s
DT_PILE = 5.0e-5
T_PILE = 1.5  # s
N_PILE = 500


def column(seed: int = 0) -> np.ndarray:
    """500 sphere centres of a column on the floor, axis at the origin.

    Square lattice of pitch 1.05 d, centres within 3 d of the axis (25 per layer, 20 layers, height about 21 d),
    with a seeded horizontal jitter of +- 0.02 d.
    """
    rng = np.random.default_rng(seed)
    pitch = 1.05 * D
    k = np.arange(-4, 5)
    pts = [(x * pitch, y * pitch) for x in k for y in k if math.hypot(x * pitch, y * pitch) <= 3.5 * D - D / 2]
    out = []
    layer = 0
    while len(out) < N_PILE:
        out.extend((x, y, D / 2 + 0.002 * D + layer * pitch) for x, y in pts)
        layer += 1
    p = np.asarray(out[:N_PILE])
    return p + rng.uniform(-0.02 * D, 0.02 * D, p.shape) * np.array([1.0, 1.0, 0.0])


def pile(
    pos: np.ndarray, *, scale: float = 1.0, shift=(0.0, 0.0, 0.0), mu_s: float = 0.5, mu_r: float = 0.1
) -> tuple[np.ndarray, np.ndarray]:
    """Collapse the column on a floor; returns final positions and radii (in the frame of the run)."""
    s = np.asarray(shift, float)
    radii = np.full(len(pos), D / 2 * scale)
    sim = DemSimulation(
        pos * scale + s, radii, mat(E_PILE * scale, mu_s=mu_s, mu_r=mu_r), DT_PILE * math.sqrt(scale),
        gravity=(0.0, 0.0, -G), walls=(Plane(point=tuple(s), normal=(0.0, 0.0, 1.0)),), device=DEVICE,
    )  # fmt: skip
    sim.step(round(T_PILE / DT_PILE))
    return sim.positions, radii


def observables(pos: np.ndarray, radii: np.ndarray, axis=(0.0, 0.0), z0: float = 0.0) -> tuple[float, float]:
    rel = pos - np.array([axis[0], axis[1], z0])
    runout = float(np.percentile(np.hypot(rel[:, 0], rel[:, 1]), 99.0))
    repose = float(repose_angle(rel, radii, geometry="cone", axis_xy=(0.0, 0.0)))
    return repose, runout


@functools.cache
def base_pile() -> tuple[float, float]:
    return observables(*pile(column()))


@pytest.mark.slow
@pytest.mark.req("P-005-01")
@pytest.mark.parametrize("lam", [0.5, 2.0, 10.0])
def test_froude_similarity_pile(lam: float) -> None:
    repose1, runout1 = base_pile()
    pos, radii = pile(column(), scale=lam)
    repose_l, runout_l = observables(pos, radii)
    assert repose_l == pytest.approx(repose1, rel=0.01)
    assert runout_l / lam == pytest.approx(runout1, rel=0.01)


@pytest.mark.slow
@pytest.mark.req("P-005-02")
def test_translation_invariance_pile() -> None:
    repose1, runout1 = base_pile()
    shift = (57.735, -57.735, 57.735)  # |shift| = 100 m
    pos, radii = pile(column(), shift=shift)
    repose_s, runout_s = observables(pos, radii, axis=shift[:2], z0=shift[2])
    assert abs(repose_s - repose1) <= 0.5
    assert runout_s == pytest.approx(runout1, rel=0.01)


@pytest.mark.slow
@pytest.mark.req("P-005-03")
@pytest.mark.parametrize("k", [1, 2, 3])
def test_rotation_invariance_pile(k: int) -> None:
    repose1, _ = base_pile()
    pos, radii = pile(column() @ rot_z(k).T)
    repose_r, _ = observables(pos, radii)
    assert abs(repose_r - repose1) <= 0.5


@pytest.mark.slow
@pytest.mark.req("P-005-05")
@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_permutation_invariance_pile(seed: int) -> None:
    repose1, _ = base_pile()
    perm = np.random.default_rng(seed).permutation(N_PILE)
    pos, radii = pile(column()[perm])
    repose_p, _ = observables(pos, radii)
    assert abs(repose_p - repose1) <= 0.5


@pytest.mark.slow
@pytest.mark.req("P-005-06")
@pytest.mark.parametrize(("mu_s", "mu_r"), [(0.8, 0.1), (0.5, 0.3)])
def test_more_friction_never_lowers_the_repose_angle(mu_s: float, mu_r: float) -> None:
    repose1, _ = base_pile()
    repose_f, _ = observables(*pile(column(), mu_s=mu_s, mu_r=mu_r))
    assert repose_f >= repose1 - 0.5


@pytest.mark.slow
@pytest.mark.req("P-005-06")
def test_wider_orifice_never_lowers_the_discharge() -> None:
    q4 = slot_discharge(4.0, device=DEVICE)
    q6 = slot_discharge(6.0, device=DEVICE)
    assert q4 > 0.0
    assert q6 >= 0.98 * q4
